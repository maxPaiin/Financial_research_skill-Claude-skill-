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


# -----------------------------------------------------------------------------
# B4 — consensus_signal.py: closed forms and properties (spec Appendix A)
# -----------------------------------------------------------------------------

import math  # noqa: E402
import random  # noqa: E402


def _random_matrix(rng: random.Random, n: int) -> dict[str, dict[str, float]]:
    """A symmetric similarity matrix with entries in [0, 1] and a unit diagonal."""
    fids = [f"F{i}" for i in range(n)]
    s = {f: {f: 1.0} for f in fids}
    for i, f in enumerate(fids):
        for g in fids[i + 1:]:
            s[f][g] = s[g][f] = rng.random()
    return s


class TestIndependenceWeights(unittest.TestCase):
    def test_duplicates_share_one_funds_weight(self):
        from consensus_signal import independence, similarity
        s = similarity({"A": {"X": 0.05}, "B": {"X": 0.05}, "C": {"Y": 0.05}})
        u, n_eff, omega = independence(s)
        self.assertAlmostEqual(n_eff, 2.0, places=12)
        self.assertEqual([round(omega[f], 12) for f in "ABC"], [0.25, 0.25, 0.5])

    def test_equicorrelated_funds_match_the_closed_form(self):
        from consensus_signal import independence, similarity
        for n in (2, 5, 7, 11):
            for rho in (0.0, 0.3, 0.6, 0.95):
                with self.subTest(n=n, rho=rho):
                    vectors = {f"F{i}": {"COMMON": math.sqrt(rho), f"OWN{i}": math.sqrt(1 - rho)}
                               for i in range(n)}
                    n_eff = independence(similarity(vectors))[1]
                    self.assertAlmostEqual(n_eff, n / (1 + (n - 1) * rho), delta=1e-9)

    def test_spec_example_seven_funds_at_rho_0_6(self):
        from consensus_signal import independence, similarity
        vectors = {f"F{i}": {"C": math.sqrt(0.6), f"O{i}": math.sqrt(0.4)} for i in range(7)}
        self.assertAlmostEqual(independence(similarity(vectors))[1], 1.52, places=2)

    def test_bounds_over_1000_random_inputs(self):
        from consensus_signal import independence, similarity
        rng = random.Random(4)
        tickers = [f"T{i}" for i in range(15)]
        for _ in range(1000):
            n = rng.randint(1, 11)
            vectors = {f"F{i}": {t: rng.random() for t in rng.sample(tickers, rng.randint(1, 10))}
                       for i in range(n)}
            u, n_eff, omega = independence(similarity(vectors))
            self.assertGreaterEqual(n_eff, 1 - 1e-12)
            self.assertLessEqual(n_eff, n + 1e-12)
            self.assertTrue(all(1 / n - 1e-12 <= x <= 1 + 1e-12 for x in u.values()))
            self.assertAlmostEqual(sum(omega.values()), 1.0, places=12)

    def test_marginal_contribution_of_a_duplicate_is_small(self):
        from consensus_signal import marginal_contributions, similarity
        s = similarity({"A": {"X": 0.05}, "B": {"X": 0.05}, "C": {"Y": 0.05}})
        m = marginal_contributions(s)
        self.assertAlmostEqual(m["C"], 1.0, places=12)      # removing C loses a whole opinion
        self.assertAlmostEqual(m["A"], 0.0, places=12)      # removing A loses nothing


class TestMonotonicity(unittest.TestCase):
    def test_adding_a_yes_vote_never_lowers_c_share(self):
        from consensus_signal import independence
        rng = random.Random(7)
        for _ in range(500):
            s = _random_matrix(rng, rng.randint(2, 11))
            _, _, omega = independence(s)
            fids = list(s)
            voters = set(rng.sample(fids, rng.randint(0, len(fids) - 1)))
            before = sum(omega[f] for f in voters)
            extra = rng.choice([f for f in fids if f not in voters])
            self.assertGreaterEqual(sum(omega[f] for f in voters | {extra}), before)

    def test_f1_regression_more_holders_never_score_lower(self):
        # v0.33: in a single-mandate run C(1)=0.64 > C(2)=0.47 < C(7)=0.49.
        # Equal 5% weights, every fund holding the stock votes for it.
        from consensus_signal import compute
        rng = random.Random(11)
        base = {f"F{i}": {f"OWN{i}{j}": 0.05 for j in range(5)} for i in range(7)}
        for _ in range(50):
            for f in base:                                   # random overlap structure
                for j in range(3):
                    base[f][f"SHARED{j}"] = 0.05 if rng.random() < 0.5 else 0.0
                base[f] = {t: w for t, w in base[f].items() if w}
            shares = []
            for k in range(1, 8):
                funds = [_fund(fid, {**vec, **({"TGT": 0.05} if i < k else {})})
                         for i, (fid, vec) in enumerate(sorted(base.items()))]
                row = next(r for r in compute({"funds": funds}, vote_floor="none")["stocks"]
                           if r["ticker"] == "TGT")
                shares.append(row["c_share"])
            self.assertEqual(shares, sorted(shares), shares)


