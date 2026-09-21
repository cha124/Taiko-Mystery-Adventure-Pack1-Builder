from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.models.audio import AudioFileAnalysis, NAACInspection


FORENSICS_SCHEMA_VERSION = 1
TABLE_START = 0x30
TABLE_POINTER_OFFSET = 0x2C
TABLE_ENTRY_WIDTH = 4
TABLE_STRIDES = tuple(range(1, 17))
COHORT_NAMES = (
    "all",
    "main",
    "preview",
    "mpeg_id_0",
    "mpeg_id_1",
    "main_mpeg_id_0",
    "main_mpeg_id_1",
    "preview_mpeg_id_0",
    "preview_mpeg_id_1",
)
FIELD_TARGETS = (
    "header_size",
    "payload_offset",
    "naac_total_size",
    "payload_size",
    "frame_count",
    "decoded_nominal_samples",
    "sample_rate",
    "duration_samples",
)
FIELD_TRANSFORMS = (("identity", 1), ("divide_by_256", 256), ("divide_by_1024", 1024))
PREVIEW_SAMPLE_VALUES = (480256, 480000, 256, 1024, 469)
ROLE_PATTERN_OFFSETS = (0x18, 0x19, 0x1A, 0x22)
ROLE_WINDOW_START = 0x16
ROLE_WINDOW_END = 0x28


def _integer_distribution(values: Iterable[int]) -> dict[str, int]:
    counts = Counter(values)
    return {str(key): counts[key] for key in sorted(counts)}


def _hex_distribution(values: Iterable[int]) -> dict[str, int]:
    counts = Counter(values)
    return {f"{key:02X}": counts[key] for key in sorted(counts)}


def _successful(records: Iterable[AudioFileAnalysis]) -> list[AudioFileAnalysis]:
    return [
        record
        for record in records
        if record.parse_status == "SUCCESS"
        and record.inspection is not None
        and record.inspection.adts is not None
    ]


def _cohorts(records: list[AudioFileAnalysis]) -> dict[str, list[AudioFileAnalysis]]:
    return {
        "all": records,
        "main": [record for record in records if record.role == "main"],
        "preview": [record for record in records if record.role == "preview"],
        "mpeg_id_0": [
            record for record in records if record.inspection.adts.mpeg_id == 0  # type: ignore[union-attr]
        ],
        "mpeg_id_1": [
            record for record in records if record.inspection.adts.mpeg_id == 1  # type: ignore[union-attr]
        ],
        "main_mpeg_id_0": [
            record
            for record in records
            if record.role == "main" and record.inspection.adts.mpeg_id == 0  # type: ignore[union-attr]
        ],
        "main_mpeg_id_1": [
            record
            for record in records
            if record.role == "main" and record.inspection.adts.mpeg_id == 1  # type: ignore[union-attr]
        ],
        "preview_mpeg_id_0": [
            record
            for record in records
            if record.role == "preview" and record.inspection.adts.mpeg_id == 0  # type: ignore[union-attr]
        ],
        "preview_mpeg_id_1": [
            record
            for record in records
            if record.role == "preview" and record.inspection.adts.mpeg_id == 1  # type: ignore[union-attr]
        ],
    }


def _header_stats(selected: list[AudioFileAnalysis]) -> dict[str, Any]:
    headers = [record.inspection.unknown_header_bytes for record in selected if record.inspection]
    header_sizes = [record.inspection.header_size for record in selected if record.inspection]
    maximum_size = max((len(header) for header in headers), default=0)
    per_offset: dict[str, int] = {}
    constant_count = 0
    for offset in range(maximum_size):
        values = [header[offset] for header in headers if offset < len(header)]
        per_offset[str(offset)] = len(set(values))
        if len(values) == len(headers) and values and len(set(values)) == 1:
            constant_count += 1
    return {
        "file_count": len(selected),
        "header_size_distribution": _integer_distribution(header_sizes),
        "constant_byte_count": constant_count,
        "per_offset_unique_value_count": per_offset,
        "compared_header_size": maximum_size,
    }


