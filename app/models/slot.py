from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SongSlot:
    content_index: int
    content_id: int
    internal_id: str | None
    capacity: int | None = None
    protected: bool = True
    replacement_eligible: bool = False
    protection_reason: str | None = None
    verified: bool = False
