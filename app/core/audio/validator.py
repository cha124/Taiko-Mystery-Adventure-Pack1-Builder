from __future__ import annotations

from collections import Counter

from app.models.audio import AudioFileAnalysis, AudioIssue


def validate_collection(records: list[AudioFileAnalysis]) -> tuple[AudioIssue, ...]:
    issues: list[AudioIssue] = []
    successful = [record for record in records if record.inspection is not None]
    header_sizes = Counter(record.inspection.header_size for record in successful if record.inspection)
    if len(header_sizes) > 1:
        issues.append(
            AudioIssue(
                "NAAC_HEADER_SIZE_VARIATION",
                "WARNING",
                f"Multiple observed NAAC header sizes: {dict(sorted(header_sizes.items()))}.",
            )
        )
    for role in ("main", "preview"):
        role_records = [record for record in successful if record.role == role]
        dimensions = {
            "sample rate": (
                "SAMPLE_RATE",
                [record.inspection.adts.sample_rate for record in role_records if record.inspection and record.inspection.adts],
            ),
            "channel count": (
                "CHANNEL_COUNT",
                [record.inspection.adts.channels for record in role_records if record.inspection and record.inspection.adts],
            ),
            "audio object type": (
                "AUDIO_OBJECT_TYPE",
                [record.inspection.adts.audio_object_type for record in role_records if record.inspection and record.inspection.adts],
            ),
            "MPEG ID": (
                "MPEG_ID",
                [record.inspection.adts.mpeg_id for record in role_records if record.inspection and record.inspection.adts],
            ),
            "CRC usage": (
                "CRC_USAGE",
                [record.inspection.adts.crc_usage for record in role_records if record.inspection and record.inspection.adts],
            ),
        }
        for label, (code_label, values) in dimensions.items():
            distribution = Counter(values)
            if len(distribution) > 1:
                issues.append(
                    AudioIssue(
                        f"NAAC_ROLE_{code_label}_VARIATION",
                        "WARNING",
                        f"Observed multiple {label} values among {role} files: "
                        f"{dict(sorted(distribution.items()))}.",
                    )
                )
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
    if len(main_headers) >= 2 and len(preview_headers) >= 2:
        limit = min(map(len, main_headers + preview_headers))
        role_specific_offsets = [
            offset
            for offset in range(limit)
            if len({header[offset] for header in main_headers}) == 1
            and len({header[offset] for header in preview_headers}) == 1
            and main_headers[0][offset] != preview_headers[0][offset]
        ]
        if role_specific_offsets:
            displayed = ", ".join(f"0x{offset:X}" for offset in role_specific_offsets[:16])
            suffix = " ..." if len(role_specific_offsets) > 16 else ""
            issues.append(
                AudioIssue(
                    "NAAC_MAIN_PREVIEW_HEADER_PATTERN_DIFFERENCE",
                    "WARNING",
                    "Observed role-specific constant header bytes with unknown semantics at "
                    f"{displayed}{suffix} ({len(role_specific_offsets)} byte positions).",
                )
            )
    return tuple(issues)