class TestBands(unittest.TestCase):
    def test_band_rules(self):
        from consensus_signal import band
        self.assertEqual(band(0.62, 5), "majority")
        self.assertEqual(band(0.5, 2), "majority")
        self.assertEqual(band(0.49, 4), "plural")
        self.assertEqual(band(0.9, 1), "single")      # one dissimilar fund is never a majority
        self.assertEqual(band(0.0, 0), "none")

    def test_single_dissimilar_voter_with_omega_above_half_is_single(self):
        from consensus_signal import compute
        # F3 is unlike F1/F2 (identical twins), so its omega is 0.5.
        funds = [_fund("F1", {"A": 0.05, "B": 0.05}), _fund("F2", {"A": 0.05, "B": 0.05}),
                 _fund("F3", {"C": 0.05, "D": 0.05, "X": 0.0001})]
        out = compute({"funds": funds}, vote_floor="none")
        omega = {f["fund_id"]: f["omega"] for f in out["funds"]}
        self.assertGreaterEqual(omega["F3"], 0.5 - 1e-6)
        c = next(r for r in out["stocks"] if r["ticker"] == "C")
        self.assertEqual(c["band"], "single")


class TestVoteRule(unittest.TestCase):
    def test_each_branch(self):
        from consensus_signal import vote
        tau = 0.02
        self.assertEqual(vote(0.015, tau, "active", 0.05), (0, "below_floor"))
        self.assertEqual(vote(0.06, tau, "active", 0.05), (1, "active"))
        self.assertEqual(vote(0.04, tau, "active", 0.05), (0, "anchored"))
        self.assertEqual(vote(0.04, tau, "active", None), (1, "presence"))   # not in top-10
        self.assertEqual(vote(0.04, tau, "presence", 0.05), (1, "presence"))
        self.assertEqual(vote(0.015, None, "active", None), (1, "presence"))  # floor off

    def test_capped_benchmark_weight(self):
        # A 14% benchmark weight is capped at the 10% single-issuer limit: a
        # fund at 10% is at the most any fund may hold, which is a vote.
        from consensus_signal import vote
        self.assertEqual(vote(0.10, 0.02, "active", 0.14), (1, "active"))
        self.assertEqual(vote(0.095, 0.02, "active", 0.14), (0, "anchored"))

    def test_no_proxy_means_presence(self):
        from consensus_signal import compute
        funds = [_fund("F1", {"NVDA": 0.08, "X": 0.03}), _fund("F2", {"NVDA": 0.08, "Y": 0.03})]
        bench = {"F1": {"proxy": None, "top10": {}}, "F2": {"proxy": "IXN",
                                                           "top10": {"NVDA": 0.18}}}
        out = compute({"funds": funds}, bench)
        nvda = next(r for r in out["stocks"] if r["ticker"] == "NVDA")
        bases = {v["fund_id"]: v["basis"] for v in nvda["votes"]}
        self.assertEqual(bases, {"F1": "presence", "F2": "anchored"})
        self.assertEqual(nvda["n_votes"], 1)


