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


@dataclass(frozen=True)
class Pack1SongInfo:
    record_count: int
    record_offset: int
    string_pointers: tuple[int, ...]
    unknown_words: tuple[int, ...]
    record_key: str
    display_title: str
    music_info_key: str
    chart_key: str
    unknown_string_4: str
    unknown_string_5: str


@dataclass(frozen=True)
class Pack1MusicInfo:
    record_count: int
    record_offset: int
    string_pointers: tuple[int, ...]
    unknown_words: tuple[int, ...]
    music_info_key: str
    main_audio_key: str
    preview_audio_key: str


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


def _parse_pack1_pointer_table(
    data: bytes,
    *,
    pointer_field_offsets: tuple[int, ...],
    minimum_string_offset: int,
    label: str,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[str, ...]]:
    if len(data) < minimum_string_offset:
        raise BinaryFormatError(f"{label} is shorter than its pointer table")
    record_count, record_offset = struct.unpack_from("<II", data, 0)
    if record_count != 1:
        raise BinaryFormatError(f"{label} record count is {record_count}, expected 1")
    if record_offset != 0x10:
        raise BinaryFormatError(
            f"{label} record offset is 0x{record_offset:X}, expected 0x10"
        )
    if any(data[0x08:0x10]):
        raise BinaryFormatError(f"{label} reserved header bytes are not zero")
    pointers = tuple(struct.unpack_from("<I", data, field)[0] for field in pointer_field_offsets)
    if tuple(sorted(set(pointers))) != pointers:
        raise BinaryFormatError(f"{label} string pointers are not strictly increasing")
    if pointers[0] < minimum_string_offset:
        raise BinaryFormatError(f"{label} first string overlaps fixed record fields")
    if pointers[-1] >= len(data):
        raise BinaryFormatError(f"{label} string pointer is outside the file")
    unknown_start = pointer_field_offsets[-1] + 4
    if (pointers[0] - unknown_start) % 4:
        raise BinaryFormatError(f"{label} unknown fixed region is not word-aligned")
    unknown_words = tuple(
        struct.unpack_from("<I", data, offset)[0]
        for offset in range(unknown_start, pointers[0], 4)
    )
    strings: list[str] = []
    for number, pointer in enumerate(pointers):
        boundary = pointers[number + 1] if number + 1 < len(pointers) else len(data)
        value = read_bounded_c_string(
            data,
            pointer,
            lower_bound=pointer,
            upper_bound=boundary,
            encoding="utf-8",
        )
        if not value.raw:
            raise BinaryFormatError(f"{label} required string {number} is empty")
        terminator = pointer + len(value.raw)
        if any(data[terminator + 1 : boundary]):
            raise BinaryFormatError(
                f"{label} string {number} has non-zero bytes after its NUL terminator"
            )
        strings.append(value.text)
    return pointers, unknown_words, tuple(strings)


def parse_pack1_songinfo(data: bytes) -> Pack1SongInfo:
    pointers, unknown_words, strings = _parse_pack1_pointer_table(
        data,
        pointer_field_offsets=(0x10, 0x14, 0x18, 0x1C, 0x20, 0x24),
        minimum_string_offset=0x28,
        label="Pack1 SongInfo",
    )
    return Pack1SongInfo(
        record_count=1,
        record_offset=0x10,
        string_pointers=pointers,
        unknown_words=unknown_words,
        record_key=strings[0],
        display_title=strings[1],
        music_info_key=strings[2],
        chart_key=strings[3],
        unknown_string_4=strings[4],
        unknown_string_5=strings[5],
    )


def parse_pack1_musicinfo(data: bytes) -> Pack1MusicInfo:
    pointers, unknown_words, strings = _parse_pack1_pointer_table(
        data,
        pointer_field_offsets=(0x10, 0x14, 0x18),
        minimum_string_offset=0x1C,
        label="Pack1 MusicInfo",
    )
    return Pack1MusicInfo(
        record_count=1,
        record_offset=0x10,
        string_pointers=pointers,
        unknown_words=unknown_words,
        music_info_key=strings[0],
        main_audio_key=strings[1],
        preview_audio_key=strings[2],
    )
