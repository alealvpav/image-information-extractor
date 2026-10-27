"""Genera archivos de prueba (fotos, RAW y vídeos) con metadatos y GPS conocidos.

No reproducen los archivos reales completos: solo la estructura de metadatos que lee el programa.
"""
import io
import math
import struct

from PIL import Image
from pillow_heif import register_heif_opener
import pillow_avif  # noqa: F401  (soporte AVIF)

register_heif_opener()

# Madrid: 40º 25' 0.48" N, 3º 42' 13.68" W, 650 m
GPS_IFD = {1: 'N', 2: (40.0, 25.0, 0.48), 3: 'W', 4: (3.0, 42.0, 13.68), 5: b'\x00', 6: 650.0}
MADRID = (40.4168, -3.7038, 650.0)


# ---------------------------------------------------------------------------
# Fotos y RAW
# ---------------------------------------------------------------------------

def image_with_exif(make='TestMake', mode='RGB', gps=GPS_IFD, extra=None):
    img = Image.new(mode, (64, 48), 128 if mode == 'L' else 'red')
    exif = img.getexif()
    exif[0x010F] = make
    exif[0x0110] = make + ' Model'
    if gps:
        exif[0x8825] = gps
    for tag, value in (extra or {}).items():
        exif[tag] = value
    return img, exif


def save_image(path, fmt=None, **kwargs):
    img, exif = image_with_exif(**kwargs)
    if fmt == 'TIFF' or str(path).lower().endswith(('.tif', '.tiff')):
        img.save(path, format='TIFF', exif=exif.tobytes())
    else:
        img.save(path, format=fmt, exif=exif)


def jpeg_bytes(make):
    img, exif = image_with_exif(make)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', exif=exif)
    return buf.getvalue()


def tiff_bytes(make):
    img, exif = image_with_exif(make)
    buf = io.BytesIO()
    img.save(buf, format='TIFF', exif=exif.tobytes())
    return bytearray(buf.getvalue())


def set_ifd0_short(data, tag_id, value):
    ifd = struct.unpack('<I', data[4:8])[0]
    for i in range(struct.unpack('<H', data[ifd:ifd + 2])[0]):
        p = ifd + 2 + 12 * i
        if struct.unpack('<H', data[p:p + 2])[0] == tag_id:
            data[p + 8:p + 10] = struct.pack('<H', value)
    return data


def tiff_raw(make, header=None):
    # Compresión 34713 (Nikon): Pillow no sabe abrir la imagen, igual que con un RAW real
    data = set_ifd0_short(tiff_bytes(make), 259, 34713)
    if header:
        data[0:4] = header
    return bytes(data)


def rw2_bytes():
    # Panasonic: cabecera IIU y el EXIF completo en un JPEG incrustado (etiqueta 0x2E)
    buf = io.BytesIO()
    Image.new('RGB', (64, 48), 'red').save(buf, format='TIFF', tiffinfo={0x2E: jpeg_bytes('Panasonic')})
    data = bytearray(buf.getvalue())
    data[0:4] = b'IIU\x00'
    return bytes(data)


def raf_bytes():
    # Fujifilm: cabecera con offset y longitud del JPEG de vista previa
    jpeg = jpeg_bytes('FUJIFILM')
    header = b'FUJIFILMCCD-RAW 0201FF383501'.ljust(84, b'\0')
    return header + struct.pack('>II', 100, len(jpeg)) + b'\0' * 8 + jpeg


def tiff_of(tags):
    exif = Image.Exif()
    for k, v in tags.items():
        exif[k] = v
    return exif.tobytes()[6:]  # sin el prefijo "Exif\0\0"


def cr3_bytes():
    # Canon CR3: moov/uuid con CMT1 (IFD0), CMT2 (EXIF) y CMT4 (GPS)
    uuid = box(b'uuid', bytes.fromhex('85c0b687820f11e08111f4ce462b6a48')
               + box(b'CMT1', tiff_of({0x010F: 'Canon', 0x0110: 'Canon EOS R5'}))
               + box(b'CMT2', tiff_of({0x9003: '2024:10:30 12:00:00'}))
               + box(b'CMT4', tiff_of(GPS_IFD)))
    return box(b'ftyp', b'crx \0\0\0\1crx isom') + box(b'moov', uuid) + box(b'mdat', b'\0' * 64)


