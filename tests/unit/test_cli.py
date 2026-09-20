from __future__ import annotations

from pathlib import Path

from app.main import main


def test_tja_check_cli_reports_valid(tmp_path: Path, capsys) -> None:
    path = tmp_path / "valid.tja"
    path.write_text(
        "TITLE:CLI\nBPM:120\nWAVE:test.wav\nCOURSE:Oni\n#START\n0000,\n#END\n",
        encoding="utf-8",
    )
    assert main(["tja-check", str(path)]) == 0
    output = capsys.readouterr().out
    assert "TJA SYNTAX: VALID" in output
    assert "TARGET CONVERSION: ELIGIBLE" in output
    assert "Oni: yes" in output
    assert "Errors: 0" in output


def test_tja_check_cli_reports_location_for_invalid_measure(tmp_path: Path, capsys) -> None:
    path = tmp_path / "invalid.tja"
    path.write_text(
        "TITLE:CLI\nBPM:120\nWAVE:test.wav\nCOURSE:Oni\n#START\n#MEASURE8/\n0000,\n#END\n",
        encoding="utf-8",
    )
    assert main(["tja-check", str(path)]) == 2
    output = capsys.readouterr().out
    assert "TJA SYNTAX: INVALID" in output
    assert "TARGET CONVERSION: BLOCKED" in output
    assert f"{path.resolve()}:6:1" in output
    assert 'Invalid MEASURE value "8/"' in output


def test_tja_check_cli_returns_one_for_conversion_blocked(tmp_path: Path, capsys) -> None:
    path = tmp_path / "blocked.tja"
    path.write_text(
        "TITLE:CLI\nBPM:120\nWAVE:test.wav\nCOURSE:Oni\n"
        "#START P1\n0000,\n#END\n",
        encoding="utf-8",
    )
    assert main(["tja-check", str(path)]) == 1
    output = capsys.readouterr().out
    assert "TJA SYNTAX: VALID" in output
    assert "TARGET CONVERSION: BLOCKED" in output
    assert "TJA_START_ARGUMENT_UNVERIFIED" in output


def test_diagnose_cli_reports_corrupt_container_as_exit_two(tmp_path: Path, capsys) -> None:
    source = tmp_path / "corrupt.cia"
    output = tmp_path / "report.json"
    source.write_bytes(b"broken")
    assert main(["diagnose", str(source), "--output", str(output)]) == 2
    console = capsys.readouterr().out
    assert "CIA DIAGNOSTIC: FAIL" in console
    assert "Title ID: (unavailable)" in console
    assert output.exists()
