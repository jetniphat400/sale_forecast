# Task 2a — Independent Validator Report

**Role**: Validator (AGENTS.md). Independent recomputation only — no implementer scripts, reports,
or reasoning were read for this task, per the task's own instruction. All artifacts under test
(`index.html`, `forecast/sales_report.html`, `forecast/inventory.html`, `data/inventory.json`,
`output/summary/phaseC_step2_transferability_per_division.csv`) were read directly, as instructed.

**Date of this check**: 2026-09-25 (`Get-Date`/`date`, this session).

**Data access**: one connection session (Python, `src/db.py`, one process) bundling 3 queries
(Cube_Inventory_Exact for the 445-code scope; Cube_CES Status='Backlog' for the same scope;
Cube_CES for the 128-item PEM101 pilot scope, 2023+). Login succeeded on the first attempt, no
retries. **One additional, small follow-up query was run** (same session type, same login) to
pull `BacklogQty` for the Cube_CES backlog rows — omitted from the first pull by my own oversight.
This is disclosed explicitly as a deviation from a single query batch (see Check 1e below for why
it was necessary); it was not a retry after a failure, and no further queries were run after it
resolved the check.

**Privacy**: no customer names, contract IDs, or employee names appear below or in the CSVs
written for this report (ContractID values were used only in-memory for dedup logic, never
written to any output file).

---

## Check 1: Stock panel (total on-hand, sellable/staging/elsewhere, Reserved)

**Scope**: all 445 codes in `data/inventory.json` (read directly — confirmed 445 entries).
**Division attached from the pricelist**, independently, per CONVENTIONS.md's rule (never the
DB's own division column): I built my own itemcode→division map directly from
`reference/pricelist.xlsx`, reading each of the 6 visible sheets named in `config/config.yaml`'s
`sheet_to_division` (header row 3, `Product Code` / `Business` columns). Result: 445 distinct
codes mapped, 0 mismatches against each sheet's own `Business` column, and **0 mismatches, 0
missing codes** against `data/inventory.json`'s own `business` field for all 445 items — the
artifact's division attachment is independently confirmed correct (**V2**: two independent
derivations — my fresh pricelist read vs. the artifact's own field — agree exactly).

**Sellable warehouse codes, verified against the live `config/config.yaml`** (not just trusted from
the task prompt): `sellable_warehouse_codes` block confirms exactly — PEM101: `FG01, FG21, WH21`;
PEM103: `FG23`; PEM107: `FG27, WH22, WH24, FG22, FG01`. Staging codes confirmed as `QA, FMTS, FMTO`
(`config.yaml` `staging_warehouse_codes`/`warehouse_roles`, and independently matches
`data/inventory.json`'s own `staging_warehouse_codes` field).

**One data-shape trap caught and corrected in my own script**: `Cube_Inventory_Exact.warehouse` is
a fixed-width column — `QA` comes back as `'QA  '` (2 trailing spaces) from the live DB, while
4-letter codes (`FG01`, `FMTS`, etc.) are unaffected. My first pass excluded QA's stock from
"staging" because of this un-stripped whitespace (a bug in my own recomputation, not the
artifact). After stripping whitespace on the warehouse column, every figure below matches exactly.
This is flagged because it is exactly the kind of column-shape trap CONVENTIONS.md warns about —
recorded here for future reference, not attributed to the implementer.

### Results (fresh DB query vs. `data/inventory.json` / index.html)

| Metric | Validator (fresh DB pull) | Artifact (`data/inventory.json`) | Verdict |
|---|---|---|---|
| Total on-hand (445 codes, all warehouses) | 147,899.0 | 147,899.0 (`totals`, sum of item `qty`) | **MATCH** |
| PEM101 on-hand total | 147,014.0 | 147,014.0 | MATCH |
| PEM101 sellable | 141,323.0 | 141,323.0 | **MATCH** |
| PEM101 staging (QA/FMTS/FMTO) | 5,671.0 | 5,671.0 | **MATCH** |
| PEM101 elsewhere | 20.0 | 20.0 | **MATCH** |
| PEM103 on-hand total | 43.0 | 43.0 | MATCH |
| PEM103 sellable / staging / elsewhere | 43.0 / 0.0 / 0.0 | 43.0 / 0.0 / 0.0 | **MATCH** |
| PEM107 on-hand total | 790.0 | 790.0 | MATCH |
| PEM107 sellable / staging / elsewhere | 720.0 / 70.0 / 0.0 | 720.0 / 70.0 / 0.0 | **MATCH** |
| CI101 on-hand (unsplit, no sellable list configured) | 47.0 | 47.0 | MATCH |
| PEM102 on-hand (unsplit) | 4.0 | 4.0 | MATCH |
| PEM104 on-hand (unsplit) | 1.0 | 1.0 | MATCH |
| Items with 0 DB rows (`no_db_record`) | 57 (445 − 388 distinct itemcodes returned) | 57 | MATCH |
| Items with nonzero stock (`has_stock`) | 160 | 160 | MATCH |
| Items with DB rows but zero stock (`zero_stock`) | 228 | 228 | MATCH |

**Check 1e — Reserved (Cube_CES, Status='Backlog', deduplicated on (ContractID, ItemCode))**:

My first pass summed only `ActualQty` (as the task prompt literally specified) and got **1,342.0**
— a ~31x mismatch against the artifact's 42,121.0. Before reporting this as a discrepancy, I
checked the project's own **pre-existing** convention for this exact table/status (not the
implementer's task-2a work): `src/investigations/phaseE1fix_part0_backlog_source.py` (predates
task 2a) computes Cube_CES Backlog-row quantity as `ActualQty.fillna(0) + BacklogQty.fillna(0)` —
consistent with `delivery_performance.py`'s identical pattern for CES quantity. For `Status='Backlog'`
rows, `ActualQty` is populated for only 7 of 142 distinct item codes (mostly 0) — the real
outstanding quantity lives in `BacklogQty`. I re-pulled `BacklogQty` (the one extra query, disclosed
above) and recomputed:

