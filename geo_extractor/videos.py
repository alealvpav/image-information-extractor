import os
import re
import struct
from datetime import datetime, timedelta, timezone
from .action_cameras import get_dji_gps, get_gopro_gps, get_gopro_model, get_srt_gps, get_subtitle_gps
from .i18n import _
from .mp4 import iter_boxes

VIDEO_EXTENSIONS = ('.mov', '.mp4', '.m4v', '.3gp', '.3g2', '.360')

# Subtítulos con GPS que los drones DJI guardan junto al vídeo (se leen junto con él)
SUBTITLE_EXTENSIONS = ('.srt',)

# Cajas (atoms) MP4/QuickTime que contienen otras cajas y hay que recorrer
CONTAINER_BOXES = {b'moov', b'udta', b'meta', b'ilst'}

# Cajas de una pista ('trak') que contienen la tabla de muestras
TRACK_CONTAINER_BOXES = {b'mdia', b'minf', b'stbl'}

# Las fechas de QuickTime cuentan segundos desde el 1 de enero de 1904
QUICKTIME_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)

# Claves del metadato "mdta" (iPhone) y nombre con el que se escriben en el CSV,
# alineado con los nombres EXIF de las imágenes cuando existe equivalente
QUICKTIME_KEYS = {
    'com.apple.quicktime.location.ISO6709': 'GPSCoordinates',
    'com.apple.quicktime.location.accuracy.horizontal': 'GPSHorizontalAccuracy',
    'com.apple.quicktime.make': 'Make',
    'com.apple.quicktime.model': 'Model',
    'com.apple.quicktime.software': 'Software',
    'com.apple.quicktime.creationdate': 'DateTimeOriginal',
}

# Formato ISO 6709 usado por los móviles: "+40.4168-003.7038+650.000/"
ISO6709_PATTERN = re.compile(r'([+-][\d.]+)([+-][\d.]+)([+-][\d.]+)?')


def is_video(fname: str):
    return fname.lower().endswith(VIDEO_EXTENSIONS)


def is_subtitle(fname: str):
    return fname.lower().endswith(SUBTITLE_EXTENSIONS)


def read_moov(fname: str):
    """Devuelve el contenido de la caja 'moov' sin cargar el vídeo entero en memoria."""
    with open(fname, 'rb') as f:
        while True:
            header = f.read(8)
            if len(header) < 8:
                return None
            size, box_type = struct.unpack('>I4s', header)
            header_size = 8
            if size == 1:
                size = struct.unpack('>Q', f.read(8))[0]
                header_size = 16
            if box_type == b'moov':
                return f.read(size - header_size) if size else f.read()
            if size == 0:
                return None
            f.seek(size - header_size, 1)


def parse_iso6709(value: str):
    match = ISO6709_PATTERN.match(value.strip())
    if not match:
        return {}
    latitude = iso6709_to_decimal(match.group(1), degree_digits=2)
    longitude = iso6709_to_decimal(match.group(2), degree_digits=3)
    coordinates = {'Latitude': latitude, 'Longitude': longitude}
    if match.group(3):
        coordinates['Altitude'] = float(match.group(3))
    return coordinates


def iso6709_to_decimal(value: str, degree_digits: int):
    # Admite grados (±DD.DD), grados+minutos (±DDMM.MM) y grados+minutos+segundos (±DDMMSS.SS)
    sign = -1 if value[0] == '-' else 1
    integer, _, fraction = value[1:].partition('.')
    fraction = float('0.' + fraction) if fraction else 0.0
    extra_digits = len(integer) - degree_digits
    if extra_digits <= 0:
        return sign * (int(integer) + fraction)
    degrees = int(integer[:degree_digits])
    if extra_digits == 2:
        minutes = int(integer[degree_digits:]) + fraction
        return sign * (degrees + minutes / 60)
    minutes = int(integer[degree_digits:degree_digits + 2])
    seconds = int(integer[degree_digits + 2:]) + fraction
    return sign * (degrees + minutes / 60 + seconds / 3600)


