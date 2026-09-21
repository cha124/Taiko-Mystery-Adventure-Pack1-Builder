from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.audio.naac import NAACParseError, inspect_naac
from app.core.audio.header_forensics import analyze_header_forensics
from app.core.audio.statistics import header_analysis, role_statistics
from app.core.audio.validator import validate_collection
from app.core.cia_reader import CiaImage, read_cia_snapshot
from app.core.pack1_analyzer import (
    analyze_pack1,
    classify_baseline_anomalies,
    fingerprint_pack1,
)
from app.core.song_catalog import load_profile
from app.core.source_snapshot import SourceSnapshot
from app.models.audio import AudioFileAnalysis, AudioIssue, NAACInspection
from app.models.fingerprint import ReadCompatibility
from app.models.validation import ValidationIssue


@dataclass(frozen=True)
class AudioScanReport:
    source: Path
    source_size: int
    source_sha256: str
    compatibility: dict[str, Any]
    song_count: int
    records: tuple[AudioFileAnalysis, ...]
    collection_issues: tuple[AudioIssue, ...]
    header: dict[str, Any]
    include_source_path: bool = False
    schema_version: int = 1

    @property
    def all_issues(self) -> tuple[AudioIssue, ...]:
        return self.collection_issues + tuple(issue for record in self.records for issue in record.issues)

    @property
    def status(self) -> str:
        if any(issue.severity == "ERROR" for issue in self.all_issues):
            return "FAIL"
        if self.all_issues:
            return "WARNING"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        source: dict[str, Any] = {
            "filename": self.source.name,
            "size": self.source_size,
            "sha256": self.source_sha256,
        }
        if self.include_source_path:
            source["absolute_path"] = str(self.source.resolve())
        successful = [record for record in self.records if record.parse_status == "SUCCESS"]
        main = role_statistics(list(self.records), "main")
        preview = role_statistics(list(self.records), "preview")
        unique = {
            (record.content_index, record.romfs_path.casefold(), record.naac_sha256)
            for record in self.records
        }
        distinct_references = {
            (record.content_index, record.romfs_path.casefold()) for record in self.records
        }
        distinct_content_hashes = {
            record.naac_sha256 for record in self.records if record.naac_sha256
        }
        summary = {
            "song_count": self.song_count,
            "main_references": sum(record.role == "main" for record in self.records),
            "preview_references": sum(record.role == "preview" for record in self.records),
            "unique_naac_count": len(unique),
            "distinct_reference_count": len(distinct_references),
            "distinct_content_hash_count": len(distinct_content_hashes),
            "success_count": len(successful),
            "failure_count": len(self.records) - len(successful),
            "warning_count": sum(issue.severity == "WARNING" for issue in self.all_issues),
            "error_count": sum(issue.severity == "ERROR" for issue in self.all_issues),
            "payload_offset_distribution": _distribution(
                record.inspection.payload_offset
                for record in successful
                if record.inspection
            ),
            "header_size_distribution": _distribution(
                record.inspection.header_size
                for record in successful
                if record.inspection
            ),
            "main": main,
            "preview": preview,
        }
        return {
            "schema_version": self.schema_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": self.status,
            "read_only": True,
            "encoding_approved": False,
            "device_tested": False,
            "source": source,
            "compatibility": self.compatibility,
            "summary": summary,
            "files": [record.to_dict() for record in self.records],
            "header_analysis": self.header,
            "issues": [issue.to_dict() for issue in self.all_issues],
            "optional_validation": {"external_decoder": "NOT_RUN"},
        }


