"""
v0.4 C2 + C3 — intake: one .zip (or a directory on the CLI), checked before
anything is written, with the Stage 0 rules unchanged; then scripted Stage 1a
(extract_candidates.py), the one-page render and the review corrections.

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


# -----------------------------------------------------------------------------
# C3 — scripted Stage 1a
# -----------------------------------------------------------------------------

def _have_pdfplumber() -> bool:
    try:
        import pdfplumber  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(factsheets.have_reportlab() and _have_pdfplumber(),
                     "reportlab and pdfplumber are required")
class TestExtractCandidates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def extract(self, **kw) -> dict:
        import extract_candidates as ec
        pdf = factsheets.make_factsheet(self.tmp / "f.pdf", **kw)
        return ec.extract_fund(pdf, "F1")

    def test_english_factsheet_fields(self):
        c = self.extract()
        f = {k: v["value"] for k, v in c["fields"].items()}
        self.assertEqual(f, {
            "fund_name": "Global Technology Equity Fund", "asof": "2026-03-31",
            "currency": "USD", "total_aum": 4.2e9,
            "benchmark": "MSCI AC World Information Technology Index",
            "fund_isin": "LU0000000001", "nav_per_share": 87.31})
        self.assertTrue(all(v["confidence"] == "high" for v in c["fields"].values()))
        self.assertEqual(c["fields"]["total_aum"]["unit"], "million")
        self.assertEqual(c["flags"], [])

    def test_english_factsheet_rows(self):
        rows = self.extract()["holdings"]["rows"]
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0], {"name": "Apple Inc", "ticker_raw": "AAPL", "isin": None,
                                   "weight": 0.071, "confidence": "high", "page": 1})
        self.assertEqual(rows[5]["ticker_raw"], "2330 TT")
        self.assertAlmostEqual(sum(r["weight"] for r in rows), 0.419, places=6)

    def test_holdings_on_a_later_page(self):
        c = self.extract(filler_pages=2)
        self.assertEqual(c["holdings"]["page"], 3)
        self.assertTrue(all(r["page"] == 3 for r in c["holdings"]["rows"]))

    def test_currency_comes_from_what_is_printed(self):
        c = self.extract(facts=["Fund size (HKD): 3,100 million", "Benchmark: S&P 500 Index"])
        self.assertEqual(c["fields"]["currency"]["value"], "HKD")
        bare = self.extract(facts=["Currency: $", "Fund size: $ 900 million"])
        self.assertIsNone(bare["fields"]["currency"]["value"])
        self.assertIn("F1.currency", [fl["path"] for fl in bare["flags"]])

    def test_missing_fields_are_null_and_flagged_never_guessed(self):
        c = self.extract(facts=["Fund size: USD 500 million"])
        self.assertIsNone(c["fields"]["benchmark"]["value"])
        self.assertIsNone(c["fields"]["fund_isin"]["value"])
        self.assertIn("F1.benchmark", [fl["path"] for fl in c["flags"]])

    def test_chinese_headers_and_units_best_effort(self):
        import extract_candidates as ec
        pdf = factsheets.make_cjk_factsheet(self.tmp / "zh.pdf")
        import pdfplumber
        with pdfplumber.open(str(pdf)) as doc:
            if "十大持倉" not in (doc.pages[0].extract_text() or ""):
                self.skipTest("CJK text extraction unavailable for this font")
        c = ec.extract_fund(pdf, "F1")
        f = {k: v["value"] for k, v in c["fields"].items()}
        self.assertEqual((f["fund_name"], f["asof"], f["currency"], f["total_aum"]),
                         ("環球科技股票基金", "2026-03-31", "USD", 4.2e9))
        rows = c["holdings"]["rows"]
        self.assertEqual([r["name"] for r in rows], ["蘋果", "微軟", "輝達", "台積電", "博通"])
        self.assertEqual(rows[0]["weight"], 0.071)

    def test_summary_is_short_and_names_apply_review_paths(self):
        import extract_candidates as ec
        c = self.extract(facts=["Currency: $"], holdings=factsheets.DEFAULT_HOLDINGS[:3])
        lines = ec.summary_lines(c)
        self.assertLessEqual(len(lines), ec.MAX_SUMMARY_LINES)
        text = "\n".join(lines)
        self.assertIn("`F1.currency`", text)
        self.assertIn("`F1.holdings`", text)          # only 3 rows

    def test_cli_writes_three_files_and_protects_a_reviewed_draft(self):
        src = self.tmp / "pdfs"
        factsheets.make_upload_set(src, 2)
        out = self.tmp / "work"
        cmd = [sys.executable, str(_REPO_ROOT / "scripts" / "extract_candidates.py"), str(src),
               "--out-dir", str(out)]
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        for name in ("candidates.json", "candidates_summary.md", "holdings.json"):
            self.assertTrue((out / name).exists(), name)
        draft = json.loads((out / "holdings.json").read_text())
        self.assertEqual([f["fund_id"] for f in draft["funds"]], ["F1", "F2"])
        self.assertEqual(draft["funds"][0]["holdings"][0]["ticker_raw"], "AAPL")
        draft["funds"][0]["review_log"] = ["set F1.currency=USD"]
        (out / "holdings.json").write_text(json.dumps(draft))
        again = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        self.assertEqual(again.returncode, 1)
        self.assertIn("--force", again.stderr)
        forced = subprocess.run(cmd + ["--force"], capture_output=True, text=True, timeout=120)
        self.assertEqual(forced.returncode, 0, forced.stderr)

    def test_draft_feeds_the_listing_check_and_extract_holdings(self):
        import extract_candidates as ec
        from extract_holdings import filter_fund_holdings
        record = ec.draft_record(self.extract())
        kept, scope = filter_fund_holdings(record)       # legacy path: no resolution yet
        self.assertIn("AAPL", [h["ticker_normalized"] for h in kept])
        self.assertNotIn("2330 TT", [h["ticker_normalized"] for h in kept])
        self.assertEqual(scope["disclosure_depth"], 10)


@unittest.skipUnless(factsheets.have_reportlab() and _have_pdfplumber(),
                     "reportlab and pdfplumber are required")
class TestRenderPage(unittest.TestCase):
    def test_one_page_to_png(self):
        from render_page import render
        with tempfile.TemporaryDirectory() as tmp:
            pdf = factsheets.make_factsheet(Path(tmp) / "f.pdf", filler_pages=1)
            out = render(pdf, 2, dpi=60, out=Path(tmp) / "p2.png")
            self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            with self.assertRaises(ValueError):
                render(pdf, 9, out=Path(tmp) / "p9.png")


class TestApplyReview(unittest.TestCase):
    def _data(self):
        return {"funds": [{"fund_id": "F1", "currency": None, "benchmark": None,
                           "holdings": [{"name": f"N{i}", "ticker_raw": None, "isin": None,
                                         "weight": 0.01 * (i + 1)} for i in range(5)],
                           "review_flags": ["F1.currency", "F1.holdings[1]", "F1.holdings[3]"]}]}

    def test_set_append_delete_and_flags(self):
        from apply_review import apply
        data = self._data()
        apply(data, ["F1.currency=USD", "F1.holdings[3].weight=4.5%",
                     "F1.holdings[5].name=Visa Inc", "F1.holdings[5].weight=0.012"],
              ["F1.holdings[1]"])
        fund = data["funds"][0]
        self.assertEqual(fund["currency"], "USD")
        self.assertEqual([r["name"] for r in fund["holdings"]], ["N0", "N2", "N3", "N4", "Visa Inc"])
        self.assertEqual(fund["holdings"][2]["weight"], 0.045)
        self.assertEqual(fund["review_flags"], [])
        self.assertEqual(len(fund["review_log"]), 5)

    def test_bad_input_changes_nothing(self):
        import subprocess as sp
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.json"
            path.write_text(json.dumps(self._data()))
            before = path.read_bytes()
            for args in (["--set", "F1.holdings[0].weight=7"], ["--set", "F9.currency=USD"],
                         ["--set", "F1.colour=red"], ["--set", "F1.holdings[9].name=x"],
                         ["--delete", "F1.holdings[42]"]):
                with self.subTest(args=args):
                    run = sp.run([sys.executable, str(_REPO_ROOT / "scripts" / "apply_review.py"),
                                  "--holdings", str(path), *args],
                                 capture_output=True, text=True, timeout=60)
                    self.assertEqual(run.returncode, 1, run.stdout)
                    self.assertIn("nothing was changed", run.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_a_changed_row_is_resolved_again(self):
        from apply_review import apply
        data = self._data()
        data["funds"][0]["holdings"][0].update(resolution={"status": "unresolved_name"},
                                               ticker_resolved=None)
        apply(data, ["F1.holdings[0].ticker_raw=AAPL"], [])
        self.assertNotIn("resolution", data["funds"][0]["holdings"][0])


class TestShareClassFieldsSurviveP2(unittest.TestCase):
    """D1: the fund's own fund_isin and nav_per_share, recorded at 1a, reach the
    listing-checked holdings.json — a later run's consensus flow reads them."""

    def test_fields_survive_resolve_and_dedupe(self):
        import contextlib
        import io
        import os
        from unittest import mock
        import run_phase
        import runner_fixtures
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGAR_CONTACT_EMAIL": "intake-test@example.com"}):
            root = Path(tmp)
            work, replay = root / "work", root / "replay"
            runner_fixtures.build(work, replay)
            data = json.loads((work / "holdings.json").read_text())
            for i, f in enumerate(data["funds"], 1):
                f["fund_isin"], f["nav_per_share"] = f"LU000000000{i}", 100.0 + i
            (work / "holdings.json").write_text(json.dumps(data))
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = run_phase.main(["p2", "--work-dir", str(work), "--outputs-dir",
                                       str(root / "out"), "--replay-dir", str(replay)])
            self.assertEqual(code, 0, err.getvalue())
            funds = json.loads((work / "holdings.json").read_text())["funds"]
            self.assertTrue(all(f.get("holdings_us") for f in funds))
            self.assertEqual([(f["fund_isin"], f["nav_per_share"]) for f in funds[:2]],
                             [("LU0000000001", 101.0), ("LU0000000002", 102.0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
