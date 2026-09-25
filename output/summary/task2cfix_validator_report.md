# Task 2cfix — Independent Validator Report

Role: Validator (AGENTS.md). Independent pass (V1 — one recomputation, not cross-checked by a
second Validator). Verified system clock via `date`: **2026-09-25, ICT (UTC+7)**, at task start
(`Fri, Sep 25, 2026 3:47:32 PM`).

Scope: verify 3 specific claims about task 2cfix (config refactor of backtest constants into
`config/config.yaml`, step-4 wiring of 4 analysis-input regenerations in `src/monthly_refresh.py`,
per-section `data_pulled_at` on `forecast/sales_report.html`/`index.html`) without reading the
implementer's own narrative/summary write-ups. Read only: production files under test
(`config/config.yaml`, `src/backtest_rekeyed.py`, `src/build_report.py`, `src/monthly_refresh.py`,
`forecast/sales_report.html`, `index.html`, CSVs in `output/summary/`, `data/inventory.json`,
`output/runs/monthly_refresh_20260925T153426.json`), plus `AGENTS.md`, `CONVENTIONS.md`,
`METRICS.md` §25/26/28/39, `DATA_MAP.md`, `PROJECT_GRAPH.md`, and grepped `STATUS.md` for the
task-2cfix section header only (not its narrative body).

No DB pull was needed for any of the 3 checks (confirmed before starting) — every check is
answerable from files already pulled to disk. Zero DB connection attempts used.

---

## Check 1 — Backtest outputs identical before and after the config refactor

**config.yaml's new `backtest:` block** (lines 1285–1308), confirmed by direct read:

    holdout_months: 6
    min_train_months: 13
    origin_step_months: 2
    train_months: 19
    val_months: 6
    test_months: 6

These match the values named in the task prompt exactly. `total_months` (31) is derived, not
stored.

**`src/backtest_rekeyed.py` genuinely reads these from config** (lines 62–94): `load_backtest_settings()`
does `b = config["backtest"]` then `b["holdout_months"]` etc. — **plain dict indexing, no `.get()`
with a fallback default**. A missing/renamed key would raise `KeyError` at import time, not
silently fall back to a hardcoded value. Module-level constants (`HOLDOUT`, `MIN_TRAIN_MONTHS`,
`ORIGIN_STEP`, `TRAIN_MONTHS`, `VAL_MONTHS`, `TEST_MONTHS`, `TOTAL_MONTHS`) are set from this
function's return value at import time (line 87–94), and `src/backtest_all_divisions.py` /
`src/transferability_all_divisions.py` both import these constants from `backtest_rekeyed`
(confirmed by grep), not from any other module. **Confirmed no silent hardcoded fallback wins.**

I did find hardcoded copies of the same-valued constants (`HOLDOUT=6`, `MIN_TRAIN_MONTHS=13`,
etc.) in `src/investigations/backtest_aggregate.py`, `rolling_origin.py`, `rule_stability_origins.py`,
`train_val_test.py` — but these are old, frozen, standalone investigation scripts under
`src/investigations/`, not imported by `backtest_all_divisions.py` / `transferability_all_divisions.py`
(confirmed by grep of their import statements) — consistent with the refactor's own comment that
these are "a deliberately separate, frozen concept, not a duplicate." **Not a fallback risk to the
live pipeline.**

**Independent re-run.** Backed up the current on-disk CSVs, then ran both scripts myself fresh:

    python src/backtest_all_divisions.py --value-col qty
    python src/transferability_all_divisions.py

`diff` against the pre-run backup showed **zero byte differences** for both
`output/summary/phaseC_step2_per_division_summary_qty.csv` and
`output/summary/phaseC_step2_transferability_per_division.csv`.

Figures for the two requested divisions (my fresh re-run; identical to what was already on disk):

