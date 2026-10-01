"""
Phase runner (v0.4 C6): the deterministic stages, six phases, short summaries.

Each phase runs its stages as subprocesses and prints at most 15 summary lines
and the next step for Claude — so Claude never has to open a large JSON file,
and a run costs one tool call per phase instead of one per stage (F17).

  p1  Stage 0 validate_uploads (one .zip or a folder) · 1a extract_candidates
  —   Claude: 1a review (summary only; render_page + apply_review)
  p2  1b-resolve resolve_tickers · 1b-d extract_holdings --dedupe · 1e layer1_report
  p3  2a overlap · 2b fundamentals · 2d screen · 2e scores · 2f-i benchmark weights
      · 2f-ii consensus · 2f-iii exit liquidity · 2g layer2_report
  p4  3a build_rankings · 3a-bis-i etf_relative_strength
      · (D2, only with --prior-holdings) consensus_flow
  —   Claude: M1 + M1b, scoped to the ranked names' industries
  p5  3a-bis coherence_audit
  —   Claude: 3b cards, 3c framing, M2, M3, H1
  p6  3d layer3_report · Mg check_checkpoints · 4 build_report

After every phase the work dir is saved to <outputs>/work_bundle.zip (C7), so a
run interrupted anywhere continues from `bundle.py load` in a new session.

Usage:
  run_phase.py p1 <uploads.zip | folder> [--force]
  run_phase.py p2|p3|p4|p5|p6 [options]
  run_phase.py status

Options (stored in <work>/run_config.json and reused by later phases):
  --vote-basis active|presence, --vote-floor common|none   (p3, consensus_signal.py)
  --asof YYYY-MM-DD   request date for fundamentals (p3)
  --max-files N       Stage 0 upper bound, measurement runs only (p1)
  --prior-holdings P  an earlier run's holdings.json or work_bundle.zip (p4, D2):
                      consensus flow between the two snapshots
  --replay-dir DIR    offline run: DIR/sec_exchange.json, DIR/edgar_cache/,
                      DIR/yfinance/, DIR/benchmark_top_holdings.json, DIR/prices.json
  --work-dir / --outputs-dir   override paths.py for this run
  --email E           SEC contact email for this process only — never written to
                      run_config.json, state.json or any other file (or set
                      EDGAR_CONTACT_EMAIL)

Each phase writes <work>/state.json: {version, completed_phases, next,
input_hashes}. Rerunning a phase drops the later ones from completed_phases,
and `status` names any phase whose inputs changed since it ran.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from bundle import BUNDLE_NAME, BundleError, save as save_bundle  # noqa: E402
from paths import outputs_dir, work_dir  # noqa: E402

VERSION = "0.4"
PHASES = ("p1", "p2", "p3", "p4", "p5", "p6")
MAX_SUMMARY_LINES = 15
_STDERR_TAIL = 20
_CONFIG_KEYS = ("upload", "pdf_dir", "vote_basis", "vote_floor", "asof", "max_files",
                "replay_dir", "prior_holdings")

NEXT_STEP = {
    "p1": "Claude: read candidates_summary.md only; for each flagged path render that page "
          "(render_page.py) and fix it with apply_review.py — never guess currency or "
          "benchmark. Then: run_phase.py p2",
    "p2": "Claude: if rows need review, fix them only from what the page prints "
          "(apply_review.py) and rerun p2. Otherwise: run_phase.py p3",
    "p3": "run_phase.py p4",
    "p4": "Claude: M1 + M1b for the industries above -> macro_checkpoint.md, "
          "macro_factors.json, sector_logic.json. Then: run_phase.py p5",
    "p5": "Claude: 3b rationale cards (3 batches of 5 -> rationale/<TICKER>.txt), 3c "
          "honest_framing.txt, M2, M3, H1 checkpoints. Then: run_phase.py p6",
    "p6": "Tell the user the PDF and the checkpoint files are in the outputs directory; "
          "the work directory does not persist.",
}


class PhaseError(RuntimeError):
    """A stage failed or a prerequisite is missing; the message is for the user."""


# --- Context ----------------------------------------------------------------------

_PATH_KEYS = ("upload", "replay_dir", "prior_holdings")


class Run:
    # Every stage runs with cwd = the work dir, so a relative path from the command
    # line is resolved against the caller's directory here, before any stage sees it.
    def __init__(self, args: argparse.Namespace):
        self.work = (Path(args.work_dir) if args.work_dir else work_dir()).resolve()
        self.outputs = (Path(args.outputs_dir) if args.outputs_dir else outputs_dir()).resolve()
        self.work.mkdir(parents=True, exist_ok=True)
        self.config = self._load("run_config.json")
        for key in _CONFIG_KEYS:
            value = getattr(args, key, None)
            if value is not None:
                self.config[key] = str(Path(value).resolve()) if key in _PATH_KEYS else value
        self.config.setdefault("vote_basis", "active")
        self.config.setdefault("vote_floor", "common")
        self.env = dict(os.environ)
        if getattr(args, "email", None):
            self.env["EDGAR_CONTACT_EMAIL"] = args.email      # this process tree only
        replay = self.config.get("replay_dir")
        self.replay = Path(replay) if replay else None
        if self.replay:
            self.env["EDGAR_OFFLINE"] = "1"
            self.env["EDGAR_CACHE_DIR"] = str(self.replay / "edgar_cache")
            self.env["YF_REPLAY_DIR"] = str(self.replay / "yfinance")
        self.env["FR_WORK_DIR"] = str(self.work)
        self.env["FR_OUTPUTS_DIR"] = str(self.outputs)

    def path(self, name: str) -> Path:
        return self.work / name

    def _load(self, name: str) -> dict:
        p = self.work / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def read(self, name: str) -> dict:
        return self._load(name)

    def save_config(self) -> None:
        cfg = {"version": VERSION, **{k: self.config.get(k) for k in _CONFIG_KEYS}}
        _write_json(self.work / "run_config.json", cfg, self.env.get("EDGAR_CONTACT_EMAIL"))

    def require(self, *names: str, hint: str) -> None:
        missing = [n for n in names if not self.path(n).exists()]
        if missing:
            raise PhaseError(f"missing {', '.join(missing)} in {self.work} — {hint}")

    def script(self, stage: str, name: str, *argv) -> str:
        """Run one stage; return its stdout. Raise PhaseError with the stderr tail."""
        cmd = [sys.executable, str(_SCRIPTS / name), *[str(a) for a in argv]]
        run = subprocess.run(cmd, capture_output=True, text=True, env=self.env, cwd=self.work)
        if run.returncode != 0:
            tail = (run.stderr or run.stdout).strip().splitlines()[-_STDERR_TAIL:]
            raise PhaseError(f"stage {stage} ({name}) failed with exit code "
                             f"{run.returncode}:\n" + "\n".join("  " + t for t in tail))
        return run.stdout


def _write_json(path: Path, payload: dict, email: Optional[str]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if email and email.lower() in text.lower():
        raise PhaseError(f"refusing to write {path.name}: it would contain the contact email")
    path.write_text(text + "\n", encoding="utf-8")


def _sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# --- Phases -----------------------------------------------------------------------

def phase_p1(run: Run) -> list[str]:
    upload = run.config.get("upload")
    if not upload:
        raise PhaseError("p1 needs the upload: run_phase.py p1 <uploads.zip | folder>")
    argv = [upload, "--out", run.path("stage0_validation.json")]
    if run.config.get("max_files"):
        argv += ["--max-files", run.config["max_files"]]
    try:
        run.script("0", "validate_uploads.py", *argv)
    except PhaseError:
        stage0 = run.read("stage0_validation.json")
        if stage0.get("errors"):
            raise PhaseError("Stage 0 rejected the upload:\n" + "\n".join(
                "  " + e.splitlines()[0] for e in stage0["errors"][:_STDERR_TAIL]))
        raise
    stage0 = run.read("stage0_validation.json")
    pdf_dir = (stage0.get("input") or {}).get("pdf_dir") or upload
    run.config["pdf_dir"] = pdf_dir
    argv = [pdf_dir, "--out-dir", run.work] + (["--force"] if run.force else [])
    run.script("1a", "extract_candidates.py", *argv)
    cands = run.read("candidates.json")
    funds = cands.get("funds", [])
    flags = sum(len(f.get("flags", [])) for f in funds)
    lines = [f"Stage 0: {stage0.get('n_files')} PDF(s) ok ({(stage0.get('input') or {}).get('kind')})"
             + (f"; {len(stage0.get('advisories') or [])} regional advisory(ies)"
                if stage0.get("advisories") else "")]
    lines += [f"Stage 1a: {len(funds)} factsheet(s) extracted; {flags} field(s) flagged for review"]
    lines += [f"  {a.splitlines()[0][:150]}" for a in (stage0.get("advisories") or [])[:3]]
    lines += [f"Review file: {run.path('candidates_summary.md')}"]
    return lines


def _resolve_args(run: Run) -> list:
    argv = ["--holdings", run.path("holdings.json")]
    if run.replay:
        argv += ["--sec-file", run.replay / "sec_exchange.json", "--offline"]
    return argv


def phase_p2(run: Run) -> list[str]:
    run.require("holdings.json", hint="run p1 and review the flagged fields first")
    out = run.script("1b-resolve", "resolve_tickers.py", *_resolve_args(run))
    run.script("1b-d", "extract_holdings.py", "--input", run.path("holdings.json"), "--dedupe")
    argv = ["--holdings", run.path("holdings.json"), "--out", run.path("layer1_extraction.md")]
    if run.path("stage0_validation.json").exists():
        argv += ["--stage0", run.path("stage0_validation.json")]
    run.script("1e", "layer1_report.py", *argv)
    data = run.read("holdings.json")
    funds = data.get("funds", [])
    accepted = [f for f in funds if not f.get("rejected") and not f.get("merged_into")]
    counts: dict[str, int] = {}
    for f in funds:
        for status, n in ((f.get("scope_summary") or {}).get("resolution_counts") or {}).items():
            counts[status] = counts.get(status, 0) + n
    review = [ln.strip() for ln in out.splitlines() if ".holdings[" in ln][:6]
    lines = [f"Funds: {len(accepted)} independent of {len(funds)} "
             f"({sum(1 for f in funds if f.get('rejected'))} rejected, "
             f"{sum(1 for f in funds if f.get('merged_into'))} merged share classes)",
             "Listing check: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                                  or "legacy format check only"),
             f"Universe: {data.get('universe_size', 0)} unique US-listed tickers",
             f"Layer 1: {run.path('layer1_extraction.md')}"]
    if review:
        lines += [f"Rows needing review ({sum(1 for ln in out.splitlines() if '.holdings[' in ln)}):"]
        lines += ["  " + r[:150] for r in review]
    return lines


def phase_p3(run: Run) -> list[str]:
    run.require("holdings.json", hint="run p2 first")
    if not run.read("holdings.json").get("unique_universe"):
        raise PhaseError("holdings.json has no unique_universe — run p2 first")
    w = run.path
    run.script("2a", "overlap_analysis.py", "--holdings", w("holdings.json"), "--out", w("overlap.json"))
    argv = ["--holdings", w("holdings.json"), "--out", w("fundamentals.json")]
    if run.config.get("asof"):
        argv += ["--asof", run.config["asof"]]
    run.script("2b", "fetch_fundamentals.py", *argv)
    run.script("2d", "quality_screen.py", "--holdings", w("holdings.json"), "--fundamentals",
               w("fundamentals.json"), "--unscored", w("unscored_tickers.json"),
               "--out", w("screen_results.json"))
    run.script("2e", "compute_scores.py", "--fundamentals", w("fundamentals.json"), "--screen",
               w("screen_results.json"), "--out", w("scores_per_stock.json"))
    argv = ["--holdings", w("holdings.json"), "--out", w("benchmark_weights.json")]
    if run.replay and (run.replay / "benchmark_top_holdings.json").exists():
        argv += ["--replay", run.replay / "benchmark_top_holdings.json"]
    run.script("2f-i", "benchmark_weights.py", *argv)
    run.script("2f-ii", "consensus_signal.py", "--holdings", w("holdings.json"),
               "--benchmark-weights", w("benchmark_weights.json"),
               "--vote-basis", run.config["vote_basis"], "--vote-floor", run.config["vote_floor"],
               "--out", w("consensus.json"))
    run.script("2f-iii", "crowding_signal.py", "--overlap", w("overlap.json"), "--holdings",
               w("holdings.json"), "--fundamentals", w("fundamentals.json"),
               "--out", w("crowding_signals.json"))
    run.script("2g", "layer2_report.py", "--overlap", w("overlap.json"), "--screen",
               w("screen_results.json"), "--fundamentals", w("fundamentals.json"),
               "--crowding", w("crowding_signals.json"), "--scores", w("scores_per_stock.json"),
               "--consensus", w("consensus.json"), "--out", w("layer2_screening.md"))
    screen, scores = run.read("screen_results.json"), run.read("scores_per_stock.json")
    con, crowd = run.read("consensus.json"), run.read("crowding_signals.json")
    bands: dict[str, int] = {}
    for r in con.get("stocks", []):
        bands[r["band"]] = bands.get(r["band"], 0) + 1
    floor = con.get("vote_floor")
    return [
        f"Fundamentals: {len(run.read('fundamentals.json'))} fetched; "
        f"{screen.get('n_unscored', 0)} unavailable",
        f"Screen: {screen.get('n_passed', 0)} passed, {screen.get('n_failed', 0)} failed; "
        f"{scores.get('n_unscored_no_roe', 0)} passed but unscored (no ROE)",
        f"Consensus ({con.get('vote_basis')} votes): N_eff {con.get('n_eff_run', 0):.2f} of "
        f"{con.get('n_funds', 0)} funds; floor "
        + (f"{floor:.2%}" if isinstance(floor, (int, float)) else "off"),
        "Bands: " + ", ".join(f"{b} {bands.get(b, 0)}" for b in ("majority", "plural", "single", "none")),
        "Benchmark-anchored core: " + (", ".join(con.get("anchored_core") or []) or "none"),
        f"Exit-crowded (>= 10 days): "
        + (", ".join(s["ticker"] for s in crowd.get("signals", []) if s.get("is_exit_crowded"))
           or "none"),
        f"Layer 2: {w('layer2_screening.md')}",
    ]


def phase_p4(run: Run) -> list[str]:
    run.require("scores_per_stock.json", "consensus.json", "overlap.json", hint="run p3 first")
    w = run.path
    run.script("3a", "build_rankings.py", "--scores", w("scores_per_stock.json"), "--consensus",
               w("consensus.json"), "--overlap", w("overlap.json"), "--out", w("rankings.json"))
    argv = ["--rankings", w("rankings.json"), "--out", w("etf_relative_strength.json")]
    if run.replay and (run.replay / "prices.json").exists():
        argv += ["--prices", run.replay / "prices.json"]
    run.script("3a-bis-i", "etf_relative_strength.py", *argv)
    rk, etf = run.read("rankings.json"), run.read("etf_relative_strength.json")
    ranked = rk.get("ranked", [])
    industries: dict[str, int] = {}
    for r in ranked:
        key = r.get("industry") or "other"
        industries[key] = industries.get(key, 0) + 1
    lines = [f"Ranked {rk.get('n_ranked', 0)} of {rk.get('n_eligible', 0)} eligible: "
             + " ".join(f"{r['rank']}.{r['ticker']}({r['band'][0]})" for r in ranked[:15])]
    if rk.get("warning") == "few_eligible":
        lines += ["WARNING few_eligible: tell the user; offer to rerun p3 and p4 with "
                  "--vote-basis presence (never switch silently)"]
    lines += ["M1 scope (industries in rankings.json): "
              + ", ".join(f"{k} {v}" for k, v in sorted(industries.items(), key=lambda kv: (-kv[1], kv[0])))]
    n_ok = sum(1 for s in (etf.get("stocks") or {}).values() if s.get("status") == "ok")
    lines += [f"ETF relative strength: {n_ok}/{etf.get('n_stocks', 0)} stocks measured"]
    if run.config.get("prior_holdings"):
        lines += _consensus_flow(run, {r["ticker"]: r.get("band") for r in ranked})
    return lines


def _consensus_flow(run: Run, bands: dict[str, str]) -> list[str]:
    """D2: drift-adjusted flow against the prior snapshot; the overlay reads it at p5."""
    w = run.path
    argv = ["--holdings", w("holdings.json"), "--prior-holdings", run.config["prior_holdings"],
            "--consensus", w("consensus.json"), "--out", w("consensus_flow.json")]
    if w("benchmark_weights.json").exists():
        argv += ["--benchmark-weights", w("benchmark_weights.json")]
    run.script("D2", "consensus_flow.py", *argv)
    flow = run.read("consensus_flow.json")
    c = flow.get("counts") or {}
    lines = [f"Consensus flow: {flow.get('n_comparable_funds', 0)} of {flow.get('n_funds', 0)} "
             f"funds comparable; building {c.get('building', 0)}, unwinding "
             f"{c.get('unwinding', 0)}, mixed {c.get('mixed', 0)}, insufficient "
             f"{c.get('insufficient', 0)}"]
    unwound = [s["ticker"] for s in flow.get("stocks", [])
               if s.get("state") == "unwinding" and bands.get(s["ticker"]) == "majority"]
    if unwound:
        lines += [f"  majority band being unwound: "
                  f"{', '.join(unwound)}"]
    excluded = flow.get("excluded_funds") or []
    if excluded:
        lines += ["  excluded: " + "; ".join(f"{e['fund_id']} ({e['reason']})"
                                             for e in excluded[:3])]
    return lines


def phase_p5(run: Run) -> list[str]:
    run.require("rankings.json", hint="run p4 first")
    w = run.path
    argv = ["--rankings", w("rankings.json"), "--out", w("coherence.json")]
    for flag, name in (("--macro", "macro_factors.json"), ("--sector-logic", "sector_logic.json"),
                       ("--etf", "etf_relative_strength.json"),
                       ("--crowding", "crowding_signals.json")):
        if w(name).exists():
            argv += [flag, w(name)]
    run.script("3a-bis", "coherence_audit.py", *argv)
    coh = run.read("coherence.json")
    missing = [n for n in ("macro_factors.json", "sector_logic.json") if not w(n).exists()]
    lines = [f"Coherence: {coh.get('n_demoted', 0)} demoted (rank unchanged), "
             f"{coh.get('n_exit_liquidity_risks', 0)} exit-liquidity risk(s), "
             f"{coh.get('n_insufficient', 0)} with insufficient data"]
    for r in coh.get("records", []):
        if r.get("tier_delta", 0) < 0:
            lines.append(f"  #{r['rank']} {r['ticker']}: {r['base_tier']}->{r['tier']}")
    if missing:
        lines += [f"Not supplied (pairs judged insufficient): {', '.join(missing)}"]
    return lines[:MAX_SUMMARY_LINES - 1]


def phase_p6(run: Run) -> list[str]:
    run.require("rankings.json", "honest_framing.txt",
                hint="write honest_framing.txt (Stage 3c) and the rationale cards (3b) first")
    w = run.path
    argv = ["--rankings", w("rankings.json"), "--framing", w("honest_framing.txt"),
            "--out", w("layer3_ranked_advice.md")]
    if w("rationale").is_dir():
        argv += ["--rationale-dir", w("rationale")]
    for flag, name in (("--coherence", "coherence.json"), ("--crowding", "crowding_signals.json")):
        if w(name).exists():
            argv += [flag, w(name)]
    run.script("3d", "layer3_report.py", *argv)
    gate = subprocess.run([sys.executable, str(_SCRIPTS / "check_checkpoints.py"), str(run.work)],
                          capture_output=True, text=True, env=run.env)
    if gate.returncode != 0:
        try:
            problems = json.loads(gate.stdout).get("problems", [])
        except json.JSONDecodeError:
            problems = gate.stdout.splitlines()
        raise PhaseError("stage Mg (check_checkpoints.py) failed — fix these checkpoints, then "
                         "rerun p6:\n" + "\n".join("  " + p for p in problems[:_STDERR_TAIL]))
    pdf = run.outputs / "financial_research_report.pdf"
    run.script("4", "build_report.py", "--work-dir", run.work, "--out", pdf,
               "--outputs-dir", run.outputs)
    copied = sorted(p.name for p in run.outputs.glob("*") if p.name not in (pdf.name, BUNDLE_NAME))
    return [f"Layer 3: {w('layer3_ranked_advice.md')}",
            "Checkpoint gate: passed",
            f"PDF: {pdf}",
            f"Copied to outputs: {len(copied)} file(s)"]


RUNNERS: dict[str, Callable[[Run], list[str]]] = {
    "p1": phase_p1, "p2": phase_p2, "p3": phase_p3, "p4": phase_p4, "p5": phase_p5, "p6": phase_p6,
}

# Files each phase consumes (for state.json input_hashes and `status`).
PHASE_INPUTS = {
    "p1": [],
    "p2": ["holdings.json"],
    "p3": ["holdings.json"],
    "p4": ["scores_per_stock.json", "consensus.json", "overlap.json"],
    "p5": ["rankings.json", "macro_factors.json", "sector_logic.json",
           "etf_relative_strength.json", "crowding_signals.json"],
    "p6": ["rankings.json", "coherence.json", "honest_framing.txt"],
}


def update_state(run: Run, phase: str, hashes_before: dict[str, Optional[str]]) -> dict:
    state = run.read("state.json") or {}
    done = [p for p in state.get("completed_phases", []) if PHASES.index(p) < PHASES.index(phase)]
    done.append(phase)
    hashes = dict(state.get("input_hashes") or {})
    hashes.update({f"{phase}:{name}": h for name, h in hashes_before.items() if h})
    nxt = PHASES[PHASES.index(phase) + 1] if phase != PHASES[-1] else None
    state = {"version": VERSION, "completed_phases": done, "next": nxt, "input_hashes": hashes}
    _write_json(run.path("state.json"), state, run.env.get("EDGAR_CONTACT_EMAIL"))
    return state


def resume_bundle(run: Run) -> str:
    """C7: saved after state.json is updated, so the bundle names the right next phase."""
    out = run.outputs / BUNDLE_NAME
    try:
        save_bundle(run.work, out, email=run.env.get("EDGAR_CONTACT_EMAIL"))
    except BundleError as e:
        return f"Resume bundle not saved: {e}"
    return f"Resume bundle: {out}"


def status(run: Run) -> list[str]:
    state = run.read("state.json")
    lines = [f"Work dir: {run.work}", f"Outputs:  {run.outputs}"]
    if not state:
        return lines + ["No phase has run yet. Start with: run_phase.py p1 <uploads.zip>"]
    lines += [f"Completed: {', '.join(state.get('completed_phases') or []) or 'none'}; "
              f"next: {state.get('next') or 'done'}"]
    stale = []
    for key, recorded in (state.get("input_hashes") or {}).items():
        phase, _, name = key.partition(":")
        if phase in (state.get("completed_phases") or []) and _sha256(run.path(name)) != recorded:
            stale.append(f"{phase} ({name} changed since it ran)")
    if stale:
        lines += ["Stale — rerun: " + "; ".join(stale)]
    cfg = {k: run.config.get(k) for k in ("vote_basis", "vote_floor", "replay_dir") if run.config.get(k)}
    lines += ["Settings: " + ", ".join(f"{k}={v}" for k, v in cfg.items())]
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run one deterministic phase of the pipeline")
    ap.add_argument("phase", choices=PHASES + ("status",))
    ap.add_argument("upload", nargs="?", help="p1: the uploaded .zip (or a folder of PDFs)")
    ap.add_argument("--force", action="store_true", help="p1: replace a reviewed holdings.json")
    ap.add_argument("--vote-basis", choices=("active", "presence"))
    ap.add_argument("--vote-floor", choices=("common", "none"))
    ap.add_argument("--asof", help="p3: request date for fundamentals (YYYY-MM-DD)")
    ap.add_argument("--max-files", type=int, help="p1: Stage 0 upper bound (measurement only)")
    ap.add_argument("--prior-holdings",
                    help="p4: an earlier run's holdings.json or work_bundle.zip (consensus flow)")
    ap.add_argument("--replay-dir", help="offline run from recorded inputs")
    ap.add_argument("--work-dir")
    ap.add_argument("--outputs-dir")
    ap.add_argument("--email", help="SEC contact email for this run only (never stored)")
    args = ap.parse_args(argv)

    run = Run(args)
    run.force = args.force
    if args.phase == "status":
        print("\n".join(status(run)))
        return 0

    hashes_before = {name: _sha256(run.path(name)) for name in PHASE_INPUTS[args.phase]}
    try:
        lines = RUNNERS[args.phase](run)
    except PhaseError as e:
        print(f"{args.phase} FAILED — {e}", file=sys.stderr)
        return 1
    run.save_config()
    state = update_state(run, args.phase, hashes_before)
    lines = lines[:MAX_SUMMARY_LINES - 3] + [resume_bundle(run)]
    print(f"{args.phase} done.")
    print("\n".join(lines))
    print(f"Next: {NEXT_STEP[args.phase]}" + (f" (state: next={state['next']})" if state["next"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
