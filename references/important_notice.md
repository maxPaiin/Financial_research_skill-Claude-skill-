# Important Notice Reference (v0.33 — Part H)

This file specifies the v0.33 **Important Notice**: a per-stock section covering
two factors the ranking framework structurally cannot measure — the
**expectations bar** and the **sentiment cycle**. It is a reader for Claude and
humans. Stage H1 is performed by Claude in-conversation; the only scripts
involved are `check_checkpoints.py` (deterministic gate) and `build_report.py`
(placement in the PDF).

> **Governing principle: this section sits outside every existing layer.**
> The composite (v0.3) ranks. The coherence overlay (v0.31) may demote a tier.
> **The notice touches neither.** It never enters `Q''`, `C`, `composite`,
> `rankings.json` or `coherence.json`; it changes no score, no rank and no tier.
> Deleting it must leave every ranking, tier and score **bit-for-bit
> unchanged** — the same reversibility property v0.31 holds, stated one layer
> further out.

---

## H0. Why the outermost position is correct, not a compromise

The two factors are genuinely **unquantifiable within this tool**. The backtest
was deliberately removed in v0.2, so there is no mechanism to calibrate "is the
market currently overheated." Manufacturing a number for it would be exactly the
false precision the honest-framing policy exists to prevent — and a value tilt
would systematically demote semiconductor/AI names, precisely the names the HK
distribution channel surfaces most. **A sourced notice is the only truthful form
available.**

### H0.2 Purpose — balance of thinking, not a disclaimer

Three premises govern the tone:

1. The standing disclaimer (front + back of the PDF, plus chat) already carries
   the "not investment advice" position. **This section is not a second
   disclaimer and must not be written as one.**
2. The report exists to give the reader a **balance of thinking** — it is
   reference material, not a conclusion.
3. **Risk awareness is a constitutive part of a correct understanding of
   markets**, not a defensive add-on.

The difference is concrete:

| | |
|---|---|
| **Defensive — do not write** | "This section does not constitute investment advice and is for reference only." |
| **Constructive — write this** | "This section describes a dimension the ranking cannot measure. 'Tier A' means highest-ranked on the measurable dimensions — and precisely for that reason, such a name is more likely to be **already fully priced**. The two readings must be held together." |

The second achieves the same protection *and* helps the reader think. That makes
**Tier A ≠ best time to buy, and the two may be inversely related** the section's
*argument*, not its escape clause.

---

## H1. The two factors, and why the framework cannot see them

**H1.1 The expectations bar.** For some groups — semiconductors / AI
infrastructure being the clearest current case — the market's default assumption
is *already* a beat; merely meeting expectations functions as bad news. The
framework cannot see this because **the quality axis is entirely
backward-looking**: the 5-year-average ROE percentile measures profitability that
has already occurred. A company that has beaten for eight consecutive quarters,
with three years of growth already in the price, and a company with identical ROE
that nobody expects anything from, **receive the same score on Q**. A4's
low-anchor shrinkage reinforces this, since it rewards verifiable historical data
while expectations are by nature unverifiable.

`EV/EBITDA` does not help: it is a **screen gate only** (`quality_screen.py`), it
never enters the score, and it is an absolute threshold rather than a position
relative to the stock's own history — so it cannot detect "this name sits in the
highest decile of its own five-year valuation range."

**H1.2 The sentiment cycle.** Recent performance shapes market sentiment toward
optimism or pessimism. The framework has **no regime-detection capability, by
deliberate design** — see H0. State this as a known measurement boundary.

**H1.3 State these as boundaries, constructively.** Do not write "we cannot do
this." Write: *this is the framework's measurement boundary; the reader needs to
supply this dimension themselves.* Same information, opposite posture.

---

## H2. Evidence sourcing — sector-level evidence, per-stock attribution

**This is the load-bearing rule of Part H.**

### H2.1 Retrieve and corroborate at the sector/theme level; attribute to the stock's group

- Claims such as *"the expectations bar for semiconductors / AI infrastructure
  has been raised"* appear abundantly in Reuters, WSJ, BlackRock commentary and
  Fed characterisations of financial conditions. Meeting the **C2 two-primary-tier
  -source requirement at this level is achievable.**
