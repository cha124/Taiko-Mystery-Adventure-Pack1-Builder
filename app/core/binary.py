from __future__ import annotations

import struct


class BinaryFormatError(ValueError):
    """Raised when a binary container cannot be parsed safely."""


def require_range(data: bytes | memoryview, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise BinaryFormatError(
            f"{label} is outside the file: offset=0x{offset:X}, "
            f"size=0x{size:X}, file_size=0x{len(data):X}"
        )


def u16be(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 2, label)
    return struct.unpack_from(">H", data, offset)[0]


def u32be(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 4, label)
    return struct.unpack_from(">I", data, offset)[0]


def u16le(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 2, label)
    return struct.unpack_from("<H", data, offset)[0]


def u32le(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 4, label)
    return struct.unpack_from("<I", data, offset)[0]


def u64be(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 8, label)
    return struct.unpack_from(">Q", data, offset)[0]


def u64le(data: bytes | memoryview, offset: int, label: str) -> int:
    require_range(data, offset, 8, label)
    return struct.unpack_from("<Q", data, offset)[0]


def align(value: int, boundary: int = 0x40) -> int:
    return (value + boundary - 1) & ~(boundary - 1)

