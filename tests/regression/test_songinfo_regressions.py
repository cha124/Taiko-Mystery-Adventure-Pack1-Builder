from __future__ import annotations

import struct

import pytest

from app.core.binary import BinaryFormatError
from app.core.songinfo.parser import read_pointer_c_string


def _pointer_fixture(pointer: int, tail: bytes = b"") -> bytes:
    data = bytearray(32)
    struct.pack_into("<I", data, 0, pointer)
    data[8 : 8 + len(tail)] = tail
    return bytes(data)


def test_valid_nul_terminated_reference() -> None:
    assert read_pointer_c_string(_pointer_fixture(8, b"music/info\0"), 0).text == "music/info"


def test_empty_required_reference_is_error() -> None:
    with pytest.raises(BinaryFormatError):
        read_pointer_c_string(_pointer_fixture(8, b"\0"), 0)


def test_out_of_range_pointer_is_error() -> None:
    with pytest.raises(BinaryFormatError):
        read_pointer_c_string(_pointer_fixture(0x1000), 0)


def test_missing_nul_is_error_with_bounded_region() -> None:
    with pytest.raises(BinaryFormatError):
        read_pointer_c_string(_pointer_fixture(8, b"not-terminated"), 0, upper_bound=22)

