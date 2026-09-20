from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.tja.decoder import decode_tja
from app.core.tja.lexer import CommandToken, lex_tja
from app.core.tja.model import ConversionEligibility, TjaDocument
from app.core.tja.normalizer import normalize_tja
from app.core.tja.parser import parse_tja
from app.core.tja.validator import validate_tja
from app.models.validation import ValidationResult


@dataclass(frozen=True)
class TjaCheckReport:
    document: TjaDocument
    validation: ValidationResult
    canonical_text: str
    conversion_blockers: tuple[str, ...]

    @property
    def syntax_valid(self) -> bool:
        return self.validation.is_valid

    @property
    def conversion_eligible(self) -> bool:
        return self.syntax_valid and not self.conversion_blockers

    @property
    def conversion_eligibility(self) -> ConversionEligibility:
        return (
            ConversionEligibility.ELIGIBLE
            if self.conversion_eligible
            else ConversionEligibility.BLOCKED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "syntax_valid": self.syntax_valid,
            "conversion_eligible": self.conversion_eligible,
            "conversion_eligibility": self.conversion_eligibility.value,
            "conversion_blockers": list(self.conversion_blockers),
            "messages": [message.to_dict() for message in self.validation.messages],
        }


def _conversion_blockers(document: TjaDocument, validation: ValidationResult) -> tuple[str, ...]:
    blockers = [message.code for message in validation.errors]
    for token in document.source_tokens:
        if not isinstance(token, CommandToken) or token.supported:
            continue
        if token.name in {"BRANCHSTART", "BRANCHEND", "N", "E", "M"}:
            blockers.append("TJA_BRANCH_SEMANTICS_UNSUPPORTED")
        elif token.name in {"GOGOSTART", "GOGOEND"}:
            blockers.append("TJA_GOGO_SEMANTICS_UNSUPPORTED")
        elif token.name in {"BARLINEON", "BARLINEOFF"}:
            blockers.append("TJA_BARLINE_SEMANTICS_UNSUPPORTED")
        else:
            blockers.append(f"TJA_{token.name}_SEMANTICS_UNSUPPORTED")
    for course in document.courses:
        if course.start_argument:
            blockers.append("TJA_START_ARGUMENT_UNVERIFIED")
        for measure in course.measures:
            for command in measure.commands:
                if (
                    command.name == "DELAY"
                    and getattr(command.value, "is_signed", lambda: False)()
                ):
                    blockers.append("TJA_NEGATIVE_DELAY_UNVERIFIED")
    specialized_warnings = {
        "TJA_COMMAND_RECOGNIZED_UNSUPPORTED",
        "TJA_START_ARGUMENT_UNVERIFIED",
        "TJA_NEGATIVE_DELAY_UNVERIFIED",
    }
    blockers.extend(
        message.code
        for message in validation.warnings
        if message.code not in specialized_warnings
    )
    return tuple(dict.fromkeys(blockers))


def check_tja_bytes(raw: bytes, source_file: str = "<memory>") -> TjaCheckReport:
    decoded = decode_tja(raw)
    lexed = lex_tja(decoded.text, source_file)
    parsed = parse_tja(lexed.tokens, source_file, decoded.encoding)
    semantic = validate_tja(parsed.document)
    combined = lexed.validation.extend(parsed.validation, semantic)
    return TjaCheckReport(
        parsed.document,
        combined,
        normalize_tja(parsed.document),
        _conversion_blockers(parsed.document, combined),
    )


def check_tja_file(path: Path) -> TjaCheckReport:
    path = path.resolve()
    return check_tja_bytes(path.read_bytes(), str(path))
