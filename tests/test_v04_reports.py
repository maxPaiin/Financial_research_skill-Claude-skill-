"""
v0.4 B8 — reports and the checkpoint gate.

Layer 1 shows benchmarks, disclosure depth and the common floor; Layer 2 shows
the consensus structure and exit liquidity; Layer 3 uses the v0.4 card, lists
the benchmark-anchored core, and announces an empty tier only when the overlay
emptied a populated slice. The gate requires the new sections.

    python -m unittest tests.test_v04_reports -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))


def _stock(rank: int, ticker: str, **kw) -> dict:
    tier = "A" if rank <= 5 else "B" if rank <= 10 else "C"
    row = {"rank": rank, "tier": tier, "ticker": ticker, "name": f"{ticker} Corp",
           "band": "majority", "c_share": 0.62, "opinions": 2.5, "n_votes": 5,
           "n_holders": 7, "vote_basis_counts": {"active": 4, "presence": 1, "anchored": 1,
                                                 "below_floor": 1},
           "q_raw": 70.0, "q_shrunk": 64.0, "quality_confidence": 0.9, "roe_years": 5,
           "roe_source": "edgar", "roe_5y_avg": 0.21, "ev_ebitda": 18.0,
           "debt_equity": 0.4, "avg_weight": 0.045, "max_weight": 0.08,
           "data_asof": "2025-12-31", "industry": "technology"}
    row.update(kw)
    return row


def _rankings(ranked: list[dict], **kw) -> dict:
    out = {"ranking_method": "v0.4-consensus-bands", "vote_basis": "active", "n_funds": 8,
           "n_eff_run": 4.12, "vote_floor": 0.032, "n_eligible": 12, "n_ranked": len(ranked),
           "warning": None, "anchored_core": ["NVDA"],
           "anchored_core_detail": [{"ticker": "NVDA", "name": "NVIDIA", "n_holders": 8,
                                     "vote_basis_counts": {"anchored": 6},
                                     "screen_status": "ok"}],
           "ranked": ranked}
    out.update(kw)
    return out


def _md(rankings, coherence=None, crowding=None):
    from layer3_report import build_layer3_md
    return build_layer3_md(rankings, None, "framing", {}, coherence, crowding)


class TestLayer3Card(unittest.TestCase):
    def test_card_fields_follow_appendix_c(self):
        crowding = {"signals": [{"ticker": "AAA", "days_to_liquidate": 1.4,
                                 "is_exit_crowded": False, "n_usd_aum_holders": 3,
                                 "n_holders": 7}]}
        md = _md(_rankings([_stock(1, "AAA")]), crowding=crowding)
        card = md[md.index("### #1   AAA"):md.index("## Benchmark-anchored")]
        for needle in ("**Consensus:** Majority consensus — 2.5 of 4.1 independent opinions "
                       "(share 62%)",
                       "Votes: 5 of 8 funds (4 active, 1 presence) | benchmark-anchored "
                       "holders: 1 | below common floor (3.2%): 1",
                       "**Holdings:** held by 7 of 8 funds | avg weight where held 4.50% "
                       "| max 8.00% | asof 2025-12-31",
                       "**Exit liquidity:** 1.4 trading days for the 3 of 7 holders that "
                       "report AUM in USD to sell together",
                       "**Quality screen:** PASS | **Quality confidence:** 0.90",
                       "ROE avg: 21.0% (5 fiscal years; edgar)",
                       "EV/EBITDA: 18.00 | Debt/Equity: 0.40",
                       "**Rank:** 1 of 12 | **Tier:** A"):
            self.assertIn(needle, card)
        self.assertNotIn("Composite rank", md)
        self.assertNotIn("HIGH CROWDING", card)

    def test_high_crowding_flag_only_when_exit_crowded(self):
        crowding = {"signals": [
            {"ticker": "AAA", "days_to_liquidate": 12.3, "is_exit_crowded": True,
             "n_usd_aum_holders": 2, "n_holders": 4},
            {"ticker": "BBB", "days_to_liquidate": 9.9, "is_exit_crowded": False,
             "n_usd_aum_holders": 2, "n_holders": 4}]}
        md = _md(_rankings([_stock(1, "AAA"), _stock(2, "BBB")]), crowding=crowding)
        aaa = md[md.index("### #1   AAA"):md.index("### #2   BBB")]
        bbb = md[md.index("### #2   BBB"):md.index("## Benchmark-anchored")]
        self.assertIn("HIGH CROWDING", aaa)
        self.assertIn("12.3 trading days", aaa)
        self.assertNotIn("HIGH CROWDING", bbb)

    def test_band_labels(self):
        md = _md(_rankings([_stock(1, "AAA", band="plural"), _stock(2, "BBB", band="single")]))
        self.assertIn("Plural consensus", md)
        self.assertIn("Single-fund conviction", md)

    def test_missing_liquidity_inputs_are_said_plainly(self):
        md = _md(_rankings([_stock(1, "AAA")]), crowding={"signals": []})
        self.assertIn("no days-to-liquidate figure", md)
        self.assertIn("not reported (no crowding file", _md(_rankings([_stock(1, "AAA")])))


class TestEmptyTiers(unittest.TestCase):
    COHERENCE = {"records": [
        {"ticker": t, "base_tier": "A", "tier": "B", "tier_delta": -1,
         "contradictions": ["x"], "commentary": "demoted A->B"} for t in ("AAA", "BBB")]}

    def test_note_when_the_overlay_empties_a_populated_slice(self):
        md = _md(_rankings([_stock(1, "AAA"), _stock(2, "BBB"), _stock(6, "CCC")]),
                 coherence=self.COHERENCE)
        self.assertIn("## Tier A", md)
        self.assertIn("_No stock is displayed in Tier A: every rank 1–2 name was demoted "
                      "one tier by the overlay (ranks unchanged)._", md)
        tier_a = md[md.index("## Tier A"):md.index("## Tier B")]
        self.assertNotIn("### #", tier_a)

    def test_no_heading_for_a_slice_without_ranked_stocks(self):
        md = _md(_rankings([_stock(1, "AAA"), _stock(2, "BBB")]))
        self.assertNotIn("## Tier B", md)
        self.assertNotIn("## Tier C", md)
        self.assertNotIn("No stock is displayed", md)


class TestAnchoredSection(unittest.TestCase):
    def test_lists_the_anchored_core(self):
        md = _md(_rankings([_stock(1, "AAA")]))
        section = md[md.index("## Benchmark-anchored core holdings"):md.index("## Methodology")]
        self.assertIn("| NVDA | NVIDIA | 8 of 8 funds | 6 | ok |", section)
        self.assertIn("not ranked", section)

    def test_empty_and_presence_runs_say_so(self):
        none = _md(_rankings([_stock(1, "AAA")], anchored_core=[], anchored_core_detail=[]))
        self.assertIn("_None this run", none)
        presence = _md(_rankings([_stock(1, "AAA")], vote_basis="presence"))
        self.assertIn("this run counts presence votes", presence)

    def test_section_sits_between_the_tiers_and_the_methodology(self):
        md = _md(_rankings([_stock(1, "AAA")]))
        self.assertLess(md.index("## Tier A"), md.index("## Benchmark-anchored core holdings"))
        self.assertLess(md.index("## Benchmark-anchored core holdings"),
                        md.index("## Methodology disclosure"))


class TestMethodology(unittest.TestCase):
    def test_required_literals_and_run_numbers(self):
        md = _md(_rankings([_stock(1, "AAA")]))
        for literal in ("Consensus band", "Confidence-shrinkage", "Exit liquidity",
                        "4.12 independent opinions", "3.2% this run"):
            self.assertIn(literal, md)
        self.assertNotIn("50/50", md)

    def test_few_eligible_is_explained(self):
        md = _md(_rankings([_stock(1, "AAA")], warning="few_eligible", n_eligible=3))
        self.assertIn("Fewer than five names have a qualifying vote", md)


class TestLayer2Sections(unittest.TestCase):
    CONSENSUS = {"vote_basis": "active", "n_funds": 3, "n_eff_run": 1.87, "vote_floor": 0.03,
                 "vote_floor_set_by": ["F2"],
                 "vote_basis_coverage": {"active": 4, "presence": 2, "anchored": 3,
                                         "below_floor": 1},
                 "funds": [{"fund_id": "F1", "omega": 0.2, "marginal_contribution": 0.05,
                            "benchmark_proxy": "IXN"},
                           {"fund_id": "F2", "omega": 0.3, "marginal_contribution": 0.4,
                            "benchmark_proxy": None},
                           {"fund_id": "F3", "omega": 0.5, "marginal_contribution": 0.9,
                            "benchmark_proxy": "QQQ"}],
                 "stocks": [{"ticker": "AAA", "band": "majority"},
                            {"ticker": "NVDA", "band": "none"}],
                 "anchored_core": ["NVDA"]}
    CROWDING = {"dtl_threshold": 10.0,
                "signals": [{"ticker": "AAA", "days_to_liquidate": 14.0, "is_exit_crowded": True,
                             "n_usd_aum_holders": 2, "n_holders": 3},
                            {"ticker": "BBB", "days_to_liquidate": None,
                             "is_exit_crowded": False}],
                "homogeneity": {"labelled": True, "dominant_style": "growth",
                                "dominant_share": 1.0, "is_homogeneous": True,
                                "style_distribution": {"growth": 3}},
                "input_review": {"currency": {"by_currency": {"USD": 3},
                                              "n_excluded_for_currency": 0}}}

    def _md(self, consensus=CONSENSUS):
        from layer2_report import build_layer2_md
        return build_layer2_md({"n_tickers": 2, "overlap": []}, {"results": [], "unscored": []},
                               {}, self.CROWDING, None, consensus)

    def test_consensus_structure(self):
        md = self._md()
        section = md[md.index("## Consensus structure"):md.index("## Exit liquidity")]
        self.assertIn("N_eff = 1.87", section)
        self.assertIn("3.00% (set by F2)", section)
        self.assertIn("anchored 3", section)
        self.assertIn("| F1 | 0.200 | 0.050 | IXN |", section)
        self.assertIn("| F2 | 0.300 | 0.400 | — (presence votes) |", section)
        self.assertIn("Lowest marginal contribution: F1", section)
        self.assertIn("### Fund-style distribution (display only)", section)
        self.assertIn("Benchmark-anchored core", section)

    def test_exit_liquidity(self):
        md = self._md()
        section = md[md.index("## Exit liquidity"):md.index("## Reporting currency")]
        self.assertIn("| AAA | 14.0 | 2 of 3 | yes |", section)
        self.assertIn("1 have no liquidity data", section)
        self.assertIn("Exit-crowded (≥ 10 days, an uncalibrated line): AAA", section)

    def test_old_sections_are_gone(self):
        md = self._md()
        self.assertNotIn("Consensus-with-crowding-discount", md)
        self.assertNotIn("## Input-set style homogeneity", md)

    def test_without_consensus_file(self):
        self.assertIn("consensus.json was not supplied", self._md(None))


class TestLayer1Disclosure(unittest.TestCase):
    def test_benchmarks_depth_and_tau(self):
        from layer1_report import build_layer1_md
        funds = [
            {"fund_id": "F1", "fund_name": "Tech", "rejected": False, "currency": "USD",
             "benchmark": "MSCI AC World Information Technology Index",
             "scope_summary": {"weight_kept": 0.6, "disclosure_depth": 10,
                               "disclosure_floor": 0.024}},
            {"fund_id": "F2", "fund_name": "Global", "rejected": False, "currency": "USD",
             "benchmark": None,
             "scope_summary": {"weight_kept": 0.5, "disclosure_depth": 10,
                               "disclosure_floor": 0.031}},
        ]
        md = build_layer1_md({"funds": funds, "unique_universe": [], "pit_snapshot_info": []})
        section = md[md.index("### Benchmarks and disclosure depth"):]
        self.assertIn("| F1 | MSCI AC World Information Technology Index | IXN (approximate",
                      section)
        self.assertIn("| F2 | not printed | — (presence votes) | 10 | 3.10% |", section)
        self.assertIn("Common vote floor: **3.10%**, set by F2", section)
        self.assertIn("No benchmark proxy for F2", section)


class TestGate(unittest.TestCase):
    def _seed(self, work: Path):
        (work / "layer1_extraction.md").write_text("# Layer 1\n## Input review\n"
                                                   "## Per-fund extraction\n")
        (work / "layer2_screening.md").write_text(
            "## Quality screen results\n## Consensus structure\n## Exit liquidity\n"
            "## Reporting currency and the exit-liquidity aggregate\n")
        (work / "layer3_ranked_advice.md").write_text(
            "## Methodology disclosure\nConsensus band\nConfidence-shrinkage\nExit liquidity\n")

    def test_new_sections_are_required(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            self.assertTrue(cc.review(work, set())["ok"])
            (work / "layer2_screening.md").write_text("## Quality screen results\n")
            res = cc.review(work, set())
            self.assertFalse(res["ok"])
            self.assertTrue(any("## Consensus structure" in p for p in res["problems"]))
            self.assertTrue(any("## Exit liquidity" in p for p in res["problems"]))

    def test_appendix3_accepts_the_v04_remediation(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self._seed(work)
            (work / "appendix3_consensus_warning.md").write_text(
                "Your funds amount to 1.4 independent opinions. Replace the "
                "lowest-contribution fund with a dissimilar one.\n")
            self.assertTrue(cc.review(work, set())["ok"])
            (work / "appendix3_consensus_warning.md").write_text("Nothing to say.\n")
            self.assertFalse(cc.review(work, set())["ok"])

    def test_a_fired_check_without_a_demotion_is_caught(self):
        import check_checkpoints as cc
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coherence.json"
            path.write_text(json.dumps({"records": [{
                "ticker": "AAA", "base_tier": "A", "tier": "A", "tier_delta": 0,
                "contradictions": [], "risks": ["exit"],
                "verdicts": [{"pair": "exit_liquidity", "verdict": "risk"}]}]}))
            problems = cc.check_coherence(path)
            self.assertTrue(any("no demotion" in p for p in problems))


class TestPercentSanityBound(unittest.TestCase):
    def test_real_roe_above_100_percent_passes_and_gross_errors_fail(self):
        # Found by the C6 dry run: Apple's recorded EDGAR ROE (163.9%) failed
        # the old +/-100% bound and would have blocked every real run.
        from check_checkpoints import _check_percent_ranges
        self.assertEqual(_check_percent_ranges("| AAPL | 163.9% (5y; edgar) |"), [])
        self.assertEqual(_check_percent_ranges("weight 4500%"),
                         ["percentage out of range: 4500%"])


class TestPdfIncludesTheNewSections(unittest.TestCase):
    def test_pdf_builds_with_cards_and_the_anchored_core(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf not installed")
        import build_report
        if not build_report._HAS_REPORTLAB:
            self.skipTest("reportlab not installed")
        from layer3_report import build_layer3_md
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            (work / "layer1_extraction.md").write_text("# Layer 1\n## Input review\nbody\n")
            (work / "layer2_screening.md").write_text("## Consensus structure\nbody\n")
            (work / "layer3_ranked_advice.md").write_text(
                build_layer3_md(_rankings([_stock(1, "AAA")]), None, "Framing prose.", {}))
            pdf = Path(tmp) / "r.pdf"
            build_report.build_pdf(work, pdf)
            text = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
            self.assertIn("Benchmark-anchored core holdings", text)
            self.assertLess(text.index("Benchmark-anchored core holdings"),
                            text.index("Methodology disclosure"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
