"""
v0.4 A7 + B5 — the ranking: an ordering of keys, deterministic.

B5: eligible stocks are ordered by (consensus band, -Q'', -c_share, ticker);
up to 15 are ranked; nothing below reads a top-down or price input.
A7 / I10: the same inputs give a byte-identical rankings.json.

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
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "dev"))

import build_rankings  # noqa: E402


def _score(t: str, q: float, conf: float = 0.9, status: str = "ok") -> dict:
    return {"ticker": t, "status": status, "fundamental_quality_score": q,
            "quality_confidence": conf, "roe_years": 5, "roe_source": "edgar",
            "industry": "technology", "roe_5y_avg": 0.2, "data_confidence": conf}


def _con(t: str, band: str, c_share: float, n_votes: int) -> dict:
    return {"ticker": t, "band": band, "c_share": c_share, "opinions": c_share * 3,
            "n_votes": n_votes, "n_holders": max(n_votes, 1),
            "vote_basis_counts": {"active": n_votes, "presence": 0, "anchored": 0,
                                  "below_floor": 0}}


def _consensus(rows: list[dict], **kw) -> dict:
    return {"vote_basis": "active", "n_funds": 8, "n_eff_run": 3.0, "vote_floor": 0.03,
            "stocks": rows, "anchored_core": kw.get("anchored", [])}


def _inputs(n: int = 24) -> tuple[dict, dict, dict]:
    """A universe with deliberate ties: three bands, three quality levels."""
    tickers = [f"T{i:02d}" for i in range(n)]
    scores = {"stocks": {t: _score(t, [40.0, 60.0, 80.0][i % 3]) for i, t in enumerate(tickers)}}
    consensus = _consensus([_con(t, ["majority", "plural", "single"][i % 3],
                                 [0.6, 0.3, 0.1][i % 3], [3, 2, 1][i % 3])
                            for i, t in enumerate(tickers)])
    overlap = {"overlap": [{"ticker": t, "name": f"Name {t}", "held_by": ["F1", "F2"],
                            "weights_by_fund": {"F1": 0.03, "F2": 0.02},
                            "n_funds_holding": 2, "avg_weight": 0.025, "max_weight": 0.03,
                            "sum_of_weights": 0.05} for t in tickers]}
    return scores, consensus, overlap


class TestBandRanking(unittest.TestCase):
    def test_band_decides_before_quality(self):
        scores = {"stocks": {"LOWQ": _score("LOWQ", 20.0), "HIGHQ": _score("HIGHQ", 95.0)}}
        con = _consensus([_con("LOWQ", "majority", 0.55, 3), _con("HIGHQ", "plural", 0.3, 2)])
        ranked = build_rankings.rank(scores, con, {"overlap": []})["ranked"]
        self.assertEqual([r["ticker"] for r in ranked], ["LOWQ", "HIGHQ"])

    def test_quality_orders_names_inside_a_band(self):
        scores = {"stocks": {"A": _score("A", 50.0), "B": _score("B", 90.0),
                             "C": _score("C", 70.0, conf=0.5)}}
        con = _consensus([_con(t, "plural", 0.3, 2) for t in "ABC"])
        ranked = build_rankings.rank(scores, con, {"overlap": []})["ranked"]
        self.assertEqual([r["ticker"] for r in ranked], ["B", "A", "C"])   # C's Q'' is 40
        self.assertEqual(ranked[2]["q_shrunk"], 40.0)

    def test_c_share_then_ticker_break_quality_ties(self):
        scores = {"stocks": {t: _score(t, 70.0) for t in ("A", "B", "C")}}
        con = _consensus([_con("A", "plural", 0.3, 2), _con("B", "plural", 0.4, 2),
                          _con("C", "plural", 0.3, 2)])
        ranked = build_rankings.rank(scores, con, {"overlap": []})["ranked"]
        self.assertEqual([r["ticker"] for r in ranked], ["B", "A", "C"])

    def test_eligibility(self):
        scores = {"stocks": {"OK": _score("OK", 70.0), "NOVOTE": _score("NOVOTE", 99.0),
                             "UNSCORED": {**_score("UNSCORED", None), "status": "unscored_no_roe"},
                             "NOCON": _score("NOCON", 80.0)}}
        con = _consensus([_con("OK", "single", 0.2, 1), _con("NOVOTE", "none", 0.0, 0),
                          _con("UNSCORED", "majority", 0.7, 4)])
        out = build_rankings.rank(scores, con, {"overlap": []})
        self.assertEqual([r["ticker"] for r in out["ranked"]], ["OK"])
        self.assertEqual(out["n_eligible"], 1)

    def test_up_to_fifteen_with_rank_slice_tiers(self):
        out = build_rankings.rank(*_inputs(24))
        self.assertEqual(out["n_ranked"], 15)
        self.assertEqual(out["n_eligible"], 24)
        self.assertEqual([r["tier"] for r in out["ranked"]], ["A"] * 5 + ["B"] * 5 + ["C"] * 5)
        self.assertEqual([r["rank"] for r in out["ranked"]], list(range(1, 16)))

    def test_few_eligible_warning(self):
        few = build_rankings.rank(*_inputs(4))
        self.assertEqual(few["warning"], "few_eligible")
        self.assertIsNone(build_rankings.rank(*_inputs(5))["warning"])

    def test_output_fields(self):
        scores, con, overlap = _inputs(6)
        con["anchored_core"] = ["NVDA"]
        out = build_rankings.rank(scores, con, overlap)
        for key, value in (("ranking_method", "v0.4-consensus-bands"), ("vote_basis", "active"),
                           ("n_funds", 8), ("n_eff_run", 3.0), ("vote_floor", 0.03),
                           ("anchored_core", ["NVDA"])):
            self.assertEqual(out[key], value)
        self.assertEqual(out["anchored_core_detail"][0]["ticker"], "NVDA")
        row = out["ranked"][0]
        for key in ("rank", "tier", "band", "c_share", "opinions", "n_votes", "n_holders",
                    "vote_basis_counts", "q_raw", "q_shrunk", "quality_confidence",
                    "roe_years", "roe_source", "name", "industry", "held_by"):
            self.assertIn(key, row)
        for gone in ("composite_score", "crowding_signal_raw", "crowding_signal_normalized",
                     "crowding_discount"):
            self.assertNotIn(gone, row)


class TestRankingReadsNoMacro(unittest.TestCase):
    """B5/C5 — structural test (spec §8.3): never delete.

    The ranking must not depend on M1 (or on any later stage), which is what
    makes running M1 after 3a legitimate.
    """

    def test_build_rankings_reads_no_top_down_or_price_input(self):
        text = (_REPO_ROOT / "scripts" / "build_rankings.py").read_text(encoding="utf-8").lower()
        for banned in ("macro_factors", "sector_logic", "etf_relative_strength", "coherence",
                       "crowding"):
            self.assertFalse(banned in text, f"build_rankings.py mentions {banned!r}")


class TestDeterministicRanking(unittest.TestCase):
    """A7 / I10 — structural test (spec §8.3): never delete."""

    @staticmethod
    def _run(tmp: Path, tag: str, scores: dict, consensus: dict, overlap: dict) -> bytes:
        paths = {}
        for name, payload in (("scores", scores), ("consensus", consensus), ("overlap", overlap)):
            paths[name] = tmp / f"{tag}_{name}.json"
            paths[name].write_text(json.dumps(payload), encoding="utf-8")
        out = tmp / f"{tag}_rankings.json"
        run = subprocess.run([sys.executable, str(_SCRIPT), "--scores", str(paths["scores"]),
                              "--consensus", str(paths["consensus"]),
                              "--overlap", str(paths["overlap"]), "--out", str(out)],
                             capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        return out.read_bytes()

    @staticmethod
    def _shuffled(scores, consensus, overlap, seed):
        rng = random.Random(seed)
        items = list(scores["stocks"].items())
        rows, ov = list(consensus["stocks"]), list(overlap["overlap"])
        for seq in (items, rows, ov):
            rng.shuffle(seq)
        return {"stocks": dict(items)}, {**consensus, "stocks": rows}, {"overlap": ov}

    def test_shuffled_inputs_give_a_byte_identical_rankings_json(self):
        base = _inputs()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reference = self._run(tmp, "base", *base)
            for seed in range(5):
                with self.subTest(seed=seed):
                    self.assertEqual(self._run(tmp, f"s{seed}", *self._shuffled(*base, seed)),
                                     reference)

    def test_ties_break_by_ticker(self):
        ranked = build_rankings.rank(*_inputs())["ranked"]
        keys = [build_rankings.sort_key(r) for r in ranked]
        self.assertEqual(keys, sorted(keys))


class TestLegacyComparison(unittest.TestCase):
    def test_legacy_reproduces_the_v033_composite(self):
        from legacy_v033 import legacy_rank, v033_signal
        scores = {"stocks": {"AAA": _score("AAA", 80.0), "BBB": _score("BBB", 40.0)}}
        overlap = {"overlap": [
            {"ticker": "AAA", "held_by": ["F1"], "weights_by_fund": {"F1": 0.03},
             "n_funds_holding": 1, "avg_weight": 0.03},
            {"ticker": "BBB", "held_by": ["F1", "F2", "F3"],
             "weights_by_fund": {"F1": 0.01, "F2": 0.01, "F3": 0.01},
             "n_funds_holding": 3, "avg_weight": 0.01}]}
        out = legacy_rank(scores, overlap, {"funds": []})
        # BBB: 3 holders, no discount; AAA: 1 holder at 3% -> small discount.
        self.assertGreater(v033_signal(3, 0.01, None, None, None),
                           v033_signal(1, 0.03, None, None, None))
        aaa = next(r for r in out["ranked"] if r["ticker"] == "AAA")
        self.assertEqual(aaa["composite_score"], round(0.5 * aaa["q_shrunk"] + 0.5 * 25.0, 2))

    def test_compare_rankings_prints_both_columns(self):
        from compare_rankings import compare
        scores, consensus, overlap = _inputs(6)
        holdings = {"funds": [
            {"fund_id": "F1", "rejected": False, "currency": "USD", "total_aum": 1e9,
             "holdings_us": [{"ticker_normalized": f"T{i:02d}", "weight": 0.03} for i in range(6)]},
            {"fund_id": "F2", "rejected": False, "currency": "USD", "total_aum": 1e9,
             "holdings_us": [{"ticker_normalized": f"T{i:02d}", "weight": 0.02} for i in range(3)]}]}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name, payload in (("holdings.json", holdings), ("scores_per_stock.json", scores),
                                  ("overlap.json", overlap)):
                (work / name).write_text(json.dumps(payload))
            lines = compare(work, "presence")
        self.assertIn("v0.33 legacy composite", lines[0])
        self.assertTrue(any(line.startswith("N_eff_run") for line in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
