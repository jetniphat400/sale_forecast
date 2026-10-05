# Check V1, V2, V3 -- the 5 October scheduled run, source-table load times, PlanDelDate against ForecastDelDate (2026-10-05)

Read-only check. Nothing in code, config, data, pages, scheduled tasks or any model was changed; the monthly runner was not run. One read-only database session (SELECT and metadata only, one connection, 2026-10-05 08:1x), its query outputs saved outside the repository and not committed. Date and time from Get-Date 2026-10-05 08:05 (+07:00); the database server clock read 2026-10-05 08:19:54 at the end of the session; git history agrees (last commit 2026-10-05 07:48). Evidence levels: **V2** = computed by the checker and independently recomputed by a Validator that read none of the checker's conclusions and made no database connection; **V1** = computed once; **inferred** = a reading of patterns, marked as such.

## Part V2 -- the scheduled run on 5 October (C3)

**Records read:** `Get-ScheduledTaskInfo SaleForecastMonthlyRefresh`; the Task Scheduler operational log since 2026-10-04; the run log `output/runs/monthly_refresh_20261005T074101.json`; git history.

| Item | Result | Source |
|---|---|---|
| Ran | **YES.** Started 2026-10-05 07:40:43 (scheduled 07:00), ended 07:48:23. Event 114 at 07:40:43: "could not launch ... as scheduled ... started now as required by the configuration option to start the task when available". Events 100, 129, 200 (launch) and 102, 201 (finish, return code 0) follow. Many other tasks logged the same missed-schedule start between 07:34 and 07:44, so the laptop was not running (inferred: off or asleep) at 07:00 and the task caught up when it resumed | Task Scheduler operational log |
| Result code | **0** (`LastTaskResult` 0; next run 2026-11-05 07:00; missed runs 0) | Get-ScheduledTaskInfo; event 201 |
| Unattended | The Task Scheduler launched it (event 100, user PRECISE\jetniphat.boo); no manual launch is recorded | event log |
| Steps | **11 of 11 ok** (run log, every step `status: ok`) | run log |
| Step 5 | **Skipped** under the one-vintage-per-month guard ("a vintage already exists for 2026-10 (vintage_id=2, forecast_run_date=2026-10-02)") | run log step 5 |
| Step 6 | Verified both vintages; target month 2026-08 only; 390 rows (re)filled; score record: 0 appended, 8 already recorded | run log step 6 |
| New pull stage, pilot file | Ran against the database: `load_data_full.py` returncode 0, `refreshed` true | run log step 1 (`pilot_128item_refresh`) |
| New pull stage, stock panel | Ran against the database: `build_inventory_dataset.py` returncode 0, `refreshed` true; step 7 regenerated `data/inventory.json` with pull time 2026-10-05 07:41:40, stock snapshot `inventory_daily_2026-10-05.csv` load time 2026-10-04 21:41:03 | run log steps 1 and 7 |
| Step 8 | 271 passed, 2 warnings, 343.58 s | run log step 8 |
| Step 9 | 3 files scanned (`data/inventory.json`, `forecast/inventory.html`, `forecast/sales_report.html`), no findings | run log step 9 |
| Step 10 | **Passed, no violations**: backtest MAE change 0.0% for all five divisions against run 20261002T081225. Two sub-checks were not meaningful (see Found, not done): the six-month forecast check is empty because step 5 skipped, and total on-hand stock "not independently re-pulled this run ... carried forward unchanged" | run log step 10 |
| Step 11 | **Committed and pushed**: commit `db1d04b` ("Automated monthly refresh", 2026-10-05 07:48:20), push `c80d7a8..db1d04b main -> main`; the three files above. The permission classifier did not refuse | run log step 11; `git show --stat db1d04b` |

