# Phase B, B1 — Re-key the demand series and re-run every backtest

Single Modeler task (per `AGENTS.md`: needs all three aggregation levels in one view, each step
depends on the previous — not split). Scripts: `src/load_data.py`, `src/load_data_full.py`
(modified), `src/backtest_rekeyed.py` (new). No model choice written to `config.yaml`.

## What changed in the pipeline

- `load_data.py` and `load_data_full.py` now pull `forecast_date` alongside `createDate`, validate
  it (null/negative-interval rows excluded from the forecast_date-keyed series only, epoch/future
  anomaly re-checked on every fresh pull — 0 found, confirming Phase A's finding still holds),
  and build **both** monthly series: `processed_..._createDate.csv` and
  `processed_..._forecastDate.csv`. The original unsuffixed filename is written as an **exact
  alias of the createDate-keyed series** — every existing script that reads it keeps working
  unmodified. Nothing was deleted.
- `forecast_date` is frozen at pull time: a `snapshot_pull_date` column (this run:
  2026-09-02 15:52:39) is written into the output. It is not re-queried live on later reads.
- Both keyings are restricted to the **identical 31-month window** (2024-01 to 2026-07) that
  every existing backtest result in `output/summary/` was computed on — confirmed HIGH: 32
  complete months were actually available on this run (real time has advanced since the original
  pull), but the window was deliberately fixed at 31 to keep this an apples-to-apples comparison,
  not a silently-shifted one. The newly-available month is excluded and stated explicitly, not
  absorbed.

## Re-keying magnitude (confirmed, HIGH confidence — direct recomputation)

Within the fixed 31-month window: createDate in-window qty = 3,239,577; forecast_date in-window
qty = 3,157,956 (**-2.52%**). 129,387 units of createDate-keyed demand and 210,961 units of
forecast_date-keyed demand fall outside this window (the latter is real future-dated demand
Phase A already flagged as "invisible" to a createDate-keyed model). These figures are close to
but not identical to Phase A's (-2.17%/2.15%) because this is a **fresh pull** on a slightly
later date, from a live database — stated explicitly, not a methodology discrepancy.

**Validation re-confirmed passing** (CONVENTIONS.md): 0 negative qty in either keyed series; 113
of 128 scope items present with a row; every item has exactly 31 months (min=max=31) in both
keyings; monthly totals reconcile exactly to their own filtered daily source (checked inside
`aggregate_monthly`, raises loudly otherwise — did not raise).

## Backtest re-run: what changed, what didn't

**Cross-check (validates this re-run before trusting it, HIGH confidence)**: this run's freshly
recomputed createDate-keyed Combination test-set MAE/RMSE/Bias/MASE match the existing
`rule_part4_test_results_per_series.csv` (from `evaluate_strategies.py`, an earlier task)
**exactly**, to the decimal, at all 3 levels. This confirms the new pipeline reproduces the
established methodology precisely — any difference found below is attributable only to the
re-keying, not to script drift.

**Train/val/test (test-set, the number that matters for accuracy claims) — mostly IMPROVES under
forecast_date-keying, HIGH confidence in the numbers:**

| Level | Model | MAE createDate | MAE forecastDate | Change |
|---|---|---|---|---|
| Category | Combination | 14,606.4 | 14,143.4 | -3.2% |
| Type | Combination | 4,010.8 | 3,808.4 | -5.0% |
| Item | Combination | 389.4 | 353.2 | **-9.3%** |

Every base model except **Naive** improves at every level (MA6/MA12/Croston/SBA/MA3 all show
double-digit MAE reductions at Category/Type). **Naive gets dramatically WORSE**
(Category: 15,334→28,498 MAE, Item: 437.6→566.1) — it repeats the last observed value, and
forecast_date-keying evidently changes what that last value looks like at the train/val
boundary in a way that hurts a no-model baseline specifically.

**Rolling-origin (7 origins spanning the whole series) — the OPPOSITE direction, WORSENS under
forecast_date-keying, HIGH confidence in the numbers, and this is a genuine, unresolved
tension, not glossed over:**

| Level | Model | MAE createDate | MAE forecastDate | Change |
|---|---|---|---|---|
| Category | Combination | 14,392.3 | 18,601.9 | **+29.3%** |
| Type | Combination | 3,946.8 | 4,974.1 | **+26.0%** |
| Item | Combination | 391.4 | 432.2 | **+10.4%** |

**21 of 21 level/model cells show a material change in BOTH evaluation methodologies — but in
OPPOSITE directions.** Stated plainly, per instruction: **re-keying does not have a single,
clean "better" or "worse" answer for forecast accuracy — it depends on which evaluation window
is used.** The single train/val/test split (the last 6 of 31 months) improves; averaging across
7 rolling origins spanning the whole series worsens. **Moderate confidence in why**: the
train/val/test test period sits at the very end of the series, closest to where the
"invisible future demand" effect (Phase A) concentrates and where forecast_date's smoother
delivery-scheduling behaviour may dominate; earlier rolling-origin windows sit mid-series, where
reallocating demand across months can introduce volatility that wasn't there under
createDate-keying. **This mechanism is not proven here — it is a plausible reading of the
pattern, flagged for further investigation, not a demonstrated cause.**

**Bias**: Combination's bias gets slightly MORE negative (more under-forecasting) under
forecast_date at every level in train/val/test (Category -12,138.8→-13,946.4, Type
-3,045.1→-3,496.2, Item -216.1→-249.0) — a **-13% to -15% worsening in bias despite MAE
improving**. This is picked up directly by task B2 below.

**Validation-to-test gap**: createDate's gap is small (Category +3.8%, Type +4.2%, Item -0.9%).
forecast_date's gap is **large and negative** (Category -30.5%, Type -27.7%, Item -19.9%) — test
MAE is much better than validation MAE predicted. Reported plainly; not investigated further here
(a Modeler follow-up item, see Unresolved).

## Does any earlier conclusion no longer hold?

- **STATUS.md's Phase 2 selection of Combination forecasting is NOT overturned** — Combination
  remains competitive (never the worst model) under both keyings and both evaluation methods.
- **STATUS.md's item-level instability finding (74% no stable rolling-origin winner, 127%
  val-to-test gap) is NOT retested for stability here** (out of this task's scope — B1 asked for
  re-running the backtest, not re-running the stability analysis) — flagged as not done.
