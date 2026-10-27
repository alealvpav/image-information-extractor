import pytest

from geo_extractor import get_media_info
from geo_extractor.videos import parse_iso6709
from tests import builders as b


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


# ---------------------------------------------------------------------------
# Móviles
# ---------------------------------------------------------------------------

def test_iphone_video(tmp_path):
    info = get_media_info(write(tmp_path, 'IMG_0001.MOV', b.iphone_mov()))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((40.4168, -3.7038, 650.123))
    assert info['Make'] == 'Apple'
    assert info['Model'] == 'iPhone 15 Pro'
    assert info['GPSHorizontalAccuracy'] == pytest.approx(4.7)
    assert info['DateTimeOriginal'] == '2024-10-30T12:00:00+0100'
    assert info['GPSSource'] == 'QuickTime'


def test_android_video_with_moov_at_the_end(tmp_path):
    info = get_media_info(write(tmp_path, 'VID.mp4', b.android_mp4()))
    assert (info['Latitude'], info['Longitude']) == pytest.approx((-33.8688, 151.2093))
    assert info['CreationTime'] == '2024:10:30 10:40:00'


def test_video_without_gps(tmp_path):
    info = get_media_info(write(tmp_path, 'sin_gps.mp4', b.no_gps_mp4()))
    assert 'Latitude' not in info
    assert info['CreationTime'] == '2024:10:30 10:40:00'


def test_broken_video_raises(tmp_path):
    with pytest.raises(ValueError):
        get_media_info(write(tmp_path, 'roto.mov', b'esto no es un video'))


@pytest.mark.parametrize('value, expected', [
    ('+40.4168-003.7038+650.123/', (40.4168, -3.7038, 650.123)),   # grados
    ('+4024.10-00342.22/', (40.401667, -3.703667, None)),            # grados y minutos
    ('+402500.48-0034213.68/', (40.4168, -3.7038, None)),            # grados, minutos y segundos
])
def test_parse_iso6709(value, expected):
    result = parse_iso6709(value)
    assert (result['Latitude'], result['Longitude']) == pytest.approx(expected[:2], abs=1e-6)
    assert result.get('Altitude') == (pytest.approx(expected[2]) if expected[2] is not None else None)


# ---------------------------------------------------------------------------
# GoPro
# ---------------------------------------------------------------------------

def test_gopro_gps5_skips_samples_without_fix(tmp_path):
    samples = [b.gps5_sample(0, 1, 1, 1), b.gps5_sample(3, 28.123456, -16.654321, 2100.5)]
    data = b.video_with_track(samples, b'gpmd', b'meta', b.gopro_model_udta(b'HERO9 Black'))
    info = get_media_info(write(tmp_path, 'GX010001.MP4', data))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((28.123456, -16.654321, 2100.5))
    assert info['GPSDateTime'] == '2024:10:30 12:00:00'
    assert (info['Make'], info['Model'], info['GPSSource']) == ('GoPro', 'HERO9 Black', 'GoPro GPMF')


def test_gopro_gps9_with_co64_and_several_chunks(tmp_path):
    samples = [b.gps9_sample(0, 0, 0, 0)] * 3 + [b.gps9_sample(3, -33.8688, 151.2093, 58.0)]
    data = b.video_with_track(samples, b'gpmd', b'meta', b.gopro_model_udta(b'HERO12 Black'), co64=True, chunks=[1, 1, 2])
    info = get_media_info(write(tmp_path, 'GX020002.MP4', data))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((-33.8688, 151.2093, 58.0))
    assert info['GPSDateTime'] == '2024:10:30 12:00:00'
    assert info['Model'] == 'HERO12 Black'


def test_gopro_without_fix_has_no_position(tmp_path):
    data = b.video_with_track([b.gps5_sample(0, 42.0, -129.0, 9.0)] * 3, b'gpmd', b'meta')
    info = get_media_info(write(tmp_path, 'GX030003.MP4', data))
    assert 'Latitude' not in info


# ---------------------------------------------------------------------------
# DJI
# ---------------------------------------------------------------------------

def test_dji_osmo_action_4(tmp_path):
    samples = [b.dji_sample(b'dvtm_ac203.proto', (3, 4, 2), 0, 0, 0),
               b.dji_sample(None, (3, 4, 2), 43.2630, -2.9350, 18500, when=b'2024-10-30 10:00:01')]
    info = get_media_info(write(tmp_path, 'DJI_0001.MP4', b.video_with_track(samples, b'djmd', b'meta')))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((43.2630, -2.9350, 18.5))
    assert info['GPSDateTime'] == '2024:10:30 10:00:01'
    assert (info['Make'], info['Model'], info['GPSSource']) == ('DJI', 'Osmo Action 4', 'DJI djmd')


def test_dji_mini_4_pro_negative_altitude(tmp_path):
    samples = [b.dji_sample(b'dvtm_Mini4_Pro.proto', (3, 3, 4), 37.3891, -5.9845, 0xFFFFFFFFFFFFFF9C)]
    info = get_media_info(write(tmp_path, 'DJI_0002.MP4', b.video_with_track(samples, b'djmd', b'meta')))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((37.3891, -5.9845, -0.1))
    assert info['Model'] == 'Mini 4 Pro'


def test_dji_unknown_protocol_in_degrees(tmp_path):
    samples = [b.dji_sample(b'dvtm_Foo9.proto', (3, 3, 4), 41.3874, 2.1686, 100000, units=1, radians=False)]
    info = get_media_info(write(tmp_path, 'DJI_0003.MP4', b.video_with_track(samples, b'djmd', b'meta')))
    assert (info['Latitude'], info['Longitude']) == pytest.approx((41.3874, 2.1686))
    assert info['Model'] == 'Foo9'


def test_dji_embedded_subtitles(tmp_path):
    samples = [b.tx3g('FrameCnt: 1\n[latitude: 0.000000] [longitude: 0.000000]'),
               b.tx3g('[iso : 100] [latitude: 39.469900] [longtitude: -0.376300] [rel_alt: 1.200 abs_alt: 15.700]')]
    info = get_media_info(write(tmp_path, 'DJI_0004.MP4', b.video_with_track(samples, b'tx3g', b'sbtl')))
    assert (info['Latitude'], info['Longitude'], info['Altitude']) == pytest.approx((39.4699, -0.3763, 15.7))
    assert info['GPSSource'] == 'Subtítulos'


def test_dji_sidecar_srt(tmp_path):
    video = write(tmp_path, 'DJI_0005.MOV', b.video_with_track([b'\0' * 16], b'avc1', b'vide'))
    (tmp_path / 'DJI_0005.SRT').write_text(
        '1\n00:00:00,000 --> 00:00:01,000\nGPS(0,0,0) BAROMETER:0.0\n\n'
        '2\n00:00:01,000 --> 00:00:02,000\nGPS(-3.7038,40.4168,19) BAROMETER:1.9\n')
    info = get_media_info(video)
    assert (info['Latitude'], info['Longitude']) == pytest.approx((40.4168, -3.7038))
    assert info['GPSSource'] == 'DJI_0005.SRT'
