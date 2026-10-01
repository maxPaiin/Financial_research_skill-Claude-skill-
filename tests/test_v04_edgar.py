"""
v0.4 A2 — EDGAR provider: the exchange-file ticker map, 20-F/40-F filers, the
ifrs-full taxonomy, same-unit ratios, the negative-equity guards, and the
request guard that replaced the fictitious daily budget.

Offline throughout. Recorded fixtures live in tests/fixtures/edgar/ (written by
scripts/dev/record_fixtures.py — see manifest.json) and are served from a
temporary cache directory with the provider in offline mode; the rest uses
inline synthetic facts.

    python -m unittest tests.test_v04_edgar -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from providers import edgar_provider as ep  # noqa: E402
from providers.edgar_provider import EDGARProvider  # noqa: E402

_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "edgar"
_SAMPLE_MAP = _FIXTURES / "company_tickers_exchange_sample.json"


def _manifest() -> dict:
    return json.loads((_FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _asof() -> date:
    return date.fromisoformat(_manifest()["recorded_on"])


class _CacheDir:
    """A temporary EDGAR cache holding the sample ticker map and the recorded
    facts/submissions, served by an offline provider."""

    def __enter__(self) -> EDGARProvider:
        self._tmp = tempfile.TemporaryDirectory()
        cache = Path(self._tmp.name)
        shutil.copy(_SAMPLE_MAP, cache / "ticker_exchange_map.json")
        for path in _FIXTURES.glob("*_[0-9]*.json"):
            shutil.copy(path, cache / path.name)
        self.cache = cache
        return EDGARProvider(cache_dir=cache, offline=True)

    def __exit__(self, *exc):
        self._tmp.cleanup()


def _fy(year: int, val: float, *, unit_form: str = "10-K", duration: bool = True) -> dict:
    item = {"end": f"{year}-12-31", "val": val, "form": unit_form,
            "filed": f"{year + 1}-02-20"}
    if duration:
        item["start"] = f"{year}-01-01"
    return item


def _facts(taxonomy: str, concepts: dict[str, dict[str, list[dict]]]) -> dict:
    return {"facts": {taxonomy: {c: {"units": u} for c, u in concepts.items()}}}


# -----------------------------------------------------------------------------
# Recorded fixtures (A2.8)
# -----------------------------------------------------------------------------

class TestRecordedFixtures(unittest.TestCase):
    def test_manifest_carries_no_contact_email(self):
        # Spec rule 6: the maintainer's email is never committed.
        for path in _FIXTURES.glob("*.json"):
            self.assertNotRegex(path.read_text(encoding="utf-8"),
                                r"[\w.+-]+@[\w-]+\.[\w.]+", path.name)

    def test_tsmc_yields_roe_in_twd(self):
        info = _manifest()["fixtures"]["ifrs_twd"]
        with _CacheDir() as p:
            rec = p.fetch(info["ticker"], _asof())
            self.assertEqual(p._detect_filing_type(info["cik"]), "20-F")
            self.assertTrue(p.is_foreign_private_issuer(info["cik"]))
        self.assertIsNotNone(rec, "TSMC must not vanish (F7)")
        defined = [dp.value for dp in rec.roe_5y if dp is not None and dp.value is not None]
        self.assertGreaterEqual(len(defined), 2)
        self.assertEqual(rec.reporting_currency, "TWD")
        self.assertEqual(rec.taxonomy, "ifrs-full")
        self.assertTrue(all(0 < v < 1 for v in defined), defined)

    def test_usd_10k_filer(self):
        info = _manifest()["fixtures"]["usd_10k"]
        with _CacheDir() as p:
            rec = p.fetch(info["ticker"], _asof())
            self.assertEqual(p._detect_filing_type(info["cik"]), "10-K")
        self.assertEqual(rec.taxonomy, "us-gaap")
        self.assertEqual(rec.reporting_currency, "USD")
        defined = [dp for dp in rec.roe_5y if dp.value is not None]
        self.assertGreaterEqual(len(defined), 2)
        self.assertTrue(all(dp.source.startswith("edgar:10-K") for dp in defined))

    def test_negative_equity_years_are_undefined_not_sign_flipped(self):
        info = _manifest()["fixtures"]["negative_equity"]
        asof = _asof()
        with _CacheDir() as p:
            rec = p.fetch(info["ticker"], asof)
            facts = p._get_company_facts(info["cik"])
        self.assertTrue(rec.roe_undefined_years, "fixture was chosen for negative equity")
        # Every year whose equity was <= 0 has no ROE value.
        eq = ep._series_by_unit(facts, rec.taxonomy, "StockholdersEquity", asof,
                                ep.ANNUAL_FORMS, False).get(rec.reporting_currency, {})
        negative_years = {end.year for end, v in eq.items() if v <= 0}
        self.assertTrue(set(rec.roe_undefined_years) <= negative_years)
        # With the latest equity <= 0 there is no D/E at all.
        bs = ep._series_by_unit(facts, rec.taxonomy, "StockholdersEquity", asof,
                                ep.ANNUAL_FORMS + ("10-Q",), False)[rec.reporting_currency]
        if bs[max(bs)] <= 0:
            self.assertIsNone(rec.debt_equity)


# -----------------------------------------------------------------------------
# No usable facts -> None (A2.5)
# -----------------------------------------------------------------------------

class TestNoUsableFacts(unittest.TestCase):
    def setUp(self):
        self.facts = json.loads(
            (_FIXTURES / "facts_no_usable_synthetic.json").read_text(encoding="utf-8"))

    def test_build_record_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), offline=True)
            self.assertIsNone(p._build_record("ZZZZ", 9999999, date(2026, 6, 30),
                                              self.facts, "10-K"))

    def test_fetch_returns_none_so_the_registry_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "ticker_exchange_map.json").write_text(json.dumps({
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[9999999, "SYNTHETIC NO USABLE FACTS INC", "ZZZZ", "NYSE"]]}))
            (cache / "facts_9999999.json").write_text(json.dumps(self.facts))
            p = EDGARProvider(cache_dir=cache, offline=True)
            self.assertIsNone(p.fetch("ZZZZ", date(2026, 6, 30)))


# -----------------------------------------------------------------------------
# Same-unit pairing (A2.4)
# -----------------------------------------------------------------------------

class TestUnitsNeverMix(unittest.TestCase):
    ASOF = date(2026, 6, 30)

    def _record(self, facts: dict, taxonomy_form: str = "10-K"):
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), offline=True)
            return p._build_record("TSTX", 1, self.ASOF, facts, taxonomy_form)

    def test_ratio_uses_the_unit_both_sides_share(self):
        facts = _facts("us-gaap", {
            "NetIncomeLoss": {"USD": [_fy(2023, 100.0), _fy(2024, 110.0)],
                              "EUR": [_fy(2024, 90.0)]},
            "StockholdersEquity": {"EUR": [_fy(2024, 900.0, duration=False)]},
        })
        rec = self._record(facts)
        defined = [dp.value for dp in rec.roe_5y if dp.value is not None]
        self.assertEqual(defined, [0.1])              # 90 EUR / 900 EUR, never 110 USD / 900 EUR
        self.assertEqual(rec.reporting_currency, "EUR")

    def test_usd_preferred_when_both_sides_carry_it(self):
        facts = _facts("us-gaap", {
            "NetIncomeLoss": {"USD": [_fy(2023, 100.0), _fy(2024, 120.0)],
                              "EUR": [_fy(2024, 999.0)]},
            "StockholdersEquity": {"USD": [_fy(y, 1000.0, duration=False) for y in (2023, 2024)],
                                   "EUR": [_fy(2024, 1.0, duration=False)]},
        })
        rec = self._record(facts)
        self.assertEqual([dp.value for dp in rec.roe_5y if dp.value is not None], [0.1, 0.12])
        self.assertEqual(rec.reporting_currency, "USD")

    def test_no_shared_unit_means_no_ratio(self):
        facts = _facts("us-gaap", {
            "NetIncomeLoss": {"USD": [_fy(2023, 100.0), _fy(2024, 120.0)]},
            "StockholdersEquity": {"EUR": [_fy(2024, 1000.0, duration=False)]},
        })
        rec = self._record(facts)
        self.assertTrue(all(dp.value is None for dp in rec.roe_5y))
        self.assertEqual([dp.value for dp in rec.net_income_5y if dp], [100.0, 120.0])

    def test_ifrs_filer_in_its_own_currency(self):
        facts = _facts("ifrs-full", {
            "ProfitLossAttributableToOwnersOfParent": {
                "TWD": [_fy(y, 100.0 * (y - 2019), unit_form="20-F") for y in range(2020, 2026)]},
            "EquityAttributableToOwnersOfParent": {
                "TWD": [_fy(y, 1000.0, unit_form="20-F", duration=False)
                        for y in range(2020, 2026)]},
            "LongtermBorrowings": {
                "TWD": [_fy(2025, 300.0, unit_form="20-F", duration=False)]},
        })
        rec = self._record(facts, "20-F")
        self.assertEqual(rec.taxonomy, "ifrs-full")
        self.assertEqual(rec.reporting_currency, "TWD")
        self.assertEqual([dp.value for dp in rec.roe_5y], [0.2, 0.3, 0.4, 0.5, 0.6])
        self.assertEqual(rec.debt_equity.value, 0.3)
        self.assertTrue(rec.is_adr)

    def test_quarterly_fact_never_stands_in_for_the_fiscal_year(self):
        q4 = {"start": "2024-10-01", "end": "2024-12-31", "val": 5.0, "form": "10-K",
              "filed": "2025-02-20"}
        facts = _facts("us-gaap", {
            "NetIncomeLoss": {"USD": [q4, _fy(2024, 100.0)]},
            "StockholdersEquity": {"USD": [_fy(2024, 1000.0, duration=False)]},
        })
        rec = self._record(facts)
        self.assertEqual([dp.value for dp in rec.roe_5y if dp.value is not None], [0.1])

    def test_a_stale_tag_never_beats_a_current_one(self):
        facts = _facts("us-gaap", {
            "NetIncomeLoss": {"USD": [_fy(2016, 1.0), _fy(2017, 1.0)]},
            "ProfitLoss": {"USD": [_fy(y, 50.0) for y in (2022, 2023, 2024, 2025)]},
            "StockholdersEquity": {"USD": [_fy(y, 500.0, duration=False)
                                           for y in (2022, 2023, 2024, 2025)]},
        })
        rec = self._record(facts)
        self.assertEqual([dp.value for dp in rec.roe_5y if dp.value is not None],
                         [0.1, 0.1, 0.1, 0.1])


# -----------------------------------------------------------------------------
# Negative or zero equity (A2.6, F10)
# -----------------------------------------------------------------------------

class TestNegativeEquityGuards(unittest.TestCase):
    ASOF = date(2026, 6, 30)

    def _record(self, equity_by_year: dict[int, float], ni_by_year: dict[int, float],
                debt: float | None = 100.0):
        concepts = {
            "NetIncomeLoss": {"USD": [_fy(y, v) for y, v in ni_by_year.items()]},
            "StockholdersEquity": {"USD": [_fy(y, v, duration=False)
                                           for y, v in equity_by_year.items()]},
        }
        if debt is not None:
            concepts["LongTermDebt"] = {"USD": [_fy(max(equity_by_year), debt, duration=False)]}
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), offline=True)
            return p._build_record("TSTX", 1, self.ASOF, _facts("us-gaap", concepts), "10-K")

    def test_loss_over_negative_equity_is_not_a_positive_roe(self):
        rec = self._record({2023: 500.0, 2024: -200.0, 2025: -300.0},
                           {2023: 50.0, 2024: -40.0, 2025: 30.0})
        values = [dp.value for dp in rec.roe_5y]
        self.assertEqual(values[-3:], [0.1, None, None])
        self.assertEqual(rec.roe_undefined_years, [2024, 2025])
        self.assertFalse(any(v is not None and v > 0.1 for v in values))

    def test_zero_equity_is_undefined_too(self):
        rec = self._record({2024: 400.0, 2025: 0.0}, {2024: 40.0, 2025: 10.0})
        self.assertEqual([dp.value for dp in rec.roe_5y][-2:], [0.1, None])
        self.assertEqual(rec.roe_undefined_years, [2025])

    def test_negative_latest_equity_leaves_debt_equity_undefined(self):
        rec = self._record({2024: 400.0, 2025: -50.0}, {2024: 40.0, 2025: 10.0}, debt=900.0)
        self.assertIsNone(rec.debt_equity)       # never a negative D/E under the ceiling

    def test_positive_equity_keeps_debt_equity(self):
        rec = self._record({2024: 400.0, 2025: 500.0}, {2024: 40.0, 2025: 50.0}, debt=250.0)
        self.assertEqual(rec.debt_equity.value, 0.5)


# -----------------------------------------------------------------------------
# Ticker map: exchange file, share classes, name index (A2.1)
# -----------------------------------------------------------------------------

class TestTickerMap(unittest.TestCase):
    def test_columns_are_found_by_field_name(self):
        rows = ep.parse_exchange_file({
            "fields": ["ticker", "exchange", "cik", "name"],
            "data": [["BRK-B", "NYSE", 1067983, "BERKSHIRE HATHAWAY INC"]]})
        self.assertEqual(rows[0].cik, 1067983)
        self.assertEqual(rows[0].ticker, "BRK.B")
        self.assertEqual(rows[0].exchange, "NYSE")

    def test_share_class_resolves_with_dot_or_hyphen(self):
        with _CacheDir() as p:
            dot, hyphen = p.lookup_ticker("BRK.B"), p.lookup_ticker("BRK-B")
            self.assertIsNotNone(dot)
            self.assertEqual(dot, hyphen)
            self.assertEqual(p._resolve_cik("brk-b"), dot.cik)

    def test_listing_exchange(self):
        with _CacheDir() as p:
            self.assertEqual(p.listing_exchange("TSM"), "NYSE")
            self.assertEqual(p.listing_exchange("ATEYY"), "OTC")     # Advantest ADR
            self.assertIsNone(p.listing_exchange("AYR"))              # exchange null
            # TCEHY trades OTC but Tencent is not an SEC registrant, so the
            # exchange file has no row for it at all.
            self.assertIsNone(p.lookup_ticker("TCEHY"))
            self.assertIsNone(p.listing_exchange("NOT-A-TICKER"))

    def test_dropped_candidate_stays_dropped(self):
        # A2.3: NoncurrentPortionOfNoncurrentBorrowings occurred in none of 19
        # recorded filers, so it is not a candidate.
        self.assertNotIn("NoncurrentPortionOfNoncurrentBorrowings",
                         ep.CONCEPTS["debt"]["ifrs-full"])

    def test_name_index_is_keyed_by_normalised_name(self):
        with _CacheDir() as p:
            hits = p.name_index().get("taiwan semiconductor manufacturing") or []
            self.assertIn("TSM", [t for _, t, _ in hits])
            alphabet = p.name_index().get("alphabet") or []
            self.assertGreaterEqual(len({t for _, t, _ in alphabet}), 2)   # GOOGL + GOOG


# -----------------------------------------------------------------------------
# Filer type (A2.2)
# -----------------------------------------------------------------------------

class TestFilingTypeV04(unittest.TestCase):
    def _provider(self, forms: list[str] | None = None, path: Path | None = None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cache = Path(tmp.name)
        payload = (json.loads(path.read_text(encoding="utf-8")) if path
                   else {"filings": {"recent": {"form": forms}}})
        (cache / "submissions_42.json").write_text(json.dumps(payload))
        return EDGARProvider(cache_dir=cache, offline=True)

    def test_40f_sample(self):
        p = self._provider(path=_FIXTURES / "submissions_40f_synthetic.json")
        self.assertEqual(p._detect_filing_type(42), "40-F")
        self.assertTrue(p.is_foreign_private_issuer(42))

    def test_domestic_filer_is_not_foreign(self):
        p = self._provider(["10-Q", "8-K", "10-K"])
        self.assertEqual(p._detect_filing_type(42), "10-K")
        self.assertFalse(p.is_foreign_private_issuer(42))

    def test_amended_annual_form_counts(self):
        self.assertEqual(self._provider(["6-K", "20-F/A"])._detect_filing_type(42), "20-F")

    def test_newest_annual_form_wins(self):
        # An issuer that moved from 20-F to 10-K now files as a domestic filer.
        self.assertEqual(self._provider(["10-K", "20-F"])._detect_filing_type(42), "10-K")


# -----------------------------------------------------------------------------
# Ticker-map TTL and the request guard (A2.1, A2.7, F13, F14)
# -----------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None):
        self.response = response
        self.urls: list[str] = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if self.response is None:
            raise AssertionError(f"unexpected network call: {url}")
        return self.response


_OLD_MAP = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "OLD CO", "OLDX", "NYSE"]]}
_NEW_MAP = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[2, "NEW CO", "NEWX", "Nasdaq"]]}


class TestTickerMapTTL(unittest.TestCase):
    def _provider(self, cache: Path, age_days: float, session: _FakeSession) -> EDGARProvider:
        path = cache / "ticker_exchange_map.json"
        path.write_text(json.dumps(_OLD_MAP))
        then = time.time() - age_days * 86400
        os.utime(path, (then, then))
        p = EDGARProvider(cache_dir=cache, contact_email="ops@example.com", offline=False)
        p._session = session
        return p

    def test_stale_cache_triggers_a_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _FakeSession(_FakeResponse(200, _NEW_MAP))
            p = self._provider(Path(tmp), age_days=8, session=session)
            self.assertIsNotNone(p.lookup_ticker("NEWX"))
            self.assertIsNone(p.lookup_ticker("OLDX"))
            self.assertEqual(session.urls, [ep._TICKER_MAP_URL])

    def test_fresh_cache_is_not_refetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._provider(Path(tmp), age_days=1, session=_FakeSession(None))
            self.assertIsNotNone(p.lookup_ticker("OLDX"))

    def test_failed_refresh_keeps_the_stale_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._provider(Path(tmp), age_days=30, session=_FakeSession(_FakeResponse(503)))
            self.assertIsNotNone(p.lookup_ticker("OLDX"))

    def test_ticker_map_is_read_from_www_sec_gov(self):
        self.assertEqual(ep._TICKER_MAP_URL,
                         "https://www.sec.gov/files/company_tickers_exchange.json")
        self.assertTrue(ep._COMPANY_FACTS_URL.startswith("https://data.sec.gov/"))
        self.assertEqual(ep._TICKER_MAP_CACHE_KEY, "ticker_exchange_map")


class TestRequestGuard(unittest.TestCase):
    def test_no_daily_budget_only_a_runaway_guard(self):
        self.assertFalse(hasattr(ep, "_DAILY_BUDGET"))
        self.assertGreaterEqual(ep._RUNAWAY_REQUEST_GUARD, 10_000)

    def test_guard_stops_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), contact_email="ops@example.com",
                              offline=False)
            p._session = _FakeSession(None)
            p._request_count = ep._RUNAWAY_REQUEST_GUARD
            with self.assertLogs("providers.edgar_provider", level="WARNING"):
                self.assertIsNone(p._get_json("https://data.sec.gov/x", "x"))

    def test_offline_mode_never_touches_the_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), offline=True)
            p._session = _FakeSession(None)
            self.assertIsNone(p._get_json("https://data.sec.gov/x", "x"))
            self.assertIsNone(p.fetch("AAPL", date(2026, 1, 1)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
