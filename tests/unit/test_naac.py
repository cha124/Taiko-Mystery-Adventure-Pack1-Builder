from __future__ import annotations

import hashlib

import pytest

from app.core.audio.naac import NAACParseError, inspect_naac
from tests.synthetic_audio import make_adts_stream, make_synthetic_naac


def test_finds_adts_after_unknown_synthetic_header() -> None:
    data = make_synthetic_naac(header_size=48, frame_count=4)
    inspection = inspect_naac(data)
    assert inspection.header_size == 48
    assert inspection.payload_offset == 48
    assert inspection.payload_size == len(data) - 48
    assert inspection.sha256 == hashlib.sha256(data).hexdigest()
    assert inspection.header_sha256 == hashlib.sha256(data[:48]).hexdigest()
    assert inspection.payload_sha256 == hashlib.sha256(data[48:]).hexdigest()
    assert inspection.unknown_header_bytes == data[:48]
    assert inspection.adts is not None
    assert inspection.adts.frame_count == 4


def test_does_not_accept_single_false_sync_in_header() -> None:
    false_header = b"\xff\xf1" + b"\x00" * 30
    payload = make_adts_stream(3)
    inspection = inspect_naac(false_header + payload)
    assert inspection.payload_offset == len(false_header)


def test_requires_multiple_consecutive_frames() -> None:
    with pytest.raises(NAACParseError) as caught:
        inspect_naac(b"unknown" + make_adts_stream(2))
    assert caught.value.code == "NAAC_PAYLOAD_NOT_FOUND"


def test_does_not_resynchronize_after_established_stream_is_corrupt() -> None:
    data = b"unknown" + make_adts_stream(3) + b"corrupt!" + make_adts_stream(3)
    with pytest.raises(NAACParseError) as caught:
        inspect_naac(data)
    assert caught.value.code == "NAAC_ADTS_STREAM_INVALID"
