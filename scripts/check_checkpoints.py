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

Exit code 0 if every present (and every required) checkpoint passes; 1 otherwise.

v0.31: when `coherence.json` is present it is checked against the overlay's
hard invariants (demotion-only, one-tier cap, tier == base_tier + delta). It is
deliberately NOT required by default — the overlay must remain removable
without breaking the gate (reversibility test, E1).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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
        "## Input-set style homogeneity",
        # v0.32 G1.4: the currency-exclusion statement must accompany the
        # crowding labels; a NAV-only label alone does not explain itself.
        "## Reporting currency and the exit-liquidity aggregate",
    ],
    "layer3_ranked_advice.md": [
        "## Methodology disclosure",
        "Confidence-shrinkage",
        "exit-crowdedness",
    ],
    "macro_checkpoint.md": [],            # presence + attribution checked below
    "expectations_checkpoint.md": ["Best", "Average", "Worst"],
    "appendix3_consensus_warning.md": [], # presence + remediation checked below
}

_ALWAYS = {"layer1_extraction.md", "layer2_screening.md", "layer3_ranked_advice.md"}

# Per-sentence attribution looks like "... [Fed; Reuters]". The macro/expectations
# appendices must carry at least one bracketed citation (C2 per-sentence sources).
_CITATION_RE = re.compile(r"\[[^\]\n]+\]")
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _check_percent_ranges(text: str) -> list[str]:
    """Cheap range sanity: percentage figures should sit in [-100, 100]%.

    Catches gross extraction/formatting errors (e.g. a stray 4500%). This is a
    sanity floor, not a statistical check.
    """
    problems = []
    for m in _PERCENT_RE.finditer(text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if v < -100.0 or v > 100.0:
            problems.append(f"percentage out of range: {m.group(0)}")
    return problems


def check_file(path: Path, required: list[str]) -> list[str]:
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

    # C4: Appendix 3 should name fund styles to add (remediation).
    if path.name == "appendix3_consensus_warning.md":
        if not re.search(r"\b(add|value|income|dividend|small.?mid|non-?US)\b", text, re.I):
            problems.append(
                "appendix3_consensus_warning.md: no style-remediation language found "
                "(expected guidance on which fund styles to add) (C4)."
            )

    problems += [f"{path.name}: {p}" for p in _check_percent_ranges(text)]
    return problems


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
        if r.get("tier_delta") == -1 and not r.get("contradictions"):
            problems.append(
                f"{path.name}: {tkr} was demoted without a named contradiction "
                "(E3.2 requires the contradiction to be stated)."
            )
    return problems


def review(work_dir: Path, required_optional: set[str]) -> dict:
    results: dict[str, list[str]] = {}
    for name, sections in _REQUIRED_SECTIONS.items():
        path = work_dir / name
        is_required = name in _ALWAYS or name in required_optional
        if not path.exists() and not is_required:
            continue  # optional checkpoint that simply was not produced
        results[name] = check_file(path, sections)

    coherence_path = work_dir / "coherence.json"
    if coherence_path.exists() or "coherence.json" in required_optional:
        results["coherence.json"] = check_coherence(coherence_path)

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

    result = review(Path(args.work_dir), required_optional)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
