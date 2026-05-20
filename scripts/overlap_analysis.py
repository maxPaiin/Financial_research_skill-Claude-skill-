"""
Stage 2a: Cross-fund overlap matrix.

Promoted from appendix-level (v1) to core pipeline component (v0.2).
Computes overlap metrics for every unique ticker; feeds the crowding signal.
"""

import json
import argparse
from pathlib import Path


def build_overlap(unique_universe: list[dict]) -> list[dict]:
    """Build the full overlap matrix from unique_universe."""
    rows = []
    for u in unique_universe:
        rows.append({
            "ticker": u["ticker"],
            "name": u.get("name"),
            "held_by": u["held_by"],
            "weights_by_fund": u["weights_by_fund"],
            "n_funds_holding": u["n_funds_holding"],
            "sum_of_weights": u.get("sum_of_weights", 0.0),
            "avg_weight": u.get("avg_weight", 0.0),
            "max_weight": u.get("max_weight", 0.0),
        })
    rows.sort(key=lambda r: (-r["n_funds_holding"], -r["avg_weight"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True, help="holdings.json with unique_universe")
    ap.add_argument("--out", required=True, help="Output overlap.json path")
    args = ap.parse_args()

    data = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    universe = data.get("unique_universe", [])

    overlap = build_overlap(universe)

    out = {
        "n_tickers": len(universe),
        "n_held_by_2plus": sum(1 for r in overlap if r["n_funds_holding"] >= 2),
        "n_held_by_5plus": sum(1 for r in overlap if r["n_funds_holding"] >= 5),
        "overlap": overlap,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Overlap matrix: {out['n_tickers']} tickers, "
          f"{out['n_held_by_2plus']} held by 2+, "
          f"{out['n_held_by_5plus']} held by 5+")


if __name__ == "__main__":
    main()
