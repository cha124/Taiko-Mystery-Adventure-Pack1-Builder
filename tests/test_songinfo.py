from __future__ import annotations

import unittest
import struct

from app.core.binary import BinaryFormatError
from app.core.songinfo.parser import (
    parse_pack1_musicinfo,
    parse_pack1_songinfo,
    read_bounded_c_string,
    read_pointer_c_string,
)
from tests.synthetic_romfs import _pointer_table
from app.core.songinfo.validator import validate_required_references


class SongInfoSafetyTests(unittest.TestCase):
    def test_reads_only_until_nul(self) -> None:
        field = read_bounded_c_string(b"xxxxTitle\0untouched", 4)
        self.assertEqual(field.text, "Title")

    def test_rejects_missing_nul(self) -> None:
        with self.assertRaises(BinaryFormatError):
            read_bounded_c_string(b"xxxxTitle", 4)

    def test_reports_missing_reference(self) -> None:
        issues = validate_required_references(
            ["sound/song.naac", "chart/song.bin"],
            ["sound/song.naac"],
        )
        self.assertEqual([issue.code for issue in issues], ["SONGINFO_REFERENCE_MISSING"])

    def test_resolves_real_pointer_field(self) -> None:
        data = bytearray(32)
        struct.pack_into("<I", data, 4, 16)
        data[16:22] = b"chart\0"
        self.assertEqual(read_pointer_c_string(bytes(data), 4).text, "chart")

    def test_rejects_out_of_range_pointer(self) -> None:
        data = bytearray(16)
        struct.pack_into("<I", data, 0, 0x1000)
        with self.assertRaises(BinaryFormatError):
            read_pointer_c_string(bytes(data), 0)

    def test_rejects_empty_required_pointer_target(self) -> None:
        data = bytearray(16)
        struct.pack_into("<I", data, 0, 8)
        with self.assertRaises(BinaryFormatError):
            read_pointer_c_string(bytes(data), 0)

    def test_parses_pack1_songinfo_pointer_table(self) -> None:
        data = _pointer_table(
            ("DSONG_TEST", "Synthetic", "d_test", "test", "test", "test"),
            0x50,
            6,
        )
        parsed = parse_pack1_songinfo(data)
        self.assertEqual(parsed.display_title, "Synthetic")
        self.assertEqual(parsed.music_info_key, "d_test")
        self.assertEqual(parsed.chart_key, "test")

    def test_parses_pack1_musicinfo_pointer_table(self) -> None:
        data = _pointer_table(("d_test", "test_3ds", "test_3ds_s"), 0x30, 3)
        parsed = parse_pack1_musicinfo(data)
        self.assertEqual(parsed.main_audio_key, "test_3ds")
        self.assertEqual(parsed.preview_audio_key, "test_3ds_s")


if __name__ == "__main__":
    unittest.main()
