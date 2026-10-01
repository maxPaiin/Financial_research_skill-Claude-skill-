"""
v0.4 A4 + A5 — the registry's field-level fallback, and quality confidence.

A4: each field takes EDGAR's value when EDGAR has one, else yfinance's; a thin
EDGAR ROE series (< 2 defined years) gives way to a real yfinance series. A
fiscal year is reconciled only against the same fiscal year.

    python -m unittest tests.test_v04_quality -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from providers.base import DataPoint, FundamentalsRecord  # noqa: E402
from providers.registry import ProviderRegistry  # noqa: E402
from providers.resolver import _PROVENANCE_LOG  # noqa: E402

ASOF = date(2026, 9, 30)


class _Stub:
    """A provider that returns a prepared record (or None)."""

    def __init__(self, record: FundamentalsRecord | None):
        self.record = record

    def fetch(self, ticker, asof):
        return copy.deepcopy(self.record)


def _series(source: str, conf: float, values_by_year: dict[int, float | None],
            month_day: str = "12-31") -> list[DataPoint]:
    return [
        DataPoint(value=v, confidence=conf if v is not None else 0.0, source=source,
                  asof=ASOF, period_end=date.fromisoformat(f"{y}-{month_day}"))
        for y, v in sorted(values_by_year.items())
    ]


def _edgar(roe: dict[int, float | None], **kw) -> FundamentalsRecord:
    return FundamentalsRecord(
        ticker="TSTX", asof=ASOF,
        roe_5y=_series("edgar:20-F-2026", 0.9, roe),
        net_income_5y=kw.pop("ni", _series("edgar:20-F-2026", 0.9, {2024: 10.0, 2025: 12.0})),
        **kw)


def _yf(roe: dict[int, float | None], **kw) -> FundamentalsRecord:
    return FundamentalsRecord(
        ticker="TSTX", asof=ASOF,
        roe_5y=[DataPoint(value=v, confidence=0.5, source=f"yfinance:annual-{y}-12-31",
                          asof=ASOF, period_end=date(y, 12, 31))
                for y, v in sorted(roe.items())],
        net_income_5y=kw.pop("ni", []),
        **kw)


def _registry(edgar_rec, yf_rec) -> ProviderRegistry:
    return ProviderRegistry(edgar=_Stub(edgar_rec), yfinance=_Stub(yf_rec))


class TestFieldLevelFallback(unittest.TestCase):
    def setUp(self):
        _PROVENANCE_LOG.clear()

    def test_empty_edgar_series_takes_the_yfinance_series(self):
        # A4 acceptance: an empty EDGAR series plus a 4-year yfinance series
        # gives ROE from yfinance, tagged yfinance:*.
        edgar = _edgar({2021: None, 2022: None, 2023: None, 2024: None, 2025: None})
        yf = _yf({2022: 0.18, 2023: 0.20, 2024: 0.22, 2025: 0.24},
                 roe_undefined_years=[])
        rec, source = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(source, "edgar+yfinance")
        self.assertEqual([dp.value for dp in rec.roe_5y], [0.18, 0.20, 0.22, 0.24])
        self.assertTrue(all(dp.source.startswith("yfinance:") for dp in rec.roe_5y))
        self.assertTrue(all(dp.confidence == 0.5 for dp in rec.roe_5y))

    def test_one_edgar_year_is_still_too_thin(self):
        edgar = _edgar({2024: None, 2025: 0.30})
        yf = _yf({2023: 0.2, 2024: 0.25, 2025: 0.3})
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(len(rec.roe_5y), 3)
        self.assertTrue(rec.roe_5y[0].source.startswith("yfinance:"))

    def test_a_real_edgar_series_is_kept(self):
        edgar = _edgar({2021: 0.10, 2022: 0.12, 2023: 0.14, 2024: 0.16, 2025: 0.18})
        yf = _yf({2023: 0.5, 2024: 0.5, 2025: 0.181})
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual([dp.value for dp in rec.roe_5y[:4]], [0.10, 0.12, 0.14, 0.16])
        self.assertTrue(rec.roe_5y[0].source.startswith("edgar:"))

    def test_latest_year_reconciled_against_the_same_fiscal_year(self):
        edgar = _edgar({2024: 0.16, 2025: 0.18})
        yf = _yf({2024: 0.9, 2025: 0.181})
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(rec.roe_5y[-1].n_sources_agreed, 2)        # 0.18 vs 0.181 agree
        self.assertAlmostEqual(rec.roe_5y[-1].value, 0.1805, places=4)
        self.assertEqual(_PROVENANCE_LOG, [])

    def test_different_fiscal_years_are_not_reconciled(self):
        # EDGAR's latest is FY2024 (companyfacts lag); yfinance's latest is
        # FY2025. Comparing them would log a conflict that does not exist.
        edgar = _edgar({2023: 0.16, 2024: 0.18})
        yf = _yf({2025: 0.40})
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(rec.roe_5y[-1].value, 0.18)
        self.assertEqual(rec.roe_5y[-1].confidence, 0.9)
        self.assertEqual(_PROVENANCE_LOG, [])

    def test_a_trailing_point_is_compared_as_before(self):
        edgar = _edgar({2024: 0.16, 2025: 0.18})
        ttm = FundamentalsRecord(ticker="TSTX", asof=ASOF, roe_5y=[
            DataPoint(value=0.40, confidence=0.5, source="yfinance:ttm-2026-09", asof=ASOF)])
        rec, _ = _registry(edgar, ttm).fetch("TSTX", ASOF)
        self.assertEqual(len(_PROVENANCE_LOG), 1)                  # > 20% apart: logged
        self.assertEqual(rec.roe_5y[-1].value, 0.18)               # EDGAR wins on confidence

    def test_missing_fields_are_filled_from_yfinance(self):
        dp = lambda v: DataPoint(value=v, confidence=0.5, source="yfinance:2026-09", asof=ASOF)
        edgar = _edgar({2024: 0.16, 2025: 0.18}, industry="other")
        yf = _yf({2025: 0.18}, ev_ebitda=dp(14.0), market_cap=dp(5e10), adv=dp(2e8),
                 industry="technology")
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(rec.ev_ebitda.value, 14.0)
        self.assertEqual(rec.market_cap.value, 5e10)
        self.assertEqual(rec.adv.value, 2e8)
        self.assertEqual(rec.industry, "technology")

    def test_edgar_values_are_never_overwritten_by_fill_ins(self):
        dp = lambda v, s: DataPoint(value=v, confidence=0.9, source=s, asof=ASOF)
        edgar = _edgar({2024: 0.16, 2025: 0.18}, ev_ebitda=dp(11.0, "edgar:x"))
        yf = _yf({2025: 0.18}, ev_ebitda=dp(30.0, "yfinance:x"))
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual(rec.ev_ebitda.value, 11.0)

    def test_empty_edgar_net_income_takes_yfinance(self):
        edgar = _edgar({2024: None, 2025: None}, ni=[None, None])
        yf = _yf({2024: 0.2, 2025: 0.2}, ni=_series("yfinance:annual", 0.5, {2024: 5.0, 2025: 6.0}))
        rec, _ = _registry(edgar, yf).fetch("TSTX", ASOF)
        self.assertEqual([dp.value for dp in rec.net_income_5y], [5.0, 6.0])

    def test_edgar_failure_falls_back_to_yfinance_alone(self):
        rec, source = _registry(None, _yf({2025: 0.2})).fetch("TSTX", ASOF)
        self.assertEqual(source, "yfinance")
        self.assertEqual(rec.roe_5y[0].value, 0.2)

    def test_both_failing_is_unscored(self):
        self.assertEqual(_registry(None, None).fetch("TSTX", ASOF), (None, "none"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
