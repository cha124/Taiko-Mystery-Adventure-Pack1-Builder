from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from app.core.tja import check_tja_bytes
from app.core.tja.model import CourseKind


def _chart(body: str, *, bpm: str = "260", course: str = "Oni") -> bytes:
    return (
        "TITLE:Test Song\n"
        f"BPM:{bpm}\n"
        "WAVE:test.wav\n"
        f"COURSE:{course}\n"
        "LEVEL:5\n"
        "#START\n"
        f"{body}\n"
        "#END\n"
    ).encode("utf-8")


def _only_measure(report):
    assert report.validation.is_valid, report.validation.messages
    return report.document.courses[0].measures[0]


def test_bpmchange_without_space_uses_longest_match() -> None:
    measure = _only_measure(check_tja_bytes(_chart("#BPMCHANGE260\n0000,")))
    command = measure.commands[0]
    assert command.name == "BPMCHANGE"
    assert command.value == Decimal("260")


def test_scroll_without_space_is_decimal_and_does_not_scale_time() -> None:
    normal = _only_measure(check_tja_bytes(_chart("#SCROLL1.0\n0000,")))
    slower_visual = _only_measure(check_tja_bytes(_chart("#SCROLL0.5\n0000,")))
    assert slower_visual.commands[0].value == Decimal("0.5")
    assert slower_visual.duration_seconds == normal.duration_seconds
    assert slower_visual.start_time_seconds == normal.start_time_seconds


def test_measure_eight_four_is_preserved_and_twice_four_four() -> None:
    eight_four = _only_measure(check_tja_bytes(_chart("#MEASURE8/4\n0000,")))
    four_four = _only_measure(check_tja_bytes(_chart("#MEASURE4/4\n0000,")))
    assert eight_four.commands[0].argument == "8/4"
    assert eight_four.commands[0].value == Fraction(8, 4)
    assert eight_four.time_signature == Fraction(8, 4)
    assert eight_four.duration_seconds == four_four.duration_seconds * 2


def test_measure_seven_eight_is_fraction() -> None:
    measure = _only_measure(check_tja_bytes(_chart("#MEASURE7/8\n0000,")))
    assert measure.time_signature == Fraction(7, 8)


def test_negative_offset_is_decimal() -> None:
    raw = (
        "TITLE:Offset\nBPM:120\nWAVE:test.wav\nOFFSET:-10\n"
        "COURSE:Oni\n#START\n0,\n#END\n"
    ).encode()
    report = check_tja_bytes(raw)
    assert report.document.header.offset == Decimal("-10")


def test_negative_decimal_delay_is_preserved_with_explicit_warning() -> None:
    report = check_tja_bytes(_chart("#DELAY-0.25\n0000,"))
    measure = report.document.courses[0].measures[0]
    assert measure.commands[0].value == Decimal("-0.25")
    assert measure.start_time_seconds == Decimal("-0.25")
    assert "TJA_NEGATIVE_DELAY_UNVERIFIED" in {m.code for m in report.validation.warnings}


def test_multiline_note_data_forms_one_measure() -> None:
    measure = _only_measure(check_tja_bytes(_chart("00110011\n00110011\n,")))
    assert measure.notes == "0011001100110011"


def test_course_aliases_include_edit_as_ura() -> None:
    report = check_tja_bytes(_chart("0000,", course="Edit"))
    assert report.document.courses[0].kind is CourseKind.URA


def test_start_argument_is_preserved_and_warned() -> None:
    raw = (
        "TITLE:Player\nBPM:120\nWAVE:test.wav\nCOURSE:Oni\n"
        "#START P1\n0000,\n#END\n"
    ).encode()
    report = check_tja_bytes(raw)
    assert report.document.courses[0].start_argument == "P1"
    assert "TJA_START_ARGUMENT_UNVERIFIED" in {m.code for m in report.validation.warnings}
