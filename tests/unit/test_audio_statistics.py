from __future__ import annotations

import struct

from app.core.audio.naac import inspect_naac
from app.core.audio.statistics import header_analysis
from app.models.audio import AudioFileAnalysis
from tests.synthetic_audio import make_adts_stream


def _record(*, content_index: int, role: str, frame_count: int) -> AudioFileAnalysis:
    header = bytearray(64)
    header[:4] = b"AAC "
    struct.pack_into("<I", header, 12, 32000)
    struct.pack_into("<H", header, 17, frame_count * 4)
    payload = make_adts_stream(frame_count)
    inspection = inspect_naac(bytes(header) + payload)
    return AudioFileAnalysis(
        content_index=content_index,
        internal_song_id=f"song-{content_index}",
        role=role,
        romfs_path=f"/song-{content_index}.naac",
        naac_size=len(header) + len(payload),
        naac_sha256=inspection.sha256,
        parse_status="SUCCESS",
        inspection=inspection,
    )


def test_discovers_unaligned_scaled_sample_candidate_without_claiming_sample_count() -> None:
    analysis = header_analysis(
        [_record(content_index=1, role="main", frame_count=3), _record(content_index=2, role="main", frame_count=4)]
    )
    candidate = next(
        item
        for item in analysis["field_candidates"]
        if item["scope"] == "all"
        and item["offset"] == 17
        and item["width"] == 2
        and item["endianness"] == "little"
        and item["interpretation"] == "decoded_nominal_samples_div_256_candidate"
    )
    assert candidate["alignment"] == 1
    assert candidate["confidence"] == "STRONGLY_CORRELATED"
    assert analysis["sample_count_status"] == "UNKNOWN"
    assert analysis["encoder_delay_status"] == "UNKNOWN"
    assert analysis["padding_status"] == "UNKNOWN"


def test_seek_like_array_is_correlated_but_not_confirmed() -> None:
    header = bytearray(64)
    frame_size = len(make_adts_stream(1))
    struct.pack_into("<4I", header, 48, 0, frame_size, frame_size * 2, frame_size * 3)
    inspection = inspect_naac(bytes(header) + make_adts_stream(4))
    record = AudioFileAnalysis(
        content_index=1,
        internal_song_id="song",
        role="preview",
        romfs_path="/song.naac",
        naac_size=inspection.total_size,
        naac_sha256=inspection.sha256,
        parse_status="SUCCESS",
        inspection=inspection,
    )
    seek = header_analysis([record])["seek_table_analysis"]
    assert seek["candidate_file_count"] == 1
    assert seek["confirmed"] is False
    assert seek["confidence"] == "STRONGLY_CORRELATED"
    assert seek["signatures"][0]["offset"] == 48
    assert seek["signatures"][0]["match_ratio"] == 1.0
