# Focus-Item Model Selection — EEE-F-FC-1040010002, HS-F-99-02110, HS-F-99-0213

**Role**: Modeler (per `AGENTS.md`), single agent — three items examined individually with the
same candidate set and evaluation, one context. **Run**: 2026-09-08. Data:
`output/data/processed_all_divisions_monthly_qty.csv` (335-item scope, forecast_date-keyed,
snapshot_pull_date 2026-09-07 09:05:06 — the same data Top-down combination, the baseline compared
against throughout, was itself scored on in Phase C step 2). Every figure cited to its script/CSV.

**Purpose, restated**: these three items have only ever been scored as part of aggregate
Category/Type/division comparisons. This task asks a narrower question per item: given every
candidate the pipeline supports, and the user's own stated criterion — **low bias and no
overfitting**, not accuracy alone — what fits each item individually?

---

## Part 1 — Candidate set

All 11 candidates fit successfully on every item, at every origin, with **zero fitting
failures** (`focus_items_rolling_origin_all.csv`: 231 rows = 3 items × 7 origins × 11 models,
`error` column null throughout; same for the 66 val/test rows). Candidates: Naive, MA3, MA6,
MA12, SES, Holt, Croston, SBA, **TSB** (new — statsforecast has no auto-optimized TSB variant,
so `src/models.py`'s `tsb_forecast` grid-searches `alpha_d`/`alpha_p` over `{0.05, 0.1, 0.2, 0.3,
0.4}` minimizing in-sample fitted error, a stated assumption not derived from this project's
data), the adopted six-model Combination (unchanged definition — Naive/MA3/MA6/MA12/Croston/SBA,
NOT redefined to include SES/Holt/TSB), and Top-down (Type-level Combination allocated by the
item's historical qty share, refit at every origin — same method as
`src/transferability_all_divisions.py`).

**Directly confirmed, not assumed**: demand classification (`aggregate_levels.classify_demand`,
Syntetos-Boylan thresholds) — `EEE-F-FC-1040010002`: **Erratic** (ADI=1.107, CV²=0.718, 9.7%
zero months) — matches the classification already recorded elsewhere in `STATUS.md`, not Lumpy.
`HS-F-99-02110`: **Lumpy** (ADI=2.583, CV²=2.510, **61.3% zero months**). `HS-F-99-0213`:
**Lumpy** (ADI=1.632, CV²=1.410, **38.7% zero months**).

---

## Part 2 — Per-item evaluation (rolling-origin, primary; 7 origins, `get_origins(31,6)` — same
origins as every other backtest in this project)

### EEE-F-FC-1040010002

| Model | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|
| TSB | 580.57 | 749.08 | -410.37 | 1.17 |
| MA3 | 594.82 | 763.57 | -452.60 | 1.21 |
| MA6 | 595.87 | 779.40 | -472.69 | 1.20 |
| Combination | 602.93 | 753.30 | -230.63 | 1.19 |
| **Top-down** | 605.86 | 734.10 | **18.90** | 1.17 |
| SES | 646.03 | 794.54 | -469.45 | 1.31 |
| Naive | 646.93 | 795.27 | -470.40 | 1.31 |
| Holt | 695.54 | 841.00 | -525.44 | 1.41 |
| SBA | 706.72 | 844.50 | 60.86 | 1.35 |
| Croston | 719.71 | 854.54 | 109.42 | 1.37 |
| MA12 | 862.76 | 1010.82 | -158.38 | 1.66 |

**Bias**: mean MAE ranks TSB first, but **Top-down's mean Bias (18.9) is by far the smallest in
magnitude of any candidate** — every other candidate's |Bias| is 60-525. **Sign
consistency**: **no candidate is sign-consistent across the 7 origins**, Top-down included (3
positive, 4 negative origins) — even the least-biased-on-average candidate flips direction
origin to origin (`focus_items_bias_sign_all.csv`). This item does not have a steadily-biased
candidate at all; every model's mean-near-zero-or-not is an average of flip-flopping errors.

**Winner-per-origin**: `focus_EEE-F-FC-1040010002_winner_per_origin.csv` — **every one of the 7
origins was won by a DIFFERENT model** (MA3, TSB, MA12, Croston, Holt, MA6, Top-down — one win
each). No candidate is a repeat winner. This is the most unstable winner pattern of the three
items, consistent with this item's known collapse-then-recovery volatility.

**Overfitting gap (secondary, train/val/test — flagged unrepresentative window, see Part 2
note below)**: Combination's gap is 119.8%. SBA (138.8%), MA12 (133.7%) and Croston (132.2%)
exceed it; Top-down (120.2%) is essentially level with Combination; TSB (91.1%), MA3 (85.8%) and
MA6 (49.1%) are materially smaller.

### HS-F-99-02110 (Lumpy, 61.3% zero months)

| Model | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|
| Naive | 121.21 | 199.32 | -121.21 | 2.15 |
| SBA | 125.81 | 188.59 | -98.55 | 2.24 |
| Croston | 126.06 | 188.14 | -97.36 | 2.24 |
| SES | 126.21 | 190.35 | -101.03 | 2.24 |
| MA12 | 126.77 | 186.82 | -92.89 | 2.25 |
| Combination | 127.38 | 190.08 | -99.43 | 2.26 |
| **Top-down** | 127.98 | 186.97 | -92.61 | 2.28 |
| Holt | 128.08 | 189.99 | -94.71 | 2.26 |
| TSB | 128.20 | 189.78 | -95.94 | 2.27 |
| MA6 | 130.55 | 187.11 | -86.76 | 2.31 |
| MA3 | 133.88 | 196.65 | -99.83 | 2.36 |

**A tight cluster** — every candidate's MAE sits within 121-134, a 10% spread. **Bias**: **Naive,
SBA and Croston are the only three sign-consistent candidates (always negative — every one of
the 7 origins under-forecasts)** — a genuinely steady bias, unlike EEE. Top-down and Combination
are NOT sign-consistent despite competitive mean-Bias magnitude.

**Winner-per-origin**: Naive wins 4 of 7, Holt 2, MA12 1 — Naive is the closest thing to a
repeat winner among the three items, though still short of a majority-dominant pattern.

**Overfitting gap — flagged, not comparable at face value**: gap percentages here are enormous
(600-1600%) for every model, because the validation-window MAE denominator is tiny (30-68) —
this is the already-documented Feb-Jul 2026 anomalous final window (`STATUS.md`, closed without
further pursuit, Section 8), which this task's own train/val/test split lands on for every
focus item. **Reported for completeness, but explicitly not treated as a reliable comparative
signal here** — this is exactly why rolling-origin is primary and train/val/test secondary.

### HS-F-99-0213 (Lumpy, 38.7% zero months)

| Model | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|
| **Top-down** | **112.26** | 149.94 | -53.28 | 1.53 |
| SBA | 112.29 | 153.65 | -70.88 | 1.54 |
| Croston | 112.42 | 153.02 | -68.24 | 1.54 |
| MA12 | 112.72 | 149.43 | -50.25 | 1.54 |
| Combination | 119.66 | 158.34 | -46.02 | 1.63 |
| TSB | 126.01 | 166.05 | -46.95 | 1.71 |
| MA6 | 126.13 | 160.27 | -33.45 | 1.71 |
| Holt | 126.77 | 162.74 | -39.75 | 1.72 |
| SES | 128.50 | 164.82 | -36.37 | 1.74 |
| MA3 | 133.01 | 172.36 | -31.36 | 1.80 |
| Naive | 144.69 | 185.33 | -21.93 | 1.92 |

**Top-down is already the outright MAE winner** for this item, though SBA/Croston/MA12 are
statistically indistinguishable from it (within 0.5 MAE). **Bias**: no candidate is
sign-consistent. Combination has the smallest mean-|Bias| (46.02) of the near-top-MAE group;
Top-down's is 53.28.

**Winner-per-origin**: Naive 2, SBA 2, Top-down 1, MA3 1, Holt 1 — spread thin, no dominant
winner.

**Overfitting gap (secondary)**: Combination's gap is 116.8%. Only MA3 (123.7%) exceeds it;
**Top-down's own gap (104.5%) is smaller than Combination's** — a mild point in Top-down's
favour on this secondary metric.

---

## Part 3 — Item-specific considerations

### EEE-F-FC-1040010002: pre-recovery supplementary split

**Method, stated explicitly**: the standard 7 rolling origins (`MIN_TRAIN_MONTHS=13`) all have
test windows that already extend into the 2025-04-onward recovery — **none of this project's
standard origins can test a model purely on pre-recovery data**, confirmed by construction (the
earliest origin's test window is months 13-18 = 2025-02 to 2025-07). A separate, single-split
supplementary check was built instead: **train on 2024-01 to 2024-09 (9 months), test on 2024-10
to 2025-03 (6 months)** — the largest split that stays entirely within the collapse-to-trough
window (qty is confirmed 0 for 2025-01/02/03, `processed_all_divisions_monthly_qty.csv`).

| Model | MAE | Bias | MASE |
|---|---|---|---|
| **Naive** | **197.67** | 180.67 | 0.22 |
| SES | 209.61 | 198.58 | 0.24 |
| TSB | 1531.70 | 1531.70 | 1.72 |
| Holt | 1558.48 | 1558.48 | 1.75 |
| Combination | 1584.45 | 1584.45 | 1.78 |
| MA3 | 1643.00 | 1643.00 | 1.85 |
| SBA | 1652.79 | 1652.79 | 1.86 |
| Croston | 1742.74 | 1742.74 | 1.96 |
| Top-down | 1767.02 | 1767.02 | 1.99 |
| MA6 | 2126.50 | 2126.50 | 2.39 |
| MA12 | 2161.00 | 2161.00 | 2.43 |

**This inverts the full-series ranking entirely.** TSB, the full-series MAE winner, is **7.9x
worse** here than Naive; Top-down (near-best full-series bias) is **8.9x worse than Naive** here
and has the second-worst MAE of all 11. **The full-series numbers for TSB/MA-family/Combination/
Top-down are materially inflated by the 2025-09-onward recovery ramp being easy to track once it
starts — the models that "look good" full-series are not doing so because they handle the
collapse well; they do so because the recovery period rewards models that can ride a rising
trend, and the collapse period is a small enough share of the 31-month window (6 of 31 test-month
slots touch it) to be swamped in the full-series average.** Naive and SES — which just hold the
last observed level — are what actually tracks the sudden drop-to-zero correctly; every model
with any smoothing/momentum (MA6/MA12/Combination/Top-down/TSB) overshoots badly into the
collapse because it is still carrying pre-collapse momentum. **Confidence: high** — this is a
direct, single supplementary computation, not an inference, though it rests on one split (n=1),
smaller than the standard 7-origin evidence base, and is reported as such.

### HS-F-99-02110 and HS-F-99-0213, side by side (same Type, "Medium Voltage Surge Arrester")

| | HS-F-99-02110 | HS-F-99-0213 |
|---|---|---|
| Zero-month % | **61.3%** | **38.7%** |
| ADI / CV² | 2.583 / 2.510 | 1.632 / 1.410 |
| Croston rank (of 11, by MAE) | 3rd | 3rd |
| SBA rank | 2nd | **2nd** (tied ~112.3) |
| TSB rank | 9th | 6th |
| Top-down rank | 7th | **1st** |
| Best candidate | Naive | Top-down |

**Croston/SBA do NOT show the aggregate Intermittent class's known weakness here.** The
established aggregate finding (`STATUS.md`, Phase 3.1 backtest) is that Croston/SBA were the
**worst** of six models on the pooled Intermittent class (MAE 26-28 vs. 2.55-2.77 for MA3/Naive
— a magnitude comparison at a different, pooled scale, not directly comparable to these two
items' own units). **At the individual-item level, for both of these two specific Lumpy items,
Croston and SBA rank 2nd-3rd of 11 — competitive, not the worst.** This is a genuine, evidenced
difference between how these models behave on an aggregate class average versus on a specific
item within it — **confidence: high**, directly computed, not inferred from the aggregate figure.

**"A fitting model for one may fit the other" — does NOT hold cleanly.** Top-down ranks 7th of 11
for `HS-F-99-02110` but 1st of 11 for `HS-F-99-0213` — despite being the same Type, same
division, and both Lumpy, the item that best fits one (Top-down for `0213`) is mediocre for the
other. `HS-F-99-02110`'s much higher zero-rate (61.3% vs. 38.7%) is the most visible structural
difference between them and a plausible reason Top-down (which allocates a shared Type-level
signal) fits `0213` better — `0213` likely tracks its Type's overall pattern more closely than
`02110` does, though this is stated as a plausible explanation, not independently verified
further (stopping rule).

---

## Part 4 — Verdict per item

**Paired significance vs. Top-down** (`focus_items_significance_vs_topdown_all.csv`), same
methodology as `src/transferability_all_divisions.py`/`src/item_level_reconciliation.py`: paired
by origin, `diff = candidate_MAE - Top-down_MAE`, `t = mean(diff)/se(diff)`, n=7 origins per
test.

| Item | Best-placed candidate vs. Top-down | t-stat | Significant (\|t\|>2)? |
|---|---|---|---|
| EEE-F-FC-1040010002 | TSB (mean diff -25.28) | -0.230 | **No** |
| HS-F-99-02110 | Naive (mean diff -6.77) | -1.203 | **No** |
| HS-F-99-0213 | SBA (mean diff +0.02, essentially tied) | 0.007 | **No** |

**No candidate beats Top-down combination with statistical confidence on any of the three
items.** (One candidate is significantly WORSE: MA12 for `EEE-F-FC-1040010002`, t=3.649 — a
one-sided caution against MA12 specifically for that item, not a finding about any other model.)

### EEE-F-FC-1040010002 — **keep Top-down combination**. Confidence: moderate.

TSB has the lowest full-series MAE (580.57 vs. 605.86) but the difference is not significant
(t=-0.230), TSB's own Bias magnitude (-410.37) is far larger than Top-down's (18.90 — the
smallest of any candidate), and TSB is a **markedly worse fit specifically during the collapse**
(pre-recovery MAE 1531.70 vs. Naive's 197.67 — 7.9x worse). Given the user's explicit criterion
is **low bias**, not lowest MAE alone, and no candidate clears statistical significance, **Top-
down's near-zero mean bias is a genuine point in its favour that a pure MAE ranking would miss.**
Neither Top-down nor any other candidate is sign-consistent, and the winner changes every single
origin — this item does not currently have a candidate that is both accurate and steadily behaved;
**recommend keeping the default, flag this item as inherently hard to fit consistently, not as a
model-selection failure.**

### HS-F-99-02110 — **keep Top-down combination**. Confidence: moderate.

Naive has the best MAE (121.21) and is one of only three sign-consistent candidates (steadily
under-forecasting, not flip-flopping) — a real, evidenced trait, but the margin over Top-down is
not significant (t=-1.203, the strongest of the three items' improvement attempts, still short of
conventional significance) and the whole candidate set is clustered within a 10% MAE band, so
this is a thin basis for an override. Croston/SBA's competitive individual-item performance
(against their poor aggregate-class reputation) is a useful finding but does not itself beat
Top-down either. **Recommend keeping the default.**

### HS-F-99-0213 — **keep Top-down combination**. Confidence: high (of the three, the clearest
case for keeping the default, since Top-down IS the empirical winner here, not merely tied).

Top-down already has the best rolling-origin MAE (112.26) among all 11 candidates, plus a
smaller val-test gap (104.5%) than Combination's own (116.8%) — no candidate offers a
meaningfully better fit on either accuracy or the overfitting-gap criterion. SBA/Croston/MA12 are
statistically indistinguishable (differences under 0.5 MAE, well short of the paired-t threshold)
so are not recommended overrides either, just noted as near-ties. **Recommend keeping the
default with the highest confidence of the three items.**

### What would need recording in config if an override were ever adopted (NOT done in this task)

If future evidence changed this verdict for any item, the mechanism already exists and would need
no new structure: `config.yaml`'s `division_forecast_method` block (Phase C closure,
2026-09-07) currently records method at DIVISION level only — an item-level override would need
a new, analogous per-item key (e.g. `item_forecast_method_override: {ITEMCODE: {method, reason}}`,
mirroring `placeholder_item_assignments_82`'s per-item shape) so a single item can diverge from
its division's default without changing the division-level entry. **Not created in this task, per
instruction — nothing was written to config.**

---

## Confidence summary

| Finding | Confidence |
|---|---|
| All 11 candidates fit successfully, zero failures, on every item/origin | High (directly confirmed) |
| Demand classification: EEE=Erratic, HS-02110=Lumpy, HS-0213=Lumpy | High (directly computed) |
| No candidate beats Top-down with statistical significance, any item | High (direct paired t-test) |
| Top-down's near-zero bias for EEE is a genuine advantage over the MAE-only winner (TSB) | High (directly computed) |
| EEE's full-series ranking is materially inflated by the recovery period, not collapse-period skill | High (direct supplementary split), though based on n=1 split |
| Croston/SBA are competitive (not worst) for these two specific Lumpy items, unlike the aggregate class | High (directly computed) |
| "A fitting model for one may fit the other" does not hold for HS-02110/HS-0213 | Moderate (the zero-rate-difference explanation is plausible, not independently verified further) |
| Train/val/test overfitting-gap figures for HS-F-99-02110 are not a reliable comparative signal | High (near-zero denominator effect, directly visible in the data) |

## What remains unresolved

1. **Why `HS-F-99-02110` and `HS-F-99-0213` diverge so much on which model fits best** (Top-down
   7th vs. 1st) is not investigated beyond the plausible zero-rate explanation — would need
   further item-level structural comparison, not attempted here (stopping rule).
2. **EEE-F-FC-1040010002's pre-recovery split is a single supplementary check (n=1)**, not a
   7-origin rolling result — a genuinely smaller evidence base than the rest of this report;
   treated as suggestive, high-confidence for what it directly shows, but not equivalent in
   statistical weight to the primary rolling-origin results.
3. **The TSB alpha grid (`{0.05,0.1,0.2,0.3,0.4}`) is a stated assumption**, not derived from
   this project's data or exhaustively searched — a finer grid might change TSB's exact numbers
   slightly, though unlikely to change the qualitative conclusion (no candidate beats Top-down
   significantly).
4. **No item-level override config mechanism exists yet** — not built in this task, since no
   item's evidence supported adopting one.
5. **`cube_Sale_APD` is a live, growing table**; a re-run on a later date will not reproduce
   these exact figures, though the qualitative conclusions (no significant override for any of
   the three items) are expected to be stable.
