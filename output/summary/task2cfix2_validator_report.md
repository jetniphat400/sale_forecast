# Task 2cfix2 -- Independent Validator report

**Role**: independent Validator (AGENTS.md Validator role). This pass is V1 (this Validator's own
single independent pass; not yet cross-checked by a second Validator). Per this task's own
instruction, none of the implementing agent's narrative/investigative files were read -- only
production code (`src/monthly_refresh.py`, `src/db.py`, `src/build_report.py`), production data
files under `output/`, the implementer's own machine-generated run-log JSON files (not narrative
text), and pre-existing project docs (`AGENTS.md`, `CONVENTIONS.md`, `METRICS.md`, `DATA_MAP.md`,
`PROJECT_GRAPH.md`, `STATUS.md`).

Date/time confirmed via `date` at task start: **2026-09-25, Thailand local time (ICT, UTC+7)**.

No customer names, contract IDs or employee names appear anywhere below.

---

## Check 1 -- system32 dry run

**Python executable confirmed independently** (`python -c "import sys; print(sys.executable)"`,
run from the project folder): `C:\Users\jetniphat.boo\AppData\Local\Programs\Python\Python312\python.exe`
-- matches the path task 2cfix2 itself recorded.

**Command run, exactly the scheduled-task form, from `C:\Windows\system32`:**
```
C:\Users\jetniphat.boo\AppData\Local\Programs\Python\Python312\python.exe D:\sale_forecast\src\monthly_refresh.py --dry-run
```

**Result: every step `ok`, every gate (8, 9, 10) passed.** Own run log:
`output/runs/monthly_refresh_20260925T163507.json` (run_id `20260925T163507`, exit code 0).

- Steps 1-11: all `status: "ok"`.
- Step 1 (pull data): DB reachable, GitHub reachable, 335 items / 5 divisions pulled, 10,385 rows,
  no negative values, no duplicate item-month rows, all items matched to scope, every item has an
  equal 31-month count.
- Step 5 (new vintage guard): **`skipped: true`**, cites `existing_vintage_id_this_month: 1`,
  `existing_forecast_run_date_this_month: "2026-09-07"` -- the guard correctly fired against the
  REAL tracked log (read-only; dry-run never writes).
- Step 8 (tests): `141 passed in 17.38s`.
- Step 9 (sensitive-content scan): `n_changed_files_scanned: 0`, `findings: []`, `passed: true`.
- Step 10 (change magnitude): `violations: []`, `passed: true`; `backtest_mae_change_pct_by_division`
  all `0.0` (CI101/PEM101/PEM102/PEM103/PEM107).
- Step 11: `pushed: false` (dry-run, as designed), `would_push_if_real_run: true`, all three gate
  results `true`.
- `git status --porcelain` confirmed clean (no output) after this run.
- Forward-test log hash unchanged: `sha256sum output/summary/forward_test_log_all_divisions.csv`
  -> `7ba4a3a45a975e04a52935d62036995e1c02db93d52fc9c24e8028d3182dfa2c` -- **identical** to the
  value already recorded in STATUS.md/DATA_MAP.md for task 2cfix2's own runs, both before and
  after my own check 1 and check 2 work below.

**Comparison against task 2cfix2's own recorded system32 run** -- read directly from that run's own
machine-generated log file still present on disk, `output/runs/monthly_refresh_20260925T162451.json`
(a production artifact, not the implementer's narrative writeup; this is the one DB-touching
artifact check 1 is allowed to read for comparison):

| Figure | My run (`20260925T163507`) | Implementer's system32 run (`20260925T162451`) | MATCH/DISCREPANCY |
|---|---|---|---|
| All 11 steps `ok` | yes | yes | MATCH |
| Step 8 test count | 141 passed | 141 passed | MATCH |
| Step 9 findings | 0, passed | 0, passed | MATCH |
| Step 10 violations | 0, passed | 0, passed | MATCH |
| Step 10 `backtest_mae_change_pct_by_division` | all 0.0% (5 divisions) | all 0.0% (5 divisions) | MATCH |
| Step 11 `would_push_if_real_run` | true | true | MATCH |
| Step 5 vintage guard | skipped (vintage 1, 2026-09-07) | skipped (vintage 1, 2026-09-07) | MATCH |

