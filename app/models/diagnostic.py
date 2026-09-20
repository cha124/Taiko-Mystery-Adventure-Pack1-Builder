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
    issues: list[ValidationIssue] = field(default_factory=list)
    schema_version: int = 1
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def status(self) -> str:
        return status_from_issues(self.issues)

    def to_dict(self) -> dict[str, Any]:
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
            "cia": self.cia,
            "song_catalog": self.song_catalog,
            "summary": {
                "detected_song_count": self.song_catalog.get("song_count", 0),
                "error_count": sum(i.severity == "ERROR" for i in self.issues),
                "warning_count": sum(i.severity == "WARNING" for i in self.issues),
            },
            "issues": [issue.to_dict() for issue in self.issues],
        }
