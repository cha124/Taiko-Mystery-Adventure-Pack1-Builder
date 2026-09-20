from __future__ import annotations

import hashlib

from app.core.audio.adts import ADTSParseError, parse_adts_frame, parse_adts_stream
from app.models.audio import AudioIssue, NAACInspection, SeekTableCandidate

MIN_CONSECUTIVE_FRAMES = 3


class NAACParseError(ValueError):
    def __init__(self, code: str, message: str, offset: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.offset = offset


def _probe_frames(data: bytes | memoryview, offset: int, count: int) -> bool:
    cursor = offset
    expected: tuple[int, int, int, int] | None = None
    try:
        for _ in range(count):
            frame = parse_adts_frame(data, cursor)
            current = (
                frame.sampling_frequency_index,
                frame.channel_configuration,
                frame.profile,
                frame.mpeg_id,
            )
            if expected is None:
                expected = current
            elif current != expected:
                return False
            cursor = frame.end_offset
    except ADTSParseError:
        return False
    return True


def find_adts_payload_offset(data: bytes | memoryview) -> int:
    limit = len(data) - 7
    for offset in range(max(0, limit + 1)):
        if data[offset] != 0xFF or (data[offset + 1] >> 4) != 0x0F:
            continue
        if not _probe_frames(data, offset, MIN_CONSECUTIVE_FRAMES):
            continue
        try:
            parse_adts_stream(data[offset:])
            return offset
        except ADTSParseError as exc:
            # Once multiple valid consecutive frames establish a stream start, do not
            # silently resynchronize after damage and reinterpret earlier AAC as header.
            raise NAACParseError(
                "NAAC_ADTS_STREAM_INVALID",
                f"ADTS candidate at 0x{offset:X} failed: {exc}",
                offset + exc.offset,
            ) from exc
    raise NAACParseError(
        "NAAC_PAYLOAD_NOT_FOUND",
        f"No candidate contained {MIN_CONSECUTIVE_FRAMES} consecutive valid ADTS frames.",
    )


def _seek_candidates(
    header: bytes, payload_offset: int, frame_offsets: tuple[int, ...]
) -> tuple[SeekTableCandidate, ...]:
    candidates: list[SeekTableCandidate] = []
    for width in (4, 8):
        for endianness in ("little", "big"):
            for base_name, values in (
                ("payload_relative", frame_offsets),
                ("file_absolute", tuple(payload_offset + value for value in frame_offsets)),
            ):
                frame_index = {value: index for index, value in enumerate(values)}
                for start in range(0, len(header) - width * 4 + 1, width):
                    matched: list[int] = []
                    cursor = start
                    previous = -1
                    while cursor + width <= len(header):
                        value = int.from_bytes(header[cursor : cursor + width], endianness)
                        if value not in frame_index or value <= previous:
                            break
                        matched.append(value)
                        previous = value
                        cursor += width
                    if len(matched) < 4:
                        continue
                    indexes = [frame_index[value] for value in matched]
                    gaps = [right - left for left, right in zip(indexes, indexes[1:])]
                    interval = gaps[0] if gaps and len(set(gaps)) == 1 else None
                    candidates.append(
                        SeekTableCandidate(
                            offset=start,
                            entry_width=width,
                            entry_count=len(matched),
                            endianness=endianness,
                            base=base_name,
                            frame_interval=interval,
                            match_ratio=1.0,
                        )
                    )
    # Keep maximal sequences; shorter candidates wholly inside another sequence add no evidence.
    candidates.sort(key=lambda item: (-item.entry_count, item.offset, item.entry_width))
    kept: list[SeekTableCandidate] = []
    for candidate in candidates:
        if any(
            candidate.entry_width == existing.entry_width
            and candidate.endianness == existing.endianness
            and candidate.base == existing.base
            and existing.offset <= candidate.offset
            and candidate.offset + candidate.entry_count * candidate.entry_width
            <= existing.offset + existing.entry_count * existing.entry_width
            for existing in kept
        ):
            continue
        kept.append(candidate)
    return tuple(sorted(kept, key=lambda item: (item.offset, item.entry_width, item.endianness)))


def inspect_naac(data: bytes | memoryview) -> NAACInspection:
    payload_offset = find_adts_payload_offset(data)
    stream = parse_adts_stream(data[payload_offset:])
    header = bytes(data[:payload_offset])
    payload = data[payload_offset:]
    frame_offsets = tuple(frame.offset for frame in stream.frames)
    issues: list[AudioIssue] = []
    if payload_offset == 0:
        issues.append(
            AudioIssue(
                "NAAC_HEADER_EMPTY",
                "WARNING",
                "ADTS starts at byte zero; no NAAC wrapper header was observed.",
            )
        )
    return NAACInspection(
        total_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        header_size=payload_offset,
        payload_offset=payload_offset,
        payload_size=len(payload),
        header_sha256=hashlib.sha256(header).hexdigest(),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        unknown_header_bytes=header,
        adts=stream.statistics,
        seek_candidates=_seek_candidates(header, payload_offset, frame_offsets),
        issues=tuple(issues),
    )
