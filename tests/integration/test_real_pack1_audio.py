from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.audio.analyzer import run_audio_forensics, run_audio_scan


def test_private_real_pack1_audio_scan() -> None:
    configured = os.environ.get("TAIKO_PACK1_TEST_CIA")
    if not configured:
        pytest.skip("TAIKO_PACK1_TEST_CIA is not configured")

    report = run_audio_scan(Path(configured))
    payload = report.to_dict()
    summary = payload["summary"]
    assert payload["source"]["sha256"] == (
        "655942fd605efc326ad1d8e7913af8c1b552e3a30548eb7d6c0233333d9373b7"
    )
    assert payload["read_only"] is True
    assert payload["encoding_approved"] is False
    assert payload["device_tested"] is False
    assert payload["compatibility"]["read"] == "SUPPORTED"
    assert payload["compatibility"]["write"] == "BLOCKED"
    assert summary["song_count"] == 77
    assert summary["main_references"] == 77
    assert summary["preview_references"] == 77
    assert summary["unique_naac_count"] == 154
    assert summary["distinct_reference_count"] == 154
    assert summary["distinct_content_hash_count"] == 154
    assert summary["success_count"] == 154
    assert summary["failure_count"] == 0
    assert summary["error_count"] == 0
    assert summary["payload_offset_distribution"] == {"4096": 154}

    # These assertions were promoted only after the initial full-Pack1 observation.
    for role in ("main", "preview"):
        role_summary = summary[role]
        assert role_summary["success_count"] == 77
        assert role_summary["sample_rate_distribution"] == {"32000": 77}
        assert role_summary["channel_distribution"] == {"2": 77}
        assert role_summary["profile_distribution"] == {"profile=1,AOT=2,AAC-LC": 77}
        assert role_summary["crc_distribution"] == {"none": 77}
        assert role_summary["header_size_distribution"] == {"4096": 77}

    assert summary["main"]["mpeg_id_distribution"] == {"0": 37, "1": 40}
    assert summary["preview"]["mpeg_id_distribution"] == {"0": 30, "1": 47}
    assert all(item["parse_status"] == "SUCCESS" for item in payload["files"])
    assert payload["header_analysis"]["seek_table_analysis"]["confirmed"] is False

    forensics = run_audio_forensics(Path(configured))
    assert forensics["source"]["sha256"] == (
        "655942fd605efc326ad1d8e7913af8c1b552e3a30548eb7d6c0233333d9373b7"
    )
    assert forensics["read_only"] is True
    assert forensics["device_tested"] is False
    assert forensics["generation_approved"] is False
    assert forensics["cohorts"]["all"]["file_count"] == 154
    assert forensics["cohorts"]["main"]["file_count"] == 77
    assert forensics["cohorts"]["preview"]["file_count"] == 77
    assert forensics["cohorts"]["mpeg_id_0"]["file_count"] == 67
    assert forensics["cohorts"]["mpeg_id_1"]["file_count"] == 87

    table = forensics["frame_offset_table_hypothesis"]
    assert table["confidence"] in {"PARTIAL_COHORT_EVIDENCE", "POSSIBLE", "UNKNOWN"}
    assert table["semantic_status"] == "UNKNOWN"
    for cohort_name in ("all", "main", "preview", "mpeg_id_0", "mpeg_id_1"):
        cohort = table["cohort_summary"][cohort_name]
        assert cohort["files"] == forensics["cohorts"][cohort_name]["file_count"]
        for key in (
            "exact_prefix_matches",
            "predicted_stride_matches",
            "generation_rule_matches",
        ):
            assert isinstance(cohort[key], int)
            assert 0 <= cohort[key] <= cohort["files"]
        assert 0.0 <= cohort["generation_rule_match_ratio"] <= 1.0
        assert cohort["confidence"] in {
            "FRAME_OFFSET_GENERATION_RULE_STRONGLY_CORRELATED",
            "POSSIBLE",
            "UNKNOWN",
        }

    required_per_file_fields = {
        "content_index",
        "role",
        "mpeg_id",
        "frame_count",
        "capacity",
        "predicted_stride",
        "observed_best_stride",
        "exact_prefix_match",
        "predicted_stride_match",
        "generation_rule_match",
        "entry_count",
        "matched_entries",
        "match_ratio",
        "tail_size",
        "tail_zero_bytes",
        "tail_non_zero_bytes",
        "table_tail_zero_ratio",
        "table_tail_zero",
    }
    for item in table["per_file"]:
        assert required_per_file_fields <= item.keys()
        assert item["role"] in {"main", "preview"}
        assert item["mpeg_id"] in {0, 1}
        assert 0.0 <= item["match_ratio"] <= 1.0
        assert 0.0 <= item["table_tail_zero_ratio"] <= 1.0
        assert isinstance(item["table_tail_zero"], bool)

    pointer = forensics["table_offset_pointer"]
    assert pointer["files"] == table["cohort_summary"]["all"]["files"]
    assert 0 <= pointer["matches"] <= pointer["files"]
    assert 0.0 <= pointer["match_ratio"] <= 1.0

    for key in ("decoded_nominal_samples_candidate", "payload_size_candidate"):
        candidate = forensics["mpeg_id_1"][key]
        assert candidate["status"] in {"FOUND", "NOT_FOUND"}
        assert isinstance(candidate["candidates"], list)

    alternatives = forensics["alternative_offset_arrays"]
    assert isinstance(alternatives["files_scanned"], int)
    assert isinstance(alternatives["files_with_candidate"], int)
    assert 0 <= alternatives["files_with_candidate"] <= alternatives["files_scanned"]
    assert forensics["decision"] in {
        "READY_FOR_AUDIO_CANDIDATE_PROTOTYPE",
        "MORE_AUDIO_RESEARCH_REQUIRED",
    }