**Published page (cache bypassed).** `https://jetniphat400.github.io/sale_forecast/index.html` was opened in my own Edge (headless, temp profile under the system temp folder, PID 21348 recorded; only that PID was closed; profile deleted; PID and folder confirmed gone), with the browser cache disabled through the DevTools protocol and a fresh profile. `data/inventory.json` came back HTTP 200 with `Last-Modified: Mon, 05 Oct 2026 00:49:04 GMT` (07:49 ICT, one minute after the push). After opening the stock panel (the "Chase" index page's stock menu row), the panel states:

| Date shown on the stock panel | Value |
|---|---|
| data_pulled_at (stock) | **2026-10-04 21:41** ICT (the source table's own load time) |
| data_pulled_at (Reserved) | **2026-10-05 07:35** ICT (the Cube_CES load time, `Status = Backlog`) |
| page_built_at | 2026-10-05 07:41 ICT |
| Staleness notices | none shown (both hidden) |
| Code counts | 445 codes; 156 with stock; 232 zero; 57 no record |

Screenshot: `output/charts/v2_check/v2_published_stock_panel.png` (untracked; `output/` is not versioned). The stock date is the load time of the source table, not the pull time, as already recorded under W3.

**Finding for C3.** The run executed unattended, completed all 11 steps and pushed; the first run of the new pull stages and `--from-pulls` worked against the database. C3 is **confirmed met**, with the open items below carried forward.

## Part V3 -- source table load times

Latest value of each table's own timestamp column, from the one read-only session (`q2_loadtimes_*`, `q2b_batches_*`; the table-wide minimum and maximum fall in one narrow batch, as at the earlier check, so each is a truncate-and-reload snapshot, inferred).

| Table | Latest load | Earlier check (2026-10-02) | Loaded again since? |
|---|---|---|---|
| Cube_CES | **2026-10-05 07:37:46** (batch 07:35:22 to 07:37:46) | 2026-09-28 07:00:34 | **Yes** |
| Cube_BOM_Exact | **2026-10-05 06:42:48** (batch 06:39:06 to 06:42:48) | 2026-09-28 06:19:06 | **Yes** |
| Cube_Inventory_Aging | **2026-10-05 06:39:02** (batch 06:30:55 to 06:39:02) | 2026-09-28 06:15:10 | **Yes** |
| Cube_Inventory_Exact | **2026-10-04 21:42:24** (batch 21:41:03 to 21:42:24) | 2026-10-01 21:47:21 | Yes |
| cube_Sale_APD | **2026-10-04 17:17:46** (batch 17:00:15 to 17:17:46) | 2026-10-01 17:17:33 | Yes |

Row counts at the session: Cube_CES 169,309; Cube_BOM_Exact 348,805; Cube_Inventory_Aging 447,425; Cube_Inventory_Exact 97,570; cube_Sale_APD 53,139.

**What this implies.** The three tables that last loaded on 2026-09-28 loaded again on Monday 2026-10-05, so that job has **not stopped**. The 2026-10-02 reading (taken at 10:50) showed no load on 09-29, 09-30, 10-01 or the morning of 10-02, so it is **not a daily job**. Loads observed on Mondays 2026-08-31, 2026-09-28 and 2026-10-05 fit a weekly Monday run; the repository's other observations (Wednesday 09-02, Tuesday 09-22, Friday 09-25) do not fit it, and a snapshot of an overwritten table cannot show that nothing loaded in between. The 17:00 and 21:45 groups loaded on Thursday 2026-10-01 and again on Sunday 2026-10-04, which is not a weekly pattern on the same day either. **Schedule: unclear** (not stopped, not daily; weekly on Monday is consistent with the three 06:00-07:00 tables but not established). The questions for the ETL team in the Phase R audit stand.

## Part V1 -- PlanDelDate against ForecastDelDate (tests only; nothing decided)

Neither field's meaning is confirmed. The user's stated understanding (level A) is that Sales enters PlanDelDate and so knows that due date; it is **not** tested here and no result below confirms or refutes it. DATA_MAP already records that `cube_Sale_APD.forecast_date` equals `Cube_CES.ForecastDelDate` (confirmed again below: 100% of joined rows).

**Population.** `Cube_CES` (pulled for the 445 pricelist codes, 112,206 rows, no date filter at pull per `src/cube_ces_pull.py`), `RevenueType = 'Omni Channel'`, `Status = 'Actual'`, `ActualDelDate` not null, `ActualQty > 0`, `ForecastDelDate` from 2024-01-01, item in the 445-code pricelist-derived map (`output/summary/phaseC_step1revised_item_status_445.csv`): **37,618 rows, 3,561,187 units**. Year = year of ForecastDelDate. Units = ActualQty. `PlanDelDate` is never null in this population (0 rows); it is null for 15.1% of all 112,206 pulled rows (other statuses).

### V1.1 Agreement

| Scope | Rows | Units | Plan = Forecast (rows / units) | Plan earlier (rows / units) | Plan later (rows / units) | Null |
|---|---|---|---|---|---|---|
| All | 37,618 | 3,561,187 | 95.45% / **99.09%** | 1.65% / **0.44%** | 2.90% / **0.47%** | 0 |
| 2024 | 12,872 | 1,151,741 | 94.59% / 98.89% | 2.57% / 0.37% | 2.84% / 0.74% | 0 |
| 2025 | 13,366 | 1,330,596 | 95.97% / 99.35% | 1.70% / 0.26% | 2.33% / 0.39% | 0 |
| 2026 | 11,380 | 1,078,850 | 95.80% / 98.99% | 0.55% / 0.73% | 3.65% / 0.27% | 0 |
| 2026, before May | 4,413 | 389,334 | 96.40% / 99.77% | 0.39% / 0.08% | 3.22% / 0.14% | 0 |
| 2026, from May | 6,967 | 689,516 | 95.42% / 98.55% | 0.66% / 1.10% | 3.92% / 0.35% | 0 |
| CI101 | 737 | 7,458 | 94.57% / 92.80% | 2.17% / 4.59% | 3.26% / 2.61% | 0 |
| PEM101 | 29,589 | 3,505,050 | 97.22% / 99.16% | 0.90% / 0.41% | 1.88% / 0.43% | 0 |
| PEM102 | 449 | 612 | 81.07% / 82.35% | 3.34% / 2.61% | 15.59% / 15.03% | 0 |
| PEM103 | 1,285 | 3,813 | 78.13% / 82.74% | 15.64% / 12.01% | 6.23% / 5.25% | 0 |
| PEM104 | 13 | 13 | 92.31% / 92.31% | 0.00% / 0.00% | 7.69% / 7.69% | 0 |
| PEM107 | 5,545 | 44,241 | 91.29% / 96.63% | 2.22% / 0.77% | 6.49% / 2.59% | 0 |
| Late under ForecastDelDate | 2,566 | 85,295 | 63.48% / **81.42%** | 0.04% / 0.18% | 36.48% / **18.40%** | 0 |
| Not late under ForecastDelDate | 35,052 | 3,475,892 | 97.79% / 99.53% | 1.77% / 0.45% | 0.45% / 0.03% | 0 |

Distribution of PlanDelDate minus ForecastDelDate in days (rows / units): 0 days 95.45% / 99.09%; Plan 1 to 7 days later 1.26% / 0.17%; 8 to 30 later 0.94% / 0.15%; 31 or more later 0.70% / 0.14%; Plan 1 to 7 days earlier 1.12% / 0.36%; 8 to 30 earlier 0.41% / 0.05%; 31 or more earlier 0.12% / 0.03%. Among the 1,713 rows that differ: median +3 days, mean +11.5, 5th to 95th percentile -15 to +76, extremes -729 and +429 days.

### V1.2 not_late under each date (METRICS section 19, unit-weighted unless stated; Plan version excludes null PlanDelDate rows, none here)

Per division and year (population above). `late units` are units delivered after the due date.

| Division | Year | Units | not_late Forecast | not_late Plan | Difference (Plan minus Forecast) | Late units Forecast / Plan |
|---|---|---|---|---|---|---|
| CI101 | 2024 | 4,195 | 97.54% | 93.25% | -4.29 pp | 103 / 283 |
| CI101 | 2025 | 2,024 | 97.13% | 98.32% | +1.19 | 58 / 34 |
| CI101 | 2026 | 1,239 | 94.11% | 95.56% | +1.45 | 73 / 55 |
| PEM101 | 2024 | 1,124,219 | 96.27% | 96.78% | +0.51 | 41,976 / 36,151 |
| PEM101 | 2025 | 1,311,332 | 98.69% | 98.98% | +0.29 | 17,222 / 13,314 |
| PEM101 | 2026 | 1,069,499 | 98.23% | 97.74% | -0.49 | 18,982 / 24,144 |
| PEM102 | 2024 | 185 | 83.78% | 94.59% | +10.81 | 30 / 10 |
| PEM102 | 2025 | 227 | 81.06% | 93.39% | +12.33 | 43 / 15 |
| PEM102 | 2026 | 200 | 63.50% | 75.50% | +12.00 | 73 / 49 |
| PEM103 | 2024 | 986 | 94.32% | 97.36% | +3.04 | 56 / 26 |
| PEM103 | 2025 | 660 | 85.76% | 96.36% | +10.60 | 94 / 24 |
| PEM103 | 2026 | 2,167 | 96.22% | 98.48% | +2.26 | 82 / 33 |
| PEM104 | 2025 | 9 | 77.78% | 88.89% | +11.11 | 2 / 1 |
| PEM104 | 2026 | 4 | 100.00% | 100.00% | 0.00 | 0 / 0 |
| PEM107 | 2024 | 22,156 | 83.38% | 84.48% | +1.10 | 3,682 / 3,438 |
| PEM107 | 2025 | 16,344 | 90.98% | 93.25% | +2.27 | 1,474 / 1,103 |
| PEM107 | 2026 | 5,741 | 76.57% | 80.84% | +4.27 | 1,345 / 1,100 |
| All | 2024 | 1,151,741 | 96.02% | 96.53% | +0.51 | 45,847 / 39,908 |
| All | 2025 | 1,330,596 | 98.58% | 98.91% | +0.33 | 18,893 / 14,491 |
| All | 2026 | 1,078,850 | 98.09% | 97.65% | -0.44 | 20,555 / 25,381 |
| All | 2024 to 2026 | 3,561,187 | **97.60%** | **97.76%** | +0.16 | 85,295 / 79,780 |

Row-weighted figures (all 2024 to 2026): 93.18% under ForecastDelDate, 95.32% under PlanDelDate; per division and year in the saved analysis outputs (scratch folder, not committed).

**PEM101, the J3 calibration check.** J3's method (`src/investigations/phaseJ3_validator_reconciliation.py` `part_b`): the 128 PEM101 items of the 351-item scope file, `Status = 'Actual'` (any RevenueType), ForecastDelDate and ActualDelDate not null, ForecastDelDate from 2026-01-01, weights ActualQty as recorded.

| Data and definition | Units | not_late ForecastDelDate | not_late PlanDelDate |
|---|---|---|---|
| J3 method on J3's own cached pull (2026-09-23) | 1,028,354 | **98.276%** (reproduces 98.28%) | 97.688% |
| J3 method on today's pull (2026-10-05) | 1,170,028 | 98.400% | 97.958% |
| Population definition (Omni, qty > 0), same 128 items, from 2026-01-01 | 1,061,684 | 98.236% | 97.750% |
| Population definition, same 128 items, calibration window 2024-01-01 to 2025-12-31 | 2,401,443 | 97.701% (J3 recorded 97.70%) | 97.991% |

The 98.28% is reproduced exactly from J3's cached data with J3's method (the check passes). On the database as it stands today the same method gives 98.40%, because deliveries have been added since 2026-09-23; this is a change in data, not in method.

**PEM107's 66 items** (36 confirmed_to_order failing C3 plus 30 conflict, the code list from `audit_minmax_pem107_season.md`; all 66 are PEM107 in the map). Delivered set: Omni, Actual, ActualDelDate present, qty > 0. Late under Forecast: ActualDelDate after ForecastDelDate; late under Plan: after PlanDelDate.

| Set and period | Floor | Units | Late units Forecast | not_late Forecast | Late units Plan | not_late Plan |
|---|---|---|---|---|---|---|
| 66 items, before May 2026 | none (as the audit) | 44,030 | 5,207 | 88.17% | 4,851 | 88.98% |
| 66 items, before May 2026 | ForecastDelDate from 2024-01-01 (population) | 23,943 | 3,106 | 87.03% | 2,550 | 89.35% |
| 66 items, from May 2026 | either | 1,914 | 908 | 52.56% | 786 | 58.93% |
| 9 items, before May 2026 | from 2024-01-01 | 16,084 | 2,296 | 85.72% | 2,040 | 87.32% |
| 9 items, from May 2026 | either | 1,169 | 740 | 36.70% | 676 | 42.17% |

The audit's figures for the 66 items are reproduced from the same query logic (44,030 delivered and 5,207 late before May: identical). From May 2026 the pull of 2026-10-05 holds 1,914 delivered and 908 late units against the audit's 1,880 and 891 of 2026-10-02: the 17 extra late units are deliveries recorded in the three days between the pulls. The nine items with the most late units from May 2026 are the same nine as in the audit (they hold 740 of the 908, 81.5%; the audit had 737 of 891, 82.7%).

The 9 items, late units from May 2026 (Forecast / Plan): RS-F-99-070002 160 / 160; CT-F-99-020501 153 / 150; RS-F-99-070003 100 / 100; VT-F-99-010203 83 / 78; CT-F-99-020502 70 / 55; CT-F-99-020514 58 / 58; VT-F-99-010721 50 / 21; CT-F-99-020505 36 / 24; RS-F-99-070005 30 / 30. **Total 740 by ForecastDelDate / 676 by PlanDelDate** (-64 units, -8.6%). No row of these items lacks a PlanDelDate.

### V1.3 Months of sales

`cube_Sale_APD` pulled for the 445 codes in the pipeline's own scope (Omni Channel, Actual plus MPS; 38,027 rows). Window as the pipeline's series: `forecast_date` not before `createDate`, from 2024-02-01 to 2026-08-31, item in the map: **35,134 rows, 3,340,212 units** (the pipeline's 335-code series totals 3,340,200; the 12-unit difference is the 110 pricelist codes outside the forecast scope). Join to `Cube_CES` on **(contract, item, planid) = (ContractID, ItemCode, PlanID)**: the key is unique on both sides (0 duplicates in 112,206 CES rows; 38,027 distinct in APD). On joined rows `forecast_date` equals `ForecastDelDate` for **100%** of units in every division (the existing DATA_MAP finding, reproduced). A row's month "changes" if the calendar month of the joined PlanDelDate differs from that of `forecast_date`. Joined rows with a null PlanDelDate: 0.

| Division | APD units in window | Join coverage (units / rows) | Units whose month changes | Share of units |
|---|---|---|---|---|
| CI101 | 6,552 | 100.00% / 100.00% | 96 | 1.47% |
| PEM101 | 3,288,931 | 99.98% / 99.92% | 4,966 | 0.15% |
| PEM102 | 590 | 98.98% / 99.54% | 39 | 6.61% (6.68% of joined) |
| PEM103 | 3,442 | 100.00% / 100.00% | 135 | 3.92% |
| PEM104 | 12 | 100.00% / 100.00% | 1 | 8.33% |
| PEM107 | 40,685 | 96.72% / 99.71% | 572 | 1.41% (1.45% of joined) |
| **All** | **3,340,212** | **99.94% / 99.89%** | **5,809** | **0.17%** (538 rows) |

Unjoined rows are counted as unchanged in the shares above; the largest the overall share could be if every unjoined unit changed is 0.17% + 0.06% = 0.23%.

### V1.4 Weekday of ActualDelDate (a weak indication only; no conclusion drawn)

Population (37,618 rows): **Sunday 0.06% of rows (24 rows; 0.00% of units); Saturday 0.45% of rows (170 rows; 0.06% of units)**. Weekday counts Monday to Friday: 5,591, 6,252, 8,306, 7,014, 10,261. For comparison in the same rows: ForecastDelDate falls on a Sunday in 0.44% and a Saturday in 0.73% of rows; PlanDelDate on a Sunday in 0.45% and a Saturday in 0.78%. By year, Saturday ActualDelDate 0.72% (2024), 0.29% (2025), 0.33% (2026).

### V1.5 Impact: which figure or decision depends on which date

Dependencies were read from the code and METRICS, not recalled: `src/build_report.py:393` (not_late "delivered on or before ForecastDelDate" on the sales report); `src/investigations/phaseJ3_validator_reconciliation.py` part B (calibration targets, ForecastDelDate window); METRICS section 19, 20 (not_late targets), 27 (forward-test months); `src/load_data_all_divisions.py` (the series is keyed on `forecast_date`); `src/build_inventory_dataset.py:341-342` (Reserved list `delivery_date` = ForecastDelDate, `plan_delivery_date` = PlanDelDate); `src/phaseE1fix_recompute.py:614-615` (Reserved placed in months by ForecastDelDate); `output/summary/audit_minmax_pem107_season.md` Part A (late units from May 2026) and the PEM107 G3 criterion C3 (not_late >= 85%).

| Figure | Under ForecastDelDate | Under PlanDelDate | Difference | Depends on it |
|---|---|---|---|---|
| not_late, all divisions 2024-2026, unit | 97.60% | 97.76% | +0.16 pp | the sales report's delivery-timeliness chart by year (`build_report.py:393`) |
| not_late, all divisions 2026, unit | 98.09% | 97.65% | -0.44 pp | same chart, 2026 bar |
| PEM101 not_late, J3 method, 128 items, from 2026-01 (J3 cached) | 98.28% | 97.69% | -0.59 pp | Phase J3 validation target and "today's operating point" in the Max-Min trade-off curve (DATA_MAP "Today's operating point 98.28%") |
| PEM101 not_late, calibration window 2024-2025, 128 items | 97.70% | 97.99% | +0.29 pp | J3 calibration target |
| PEM107 not_late 2026, unit | 76.57% | 80.84% | +4.27 pp | the J3 finding "PEM107 not calibratable" and the PEM107 alert items |
| PEM107 66 items from May 2026, not_late | 52.56% | 58.93% | +6.37 pp | the audit's 891 late units, the 9 items, E2 confirmation packs |
| PEM107 66 items before May 2026 (2024 on), not_late | 87.03% | 89.35% | +2.32 pp | criterion C3 (not_late >= 85%) of the PEM107 G3 verification, if recomputed from 2024 |
| PEM107 9 items, late units from May 2026 | 740 | 676 | -64 | the E2 packs' list of items driving lateness |
| PEM102 not_late 2026, unit | 63.50% | 75.50% | +12.00 pp | PEM102 delivery status (small: 200 units) |
| PEM103 not_late 2025, unit | 85.76% | 96.36% | +10.60 pp | G3 tender-pipeline reading of PEM103 service (small: 660 units) |
| Units whose sales month changes, all divisions | 0 by definition | 0.17% of 3,340,212 | +5,809 units | the forecast series and the forward-test actuals (both keyed on `forecast_date`); PEM102 6.61%, PEM103 3.92%, PEM104 8.33% are the divisions where a month key would matter, all small in units |
| Late units under each date, all, 2024-2026 | 85,295 | 79,780 | -5,515 | every lateness total quoted in STATUS and the pages |

**Reading (labelled as such; no decision):** the two dates are equal on 99.09% of units and the month of sale changes for 0.17% of units, so for the pilot-scale PEM101 the choice moves not_late by under one point; the difference is concentrated in PEM102, PEM103, PEM107 and CI101, where Plan is more often later than Forecast on late rows (36% of late rows have Plan later). Which date is the real commitment is for the user and Sales to define: **V1 is pending the user's definitions.**

## Part F -- Validator

A separate Validator (no database access; read none of the checker's conclusions or analysis outputs; re-derived from the same saved query outputs by its own code, so this is an **independent recomputation of the method on the same pulled rows**, not a second pull) re-derived the following. Its code and report are in the scratch folder, not committed.

| Item | Checker | Validator | Result |
|---|---|---|---|
| V1 agreement by year, rows and units (2024, 2025, 2026, overall); overall equal 35,905 rows / 3,528,882 units, earlier 621 rows, later 1,092 rows | as in V1.1 | 94.585 / 98.886, 95.975 / 99.354, 95.800 / 98.992, 95.446 / 99.093 percent equal (rows / units); earlier and later shares equal to V1.1 | **MATCH** |
| PEM101 not_late, J3 method, today's pull | 98.400% / 97.958% | 98.3995% / 97.9583% (8,683 rows, 1,170,028 units) | **MATCH** |
| PEM101 not_late, population definition, 128 items from 2026-01 | 98.236% / 97.750% | 98.2362% / 97.7500% | **MATCH** |
| PEM101 not_late, J3 method on the cached 2026-09-23 pull | 98.276% / 97.688% | 98.2760% / 97.6876%; reproduces 98.28% | **MATCH** |
| The 9 items' late units from May 2026 | 740 / 676, same nine codes | 740 / 676, same nine codes (the 10th item has 23, no tie); all 66 items 908 / 786 | **MATCH** |
| Month-change share by division, join coverage | CI101 1.47, PEM101 0.15, PEM102 6.61, PEM103 3.92, PEM104 8.33, PEM107 1.41, all 0.17 percent; coverage 99.94% of units | same to three decimals (all 0.174%; coverage 99.941%) | **MATCH** |
| V3 load times | CES 07:37:46, BOM 06:42:48, Aging 06:39:02, Inventory 21:42:24 (10-04), APD 17:17:46 (10-04) | same to the millisecond | **MATCH** |

Side finding by the Validator: of the 128 J3 PEM101 codes, 126 have rows in the current pull (two have none); 7 CES rows have a null PlanID and cannot be joined. Not re-derived by the Validator (checked by the checker only, level V1): the late-row split by agreement, the per-division per-year not_late table beyond PEM101, and the weekday shares.

## Found, not done

- **C6 (open, phase C):** step 10's six-month-forecast check is empty whenever step 5 skips, and its total-on-hand check is carried forward without a second pull, so on a skipped-vintage month two of the three change-magnitude gates did not test anything. Seen again in this run's log.
- **W3 (open):** the stock panel's date is the source table's load time, not the pull time.
- **V1 (pending the user's definitions, phase R):** which date is the due date; whether Sales enters PlanDelDate; which date should key the series and measure on-time. Nothing was decided.
- **ETL (phase R, ETL team):** the schedule of the 06:00-07:00 job (Cube_CES, Cube_BOM_Exact, Cube_Inventory_Aging) and the 17:00 and 21:45 jobs is still unclear; the Phase R questions stand.
- **Laptop on the 5th (people only):** the run started at 07:40, not 07:00, because the laptop was not running at 07:00; StartWhenAvailable caught it up. No action beyond keeping the existing practice.
