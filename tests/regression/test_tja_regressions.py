from __future__ import annotations

from app.core.tja import check_tja_bytes


def _valid_prefix() -> str:
    return "TITLE:45秒\nBPM:260\nWAVE:45秒.ogg\nCOURSE:Oni\n#START\n"


def test_unknown_command_is_an_error_with_source_line() -> None:
    source = _valid_prefix() + "#THISCOMMANDDOESNOTEXIST123\n0000,\n#END\n"
    report = check_tja_bytes(source.encode("utf-8"), "unknown.tja")
    error = next(m for m in report.validation.errors if m.code == "TJA_UNKNOWN_COMMAND")
    assert error.location is not None
    assert error.location.file == "unknown.tja"
    assert error.location.line == 6
    assert error.location.raw_text == "#THISCOMMANDDOESNOTEXIST123"


def test_normalizer_round_trip_preserves_ast_meaning() -> None:
    source = _valid_prefix() + "#BPMCHANGE260\n#SCROLL0.5\n#MEASURE8/4\n0000,\n#END\n"
    first = check_tja_bytes(source.encode("utf-8"), "original.tja")
    second = check_tja_bytes(first.canonical_text.encode("utf-8"), "normalized.tja")
    assert "#BPMCHANGE 260" in first.canonical_text
    assert "#SCROLL 0.5" in first.canonical_text
    assert "#MEASURE 8/4" in first.canonical_text
    assert first.document.semantic_fingerprint() == second.document.semantic_fingerprint()


def test_unicode_title_and_wave_are_not_damaged() -> None:
    source = _valid_prefix() + "0000,\n#END\n"
    report = check_tja_bytes(source.encode("utf-8"))
    assert report.document.header.title == "45秒"
    assert report.document.header.wave == "45秒.ogg"
    assert "TITLE:45秒" in report.canonical_text
    assert "WAVE:45秒.ogg" in report.canonical_text


def test_invalid_measure_reports_exact_source() -> None:
    source = _valid_prefix() + "#MEASURE8/\n0000,\n#END\n"
    report = check_tja_bytes(source.encode("utf-8"), "bad-measure.tja")
    error = next(m for m in report.validation.errors if m.code == "TJA_INVALID_MEASURE")
    assert error.location is not None
    assert str(error.location) == "bad-measure.tja:6:1"
    assert "8/" in error.message

