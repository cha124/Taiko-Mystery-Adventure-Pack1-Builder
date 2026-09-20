from __future__ import annotations

import struct
from collections import defaultdict


def _align(value: int, boundary: int = 4) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def _directory_entry(
    *,
    parent: int,
    sibling: int = 0xFFFFFFFF,
    child_directory: int = 0xFFFFFFFF,
    child_file: int = 0xFFFFFFFF,
    name: str = "",
) -> bytes:
    encoded = name.encode("utf-16le")
    raw = bytearray(_align(0x18 + len(encoded)))
    struct.pack_into(
        "<6I",
        raw,
        0,
        parent,
        sibling,
        child_directory,
        child_file,
        0xFFFFFFFF,
        len(encoded),
    )
    raw[0x18 : 0x18 + len(encoded)] = encoded
    return bytes(raw)


def _file_entry(
    *,
    parent: int,
    data_offset: int,
    size: int,
    name: str,
    sibling: int = 0xFFFFFFFF,
) -> bytes:
    encoded = name.encode("utf-16le")
    raw = bytearray(_align(0x20 + len(encoded)))
    struct.pack_into(
        "<IIQQII",
        raw,
        0,
        parent,
        sibling,
        data_offset,
        size,
        0xFFFFFFFF,
        len(encoded),
    )
    raw[0x20 : 0x20 + len(encoded)] = encoded
    return bytes(raw)


def make_synthetic_romfs(
    *,
    duplicate_path: bool = False,
    file_cycle: bool = False,
    out_of_range_child: bool = False,
    out_of_range_file: bool = False,
) -> bytes:
    payload = b"synthetic-file-data"
    root_size = len(_directory_entry(parent=0))
    child_offset = root_size
    file_one = _file_entry(
        parent=child_offset,
        data_offset=0,
        size=len(payload) + (0x1000 if out_of_range_file else 0),
        name="test.bin",
    )
    file_two_offset = len(file_one)
    if duplicate_path:
        file_one = _file_entry(
            parent=child_offset,
            data_offset=0,
            size=len(payload),
            name="test.bin",
            sibling=file_two_offset,
        )
        file_two = _file_entry(
            parent=child_offset,
            data_offset=0,
            size=len(payload),
            name="test.bin",
        )
    elif file_cycle:
        file_one = _file_entry(
            parent=child_offset,
            data_offset=0,
            size=len(payload),
            name="test.bin",
            sibling=0,
        )
        file_two = b""
    else:
        file_two = b""
    file_meta = file_one + file_two
    root = _directory_entry(
        parent=0,
        child_directory=0x1000 if out_of_range_child else child_offset,
    )
    child = _directory_entry(parent=0, child_file=0, name="songs")
    dir_meta = root + child

    dir_hash_offset = 0x28
    dir_hash = struct.pack("<I", 0xFFFFFFFF)
    dir_meta_offset = dir_hash_offset + len(dir_hash)
    file_hash_offset = dir_meta_offset + len(dir_meta)
    file_hash = struct.pack("<I", 0xFFFFFFFF)
    file_meta_offset = file_hash_offset + len(file_hash)
    file_data_offset = _align(file_meta_offset + len(file_meta), 0x10)
    level3 = bytearray(file_data_offset + len(payload))
    struct.pack_into(
        "<10I",
        level3,
        0,
        0x28,
        dir_hash_offset,
        len(dir_hash),
        dir_meta_offset,
        len(dir_meta),
        file_hash_offset,
        len(file_hash),
        file_meta_offset,
        len(file_meta),
        file_data_offset,
    )
    level3[dir_hash_offset : dir_hash_offset + len(dir_hash)] = dir_hash
    level3[dir_meta_offset : dir_meta_offset + len(dir_meta)] = dir_meta
    level3[file_hash_offset : file_hash_offset + len(file_hash)] = file_hash
    level3[file_meta_offset : file_meta_offset + len(file_meta)] = file_meta
    level3[file_data_offset : file_data_offset + len(payload)] = payload

    result = bytearray(0x1000 + len(level3))
    result[0:4] = b"IVFC"
    struct.pack_into("<I", result, 0x04, 0x00010000)
    struct.pack_into("<I", result, 0x08, 0x20)
    struct.pack_into("<I", result, 0x4C, 12)
    struct.pack_into("<I", result, 0x54, 0x5C)
    result[0x1000:] = level3
    return bytes(result)