| Division | Approach | MAE | RMSE | Bias | MASE |
|---|---|---|---|---|---|
| CI101 | Top-down (per-division summary) | 13.018704 | 16.764011 | 5.144554 | 0.739087 |
| CI101 | Direct | 11.080051 | 13.415542 | 3.309512 | 0.730095 |
| CI101 | Naive | 10.109890 | 13.336231 | -1.923077 | 0.581331 |
| PEM107 | Top-down (per-division summary) | 69.183464 | 80.100899 | 15.613048 | 0.720357 |
| PEM107 | Direct | 11.436124 | 14.029069 | 2.068935 | 1.087228 |
| PEM107 | Naive | 13.611182 | 17.239930 | 1.837798 | 1.162184 |

(Note: the "per-division summary" MAE for CI101/PEM107 above is the Type-level rolling-origin
Combination-forecast MAE reported by `backtest_all_divisions.py`; Direct/Naive/Top-down rows are
`transferability_all_divisions.py`'s separate item-level comparison — both scripts' full output is
in `output/summary/task2cfix_validator_backtest_rerun_diff_qty.csv`, all 5 divisions.)

**Verdict: MATCH. Confidence: V1, high** — this is a direct, independent re-execution of the
refactored code path (not a re-read of the same file), producing byte-identical output to what
was already on disk. Evidence: `output/summary/task2cfix_validator_backtest_rerun_diff_qty.csv`
(this task), `output/summary/phaseC_step2_per_division_summary_qty.csv`,
`output/summary/phaseC_step2_transferability_per_division.csv`.

**Side effect to disclose:** re-running these two scripts overwrote 3 on-disk CSVs
(`phaseC_step2_per_division_summary_qty.csv`, `phaseC_step2_transferability_per_division.csv`,
`phaseC_step2_rolling_origin_qty.csv`) with byte-identical content but **new file mtimes**
(~15:48–15:49). This is relevant to Check 2 below — see that section's caveat. These files are
git-ignored (`output/` is in `.gitignore`; confirmed via `git check-ignore -v`), so this caused no
tracked-file change (`git status --porcelain` is clean).

---

## Check 2 — Per-section `data_pulled_at` vs. underlying file's own recorded pull date

Traced `src/build_report.py`'s `gather_freshness()` (lines 303–331), which is what actually
produces every value in `forecast/sales_report.html`'s per-section table (lines 56–63).

| Section (as labelled on the page) | Page shows | Source (per `gather_freshness()`) | Independently checked value | Verdict |
|---|---|---|---|---|
| หลัก (main scope/forecast/actual) — snapshot_pull_date | 2026-09-25 11:51:56 | `output/data/processed_full_category_sales_monthly_forecastDate.csv`, column `snapshot_pull_date`, row 0 | **2026-09-25 11:51:56** (read directly, only one unique value in the column) | **MATCH** |
| ตารางผลลัพธ์ต่อฝ่าย (transferability / per-division summary) — file mtime | 2026-09-25 15:30 | `output/summary/phaseC_step2_per_division_summary_qty.csv` mtime | mtime now 2026-09-25 15:48:49 (after my Check-1 re-run); the dry run's own archived pre-copy (`..._pre_monthly_refresh_20260925T153426.csv`) is timestamped **15:34:30**, i.e. this file was already regenerated to 15:34 by the dry run itself, before I touched it | **DISCREPANCY** (see note below) |
| Rolling-origin chart — file mtime | 2026-09-25 15:30 | `phaseC_step2_rolling_origin_qty.csv` mtime | mtime now 15:48:49 (my re-run touched this file too, produced by the same script call) | **DISCREPANCY** (see note) |
| Notice-period chart — file mtime | 2026-09-25 15:30 | `leadtime_notice_buckets_overall.csv` mtime | **15:34:47** (I did not touch this file) | **DISCREPANCY** |
| โมเดลพื้นฐาน chart — file mtime | 2026-09-25 15:30 | `focus_items_test_all.csv` mtime | **15:34:43** (untouched by me) | **DISCREPANCY** |
| On-time exact — file mtime | 2026-09-25 15:30 | `delivery_by_year.csv` mtime | **15:34:51** (untouched by me) | **DISCREPANCY** |
| Not-late — file mtime | 2026-09-25 15:30 | `delivery_not_late_by_year.csv` mtime | **15:34:54** (untouched by me) | **DISCREPANCY** |

