from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SongSlot:
    content_index: int
    content_id: int
    internal_id: str | None
    capacity: int | None = None
    protected: bool = True
    verified: bool = False

