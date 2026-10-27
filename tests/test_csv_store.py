import csv

import csv_store
from csv_store import FILE_NAME_COLUMN, FILE_PATH_COLUMN


def row(name, path, **values):
    return {FILE_NAME_COLUMN: name, FILE_PATH_COLUMN: path, **values}


def test_merge_updates_existing_and_appends_new():
    existing = [row('a.jpg', '/f/a.jpg', Latitude='1'), row('b.jpg', '/f/b.jpg', Latitude='2')]
    new = [row('b.jpg', '/f/b.jpg', Latitude='20'), row('c.jpg', '/f/c.jpg', Latitude='3')]
    rows, updated = csv_store.merge_rows(existing, new)
    assert updated == 1
    assert [(r[FILE_NAME_COLUMN], r['Latitude']) for r in rows] == [('a.jpg', '1'), ('b.jpg', '20'), ('c.jpg', '3')]


def test_merge_keeps_same_name_in_different_folders():
    existing = [row('GX010001.MP4', '/tarjeta1/GX010001.MP4')]
    rows, updated = csv_store.merge_rows(existing, [row('GX010001.MP4', '/tarjeta2/GX010001.MP4')])
    assert updated == 0
    assert len(rows) == 2


def test_merge_matches_old_rows_without_path_by_name():
    existing = [{FILE_NAME_COLUMN: 'foto.jpg', 'Latitude': '1'}]
    rows, updated = csv_store.merge_rows(existing, [row('foto.jpg', '/f/foto.jpg', Latitude='2')])
    assert updated == 1
    assert rows == [row('foto.jpg', '/f/foto.jpg', Latitude='2')]


def test_write_and_read_roundtrip(tmp_path):
    path = tmp_path / 'salida.csv'
    rows = [row('montaña.jpg', '/f/montaña.jpg', Latitude=1.5), row('vídeo.mp4', '/f/vídeo.mp4', GPSSource='QuickTime')]
    csv_store.write_csv(path, rows)
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')  # BOM para Excel
    fieldnames, read_rows = csv_store.read_csv(path)
    assert fieldnames == sorted({FILE_NAME_COLUMN, FILE_PATH_COLUMN, 'Latitude', 'GPSSource'})
    assert read_rows[0][FILE_NAME_COLUMN] == 'montaña.jpg'
    assert read_rows[1]['Latitude'] == ''


def test_write_keeps_columns_of_existing_csv(tmp_path):
    path = tmp_path / 'salida.csv'
    csv_store.write_csv(path, [row('a.jpg', '/f/a.jpg')], fieldnames=['ColumnaAntigua'])
    assert 'ColumnaAntigua' in csv_store.read_csv(path)[0]


def test_read_old_cp1252_csv_with_huge_cells(tmp_path):
    path = tmp_path / 'antiguo.csv'
    with open(path, 'w', newline='', encoding='cp1252') as f:
        writer = csv.DictWriter(f, fieldnames=[FILE_NAME_COLUMN, 'MakerNote'])
        writer.writeheader()
        writer.writerow({FILE_NAME_COLUMN: 'montaña.jpg', 'MakerNote': 'x' * 300000})
    fieldnames, rows = csv_store.read_csv(path)
    assert csv_store.is_generated_csv(fieldnames)
    assert rows[0][FILE_NAME_COLUMN] == 'montaña.jpg'


def test_foreign_csv_is_not_generated(tmp_path):
    path = tmp_path / 'ajeno.csv'
    path.write_text('a,b\n1,2\n')
    assert not csv_store.is_generated_csv(csv_store.read_csv(path)[0])
