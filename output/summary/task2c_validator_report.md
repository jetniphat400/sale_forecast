# Task 2c Validator Report

**Role:** independent Validator (AGENTS.md Validator role), V1 pass (first independent
recomputation — no prior validator pass exists yet for this task to cross-check against).

**Scope:** three independent recomputations of task 2c's claims (forward-test vintage
migration, backtest re-run, `monthly_refresh.py` dry run). Per the task brief, none of the
implementer's own narrative/investigative files were read; only production data files, the
run-log artifact under test, and pre-existing project code (`src/transferability_all_divisions.py`,
`src/backtest_rekeyed.py`, `src/leakage_guard.py`, `METRICS.md`).

Read before starting: `AGENTS.md`, `CONVENTIONS.md`, `METRICS.md` (§12-13, §25, §27, §28),
`DATA_MAP.md`/`PROJECT_GRAPH.md` (headers), `STATUS.md` (grepped for `monthly_refresh`,
`forward_test_log_all_divisions`, `vintage_id`, "task 2c").

No new database connection was needed — all three checks were answerable from existing output
files, confirmed before starting (per the task's data-access note).

All own scripts used for this report live in the scratchpad
(`task2c_validator_check1_ci101.py`, `task2c_validator_check2_vintage1.py`,
`task2c_validator_check3_gate.py`) — independent of any script the implementer wrote or ran.

---

## Check 1 — CI101 Top-down backtest MAE/RMSE/Bias/MASE, recomputed from row-level scores

**Source of raw rows:** `src/transferability_all_divisions.py` (read directly, not assumed) computes,
for every item x rolling-origin x approach, `compute_metrics(test, fc, train)` — imported unchanged
from `src/backtest_rekeyed.py` — and appends only the resulting `{MAE, RMSE, Bias, MASE}` dict; the
underlying month-by-month forecast/actual arrays for each 6-month holdout window are **not**
persisted anywhere. The finest-grain file that exists is therefore
`output/summary/phaseC_step2_transferability_item_rolling_origin.csv` (one row per item x origin x
approach, 6,980 data rows total). This is the "raw per-item, per-origin" file the division-level
`phaseC_step2_transferability_per_division.csv` aggregates from (confirmed by reading the script:
`per_division = results.groupby(["division","approach"]).agg(MAE=mean, RMSE=mean, Bias=mean,
MASE=mean, n_scored=size)`).

`src/backtest_rekeyed.py::compute_metrics` was read and confirmed to match METRICS.md formulas
exactly: `MAE=mean(|forecast-actual|)` (§25), `RMSE=sqrt(mean(errors²))` (§25), `Bias=mean(forecast-actual)`
(§12), `MASE=MAE/mean(|diff(train)|)` — i.e. MAE over in-sample seasonal-naive m=1 (§13), NaN
(never 0/∞) when the in-sample scale is 0.

**My independent recomputation** (own script, plain `csv` module + manual mean, not pandas
`.groupby().agg()`): filtered the row-level file to `division==CI101, approach=='Top-down'`
(91 rows matched), excluded 7 rows with `MASE` undefined (NaN, per METRICS §13) from the MASE
average only, and took the mean of each of MAE/RMSE/Bias/(84 valid) MASE values by hand.

| metric | recomputed (mine) | stated in `phaseC_step2_transferability_per_division.csv` | abs diff |
|---|---|---|---|
| MAE  | 10.282871483097 | 10.282871483097 | 0 |
| RMSE | 12.656487714330 | 12.656487714330 | 0 |
| Bias | 2.770144471813  | 2.770144471813  | 0 |
| MASE | 0.674942142710  | 0.674942142710  | 0 |
| n_scored | 91 | 91 | 0 |

**Result: MATCH.** Exact to machine precision — the CSV's own aggregation is a correct mean of
the row-level per-origin metrics, and those row-level metrics follow METRICS §12/§13/§25's
formulas exactly (confirmed by reading `compute_metrics` itself, not by assuming the function name
implies correctness).

**Confidence: V1 (high).** Independently coded aggregation over the full row set (not a sample);
formulas cross-checked line-by-line against METRICS.md. Caveat: this recomputation validates the
*aggregation step* (row-level metrics -> division mean), not the *forecast-generation step*
(whether `combination_forecast`/`naive_forecast` themselves are implemented correctly) — the raw
month-by-month forecast/actual arrays needed to check that further are not persisted in this
project's outputs, and re-deriving them would mean re-running the full rolling-origin pipeline
against the database, which is out of this task's scope (three specific recomputations from
existing files). This limitation is stated, not silently absorbed.

