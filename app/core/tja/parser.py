from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from app.core.tja.lexer import (
    BlankToken,
    CommandToken,
    CommentToken,
    HeaderToken,
    NoteToken,
    TjaToken,
    UnknownCommandToken,
)
from app.core.tja.model import (
    CommandSupport,
    CourseKind,
    TjaCommand,
    TjaCourse,
    TjaDocument,
    TjaHeader,
    TjaHeaderEntry,
    TjaMeasure,
)
from app.models.validation import (
    DiagnosticMessage,
    DiagnosticSeverity,
    SourceLocation,
    ValidationResult,
)

DECIMAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
FRACTION_PATTERN = re.compile(r"^([+]?[0-9]+)\s*/\s*([+]?[0-9]+)$")

COURSE_ALIASES = {
    "0": CourseKind.EASY,
    "easy": CourseKind.EASY,
    "kantan": CourseKind.EASY,
    "1": CourseKind.NORMAL,
    "normal": CourseKind.NORMAL,
    "futsuu": CourseKind.NORMAL,
    "2": CourseKind.HARD,
    "hard": CourseKind.HARD,
    "muzukashii": CourseKind.HARD,
    "3": CourseKind.ONI,
    "oni": CourseKind.ONI,
    "4": CourseKind.URA,
    "edit": CourseKind.URA,
    "ura": CourseKind.URA,
}


@dataclass(frozen=True)
class ParseResult:
    document: TjaDocument
    validation: ValidationResult


@dataclass
class _CourseBuilder:
    kind: CourseKind
    original_name: str
    level: Decimal | None
    balloon: tuple[int, ...]
    start_argument: str
    start_location: SourceLocation
    measures: list[TjaMeasure]
    end_location: SourceLocation | None = None


def _message(
    code: str, message: str, location: SourceLocation, severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
) -> DiagnosticMessage:
    return DiagnosticMessage(code, severity, message, location)


def _decimal(argument: str) -> Decimal | None:
    if not DECIMAL_PATTERN.fullmatch(argument):
        return None
    try:
        return Decimal(argument)
    except InvalidOperation:
        return None


def _fraction(argument: str) -> Fraction | None:
    match = FRACTION_PATTERN.fullmatch(argument)
    if match is None:
        return None
    numerator, denominator = int(match.group(1)), int(match.group(2))
    if numerator <= 0 or denominator <= 0:
        return None
    return Fraction(numerator, denominator)


def _command(token: CommandToken, messages: list[DiagnosticMessage]) -> TjaCommand:
    support = (
        CommandSupport.SUPPORTED if token.supported else CommandSupport.RECOGNIZED_UNSUPPORTED
    )
    value: Decimal | Fraction | str | None = token.argument or None
    if token.name in {"BPMCHANGE", "SCROLL", "DELAY"}:
        value = _decimal(token.argument)
        if value is None:
            messages.append(
                _message(
                    f"TJA_INVALID_{token.name}",
                    f'Invalid {token.name} value "{token.argument}"',
                    token.location,
                )
            )
    elif token.name == "MEASURE":
        value = _fraction(token.argument)
        if value is None:
            messages.append(
                _message(
                    "TJA_INVALID_MEASURE",
                    f'Invalid MEASURE value "{token.argument}"',
                    token.location,
                )
            )
    elif token.name in {"END", "BRANCHEND", "GOGOSTART", "GOGOEND", "BARLINEON", "BARLINEOFF", "N", "E", "M"}:
        value = None
    return TjaCommand(token.name, token.argument, value, support, token.location)