def _distribution(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _romfs_entries(image: CiaImage, content_index: int) -> dict[str, dict[str, Any]]:
    content = next((item for item in image.contents if item.index == content_index), None)
    if content is None or not content.ncch:
        return {}
    romfs = content.ncch.get("romfs", {})
    return {
        entry["path"].casefold(): entry
        for entry in romfs.get("files", [])
        if isinstance(entry, dict) and "path" in entry
    }


def _pack1_issue_to_audio_issue(issue: ValidationIssue) -> AudioIssue:
    """Preserve Pack1 severity while moving its issue into the audio report."""

    known_baseline = issue.classification == "KNOWN_BASELINE_ANOMALY"
    return AudioIssue(
        "PACK1_REFERENCE_ANOMALY" if known_baseline else "PACK1_REFERENCE_ERROR",
        issue.severity if issue.severity in {"WARNING", "ERROR"} else "ERROR",
        f"{issue.code}: {issue.message}",
        details=dict(issue.details),
        source_code=issue.code,
        classification=issue.classification,
    )


def _verified_audio_expectations(
    profile: dict[str, Any], source_sha256: str
) -> tuple[int | None, dict[str, int]]:
    """Return slot observations and verified-source-only reference observations."""

    observations = profile.get("verified_observations", {})
    expected_slots = observations.get("song_slot_count")
    if source_sha256 not in profile.get("verified_sha256", []):
        return (int(expected_slots) if expected_slots is not None else None), {}
    expected_references: dict[str, int] = {}
    for role in ("main", "preview"):
        value = observations.get(f"{role}_references")
        if value is None:
            value = observations.get(f"{role}_reference_count")
        if value is not None:
            expected_references[role] = int(value)
    return (int(expected_slots) if expected_slots is not None else None), expected_references


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=resolved.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, resolved)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run_audio_scan(
    source: Path,
    *,
    output: Path | None = None,
    include_source_path: bool = False,
    profile_name: str = "taiko3ds3_jp_pack1",
) -> AudioScanReport:
    source = source.resolve()
    if output is not None and output.resolve() == source:
        raise ValueError("audio report output must not overwrite the source CIA")
    snapshot = SourceSnapshot.from_path(source)
    image = read_cia_snapshot(snapshot)
    profile = load_profile(profile_name)
    fingerprint = fingerprint_pack1(image, snapshot.sha256, profile)
    if fingerprint.read_compatibility not in {
        ReadCompatibility.SUPPORTED,
        ReadCompatibility.COMPATIBLE_BUT_UNVERIFIED,
    }:
        raise ValueError(
            f"audio scan requires a structurally compatible Pack1: {fingerprint.read_compatibility.value}"
        )
    pack1 = analyze_pack1(image)
    records: list[AudioFileAnalysis] = []
    cached: dict[tuple[int, int, str], NAACInspection] = {}
    for slot in pack1.slots:
        entries = _romfs_entries(image, slot.content_index)
        for role, path in (("main", slot.main_audio), ("preview", slot.preview_audio)):
            entry = entries.get(path.casefold())
            if entry is None:
                records.append(
                    AudioFileAnalysis(
                        content_index=slot.content_index,
                        internal_song_id=slot.internal_id,
                        role=role,
                        romfs_path=path,
                        naac_size=0,
                        naac_sha256="",
                        parse_status="UNRESOLVED",
                        issues=(
                            AudioIssue(
                                "NAAC_REFERENCE_NOT_FOUND",
                                "ERROR",
                                "Referenced NAAC does not exist in the slot RomFS.",
                            ),
                        ),
                    )
                )
                continue
            offset, size = int(entry["absolute_offset"]), int(entry["size"])
            view = snapshot.view(offset, size)
            digest = hashlib.sha256(view).hexdigest()
            key = (offset, size, digest)
            try:
                inspection = cached.get(key)
                if inspection is None:
                    inspection = inspect_naac(view)
                    cached[key] = inspection
                records.append(
                    AudioFileAnalysis(
                        content_index=slot.content_index,
                        internal_song_id=slot.internal_id,
                        role=role,
                        romfs_path=path,
                        naac_size=size,
                        naac_sha256=digest,
                        parse_status="SUCCESS",
                        inspection=inspection,
                        issues=inspection.issues,
                    )
                )
            except NAACParseError as exc:
                records.append(
                    AudioFileAnalysis(
                        content_index=slot.content_index,
                        internal_song_id=slot.internal_id,
                        role=role,
                        romfs_path=path,
                        naac_size=size,
                        naac_sha256=digest,
                        parse_status="UNRESOLVED",
                        issues=(AudioIssue(exc.code, "ERROR", str(exc), exc.offset),),
                    )
                )
    collection_issues = list(validate_collection(records))
    classified_pack1_issues = classify_baseline_anomalies(pack1.issues, profile)
    collection_issues.extend(_pack1_issue_to_audio_issue(issue) for issue in classified_pack1_issues)

    expected_slots, expected_references = _verified_audio_expectations(
        profile, snapshot.sha256
    )
    if expected_slots is not None and len(pack1.slots) != expected_slots:
        collection_issues.append(
            AudioIssue(
                "AUDIO_PACK1_SLOT_COUNT_MISMATCH",
                "ERROR",
                f"Detected {len(pack1.slots)} Pack1 song slots; expected {expected_slots}.",
                details={"expected": expected_slots, "detected": len(pack1.slots)},
            )
        )
    if expected_references:
        detected_references = {
            "main": sum(record.role == "main" for record in records),
            "preview": sum(record.role == "preview" for record in records),
        }
        if any(
            detected_references[role] != expected
            for role, expected in expected_references.items()
        ):
            collection_issues.append(
                AudioIssue(
                    "AUDIO_REFERENCE_COUNT_MISMATCH",
                    "ERROR",
                    "Verified Pack1 audio reference counts do not match profile observations.",
                    details={
                        "expected": dict(expected_references),
                        "detected": detected_references,
                    },
                )
            )
    report = AudioScanReport(
        source=source,
        source_size=snapshot.size,
        source_sha256=snapshot.sha256,
        compatibility=fingerprint.to_dict(),
        song_count=len(pack1.slots),
        records=tuple(records),
        collection_issues=tuple(collection_issues),
        header=header_analysis(records),
        include_source_path=include_source_path,
    )
    if output is not None:
        _write_json_atomic(output, report.to_dict())
    return report


def run_audio_forensics(
    source: Path,
    *,
    output: Path | None = None,
    include_source_path: bool = False,
    profile_name: str = "taiko3ds3_jp_pack1",
) -> dict[str, Any]:
    """Run Audio Scan once, then analyze its successful NAAC records in memory."""

    report = run_audio_scan(
        source,
        include_source_path=include_source_path,
        profile_name=profile_name,
    )
    payload = analyze_header_forensics(
        report.records,
        source=report.source,
        source_size=report.source_size,
        source_sha256=report.source_sha256,
        audio_report=report,
    )
    if include_source_path:
        payload["source"]["absolute_path"] = str(report.source.resolve())
    if output is not None:
        _write_json_atomic(output, payload)
    return payload
