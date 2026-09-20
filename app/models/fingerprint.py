from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Compatibility(str, Enum):
    SUPPORTED = "SUPPORTED"
    COMPATIBLE_BUT_UNVERIFIED = "COMPATIBLE_BUT_UNVERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True)
class Pack1Fingerprint:
    compatibility: Compatibility
    matched_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.compatibility.value,
            "matched_checks": list(self.matched_checks),
            "failed_checks": list(self.failed_checks),
        }
