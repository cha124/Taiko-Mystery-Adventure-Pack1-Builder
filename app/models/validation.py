from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["INFO", "WARNING", "ERROR"]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    location: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.location is not None:
            result["location"] = self.location
        if self.details:
            result["details"] = self.details
        return result


def status_from_issues(issues: list[ValidationIssue]) -> str:
    if any(issue.severity == "ERROR" for issue in issues):
        return "FAIL"
    if any(issue.severity == "WARNING" for issue in issues):
        return "WARNING"
    return "PASS"

