from __future__ import annotations

from dataclasses import replace
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
        capacity = max((len(header) - 0x30) // 4, 0)
        for number, offset in enumerate(initial.frame_offsets[:capacity]):
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


def _with_corrupted_first_table_entry(record: AudioFileAnalysis) -> AudioFileAnalysis:
    assert record.inspection is not None
    header = bytearray(record.inspection.unknown_header_bytes)
    header[0x30] ^= 0xFF
    return replace(
        record,
        inspection=replace(record.inspection, unknown_header_bytes=bytes(header)),
    )


def _with_nonzero_table_tail(record: AudioFileAnalysis) -> AudioFileAnalysis:
    assert record.inspection is not None
    header = bytearray(record.inspection.unknown_header_bytes)
    header[0x3C] = 0xA5
    return replace(
        record,
        inspection=replace(record.inspection, unknown_header_bytes=bytes(header)),
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
    assert first["exact_prefix_match"] is True
    assert first["exact_match"] is True
    assert first["predicted_stride_match"] is True
    assert first["generation_rule_match"] is True
    assert first["table_tail_zero"] is True
    assert analysis["cohort_summary"]["mpeg_id_0"]["exact_matches_over_files"] == "5 / 5"
    assert analysis["cohort_summary"]["mpeg_id_0"]["exact_match_ratio"] == 1.0
    assert analysis["cohort_summary"]["mpeg_id_0"]["exact_prefix_matches"] == 5
    assert analysis["cohort_summary"]["mpeg_id_0"]["predicted_stride_matches"] == 5
    assert analysis["cohort_summary"]["mpeg_id_0"]["generation_rule_matches"] == 5
    assert (
        analysis["cohort_summary"]["mpeg_id_0"]["confidence"]
        == "FRAME_OFFSET_GENERATION_RULE_STRONGLY_CORRELATED"
    )
    assert analysis["confidence"] == "PARTIAL_COHORT_EVIDENCE"
    assert (
        analysis["exact_match_semantics"]
        == "exact_match is an alias for exact_prefix_match"
    )
    assert "table_tail_zero is observational only" in analysis["generation_rule_semantics"]
    assert analysis["semantic_status"] == "UNKNOWN"


def test_frame_offset_table_prefix_can_match_with_wrong_predicted_stride() -> None:
    analysis = frame_offset_table_hypothesis([_record(0, frame_count=21)])
    result = analysis["per_file"][0]

    assert result["frame_count"] == 21
    assert result["predicted_stride"] == 2
    assert result["observed_best_stride"] == 1
    assert result["exact_prefix_match"] is True
    assert result["predicted_stride_match"] is False
    assert result["generation_rule_match"] is False


def test_frame_offset_table_tail_is_observed_separately_from_generation_rule() -> None:
    record = _with_nonzero_table_tail(_record(0, frame_count=3))
    result = frame_offset_table_hypothesis([record])["per_file"][0]

    assert result["exact_prefix_match"] is True
    assert result["predicted_stride_match"] is True
    assert result["generation_rule_match"] is True
    assert result["table_tail_zero"] is False
    assert result["table_tail_zero_ratio"] < 1.0


def test_frame_offset_table_one_of_five_is_only_possible() -> None:
    records = [_record(index, frame_count=index + 3) for index in range(5)]
    records[0] = _with_corrupted_first_table_entry(records[0])

    summary = frame_offset_table_hypothesis(records)["cohort_summary"]["main"]

    assert summary["files"] == 5
    assert summary["exact_prefix_matches"] == 4
    assert summary["predicted_stride_matches"] == 5
    assert summary["generation_rule_matches"] == 4
    assert summary["exact_match_ratio"] == 0.8
    assert summary["confidence"] == "POSSIBLE"


def test_frame_offset_table_four_of_four_is_not_strong() -> None:
    records = [_record(index, frame_count=index + 3) for index in range(4)]

    summary = frame_offset_table_hypothesis(records)["cohort_summary"]["main"]

    assert summary["files"] == 4
    assert summary["exact_prefix_matches"] == 4
    assert summary["predicted_stride_matches"] == 4
    assert summary["generation_rule_matches"] == 4
    assert summary["exact_match_ratio"] == 1.0
    assert summary["confidence"] == "POSSIBLE"


def test_frame_offset_table_zero_of_n_is_unknown() -> None:
    records = [
        _with_corrupted_first_table_entry(
            _record(index, frame_count=index + 3, mpeg0_table=False)
        )
        for index in range(5)
    ]

    summary = frame_offset_table_hypothesis(records)["cohort_summary"]["mpeg_id_0"]

    assert summary["files"] == 5
    assert summary["exact_prefix_matches"] == 0
    assert summary["predicted_stride_matches"] == 5
    assert summary["generation_rule_matches"] == 0
    assert summary["exact_match_ratio"] == 0.0
    assert summary["confidence"] == "UNKNOWN"


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
    table = payload["frame_offset_table_hypothesis"]
    for cohort_name in ("all", "main", "preview", "mpeg_id_0", "mpeg_id_1"):
        assert {
            "files",
            "exact_prefix_matches",
            "predicted_stride_matches",
            "generation_rule_matches",
            "generation_rule_match_ratio",
            "confidence",
        } <= table["cohort_summary"][cohort_name].keys()
    serialized = json.dumps(payload)
    assert "unknown_header_bytes" not in serialized
    assert "frame_payload_lengths" not in serialized
