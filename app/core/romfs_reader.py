from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from app.core.binary import BinaryFormatError, align, require_range, u32le, u64le

IVFC_HEADER_SIZE = 0x5C
IVFC_MAGIC_NUMBER = 0x00010000
ROMFS_LV3_HEADER_SIZE = 0x28
NULL_OFFSET = 0xFFFFFFFF


class RomFSFormatError(BinaryFormatError):
    """Raised when IVFC/RomFS metadata cannot be followed safely."""


class RomFSCycleError(RomFSFormatError):
    """Raised when a metadata reference cycle is found."""


class RomFSDuplicatePathError(RomFSFormatError):
    """Raised when two entries resolve to the same path."""


@dataclass(frozen=True)
class RomFSRegion:
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass(frozen=True)
class RomFSDirectory:
    metadata_offset: int
    parent: int
    sibling: int
    child_directory: int
    child_file: int
    hash_sibling: int
    name: str


@dataclass(frozen=True)
class RomFSFile:
    path: str
    metadata_offset: int
    data_offset: int
    absolute_offset: int
    size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "metadata_offset": self.metadata_offset,
            "data_offset": self.data_offset,
            "absolute_offset": self.absolute_offset,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RomFSImage:
    ivfc_offset: int
    ivfc_size: int
    level3_offset: int
    file_data_offset: int
    directories: tuple[str, ...]
    files: tuple[RomFSFile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level3_offset": self.level3_offset,
            "file_data_offset": self.file_data_offset,
            "directory_count": len(self.directories),
            "file_count": len(self.files),
            "directories": list(self.directories),
            "files": [entry.to_dict() for entry in self.files],
        }


@dataclass(frozen=True)
class _FileMetadata:
    offset: int
    parent: int
    sibling: int
    data_offset: int
    size: int
    hash_sibling: int
    name: str


def _decode_name(raw: memoryview, label: str) -> str:
    if len(raw) % 2:
        raise RomFSFormatError(f"{label} UTF-16 name has an odd byte length")
    try:
        name = bytes(raw).decode("utf-16le", errors="strict")
    except UnicodeDecodeError as exc:
        raise RomFSFormatError(f"{label} name is not valid UTF-16LE") from exc
    if "\0" in name or "/" in name or "\\" in name:
        raise RomFSFormatError(f"{label} name contains a forbidden path character")
    return name


def _parse_directories(table: memoryview) -> dict[int, RomFSDirectory]:
    entries: dict[int, RomFSDirectory] = {}
    cursor = 0
    while cursor < len(table):
        require_range(table, cursor, 0x18, "RomFS directory metadata entry")
        name_length = u32le(table, cursor + 0x14, "RomFS directory name length")
        entry_size = align(0x18 + name_length, 4)
        require_range(table, cursor, entry_size, "RomFS directory metadata entry and name")
        name = _decode_name(table[cursor + 0x18 : cursor + 0x18 + name_length], "RomFS directory")
        entries[cursor] = RomFSDirectory(
            metadata_offset=cursor,
            parent=u32le(table, cursor, "RomFS directory parent"),
            sibling=u32le(table, cursor + 0x04, "RomFS directory sibling"),
            child_directory=u32le(table, cursor + 0x08, "RomFS child directory"),
            child_file=u32le(table, cursor + 0x0C, "RomFS child file"),
            hash_sibling=u32le(table, cursor + 0x10, "RomFS directory hash sibling"),
            name=name,
        )
        cursor += entry_size
    if not entries or 0 not in entries:
        raise RomFSFormatError("RomFS directory metadata has no root entry at offset 0")
    return entries


def _parse_files(table: memoryview) -> dict[int, _FileMetadata]:
    entries: dict[int, _FileMetadata] = {}
    cursor = 0
    while cursor < len(table):
        require_range(table, cursor, 0x20, "RomFS file metadata entry")
        name_length = u32le(table, cursor + 0x1C, "RomFS file name length")
        entry_size = align(0x20 + name_length, 4)
        require_range(table, cursor, entry_size, "RomFS file metadata entry and name")
        name = _decode_name(table[cursor + 0x20 : cursor + 0x20 + name_length], "RomFS file")
        entries[cursor] = _FileMetadata(
            offset=cursor,
            parent=u32le(table, cursor, "RomFS file parent"),
            sibling=u32le(table, cursor + 0x04, "RomFS file sibling"),
            data_offset=u64le(table, cursor + 0x08, "RomFS file data offset"),
            size=u64le(table, cursor + 0x10, "RomFS file size"),
            hash_sibling=u32le(table, cursor + 0x18, "RomFS file hash sibling"),
            name=name,
        )
        cursor += entry_size
    return entries


