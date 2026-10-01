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


# -----------------------------------------------------------------------------
# B2 — disclosure depth and the common vote floor
# -----------------------------------------------------------------------------

class TestDisclosureFloor(unittest.TestCase):
    def test_depth_and_floor_count_every_equity_row_with_a_weight(self):
        from extract_holdings import filter_fund_holdings
        _, scope = filter_fund_holdings({"fund_id": "F1", "holdings": [
            {"ticker_raw": "AAPL", "name": "Apple", "weight": 0.071},
            {"ticker_raw": "2330.TW", "name": "TSMC", "weight": 0.055},   # non-US: counted
            {"ticker_raw": "MSFT", "name": "Microsoft", "weight": 0.024},
            {"name": "Cash and equivalents", "weight": 0.010},             # non-equity: not
            {"ticker_raw": "NVDA", "name": "NVIDIA", "weight": None},      # no weight: not
        ]})
        self.assertEqual(scope["disclosure_depth"], 3)
        self.assertEqual(scope["disclosure_floor"], 0.024)

    def test_no_weights_means_no_floor(self):
        from extract_holdings import filter_fund_holdings
        _, scope = filter_fund_holdings({"fund_id": "F1", "holdings": [
            {"ticker_raw": "AAPL", "name": "Apple"}]})
        self.assertEqual(scope["disclosure_depth"], 0)
        self.assertIsNone(scope["disclosure_floor"])

    def _with_floor(self, fid, floor, **kw):
        return _fund(fid, {"AAA": 0.05}, scope_summary={"disclosure_floor": floor}, **kw)

    def test_tau_is_the_largest_floor(self):
        from extract_holdings import common_vote_floor
        tau, set_by = common_vote_floor([self._with_floor("F1", 0.011),
                                         self._with_floor("F2", 0.032),
                                         self._with_floor("F3", 0.024)])
        self.assertEqual(tau, 0.032)
        self.assertEqual(set_by, ["F2"])

    def test_ties_name_every_fund_that_sets_it(self):
        from extract_holdings import common_vote_floor
        _, set_by = common_vote_floor([self._with_floor("F10", 0.03),
                                       self._with_floor("F2", 0.03),
                                       self._with_floor("F1", 0.01)])
        self.assertEqual(set_by, ["F2", "F10"])

    def test_merged_and_rejected_funds_do_not_set_it(self):
        from extract_holdings import common_vote_floor
        tau, _ = common_vote_floor([self._with_floor("F1", 0.02),
                                    self._with_floor("F2", 0.09, merged_into="F1"),
                                    {**self._with_floor("F3", 0.08), "rejected": True}])
        self.assertEqual(tau, 0.02)

    def test_no_floor_anywhere(self):
        from extract_holdings import common_vote_floor
        self.assertEqual(common_vote_floor([self._with_floor("F1", None)]), (None, []))


# -----------------------------------------------------------------------------
# B3 — benchmark proxies and their top-10 weights
# -----------------------------------------------------------------------------

class TestBenchmarkMap(unittest.TestCase):
    def test_appendix_b_rows(self):
        from providers.benchmark_map import proxy_for
        cases = {
            "S&P 500 Information Technology Index": "XLK",
            "Technology Select Sector Index": "XLK",
            "MSCI AC World Information Technology 10/40 Index": "IXN",
            "MSCI ACWI Information Technology Index (Net)": "IXN",
            "MSCI World Information Technology Index": "IXN",
            "MSCI USA IMI Information Technology 25/50 Index": "VGT",
            "NASDAQ-100 Index": "QQQ", "Nasdaq 100": "QQQ",
            "Russell 1000 Growth Index": "IWF", "Russell 1000 Index": "IWB",
            "S&P 500 Index": "SPY", "MSCI ACWI Index": "ACWI",
            "MSCI All Country World Index": "ACWI", "MSCI AC World Index (Net)": "ACWI",
            "MSCI World Index (Net)": "URTH",
        }
        for text, etf in cases.items():
            with self.subTest(text=text):
                self.assertEqual(proxy_for(text)[0], etf)

    def test_sector_rows_win_over_broad_rows(self):
        from providers.benchmark_map import proxy_for
        self.assertEqual(proxy_for("S&P 500 Information Technology"),
                         ("XLK", "approximate (capped index)"))
        self.assertEqual(proxy_for("S&P 500")[1], "exact")

    def test_unmapped_is_none_never_a_plausible_proxy(self):
        from providers.benchmark_map import proxy_for
        for text in ("MSCI World Health Care Index", "Russell 1000 Value",
                     "MSCI World Growth", "MSCI ACWI ex USA", "S&P 500 Equal Weight",
                     "Nasdaq 100 Technology Sector", "Hang Seng Index", "", None):
            with self.subTest(text=text):
                self.assertIsNone(proxy_for(text))

    def test_dash_variants_normalise(self):
        from providers.benchmark_map import proxy_for
        self.assertEqual(proxy_for("NASDAQ\u2011100")[0], "QQQ")


