from __future__ import annotations

from collections import Counter

from app.models.audio import ADTSFrame, ADTSStream, ADTSStreamStatistics

SAMPLE_RATES = {
    0: 96000,
    1: 88200,
    2: 64000,
    3: 48000,
    4: 44100,
    5: 32000,
    6: 24000,
    7: 22050,
    8: 16000,
    9: 12000,
    10: 11025,
    11: 8000,
    12: 7350,
}
CHANNEL_COUNTS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 8}
AUDIO_OBJECT_TYPE_NAMES = {1: "AAC Main", 2: "AAC-LC", 3: "AAC SSR", 4: "AAC LTP"}


class ADTSParseError(ValueError):
    def __init__(self, code: str, message: str, offset: int) -> None:
        super().__init__(message)
        self.code = code
        self.offset = offset


def parse_adts_frame(data: bytes | memoryview, offset: int = 0) -> ADTSFrame:
    available = len(data) - offset
    if offset < 0 or available < 7:
        raise ADTSParseError("ADTS_TRUNCATED_HEADER", "ADTS fixed header is truncated.", offset)
    b0, b1, b2, b3, b4, b5, b6 = data[offset : offset + 7]
    syncword = (b0 << 4) | (b1 >> 4)
    if syncword != 0xFFF:
        raise ADTSParseError("ADTS_BAD_SYNC", "ADTS syncword is not 0xFFF.", offset)
    mpeg_id = (b1 >> 3) & 1
    layer = (b1 >> 1) & 0x03
    if layer != 0:
        raise ADTSParseError("ADTS_RESERVED_LAYER", "ADTS layer must be zero.", offset)
    protection_absent = bool(b1 & 1)
    profile = (b2 >> 6) & 0x03
    audio_object_type = profile + 1
    sampling_frequency_index = (b2 >> 2) & 0x0F
    sample_rate = SAMPLE_RATES.get(sampling_frequency_index)
    if sample_rate is None:
        raise ADTSParseError(
            "ADTS_INVALID_SAMPLE_RATE_INDEX",
            f"Reserved or explicit ADTS sample-rate index: {sampling_frequency_index}.",
            offset,
        )
    private_bit = (b2 >> 1) & 1
    channel_configuration = ((b2 & 1) << 2) | ((b3 >> 6) & 0x03)
    channels = CHANNEL_COUNTS.get(channel_configuration)
    if channels is None:
        raise ADTSParseError(
            "ADTS_UNSUPPORTED_CHANNEL_CONFIGURATION",
            f"ADTS channel configuration {channel_configuration} requires unsupported PCE handling.",
            offset,
        )
    original_copy = (b3 >> 5) & 1
    home = (b3 >> 4) & 1
    copyright_identification_bit = (b3 >> 3) & 1
    copyright_identification_start = (b3 >> 2) & 1
    aac_frame_length = ((b3 & 0x03) << 11) | (b4 << 3) | (b5 >> 5)
    adts_buffer_fullness = ((b5 & 0x1F) << 6) | (b6 >> 2)
    number_of_raw_data_blocks = b6 & 0x03
    header_length = 7 if protection_absent else 9
    if available < header_length:
        raise ADTSParseError("ADTS_CRC_TRUNCATED", "ADTS CRC bytes are truncated.", offset)
    if aac_frame_length < header_length:
        raise ADTSParseError(
            "ADTS_INVALID_FRAME_LENGTH",
            f"ADTS frame length {aac_frame_length} is smaller than header {header_length}.",
            offset,
        )
    end_offset = offset + aac_frame_length
    if end_offset > len(data):
        raise ADTSParseError(
            "ADTS_TRUNCATED_FRAME",
            f"ADTS frame ends at {end_offset}, beyond stream size {len(data)}.",
            offset,
        )
    return ADTSFrame(
        offset=offset,
        syncword=syncword,
        mpeg_id=mpeg_id,
        layer=layer,
        protection_absent=protection_absent,
        profile=profile,
        audio_object_type=audio_object_type,
        sampling_frequency_index=sampling_frequency_index,
        sample_rate=sample_rate,
        private_bit=private_bit,
        channel_configuration=channel_configuration,
        channels=channels,
        original_copy=original_copy,
        home=home,
        copyright_identification_bit=copyright_identification_bit,
        copyright_identification_start=copyright_identification_start,
        aac_frame_length=aac_frame_length,
        adts_buffer_fullness=adts_buffer_fullness,
        number_of_raw_data_blocks_in_frame=number_of_raw_data_blocks,
        crc_present=not protection_absent,
        header_length=header_length,
        payload_length=aac_frame_length - header_length,
        end_offset=end_offset,
    )


