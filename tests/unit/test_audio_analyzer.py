from __future__ import annotations

from pathlib import Path

import pytest

from app.core.audio.analyzer import run_audio_scan


def test_audio_report_cannot_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "source.cia"
    original = b"not-a-real-cia"
    source.write_bytes(original)
    with pytest.raises(ValueError, match="must not overwrite"):
        run_audio_scan(source, output=source)
    assert source.read_bytes() == original
