# Requisitos previos:

Crear y activar un entorno virtual en python 3.10+

# Instalación:

`pip install -r requirements.txt`

# Uso:

Ejecutar:

`python main.py`

El programa pide la ruta de la carpeta con las imágenes (.jpg, .heic, .avif, .png, .webp, .tiff y RAW: .dng,
.cr2, .cr3, .nef, .arw, .orf, .rw2, .pef, .srw, .raf) y los vídeos (.mov, .mp4, .m4v, .3gp). Admite rutas de
Windows (`C:\Users\yo\Fotos`, `%USERPROFILE%\Pictures`) y de Linux (`/home/yo/Fotos`, `~/Fotos`), con o sin
comillas, así que se puede pegar la ruta copiada o arrastrar la carpeta a la terminal. Pulsando Enter sin escribir
nada se usa la carpeta "media" del directorio actual.

Después pregunta si se quiere crear un CSV nuevo o actualizar uno existente. El CSV se busca y se guarda en la propia
carpeta de las fotos y vídeos:

- Pulsando Enter se usa `media_geo_information.csv` dentro de esa carpeta.
- Un nombre de archivo (`viaje.csv`) o una ruta relativa (`resultados/viaje.csv`) también se toman desde esa carpeta,
  tanto en las preguntas como en los argumentos `--nuevo` y `--actualizar`.
- Para guardarlo en otro sitio hay que escribir una ruta absoluta (`C:\Informes\viaje.csv`, `/home/yo/viaje.csv`,
  `~/viaje.csv`).

Los `.csv` de la carpeta no se analizan como si fueran fotos.

- **Nuevo**: se pide la ruta del CSV; si ya existe, se pregunta antes de sobrescribirlo.
- **Actualizar**: los archivos que ya estaban en el CSV se actualizan, los nuevos se añaden al final y el resto de
  filas se conservan. Cada archivo se identifica por su ruta completa (columna `0-MediaPath`), así que archivos
  con el mismo nombre en carpetas distintas (por ejemplo `GX010001.MP4` de dos tarjetas) no se pisan.

## Argumentos

Todo lo anterior se puede indicar también con argumentos; lo que no se indique se pregunta:

```
python main.py [carpeta] [--nuevo CSV | --actualizar CSV] [--sobrescribir] [--lang {es,en}]
```

| Castellano | Inglés | Qué hace |
|---|---|---|
| `carpeta` | `folder` | Carpeta con las fotos y vídeos |
| `-n CSV`, `--nuevo CSV` | `-n CSV`, `--new CSV` | Crea un CSV nuevo. Si ya existe, termina con un error salvo que se añada `--sobrescribir` |
| `-a CSV`, `--actualizar CSV` | `-u CSV`, `--update CSV` | Actualiza un CSV existente |
| `-s`, `--sobrescribir` | `-o`, `--overwrite` | Con `--nuevo`, sobrescribe el CSV si ya existe |
| `--lang {es,en}` | `--lang {es,en}` | Idioma de los mensajes |
| `-h`, `--help` | `-h`, `--help` | Muestra la ayuda |

Las opciones se aceptan en los dos idiomas sea cual sea el idioma de los mensajes (`--update` funciona con los
mensajes en castellano y `--actualizar` con los mensajes en inglés); la ayuda muestra las del idioma actual.

Ejemplos:

```
python main.py D:\Fotos --nuevo viaje.csv
python main.py ~/GoPro/tarjeta2 --actualizar viaje.csv
```

Con argumentos, si una ruta no es válida el programa no vuelve a preguntar: termina con un mensaje de error y código
de salida 1 (2 si la combinación de argumentos no es válida), para poder usarlo desde otros scripts.

## Idioma

La ayuda, las preguntas y los mensajes están en castellano y en inglés. El idioma se toma del sistema:

- **Linux y macOS**: de las variables `LANGUAGE`, `LC_ALL`, `LC_MESSAGES` y `LANG`, en ese orden de prioridad
  (el mismo que usan el resto de programas). Por ejemplo, con `LANGUAGE=es:en` se usa el castellano aunque
  `LANG` esté en inglés.
- **Windows**: del idioma de la interfaz de Windows.

