from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any

from app.models.validation import SourceLocation


class CourseKind(str, Enum):
    EASY = "Easy"
    NORMAL = "Normal"
    HARD = "Hard"
    ONI = "Oni"
    URA = "Ura"
    UNKNOWN = "Unknown"


class CommandSupport(str, Enum):
    SUPPORTED = "supported"
    RECOGNIZED_UNSUPPORTED = "recognized_unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TjaHeaderEntry:
    name: str
    value: str
    recognized: bool
    location: SourceLocation


@dataclass(frozen=True)
class TjaHeader:
    entries: tuple[TjaHeaderEntry, ...]

    def values(self, name: str) -> tuple[str, ...]:
        upper = name.upper()
        return tuple(entry.value for entry in self.entries if entry.name == upper)

    def first(self, name: str) -> str | None:
        values = self.values(name)
        return values[0] if values else None

    @property
    def title(self) -> str | None:
        return self.first("TITLE")

    @property
    def wave(self) -> str | None:
        return self.first("WAVE")

    @property
    def bpm(self) -> Decimal | None:
        raw = self.first("BPM")
        if raw is None:
            return None
        try:
            return Decimal(raw)
        except Exception:
            return None

    @property
    def offset(self) -> Decimal | None:
        raw = self.first("OFFSET")
        if raw is None:
            return None
        try:
            return Decimal(raw)
        except Exception:
            return None


TjaCommandValue = Decimal | Fraction | str | None


@dataclass(frozen=True)
class TjaCommand:
    name: str
    argument: str
    value: TjaCommandValue
    support: CommandSupport
    location: SourceLocation


@dataclass(frozen=True)
class TjaMeasure:
    notes: str
    commands: tuple[TjaCommand, ...]
    time_signature: Fraction
    bpm: Decimal
    scroll: Decimal
    start_time_seconds: Decimal
    duration_seconds: Decimal
    terminated: bool
    location: SourceLocation


@dataclass(frozen=True)
class TjaCourse:
    kind: CourseKind
    original_name: str
    level: Decimal | None
    balloon: tuple[int, ...]
    start_argument: str
    measures: tuple[TjaMeasure, ...]
    start_location: SourceLocation
    end_location: SourceLocation | None


@dataclass(frozen=True)
class TjaDocument:
    source_file: str
    encoding: str
    header: TjaHeader
    courses: tuple[TjaCourse, ...]
    source_tokens: tuple[Any, ...]

    def semantic_fingerprint(self) -> tuple[Any, ...]:
        """Location/raw-text independent representation used by normalization tests."""
        headers = tuple((e.name, e.value) for e in self.header.entries)
        courses = tuple(
            (
                c.kind.value,
                c.original_name.casefold(),
                c.level,
                c.balloon,
                c.start_argument,
                tuple(
                    (
                        m.notes,
                        tuple((cmd.name, cmd.value, cmd.support.value) for cmd in m.commands),
                        m.time_signature,
                        m.bpm,
                        m.scroll,
                        m.start_time_seconds,
                        m.duration_seconds,
                        m.terminated,
                    )
                    for m in c.measures
                ),
            )
            for c in self.courses
        )
        return headers, courses