class TestBenchmarkWeights(unittest.TestCase):
    TOP = {"IXN": {"NVDA": 0.18, "AAPL": 0.15, "MSFT": 0.13, "AVGO": 0.05, "ORCL": 0.03,
                   "CRM": 0.025, "TSM": 0.024, "AMD": 0.023, "ASML": 0.022, "CSCO": 0.021,
                   "ADBE": 0.019, "ACN": 0.018}}

    def _holdings(self):
        return {"funds": [
            _fund("F1", {"NVDA": 0.09}, benchmark="MSCI AC World Information Technology Index"),
            _fund("F2", {"NVDA": 0.09}, benchmark="Hang Seng Index"),
            _fund("F3", {"NVDA": 0.09}, benchmark=None),
            _fund("F4", {"NVDA": 0.09}, benchmark="NASDAQ-100 Index"),
            _fund("F5", {"NVDA": 0.09}, benchmark="MSCI ACWI IT", merged_into="F1"),
        ]}

    def test_records_proxy_top10_and_b10(self):
        from benchmark_weights import build
        out = build(self._holdings(), lambda etfs: {e: self.TOP[e] for e in etfs if e in self.TOP},
                    fetched_at="2026-10-01")
        f1 = out["F1"]
        self.assertEqual(f1["proxy"], "IXN")
        self.assertTrue(f1["proxy_quality"].startswith("approximate"))
        self.assertEqual(len(f1["top10"]), 10)
        self.assertNotIn("ACN", f1["top10"])                      # 12th largest
        self.assertEqual(f1["b10"], 0.021)
        self.assertIsNone(f1["error"])

    def test_every_failure_is_a_null_proxy_with_a_reason(self):
        from benchmark_weights import build
        out = build(self._holdings(), lambda etfs: {e: self.TOP[e] for e in etfs if e in self.TOP})
        self.assertIsNone(out["F2"]["proxy"])
        self.assertIn("not in the proxy table", out["F2"]["error"])
        self.assertIn("no benchmark printed", out["F3"]["error"])
        self.assertIsNone(out["F4"]["proxy"])                      # QQQ not fetched
        self.assertIn("unavailable for QQQ", out["F4"]["error"])
        self.assertNotIn("F5", out)                                # merged share class

    def test_a_crashing_fetch_is_recorded_not_raised(self):
        from benchmark_weights import build
        def boom(etfs):
            raise RuntimeError("network down")
        out = build(self._holdings(), boom)
        self.assertIsNone(out["F1"]["proxy"])
        self.assertIn("unavailable", out["F1"]["error"])

    def test_cli_replay(self):
        import json, subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "h.json").write_text(json.dumps(self._holdings()))
            (tmp / "r.json").write_text(json.dumps(self.TOP))
            run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / "benchmark_weights.py"),
                                  "--holdings", str(tmp / "h.json"), "--replay", str(tmp / "r.json"),
                                  "--out", str(tmp / "bw.json")],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("1/4 funds", run.stdout)
            self.assertEqual(json.loads((tmp / "bw.json").read_text())["F1"]["proxy"], "IXN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
