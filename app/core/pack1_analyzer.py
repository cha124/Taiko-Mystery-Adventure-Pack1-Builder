from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.binary import BinaryFormatError
from app.core.cia_reader import CiaImage
from app.core.songinfo.parser import parse_pack1_musicinfo, parse_pack1_songinfo
from app.models.fingerprint import Compatibility, Pack1Fingerprint
from app.models.validation import ValidationIssue

SONGINFO_PATH = "/_data/system/SongInfo.dat"
MUSICINFO_PATH = "/_data/system/MusicInfo.dat"
CHART_PATTERN = re.compile(
    r"^/_data/fumen/(?P<key>[^/]+)/solo/(?P<file>[^/]+)_(?P<course>[enhmx])\.bin$",
    re.IGNORECASE,
)
AUDIO_PATTERN = re.compile(r"^/_data/sound/song/(?P<name>[^/]+)\.naac$", re.IGNORECASE)
COURSE_NAMES = {"e": "easy", "n": "normal", "h": "hard", "m": "oni", "x": "ura"}


@dataclass(frozen=True)
class Pack1SongSlot:
    content_index: int
    content_id: int
    capacity: int
    internal_id: str
    record_key: str
    display_title: str
    music_info_key: str
    main_audio: str
    preview_audio: str
    charts: dict[str, str]
    songinfo: str
    musicinfo: str
    title_resources: tuple[str, ...]
    unknown_songinfo_words: tuple[int, ...]
    unknown_musicinfo_words: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_index": self.content_index,
            "content_id": f"{self.content_id:08x}",
            "capacity": self.capacity,
            "internal_id": self.internal_id,
            "record_key": self.record_key,
            "display_title": self.display_title,
            "music_info_key": self.music_info_key,
            "main_audio": self.main_audio,
            "preview_audio": self.preview_audio,
            "charts": dict(sorted(self.charts.items())),
            "songinfo": self.songinfo,
            "musicinfo": self.musicinfo,
            "title_resources": list(self.title_resources),
            "unknown_songinfo_words": list(self.unknown_songinfo_words),
            "unknown_musicinfo_words": list(self.unknown_musicinfo_words),
        }


