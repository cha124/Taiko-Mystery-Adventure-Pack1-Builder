from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.core.cia_reader import read_cia
from app.core.pack1_analyzer import analyze_pack1, fingerprint_pack1
from app.core.song_catalog import load_profile, load_song_catalog, profile_diagnostic
from app.core.validator import validate_cia
from app.models.diagnostic import DiagnosticReport
from app.models.validation import ValidationIssue


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
    source_sha256 = _file_sha256(source)
    analysis = analyze_pack1(image)
    fingerprint = fingerprint_pack1(image, source_sha256, profile)
    issues = validate_cia(image, profile)
    issues.extend(analysis.issues)
    if fingerprint.compatibility.value == "UNSUPPORTED":
        issues.append(
            ValidationIssue(
                "PROFILE_FINGERPRINT_MISMATCH",
                "ERROR",
                "CIA structure does not match the selected Pack1 profile.",
                "profile.fingerprint",
                {"failed_checks": list(fingerprint.failed_checks)},
            )
        )
    detected_songs = [slot.to_dict() for slot in analysis.slots]
    report = DiagnosticReport(
        source=source,
        source_sha256=source_sha256,
        source_size=source.stat().st_size,
        cia=image.to_dict(),
        profile=profile_diagnostic(profile, image.title_id),
        song_catalog={
            "profile_id": catalog.profile_id,
            "verified": catalog.verified and not analysis.issues,
            "song_count": len(detected_songs) if detected_songs else len(catalog.songs),
            "songs": detected_songs or [
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
        compatibility=fingerprint.to_dict(),
        reference_validation=analysis.reference_validation,
        issues=issues,
    )
    if output is not None:
        _write_json_atomic(output, report.to_dict())
    return report
