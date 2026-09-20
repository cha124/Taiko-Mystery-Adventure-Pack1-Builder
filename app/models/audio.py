from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AudioSeverity = Literal["WARNING", "ERROR"]


@dataclass(frozen=True)
class AudioIssue:
    code: str
    severity: AudioSeverity
    message: str
    offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.offset is not None:
            result["offset"] = self.offset
        return result


@dataclass(frozen=True)
class ADTSFrame:
    offset: int
    syncword: int
    mpeg_id: int
    layer: int
    protection_absent: bool
    profile: int
    audio_object_type: int
    sampling_frequency_index: int
    sample_rate: int
    private_bit: int
    channel_configuration: int
    channels: int
    original_copy: int
    home: int
    copyright_identification_bit: int
    copyright_identification_start: int
    aac_frame_length: int
    adts_buffer_fullness: int
    number_of_raw_data_blocks_in_frame: int
    crc_present: bool
    header_length: int
    payload_length: int
    end_offset: int


@dataclass(frozen=True)
class ADTSStreamStatistics:
    frame_count: int
    total_bytes: int
    payload_bytes: int
    header_bytes: int
    sample_rate: int
    channel_configuration: int
    channels: int
    profile: int
    audio_object_type: int
    audio_object_type_name: str
    mpeg_id: int
    mpeg_version: str
    crc_usage: str
    raw_data_blocks: dict[int, int]
    total_samples: int
    duration_seconds: float
    measured_bitrate_bps: float
    minimum_frame_size: int
    maximum_frame_size: int
    average_frame_size: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_count": self.frame_count,
            "total_bytes": self.total_bytes,
            "payload_bytes": self.payload_bytes,
            "header_bytes": self.header_bytes,
            "sample_rate": self.sample_rate,
            "channel_configuration": self.channel_configuration,
            "channels": self.channels,
            "profile": self.profile,
            "audio_object_type": self.audio_object_type,
            "audio_object_type_name": self.audio_object_type_name,
            "mpeg_id": self.mpeg_id,
            "mpeg_version": self.mpeg_version,
            "crc_usage": self.crc_usage,
            "raw_data_blocks": {str(key): value for key, value in sorted(self.raw_data_blocks.items())},
            "total_samples": self.total_samples,
            "duration_seconds": self.duration_seconds,
            "measured_bitrate_bps": self.measured_bitrate_bps,
            "minimum_frame_size": self.minimum_frame_size,
            "maximum_frame_size": self.maximum_frame_size,
            "average_frame_size": self.average_frame_size,
        }


@dataclass(frozen=True)
class ADTSStream:
    frames: tuple[ADTSFrame, ...]
    statistics: ADTSStreamStatistics


@dataclass(frozen=True)
class SeekTableCandidate:
    offset: int
    entry_width: int
    entry_count: int
    endianness: str
    base: str
    frame_interval: int | None
    match_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "entry_width": self.entry_width,
            "entry_count": self.entry_count,
            "endianness": self.endianness,
            "base": self.base,
            "frame_interval": self.frame_interval,
            "match_ratio": self.match_ratio,
        }


@dataclass(frozen=True)
class NAACInspection:
    total_size: int
    sha256: str
    header_size: int
    payload_offset: int
    payload_size: int
    header_sha256: str
    payload_sha256: str
    unknown_header_bytes: bytes = field(repr=False)
    adts: ADTSStreamStatistics | None = None
    seek_candidates: tuple[SeekTableCandidate, ...] = ()
    issues: tuple[AudioIssue, ...] = ()


@dataclass(frozen=True)
class AudioFileAnalysis:
    content_index: int
    internal_song_id: str
    role: str
    romfs_path: str
    naac_size: int
    naac_sha256: str
    parse_status: str
    inspection: NAACInspection | None = field(default=None, repr=False)
    issues: tuple[AudioIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "content_index": self.content_index,
            "internal_song_id": self.internal_song_id,
            "role": self.role,
            "romfs_path": self.romfs_path,
            "naac_size": self.naac_size,
            "naac_sha256": self.naac_sha256,
            "parse_status": self.parse_status,
            "issues": [issue.to_dict() for issue in self.issues],
        }
        if self.inspection is not None:
            inspection = self.inspection
            result.update(
                {
                    "header_size": inspection.header_size,
                    "header_sha256": inspection.header_sha256,
                    "payload_offset": inspection.payload_offset,
                    "payload_size": inspection.payload_size,
                    "payload_sha256": inspection.payload_sha256,
                    "unknown_header_bytes": {
                        "size": len(inspection.unknown_header_bytes),
                        "sha256": inspection.header_sha256,
                    },
                    "adts": inspection.adts.to_dict() if inspection.adts else None,
                    "seek_candidates": [item.to_dict() for item in inspection.seek_candidates],
                }
            )
        return result
