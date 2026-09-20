from __future__ import annotations

import unittest
import struct

from app.core.binary import BinaryFormatError
from app.core.songinfo.parser import read_bounded_c_string, read_pointer_c_string
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


if __name__ == "__main__":
    unittest.main()