**Note on raw backtest MAE (not a discrepancy):** my own fresh DB pull's raw per-division MAE
values (e.g. CI101 new_MAE=10.28, PEM107 new_MAE=11.57 in step 4's `per_division_comparison_topdown`)
differ in absolute terms from task 2cfix's own earlier-recorded raw Top-down MAE figures
(CI101 13.02, PEM107 69.18, STATUS.md Section 12) -- **this is expected, not a discrepancy**: those
are two different live pulls taken at different points in time (data changes between pulls), and
CONVENTIONS.md's "compare only like with like" rule means the load-bearing comparison for the
change-magnitude gate is the **percentage change against each run's own immediately-preceding
run**, which is what step 10 actually reports -- and that figure (0.0% for every division, both my
run and the implementer's own system32 run) matches exactly.

CSV backing this section: `output/summary/task2cfix2_validator_check1_gate_results.csv`,
`output/summary/task2cfix2_validator_check1_key_figures.csv`.

**Confidence: V1** (my own independent execution and direct read of both run logs' raw JSON).

---

## Check 2 -- one-vintage-per-month guard, tested against a copy only

**Never touched the real tracked files.** Copied `output/summary/forward_test_log_all_divisions.csv`
and `output/summary/forward_test_log_all_divisions_metadata.json` to a throwaway temp directory
(`D:\_task2cfix2_validator_tmp\...`, outside the repo, deleted after the test). Wrote my own
independent driver script (not the implementer's `tests/test_monthly_refresh.py`) that:
1. Confirmed the copy's existing vintage (`vintage_id=1`, `forecast_run_date=2026-09-07`) falls in
   the current calendar month (2026-09), so the block test is a genuine same-month scenario.
2. Temporarily monkeypatched `monthly_refresh.FORWARD_TEST_LOG_PATH` /
   `FORWARD_TEST_METADATA_PATH` (module-level constants -- `step5_new_vintage()`/
   `compute_new_vintage()` do not accept a path parameter, so this is the only way to exercise the
   real write path against a copy rather than the real file) to point at the copy, restoring the
   originals in a `finally` block regardless of outcome.
3. Called the actual production functions `step5_new_vintage(dry_run=False, force_new_vintage=...)`
   against the redirected (copy) paths.
4. Hashed the real files (SHA-256) before and after the entire test.

**Result (a) -- normal call, no force: BLOCKED.** `step5_new_vintage(dry_run=False,
force_new_vintage=False)` returned `skipped: true, written: false`, citing
`existing_vintage_id_this_month=1, existing_forecast_run_date_this_month="2026-09-07"`. The copy's
file hash was **byte-identical before and after** (confirmed by direct SHA-256 comparison).

**Result (b) -- forced override: a new vintage IS computed and written, to the COPY only.**
`step5_new_vintage(dry_run=False, force_new_vintage=True)` returned `skipped: false, written: true,
force_override_used: true, vintage_id: 2, overridden_existing_vintage_id: 1`. The copy's row count
grew from 2,341 to 4,681 lines and its hash changed; the copy's metadata JSON gained key `"2"`
alongside the pre-existing `"1"`.

**Isolation confirmed.** After the entire test (both (a) and (b)), the REAL tracked files' SHA-256
hashes were re-checked and are **identical to their values before the test started**:
`forward_test_log_all_divisions.csv` = `7ba4a3a45a975e04a52935d62036995e1c02db93d52fc9c24e8028d3182dfa2c`,
`forward_test_log_all_divisions_metadata.json` = `82129fc1ea43c5b9d56e98f5d8fb21e6ce91ef4bccee67e4253b51335aa114c1`.
`git status --porcelain` also confirmed clean after this check. The temp copy and driver script
were deleted after the test; nothing from this check was left on disk inside the repo.

**Comparison against DATA_MAP.md's task 2cfix2 entry:** DATA_MAP.md claims the guard blocks a
same-month append (citing vintage 1, `forecast_run_date=2026-09-07`, against the real log,
read-only) and that `--force-new-vintage` overrides it -- both behaviours independently
reproduced here, against a copy, with a real write for the override path. **MATCH.**

**Confidence: V1** (independent recomputation, own driver script, own copy, own hash
verification -- not a re-read of the implementer's own test file or report).

---

## Check 3 -- no displayed date comes from a file modification time

**(a) Static check of `src/build_report.py` (read end-to-end, all 1,007 lines).**
`grep -n "getmtime\|os.stat\|st_mtime\|_file_mtime_str" src/build_report.py` returns exactly one
hit -- inside a docstring/comment (`_source_pull_date()`'s own docstring, line 279) *describing*
the historical bug it fixed, not a call. **No function in the file, including the freshness-table
rendering path (`gather_freshness()` / `_source_pull_date()` / `render_page()`), calls
`os.path.getmtime` or any equivalent file-mtime API.** MATCH with DATA_MAP.md's claim.

**(b) The exact file list, taken from the code itself, not copied from the brief.**
`gather_freshness()` (lines 318-346) calls `_source_pull_date()` on exactly **6** files:
`phaseC_step2_per_division_summary_qty.csv`, `phaseC_step2_rolling_origin_qty.csv`,
`leadtime_notice_buckets_overall.csv`, `focus_items_test_all.csv`, `delivery_by_year.csv`,
`delivery_not_late_by_year.csv`. **Note**: this orchestrator brief's list of 7 files also named
`phaseC_step2_transferability_per_division.csv` -- checked directly in the code and confirmed that
file is **not** one of the 6 `gather_freshness()` pull-time sections (it feeds a different part of
the page, `gather_primary_results()`/`gather_backtest_window()`, which states its own
`first_test_month`/`last_test_month` window, not a `data_pulled_at`). DATA_MAP.md's own task
2cfix2 entry lists the same 6 files as the code, not 7 -- so this is the brief overcounting by one,
not a project-doc discrepancy.

All 6 files independently confirmed (direct `pandas.read_csv`, this task) to carry a real, non-null
`snapshot_pull_date` value:

| file | has `snapshot_pull_date` | value read directly from file |
|---|---|---|
| phaseC_step2_per_division_summary_qty.csv | True | 2026-09-25 16:35:11 |
| phaseC_step2_rolling_origin_qty.csv | True | 2026-09-25 16:35:11 |
| leadtime_notice_buckets_overall.csv | True | 2026-09-25 16:35:28 |
| focus_items_test_all.csv | True | 2026-09-25 16:35:11 |
| delivery_by_year.csv | True | 2026-09-25 16:35:32 |
| delivery_not_late_by_year.csv | True | 2026-09-25 16:35:32 |

(These are the timestamps from my own Check 1 dry run's live pull, since that run regenerated all
6 files minutes before this check.) **MATCH** -- all 6 genuinely carry the column with a real value.

**(c) Built the report fresh, to my OWN output path** (`build_report.build_report(output_path=...)`
-- the function supports an explicit override, confirmed by reading its signature/docstring, so
the tracked `forecast/sales_report.html` was never touched by this check). Parsed the rendered
freshness table out of the resulting HTML and compared each section's displayed
`data_pulled_at` against the source file's own recorded value:

| section (file) | file's own `snapshot_pull_date` | rendered in report | MATCH/DISCREPANCY |
|---|---|---|---|
| phaseC_step2_per_division_summary_qty.csv / transferability | 16:35:11 | 16:35 | MATCH |
| phaseC_step2_rolling_origin_qty.csv | 16:35:11 | 16:35 | MATCH |
| leadtime_notice_buckets_overall.csv | 16:35:28 | 16:35 | MATCH |
| focus_items_test_all.csv | 16:35:11 | 16:35 | MATCH |
| delivery_by_year.csv | 16:35:32 | 16:35 | MATCH |
| delivery_not_late_by_year.csv | 16:35:32 | 16:35 | MATCH |

(Rendered to the minute, per `_source_pull_date()`'s own `strftime("%Y-%m-%d %H:%M")` formatting --
consistent with every file's own recorded second-level value truncated to the minute.) The
report's own build happened at 16:39 (four minutes after the files were regenerated at ~16:35);
the freshness table still shows 16:35 throughout, i.e. the files' pull time, not the later build
time -- consistent with reading a recorded column rather than any live clock or file-write
timestamp at render time.

CSV backing this section: `output/summary/task2cfix2_validator_check3_freshness_comparison.csv`.

**Flag, as instructed either way:** this check wrote its own fresh render to a temp path
(`D:\_task2cfix2_validator_tmp\sales_report_validator_check.html`, deleted after inspection) --
`build_report()` does support an `output_path` override, so the tracked
`forecast/sales_report.html` was **not** touched by this check; `git status --porcelain` confirmed
clean throughout.

**Confidence: V1** (own static grep of the full file, own direct file reads, own independent
report build to an isolated path).

---

## Summary of 3 checks

| # | Check | Result | My figure | Recorded figure (task 2cfix2, STATUS.md/DATA_MAP.md) |
|---|---|---|---|---|
| 1 | system32 dry run passes every gate | **MATCH** | steps 1-11 all `ok`; 141 tests passed; 0 sensitive-content findings; 0 change-magnitude violations (all divisions 0.0% MAE change); vintage guard correctly skipped (vintage 1, 2026-09-07) | steps 1-11 all `ok`; 141/141 tests; sensitive-content scan passed; change-magnitude gate passed, 0 violations, `backtest_mae_change_pct_by_division` all 0.0% |
| 2 | one-vintage-per-month guard blocks/overrides correctly, tested on a copy only | **MATCH** | (a) blocked, copy byte-identical before/after; (b) forced override computed vintage_id=2 and wrote it to the copy only; real tracked log/metadata hashes unchanged (`7ba4a3a4...82fa2c`, `82129fc1...14c1`) | guard blocks a same-month append (vintage 1, 2026-09-07) unless `--force-new-vintage`; demonstrated read-only against the real log in the implementer's own proof runs |
| 3 | no displayed date comes from a file mtime | **MATCH** | no `os.path.getmtime`/equivalent call anywhere in `src/build_report.py`; all 6 actual `gather_freshness()` source files carry a real `snapshot_pull_date`; a fresh, isolated report build shows each section's date matching its file's own recorded pull time (to the minute) | `_file_mtime_str()`/`os.path.getmtime` removed entirely; all 6 files now carry `snapshot_pull_date`; a fresh dry run confirmed all 6 files carry the column and 141 tests passed |

**All 3 checks: MATCH, no discrepancies found.** One clarification recorded above (not a
discrepancy): the orchestrator's brief-supplied 7-file list for check 3(b) included
`phaseC_step2_transferability_per_division.csv`, which the code itself confirms is not one of the
6 `gather_freshness()` pull-time sections -- the correct list (6 files) matches DATA_MAP.md's own
task 2cfix2 entry exactly.

No customer names, contract IDs or employee names appear in this report or its CSVs. Nothing was
committed, pushed, or left modified in the tracked repository; `git status --porcelain` was
confirmed clean at the end of every check.
