"""
Runtime directories (v0.4 C1) — the one place that knows where things live.

The skill runs in two environments:

  claude.ai sandbox      detected by /mnt/user-data/outputs existing
      work      /home/claude/work           (ephemeral; resets between sessions)
      outputs   /mnt/user-data/outputs      (user-visible, downloadable)
      uploads   /mnt/user-data/uploads      (the user's uploaded files)
      cache     /home/claude/work/.cache/edgar

  anywhere else, e.g. Claude Code CLI       (relative to the current directory)
      work      ./fr_work
      outputs   ./fr_outputs
      uploads   ./fr_uploads
      cache     <repo>/.cache/edgar

Each is overridden by an environment variable: FR_WORK_DIR, FR_OUTPUTS_DIR,
FR_UPLOADS_DIR, EDGAR_CACHE_DIR. Values are resolved on every call, never at
import, so a test or a runner can set the environment first. No other file in
scripts/ may name a runtime path (TestNoRuntimePathLiterals).
"""

from __future__ import annotations

import os
from pathlib import Path

_SANDBOX_OUTPUTS = Path("/mnt/user-data/outputs")
_SANDBOX_UPLOADS = Path("/mnt/user-data/uploads")
_SANDBOX_WORK = Path("/home/claude/work")
_REPO_ROOT = Path(__file__).resolve().parents[1]


def in_sandbox() -> bool:
    """True inside the claude.ai sandbox (its outputs mount exists)."""
    return _SANDBOX_OUTPUTS.exists()


def _resolve(env: str, sandbox: Path, local_name: str) -> Path:
    value = os.environ.get(env)
    if value:
        return Path(value).expanduser()
    return sandbox if in_sandbox() else Path.cwd() / local_name


def work_dir() -> Path:
    """Working files: JSON stages, checkpoints, rationale cards, state.json."""
    return _resolve("FR_WORK_DIR", _SANDBOX_WORK, "fr_work")


def outputs_dir() -> Path:
    """What the user can download: the PDF, checkpoint copies, the resume bundle."""
    return _resolve("FR_OUTPUTS_DIR", _SANDBOX_OUTPUTS, "fr_outputs")


def uploads_dir() -> Path:
    """Where uploads arrive; a .zip is extracted under <uploads>/extracted."""
    return _resolve("FR_UPLOADS_DIR", _SANDBOX_UPLOADS, "fr_uploads")


def cache_dir() -> Path:
    """EDGAR cache. In the sandbox the skill directory may be read-only, so the
    cache lives in the work dir there; elsewhere it persists in the repo."""
    value = os.environ.get("EDGAR_CACHE_DIR")
    if value:
        return Path(value).expanduser()
    return (_SANDBOX_WORK / ".cache" / "edgar") if in_sandbox() else (
        _REPO_ROOT / ".cache" / "edgar")
