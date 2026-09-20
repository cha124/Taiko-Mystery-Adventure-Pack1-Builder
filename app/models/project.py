from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosticProject:
    source_cia: Path
    profile_id: str
    source_sha256: str | None = None

