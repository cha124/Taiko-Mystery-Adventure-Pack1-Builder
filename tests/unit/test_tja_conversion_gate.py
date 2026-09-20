from __future__ import annotations

import pytest

from app.core.tja import check_tja_bytes


def _chart(body: str, start: str = "#START") -> bytes:
    return (
        "TITLE:Safety Gate\n"
        "BPM:120\n"
        "WAVE:test.wav\n"
        "COURSE:Oni\n"
        f"{start}\n"
        f"{body}\n"
        "#END\n"
    ).encode()


@pytest.mark.parametrize(
    ("body", "blocker"),
    [
        (
            "#BRANCHSTART r,50,100\n#N\n0000,\n#E\n0000,\n#M\n0000,\n#BRANCHEND",
            "TJA_BRANCH_SEMANTICS_UNSUPPORTED",
        ),
        ("#GOGOSTART\n0000,\n#GOGOEND", "TJA_GOGO_SEMANTICS_UNSUPPORTED"),
    ],
)
def test_recognized_but_unsupported_semantics_block_conversion(body: str, blocker: str) -> None:
    report = check_tja_bytes(_chart(body))
    assert report.syntax_valid
    assert not report.conversion_eligible
    assert blocker in report.conversion_blockers


def test_start_argument_is_valid_syntax_but_blocks_conversion() -> None:
    report = check_tja_bytes(_chart("0000,", "#START P1"))
    assert report.syntax_valid
    assert not report.conversion_eligible
    assert "TJA_START_ARGUMENT_UNVERIFIED" in report.conversion_blockers


def test_negative_delay_is_valid_syntax_but_blocks_conversion() -> None:
    report = check_tja_bytes(_chart("#DELAY-0.25\n0000,"))
    assert report.syntax_valid
    assert not report.conversion_eligible
    assert "TJA_NEGATIVE_DELAY_UNVERIFIED" in report.conversion_blockers


def test_supported_timing_commands_are_conversion_eligible() -> None:
    report = check_tja_bytes(
        _chart("#MEASURE4/4\n#SCROLL1.25\n#BPMCHANGE150\n#DELAY0.25\n0000,")
    )
    assert report.syntax_valid
    assert report.conversion_eligible
    assert report.conversion_blockers == ()


def test_unknown_command_is_invalid_and_blocks_conversion() -> None:
    report = check_tja_bytes(_chart("#THISISUNKNOWN\n0000,"))
    assert not report.syntax_valid
    assert not report.conversion_eligible
    assert "TJA_UNKNOWN_COMMAND" in report.conversion_blockers
