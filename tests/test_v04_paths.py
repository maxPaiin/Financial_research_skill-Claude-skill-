"""
v0.4 C1 — runtime directories come from scripts/paths.py, so the skill runs
both in the claude.ai sandbox and under Claude Code CLI (F18).

    python -m unittest tests.test_v04_paths -v
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import paths  # noqa: E402

_ENV = ("FR_WORK_DIR", "FR_OUTPUTS_DIR", "FR_UPLOADS_DIR", "EDGAR_CACHE_DIR")


def _clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _ENV}
    env.update(extra)
    return env


class TestResolution(unittest.TestCase):
    def test_environment_variables_win(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
                os.environ, {"FR_WORK_DIR": f"{tmp}/w", "FR_OUTPUTS_DIR": f"{tmp}/o",
                             "FR_UPLOADS_DIR": f"{tmp}/u", "EDGAR_CACHE_DIR": f"{tmp}/c"}):
            self.assertEqual(paths.work_dir(), Path(f"{tmp}/w"))
            self.assertEqual(paths.outputs_dir(), Path(f"{tmp}/o"))
            self.assertEqual(paths.uploads_dir(), Path(f"{tmp}/u"))
            self.assertEqual(paths.cache_dir(), Path(f"{tmp}/c"))

    def test_cli_defaults_are_relative_to_the_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, _clean_env(), clear=True), \
                mock.patch.object(paths, "in_sandbox", return_value=False):
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                here = Path.cwd()
                self.assertEqual(paths.work_dir(), here / "fr_work")
                self.assertEqual(paths.outputs_dir(), here / "fr_outputs")
                self.assertEqual(paths.uploads_dir(), here / "fr_uploads")
                self.assertEqual(paths.cache_dir(), _REPO_ROOT / ".cache" / "edgar")
            finally:
                os.chdir(cwd)

    def test_sandbox_defaults(self):
        with mock.patch.dict(os.environ, _clean_env(), clear=True), \
                mock.patch.object(paths, "in_sandbox", return_value=True):
            self.assertEqual(paths.work_dir(), Path("/home/claude/work"))
            self.assertEqual(paths.outputs_dir(), Path("/mnt/user-data/outputs"))
            self.assertEqual(paths.uploads_dir(), Path("/mnt/user-data/uploads"))
            self.assertEqual(paths.cache_dir(), Path("/home/claude/work/.cache/edgar"))

    def test_resolved_on_every_call_not_at_import(self):
        with mock.patch.dict(os.environ, {"FR_WORK_DIR": "/tmp/a"}):
            first = paths.work_dir()
        with mock.patch.dict(os.environ, {"FR_WORK_DIR": "/tmp/b"}):
            self.assertNotEqual(paths.work_dir(), first)


class TestNoRuntimePathLiterals(unittest.TestCase):
    """C1 — structural test (spec §8.3): never delete."""

    _LITERAL = re.compile(r"/home/claude|/mnt/user-data")

    def test_only_paths_py_names_a_runtime_path(self):
        scripts = _REPO_ROOT / "scripts"
        offenders = sorted(str(p.relative_to(scripts)) for p in scripts.rglob("*.py")
                           if p.name != "paths.py"
                           and self._LITERAL.search(p.read_text(encoding="utf-8")))
        self.assertEqual(offenders, [])


class TestDefaultsReachTheScripts(unittest.TestCase):
    def test_layer1_writes_into_the_work_dir_by_default(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            holdings = tmp / "holdings.json"
            holdings.write_text(json.dumps({"funds": [], "unique_universe": [],
                                            "pit_snapshot_info": []}))
            run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / "layer1_report.py"),
                                  "--holdings", str(holdings)],
                                 capture_output=True, text=True, timeout=60,
                                 env=_clean_env(FR_WORK_DIR=str(tmp / "work")))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue((tmp / "work" / "layer1_extraction.md").exists())

    def test_every_cli_with_a_paths_default_starts(self):
        # Regression: a local `work_dir` in build_report.main() shadowed
        # paths.work_dir() and crashed the CLI before argument parsing.
        for script in ("build_report.py", "layer1_report.py", "layer2_report.py",
                       "layer3_report.py", "extract_candidates.py", "render_page.py",
                       "apply_review.py", "run_phase.py", "bundle.py"):
            with self.subTest(script=script):
                run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / script),
                                      "--help"], capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr[-400:])

    def test_provenance_defaults_to_the_work_dir(self):
        from providers import resolver
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"FR_WORK_DIR": tmp}):
            self.assertEqual(resolver.flush_provenance(), Path(tmp) / "data_provenance.json")

    def test_edgar_cache_defaults_to_paths_cache_dir(self):
        from providers.edgar_provider import EDGARProvider
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGAR_CACHE_DIR": f"{tmp}/edgar"}):
            p = EDGARProvider(offline=True)
            self.assertEqual(p._cache, Path(f"{tmp}/edgar"))
            self.assertTrue(p._cache.is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
