"""Lectura de la estructura de cajas (atoms) de MP4/QuickTime, compartida por vídeos y RAW CR3 de Canon."""
import struct


def iter_boxes(data: bytes, start=0, end=None):
    """Recorre las cajas entre start y end y devuelve (tipo, inicio del contenido, fin)."""
    end = len(data) if end is None else end
    pos = start
    while pos + 8 <= end:
        size, box_type = struct.unpack('>I4s', data[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack('>Q', data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            break
        yield box_type, pos + header, min(pos + size, end)
        pos += size
