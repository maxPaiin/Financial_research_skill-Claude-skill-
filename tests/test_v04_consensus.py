"""
v0.4 B1–B4 — consensus signal v2: identical-fund merge, disclosure depth and
the common vote floor, benchmark proxies, and the consensus computation
(property and closed-form tests).

    python -m unittest tests.test_v04_consensus -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))


def _fund(fid: str, weights: dict[str, float], asof: str = "2026-03-31", **kw) -> dict:
    """An accepted fund whose kept US rows are `weights`."""
    return {
        "fund_id": fid, "fund_name": f"Fund {fid}", "asof": asof, "rejected": False,
        "currency": kw.pop("currency", "USD"), "total_aum": kw.pop("total_aum", 1e9),
        "holdings_us": [{"ticker_normalized": t, "weight": w} for t, w in weights.items()],
        **kw,
    }


# -----------------------------------------------------------------------------
# B1 — identical-fund merge
# -----------------------------------------------------------------------------

class TestIdenticalFundMerge(unittest.TestCase):
    W = {"AAA": 0.07, "BBB": 0.05, "CCC": 0.04, "DDD": 0.03, "EEE": 0.02}

    def test_share_class_duplicates_merge_into_the_lower_fund_id(self):
        from extract_holdings import merge_identical_funds, is_accepted
        data = {"funds": [_fund("F10", self.W), _fund("F2", self.W), _fund("F3", {"ZZZ": 0.1})]}
        merges = merge_identical_funds(data)
        f10, f2, f3 = data["funds"]
        self.assertEqual(f2["merged_with"], ["F10"])          # F2 < F10 in natural order
        self.assertEqual(f10["merged_into"], "F2")
        self.assertIsNone(f3["merged_with"])
        self.assertEqual([m["merged"] for m in merges], ["F10"])
        self.assertEqual([f["fund_id"] for f in data["funds"] if is_accepted(f)], ["F2", "F3"])

    def test_reweighted_holdings_are_not_identical(self):
        from extract_holdings import merge_identical_funds
        other = {**self.W, "AAA": 0.03}
        data = {"funds": [_fund("F1", self.W), _fund("F2", other)]}
        self.assertEqual(merge_identical_funds(data), [])

    def test_identical_holdings_at_different_dates_are_two_snapshots(self):
        from extract_holdings import merge_identical_funds
        data = {"funds": [_fund("F1", self.W), _fund("F2", self.W, asof="2026-02-28")]}
        self.assertEqual(merge_identical_funds(data), [])

    def test_proportional_weights_are_identical(self):
        # Cosine ignores scale: the same portfolio reported as a share of the
        # whole fund or of the equity sleeve is still one portfolio.
        from extract_holdings import merge_identical_funds
        doubled = {t: 2 * w for t, w in self.W.items()}
        data = {"funds": [_fund("F1", self.W), _fund("F2", doubled)]}
        self.assertEqual(len(merge_identical_funds(data)), 1)

    def test_merged_duplicate_is_one_holder_and_one_aum(self):
        from extract_holdings import dedupe, merge_identical_funds
        from crowding_signal import fund_aum_map
        data = {"funds": [_fund("F1", self.W), _fund("F2", self.W)]}
        merge_identical_funds(data)
        universe = {u["ticker"]: u for u in dedupe(data)["unique_universe"]}
        self.assertEqual(universe["AAA"]["held_by"], ["F1"])
        aum, _ = fund_aum_map(data)
        self.assertEqual(set(aum), {"F1"})

    def test_layer1_discloses_the_merge(self):
        from extract_holdings import merge_identical_funds
        from layer1_report import build_layer1_md
        data = {"funds": [_fund("F1", self.W, scope_summary={"weight_kept": 0.6}),
                          _fund("F2", self.W, scope_summary={"weight_kept": 0.6})],
                "unique_universe": [], "pit_snapshot_info": []}
        data["merged_funds"] = merge_identical_funds(data)
        md = build_layer1_md(data)
        self.assertIn("Identical share classes merged: 1", md)
        self.assertIn("F2 (Fund F2) merged into F1 (Fund F1)", md)
        self.assertIn("Independent funds in this run: 1", md)
        self.assertIn("merged into F1 (identical share class)", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
