from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ReadCompatibility(str, Enum):
    SUPPORTED = "SUPPORTED"
    COMPATIBLE_BUT_UNVERIFIED = "COMPATIBLE_BUT_UNVERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    CORRUPT = "CORRUPT"


# Backward-compatible import name. This always describes read compatibility.
Compatibility = ReadCompatibility


class WriteCompatibility(str, Enum):
    NOT_SUPPORTED = "NOT_SUPPORTED"
    BLOCKED = "BLOCKED"
    VERIFIED_STRUCTURE_ONLY = "VERIFIED_STRUCTURE_ONLY"


WRITE_REQUIRED_CHECKS = (
    "title_id",
    "content_count",
    "content_indexes",
    "content_ids",
    "content_sizes",
    "product_code",
    "ncch_romfs_structure",
    "slot_identities",
    "songinfo_schema",
    "musicinfo_schema",
    "known_baseline_anomalies",
)


@dataclass(frozen=True)
class Pack1WriteFingerprint:
    compatibility: WriteCompatibility = WriteCompatibility.BLOCKED
    required_checks: tuple[str, ...] = WRITE_REQUIRED_CHECKS
    satisfied_checks: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = (
        "writer_not_implemented",
        "device_behavior_not_certified",
        "replacement_policy_not_approved",
    )

    def __post_init__(self) -> None:
        unknown = set(self.satisfied_checks) - set(self.required_checks)
        if unknown:
            raise ValueError(f"unknown write fingerprint checks: {sorted(unknown)}")

    @property
    def missing_checks(self) -> tuple[str, ...]:
        satisfied = set(self.satisfied_checks)
        return tuple(check for check in self.required_checks if check not in satisfied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.compatibility.value,
            "required_checks": list(self.required_checks),
            "satisfied_checks": list(self.satisfied_checks),
            "missing_checks": list(self.missing_checks),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class Pack1Fingerprint:
    read_compatibility: ReadCompatibility
    matched_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
    write_fingerprint: Pack1WriteFingerprint = Pack1WriteFingerprint()

    @property
    def compatibility(self) -> ReadCompatibility:
        """Compatibility alias retained for callers of the schema-v1 model."""
        return self.read_compatibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.read_compatibility.value,
            "read": self.read_compatibility.value,
            "write": self.write_fingerprint.compatibility.value,
            "matched_checks": list(self.matched_checks),
            "failed_checks": list(self.failed_checks),
            "write_gate": self.write_fingerprint.to_dict(),
        }
