from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from app.core.audio import analyzer
from app.core.audio.analyzer import AudioScanReport, run_audio_forensics, run_audio_scan
from app.models.fingerprint import Pack1Fingerprint, ReadCompatibility
from app.models.validation import ValidationIssue
from tests.synthetic_cia import make_synthetic_cia, make_synthetic_ncch
from tests.synthetic_romfs import make_synthetic_pack1_romfs


def test_audio_report_cannot_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "source.cia"
    original = b"not-a-real-cia"
    source.write_bytes(original)
    with pytest.raises(ValueError, match="must not overwrite"):
        run_audio_scan(source, output=source)
    assert source.read_bytes() == original


def test_audio_forensics_report_cannot_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "source.cia"
    original = b"not-a-real-cia"
    source.write_bytes(original)
    with pytest.raises(ValueError, match="audio forensics output must not overwrite"):
        run_audio_forensics(source, output=source)
    assert source.read_bytes() == original


def _run_synthetic_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    expected_slots: int,
    include_preview: bool = False,
):
    romfs = make_synthetic_pack1_romfs(include_preview=include_preview)
    source = tmp_path / f"synthetic-{expected_slots}.cia"
    source.write_bytes(make_synthetic_cia(contents=(make_synthetic_ncch(romfs),)))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    profile = {
        "verified_sha256": [source_hash],
        "verified_observations": {
            "song_slot_count": expected_slots,
            "main_references": 1,
            "preview_references": 1,
        },
    }
    monkeypatch.setattr(analyzer, "load_profile", lambda _name: profile)
    monkeypatch.setattr(
        analyzer,
        "fingerprint_pack1",
        lambda _image, _sha256, _profile: Pack1Fingerprint(
            ReadCompatibility.SUPPORTED, (), ()
        ),
    )
    return run_audio_scan(source, profile_name="synthetic")


def test_pack1_error_is_not_weakened_by_audio_scan(monkeypatch, tmp_path: Path) -> None:
    report = _run_synthetic_scan(monkeypatch, tmp_path, expected_slots=1)
    issue = next(
        issue for issue in report.collection_issues if issue.source_code == "PACK1_PREVIEW_AUDIO_MISSING"
    )
    assert issue.code == "PACK1_REFERENCE_ERROR"
    assert issue.severity == "ERROR"
    assert report.status == "FAIL"


def test_verified_slot_loss_is_an_audio_scan_error(monkeypatch, tmp_path: Path) -> None:
    report = _run_synthetic_scan(monkeypatch, tmp_path, expected_slots=2)
    issue = next(
        issue for issue in report.collection_issues if issue.code == "AUDIO_PACK1_SLOT_COUNT_MISMATCH"
    )
    assert issue.severity == "ERROR"
    assert issue.details == {"expected": 2, "detected": 1}


def test_known_baseline_issue_only_keeps_audio_scan_at_warning() -> None:
    validation_issue = ValidationIssue(
        "PACK1_CHART_KEY_MISMATCH",
        "WARNING",
        "known source anomaly",
        "content[69]",
        {"content_index": 69},
        "KNOWN_BASELINE_ANOMALY",
    )
    audio_issue = analyzer._pack1_issue_to_audio_issue(validation_issue)
    report = AudioScanReport(
        source=Path("source.cia"),
        source_size=0,
        source_sha256="a" * 64,
        compatibility={},
        song_count=0,
        records=(),
        collection_issues=(audio_issue,),
        header={},
    )
    assert audio_issue.code == "PACK1_REFERENCE_ANOMALY"
    assert audio_issue.source_code == "PACK1_CHART_KEY_MISMATCH"
    assert report.status == "WARNING"
