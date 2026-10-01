"""
v0.4 B7 (+ D3 later) — the coherence overlay's exit-liquidity risk check.

A risk demotes exactly like a contradiction: one tier, never more, rank
untouched, rankings.json read-only. Without a crowding file the check does
not run and every record is what it was before (I3).

    python -m unittest tests.test_v04_overlay -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from coherence_audit import audit, audit_stock  # noqa: E402

NEUTRAL_MACRO = {"policy_rate_direction": "on_hold", "inflation_trend": "stable"}
TIGHTENING = {"policy_rate_direction": "tightening", "inflation_trend": "rising"}
EXPANSIONARY = {"industries": {"technology": {
    "input_constraint": {"direction": "easing"},
    "pricing_power": {"direction": "expanding"},
    "return_on_capital": {"direction": "improving"},
    "capital_sensitivity": "high"}}}
ETF = {"benchmark": "SPY",
       "sectors": {"technology": {"etf": "XLK", "status": "ok", "rs_state": "inline"}},
       "stocks": {"AAA": {"etf": "XLK", "status": "ok", "divergence": "none"}}}
LAGGING = {**ETF, "sectors": {"technology": {"etf": "XLK", "status": "ok",
                                             "rs_state": "lagging"}}}


def _row(rank=2, tier="A"):
    return {"ticker": "AAA", "rank": rank, "tier": tier, "industry": "technology"}


def _sig(dtl, crowded, n_usd=3, n_all=5):
    return {"AAA": {"ticker": "AAA", "days_to_liquidate": dtl, "is_exit_crowded": crowded,
                    "liquidity_label": "liquidity-inclusive" if dtl is not None
                    else "no-liquidity-data",
                    "n_usd_aum_holders": n_usd, "n_holders": n_all}}


class TestExitLiquidityCheck(unittest.TestCase):
    def test_risk_alone_demotes_one_tier(self):
        rec = audit_stock(_row(), NEUTRAL_MACRO, EXPANSIONARY, ETF, _sig(14.2, True))
        self.assertEqual(rec["contradictions"], [])
        self.assertEqual(len(rec["risks"]), 1)
        self.assertEqual((rec["tier_delta"], rec["tier"], rec["rank"]), (-1, "B", 2))
        self.assertIn("14.2 trading days", rec["risks"][0])
        self.assertIn("3 of 5 holders that report AUM in USD", rec["risks"][0])
        self.assertIn("demoted A->B", rec["commentary"])

    def test_risk_plus_contradiction_is_still_one_tier(self):
        rec = audit_stock(_row(), TIGHTENING, EXPANSIONARY, LAGGING, _sig(30.0, True))
        self.assertTrue(rec["contradictions"])
        self.assertTrue(rec["risks"])
        self.assertEqual((rec["tier_delta"], rec["tier"]), (-1, "B"))

    def test_liquid_position_is_coherent(self):
        rec = audit_stock(_row(), NEUTRAL_MACRO, EXPANSIONARY, ETF, _sig(0.4, False))
        verdict = next(v for v in rec["verdicts"] if v["pair"] == "exit_liquidity")
        self.assertEqual(verdict["verdict"], "coherent")
        self.assertEqual(rec["tier_delta"], 0)

    def test_no_liquidity_figure_is_insufficient_data_and_never_demotes(self):
        without = audit_stock(_row(), NEUTRAL_MACRO, EXPANSIONARY, ETF)
        rec = audit_stock(_row(), NEUTRAL_MACRO, EXPANSIONARY, ETF, _sig(None, False))
        verdict = next(v for v in rec["verdicts"] if v["pair"] == "exit_liquidity")
        self.assertEqual(verdict["verdict"], "insufficient_data")
        self.assertEqual(rec["tier_delta"], 0)
        # Reported in its own verdict, not as a gap in the three readings.
        self.assertEqual(rec["commentary"], without["commentary"])
        self.assertEqual(rec["insufficient_data"], without["insufficient_data"])

    def test_ticker_missing_from_the_file_is_insufficient(self):
        rec = audit_stock(_row(), NEUTRAL_MACRO, EXPANSIONARY, ETF, {})
        verdict = next(v for v in rec["verdicts"] if v["pair"] == "exit_liquidity")
        self.assertEqual(verdict["verdict"], "insufficient_data")

    def test_a_missing_crowding_file_changes_nothing(self):
        rankings = {"ranked": [_row(1, "A"), {**_row(7, "B"), "ticker": "BBB"}]}
        a = audit(rankings, NEUTRAL_MACRO, EXPANSIONARY, ETF)
        b = audit(rankings, NEUTRAL_MACRO, EXPANSIONARY, ETF, None)
        self.assertEqual(a["records"], b["records"])
        self.assertTrue(all("risks" not in r for r in b["records"]))
        self.assertTrue(all(v["pair"] != "exit_liquidity"
                            for r in b["records"] for v in r["verdicts"]))


class TestRankingsStayReadOnly(unittest.TestCase):
    def test_rankings_json_is_byte_identical_after_the_audit(self):
        rankings = {"ranked": [_row(1, "A"), {**_row(7, "B"), "ticker": "BBB"}]}
        crowding = {"signals": [{"ticker": "AAA", "days_to_liquidate": 12.0,
                                 "is_exit_crowded": True, "n_usd_aum_holders": 2,
                                 "n_holders": 4}]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            r_path, c_path = tmp / "rankings.json", tmp / "crowding_signals.json"
            r_path.write_text(json.dumps(rankings, indent=2), encoding="utf-8")
            c_path.write_text(json.dumps(crowding), encoding="utf-8")
            before = r_path.read_bytes()
            run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / "coherence_audit.py"),
                                  "--rankings", str(r_path), "--crowding", str(c_path),
                                  "--out", str(tmp / "coherence.json")],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(r_path.read_bytes(), before)
            out = json.loads((tmp / "coherence.json").read_text())
            self.assertEqual(out["n_exit_liquidity_risks"], 1)
            aaa = next(r for r in out["records"] if r["ticker"] == "AAA")
            self.assertEqual((aaa["rank"], aaa["tier"]), (1, "B"))


class TestGateAcceptsNamedRisks(unittest.TestCase):
    def _check(self, record):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coherence.json"
            path.write_text(json.dumps({"records": [record]}))
            return cc.check_coherence(path)

    def test_risk_only_demotion_passes(self):
        self.assertEqual(self._check({"ticker": "AAA", "base_tier": "A", "tier": "B",
                                      "tier_delta": -1, "contradictions": [],
                                      "risks": ["exit liquidity"]}), [])

    def test_demotion_with_neither_fails(self):
        problems = self._check({"ticker": "AAA", "base_tier": "A", "tier": "B",
                                "tier_delta": -1, "contradictions": [], "risks": []})
        self.assertTrue(any("without a named contradiction or risk" in p for p in problems))

    def test_two_tier_drop_still_caught_with_a_risk(self):
        problems = self._check({"ticker": "AAA", "base_tier": "A", "tier": "C",
                                "tier_delta": -2, "risks": ["x"]})
        self.assertTrue(any("demotion-only and capped" in p for p in problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
