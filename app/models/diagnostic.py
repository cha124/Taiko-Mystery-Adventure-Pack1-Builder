from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.validation import ValidationIssue, status_from_issues


@dataclass
class DiagnosticReport:
    source: Path
    source_sha256: str
    source_size: int
    cia: dict[str, Any]
    profile: dict[str, Any]
    song_catalog: dict[str, Any] = field(default_factory=dict)
    compatibility: dict[str, Any] = field(default_factory=dict)
    reference_validation: dict[str, Any] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    schema_version: int = 1
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def status(self) -> str:
        return status_from_issues(self.issues)

    def to_dict(self) -> dict[str, Any]:
        issues = [issue.to_dict() for issue in self.issues]
        errors = [issue for issue in issues if issue["severity"] == "ERROR"]
        warnings = [issue for issue in issues if issue["severity"] == "WARNING"]
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "static_validation": self.status,
            "device_validation": "NOT_TESTED",
            "source": {
                "path": str(self.source.resolve()),
                "size": self.source_size,
                "sha256": self.source_sha256,
            },
            "profile": self.profile,
            "game_profile": self.profile,
            "compatibility": self.compatibility,
            "title_id": self.cia.get("title_id"),
            "cia_sha256": self.source_sha256,
            "content_count": self.cia.get("tmd_content_count"),
            "contents": self.cia.get("contents", []),
            "romfs_files": self.cia.get("romfs_files", []),
            "cia": self.cia,
            "song_catalog": self.song_catalog,
            "song_slots": self.song_catalog.get("songs", []),
            "reference_validation": self.reference_validation,
            "summary": {
                "detected_song_count": self.song_catalog.get("song_count", 0),
                "error_count": sum(i.severity == "ERROR" for i in self.issues),
                "warning_count": sum(i.severity == "WARNING" for i in self.issues),
            },
            "issues": issues,
            "errors": errors,
            "warnings": warnings,
        }
