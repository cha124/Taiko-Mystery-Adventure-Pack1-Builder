from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

Severity = Literal["INFO", "WARNING", "ERROR"]


class DiagnosticSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    column: int
    raw_text: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass(frozen=True)
class DiagnosticMessage:
    code: str
    severity: DiagnosticSeverity
    message: str
    location: SourceLocation | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.location is not None:
            result["location"] = {
                "file": self.location.file,
                "line": self.location.line,
                "column": self.location.column,
                "raw_text": self.location.raw_text,
            }
        return result


@dataclass(frozen=True)
class ValidationResult:
    messages: tuple[DiagnosticMessage, ...] = ()

    @property
    def errors(self) -> tuple[DiagnosticMessage, ...]:
        return tuple(m for m in self.messages if m.severity is DiagnosticSeverity.ERROR)

    @property
    def warnings(self) -> tuple[DiagnosticMessage, ...]:
        return tuple(m for m in self.messages if m.severity is DiagnosticSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def extend(self, *groups: "ValidationResult") -> "ValidationResult":
        messages = list(self.messages)
        for group in groups:
            messages.extend(group.messages)
        return ValidationResult(tuple(messages))


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
