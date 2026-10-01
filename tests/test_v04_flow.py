"""
v0.4 D1–D2 — consensus flow: between two factsheets, did the funds add to a
stock or trim it, once price drift and rounding are taken out?

Pure drift is never a trade; one manager's trim registers as a trim; the
rounding step is detected per fund; a non-USD share class never prices R_f
from its NAV (I8); without a comparable prior snapshot there is no reading.

    python -m unittest tests.test_v04_flow -v
"""

from __future__ import annotations

import copy
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "tests"))

from consensus_flow import (  # noqa: E402
    compute, flow_state, load_prior, match_funds, reporting_step, row_signal,
)

D0, D1 = date(2026, 5, 29), date(2026, 8, 31)


def _series(p0: float, p1: float) -> list[tuple[date, float]]:
    return [(D0 - timedelta(days=3), p0), (D0, p0), (D1, p1)]


def _fund(fid, weights, asof, currency="USD", nav=None, isin=None, name=None):
    return {"fund_id": fid, "fund_name": name or f"Fund {fid}", "asof": asof.isoformat(),
            "currency": currency, "nav_per_share": nav, "fund_isin": isin,
            "holdings": [{"ticker_raw": t, "weight": w} for t, w in weights.items()],
            "holdings_us": [{"ticker_normalized": t, "weight": w} for t, w in weights.items()]}


def _consensus(*fids):
    return {"funds": [{"fund_id": f, "omega": 1 / len(fids)} for f in fids]}


def _fetch(closes):
    return lambda symbols, start, end: {s: closes[s] for s in symbols if s in closes}


def _flat(*symbols):
    return {s: _series(100.0, 100.0) for s in (*symbols, "SPY")}


def _stock(out, ticker):
    return next(s for s in out["stocks"] if s["ticker"] == ticker)


class TestReportingStep(unittest.TestCase):
    def test_steps_are_detected_from_the_weights(self):
        self.assertEqual(reporting_step([0.061, 0.045, 0.030]), 0.001)     # 0.1pp -> ε 0.0005
        self.assertEqual(reporting_step([0.0612, 0.0451, 0.03]), 0.0001)   # 0.01pp
        self.assertEqual(reporting_step([0.05, 0.03, 0.02]), 0.01)         # whole percent
        self.assertEqual(reporting_step([0.0612345]), 0.00001)             # finer: finest step
        self.assertIsNone(reporting_step([None, "n/a"]))

    def test_the_step_is_per_fund_and_per_snapshot(self):
        cur = {"F1": _fund("F1", {"AAA": 0.0612, "BBB": 0.0451}, D1),
               "F2": _fund("F2", {"AAA": 0.061, "BBB": 0.045}, D1)}
        pri = [_fund("F1", {"AAA": 0.061, "BBB": 0.045}, D0),
               _fund("F2", {"AAA": 0.061, "BBB": 0.045}, D0)]
        out = compute({"funds": list(cur.values())}, {"funds": pri}, _consensus("F1", "F2"),
                      None, _fetch(_flat("AAA", "BBB")))
        steps = {f["fund_id"]: (f["step_now"], f["step_prev"]) for f in out["funds"]}
        self.assertEqual(steps, {"F1": (0.0001, 0.001), "F2": (0.001, 0.001)})


class TestPureDriftIsNoTrade(unittest.TestCase):
    def test_rounded_drift_never_crosses_the_threshold(self):
        rng = random.Random(20261001)
        for _ in range(5000):
            step = rng.choice((0.01, 0.001, 0.0001))
            w_prev = rng.uniform(0.005, 0.095)
            r_stock, r_fund = rng.uniform(-0.4, 0.6), rng.uniform(-0.3, 0.4)
            w_now = w_prev * (1 + r_stock) / (1 + r_fund)
            sig = row_signal(round(w_prev / step) * step, round(w_now / step) * step,
                             r_stock, r_fund, step, step)
            self.assertEqual(sig["s"], 0, (step, w_prev, r_stock, r_fund, sig))

    def test_a_single_half_step_would_have_called_this_a_trade(self):
        # 3.049% printed as 3.0%; drift 1.64% -> 3.0990% printed as 3.1%. The gap
        # to w* is 0.0508pp: above half a step, inside the two-sided rounding.
        sig = row_signal(0.030, 0.031, 0.0164, 0.0, 0.001, 0.001)
        self.assertGreater(abs(sig["trade"]), 0.0005)
        self.assertEqual(sig["s"], 0)

    def test_drift_through_compute_leaves_every_fund_unchanged(self):
        prices = {"AAA": _series(100, 130), "BBB": _series(100, 80), "CCC": _series(100, 104),
                  "SPY": _series(100, 105)}
        prev = {"AAA": 0.050, "BBB": 0.040, "CCC": 0.030}
        r_fund = 0.07                                         # from USD NAV 100 -> 107
        now = {t: round(w * prices[t][-1][1] / 100 / (1 + r_fund), 3) for t, w in prev.items()}
        cur = [_fund(f, now, D1, nav=107.0) for f in ("F1", "F2")]
        pri = [_fund(f, prev, D0, nav=100.0) for f in ("F1", "F2")]
        out = compute({"funds": cur}, {"funds": pri}, _consensus("F1", "F2"), None,
                      _fetch(prices))
        self.assertTrue(all(f["r_fund_source"] == "nav_usd" for f in out["funds"]))
        for s in out["stocks"]:
            self.assertEqual([r["s"] for r in s["funds"]], [0, 0], s["ticker"])
            self.assertEqual(s["state"], "mixed")


