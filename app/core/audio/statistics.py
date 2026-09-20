from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from app.models.audio import AudioFileAnalysis


def _distribution(values: list[Any]) -> dict[str, int]:
    return {str(key): value for key, value in sorted(Counter(values).items(), key=lambda item: str(item[0]))}


def _range(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"minimum": min(values), "maximum": max(values)}


def role_statistics(records: list[AudioFileAnalysis], role: str) -> dict[str, Any]:
    selected = [
        record
        for record in records
        if record.role == role and record.inspection is not None and record.inspection.adts is not None
    ]
    stats = [record.inspection.adts for record in selected if record.inspection and record.inspection.adts]
    return {
        "reference_count": sum(record.role == role for record in records),
        "success_count": len(selected),
        "sample_rate_distribution": _distribution([item.sample_rate for item in stats]),
        "channel_distribution": _distribution([item.channels for item in stats]),
        "profile_distribution": _distribution(
            [f"profile={item.profile},AOT={item.audio_object_type},{item.audio_object_type_name}" for item in stats]
        ),
        "mpeg_id_distribution": _distribution([item.mpeg_id for item in stats]),
        "crc_distribution": _distribution([item.crc_usage for item in stats]),
        "header_size_distribution": _distribution(
            [record.inspection.header_size for record in selected if record.inspection]
        ),
        "frame_count_range": _range([float(item.frame_count) for item in stats]),
        "duration_seconds_range": _range([item.duration_seconds for item in stats]),
        "measured_bitrate_bps_range": _range([item.measured_bitrate_bps for item in stats]),
    }


def common_byte_ranges(headers: list[bytes], *, minimum_size: int = 4) -> dict[str, Any]:
    """Describe byte-for-byte commonality without dumping thousands of tiny ranges."""
    if not headers:
        return {"compared_files": 0, "compared_size": 0, "common_byte_count": 0, "ranges": []}
    limit = min(map(len, headers))
    equal = [all(header[index] == headers[0][index] for header in headers[1:]) for index in range(limit)]
    ranges: list[dict[str, Any]] = []
    common_count = sum(equal)
    start: int | None = None
    for index, is_equal in enumerate(equal + [False]):
        if is_equal and start is None:
            start = index
        elif not is_equal and start is not None:
            size = index - start
            if size >= minimum_size:
                ranges.append(
                    {
                        "offset": start,
                        "offset_hex": f"0x{start:X}",
                        "size": size,
                        "raw_hex": headers[0][start:index].hex(),
                    }
                )
            start = None
    return {
        "compared_files": len(headers),
        "compared_size": limit,
        "common_byte_count": common_count,
        "minimum_reported_range_size": minimum_size,
        "ranges": ranges,
    }


def _candidate_scopes(records: list[AudioFileAnalysis]) -> dict[str, list[AudioFileAnalysis]]:
    successful = [record for record in records if record.inspection and record.inspection.adts]
    return {
        "all": successful,
        "main": [record for record in successful if record.role == "main"],
        "preview": [record for record in successful if record.role == "preview"],
        "mpeg_id_0": [record for record in successful if record.inspection.adts.mpeg_id == 0],  # type: ignore[union-attr]
        "mpeg_id_1": [record for record in successful if record.inspection.adts.mpeg_id == 1],  # type: ignore[union-attr]
    }


def field_candidates(records: list[AudioFileAnalysis]) -> list[dict[str, Any]]:
    targets: dict[str, Callable[[AudioFileAnalysis], int]] = {
        "naac_total_size_candidate": lambda record: record.inspection.total_size,  # type: ignore[union-attr]
        "payload_size_candidate": lambda record: record.inspection.payload_size,  # type: ignore[union-attr]
        "frame_count_candidate": lambda record: record.inspection.adts.frame_count,  # type: ignore[union-attr]
        "decoded_nominal_samples_candidate": lambda record: record.inspection.adts.total_samples,  # type: ignore[union-attr]
        # Deliberately named as a scaled candidate, not as a decoded/playable sample count.
        "decoded_nominal_samples_div_256_candidate": (
            lambda record: record.inspection.adts.total_samples // 256  # type: ignore[union-attr]
        ),
        "sample_rate_candidate": lambda record: record.inspection.adts.sample_rate,  # type: ignore[union-attr]
    }
    results: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for scope, selected in _candidate_scopes(records).items():
        if len(selected) < 2:
            continue
        limit = min(record.inspection.header_size for record in selected if record.inspection)
        headers = [record.inspection.unknown_header_bytes for record in selected if record.inspection]
        for interpretation, target in targets.items():
            target_values = [target(record) for record in selected]
            target_variation_count = len(set(target_values))
            for width in (2, 4, 8):
                maximum = (1 << (width * 8)) - 1
                if any(value < 0 or value > maximum for value in target_values):
                    continue
                for endianness in ("little", "big"):
                    possible_offsets: Counter[int] = Counter()
                    encoded_values = [value.to_bytes(width, endianness) for value in target_values]
                    for header, expected in zip(headers, encoded_values):
                        start = 0
                        while True:
                            offset = header.find(expected, start, limit)
                            if offset < 0:
                                break
                            possible_offsets[offset] += 1
                            start = offset + 1
                    threshold = 0.9 * len(selected)
                    for offset, matches in possible_offsets.items():
                        if matches < threshold:
                            continue
                        key = (scope, offset, width, endianness, interpretation)
                        if key in seen:
                            continue
                        seen.add(key)
                        ratio = matches / len(selected)
                        raw_values = [header[offset : offset + width] for header in headers]
                        # An invariant target can coincide with a constant by chance; it is not correlation evidence.
                        strongly_correlated = ratio == 1.0 and target_variation_count > 1
                        results.append(
                            {
                                "scope": scope,
                                "offset": offset,
                                "offset_hex": f"0x{offset:X}",
                                "alignment": offset % width,
                                "width": width,
                                "endianness": endianness,
                                "interpretation": interpretation,
                                "matches": matches,
                                "total": len(selected),
                                "match_ratio": ratio,
                                "target_variation_count": target_variation_count,
                                "observed_raw_hex_examples": sorted({value.hex() for value in raw_values})[:8],
                                "confidence": "STRONGLY_CORRELATED" if strongly_correlated else "POSSIBLE",
                            }
                        )
    return sorted(
        results,
        key=lambda item: (
            item["scope"], item["offset"], item["width"], item["endianness"], item["interpretation"]
        ),
    )


