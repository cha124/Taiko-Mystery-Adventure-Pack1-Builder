from __future__ import annotations

from pathlib import Path

from app.core.cia_reader import read_cia
from app.core.pack1_analyzer import analyze_pack1, classify_baseline_anomalies
from app.models.validation import ValidationIssue
from tests.synthetic_cia import make_synthetic_cia, make_synthetic_ncch
from tests.synthetic_romfs import make_synthetic_pack1_romfs


def _analyze(
    tmp_path: Path,
    *,
    include_musicinfo: bool = True,
    include_audio: bool = True,
    include_preview: bool = True,
    songinfo_chart_key: str = "test",
):
    romfs = make_synthetic_pack1_romfs(
        include_musicinfo=include_musicinfo,
        include_audio=include_audio,
        include_preview=include_preview,
        songinfo_chart_key=songinfo_chart_key,
    )
    cia = make_synthetic_cia(contents=(make_synthetic_ncch(romfs),))
    path = tmp_path / "synthetic.cia.fixture"
    path.write_bytes(cia)
    return analyze_pack1(read_cia(path))


def test_generates_slot_from_verified_references(tmp_path: Path) -> None:
    analysis = _analyze(tmp_path)
    assert analysis.issues == ()
    assert len(analysis.slots) == 1
    slot = analysis.slots[0]
    assert slot.internal_id == "test"
    assert slot.music_info_key == "d_test"
    assert slot.charts["oni"].endswith("test_m.bin")
    assert slot.main_audio.endswith("test_3ds.naac")


def test_rejects_missing_musicinfo(tmp_path: Path) -> None:
    analysis = _analyze(tmp_path, include_musicinfo=False)
    assert not analysis.slots
    assert {issue.code for issue in analysis.issues} == {"PACK1_INCOMPLETE_SONG_CONTENT"}


def test_rejects_missing_audio_references(tmp_path: Path) -> None:
    analysis = _analyze(tmp_path, include_preview=False)
    assert len(analysis.slots) == 1
    assert "PACK1_PREVIEW_AUDIO_MISSING" in {issue.code for issue in analysis.issues}


def test_rejects_songinfo_chart_key_mismatch(tmp_path: Path) -> None:
    analysis = _analyze(tmp_path, songinfo_chart_key="typo")
    assert len(analysis.slots) == 1
    assert "PACK1_CHART_KEY_MISMATCH" in {issue.code for issue in analysis.issues}


def _chart_mismatch(content_index: int, romfs_key: str) -> ValidationIssue:
    return ValidationIssue(
        "PACK1_CHART_KEY_MISMATCH",
        "ERROR",
        "mismatch",
        f"content[{content_index}]",
        {
            "content_index": content_index,
            "songinfo": "akb437",
            "romfs_keys": [romfs_key],
        },
    )


def _baseline_profile() -> dict[str, object]:
    return {
        "known_baseline_anomalies": [
            {
                "content_index": 69,
                "code": "PACK1_CHART_KEY_MISMATCH",
                "expected": {
                    "songinfo_chart_key": "akb437",
                    "romfs_chart_keys": ["akb347"],
                },
            }
        ]
    }


def test_exact_content_69_mismatch_is_known_baseline_warning() -> None:
    issue = classify_baseline_anomalies((_chart_mismatch(69, "akb347"),), _baseline_profile())[0]
    assert issue.severity == "WARNING"
    assert issue.classification == "KNOWN_BASELINE_ANOMALY"
    assert issue.details["songinfo"] == "akb437"


def test_same_keys_in_different_content_remain_error() -> None:
    issue = classify_baseline_anomalies((_chart_mismatch(68, "akb347"),), _baseline_profile())[0]
    assert issue.severity == "ERROR"
    assert issue.classification is None


def test_different_romfs_key_in_content_69_remains_error() -> None:
    issue = classify_baseline_anomalies((_chart_mismatch(69, "akb999"),), _baseline_profile())[0]
    assert issue.severity == "ERROR"
    assert issue.classification is None
