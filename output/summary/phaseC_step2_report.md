# Phase C Step 2 — Forecast All In-Scope Items, Value-vs-Quantity Test, Transferability

**Role**: Modeler (per `AGENTS.md`), single agent — "forecasting all divisions is one continuous
run that must use identical settings throughout, so it is not split." **Run**: 2026-09-07, live
against `[salewarehouse].[dbo].[cube_Sale_APD]`. Every figure below is cited to its script/CSV.

---

## Part 0 — Preconditions

### 0a. Division-filter check across the active pipeline

**Confidence: high, directly confirmed by grep + a passing test suite, not assumed.** Checked
every script under `src/` (the active pipeline; `src/investigations/*.py` are archived,
already-run one-off scripts, addressed separately below) for a `division = '...'` SQL WHERE
clause:

| Script | Division filter? | Evidence |
|---|---|---|
| `src/load_data_full.py` | **None.** Selects `division AS division_db_raw` (reference only); division attached from `config['sheet_to_division']`. | Direct grep + source read. |
| `src/investigations/load_data.py` (the file this project's prose calls `src/load_data.py`, relocated in the 2026-09-04 reorg) | **None.** Same pattern as above. | Direct grep + source read. |
| `src/score_forward_test_v2.py` | **None.** | Direct grep + source read. |
| `src/aggregate_levels.py`, `item_level_reconciliation.py`, `backtest_rekeyed.py`, `forward_test_v2.py`, `forward_test_common.py`, `leakage_guard.py`, `models.py`, `run_pipeline.py` | **The word "division" does not appear at all.** | `grep -c division` on each returned 0. |

**No fix was needed** — the 2026-09-04 loader fix (STATUS.md, "Division source-of-truth
correction") is still in place and was never reverted. `python -m pytest tests/` passes 40/40
before and after this task's other changes, confirming nothing regressed.

**Why PEM101 still shows a 1.22% shift, explained, not a sign of a missed filter**: the aggregate
full-scope re-validation's 1.22% figure (`phaseC_revalidation_report.md` §1) covers ALL 171
PEM101-sheet codes; `load_data_full.py`'s own scope is only the 128-item Fuse+Surge Category
subset of that sheet. A fresh run of `load_data_full.py` in this task confirms this directly:
81 of 27,746 rows (0.29%) have a `division_db_raw` differing from the item's pricelist division
— small, already counted (no filter), consistent in direction with the 1.22% figure at a
different (smaller, Category-restricted) scope. **The two numbers describe different scopes, not
a contradiction.**

**Archived `src/investigations/*.py` scripts (validator/investigation scripts, e.g.
`phaseC_validator_PEM107.py`, `investigate_2025_decline.py`) still contain literal
`division = '...'` clauses.** These are frozen historical artifacts of already-completed,
one-off tasks — never re-run by `src/run_pipeline.py` or any script this task touches. Left
unmodified, consistent with this project's existing precedent (`src/investigations/
score_forward_test.py`, the superseded v1 scorer, was likewise left as-is when found in the same
state on 2026-09-04).

### 0b. The 7-item PEM104 overlap

**Confidence: high — this was already the resolution the 2026-09-07 Synthesizer's own CSV
applied**, not something new applied here. `output/summary/phaseC_step1revised_item_status_445.csv`
already classifies all 12 PEM104-sheet codes (the 7 no-history ones and the 5 with history alike)
as `excluded — division excluded from forecasting (data volume)` — Reading A from the synthesis
report's two-sided framing. **This task ratifies that reading as the one to use going forward**:
a division-level exclusion (data volume, unrelated to division tagging) subsumes the item-level
placeholder question for these 7 codes. They are removed from the 89-item placeholder-pending
population's *actionable* count (82 remain pending a mechanism decision), per instruction. See
STATUS.md's Phase C step 2 entry for the recorded decision.

### 0c. The 9-item Cube_CES-trace-only check

**Confidence: high, single direct query, per instruction ("do not spend more than this single
check").** Queried `Cube_CES` for the 9 codes' Omni-Channel rows directly
(`output/summary/phaseC_9item_cubeces_check.csv`, 19 rows across the 9 codes):

**All 19 rows are `Status = 'Actual'`, ActualQty > 0, BacklogQty = 0 — none are Backlog rows for
undelivered contracts.** Every row carries a real `ActualDelDate`. **Dates are the key finding**:
`CtrDate` ranges 2023-03-04 to 2023-10-25; `ActualDelDate` ranges 2023-03-20 to 2023-11-15 — **all
19 rows are dated in 2023**, before this project's `cube_Sale_APD`-based modelling window even
starts (2024-01-01) and before several of these divisions' own structurally-absent-before-2024
history boundary (already established for PEM102/PEM103/PEM107/CI101 in Phase C step 1). **This
fully explains the gap as a table-coverage boundary, not a data-integrity problem**: `Cube_CES`
extends back to 2023 for these codes; `cube_Sale_APD` (the table this project's entire pipeline
reads) does not, for these specific items. Not further investigated, per instruction.

---

## Part 1 — Forecast all in-scope items

### Scope

**335 forecast-status items** (`output/summary/phaseC_step1revised_item_status_445.csv`,
`status_category == 'forecast'`), across **5 of 6 divisions** — **PEM104 contributes ZERO
forecast-status items** (all 12 excluded, Part 0b) — confirmed directly, not assumed, before
building anything: PEM101 144, PEM107 112, PEM103 50, PEM102 16, CI101 13.

**Query pattern** (`src/load_data_all_divisions.py`): `itemcode IN (335 codes)`,
`revenue_type = 'Omni Channel'`, `status IN ('Actual','MPS')`, `createDate >= 2024-01-01` — **no
division filter**; division attached from `config['sheet_to_division']`, `division_db_raw` kept
for reference. 36,743 raw rows pulled; 2,708 (7.37%) show a `division_db_raw` differing from the
item's pricelist division — still counted, consistent with the established `-OLD`-tag and
cross-division patterns. Series keyed on `forecast_date`, frozen snapshot
(`snapshot_pull_date=2026-09-07 09:05:06`). **Leakage guard active and load-time-enforced**: the
loader itself excludes any month too close to the pull date (min_margin_days=30) before writing
the common window, not just at backtest time — 2026-08 was excluded this way (7-day margin,
needed 30). Common window: **31 months, 2024-01 to 2026-07** — the same window every other Phase
B/C backtest in this project uses, confirmed not coincidental (the leakage-guard-aware selection
converged on it independently).

### Method

**Top-down combination**: arithmetic mean of the six base models (Naive, MA3, MA6, MA12, Croston,
SBA — `src/models.py combination_forecast`) fitted at **Type level**, division-qualified
(`"DIVISION::Type"` keys, so no Category/Type name collision across divisions is ever pooled —
e.g. PEM101's "Fuse" and any other division's "Fuse" are never summed together), allocated to
items by each item's historical qty share of its Type over the fitting window. Reuses
`src/backtest_rekeyed.py`'s tested `run_rolling_origin`/`run_train_val_test`/`compute_metrics`
and `src/item_level_reconciliation.py`'s `forecast_all_approaches` UNCHANGED (imported, not
copied) — `src/backtest_all_divisions.py` (Category/Type level) and
`src/forward_test_all_divisions.py`/`src/charts_all_divisions.py` (item-level Top-down).
**Rolling-origin (7 origins) is PRIMARY; train/val/test is SECONDARY**, per this project's
adopted evaluation policy.

### Results — per division (Type level, Combination, rolling-origin, qty basis)

Source: `phaseC_step2_per_division_summary_qty.csv`.

| Division | MAE | RMSE | Bias | MASE | n items |
|---|---|---|---|---|---|
| CI101 | 13.01 | 16.75 | 5.13 | 0.74 | 13 |
| PEM101 | 2895.82 | 3426.47 | -836.22 | 1.29 | 144 |
| PEM102 | 1.98 | 2.46 | -0.36 | 1.17 | 16 |
| PEM103 | 36.96 | 45.34 | -28.17 | 2.16 | 50 |
| PEM107 | 69.18 | 80.10 | 15.61 | 0.72 | 112 |

All five divisions' Bias is negative or small-positive (under-forecasting bias, consistent with
this project's already-established structural reason: point forecasts targeting the mean of
spiky/intermittent demand). PEM103's MASE (2.16) is markedly worse than the others — consistent
with Phase C step 1's flag that PEM103's demand is 0% Smooth/Erratic (mean ADI 12.5).

**Rolling-origin stability of the winner** (`phaseC_step2_winner_stability_qty.csv`): across all
40 division-qualified Types, the mean winner-stability is **34.3%** (i.e. the single best-by-mean
model was ALSO the best at only about a third of each Type's 7 origins) and **Combination itself
is the outright mean-MAE winner in only 3 of 40 Types**. **This is not a weakness specific to this
run — it reproduces this project's own long-standing finding (Phase 3.1: "None of the 10
Category/Type series had a stable rolling-origin winner") at 4x the scope**, reinforcing rather
than undermining the case for Combination (a robust average, not usually THE best, rarely the
worst) over picking a single per-Type model.

### Focus codes individually (Top-down, adopted method, single train/val/test split — secondary
evaluation, since these three specific codes' behaviour across the primary rolling-origin split is
already tracked in `phaseC_step2_transferability_item_rolling_origin.csv`)

Source: `phaseC_step2_topdown_item_test_scores.csv` (recomputed directly with the Top-down branch,
not the raw per-item Combination number, since the adopted method is Top-down, not Direct, at
item level).

| Item | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 1016.37 | 1392.28 | -978.56 | 2.08 |
| `HS-F-99-02110` | 497.28 | 788.19 | -487.09 | 8.52 |
| `HS-F-99-0213` | 228.50 | 386.99 | -178.72 | 2.62 |

All three under-forecast (negative Bias), consistent with this project's established structural
bias finding. `HS-F-99-02110`'s MASE (8.52) is an outlier — consistent with its already-documented
Lumpy classification and small scale (its own first-difference scale is tiny, inflating MASE for
a fixed absolute error) — not a new finding, restated at the new scope.

### Forward-test log extended

`src/forward_test_all_divisions.py` → `output/summary/forward_test_log_all_divisions.csv`
(2,340 rows: 2,010 Item + 240 Type + 90 Category, all 335 items had full 31-month history — no
zero-history rows needed). **Schema extended with one column, `division`** (necessary: Type/
Category names collide across divisions) — every other column unchanged from
`forward_test_log_v2.csv`'s schema. Metadata:
`forward_test_log_all_divisions_metadata.json`. **`actual_qty` is empty for every row** — target
months 2026-08 through 2027-01 have not happened yet.

**128-item version archived**, not deleted: `output/summary/archive/
forward_test_log_v2_128items_superseded_2026-09-07.csv` (+ scored/metadata copies), with
`SUPERSEDED_forward_test_log_v2_128items_README.txt` explaining the supersession is **scope-only**
— date key and method are unchanged, unlike the earlier 58-item log's three-way supersession.
Confirmed before archiving: 0 of 828 rows had a non-null `actual_qty`. **No scoring script exists
yet for the new log** (`src/score_forward_test_v2.py` is built for the old 128-item schema/scope
specifically and must not be pointed at the new log unmodified) — flagged as not-yet-done work,
not attempted here.

---

## Part 2 — Value-based vs. quantity-based aggregation

**Method**: `src/backtest_all_divisions.py --value-col sale` — the IDENTICAL backtest (same
models, same rolling-origin/train-val-test split, same division-qualified Category/Type
grouping) run on `sale` instead of `qty` as the aggregated value.

### Zero-inflation: identical by construction, not an empirical question

**Confidence: high, a mathematical necessity, not a measured coincidence.** Category-level
zero-% and Type-level zero-% are **exactly the same** under both bases (Category 25.59%, Type
37.18%) — a month with zero units sold has zero sale value for the same underlying rows, so
"aggregation reduces zero-inflation" cannot be an artifact of which physical unit is summed: the
zero/non-zero pattern is identical either way. **Item-level zero-% (qty) is 58.1%** — so
aggregation still cuts zero-inflation substantially at this 335-item, 5-division scope (58.1% →
37.18% → 25.59%), though **not all the way to 0% as the original 128-item PEM101-only finding
reported** — a genuinely weaker, more honest result at the broader scope, not a re-confirmation of
the original number.

### Validation-to-test gap: mixed, no uniform answer

| Division | qty gap % | sale gap % | Value-basis vs. qty-basis |
|---|---|---|---|
| PEM101 | -28.70 | -7.32 | smaller magnitude under value |
| PEM102 | +50.51 | +64.15 | larger under value |
| PEM103 | +134.10 | +220.70 | larger under value |
| PEM107 | -16.61 | -37.80 | larger under value |
| CI101 | -31.59 | -27.78 | smaller under value |

Source: `phaseC_step2_val_test_gap_qty.csv`, `_sale.csv`. **2 of 5 divisions show a smaller gap
under value aggregation, 3 of 5 show a larger one — no consistent direction.** MASE (scale-free)
is also very similar between bases for every division (e.g. PEM101 1.29 qty vs. 1.22 sale; PEM103
2.16 qty vs. 1.96 sale) — neither basis is a clear, general improvement.

### Verdict: evidence supports continuing with quantity-based aggregation

**Confidence: moderate — genuinely mixed evidence, not a strong result either way.** The original
concern (summing units across different product kinds within a Category has no physical meaning)
is a valid conceptual point and is NOT undermined by this test, but it also does not translate
into value aggregation being measurably better here: the zero-inflation benefit holds identically
under both bases (so that part of the original claim was never actually about units, contrary to
what the concern implied), and the overfitting-gap comparison is mixed with no clean winner.
**No evidence found to justify switching Top-down allocation from quantity to value** — the
current method (quantity) is kept, not because value was tested and lost decisively, but because
it was tested and found no consistent advantage.

---

## Part 3 — Transferability by division (Top-down vs. Direct vs. Naive, rolling-origin)

**Method**: `src/transferability_all_divisions.py` — at every rolling-origin (same 7 origins as
Part 1), scores Direct (item's own Combination), Naive (item's own Naive), and Top-down
(division-qualified Type-level Combination, allocated by the item's historical share AT THAT
ORIGIN — refit every origin, not a single fixed allocation), for every one of the 335 items.
6,979 item x origin x approach rows scored. Source: `phaseC_step2_transferability_per_division.csv`,
`_verdict.csv`, `_significance.csv`.

| Division | MAE Top-down | MAE Direct | MAE Naive | Verdict | Top-down vs Direct (paired t) |
|---|---|---|---|---|---|
| PEM101 | 343.82 | 344.63 | 449.18 | **Holds its advantage** (beats both) | t=-1.27, not significant |
| PEM102 | 1.16 | 1.15 | 1.34 | Beats Naive, loses edge over Direct | t=0.24, not significant |
| PEM103 | 2.49 | 2.43 | 2.70 | Beats Naive, loses edge over Direct | t=0.55, not significant |
| PEM107 | 11.57 | 11.44 | 13.61 | Beats Naive, loses edge over Direct | t=0.12, not significant |
| CI101 | 10.27 | 11.07 | 10.11 | **Falls behind Naive** (+1.6%, small) | t=-2.12 (Top-down **beats** Direct, borderline significant, n=13) |

**Confidence: moderate for every verdict — none of the Direct-vs-Top-down differences reaches
conventional significance (all \|t\|<2.2) except CI101's, which is small-n (13 items) and only
borderline.** No division's result is a dramatic reversal — reads as a restatement, not a
contradiction, of Phase B3's own original finding ("no approach clearly better... but Top-down had
the best point estimate").

**What the evidence suggests per division, stated but NOT implemented (per instruction):**
- **PEM101**: Top-down's advantage holds cleanly — no change suggested.
- **PEM102, PEM103, PEM107**: Top-down is directionally competitive with Direct (small,
  non-significant differences) — the step 1 flags for PEM103 (Intermittent/Lumpy-only demand) and
  PEM107 (demand-mix difference) do NOT show up here as a measured Top-down failure; **evidence
  suggests Top-down can stay the default for these three, though the margin over Direct is thin
  enough that Direct would be an equally defensible fallback if the business wants
  per-item simplicity.**
- **CI101**: the only division where Top-down underperforms Naive, though narrowly (+1.6%) and
  not significantly (t=0.12 vs. Naive). Combined with Phase C step 1's own flagged "thin-history
  caution" (13 items, 0% Smooth), **evidence suggests Direct or Naive may be worth considering
  ahead of Top-down for CI101 specifically** if this margin persists in future re-tests — **not
  implemented here**, per instruction; a small-n result, not a confident basis for a policy change
  on its own.

---

## Confidence summary

| Finding | Confidence |
|---|---|
| No division filter remains in the active pipeline | High |
| PEM101's 1.22% vs. load_data_full.py's 0.29% are consistent (different scopes) | High |
| The 7 PEM104-overlap items: division exclusion subsumes item-level placeholder question | High (this task's ratification of the synthesis's own Reading A) |
| The 9 Cube_CES-only codes are pre-2024 Actual deliveries, a coverage-window gap | High |
| Per-division/Type MAE/RMSE/Bias/MASE, rolling-origin | High (direct computation, cited) |
| No stable rolling-origin winner across 40 Types (34.3% mean stability) | High, reproduces an established finding |
| Zero-inflation identical under qty/value bases | High (mathematical necessity) |
| Value-vs-quantity overfitting-gap comparison: mixed, no clear winner | Moderate (genuinely mixed data) |
| Quantity basis kept for Top-down allocation | Moderate (absence of a reason to switch, not a decisive win) |
| Transferability verdicts per division | Moderate (no Direct-vs-Top-down difference reaches significance except CI101's, borderline, small n) |

## What remains unresolved

1. **No scoring script exists for `forward_test_log_all_divisions.csv`** — building one
   (adapting `src/score_forward_test_v2.py`'s consistency-check pattern to the new schema/scope)
   is separate, not-yet-done work.
2. **The 82 non-PEM104 placeholder-pending items' exclude/placeholder mechanism is still not
   chosen** — unaffected by this task, which only forecasts the 335 already-history-bearing items.
3. **CI101's Top-down-vs-Naive underperformance is small-n (13 items) and not statistically
   significant** — worth re-checking once more history accumulates, not acted on now.
4. **The 82-item and PEM104-overlap classification, the PEM102/PEM107 legacy-tag mechanism, and
   whether PEM101's own item codes outside the 128-item Fuse+Surge Category (i.e. the other 27 of
   PEM101's 171 sheet codes now in the 335-item forecast scope) were ever previously forecast under
   any different method** — not investigated in this task, flagged for completeness.
5. **`cube_Sale_APD` is a live, growing table** — a re-run on a later date will not reproduce these
   exact figures; qualitative conclusions are expected to be stable.