def parse_adts_stream(data: bytes | memoryview) -> ADTSStream:
    frames: list[ADTSFrame] = []
    cursor = 0
    expected_format: tuple[int, int, int, int] | None = None
    while cursor < len(data):
        if len(data) - cursor < 7:
            raise ADTSParseError(
                "ADTS_TRAILING_BYTES",
                f"{len(data) - cursor} unexplained trailing bytes follow the final frame.",
                cursor,
            )
        try:
            frame = parse_adts_frame(data, cursor)
        except ADTSParseError as exc:
            if frames and exc.code == "ADTS_BAD_SYNC":
                raise ADTSParseError(
                    "ADTS_NEXT_SYNC_MISMATCH",
                    "The next ADTS frame does not start with a valid syncword.",
                    cursor,
                ) from exc
            raise
        current_format = (
            frame.sampling_frequency_index,
            frame.channel_configuration,
            frame.profile,
            frame.mpeg_id,
        )
        if expected_format is None:
            expected_format = current_format
        elif current_format != expected_format:
            raise ADTSParseError(
                "ADTS_FORMAT_CHANGED",
                "Sample rate, channels, profile, or MPEG ID changed inside the ADTS stream.",
                cursor,
            )
        frames.append(frame)
        cursor = frame.end_offset
    if not frames:
        raise ADTSParseError("ADTS_EMPTY_STREAM", "ADTS stream contains no frames.", 0)

    first = frames[0]
    total_bytes = sum(frame.aac_frame_length for frame in frames)
    header_bytes = sum(frame.header_length for frame in frames)
    payload_bytes = sum(frame.payload_length for frame in frames)
    # ISO AAC raw_data_blocks adds one 1024-sample AAC block for every stored value.
    total_samples = sum(
        1024 * (frame.number_of_raw_data_blocks_in_frame + 1) for frame in frames
    )
    duration = total_samples / first.sample_rate
    crc_count = sum(frame.crc_present for frame in frames)
    crc_usage = "all" if crc_count == len(frames) else "none" if crc_count == 0 else "mixed"
    sizes = [frame.aac_frame_length for frame in frames]
    raw_blocks = Counter(frame.number_of_raw_data_blocks_in_frame for frame in frames)
    statistics = ADTSStreamStatistics(
        frame_count=len(frames),
        total_bytes=total_bytes,
        payload_bytes=payload_bytes,
        header_bytes=header_bytes,
        sample_rate=first.sample_rate,
        channel_configuration=first.channel_configuration,
        channels=first.channels,
        profile=first.profile,
        audio_object_type=first.audio_object_type,
        audio_object_type_name=AUDIO_OBJECT_TYPE_NAMES.get(
            first.audio_object_type, f"AOT {first.audio_object_type}"
        ),
        mpeg_id=first.mpeg_id,
        mpeg_version="MPEG-2" if first.mpeg_id else "MPEG-4",
        crc_usage=crc_usage,
        raw_data_blocks=dict(raw_blocks),
        total_samples=total_samples,
        duration_seconds=duration,
        measured_bitrate_bps=(total_bytes * 8) / duration,
        minimum_frame_size=min(sizes),
        maximum_frame_size=max(sizes),
        average_frame_size=total_bytes / len(frames),
    )
    return ADTSStream(tuple(frames), statistics)
