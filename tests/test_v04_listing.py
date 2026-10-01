"""
v0.4 A6 — US-listing verification against SEC's exchange file, the legacy
format check's OTC fix, Layer 1's listing review, and the industry-map strings.

Uses the recorded SEC sample (tests/fixtures/edgar/). One correction to the
spec's table, forced by the real file: TCEHY is not in it at all (Tencent is
not an SEC registrant), so a bare "TCEHY" resolves to unresolved_ticker; the
OTC cases use "TCEHY.PK" (an explicit OTC marker) and ATEYY (Advantest's ADR,
which SEC does list on OTC). Every one of them is excluded.

    python -m unittest tests.test_v04_listing -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from providers.edgar_provider import EDGARProvider  # noqa: E402
from resolve_tickers import ListingResolver, load_aliases  # noqa: E402

_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "edgar"
_SAMPLE = _FIXTURES / "company_tickers_exchange_sample.json"

# Filer types for the issuers the tests name (TSMC's is also checked against
# the recorded submissions file below).
_FORMS = {1046179: "20-F", 320193: "10-K", 1652044: "10-K", 1467373: "10-K",
          937966: "20-F", 1067983: "10-K", 1045810: "10-K"}


def _provider(cache: Path) -> EDGARProvider:
    shutil.copy(_SAMPLE, cache / "ticker_exchange_map.json")
    for path in _FIXTURES.glob("submissions_[0-9]*.json"):
        shutil.copy(path, cache / path.name)
    return EDGARProvider(cache_dir=cache, offline=True)


class _Resolver(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.provider = _provider(Path(tmp.name))
        self.resolver = ListingResolver(self.provider.lookup_ticker,
                                        self.provider.name_index,
                                        lambda cik: _FORMS.get(cik),
                                        load_aliases())

    def status(self, **row) -> str:
        return self.resolver.resolve_row(row)["resolution"]["status"]


class TestSpecTable(_Resolver):
    """The spec's A6 table, row by row."""

    def test_tsm_nyse_is_kept(self):
        out = self.resolver.resolve_row({"ticker_raw": "TSM", "name": "TSMC ADR"})
        self.assertEqual(out["resolution"]["status"], "kept")
        self.assertEqual(out["listing_exchange"], "NYSE")
        self.assertEqual(out["ticker_resolved"], "TSM")

    def test_acn_with_an_irish_isin_is_kept(self):
        # The ticker is checked before the ISIN: a non-US ISIN alone never
        # excludes a US-listed share.
        self.assertEqual(self.status(ticker_raw="ACN", name="Accenture plc",
                                     isin="IE00B4BNMY34"), "kept")

    def test_taiwan_line_is_non_us(self):
        self.assertEqual(self.status(ticker_raw="2330.TW", name="TSMC"), "non_us_listing")

    def test_otc_lines_are_excluded(self):
        self.assertEqual(self.status(ticker_raw="ATEYY", name="Advantest ADR"), "otc_only")
        self.assertEqual(self.status(ticker_raw="TCEHY.PK", name="Tencent ADR"), "otc_only")
        self.assertEqual(self.status(ticker_raw="TCEHY", name="Tencent ADR"),
                         "unresolved_ticker")

    def test_legacy_path_drops_tcehy_pk(self):
        from extract_holdings import normalize_us_ticker
        self.assertIsNone(normalize_us_ticker("TCEHY.PK"))
        self.assertIsNone(normalize_us_ticker("XYZ.OB"))

    def test_name_only_fpi_without_evidence_is_ambiguous(self):
        self.assertEqual(self.status(name="Taiwan Semiconductor Manufacturing"),
                         "ambiguous_listing")

    def test_name_with_an_adr_marker_is_kept(self):
        out = self.resolver.resolve_row({"name": "Taiwan Semiconductor Manufacturing ADR"})
        self.assertEqual(out["resolution"]["status"], "kept")
        self.assertEqual(out["ticker_resolved"], "TSM")
        self.assertEqual(out["resolution"]["method"], "name")

    def test_same_name_with_a_taiwan_isin_is_the_home_market_share(self):
        self.assertEqual(self.status(name="Taiwan Semiconductor Manufacturing",
                                     isin="TW0002330008"), "non_us_listing")

    def test_share_class_resolves_either_way(self):
        for raw in ("BRK.B", "BRK-B", "BRK/B US"):
            with self.subTest(raw=raw):
                out = self.resolver.resolve_row({"ticker_raw": raw})
                self.assertEqual(out["resolution"]["status"], "kept")
                self.assertEqual(out["ticker_resolved"], "BRK.B")