- Raw rows: 650 (**MATCH** to `data/inventory.json`'s own `backlog.raw_rows_before_dedup: 650`)
- After dedup on (ContractID, ItemCode): 633 row-pairs, 142 distinct item codes (**MATCH** to
  `totals.codes_with_backlog: 142` and `backlog.rows_used: 142`)
- Sum of `ActualQty + BacklogQty` after dedup: **42,121.0** — **exact MATCH** to
  `data/inventory.json`'s `totals.backlog_total: 42121.0` and
  `backlog.reserved_change_report.new_total_cube_ces_backlog: 42121.0`.

**Conclusion for Check 1e**: MATCH, but only once the established `ActualQty+BacklogQty` quantity
convention is used — the task prompt's literal "sum ActualQty" instruction does not reproduce the
displayed figure and would have been a false-positive discrepancy. Reporting both numbers per
AGENTS.md rule 4 (contradictions stated explicitly): sum of `ActualQty` alone = 1,342.0 (does not
match anything meaningful); sum of `ActualQty+BacklogQty` after dedup = 42,121.0 (matches the
artifact exactly).

**data_pulled_at cross-check (folds into Check 4 too)**: `Cube_Inventory_Exact`'s own `timestamp`
column for these 445 codes ranges 2026-09-24 21:40:32.730 to 21:41:49.573 — **the minimum exactly
equals** `data/inventory.json`'s `snapshot.loaded_at: "2026-09-24 21:40:32.730000"`. `Cube_CES`
backlog rows' own `Timestamp` column ranges 2026-09-25 10:04:52.040 to 10:06:32.017 — **the minimum
exactly equals** `backlog.loaded_at: "2026-09-25 10:04:52.040000"`. Both independently confirmed
against the live DB's own timestamp columns, not just re-reading the JSON file.

**Confidence: V2** for every figure in the table above (independent recomputation, from a fresh
DB pull, of both the artifact's stated totals and the live DB's own timestamp columns — not a
re-read of the same query). **V1** for the pricelist-derived division map matching the artifact's
`business` field (one independent derivation this session, matched against one artifact field).

---

## Check 2: Sales report `not_late` per year (2023-2026), PEM101 128-item pilot, unit-weighted

**Scope verified independently**: `src/investigations/delivery_performance.py` (pre-existing,
read as permitted) defines the 128-item on_time_exact scope as `ManuDivision='PEM101'`,
`RevenueType='Omni Channel'`, `Status IN ('Actual','Backlog')`, `CtrDate >= '2023-01-01'`, items
from `output/summary/part1_category_scope_all_codes.csv` (128 rows, confirmed by reading the file).
I also confirmed the scope match indirectly: `output/summary/delivery_by_year.csv` (128-item scope,
pre-existing) and `output/summary/delivery_not_late_by_year.csv` (the file the page cites) carry
**identical row counts `n` per year for 2023/2024** — confirming both are the same underlying
scope before I ran my own query.

**Method**: assessable = `Status='Actual'` AND `ActualDelDate` not null; `not_late` =
`ActualDelDate <= ForecastDelDate`; unit-weighted by `ActualQty`; grouped by `CtrDate`'s calendar
year (matches the grouping `delivery_performance.py` already uses for its own by-year breakdown).

### Results

| Year | n (page, pulled ~11:57) | n (validator, fresh pull) | not_late % unit-wtd (page) | not_late % unit-wtd (validator) | Verdict |
|---|---|---|---|---|---|
| 2023 | 8,845 | 8,845 | 55.436087 | 55.436087 | **MATCH (exact)** |
| 2024 | 9,509 | 9,509 | 97.299142 | 97.299142 | **MATCH (exact)** |
| 2025 | 10,190 | 10,194 | 98.888626 | 98.888650 | **DISCREPANCY (small)** — +4 rows, +28 qty |
| 2026 | 7,403 | 8,336 | 98.254706 | 98.291130 | **DISCREPANCY (larger)** — +933 rows, +124,385 qty |

Full detail: `output/summary/task2a_validator_not_late_comparison.csv`.

**Interpretation, stated as inference not fact**: 2023 and 2024 match to full displayed precision,
which proves the filters, dedup/assessability rule, and weighting are reproduced identically. The
2025/2026 gaps grow with recency (tiny for 2025, large for 2026, the current year) and only ever
**add** rows/qty, never remove any — consistent with new Omni-Channel PEM101 contracts being
entered into the live system between the page's own pull (`delivery_not_late_by_year.csv` file
mtime 2026-09-25 11:57) and my query (run later the same day), not a computation error. I cannot
prove this from the two aggregate snapshots alone (I did not do a row-level diff, since the page's
underlying row-level pull was not saved for this task) — **this is my inference (H), not a
confirmed fact**; the alternative (a genuine scope/logic difference) cannot be fully ruled out from
the aggregates alone, though it is weighed against by the two exact-matching years.

