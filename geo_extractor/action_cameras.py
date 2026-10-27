import math
import re
import struct
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# GoPro: telemetría GPMF (pista 'gpmd', HERO5 en adelante y MAX)
# https://github.com/gopro/gpmf-parser
# ---------------------------------------------------------------------------

# Tipos GPMF y su equivalente en el módulo struct
GPMF_TYPES = {'b': 'b', 'B': 'B', 'c': 'c', 'd': 'd', 'f': 'f', 'j': 'q', 'J': 'Q',
              'l': 'l', 'L': 'L', 's': 'h', 'S': 'H'}

GPS9_EPOCH = datetime(2000, 1, 1)


def iter_klv(data: bytes):
    # Cada entrada: clave (4 bytes), tipo (1), tamaño de la estructura (1), repeticiones (2) y datos
    pos = 0
    while pos + 8 <= len(data):
        key = data[pos:pos + 4]
        type_char = chr(data[pos + 4])
        size = data[pos + 5]
        repeat = struct.unpack('>H', data[pos + 6:pos + 8])[0]
        length = size * repeat
        yield key, type_char, size, repeat, data[pos + 8:pos + 8 + length]
        pos += 8 + (length + 3) // 4 * 4  # los datos se alinean a 4 bytes


def decode_klv(type_char, size, repeat, payload, complex_type=None):
    if type_char in ('c', 'U'):
        return payload.rstrip(b'\0').decode('latin-1')
    if type_char == '?':
        fmt = '>' + ''.join(GPMF_TYPES[c] for c in complex_type)
    else:
        fmt = '>' + GPMF_TYPES[type_char] * (size // struct.calcsize('>' + GPMF_TYPES[type_char]))
    return [struct.unpack(fmt, payload[i * size:(i + 1) * size]) for i in range(repeat)]


def parse_gpmf_stream(payload: bytes):
    # Los valores "fijos" (escala, tipo, calidad del fix, hora) preceden a los datos GPS en el mismo stream
    scale, complex_type, fix, gps_time = None, None, None, None
    for key, type_char, size, repeat, value in iter_klv(payload):
        if key == b'SCAL':
            scale = [v for row in decode_klv(type_char, size, repeat, value) for v in row]
        elif key == b'TYPE':
            complex_type = decode_klv(type_char, size, repeat, value)
        elif key == b'GPSF':
            fix = decode_klv(type_char, size, repeat, value)[0][0]
        elif key == b'GPSU':
            gps_time = decode_klv(type_char, size, repeat, value)
        elif key in (b'GPS5', b'GPS9'):
            rows = decode_klv(type_char, size, repeat, value, complex_type)
            for row in rows:
                scales = scale * len(row) if len(scale) == 1 else scale
                values = [v / s for v, s in zip(row, scales)]
                if key == b'GPS9':
                    fix = values[8]
                if (fix is not None and fix < 2) or (values[0] == 0 and values[1] == 0):
                    continue
                gps = {'Latitude': values[0], 'Longitude': values[1], 'Altitude': values[2]}
                if key == b'GPS9':
                    moment = GPS9_EPOCH + timedelta(days=values[5], seconds=values[6])
                    gps['GPSDateTime'] = moment.strftime('%Y:%m:%d %H:%M:%S')
                elif gps_time:
                    # GPSU: "yymmddhhmmss.sss" en UTC
                    t = gps_time
                    gps['GPSDateTime'] = f'20{t[0:2]}:{t[2:4]}:{t[4:6]} {t[6:8]}:{t[8:10]}:{t[10:12]}'
                return gps
    return None


def find_gpmf_streams(data: bytes):
    for key, type_char, size, repeat, value in iter_klv(data):
        if key == b'STRM':
            yield value
        elif type_char == '\0':  # entrada anidada (DEVC...)
            yield from find_gpmf_streams(value)


def get_gopro_gps(samples):
    """Devuelve la primera posición GPS válida (con fix 2D/3D) de las muestras de la pista GPMF."""
    for sample in samples:
        for stream in find_gpmf_streams(sample):
            try:
                gps = parse_gpmf_stream(stream)
            except (struct.error, KeyError, IndexError, TypeError):
                continue
            if gps:
                return gps
    return None


def get_gopro_model(gpmf: bytes):
    # La caja 'GPMF' de 'udta' incluye el modelo de cámara en la clave MINF (p. ej. "HERO9 Black")
    for key, type_char, size, repeat, value in iter_klv(gpmf):
        if key == b'MINF':
            return decode_klv(type_char, size, repeat, value)
        if type_char == '\0':
            model = get_gopro_model(value)
            if model:
                return model
    return None


# ---------------------------------------------------------------------------
# DJI moderno: metadatos protobuf (pista 'djmd')
# Rutas de campos tomadas de ExifTool (lib/Image/ExifTool/DJI.pm)
# ---------------------------------------------------------------------------

# Protocolo -> (modelo, ruta del bloque GPS, coordenadas siempre en grados)
DJI_PROTOCOLS = {
    'ac203': ('Osmo Action 4', (3, 4, 2), False),
    'ac204': ('Osmo Action 5 Pro', (3, 4, 2), False),
    'ac206': ('Osmo Action 6', (3, 4, 2), False),
    'oq101': ('Osmo 360', (3, 4, 2), False),
    'AVATA2': ('Avata 2', (3, 4, 4), False),
    'dji_neo': ('Neo', (3, 4, 4), False),
    'wm265e': ('Mavic 3', (3, 3, 4), False),
    'wm261': ('Mavic 3 Pro', (3, 3, 4), False),
    'Mavic4': ('Mavic 4 Pro', (3, 3, 4), True),
    'pm320': ('Matrice 30', (3, 3, 4), False),
    'wa345e': ('Matrice 4E', (3, 3, 4), False),
    'Mini4_Pro': ('Mini 4 Pro', (3, 3, 4), False),
    'Mini5Pro': ('Mini 5 Pro', (3, 3, 4), True),
    'Air3': ('Air 3', (3, 3, 4), False),
    'Air3s': ('Air 3S', (3, 3, 4), False),
}
DJI_GPS_PATHS = [(3, 4, 2), (3, 3, 4), (3, 4, 4)]
DJI_PROTOCOL_PATTERN = re.compile(rb'dvtm_([\w-]+)\.proto')


def read_varint(data: bytes, pos: int):
    value, shift = 0, 0
    while True:
        byte = data[pos]
        value |= (byte & 0x7f) << shift
        pos += 1
        if not byte & 0x80:
            return value, pos
        shift += 7


def iter_protobuf(data: bytes):
    pos = 0
    while pos < len(data):
        key, pos = read_varint(data, pos)
        field, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value, pos = read_varint(data, pos)
        elif wire_type == 1:
            value, pos = data[pos:pos + 8], pos + 8
        elif wire_type == 2:
            length, pos = read_varint(data, pos)
            value, pos = data[pos:pos + length], pos + length
        elif wire_type == 5:
            value, pos = data[pos:pos + 4], pos + 4
        else:
            return
        yield field, value


def protobuf_get(data: bytes, path):
    for field_number in path:
        if not isinstance(data, bytes):
            return None
        for field, value in iter_protobuf(data):
            if field == field_number:
                data = value
                break
        else:
            return None
    return data


def to_signed(value: int):
    # DJI guarda algunos enteros negativos de forma incorrecta: solo valen los 32 bits bajos
    if value >= 2 ** 32:
        value &= 0xffffffff
    return value - 2 ** 32 if value >= 2 ** 31 else value


def parse_dji_sample(sample: bytes, path, always_degrees: bool):
    gps_info = protobuf_get(sample, path + (1,))
    if not isinstance(gps_info, bytes):
        return None
    units = protobuf_get(gps_info, (1,))
    latitude = protobuf_get(gps_info, (2,))
    longitude = protobuf_get(gps_info, (3,))
    if not (isinstance(latitude, bytes) and isinstance(longitude, bytes)
            and len(latitude) == 8 and len(longitude) == 8):
        return None
    latitude = struct.unpack('<d', latitude)[0]
    longitude = struct.unpack('<d', longitude)[0]
    if not (always_degrees or units):  # sin indicar unidades, vienen en radianes
        latitude, longitude = math.degrees(latitude), math.degrees(longitude)
    if (latitude == 0 and longitude == 0) or abs(latitude) > 90 or abs(longitude) > 180:
        return None

    gps = {'Latitude': latitude, 'Longitude': longitude}
    altitude = protobuf_get(sample, path + (2,))
    if isinstance(altitude, int):
        gps['Altitude'] = to_signed(altitude) / 1000
    gps_time = protobuf_get(sample, path + (6, 1))
    if isinstance(gps_time, bytes) and gps_time:
        gps['GPSDateTime'] = gps_time.decode('latin-1').replace('-', ':')
    return gps


def get_dji_gps(samples):
    """Devuelve la primera posición GPS válida de la pista 'djmd' y el modelo de DJI."""
    model, paths, always_degrees = None, DJI_GPS_PATHS, False
    for sample in samples:
        match = DJI_PROTOCOL_PATTERN.search(sample)
        if match and model is None:
            protocol = match.group(1).decode()
            model, path, always_degrees = DJI_PROTOCOLS.get(protocol, (protocol, None, False))
            paths = [path] if path else DJI_GPS_PATHS
        for path in paths:
            try:
                gps = parse_dji_sample(sample, path, always_degrees)
            except (IndexError, struct.error):
                gps = None
            if gps:
                return gps, model
    return None, model


# ---------------------------------------------------------------------------
# DJI antiguo: GPS en los subtítulos (pista de texto o archivo .SRT al lado del vídeo)
# ---------------------------------------------------------------------------

# Mini 2, Air 2S, Mavic 3... "[latitude: 40.416800] [longitude: -3.703800] [rel_alt: 1.2 abs_alt: 650.1]"
# (algunos modelos escriben "longtitude")
SUBTITLE_LATITUDE = re.compile(r'latitude\s*:\s*(-?[\d.]+)', re.IGNORECASE)
SUBTITLE_LONGITUDE = re.compile(r'longt?itude\s*:\s*(-?[\d.]+)', re.IGNORECASE)
SUBTITLE_ALTITUDE = re.compile(r'abs_alt\s*:\s*(-?[\d.]+)', re.IGNORECASE)
# Mavic Pro, Mavic 2, Phantom 4...: "GPS (-3.7038, 40.4168, 15)" -> (longitud, latitud, ...)
SUBTITLE_GPS = re.compile(r'GPS\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)')


def parse_subtitle_text(text: str):
    latitude, longitude = SUBTITLE_LATITUDE.search(text), SUBTITLE_LONGITUDE.search(text)
    if latitude and longitude:
        gps = {'Latitude': float(latitude.group(1)), 'Longitude': float(longitude.group(1))}
        altitude = SUBTITLE_ALTITUDE.search(text)
        if altitude:
            gps['Altitude'] = float(altitude.group(1))
    else:
        match = SUBTITLE_GPS.search(text)
        if not match:
            return None
        gps = {'Latitude': float(match.group(2)), 'Longitude': float(match.group(1))}
    if gps['Latitude'] == 0 and gps['Longitude'] == 0:
        return None
    return gps


def get_subtitle_gps(texts):
    """Devuelve la primera posición GPS válida de una secuencia de subtítulos."""
    for text in texts:
        gps = parse_subtitle_text(text)
        if gps:
            return gps
    return None


def get_srt_gps(fname: str):
    with open(fname, encoding='utf-8', errors='replace') as f:
        blocks = re.split(r'\n\s*\n', f.read())
    return get_subtitle_gps(blocks)