Output: `output/summary/task2c_validator_check1_ci101_topdown.csv`

---

## Check 2 — Vintage 1 rows vs. pre-migration archive, full value-for-value comparison

**Files:**
- Current: `output/summary/forward_test_log_all_divisions.csv` — 2,340 rows, 18 columns
  (17 original + `vintage_id`). `vintage_id` is 1 for all 2,340 rows (confirmed:
  `set(df['vintage_id'].unique()) == {1}`).
- Archive: `output/summary/archive/forward_test_log_all_divisions_pre_vintage_migration_2026-09-25.csv`
  — 2,340 rows, 17 columns (identical column names to current minus `vintage_id`).

**Method (own script, not the implementer's migration script):** row counts matched (2,340 =
2,340); both files were sorted independently on the same natural key (`itemcode`, `division`,
`level`, `category`, `type`, `forecast_run_date`, `data_cutoff_date`, `fit_last_month`, `model`,
`config_version`, `date_key`, `scope_hash`, `scope_n_items`, `horizon`, `target_month`) rather than
compared by raw row order, and checked for duplicate keys after sorting (0 duplicates in either
file, so key-based alignment is safe). Every one of the 17 archive columns was then compared
cell-by-cell across all 2,340 aligned rows (numeric columns: exact equality within 1e-9 absolute
tolerance, treating NaN==NaN as equal since `actual_qty` is legitimately blank for ineligible
months; non-numeric columns: exact string equality).

**Result: MATCH.** 0 differing cells across 17 columns x 2,340 rows = 39,780 cells compared.
0 rows with any difference. Column sets are identical (only `vintage_id` was added, exactly as
the task brief expected).

**Confidence: V1 (high).** Full population comparison, not a sample; own alignment/comparison
code, not a re-read of the migration script's own diff.

Output: `output/summary/task2c_validator_check2_vintage1_comparison.csv`

---

## Check 3 — Step-10 change-magnitude gate: backtest-MAE-change per division

**Run log claim** (`output/runs/monthly_refresh_20260925T141119.json`, step
`10_change_magnitude.result.backtest_mae_change_pct_by_division`, gate threshold
`thresholds.backtest_mae_change_pct = 20.0`):

| division | run log's stated MAE change % |
|---|---|
| CI101  | 0.0822490421353276 |
| PEM101 | 0.0 |
| PEM102 | 0.0 |
| PEM103 | 0.0 |
| PEM107 | 0.0 |

**My independent recomputation** (own script): merged
`output/summary/phaseC_step2_transferability_per_division.csv` (new/current) against
`output/summary/archive/phaseC_step2_transferability_per_division_pre_monthly_refresh_20260925T141119.csv`
(old, the archived pre-monthly-refresh copy the run log itself names as
`archived_previous_transferability`) on `(division, approach)`, and computed
`abs(MAE_new - MAE_old) / MAE_old * 100` for **all three** approaches per division (Direct, Naive,
Top-down) — not just Top-down — to determine, from the data, which approach the run log's figure
actually corresponds to (the run log's JSON does not itself state which approach the
"backtest MAE" gate figure uses).

