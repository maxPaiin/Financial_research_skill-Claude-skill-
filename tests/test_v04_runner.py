"""
v0.4 C6 + C7 — the phase runner: a dry run of p2–p4 on fixtures produces the
expected files and short summaries, state.json tracks progress, nothing stores
the contact email, and failures name the stage; the resume bundle round-trips.

Offline throughout (runner_fixtures.py + --replay-dir).

    python -m unittest tests.test_v04_runner -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TESTS = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_TESTS))

import run_phase  # noqa: E402
import runner_fixtures  # noqa: E402

EMAIL = "runner-test@example.com"


def _run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = run_phase.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class _Workspace(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.work, self.replay, self.outputs = root / "work", root / "replay", root / "out"
        runner_fixtures.build(self.work, self.replay)
        env = mock.patch.dict(os.environ, {"EDGAR_CONTACT_EMAIL": EMAIL})
        env.start()
        self.addCleanup(env.stop)

    def phase(self, name: str, *extra) -> tuple[int, str, str]:
        return _run(name, *extra, "--work-dir", str(self.work), "--outputs-dir",
                    str(self.outputs), "--replay-dir", str(self.replay), "--asof", "2026-10-01")


class TestDryRunP2ToP4(_Workspace):
    def test_files_summaries_and_state(self):
        expected = {
            "p2": ["holdings.json", "layer1_extraction.md"],
            "p3": ["overlap.json", "fundamentals.json", "screen_results.json",
                   "scores_per_stock.json", "benchmark_weights.json", "consensus.json",
                   "crowding_signals.json", "layer2_screening.md"],
            "p4": ["rankings.json", "etf_relative_strength.json"],
        }
        for phase, files in expected.items():
            with self.subTest(phase=phase):
                code, out, err = self.phase(phase)
                self.assertEqual(code, 0, err)
                for name in files:
                    self.assertTrue((self.work / name).exists(), name)
                lines = out.strip().splitlines()
                self.assertLessEqual(len(lines), run_phase.MAX_SUMMARY_LINES)
                self.assertTrue(lines[-1].startswith("Next: "), lines[-1])
                self.assertIn("Resume bundle: ", out)                       # C7

        state = json.loads((self.work / "state.json").read_text())
        self.assertEqual(state["completed_phases"], ["p2", "p3", "p4"])
        self.assertEqual(state["next"], "p5")
        self.assertTrue(state["input_hashes"]["p3:holdings.json"].startswith("sha256:"))

    def test_what_the_summaries_say(self):
        code, p2, _ = self.phase("p2")
        self.assertIn("Funds: 7 independent of 7", p2)
        self.assertIn("non_us_listing 7", p2)            # the 0700.HK rows
        code, p3, err = self.phase("p3")
        self.assertEqual(code, 0, err)
        self.assertIn("Consensus (active votes): N_eff", p3)
        self.assertIn("Bands: majority", p3)
        code, p4, err = self.phase("p4")
        self.assertEqual(code, 0, err)
        self.assertIn("Ranked ", p4)
        self.assertIn("M1 scope (industries in rankings.json): technology", p4)
        self.assertIn("M1 + M1b", p4)

    def test_pipeline_outputs_are_coherent(self):
        for phase in ("p2", "p3", "p4"):
            self.assertEqual(self.phase(phase)[0], 0)
        fundamentals = json.loads((self.work / "fundamentals.json").read_text())
        self.assertEqual(fundamentals["AAPL"]["source"], "edgar+yfinance")   # EDGAR offline
        self.assertEqual(fundamentals["MSFT"]["source"], "yfinance")
        bw = json.loads((self.work / "benchmark_weights.json").read_text())
        self.assertEqual(bw["F1"]["proxy"], "IXN")
        self.assertIsNone(bw["F6"]["proxy"])
        rankings = json.loads((self.work / "rankings.json").read_text())
        self.assertEqual(rankings["ranking_method"], "v0.4-consensus-bands")
        self.assertGreater(rankings["n_ranked"], 0)
        layer2 = (self.work / "layer2_screening.md").read_text()
        self.assertIn("## Consensus structure", layer2)

    def test_settings_persist_and_the_email_never_does(self):
        self.assertEqual(self.phase("p2")[0], 0)
        self.assertEqual(self.phase("p3", "--vote-basis", "presence")[0], 0)
        cfg = json.loads((self.work / "run_config.json").read_text())
        self.assertEqual(cfg["vote_basis"], "presence")
        self.assertEqual(json.loads((self.work / "consensus.json").read_text())["vote_basis"],
                         "presence")
        for path in self.work.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".md", ".txt"):
                self.assertNotIn(EMAIL, path.read_text(encoding="utf-8"), path.name)

    def test_every_phase_leaves_a_bundle_that_names_the_next_phase(self):
        # C7: the bundle is saved after state.json, so an interruption after
        # p4 resumes at p5 — with the same files the work dir holds.
        from bundle import load
        for phase in ("p2", "p3", "p4"):
            self.assertEqual(self.phase(phase)[0], 0)
        fresh = self.work.parent / "fresh"
        names, state = load(self.outputs / "work_bundle.zip", fresh)
        self.assertEqual(state["completed_phases"], ["p2", "p3", "p4"])
        self.assertEqual(state["next"], "p5")
        for name in ("rankings.json", "consensus.json", "run_config.json", "state.json"):
            self.assertIn(name, names)
            self.assertEqual((fresh / name).read_bytes(), (self.work / name).read_bytes(), name)
        self.assertFalse(any(n.endswith(".pdf") for n in names))

    def test_rerunning_an_earlier_phase_resets_later_ones(self):
        for phase in ("p2", "p3", "p4"):
            self.phase(phase)
        self.phase("p3")
        state = json.loads((self.work / "state.json").read_text())
        self.assertEqual(state["completed_phases"], ["p2", "p3"])
        self.assertEqual(state["next"], "p4")


class TestFailuresAndStatus(_Workspace):
    def test_a_phase_out_of_order_says_what_to_run(self):
        code, _, err = self.phase("p4")
        self.assertEqual(code, 1)
        self.assertIn("run p3 first", err)

    def test_a_failing_stage_is_named_with_its_stderr_tail(self):
        (self.work / "holdings.json").write_text("{not json")
        code, _, err = self.phase("p2")
        self.assertEqual(code, 1)
        self.assertIn("stage 1b-resolve (resolve_tickers.py) failed", err)
        self.assertLessEqual(len(err.splitlines()), run_phase._STDERR_TAIL + 2)

    def test_status_reports_progress_and_stale_inputs(self):
        self.phase("p2")
        self.phase("p3")
        holdings = self.work / "holdings.json"
        holdings.write_text(holdings.read_text() + "\n")
        code, out, _ = _run("status", "--work-dir", str(self.work))
        self.assertEqual(code, 0)
        self.assertIn("Completed: p2, p3; next: p4", out)
        self.assertIn("p3 (holdings.json changed since it ran)", out)

    def test_p5_and_p6(self):
        for phase in ("p2", "p3", "p4"):
            self.assertEqual(self.phase(phase)[0], 0)
        code, out, err = self.phase("p5")
        self.assertEqual(code, 0, err)
        self.assertIn("Not supplied (pairs judged insufficient): macro_factors.json", out)
        code, _, err = self.phase("p6")
        self.assertEqual(code, 1)
        self.assertIn("honest_framing.txt", err)
        (self.work / "honest_framing.txt").write_text(
            "This report analyzes seven funds. Consensus here means what these funds "
            "collectively hold at or above their benchmark weight.")
        code, out, err = self.phase("p6")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.outputs / "financial_research_report.pdf").exists())
        self.assertIn("Checkpoint gate: passed", out)
        self.assertIn("Resume bundle: ", out)                             # C7
        from bundle import load
        _, state = load(self.outputs / "work_bundle.zip", self.work.parent / "fresh")
        self.assertEqual(state["completed_phases"][-1], "p6")
        self.assertIsNone(state["next"])


class TestPhaseOne(unittest.TestCase):
    def test_p1_on_a_generated_zip(self):
        import zipfile
        import factsheets
        if not factsheets.have_reportlab():
            self.skipTest("reportlab not installed")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGAR_CONTACT_EMAIL": EMAIL}):
            tmp = Path(tmp)
            pdfs = factsheets.make_upload_set(tmp / "src", 7)
            upload = tmp / "funds.zip"
            with zipfile.ZipFile(upload, "w") as zf:
                for p in pdfs:
                    zf.write(p, p.name)
            uploads = tmp / "uploads"
            with mock.patch.dict(os.environ, {"FR_UPLOADS_DIR": str(uploads)}):
                code, out, err = _run("p1", str(upload), "--work-dir", str(tmp / "work"),
                                      "--outputs-dir", str(tmp / "out"))
            self.assertEqual(code, 0, err)
            self.assertIn("Stage 0: 7 PDF(s) ok (zip)", out)
            self.assertIn("Stage 1a: 7 factsheet(s) extracted", out)
            self.assertTrue((tmp / "work" / "candidates_summary.md").exists())
            cfg = json.loads((tmp / "work" / "run_config.json").read_text())
            self.assertEqual(cfg["pdf_dir"], str(uploads / "extracted"))


class TestResumeBundle(unittest.TestCase):
    """C7: save -> load restores identical files and names the next phase."""

    def _work(self, root: Path) -> Path:
        work = root / "work"
        (work / "rationale").mkdir(parents=True)
        (work / "pages").mkdir()
        (work / "state.json").write_text(json.dumps(
            {"version": "0.4", "completed_phases": ["p1", "p2", "p3", "p4"], "next": "p5",
             "input_hashes": {}}))
        (work / "rankings.json").write_text(json.dumps({"ranked": [{"ticker": "AAA"}]}))
        (work / "macro_checkpoint.md").write_text("Rates on hold. [Fed; Reuters]\n")
        (work / "honest_framing.txt").write_text("Framing.\n")
        (work / "rationale" / "AAA.txt").write_text("Rationale for AAA.\n")
        (work / "factsheet.pdf").write_bytes(b"%PDF-1.4 not carried")
        (work / "pages" / "f_p1.png").write_bytes(b"\x89PNG not carried")
        return work

    def test_round_trip_restores_identical_files(self):
        from bundle import load, members, save
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = self._work(root)
            names = save(work, root / "out" / "work_bundle.zip")
            self.assertEqual(sorted(names), ["honest_framing.txt", "macro_checkpoint.md",
                                             "rankings.json", "rationale/AAA.txt", "state.json"])
            fresh = root / "fresh"
            restored, state = load(root / "out" / "work_bundle.zip", fresh)
            self.assertEqual(sorted(restored), sorted(names))
            for name in names:
                self.assertEqual((fresh / name).read_bytes(), (work / name).read_bytes(), name)
            self.assertEqual(state["next"], "p5")
            self.assertFalse((fresh / "factsheet.pdf").exists())
            self.assertEqual(len(members(fresh)), len(names))

    def test_cli_load_names_the_next_phase(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = self._work(root)
            bundle = root / "b.zip"
            env = {**os.environ, "FR_WORK_DIR": str(work)}
            env.pop("EDGAR_CONTACT_EMAIL", None)
            script = str(_REPO_ROOT / "scripts" / "bundle.py")
            save = subprocess.run([sys.executable, script, "save", "--out", str(bundle)],
                                  capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(save.returncode, 0, save.stderr)
            env["FR_WORK_DIR"] = str(root / "restored")
            load = subprocess.run([sys.executable, script, "load", str(bundle)],
                                  capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(load.returncode, 0, load.stderr)
            self.assertIn("Next: run_phase.py p5", load.stdout)

    def test_unsafe_bundles_are_refused(self):
        import zipfile
        from bundle import BundleError, load
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for member in ("../state.json", "/abs/state.json", "inner.zip", "report.pdf",
                           "pages/f_p1.png", "deep/a/b.json"):
                with self.subTest(member=member):
                    bad = root / "bad.zip"
                    with zipfile.ZipFile(bad, "w") as zf:
                        zf.writestr(member, "{}")
                    with self.assertRaises(BundleError):
                        load(bad, root / "w")
                    self.assertFalse((root / "state.json").exists())

    def test_a_save_that_would_carry_the_email_is_refused(self):
        from bundle import BundleError, save
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGAR_CONTACT_EMAIL": EMAIL}):
            root = Path(tmp)
            work = self._work(root)
            (work / "notes.md").write_text(f"contact {EMAIL}\n")
            with self.assertRaises(BundleError):
                save(work, root / "b.zip")

    def test_bundle_names_no_checkpoint_i2(self):
        text = (_REPO_ROOT / "scripts" / "bundle.py").read_text(encoding="utf-8")
        self.assertNotIn("important_notice", text)


class TestRunnerNeverNamesTheNotice(unittest.TestCase):
    def test_i2(self):
        text = (_REPO_ROOT / "scripts" / "run_phase.py").read_text(encoding="utf-8")
        self.assertNotIn("important_notice", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