**Confidence: V1** for my own recomputation (one independent pass, this session) — reported as a
DISCREPANCY for 2025/2026 per the task's instruction to report exactly what was found, with the
above interpretation flagged as inference, not fact.

---

## Check 3: Primary results table (PEM107 row) vs. `phaseC_step2_transferability_per_division.csv`

Read `output/summary/phaseC_step2_transferability_per_division.csv` directly and took the PEM107,
`approach=='Top-down'` row: **MAE=11.571453087242183, RMSE=14.14489231409701,
Bias=1.6852751985457102, MASE=0.9940402816237874, n_scored=779**.

Read the embedded `REPORT_DATA.primary_results` JSON blob inside `forecast/sales_report.html` for
the PEM107 entry: **MAE=11.571453087242183, RMSE=14.14489231409701, Bias=1.6852751985457102,
MASE=0.9940402816237874, n_scored=779**.

**Verdict: MATCH — exact, to full floating-point precision, on every one of the 5 values.**

**Confidence: V2** (direct byte-for-byte comparison of the CSV's own values against the page's
embedded values — both read directly this session).

---

## Check 4: `data_pulled_at` per page

### `index.html` (stock panel)
Loads `data/inventory.json` **client-side via `fetch`** and renders `snapshot.loaded_at` /
`backlog.loaded_at` directly (confirmed by reading the page's JS, `index.html` lines ~7888-7930).
Both fields were independently re-verified against the live DB's own timestamp columns in Check 1
above (both exact matches to the DB's own minimum `timestamp`/`Timestamp` value for the pulled
rows). **Verdict: MATCH**, and independently confirmed against the database, not merely a
self-referential read of the same JSON file. **Confidence: V2.**

### `forecast/sales_report.html`
Displayed primary `data_pulled_at`: **"2026-09-25 11:51:56"** (labelled `snapshot_pull_date`).
Independently verified: `output/data/processed_full_category_sales_monthly_forecastDate.csv`'s own
`snapshot_pull_date` column has exactly one value, **"2026-09-25 11:51:56"** — **MATCH (exact)**.
The page's own per-section freshness table was also spot-checked against each cited file's real
mtime on disk: `phaseC_step2_transferability_per_division.csv`/`_per_division_summary_qty.csv`
(displayed "2026-09-07 09:05"; actual mtimes 09:06 and 09:05 respectively — 1-minute apart, page
shows the earlier of the two, **MATCH** within expected combination of two files),
`delivery_by_year.csv` (displayed "2026-09-18 14:38"; actual mtime 2026-09-18 14:38, **MATCH**),
`delivery_not_late_by_year.csv` (displayed "2026-09-25 11:57"; actual mtime 2026-09-25 11:57,
**MATCH**), `leadtime_notice_buckets_overall.csv` (displayed "2026-09-01 16:35"; actual mtime
2026-09-01 16:35, **MATCH**), `focus_items_test_all.csv` (displayed "2026-09-08 13:15"; actual
mtime 2026-09-08 13:15, **MATCH**). **Verdict: MATCH** on every row checked. **Confidence: V2**
(direct filesystem mtime check + direct CSV column read, this session).

### `forecast/inventory.html`
`model_calibrated_at` = "2026-09-23" / "2026-07" — matches `output/summary/phaseJ3_report.md`'s
own header date and stated `ForecastDelDate` bound as cited on the page (read directly). PEM101's
`snapshot_pull_date` = "2026-09-25 11:51:56" — same value as, and independently verified against,
the sales report's own `processed_full_category_sales_monthly_forecastDate.csv` check above —
**MATCH**. PEM103's and PEM107's `snapshot_pull_date` are each labelled "(live pull, not a frozen
file)" — **"2026-09-25 12:05:02"** and **"2026-09-25 12:05:04"** respectively, both within the
same minute as the page's own `page_built_at` ("2026-09-25 12:05"). **These cannot be
independently re-verified from data**: a live pull leaves no separate, persisted timestamp record
outside the page-generation process itself, and re-querying the DB now cannot recover what time an
earlier build actually ran its query. I did **not** attempt to fabricate a second-hand
verification of this — per AGENTS.md's stopping rule, this is reported as **CANNOT BE
INDEPENDENTLY VERIFIED FROM DATA**, not as MATCH or DISCREPANCY. It is at least internally
plausible (same-minute proximity to `page_built_at`, consistent with the page's own claim of a
live build-time pull) — **confidence: V1 (self-consistency only, not independent confirmation)**.

