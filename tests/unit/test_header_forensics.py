from __future__ import annotations

import json
import struct
from pathlib import Path

from app.core.audio.analyzer import AudioScanReport
from app.core.audio.header_forensics import (
    analyze_header_forensics,
    field_candidates,
    frame_offset_table_hypothesis,
)
from app.core.audio.naac import inspect_naac
from app.models.audio import AudioFileAnalysis
from tests.synthetic_audio import make_adts_stream


def _record(
    index: int,
    *,
    frame_count: int,
    mpeg_id: int = 0,
    role: str = "main",
    mpeg0_table: bool = True,
) -> AudioFileAnalysis:
    payload = make_adts_stream(frame_count, mpeg_id=mpeg_id)
    header = bytearray(128)
    struct.pack_into("<I", header, 0x10 if mpeg_id == 0 else 0x50, frame_count * 1024)
    struct.pack_into("<I", header, 0x24 if mpeg_id == 0 else 0x54, len(payload))
    struct.pack_into("<I", header, 0x2C, 0x30)
    initial = inspect_naac(bytes(header) + payload)
    if mpeg0_table:
        for number, offset in enumerate(initial.frame_offsets):
            struct.pack_into("<I", header, 0x30 + number * 4, offset)
    inspection = inspect_naac(bytes(header) + payload)
    return AudioFileAnalysis(
        content_index=index,
        internal_song_id=f"song-{index}",
        role=role,
        romfs_path=f"/{role}-{index}.naac",
        naac_size=inspection.total_size,
        naac_sha256=inspection.sha256,
        parse_status="SUCCESS",
        inspection=inspection,
    )


def test_forensics_field_confidence_requires_five_files_and_three_values() -> None:
    records = [_record(index, frame_count=index + 3) for index in range(4)]
    candidate = next(
        item
        for item in field_candidates(records)
        if item["scope"] == "all"
        and item["target"] == "decoded_nominal_samples"
        and item["offset"] == 0x10
        and item["width"] == 4
        and item["endianness"] == "little"
        and item["transform"] == "identity"
    )
    assert candidate["match_ratio"] == 1.0
    assert candidate["confidence"] == "POSSIBLE"


def test_forensics_reports_mpeg1_candidate_at_another_offset() -> None:
    records = [_record(index, frame_count=index + 3, mpeg_id=1, mpeg0_table=False) for index in range(5)]
    candidates = field_candidates(records)
    candidate = next(
        item
        for item in candidates
        if item["scope"] == "mpeg_id_1"
        and item["target"] == "decoded_nominal_samples"
        and item["offset"] == 0x50
        and item["width"] == 4
        and item["endianness"] == "little"
        and item["transform"] == "identity"
    )
    assert candidate["confidence"] == "STRONGLY_CORRELATED"


def test_frame_offset_table_uses_formula_and_stays_semantic_unknown() -> None:
    records = [_record(index, frame_count=index + 3) for index in range(5)]
    analysis = frame_offset_table_hypothesis(records)
    first = analysis["per_file"][0]
    assert first["capacity"] == (128 - 0x30) // 4
    assert first["predicted_stride"] == 1
    assert first["exact_match"] is True
    assert analysis["cohort_summary"]["mpeg_id_0"]["exact_matches_over_files"] == "5 / 5"
    assert analysis["semantic_status"] == "UNKNOWN"


def test_forensics_json_has_schema_and_no_full_header_dump(tmp_path: Path) -> None:
    records = [_record(index, frame_count=index + 3) for index in range(5)]
    report = AudioScanReport(
        source=tmp_path / "source.cia",
        source_size=123,
        source_sha256="a" * 64,
        compatibility={"read": "SUPPORTED", "write": "BLOCKED"},
        song_count=5,
        records=tuple(records),
        collection_issues=(),
        header={},
    )
    payload = analyze_header_forensics(
        records,
        source=report.source,
        source_size=report.source_size,
        source_sha256=report.source_sha256,
        audio_report=report,
    )
    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["generation_approved"] is False
    assert payload["cohorts"]["all"]["file_count"] == 5
    serialized = json.dumps(payload)
    assert "unknown_header_bytes" not in serialized
    assert "frame_payload_lengths" not in serialized
