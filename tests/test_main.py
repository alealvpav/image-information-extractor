import ntpath
import os
import types

import pytest

import csv_store
import main
from geo_extractor import get_media_files
from tests import builders as b


def answer(monkeypatch, *answers):
    """Simula lo que el usuario escribe en cada pregunta."""
    pending = iter(answers)
    monkeypatch.setattr('builtins.input', lambda prompt='': next(pending))


@pytest.fixture
def media_dir(tmp_path):
    folder = tmp_path / 'media'
    folder.mkdir()
    b.save_image(folder / 'foto.jpg')
    (folder / 'IMG_0001.MOV').write_bytes(b.iphone_mov())
    (folder / 'roto.mov').write_bytes(b'esto no es un video')
    return folder


def test_get_media_files_skips_hidden_subfolders_and_srt(tmp_path):
    for name in ('b.jpg', 'a.mp4', 'a.SRT', '.oculto.jpg'):
        (tmp_path / name).write_bytes(b'')
    (tmp_path / 'subcarpeta').mkdir()
    assert get_media_files(str(tmp_path)) == ['a.mp4', 'b.jpg']


def test_normalize_path_linux(monkeypatch):
    monkeypatch.setenv('HOME', '/home/yo')
    assert main.normalize_path("'/home/yo/Mis fotos'") == '/home/yo/Mis fotos'
    assert main.normalize_path('~/Fotos') == '/home/yo/Fotos'
    assert main.normalize_path('$HOME/Fotos') == '/home/yo/Fotos'


@pytest.mark.parametrize('typed, expected', [
    (r'"C:\Users\yo\Fotos de viaje"', r'C:\Users\yo\Fotos de viaje'),
    (r'%USERPROFILE%\Pictures', r'C:\Users\yo\Pictures'),
    (r'\\nas\fotos\2024', r'\\nas\fotos\2024'),
    ('C:/Users/yo/Fotos', r'C:\Users\yo\Fotos'),
])
def test_normalize_path_windows(monkeypatch, typed, expected):
    monkeypatch.setenv('USERPROFILE', r'C:\Users\yo')
    monkeypatch.setattr(main, 'os', types.SimpleNamespace(path=ntpath))
    assert main.normalize_path(typed) == expected


def test_new_csv(monkeypatch, media_dir, tmp_path, capsys):
    csv_path = tmp_path / 'salida.csv'
    answer(monkeypatch, str(media_dir), 'n', str(csv_path))
    main.main([])

    _, rows = csv_store.read_csv(csv_path)
    by_name = {r[csv_store.FILE_NAME_COLUMN]: r for r in rows}
    assert set(by_name) == {'foto.jpg', 'IMG_0001.MOV', 'roto.mov'}
    assert by_name['IMG_0001.MOV']['Model'] == 'iPhone 15 Pro'
    assert by_name['foto.jpg'][csv_store.FILE_TYPE_COLUMN] == 'image'
    assert by_name['roto.mov']['Latitude'] == ''
    assert 'No se ha podido leer roto.mov' in capsys.readouterr().out


def test_new_csv_does_not_overwrite_by_default(monkeypatch, media_dir, tmp_path):
    existing = tmp_path / 'existente.csv'
    existing.write_text('no tocar')
    other = tmp_path / 'otro'
    answer(monkeypatch, str(media_dir), 'n', str(existing), '', str(other))  # Enter = no sobrescribir
    main.main([])
    assert existing.read_text() == 'no tocar'
    assert os.path.exists(str(other) + '.csv')


def test_update_csv(monkeypatch, media_dir, tmp_path, capsys):
    csv_path = tmp_path / 'salida.csv'
    csv_store.write_csv(csv_path, [csv_store.build_row('otra.jpg', '/otra/otra.jpg', 'image', {})])
    answer(monkeypatch, str(media_dir), 'A', 'noexiste.csv', str(csv_path))
    main.main([])

    _, rows = csv_store.read_csv(csv_path)
    assert [r[csv_store.FILE_NAME_COLUMN] for r in rows] == ['otra.jpg', 'IMG_0001.MOV', 'foto.jpg', 'roto.mov']
    assert '3 archivos nuevos, 0 actualizados, 4 en total' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Argumentos de la línea de comandos
# ---------------------------------------------------------------------------

def no_questions(monkeypatch):
    def fail(prompt=''):
        raise AssertionError(f'No debería preguntar: {prompt}')
    monkeypatch.setattr('builtins.input', fail)


def test_args_new_csv_without_questions(monkeypatch, media_dir, tmp_path):
    no_questions(monkeypatch)
    main.main([str(media_dir), '--nuevo', str(tmp_path / 'viaje')])
    _, rows = csv_store.read_csv(tmp_path / 'viaje.csv')
    assert len(rows) == 3


def test_args_new_csv_existing_needs_overwrite(monkeypatch, media_dir, tmp_path):
    no_questions(monkeypatch)
    existing = tmp_path / 'viaje.csv'
    existing.write_text('no tocar')
    with pytest.raises(ValueError, match='--sobrescribir'):
        main.main([str(media_dir), '-n', str(existing)])
    assert existing.read_text() == 'no tocar'

    main.main([str(media_dir), '-n', str(existing), '-s'])
    assert len(csv_store.read_csv(existing)[1]) == 3


def test_args_update_csv(monkeypatch, media_dir, tmp_path, capsys):
    no_questions(monkeypatch)
    csv_path = tmp_path / 'viaje.csv'
    csv_store.write_csv(csv_path, [csv_store.build_row('otra.jpg', '/otra/otra.jpg', 'image', {})])
    main.main([str(media_dir), '--actualizar', str(csv_path)])
    assert '3 archivos nuevos, 0 actualizados, 4 en total' in capsys.readouterr().out


@pytest.mark.parametrize('args, message', [
    (['no/existe', '-n', 'x.csv'], 'no existe o no es una carpeta'),
    (['{media}', '-a', 'no_existe.csv'], 'no existe'),
    (['{media}', '-n', 'carpeta/que/no/existe/x.csv'], 'no existe'),
])
def test_args_errors_do_not_ask_again(monkeypatch, media_dir, tmp_path, args, message):
    no_questions(monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=message):
        main.main([a.format(media=media_dir) for a in args])


def test_args_update_rejects_foreign_csv(monkeypatch, media_dir, tmp_path):
    no_questions(monkeypatch)
    foreign = tmp_path / 'ajeno.csv'
    foreign.write_text('a,b\n1,2\n')
    with pytest.raises(ValueError, match='no es un CSV generado'):
        main.main([str(media_dir), '-a', str(foreign)])


@pytest.mark.parametrize('args', [['x', '-n', 'a.csv', '-a', 'b.csv'], ['x', '--sobrescribir']])
def test_args_invalid_combinations(args):
    with pytest.raises(SystemExit) as error:
        main.main(args)
    assert error.value.code == 2


def test_args_only_folder_asks_the_rest(monkeypatch, media_dir, tmp_path):
    asked = []
    answers = iter(['n', str(tmp_path / 'viaje.csv')])
    monkeypatch.setattr('builtins.input', lambda prompt='': asked.append(prompt) or next(answers))
    main.main([str(media_dir)])
    assert not any('carpeta' in prompt for prompt in asked)
    assert (tmp_path / 'viaje.csv').exists()
