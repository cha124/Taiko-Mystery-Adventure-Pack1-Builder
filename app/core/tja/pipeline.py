from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.tja.decoder import decode_tja
from app.core.tja.lexer import lex_tja
from app.core.tja.model import TjaDocument
from app.core.tja.normalizer import normalize_tja
from app.core.tja.parser import parse_tja
from app.core.tja.validator import validate_tja
from app.models.validation import ValidationResult


@dataclass(frozen=True)
class TjaCheckReport:
    document: TjaDocument
    validation: ValidationResult
    canonical_text: str


def check_tja_bytes(raw: bytes, source_file: str = "<memory>") -> TjaCheckReport:
    decoded = decode_tja(raw)
    lexed = lex_tja(decoded.text, source_file)
    parsed = parse_tja(lexed.tokens, source_file, decoded.encoding)
    semantic = validate_tja(parsed.document)
    combined = lexed.validation.extend(parsed.validation, semantic)
    return TjaCheckReport(parsed.document, combined, normalize_tja(parsed.document))


def check_tja_file(path: Path) -> TjaCheckReport:
    path = path.resolve()
    return check_tja_bytes(path.read_bytes(), str(path))

