from __future__ import annotations

from dataclasses import dataclass

from app.models.slot import SongSlot


@dataclass(frozen=True)
class SongReference:
    kind: str
    key: str
    target_path: str | None
    required: bool = True


@dataclass(frozen=True)
class CatalogSong:
    display_title: str | None
    slot: SongSlot
    reference_key: str | None
    references: tuple[SongReference, ...] = ()