def _validate_hash_table(table: memoryview, entries: dict[int, object], label: str) -> None:
    if len(table) % 4:
        raise RomFSFormatError(f"{label} size is not divisible by four")
    for position in range(0, len(table), 4):
        entry_offset = u32le(table, position, label)
        if entry_offset != NULL_OFFSET and entry_offset not in entries:
            raise RomFSFormatError(
                f"{label} points to non-entry offset 0x{entry_offset:X}"
            )


def read_romfs(data: bytes | memoryview, offset: int, size: int) -> RomFSImage:
    """Read one IVFC-wrapped RomFS without extracting or modifying file data."""
    view = memoryview(data)
    require_range(view, offset, size, "IVFC RomFS region")
    require_range(view, offset, IVFC_HEADER_SIZE, "IVFC header")
    if bytes(view[offset : offset + 4]) != b"IVFC":
        raise RomFSFormatError("RomFS IVFC magic is missing")
    if u32le(view, offset + 0x04, "IVFC magic number") != IVFC_MAGIC_NUMBER:
        raise RomFSFormatError("unsupported IVFC magic number")
    master_hash_size = u32le(view, offset + 0x08, "IVFC master hash size")
    block_exponent = u32le(view, offset + 0x4C, "IVFC Level 3 block exponent")
    if not 5 <= block_exponent <= 30:
        raise RomFSFormatError(f"unsafe IVFC block exponent: {block_exponent}")
    if u32le(view, offset + 0x54, "IVFC header size") != IVFC_HEADER_SIZE:
        raise RomFSFormatError("IVFC header size is not 0x5C")
    level3_relative = align(0x60 + master_hash_size, 1 << block_exponent)
    if level3_relative + ROMFS_LV3_HEADER_SIZE > size:
        raise RomFSFormatError("RomFS Level 3 header is outside the IVFC region")
    level3 = offset + level3_relative

    values = struct.unpack_from("<10I", view, level3)
    if values[0] != ROMFS_LV3_HEADER_SIZE:
        raise RomFSFormatError("RomFS Level 3 header size is not 0x28")
    dir_hash = RomFSRegion(values[1], values[2])
    dir_meta = RomFSRegion(values[3], values[4])
    file_hash = RomFSRegion(values[5], values[6])
    file_meta = RomFSRegion(values[7], values[8])
    file_data_offset = values[9]
    if dir_hash.offset < ROMFS_LV3_HEADER_SIZE:
        raise RomFSFormatError("directory hash region overlaps the Level 3 header")
    if dir_meta.offset < dir_hash.end:
        raise RomFSFormatError("directory metadata overlaps the directory hash table")
    if file_hash.offset < dir_meta.end:
        raise RomFSFormatError("file hash table overlaps directory metadata")
    if file_meta.offset < file_hash.end:
        raise RomFSFormatError("file metadata overlaps the file hash table")
    if file_data_offset < file_meta.end:
        raise RomFSFormatError("file data overlaps file metadata")
    level3_size = size - level3_relative
    if file_data_offset > level3_size:
        raise RomFSFormatError("file data offset is outside RomFS Level 3")
    for region, label in (
        (dir_hash, "directory hash"),
        (dir_meta, "directory metadata"),
        (file_hash, "file hash"),
        (file_meta, "file metadata"),
    ):
        if region.end > level3_size:
            raise RomFSFormatError(f"{label} region is outside RomFS Level 3")

    dir_hash_data = view[level3 + dir_hash.offset : level3 + dir_hash.end]
    dir_meta_data = view[level3 + dir_meta.offset : level3 + dir_meta.end]
    file_hash_data = view[level3 + file_hash.offset : level3 + file_hash.end]
    file_meta_data = view[level3 + file_meta.offset : level3 + file_meta.end]
    directories = _parse_directories(dir_meta_data)
    files = _parse_files(file_meta_data)
    _validate_hash_table(dir_hash_data, directories, "RomFS directory hash table")
    _validate_hash_table(file_hash_data, files, "RomFS file hash table")

    for directory in directories.values():
        for reference, label, targets in (
            (directory.parent, "parent", directories),
            (directory.sibling, "sibling", directories),
            (directory.child_directory, "child directory", directories),
            (directory.child_file, "child file", files),
            (directory.hash_sibling, "hash sibling", directories),
        ):
            if reference != NULL_OFFSET and reference not in targets:
                raise RomFSFormatError(
                    f"directory entry 0x{directory.metadata_offset:X} {label} "
                    f"points to non-entry offset 0x{reference:X}"
                )
    for entry in files.values():
        for reference, label, targets in (
            (entry.parent, "parent", directories),
            (entry.sibling, "sibling", files),
            (entry.hash_sibling, "hash sibling", files),
        ):
            if reference != NULL_OFFSET and reference not in targets:
                raise RomFSFormatError(
                    f"file entry 0x{entry.offset:X} {label} points to "
                    f"non-entry offset 0x{reference:X}"
                )
        if entry.data_offset + entry.size > level3_size - file_data_offset:
            raise RomFSFormatError(f"file {entry.name!r} exceeds the RomFS file data region")

    reached_directories: set[int] = set()
    reached_files: set[int] = set()
    active_directories: set[int] = set()
    paths: set[str] = set()
    folded_paths: set[str] = set()
    directory_paths: list[str] = []
    output_files: list[RomFSFile] = []

    def register_path(path: str) -> None:
        folded = path.casefold()
        if path in paths or folded in folded_paths:
            raise RomFSDuplicatePathError(f"duplicate RomFS path: {path}")
        paths.add(path)
        folded_paths.add(folded)

    def walk_file_chain(first: int, parent_offset: int, parent_path: str) -> None:
        chain: set[int] = set()
        current = first
        while current != NULL_OFFSET:
            if current in chain or current in reached_files:
                raise RomFSCycleError(f"RomFS file sibling cycle at 0x{current:X}")
            chain.add(current)
            reached_files.add(current)
            entry = files[current]
            if entry.parent != parent_offset:
                raise RomFSFormatError(
                    f"file {entry.name!r} parent does not match containing directory"
                )
            path = f"{parent_path}/{entry.name}" if parent_path else f"/{entry.name}"
            register_path(path)
            absolute = level3 + file_data_offset + entry.data_offset
            digest = hashlib.sha256(view[absolute : absolute + entry.size]).hexdigest()
            output_files.append(
                RomFSFile(path, entry.offset, entry.data_offset, absolute, entry.size, digest)
            )
            current = entry.sibling

    def walk_directory(offset_value: int, parent_path: str, expected_parent: int | None) -> None:
        if offset_value in active_directories or offset_value in reached_directories:
            raise RomFSCycleError(f"RomFS directory cycle at 0x{offset_value:X}")
        active_directories.add(offset_value)
        reached_directories.add(offset_value)
        entry = directories[offset_value]
        if expected_parent is not None and entry.parent != expected_parent:
            raise RomFSFormatError(
                f"directory {entry.name!r} parent does not match containing directory"
            )
        if offset_value == 0:
            if entry.name:
                raise RomFSFormatError("RomFS root directory name is not empty")
            path = ""
        else:
            path = f"{parent_path}/{entry.name}" if parent_path else f"/{entry.name}"
            register_path(path)
            directory_paths.append(path)

        child_chain: set[int] = set()
        child = entry.child_directory
        while child != NULL_OFFSET:
            if child in child_chain:
                raise RomFSCycleError(f"RomFS child directory sibling cycle at 0x{child:X}")
            child_chain.add(child)
            child_entry = directories[child]
            next_sibling = child_entry.sibling
            walk_directory(child, path, offset_value)
            child = next_sibling
        walk_file_chain(entry.child_file, offset_value, path)
        active_directories.remove(offset_value)

    walk_directory(0, "", None)
    if reached_directories != set(directories):
        missing = sorted(set(directories) - reached_directories)
        raise RomFSFormatError(f"unreachable RomFS directory entries: {missing}")
    if reached_files != set(files):
        missing = sorted(set(files) - reached_files)
        raise RomFSFormatError(f"unreachable RomFS file entries: {missing}")

    return RomFSImage(
        ivfc_offset=offset,
        ivfc_size=size,
        level3_offset=level3,
        file_data_offset=level3 + file_data_offset,
        directories=tuple(sorted(directory_paths)),
        files=tuple(sorted(output_files, key=lambda entry: entry.path)),
    )
