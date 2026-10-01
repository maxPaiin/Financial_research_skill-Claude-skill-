"""
Resume bundle (v0.4 C7): carry one run across two usage windows.

On claude.ai the work directory is ephemeral; a long run can also outlast a
usage window. `save` packs everything a later session needs to continue —
never the PDFs — into the user-visible outputs directory; `load` restores it
and says which phase comes next.

  save           <work>/*.json, *.md, *.txt (the framing) and rationale/*.txt
                 -> <outputs>/work_bundle.zip
  load <zip>     restore those files into <work>; print state.json's next phase

The bundle is matched by pattern only — it never names a particular
checkpoint. A member outside the allowed patterns, a path that would land
outside the work directory, or a nested archive is refused on load. A save
that would contain the SEC contact email (from EDGAR_CONTACT_EMAIL) is refused.

Usage:
  bundle.py save [--work-dir DIR] [--out ZIP]
  bundle.py load <work_bundle.zip> [--work-dir DIR]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import outputs_dir, work_dir  # noqa: E402

BUNDLE_NAME = "work_bundle.zip"
PATTERNS = ("*.json", "*.md", "*.txt", "rationale/*.txt", "rationale/*.md")
_MAX_BYTES = 200 * 1024 * 1024


class BundleError(ValueError):
    pass


def _wanted(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in PATTERNS) and rel.count("/") <= 1


def members(work: Path) -> list[Path]:
    """Files a bundle carries, relative to the work dir, sorted."""
    found = []
    for path in sorted(work.rglob("*")):
        if path.is_file():
            rel = path.relative_to(work).as_posix()
            if _wanted(rel):
                found.append(path)
    return found


def save(work: Path, out: Path, email: str | None = None) -> list[str]:
    """Zip the work dir's checkpoint files to `out`; refuse if one holds the email
    (`email`, else EDGAR_CONTACT_EMAIL)."""
    files = members(work)
    if not files:
        raise BundleError(f"nothing to save in {work}")
    email = (email if email is not None else os.environ.get("EDGAR_CONTACT_EMAIL") or "")
    email = email.strip().lower()
    if email:
        for f in files:
            if email in f.read_text(encoding="utf-8", errors="ignore").lower():
                raise BundleError(f"refusing to save: {f.name} contains the contact email")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(work).as_posix())
    tmp.replace(out)
    return [f.relative_to(work).as_posix() for f in files]


def load(bundle: Path, work: Path) -> tuple[list[str], dict]:
    """Restore a bundle into `work`; return (restored names, state)."""
    try:
        zf = zipfile.ZipFile(bundle)
    except zipfile.BadZipFile as e:
        raise BundleError(f"'{bundle.name}' is not a readable bundle ({e})")
    with zf:
        plan = []
        total = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
                raise BundleError(f"'{info.filename}' points outside the work directory")
            if name.lower().endswith((".zip", ".pdf")) or not _wanted(name):
                raise BundleError(f"'{info.filename}' is not something a work bundle carries")
            total += info.file_size
            if total > _MAX_BYTES:
                raise BundleError("the bundle expands beyond 200 MB")
            plan.append((info, name))
        work.mkdir(parents=True, exist_ok=True)
        for info, name in plan:
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src:
                target.write_bytes(src.read())
    state_path = work / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    return [n for _, n in plan], state


def main() -> int:
    ap = argparse.ArgumentParser(description="Save or load a resume bundle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("--work-dir")
    s.add_argument("--out", help=f"Default: <outputs>/{BUNDLE_NAME}")
    lo = sub.add_parser("load")
    lo.add_argument("bundle")
    lo.add_argument("--work-dir")
    args = ap.parse_args()

    work = Path(args.work_dir) if args.work_dir else work_dir()
    try:
        if args.cmd == "save":
            out = Path(args.out) if args.out else outputs_dir() / BUNDLE_NAME
            names = save(work, out)
            print(f"Saved {len(names)} file(s) to {out} — give this file back in a new "
                  "session to continue the run.")
        else:
            names, state = load(Path(args.bundle), work)
            nxt = state.get("next")
            done = ", ".join(state.get("completed_phases") or []) or "none"
            print(f"Restored {len(names)} file(s) into {work}. Completed: {done}. "
                  + (f"Next: run_phase.py {nxt}" if nxt else "The run is complete."))
    except BundleError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
