from __future__ import annotations


def make_adts_frame(
    *,
    payload_size: int = 20,
    mpeg_id: int = 0,
    protection_absent: bool = True,
    profile: int = 1,
    sample_rate_index: int = 5,
    channel_configuration: int = 2,
    raw_data_blocks: int = 0,
    payload_byte: int = 0x5A,
) -> bytes:
    header_length = 7 if protection_absent else 9
    frame_length = header_length + payload_size
    fullness = 0x7FF
    header = bytearray(7)
    header[0] = 0xFF
    header[1] = 0xF0 | ((mpeg_id & 1) << 3) | int(protection_absent)
    header[2] = (
        ((profile & 0x03) << 6)
        | ((sample_rate_index & 0x0F) << 2)
        | ((channel_configuration >> 2) & 1)
    )
    header[3] = ((channel_configuration & 0x03) << 6) | ((frame_length >> 11) & 0x03)
    header[4] = (frame_length >> 3) & 0xFF
    header[5] = ((frame_length & 0x07) << 5) | ((fullness >> 6) & 0x1F)
    header[6] = ((fullness & 0x3F) << 2) | (raw_data_blocks & 0x03)
    crc = b"" if protection_absent else b"\x12\x34"
    return bytes(header) + crc + bytes([payload_byte]) * payload_size


def make_adts_stream(frame_count: int = 3, **frame_options) -> bytes:
    return b"".join(
        make_adts_frame(payload_byte=(0x40 + index) & 0xFF, **frame_options)
        for index in range(frame_count)
    )


def make_synthetic_naac(header_size: int = 32, frame_count: int = 3, **frame_options) -> bytes:
    header = (b"SYNTHETIC-UNKNOWN-HEADER" + bytes(range(32)))[:header_size].ljust(
        header_size, b"\xA5"
    )
    return header + make_adts_stream(frame_count, **frame_options)
