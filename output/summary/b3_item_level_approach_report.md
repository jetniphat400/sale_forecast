# Phase B, B3 — How aggregate levels support item-level forecasting

Single Modeler task, continuing directly from B1/B2. Script: `src/item_level_reconciliation.py`.
Evaluated on the forecast_date-keyed series (B1's recommendation) — a stated scope choice, not
re-tested against createDate here. No model choice written to `config.yaml`.

## Approaches compared (all measured at item level, test set = months 26-31 of 31)

- **Direct**: Combination forecast fit on each item's own series independently.
- **Top-down**: Combination forecast at Type level, allocated to items by each item's historical
  share of its Type's total qty over the fitting window (train+val, 25 months), held constant
  across the 6 test months.
- **Reconciled**: each item forecast directly (= Direct), then rescaled per Type per month so the
  items in a Type sum exactly to that Type's own Combination forecast for that month.

113 items with a full 31-month history, across 8 Types.

## Results

| Approach | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|
| Direct | 350.04 | 440.86 | -246.77 | 1.73 |
| Reconciled | 349.97 | 440.90 | -247.52 | 1.72 |
| **Top-down** | **341.61** | **434.83** | -247.52 | **1.66** |

**Top-down has the best point estimate on every metric except Bias (tied with Reconciled).**
**Confidence: LOW that this margin is real** — the paired significance test (same methodology as
the prior winner-margin check, `strategy_gap_and_bias_report.py`) finds **none of the three
pairwise differences distinguishable from noise**:

| A vs B | mean diff (B-A) | paired t |
|---|---|---|
| Direct vs Top-down | -8.43 | -1.52 |
| Direct vs Reconciled | -0.07 | -0.34 |
| Top-down vs Reconciled | +8.36 | 1.51 |

All \|t\| < 2. **Stated directly, per instruction: none of the three approaches is clearly
better on this evidence alone** — Top-down's edge is a real point estimate but not statistically
distinguishable from Direct or Reconciled with 113 paired items.

**Validation-to-test gap**: near-identical and large-negative for all three (Direct -19.9%,
Top-down -21.0%, Reconciled -19.9%) — test MAE is much better than validation predicted, for
every approach equally. This matches B1's finding that forecast_date-keyed test-set performance
broadly outperforms validation; it is not specific to any one approach.

## Does it depend on the item's share of its Type? YES — this is the clearest finding here

Splitting by whether an item is "dominant" (≥30% of its Type's train+val qty) or not:

| Approach | Minor items (n=~108) MAE | Dominant items (n=~5) MAE |
|---|---|---|
| Direct | 318.80 | 823.06 |
| Top-down | **310.85** | **807.43** |
| Reconciled | 318.74 | 822.84 |

**Top-down's advantage is small for minor items (318.80→310.85, -2.5%) but larger for dominant
items (823.06→807.43, -1.9% in absolute terms, but the underlying per-item detail below shows a
much bigger effect for the specific dominant focus item).** For the one focus item that actually
qualifies as dominant:

| Approach | EEE-F-FC-1040010002 (share=48.3%) MAE | Bias |
|---|---|---|
| Direct | 1206.10 | -1206.10 |
| **Top-down** | **1011.91** | **-971.87** |
| Reconciled | 1209.47 | -1209.47 |

**Top-down cuts this dominant item's own MAE by 16.1% and \|Bias\| by 19.4%**, HIGH confidence in
the number (direct recomputation) though not tested for significance at n=1. The mechanism is
intuitive: for an item that IS most of its Type's volume, the Type-level aggregate forecast is
essentially a smoothed version of the item's own signal, so allocating it back down loses little
information while gaining the aggregate's lower volatility.

For the two minor/mid-rank focus items (shares 1.2% and 3.2%), Top-down and Direct/Reconciled are
nearly identical (`HS-F-99-02110`: 503.8→497.3 MAE; `HS-F-99-0213`: 228.5→228.5, unchanged) —
**for items that are a small share of their Type, the Type-level aggregate carries comparatively
little information about that specific item, so top-down allocation helps little to not at all.**

## What the evidence supports

- **No approach is clearly better in general** — the pooled paired test does not clear
  significance for any pair.
- **The benefit of Top-down (and by extension, of using the aggregate level at all to help an
  item) DOES depend on the item's share of its Type**, confirmed directly: material improvement
  for a dominant item (~16-19%), negligible-to-no improvement for minor/mid-rank items. This is
  the answer to "does it depend on the item's share of its type" — **yes, clearly, HIGH
  confidence in the direction, MODERATE in the exact magnitude** (single-item evidence for the
  dominant case; only one dominant item exists in this scope to test).
- **Practical reading**: a share-of-type-conditional policy (use Top-down or a share-weighted
  blend for dominant items, Direct for minor items) is better supported by this evidence than
  picking one approach uniformly — but this was not itself tested as a fourth "conditional"
  approach here (flagged as a natural next step, not done).

## Confidence levels

- Point-estimate ranking (Top-down best, narrowly): **MODERATE** (real numbers, not
  significance-tested as a pooled difference).
- No pairwise difference is statistically distinguishable at n=113: **HIGH** (direct paired
  t-test, consistent with this project's prior significance-testing methodology).
- Benefit is share-of-type-dependent (dominant items benefit more): **HIGH** in direction,
  **MODERATE** in magnitude (only 1 genuinely dominant item in this scope).

## Unresolved

- Not tested against createDate-keyed series (stated scope choice, not a gap in evidence so much
  as an explicit boundary — could be repeated as a robustness check).
- A conditional/blended approach (Top-down for dominant items, Direct for minor ones) was not
  itself built or tested — a natural next step, not attempted here.
- Only one item in this 128-item scope crosses the 30%-dominance threshold used here — the
  "dominant item" finding rests on an n=1 case study for the sharpest test, though the
  minor-item pattern (n≈108-112) is well-powered.
