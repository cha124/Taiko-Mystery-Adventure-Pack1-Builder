from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.core.binary import BinaryFormatError, UnsupportedFormatError
from app.core.cia_reader import read_cia_snapshot
from app.core.pack1_analyzer import (
    analyze_pack1,
    build_reference_validation,
    classify_baseline_anomalies,
    fingerprint_pack1,
)
from app.core.song_catalog import load_profile, load_song_catalog, profile_diagnostic
from app.core.source_snapshot import SourceSnapshot
from app.core.validator import validate_cia
from app.models.diagnostic import DiagnosticReport
from app.models.fingerprint import Pack1Fingerprint, ReadCompatibility
from app.models.validation import ValidationIssue

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
    include_source_path: bool = False,
) -> DiagnosticReport:
    source = source.resolve()
    profile = load_profile(profile_name)
    catalog = load_song_catalog(profile_name)
    snapshot = SourceSnapshot.from_path(source)
    try:
        image = read_cia_snapshot(snapshot)
    except (UnsupportedFormatError, BinaryFormatError) as exc:
        read_status = (
            ReadCompatibility.UNSUPPORTED
            if isinstance(exc, UnsupportedFormatError)
            else ReadCompatibility.CORRUPT
        )
        code = "CIA_UNSUPPORTED_FORMAT" if read_status is ReadCompatibility.UNSUPPORTED else "CIA_CORRUPT"
        report = DiagnosticReport(
            source=source,
            source_sha256=snapshot.sha256,
            source_size=snapshot.size,
            cia={"parse_status": read_status.value.lower(), "parse_error": str(exc)},
            profile=profile_diagnostic(profile, None),
            song_catalog={"profile_id": catalog.profile_id, "verified": False, "song_count": 0, "songs": []},
            compatibility=Pack1Fingerprint(
                read_status, (), ("container_parse",)
            ).to_dict(),
            reference_validation={"status": "NOT_RUN", "checked_song_slots": 0, "errors": [], "warnings": []},
            issues=[ValidationIssue(code, "ERROR", str(exc), "source")],
            include_source_path=include_source_path,
        )
        if output is not None:
            _write_json_atomic(output, report.to_dict())
        return report

    analysis = analyze_pack1(image)
    classified_analysis_issues = classify_baseline_anomalies(analysis.issues, profile)
    fingerprint = fingerprint_pack1(image, snapshot.sha256, profile)
    issues = validate_cia(image, profile)
    issues.extend(classified_analysis_issues)
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
    catalog_by_index = {song.slot.content_index: song.slot for song in catalog.songs}
    detected_songs = []
    for slot in analysis.slots:
        payload = slot.to_dict()
        policy = catalog_by_index.get(slot.content_index)
        if policy is not None:
            payload.update(
                {
                    "protected": policy.protected,
                    "replacement_eligible": policy.replacement_eligible,
                    "protection_reason": policy.protection_reason,
                }
            )
        detected_songs.append(payload)
    report = DiagnosticReport(
        source=source,
        source_sha256=snapshot.sha256,
        source_size=snapshot.size,
        cia=image.to_dict(),
        profile=profile_diagnostic(profile, image.title_id),
        song_catalog={
            "profile_id": catalog.profile_id,
            "verified": catalog.verified
            and not any(issue.severity == "ERROR" for issue in classified_analysis_issues),
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
        reference_validation=build_reference_validation(
            analysis.slots, classified_analysis_issues
        ),
        issues=issues,
        include_source_path=include_source_path,
    )
    if output is not None:
        _write_json_atomic(output, report.to_dict())
    return report
