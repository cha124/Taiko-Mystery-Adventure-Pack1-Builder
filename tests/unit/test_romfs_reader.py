from __future__ import annotations

import hashlib

import pytest

from app.core.romfs_reader import (
    RomFSCycleError,
    RomFSDuplicatePathError,
    RomFSFormatError,
    read_romfs,
)
from tests.synthetic_romfs import make_synthetic_romfs


def test_reads_normal_tree_and_hashes_file() -> None:
    data = make_synthetic_romfs()
    image = read_romfs(data, 0, len(data))
    assert image.directories == ("/songs",)
    assert len(image.files) == 1
    entry = image.files[0]
    assert entry.path == "/songs/test.bin"
    assert entry.size == len(b"synthetic-file-data")
    assert entry.sha256 == hashlib.sha256(b"synthetic-file-data").hexdigest()


def test_rejects_out_of_range_directory_entry() -> None:
    data = make_synthetic_romfs(out_of_range_child=True)
    with pytest.raises(RomFSFormatError, match="non-entry offset"):
        read_romfs(data, 0, len(data))


def test_rejects_duplicate_path() -> None:
    data = make_synthetic_romfs(duplicate_path=True)
    with pytest.raises(RomFSDuplicatePathError, match="duplicate RomFS path"):
        read_romfs(data, 0, len(data))


def test_rejects_file_sibling_cycle() -> None:
    data = make_synthetic_romfs(file_cycle=True)
    with pytest.raises(RomFSCycleError, match="file sibling cycle"):
        read_romfs(data, 0, len(data))


def test_rejects_file_region_overflow() -> None:
    data = make_synthetic_romfs(out_of_range_file=True)
    with pytest.raises(RomFSFormatError, match="exceeds the RomFS file data region"):
        read_romfs(data, 0, len(data))
