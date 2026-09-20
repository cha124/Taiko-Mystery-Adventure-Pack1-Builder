from __future__ import annotations

import pytest

from app.core.audio.adts import ADTSParseError, parse_adts_frame, parse_adts_stream
from tests.synthetic_audio import make_adts_frame, make_adts_stream


def test_parses_multiple_32khz_stereo_aac_lc_frames() -> None:
    data = make_adts_stream(3, sample_rate_index=5, channel_configuration=2, profile=1)
    stream = parse_adts_stream(data)
    frame = stream.frames[0]
    assert frame.syncword == 0xFFF
    assert frame.profile == 1
    assert frame.audio_object_type == 2
    assert frame.sample_rate == 32000
    assert frame.channels == 2
    assert frame.header_length == 7
    assert frame.payload_length == 20
    assert stream.statistics.frame_count == 3
    assert stream.statistics.audio_object_type_name == "AAC-LC"


@pytest.mark.parametrize("mpeg_id", [0, 1])
def test_preserves_mpeg_id(mpeg_id: int) -> None:
    stream = parse_adts_stream(make_adts_stream(3, mpeg_id=mpeg_id))
    assert stream.statistics.mpeg_id == mpeg_id
    assert stream.statistics.mpeg_version == ("MPEG-2" if mpeg_id else "MPEG-4")


def test_parses_crc_present_header() -> None:
    frame = parse_adts_frame(make_adts_frame(protection_absent=False))
    assert frame.crc_present
    assert frame.header_length == 9
    assert frame.payload_length == 20


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xff\xf1", "ADTS_TRUNCATED_HEADER"),
        (b"not adts", "ADTS_BAD_SYNC"),
    ],
)
def test_rejects_truncated_header_and_bad_sync(data: bytes, code: str) -> None:
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == code


def test_rejects_truncated_frame() -> None:
    data = make_adts_frame()[:-1]
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_TRUNCATED_FRAME"


def test_rejects_reserved_sample_rate_index() -> None:
    data = make_adts_frame(sample_rate_index=13)
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_INVALID_SAMPLE_RATE_INDEX"


def test_rejects_reserved_layer() -> None:
    data = bytearray(make_adts_frame())
    data[1] |= 0x02
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_RESERVED_LAYER"


def test_rejects_unsupported_channel_configuration() -> None:
    data = make_adts_frame(channel_configuration=0)
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_UNSUPPORTED_CHANNEL_CONFIGURATION"


def test_rejects_truncated_crc() -> None:
    data = make_adts_frame(protection_absent=False)[:8]
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_CRC_TRUNCATED"


def test_rejects_frame_length_smaller_than_header() -> None:
    data = bytearray(make_adts_frame())
    frame_length = 6
    data[3] = (data[3] & 0xFC) | ((frame_length >> 11) & 0x03)
    data[4] = (frame_length >> 3) & 0xFF
    data[5] = (data[5] & 0x1F) | ((frame_length & 0x07) << 5)
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_frame(data)
    assert caught.value.code == "ADTS_INVALID_FRAME_LENGTH"


@pytest.mark.parametrize(
    "changed",
    [
        {"sample_rate_index": 4},
        {"channel_configuration": 1},
        {"profile": 0},
    ],
)
def test_rejects_format_change_between_frames(changed: dict[str, int]) -> None:
    data = make_adts_frame() + make_adts_frame(**changed)
    with pytest.raises(ADTSParseError) as caught:
        parse_adts_stream(data)
    assert caught.value.code == "ADTS_FORMAT_CHANGED"


def test_raw_data_blocks_drive_duration_and_measured_bitrate() -> None:
    data = make_adts_stream(2, raw_data_blocks=1)
    stats = parse_adts_stream(data).statistics
    assert stats.total_samples == 2 * 2 * 1024
    assert stats.duration_seconds == pytest.approx(4096 / 32000)
    assert stats.measured_bitrate_bps == pytest.approx(len(data) * 8 / stats.duration_seconds)
    assert stats.average_frame_size == pytest.approx(len(data) / 2)


def test_rejects_unexplained_trailing_bytes_and_next_sync_mismatch() -> None:
    with pytest.raises(ADTSParseError) as short_tail:
        parse_adts_stream(make_adts_stream(3) + b"\x00")
    assert short_tail.value.code == "ADTS_TRAILING_BYTES"
    with pytest.raises(ADTSParseError) as bad_next:
        parse_adts_stream(make_adts_stream(3) + b"\x00" * 7)
    assert bad_next.value.code == "ADTS_NEXT_SYNC_MISMATCH"
