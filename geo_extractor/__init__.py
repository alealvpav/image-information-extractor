"""Extracción de metadatos y geolocalización de fotos (incluidos RAW) y vídeos (incluidas GoPro y DJI)."""
from .extractor import get_file_type, get_media_files, get_media_info

__all__ = ["get_file_type", "get_media_files", "get_media_info"]
