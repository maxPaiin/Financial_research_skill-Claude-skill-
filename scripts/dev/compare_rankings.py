"""
Dev tool (v0.4 §9): v0.33 and v0.4 rankings of one input set, side by side.

    python scripts/dev/compare_rankings.py --work-dir fr_work
    python scripts/dev/compare_rankings.py --work-dir fr_work --vote-basis presence

Reads a finished work directory (holdings, scores, overlap, consensus and
benchmark weights). The v0.33 column comes from legacy_v033.py; the v0.4 column
is recomputed with the requested vote basis, so one directory answers both
comparisons the validation procedure asks for. Prints N_eff_run, the floor,
vote-basis coverage, the anchored core, and where each name moved.

Never imported by the pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_rankings  # noqa: E402
import consensus_signal  # noqa: E402
from legacy_v033 import legacy_rank  # noqa: E402


def _load(work: Path, name: str, required: bool = True):
    path = work / name
    if not path.exists():
        if required:
            raise SystemExit(f"missing {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compare(work: Path, vote_basis: str = "active") -> list[str]:
    holdings, scores = _load(work, "holdings.json"), _load(work, "scores_per_stock.json")
    overlap = _load(work, "overlap.json")
    bench = _load(work, "benchmark_weights.json", required=False)
    consensus = consensus_signal.compute(holdings, bench, vote_basis)
    v04 = build_rankings.rank(scores, consensus, overlap)
    v033 = legacy_rank(scores, overlap, holdings)

    old_rank = {r["ticker"]: r["rank"] for r in v033["ranked"]}
    new_rank = {r["ticker"]: r["rank"] for r in v04["ranked"]}
    lines = [f"v0.33 legacy composite                | v0.4 consensus bands ({vote_basis} votes)"]
    for i in range(max(len(v033["ranked"]), len(v04["ranked"]))):
        left = v033["ranked"][i] if i < len(v033["ranked"]) else None
        right = v04["ranked"][i] if i < len(v04["ranked"]) else None
        lt = f"{left['rank']:>2} {left['ticker']:<6} composite {left['composite_score']:6.2f}" if left else ""
        rt = (f"{right['rank']:>2} {right['ticker']:<6} {right['band']:<8} "
              f"c={right['c_share']:.2f} Q''={right['q_shrunk']:.1f}") if right else ""
        lines.append(f"{lt:<38}| {rt}")
    cov = consensus["vote_basis_coverage"]
    floor = consensus["vote_floor"]
    lines += ["",
              f"N_eff_run {consensus['n_eff_run']:.2f} of {consensus['n_funds']} funds | floor "
              f"{f'{floor:.2%}' if floor is not None else 'off'} | coverage "
              + ", ".join(f"{k} {v}" for k, v in cov.items()),
              "Anchored core: " + (", ".join(consensus["anchored_core"]) or "none"),
              "Moves:"]
    anchored = set(consensus["anchored_core"])
    for t in sorted(set(old_rank) | set(new_rank)):
        o, n = old_rank.get(t), new_rank.get(t)
        if o == n:
            continue
        where = (f"#{n}" if n else ("anchored core" if t in anchored else "not ranked"))
        lines.append(f"  {t:<6} v0.33 {'#' + str(o) if o else 'not ranked':<11} -> v0.4 {where}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--vote-basis", choices=("active", "presence"), default="active")
    args = ap.parse_args()
    print("\n".join(compare(Path(args.work_dir), args.vote_basis)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
