import string

import pytest

import csv_store
import main
from geo_extractor import get_media_info, i18n
from tests import builders as b


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.mark.parametrize('key', i18n.MESSAGES)
def test_every_message_has_both_languages_with_same_placeholders(key):
    translations = i18n.MESSAGES[key]
    assert set(translations) == set(i18n.SUPPORTED_LANGUAGES)
    assert placeholders(translations['es']) == placeholders(translations['en'])


# ---------------------------------------------------------------------------
# Detección del idioma
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('variables, expected', [
    ({'LANG': 'es_ES.UTF-8'}, 'es'),
    ({'LANG': 'es_MX.UTF-8'}, 'es'),
    ({'LANG': 'en_US.UTF-8'}, 'en'),
    ({'LANG': 'fr_FR.UTF-8'}, 'en'),                  # idioma no soportado -> inglés
    ({'LANG': 'C'}, 'en'),
    ({'LANG': 'en_US.UTF-8', 'LC_ALL': 'es_ES'}, 'es'),  # LC_ALL tiene prioridad sobre LANG
    ({'LANG': 'es_ES', 'LANGUAGE': 'fr:en'}, 'en'),      # LANGUAGE es una lista de preferencias
])
def test_detect_language_from_environment(monkeypatch, variables, expected):
    monkeypatch.delenv('LANG')
    for variable, value in variables.items():
        monkeypatch.setenv(variable, value)
    assert i18n.detect_language() == expected


@pytest.mark.parametrize('lang_id, expected', [(0x0C0A, 'es'), (0x080A, 'es'), (0x0409, 'en'), (0x040C, 'en')])
def test_detect_language_on_windows(monkeypatch, lang_id, expected):
    monkeypatch.delenv('LANG')
    monkeypatch.setattr(i18n.os, 'name', 'nt')
    monkeypatch.setattr(i18n, 'windows_language', lambda: i18n.WINDOWS_LANGUAGES.get(lang_id & 0x3FF))
    assert i18n.detect_language() == expected


@pytest.mark.parametrize('code, expected', [
    ('Spanish_Spain', 'es'), ('English_United States', 'en'), ('es-ES', 'es'), ('de', None), ('', None),
])
def test_language_from_code(code, expected):
    assert i18n.language_from_code(code) == expected


# ---------------------------------------------------------------------------
# Ayuda y opciones
# ---------------------------------------------------------------------------

def help_text(capsys, argv):
    with pytest.raises(SystemExit):
        main.main(argv)
    return capsys.readouterr().out


def test_help_in_spanish(capsys):
    text = help_text(capsys, ['-h'])
    assert text.startswith('uso: ')
    assert 'argumentos:' in text and 'opciones:' in text
    assert '--nuevo' in text and '--actualizar' in text and '--sobrescribir' in text
    assert '--new' not in text


def test_help_in_english(capsys):
    text = help_text(capsys, ['-h', '--lang', 'en'])
    assert text.startswith('usage: ')
    assert 'arguments:' in text and 'options:' in text
    assert '--new' in text and '--update' in text and '--overwrite' in text
    assert '--nuevo' not in text


def test_help_follows_system_language(monkeypatch, capsys):
    monkeypatch.setenv('LANG', 'en_GB.UTF-8')
    assert help_text(capsys, ['--help']).startswith('usage: ')


def test_lang_with_equals_sign(capsys):
    assert help_text(capsys, ['--lang=en', '-h']).startswith('usage: ')


def test_invalid_lang_is_rejected(capsys):
    with pytest.raises(SystemExit) as error:
        main.main(['--lang', 'fr'])
    assert error.value.code == 2
    assert 'uso: ' in capsys.readouterr().err


