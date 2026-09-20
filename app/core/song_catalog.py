from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.song import CatalogSong
from app.models.slot import SongSlot


def profiles_root() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles"


def load_profile(name: str) -> dict[str, Any]:
    root = (profiles_root() / name).resolve()
    if root.parent != profiles_root().resolve():
        raise ValueError(f"invalid profile name: {name!r}")
    profile_path = root / "profile.json"
    with profile_path.open("r", encoding="utf-8") as stream:
        profile = json.load(stream)
    if profile.get("schema_version") != 1:
        raise ValueError(f"unsupported profile schema: {profile.get('schema_version')!r}")
    return profile


@dataclass(frozen=True)
class SongCatalog:
    profile_id: str
    songs: tuple[CatalogSong, ...]
    verified: bool

    @property
    def by_identity(self) -> dict[tuple[int, int, str | None], CatalogSong]:
        return {
            (song.slot.content_index, song.slot.content_id, song.slot.internal_id): song
            for song in self.songs
        }


def load_song_catalog(name: str) -> SongCatalog:
    profile = load_profile(name)
    slots_path = profiles_root() / name / "slots.json"
    with slots_path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported slot catalog schema")

    songs: list[CatalogSong] = []
    for raw in payload.get("slots", []):
        required = {"content_index", "content_id"}
        if not required.issubset(raw):
            raise ValueError("slot entry is missing a stable content identity")
        content_id = raw["content_id"]
        if isinstance(content_id, str):
            content_id = int(content_id, 0)
        slot = SongSlot(
            content_index=int(raw["content_index"]),
            content_id=int(content_id),
            internal_id=raw.get("internal_id"),
            capacity=raw.get("capacity"),
            protected=bool(raw.get("protected", True)),
            verified=payload.get("status") == "verified",
        )
        songs.append(
            CatalogSong(
                display_title=raw.get("display_title"),
                slot=slot,
                reference_key=raw.get("reference_key"),
            )
        )
    return SongCatalog(
        profile_id=profile["id"],
        songs=tuple(songs),
        verified=payload.get("status") == "verified",
    )


def profile_diagnostic(profile: dict[str, Any], title_id: int) -> dict[str, Any]:
    title_hex = f"{title_id:016x}"
    allowed = {str(value).lower().removeprefix("0x") for value in profile["allowed_title_ids"]}
    title_match: bool | None = title_hex in allowed if allowed else None
    return {
        "id": profile["id"],
        "display_name": profile["display_name"],
        "certification": profile["certification"],
        "title_id_match": title_match,
        "slot_catalog_status": profile["slot_catalog_status"],
        "songinfo_schema_status": profile["songinfo_schema_status"],
    }