def parse_mvhd(data: bytes, start: int):
    version = data[start]
    if version == 1:
        seconds = struct.unpack('>Q', data[start + 4:start + 12])[0]
    else:
        seconds = struct.unpack('>I', data[start + 4:start + 8])[0]
    if not seconds:
        return None
    return (QUICKTIME_EPOCH + timedelta(seconds=seconds)).strftime('%Y:%m:%d %H:%M:%S')


def parse_keys(data: bytes, start: int, end: int):
    keys = []
    pos = start + 8  # versión/flags + número de entradas
    while pos + 8 <= end:
        size = struct.unpack('>I', data[pos:pos + 4])[0]
        if size < 8:
            break
        keys.append(data[pos + 8:pos + size].decode('utf-8', errors='replace'))
        pos += size
    return keys


def parse_ilst(data: bytes, start: int, end: int, keys: list):
    values = {}
    for item_type, item_start, item_end in iter_boxes(data, start, end):
        index = struct.unpack('>I', item_type)[0]
        if not 1 <= index <= len(keys):
            continue
        for box_type, box_start, box_end in iter_boxes(data, item_start, item_end):
            if box_type == b'data':
                data_type = struct.unpack('>I', data[box_start:box_start + 4])[0]
                raw = data[box_start + 8:box_end]
                if data_type == 23:  # float32
                    values[keys[index - 1]] = struct.unpack('>f', raw)[0]
                elif data_type == 24:  # float64
                    values[keys[index - 1]] = struct.unpack('>d', raw)[0]
                else:
                    values[keys[index - 1]] = raw.decode('utf-8', errors='replace')
    return values


def parse_xyz(data: bytes, start: int, end: int):
    # Caja '©xyz' (Android y otros): 2 bytes de longitud, 2 de idioma y el texto ISO 6709
    length = struct.unpack('>H', data[start:start + 2])[0]
    return data[start + 4:start + 4 + length].decode('utf-8', errors='replace')


def walk_boxes(data: bytes, start: int, end: int, info: dict, keys: list):
    for box_type, box_start, box_end in iter_boxes(data, start, end):
        if box_type == b'mvhd':
            info.setdefault('CreationTime', parse_mvhd(data, box_start))
        elif box_type == b'\xa9xyz':
            info.setdefault('GPSCoordinates', parse_xyz(data, box_start, box_end))
        elif box_type == b'GPMF':
            info['Make'] = 'GoPro'
            info.setdefault('Model', get_gopro_model(data[box_start:box_end]))
        elif box_type == b'keys':
            keys[:] = parse_keys(data, box_start, box_end)
        elif box_type == b'ilst' and keys:
            for key, value in parse_ilst(data, box_start, box_end, keys).items():
                if key in QUICKTIME_KEYS:
                    info[QUICKTIME_KEYS[key]] = value
        elif box_type in CONTAINER_BOXES:
            # En MP4 'meta' es una "full box" (4 bytes de versión/flags antes de sus hijas);
            # en QuickTime no lo es
            if box_type == b'meta' and data[box_start + 4:box_start + 8] != b'hdlr':
                box_start += 4
            walk_boxes(data, box_start, box_end, info, [])


def parse_track(data: bytes, start: int, end: int, track: dict):
    for box_type, box_start, box_end in iter_boxes(data, start, end):
        if box_type in TRACK_CONTAINER_BOXES:
            parse_track(data, box_start, box_end, track)
        elif box_type == b'hdlr':
            # El primero es el de 'mdia' (tipo de pista); el de 'minf' solo describe el almacenamiento
            track.setdefault('handler', data[box_start + 8:box_start + 12])
        elif box_type == b'stsd':
            track['format'] = data[box_start + 12:box_start + 16]
        elif box_type in (b'stco', b'co64'):
            count = struct.unpack('>I', data[box_start + 4:box_start + 8])[0]
            fmt = '>%dI' % count if box_type == b'stco' else '>%dQ' % count
            track['chunk_offsets'] = struct.unpack(fmt, data[box_start + 8:box_start + 8 + struct.calcsize(fmt)])
        elif box_type == b'stsz':
            sample_size, count = struct.unpack('>II', data[box_start + 4:box_start + 12])
            if sample_size:
                track['sample_sizes'] = [sample_size] * count
            else:
                track['sample_sizes'] = struct.unpack('>%dI' % count, data[box_start + 12:box_start + 12 + 4 * count])
        elif box_type == b'stsc':
            count = struct.unpack('>I', data[box_start + 4:box_start + 8])[0]
            values = struct.unpack('>%dI' % (3 * count), data[box_start + 8:box_start + 8 + 12 * count])
            track['sample_to_chunk'] = [values[i:i + 3] for i in range(0, len(values), 3)]