**Root cause identified (not a build_report.py bug in the timestamp *logic*, but a real staleness
problem in what the tracked page currently shows):** `forecast/sales_report.html`'s own file mtime
is **15:33:39**, and it was committed at 15:41:30 (commit `9058b26`, "Rebuild sales_report.html
from refreshed backtest/leadtime/delivery data") — built from a regeneration that ran at ~15:30
(confirmed: `output/summary/archive/phaseC_step2_per_division_summary_qty_pre_monthly_refresh_20260925T153029.csv`
exists, timestamped 15:30). The page's displayed "15:30" is an accurate report of file state
**at build time**. But `output/runs/monthly_refresh_20260925T153426.json` (the dry run this task
was also asked to check) started at 15:34:26 — **after** the page was already built — and its own
step 4 (`4_backtest`) genuinely re-executed the backtest and all 4 analysis-input regeneration
scripts for real (archiving the pre-run copies at 15:34:30, confirmed above), while step 7
(`7_rebuild_pages`) wrote the rebuilt page only to a **staged, non-tracked path**
(`"written_to_tracked_path": false` in the run log) and never touched `forecast/sales_report.html`.
**Net effect: the dry run mutated the same on-disk analysis-input files the committed page cites,
without rebuilding the committed page to match — so the committed page's per-section timestamps
went stale (by ~4–5 minutes) the moment the dry run ran, and this is a structural gap that will
recur on every future dry run or intermediate rerun, not a one-off fluke.**

Content, however, is unaffected: the dry run's own step 10 recorded 0.0% MAE change for every
division (i.e. the 15:34 regeneration produced numerically identical results to the 15:30
version), and I independently confirmed this via Check 1's byte-identical diff. So this is a
**timestamp/metadata staleness gap, not a data-correctness gap** — and at 4–5 minutes' drift it is
nowhere near METRICS §26's 7-day visible-staleness-notice threshold, so no user-facing incorrect
staleness banner results from it today. I still record it as a DISCREPANCY per the letter of what
was asked (page-displayed value vs. the file's own current timestamp), because it demonstrates the
mechanism does not stay accurate between a page's build and any later pipeline execution that
touches the same files.

**Other `data_pulled_at` instances checked (index.html):**

- **Inventory panel** (`invPageTimestampNote`, JS lines ~7922–7932): reads `data.snapshot.loaded_at`
  and `data.backlog.loaded_at` **live from `data/inventory.json` at page-render time** (not baked
  into static HTML text), so it cannot drift out of sync with that file the way the mtime-based
  sections above can. Verified the source fields directly: `snapshot.loaded_at` =
  `2026-09-24 21:40:32.730000`, `backlog.loaded_at` = `2026-09-25 10:04:52.040000` (read via
  `json.load`). The JS does `.slice(0,16)`, so it would render `2026-09-24 21:40` and
  `2026-09-25 10:04` respectively. **MATCH (by construction — dynamic binding to the file I read
  directly; I did not execute the page in a browser, but the binding is a direct, unconditional
  read of these two fields with no intermediate transformation that could introduce drift).**
- **OMNI/MATCH trend tab** (index.html ~line 7529): states `data_pulled_at: 2026-08-25`, "embedded
  in commit `62b1e81`, 2026-08-26 10:16 ICT." Verified via `git log`/`git show -s --format='%cI'
  62b1e81`: actual commit timestamp is **2026-08-26T10:16:02+07:00**. **MATCH.** This section
  correctly follows METRICS §26's exemption for external/unrefreshed data (explicitly states it is
  "not refreshed by this pipeline").
- **Price List tab**: explicitly states no exact date, external file, not refreshed by this
  pipeline — matches METRICS §26's exemption by design; not a figure to independently check.

**Verdict: MIXED.** Main section and the two index.html sections checked: **MATCH** (confidence
V1, high — direct comparison against the cited source field/commit). The 6 file-mtime sections on
`sales_report.html`: **DISCREPANCY** as measured right now, with the root cause identified as a
dry-run/rebuild-ordering gap rather than a logic error in `build_report.py`'s `_file_mtime_str()`
itself, and the underlying data confirmed unchanged in value. Confidence: V1, high on the
underlying facts (mtimes and commit timestamps directly read), medium on how the orchestrator
should classify severity (a genuinely stale display text vs. a design limitation worth fixing is a
judgement call for the human, not mine to resolve — AGENTS.md rule 9 analog).

---

## Check 3 — Step 10 change-magnitude figures in the dry run

Read `output/runs/monthly_refresh_20260925T153426.json`, step `10_change_magnitude`. Independently
recomputed both figure types from source, without needing the implementer's own numbers:

**Six-month forecast total by division** — `previous_vintage1_total` should be vintage 1 of
`output/summary/forward_test_log_all_divisions.csv`, item level, summed by division. I
recomputed this directly with pandas:

    CI101=767.8554, PEM101=735378.3168, PEM102=133.719, PEM103=1244.6052, PEM107=4873.596

— **exact match** to the run log's `previous_vintage1_total` for all 5 divisions.

`new_vintage_total` is `src/monthly_refresh.py compute_new_vintage()`'s output. This function reads
only already-pulled local files (`output/data/processed_all_divisions_monthly_qty.csv`,
the scope CSV) — **no DB connection needed** (confirmed by reading the function before running
it). I called it directly myself:

    CI101=767.9676, PEM101=735378.3168, PEM102=133.719, PEM103=1244.6052, PEM107=4873.596

— **exact match** to the run log's `new_vintage_total` for all 5 divisions.

Recomputed `change_pct` from these two independently-obtained figures:

| Division | prev (vintage 1) | new (recomputed) | change % (recomputed) | run log's change % | Passes 25% threshold? |
|---|---|---|---|---|---|
| CI101 | 767.8554 | 767.9676 | 0.014612% | 0.014612126189373173 | Yes |
| PEM101 | 735378.3168 | 735378.3168 | 0.0% | 0.0 | Yes |
| PEM102 | 133.7190 | 133.7190 | 0.0% | 0.0 | Yes |
| PEM103 | 1244.6052 | 1244.6052 | 0.0% | 0.0 | Yes |
| PEM107 | 4873.5960 | 4873.5960 | ~0.0% (1.9e-14, float noise) | 0.0 | Yes |

**Backtest MAE change** — Top-down MAE, previous vs. new, per division. The dry run's own
"previous" is the file it archived immediately before overwriting
(`output/summary/archive/phaseC_step2_per_division_summary_qty_pre_monthly_refresh_20260925T153426.csv`
/ `..._transferability_..._pre_monthly_refresh_20260925T153426.csv`, both read directly by me).
These archived "previous" values are **byte-identical** to the "new" values the dry run itself
computed (both files read and compared directly), and both are in turn identical to what Check 1's
completely independent fresh re-run reproduced. So the reported 0.0% MAE change per division is
independently reproduced through two separate paths (the archived pre-run file, and my own
from-scratch script re-run in Check 1) — not merely re-reading the implementer's own arithmetic.

| Division | previous_MAE (archived pre-run) | new_MAE (current file / my Check-1 rerun) | change % | Passes 20% threshold? |
|---|---|---|---|---|
| CI101 | 10.282871483096738 | 10.282871483096738 | 0.0% | Yes |
| PEM101 | 343.8229245692337 | 343.8229245692337 | 0.0% | Yes |
| PEM102 | 1.1560523763040642 | 1.1560523763040642 | 0.0% | Yes |
| PEM103 | 2.493430328612538 | 2.493430328612538 | 0.0% | Yes |
| PEM107 | 11.571453087242183 | 11.571453087242183 | 0.0% | Yes |

**Total on-hand stock sub-check**: the run log itself discloses this was **not independently
re-pulled** this run ("existing data/inventory.json figure carried forward unchanged; this
sub-check is not yet meaningful"). I verified this disclosure is accurate rather than glossed
over: `data/inventory.json`'s own `totals` field (`codes=445, has_stock=160, zero_stock=228,
no_db_record=57, codes_with_backlog=142, backlog_total=42121.0, available_positive=122,
available_zero=192, available_negative=74, available_unknown=57, available_total=105778.0`) is
byte-for-byte identical to the `current_totals` block the run log reports. **MATCH** on the
figures actually shown; the run log's own caveat that this sub-check is not meaningful this run is
itself accurate and should not be read as a passed stock-change test — it is explicitly not one.

**Thresholds**: verified in `config/config.yaml` (`six_month_forecast_change_pct: 25.0`,
`backtest_mae_change_pct: 20.0`, `total_on_hand_stock_change_pct: 30.0`) — match METRICS §28 and
the run log's stated thresholds exactly.

**Verdict: MATCH for every division on both figure types** (six-month forecast change, backtest
MAE change), and my own independently-recomputed figures would also pass both thresholds (25% /
20%) for every division. Confidence: V1, high — both "previous" and "new" sides of every
comparison were obtained from a source or computation independent of the implementer's own step-10
arithmetic (a genuinely different query/script, not a re-read of the same number), per
CONVENTIONS.md's rule on what counts as a second direction.

---

## Summary of 3 checks

| # | Check | Verdict | Key numbers (implementer's / my independent figure) |
|---|---|---|---|
| 1 | Backtest outputs identical pre/post config refactor | **MATCH** | CI101 Top-down MAE 13.018704 / 13.018704; PEM107 Top-down MAE 69.183464 / 69.183464 (byte-identical CSVs, all 5 divisions, both scripts) |
| 2 | Per-section `data_pulled_at` vs. underlying file | **MIXED** — main section + both index.html sections checked: MATCH (11:51:56 / 11:51:56; commit 62b1e81 2026-08-26T10:16:02+07:00 / same); 6 file-mtime sections on sales_report.html: DISCREPANCY (page shows 15:30 for all 6 / actual current mtimes 15:34:26–15:35:13 immediately after the dry run, later 15:48–15:49 after my own required Check-1 rerun) — root cause: dry run regenerates analysis-input files for real but writes the rebuilt page only to a staged/non-tracked path, so the tracked page's timestamps go stale within minutes of any dry run; content unaffected (0% change) |
| 3 | Step-10 change-magnitude figures | **MATCH** | Six-month forecast change: CI101 0.0146% / 0.0146% (others 0.0% / 0.0%), all pass 25% gate; Backtest MAE change: all 5 divisions 0.0% / 0.0%, all pass 20% gate |

**Overall**: Checks 1 and 3 are clean independent MATCHes at V1/high confidence — the config
refactor did not change backtest behavior, and the dry run's own gate-passing figures reproduce
under fully independent recomputation. Check 2 surfaces a real, previously undocumented gap: the
per-section timestamp mechanism is only as fresh as the last time the tracked page itself was
rebuilt, and any subsequent pipeline execution (including a "dry" run) that touches the same
analysis-input files — without also rebuilding and committing the page in the same pass — silently
lets the displayed dates fall behind the files' actual state. This did not cause a false "fresh"
claim beyond the 7-day notice threshold today, and did not affect any displayed figure's
correctness, but it means the specific minute-level `data_pulled_at` text on `sales_report.html`
should not be trusted at face value between rebuilds. Recommend the orchestrator decide whether
this needs a fix (e.g., step 7 always rebuilding the tracked page whenever step 4 actually wrote
new files, even in dry-run mode) or is accepted as a known limitation.