def cohort_statistics(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    cohorts = _cohorts(successful)
    return {name: _header_stats(cohorts[name]) for name in COHORT_NAMES}


def _field_value(record: AudioFileAnalysis, target: str) -> int:
    inspection = record.inspection
    assert inspection is not None and inspection.adts is not None
    values: dict[str, int] = {
        "header_size": inspection.header_size,
        "payload_offset": inspection.payload_offset,
        "naac_total_size": inspection.total_size,
        "payload_size": inspection.payload_size,
        "frame_count": inspection.adts.frame_count,
        "decoded_nominal_samples": inspection.adts.total_samples,
        "sample_rate": inspection.adts.sample_rate,
        # ADTS parsing gives duration in samples directly.  Keep the duplicate
        # target explicit so a matching offset is not over-interpreted.
        "duration_samples": inspection.adts.total_samples,
    }
    return values[target]


def _field_candidate(
    *,
    scope: str,
    selected: list[AudioFileAnalysis],
    target: str,
    transform: str,
    offset: int,
    width: int,
    endianness: str,
    transformed_values: list[int],
    matches: int,
) -> dict[str, Any]:
    headers = [record.inspection.unknown_header_bytes for record in selected if record.inspection]
    raw_examples = sorted({header[offset : offset + width].hex() for header in headers})[:8]
    ratio = matches / len(selected)
    distinct_count = len(set(transformed_values))
    strongly_correlated = ratio == 1.0 and len(selected) >= 5 and distinct_count >= 3
    interpretation = f"{target}_{transform}_candidate"
    return {
        "scope": scope,
        "target": target,
        "transform": transform,
        "interpretation": interpretation,
        "offset": offset,
        "offset_hex": f"0x{offset:X}",
        "alignment": offset % width,
        "width": width,
        "endianness": endianness,
        "matches": matches,
        "total": len(selected),
        "match_ratio": ratio,
        "target_distinct_value_count": distinct_count,
        "observed_raw_hex_examples": raw_examples,
        "confidence": "STRONGLY_CORRELATED" if strongly_correlated else "POSSIBLE",
        "duplicate_of": "decoded_nominal_samples"
        if target == "duration_samples"
        else None,
    }


def field_candidates(records: Iterable[AudioFileAnalysis]) -> list[dict[str, Any]]:
    """Search only the explicit targets, widths, byte orders, and transforms."""

    successful = _successful(records)
    results: list[dict[str, Any]] = []
    for scope, selected in _cohorts(successful).items():
        if not selected:
            continue
        headers = [record.inspection.unknown_header_bytes for record in selected if record.inspection]
        limit = min((len(header) for header in headers), default=0)
        for target in FIELD_TARGETS:
            raw_values = [_field_value(record, target) for record in selected]
            for transform, divisor in FIELD_TRANSFORMS:
                if any(value % divisor for value in raw_values):
                    continue
                transformed_values = [value // divisor for value in raw_values]
                for width in (2, 4, 8):
                    maximum = (1 << (width * 8)) - 1
                    if any(value < 0 or value > maximum for value in transformed_values):
                        continue
                    for endianness in ("little", "big"):
                        encoded = [value.to_bytes(width, endianness) for value in transformed_values]
                        possible_offsets: Counter[int] = Counter()
                        for header, expected in zip(headers, encoded):
                            cursor = 0
                            while True:
                                offset = header.find(expected, cursor, limit)
                                if offset < 0:
                                    break
                                possible_offsets[offset] += 1
                                cursor = offset + 1
                        for offset, matches in possible_offsets.items():
                            if matches / len(selected) < 0.95:
                                continue
                            results.append(
                                _field_candidate(
                                    scope=scope,
                                    selected=selected,
                                    target=target,
                                    transform=transform,
                                    offset=offset,
                                    width=width,
                                    endianness=endianness,
                                    transformed_values=transformed_values,
                                    matches=matches,
                                )
                            )
    return sorted(
        results,
        key=lambda item: (
            item["scope"],
            item["target"],
            item["transform"],
            item["offset"],
            item["width"],
            item["endianness"],
        ),
    )


def _value_profile(values: list[bytes]) -> dict[str, Any]:
    unique_values = sorted({value.hex() for value in values})
    return {
        "file_count": len(values),
        "unique_value_count": len(unique_values),
        "unique_values_hex": unique_values[:16],
        "unique_values_truncated": len(unique_values) > 16,
    }


def mpeg_comparison(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    cohorts = _cohorts(successful)
    mpeg0 = cohorts["mpeg_id_0"]
    mpeg1 = cohorts["mpeg_id_1"]
    maximum_size = max(
        (len(record.inspection.unknown_header_bytes) for record in successful if record.inspection),
        default=0,
    )
    offsets: list[dict[str, Any]] = []
    for offset in range(maximum_size):
        offsets.append(
            {
                "offset": offset,
                "offset_hex": f"0x{offset:X}",
                "mpeg_id_0": _value_profile(
                    [
                        record.inspection.unknown_header_bytes[offset : offset + 1]
                        for record in mpeg0
                        if record.inspection and offset < len(record.inspection.unknown_header_bytes)
                    ]
                ),
                "mpeg_id_1": _value_profile(
                    [
                        record.inspection.unknown_header_bytes[offset : offset + 1]
                        for record in mpeg1
                        if record.inspection and offset < len(record.inspection.unknown_header_bytes)
                    ]
                ),
            }
        )

    low_offset_windows: list[dict[str, Any]] = []
    for offset in range(0x00, min(0x40, maximum_size)):
        item: dict[str, Any] = {"offset": offset, "offset_hex": f"0x{offset:X}"}
        for cohort_name, selected in (("mpeg_id_0", mpeg0), ("mpeg_id_1", mpeg1)):
            u16 = [
                int.from_bytes(record.inspection.unknown_header_bytes[offset : offset + 2], "little")
                for record in selected
                if record.inspection and offset + 2 <= len(record.inspection.unknown_header_bytes)
            ]
            u32 = [
                int.from_bytes(record.inspection.unknown_header_bytes[offset : offset + 4], "little")
                for record in selected
                if record.inspection and offset + 4 <= len(record.inspection.unknown_header_bytes)
            ]
            item[cohort_name] = {
                "u16_le": {
                    "unique_value_count": len(set(u16)),
                    "values": sorted(set(u16))[:16],
                    "values_truncated": len(set(u16)) > 16,
                },
                "u32_le": {
                    "unique_value_count": len(set(u32)),
                    "values": sorted(set(u32))[:16],
                    "values_truncated": len(set(u32)) > 16,
                },
            }
        low_offset_windows.append(item)
    return {
        "mpeg_id_0_file_count": len(mpeg0),
        "mpeg_id_1_file_count": len(mpeg1),
        "offsets": offsets,
        "low_offset_windows_u16_u32_le": low_offset_windows,
        "value_examples_are_capped": True,
    }


def _table_tail(header: bytes, entry_count: int) -> dict[str, Any]:
    tail = header[TABLE_START + entry_count * TABLE_ENTRY_WIDTH :]
    zero_bytes = sum(byte == 0 for byte in tail)
    non_zero_bytes = len(tail) - zero_bytes
    return {
        "tail_size": len(tail),
        "zero_bytes": zero_bytes,
        "non_zero_bytes": non_zero_bytes,
        "zero_ratio": zero_bytes / len(tail) if tail else 1.0,
    }


def _table_for_record(record: AudioFileAnalysis) -> dict[str, Any]:
    inspection = record.inspection
    assert inspection is not None and inspection.adts is not None
    header = inspection.unknown_header_bytes
    capacity = max((inspection.header_size - TABLE_START) // TABLE_ENTRY_WIDTH, 0)
    frame_offsets = inspection.frame_offsets
    predicted_stride = (
        (len(frame_offsets) + capacity - 1) // capacity if capacity and frame_offsets else None
    )
    if capacity == 0 or not frame_offsets:
        return {
            "content_index": record.content_index,
            "role": record.role,
            "mpeg_id": inspection.adts.mpeg_id,
            "predicted_stride": predicted_stride,
            "observed_best_stride": None,
            "exact_match": False,
            "entry_count": 0,
            "capacity": capacity,
            "unused_entries": capacity,
            "tail_zero_ratio": 1.0,
            "status": "NOT_APPLICABLE",
            "strides": [],
        }
    stride_results: list[dict[str, Any]] = []
    for stride in TABLE_STRIDES:
        expected = frame_offsets[::stride][:capacity]
        observed = [
            int.from_bytes(
                header[TABLE_START + index * TABLE_ENTRY_WIDTH : TABLE_START + (index + 1) * TABLE_ENTRY_WIDTH],
                "little",
            )
            for index in range(min(capacity, len(header[TABLE_START:]) // TABLE_ENTRY_WIDTH))
        ]
        observed = observed[: len(expected)]
        matches = sum(left == right for left, right in zip(observed, expected))
        mismatches = [index for index, (left, right) in enumerate(zip(observed, expected)) if left != right]
        tail = _table_tail(header, len(expected))
        stride_results.append(
            {
                "stride": stride,
                "expected_entry_count": len(expected),
                "matched_entries": matches,
                "match_ratio": matches / len(expected) if expected else 0.0,
                "remaining_header_bytes_zero_ratio": tail["zero_ratio"],
                "first_mismatch_index": mismatches[0] if mismatches else None,
                "tail": tail,
            }
        )
    best = max(
        stride_results,
        key=lambda item: (
            item["match_ratio"],
            item["matched_entries"],
            item["remaining_header_bytes_zero_ratio"],
            int(item["stride"] == predicted_stride),
            -item["stride"],
        ),
    )
    entry_count = best["expected_entry_count"]
    exact_match = bool(entry_count and best["matched_entries"] == entry_count)
    return {
        "content_index": record.content_index,
        "role": record.role,
        "mpeg_id": inspection.adts.mpeg_id,
        "predicted_stride": predicted_stride,
        "observed_best_stride": best["stride"],
        "exact_match": exact_match,
        "entry_count": entry_count,
        "capacity": capacity,
        "unused_entries": max(capacity - entry_count, 0),
        "tail_zero_ratio": best["tail"]["zero_ratio"],
        "matched_entries": best["matched_entries"],
        "match_ratio": best["match_ratio"],
        "first_mismatch_index": best["first_mismatch_index"],
        "remaining_header_bytes_zero_ratio": best["remaining_header_bytes_zero_ratio"],
        "tail": best["tail"],
        "strides": stride_results,
    }


def _table_group_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    exact = sum(item["exact_match"] for item in results)
    files = len(results)
    strides = Counter(
        str(item["observed_best_stride"])
        for item in results
        if item["observed_best_stride"] is not None
    )
    entries = [item["entry_count"] for item in results]
    exact_match_ratio = exact / files if files else 0.0
    if files == 0:
        confidence = "UNKNOWN"
    elif files >= 5 and exact == files:
        confidence = "FRAME_OFFSET_ARRAY_STRONGLY_CORRELATED"
    elif exact > 0:
        confidence = "POSSIBLE"
    else:
        confidence = "UNKNOWN"
    return {
        "exact_matches": exact,
        "files": files,
        "exact_match_ratio": exact_match_ratio,
        # Keep the historical key for consumers that used the generic name.
        "match_ratio": exact_match_ratio,
        "confidence": confidence,
        "entry_count_range": (
            {"minimum": min(entries), "maximum": max(entries)} if entries else None
        ),
        "stride_distribution": dict(sorted(strides.items())),
    }


def frame_offset_table_hypothesis(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    per_file = [_table_for_record(record) for record in successful]
    groups = {
        "all": per_file,
        "main": [item for item in per_file if item["role"] == "main"],
        "preview": [item for item in per_file if item["role"] == "preview"],
        "mpeg_id_0": [item for item in per_file if item["mpeg_id"] == 0],
        "mpeg_id_1": [item for item in per_file if item["mpeg_id"] == 1],
    }
    tail_by_mpeg: dict[str, Any] = {}
    for mpeg_id in (0, 1):
        selected = groups[f"mpeg_id_{mpeg_id}"]
        total_tail = sum(item["tail"]["tail_size"] for item in selected)
        total_zero = sum(item["tail"]["zero_bytes"] for item in selected)
        total_non_zero = sum(item["tail"]["non_zero_bytes"] for item in selected)
        tail_by_mpeg[str(mpeg_id)] = {
            "files": len(selected),
            "tail_size_distribution": _integer_distribution(
                item["tail"]["tail_size"] for item in selected
            ),
            "zero_bytes": total_zero,
            "non_zero_bytes": total_non_zero,
            "zero_ratio": total_zero / (total_zero + total_non_zero)
            if total_zero + total_non_zero
            else 1.0,
        }
    summary = {name: _table_group_summary(selected) for name, selected in groups.items()}
    for name in ("mpeg_id_0", "mpeg_id_1", "main", "preview"):
        summary[name]["exact_matches_over_files"] = (
            f"{summary[name]['exact_matches']} / {summary[name]['files']}"
        )
    cohort_confidence = {
        name: summary[name]["confidence"] for name in groups
    }
    if any(
        value == "FRAME_OFFSET_ARRAY_STRONGLY_CORRELATED"
        for value in cohort_confidence.values()
    ):
        confidence = "PARTIAL_COHORT_EVIDENCE"
    elif any(value == "POSSIBLE" for value in cohort_confidence.values()):
        confidence = "POSSIBLE"
    else:
        confidence = "UNKNOWN"
    return {
        "array_start_offset": TABLE_START,
        "array_start_offset_hex": f"0x{TABLE_START:X}",
        "entry_width": TABLE_ENTRY_WIDTH,
        "capacity_formula": "(header_size - 0x30) // 4",
        "predicted_stride_formula": "ceil(frame_count / capacity)",
        "per_file": per_file,
        "cohort_summary": summary,
        "cohort_confidence": cohort_confidence,
        "tail_analysis_by_mpeg_id": tail_by_mpeg,
        "confidence": confidence,
        "semantic_status": "UNKNOWN",
    }


def table_pointer_analysis(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    values: list[int] = []
    for record in successful:
        header = record.inspection.unknown_header_bytes  # type: ignore[union-attr]
        if len(header) >= TABLE_POINTER_OFFSET + 4:
            values.append(int.from_bytes(header[TABLE_POINTER_OFFSET : TABLE_POINTER_OFFSET + 4], "little"))
    matches = sum(value == TABLE_START for value in values)
    return {
        "offset": TABLE_POINTER_OFFSET,
        "offset_hex": f"0x{TABLE_POINTER_OFFSET:X}",
        "value_distribution": _integer_distribution(values),
        "array_start_offset": TABLE_START,
        "matches": matches,
        "files": len(values),
        "match_ratio": matches / len(values) if values else 0.0,
        "candidate_label": "TABLE_OFFSET_POINTER_CANDIDATE",
        "confidence": "POSSIBLE" if values and matches == len(values) else "UNKNOWN",
    }


def _representation_values(inspection: NAACInspection) -> dict[str, tuple[int, ...]]:
    cumulative: list[int] = []
    total = 0
    for payload_length in inspection.frame_payload_lengths:
        cumulative.append(total)
        total += payload_length
    return {
        "frame_start_payload_relative": inspection.frame_offsets,
        "frame_end_payload_relative": inspection.frame_end_offsets,
        "frame_start_file_absolute": tuple(
            inspection.payload_offset + offset for offset in inspection.frame_offsets
        ),
        "cumulative_raw_aac_payload_bytes": tuple(cumulative),
    }


def _alternative_arrays_for_record(record: AudioFileAnalysis) -> list[dict[str, Any]]:
    inspection = record.inspection
    assert inspection is not None and inspection.adts is not None
    header = inspection.unknown_header_bytes
    candidates: list[dict[str, Any]] = []
    for representation, expected in _representation_values(inspection).items():
        if len(expected) < 8:
            continue
        for endianness in ("little", "big"):
            maximum = min(len(expected), len(header) // 4)
            # Seed the scan from several expected entries.  A full value
            # comparison is still performed for every seeded start, while
            # avoiding an O(header_size * entry_count) walk over every random
            # byte offset in a 4 KiB header.
            sample_indices = sorted(
                {
                    *range(min(8, maximum)),
                    *range(8, maximum, 64),
                    maximum - 1,
                }
            )
            possible_offsets: set[int] = set()
            for sample_index in sample_indices:
                encoded = expected[sample_index].to_bytes(4, endianness)
                cursor = 0
                while True:
                    found = header.find(encoded, cursor)
                    if found < 0:
                        break
                    candidate_offset = found - sample_index * 4
                    if 0 <= candidate_offset <= len(header) - 4 * 8:
                        possible_offsets.add(candidate_offset)
                    cursor = found + 1
            for offset in sorted(possible_offsets):
                entry_count = min(maximum, (len(header) - offset) // 4)
                if entry_count < 8:
                    continue
                observed = [
                    int.from_bytes(header[offset + index * 4 : offset + (index + 1) * 4], endianness)
                    for index in range(entry_count)
                ]
                if any(left >= right for left, right in zip(observed, observed[1:])):
                    continue
                matches = sum(observed[index] == expected[index] for index in range(entry_count))
                ratio = matches / entry_count
                if ratio < 0.95:
                    continue
                mismatch_indices = [
                    index for index in range(entry_count) if observed[index] != expected[index]
                ]
                candidates.append(
                    {
                        "content_index": record.content_index,
                        "role": record.role,
                        "mpeg_id": inspection.adts.mpeg_id,
                        "representation": representation,
                        "offset": offset,
                        "offset_hex": f"0x{offset:X}",
                        "entry_width": 4,
                        "endianness": endianness,
                        "entry_count": entry_count,
                        "matches": matches,
                        "match_ratio": ratio,
                        "first_mismatch_index": mismatch_indices[0]
                        if mismatch_indices
                        else None,
                    }
                )
    return candidates


def alternative_offset_arrays(records: Iterable[AudioFileAnalysis], table: dict[str, Any]) -> dict[str, Any]:
    successful = _successful(records)
    table_by_identity = {
        (item["content_index"], item["role"]): item for item in table["per_file"]
    }
    per_file: list[dict[str, Any]] = []
    for record in successful:
        inspection = record.inspection
        assert inspection is not None and inspection.adts is not None
        if inspection.adts.mpeg_id != 1:
            continue
        direct = table_by_identity[(record.content_index, record.role)]
        direct_found = any(item["match_ratio"] >= 0.95 for item in direct["strides"])
        if direct_found:
            continue
        candidates = _alternative_arrays_for_record(record)
        per_file.append(
            {
                "content_index": record.content_index,
                "role": record.role,
                "mpeg_id": 1,
                "direct_0x30_found": False,
                "candidates": candidates,
            }
        )
    flat = [candidate for item in per_file for candidate in item["candidates"]]
    return {
        "scope": "mpeg_id_1_without_direct_0x30_match",
        "representations": [
            "frame_start_payload_relative",
            "frame_end_payload_relative",
            "frame_start_file_absolute",
            "cumulative_raw_aac_payload_bytes",
        ],
        "minimum_entry_count": 8,
        "minimum_match_ratio": 0.95,
        "files_scanned": len(per_file),
        "files_with_candidate": sum(bool(item["candidates"]) for item in per_file),
        "per_file": per_file,
        "candidates": flat,
    }


def _raw_role_distribution(selected: list[AudioFileAnalysis], offset: int) -> dict[str, int]:
    values = [
        record.inspection.unknown_header_bytes[offset]
        for record in selected
        if record.inspection and offset < len(record.inspection.unknown_header_bytes)
    ]
    return _hex_distribution(values)


def role_specific_patterns(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    cohorts = _cohorts(successful)
    required_cohorts = {
        "main": cohorts["main"],
        "preview": cohorts["preview"],
        "mpeg0": cohorts["mpeg_id_0"],
        "mpeg1": cohorts["mpeg_id_1"],
    }
    raw = {
        f"0x{offset:X}": {
            cohort: _raw_role_distribution(selected, offset)
            for cohort, selected in required_cohorts.items()
        }
        for offset in ROLE_PATTERN_OFFSETS
    }
    windows: dict[str, Any] = {}
    for cohort, selected in required_cohorts.items():
        u16: dict[str, Any] = {}
        u32: dict[str, Any] = {}
        for offset in range(ROLE_WINDOW_START, ROLE_WINDOW_END):
            values16 = [
                int.from_bytes(record.inspection.unknown_header_bytes[offset : offset + 2], "little")
                for record in selected
                if record.inspection and offset + 2 <= len(record.inspection.unknown_header_bytes)
            ]
            values32 = [
                int.from_bytes(record.inspection.unknown_header_bytes[offset : offset + 4], "little")
                for record in selected
                if record.inspection and offset + 4 <= len(record.inspection.unknown_header_bytes)
            ]
            u16[f"0x{offset:X}"] = _integer_distribution(values16)
            u32[f"0x{offset:X}"] = _integer_distribution(values32)
        windows[cohort] = {"u16_le": u16, "u32_le": u32}
    return {
        "raw_value_distribution": raw,
        "window_start": ROLE_WINDOW_START,
        "window_end_exclusive": ROLE_WINDOW_END,
        "le_integer_windows": windows,
        "semantics": "UNKNOWN",
    }


def _preview_value_candidates(records: list[AudioFileAnalysis]) -> list[dict[str, Any]]:
    previews = [record for record in records if record.role == "preview"]
    headers = [record.inspection.unknown_header_bytes for record in previews if record.inspection]
    if not headers:
        return []
    candidates: list[dict[str, Any]] = []
    for target in PREVIEW_SAMPLE_VALUES:
        for width in (2, 4, 8):
            if target > (1 << (width * 8)) - 1:
                continue
            for endianness in ("little", "big"):
                expected = target.to_bytes(width, endianness)
                limit = min(len(header) for header in headers)
                for offset in range(0, max(0, limit - width + 1)):
                    matches = sum(header[offset : offset + width] == expected for header in headers)
                    if matches != len(headers):
                        continue
                    candidates.append(
                        {
                            "value": target,
                            "offset": offset,
                            "offset_hex": f"0x{offset:X}",
                            "width": width,
                            "endianness": endianness,
                            "matches": matches,
                            "total": len(headers),
                            "match_ratio": 1.0,
                            "confidence": "POSSIBLE",
                        }
                    )
    return candidates


def _main_sample_correlations(
    records: list[AudioFileAnalysis], preview_candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    mains = [record for record in records if record.role == "main"]
    output: list[dict[str, Any]] = []
    metrics = ("decoded_nominal_samples", "frame_count", "payload_size")
    for candidate in preview_candidates:
        selected: list[tuple[AudioFileAnalysis, int]] = []
        for record in mains:
            inspection = record.inspection
            if inspection is None or candidate["offset"] + candidate["width"] > len(
                inspection.unknown_header_bytes
            ):
                continue
            selected.append(
                (
                    record,
                    int.from_bytes(
                        inspection.unknown_header_bytes[
                            candidate["offset"] : candidate["offset"] + candidate["width"]
                        ],
                        candidate["endianness"],
                    ),
                )
            )
        correlations: list[dict[str, Any]] = []
        for metric in metrics:
            expected = [_field_value(record, metric) for record, _ in selected]
            matches = sum(value == observed for (record, observed), value in zip(selected, expected))
            distinct_count = len(set(expected))
            ratio = matches / len(selected) if selected else 0.0
            strong = ratio == 1.0 and len(selected) >= 5 and distinct_count >= 3
            if selected and ratio >= 0.95:
                correlations.append(
                    {
                        "metric": metric,
                        "matches": matches,
                        "total": len(selected),
                        "match_ratio": ratio,
                        "target_distinct_value_count": distinct_count,
                        "confidence": "STRONGLY_CORRELATED" if strong else "POSSIBLE",
                    }
                )
        if correlations:
            output.append({**candidate, "main_correlations": correlations})
    return output


def sample_count_analysis(records: Iterable[AudioFileAnalysis]) -> dict[str, Any]:
    successful = _successful(records)
    preview_candidates = _preview_value_candidates(successful)
    main_correlations = _main_sample_correlations(successful, preview_candidates)
    return {
        "preview_expected_values": list(PREVIEW_SAMPLE_VALUES),
        "preview_candidates": preview_candidates,
        "main_variation_checks": main_correlations,
        "nominal_samples": {
            "status": "OBSERVED",
            "definition": "ADTS decoded nominal samples = sum(1024 * (raw_data_blocks + 1)).",
        },
        "duration_samples": {
            "status": "OBSERVED",
            "duplicate_of": "decoded_nominal_samples",
        },
        "playable_samples": {"status": "UNKNOWN"},
        "encoder_delay": {"status": "UNKNOWN"},
        "padding": {"status": "UNKNOWN"},
    }


def _best_candidates(
    candidates: list[dict[str, Any]], scope: str, target: str
) -> dict[str, Any]:
    selected = [item for item in candidates if item["scope"] == scope and item["target"] == target]
    selected.sort(
        key=lambda item: (
            item["confidence"] == "STRONGLY_CORRELATED",
            item["match_ratio"],
            item["target_distinct_value_count"],
            -item["offset"],
        ),
        reverse=True,
    )
    return {
        "status": "FOUND" if selected else "NOT_FOUND",
        "candidates": selected,
    }


def _unresolved(
    *,
    audio_status: str,
    candidates: list[dict[str, Any]],
    table: dict[str, Any],
    alternatives: dict[str, Any],
) -> list[str]:
    unresolved: list[str] = []
    if audio_status == "FAIL":
        unresolved.append("Audio Scan safety checks contain ERROR issues.")
    for target in ("decoded_nominal_samples", "payload_size"):
        mpeg1 = _best_candidates(candidates, "mpeg_id_1", target)
        if mpeg1["status"] == "NOT_FOUND":
            unresolved.append(f"MPEG ID 1 {target} candidate was NOT_FOUND.")
    mpeg1_table = table["cohort_summary"]["mpeg_id_1"]
    if mpeg1_table["exact_matches"] != mpeg1_table["files"]:
        if not alternatives["files_with_candidate"]:
            unresolved.append("No alternative MPEG ID 1 monotonic offset array candidate was found.")
        else:
            unresolved.append("MPEG ID 1 offset representation is not an exact all-file rule.")
    unresolved.extend(
        [
            "Encoder delay is UNKNOWN.",
            "Padding is UNKNOWN.",
            "Playable sample count is UNKNOWN.",
            "NAAC write compatibility remains BLOCKED and generation is not approved.",
        ]
    )
    return unresolved


def analyze_header_forensics(
    records: Iterable[AudioFileAnalysis],
    *,
    source: Path,
    source_size: int,
    source_sha256: str,
    audio_report: Any,
) -> dict[str, Any]:
    """Build a bounded, read-only NAAC header report from already parsed records."""

    successful = _successful(records)
    candidates = field_candidates(successful)
    table = frame_offset_table_hypothesis(successful)
    alternatives = alternative_offset_arrays(successful, table)
    preview_sample_analysis = sample_count_analysis(successful)
    audio_payload = audio_report.to_dict()
    audio_issues = [issue.to_dict() for issue in audio_report.all_issues]
    mpeg1_decoded = _best_candidates(candidates, "mpeg_id_1", "decoded_nominal_samples")
    mpeg1_payload = _best_candidates(candidates, "mpeg_id_1", "payload_size")
    unresolved = _unresolved(
        audio_status=audio_report.status,
        candidates=candidates,
        table=table,
        alternatives=alternatives,
    )
    mpeg1_summary = {
        "files": len(_cohorts(successful)["mpeg_id_1"]),
        "decoded_nominal_samples_candidate": mpeg1_decoded,
        "payload_size_candidate": mpeg1_payload,
        "array_candidate": alternatives,
        "unresolved": [item for item in unresolved if "MPEG ID 1" in item],
    }
    ready = (
        audio_report.status != "FAIL"
        and len(successful) == len(audio_report.records)
        and mpeg1_decoded["status"] == "FOUND"
        and mpeg1_payload["status"] == "FOUND"
        and all(
            item["confidence"] == "STRONGLY_CORRELATED"
            for item in mpeg1_decoded["candidates"][:1] + mpeg1_payload["candidates"][:1]
        )
        and table["cohort_summary"]["mpeg_id_0"]["exact_matches"]
        == table["cohort_summary"]["mpeg_id_0"]["files"]
        and table["cohort_summary"]["mpeg_id_1"]["exact_matches"]
        == table["cohort_summary"]["mpeg_id_1"]["files"]
    )
    return {
        "schema_version": FORENSICS_SCHEMA_VERSION,
        "read_only": True,
        "device_tested": False,
        "generation_approved": False,
        "write_compatibility": "BLOCKED",
        "source": {
            "filename": source.name,
            "size": source_size,
            "sha256": source_sha256,
        },
        "safety": {
            "audio_scan_status": audio_report.status,
            "audio_scan_summary": audio_payload["summary"],
            "issues": audio_issues,
        },
        "cohorts": cohort_statistics(successful),
        "field_candidates": candidates,
        "mpeg_comparison": mpeg_comparison(successful),
        "mpeg_id_1": mpeg1_summary,
        "frame_offset_table_hypothesis": table,
        "table_offset_pointer": table_pointer_analysis(successful),
        "alternative_offset_arrays": alternatives,
        "role_specific_patterns": role_specific_patterns(successful),
        "sample_count_analysis": preview_sample_analysis,
        "decision": "READY_FOR_AUDIO_CANDIDATE_PROTOTYPE"
        if ready
        else "MORE_AUDIO_RESEARCH_REQUIRED",
        "unresolved": unresolved,
    }
