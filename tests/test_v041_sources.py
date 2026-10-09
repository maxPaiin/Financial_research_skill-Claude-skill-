"""v0.41 — the source whitelist and the search-first retrieval protocol.

Fetch only whitelisted pages that a search surfaced; cite only whitelisted
institutions; record every fetched page in sources_log.json. The gate
(check_checkpoints.py) enforces the last two mechanically.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import source_whitelist as sw  # noqa: E402

_FED = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
_BLS = "https://www.bls.gov/news.release/archives/cpi_09112026.htm"
_BLACKROCK = "https://www.blackrock.com/us/individual/literature/market-commentary/x.pdf"


def _seed(work: Path) -> None:
    (work / "layer1_extraction.md").write_text(
        "# Layer 1\n## Input review\n## Per-fund extraction\n")
    (work / "layer2_screening.md").write_text(
        "## Quality screen results\n## Consensus structure\n## Exit liquidity\n"
        "## Reporting currency and the exit-liquidity aggregate\n")
    (work / "layer3_ranked_advice.md").write_text(
        "## Methodology disclosure\nConsensus band\nConfidence-shrinkage\nExit liquidity\n")


def _log(work: Path, urls: list[str]) -> None:
    (work / "sources_log.json").write_text(json.dumps(
        {"version": "0.41", "fetched": [{"stage": "M1", "url": u, "cite_as": "x"} for u in urls]}))


def _review(setup) -> dict:
    import check_checkpoints as cc
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        _seed(work)
        setup(work)
        return cc.review(work, set())


class TestWhitelistData(unittest.TestCase):
    def test_every_institution_has_aliases_and_domains(self):
        insts = sw.load()
        for iid, rec in insts.items():
            with self.subTest(institution=iid):
                self.assertTrue(rec["name"])
                self.assertTrue(rec["aliases"])
                self.assertTrue(rec["domains"])

    def test_the_c2_primary_tier_is_on_the_list(self):
        # macro_appendix.md C2: central banks, official statistics, Reuters, WSJ,
        # BlackRock, Fitch (+ US Census Bureau, DEC-F1).
        self.assertEqual(set(sw.load()), {
            "fed", "ecb", "boj", "bls", "bea", "census", "eurostat", "estat",
            "reuters", "wsj", "blackrock", "fitch"})

    def test_aliases_and_domains_are_unique(self):
        aliases, domains = {}, {}
        for iid, rec in sw.load().items():
            for a in rec["aliases"]:
                self.assertNotIn(a.lower(), aliases, f"alias {a!r} used twice")
                aliases[a.lower()] = iid
            for d in rec["domains"]:
                self.assertNotIn(d.lower(), domains, f"domain {d!r} used twice")
                domains[d.lower()] = iid


class TestUrlMapping(unittest.TestCase):
    CASES = [
        (_FED, "fed"),
        ("https://federalreserve.gov/monetarypolicy/fomccalendars.htm", "fed"),
        ("https://fred.stlouisfed.org/series/CPIAUCSL", "fed"),
        ("https://minneapolisfed.org/beige-book-reports/2026/2026-09-su", "fed"),
        (_BLS, "bls"),
        ("https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k260918a.pdf", "boj"),
        ("https://ec.europa.eu/eurostat/web/main/home", "eurostat"),
        ("https://www.reuters.com/markets/us/x", "reuters"),
        (_BLACKROCK, "blackrock"),
        # not whitelisted
        ("https://ec.europa.eu/commission/presscorner/x", None),       # path prefix
        ("https://ec.europa.eu/eurostatistics/x", None),              # prefix boundary
        ("https://federalreserve.gov.example.com/x", None),           # suffix trick
        ("https://evilfederalreserve.gov/x", None),                   # not a subdomain
        ("https://federalreserve.gov@example.com/x", None),           # userinfo trick
        ("https://finance.yahoo.com/news/reuters-copy-x.html", None),  # syndicated copy
        ("https://www.scmp.com/business/x", None),
        ("ftp://www.federalreserve.gov/x", None),
        ("federalreserve.gov/x", None),                               # no scheme
        ("", None),
    ]

    def test_cases(self):
        for url, expected in self.CASES:
            with self.subTest(url=url):
                self.assertEqual(sw.institution_for_url(url), expected)


class TestCitationMapping(unittest.TestCase):
    CASES = [
        ("Fed FOMC statement 2026-09-16", "fed"),
        ("Fed", "fed"),
        ("FOMC statement", "fed"),
        ("Federal Reserve Financial Stability Report 2026-05", "fed"),
        ("Beige Book 2026-09", "fed"),
        ("BLS CPI release 2026-09-11", "bls"),
        ("BoJ MPM decision 2026-09-18", "boj"),
        ("BOJ statement", "boj"),
        ("BlackRock Investment Institute 2026-07", "blackrock"),
        ("Reuters 2026-08-04", "reuters"),
        ("The Wall Street Journal 2026-07-30", "wsj"),
        ("e-Stat CPI Japan", "estat"),
        # not whitelisted
        ("Federalist Papers", None),          # word boundary
        ("Kitco (Reuters wire)", None),       # must START with an alias
        ("SCMP 2026-09-01", None),
        ("Xinhua", None),
        ("Bloomberg", None),
        ("", None),
    ]

    def test_cases(self):
        for item, expected in self.CASES:
            with self.subTest(item=item):
                self.assertEqual(sw.institution_for_citation(item), expected)

    def test_citation_items(self):
        self.assertEqual(sw.citation_items("[Fed SEP 2026-09; BLS CPI ;  ]"),
                         ["Fed SEP 2026-09", "BLS CPI"])


class TestGateWhitelist(unittest.TestCase):
    def test_whitelisted_and_fetched_sources_pass(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text(
                "Rates rose. [Fed FOMC statement 2026-09-16; BLS CPI release 2026-09-11]\n")
            _log(work, [_FED, _BLS])
        self.assertTrue(_review(setup)["ok"])

    def test_unlisted_source_in_a_checkpoint_fails(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text(
                "Rates rose. [Fed FOMC statement; SCMP 2026-09-01]\n")
            _log(work, [_FED])
        res = _review(setup)
        self.assertFalse(res["ok"])
        self.assertTrue(any("'SCMP 2026-09-01'" in p and "not a whitelisted source" in p
                            for p in res["problems"]), res["problems"])

    def test_unlisted_source_in_the_expectations_checkpoint_fails(self):
        def setup(work):
            (work / "expectations_checkpoint.md").write_text(
                "Best Average Worst. [Fed SEP; Motley Fool]\n")
            _log(work, [_FED])
        self.assertFalse(_review(setup)["ok"])

    def test_unlisted_source_in_json_source_lists_fails(self):
        for name, payload in (
            ("macro_factors.json", {"policy_rate_direction": "tightening",
                                    "inflation_trend": "rising",
                                    "sources": {"policy_rate_direction": ["Fed FOMC", "Kitco"]}}),
            ("sector_logic.json", {"industries": {"technology": {"sources": ["Omdia"]}}}),
        ):
            with self.subTest(file=name):
                def setup(work, name=name, payload=payload):
                    (work / name).write_text(json.dumps(payload))
                    _log(work, [_FED])
                res = _review(setup)
                self.assertFalse(res["ok"])
                self.assertTrue(any(p.startswith(name) and "not a whitelisted source" in p
                                    for p in res["problems"]), res["problems"])


class TestGateInternalData(unittest.TestCase):
    """The run's own data (Layer 2, SEC EDGAR, yfinance) is evidence about a stock,
    not a macro or sentiment source."""

    def test_internal_data_is_accepted_in_sector_logic(self):
        def setup(work):
            (work / "sector_logic.json").write_text(json.dumps({"industries": {"technology": {
                "sources": ["Fed Beige Book 2026-09", "Layer 2 fundamentals (SEC EDGAR)"]}}}))
            _log(work, [_FED])
        self.assertTrue(_review(setup)["ok"], _review(setup)["problems"])

    def test_internal_data_is_refused_in_the_notice_and_macro_factors(self):
        for name, write in (
            ("important_notice_checkpoint.md",
             lambda w: (w / "important_notice_checkpoint.md").write_text(
                 "## Important Notice\nExpectations bar. Sentiment cycle. regime. already fully "
                 "priced.\n\n### AAA — technology\n\nElevated. [Fed FSR 2026-05; Layer 2]\n")),
            ("macro_factors.json",
             lambda w: (w / "macro_factors.json").write_text(json.dumps(
                 {"sources": {"inflation_trend": ["BLS CPI", "yfinance"]}}))),
        ):
            with self.subTest(file=name):
                def setup(work, write=write):
                    write(work)
                    _log(work, [_FED, _BLS])
                res = _review(setup)
                self.assertFalse(res["ok"])
                self.assertTrue(any(p.startswith(name) and "run's own data" in p
                                    for p in res["problems"]), res["problems"])

    def test_a_repeated_bad_source_is_reported_once(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text(
                "A. [Fed SEP; BoE FPC 2026-07]\nB. [Fed SEP; BoE FPC 2026-07]\n")
            _log(work, [_FED])
        problems = [p for p in _review(setup)["problems"] if "BoE FPC" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("(2 times)", problems[0])


class TestGateSourcesLog(unittest.TestCase):
    def test_citations_without_a_log_fail(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text("Rates rose. [Fed; BLS]\n")
        res = _review(setup)
        self.assertFalse(res["ok"])
        self.assertTrue(any("sources_log.json: missing" in p for p in res["problems"]))

    def test_cited_institution_must_have_a_fetched_page(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text("Rates rose. [Fed; BLS]\n")
            _log(work, [_FED])                       # BLS cited, never fetched
        res = _review(setup)
        self.assertFalse(res["ok"])
        self.assertTrue(any("Bureau of Labor Statistics" in p and "(R6)" in p
                            for p in res["problems"]), res["problems"])

    def test_a_fetched_page_off_the_whitelist_fails(self):
        def setup(work):
            (work / "macro_checkpoint.md").write_text("Rates rose. [Fed; BLS]\n")
            _log(work, [_FED, _BLS, "https://www.scmp.com/business/x"])
        res = _review(setup)
        self.assertFalse(res["ok"])
        self.assertTrue(any("scmp.com" in p and "(R3)" in p for p in res["problems"]))

    def test_no_macro_stage_needs_no_log(self):
        # The macro stages stay removable: no citation, no log, gate passes.
        self.assertTrue(_review(lambda work: None)["ok"])

    def test_not_found_notice_needs_no_log(self):
        def setup(work):
            (work / "important_notice_checkpoint.md").write_text(
                "## Important Notice — Expectations Environment and Sentiment Cycle\n\n"
                "The tool has no regime-detection capability. A Tier A name is more likely "
                "already fully priced.\n\n### AAA — technology\n\n**Expectations bar.** No "
                "publicly available evidence meeting the corroboration standard was found "
                "for this group.\n\n**Sentiment cycle.** No publicly available evidence "
                "meeting the corroboration standard was found for this group.\n")
        self.assertTrue(_review(setup)["ok"], _review(setup)["problems"])


class TestCli(unittest.TestCase):
    def test_check_exit_codes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sw.main(["check", _FED, _BLS]), 0)
            self.assertEqual(sw.main(["check", _FED, "https://www.scmp.com/x"]), 1)
            self.assertEqual(sw.main(["domains"]), 0)
            self.assertEqual(sw.main([]), 2)
        self.assertIn("NO https://www.scmp.com/x", out.getvalue())


class TestDocsFollowTheProtocol(unittest.TestCase):
    """The v0.3 'directed fetch by URL, never by open search' rule is gone everywhere
    a run reads it (CHANGELOG keeps the history)."""

    _STALE = re.compile(r"directed[- ]fetch|directed URL", re.IGNORECASE)

    def test_no_directed_fetch_instruction_remains(self):
        files = [_REPO_ROOT / "SKILL.md", _REPO_ROOT / "README.md",
                 *sorted((_REPO_ROOT / "references").glob("*.md")),
                 *sorted((_REPO_ROOT / "scripts").glob("*.py"))]
        offenders = [p.name for p in files if self._STALE.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_retrieval_protocol_is_documented_where_m1_reads(self):
        text = (_REPO_ROOT / "references" / "macro_appendix.md").read_text(encoding="utf-8")
        self.assertIn("## Retrieval protocol and the source whitelist (v0.41)", text)
        for rule in ("R1", "R2", "R3", "R4", "R5", "R6"):
            self.assertIn(f"**{rule}", text)
        skill = (_REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/source_whitelist.json", skill)


if __name__ == "__main__":
    unittest.main()
