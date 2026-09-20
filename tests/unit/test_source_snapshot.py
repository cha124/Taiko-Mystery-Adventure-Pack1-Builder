from __future__ import annotations

import hashlib

import pytest

from app.core.binary import BinaryFormatError
from app.core.source_snapshot import SourceSnapshot


def test_snapshot_is_unchanged_after_source_is_overwritten(tmp_path) -> None:
    source = tmp_path / "source.bin"
    original = b"immutable input snapshot"
    source.write_bytes(original)

    snapshot = SourceSnapshot.from_path(source)
    source.write_bytes(b"replacement bytes")

    assert snapshot.size == len(original)
    assert snapshot.sha256 == hashlib.sha256(original).hexdigest()
    assert snapshot.read(0, snapshot.size) == original
    assert snapshot.view().readonly


def test_snapshot_rejects_out_of_range_reads(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"1234")
    snapshot = SourceSnapshot.from_path(source)

    with pytest.raises(BinaryFormatError):
        snapshot.read(3, 2)
