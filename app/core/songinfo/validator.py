from __future__ import annotations

from collections.abc import Iterable

from app.models.validation import ValidationIssue


def validate_required_references(
    required_paths: Iterable[str], available_paths: Iterable[str]
) -> list[ValidationIssue]:
    available = {path.replace("\\", "/").casefold() for path in available_paths}
    issues: list[ValidationIssue] = []
    for path in required_paths:
        normalized = path.replace("\\", "/").casefold()
        if normalized not in available:
            issues.append(
                ValidationIssue(
                    "SONGINFO_REFERENCE_MISSING",
                    "ERROR",
                    f"Required SongInfo reference does not exist: {path}",
                    path,
                )
            )
    return issues

