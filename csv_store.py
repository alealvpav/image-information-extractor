"""Lectura, fusión y escritura del CSV de resultados."""
import csv
import locale
from geo_extractor.i18n import _

# Columnas que identifican cada archivo dentro del CSV
FILE_NAME_COLUMN = "0-MediaFileName"
FILE_PATH_COLUMN = "0-MediaPath"
FILE_TYPE_COLUMN = "0-FileType"

# Los CSV de versiones anteriores podían tener celdas enormes (MakerNote); 2**31 - 1 es el máximo que admite Windows
csv.field_size_limit(2 ** 31 - 1)

def build_row(media_file, media_path, file_type, media_info):
    row = dict(media_info)
    row[FILE_NAME_COLUMN] = media_file
    row[FILE_PATH_COLUMN] = media_path
    row[FILE_TYPE_COLUMN] = file_type
    return row

def is_generated_csv(fieldnames):
    return FILE_NAME_COLUMN in fieldnames

def read_csv(csv_path):
    # Los CSV de versiones anteriores se guardaban con la codificación del sistema (cp1252 en Windows en español)
    for encoding in ("utf-8-sig", locale.getpreferredencoding(False), "cp1252"):
        try:
            with open(csv_path, newline="", encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                return reader.fieldnames or [], rows
        except UnicodeDecodeError:
            pass
    raise csv.Error(_("error_unknown_encoding"))

def merge_rows(existing_rows, new_rows):
    """Sustituye las filas de los archivos ya presentes en el CSV y añade al final los nuevos."""
    positions = {row.get(FILE_PATH_COLUMN) or row[FILE_NAME_COLUMN]: i for i, row in enumerate(existing_rows)}
    # Filas de CSV antiguos, sin ruta: se identifican solo por el nombre del archivo
    positions_by_name = {row[FILE_NAME_COLUMN]: i for i, row in enumerate(existing_rows) if not row.get(FILE_PATH_COLUMN)}

    rows = list(existing_rows)
    updated = 0
    for new_row in new_rows:
        position = positions.get(new_row[FILE_PATH_COLUMN], positions_by_name.get(new_row[FILE_NAME_COLUMN]))
        if position is None:
            rows.append(new_row)
        else:
            rows[position] = new_row
            updated += 1
    return rows, updated

def write_csv(csv_path, rows, fieldnames=()):
    # utf-8-sig para que Excel en Windows muestre bien tildes y eñes
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        # Imágenes y vídeos tienen campos distintos: se usan todos los que aparezcan
        fieldnames = sorted(set(fieldnames) | {k for row in rows for k in row})
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in rows:
            writer.writerow(row)
