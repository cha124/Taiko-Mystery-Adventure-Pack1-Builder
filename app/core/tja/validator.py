from __future__ import annotations

from app.core.tja.model import CommandSupport, TjaDocument
from app.models.validation import DiagnosticMessage, DiagnosticSeverity, ValidationResult


def validate_tja(document: TjaDocument) -> ValidationResult:
    messages: list[DiagnosticMessage] = []
    for entry in document.header.entries:
        if not entry.recognized:
            messages.append(
                DiagnosticMessage(
                    "TJA_UNKNOWN_HEADER",
                    DiagnosticSeverity.WARNING,
                    f"Header {entry.name} is preserved but its meaning is not supported.",
                    entry.location,
                )
            )

    for name in ("BPM", "TITLE", "WAVE"):
        entries = [entry for entry in document.header.entries if entry.name == name]
        if len(entries) > 1:
            messages.append(
                DiagnosticMessage(
                    "TJA_DUPLICATE_HEADER",
                    DiagnosticSeverity.ERROR,
                    f"Header {name} occurs more than once; precedence is not guessed.",
                    entries[1].location,
                )
            )
    if document.header.title is None:
        messages.append(
            DiagnosticMessage(
                "TJA_TITLE_MISSING",
                DiagnosticSeverity.WARNING,
                "TITLE header is missing.",
            )
        )
    if document.header.wave is None:
        messages.append(
            DiagnosticMessage(
                "TJA_WAVE_MISSING",
                DiagnosticSeverity.WARNING,
                "WAVE header is missing.",
            )
        )
    if not document.courses:
        messages.append(
            DiagnosticMessage(
                "TJA_NO_COURSES",
                DiagnosticSeverity.ERROR,
                "No complete TJA course was found.",
            )
        )

    for course in document.courses:
        if course.start_argument:
            messages.append(
                DiagnosticMessage(
                    "TJA_START_ARGUMENT_UNVERIFIED",
                    DiagnosticSeverity.WARNING,
                    f"#START argument {course.start_argument!r} is preserved but not interpreted.",
                    course.start_location,
                )
            )
        if course.end_location is None:
            messages.append(
                DiagnosticMessage(
                    "TJA_COURSE_NOT_ENDED",
                    DiagnosticSeverity.ERROR,
                    f"Course {course.original_name!r} has no #END.",
                    course.start_location,
                )
            )
        for measure in course.measures:
            if not measure.terminated:
                continue
            invalid_notes = sorted({char for char in measure.notes if char not in "0123456789ABCDF"})
            if invalid_notes:
                messages.append(
                    DiagnosticMessage(
                        "TJA_INVALID_NOTE_SYMBOL",
                        DiagnosticSeverity.ERROR,
                        f"Unsupported note symbols: {''.join(invalid_notes)}",
                        measure.location,
                    )
                )
            for command in measure.commands:
                if command.support is CommandSupport.RECOGNIZED_UNSUPPORTED:
                    messages.append(
                        DiagnosticMessage(
                            "TJA_COMMAND_RECOGNIZED_UNSUPPORTED",
                            DiagnosticSeverity.WARNING,
                            f"#{command.name} is preserved but its game semantics are not validated.",
                            command.location,
                        )
                    )
                if command.name == "DELAY" and getattr(command.value, "is_signed", lambda: False)():
                    messages.append(
                        DiagnosticMessage(
                            "TJA_NEGATIVE_DELAY_UNVERIFIED",
                            DiagnosticSeverity.WARNING,
                            "Negative DELAY is parsed exactly, but target-game behavior is not certified.",
                            command.location,
                        )
                    )
    return ValidationResult(tuple(messages))
