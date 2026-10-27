import os
from .images import get_exif_dict
from .videos import get_video_dict, is_subtitle, is_video


def get_file_type(fname: str):
    return "video" if is_video(fname) else "image"


# Archivos que pueden estar en la carpeta pero no son fotos ni vídeos: los CSV de resultados que se guardan en ella
IGNORED_EXTENSIONS = ('.csv',)


def get_media_files(media_dir: str):
    """Archivos de la carpeta que hay que analizar, ordenados por nombre (sin subcarpetas ni ocultos)."""
    # Los .SRT de los drones DJI se leen junto con su vídeo, no como archivos aparte
    return sorted(f for f in os.listdir(media_dir)
                  if os.path.isfile(os.path.join(media_dir, f)) and not f.startswith(".") and not is_subtitle(f)
                  and not f.lower().endswith(IGNORED_EXTENSIONS))


def get_media_info(path: str):
    """Metadatos de una foto o vídeo, con Latitude/Longitude/Altitude en grados decimales si tiene GPS."""
    if is_video(path):
        info = get_video_dict(path)
    else:
        info = get_exif_dict(path)
    return {str(k): v for k, v in info.items()}
