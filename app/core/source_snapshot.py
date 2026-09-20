from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app.core.binary import BinaryFormatError


@dataclass(frozen=True)
class SourceSnapshot:
    """Immutable bytes captured from one source-file open operation."""

    path: Path
    size: int
    sha256: str
    _data: bytes = field(repr=False)

    @classmethod
    def from_path(cls, path: Path) -> "SourceSnapshot":
        resolved = path.resolve()
        data = resolved.read_bytes()
        return cls(
            path=resolved,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            _data=data,
        )

    def read(self, offset: int, size: int) -> bytes:
        self._require_range(offset, size)
        return self._data[offset : offset + size]

    def view(self, offset: int = 0, size: int | None = None) -> memoryview:
        length = self.size - offset if size is None else size
        self._require_range(offset, length)
        return memoryview(self._data)[offset : offset + length]

    def _require_range(self, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > self.size:
            raise BinaryFormatError(
                f"snapshot range is outside the source: offset=0x{offset:X}, "
                f"size=0x{size:X}, source_size=0x{self.size:X}"
            )