@dataclass(frozen=True)
class Pack1Analysis:
    slots: tuple[Pack1SongSlot, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def reference_validation(self) -> dict[str, Any]:
        errors = [issue.to_dict() for issue in self.issues if issue.severity == "ERROR"]
        warnings = [issue.to_dict() for issue in self.issues if issue.severity == "WARNING"]
        return {
            "status": "PASS" if not errors else "FAIL",
            "checked_song_slots": len(self.slots),
            "errors": errors,
            "warnings": warnings,
        }


def _read_exact(path: Path, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0:
        raise BinaryFormatError("negative file range")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(size)
    if len(data) != size:
        raise BinaryFormatError(
            f"short read at 0x{offset:X}: expected {size}, received {len(data)}"
        )
    return data


def _romfs_files(content: Any) -> dict[str, dict[str, Any]]:
    if not content.ncch:
        return {}
    romfs = content.ncch.get("romfs", {})
    entries = romfs.get("files", []) if isinstance(romfs, dict) else []
    return {entry["path"].casefold(): entry for entry in entries}


def analyze_pack1(image: CiaImage) -> Pack1Analysis:
    slots: list[Pack1SongSlot] = []
    issues: list[ValidationIssue] = []
    for content in image.contents:
        files = _romfs_files(content)
        has_songinfo = SONGINFO_PATH.casefold() in files
        has_musicinfo = MUSICINFO_PATH.casefold() in files
        chart_entries = [entry for entry in files.values() if CHART_PATTERN.match(entry["path"])]
        audio_entries = [entry for entry in files.values() if AUDIO_PATTERN.match(entry["path"])]
        song_like = has_songinfo or has_musicinfo or bool(chart_entries) or bool(audio_entries)
        if not song_like:
            continue
        location = f"content[{content.index}]"
        if not (has_songinfo and has_musicinfo and chart_entries and audio_entries):
            issues.append(
                ValidationIssue(
                    "PACK1_INCOMPLETE_SONG_CONTENT",
                    "ERROR",
                    "Song-like content is missing SongInfo, MusicInfo, chart, or audio resources.",
                    location,
                )
            )
            continue
        try:
            song_entry = files[SONGINFO_PATH.casefold()]
            music_entry = files[MUSICINFO_PATH.casefold()]
            songinfo = parse_pack1_songinfo(
                _read_exact(image.path, song_entry["absolute_offset"], song_entry["size"])
            )
            musicinfo = parse_pack1_musicinfo(
                _read_exact(image.path, music_entry["absolute_offset"], music_entry["size"])
            )
        except BinaryFormatError as exc:
            issues.append(
                ValidationIssue(
                    "PACK1_INFO_PARSE_ERROR",
                    "ERROR",
                    str(exc),
                    location,
                )
            )
            continue

        chart_keys = {CHART_PATTERN.match(entry["path"]).group("key") for entry in chart_entries}  # type: ignore[union-attr]
        charts: dict[str, str] = {}
        for entry in chart_entries:
            match = CHART_PATTERN.match(entry["path"])
            assert match is not None
            filename = match.group("file").casefold()
            key = match.group("key").casefold()
            course = (
                "ura"
                if filename == f"ex_{key}" and match.group("course").lower() == "m"
                else COURSE_NAMES[match.group("course").lower()]
            )
            if course in charts:
                issues.append(
                    ValidationIssue(
                        "PACK1_DUPLICATE_CHART_COURSE",
                        "ERROR",
                        f"Multiple {course} charts exist in one content.",
                        location,
                    )
                )
            charts[course] = entry["path"]
        if len(chart_keys) != 1 or songinfo.chart_key not in chart_keys:
            issues.append(
                ValidationIssue(
                    "PACK1_CHART_KEY_MISMATCH",
                    "ERROR",
                    "SongInfo chart key does not identify the RomFS chart directory.",
                    location,
                    {"songinfo": songinfo.chart_key, "romfs_keys": sorted(chart_keys)},
                )
            )
        if songinfo.music_info_key != musicinfo.music_info_key:
            issues.append(
                ValidationIssue(
                    "PACK1_MUSICINFO_KEY_MISMATCH",
                    "ERROR",
                    "SongInfo does not reference the MusicInfo record key.",
                    location,
                )
            )
        main_path = f"/_data/sound/song/{musicinfo.main_audio_key}.naac"
        preview_path = f"/_data/sound/song/{musicinfo.preview_audio_key}.naac"
        for required_path, code in (
            (main_path, "PACK1_MAIN_AUDIO_MISSING"),
            (preview_path, "PACK1_PREVIEW_AUDIO_MISSING"),
        ):
            if required_path.casefold() not in files:
                issues.append(
                    ValidationIssue(code, "ERROR", f"Referenced audio does not exist: {required_path}", location)
                )
        title_resources = tuple(
            sorted(
                entry["path"]
                for entry in files.values()
                if entry["path"].casefold().startswith("/_data/system/songtitle/")
            )
        )
        if not title_resources:
            issues.append(
                ValidationIssue(
                    "PACK1_TITLE_RESOURCES_MISSING",
                    "ERROR",
                    "No title resources were found for the song slot.",
                    location,
                )
            )
        internal_id = next(iter(chart_keys)) if len(chart_keys) == 1 else songinfo.chart_key
        slots.append(
            Pack1SongSlot(
                content_index=content.index,
                content_id=content.content_id,
                capacity=content.size,
                internal_id=internal_id,
                record_key=songinfo.record_key,
                display_title=songinfo.display_title,
                music_info_key=songinfo.music_info_key,
                main_audio=main_path,
                preview_audio=preview_path,
                charts=charts,
                songinfo=SONGINFO_PATH,
                musicinfo=MUSICINFO_PATH,
                title_resources=title_resources,
                unknown_songinfo_words=songinfo.unknown_words,
                unknown_musicinfo_words=musicinfo.unknown_words,
            )
        )
    return Pack1Analysis(tuple(sorted(slots, key=lambda slot: slot.content_index)), tuple(issues))


def fingerprint_pack1(
    image: CiaImage, source_sha256: str, profile: dict[str, Any]
) -> Pack1Fingerprint:
    matched: list[str] = []
    failed: list[str] = []
    title_hex = f"{image.title_id:016x}"
    allowed_titles = {str(value).lower().removeprefix("0x") for value in profile.get("allowed_title_ids", [])}
    if title_hex in allowed_titles:
        matched.append("title_id")
    else:
        failed.append("title_id")
    expected_count = profile.get("expected_content_count")
    if expected_count == len(image.contents):
        matched.append("content_count")
    else:
        failed.append("content_count")
    expected_indexes = profile.get("expected_content_indexes")
    actual_indexes = [content.index for content in image.contents]
    if expected_indexes == actual_indexes:
        matched.append("content_indexes")
    else:
        failed.append("content_indexes")
    product = profile.get("expected_product_code")
    if product and all(content.ncch and content.ncch.get("product_code") == product for content in image.contents):
        matched.append("product_code")
    else:
        failed.append("product_code")
    if all(
        content.ncch
        and content.ncch.get("status") == "parsed"
        and content.ncch.get("romfs", {}).get("status") == "ivfc_detected"
        for content in image.contents
    ):
        matched.append("ncch_romfs_structure")
    else:
        failed.append("ncch_romfs_structure")
    if failed:
        compatibility = Compatibility.UNSUPPORTED
    elif source_sha256 in profile.get("verified_sha256", []):
        matched.append("verified_sha256")
        compatibility = Compatibility.SUPPORTED
    else:
        compatibility = Compatibility.COMPATIBLE_BUT_UNVERIFIED
    return Pack1Fingerprint(compatibility, tuple(matched), tuple(failed))
