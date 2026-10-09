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


if __name__ == "__main__":
    unittest.main()