def _seek_table_analysis(records: list[AudioFileAnalysis]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidate_files: set[tuple[int, str, str]] = set()
    roles: Counter[str] = Counter()
    mpeg_ids: Counter[int] = Counter()
    inspected_mpeg_ids: Counter[int] = Counter()
    signatures: Counter[tuple[Any, ...]] = Counter()
    entry_counts: list[int] = []
    frame_intervals: Counter[int | None] = Counter()
    for record in records:
        if not record.inspection or not record.inspection.adts:
            continue
        inspected_mpeg_ids[record.inspection.adts.mpeg_id] += 1
        if record.inspection.seek_candidates:
            identity = (record.content_index, record.role, record.romfs_path.casefold())
            candidate_files.add(identity)
            roles[record.role] += 1
            mpeg_ids[record.inspection.adts.mpeg_id] += 1
        for candidate in record.inspection.seek_candidates:
            entry_counts.append(candidate.entry_count)
            frame_intervals[candidate.frame_interval] += 1
            item = {
                "content_index": record.content_index,
                "role": record.role,
                "mpeg_id": record.inspection.adts.mpeg_id,
                **candidate.to_dict(),
            }
            candidates.append(item)
            signatures[
                (
                    candidate.offset,
                    candidate.entry_width,
                    candidate.endianness,
                    candidate.base,
                    candidate.match_ratio,
                )
            ] += 1
    signature_records = [
        {
            "offset": signature[0],
            "offset_hex": f"0x{signature[0]:X}",
            "entry_width": signature[1],
            "endianness": signature[2],
            "base": signature[3],
            "match_ratio": signature[4],
            "file_count": count,
        }
        for signature, count in signatures.most_common()
    ]
    summary = {
        "confirmed": False,
        "confidence": "STRONGLY_CORRELATED" if candidate_files else "UNKNOWN",
        "candidate_file_count": len(candidate_files),
        "inspected_file_count": sum(
            record.inspection is not None and record.inspection.adts is not None for record in records
        ),
        "candidate_files_by_role": dict(sorted(roles.items())),
        "candidate_files_by_mpeg_id": {str(key): value for key, value in sorted(mpeg_ids.items())},
        "inspected_files_by_mpeg_id": {
            str(key): value for key, value in sorted(inspected_mpeg_ids.items())
        },
        "files_without_candidate_by_mpeg_id": {
            str(key): value - mpeg_ids[key] for key, value in sorted(inspected_mpeg_ids.items())
        },
        "entry_count_range": (
            {"minimum": min(entry_counts), "maximum": max(entry_counts)} if entry_counts else None
        ),
        "frame_interval_distribution": {
            "variable" if key is None else str(key): value
            for key, value in sorted(frame_intervals.items(), key=lambda item: str(item[0]))
        },
        "signatures": signature_records,
        "interpretation": (
            "Candidate arrays match observed ADTS frame starts; semantic seek behavior is not confirmed."
        ),
    }
    return candidates, summary


def header_analysis(records: list[AudioFileAnalysis]) -> dict[str, Any]:
    successful = [record for record in records if record.inspection]
    all_headers = [record.inspection.unknown_header_bytes for record in successful if record.inspection]
    main_headers = [
        record.inspection.unknown_header_bytes
        for record in successful
        if record.role == "main" and record.inspection
    ]
    preview_headers = [
        record.inspection.unknown_header_bytes
        for record in successful
        if record.role == "preview" and record.inspection
    ]
    seek, seek_summary = _seek_table_analysis(records)
    return {
        "confidence_vocabulary": ["CONFIRMED", "STRONGLY_CORRELATED", "POSSIBLE", "UNKNOWN"],
        "common_byte_ranges_all": common_byte_ranges(all_headers),
        "common_byte_ranges_main": common_byte_ranges(main_headers),
        "common_byte_ranges_preview": common_byte_ranges(preview_headers),
        "field_candidates": field_candidates(records),
        "seek_table_analysis": seek_summary,
        "seek_table_candidates": seek,
        "sample_count_status": "UNKNOWN",
        "encoder_delay_status": "UNKNOWN",
        "padding_status": "UNKNOWN",
        "unknown_regions": "All header bytes remain unknown unless listed as correlated candidates.",
    }
