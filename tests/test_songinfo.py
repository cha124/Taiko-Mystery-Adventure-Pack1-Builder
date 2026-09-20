from __future__ import annotations

import unittest

from app.core.binary import BinaryFormatError
from app.core.songinfo.parser import read_bounded_c_string
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


if __name__ == "__main__":
    unittest.main()