class TestMoreCases(_Resolver):
    def test_us_suffixes_are_stripped(self):
        for raw in ("AAPL US", "AAPL UW", "MSFT.O", "aapl"):
            with self.subTest(raw=raw):
                self.assertEqual(self.status(ticker_raw=raw), "kept")

    def test_bloomberg_non_us_code_is_decisive(self):
        # SEC lists VOD (the ADR), but "VOD LN" is the London line.
        self.assertEqual(self.status(ticker_raw="VOD LN"), "non_us_listing")
        self.assertEqual(self.status(ticker_raw="2330 TT"), "non_us_listing")
        self.assertEqual(self.status(ticker_raw="7203"), "non_us_listing")

    def test_row_without_an_exchange(self):
        self.assertEqual(self.status(ticker_raw="AYR"), "no_exchange")

    def test_domestic_filer_by_name_is_kept_whatever_the_isin(self):
        self.assertEqual(self.status(name="Apple Inc."), "kept")
        self.assertEqual(self.status(name="Apple Inc.", isin="XS0000000000"), "kept")

    def test_multiple_tickers_for_one_name_is_ambiguous(self):
        # SEC lists GOOGL and GOOG as "Alphabet Inc."; with no alias that is
        # two candidate lines.
        bare = ListingResolver(self.provider.lookup_ticker, self.provider.name_index,
                               lambda cik: _FORMS.get(cik), aliases={})
        out = bare.resolve_row({"name": "Alphabet Inc"})
        self.assertEqual(out["resolution"]["status"], "ambiguous_name")
        self.assertIn("GOOG", out["resolution"]["detail"])

    def test_curated_alias_resolves_class_consolidation(self):
        out = self.resolver.resolve_row({"name": "Alphabet Inc Class C"})
        self.assertEqual(out["ticker_resolved"], "GOOGL")
        self.assertEqual(out["resolution"]["method"], "alias")
        self.assertEqual(out["resolution"]["status"], "kept")

    def test_chinese_alias_still_needs_evidence_for_a_foreign_issuer(self):
        self.assertEqual(self.status(name="台積電"), "ambiguous_listing")
        self.assertEqual(self.status(name="台積電", isin="TW0002330008"), "non_us_listing")
        self.assertEqual(self.status(name="輝達"), "kept")

    def test_unknown_name_is_unresolved(self):
        self.assertEqual(self.status(name="Tencent Holdings Ltd"), "unresolved_name")

    def test_unknown_filer_type_is_never_read_as_domestic(self):
        unknown = ListingResolver(self.provider.lookup_ticker, self.provider.name_index,
                                  lambda cik: None, load_aliases())
        self.assertEqual(unknown.resolve_row({"name": "Apple Inc."})["resolution"]["status"],
                         "ambiguous_listing")
        self.assertEqual(unknown.resolve_row({"name": "Apple Inc. ADR"})["resolution"]["status"],
                         "kept")

    def test_recorded_submissions_give_tsmc_a_20f(self):
        self.assertEqual(self.provider.annual_form(1046179), "20-F")
        self.assertEqual(self.provider.annual_form(320193), "10-K")
        self.assertIsNone(self.provider.annual_form(1652044))     # not recorded

    def test_non_equity_rows_are_left_to_extract_holdings(self):
        data = {"funds": [{"fund_id": "F1", "holdings": [
            {"ticker_raw": "AAPL", "name": "Apple Inc", "weight": 0.05},
            {"name": "Cash and equivalents", "weight": 0.02}]}]}
        self.resolver.resolve_holdings(data)
        rows = data["funds"][0]["holdings"]
        self.assertIn("resolution", rows[0])
        self.assertNotIn("resolution", rows[1])

    def test_every_alias_names_a_ticker_in_the_sec_sample(self):
        for key, ticker in load_aliases().items():
            with self.subTest(alias=key):
                self.assertIsNotNone(self.provider.lookup_ticker(ticker), ticker)


