from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