class TestComputeOutput(unittest.TestCase):
    def _run(self, **kw):
        from consensus_signal import compute
        funds = [
            _fund("F1", {"NVDA": 0.09, "AAPL": 0.08, "MSFT": 0.06, "AMD": 0.04, "TTD": 0.025},
                  scope_summary={"disclosure_floor": 0.025}),
            _fund("F2", {"NVDA": 0.07, "AAPL": 0.06, "MSFT": 0.03, "AMD": 0.05, "PLTR": 0.03},
                  scope_summary={"disclosure_floor": 0.030}),
            _fund("F3", {"NVDA": 0.05, "AAPL": 0.04, "MSFT": 0.035, "CRWD": 0.03, "SNOW": 0.031},
                  scope_summary={"disclosure_floor": 0.030}),
        ]
        top = {"NVDA": 0.18, "AAPL": 0.15, "MSFT": 0.13, "AVGO": 0.05}
        bench = {f: {"proxy": "IXN", "proxy_quality": "approximate", "top10": top}
                 for f in ("F1", "F2", "F3")}
        return compute({"funds": funds}, bench, **kw)

    def test_common_floor_and_who_sets_it(self):
        out = self._run()
        self.assertEqual(out["vote_floor"], 0.03)
        self.assertEqual(out["vote_floor_set_by"], ["F2", "F3"])
        ttd = next(r for r in out["stocks"] if r["ticker"] == "TTD")
        self.assertEqual(ttd["votes"][0]["basis"], "below_floor")

    def test_benchmark_heavy_names_become_anchored_core(self):
        out = self._run()
        # Every fund holds NVDA/AAPL/MSFT below min(b, 10%): no active vote.
        self.assertEqual(out["anchored_core"], ["AAPL", "MSFT", "NVDA"])
        nvda = next(r for r in out["stocks"] if r["ticker"] == "NVDA")
        self.assertEqual((nvda["n_votes"], nvda["band"]), (0, "none"))
        self.assertEqual(nvda["vote_basis_counts"]["anchored"], 3)
        self.assertEqual(nvda["vote_basis_counts"]["active"], 0)

    def test_presence_basis_reproduces_holding_based_consensus(self):
        out = self._run(vote_basis="presence")
        nvda = next(r for r in out["stocks"] if r["ticker"] == "NVDA")
        self.assertEqual((nvda["n_votes"], nvda["band"]), (3, "majority"))
        self.assertEqual(out["anchored_core"], [])
        self.assertEqual(out["vote_basis_coverage"]["anchored"], 0)

    def test_floor_off_for_sensitivity_runs(self):
        out = self._run(vote_floor="none")
        self.assertIsNone(out["vote_floor"])
        self.assertEqual(out["vote_basis_coverage"]["below_floor"], 0)

    def test_report_fields(self):
        out = self._run()
        self.assertEqual(out["version"], "0.4")
        self.assertEqual(out["n_funds"], 3)
        self.assertEqual(set(out["similarity"]), {"F1", "F2"})            # upper triangle
        self.assertEqual(set(out["similarity"]["F1"]), {"F2", "F3"})
        self.assertAlmostEqual(sum(f["omega"] for f in out["funds"]), 1.0, places=5)
        row = out["stocks"][0]
        for key in ("ticker", "n_holders", "n_votes", "c_share", "opinions", "band",
                    "vote_basis_counts", "votes"):
            self.assertIn(key, row)
        self.assertAlmostEqual(row["opinions"], row["c_share"] * out["n_eff_run"], places=5)
        cov = out["vote_basis_coverage"]
        self.assertEqual(sum(cov.values()), sum(r["n_holders"] for r in out["stocks"]))

    def test_cli(self):
        import json, subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "h.json").write_text(json.dumps({"funds": [
                _fund("F1", {"A": 0.05, "B": 0.04}), _fund("F2", {"A": 0.05, "C": 0.04})]}))
            run = subprocess.run([sys.executable, str(_REPO_ROOT / "scripts" / "consensus_signal.py"),
                                  "--holdings", str(tmp / "h.json"), "--vote-floor", "none",
                                  "--out", str(tmp / "c.json")],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("independent opinions N_eff", run.stdout)
            out = json.loads((tmp / "c.json").read_text())
            self.assertEqual(next(r for r in out["stocks"] if r["ticker"] == "A")["band"], "majority")


class TestConsensusIgnoresStyle(unittest.TestCase):
    """I9 — structural test (spec §8.3): never delete."""

    def test_no_style_input(self):
        text = (_REPO_ROOT / "scripts" / "consensus_signal.py").read_text(encoding="utf-8")
        self.assertFalse("style" in text.lower(), "consensus_signal.py mentions 'style'")

    def test_no_crowding_macro_or_notice_input(self):
        text = (_REPO_ROOT / "scripts" / "consensus_signal.py").read_text(encoding="utf-8")
        for banned in ("crowding", "macro_factors", "sector_logic", "important_notice",
                       "coherence"):
            self.assertFalse(banned in text.lower(), f"consensus_signal.py mentions {banned!r}")


class TestNoLegacyWeights(unittest.TestCase):
    """I4 — structural test (spec §8.3): never delete.

    The ranking is an ordering of keys; no uncalibrated weight may return to
    the pipeline. The v0.33 composite weights and crowding constants live only
    in scripts/dev/legacy_v033.py, for comparison runs.
    """

    import re as _re
    _LEGACY = _re.compile(
        r"\b_(?:QUALITY_WEIGHT|CONSENSUS_WEIGHT|MAX_DISCOUNT|AVG_WEIGHT_THRESHOLD|"
        r"WEIGHT_RANGE|FUND_DENOMINATOR|LIQ_WEIGHT|STYLE_MIN_FACTOR)\b")

    def test_v033_weights_live_only_under_dev(self):
        scripts = _REPO_ROOT / "scripts"
        offenders = sorted(
            str(path.relative_to(scripts)) for path in scripts.rglob("*.py")
            if "dev" not in path.relative_to(scripts).parts
            and self._LEGACY.search(path.read_text(encoding="utf-8")))
        self.assertEqual(offenders, [])

    def test_the_comparison_copy_still_has_them(self):
        text = (_REPO_ROOT / "scripts" / "dev" / "legacy_v033.py").read_text(encoding="utf-8")
        self.assertIn("_QUALITY_WEIGHT = 0.50", text)
        self.assertIn("_CONSENSUS_WEIGHT = 0.50", text)
        self.assertIn("_MAX_DISCOUNT = 0.60", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