class TestTradesAndStates(unittest.TestCase):
    def _run(self, now_by_fund, prev=0.05):
        # ZZZ at 2.1% puts every snapshot on a 0.1pp step: threshold 0.1pp.
        fids = sorted(now_by_fund)
        cur = [_fund(f, {"AAA": w, "ZZZ": 0.021}, D1) for f, w in now_by_fund.items()]
        pri = [_fund(f, {"AAA": prev, "ZZZ": 0.021}, D0) for f in fids]
        return compute({"funds": cur}, {"funds": pri}, _consensus(*fids), None,
                       _fetch(_flat("AAA", "ZZZ")))

    def test_one_managers_trim_registers_as_trimmed(self):
        aaa = _stock(self._run({"F1": 0.040, "F2": 0.050, "F3": 0.050}), "AAA")
        signs = {r["fund_id"]: r["s"] for r in aaa["funds"]}
        self.assertEqual(signs, {"F1": -1, "F2": 0, "F3": 0})
        self.assertEqual((aaa["n_trimmed"], aaa["state"]), (1, "mixed"))   # one fund is no trend

    def test_two_trims_unwind_and_two_adds_build(self):
        self.assertEqual(_stock(self._run({"F1": 0.04, "F2": 0.04, "F3": 0.05}), "AAA")["state"],
                         "unwinding")
        self.assertEqual(_stock(self._run({"F1": 0.06, "F2": 0.061, "F3": 0.05}), "AAA")["state"],
                         "building")
        self.assertEqual(_stock(self._run({"F1": 0.06, "F2": 0.04, "F3": 0.05}), "AAA")["state"],
                         "mixed")

    def test_a_move_that_only_ties_the_rounding_bound_is_no_trade(self):
        # Whole-percent weights: 5% -> 4% could be 4.5x% rounded both ways.
        cur = [_fund(f, {"AAA": 0.04, "ZZZ": 0.02}, D1) for f in ("F1", "F2")]
        pri = [_fund(f, {"AAA": 0.05, "ZZZ": 0.02}, D0) for f in ("F1", "F2")]
        out = compute({"funds": cur}, {"funds": pri}, _consensus("F1", "F2"), None,
                      _fetch(_flat("AAA", "ZZZ")))
        aaa = _stock(out, "AAA")
        self.assertEqual([r["threshold"] for r in aaa["funds"]], [0.01, 0.01])
        self.assertEqual([r["s"] for r in aaa["funds"]], [0, 0])

    def test_states_follow_the_table(self):
        self.assertEqual(flow_state(1, 1, 0, 0.5), "insufficient")
        self.assertEqual(flow_state(3, 2, 1, 0.2), "building")
        self.assertEqual(flow_state(3, 1, 2, -0.2), "unwinding")
        self.assertEqual(flow_state(3, 2, 0, 0.0), "mixed")             # weights cancel
        self.assertEqual(flow_state(3, 1, 2, 0.1), "mixed")             # trims outweighed by ω

    def test_entries_and_exits_carry_no_sign(self):
        cur = [_fund("F1", {"AAA": 0.05, "NEW": 0.03}, D1), _fund("F2", {"AAA": 0.05}, D1)]
        pri = [_fund("F1", {"AAA": 0.05, "OLD": 0.03}, D0), _fund("F2", {"AAA": 0.05}, D0)]
        out = compute({"funds": cur}, {"funds": pri}, _consensus("F1", "F2"), None,
                      _fetch(_flat("AAA", "NEW", "OLD")))
        new, old = _stock(out, "NEW"), _stock(out, "OLD")
        self.assertEqual((new["entered_disclosure"], new["funds"], new["state"]),
                         (["F1"], [], "insufficient"))
        self.assertEqual((old["left_disclosure"], old["funds"]), (["F1"], []))

    def test_output_is_deterministic(self):
        a = self._run({"F1": 0.04, "F2": 0.06, "F3": 0.05})
        b = self._run({"F3": 0.05, "F2": 0.06, "F1": 0.04})
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