def parse_tja(
    tokens: tuple[TjaToken, ...], source_file: str, encoding: str
) -> ParseResult:
    messages: list[DiagnosticMessage] = []
    header_entries: list[TjaHeaderEntry] = []
    courses: list[TjaCourse] = []
    current: _CourseBuilder | None = None
    pending_course_name: str | None = None
    pending_level: Decimal | None = None
    pending_balloon: tuple[int, ...] = ()

    global_bpm: Decimal | None = None
    bpm = Decimal(0)
    signature = Fraction(4, 4)
    scroll = Decimal(1)
    cursor = Decimal(0)
    note_parts: list[str] = []
    measure_commands: list[TjaCommand] = []
    measure_location: SourceLocation | None = None

    def finalize_measure(terminated: bool) -> None:
        nonlocal cursor, note_parts, measure_commands, measure_location
        if current is None or measure_location is None:
            return
        if bpm <= 0:
            duration = Decimal(0)
        else:
            beats = Decimal(signature.numerator * 4) / Decimal(signature.denominator)
            duration = Decimal(60) * beats / bpm
        current.measures.append(
            TjaMeasure(
                notes="".join(note_parts),
                commands=tuple(measure_commands),
                time_signature=signature,
                bpm=bpm,
                scroll=scroll,
                start_time_seconds=cursor,
                duration_seconds=duration,
                terminated=terminated,
                location=measure_location,
            )
        )
        cursor += duration
        note_parts = []
        measure_commands = []
        measure_location = None

    def finish_course(end_location: SourceLocation | None) -> None:
        nonlocal current, note_parts, measure_commands, measure_location
        if current is None:
            return
        if note_parts or measure_location is not None:
            messages.append(
                _message(
                    "TJA_UNTERMINATED_MEASURE",
                    "Measure is not terminated by a comma before #END.",
                    measure_location or current.start_location,
                )
            )
            finalize_measure(False)
        current.end_location = end_location
        courses.append(
            TjaCourse(
                current.kind,
                current.original_name,
                current.level,
                current.balloon,
                current.start_argument,
                tuple(current.measures),
                current.start_location,
                current.end_location,
            )
        )
        current = None
        note_parts = []
        measure_commands = []
        measure_location = None

    for token in tokens:
        if isinstance(token, HeaderToken):
            entry = TjaHeaderEntry(token.name, token.value, token.recognized, token.location)
            header_entries.append(entry)
            if current is not None:
                messages.append(
                    _message(
                        "TJA_HEADER_INSIDE_CHART",
                        f"Header {token.name} is not allowed between #START and #END.",
                        token.location,
                    )
                )
                continue
            if token.name == "BPM" and global_bpm is None:
                global_bpm = _decimal(token.value.strip())
            elif token.name == "COURSE":
                pending_course_name = token.value.strip()
                pending_level = None
                pending_balloon = ()
            elif token.name == "LEVEL":
                pending_level = _decimal(token.value.strip())
                if pending_level is None:
                    messages.append(_message("TJA_INVALID_LEVEL", f'Invalid LEVEL value "{token.value}"', token.location))
            elif token.name == "BALLOON":
                try:
                    values = tuple(int(item.strip()) for item in token.value.split(",") if item.strip())
                    if any(value <= 0 for value in values):
                        raise ValueError
                    pending_balloon = values
                except ValueError:
                    messages.append(_message("TJA_INVALID_BALLOON", f'Invalid BALLOON value "{token.value}"', token.location))
            continue

        if isinstance(token, (BlankToken, CommentToken, UnknownCommandToken)):
            continue
        if isinstance(token, CommandToken):
            if token.name == "START":
                if current is not None:
                    messages.append(_message("TJA_NESTED_START", "#START encountered before the previous course ended.", token.location))
                    continue
                original = pending_course_name or ""
                kind = COURSE_ALIASES.get(original.casefold(), CourseKind.UNKNOWN)
                if not original:
                    messages.append(_message("TJA_MISSING_COURSE", "COURSE header is required before #START.", token.location))
                elif kind is CourseKind.UNKNOWN:
                    messages.append(_message("TJA_UNKNOWN_COURSE", f'Unknown COURSE value "{original}"', token.location))
                current = _CourseBuilder(
                    kind,
                    original,
                    pending_level,
                    pending_balloon,
                    token.argument,
                    token.location,
                    [],
                )
                bpm = global_bpm or Decimal(0)
                signature = Fraction(4, 4)
                scroll = Decimal(1)
                cursor = Decimal(0)
                continue
            if token.name == "END":
                if current is None:
                    messages.append(_message("TJA_END_WITHOUT_START", "#END encountered without #START.", token.location))
                else:
                    finish_course(token.location)
                continue
            command = _command(token, messages)
            if current is None:
                messages.append(_message("TJA_COMMAND_OUTSIDE_CHART", f"#{token.name} is outside #START/#END.", token.location))
                continue
            if note_parts and token.name in {"BPMCHANGE", "SCROLL", "MEASURE", "DELAY"}:
                messages.append(
                    _message(
                        "TJA_TIMING_COMMAND_MID_MEASURE",
                        f"#{token.name} after note data has started is not timed by this safe parser.",
                        token.location,
                    )
                )
            if measure_location is None:
                measure_location = token.location
            measure_commands.append(command)
            if token.name == "BPMCHANGE" and isinstance(command.value, Decimal):
                if command.value <= 0:
                    messages.append(_message("TJA_NONPOSITIVE_BPM", "BPMCHANGE must be greater than zero.", token.location))
                else:
                    bpm = command.value
            elif token.name == "MEASURE" and isinstance(command.value, Fraction):
                signature = command.value
            elif token.name == "SCROLL" and isinstance(command.value, Decimal):
                scroll = command.value
            elif token.name == "DELAY" and isinstance(command.value, Decimal):
                cursor += command.value
            continue

        if isinstance(token, NoteToken):
            if current is None:
                if token.notes or token.closes_measure:
                    messages.append(_message("TJA_NOTES_OUTSIDE_CHART", "Note data is outside #START/#END.", token.location))
                continue
            if measure_location is None:
                measure_location = token.location
            note_parts.append(token.notes)
            if token.closes_measure:
                finalize_measure(True)

    if current is not None:
        messages.append(_message("TJA_MISSING_END", "Course reaches end of file without #END.", current.start_location))
        finish_course(None)

    if global_bpm is None:
        bpm_entries = [entry for entry in header_entries if entry.name == "BPM"]
        location = bpm_entries[0].location if bpm_entries else SourceLocation(source_file, 1, 1, "")
        messages.append(_message("TJA_INVALID_OR_MISSING_BPM", "A valid BPM header is required.", location))
    elif global_bpm <= 0:
        entry = next(entry for entry in header_entries if entry.name == "BPM")
        messages.append(_message("TJA_NONPOSITIVE_BPM", "BPM must be greater than zero.", entry.location))

    document = TjaDocument(
        source_file=source_file,
        encoding=encoding,
        header=TjaHeader(tuple(header_entries)),
        courses=tuple(courses),
        source_tokens=tokens,
    )
    return ParseResult(document, ValidationResult(tuple(messages)))