def make_synthetic_romfs_files(files: dict[str, bytes]) -> bytes:
    """Build a small original fixture from path/payload pairs."""
    normalized: dict[str, bytes] = {}
    directory_names = {""}
    for raw_path, payload in files.items():
        path = "/" + raw_path.strip("/")
        if path in normalized:
            raise ValueError(f"duplicate input path: {path}")
        normalized[path] = payload
        parts = path.strip("/").split("/")
        for depth in range(1, len(parts)):
            directory_names.add("/" + "/".join(parts[:depth]))

    directory_order = [""] + sorted(directory_names - {""}, key=lambda path: (path.count("/"), path))
    directory_offsets: dict[str, int] = {}
    cursor = 0
    for path in directory_order:
        name = path.rsplit("/", 1)[-1] if path else ""
        directory_offsets[path] = cursor
        cursor += _align(0x18 + len(name.encode("utf-16le")))

    file_order = sorted(normalized)
    file_offsets: dict[str, int] = {}
    cursor = 0
    for path in file_order:
        name = path.rsplit("/", 1)[-1]
        file_offsets[path] = cursor
        cursor += _align(0x20 + len(name.encode("utf-16le")))

    child_directories: dict[str, list[str]] = defaultdict(list)
    for path in directory_order[1:]:
        parent = path.rsplit("/", 1)[0]
        child_directories[parent].append(path)
    child_files: dict[str, list[str]] = defaultdict(list)
    for path in file_order:
        parent = path.rsplit("/", 1)[0]
        child_files[parent].append(path)

    directory_meta = bytearray()
    for path in directory_order:
        children = child_directories[path]
        siblings = child_directories[path.rsplit("/", 1)[0]] if path else []
        sibling = 0xFFFFFFFF
        if path and siblings.index(path) + 1 < len(siblings):
            sibling = directory_offsets[siblings[siblings.index(path) + 1]]
        parent_path = path.rsplit("/", 1)[0] if path else ""
        directory_meta.extend(
            _directory_entry(
                parent=directory_offsets[parent_path],
                sibling=sibling,
                child_directory=directory_offsets[children[0]] if children else 0xFFFFFFFF,
                child_file=file_offsets[child_files[path][0]] if child_files[path] else 0xFFFFFFFF,
                name=path.rsplit("/", 1)[-1] if path else "",
            )
        )

    file_meta = bytearray()
    file_data = bytearray()
    for path in file_order:
        parent_path = path.rsplit("/", 1)[0]
        siblings = child_files[parent_path]
        position = siblings.index(path)
        sibling = file_offsets[siblings[position + 1]] if position + 1 < len(siblings) else 0xFFFFFFFF
        payload = normalized[path]
        file_meta.extend(
            _file_entry(
                parent=directory_offsets[parent_path],
                sibling=sibling,
                data_offset=len(file_data),
                size=len(payload),
                name=path.rsplit("/", 1)[-1],
            )
        )
        file_data.extend(payload)

    dir_hash_offset = 0x28
    dir_hash = struct.pack("<I", 0xFFFFFFFF)
    dir_meta_offset = dir_hash_offset + len(dir_hash)
    file_hash_offset = dir_meta_offset + len(directory_meta)
    file_hash = struct.pack("<I", 0xFFFFFFFF)
    file_meta_offset = file_hash_offset + len(file_hash)
    file_data_offset = _align(file_meta_offset + len(file_meta), 0x10)
    level3 = bytearray(file_data_offset + len(file_data))
    struct.pack_into(
        "<10I",
        level3,
        0,
        0x28,
        dir_hash_offset,
        len(dir_hash),
        dir_meta_offset,
        len(directory_meta),
        file_hash_offset,
        len(file_hash),
        file_meta_offset,
        len(file_meta),
        file_data_offset,
    )
    level3[dir_hash_offset : dir_hash_offset + len(dir_hash)] = dir_hash
    level3[dir_meta_offset : dir_meta_offset + len(directory_meta)] = directory_meta
    level3[file_hash_offset : file_hash_offset + len(file_hash)] = file_hash
    level3[file_meta_offset : file_meta_offset + len(file_meta)] = file_meta
    level3[file_data_offset:] = file_data

    result = bytearray(0x1000 + len(level3))
    result[0:4] = b"IVFC"
    struct.pack_into("<I", result, 0x04, 0x00010000)
    struct.pack_into("<I", result, 0x08, 0x20)
    struct.pack_into("<I", result, 0x4C, 12)
    struct.pack_into("<I", result, 0x54, 0x5C)
    result[0x1000:] = level3
    return bytes(result)


def _pointer_table(strings: tuple[str, ...], first_pointer: int, pointer_count: int) -> bytes:
    data = bytearray(first_pointer)
    struct.pack_into("<II", data, 0, 1, 0x10)
    cursor = first_pointer
    pointers: list[int] = []
    for value in strings:
        pointers.append(cursor)
        encoded = value.encode("utf-8") + b"\0"
        data.extend(encoded)
        while len(data) % 0x10:
            data.append(0)
        cursor = len(data)
    if len(pointers) != pointer_count:
        raise ValueError("unexpected pointer count")
    for number, pointer in enumerate(pointers):
        struct.pack_into("<I", data, 0x10 + number * 4, pointer)
    return bytes(data)


def make_synthetic_pack1_romfs(
    *,
    include_musicinfo: bool = True,
    include_audio: bool = True,
    include_preview: bool = True,
    songinfo_chart_key: str = "test",
) -> bytes:
    songinfo = _pointer_table(
        ("DSONG_TEST", "Synthetic Song", "d_test", songinfo_chart_key, "test", "test"),
        0x50,
        6,
    )
    musicinfo = _pointer_table(("d_test", "test_3ds", "test_3ds_s"), 0x30, 3)
    files = {
        "/_data/system/SongInfo.dat": songinfo,
        "/_data/fumen/test/solo/test_e.bin": b"easy",
        "/_data/fumen/test/solo/test_n.bin": b"normal",
        "/_data/fumen/test/solo/test_h.bin": b"hard",
        "/_data/fumen/test/solo/test_m.bin": b"oni",
        "/_data/system/songtitle/song_title_yoko.txp": b"synthetic-title",
    }
    if include_musicinfo:
        files["/_data/system/MusicInfo.dat"] = musicinfo
    if include_audio:
        files["/_data/sound/song/test_3ds.naac"] = b"synthetic-main-audio"
    if include_preview:
        files["/_data/sound/song/test_3ds_s.naac"] = b"synthetic-preview-audio"
    return make_synthetic_romfs_files(files)
