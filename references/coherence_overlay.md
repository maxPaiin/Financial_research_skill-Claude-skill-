# Coherence Overlay Reference (v0.31)

This file specifies the v0.31 coherence overlay — Stage 3a-bis plus the two
amendments it makes to v0.3. It is a reader for Claude and humans. The
deterministic half lives in `scripts/coherence_audit.py` and
`scripts/etf_relative_strength.py`; the qualitative inputs are written by Claude.

> **Governing principle: the overlay may only demote.** If it could promote,
> switching it off would change the report's ordering — meaning it was never a
> bolt-on, it was a rewrite. Because it can only demote, disabling it returns
> the report to exactly the v0.3 output. Reversibility is a hard property here,
> not an aspiration.

---

## Why an overlay rather than a third scoring axis

`0.4·Q + 0.4·C + 0.2·Macro` was considered and rejected:

1. **The weight cannot be calibrated.** The backtest was deliberately removed in
   v0.2, so there is no mechanism to validate "15% vs 25%". Writing a number
   down would be exactly the false precision the honest-framing policy exists to
   prevent.
2. **It would break the locked 50/50 split.**

What the overlay *is* instead: v0.3 §0 premise 2 ("uncertainty is a quality
defect") extended to a new axis. If the macro picture, the sector logic and the
price action contradict each other, that stock's picture is **incoherent**;
incoherence is uncertainty; uncertainty is treated as a defect. The overlay is
the existing premise applied to a new dimension, not a new rule.

---

## The two amendments to v0.3

### 1. M1 moves from after-3a to after-2d, re-anchored to the post-screen universe

v0.3 scoped the macro/sector analysis to *"the industries present in the
top-15."* If macro is to inform tiering, it must exist before/alongside ranking
— but the top-15 is **produced by** ranking, so the old anchor is circular the
moment macro moves upstream.

The screened universe exists prior to ranking, is bounded (typically a few dozen
names across a limited set of industries), and so preserves the cost-control
intent of the original scoping rule. `quality_screen.py` emits
`passed_industries` for exactly this purpose.

**This is a pure sequencing move.** M1's internal logic, its sources, the
directed-fetch policy and the C2 corroboration hard gate are **unchanged**. M2
(per-stock scenarios) stays after ranking, since it is scoped to the final 15.

### 2. Tiers stop being a display slice

v0.3 assigned tiers as pure rank slices (A = 1–5, B = 6–10, C = 11–15), carrying
no information beyond position. v0.31 keeps the rank slice as the **starting
point** and then adjusts it **downward only**.

**Rank order itself never changes.** A stock ranked #3 whose macro and sector
logic contradict each other stays at **rank #3** and is shown in **Tier B**,
with the contradiction named on its card. Rank remains a purely quantitative,
fully traceable product of the composite; tier carries the qualitative judgment.
A reader can see *"ranked #3 by the composite, demoted to B because X
contradicts Y"* — far more auditable than folding macro into the score, where it
could never be separated out again.

---

## Stage 3a-bis — the audit

- **Position:** after 3a (`build_rankings.py`), before 3b (rationale cards).
- **Inputs (read-only):** `rankings.json`, `macro_factors.json`,
  `sector_logic.json`, `etf_relative_strength.json`.
- **Output:** the side-car `coherence.json` — one record per ranked stock.
- **Hard constraint:** `rankings.json` is **not modified**. Composite scores,
  `Q''`, `C` and rank order are written by 3a and never rewritten.
- **Reversibility test (must hold):** deleting 3a-bis and `coherence.json`
  leaves the pipeline runnable and produces the v0.3 report minus the coherence
  annotations. If removing the overlay breaks anything downstream or changes
  ranks, the implementation is wrong.

---

## The three inputs

### E2.1 Macro factors — structure what M1 already fetched

M1 already retrieves FOMC statements/minutes, the SEP (incl. the dot plot), the
Beige Book, plus ECB and BoJ material. The inflation trajectory and the
policy-rate path are already in that corpus. **No new sources are fetched for
this factor** — it is the cheapest of the three, which is why it is in scope.

Claude writes `macro_factors.json` alongside `macro_checkpoint.md`:

```json
{
  "asof": "2026-08-01",
  "policy_rate_direction": "tightening | on_hold | easing",
  "inflation_trend": "rising | stable | falling",
  "sources": {
    "policy_rate_direction": ["Fed FOMC statement 2026-07-29", "Reuters"],
    "inflation_trend": ["BLS CPI release 2026-07-14", "Fed SEP 2026-06"]
  },
  "notes": "free-text; not parsed"
}
```

The **C2 corroboration hard gate applies unchanged** to any factual macro
statement carried into the report. `coherence_audit.py` collapses the two fields
into one stance: on-hold policy with rising inflation reads as **tightening**,
because the real-rate path is the transmission channel, not the headline
decision.

### E2.2 Sector logic — three universal questions

The original *upstream resources / trade spread / investment return* triad is a
**physical supply-chain** framework. It fits semiconductors, energy, materials
and industrial manufacturing; it does **not** fit the rest of a screened
universe. A software company has no meaningful "upstream resource", a bank's
"trade spread" is ambiguous, and forcing the triad onto them produces confident
nonsense. The abstraction below preserves the analytical angle while staying
well-defined across every sector the screen can produce:

1. **Input side — what constrains the inputs?**
   (physical: raw materials / wafer supply / energy · software: compute & talent
   cost · financial: cost of funds)
2. **Output side — how much pricing power is there?**
   (physical: spread between input cost and selling price · software:
   pricing/retention power · financial: net interest margin)
3. **Capital — what is the return on capital deployed?**
   (capex return · R&D return · credit cost)

Instantiate using the existing `industry` buckets and the fundamentals already
gathered in Layer 2. **Do not introduce new company-level data requirements.**

Claude writes `sector_logic.json`, one entry per industry in the post-screen
universe:

```json
{
  "industries": {
    "technology": {
      "input_constraint":   {"text": "...", "direction": "easing | neutral | tightening"},
      "pricing_power":      {"text": "...", "direction": "expanding | neutral | compressing"},
      "return_on_capital":  {"text": "...", "direction": "improving | neutral | deteriorating"},
      "capital_sensitivity": "high | medium | low",
      "sources": ["..."]
    }
  }
}
```

Net logic direction = sum of the three directions (+1 / 0 / −1 each):
**≥ +2 → expansionary**, **≤ −2 → contractionary**, otherwise **neutral**.
Fewer than two answered questions → **insufficient data** (never a verdict).

### E2.3 ETF check — divergence detection, not confirmation

"Does the price reflect it?" has two opposite readings, and the tool cannot hold
both: **(A) confirmation** — price moved with the thesis, so the thesis is
validated; **(B) already priced in** — everyone knows it, so no residual value
remains.

**Reading A is rejected.** Consensus is already pro-cyclical by construction
(v0.3 §0 premise 3), and momentum-style price confirmation is *also*
pro-cyclical. Stacking them means that in a 2022-style de-rating both signals
point the wrong way together — undoing the entire A2/A3 rebuild of `C`. That
would be destructive, not additive.

**Adopted instead — the ETF as a divergence detector**, answering:

1. Does the stock diverge sharply from its **sector ETF**?
2. Is the sector ETF's **relative strength vs SPY** consistent with the
   central-bank-derived macro narrative?
3. If these disagree → flag, demote, and **name the contradiction**.

Measurement rules (canonical constants in `etf_relative_strength.py`):

- **Relative strength versus SPY**, never absolute return — absolute return
  mostly measures beta.
- **Fixed 3M / 6M / 12M windows** (63 / 126 / 252 trading days). Fixed windows
  prevent post-hoc window-picking. Verdicts use the mean across available
  windows so one strong quarter cannot decide alone.
- Bands: `RS_BAND = 0.05` (sector inline/outperforming/lagging),
  `DIVERGENCE_BAND = 0.20` (sharp stock-vs-sector divergence). Both are
  **coarse, uncalibrated defaults** — there is no backtest to calibrate against,
  and they only separate "decisively different" from noise.
- Data via yfinance quotes; the industry → sector-ETF column lives in
  `providers/industry_map.py`. `other` is deliberately unmapped, so an
  unresolved industry surfaces as insufficient data rather than being attached
  to a plausible-looking ETF.

**Divergence is not automatically bad.** A stock diverging from its sector may be
precisely where the alpha is. A divergence therefore produces **a flag plus a
required explanation**, never a mechanical penalty — the demotion is triggered by
*contradictory* configurations, not by divergence per se.

**Caveat to carry into the report:** sector ETFs have their own crowding
dynamics; ETF relative strength is context, not truth.

---

## The verdict and the tier adjustment

One question per stock: **do the macro factors, the sector logic and the price
action tell the same story?** Three pairwise checks:

| Pair | Contradiction fires when |
|---|---|
| macro vs sector logic | tightening macro + expansionary logic in a capital-sensitive sector; or easing macro + contracting logic in a highly capital-sensitive sector |
| sector logic vs ETF RS | expansionary logic + sector ETF lagging SPY; or contracting logic + sector ETF outperforming |
| macro vs ETF RS | tightening macro + capital-sensitive sector outperforming; or easing macro + capital-sensitive sector lagging |

A pair with no directional expectation (neutral stance, low capital sensitivity,
inline RS) is recorded as **not applicable** rather than coherent — so the record
never implies agreement that was not tested.

**Adjustment rule:**

- All coherent → tier unchanged.
- **A material contradiction in any pair → demote exactly one tier** (A→B, B→C;
  C is the floor), and state the contradiction explicitly in the card commentary.
- **Never promote.** No upward adjustment exists under any configuration.
- **Insufficient data** (no ETF mapping, sparse macro read) → tier unchanged,
  recorded as "insufficient data" in both the record and the commentary. Missing
  data must not silently masquerade as coherence — but neither may it be
  punished as a contradiction, since that would let data gaps drive tiering.
- **Cap: at most one tier of demotion per stock**, regardless of how many pairs
  contradict. Multiple contradictions are all *named* but do not compound into a
  two-tier drop; this keeps the overlay bounded and prevents it from de-facto
  reordering the report.

`check_checkpoints.py` verifies these mechanically whenever `coherence.json` is
present: `tier_delta ∈ {0, −1}`, `tier` follows from `base_tier + delta`, no
promotion, and no demotion without a named contradiction.

---

## Reporting the overlay

- Ranked cards show **rank (unchanged)** and **tier (possibly demoted)**, plus
  the contradiction statement where one exists.
- The tier-grouping section notes which stocks were demoted into it and from
  where.
- The methodology section documents the overlay **once** (not per card): what it
  checks, that it is demotion-only, that it never alters rank or the composite,
  and the limitations below. Per-card text carries only that stock's specific
  contradiction or divergence explanation.

### Mandatory limitations disclosure

State plainly in the methodology section:

- The coherence verdict is a **qualitative judgment, not a calibrated model**,
  and is **deliberately unweighted** — there is no backtest to calibrate against.
- ETF relative strength is **context, not confirmation**; sector ETFs carry their
  own crowding.
- Macro readings are **directional summaries of central-bank material, not
  forecasts**.
- The overlay can only **lower** confidence in a name; it never raises it.

---

## Deferred (explicitly out of scope)

**Global industry policy + supply-chain mapping is deferred** — the motivating
example being a chip company's chain touching Japan / Korea / Taiwan.

- **Why.** It is simultaneously the most expensive, the most
  hallucination-prone, and the least verifiable of the requested additions.
  Company-level supplier relationships are **not** in EDGAR's structured data —
  they are scattered through 10-K risk factors and geographic segment
  disclosures. Relying on latent model knowledge for "company X depends on
  supplier Y in country Z" is the single highest fabrication risk in the
  proposal.
- **Consistency with prior trade-offs.** Stratified sampling was abandoned in
  v0.3 on token-budget grounds; policy + supply-chain mapping is of comparable
  cost. Doing the cheap, falsifiable parts first applies the same logic.
- **Preconditions before it can be attempted:**
  1. Extend the C2 primary tier to national industry ministries — **METI**
     (Japan), **MOTIE** (Korea), **Taiwan's Ministry of Economic Affairs** —
     since the current tier (central banks / official statistics / Reuters / WSJ
     / BlackRock / Fitch) does not cover industrial policy. Taiwan is not within
     the PRC/HK/Macau exclusion, so Taiwanese official sources are admissible.
  2. Apply the C2 cross-source corroboration hard gate to supply-chain claims —
     any chain relationship not corroborated by ≥2 primary-tier sources is not
     written.
  3. Prefer **coarse geographic exposure** (EDGAR geographic segment revenue +
     industry-level established facts) over company-level supplier
     identification.

**Until then: no industry-policy or company-level supply-chain claims appear
anywhere in the output.**