- Claims such as *"the market's expectations for AVGO specifically are too high"*
  are **effectively impossible** to corroborate with two independent primary-tier
  sources. Single-stock sentiment assertions are the **highest-fabrication-risk
  content in this entire skill** — they read fluently and are trivially invented.

**Rule:** retrieve and corroborate at sector/theme level; narrate by attributing
the stock to its group.

- ✅ "The semiconductor / AI-infrastructure group this stock belongs to is
  currently in an elevated-expectations environment [Source A; Source B]."
- ❌ "The market is over-optimistic on AVGO."

**Choosing the group.** Start from the stock's `industry` bucket in
`rankings.json` (the canonical buckets in `providers/industry_map.py`). Narrow to
a named theme (e.g. "semiconductors / AI infrastructure") **only when the
retrieved evidence is itself at that theme level**. Never narrow to a group that
contains one company — that is a stock-level claim wearing a group's clothes.

### H2.2 The C2 hard gate does not relax here

There will be pressure to loosen the gate for groups where two sources cannot be
found, on the grounds that "it's only a notice." **Do not.** The moment this
section admits single-source claims, it becomes the one low-standard region in
the report — and it is the region most easily fabricated.

**When evidence is insufficient, say so explicitly**, following the v0.31 E3.2
pattern for insufficient data:

> No publicly available evidence meeting the corroboration standard was found for
> this group.

This is an honest output, not a failure — and it carries information: the reader
learns which groups have abundant sentiment evidence and which do not.

### H2.3 Cite references

Every factual statement carries its sources, consistent with the C2 per-sentence
attribution rule already in force for the macro appendices.

**Citation shape (mandated in this file).** Write two or more sources inside one
bracket, semicolon-separated: `[Reuters 2026-08-04; BlackRock Investment
Institute 2026-07]`. Adjacent brackets (`[Source A][Source B]`) are also
accepted. Within `important_notice_checkpoint.md`, **square brackets are reserved
for citations** — the deterministic gate reads them, and a single-source bracket
fails the run. The explicit not-found statement above needs no citation.

### H2.4 Cost is contained — no new retrieval scope

M1's scope is already bound to the **post-screen universe's industries** (v0.31
E0.2), and the top-15's industries are a subset of that. Therefore: **add an
expectations / valuation / sentiment facet to the existing M1 retrieval — do not
add new retrieval scope.** Per-stock retrieval would raise cost by an order of
magnitude and is out of scope.

> **The facet must not leak into the overlay.** Record it in
> `macro_checkpoint.md` only. **Do not add sentiment or expectations fields to
> `macro_factors.json`** — that file feeds `coherence_audit.py`, and anything
> written there can move a display tier. Acceptance criterion 1 (removing the
> notice changes nothing) fails the moment the facet reaches the overlay's input.

---

## H3. The two guardrails

**H3.1 Wording precision must match evidence granularity.** The evidence is
sector-level (H2.1). Writing "this stock is overpriced" **smuggles sector-level
evidence into a stock-level assertion** — the defect is not that it resembles
advice, it is that it **exceeds the granularity of the evidence**. Same principle
as the C2 gate. Describe the *environment*, not the *stock*: "this group is in an
elevated-expectations environment," never "this stock's price is too high."

Verdict vocabulary — *overvalued, undervalued, overpriced, underpriced,
overbought, oversold, overhyped, overly optimistic, priced for perfection, too
expensive, too cheap, is a buy/sell* — is **banned outright in this section**,
at any granularity. It states a price verdict; the sanctioned register describes
an environment. The gate enforces this mechanically.

**H3.2 State that this section and the ranking are two independent dimensions —
constructively.** The purpose is **not** to disclaim, but to tell the reader
these are separate axes: the ranking answers *"which stocks score highest on the
measurable dimensions"*; this notice answers *"what those measurements do not
capture."* Held together, the reader gets a balanced picture.

Fold the H1 boundary statements in here, in the constructive register of H1.3.
This matters especially because **adding evidence makes it easy for a reader to
conclude the tool can now judge overheating — it still cannot**, and that must be
unambiguous.

