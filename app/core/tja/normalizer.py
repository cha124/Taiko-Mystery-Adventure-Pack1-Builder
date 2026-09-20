from __future__ import annotations

from app.core.tja.lexer import (
    BlankToken,
    CommandToken,
    CommentToken,
    HeaderToken,
    NoteToken,
    UnknownCommandToken,
)
from app.core.tja.model import TjaDocument


def normalize_tja(document: TjaDocument) -> str:
    """Canonicalize syntax only; values and note line boundaries are preserved."""
    lines: list[str] = []
    for token in document.source_tokens:
        if isinstance(token, HeaderToken):
            lines.append(f"{token.name}:{token.value}")
        elif isinstance(token, CommandToken):
            suffix = f" {token.argument}" if token.argument else ""
            lines.append(f"#{token.name}{suffix}")
        elif isinstance(token, NoteToken):
            lines.append(token.notes + ("," if token.closes_measure else ""))
        elif isinstance(token, UnknownCommandToken):
            lines.append(token.text)
        elif isinstance(token, CommentToken):
            lines.append(token.text)
        elif isinstance(token, BlankToken):
            lines.append("")
    return "\n".join(lines) + "\n"