RAW_FILES = {
    'raw.dng': ('DNGCam', lambda: tiff_raw('DNGCam')),
    'raw.cr2': ('Canon', lambda: tiff_raw('Canon')),
    'raw.nef': ('NIKON', lambda: tiff_raw('NIKON')),
    'raw.arw': ('SONY', lambda: tiff_raw('SONY')),
    'raw.pef': ('PENTAX', lambda: tiff_raw('PENTAX')),
    'raw.srw': ('SAMSUNG', lambda: tiff_raw('SAMSUNG')),
    'raw.orf': ('OLYMPUS', lambda: tiff_raw('OLYMPUS', header=b'IIRO')),
    'raw.rw2': ('Panasonic', rw2_bytes),
    'raw.raf': ('FUJIFILM', raf_bytes),
    'raw.cr3': ('Canon', cr3_bytes),
}


# ---------------------------------------------------------------------------
# Vídeos MP4/MOV
# ---------------------------------------------------------------------------

def box(box_type, payload):
    return struct.pack('>I', 8 + len(payload)) + box_type + payload


def full_box(box_type, payload, version=0):
    return box(box_type, bytes([version, 0, 0, 0]) + payload)


MVHD = full_box(b'mvhd', struct.pack('>IIII', 3813129600, 3813129600, 600, 6000) + b'\0' * 80)  # 2024-10-30
FTYP = box(b'ftyp', b'isom\0\0\0\0isom')
MDAT = box(b'mdat', b'\0' * 1000)


def iphone_mov():
    keys = [b'com.apple.quicktime.location.accuracy.horizontal', b'com.apple.quicktime.location.ISO6709',
            b'com.apple.quicktime.make', b'com.apple.quicktime.model', b'com.apple.quicktime.creationdate']
    keys_box = full_box(b'keys', struct.pack('>I', len(keys)) + b''.join(box(b'mdta', k) for k in keys))

    def data(value, data_type=1):
        return box(b'data', struct.pack('>II', data_type, 0) + value)

    values = [data(struct.pack('>d', 4.7), 24), data(b'+40.4168-003.7038+650.123/'), data(b'Apple'),
              data(b'iPhone 15 Pro'), data(b'2024-10-30T12:00:00+0100')]
    ilst = box(b'ilst', b''.join(box(struct.pack('>I', i + 1), v) for i, v in enumerate(values)))
    meta = box(b'meta', full_box(b'hdlr', b'\0' * 4 + b'mdta' + b'\0' * 13) + keys_box + ilst)
    return box(b'ftyp', b'qt  \0\0\0\0qt  ') + box(b'moov', MVHD + meta) + MDAT


def android_mp4(coordinates=b'-33.8688+151.2093/'):
    # 'moov' al final del archivo y mvhd versión 1
    mvhd1 = full_box(b'mvhd', struct.pack('>QQIQ', 3813129600, 3813129600, 600, 6000) + b'\0' * 80, version=1)
    xyz = box(b'\xa9xyz', struct.pack('>HH', len(coordinates), 0x15c7) + coordinates)
    return FTYP + MDAT + box(b'moov', mvhd1 + box(b'udta', xyz))


def no_gps_mp4():
    return FTYP + box(b'moov', MVHD) + MDAT


def video_with_track(samples, fmt, handler, udta=b'', co64=False, chunks=None):
    """Vídeo con una pista de datos cuyas muestras están en 'mdat'; chunks = muestras por chunk."""
    mdat = box(b'mdat', b''.join(samples))
    sizes = [len(s) for s in samples]
    chunks = chunks or [len(samples)]
    offsets, pos, i = [], len(FTYP) + 8, 0
    for n in chunks:
        offsets.append(pos)
        pos += sum(sizes[i:i + n])
        i += n
    stsc_entries = []
    for index, n in enumerate(chunks):
        if not stsc_entries or stsc_entries[-1][1] != n:
            stsc_entries.append((index + 1, n, 1))
    stsc = full_box(b'stsc', struct.pack('>I', len(stsc_entries)) + b''.join(struct.pack('>III', *e) for e in stsc_entries))
    stsz = full_box(b'stsz', struct.pack('>II', 0, len(sizes)) + b''.join(struct.pack('>I', s) for s in sizes))
    offset_fmt, offset_box = ('>Q', b'co64') if co64 else ('>I', b'stco')
    stco = full_box(offset_box, struct.pack('>I', len(offsets)) + b''.join(struct.pack(offset_fmt, o) for o in offsets))
    stsd = full_box(b'stsd', struct.pack('>I', 1) + box(fmt, b'\0' * 8))
    minf = box(b'minf', full_box(b'hdlr', b'dhlr' + b'alis' + b'\0' * 13) + box(b'stbl', stsd + stsc + stsz + stco))
    mdia = box(b'mdia', full_box(b'hdlr', b'mhlr' + handler + b'\0' * 13) + minf)
    moov = box(b'moov', MVHD + (box(b'udta', udta) if udta else b'') + box(b'trak', mdia))
    return FTYP + mdat + moov


