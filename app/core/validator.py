from __future__ import annotations

from app.core.cia_reader import CiaImage
from app.models.validation import ValidationIssue


def validate_cia(image: CiaImage, profile: dict[str, object]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    indices: set[int] = set()
    content_ids: set[int] = set()
    selected_sizes = 0

    for content in image.contents:
        location = f"tmd.content[{content.index}]"
        if content.index in indices:
            issues.append(
                ValidationIssue(
                    "CIA_TMD_DUPLICATE_INDEX",
                    "ERROR",
                    f"TMD content index {content.index} is duplicated.",
                    location,
                )
            )
        indices.add(content.index)
        if content.content_id in content_ids:
            issues.append(
                ValidationIssue(
                    "CIA_TMD_DUPLICATE_CONTENT_ID",
                    "ERROR",
                    f"TMD content ID {content.content_id:08x} is duplicated.",
                    location,
                )
            )
        content_ids.add(content.content_id)
        if content.selected:
            selected_sizes += content.size
            if content.file_offset is None or content.actual_sha256 is None:
                issues.append(
                    ValidationIssue(
                        "CIA_SELECTED_CONTENT_MISSING",
                        "ERROR",
                        "Selected content could not be mapped into the CIA.",
                        location,
                    )
                )
            elif not (content.content_type & 0x0001) and (
                content.actual_sha256 != content.sha256
            ):
                issues.append(
                    ValidationIssue(
                        "CIA_CONTENT_HASH_MISMATCH",
                        "ERROR",
                        "Unencrypted content does not match the SHA-256 stored in the TMD.",
                        location,
                        {
                            "expected": content.sha256,
                            "actual": content.actual_sha256,
                        },
                    )
                )

    if selected_sizes > image.declared_content_size:
        issues.append(
            ValidationIssue(
                "CIA_CONTENT_SIZE_UNDERRUN",
                "ERROR",
                "Selected TMD content sizes exceed the declared CIA content section.",
                "header.content_size",
                {"selected_sizes": selected_sizes, "declared": image.declared_content_size},
            )
        )

    allowed = {
        str(value).lower().removeprefix("0x")
        for value in profile.get("allowed_title_ids", [])  # type: ignore[union-attr]
    }
    title_hex = f"{image.title_id:016x}"
    if allowed and title_hex not in allowed:
        issues.append(
            ValidationIssue(
                "PROFILE_TITLE_ID_MISMATCH",
                "ERROR",
                "The CIA Title ID is not allowed by the selected profile.",
                "tmd.title_id",
                {"actual": title_hex, "allowed": sorted(allowed)},
            )
        )

    if profile.get("certification") != "device_tested":
        issues.append(
            ValidationIssue(
                "PROFILE_NOT_CERTIFIED",
                "WARNING",
                "The selected Pack1 profile has not been certified with verified device data.",
                "profile",
            )
        )
    if profile.get("slot_catalog_status") != "verified":
        issues.append(
            ValidationIssue(
                "SLOT_CATALOG_NOT_VERIFIED",
                "WARNING",
                "Pack1 slot descriptors are not verified; no song catalog claim is made.",
                "profile.slots",
            )
        )
    if profile.get("songinfo_schema_status") != "verified":
        issues.append(
            ValidationIssue(
                "SONGINFO_SCHEMA_NOT_VERIFIED",
                "WARNING",
                "SongInfo offsets and references are not verified and were not guessed.",
                "profile.songinfo",
            )
        )

    return issues