- **The magnitude of every MAE/Bias figure in every existing item-level and aggregate-level
  backtest output (rule_part4_*, part4_*, combo_variant_*) is now understood to have been
  computed on the wrong date key** — per the STATUS.md action item already recorded, these should
  be treated as superseded once forecast_date-keyed results are adopted, not as final.
- **No contradiction found with any STATUS.md claim** — this is a refinement (re-keying changes
  magnitudes, sometimes direction, but does not overturn which model family wins or reverse the
  fundamental under-forecasting-bias finding).

## Focus items (Combination, test set)

| Item | createDate MAE | forecastDate MAE | createDate Bias | forecastDate Bias |
|---|---|---|---|---|
| EEE-F-FC-1040010002 | 1970.8 | 1206.1 | -1970.8 | -1206.1 |
| HS-F-99-02110 | 611.6 | 503.8 | -562.9 | -496.9 |
| HS-F-99-0213 | 272.5 | 228.5 | -222.7 | -180.5 |

All three focus items improve under forecast_date-keying on both MAE and |Bias| — consistent
with the general item-level improvement pattern in train/val/test.

## Confidence levels

- Re-keying implemented correctly, snapshot recorded, createDate kept alongside: **HIGH**
  (direct code read + successful run).
- Re-keying magnitude (-2.52% qty in-window): **HIGH** (direct recomputation).
- Pipeline validation still passes: **HIGH** (explicit checks re-run, none failed).
- Train/val/test improves under forecast_date, rolling-origin worsens: **HIGH** in the numbers,
  **MODERATE** in the proposed explanation (window position / demand-smoothing hypothesis, not
  proven).
- Cross-check against existing createDate results: **HIGH** (exact match).

## Unresolved

- **Why rolling-origin and train/val/test disagree in direction** — a plausible mechanism is
  offered, not proven. Would need per-origin decomposition of which months' reallocation drives
  the divergence.
- **The validation-to-test gap explosion under forecast_date** (-20% to -31%) — not investigated;
  could relate to the same window-position effect above.
- **Item-level rolling-origin stability (the 74%-unstable finding) was not re-tested on
  forecast_date** — out of this task's scope, flagged for a future task.