class TestExtractHoldingsUsesTheResolution(_Resolver):
    def _fund(self, rows):
        fund = {"fund_id": "F1", "holdings": rows}
        self.resolver.resolve_holdings({"funds": [fund]})
        return fund

    def test_kept_if_and_only_if_status_is_kept(self):
        from extract_holdings import filter_fund_holdings
        fund = self._fund([
            {"ticker_raw": "AAPL", "name": "Apple", "weight": 0.07},
            {"ticker_raw": "ACN", "name": "Accenture", "isin": "IE00B4BNMY34", "weight": 0.02},
            {"ticker_raw": "2330.TW", "name": "TSMC", "weight": 0.05},
            {"ticker_raw": "TCEHY", "name": "Tencent", "weight": 0.03},
            {"name": "Taiwan Semiconductor Manufacturing", "weight": 0.04},
            {"name": "Cash", "weight": 0.01},
        ])
        kept, scope = filter_fund_holdings(fund)
        self.assertEqual([h["ticker_normalized"] for h in kept], ["AAPL", "ACN"])
        self.assertEqual(scope["listing_check"], "sec_exchange_file")
        self.assertEqual(scope["resolution_counts"],
                         {"ambiguous_listing": 1, "kept": 2, "non_us_listing": 1,
                          "unresolved_ticker": 1})
        reasons = {r["status"]: r["reason"] for r in scope["dropped_rows"]}
        self.assertIn("non-US exchange line", reasons["non_us_listing"])
        self.assertEqual(scope["n_dropped_non_equity"], 1)

    def test_unresolved_fund_is_labelled_legacy(self):
        from extract_holdings import filter_fund_holdings
        kept, scope = filter_fund_holdings({"fund_id": "F2", "holdings": [
            {"ticker_raw": "AAPL", "name": "Apple", "weight": 0.07},
            {"ticker_raw": "TCEHY.PK", "name": "Tencent", "weight": 0.03}]})
        self.assertEqual(scope["listing_check"], "legacy_format_check")
        self.assertEqual([h["ticker_normalized"] for h in kept], ["AAPL"])
        self.assertEqual(scope["dropped_rows"][0]["status"], "legacy_dropped")

    def test_layer1_reports_counts_and_reasons(self):
        from extract_holdings import filter_fund_holdings
        from layer1_report import build_layer1_md
        fund = self._fund([
            {"ticker_raw": "AAPL", "name": "Apple", "weight": 0.07},
            {"ticker_raw": "2330.TW", "name": "TSMC", "weight": 0.05},
            {"name": "Taiwan Semiconductor Manufacturing", "weight": 0.04},
        ])
        _, fund["scope_summary"] = filter_fund_holdings(fund)
        fund.update(rejected=False, currency="USD")
        md = build_layer1_md({"funds": [fund], "unique_universe": [], "pit_snapshot_info": []})
        review = md[md.index("### US listing check"):md.index("### Reporting currency")]
        self.assertIn("| Fund | Kept | Non-US line | Ambiguous |", review)
        self.assertIn("| F1 | 1 | 1 | 1 |", review)
        self.assertIn("2330.TW / TSMC — non_us_listing", review)
        self.assertIn("ambiguous_listing", review)
        self.assertIn("A non-US ISIN alone never", review)


class TestResolveTickersCli(unittest.TestCase):
    def test_offline_replay_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "cache"
            cache.mkdir()
            for path in _FIXTURES.glob("submissions_[0-9]*.json"):
                shutil.copy(path, cache / path.name)
            holdings = tmp / "holdings.json"
            holdings.write_text(json.dumps({"funds": [{"fund_id": "F1", "holdings": [
                {"ticker_raw": "TSM", "name": "TSMC", "weight": 0.06},
                {"name": "Taiwan Semiconductor Manufacturing", "weight": 0.05, "page": 2},
            ]}]}), encoding="utf-8")
            env = {**os.environ, "EDGAR_CACHE_DIR": str(cache)}
            env.pop("EDGAR_CONTACT_EMAIL", None)
            run = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "scripts" / "resolve_tickers.py"),
                 "--holdings", str(holdings), "--sec-file", str(_SAMPLE), "--offline"],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("F1: ambiguous_listing 1, kept 1", run.stdout)
            self.assertIn("F1.holdings[1] p2", run.stdout)
            rows = json.loads(holdings.read_text(encoding="utf-8"))["funds"][0]["holdings"]
            self.assertEqual(rows[0]["resolution"]["status"], "kept")
            self.assertEqual(rows[1]["resolution"]["status"], "ambiguous_listing")

    def test_online_run_requires_the_email(self):
        env = {k: v for k, v in os.environ.items() if k != "EDGAR_CONTACT_EMAIL"}
        run = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "scripts" / "resolve_tickers.py"),
             "--holdings", "unused.json"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(run.returncode, 2)
        self.assertIn("403", run.stderr)


class TestIndustryMap(unittest.TestCase):
    def test_yfinance_consumer_sector_names(self):
        from providers.industry_map import normalize, sector_etf
        self.assertEqual(normalize("Consumer Cyclical"), "consumer_discretionary")
        self.assertEqual(normalize("Consumer Defensive"), "consumer_staples")
        self.assertEqual(sector_etf(normalize("Consumer Cyclical")), "XLY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
