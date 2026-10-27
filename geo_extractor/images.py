from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS, IFD
from pillow_heif import register_heif_opener    # HEIF support
import pillow_avif                              # AVIF support
from .raw import get_raw_exif, is_raw          # RAW support

register_heif_opener()                          # HEIF support

MAX_BINARY_LENGTH = 64

def get_ifds(exif):
    ifds = {}
    for ifd_id in IFD:
        try:
            ifds[ifd_id] = exif.get_ifd(ifd_id)
        except KeyError:
            pass
    return ifds

def get_exif_dict(fname: str):
    if is_raw(fname):
        # Pillow no sabe abrir los RAW: se leen solo sus metadatos
        base_tags, ifds = get_raw_exif(fname)
    else:
        img = Image.open(fname)
        exif = img.getexif()
        base_tags, ifds = dict(exif), get_ifds(exif)

    exif_dict = {}

    for k, v in base_tags.items():
        tag = TAGS.get(k, k)
        exif_dict[tag] = v

    for ifd_id, ifd in ifds.items():
        if ifd_id == IFD.GPSInfo:
            resolve = GPSTAGS
        else:
            resolve = TAGS

        for k, v in ifd.items():
            tag = resolve.get(k, k)
            exif_dict[tag] = v

    # Los bloques binarios grandes (MakerNote, XMP...) no son legibles y generan celdas enormes en el CSV
    exif_dict = {k: v for k, v in exif_dict.items() if not (isinstance(v, bytes) and len(v) > MAX_BINARY_LENGTH)}

    exif_dict.update(get_decimal_coordinates(exif_dict))
    if 'Latitude' in exif_dict:
        exif_dict['GPSSource'] = 'EXIF'
    gps_datetime = get_gps_datetime(exif_dict)
    if gps_datetime:
        exif_dict['GPSDateTime'] = gps_datetime

    return exif_dict

def get_gps_datetime(exif_dict: dict):
    # El EXIF guarda la fecha (GPSDateStamp, "2024:10:30") y la hora (GPSTimeStamp, (h, m, s)) del GPS por separado, en UTC
    date, time = exif_dict.get('GPSDateStamp'), exif_dict.get('GPSTimeStamp')
    if not date or not time:
        return None
    try:
        hours, minutes, seconds = (int(float(x)) for x in time)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return f'{str(date).strip()} {hours:02d}:{minutes:02d}:{seconds:02d}'

def dms_to_decimal(dms, ref):
    degrees, minutes, seconds = (float(x) for x in dms)
    decimal = degrees + minutes / 60 + seconds / 3600
    return -decimal if ref in ('S', 'W') else decimal

def get_decimal_coordinates(exif_dict: dict):
    # Mismas columnas que los vídeos (Latitude, Longitude, Altitude) para poder compararlos
    coordinates = {}
    if 'GPSLatitude' in exif_dict and 'GPSLongitude' in exif_dict:
        coordinates['Latitude'] = dms_to_decimal(exif_dict['GPSLatitude'], exif_dict.get('GPSLatitudeRef'))
        coordinates['Longitude'] = dms_to_decimal(exif_dict['GPSLongitude'], exif_dict.get('GPSLongitudeRef'))
    if 'GPSAltitude' in exif_dict:
        altitude = float(exif_dict['GPSAltitude'])
        coordinates['Altitude'] = -altitude if exif_dict.get('GPSAltitudeRef') in (1, b'\x01') else altitude
    return coordinates
