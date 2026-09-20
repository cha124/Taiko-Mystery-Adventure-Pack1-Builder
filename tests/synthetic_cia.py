from __future__ import annotations

import hashlib
import struct


def align(value: int, boundary: int = 0x40) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def make_synthetic_cia(
    *,
    title_id: int = 0x0004008CDEADBEEF,
    contents: tuple[bytes, ...] = (b"synthetic-content",),
    duplicate_index: bool = False,
) -> bytes:
    """Build a minimal structural CIA fixture containing no copyrighted data."""
    header_size = 0x2020
    cert = b"CERT"
    ticket = b"TICKET"
    signature_size = 0x140
    tmd_body_size = 0x9C4 + len(contents) * 0x30
    tmd = bytearray(signature_size + tmd_body_size)
    struct.pack_into(">I", tmd, 0, 0x00010004)
    body = signature_size
    struct.pack_into(">Q", tmd, body + 0x4C, title_id)
    struct.pack_into(">H", tmd, body + 0x9E, len(contents))
    records = body + 0x9C4

    content_blob = bytearray()
    for number, payload in enumerate(contents):
        index = 0 if duplicate_index else number
        record = records + number * 0x30
        struct.pack_into(">IHHQ", tmd, record, 0x1000 + number, index, 0, len(payload))
        tmd[record + 0x10 : record + 0x30] = hashlib.sha256(payload).digest()
        while len(content_blob) % 0x40:
            content_blob.append(0)
        content_blob.extend(payload)

    cert_offset = align(header_size)
    ticket_offset = align(cert_offset + len(cert))
    tmd_offset = align(ticket_offset + len(ticket))
    content_offset = align(tmd_offset + len(tmd))
    content_size = len(content_blob)
    total_size = content_offset + content_size
    image = bytearray(total_size)
    struct.pack_into(
        "<IHHIIIIQ",
        image,
        0,
        header_size,
        0,
        0,
        len(cert),
        len(ticket),
        len(tmd),
        0,
        content_size,
    )
    for number in range(len(contents)):
        index = 0 if duplicate_index else number
        image[0x20 + index // 8] |= 0x80 >> (index % 8)
    image[cert_offset : cert_offset + len(cert)] = cert
    image[ticket_offset : ticket_offset + len(ticket)] = ticket
    image[tmd_offset : tmd_offset + len(tmd)] = tmd
    image[content_offset : content_offset + content_size] = content_blob
    return bytes(image)