---

## H4. Section structure and placement

**H4.1 Placement.** A standalone section **after the existing appendices (1+2, 3)
and before the methodology section**. Although its content is per-stock, its
nature is *how to read the preceding results*, not analysis output — so it
follows the analysis and precedes the methodology. `build_report.py` places it;
the PDF section order is in that file's docstring.

**H4.2 Title.** Neutral wording:

```
## Important Notice — Expectations Environment and Sentiment Cycle
```

Avoid "risk warning" phrasing: this is not a warning that a particular stock is
risky, it is a statement of the framework's measurement boundary.

**H4.3 Per-stock entry shape.** For each of the 15 ranked stocks, an `### `
heading naming the ticker and its group, then:

1. The stock and the sector/theme group it is attributed to.
2. **Expectations bar** for that group — sourced, or the explicit not-found
   statement (H2.2).
3. **Sentiment cycle** for that group — sourced, or the explicit not-found
   statement.
4. References.

Every `### ` block must contain **either** a citation **or** the not-found
statement. A block with neither is an unsourced assertion, and the gate fails it.

**H4.4 Section-level framing — written once, not per stock** (consistent with
v0.3 D3, which states the HK-bias once rather than on every card). The H1
measurement boundaries, the H3.2 two-dimensions statement, and the closing
argument all appear **once at the section head**, above the first `### ` entry.
Do not use `### ` headings in the head. The closing argument must contain the
phrase **`already fully priced`**, and that phrase must appear **exactly once in
the whole section** — that is how "once, not per stock" is checked mechanically.

**H4.5 Checkpoint.** Write `important_notice_checkpoint.md` in the work dir. It
is copied to `/mnt/user-data/outputs` with the other checkpoints (v0.3 D5) and is
subject to the same deterministic review (v0.3 D4).

---

## What `check_checkpoints.py` enforces on this file

Optional by default — like the other appendix checkpoints, it is only checked
when present, and `--require-important-notice` promotes it. Removability is a
hard property (H0), so the gate must not require the section to exist.

| Check | Rule | Spec |
|---|---|---|
| Required markers | `## Important Notice`, `Expectations bar`, `Sentiment cycle` | H4.2, H4.3 |
| Regime boundary | the word `regime` must appear (the "still no regime-detection capability" statement) | H1.2, H3.2 |
| Closing argument, once | `already fully priced` appears **exactly once** | H4.4 |
| Attribution | at least one bracketed citation, unless the whole section is not-found | H2.3 |
| Two sources | every bracket names ≥2 sources (`;`-separated, or adjacent brackets) | H2.2 |
| Per-entry sourcing | every `### ` block has a citation **or** the not-found statement | H4.3 |
| Constructive register | no "for reference only" / "does not constitute investment advice" / "consult a financial adviser" | H0.2, acceptance 5 |
| Neutral register | no "risk warning" anywhere in the section | H4.2, acceptance 8 |
| Granularity | no verdict vocabulary anywhere; no `sentiment/expectations/optimism toward <TICKER>` and no `<TICKER>'s valuation/sentiment/expectations` for any ranked ticker | H3.1, acceptance 2 |
| Percent sanity | shared with every other checkpoint | D4 |

The gate reads the ranked tickers from `rankings.json` in the same work dir; if
that file is absent the ticker-bound half is skipped and the rest still runs.

**What it cannot check, and Claude must:** whether two named sources are
genuinely independent, whether a group-level sentence is really supported by the
cited material, and whether the register actually reads as constructive rather
than merely avoiding the banned strings.

---

## What this section does NOT change

- `rankings.json`, `coherence.json`, composite weights, `Q''`, `C`, rank order,
  tiers — all untouched.
- The v0.31 overlay — the notice is **not** a fourth coherence input and never
  triggers a demotion.
- The screen, the thresholds, the input gates — untouched.
- Retrieval scope — the existing M1 sector scope is reused; only the facet
  retrieved expands (H2.4).
- The existing disclaimer — unchanged, still front + back of the PDF. This
  section is **not** a second disclaimer (H0.2).
