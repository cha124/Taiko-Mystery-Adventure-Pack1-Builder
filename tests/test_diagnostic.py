from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.job_runner import run_diagnostic
from tests.synthetic_cia import make_synthetic_cia


class DiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_unknown_cia_fails_fingerprint_and_does_not_claim_device_pass(self) -> None:
        source = self.root / "source.bin"
        output = self.root / "nested" / "report.json"
        source.write_bytes(make_synthetic_cia())
        report = run_diagnostic(source, output=output)
        saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report.status, "FAIL")
        self.assertEqual(saved["compatibility"]["status"], "UNSUPPORTED")
        self.assertEqual(saved["device_validation"], "NOT_TESTED")
        self.assertEqual(saved["source"]["sha256"], report.source_sha256)
        self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_duplicate_tmd_index_is_rejected(self) -> None:
        source = self.root / "duplicate.bin"
        source.write_bytes(
            make_synthetic_cia(contents=(b"one", b"two"), duplicate_index=True)
        )
        report = run_diagnostic(source)
        self.assertEqual(report.status, "FAIL")
        self.assertIn(
            "CIA_TMD_DUPLICATE_INDEX",
            {issue.code for issue in report.issues},
        )

    def test_unencrypted_content_hash_mismatch_is_rejected(self) -> None:
        source = self.root / "tampered.bin"
        data = bytearray(make_synthetic_cia(contents=(b"payload",)))
        data[-1] ^= 0xFF
        source.write_bytes(data)
        report = run_diagnostic(source)
        self.assertEqual(report.status, "FAIL")
        self.assertIn(
            "CIA_CONTENT_HASH_MISMATCH",
            {issue.code for issue in report.issues},
        )


if __name__ == "__main__":
    unittest.main()
