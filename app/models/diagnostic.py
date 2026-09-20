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
            "issues": [issue.to_dict() for issue in self.issues],
        }

