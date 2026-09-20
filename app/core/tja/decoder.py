from __future__ import annotations

from dataclasses import dataclass


class TjaDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedTja:
    text: str
    encoding: str


def decode_tja(raw: bytes) -> DecodedTja:
    """Decode strictly; never discard or replace undecodable filename/title text."""
    failures: list[str] = []
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return DecodedTja(raw.decode(encoding, errors="strict"), encoding)
        except UnicodeDecodeError as exc:
            failures.append(f"{encoding}: {exc}")
    raise TjaDecodeError("TJA is neither valid UTF-8 nor CP932: " + "; ".join(failures))

