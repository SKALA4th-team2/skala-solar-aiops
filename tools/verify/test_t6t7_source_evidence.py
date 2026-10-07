"""CLI regressions for binding historical review notes to the reviewed files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("t6t7_source_evidence.py")
MANIFEST = SCRIPT.with_suffix(".json")


def blank_pdf(label):
    """Build a real one-page PDF fixture without third-party dependencies."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>",
    ]
    data = b"%PDF-1.4\n% " + label.encode("ascii") + b"\n"
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 4\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return data


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / SCRIPT.name
        shutil.copyfile(SCRIPT, self.script)
        self.paths = {
            "rule": self.root / "rule.pdf",
            "broker": self.root / "broker.hwp",
            "market": self.root / "market.pdf",
        }
        self.paths["rule"].write_bytes(blank_pdf("rule fixture"))
        self.paths["broker"].write_bytes(b"unreviewed HWP fixture")
        self.paths["market"].write_bytes(blank_pdf("market fixture"))
        self.broker_text = self.root / "broker.txt"
        self.broker_text.write_text("제35조의2 제35조의3", encoding="utf-8")
        # This fixture is deliberately separate from the real manual record.
        self.record = {
            "verified_on": "2000-01-01",
            "sources": [
                {
                    "name": f"Fixture {role}",
                    "url": f"https://example.invalid/{path.name}",
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                    "excerpts": {"fixture": "Historical manual observation"},
                }
                for role, path in self.paths.items()
            ],
            "unavailable_live_source": {"url": "https://example.invalid/unavailable"},
        }
        self.record["sources"][2].update(
            pages=1, checked_pdf_pages=[1], visually_checked=True
        )
        self.manifest = self.script.with_suffix(".json")
        self.manifest.write_text(json.dumps(self.record), encoding="utf-8")

    def run_cli(self, script=None):
        command = [sys.executable, str(script or self.script)]
        for role, path in self.paths.items():
            command.extend([f"--{role}", str(path)])
        # An extracted text file must never replace the binary source check.
        command.extend(["--broker-text", str(self.broker_text)])
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "", "Failure must not emit success evidence")
        self.assertTrue(result.stderr)

    def test_unreviewed_pdfs_cannot_inherit_official_review_claims(self):
        before = MANIFEST.read_bytes()
        self.assert_rejected(self.run_cli(SCRIPT))
        self.assertEqual(MANIFEST.read_bytes(), before)

    def test_matching_files_preserve_historical_review_and_separate_new_check(self):
        before = self.manifest.read_bytes()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["recorded_manual_review"], self.record)
        self.assertNotIn("verified_on", output)
        verification = output["file_identity_check"]
        self.assertEqual(verification["kind"], "sha256_match_to_recorded_manual_review")
        self.assertEqual(verification["matched_sources"], ["rule", "broker", "market"])
        self.assertIn("checked_at_utc", verification)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_each_source_is_checked_even_when_file_size_is_unchanged(self):
        for role, path in self.paths.items():
            with self.subTest(role=role):
                original = path.read_bytes()
                # Same length: a size-only check would incorrectly accept it.
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                try:
                    self.assert_rejected(self.run_cli())
                finally:
                    path.write_bytes(original)

    def test_missing_binary_cannot_be_replaced_by_extracted_clause_text(self):
        self.paths["broker"].unlink()
        self.assert_rejected(self.run_cli())


if __name__ == "__main__":
    unittest.main()
