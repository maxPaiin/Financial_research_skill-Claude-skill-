"""
v0.4 A7 (+ B5 later) — ranking determinism.

I10: the same inputs produce a byte-identical rankings.json. Every sort that
decides a rank uses the ticker as its last key, so tied scores never order by
the position a stock happened to have in an input file.

    python -m unittest tests.test_v04_ranking -v
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "build_rankings.py"
sys.path.insert(0, str(_REPO_ROOT / "scripts"))


def _inputs(n: int = 24) -> tuple[dict, dict, dict]:
    """A universe with deliberate ties: three quality levels, two signals."""
    tickers = [f"T{i:02d}" for i in range(n)]
    stocks = {
        t: {"ticker": t, "status": "ok", "fundamental_quality_score": [40.0, 60.0, 80.0][i % 3],
            "quality_confidence": 0.9, "roe_years": 5, "roe_source": "edgar",
            "industry": "technology", "roe_5y_avg": 0.2}
        for i, t in enumerate(tickers)
    }
    crowding = {"signals": [{"ticker": t, "signal": [1.0, 2.0][i % 2]}
                            for i, t in enumerate(tickers)]}
    overlap = {"overlap": [{"ticker": t, "name": f"Name {t}", "held_by": ["F1", "F2"],
                            "weights_by_fund": {"F1": 0.03, "F2": 0.02},
                            "n_funds_holding": 2, "avg_weight": 0.025, "max_weight": 0.03,
                            "sum_of_weights": 0.05} for t in tickers]}
    return {"stocks": stocks}, crowding, overlap


def _shuffled(scores: dict, crowding: dict, overlap: dict, seed: int):
    rng = random.Random(seed)
    items = list(scores["stocks"].items())
    rng.shuffle(items)
    signals, rows = list(crowding["signals"]), list(overlap["overlap"])
    rng.shuffle(signals)
    rng.shuffle(rows)
    return {"stocks": dict(items)}, {"signals": signals}, {"overlap": rows}


def _run(tmp: Path, tag: str, scores: dict, crowding: dict, overlap: dict) -> bytes:
    paths = {}
    for name, payload in (("scores", scores), ("crowding", crowding), ("overlap", overlap)):
        paths[name] = tmp / f"{tag}_{name}.json"
        paths[name].write_text(json.dumps(payload), encoding="utf-8")
    out = tmp / f"{tag}_rankings.json"
    run = subprocess.run([sys.executable, str(_SCRIPT), "--scores", str(paths["scores"]),
                          "--crowding", str(paths["crowding"]),
                          "--overlap", str(paths["overlap"]), "--out", str(out)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return out.read_bytes()


class TestDeterministicRanking(unittest.TestCase):
    """I10 — structural test (spec §8.3): never delete."""

    def test_shuffled_inputs_give_a_byte_identical_rankings_json(self):
        base = _inputs()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reference = _run(tmp, "base", *base)
            for seed in range(5):
                with self.subTest(seed=seed):
                    self.assertEqual(_run(tmp, f"s{seed}", *_shuffled(*base, seed)), reference)

    def test_ties_break_by_ticker(self):
        import build_rankings
        ranked = build_rankings.rank(*_inputs())["ranked"]
        keys = [(-r["composite_score"], r["ticker"]) for r in ranked]
        self.assertEqual(keys, sorted(keys))


if __name__ == "__main__":
    unittest.main(verbosity=2)