class TestFundReturnSource(unittest.TestCase):
    """I8: NAV prices R_f only for a USD class; otherwise the proxy, then SPY."""

    def _source(self, currency, prior_currency=None, proxy="IXN", closes=None):
        cur = [_fund("F1", {"AAA": 0.05}, D1, currency=currency, nav=110.0),
               _fund("F2", {"AAA": 0.05}, D1)]
        pri = [_fund("F1", {"AAA": 0.05}, D0, currency=prior_currency or currency, nav=100.0),
               _fund("F2", {"AAA": 0.05}, D0)]
        bench = {"F1": {"proxy": proxy}} if proxy else None
        prices = closes if closes is not None else {**_flat("AAA"), "IXN": _series(100, 103)}
        out = compute({"funds": cur}, {"funds": pri}, _consensus("F1", "F2"), bench,
                      _fetch(prices))
        f1 = next((f for f in out["funds"] if f["fund_id"] == "F1"), None)
        return (f1["r_fund_source"], f1["r_fund"]) if f1 else out["excluded_funds"]

    def test_usd_class_uses_its_nav(self):
        self.assertEqual(self._source("USD"), ("nav_usd", 0.1))

    def test_non_usd_class_falls_back_to_the_proxy(self):
        self.assertEqual(self._source("HKD"), ("proxy:IXN", 0.03))

    def test_currency_must_be_usd_in_both_snapshots(self):
        self.assertEqual(self._source("USD", prior_currency="HKD")[0], "proxy:IXN")

    def test_no_proxy_falls_back_to_spy(self):
        prices = {"AAA": _series(100, 100), "SPY": _series(100, 102)}
        self.assertEqual(self._source("EUR", proxy=None, closes=prices), ("spy", 0.02))

    def test_no_return_at_all_excludes_the_fund(self):
        excluded = self._source("EUR", proxy=None, closes={"AAA": _series(100, 100)})
        self.assertIn("no fund return", excluded[0]["reason"])


class TestMatching(unittest.TestCase):
    def test_isin_first_then_the_exact_normalised_name(self):
        cur = [_fund("F1", {}, D1, isin="LU0000000001", name="Alpha Tech Fund"),
               _fund("F2", {}, D1, name="Beta  Growth  FUND"),
               _fund("F3", {}, D1, name="Gamma Fund")]
        pri = [_fund("P9", {}, D0, isin="lu0000000001", name="Alpha Technology Fund (renamed)"),
               _fund("P8", {}, D0, name="beta growth fund"),
               _fund("P7", {}, D0, name="Gamma Fund II")]
        matched, excluded = match_funds(cur, pri)
        self.assertEqual({k: (v[0]["fund_id"], v[1]) for k, v in matched.items()},
                         {"F1": ("P9", "fund_isin"), "F2": ("P8", "fund_name")})
        self.assertEqual([e["fund_id"] for e in excluded], ["F3"])

    def test_an_ambiguous_name_matches_nothing(self):
        matched, excluded = match_funds([_fund("F1", {}, D1, name="Same")],
                                        [_fund("P1", {}, D0, name="Same"),
                                         _fund("P2", {}, D0, name="same")])
        self.assertEqual(matched, {})
        self.assertIn("more than one", excluded[0]["reason"])

    def test_a_prior_that_is_not_earlier_is_excluded(self):
        cur = [_fund("F1", {"AAA": 0.05}, D1), _fund("F2", {"AAA": 0.05}, D1)]
        pri = [_fund("F1", {"AAA": 0.05}, D1), _fund("F2", {"AAA": 0.05}, D0)]
        out = compute({"funds": cur}, {"funds": pri}, _consensus("F1", "F2"), None,
                      _fetch(_flat("AAA")))
        self.assertEqual([e["fund_id"] for e in out["excluded_funds"]], ["F1"])
        self.assertEqual(_stock(out, "AAA")["state"], "insufficient")


