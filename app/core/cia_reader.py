from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.binary import (
    BinaryFormatError,
    align,
    require_range,
    u16be,
    u16le,
    u32be,
    u32le,
    u64be,
    u64le,
)

CIA_MIN_HEADER_SIZE = 0x2020
CONTENT_INDEX_OFFSET = 0x20
CONTENT_INDEX_SIZE = 0x2000

# Signature type -> padded signature block size. The signed body starts here.
SIGNATURE_BLOCK_SIZES = {
    0x00010000: 0x240,  # RSA-4096 / SHA-1
    0x00010001: 0x140,  # RSA-2048 / SHA-1
    0x00010002: 0x080,  # ECDSA / SHA-1
    0x00010003: 0x240,  # RSA-4096 / SHA-256
    0x00010004: 0x140,  # RSA-2048 / SHA-256
    0x00010005: 0x080,  # ECDSA / SHA-256
}


@dataclass(frozen=True)
class CiaSection:
    name: str
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    def to_dict(self) -> dict[str, int | str]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": self.size,
            "end": self.end,
        }


@dataclass(frozen=True)
class TmdContentRecord:
    content_id: int
    index: int
    content_type: int
    size: int
    sha256: str
    selected: bool
    file_offset: int | None = None
    actual_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": f"{self.content_id:08x}",
            "index": self.index,
            "type": f"0x{self.content_type:04x}",
            "size": self.size,
            "expected_sha256": self.sha256,
            "selected_in_cia": self.selected,
            "file_offset": self.file_offset,
            "actual_sha256": self.actual_sha256,
        }


@dataclass(frozen=True)
class CiaImage:
    path: Path
    file_size: int
    header_size: int
    cia_type: int
    version: int
    declared_content_size: int
    title_id: int
    tmd_content_count: int
    sections: tuple[CiaSection, ...]
    contents: tuple[TmdContentRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "header_size": self.header_size,
            "type": self.cia_type,
            "version": self.version,
            "title_id": f"{self.title_id:016x}",
            "declared_content_size": self.declared_content_size,
            "tmd_content_count": self.tmd_content_count,
            "selected_content_count": sum(c.selected for c in self.contents),
            "sections": [section.to_dict() for section in self.sections],
            "contents": [content.to_dict() for content in self.contents],
        }


def _signature_body_offset(data: memoryview, offset: int, label: str) -> int:
    signature_type = u32be(data, offset, f"{label} signature type")
    try:
        return offset + SIGNATURE_BLOCK_SIZES[signature_type]
    except KeyError as exc:
        raise BinaryFormatError(
            f"unsupported {label} signature type: 0x{signature_type:08X}"
        ) from exc


def _is_content_selected(header: memoryview, index: int) -> bool:
    if not 0 <= index < CONTENT_INDEX_SIZE * 8:
        return False
    byte_value = header[CONTENT_INDEX_OFFSET + index // 8]
    return bool(byte_value & (0x80 >> (index % 8)))


def read_cia(path: Path) -> CiaImage:
    path = path.resolve()
    data_bytes = path.read_bytes()
    data = memoryview(data_bytes)
    require_range(data, 0, CIA_MIN_HEADER_SIZE, "CIA header")

    header_size = u32le(data, 0x00, "CIA header size")
    if header_size < CIA_MIN_HEADER_SIZE:
        raise BinaryFormatError(
            f"CIA header is too small: 0x{header_size:X} < 0x{CIA_MIN_HEADER_SIZE:X}"
        )
    require_range(data, 0, header_size, "declared CIA header")

    cia_type = u16le(data, 0x04, "CIA type")
    version = u16le(data, 0x06, "CIA version")
    cert_size = u32le(data, 0x08, "certificate chain size")
    ticket_size = u32le(data, 0x0C, "ticket size")
    tmd_size = u32le(data, 0x10, "TMD size")
    meta_size = u32le(data, 0x14, "meta size")
    content_size = u64le(data, 0x18, "content size")

    cert_offset = align(header_size)
    ticket_offset = align(cert_offset + cert_size)
    tmd_offset = align(ticket_offset + ticket_size)
    content_offset = align(tmd_offset + tmd_size)
    meta_offset = align(content_offset + content_size)

    sections = [
        CiaSection("header", 0, header_size),
        CiaSection("certificate_chain", cert_offset, cert_size),
        CiaSection("ticket", ticket_offset, ticket_size),
        CiaSection("tmd", tmd_offset, tmd_size),
        CiaSection("content", content_offset, content_size),
    ]
    if meta_size:
        sections.append(CiaSection("meta", meta_offset, meta_size))
    for section in sections:
        require_range(data, section.offset, section.size, f"CIA {section.name} section")

    if tmd_size == 0:
        raise BinaryFormatError("CIA contains no TMD")
    tmd_body = _signature_body_offset(data, tmd_offset, "TMD")
    tmd_end = tmd_offset + tmd_size
    require_range(data, tmd_body, 0x9C4, "TMD body and content info records")
    if tmd_body + 0x9C4 > tmd_end:
        raise BinaryFormatError("TMD body is shorter than its fixed tables")

    title_id = u64be(data, tmd_body + 0x4C, "TMD title ID")
    content_count = u16be(data, tmd_body + 0x9E, "TMD content count")
    records_offset = tmd_body + 0x9C4
    records_size = content_count * 0x30
    if records_offset + records_size > tmd_end:
        raise BinaryFormatError(
            f"TMD content records exceed TMD: count={content_count}, "
            f"required_end=0x{records_offset + records_size:X}, tmd_end=0x{tmd_end:X}"
        )

    parsed: list[dict[str, Any]] = []
    for number in range(content_count):
        record_offset = records_offset + number * 0x30
        index = u16be(data, record_offset + 0x04, "TMD content index")
        parsed.append(
            {
                "content_id": u32be(data, record_offset, "TMD content ID"),
                "index": index,
                "content_type": u16be(data, record_offset + 0x06, "TMD content type"),
                "size": u64be(data, record_offset + 0x08, "TMD content size"),
                "sha256": bytes(data[record_offset + 0x10 : record_offset + 0x30]).hex(),
                "selected": _is_content_selected(data[:header_size], index),
            }
        )

    cursor = content_offset
    content_end = content_offset + content_size
    records: list[TmdContentRecord] = []
    for raw in parsed:
        file_offset: int | None = None
        actual_hash: str | None = None
        if raw["selected"]:
            # CIA content is stored in TMD-record order. Padding between records is
            # included in the declared content section; the first record starts at
            # the already-aligned section boundary.
            file_offset = cursor
            if cursor + raw["size"] > content_end:
                raise BinaryFormatError(
                    f"content index {raw['index']} exceeds declared content section"
                )
            actual_hash = hashlib.sha256(data[cursor : cursor + raw["size"]]).hexdigest()
            cursor = align(cursor + raw["size"])
        records.append(
            TmdContentRecord(
                content_id=raw["content_id"],
                index=raw["index"],
                content_type=raw["content_type"],
                size=raw["size"],
                sha256=raw["sha256"],
                selected=raw["selected"],
                file_offset=file_offset,
                actual_sha256=actual_hash,
            )
        )

    return CiaImage(
        path=path,
        file_size=len(data),
        header_size=header_size,
        cia_type=cia_type,
        version=version,
        declared_content_size=content_size,
        title_id=title_id,
        tmd_content_count=content_count,
        sections=tuple(sections),
        contents=tuple(records),
    )