@pytest.mark.parametrize('lang, update_option', [('es', '--update'), ('en', '--actualizar'), ('en', '-a')])
def test_options_of_the_other_language_are_accepted(tmp_path, capsys, lang, update_option):
    media = tmp_path / 'media'
    media.mkdir()
    b.save_image(media / 'foto.jpg')
    csv_path = tmp_path / 'viaje.csv'
    csv_store.write_csv(csv_path, [csv_store.build_row('otra.jpg', '/otra/otra.jpg', 'image', {})])
    main.main([str(media), update_option, str(csv_path), '--lang', lang])
    assert len(csv_store.read_csv(csv_path)[1]) == 2


def test_overwrite_requires_new_in_english(capsys):
    with pytest.raises(SystemExit):
        main.main(['x', '--overwrite', '--lang', 'en'])
    assert '--overwrite can only be used together with --new' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Preguntas y mensajes
# ---------------------------------------------------------------------------

def test_interactive_run_in_english(monkeypatch, tmp_path, capsys):
    media = tmp_path / 'media'
    media.mkdir()
    b.save_image(media / 'foto.jpg')
    (media / 'roto.mov').write_bytes(b'esto no es un video')
    csv_path = tmp_path / 'trip.csv'
    csv_path.write_text('old')

    prompts = []
    answers = iter([str(media), 'n', str(csv_path), 'y'])
    monkeypatch.setattr('builtins.input', lambda prompt='': prompts.append(prompt) or next(answers))
    main.main(['--lang', 'en'])

    assert prompts == [
        'Path of the folder with the photos and videos [media]: ',
        'Create a new CSV (n) or update an existing one (u)? (N/u): ',
        f"Path of the new CSV [{media / 'media_geo_information.csv'}]: ",
        f"'{csv_path}' already exists. Overwrite it? (y/N): ",
    ]
    out = capsys.readouterr().out
    assert "Could not read roto.mov: No 'moov' box found" in out
    assert f'Information of 2 files saved to {csv_path}' in out


def test_update_answer_u_in_english(monkeypatch, tmp_path, capsys):
    media = tmp_path / 'media'
    media.mkdir()
    b.save_image(media / 'foto.jpg')
    csv_path = tmp_path / 'trip.csv'
    csv_store.write_csv(csv_path, [csv_store.build_row('otra.jpg', '/otra/otra.jpg', 'image', {})])
    answers = iter(['u', str(csv_path)])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(answers))
    main.main([str(media), '--lang', 'en'])
    assert 'CSV updated: 1 new files, 0 updated, 2 in total' in capsys.readouterr().out


def test_argument_errors_in_english(tmp_path):
    with pytest.raises(ValueError, match='does not exist or is not a folder'):
        main.main([str(tmp_path / 'no'), '--new', 'x.csv', '--lang', 'en'])


@pytest.mark.parametrize('lang, expected', [('es', 'Inténtalo de nuevo.'), ('en', 'Please try again.')])
def test_try_again_message(monkeypatch, tmp_path, capsys, lang, expected):
    i18n.set_language(lang)
    answers = iter(['no/existe', str(tmp_path)])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(answers))
    main.ask_media_dir()
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize('lang, expected', [('es', 'No se ha encontrado la caja'), ('en', "No 'moov' box found")])
def test_library_errors_are_translated(tmp_path, lang, expected):
    i18n.set_language(lang)
    path = tmp_path / 'roto.mov'
    path.write_bytes(b'esto no es un video')
    with pytest.raises(ValueError, match=expected):
        get_media_info(str(path))


@pytest.mark.parametrize('default, shown', [(None, '(s/n)'), ('s', '(S/n)'), ('n', '(s/N)')])
def test_ask_yes_no_defaults(monkeypatch, default, shown):
    prompts = []
    answers = iter(['', 'sí'])
    monkeypatch.setattr('builtins.input', lambda prompt='': prompts.append(prompt) or next(answers))
    expected = {None: True, 's': True, 'n': False}[default]  # sin valor por defecto, Enter vuelve a preguntar
    assert main.ask_yes_no('¿Seguro?', default) is expected
    assert prompts[0] == f'¿Seguro? {shown}: '