---

## Summary of 4 checks

| # | Check | Verdict | Both figures (validator vs. artifact) |
|---|---|---|---|
| 1 | Stock panel totals (on-hand, sellable/staging/elsewhere per division, Reserved) | **MATCH** (all figures, after correcting my own whitespace bug on warehouse codes, and after using the project's established `ActualQty+BacklogQty` convention for Reserved instead of the task prompt's literal "ActualQty alone") | Total on-hand: 147,899.0 = 147,899.0. PEM101 sellable/staging/elsewhere: 141,323.0/5,671.0/20.0 = 141,323.0/5,671.0/20.0. PEM103: 43.0/0.0/0.0 = 43.0/0.0/0.0. PEM107: 720.0/70.0/0.0 = 720.0/70.0/0.0. CI101/PEM102/PEM104 on-hand (unsplit): 47.0/4.0/1.0 = 47.0/4.0/1.0. Reserved: 42,121.0 = 42,121.0 |
| 2 | Sales report `not_late` by year, 2023-2026, unit-weighted | **MATCH** for 2023/2024 (exact); **DISCREPANCY** for 2025 (small, +4 rows/+28 qty) and 2026 (larger, +933 rows/+124,385 qty) — inferred (not confirmed) to be live-data drift between the page's ~11:57 pull and this session's later same-day pull, not a computation error, since the method reproduces 2023/2024 exactly | 2023: 55.436087% = 55.436087%. 2024: 97.299142% = 97.299142%. 2025: 98.888626% (page) vs 98.888650% (validator). 2026: 98.254706% (page) vs 98.291130% (validator) |
| 3 | PEM107 primary results row vs. source CSV | **MATCH (exact)** | MAE 11.571453087242183 = 11.571453087242183; RMSE 14.14489231409701 = 14.14489231409701; Bias 1.6852751985457102 = 1.6852751985457102; MASE 0.9940402816237874 = 0.9940402816237874; n_scored 779 = 779 |
| 4 | `data_pulled_at` per page | **MATCH** for `index.html` (both stock and Reserved timestamps, independently re-verified against the live DB's own timestamp columns) and `forecast/sales_report.html` (main + all 6 per-section freshness rows). **MATCH** for `forecast/inventory.html`'s PEM101 row and `model_calibrated_at`. **CANNOT BE INDEPENDENTLY VERIFIED** for `forecast/inventory.html`'s PEM103/PEM107 "live pull" timestamps (no persisted external record exists to check them against; internally plausible only) | index.html stock: DB min timestamp 2026-09-24 21:40:32.730 = displayed/JSON 2026-09-24 21:40:32.730000. index.html Reserved: DB min Timestamp 2026-09-25 10:04:52.040 = displayed/JSON 2026-09-25 10:04:52.040000. sales_report.html: 2026-09-25 11:51:56 = 2026-09-25 11:51:56 (csv). inventory.html PEM101: 2026-09-25 11:51:56 = 2026-09-25 11:51:56. inventory.html PEM103/PEM107: displayed 2026-09-25 12:05:02 / 12:05:04 — no independent source to compare against |
