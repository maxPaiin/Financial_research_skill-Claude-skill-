"""
v0.4 A3 — yfinance provider: symbol mapping, real annual series (never a
repeated trailing value), negative-equity guards, ETF top holdings, dated
closes, and the rule that yfinance is imported in exactly one file (I11).

Every test runs in replay mode: YF_REPLAY_DIR points at
tests/fixtures/yfinance/, so no test touches the network.

    python -m unittest tests.test_v04_yfinance -v
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from providers import yfinance_provider as yp  # noqa: E402

_REPLAY = _REPO_ROOT / "tests" / "fixtures" / "yfinance"
ASOF = date(2026, 9, 30)


class _Replay(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {yp.REPLAY_ENV: str(_REPLAY)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.provider = yp.yfinanceProvider()


class TestSymbolMapping(unittest.TestCase):
    def test_share_classes_use_a_hyphen_on_yahoo(self):
        self.assertEqual(yp.to_yahoo_symbol("BRK.B"), "BRK-B")
        self.assertEqual(yp.to_yahoo_symbol("BF.B"), "BF-B")
        self.assertEqual(yp.to_yahoo_symbol("brk.b"), "BRK-B")
        self.assertEqual(yp.to_yahoo_symbol("AAPL"), "AAPL")

    def test_exchange_suffixes_are_left_alone(self):
        self.assertEqual(yp.to_yahoo_symbol("2330.TW"), "2330.TW")
        self.assertEqual(yp.to_yahoo_symbol("VOD.L"), "VOD.L")

    def test_back_to_the_canonical_form(self):
        self.assertEqual(yp.from_yahoo_symbol("BRK-B"), "BRK.B")
        self.assertEqual(yp.from_yahoo_symbol("2330.TW"), "2330.TW")
        self.assertEqual(yp.from_yahoo_symbol("MSFT"), "MSFT")


class TestAnnualSeries(_Replay):
    def test_four_year_series_from_statements(self):
        rec = self.provider.fetch("TSTA", ASOF)
        # 2026-12-31 lies after asof and is ignored; four real fiscal years remain.
        self.assertEqual([dp.value for dp in rec.roe_5y], [0.2, 0.2, 0.3, 0.4])
        self.assertEqual([dp.value for dp in rec.net_income_5y], [2.0e9, 2.6e9, 3.6e9, 4.4e9])
        self.assertEqual(len({dp.value for dp in rec.roe_5y}), 3)      # not one value x5
        self.assertTrue(all(dp.source.startswith("yfinance:annual-") for dp in rec.roe_5y))
        self.assertEqual(rec.data_asof, date(2025, 12, 31))

    def test_common_stock_equity_is_the_fallback(self):
        rec = self.provider.fetch("TSTA", ASOF)
        self.assertEqual(rec.roe_5y[2].value, 0.3)                     # 3.6e9 / 12.0e9

    def test_ttm_only_is_one_point_never_repeated(self):
        rec = self.provider.fetch("TSTB", ASOF)
        self.assertEqual(len(rec.roe_5y), 1)
        self.assertEqual(rec.roe_5y[0].value, 0.21)
        self.assertTrue(rec.roe_5y[0].source.startswith("yfinance:ttm-"))
        self.assertEqual(len(rec.net_income_5y), 1)

    def test_other_fields_still_filled(self):
        rec = self.provider.fetch("TSTA", ASOF)
        self.assertEqual(rec.debt_equity.value, 0.45)
        self.assertEqual(rec.ev_ebitda.value, 18.5)
        self.assertEqual(rec.adv.value, 3.0e8)
        self.assertEqual(rec.industry, "technology")
        self.assertFalse(rec.is_adr)

    def test_unknown_symbol_returns_none(self):
        self.assertIsNone(self.provider.fetch("NOPE", ASOF))


class TestNegativeEquityGuards(_Replay):
    def test_negative_equity_year_is_undefined(self):
        rec = self.provider.fetch("TSTN", ASOF)
        self.assertEqual([dp.value for dp in rec.roe_5y], [2.0, None])
        self.assertEqual(rec.roe_undefined_years, [2025])

    def test_debt_equity_undefined_when_latest_equity_negative(self):
        self.assertIsNone(self.provider.fetch("TSTN", ASOF).debt_equity)


class TestCanonicalKeys(_Replay):
    def test_brk_b_is_fetched_as_brk_hyphen_b_and_keyed_brk_dot_b(self):
        rec = self.provider.fetch("BRK.B", ASOF)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.ticker, "BRK.B")
        self.assertEqual(len(rec.roe_5y), 2)

    def test_etf_top_holdings_are_canonicalised(self):
        out = yp.fetch_etf_top_holdings(["ETFX", "NOPE"])
        self.assertEqual(set(out), {"ETFX"})
        self.assertEqual(out["ETFX"]["BRK.B"], 0.031)
        self.assertNotIn("BRK-B", out["ETFX"])
        self.assertNotIn("ZERO", out["ETFX"])                          # zero weight dropped
        self.assertEqual(out["ETFX"]["2330.TW"], 0.022)


class TestCloses(_Replay):
    def test_dated_closes_are_inclusive_and_ordered(self):
        out = yp.fetch_close_series_dated(["TSTA", "NOPE"], date(2026, 3, 2), date(2026, 3, 6))
        self.assertEqual(set(out), {"TSTA"})
        days = [d for d, _ in out["TSTA"]]
        self.assertEqual(days[0], date(2026, 3, 2))
        self.assertEqual(days[-1], date(2026, 3, 6))
        self.assertEqual(days, sorted(days))

    def test_undated_closes_keep_their_v031_shape(self):
        out = yp.fetch_close_series(["TSTA"])
        self.assertEqual(len(out["TSTA"]), 260)
        self.assertTrue(all(isinstance(v, float) for v in out["TSTA"]))

    def test_replay_never_builds_a_network_source(self):
        self.assertIsInstance(yp._source(), yp._ReplaySource)


class TestSingleYfinanceImport(unittest.TestCase):
    """I11: yfinance is imported only in providers/yfinance_provider.py."""

    _IMPORT = re.compile(r"^\s*(?:import\s+yfinance|from\s+yfinance\b)", re.M)

    def test_only_one_file_imports_yfinance(self):
        importers = sorted(
            str(p.relative_to(_REPO_ROOT / "scripts"))
            for p in (_REPO_ROOT / "scripts").rglob("*.py")
            if self._IMPORT.search(p.read_text(encoding="utf-8"))
        )
        self.assertEqual(importers, [str(Path("providers") / "yfinance_provider.py")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
