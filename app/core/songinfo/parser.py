from __future__ import annotations

from dataclasses import dataclass
import struct

from app.core.binary import BinaryFormatError


@dataclass(frozen=True)
class BoundedCString:
    offset: int
    raw: bytes
    encoding: str

    @property
    def text(self) -> str:
        return self.raw.decode(self.encoding)


def read_bounded_c_string(
    data: bytes,
    pointer: int,
    *,
    lower_bound: int = 0,
    upper_bound: int | None = None,
    encoding: str = "utf-8",
) -> BoundedCString:
    """Read a NUL-terminated field without assuming or clearing nearby bytes."""
    end_limit = len(data) if upper_bound is None else upper_bound
    if not (0 <= lower_bound <= pointer < end_limit <= len(data)):
        raise BinaryFormatError(
            f"SongInfo string pointer 0x{pointer:X} is outside "
            f"[0x{lower_bound:X}, 0x{end_limit:X})"
        )
    terminator = data.find(b"\0", pointer, end_limit)
    if terminator < 0:
        raise BinaryFormatError(
            f"SongInfo string at 0x{pointer:X} has no NUL terminator before 0x{end_limit:X}"
        )
    raw = data[pointer:terminator]
    try:
        raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise BinaryFormatError(
            f"SongInfo string at 0x{pointer:X} is not valid {encoding}: {exc}"
        ) from exc
    return BoundedCString(pointer, raw, encoding)


def read_pointer_c_string(
    data: bytes,
    pointer_offset: int,
    *,
    pointer_base: int = 0,
    byteorder: str = "little",
    lower_bound: int = 0,
    upper_bound: int | None = None,
    encoding: str = "utf-8",
    required: bool = True,
) -> BoundedCString:
    """Resolve an actual 32-bit pointer and then read its bounded string target."""
    if pointer_offset < 0 or pointer_offset + 4 > len(data):
        raise BinaryFormatError(f"SongInfo pointer field 0x{pointer_offset:X} is outside the file")
    if byteorder not in {"little", "big"}:
        raise ValueError("byteorder must be 'little' or 'big'")
    fmt = "<I" if byteorder == "little" else ">I"
    relative = struct.unpack_from(fmt, data, pointer_offset)[0]
    pointer = pointer_base + relative
    value = read_bounded_c_string(
        data,
        pointer,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        encoding=encoding,
    )
    if required and not value.raw:
        raise BinaryFormatError(
            f"required SongInfo string referenced at 0x{pointer_offset:X} is empty"
        )
    return value
