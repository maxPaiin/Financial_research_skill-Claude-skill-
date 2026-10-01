"""
v0.4 C2 (+ C3 later) — intake: one .zip (or a directory on the CLI), checked
before anything is written, with the Stage 0 rules unchanged.

Tests generate their own factsheets (tests/factsheets.py); no real fund PDF
is ever opened.

    python -m unittest tests.test_v04_intake -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_TESTS))

import factsheets  # noqa: E402
from validate_uploads import IntakeError, extract_zip, validate  # noqa: E402

EMAIL = "ops@example.com"


@unittest.skipUnless(factsheets.have_reportlab(), "reportlab not installed")
class _WithFactsheets(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.pdfs = factsheets.make_upload_set(self.tmp / "src", 7)

    def zip_of(self, members: dict[str, bytes | Path], name: str = "funds.zip") -> Path:
        path = self.tmp / name
        with zipfile.ZipFile(path, "w") as zf:
            for arcname, content in members.items():
                data = content.read_bytes() if isinstance(content, Path) else content
                zf.writestr(arcname, data)
        return path

    def seven(self, prefix: str = "") -> dict[str, Path]:
        return {f"{prefix}{p.name}": p for p in self.pdfs}


class TestZipIntake(_WithFactsheets):
    def test_a_zip_of_seven_factsheets_validates(self):
        dest = self.tmp / "extracted"
        res = validate(self.zip_of(self.seven()), email=EMAIL, extract_to=dest)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["n_files"], 7)
        self.assertEqual(res["input"]["kind"], "zip")
        self.assertEqual(res["input"]["pdf_dir"], str(dest))
        self.assertEqual(len(list(dest.glob("*.pdf"))), 7)

    def test_pdfs_inside_a_folder_are_flattened(self):
        res = validate(self.zip_of(self.seven("Fund factsheets/")), email=EMAIL,
                       extract_to=self.tmp / "x")
        self.assertTrue(res["ok"], res["errors"])

    def test_path_traversal_is_rejected_and_nothing_written(self):
        for evil in ("../evil.pdf", "/abs/evil.pdf", "a/../../evil.pdf", "C:/evil.pdf"):
            with self.subTest(member=evil):
                members = {**self.seven(), evil: self.pdfs[0]}
                dest = self.tmp / f"x{abs(hash(evil))}"
                res = validate(self.zip_of(members), email=EMAIL, extract_to=dest)
                self.assertFalse(res["ok"])
                self.assertIn("path traversal", res["errors"][0])
                self.assertFalse(dest.exists() and any(dest.iterdir()))
                self.assertFalse((self.tmp / "evil.pdf").exists())

    def test_nested_archive_is_rejected(self):
        res = validate(self.zip_of({**self.seven(), "more.zip": b"PK\x05\x06" + b"\0" * 18}),
                       email=EMAIL, extract_to=self.tmp / "x")
        self.assertFalse(res["ok"])
        self.assertIn("another archive", res["errors"][0])

    def test_macos_metadata_is_ignored(self):
        members = {**self.seven(), "__MACOSX/._fund_01.pdf": b"junk", "._fund_02.pdf": b"junk",
                   ".DS_Store": b"junk"}
        res = validate(self.zip_of(members), email=EMAIL, extract_to=self.tmp / "x")
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["n_files"], 7)
        self.assertEqual(res["input"]["skipped"], [])

    def test_other_files_are_skipped_and_listed(self):
        res = validate(self.zip_of({**self.seven(), "notes.txt": b"hello"}), email=EMAIL,
                       extract_to=self.tmp / "x")
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["input"]["skipped"], ["notes.txt"])

    def test_two_pdfs_with_one_name_are_rejected(self):
        members = {**self.seven(), "copy/fund_01.pdf": self.pdfs[0]}
        res = validate(self.zip_of(members), email=EMAIL, extract_to=self.tmp / "x")
        self.assertFalse(res["ok"])
        self.assertIn("two PDFs named", res["errors"][0])

    def test_a_previous_extraction_does_not_leak_in(self):
        dest = self.tmp / "extracted"
        dest.mkdir()
        (dest / "stale_old_fund.pdf").write_bytes(self.pdfs[0].read_bytes())
        res = validate(self.zip_of(self.seven()), email=EMAIL, extract_to=dest)
        self.assertEqual(res["n_files"], 7)
        self.assertFalse((dest / "stale_old_fund.pdf").exists())

    def test_not_a_zip(self):
        bad = self.tmp / "funds.zip"
        bad.write_bytes(b"not a zip at all")
        res = validate(bad, email=EMAIL, extract_to=self.tmp / "x")
        self.assertFalse(res["ok"])
        self.assertIn("not a readable .zip", res["errors"][0])

    def test_extract_zip_reports_what_it_kept(self):
        out = extract_zip(self.zip_of({**self.seven(), "readme.md": b"x"}), self.tmp / "y")
        self.assertEqual(len(out["pdfs"]), 7)
        self.assertEqual(out["skipped"], ["readme.md"])
        with self.assertRaises(IntakeError):
            extract_zip(self.zip_of({"../x.pdf": b"%PDF"}, "evil.zip"), self.tmp / "z")


class TestCountRuleUnchanged(_WithFactsheets):
    def test_eleven_is_still_the_ceiling_and_max_files_raises_it(self):
        extra = factsheets.make_upload_set(self.tmp / "more", 12)
        members = {f"f{i}.pdf": p for i, p in enumerate(extra)}
        zip_path = self.zip_of(members)
        res = validate(zip_path, email=EMAIL, extract_to=self.tmp / "x")
        self.assertFalse(res["ok"])
        self.assertTrue(any("need 7–11" in e for e in res["errors"]))
        res = validate(zip_path, email=EMAIL, extract_to=self.tmp / "y", max_files=12)
        self.assertTrue(res["ok"], res["errors"])

    def test_too_few_in_a_zip(self):
        res = validate(self.zip_of({p.name: p for p in self.pdfs[:3]}), email=EMAIL,
                       extract_to=self.tmp / "x")
        self.assertFalse(res["ok"])
        self.assertTrue(any("Got 3 PDF(s)" in e and ".zip" in e for e in res["errors"]))

    def test_directory_input_still_works_and_ignores_resource_forks(self):
        (self.tmp / "src" / "._fund_01.pdf").write_bytes(b"junk")
        res = validate(self.tmp / "src", email=EMAIL)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["input"]["kind"], "directory")
        self.assertEqual(res["n_files"], 7)

    def test_cli_with_a_zip(self):
        zip_path = self.zip_of(self.seven())
        out = self.tmp / "stage0.json"
        run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / "validate_uploads.py"),
                              str(zip_path), "--email", EMAIL, "--out", str(out),
                              "--extract-to", str(self.tmp / "ex")],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout[-500:] + run.stderr[-500:])
        self.assertEqual(json.loads(out.read_text())["input"]["kind"], "zip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