| division | approach | MAE_old | MAE_new | change % (mine) |
|---|---|---|---|---|
| CI101 | Direct | 11.06625380 | 11.08005091 | 0.124677 |
| CI101 | Naive | 10.10989011 | 10.10989011 | 0.000000 |
| CI101 | **Top-down** | 10.27442087 | 10.28287148 | **0.082249** |
| PEM101/PEM102/PEM103/PEM107 | all approaches | unchanged | unchanged | 0.000000 |

**Result: MATCH, and the matching approach is confirmed to be Top-down for every division** —
my Top-down figures equal the run log's stated figures to within 1e-6 for all 5 divisions
(CI101: 0.08224904 vs 0.08224904; all others: 0.0 vs 0.0). Direct's CI101 change (0.124677%) does
**not** match the run log's figure, ruling out the alternative reading that the gate used Direct.
This resolves what the run log itself leaves ambiguous (which approach "backtest MAE" refers to)
from the data rather than by assuming.

**Gate check (METRICS §28: "a division's backtest MAE changes by more than 20%" holds the push
for human review):** every division's recomputed Top-down MAE change is <0.13%, far under the
20% threshold. **My own recomputed figures would also pass the gate** for all 5 divisions — this
matches the run log's own `10_change_magnitude.result.passed = true` and `violations = []`.

**Confidence: V1 (high).** Both source files read directly (not recalled); merge performed on
explicit `(division, approach)` keys, not positional row order; all three approaches checked to
resolve the run log's approach ambiguity rather than assuming Top-down.

**Side observation (not one of the 3 assigned checks, but visible directly in the artifact under
test and worth flagging):** the same run log's step 8 (`8_run_tests`) shows
`"passed": false, "returncode": 1` — one test, `test_embedded_json_matches_source_files_exactly`
in `tests/test_build_report.py`, failed on a **different** figure (a Category/Type-level backtest
MAE mismatch, 13.0056952135862 vs 13.018704089095952, from `phaseC_step2_per_division_summary_qty.csv`
— not the transferability file this task's 3 checks cover). This is outside this task's assigned
scope (no per-instruction file for that comparison was named), so it was not independently
re-verified here, but it is worth surfacing: the run log correctly propagates this failure into
step 11's gate (`gate_results.step8_tests_passed = false`), so a *real* (non-dry-run) execution
would correctly have been held from pushing. The gate logic itself behaved as designed in this
dry run; the underlying test failure is a separate, unresolved data-drift issue in
`phaseC_step2_per_division_summary_qty.csv` vs. the embedded report JSON that the Orchestrator
should track as an open item.

Output: `output/summary/task2c_validator_check3_mae_change_gate.csv`

---

## Summary of 3 checks

| # | Check | Result | My figure(s) | Task 2c's stated figure(s) |
|---|---|---|---|---|
| 1 | CI101 Top-down backtest MAE/RMSE/Bias/MASE, recomputed from row-level per-item/per-origin scores (91 rows, 7 MASE-undefined excluded) | **MATCH** | MAE=10.282871483097, RMSE=12.656487714330, Bias=2.770144471813, MASE=0.674942142710 | MAE=10.282871483097, RMSE=12.656487714330, Bias=2.770144471813, MASE=0.674942142710 (`phaseC_step2_transferability_per_division.csv`) |
| 2 | Vintage 1 rows vs. pre-migration archive, full value-for-value, all 17 shared columns, 2,340 rows | **MATCH** | 0 differing cells / 39,780 compared | 0 differing cells (implied by "only `vintage_id` added") |
| 3 | Step-10 backtest-MAE-change-per-division gate figures (Top-down, all 5 divisions) | **MATCH** | CI101=0.082249%, PEM101/102/103/107=0.0% — all pass the 20% gate | CI101=0.0822490421353276%, PEM101/102/103/107=0.0% (`output/runs/monthly_refresh_20260925T141119.json` step 10) — gate `passed=true` |

No contradictions found between task 2c's stated figures and this independent V1 recomputation
across any of the three checks. One unrelated, already-visible test failure (step 8, a different
metric file) is flagged above as an open item for the Orchestrator, not resolved here (out of this
task's scope).
