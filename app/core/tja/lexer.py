from __future__ import annotations

from dataclasses import dataclass

from app.models.validation import (
    DiagnosticMessage,
    DiagnosticSeverity,
    SourceLocation,
    ValidationResult,
)

KNOWN_HEADERS = frozenset(
    {
        "TITLE",
        "SUBTITLE",
        "BPM",
        "WAVE",
        "OFFSET",
        "DEMOSTART",
        "SONGVOL",
        "SEVOL",
        "SIDE",
        "GENRE",
        "COURSE",
        "LEVEL",
        "BALLOON",
        "SCOREINIT",
        "SCOREDIFF",
    }
)

SUPPORTED_COMMANDS = frozenset(
    {"START", "END", "BPMCHANGE", "SCROLL", "MEASURE", "DELAY"}
)
RECOGNIZED_UNSUPPORTED_COMMANDS = frozenset(
    {
        "BRANCHSTART",
        "BRANCHEND",
        "GOGOSTART",
        "GOGOEND",
        "BARLINEON",
        "BARLINEOFF",
        "N",
        "E",
        "M",
    }
)
ARGUMENT_COMMANDS = frozenset(
    {"START", "BPMCHANGE", "SCROLL", "MEASURE", "DELAY", "BRANCHSTART"}
)
KNOWN_COMMANDS_LONGEST_FIRST = tuple(
    sorted(SUPPORTED_COMMANDS | RECOGNIZED_UNSUPPORTED_COMMANDS, key=len, reverse=True)
)


@dataclass(frozen=True)
class HeaderToken:
    name: str
    value: str
    recognized: bool
    location: SourceLocation


@dataclass(frozen=True)
class CommandToken:
    name: str
    argument: str
    recognized: bool
    supported: bool
    location: SourceLocation


@dataclass(frozen=True)
class NoteToken:
    notes: str
    closes_measure: bool
    location: SourceLocation


@dataclass(frozen=True)
class UnknownCommandToken:
    text: str
    location: SourceLocation


@dataclass(frozen=True)
class CommentToken:
    text: str
    location: SourceLocation


@dataclass(frozen=True)
class BlankToken:
    location: SourceLocation


TjaToken = HeaderToken | CommandToken | NoteToken | UnknownCommandToken | CommentToken | BlankToken


@dataclass(frozen=True)
class LexResult:
    tokens: tuple[TjaToken, ...]
    validation: ValidationResult


def _location(file: str, line: int, raw: str) -> SourceLocation:
    column = len(raw) - len(raw.lstrip()) + 1
    return SourceLocation(file=file, line=line, column=column, raw_text=raw)


def _command_token(stripped: str, location: SourceLocation) -> TjaToken:
    body = stripped[1:]
    upper = body.upper()
    for name in KNOWN_COMMANDS_LONGEST_FIRST:
        if not upper.startswith(name):
            continue
        remainder = body[len(name) :]
        if name not in ARGUMENT_COMMANDS and remainder.strip():
            continue
        return CommandToken(
            name=name,
            argument=remainder.strip(),
            recognized=True,
            supported=name in SUPPORTED_COMMANDS,
            location=location,
        )
    return UnknownCommandToken(text=stripped, location=location)


def lex_tja(text: str, source_file: str) -> LexResult:
    tokens: list[TjaToken] = []
    messages: list[DiagnosticMessage] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        location = _location(source_file, line_number, raw)
        stripped = raw.strip()
        if not stripped:
            tokens.append(BlankToken(location))
            continue
        if stripped.startswith("//"):
            tokens.append(CommentToken(stripped, location))
            continue
        if stripped.startswith("#"):
            token = _command_token(stripped, location)
            tokens.append(token)
            if isinstance(token, UnknownCommandToken):
                messages.append(
                    DiagnosticMessage(
                        "TJA_UNKNOWN_COMMAND",
                        DiagnosticSeverity.ERROR,
                        f"Unsupported TJA command: {token.text}",
                        location,
                    )
                )
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            if key and all(char.isalnum() or char == "_" for char in key):
                name = key.upper()
                tokens.append(HeaderToken(name, value, name in KNOWN_HEADERS, location))
                continue

        closes = stripped.endswith(",")
        note_part = stripped[:-1] if closes else stripped
        notes = "".join(note_part.split())
        if "," in notes:
            messages.append(
                DiagnosticMessage(
                    "TJA_INVALID_MEASURE_LINE",
                    DiagnosticSeverity.ERROR,
                    "A measure comma must be the final non-whitespace character on its line.",
                    location,
                )
            )
        tokens.append(NoteToken(notes, closes, location))
    return LexResult(tuple(tokens), ValidationResult(tuple(messages)))

