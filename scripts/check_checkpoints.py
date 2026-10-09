"""
D4: Deterministic checkpoint review gate.

The skill checkpoints each stage to a `.md` file (context-loss protection). This
script is the *deterministic* half of the review gate: it verifies that each
checkpoint present has the sections the pipeline requires and a few cheap
range/sanity checks. It does NOT judge rationale quality or enforce the C2
source-corroboration gate — those require LLM judgment and are handled by Claude
in-conversation. Keeping the mechanical checks here makes a long run auditable
and lets a resumed run confirm its predecessors before proceeding.

Usage:
  check_checkpoints.py <work_dir> [--require-macro] [--require-expectations]
                                  [--require-appendix3] [--require-coherence]
                                  [--require-important-notice]

Exit code 0 if every present (and every required) checkpoint passes; 1 otherwise.

v0.31: when `coherence.json` is present it is checked against the overlay's
hard invariants (demotion-only, one-tier cap, tier == base_tier + delta; v0.4:
every demotion names a contradiction or a risk, and every contradiction or risk
demotes). It is
deliberately NOT required by default — the overlay must remain removable
without breaking the gate (reversibility test, E1).

v0.33: `important_notice_checkpoint.md` gets the strictest content checks in this
script — a two-source-per-citation rule, a per-entry sourcing rule, a ban on
valuation/sentiment verdict vocabulary and a ban on ticker-bound sentiment
claims. Rationale (Part H): sector-level evidence narrated per stock is the
highest-fabrication-risk content in the skill, so the mechanical half of the
review is pushed as far as it will go. Like the other appendices it is optional
by default — the notice must stay removable (H0). Full spec:
`references/important_notice.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import source_whitelist as sw  # noqa: E402  (v0.41)

# filename -> (required_substrings, optional)
# `optional=True` files are only checked when present (the macro subsystem may
# not have run); a required-but-absent optional file is promoted via CLI flags.
_REQUIRED_SECTIONS: dict[str, list[str]] = {
    # v0.32 G4: the consolidated input-review block is required, not optional —
    # scattering the currency / thin-exposure / advisory findings back across
    # sections is the failure mode the block exists to prevent.
    "layer1_extraction.md": ["# Layer 1", "## Input review", "## Per-fund extraction"],
    "layer2_screening.md": [
        "## Quality screen results",
        # v0.4 B8: how many independent opinions the run holds, and what voted.
        "## Consensus structure",
        "## Exit liquidity",
        # v0.32 G1.4: the currency-exclusion statement must accompany the
        # liquidity figures; a missing figure alone does not explain itself.
        "## Reporting currency and the exit-liquidity aggregate",
    ],
    "layer3_ranked_advice.md": [
        "## Methodology disclosure",
        "Consensus band",
        "Confidence-shrinkage",
        "Exit liquidity",
    ],
    "macro_checkpoint.md": [],            # presence + attribution checked below
    "expectations_checkpoint.md": ["Best", "Average", "Worst"],
    "appendix3_consensus_warning.md": [], # presence + remediation checked below
    # v0.33 H4.2/H4.3: the title, and the two facets every per-stock entry
    # carries. Everything else about this file is checked by _check_notice().
    "important_notice_checkpoint.md": [
        "## Important Notice",
        "Expectations bar",
        "Sentiment cycle",
    ],
}

_ALWAYS = {"layer1_extraction.md", "layer2_screening.md", "layer3_ranked_advice.md"}

# Per-sentence attribution looks like "... [Fed; Reuters]". The macro/expectations
# appendices must carry at least one bracketed citation (C2 per-sentence sources).
_CITATION_RE = re.compile(r"\[[^\]\n]+\]")
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


# A sanity bound, not a statistic. ROE can legitimately exceed 100% — a company
# that buys back most of its equity (Apple's ROE is about 160%) — so the bound
# sits at +/-1000%: wide enough for real ratios, narrow enough to catch a gross
# formatting error such as a weight printed in basis points (4500%).
_PERCENT_BOUND = 1000.0


def _check_percent_ranges(text: str) -> list[str]:
    """Cheap range sanity: percentage figures should sit in [-1000, 1000]%.

    Catches gross extraction/formatting errors (e.g. a stray 4500%). This is a
    sanity floor, not a statistical check.
    """
    problems = []
    for m in _PERCENT_RE.finditer(text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if v < -_PERCENT_BOUND or v > _PERCENT_BOUND:
            problems.append(f"percentage out of range: {m.group(0)}")
    return problems


# --- v0.33 Part H: Important Notice checks ----------------------------------

_NOTICE = "important_notice_checkpoint.md"

# H2.2: the sanctioned way to say "no evidence" — an explicit statement, never a
# single-source claim and never a fabricated summary.
_NOTICE_NOT_FOUND_RE = re.compile(
    r"\bno\b[^.\n]{0,60}\bevidence\b[^.\n]{0,80}\bcorroborat", re.I)

# H0.2 / acceptance 5: the standing disclaimer already carries this. A second
# one inside the notice turns a thinking aid back into boilerplate.
_NOTICE_DEFENSIVE = [
    "for reference only",
    "for informational purposes only",
    "for information purposes only",
    "does not constitute investment advice",
    "not investment advice",
    "no liability",
    "consult a financial adviser",
    "consult a financial advisor",
    "consult a professional adviser",
]

# H3.1: price verdicts, banned at any granularity. The sanctioned register
# describes an *environment* ("elevated-expectations environment"), not a price.
_NOTICE_VERDICT_RE = re.compile(
    r"\b(?:over-?valued|under-?valued|over-?priced|under-?priced|over-?bought"
    r"|over-?sold|over-?hyped|over-?optimistic|over-?pessimistic"
    r"|overly\s+optimistic|overly\s+pessimistic|priced\s+for\s+perfection"
    r"|too\s+expensive|too\s+cheap|is\s+a\s+(?:strong\s+)?(?:buy|sell))\b", re.I)

# H4.4: the closing argument is written once at the section head, not repeated
# per stock (the same discipline v0.3 D3 applies to the HK-bias note).
_NOTICE_CLOSING_MARKER = "already fully priced"

_NOTICE_ENTRY_SPLIT_RE = re.compile(r"^###\s+", re.M)


def _notice_ticker_patterns(ticker: str) -> list[str]:
    """H3.1 / acceptance 2: forms that bind a sentiment or expectations claim to
    a single ranked stock. The evidence is sector-level, so a stock-level
    subject exceeds the granularity of what was actually retrieved.
    """
    t = re.escape(ticker)
    return [
        rf"\b(?:sentiment|expectations|optimism|pessimism|enthusiasm|"
        rf"positioning)\s+(?:toward|towards|for|on|about|around)\s+{t}\b",
        rf"\b{t}(?:'s|’s)\s+(?:valuation|sentiment|expectations|multiple|"
        rf"price|expectation)\b",
        rf"\bthe\s+market(?:\s+\w+){{0,3}}\s+(?:on|about)\s+{t}\b",
    ]


def _check_notice_citations(text: str) -> list[str]:
    """H2.2/H2.3: inside this file square brackets are reserved for citations,
    and every citation must name >= 2 sources — either semicolon-separated
    inside one bracket, or two adjacent brackets. The C2 gate is never relaxed
    for this section; it is the region most easily fabricated.
    """
    problems: list[str] = []
    matches = list(_CITATION_RE.finditer(text))
    for m in matches:
        inner = m.group(0)[1:-1]
        if ";" in inner:
            continue
        before = text[:m.start()].rstrip()
        after = text[m.end():].lstrip()
        if before.endswith("]") or after.startswith("["):
            continue  # adjacent-bracket form
        problems.append(
            f"single-source citation {m.group(0)} — every claim needs >= 2 "
            "primary-tier sources (C2 is not relaxed here, H2.2); write "
            "[Source A; Source B], or state that no corroborating evidence "
            "was found"
        )
    return problems


def _check_notice(text: str, tickers: list[str]) -> list[str]:
    """Content rules for the v0.33 Important Notice (Part H).

    Deliberately the strictest block in this script: the notice narrates
    sector-level evidence per stock, which reads fluently and is trivially
    invented. Everything here is mechanical; the judgment calls (are two named
    sources genuinely independent, does the cited material actually support the
    sentence) stay with Claude.
    """
    problems: list[str] = []
    has_not_found = bool(_NOTICE_NOT_FOUND_RE.search(text))
    citations = _CITATION_RE.findall(text)

    # H1.2 / acceptance 6: presenting evidence must not read as new capability.
    if "regime" not in text.lower():
        problems.append(
            "no regime-detection statement found — the section must say plainly "
            "that the tool still has no regime-detection capability (H1.2)"
        )

    # H4.4: once at the section head, not per stock.
    n_closing = text.count(_NOTICE_CLOSING_MARKER)
    if n_closing == 0:
        problems.append(
            f"closing argument missing — the section head must carry the "
            f"'{_NOTICE_CLOSING_MARKER}' argument (Tier A means highest-ranked "
            "on the measurable dimensions, and for that reason more likely "
            "already priced) (H4.4)"
        )
    elif n_closing > 1:
        problems.append(
            f"closing argument appears {n_closing} times — it belongs once at "
            "the section head, not on every stock (H4.4)"
        )

    # C2 attribution, and the sanctioned alternative when evidence is thin.
    if not citations and not has_not_found:
        problems.append(
            "no bracketed source attribution and no explicit not-found "
            "statement — every claim carries its sources, or the entry says no "
            "corroborating evidence was found (H2.2/H2.3)"
        )
    problems += _check_notice_citations(text)

    # H4.3: per-entry sourcing. A block with neither is an unsourced assertion.
    parts = _NOTICE_ENTRY_SPLIT_RE.split(text)
    for block in parts[1:]:
        heading = block.splitlines()[0].strip() if block.strip() else "?"
        if not _CITATION_RE.search(block) and not _NOTICE_NOT_FOUND_RE.search(block):
            problems.append(
                f"entry '{heading}' has neither a citation nor an explicit "
                "not-found statement (H4.3)"
            )

    # H4.2 / acceptance 8: this is not a warning that a particular stock is
    # risky, it is a statement of the framework's measurement boundary — so the
    # "risk warning" register is wrong for the same reason the defensive one is.
    if "risk warning" in text.lower():
        problems.append(
            "'risk warning' phrasing — the section states a measurement "
            "boundary, not that a stock is risky; keep the neutral title (H4.2)"
        )

    # H0.2 / acceptance 5: constructive register, not a second disclaimer.
    low = text.lower()
    for phrase in _NOTICE_DEFENSIVE:
        if phrase in low:
            problems.append(
                f"defensive phrasing '{phrase}' — the standing disclaimer "
                "already carries this; write the boundary constructively "
                "instead (H0.2)"
            )

    # H3.1: price verdicts at any granularity.
    seen: set[str] = set()
    for m in _NOTICE_VERDICT_RE.finditer(text):
        term = m.group(0).lower()
        if term in seen:
            continue
        seen.add(term)
        problems.append(
            f"valuation/sentiment verdict '{m.group(0)}' — describe the "
            "environment the group is in, not a price verdict (H3.1)"
        )

    # H3.1 / acceptance 2: sentiment or expectations bound to a single ticker.
    for ticker in tickers:
        for pat in _notice_ticker_patterns(ticker):
            m = re.search(pat, text, re.I)
            if m:
                problems.append(
                    f"stock-level claim '{m.group(0).strip()}' — the evidence "
                    f"is sector-level, so attribute {ticker} to its group and "
                    "describe the group (H2.1/H3.1)"
                )
                break

    return problems


def _ranked_tickers(work_dir: Path) -> list[str]:
    """Tickers of the ranked stocks, for the ticker-bound notice checks.

    Absent rankings.json is not an error here — the notice is checked on its own
    terms and only the ticker-bound half is skipped.
    """
    path = work_dir / "rankings.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("ranked") or []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if isinstance(r, dict):
            tkr = r.get("ticker")
            if isinstance(tkr, str) and tkr.strip():
                out.append(tkr.strip())
    return out


def check_file(path: Path, required: list[str],
               tickers: list[str] | None = None) -> list[str]:
    problems: list[str] = []
    if not path.exists():
        return [f"missing file: {path.name}"]
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return [f"empty file: {path.name}"]

    for needle in required:
        if needle not in text:
            problems.append(f"{path.name}: missing required section/marker '{needle}'")

    # D3 regression: ranked cards must NOT repeat the per-card bias note.
    if path.name == "layer3_ranked_advice.md" and "Bias note:" in text:
        problems.append(
            "layer3_ranked_advice.md: per-card 'Bias note:' present — v0.3 states "
            "the HK-bias once in the framing section, not on every card (D3)."
        )

    # C2: macro/expectations facts carry per-sentence source attribution.
    if path.name in ("macro_checkpoint.md", "expectations_checkpoint.md"):
        if not _CITATION_RE.search(text):
            problems.append(
                f"{path.name}: no bracketed source attribution found — every "
                "factual sentence in the appendices must cite its source(s) (C2)."
            )

    # v0.33 Part H: the Important Notice's own content rules.
    if path.name == _NOTICE:
        problems += [f"{path.name}: {p}" for p in _check_notice(text, tickers or [])]

    # C4: Appendix 3 should say how to diversify the input (remediation). v0.4
    # B8: "replace the lowest-contribution fund with a dissimilar one" counts.
    if path.name == "appendix3_consensus_warning.md":
        if not re.search(r"\b(add|replace|lowest-contribution|dissimilar|value|income|"
                         r"dividend|small.?mid|non-?US)\b", text, re.I):
            problems.append(
                "appendix3_consensus_warning.md: no remediation language found "
                "(expected guidance on which fund to add or replace) (C4)."
            )

    problems += [f"{path.name}: {p}" for p in _check_percent_ranges(text)]
    return problems


# --- v0.41: the source whitelist ----------------------------------------------
# A citation may name only an institution in references/source_whitelist.json,
# and every cited institution must have at least one fetched page, on one of its
# whitelisted domains, recorded in <work>/sources_log.json (Retrieval protocol,
# references/macro_appendix.md). Brackets are reserved for citations in these files.
_CITED_MD = ("macro_checkpoint.md", "expectations_checkpoint.md", _NOTICE)
_SOURCES_LOG = "sources_log.json"


def _json_source_lists(work_dir: Path) -> tuple[dict[str, list[str]], list[str]]:
    """({file: [cited source names]}, problems) for macro_factors.json and sector_logic.json."""
    lists: dict[str, list[str]] = {}
    problems: list[str] = []
    for name in ("macro_factors.json", "sector_logic.json"):
        path = work_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            problems.append(f"{name}: not valid JSON ({e})")
            continue
        items: list[str] = []
        if name == "macro_factors.json":
            sources = data.get("sources") if isinstance(data, dict) else None
            for value in (sources.values() if isinstance(sources, dict) else []):
                items += value if isinstance(value, list) else [value]
        else:
            industries = data.get("industries") if isinstance(data, dict) else None
            for entry in (industries.values() if isinstance(industries, dict) else []):
                value = entry.get("sources") if isinstance(entry, dict) else None
                items += value if isinstance(value, list) else ([value] if value else [])
        lists[name] = [str(i).strip() for i in items if str(i).strip()]
    return lists, problems


def check_sources(work_dir: Path) -> dict[str, list[str]]:
    """{file: problems} for the v0.41 whitelist and sources-log rules; {} when
    nothing is cited and no log exists (the macro stages stay removable)."""
    found: list[tuple[str, str, str]] = []           # (file, item, where)
    for name in _CITED_MD:
        path = work_dir / name
        if not path.exists():
            continue
        for m in _CITATION_RE.finditer(path.read_text(encoding="utf-8")):
            found += [(name, item, m.group(0)) for item in sw.citation_items(m.group(0))]
    lists, problems_json = _json_source_lists(work_dir)
    for name, items in lists.items():
        found += [(name, item, "its 'sources'") for item in items]

    log_path = work_dir / _SOURCES_LOG
    out: dict[str, list[str]] = {}
    for p in problems_json:
        out.setdefault(p.split(":", 1)[0], []).append(p)
    if not found and not log_path.exists():
        return out

    try:
        whitelist = sw.load()
    except sw.WhitelistError as e:
        out.setdefault("source_whitelist.json", []).append(f"{e} — the gate fails closed")
        return out

    cited: dict[str, set[str]] = {}
    refused_internal = sw.internal_refused_in()
    seen: dict[tuple[str, str], int] = {}             # (file, problem item) -> count
    first_where: dict[tuple[str, str], tuple[str, str]] = {}
    for name, item, where in found:
        iid = sw.institution_for_citation(item)
        if iid is not None:
            cited.setdefault(iid, set()).add(name)
            continue
        if sw.is_internal_citation(item) and name not in refused_internal:
            continue                                  # the run's own data (Layer 2, EDGAR)
        kind = "internal" if sw.is_internal_citation(item) else "unlisted"
        key = (name, item)
        seen[key] = seen.get(key, 0) + 1
        first_where.setdefault(key, (where, kind))
    for (name, item), n in seen.items():
        where, kind = first_where[(name, item)]
        times = f" ({n} times)" if n > 1 else ""
        if kind == "internal":
            msg = (f"{name}: '{item}' in {where}{times} is the run's own data — it cannot be a "
                   "source here; cite two whitelisted institutions or use the not-found statement")
        else:
            msg = (f"{name}: '{item}' in {where}{times} is not a whitelisted source "
                   "(references/source_whitelist.json) — cite a whitelisted institution, "
                   "or leave the fact out (C2)")
        out.setdefault(name, []).append(msg)

    if not log_path.exists():
        out.setdefault(_SOURCES_LOG, []).append(
            f"{_SOURCES_LOG}: missing — record every page fetched in M1, M1b, M2 and H1 "
            "(macro_appendix.md, Retrieval protocol R6)")
        return out
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        out.setdefault(_SOURCES_LOG, []).append(f"{_SOURCES_LOG}: not valid JSON ({e})")
        return out
    entries = log.get("fetched") if isinstance(log, dict) else None
    if not isinstance(entries, list):
        out.setdefault(_SOURCES_LOG, []).append(f"{_SOURCES_LOG}: no 'fetched' list")
        return out

    fetched: set[str] = set()
    for entry in entries:
        url = entry.get("url") if isinstance(entry, dict) else None
        iid = sw.institution_for_url(url or "")
        if iid is None:
            out.setdefault(_SOURCES_LOG, []).append(
                f"{_SOURCES_LOG}: {url!r} is not on a whitelisted domain — fetch only "
                "search results on references/source_whitelist.json domains (R3)")
        else:
            fetched.add(iid)
    for iid in sorted(cited):
        if iid not in fetched:
            out.setdefault(_SOURCES_LOG, []).append(
                f"{_SOURCES_LOG}: {', '.join(sorted(cited[iid]))} cite "
                f"{whitelist[iid]['name']}, but no fetched page of it is recorded (R6)")
    return out


_TIER_ORDER = ["A", "B", "C"]


def check_coherence(path: Path) -> list[str]:
    """v0.31: verify the overlay's invariants on the coherence.json side-car.

    The overlay is only non-destructive if it can never promote and never drop
    more than one tier — so those are checked mechanically rather than trusted.
    """
    if not path.exists():
        return [f"missing file: {path.name}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"{path.name}: not valid JSON ({e})"]

    problems: list[str] = []
    records = data.get("records")
    if not isinstance(records, list):
        return [f"{path.name}: no 'records' list"]

    for r in records:
        tkr = r.get("ticker", "?")
        base, tier = r.get("base_tier"), r.get("tier")
        delta = r.get("tier_delta")
        if base not in _TIER_ORDER or tier not in _TIER_ORDER:
            problems.append(f"{path.name}: {tkr} has an unknown tier ({base} -> {tier})")
            continue
        if delta not in (0, -1):
            problems.append(
                f"{path.name}: {tkr} tier_delta={delta} — the overlay is "
                "demotion-only and capped at one tier (E3.2)."
            )
        expected = _TIER_ORDER[min(len(_TIER_ORDER) - 1,
                                   _TIER_ORDER.index(base) - min(0, int(delta or 0)))]
        if tier != expected:
            problems.append(
                f"{path.name}: {tkr} tier {tier} does not follow from "
                f"base_tier {base} with delta {delta} (expected {expected})."
            )
        if _TIER_ORDER.index(tier) < _TIER_ORDER.index(base):
            problems.append(
                f"{path.name}: {tkr} was PROMOTED {base} -> {tier} — the overlay "
                "may never promote (E0.1)."
            )
        if r.get("tier_delta") == -1 and not (r.get("contradictions") or r.get("risks")):
            problems.append(
                f"{path.name}: {tkr} was demoted without a named contradiction or "
                "risk (E3.2 / B7 require it to be stated)."
            )
        # B7/B8: the converse — a contradiction or a risk verdict always demotes
        # (C stays C, but the delta is still recorded).
        fired = [v.get("pair") for v in r.get("verdicts") or []
                 if v.get("verdict") in ("contradiction", "risk")]
        if fired and r.get("tier_delta") != -1:
            problems.append(
                f"{path.name}: {tkr} has a contradiction or risk ({', '.join(map(str, fired))}) "
                "but no demotion (E3.2 / B7)."
            )
    return problems


def review(work_dir: Path, required_optional: set[str]) -> dict:
    results: dict[str, list[str]] = {}
    tickers = _ranked_tickers(work_dir)
    for name, sections in _REQUIRED_SECTIONS.items():
        path = work_dir / name
        is_required = name in _ALWAYS or name in required_optional
        if not path.exists() and not is_required:
            continue  # optional checkpoint that simply was not produced
        results[name] = check_file(path, sections, tickers)

    coherence_path = work_dir / "coherence.json"
    if coherence_path.exists() or "coherence.json" in required_optional:
        results["coherence.json"] = check_coherence(coherence_path)

    # v0.41: cited sources must be whitelisted and fetched.
    for name, probs in check_sources(work_dir).items():
        results[name] = results.get(name, []) + probs

    all_problems = [p for probs in results.values() for p in probs]
    return {
        "ok": len(all_problems) == 0,
        "checked": list(results.keys()),
        "problems": all_problems,
        "by_file": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--require-macro", action="store_true")
    ap.add_argument("--require-expectations", action="store_true")
    ap.add_argument("--require-appendix3", action="store_true")
    ap.add_argument("--require-coherence", action="store_true",
                    help="v0.31: fail if coherence.json is absent. Off by default so "
                         "the overlay stays removable (reversibility test).")
    ap.add_argument("--require-important-notice", action="store_true",
                    help="v0.33: fail if important_notice_checkpoint.md is absent. Off "
                         "by default so the notice stays removable (H0).")
    args = ap.parse_args()

    required_optional = set()
    if args.require_macro:
        required_optional.add("macro_checkpoint.md")
    if args.require_expectations:
        required_optional.add("expectations_checkpoint.md")
    if args.require_appendix3:
        required_optional.add("appendix3_consensus_warning.md")
    if args.require_coherence:
        required_optional.add("coherence.json")
    if args.require_important_notice:
        required_optional.add(_NOTICE)

    result = review(Path(args.work_dir), required_optional)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
