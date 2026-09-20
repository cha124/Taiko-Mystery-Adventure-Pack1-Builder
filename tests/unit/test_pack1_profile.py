from __future__ import annotations

from pathlib import Path

from app.core.cia_reader import read_cia
from app.core.pack1_analyzer import fingerprint_pack1
from app.core.song_catalog import load_song_catalog
from app.models.fingerprint import Compatibility, WriteCompatibility
from tests.synthetic_cia import make_synthetic_cia, make_synthetic_ncch


def _synthetic_image(tmp_path: Path):
    path = tmp_path / "fingerprint.cia.fixture"
    path.write_bytes(make_synthetic_cia(contents=(make_synthetic_ncch(),)))
    return read_cia(path)


def _matching_profile(image) -> dict[str, object]:
    return {
        "allowed_title_ids": [f"{image.title_id:016x}"],
        "expected_content_count": 1,
        "expected_content_indexes": [0],
        "expected_product_code": "CTR-P-SYNTH",
        "verified_sha256": [],
    }


def test_fingerprint_distinguishes_verified_hash_from_structural_match(tmp_path: Path) -> None:
    image = _synthetic_image(tmp_path)
    profile = _matching_profile(image)
    structural = fingerprint_pack1(image, "not-recorded", profile)
    assert structural.compatibility is Compatibility.COMPATIBLE_BUT_UNVERIFIED
    assert structural.write_fingerprint.compatibility is WriteCompatibility.BLOCKED

    profile["verified_sha256"] = ["recorded"]
    verified = fingerprint_pack1(image, "recorded", profile)
    assert verified.compatibility is Compatibility.SUPPORTED
    assert verified.write_fingerprint.compatibility is WriteCompatibility.BLOCKED
    assert "title_id" in verified.write_fingerprint.satisfied_checks
    assert "content_ids" in verified.write_fingerprint.missing_checks
    assert "verified_sha256" in verified.matched_checks


def test_fingerprint_rejects_major_structure_mismatch(tmp_path: Path) -> None:
    image = _synthetic_image(tmp_path)
    profile = _matching_profile(image)
    profile["expected_content_indexes"] = [1]
    fingerprint = fingerprint_pack1(image, "irrelevant", profile)
    assert fingerprint.compatibility is Compatibility.UNSUPPORTED
    assert fingerprint.write_fingerprint.compatibility is WriteCompatibility.BLOCKED
    assert "content_indexes" in fingerprint.failed_checks


def test_verified_pack1_catalog_has_77_unique_protected_slots() -> None:
    catalog = load_song_catalog("taiko3ds3_jp_pack1")
    identities = {
        (song.slot.content_index, song.slot.content_id, song.slot.internal_id)
        for song in catalog.songs
    }
    assert catalog.verified
    assert len(catalog.songs) == 77
    assert len(identities) == 77
    assert all(song.slot.protected for song in catalog.songs)
    anomaly = next(song.slot for song in catalog.songs if song.slot.content_index == 69)
    assert not anomaly.replacement_eligible
    assert anomaly.protection_reason == "known unresolved source-reference anomaly"