# --- GoPro (GPMF) ---

def klv(key, type_char, size, payload, repeat):
    return key + bytes([ord(type_char), size]) + struct.pack('>H', repeat) + payload + b'\0' * ((-len(payload)) % 4)


def nested(key, payload):
    return key + b'\0\x04' + struct.pack('>H', len(payload) // 4) + payload


def gopro_model_udta(model):
    return box(b'GPMF', nested(b'DEVC', klv(b'MINF', 'c', 1, model, len(model))))


def gps5_sample(fix, lat, lon, alt):
    strm = (klv(b'GPSF', 'L', 4, struct.pack('>L', fix), 1)
            + klv(b'GPSU', 'U', 16, b'241030120000.000', 1)
            + klv(b'SCAL', 'l', 4, struct.pack('>5l', 10000000, 10000000, 1000, 1000, 100), 5)
            + klv(b'GPS5', 'l', 20, struct.pack('>5l', round(lat * 1e7), round(lon * 1e7), round(alt * 1000), 0, 0) * 2, 2))
    accelerometer = nested(b'STRM', klv(b'ACCL', 's', 6, b'\0' * 12, 2))
    return nested(b'DEVC', klv(b'DVNM', 'c', 1, b'Camera', 6) + accelerometer + nested(b'STRM', strm))


def gps9_sample(fix, lat, lon, alt):
    # 9069 días desde 2000-01-01 = 2024-10-30; 43200.5 s = 12:00:00
    row = struct.pack('>7l2H', round(lat * 1e7), round(lon * 1e7), round(alt * 1000), 0, 0, 9069, 43200500, 150, fix)
    strm = (klv(b'TYPE', 'c', 1, b'lllllllSS', 9)
            + klv(b'SCAL', 'l', 4, struct.pack('>9l', 10000000, 10000000, 1000, 1000, 100, 1, 1000, 100, 1), 9)
            + klv(b'GPS9', '?', 32, row, 1))
    return nested(b'DEVC', nested(b'STRM', strm))


# --- DJI (protobuf) ---

def varint(value):
    out = b''
    while True:
        byte, value = value & 0x7f, value >> 7
        out += bytes([byte | (0x80 if value else 0)])
        if not value:
            return out


def proto_field(field, wire_type, value):
    key = varint(field << 3 | wire_type)
    if wire_type == 0:
        return key + varint(value)
    if wire_type == 1:
        return key + value
    return key + varint(len(value)) + value


def dji_sample(protocol, path, lat, lon, alt_raw, units=0, when=None, radians=True):
    la, lo = (math.radians(lat), math.radians(lon)) if radians else (lat, lon)
    gps_info = ((proto_field(1, 0, units) if units else b'')
                + proto_field(2, 1, struct.pack('<d', la)) + proto_field(3, 1, struct.pack('<d', lo)))
    inner = (proto_field(1, 2, gps_info) + proto_field(2, 0, alt_raw)
             + (proto_field(6, 2, proto_field(1, 2, when)) if when else b''))
    for field in reversed(path):
        inner = proto_field(field, 2, inner)
    header = proto_field(1, 2, proto_field(1, 2, proto_field(1, 2, protocol))) if protocol else b''
    return header + proto_field(2, 2, b'\x08\x01') + inner


# --- Subtítulos DJI ---

def tx3g(text):
    data = text.encode()
    return struct.pack('>H', len(data)) + data