def get_tracks(moov: bytes):
    tracks = []
    for box_type, box_start, box_end in iter_boxes(moov):
        if box_type == b'trak':
            track = {}
            parse_track(moov, box_start, box_end, track)
            tracks.append(track)
    return tracks


def iter_sample_positions(track: dict):
    offsets = track.get('chunk_offsets', ())
    sizes = track.get('sample_sizes', ())
    sample_to_chunk = track.get('sample_to_chunk', ())
    sample = 0
    for i, (first_chunk, samples_per_chunk, _) in enumerate(sample_to_chunk):
        last_chunk = sample_to_chunk[i + 1][0] - 1 if i + 1 < len(sample_to_chunk) else len(offsets)
        for chunk in range(first_chunk, last_chunk + 1):
            position = offsets[chunk - 1]
            for _ in range(samples_per_chunk):
                if sample >= len(sizes):
                    return
                yield position, sizes[sample]
                position += sizes[sample]
                sample += 1


def read_samples(fname: str, track: dict):
    # Se leen de una en una para parar en cuanto aparezca una posición GPS válida
    with open(fname, 'rb') as f:
        for position, size in iter_sample_positions(track):
            f.seek(position)
            yield f.read(size)


def read_subtitles(fname: str, track: dict):
    # Subtítulos 'tx3g'/'text': 2 bytes de longitud seguidos del texto
    for sample in read_samples(fname, track):
        if len(sample) >= 2:
            length = struct.unpack('>H', sample[:2])[0]
            yield sample[2:2 + length].decode('utf-8', errors='replace')


def get_track_gps(fname: str, moov: bytes, info: dict):
    for track in get_tracks(moov):
        if track.get('format') == b'gpmd':
            gps = get_gopro_gps(read_samples(fname, track))
            if gps:
                return gps, 'GoPro GPMF'
        elif track.get('format') == b'djmd':
            gps, model = get_dji_gps(read_samples(fname, track))
            info['Make'] = 'DJI'
            info.setdefault('Model', model)
            if gps:
                return gps, 'DJI djmd'
        elif track.get('handler') in (b'sbtl', b'text') or track.get('format') in (b'tx3g', b'text'):
            gps = get_subtitle_gps(read_subtitles(fname, track))
            if gps:
                return gps, 'Subtítulos'
    return None, None


def get_sidecar_srt(fname: str):
    base = os.path.splitext(fname)[0]
    for extension in ('.SRT', '.srt'):
        if os.path.exists(base + extension):
            return base + extension
    return None


def get_video_dict(fname: str):
    moov = read_moov(fname)
    if moov is None:
        raise ValueError(_("error_no_moov"))

    info = {}
    walk_boxes(moov, 0, len(moov), info, [])

    if info.get('GPSCoordinates'):
        info.update(parse_iso6709(info['GPSCoordinates']))
        info['GPSSource'] = 'QuickTime'

    # Cámaras de acción y drones: el GPS va en una pista de telemetría o en los subtítulos
    if 'Latitude' not in info:
        gps, source = get_track_gps(fname, moov, info)
        if gps:
            info.update(gps)
            info['GPSSource'] = source

    if 'Latitude' not in info:
        srt = get_sidecar_srt(fname)
        gps = get_srt_gps(srt) if srt else None
        if gps:
            info.update(gps)
            info['GPSSource'] = os.path.basename(srt)

    return {k: v for k, v in info.items() if v is not None}
