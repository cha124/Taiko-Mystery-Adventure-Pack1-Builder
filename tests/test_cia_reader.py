from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.binary import BinaryFormatError
from app.core.cia_reader import read_cia
from tests.synthetic_cia import make_synthetic_cia, make_synthetic_ncch


class CiaReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _write(self, data: bytes) -> Path:
        path = self.root / "fixture.bin"
        path.write_bytes(data)
        return path

    def test_reads_header_tmd_and_selected_contents(self) -> None:
        payloads = (b"first", b"second-payload")
        image = read_cia(self._write(make_synthetic_cia(contents=payloads)))
        self.assertEqual(image.title_id, 0x0004008CDEADBEEF)
        self.assertEqual(image.tmd_content_count, 2)
        self.assertEqual([entry.index for entry in image.contents], [0, 1])
        self.assertTrue(all(entry.actual_sha256 for entry in image.contents))

    def test_rejects_truncated_header(self) -> None:
        with self.assertRaises(BinaryFormatError):
            read_cia(self._write(b"not a cia"))

    def test_rejects_truncated_content(self) -> None:
        data = make_synthetic_cia(contents=(b"payload",))
        with self.assertRaises(BinaryFormatError):
            read_cia(self._write(data[:-1]))

    def test_reads_unencrypted_ncch_and_romfs_boundary(self) -> None:
        image = read_cia(self._write(make_synthetic_cia(contents=(make_synthetic_ncch(),))))
        ncch = image.contents[0].ncch
        self.assertIsNotNone(ncch)
        assert ncch is not None
        self.assertEqual(ncch["status"], "parsed")
        self.assertEqual(ncch["romfs"]["status"], "ivfc_detected")
        self.assertEqual(ncch["program_id"], "0004000000000001")


if __name__ == "__main__":
    unittest.main()
