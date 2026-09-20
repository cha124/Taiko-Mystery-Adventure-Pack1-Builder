from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.job_runner import run_diagnostic


def test_private_real_pack1_diagnostic() -> None:
    configured = os.environ.get("TAIKO_PACK1_TEST_CIA")
    if not configured:
        pytest.skip("TAIKO_PACK1_TEST_CIA is not configured")

    report = run_diagnostic(Path(configured))
    payload = report.to_dict()
    assert payload["cia_sha256"] == (
        "655942fd605efc326ad1d8e7913af8c1b552e3a30548eb7d6c0233333d9373b7"
    )
    assert payload["title_id"] == "0004008c00190e00"
    assert payload["content_count"] == 78
    assert len(payload["song_slots"]) == 77
    assert len(payload["romfs_files"]) == 1445
    assert payload["compatibility"]["read"] == "SUPPORTED"
    assert payload["compatibility"]["write"] == "BLOCKED"

    anomalies = [
        issue
        for issue in payload["warnings"]
        if issue.get("classification") == "KNOWN_BASELINE_ANOMALY"
    ]
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly["code"] == "PACK1_CHART_KEY_MISMATCH"
    assert anomaly["location"] == "content[69]"
    assert anomaly["details"]["songinfo"] == "akb437"
    assert anomaly["details"]["romfs_keys"] == ["akb347"]

    slot = next(item for item in payload["song_slots"] if item["content_index"] == 69)
    assert slot["protected"] is True
    assert slot["replacement_eligible"] is False
