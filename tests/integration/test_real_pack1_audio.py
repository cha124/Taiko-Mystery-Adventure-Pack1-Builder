from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.audio.analyzer import run_audio_scan


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
