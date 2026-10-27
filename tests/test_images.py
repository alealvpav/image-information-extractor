import pytest

from geo_extractor import get_media_info
from geo_extractor.images import dms_to_decimal
from tests.builders import MADRID, RAW_FILES, save_image


def assert_madrid(info):
    assert info['Latitude'] == pytest.approx(MADRID[0])
    assert info['Longitude'] == pytest.approx(MADRID[1])
    assert info['Altitude'] == pytest.approx(MADRID[2])


@pytest.mark.parametrize('name, fmt', [
    ('foto.jpg', None), ('foto.jpeg', None), ('FOTO.JPG', None), ('foto.heic', None), ('foto.heif', 'HEIF'),
    ('foto.avif', None), ('foto.png', None), ('foto.webp', None), ('foto.tiff', None), ('foto.tif', None),
])
def test_common_image_formats(tmp_path, name, fmt):
    path = tmp_path / name
    save_image(path, fmt)
    info = get_media_info(str(path))
    assert info['Make'] == 'TestMake'
    assert_madrid(info)


@pytest.mark.parametrize('name, mode', [('gris.jpg', 'L'), ('transparente.png', 'RGBA')])
def test_image_modes(tmp_path, name, mode):
    path = tmp_path / name
    save_image(path, mode=mode)
    assert_madrid(get_media_info(str(path)))


@pytest.mark.parametrize('name', RAW_FILES)
def test_raw_formats(tmp_path, name):
    make, build = RAW_FILES[name]
    path = tmp_path / name
    path.write_bytes(build())
    info = get_media_info(str(path))
    assert info['Make'] == make
    assert_madrid(info)


def test_cr3_reads_exif_block(tmp_path):
    path = tmp_path / 'raw.cr3'
    path.write_bytes(RAW_FILES['raw.cr3'][1]())
    info = get_media_info(str(path))
    assert info['Model'] == 'Canon EOS R5'
    assert info['DateTimeOriginal'] == '2024:10:30 12:00:00'


def test_image_without_gps(tmp_path):
    path = tmp_path / 'sin_gps.jpg'
    save_image(path, gps=None)
    info = get_media_info(str(path))
    assert info['Make'] == 'TestMake'
    assert 'Latitude' not in info


def test_large_binary_values_are_dropped(tmp_path):
    path = tmp_path / 'makernote.jpg'
    save_image(path, extra={0x927C: b'\x01' * 5000})  # MakerNote
    info = get_media_info(str(path))
    assert 'MakerNote' not in info
    assert info['GPSAltitudeRef'] == b'\x00'  # los valores binarios pequeños se conservan


@pytest.mark.parametrize('dms, ref, expected', [
    ((40, 25, 0.48), 'N', 40.4168), ((3, 42, 13.68), 'W', -3.7038), ((34, 36, 12), 'S', -34.6033333),
])
def test_dms_to_decimal(dms, ref, expected):
    assert dms_to_decimal(dms, ref) == pytest.approx(expected)


def test_unreadable_file_raises(tmp_path):
    path = tmp_path / 'no_es_foto.jpg'
    path.write_bytes(b'esto no es una imagen')
    with pytest.raises(Exception):
        get_media_info(str(path))