class TestNoPriorSnapshot(unittest.TestCase):
    def test_no_comparable_fund_means_no_flow_reading(self):
        cur = [_fund(f, {"AAA": 0.05}, D1) for f in ("F1", "F2")]
        flow = compute({"funds": cur}, {"funds": [_fund("X", {}, D0, name="Other")]},
                       _consensus("F1", "F2"), None, _fetch(_flat("AAA")))
        self.assertEqual((flow["n_comparable_funds"], flow["stocks"]), (0, []))
        self.assertEqual([e["fund_id"] for e in flow["excluded_funds"]], ["F1", "F2"])

class TestPriorFromABundle(unittest.TestCase):
    def test_a_work_bundle_supplies_its_holdings(self):
        from bundle import save
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            prior = {"funds": [_fund("F1", {"AAA": 0.05}, D0)]}
            (work / "holdings.json").write_text(json.dumps(prior))
            (work / "state.json").write_text("{}")
            save(work, Path(tmp) / "work_bundle.zip")
            self.assertEqual(load_prior(Path(tmp) / "work_bundle.zip"), prior)
            (work / "holdings.json").unlink()
            save(work, Path(tmp) / "other.zip")
            with self.assertRaises(ValueError):
                load_prior(Path(tmp) / "other.zip")


class TestTheRankNeverReadsFlow(unittest.TestCase):
    def test_build_rankings_names_no_flow_input(self):
        text = (_REPO_ROOT / "scripts" / "build_rankings.py").read_text(encoding="utf-8")
        self.assertNotIn("consensus_flow", text)
        self.assertNotIn("prior_holdings", text)


class TestRunnerWithAPriorSnapshot(unittest.TestCase):
    """D1 schema through p2, D2 at p4 — offline, on the runner fixtures."""

    def setUp(self):
        import runner_fixtures
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.work, self.replay, self.out = root / "work", root / "replay", root / "out"
        runner_fixtures.build(self.work, self.replay, history_days=340)
        data = json.loads((self.work / "holdings.json").read_text())
        for i, f in enumerate(data["funds"], 1):
            f["fund_isin"], f["nav_per_share"] = f"LU000000000{i}", 104.0
        (self.work / "holdings.json").write_text(json.dumps(data))
        env = mock.patch.dict(os.environ, {"EDGAR_CONTACT_EMAIL": "flow-test@example.com"})
        env.start()
        self.addCleanup(env.stop)

    def _phase(self, *argv):
        import contextlib
        import io
        import run_phase
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_phase.main([*argv, "--work-dir", str(self.work), "--outputs-dir",
                                   str(self.out), "--replay-dir", str(self.replay),
                                   "--asof", "2026-10-01"])
        return code, out.getvalue(), err.getvalue()

    def test_a_majority_name_being_unwound_is_reported_at_p4(self):
        for phase in ("p2", "p3"):
            code, _, err = self._phase(phase)
            self.assertEqual(code, 0, err)
        holdings = json.loads((self.work / "holdings.json").read_text())
        self.assertEqual(holdings["funds"][0]["fund_isin"], "LU0000000001")     # D1 survives p2
        self.assertEqual(holdings["funds"][0]["nav_per_share"], 104.0)

        prior = copy.deepcopy(holdings)
        for f in prior["funds"]:
            f["asof"], f["nav_per_share"] = "2026-05-29", 100.0
            if f["fund_id"] in ("F1", "F2"):                    # held 3pp more AVGO in May
                for key in ("holdings", "holdings_us"):
                    for h in f.get(key) or []:
                        if "AVGO" in (h.get("ticker_normalized"), h.get("ticker_raw")):
                            h["weight"] = round(h["weight"] + 0.03, 3)
        prior_path = self.work.parent / "prior_holdings.json"
        prior_path.write_text(json.dumps(prior))

        code, out, err = self._phase("p4", "--prior-holdings", str(prior_path))
        self.assertEqual(code, 0, err)
        self.assertIn("Consensus flow: 7 of 7 funds comparable", out)
        self.assertIn("majority band being unwound: AVGO", out)
        flow = json.loads((self.work / "consensus_flow.json").read_text())
        avgo = _stock(flow, "AVGO")
        self.assertEqual((avgo["state"], avgo["n_trimmed"]), ("unwinding", 2))
        self.assertTrue(all(f["r_fund_source"] == "nav_usd" and f["matched_on"] == "fund_isin"
                            for f in flow["funds"]))

        cfg = json.loads((self.work / "run_config.json").read_text())
        self.assertEqual(Path(cfg["prior_holdings"]), prior_path.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
