import io
import struct
from PIL import Image
from PIL.ExifTags import IFD
from .i18n import _
from .mp4 import iter_boxes

RAW_EXTENSIONS = ('.dng', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.orf', '.rw2', '.pef',
                  '.srw', '.raf')

# Cabeceras TIFF "propias" de algunos fabricantes, que Pillow no reconoce
OLYMPUS_HEADERS = (b'IIRO', b'IIRS', b'MMOR')   # ORF
PANASONIC_HEADER = b'IIU\x00'                    # RW2

# Caja 'uuid' de Canon (CR3) que contiene los metadatos CMT1..CMT4
CANON_UUID = bytes.fromhex('85c0b687820f11e08111f4ce462b6a48')

# Etiqueta de los RW2 de Panasonic con un JPEG que lleva el EXIF completo
PANASONIC_JPG_FROM_RAW = 0x002E


def is_raw(fname: str):
    return fname.lower().endswith(RAW_EXTENSIONS)


def get_raw_exif(fname: str):
    """Devuelve (etiquetas base, {IFD: etiquetas}) de un RAW sin decodificar la imagen."""
    with open(fname, 'rb') as f:
        data = f.read()

    if data.startswith(b'FUJIFILMCCD-RAW'):
        return get_raf_exif(data)
    if data[4:8] == b'ftyp':
        return get_cr3_exif(data)
    if data.startswith(PANASONIC_HEADER):
        return get_rw2_exif(data)
    if data.startswith(OLYMPUS_HEADERS):
        data = (b'II*\x00' if data.startswith(b'II') else b'MM\x00*') + data[4:]
    return get_tiff_exif(data)


def get_tiff_exif(data: bytes):
    # DNG, CR2, NEF, ARW, ORF, PEF, SRW...: son TIFF y el IFD0 apunta a los bloques EXIF y GPS
    exif = Image.Exif()
    exif.load(data)
    return dict(exif), {ifd: exif.get_ifd(ifd) for ifd in (IFD.Exif, IFD.GPSInfo)}


def get_jpeg_exif(jpeg: bytes):
    exif = Image.open(io.BytesIO(jpeg)).getexif()
    return dict(exif), {ifd: exif.get_ifd(ifd) for ifd in (IFD.Exif, IFD.GPSInfo)}


def get_raf_exif(data: bytes):
    # Fujifilm: la cabecera indica dónde está el JPEG de vista previa, que lleva el EXIF
    offset, length = struct.unpack('>II', data[84:92])
    return get_jpeg_exif(data[offset:offset + length])


def get_rw2_exif(data: bytes):
    # Panasonic: el IFD0 usa etiquetas propias; el EXIF completo está en un JPEG incrustado
    exif = Image.Exif()
    exif.load(b'II*\x00' + data[4:])
    jpeg = exif.get(PANASONIC_JPG_FROM_RAW)
    if isinstance(jpeg, bytes):
        return get_jpeg_exif(jpeg)
    raise ValueError(_("error_rw2_no_exif"))


def load_tiff(data: bytes):
    exif = Image.Exif()
    exif.load(data)
    return dict(exif)


def get_cr3_exif(data: bytes):
    # Canon CR3: dentro de moov/uuid hay un TIFF por bloque: CMT1 (IFD0), CMT2 (EXIF) y CMT4 (GPS)
    for box_type, start, end in iter_boxes(data, 0, len(data)):
        if box_type != b'moov':
            continue
        for child_type, child_start, child_end in iter_boxes(data, start, end):
            if child_type == b'uuid' and data[child_start:child_start + 16] == CANON_UUID:
                blocks = {t: data[s:e] for t, s, e in iter_boxes(data, child_start + 16, child_end)}
                base = load_tiff(blocks[b'CMT1']) if b'CMT1' in blocks else {}
                ifds = {IFD.Exif: load_tiff(blocks[b'CMT2']) if b'CMT2' in blocks else {},
                        IFD.GPSInfo: load_tiff(blocks[b'CMT4']) if b'CMT4' in blocks else {}}
                return base, ifds
    raise ValueError(_("error_cr3_no_metadata"))
