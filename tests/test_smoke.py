"""
Smoke tests for the financial-research skill.

Runs with stdlib unittest only (no pytest dependency):

    python -m unittest discover tests -v

These are deliberately fast and offline: no network calls, no external
fixtures, no pytest. They cover the modules whose bugs were caught in the
review and ensure subsequent edits don't regress the fixes.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

# Put scripts/ on sys.path so tests can `import quality_screen` etc.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))


# -----------------------------------------------------------------------------
# validate_uploads — date regex (M6)
# -----------------------------------------------------------------------------

class TestDateRegex(unittest.TestCase):
    def setUp(self):
        from validate_uploads import _DATE_RE
        self.re = _DATE_RE

    def test_iso_format(self):
        self.assertIsNotNone(self.re.search("as of 2025-03-31"))

    def test_slash_dmy(self):
        self.assertIsNotNone(self.re.search("Reporting date: 31/03/2025"))

    def test_quarter(self):
        self.assertIsNotNone(self.re.search("Q1 2025 fact sheet"))
        self.assertIsNotNone(self.re.search("As at Q4-2024"))

    def test_fy(self):
        self.assertIsNotNone(self.re.search("FY 2024 annual report"))
        self.assertIsNotNone(self.re.search("FY24"))

    def test_month_day_year_comma(self):
        self.assertIsNotNone(self.re.search("Data as of March 31, 2025"))

    def test_day_month_year(self):
        self.assertIsNotNone(self.re.search("Data as of 31 March 2025"))

    def test_month_year_only(self):
        self.assertIsNotNone(self.re.search("As of March 2025"))

    def test_half_year(self):
        self.assertIsNotNone(self.re.search("H1 2025 update"))

    def test_no_date(self):
        self.assertIsNone(self.re.search("Marketing brochure with no dates"))


# -----------------------------------------------------------------------------
# validate_uploads — B1 SEC contact-email gate (v0.3)
# -----------------------------------------------------------------------------

class TestEmailGate(unittest.TestCase):
    def test_valid_emails(self):
        from validate_uploads import valid_email
        for e in ("a@b.com", "ops.team@example.co.uk", "  me@x.io  "):
            self.assertTrue(valid_email(e), e)

    def test_invalid_emails(self):
        from validate_uploads import valid_email
        for e in (None, "", "nope", "a@b", "a@@b.com", "no spaces @x.com"):
            self.assertFalse(valid_email(e), e)

    def test_gate_message_states_why_and_privacy(self):
        from validate_uploads import EMAIL_GATE_MESSAGE
        self.assertIn("403", EMAIL_GATE_MESSAGE)
        self.assertIn("Privacy", EMAIL_GATE_MESSAGE)

    def test_validate_fails_without_email(self):
        from validate_uploads import validate
        with tempfile.TemporaryDirectory() as tmp:
            res = validate(Path(tmp), email=None)
            self.assertFalse(res["ok"])
            self.assertFalse(res["email_ok"])
            self.assertTrue(any("403" in e for e in res["errors"]))


class TestEdgarUserAgent(unittest.TestCase):
    def test_ua_carries_email(self):
        from providers.edgar_provider import EDGARProvider, _USER_AGENT_APP
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), contact_email="ops@example.com")
            ua = p._session.headers["User-Agent"]
            self.assertIn("ops@example.com", ua)
            self.assertIn(_USER_AGENT_APP, ua)

    def test_ua_without_email_has_no_at(self):
        from providers.edgar_provider import EDGARProvider
        with tempfile.TemporaryDirectory() as tmp:
            p = EDGARProvider(cache_dir=Path(tmp), contact_email=None)
            self.assertNotIn("@", p._session.headers["User-Agent"])


# -----------------------------------------------------------------------------
# extract_holdings — ticker normalization (M1) & non-equity detection (M2)
# -----------------------------------------------------------------------------

class TestTickerNormalization(unittest.TestCase):
    def setUp(self):
        from extract_holdings import normalize_us_ticker
        self.fn = normalize_us_ticker

    def test_plain_us(self):
        self.assertEqual(self.fn("AAPL"), "AAPL")
        self.assertEqual(self.fn("MSFT"), "MSFT")
        self.assertEqual(self.fn("GOOGL"), "GOOGL")

    def test_share_class_single_char(self):
        self.assertEqual(self.fn("BRK.B"), "BRK.B")
        self.assertEqual(self.fn("BF.B"), "BF.B")
        self.assertEqual(self.fn("LGF.A"), "LGF.A")

    def test_share_class_two_char(self):
        # M1: BAC.PB (preferred series B) — the v1 regex rejected this.
        self.assertEqual(self.fn("BAC.PB"), "BAC.PB")
        self.assertEqual(self.fn("GS.PD"), "GS.PD")

    def test_strips_us_suffix(self):
        self.assertEqual(self.fn("AAPL US"), "AAPL")
        self.assertEqual(self.fn("MSFT.O"), "MSFT")

    def test_drops_non_us_listings(self):
        self.assertIsNone(self.fn("7203.T"))
        self.assertIsNone(self.fn("0700.HK"))
        self.assertIsNone(self.fn("VOD.L"))

    def test_rejects_garbage(self):
        self.assertIsNone(self.fn(""))
        self.assertIsNone(self.fn("not-a-ticker"))
        self.assertIsNone(self.fn("123456"))


class TestNonEquityDetection(unittest.TestCase):
    def setUp(self):
        from extract_holdings import is_non_equity
        self.fn = is_non_equity

    def test_actual_non_equity(self):
        self.assertTrue(self.fn({"name": "US Treasury Bond 2.5% 2030"}))
        self.assertTrue(self.fn({"name": "Cash and equivalents"}))
        self.assertTrue(self.fn({"name": "SPDR S&P 500 ETF"}))
        self.assertTrue(self.fn({"name": "Money Market Fund"}))
        self.assertTrue(self.fn({"name": "Apple Inc Warrant"}))

    def test_companies_with_keywords_in_name(self):
        # M2: substring match would have incorrectly flagged these.
        self.assertFalse(self.fn({"name": "Cashmere Holdings Inc."}))
        self.assertFalse(self.fn({"name": "Optionix Therapeutics"}))
        self.assertFalse(self.fn({"name": "Etfix Industries"}))


# -----------------------------------------------------------------------------
# quality_screen — pass/fail decisions
# -----------------------------------------------------------------------------

class TestQualityScreen(unittest.TestCase):
    def _make_record(
        self,
        roe_values=(0.20, 0.22, 0.24, 0.26, 0.28),
        de_value=0.5,
        ni_values=None,
        ev_value=22.0,
    ):
        from providers.base import DataPoint, FundamentalsRecord
        conf = 0.9
        asof = date(2025, 5, 1)

        def dp(v):
            return DataPoint(value=v, confidence=conf, source="test", asof=asof)

        return FundamentalsRecord(
            ticker="TEST",
            asof=asof,
            roe_5y=[dp(v) for v in roe_values],
            ev_ebitda=dp(ev_value) if ev_value is not None else None,
            debt_equity=dp(de_value) if de_value is not None else None,
            net_income_5y=[dp(v) for v in (ni_values or [1, 1, 1, 1, 1])],
            industry="technology",
            is_adr=False,
        )

    def test_pass(self):
        from quality_screen import screen
        rec = self._make_record()
        result = screen("TEST", rec)
        self.assertTrue(result.passed)

    def test_fail_high_debt(self):
        from quality_screen import screen
        rec = self._make_record(de_value=6.0)  # > 5.0 ceiling
        result = screen("TEST", rec)
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "distress_debt_ratio")

    def test_fail_negative_roe(self):
        from quality_screen import screen
        rec = self._make_record(roe_values=(-0.05, -0.03, -0.02, 0.01, 0.02))
        result = screen("TEST", rec)
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "roe_insufficient")

    def test_fail_consecutive_negative_ni(self):
        from quality_screen import screen
        rec = self._make_record(ni_values=[-1, -1, -1, 0.5, 0.5])
        result = screen("TEST", rec)
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "persistent_negative_earnings")


# -----------------------------------------------------------------------------
# crowding_signal — compute() math
# -----------------------------------------------------------------------------

class TestCrowdingSignal(unittest.TestCase):
    def test_no_crowding_when_below_threshold(self):
        from crowding_signal import compute
        # avg_weight 1% is below the 2% threshold → no discount
        result = compute("X", n_funds_holding=3, avg_weight=0.01)
        self.assertEqual(result.crowding_discount, 0.0)
        self.assertFalse(result.is_high_crowding)

    def test_crowding_grows_with_weight_and_funds(self):
        from crowding_signal import compute
        low = compute("X", n_funds_holding=3, avg_weight=0.03)
        high = compute("X", n_funds_holding=8, avg_weight=0.08)
        self.assertGreater(high.crowding_discount, low.crowding_discount)

    def test_discount_capped(self):
        from crowding_signal import compute
        result = compute("X", n_funds_holding=20, avg_weight=0.20)
        self.assertLessEqual(result.crowding_discount, 0.60)

    # --- A2: days-to-liquidate (v0.3) ---
    def test_nav_only_fallback_when_no_liquidity_data(self):
        from crowding_signal import compute
        r = compute("X", n_funds_holding=4, avg_weight=0.03)
        self.assertEqual(r.crowding_label, "NAV-only")
        self.assertIsNone(r.days_to_liquidate)
        # NAV-only must equal the pure-weight base (no amplifier).
        base = max(0.0, (0.03 - 0.02) / 0.08) * (4 / 5.0)
        self.assertAlmostEqual(r.crowding_discount, round(base, 4), places=4)

    def test_illiquid_midcap_penalised_harder(self):
        from crowding_signal import compute
        big = compute("BIG", 4, 0.03, adv_usd=5e9, aggregate_position_usd=2e9)
        mid = compute("MID", 4, 0.03, adv_usd=5e7, aggregate_position_usd=2e9)
        self.assertEqual(big.crowding_label, "liquidity-inclusive")
        self.assertGreater(mid.days_to_liquidate, big.days_to_liquidate)
        self.assertGreater(mid.crowding_discount, big.crowding_discount)

    # --- A3: style-diversity-weighted consensus (v0.3) ---
    def test_diverse_holders_beat_homogeneous(self):
        from crowding_signal import compute
        homo = compute("H", 6, 0.03, holder_styles=["growth"] * 6)
        divr = compute("D", 6, 0.03, holder_styles=[
            "growth", "value", "blend", "income_dividend",
            "small_mid_cap", "region_tilt_non_us"])
        self.assertEqual(homo.style_diversity, 0.0)
        self.assertEqual(divr.style_diversity, 1.0)
        self.assertGreater(divr.consensus_weighted, homo.consensus_weighted)

    def test_unlabelled_styles_no_weighting(self):
        from crowding_signal import compute
        r = compute("X", 5, 0.03, holder_styles=None)
        self.assertIsNone(r.style_diversity)
        self.assertEqual(r.consensus_weighted, r.consensus_raw)

    def test_homogeneity_report(self):
        from crowding_signal import homogeneity_report
        homo = homogeneity_report({"F1": "growth", "F2": "growth", "F3": "growth"}, 3)
        self.assertTrue(homo["is_homogeneous"])
        self.assertEqual(homo["dominant_style"], "growth")
        mixed = homogeneity_report(
            {"F1": "growth", "F2": "value", "F3": "income_dividend"}, 3)
        self.assertFalse(mixed["is_homogeneous"])
        none = homogeneity_report({}, 3)
        self.assertFalse(none["labelled"])


# -----------------------------------------------------------------------------
# build_rankings — A4 low-anchor confidence shrinkage (v0.3)
# -----------------------------------------------------------------------------

class TestLowAnchorShrinkage(unittest.TestCase):
    def test_lower_confidence_pulled_lower(self):
        from build_rankings import low_anchor_shrink
        edgar = low_anchor_shrink(80.0, 0.9)
        yfin = low_anchor_shrink(80.0, 0.5)
        self.assertGreater(edgar, yfin)
        # EDGAR (0.9) barely moved off 80; yfinance (0.5) pulled toward 10.
        self.assertGreater(edgar, 70.0)
        self.assertLess(yfin, 50.0)

    def test_q_low_floor_is_positive(self):
        from build_rankings import low_anchor_shrink
        # A low-confidence zero-Q stock must floor above 0 (Q_LOW > 0 invariant).
        self.assertGreater(low_anchor_shrink(0.0, 0.1), 0.0)

    def test_missing_confidence_defaults_to_shrunk(self):
        from build_rankings import low_anchor_shrink
        self.assertEqual(low_anchor_shrink(80.0, None), low_anchor_shrink(80.0, 0.5))


# -----------------------------------------------------------------------------
# build_rankings — percentile_rank (H3) & tier() (basic)
# -----------------------------------------------------------------------------

class TestPercentileRank(unittest.TestCase):
    def setUp(self):
        from build_rankings import percentile_rank
        self.fn = percentile_rank

    def test_uniform_spread(self):
        values = list(range(1, 11))  # 1..10
        ranks = [self.fn(v, values) for v in values]
        # Lowest gets ~5, highest gets ~95
        self.assertLess(ranks[0], ranks[-1])
        self.assertLess(ranks[0], 20.0)
        self.assertGreater(ranks[-1], 80.0)

    def test_outlier_does_not_squash_others(self):
        # H3 regression: under min-max, one outlier squashed the rest to ~0-10.
        # Percentile rank should give roughly even spacing regardless.
        values = [0.7, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.85, 10.0]
        ranks = [self.fn(v, values) for v in values]
        # Difference between adjacent low ranks should be > 5 (i.e., spread)
        adjacent_diffs = [ranks[i+1] - ranks[i] for i in range(len(ranks) - 2)]
        self.assertTrue(all(d > 5 for d in adjacent_diffs),
                        f"expected even spread, got diffs={adjacent_diffs}")


# -----------------------------------------------------------------------------
# resolver — agree / disagree / clear
# -----------------------------------------------------------------------------

class TestResolver(unittest.TestCase):
    def test_agree(self):
        from providers.base import DataPoint
        from providers.resolver import resolve, _PROVENANCE_LOG
        _PROVENANCE_LOG.clear()
        a = DataPoint(value=1.00, confidence=0.9, source="edgar",
                      asof=date(2025, 5, 1))
        b = DataPoint(value=1.02, confidence=0.5, source="yf",
                      asof=date(2025, 5, 1))
        merged = resolve([a, b])
        # Within 5% → averaged, n_sources_agreed=2, conf=max
        self.assertAlmostEqual(merged.value, 1.01, places=4)
        self.assertEqual(merged.n_sources_agreed, 2)
        self.assertEqual(merged.confidence, 0.9)
        self.assertEqual(len(_PROVENANCE_LOG), 0)  # no conflict logged

    def test_high_conflict_logged(self):
        from providers.base import DataPoint
        from providers.resolver import resolve, _PROVENANCE_LOG
        _PROVENANCE_LOG.clear()
        a = DataPoint(value=0.5, confidence=0.9, source="edgar",
                      asof=date(2025, 5, 1))
        b = DataPoint(value=0.8, confidence=0.5, source="yf",
                      asof=date(2025, 5, 1))
        merged = resolve([a, b])
        # >20% diff → higher-confidence wins, confidence halved, log entry written
        self.assertEqual(merged.value, 0.5)
        self.assertEqual(merged.confidence, 0.45)
        self.assertEqual(len(_PROVENANCE_LOG), 1)
        self.assertEqual(_PROVENANCE_LOG[0]["severity"], "high")

    def test_flush_clears_log(self):
        # M5: flush must clear the log so reusing the registry doesn't
        # duplicate prior conflicts.
        from providers.base import DataPoint
        from providers.resolver import resolve, flush_provenance, _PROVENANCE_LOG
        _PROVENANCE_LOG.clear()
        a = DataPoint(value=0.5, confidence=0.9, source="edgar",
                      asof=date(2025, 5, 1))
        b = DataPoint(value=0.8, confidence=0.5, source="yf",
                      asof=date(2025, 5, 1))
        resolve([a, b])
        self.assertEqual(len(_PROVENANCE_LOG), 1)
        with tempfile.TemporaryDirectory() as tmp:
            flush_provenance(Path(tmp) / "p.json")
        self.assertEqual(len(_PROVENANCE_LOG), 0)


# -----------------------------------------------------------------------------
# yfinance_provider — US-country detection (H4)
# -----------------------------------------------------------------------------

class TestUSCountry(unittest.TestCase):
    def test_us_variants_accepted(self):
        # Import lazily because the module imports yfinance at load time.
        from providers.yfinance_provider import _is_us_country
        for variant in ("United States", "USA", "US", "U.S.", "U.S.A.",
                        "United States of America", "united states", "  USA  "):
            with self.subTest(variant=variant):
                self.assertTrue(_is_us_country(variant))

    def test_non_us_rejected(self):
        from providers.yfinance_provider import _is_us_country
        for variant in ("Hong Kong", "China", "Cayman Islands",
                        "Bermuda", "", None):
            with self.subTest(variant=variant):
                self.assertFalse(_is_us_country(variant))


# -----------------------------------------------------------------------------
# edgar_provider — USD unit filter (H1) & filing detection (H2)
# -----------------------------------------------------------------------------

class TestEdgarUnitFilter(unittest.TestCase):
    def setUp(self):
        from providers.edgar_provider import EDGARProvider
        self.tmp = tempfile.TemporaryDirectory()
        self.edgar = EDGARProvider(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_mixed_units_filter_to_usd_only(self):
        # H1: previously the iterator pulled values from EVERY unit, including
        # EUR duplicates of NetIncome reported by 20-F filers.
        facts = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "end": "2024-12-31",
                                 "val": 100_000_000},
                                {"form": "10-K", "end": "2023-12-31",
                                 "val": 90_000_000},
                            ],
                            "EUR": [
                                {"form": "10-K", "end": "2024-12-31",
                                 "val": 92_000_000},
                            ],
                        }
                    }
                }
            }
        }
        series = self.edgar._extract_annual_series(
            facts, "NetIncomeLoss", 5, date(2025, 5, 1)
        )
        self.assertIn(100_000_000, series)
        self.assertIn(90_000_000, series)
        self.assertNotIn(92_000_000, series)

    def test_latest_filing_end_date(self):
        # M4 Level 2 prerequisite — make sure the latest period-end is found.
        facts = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "end": "2024-12-31", "val": 100},
                                {"form": "10-K", "end": "2023-12-31", "val": 90},
                                {"form": "10-K", "end": "2026-12-31", "val": 5},
                            ]
                        }
                    },
                }
            }
        }
        # The 2026 entry is dated after asof → must be skipped.
        latest = self.edgar._latest_filing_end_date(facts, date(2025, 5, 1))
        self.assertEqual(latest, date(2024, 12, 31))


class TestEdgarFilingType(unittest.TestCase):
    def setUp(self):
        from providers.edgar_provider import EDGARProvider
        self.tmp = tempfile.TemporaryDirectory()
        self.edgar = EDGARProvider(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_submissions(self, fake):
        self.edgar._get_json = lambda url, key: fake

    def test_20f_filer(self):
        self._patch_submissions(
            {"filings": {"recent": {"form": ["20-F", "6-K"]}, "files": []}}
        )
        self.assertEqual(self.edgar._detect_filing_type(1), "20-F")

    def test_10k_filer(self):
        self._patch_submissions(
            {"filings": {"recent": {"form": ["10-K", "10-Q"]}, "files": []}}
        )
        self.assertEqual(self.edgar._detect_filing_type(1), "10-K")

    def test_files_array_does_not_leak(self):
        # H2: the previous loop spread `files` into the form scanner; files[]
        # entries are file refs, not form names, so they'd contaminate detection.
        self._patch_submissions({
            "filings": {
                "recent": {"form": []},
                "files": [{"name": "stale.json", "filingCount": 5}],
            }
        })
        self.assertEqual(self.edgar._detect_filing_type(1), "10-K")


# -----------------------------------------------------------------------------
# Pipeline — fundamentals dict round-trip preserves data_asof (M4 L2)
# -----------------------------------------------------------------------------

class TestDataAsofRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        from providers.base import DataPoint, FundamentalsRecord
        from fetch_fundamentals import record_to_dict
        from quality_screen import record_from_dict

        dp = DataPoint(value=0.5, confidence=0.9, source="edgar",
                       asof=date(2025, 5, 1))
        rec = FundamentalsRecord(
            ticker="TEST",
            asof=date(2025, 5, 1),
            roe_5y=[dp],
            debt_equity=dp,
            net_income_5y=[],
            industry="technology",
            data_asof=date(2024, 12, 31),
        )
        as_dict = record_to_dict(rec, source="edgar")
        self.assertEqual(as_dict["data_asof"], "2024-12-31")
        round_tripped = record_from_dict(as_dict)
        self.assertEqual(round_tripped.data_asof, date(2024, 12, 31))


# -----------------------------------------------------------------------------
# build_report — layer3 slicing (v0.3 D2 section order)
# -----------------------------------------------------------------------------

class TestLayer3Slice(unittest.TestCase):
    def test_slice_separates_framing_cards_methodology(self):
        import build_report
        layer3 = (
            "# Layer 3: Ranked Watchlist\n\n"
            "## What this analysis is and is not\n\nFraming prose.\n\n"
            "## Tier A\n\n### #1 AAPL\nbody\n\n"
            "## Methodology disclosure\n\n- detail\n\n"
            "## Important caveats\n\n- caveat\n\n"
            "## Disclaimer\n\nverbatim disclaimer\n"
        )
        framing, cards, methodology = build_report._slice_layer3(layer3)
        self.assertIn("Framing prose", framing)
        self.assertIn("Tier A", cards)
        self.assertNotIn("Methodology disclosure", cards)
        self.assertNotIn("Disclaimer", cards)
        self.assertIn("Methodology disclosure", methodology)
        self.assertNotIn("Disclaimer", methodology)


# -----------------------------------------------------------------------------
# check_checkpoints — D4 deterministic review gate
# -----------------------------------------------------------------------------

class TestCheckpointGate(unittest.TestCase):
    def _seed(self, work: Path):
        (work / "layer1_extraction.md").write_text(
            "# Layer 1\n## Input\n## Per-fund extraction\n")
        (work / "layer2_screening.md").write_text(
            "## Quality screen results\n## Input-set style homogeneity\n")
        (work / "layer3_ranked_advice.md").write_text(
            "## Methodology disclosure\nConfidence-shrinkage\nexit-crowdedness\n")

    def test_base_ok(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            self.assertTrue(cc.review(work, set())["ok"])

    def test_required_optional_missing_fails(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            self.assertFalse(cc.review(work, {"macro_checkpoint.md"})["ok"])

    def test_macro_requires_attribution(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            (work / "macro_checkpoint.md").write_text("Fed held rates steady.\n")
            res = cc.review(work, set())
            self.assertFalse(res["ok"])
            (work / "macro_checkpoint.md").write_text(
                "Fed held rates steady. [Fed; Reuters]\n")
            self.assertTrue(cc.review(work, set())["ok"])

    def test_bias_note_regression_caught(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            (work / "layer3_ranked_advice.md").write_text(
                "## Methodology disclosure\nConfidence-shrinkage\nexit-crowdedness\n"
                "**Bias note:** repeated per card\n")
            res = cc.review(work, set())
            self.assertFalse(res["ok"])
            self.assertTrue(any("Bias note" in p for p in res["problems"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