Si el idioma del sistema no es castellano ni inglés, se usa el inglés. Para elegirlo a mano: `--lang es` o
`--lang en`. Los nombres de las columnas del CSV y sus valores no se traducen, para que un mismo CSV se pueda
actualizar desde cualquier idioma.

Los mensajes de error que genera `argparse` por su cuenta (por ejemplo, al combinar `--nuevo` y `--actualizar`)
quedan en inglés.

Las traducciones están en `geo_extractor/i18n.py`: para añadir o cambiar un texto basta con editar el diccionario
`MESSAGES`; un test comprueba que cada texto existe en los dos idiomas.

## Resultado

El CSV solo guarda la fecha y la ubicación de cada archivo. Las fechas tienen el mismo formato en fotos y vídeos
(`2024:10:30 12:00:00`) y las coordenadas están en grados decimales.

| Columna | Contenido |
|---|---|
| `0-MediaFileName` | Nombre del archivo |
| `0-MediaPath` | Ruta completa (identifica el archivo al actualizar el CSV) |
| `0-FileType` | `image` o `video` |
| `DateTimeOriginal` | Fecha y hora de la foto o del vídeo, en la hora local de la cámara |
| `OffsetTimeOriginal` | Zona horaria de `DateTimeOriginal` (`+01:00`), si la cámara la guarda |
| `GPSDateTime` | Fecha y hora del GPS (UTC) |
| `CreationTime` | Fecha de creación del archivo de vídeo (UTC) |
| `Latitude`, `Longitude` | Coordenadas en grados decimales (sur y oeste en negativo) |
| `Altitude` | Altitud en metros |
| `GPSSource` | De dónde se ha sacado la ubicación: `EXIF` (fotos), `QuickTime` (móviles), `GoPro GPMF`, `DJI djmd`, `Subtítulos` o el nombre del `.SRT` |

Cada cámara guarda unas fechas u otras, así que es normal que algunas columnas queden vacías. Al actualizar un CSV de
una versión anterior, sus columnas de más (marca, modelo, datos EXIF...) se eliminan.

Desde otro programa, `get_media_info()` sigue devolviendo todos los metadatos del archivo, no solo estos.

## Cámaras de acción y drones

- **GoPro** (HERO5 en adelante y MAX): se lee la telemetría GPMF del vídeo y se toma la primera posición con
  señal GPS válida (fix 2D/3D).
- **DJI** (Osmo Action 4/5 Pro/6, Osmo 360, Mini 4/5 Pro, Air 3/3S, Mavic 3/3 Pro/4 Pro, Avata 2, Neo,
  Matrice 30/4E): se leen los metadatos de la pista `djmd`.
- **DJI con subtítulos** (Mini 2, Air 2S, Mavic 2, Phantom...): se leen los subtítulos incrustados en el vídeo
  o el archivo `.SRT` con el mismo nombre que el vídeo, que tiene que estar en la misma carpeta.

La columna `GPSSource` indica de dónde se ha sacado la posición y `GPSDateTime` la hora GPS (UTC) cuando la hay.

# Estructura

```
main.py                  # preguntas al usuario y ejecución
csv_store.py             # leer, fusionar y escribir el CSV
geo_extractor/           # extracción de metadatos, sin interacción con el usuario
├── extractor.py         # get_media_info(ruta): elige el lector según el archivo
├── images.py            # fotos (EXIF con Pillow)
├── raw.py               # RAW de cámara (DNG, CR2, CR3, NEF, ARW, ORF, RW2, PEF, SRW, RAF)
├── videos.py            # vídeos MP4/MOV (móviles, pistas de telemetría y subtítulos)
├── action_cameras.py    # formatos de GoPro (GPMF) y DJI (protobuf y subtítulos)
├── mp4.py               # lectura de cajas MP4/QuickTime, compartida por vídeos y CR3
└── i18n.py              # traducciones (castellano e inglés) y detección del idioma
tests/                   # tests con pytest; builders.py genera los archivos de prueba
```

Para usar la extracción desde otro programa:

```python
from geo_extractor import get_media_info

info = get_media_info("D:/Fotos/IMG_0001.HEIC")
print(info.get("Latitude"), info.get("Longitude"))
```

# Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

Los tests generan sus propios archivos de prueba (fotos, RAW y vídeos de cada formato) en carpetas temporales.
