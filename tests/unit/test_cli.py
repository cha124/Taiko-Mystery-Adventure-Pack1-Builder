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
    assert "TJA VALID" in output
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
    assert "TJA INVALID" in output
    assert f"{path.resolve()}:6:1" in output
    assert 'Invalid MEASURE value "8/"' in output
