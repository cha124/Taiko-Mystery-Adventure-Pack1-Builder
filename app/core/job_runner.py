from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.core.cia_reader import read_cia
from app.core.song_catalog import load_profile, load_song_catalog, profile_diagnostic
from app.core.validator import validate_cia
from app.models.diagnostic import DiagnosticReport


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run_diagnostic(
    source: Path,
    *,
    profile_name: str = "taiko3ds3_jp_pack1",
    output: Path | None = None,
) -> DiagnosticReport:
    source = source.resolve()
    profile = load_profile(profile_name)
    catalog = load_song_catalog(profile_name)
    image = read_cia(source)
    report = DiagnosticReport(
        source=source,
        source_sha256=_file_sha256(source),
        source_size=source.stat().st_size,
        cia=image.to_dict(),
        profile=profile_diagnostic(profile, image.title_id),
        song_catalog={
            "profile_id": catalog.profile_id,
            "verified": catalog.verified,
            "song_count": len(catalog.songs),
            "songs": [
                {
                    "display_title": song.display_title,
                    "content_index": song.slot.content_index,
                    "content_id": f"{song.slot.content_id:08x}",
                    "internal_id": song.slot.internal_id,
                    "reference_key": song.reference_key,
                }
                for song in catalog.songs
            ],
        },
        issues=validate_cia(image, profile),
    )
    if output is not None:
        _write_json_atomic(output, report.to_dict())
    return report
