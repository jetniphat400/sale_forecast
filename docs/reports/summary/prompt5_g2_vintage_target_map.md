# Prompt 5 -- G2 on the latest vintage, PEM101 Min/Max basis, G3-only items, test inputs, target_data.xlsx

Checked 2026-10-08 (clock 08:09 to 08:45, this machine). Decisions of the user, 2026-10-08: D1 track the class-decision test inputs; D2 rebuild G2 from the latest log vintage and keep it in step every month; `target_data.xlsx`, sheet "TargetC1005 12-06-2029", is the latest target version (user's statement, not verified here). Figures come from computations run in this task by the implementer or by independent agents (Modeler, Explorer, Validator) working read-only from the repository and the saved files; their scripts and result files are in %TEMP% (`g2bak`, `valG2`, `p3_minmax`, `p4_trace`), outside the repository. CONFIRMED = computed now; INFERRED = a reading, with its confidence.

## Part 1. The daily job's gate order, and the 08:00 run of 2026-10-08

- **Order (CONFIRMED, `src/daily_stock_job.py` `publish_stage`, lines 281-286):** `check_publishing_setup`, then `git pull --ff-only origin main` (line 282), then the "tracked files clean" check (lines 283-286). The gate runs after the pull. The scheduled task also runs `git pull --ff-only` in the clone before it starts the job. **No defect.**
- **08:00 run, 2026-10-08 (CONFIRMED):** Task Scheduler events: started 08:00:01, finished 08:01:14, return code 0 (last result 0). Run log `daily_stock_20261008T080029.json`: status published, the four gates passed (row count band, on-hand total band, no null item codes, pull newer than published), committed and pushed commit 993d8e3 ("Daily stock refresh, pulled 2026-10-08 08:01:01"). The clone was clean at that commit, so no `git pull` was needed or run; the 12:00 run is expected to skip (a successful run of today exists).

## Part 2. G2 on the latest vintage

**What changed.** `build_inventory_page_data.py` takes each item's forecast from the latest vintage of the forward-test log (`latest_vintage_item_forecasts`: hash-checked, Item level, the vintage's monthly values in target-month order, extended to the page's 10 months by repeating the last month; every item's vintage forecast is flat) instead of refitting a Top-down forecast on its own series. The method and every parameter of Min/Max are unchanged. The embedded data carries `forecast_vintage` (vintage id, run date, data cutoff, fit end, target months). The monthly runner has a new step **7d** after the material plan: the vintage gate fails the run unless G1 (latest log vintage), G2 (`forecast_vintage` of the page), G3 (operation plan meta) and the material plan (its meta, now with `vintage_id`) carry the same vintage; G2 is rebuilt by step 7, after the forecast step and before G3 and the material plan. Tests: the gate fails on every mismatched or missing vintage and passes on matched ones; the builder uses the latest vintage, flat extension; the tracked page carries the log's latest vintage and every item the log forecasts has its forecast on the page.

**Rebuilt now:** `forecast/inventory.html` (vintage 2, run 2026-10-02, fit to 2026-08, targets 2026-09 to 2027-02) and the recorded dense grid inputs (identical figures; only the path of a source report changed). **The operation plan and the material plan were not rebuilt:** a rebuild now reads the daily pull of 2026-10-08 instead of 2026-10-06 and changes 82 of 439 items of G3 and 567 materials beyond the G2 effect (materials to order now 600 to 584), which is outside this task's rule; they stay at vintage 2, plan day 2026-10-06, until the next run or an instruction. G2 and G3 now differ only in the Max of the four PEM107 stock items (below).

**Per division, old to new (standard-assumption table of the page at its default controls; CONFIRMED by the implementer and the Validator):**

| Division | Items with Min/Max | Total Min | Total Max | Stock value (THB) | Items changed |
|---|---|---|---|---|---|
| PEM101 | 77 | 457,296.5 to 460,098.8 | 576,665.5 to 578,656.1 | 62,212,606 to 65,307,227 | 77 (12 in Min, 77 in Max) |
| PEM103 | 0 | 0 | 0 | 0 | 0 |
| PEM107 | 4 | 446.18 to 446.18 | 541.70 to 547.79 | 3,320,249 to 3,320,249 | 4 (Max only) |

The 5 largest changes in Max, PEM101: EEE-F-FC-1040011100 2,929.7 to 4,093.0; EEE-F-FC-1040010002 9,950.2 to 10,849.0; HS-F-99-0211 4,958.1 to 5,716.8; HS-F-99-02110 753.4 to 1,468.0; EEE-F-FL-1040030002 48,641.9 to 47,947.2. PEM107 (all four): CT-F-99-020504 199.81 to 202.78; CT-F-99-020503 133.74 to 135.25; CT-F-99-020506 191.78 to 193.05; VT-F-99-010715 16.37 to 16.70. PEM101's calibrated section (92 items, history-based) is identical to before; PEM107's Min and stock value do not move because its Min is the history percentile.

**G2 against G3 demand (re-run, CONFIRMED by both):** 306 items with a forecast on the page (PEM101 144, PEM103 50, PEM107 112), 1,530 item-months against G3's forecast column and 1,530 against the log: **0 mismatches** (largest difference 0.0005, the page's rounding). Before: 1,330 mismatches in 266 items.

**The 32 PEM101 items that showed "no forecast":** all 32 now have a positive 10-value forecast equal to the log (15 stock-policy, 8 confirmed-to-order, 9 conflict). None is in the standard-assumption table, because all 32 have no history in the page's series (empty `actual_history`), so no Min is computable there; the 15 stock-policy ones have Min/Max in the calibrated section (they are in its grid).

**Other changes to the page data that are not the forecast (CONFIRMED):** `pipeline_gap_pct` 1.61 to 3.28 (computed from the forecast); and six signal values that earlier tasks changed in the item-level file after the page was last built: S1 of HS-F-99-2121N (true to false) and of RS-F-99-070003 (false to true), S2 of EEE-F-FC-5920-383-1000, EEE-F-FL-1040030001, HS-F-99-2211N and HS-F-99-2301N (not computed to false). Class, policy and Min/Max computability are unchanged. The Validator found no other difference.

**Stale until the next run:** G3's Max for the four PEM107 items (old vintage-1 Max); G2's `actual_history` still comes from the builder's own older series (PEM101: the pilot file to 2026-07; PEM103 and PEM107: the saved sales pull), so the history behind the percentile is not the log's fit window -- not changed here.

## Part 3. PEM101 Min/Max: history-based against forecast-based (report only)

**Demand input today (CONFIRMED, `src/maxmin_v1.py` `build_page_inputs`):** `output/data/raw_all_divisions_sales.csv`, the 92 stock items of `output/data/lead_time_inputs/stock92.json`, daily series from 2024-01-01 to 2026-09-30 (`phaseJ3_calibration_engine.build_full_daily_series`, summed by forecast date, zero-filled, 1,004 days); `mean_demand = daily.mean()`; Min = r x 30.44 x mean daily demand, Max = median over the 36 distinct control-run members of (r + gap) x 30.44 x mean daily demand; r = 0.7751 months (preset today's not_late 98.34 percent, interpolated). Reproduced to 0.005 for all 92 items.

**Forecast-based (same r, gaps, members, lead times; only the demand level replaced by the latest vintage's monthly forecast):**

| Total over the 92 items | History | Forecast | Ratio |
|---|---|---|---|
| Monthly demand level (units) | 105,004 | 121,156 | 1.154 |
| Min (units) | 81,385 | 93,904 | 1.154 |
| Max, median over members (units) | 186,388 | 215,061 | 1.154 |
| Min x unit cost (THB, 77 items with a cost) | 9,997,678 | 13,178,949 | 1.318 |
| Max x unit cost (THB) | 22,896,810 | 30,182,597 | 1.318 |

Per item the ratio forecast/history equals the demand ratio: median 1.192, range 0.138 to 2.148, 72 items above 1 and 20 below. Largest in Min value: EEE-F-FC-1040010002 (+THB 1.15M), EEE-F-FC-1040011100 (+0.51M), EEE-F-FC-1040011000 (+0.37M), HS-F-99-0211 (+0.30M), EEE-F-LT-1040020100P (-0.28M). The per-item table is in the Modeler's result file (%TEMP%\p3_minmax).

**Simulated, same simulation as the calibration** (validation 2026-01 to 2026-09, 36 members, median over members; the history run reproduces the recorded point exactly, 96.95 percent at THB 14.77M). At the members' own (r, s): history 96.95 percent / THB 14.77M; forecast-based 97.96 percent / THB 20.37M. At the page's default preset (r 0.7751 with each member's gap): history 97.87 percent / THB 13.85M; forecast-based 98.54 percent / THB 19.27M. Observed: 98.34 percent not_late, THB 15.49M. **Limits:** this is a level substitution, not a backtest (the vintage is a forward level applied to a past window; the history level is in-sample for that window); the members were fitted with the history level. No page or recorded output was changed.

## Part 4. G3 items with no G1 forecast (report only)

104 items are in G3 and not in the latest vintage of the log (G1): PEM101 21, PEM102 10, PEM103 37, PEM104 12, PEM107 24, CI101 0 (G1 minus G3 is 0 items). **Source: one group.** All 104 carry `demand_source = backlog` in the plan, but the quantity is **0 in every month** for every one: `src/operation_plan.py` lines 367-372 set the forecast to 0 when the status is not "forecast" and label the source "backlog" whenever there is no forecast; the backlog is `backlog_by_month` (lines 193-203: ActualQty + BacklogQty of Cube_CES rows with Status 'Backlog', by ForecastDelDate month), and neither saved pull holds any such row for these items (material inputs pulled 2026-10-06 14:49: 873 backlog rows, 0 for them; the 2026-10-08 daily pull: 866 rows, 0). Recomputed from each of three backlog inputs: 104 of 104 equal the plan (0 = 0). The plan's own input (the 2026-10-06 12:00 pull) is overwritten; INFERRED (about 90 percent) that it also held none. Database trace: Cube_CES (`ItemCode, ContractID, ForecastDelDate, PlanDelDate, ActualQty, BacklogQty, Status = 'Backlog'`, `src/build_inventory_dataset.py` lines 291-302 and `src/investigations/task2b_part2_fulfilment_segmentation.py` lines 518-519). **Undetermined:** whether 0 is true business demand or a coverage gap in Cube_CES (some items have Cube_CES rows of other statuses and no sales history; the status file marks a few as an open question). No G3 item has a demand source other than the log forecast or the Cube_CES backlog (proved for the saved plan: demand = max(forecast, backlog) on every row). Reasons they are not in G1: placeholder, pending method (PEM101 11, PEM102 10, PEM103 37, PEM107 24), placeholder with a method assigned but not applied (PEM101 10), excluded division for data volume (PEM104 12). 99 item-months of 81 G1 items take their demand from backlog above forecast.

## Part 5. Class-decision test inputs (D1)

Tracked under `docs/reports/summary/`: `phaseA_pem101_conflict_lean.md`, `phaseA_pem107_g3_verification.md`, `task2b_part2_item_level.csv` (a copy of the recorded item-level file of 2026-10-08). `tests/test_class_decisions.py` points at them and all 7 xfail marks are removed; no assertion was weakened. The calibrated-note test now reads the tracked page's embedded data instead of rebuilding it with the builder (the builder needs many untracked files); its assertions are unchanged. Fresh clone of origin/main in a temp folder: 9 passed, 1 skipped, 0 xfail, 0 failed (the skip is the S2 test that needs the untracked saved class evidence); folder deleted.

## Part 6. target_data.xlsx -- BLOCKED

`D:\sale_forecast_private\target_data.xlsx` does not exist (the folder `D:\sale_forecast_private` does not exist on this machine); the file was also not found in `D:\sale_forecast`, its `reference/`, or `D:\sale_forecast_publish` (searched in the previous task). Nothing in Part 6 could be done: no sheet, column, row count, dimension match, measure candidate, projection or POR comparison, and no database session was used. Needed: the file at the stated path (or the right path).


# Prompt 6

Checked 2026-10-08 (clock 08:57 to 09:45, this machine). Decisions of the user, 2026-10-08: D1 rebuild the operation plan and the material plan today; D2 G2 takes its history from the same series as the forecast log; D3 PEM101 Min/Max keep the history-based demand input in v1 (a real backtest of a forecast-based input when enough vintages exist). Figures come from computations run in this task by the implementer or by independent agents (Analyst, Validator) working read-only from the repository and the saved files; their scripts and results are in %TEMP% (`g2bak`, `val6`, `e2e6_work`, `p5_target`, `val5t`, `wk6`), outside the repository. The target workbook was copied once to a private folder outside the repository (`D:\sale_forecast_private\target_data.xlsx`, same hash as the source); neither it nor any row of it is in the repository, and its source path is written nowhere in it. CONFIRMED = computed now; INFERRED = a reading, with its confidence.

## Part 1. The snapshot dated 2026-11-05

- **Files (CONFIRMED):** four, in `output/snapshots`: `inventory_page_pull_PEM101_inventory_2026-11-05.csv`, `..._PEM103_inventory_...`, `..._PEM107_inventory_...`, `..._PEM103_PEM107_sales_...`. File time 2026-10-02 10:22:37 to 10:22:45; the `_pull_time` column inside reads 2026-11-05 07:03:58 to 07:04:01.
- **Writer:** `build_inventory_page_data._persist_and_reload` (line 46: file name and `_pull_time` come from `datetime.now()`), called by `build_data()` when the page is built with no data sources, i.e. a **live database pull**. The caller was the unpatched test `test_inventory_page_rebuild_still_has_every_note_axis_title_and_disabled_control` (`tests/test_manual_survives_rebuild.py`, which called `build_inventory_page.build_page()` with no sources; its own docstring says it "performs a live database pull"), run by the 2026-10-02 full suite with the clock moved to 2026-11-05 07:00 (STATUS.md, phase C11). Evidence: file times fall in the window of that run (the next dry run started 10:24:18), the `_pull_time` is the shifted clock, and the same four-file set appears for every other day a full suite ran (2026-10-05 16:30, 10-06 16:43, 10-07 14:36, 10-08 08:35, each with the real date). **Consequence the earlier reports missed:** every full test run made a live database pull (each run's `build_data`: stock and sales); the "no database connection" statements for tasks that ran the full suite were wrong for the suite part. Fixed now (below); confirmed by running the full suite with a guard that makes any database connection raise (in the test process and every Python process it starts): 637 passed, no new snapshot file.
- **Readers of "the latest saved pull":** `inventory_page_sources._latest()` (name sorts last, so it WOULD have chosen the 2026-11-05 files) used by `_read_snapshot` and `saved_pull_sources()`; `latest_daily_snapshot()` (`inventory_daily_*`, none future-dated). `saved_pull_sources()` has no caller in the pipeline; `_read_snapshot` is reached only from the stock-settings fallback when a daily snapshot lacks the minimum/maximum columns, which was not the case for any snapshot used. The monthly runner builds the page through `daily_snapshot_sources` (latest `inventory_daily_*`), the daily job and the operation plan read the single folder `output/data/daily_stock_pull`. **No page and no recorded output was built from a future-dated file (CONFIRMED by reading every reader and by the files used for the 2026-10-08 builds).**
- **Done:** `not_after_today()` makes both selectors ignore files dated after today; the four files were moved (not deleted) to `output/snapshots_quarantine_future_dated/`; tests: a future-dated pull is never selected (and the day itself still counts), and the real snapshot folder holds none; the producing test now renders from the tracked page's data with no database.

## Part 2. D2: G2 history from the forecast log's series

`latest_vintage_item_history()` gives the demand history behind the Max-Min percentile from the latest log vintage's own series and fit window: the saved fit series when the vintage's metadata records one (hash-checked, vintage 3 on), else `processed_all_divisions_monthly_qty.csv` cut to `fit_first_month`..`fit_last_month` (vintage 2: 2024-02 to 2026-08, 31 months; the file says so in the info and is not hash-verified for vintages 1 and 2). It stops when an item does not have exactly `fit_n_months` months. The method and every parameter are unchanged. Before, PEM101 read the older pilot file (2024-01 to 2026-07; 32 items had no history) and PEM103/PEM107 a fixed 2024-01 to 2026-07 window of the raw pull. G2 data and `forecast/inventory.html` rebuilt.

**Old (page of 2026-10-08 08:12, vintage forecast, older history) to new, standard-assumption table at the page's default controls (CONFIRMED by the implementer and the Validator):**

| Division | Items with Min/Max | Total Min | Total Max | Stock value (THB) | Items changed |
|---|---|---|---|---|---|
| PEM101 | 77 to 92 | 460,098.8 to 472,872.3 | 578,656.1 to 592,277.4 | 65,307,227 to 65,587,404 | 36 (15 newly computed, 21 changed) |
| PEM103 | 0 | 0 | 0 | 0 | 0 |
| PEM107 | 4 | 446.2 to 446.2 | 547.8 to 547.8 | 3,320,249 to 3,320,249 | 0 (all 112 histories changed; the four Min/Max did not) |

The 15 newly computed PEM101 items are the stock-policy items that had no history on the page (12 CA items, ST-F-11-0001, ST-F-99-0001, PH-F-99-0001); the page's table lists every item with a computed Min (it does not read `min_max_computable`). The 5 largest changes in Max, PEM101: ST-F-11-0001 new 3,574.9; EEE-F-FL-1040030006 39,569.5 to 41,811.9; EEE-F-FL-1040030005 28,232.8 to 29,628.3; ST-F-99-0001 new 2,285.6; EEE-F-FL-1040030002 47,947.2 to 48,642.7. (The Validator restricted to items with `min_max_computable` true, the 77 of the old table: Min 460,098.8 to 466,411.1, Max 578,656.1 to 584,968.4, 21 items changed; same numbers for those 77 items.) **The calibrated PEM101 section (92 items) is identical before and after (`curve_target` compared as a whole, CONFIRMED by both).** Also changed in the page data: `pipeline_gap_pct` 3.28 to 3.73 (computed from the forecast and history) and the PEM101 data-pulled label (2026-10-05 07:41:11 to 07:41:06, the processed file's pull time). Tests: the page history equals the vintage's series window for every item (tracked page against the series file), the builder cuts the series to the fit window, and a history that is not the vintage's window stops the build.

## Part 3. D1: the operation plan and the material plan rebuilt today

Rebuilt (plan day 2026-10-08, vintage 2) from the rebuilt G2 and the daily pull of **2026-10-08 08:01:01** (stock and backlog; PEM103's backlog rows from the material inputs pulled 2026-10-06 14:49:28; raw-material stock 2026-10-06 14:49, unchanged); `forecast/operation_plan.html` and `forecast/material_plan.html` rebuilt.

**Items (all, counted) and production quantity (counted rows; planned production where an item has a Min and Max, else load), old (plan of 2026-10-06 build, stock pull of 2026-10-07) to new:** CI101 13/12, 844.3 to 843.8; PEM101 165/159, 700,932.6 to 703,699.7; PEM102 26/22, 169.2 to 169.3; PEM103 87/51, 1,305.8 to 1,305.8; PEM104 12/12, 0 to 0; PEM107 136/128, 11,522.3 to 9,018.3; total 714,774.2 to 715,037.0. Item counts did not change; 181 item-month rows (82 items) changed, from the new stock and backlog pulls, not from G2 (PEM101 stock opening and Max, PEM107 opening). **Material plan, order within 30 days / already short:** recorded before 150 / 598 (plan day 2026-10-07); the same old plan on today's date 149 / 600; **new 156 / 584**; materials to order now 600 to 587.

**The four PEM107 stock items' G3 Min and Max equal G2's (CONFIRMED by the implementer, the Analyst and the Validator, largest difference 5e-7):** VT-F-99-010715 13.80 / 16.70, CT-F-99-020503 114.04 / 135.25, CT-F-99-020504 162.42 / 202.78, CT-F-99-020506 155.92 / 193.05 (Min / Max).

**End-to-end check repeated (Analyst) and recomputed (Validator):** vintage 2 in the log, G2 (embedded), G3 and the material plan: match; demand G1 = G2 = G3: 0 mismatches (PEM101 720 cells, PEM103 250, PEM107 560 against G1; G3 forecast equals the log on 1,675 of 1,675 rows); G2 history equals the vintage series for 144 + 50 + 112 items; G2 and G3 now share one stock pull (0 of 96 stock items differ; 48 of 92 differed before); material gross = G3 exploded through the BOM: 0 mismatches on 11,220 material-months (and net, order dates); the pages equal their recorded files (G2 tables, G3 3,512 cells apart from the 7 "no production" items, material 26,928 cells apart from the dashes of flagged materials, both order lists). **Still open, unchanged:** G1 states no vintage and shows no forward forecast; G2's vintage is in its data, not its visible text; the G2 table "items with stock but no forecast" lists items that have a forecast; no item-level reason for closed divisions on G2; the material page says nothing about the 139 omitted finished items and lists PEM104 though nothing is exploded; no link to the material plan from index.html; 7 items labelled "no production" show quantities on G3 (34 cells). **Fixed since 2026-10-07:** G2 vintage and history, the 32 PEM101 items now have a forecast, one stock pull for G2 and G3, vintage gate in the runner.

## Part 4. D3

Recorded in STATUS.md (decisions, 2026-10-08) and METRICS.md ("Max-Min v1 demand input"), with the prompt 5 comparison as evidence and the reason (a level substitution, not a backtest).

## Part 5. target_data.xlsx against the database and the forecast

Sheet "TargetC1005 12-06-2029" (3,200 rows, 28 columns; the latest target version, per the user); an Analyst computed everything from the saved database aggregates (the one session served 20 read-only aggregate queries: cube_Sale_APD by createDate and by forecast_date, its POR-like filter, the database's own target table `Cube_Target_PMIS`, invoiced revenue `cube_revenue`, the catalogue), and a Validator recomputed b, c and d/e for PEM101 and PEM107.

**a. Structure.** Rows per Year: 2026 426; 2027 397; 2028 397; 2029 to 2033 396 each. Business: PEM101 1,185, PEM102 840, PEM104 504, PEM107 260, PEM103 230, PEMC 104, CI101 48, PSS 9, PTS 3, PPS 2, blank 15 (the blank-Business rows are group-company rows of 2026 with no category or type; their Base is 0). Revenue Stream Type: "2. Omni Channel" 2,575, "1. Tendering" 325, "3. Total Customer Solution" 291, "5. PPA /Long Term Contract" 5, "4. Recurring" 3, "6. Investment" 1. Type of Income: "1.1 Sale" 2,920, "1.2 Project" 184, "1.3 Commission & Service" 80, blank 15, one data-entry slip. Blank counts (all years / 2026): PO Receive 28/5, GP 27/5, Revenue-Conting 249/73, GP-Conting 225/72, Revenue-Base 247/73, GP-Base 223/72. 2026 totals (MB): PO Receive 6,552.13, Revenue-Conting 6,462.10, Revenue-Base 2,730.45; Omni rows with a Business: 1,468.74 / 1,349.80 / 1,292.41. "Responsible section / Person": 24 distinct values, 15 blank (counts only).

**b. Units.** "MB" = million baht is supported as an order of magnitude (high confidence): workbook Omni 2026 PO x 1e6 = THB 1,468.7M against the database's Omni PO by createDate 2026 (Actual + MPS, to date) THB 1,162.7M, ratio 0.79 (thousand baht would give 792, billion 0.0008). Ratio database / (workbook x 1e6), Omni then all revenue types, by Business: PEM101 0.757 / 0.801; PEM102 1.523 / 0.515; PEM103 1.262 / 0.812; PEM104 0.193 / 0.299; PEM107 0.742 / 1.661; CI101 1.862 / 1.915 (Business x Product Category ratios range 0.13 to 3.2; PEM101 Fuse 0.78, PEM101 Surge Arrester 0.86). **The August-project lead (98.74 percent for one sales team) is not reproduced** at Business, Business x category or product-type level; the only near hit is an all-division aggregate (all database Omni PO 2026 1,474.29 / workbook Omni PO 1,490.58 = 0.989), a coincidence by the evidence (low confidence). The database's own target table (`Cube_Target_PMIS`, 2026, 93 rows, one reload stamp 2026-10-07, so it does not date the target version): TargetPOAmount is filled only for PEM104 and group-company rows and equals PO Receive there (Omni 306.37 against 308.45, Tendering 69.70 against 69.50, within 0.3 to 1.4 percent); **TargetRevenueAmount (all revenue types) equals the workbook's Revenue (MB)-Conting x 1e6 at Business totals to within 0.005 percent for PEM101, PEM102, PEM104, CI101 and the database's PEM103 rows (which hold PEM107): PEM101 456.410M against 456.411M, PEM103+PEM107 1,002.600M against 1,002.595M, PEM102 327.440M against 327.439M, PEM104 465.230M against 465.227M, CI101 26.190M against 26.191M (the Validator's recomputation; against Revenue-Base the ratios are 0.907 to 1.088).** Split by revenue stream the two differ (PEM101 Omni 407.84M in the database against 416.74M in the workbook, the 8.9M being in Tendering; PEM103 Omni equals Base; PEM102, PEM104 and CI101 Omni equal Conting); the cause of that shift is not determined. So the workbook's Conting is the revenue target the database table carries, and the table's PO target is absent except for PEM104, where it equals PO Receive (0.99999). **The workbook is newer than the database's target table for PO Receive** (database 2026 PO target THB 1,059M, PEM104 and group companies only, against workbook 6,552M).

**c. Dimensions (2026 Omni, createDate, Actual + MPS: 14,725 rows, THB 1,474.3M).** Business follows the pricelist division of the item or the database `division` column, never `sale_division` (pricelist items: pricelist key matches a target Business and Type for 99.37 percent of rows, 99.19 percent of value; database division 98.61 / 96.29; sale_division 1.43 / 6.12); for 31M of items the two disagree and the test cannot choose (undetermined). Product Type: after normalisation and an explicit alias table (all aliases inferred, medium confidence) 13,397 of 14,725 rows (90.98 percent) and THB 1,069.0M of 1,474.3M (72.5 percent) match a target type; on the target side 51 of 65 Omni types match, carrying 95.3 percent of PO. The names differ systematically: the pricelist's "Medium Voltage Surge Arrester" items carry the database type "High Voltage Surge Arrester" (all 128.42M of 2025-26 value), the workbook calls it "MV Surge Arrester". Unmatched target types (PO / Conting / Base, MB): PEMC Mediuam voltage Instrument Transformer 43.93 / 40.53 / 40.53; PEM104 MDB Distribution Board (Type test) 16.67 / 15 / 15; PEM104 IOT Transformer Box 5.42 / 5 / 5; PEMC Low voltage Instrument Transformer 0.50 / 0.46 / 0.46; PEM103 3 Phase DT Smart Transformer and OLTC 1.09 / 1 / 1 each; ten zero-value types (SF6-free GIS and similar). Revenue Stream Type: "2. Omni Channel" = `revenue_type` "Omni Channel"; "1. Tendering" and "3. Total Customer Solution" equal their database strings; "4. Recurring", "5. PPA /Long Term Contract" and "6. Investment" map by name only (inferred). The workbook's Type of Income ("1.1 Sale", "1.2 Project", "1.3 Commission & Service") corresponds by name to the database `revenue` flag ("1.1 Sale Revenue", "1.2 Project", "1.3 Service and Commission"; inferred); of the database's 2026 Omni value 1,002M is "1.1 Sale Revenue".

**d. Measures (Omni, Jan-Sep 2026 actual against the full-year 2026 target, the seven Businesses with a target: PO 1,468.7 / Conting 1,349.8 / Base 1,292.4 MB):** PO by createDate (Actual + MPS) 1,134.4 MB (0.772 of PO, 0.840 of Conting, 0.878 of Base); PO Actual only 860.3 (0.586 / 0.637 / 0.666); delivered by forecast_date, Actual 1,031.3 (0.702 / 0.764 / 0.798), Actual + MPS 1,046.8 (0.713 / 0.776 / 0.810); invoiced (`cube_revenue`, invoice_date; actual_date equal for Omni 2026) 1,077.5 (0.734 / 0.798 / 0.834). **No candidate can be proven to reproduce a target column** (a year-to-date actual against a full-year target cannot prove equivalence, the unit-level ratios scatter widely); direct evidence on column meaning comes only from the database target table (TargetPOAmount = PO Receive for PEM104; TargetRevenueAmount = Revenue (MB)-Conting at Business totals). Plausible pairing (inferred, low): PO Receive with PO by createDate; Revenue with delivered by forecast_date or invoiced. **Conting against Base is UNDETERMINED:** they are equal on 97.6 percent of 2026 Omni rows with both; no tested dimension (Business, stream, Status of Product, Type of Income, Target Customer, Market Segment, AnSoff, Ansoff Matrix, category, company, core product) separates the differing rows; the only structural pattern is the 15 blank-Business group rows (Conting filled, Base 0). The row ratio PO / Base is 1.085 on 92.7 percent of rows with both (meaning undetermined). Pilot types (PEM101, delivered Jan-Sep; target PO / Conting / Base): HV Distribution Fuse Cutout 96.42 against 107.74 / 99.30 / 99.30; MV Surge Arrester 73.13 against 92.80 / 85.53 / 78.87 (actuals depend on the unit definition: forecast-scope items only 78.0 and 63.9).

**e. Forecast link.** Our forecast measures **quantity**, keyed on **forecast_date** months (delivery date), from cube_Sale_APD Omni Channel Actual + MPS, Top-down combination, vintage 2 (run 2026-10-02, fit to 2026-08, target months 2026-09 to 2027-02), **flat per item** (335 of 335 items, 123,114.6 units a month in total). To value it: the pricelist standard price (`Market Price/`, positive for 295 of 335 items, but labelled Q4-2023 / Q1-2024 under a Q3'2026 title, so its vintage is unclear) or the realised price (sale / qty, forecast_date Oct 2025 to Sep 2026); realised is used (pricelist never needed; realised / list median 0.942, value-weighted 0.883). Projection = Jan-Sep actual (forecast-scope items) + Oct-Dec forecast x price, against PO / Conting / Base: PEM101 365.5M -> 0.808 / 0.877 / 0.891; PEM102 67.5M -> 0.573 / 0.633 / 0.685; PEM103 281.3M -> 1.229 / 1.333 / 1.333; PEM107 115.8M -> 0.600 / 0.651 / 0.670; CI101 43.3M -> 1.616 / 1.652 / 1.652 (scope items cover PEM101 85.7 percent, PEM102 37.5, PEM103 82.7, PEM107 63.5, CI101 89.7 percent of the database's Omni delivered value year to date; with all database Omni year to date and scope-only Q4: PEM101 410.0M, PEM107 163.7M). Pilot types (realised price): HV Distribution Fuse Cutout 108.3M (list price 111.2M) -> 1.005 of PO, 1.091 of Conting and Base; MV Surge Arrester 91.2M (94.0M) -> 0.983 / 1.067 / 1.157. **Not supported:** PEM104 and PEMC (no forecast), the non-Omni streams, GP measures, group-company rows without a Business, types with no pricelist item (about 29 percent of Omni value). PO Receive (createDate keyed): the forecast is not keyed on createDate; it supports PO only approximately through the short createDate-to-delivery lag on scope items (median 7 days, p90 31 days; 2025 PO by createDate / delivery by forecast_date 0.999), not validated against a PO-keyed forecast and blind to Q4 orders for 2027 delivery.

**f. Sheet POR (hidden).** 38,800 rows, 22 columns (cube_Sale_APD field names: cmp, division, sale_company, sale_division, handle_by, contractid, productID, category, productTypeName, itemcode, productName, qty, sale, saleGM, cost, cusname, createDate, jobcode, ctr_name, revenue_type, status, PO); createDate 2024-01-01 to 2026-05-08; Actual 37,475, MPS 1,325; 2026 rows 6,017, sale THB 912.06M; all years qty 3,417,683, sale 5,137.10M, cost 3,630.35M. It reproduces **approximately** from `cube_Sale_APD` (createDate in that range, Actual + MPS; restricted to POR's revenue types and divisions the database holds 39,619 rows, sale 6,292.6M: rows 1.021, qty 1.050, sale 1.225 of POR): Omni within 0.5 to 3.6 percent (database larger, widening for 2026, since the table was reloaded and MPS rows turned Actual), Total Customer Solution within 0.4 to 4.6 percent, **Tendering not (database 1.56 to 1.61 times POR)**; `Cube_Sale_APD_2` and `cube_Sale_APD_test` match 2024 only (2025 Omni 0.757 and 0.666 of POR), `cube_Sale_APD_snapshot` has no status column. The extra filter on Tendering and the cut date of the snapshot POR was made from are undetermined. `Backlog_PEM104` (1,138 rows, 22 columns: company, division, ..., deliverydate, plan_deliverydate, revenue, manufacturing_type, revenue_type) and `RRC PEM104` (22,936 rows, 25 columns: contract ... invoice_date, actual_date, ctr_actual_deldate, revenue_type, manufacturing_type; resembles `cube_revenue`, not an exact copy: database / RRC sale 1.229) are counts and column names only.

## Part 6. The six S1/S2 flag changes on the G2 page

The old page was built 2026-10-06 07:35 from the item-level file of 2026-09-29; the new one from the file recomputed in week 4 after the 2026-10-06 pulls (copies of both versions compared; the S1/S2 values of the six items are identical in the later file versions of 2026-10-06 and 2026-10-08).

| Item | Flag | Old | New | Cause |
|---|---|---|---|---|
| HS-F-99-2121N | S1 | true | false | stock in Cube_Inventory_Exact fell from 9 to 0 (pull 2026-10-05 21:41: 0) |
| RS-F-99-070003 | S1 | false | true | stock rose from 0 to 3 (pull 2026-10-05 21:42: 3) |
| EEE-F-FC-5920-383-1000 | S2 | not computable | false (share 0.0) | 0 cube_final batch rows linked to its 37 delivered contracts, now 1 |
| EEE-F-FL-1040030001 | S2 | not computable | false | linked rows 0 to 1 (19 delivered contracts) |
| HS-F-99-2211N | S2 | not computable | false | linked rows 0 to 2 (182 delivered contracts) |
| HS-F-99-2301N | S2 | not computable | false | linked rows 0 to 1 (42 delivered contracts) |

Cause: newer data (stock of the 2026-10-05 pull, cube_final and Cube_CES rows loaded since 2026-09-29), not a change of definition: the S2 definition written down in week 4 (commit 66319d6, METRICS Sec.23 "S2 defined") and the item-code trimming (commit 566fca9) change none of these six (the same values appear in the file before and after them). **Each change follows the current METRICS Sec.23 definition (CONFIRMED):** S1 = on-hand stock above zero in any warehouse (sums 0 and 3 from the saved evidence); S2 is not computable only without a linked batch row, and with one it is the share of delivered contracts that trace to a batch (0 of 37, 19, 182, 42 reach 0.5, so false); the two independent S2 computations agree on all 439 items (test).


# Prompt 7

Checked 2026-10-08 (clock 10:06 to about 12:15, this machine). Decisions of the user, 2026-10-08: D1 where the pricelist division and the database division differ, Business follows the pricelist; D2 no comparison against PO Receive for now, the executive summary will use the revenue target (Revenue-Conting, as held in `Cube_Target_PMIS`) once the matching actual measure is proven; D3 PEM104 and PEMC targets are shown with a remark saying why they cannot be compared yet, nothing is left out silently. Figures come from computations run in this task by the implementer or by independent agents (Analyst) working read-only from the repository and the saved files; their scripts and results are in %TEMP% (`p7_pmis`, `p7_alias`, `g2bak`, `wk7`), outside the repository. One read-only database session was used (15 aggregate or catalogue queries, none failed; the test suite did not connect). The target workbook stays outside the repository; its source path is written nowhere in it.

## Part 1. Tests never touch the database

- **Block (CONFIRMED):** `tests/conftest.py` (existing file, appended): an autouse session fixture makes `pyodbc.connect` and SQLAlchemy's `Engine.connect` raise at once, and sets `SALE_FORECAST_BLOCK_DB=1` for the whole session, so every Python process a test starts inherits it; `src/db.py` (`get_connection`, hence `run_query` and `session`) refuses with `DatabaseBlockedError` when it is set. Every refusal is appended to a log file (the test that was running, from `PYTEST_CURRENT_TEST`, and whether the attempt was deliberate), so an error that code swallows is still counted: the session ends non-zero if any undeliberate attempt was made, and the terminal summary prints the count. Proof test (`tests/test_guards.py::test_the_database_block_refuses_every_way_to_connect`): the project's own helper (`run_query`, `session`), `pyodbc.connect` and `Engine.connect` each raise the block's error (these 4 attempts are the only ones counted as deliberate).
- **Tests that connected before (CONFIRMED by the pull files and the code):** one test, `test_inventory_page_rebuild_still_has_every_note_axis_title_and_disabled_control` (`tests/test_manual_survives_rebuild.py`): it built the inventory page with no data sources, which pulled stock (three divisions) and sales live and saved four files `inventory_page_pull_*` under the day's date in `output/snapshots`. The dates of those files, 2026-09-28, 09-29, 10-02, 10-05, 10-06, 10-07 and 10-08 (four files each), are the days a full suite ran with it (a later run on the same day overwrites the same names, so the number of pulls is higher than seven); the four files dated 2026-11-05 came from the clock-shifted run of 2026-10-02. It was fixed on 2026-10-08 (it renders from the tracked page's data, assertions unchanged). No other test attempted a connection: with the block in place the full suite made **0 undeliberate attempts** (blocked attempts 4, all deliberate). Nothing needed marking as skipped.
- **Failed logins caused by test runs:** none found. Looked in: every run log `output/runs/**/*.json` and `output/runs/*.log`, the daily-job logs, the reports under `output/summary` (searched for "login failed", error 18456/28000, "login timeout", `LOGIN_OR_SESSION_FAILED`); the test pulls all succeeded (the saved pull files hold data). The database's own login audit is not visible to the project.
- **Scratch guard deleted** (the one kept outside the repository in %TEMP%) after the in-repo block was proven. **Full suite run 1: 641 passed, connection attempts 0 (blocked 4, deliberate 4).** Run 2: see below.

## Part 2. The actual paired with `Cube_Target_PMIS` -- UNDETERMINED

**The table (CONFIRMED).** 24 columns: keys (TargetProductID, TargetHandledByID, Year), product hierarchy (ProductLevel, Type, ProductCateID, ProoductCateName [sic], ProductTypeID, ProductTypeName, ProductID, ProductName), Company, Division, RevenueType, amounts (TargetRevenueAmount, TargetRevenueGP, TargetPOAmount, TargetPOGP; decimal), HandledBy (person), TradeProcessName, MarketSegmentName, CustomerSegementName, BaseON, Timestamp. One row is one product-by-person target, by year only (no month); ProductLevel Core or End; `Type` = "Division" and BaseON = "Revenue" in every row. Rows per year (2021 to 2026): 275, 152, 72, 187, 285, 270; distinct people 275, 152, 69, 187, 279, 260; distinct products 87, 65, 27, 54, 75, 81; divisions 10, 8, 6, 12, 19, 16. **RevenueType is blank in every row of 2021 to 2025** and filled only in 2026 (Omni Channel THB 1,385.3M, Tendering 1,185.2M, Total Customer Solution 174.0M, Recurring Revenue Development by MA and SA 25.2M). TargetPOAmount is null in all rows of 2021 to 2025 and filled in 2026 only for PEM104 and group-company rows (THB 1,059M). Revenue target by year (THB): 2.80B, 2.23B, 1.27B, 3.34B, 3.93B, 2.77B. Load stamp 2026-10-07 17:20 on every row (a reload; it does not date the target version). Division labels mix company codes (PPSPPS, PTSPTS, PSSPSS) and "-OLD" tags in 2021 to 2025; the 2025 PEM107-OLD rows hold load-break-switch, recloser and sectionalizer types (THB 322M) that the database types under PEM102.

**Objects that reference it: none (CONFIRMED).** Searched: `sys.sql_modules` definitions (views, procedures, functions) for the table name and `sys.sql_expression_dependencies` for PMIS and target names: both empty. Tables with PMIS or target in the name (all tables, no views): `Cube_Target_PMIS` (created 2026-04-20), `Cube_PMIS_Organize` (2026-04-23; the organisation hierarchy: RevenueStream, Company, DivisionCode, DivisionName; 48 divisions, e.g. PEMCSA = "Sale Admin (PEMC)", PEM105 = a customer-capital and key-account office), `Cube_Invoice_Report_PMIS` (2026-08-25; invoice lines from 2025-10), `Cube_PMIS_Invoice` (created 2019, last modified 2025-11-26; PMIS invoices from 2025-01-02, latest invoice_date 2026-10-14; columns company, division, invoiceid, invoice_date, forecast_date, itemcode, sale, cost, quantity, sale_division, revenue_type). **The database itself stores no pairing of the target with an actual.** Related actual tables: `cube_Sale_APD` (PO by createDate, delivery by forecast_date), `cube_revenue` (invoiced revenue by invoice_date and actual_date, has a company column), the two PMIS invoice tables. The invoice report's `before_vat_amount` per line equals the PMIS invoice sale to within 0 to 1 percent (2.5 lines per invoice; 4,216 lines in 2025, 14,216 in 2026; `amount_baht` is null on 99 percent of lines and 0 on the rest, unusable), so the two are one measure.

**Candidates against the revenue target (CONFIRMED, one Analyst).** 2025 is the only full year every candidate covers; 2024 only for PO by createDate (a) and delivery by forecast_date (b); 2023 for none (cube_Sale_APD holds no 2023 rows for the Businesses the 2023 target has). Business level, six pricelist Businesses together, 2025 actual / target: PO createDate 0.78; delivered by forecast_date 0.95; PMIS invoice by invoice_date 1.00; cube_revenue (company-aware: PEM101 1.04, PEM103 1.16, PEM104 1.99, PEM107 0.90, CI101 0.86; raw 1.44, the difference being cube_revenue's division "101" mixing companies: PEM 511.5M, SBP 387.7M, CI 60.5M, PPD 37.4M in 2025). Per Business the ratios still run from 0.67 to 2.23 for the PMIS invoice (PEM104 2.23, PEM107 0.67), with 22 to 28 percent of Businesses within 10 percent and at most 8 percent of Business x type cells within 10 percent (a third of 2025 target value finds no actual cell with the same type name). Stability over 2024-2025: delivered by forecast_date has median coefficient of variation 0.21 (0.14 after D1), PO createDate 0.29 (0.32); only 2 of 9 Businesses below 0.10. **No candidate reproduces the target; undetermined (high confidence that none does).** Closest: delivered value by forecast_date, then the PMIS invoice; PEM101 is the one Business that fits (b under D1: 0.99 in 2024, 0.98 in 2025), which one Business of nine does not make evidence. Pointers (INFERRED, medium): the target looks like a plan (15 of 73 grouped 2025 target cells are non-round, the rest round figures such as 493.9M and 300M, and the largest cells are round); one cell, NSPC-CEN, equals the cube_Sale_APD Actual total exactly (19,560,817), weak evidence only.

**D1 applied (CONFIRMED):** value (THB M) whose Business changes when the pricelist Business replaces the database division, createDate Actual + MPS: 2024 650.2, 2025 454.2, 2026 174.6 (rows 849, 185, 138); delivered by forecast_date: 614.1, 476.5, 188.5; PMIS invoice: 2025 467.5, 2026 170.2 (main flows 2025: PPS to PEM103 223.5M, PTS to PEM103 82.3M, PPS to PEM101 40.8M, PPD101 to PEM101 26.1M, PPS to PEM107 23.6M). D1 moves the six-Business total ratio for PO createDate from 0.78 to 0.98, delivered from 0.95 to 1.17, PMIS invoice from 1.00 to 1.21; it improves PEM101 (0.96 / 0.98 / 0.95 for PO / delivered / PMIS invoice) and CI101 and worsens PPS and PTS (the target keeps them as their own Businesses) and PEM103 (1.30 delivered); it does not make any candidate reproduce the target. **For the executive summary this means:** until the actual measure is proven, a comparison of the revenue target with any actual is indicative only; the delivered-by-forecast_date measure is the one our forecast can extend (Prompt 6, Part 5e).

## Part 3. Name-inferred type aliases -- for the user to confirm (nothing recorded as fact)

24 of the 2026 Omni workbook types (65 types with a Business) were matched to a database or pricelist type by inference rather than exact (case, spaces and punctuation ignored) equality; they carry **PO Receive 477.9 MB, Revenue-Conting 438.8 MB, Revenue-Base 409.4 MB** (32.5 percent of the Omni PO target of 1,468.7 MB) and link THB 248.9M of database value (2026 Omni PO by createDate, Actual + MPS, counting the shared LED unit once). 28 types (62.8 percent of PO) are exact (13 of those 28 still have THB 161.8M of inferred-linked rows inside their database value); 13 types (4.7 percent, PO 68.7 MB) have no database counterpart (PEMC Mediuam voltage Instrument Transformer 43.9 MB, PEM104 MDB Distribution Board (Type test) 16.7 MB, PEM104 IOT Transformer Box 5.4 MB, two PEM103 variants 1.1 MB each, PEMC Low voltage Instrument Transformer 0.5 MB, seven PEM102/PEM104 types with zero target); on the database side THB 404.4M (27.4 percent) has no workbook counterpart (THB 92.8M inside the workbook's Businesses, 311.6M in Businesses the workbook does not have, e.g. PSP103 173.3M, PSP105 85.3M). The PEMC Business itself matches the database division PEMCSA by name only (`Cube_PMIS_Organize`: PEMCSA = "Sale Admin (PEMC)").

| # | Business | Workbook type | PO MB | Conting MB | Base MB | Database type it was matched to (source), rule | DB 2026 Omni value, THB |
|---|---|---|---|---|---|---|---|
| 1 | PEM101 | MV Surge Arrester | 92.80 | 85.53 | 78.87 | Medium Voltage Surge Arrester (pricelist), MV read as Medium Voltage; plus database name High Voltage Surge Arrester, HV read as MV | 81,484,734 |
| 2 | PEMC | 3 Phase Distribution Transformer | 90.19 | 83.19 | 83.19 | four database "Three Phase ... 22kV" names, many-to-one alias | 59,167,927 |
| 3 | PEM104 | Medium Voltage Switchgear | 89.62 | 82.73 | 60.00 | database "Switchgear", qualifier dropped | 330,000 |
| 4 | PEM101 | LED Street light 20W | 39.75 | 36.63 | 36.63 | "LED Street light" (pricelist) and "LED STREET LIGHT", prefix, many-to-one with #7 and #8 | 26,762,840 (shared) |
| 5 | PEM101 | Fuse Switches Disconnectors | 27.69 | 25.52 | 25.52 | pricelist "Low Voltage Fuse Switch Disconectors", qualifier and the pricelist's misspelling | 9,007,700 |
| 6 | PEM101 | STC | 25.53 | 23.53 | 23.53 | database "STC 123-2000", prefix | 3,450,000 |
| 7 | PEM101 | LED street lights 94W | 24.41 | 22.50 | 22.50 | as #4 | (shared) |
| 8 | PEM101 | LED street lights 2x20W | 21.79 | 20.08 | 20.08 | as #4 | (shared) |
| 9 | PEM104 | Protection Relay | 16.25 | 15.00 | 15.00 | database "PQM Panel" (alias) | 1,454,800 |
| 10 | PEM102 | 24kV Solid Recloser | 15.79 | 14.55 | 14.55 | "22kV Recloser" and "Recloser 22kV", 24kV Solid read as 22kV | 13,111,550 |
| 11 | PEM101 | LV Surge Arrester | 7.74 | 7.13 | 7.13 | Low Voltage Surge Arrester, LV read as Low Voltage | 17,023,092 |
| 12 | PEM101 | LV Capacitor | 6.80 | 6.26 | 6.26 | Low Voltage Capacitor | 1,861,806 |
| 13 | PEMC | 1 Phase Distribution Transformer | 3.58 | 3.30 | 3.30 | database "Single Phase (22kV Low Loss)" (alias) | 4,238,850 |
| 14 | PEM101 | SLOC/D | 3.26 | 3.00 | 3.00 | database "SLOC/D 125-630", prefix | 330,000 |
| 15 | PEM101 | Photo switch 220V 30A | 2.71 | 2.50 | 2.50 | pricelist "Photo Control Switch" (alias; the database name is equal) | 2,377,960 |
| 16 | PEMC | Mediuam voltage Surge Arrester | 2.46 | 2.27 | 2.27 | Medium Voltage Surge Arrester, spelling fix | 1,134,540 |
| 17 | PEM101 | MVCapacitor | 2.17 | 2.00 | 2.00 | Medium Voltage Capacitor, MV read as Medium Voltage | 947,250 |
| 18 | PEM104 | Unit substation 24kV 500 - 1000 kVA | 2.08 | 0 | 0 | database "Unit Substation", prefix | 12,056,720 |
| 19 | PEMC | Mediuam voltage Fuse Cutout | 1.12 | 1.03 | 1.03 | "High voltage distribution Fuse cutouts", medium read as high | 1,052,898 |
| 20 | PEM102 | Spare Part & Raw Material PEM102 | 1.09 | 1.00 | 1.00 | "Spare Part and Raw Material (PEM102)", & read as and | 12,857,025 |
| 21 | PEM107 | VT Outdoor Power supply VExL-24,VExL-36 | 1.09 | 1.00 | 1.00 | "Voltage Transformer Type VExL" (alias) | 186,682 |
| 22 | PEM104 | Control Box for Communicate | 0 | 0 | 0 | database "Control Box", prefix | 14,400 |
| 23 | PEM102 | Maintenance | 0 | 0 | 0 | "Maintenance Service", prefix | 20,000 |
| 24 | PEM102 | 36kV Solid Recloser | 0 | 0 | 0 | pricelist "33kV Recloser" (alias; no 2026 value) | 0 |

The weakest inferences (decide first): HV read as MV (#1, #19), 24kV Solid read as 22kV (#10), "Medium Voltage Switchgear" to "Switchgear" (#3, PO 89.6 MB for THB 0.33M of value), the many-to-one groups (the three LED wattage types to one database type; the PEMC three-phase transformers), PQM Panel to Protection Relay (#9), and the PEMC Business alias. Two items carry a policy flag: #5 moves to an exact type if types are linked by database name instead of pricelist type; #15 and #17 become exact on the database name. Differences from the earlier count: the same 4 of 15 exact PEM101 types and 10 of 11 PEM107 types as before; one zero-value type (#24) is now counted as inferred.

## Part 4. Today's 12:00 run and the PEM107 production drop

**The 12:00 run of 2026-10-08 (confirmed: Task Scheduler events and run log `daily_stock_20261008T120013.json`).** Task Scheduler launched `SaleForecast_PostingDelaySnapshot` at 12:00:01 and it finished at 12:00:13 with return code 0. The run's status is `skipped_success_exists_today`: a successful run of today (20261008T080029, published, finished 08:01:13) already existed, so the run did nothing, committed and pushed nothing, and made no database connection. Because it skipped before the publish stage, it did not need to pull; the publishing clone's HEAD is nevertheless the latest commit (91997b4, the commit pushed before the run) and its tracked files are clean (confirmed: `git log` and `git status` read-only). Whether the clone's own pre-run pull fetched 91997b4 cannot be told from this log (inferred: the clone holds 91997b4, so it was pulled by 12:00 or earlier).

**PEM107 production, 11,522.3 to 9,018.3 units (-2,504.0; counted rows; planned production where an item has a Min and Max, else load), 2026-10-06 build against the rebuild of 2026-10-08 (CONFIRMED, file comparison):** 13 of 128 counted items changed. **Two items make 98 percent of the change: RS-F-99-090003 -2,000.0 (backlog due 4,000 to 2,000; production 4,001.7 to 2,001.7; forecast 2.1 unchanged) and VT-F-99-010303 -500.0 (backlog 1,516 to 1,016; production 1,521.6 to 1,021.6; forecast 9.4 unchanged); RS-F-99-090003 alone is 78.5 percent.** By input: forecast: 3,963.0 to 3,963.0 (no change, same vintage); backlog due (orders received, not yet delivered, from Cube_CES Status Backlog): 8,072 to 5,566 units (-2,506), all of the drop, in 10 items (the two above, RS-F-99-041007 12 to 0, RS-F-99-041008 18 to 6, VT-F-99-010203 229 to 227, CT-F-99-020505 31 to 28, and increases for CT-F-99-020504 43 to 58, CT-F-99-020524 6 to 9, CT-F-99-020510 15 to 18, CT-F-99-020502 26 to 27); stock on hand: opening stock of the four stock items 58/23/28/1 to 58/20/28/1 (CT-F-99-020503 23 to 20), not enough to move production by itself; G2 Max of the four stock items +1.5 to +3.0 each (CT-F-99-020504 199.8 to 202.8, CT-F-99-020503 133.7 to 135.3, CT-F-99-020506 191.8 to 193.1, VT-F-99-010715 16.4 to 16.7); open production orders: not counted by the plan (`open_orders_counted` false), so they moved nothing. The four stock items together moved +16.1 units (CT-F-99-020504 +10.0, CT-F-99-020503 +4.5, CT-F-99-020506 +1.3, VT-F-99-010715 +0.3); the other nine changed items -2,520.1. In short: the drop is the backlog table losing 2,500 units on two items between the two pulls, not a forecast or Max change; what became of those orders (delivered or cancelled) is not shown by the table (inferred: delivered or cancelled, medium confidence).


# Prompt 8

Checked 2026-10-08 (clock 13:29 to about 15:00, this machine). No database connection (0 sessions); the test suite made none. Pages rebuilt offline from the recorded outputs and saved pulls by the page builders (sales report, Min-Max page with the 2026-10-08 08:01 stock snapshot, operation plan, material plan); the embedded data of the sales report and of the Min-Max page differ from the previous build only by the added fields and the build time (checked by comparing the two). Every figure on a page before the change is unchanged (visible text compared page by page against the committed version: only the replaced lines and the new sections differ). Validator: an independent subagent recomputed every filled value from its source: **MATCH** on every approved text, one wording point (Part 5c).

## Part 1. One bar in task order

- **Bar (CONFIRMED):** `index.html` (hand-maintained, no generator exists: edited directly, this is the one page the instruction "builders produce every text" cannot cover) and the four working pages carry the same labels in the same order: ยอดขายย้อนหลัง | พยากรณ์ยอดขาย ↗ | แผนสต็อก ↗ | สต็อกวันนี้ | แผนการผลิต ↗ | แผนวัตถุดิบ ↗ ‖ สมมติฐานที่ใช้อยู่ | คู่มือการใช้งาน | S&OP Plan (เดิม). On the working pages the bar comes from one function (`reader_values.nav_bar_html`, labels in `reader_values.NAV_TABS`), directly under the "← กลับ…หน้าหลัก" link; the current page's label is bold and not a link; the other labels link to `index.html#trend`, `#stock`, `#assumptions`, `#manual`, `#sop` and to the four page files. A test compares the label sequence of all five.
- **Default tab and fragments (CONFIRMED):** `index.html` opens on ยอดขายย้อนหลัง (the Trend tab, content unchanged, label changed); `#trend`, `#stock`, `#manual`, `#assumptions`, `#sop` open their tab at load and on a change of the fragment; no or an unknown fragment opens the first tab. S&OP Plan (เดิม) is last, content and warning unchanged, not open by default (its text tests now open it first).
- **สต็อกวันนี้ (CONFIRMED):** the existing panel "รายละเอียดสต็อคสินค้า (Inventory Detail)" is the fifth tab; its content is unchanged except that its "← กลับไปหน้า S&OP Plan (Tab 1)" button is gone (it led back to a tab it no longer belongs to; the bar is the way). The S&OP Inventory row's "ดูข้อมูลสต็อคจริง" control opens this tab. The panel reads `data/inventory.json`, the file the daily stock job builds and publishes (`src/daily_stock_job.py`); the daily job tests (56 tests, offline) and the tab test (the panel loads and fills from a copy of the tracked file) pass.
- **Link copies removed (list):** in the S&OP tab, the link on the row title "Sales — ยอดขาย" (to the sales report; the title stays) and the "→ Min/Max Scenario" link inside the Inventory row; in the bar, the old stand-alone `tbPlan` link; on the working pages, the stand-alone "แผนการผลิต" link of the Min-Max page and the "แผนวัตถุดิบ" link of the operation plan page (the bar carries both). Kept: the "Operations — แผนการผลิต ↗" row link in the S&OP tab, because it goes to another address (the manufacturing dashboard), not to `forecast/operation_plan.html`.
- **Layout (CONFIRMED, own headless Edge, temp profile, own PID, screenshots under `output/shots_p8/`, untracked):** at 1440×900 and 390×844 the bar fits (wraps to several rows at 390; not sticky below 600 px so it does not use a fifth of the screen), the separator is visible and no page scrolls sideways except the old S&OP tab at 390 (scroll width 520 against 390: its legacy table, unchanged; listed below).

## Part 2. Freshness lines (CONFIRMED, as rendered)

- Sales report: `ยอดทายรอบ ต.ค. 69 · ใช้ยอดขายถึง ส.ค. 69 · หน้าสร้างเมื่อ 8 ต.ค. 69 14:25` (round = run month of vintage 2, 2026-10-02; month = its last fit month 2026-08; time = build time). The per-section table "ข้อมูลแต่ละส่วนดึงเมื่อ" stays inside the same expandable block.
- Min-Max page: `ยอดทายรอบ ต.ค. 69 · ข้อมูล stock ดึงเมื่อ 8 ต.ค. 69 08:01` (the time is read by the page's script from the stock file when it opens, so the daily job keeps it current; the script's date format equals the shared formatter, tested for four dates).
- Operation plan: `ข้อมูล stock ดึงเมื่อ 8 ต.ค. 69 08:01 · ยอดทายรอบ ต.ค. 69` ("จาก" removed, nothing else changed).
- One shared formatter: `reader_values.thai_month_short` and `thai_datetime_short`; the operation plan page's own functions now call them.

## Part 3. Sales report

- **a. Range (CONFIRMED):** `ยอดขายที่ใช้ทาย ก.พ. 67 ถึง ส.ค. 69` (fit window of vintage 2, 2024-02 to 2026-08). **Removed label:** `ช่วงข้อมูลที่ใช้ได้ (Usable range) 2024-01-01 — 2026-07 (เดือนล่าสุดที่ข้อมูลครบ)`; its start came from config `date_range.start` and its end from `gather_usable_range_end`, the last month of the 128-item pilot file `processed_full_category_sales_monthly_forecastDate.csv` (so it disagreed with the all-division series, which ends 2026-08); the function is deleted. The other label, `ตัวเลขทุกตัวด้านล่างมาจากการทดสอบช่วง 2025-03 ถึง 2026-08`, is the backtest window of the results, agrees with 2026-08 and stays.
- **b. Forward forecast (CONFIRMED):** section 2 `ยอดทาย ก.ย. 69 ถึง ก.พ. 70` (vintage 2's months), sections renumbered 1 to 9; division selector (PEM101, PEM103, PEM107, PEM102, CI101; PEM104 has no forecast item); Types per division / items: CI101 7/13, PEM101 14/144, PEM102 5/16, PEM103 2/50, PEM107 12/112 (40 Types, 335 items, 2,250 cells), a Type's value the sum of its items, no division total, a click or Enter on a Type shows its items. `รหัสที่ยังไม่มียอดทาย 110 รหัส` (82 + 10 + 12 + 6 placeholder and excluded codes of the scope table). **Equality test: YES** (every cell equals the vintage's Item rows; the same vintage as the Min-Max page, tested through `latest_vintage_item_forecasts`, and as the operation plan, every forecast cell of the recorded plan; the Validator recomputed all 2,250 cells: 0 mismatches).
- **c. Pilot groups (CONFIRMED):** Bias = forecast minus actual (`compute_metrics`: `errors = forecast - actual`; tested with a unit case and by recomputing one origin by hand), so negative = under-forecast. Rendered: `▸ Fuse Cutout ทายต่ำกว่าจริงเฉลี่ยเดือนละ 608.4 ชิ้น`, `▸ Surge Arrester ทายต่ำกว่าจริงเฉลี่ยเดือนละ 650.5 ชิ้น`; table MAE 826.4 / 704.7, Bias -608.4 / -650.5 (the group's own forecast over the 7 rolling origins, `series_own` of the pilot view, recomputed at build and equal to the week 4 record). Interpretation (inferred): "MAE per month" of a group is the error of the group total, not the mean of its items' errors (the latter would be 123.8 for Fuse Cutout).
- **d. Forecast against actual (CONFIRMED):** scored months available: **1** (2026-08, horizon 1, 5 divisions, `forward_test_scores.csv`, integrity-checked); table rows 5: CI101 9.8 / -3.7 / 11.0; PEM101 348.8 / -46.0 / 315.4; PEM102 1.2 / -0.2 / 1.2; PEM103 6.1 / -0.4 / 2.9; PEM107 6.1 / 2.8 / 11.3 (MAE, Bias, backtest MAE); the note reads "ตอนนี้มีผล 1 เดือน". The Next Steps line is replaced.

## Part 4. Min-Max page

- **a. Demand note (CONFIRMED):** VERIFY passed: the calibrated PEM101 section's Min and Max use the mean daily demand of the sales series from `CALIBRATION_START` to the end of the last complete month (`maxmin_v1.build_page_inputs`), not the forecast (METRICS.md, "Max-Min v1 demand input"). Rendered under the heading: `Min/Max ส่วนนี้คิดจากยอดขายจริงย้อนหลัง ม.ค. 67 ถึง ก.ย. 69 ยังไม่ได้คิดจากยอดทาย ถ้ายอดขายข้างหน้าเพิ่มหรือลดมาก ค่านี้จะยังไม่ขยับตาม`. (The window, 2024-01 to 2026-09, differs from the vintage's fit window, 2024-02 to 2026-08: the section reads the daily series by delivery date to month end, the vintage the monthly series with a one month margin.)
- **b. List "สินค้าที่มีของแต่ไม่มียอดทาย" (CONFIRMED):** cause: the page's engine marked every item with no computed mean forecast as "no forecast", and only Min/Max items get one, so every confirmed_to_order and conflict item (which all have a forecast in the vintage) was listed, with or without stock. New rule: no positive month in the item's vintage forecast and a positive sellable stock. Counts old to new: PEM101 52 to 0, PEM103 50 to 0, PEM107 108 to 0 (the old lists were exactly the confirmed_to_order plus conflict items: 32+20, 11+39, 78+30; of the old ones with sellable stock, 6, 9 and 29 had a forecast). Items removed: all of the old lists: PEM101 CA-F-99-010207, CA-F-99-010210, CA-F-99-010212, CA-F-99-010306, CA-F-99-010309, CA-F-99-020101, CA-F-99-020102, CA-F-99-020104, EEE-F-FC-1040011002P, EEE-F-FC-5920-383-1000, EEE-F-FC-104010116, EEE-F-FL-1040030101, EEE-F-FL-5920-353-00700, EEE-F-FL-5920-353-04100, HS-F-99-0031 … (52 codes, the confirmed_to_order and conflict items of the page's PEM101 table); PEM103 the 50 transformer items of its table (49 with a forecast, one with none and no sellable stock: three units sit in a warehouse outside its sellable list); PEM107 the 108 RS-, VT- and CT- items of its table. The rule is the same in the page script and its Python mirror (tested, with three items made forecast-less to give a non-empty list). The Python mirror also had a latent difference for an item with an empty forecast (it counted it as having one); aligned with the script.

- **Items removed from the list, in full (old lists, all removed):** PEM101 (52): CA-F-99-010207, CA-F-99-010210, CA-F-99-010212, CA-F-99-010306, CA-F-99-010309, CA-F-99-020101, CA-F-99-020102, CA-F-99-020104, EEE-F-FC-1040011002P, EEE-F-FC-5920-383-1000, EEE-F-FC-104010116, EEE-F-FL-1040030101, EEE-F-FL-5920-353-00700, EEE-F-FL-5920-353-04100, HS-F-99-0031, HS-F-99-0091, HS-F-99-0121, HS-F-99-0151, HS-F-99-0215, HS-F-99-0244, HS-F-99-0271, HS-F-99-0301H22, HS-F-99-0301H33, HS-F-99-0331, HS-F-99-0361, HS-F-99-1031, HS-F-99-1091, HS-F-99-1121, HS-F-99-1242, HS-F-99-1301H22, HS-F-99-1301H33, HS-F-99-1331, HS-F-99-1361, HS-F-99-2031N, HS-F-99-2061N, HS-F-99-2301N, HS-F-99-3303, HS-F-99-2361N, HS-F-99-3061, HS-F-99-3211, HS-F-99-3241, HS-F-99-3301, IS-F-99-0245CE0, IS-F-99-0245CE1, IS-F-99-0245EE0, ST-F-01-0005, ST-F-01-0027, ST-F-12-0006, ST-F-12-0007, FD-F-01-0001, FD-F-01-0002, FS-F-99-0002 ; PEM103 (50): TF-F-99-2104221B1, TF-F-99-2304221B1, TF-F-99-2704221B1, TF-F-99-2804221B1, TF-F-99-2407221B1, TF-F-99-2807221B1, TF-F-99-2104223B1, TF-F-99-2304223B1, TF-F-99-2404223B1, TF-F-99-2504223B1, TF-F-99-2704223B1, TF-F-99-2804223B1, TF-F-99-3204223B1, TF-F-99-3104223B1, TF-F-99-2107223B1, TF-F-99-2307223B1, TF-F-99-2407223B1, TF-F-99-3707223B1, TF-F-99-2105433B4, TF-F-99-2405433B4, TF-F-99-0703811G1, TF-F-99-0704811G1, TF-F-99-10044211Q1, TF-F-99-12044211Q1, TF-F-99-15044211Q1, TF-F-99-19044211Q1, TF-F-99-10074211Q1, TF-F-99-12074211Q1, TF-F-99-15074211Q1, TF-F-99-19074211Q1, TF-F-99-10044211AB1, TF-F-99-12044211AB1, TF-F-99-15044211AB1, TF-F-99-10074211AB1, TF-F-99-12074211AB1, TF-F-99-15074211AB1, TF-F-99-19074211AB1, TF-F-99-21044211H1, TF-F-99-23044211H1, TF-F-99-24044211H1, TF-F-99-21074211H1, TF-F-99-0703811AG1, TF-F-99-0704811AG1, TF-F-99-10044211AF1, TF-F-99-12044211AF1, TF-F-99-15044211AF1, TF-F-99-19044211AF1, TF-F-99-12074211AF1, TF-F-99-15074211AF1, TF-F-99-19074211AF1 ; PEM107 (108): RS-F-99-070007, RS-F-99-070002, RS-F-99-070003, RS-F-99-070004, RS-F-99-070006, RS-F-99-070005, RS-F-99-070019, RS-F-99-070021, RS-F-99-070024, RS-F-99-050128, RS-F-99-050023, RS-F-99-090002, RS-F-99-090003, RS-F-99-090010, RS-F-99-090011, RS-F-99-090030, RS-F-99-090028, RS-F-99-090026, RS-F-99-090041, RS-F-99-090038, RS-F-99-090033, RS-F-99-090027, RS-F-99-090039, RS-F-99-100001, RS-F-99-100013, RS-F-99-130011, RS-F-99-120002, RS-F-99-120006, RS-F-99-040004, RS-F-99-040006, RS-F-99-041001, RS-F-99-041002, RS-F-99-041033, RS-F-99-041003, RS-F-99-041034, RS-F-99-041004, RS-F-99-041015, RS-F-99-041005, RS-F-99-041010, RS-F-99-041006, RS-F-99-041035, RS-F-99-041007, RS-F-99-041008, RS-F-99-010127, RS-F-99-010128, RS-F-99-010122, RS-F-99-010129, RS-F-99-010123, RS-F-99-010124, RS-F-99-010114, VT-F-99-010105, VT-F-99-010203, VT-F-99-010209, VT-F-99-010205, VT-F-99-010202, VT-F-99-010303, VT-F-99-010302, VT-F-99-010615, VT-F-99-010616, VT-F-99-010721, VT-F-99-010701, VT-F-99-010722, VT-F-99-010819, VT-F-99-010818, VT-F-99-010820, CT-F-99-020501, CT-F-99-020514, CT-F-99-020502, CT-F-99-020505, CT-F-99-020507, CT-F-99-020508, CT-F-99-020509, CT-F-99-020510, CT-F-99-020511, CT-F-99-020512, CT-F-99-020513, CT-F-99-020522, CT-F-99-020534, CT-F-99-020523, CT-F-99-020525, CT-F-99-020531, CT-F-99-020527, CT-F-99-020524, CT-F-99-020528, CT-F-99-020529, CT-F-99-020530, CT-F-99-020526, CT-F-99-020535, CT-F-99-020532, CT-F-99-020701, CT-F-99-020702, CT-F-99-020703, CT-F-99-020704, CT-F-99-020705, CT-F-99-020706, CT-F-99-020707, CT-F-99-020708, CT-F-99-020718, CT-F-99-020710, CT-F-99-020709, CT-F-99-020722, CT-F-99-020723, CT-F-99-020714, CT-F-99-020725, CT-F-99-020726, CT-F-99-020717, CT-F-99-020728, CT-F-99-020730

## Part 5. Operation plan

- **a.** Per division (n of the plan's counts, k = items of the group with a positive received order, `backlog_due` summed over the plan's months, from the plan's own item-month input): PEM101 n 21 k 0, PEM103 37 / 0, PEM107 24 / 0, PEM102 10 / 0, PEM104 12 / 0, CI101 none. All six show the zero wording, e.g. `21 รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้`; the other wording (`… ตอนนี้มีออเดอร์ค้าง {k} รหัส`) is built and tested with k from the plan.
- **b. STOPPED by VERIFY:** the recorded reason is not insufficient sales history. DATA_MAP.md: "PEM104's exclusion reason recorded as 'insufficient data' (12 transactions across 17 calendar months …) — SUPERSEDED, kept not deleted. The underlying reason is that PEM104 is made to order by business model — no stock policy is applicable … 'Insufficient data' was a correct symptom, not the cause" (business-confirmed 2026-09-23; STATUS.md Locked Decisions, "Exclusion — PEM104"). The existing line `PEM104 ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock แผนจึงเป็นการผลิตตามความต้องการทั้งหมด` stays; the proposed text `… ยังไม่มียอดทาย เพราะประวัติขายไม่พอ …` is not used.
- **c. VERIFY passed, with a wording point:** the 55 rows labelled ไม่พบการผลิตในระบบ are exactly the not-counted items and are in no division total (page totals equal the recorded totals and the sums over counted rows only: first month PEM101 229,460, PEM103 486, PEM107 4,444, PEM102 73, PEM104 0, CI101 229; the plan stops when one differs). The note is added as approved. **Point for decision:** for 5 of the 55 (PEM101 stock-policy items with a Min and Max) the monthly cells show planned production, not demand, so "ตัวเลขรายเดือนคือความต้องการ" is wrong for them (e.g. one item shows 1,105 in Nov 69 against a demand of 757; the other four show "-" against demands of 32.0, 1.1, 1.7 and 4.3 a month); it is the known low finding "7 items labelled no production show quantities".

## Part 6. Material plan

- **a.** `ฝ่ายที่รวมในแผนนี้: PEM101, PEM103, PEM107, PEM102, CI101` (divisions with a counted quantity in the plan's months); `PEM104 ไม่มียอดผลิตในแผน จึงไม่มีวัตถุดิบ` added.
- **b. VERIFY passed:** every plan item has exactly one reason (a not-counted item is `ไม่พบการผลิตในระบบ`; a counted item with no quantity `ไม่มียอดผลิต`; a counted item with a quantity and no component line in the saved bill of materials `ไม่มี BOM ในระบบ`; the rest are exploded); the page stops if the counts do not add up or differ from the plan's own `n_items_exploded`. Rendered: `สินค้าในแผนการผลิต 439 รหัส คิดวัตถุดิบ 300 รหัส ไม่ได้คิด 139 รหัส: ไม่มียอดผลิตใน 5 เดือนนี้ 83 รหัส · ไม่พบการผลิตในระบบ 55 รหัส · ไม่มี BOM ในระบบ 1 รหัส` (N 439, M 300, K 139, a 83, b 55, c 1; 83 + 55 + 1 = 139; M + c = 301 = `n_items_exploded`), the closed list `รหัส | ชื่อ | ฝ่าย | เหตุผล` holds the 139 items once each.

## Tests

Existing test files extended (no new file): sales report lines, notes, forward table equality (G1/G2/G3), Bias sign, pilot and scored tables (`test_build_report.py`); perturbation of every new source (`test_dynamic_values.py`, whose fixture now perturbs the vintage and the scores through the readers because the forward-test log is hash-checked); no brace left on any page, names exempt from the English-only rule (`test_reader_text.py`); the bar, default tab, fragments, stock tab, layout (`test_index_w3.py`); the data line, demand note, list and bar of the Min-Max page, JS date format against the shared formatter (`test_inventory_page_browser.py`); the list rule in JS and Python (`test_inventory_parity.py`); k, the note and the PEM104 line (`test_operation_plan_page_builder.py`); the coverage counts and the divisions (`test_material_plan.py`). Updated for the new text: the usable-range test, the first-scoring-month assertion, the S&OP-first assumptions, the removed links.

## Found, not done

- The S&OP Plan (เดิม) tab overflows sideways at 390 px (legacy table, content must stay): week 5, low, Claude Code.
- The user manual (`docs/user_manual.md`) still describes five sections and the old two-time line under each title, and has no entry for the new sections; the new ▸ lines are in `config/manual_notes.yaml` only: week 5, medium, Claude Code.
- Row cells of 5 not-counted PEM101 items show planned production under a note that says demand (Part 5c): week 5, low, the user decides the wording or the cells.
- `config/config.yaml` comment says the Medium Voltage Surge Arrester group has 58 items; the scope has 48 (Validator, inferred: 58 is the pricelist count): week 5, low, Claude Code.
- PEM104's "no forecast" line states a reason that DATA_MAP.md marks as the symptom, not the cause: the approved replacement waits for the user's wording (made to order by business model): week 5, low, the user.
- The monthly runner's dry run and the scheduled tasks regenerate the four pages with these builders on their next run; `index.html` has no generator, so a future change to the bar must be made there and in `reader_values.NAV_TABS` together (a test compares them): week 5, low.


# Prompt 9

Checked 2026-10-08 (clock 15:33 to about 17:00, this machine). No database connection; the test suite made none. Decisions of the user, 2026-10-08, are recorded in STATUS.md ("Week 4, prompt 9") with the October plan and the draft criteria.

## Part 1. The original tabs and links, only แผนวัตถุดิบ added

- **Bar (CONFIRMED):** `index.html` was restored from commit 5a735e2 and only the bar was changed: `S&OP Plan (เดิม) | Trend Pricelist Omni 2024–2026 | แผนการผลิต | แผนวัตถุดิบ | สมมติฐานที่ใช้อยู่ | คู่มือการใช้งาน`. S&OP is first and opens by default. แผนวัตถุดิบ links to `forecast/material_plan.html` and takes the style of the แผนการผลิต link (one CSS rule covers both). The bar wraps on a narrow screen (`flex-wrap`, and a rule below 600 px that makes it scroll away instead of sticking) so it fits at 390 px; the original bar was one non-wrapping row.
- **สต็อกวันนี้ removed (CONFIRMED):** the panel is back inside the S&OP tab exactly as at 5a735e2, opened from the Inventory row's "ดูข้อมูลสต็อคจริง" control, with its "← กลับไปหน้า S&OP Plan (Tab 1)" button. The S&OP in-tab links are back: the "Sales — ยอดขาย" row title links to `forecast/sales_report.html`, "→ Min/Max Scenario" links to `forecast/inventory.html`.
- **The four working pages (CONFIRMED):** no bar; "← กลับหน้าหลัก" (sales report) and "← กลับไปหน้าหลัก (Dashboard)" (the other three) as before; the Min-Max page's link to the operation plan (`plan-link`) and the operation plan page's link to the material plan (`material-plan-link`) restored in their original places. Every Prompt 8 change outside the bar stays.
- **Removed (list):** `reader_values.NAV_TABS`, `NAV_CSS` and `nav_bar_html`, and their uses in the four builders (the `NAV_CSS` line of the sales report; the bar and its CSS line of the Min-Max page; the bar and the CSS addition of the operation plan page; the bar of the material plan page); in `index.html` (by restoring the file) the tab สต็อกวันนี้ and its button, the links `tbSales` and `tbInv`, the separator, the URL-fragment tab opening (`OMNI_TAB_FRAGMENTS`, the `hashchange` and load handlers, `history.replaceState`, `window.loadInventoryPanel`) and the removal of the panel's back button; tests: the bar-equality test, the "four pages carry the same bar" test, the fragment test, the stock-tab test and the bar layout test of `test_index_w3.py` (replaced by tests of the restored structure), the bar test of `test_inventory_page_browser.py` (replaced by a test that the page has none), and the assertions of `test_operation_plan_page_builder.py` that looked for bar links (back to the original link assertions; the new ones check that แผนวัตถุดิบ is styled like แผนการผลิต). Nothing else used the fragment code.
- **VERIFY (CONFIRMED):** the daily job still feeds the panel: its offline tests (64: `test_daily_stock.py`, `test_daily_noon_skip.py`, `test_daily_stock_page.py`, `test_cfix_inventory_pull.py`) pass, and in my own headless Edge the panel opened from the Inventory row fills 445 item rows from `data/inventory.json` (the file the daily job builds and publishes), the back button returns to the S&OP tab.
- **Layout (CONFIRMED, own headless Edge on a temp profile, screenshots under `output/shots_p9/`, untracked):** at 1440×900 and 390×844 the bar fits (it wraps to two rows at 390), S&OP opens first, no page scrolls sideways at 1440; at 390 the S&OP tab is 520 px wide as it was at 5a735e2 (legacy table, listed below), the other tabs and the four pages fit.

## Part 2. Operation plan page

- **a. (CONFIRMED)** The note under the item table reads `แถวที่ขึ้นว่า ไม่พบการผลิตในระบบ ไม่ได้รวมในยอดผลิตของฝ่าย` (the clause that said the monthly numbers are demand is gone, which also removes the point of Prompt 8, 5c).
- **b. (CONFIRMED)** For a division with no forecast item whose recorded exclusion reason is made to order the line is `{ฝ่าย} ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย`; it applies today to PEM104 (`PEM104 ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย`, followed by `12 รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้`). The reason is read from config, not typed in code: `operation_plan.exclusion_reasons: {PEM104: made_to_order}` (new, with a comment citing DATA_MAP.md Locked Decisions 2026-09-23). The older `divisions_excluded_from_forecasting` text in config still says "data volume" (the superseded reason); it feeds nothing on a page and is left as it is (listed below). A division with no forecast item and no recorded reason, or a division that has forecast items, keeps the general line (tested for PEM102, CI101, PEM103).

## Part 3. The table "เกณฑ์ที่รอกำหนด"

- **Rendered (CONFIRMED, 8 rows, under the first table of the tab, after its heading):** row 1 `ยอดทายดีกว่าวิธีง่ายไหม | MASE ต่ำแค่ไหนถึงผ่าน | ร่าง: ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี | ผู้บริหาร | หลังรอบ 5 ธ.ค. 69`; row 2 `ยอดทายเอียงต่อเนื่อง | tracking signal เกินเท่าไหร่ถึงเตือน | ร่าง: ±4 | ผู้บริหาร | ทุกเดือน`; rows 3 to 8 as approved.
- **Where:** rows in `data/assumptions.json` under the new key `pending_criteria` (schema_version 2); the draft values (`mase_pass` 1, `mase_good` 0.7, `tracking_signal_limit` 4, `decision_date` 2026-12-05) and the verbatim row templates in `config/config.yaml`, block `maxmin_v1` (`pending_criteria_values`, `pending_criteria_rows`), each draft value with its source in a comment (MASE 1 and 0.7: Morlidge's naive-ratio evidence, Gilliland / SAS, "The avoidability of forecast error, Part 4", and Hyndman 2006 for MASE on intermittent demand; ±4: the common tracking-signal control limit, APICS / CPIM practice; drafts pending the user). The builder is `maxmin_v1.pending_criteria_rows` (the date by the shared formatter `reader_values.thai_date_short`, new beside the others). The tab's script keeps the heading and column names, as it does for the first table, and shows the failure message when the file lacks the key. Rebuilding the file also moved the `updated_date` of the ten existing records from 2026-10-06 to 2026-10-08 (the file's build date); their texts are unchanged. A test checks that no source file other than the builder reads the draft values: nothing passes or fails against them.

## Part 4. STATUS.md

Decisions, the draft criteria with their research basis, the October plan (nine rows), and the risk are recorded; the plan of 2026-10-05 stays below, marked superseded.

## Tests

Existing files: `test_index_w3.py` (six labels in order and the two page links, S&OP default, in-tab links and back button, the stock panel opened from the row and closed by the back button, no bar on the four pages, layout), `test_inventory_page_browser.py`, `test_operation_plan_page_builder.py` (note text; made-to-order line and its limits; the reason read from config), `test_maxmin_v1.py` (file schema, eight rows, values from config), `test_maxmin_v1_page.py` (the table rendered, the failure message without the key); the first assumptions-tab row count now selects the first table. `test_reader_text.py`: S&OP is read without a click again.

## Found, not done

- The S&OP tab is 520 px wide at 390 px (unchanged legacy table): week 5, low, Claude Code (already in the plan, 2026-10-19 to 10-21).
- `config.yaml` `divisions_excluded_from_forecasting` and the PEM104 entry of `method_selection` still give the data-volume reason that DATA_MAP.md marks as superseded: with the refactor, low, Claude Code.
- The user manual still describes the Prompt 7 structure: with the manual update of 2026-10-19 to 10-21, medium, Claude Code.


## Prompt 10

Baht view of the forecast on `forecast/sales_report.html`, section 2, and baht columns in the forecast-versus-actual table. Run 2026-10-08. Database sessions: 0 of 1 (the saved monthly sale and qty series and the saved raw pull hold everything needed). Test suite: zero database connection attempts.

### Decisions of the user, 2026-10-08

- Price basis (replaces "Price List price"): unit price per item = sum(sale) / sum(qty) of cube_Sale_APD over the 12 most recent complete months inside the fit window of the vintage the page uses; no quantity in those months, the same over the whole fit window; never sold, the Price List Market Price (label "Standard Price"); none of these, no price (left out of the baht values and counted). Rule and window are in config `report.price_basis`.
- Actual in the forecast-versus-actual table is valued at the same unit price. Baht = units x unit price, no discount.
- The Trend tab keeps createDate (PO receipt date) as its time axis, labelled on the tab, when it is rebuilt in the next task (no code in this task).

### Part 0

Start: `main` clean, HEAD `b9a8edf`, `git pull` already up to date. Full suite before any change: 682 passed, 0 failed, 0 skipped.

### Part 1, prices

The first answer to "which column" was stopped by VERIFY (seven candidate tier columns); the user then chose the sales-based rule above.

- Latest vintage 2, fit window 2024-02 to 2026-08, price window 2025-09 to 2026-08 (12 months). Items with a forecast: 335. Priced from the 12-month window 277, from the whole fit window 57, from Market Price 1 (`TF-F-99-10044211AF1`), without a price 0. Items without a price: none. Items priced 0: none.
- Market Price column found by header text per sheet: PEM101-Version 2 P, PEM102-Version 2 Q, PEM103-Version2 P, PEM104 Q, PEM107 CT-Version 2 Q, CI101 Q. **Deviation:** the label "Standard Price" is in row 4 of that column (directly under the row-3 header "Market Price/"), not row 2 as the prompt says; config `market_price_label_row` is 4.
- Spot check, seed 20261008, 10 items (the one Market Price item plus 9 drawn): 10 of 10 match. Market Price item: builder 112,500, Excel `PEM103-Version2!P84` 112,500. The nine sales-priced items equal sum(sale)/sum(qty) recomputed from the saved raw pull (`raw_all_divisions_sales.csv`, independent of the monthly series the builder reads): HS-F-99-0211, CT-F-99-020503, RS-F-99-041008, EEE-F-FL-5920-353-04100, DS-F-99-0312, FS-F-99-0003, CT-F-99-020531, EEE-F-FL-1040030103, HS-F-99-0301. All 334 sales-priced items match the raw pull, not only the 10. (Confirmed from data: recomputed.)
- The monthly series and the raw pull are the pulls of 2026-10-05 and the log of vintage 2 is of 2026-10-02; prices use the former.

### Part 2 and 3, page

Switch "หน่วย: ชิ้น · บาท (มีผลกับตารางในส่วนนี้เท่านั้น)", default ชิ้น; baht mode shows the label, the explanation, the summary table "ยอดทายรวมรายเดือน (บาท)" (five divisions and "รวมทุกฝ่าย"), the per-Type table with "รวม {ฝ่าย}", item rows on expansion. The pieces notes are not shown in baht mode (they say the numbers are pieces). The missing-price line with its collapsed list appears only when n > 0 (n = 0 now; tested by removing a price). The baht numbers are rounded to whole baht at item and month level, so every total is a sum of whole numbers and adds up exactly on the page. The first forecast month's "รวมทุกฝ่าย", as rendered: **77,578,311** (every month of the vintage is equal, the forecast being flat). Forecast-versus-actual: three columns added; one rendered row: `PEM101 | ส.ค. 69 | 348.8 | -46.0 | 315.4 | 28,868,690 | 40,099,829 | -11,231,139`. Sign: ต่าง = ยอดทาย − ยอดจริง, the sign of Bias (the mean of forecast − actual units of the same items equals the recorded Bias for every row, checked in the build and in a test): sign convention verified. The table sits in a scroll box (the three columns made the table 532 px wide at 390 px).

### Part 4

- a. Identities: for each division and month Σ items = Σ Types = division total, and Σ divisions = รวมทุกฝ่าย, exactly (36 checks, integers). Holds.
- b. Equality: the 335 items' forecast units behind the baht values equal the unit view, G2 (`latest_vintage_item_forecasts`) and G3 (`latest_vintage_forecast`), vintage 2 in all, maximum absolute difference 0.0. Holds.
- c. Back-check sum(actual qty x unit price) / sum(actual sale) from the saved monthly series, per division and year (2026 covers January to August). Inside the 12-month window it is 1.000 for every division. None outside 0.5 to 1.5.

| division | 2024 | 2025 | 2026 | all months |
|---|---|---|---|---|
| CI101 | 1.093 | 1.025 | 1.010 | 1.059 |
| PEM101 | 1.014 | 1.010 | 0.999 | 1.008 |
| PEM102 | 0.960 | 0.996 | 0.999 | 0.986 |
| PEM103 | 0.946 | 0.991 | 1.001 | 0.976 |
| PEM107 | 1.010 | 1.007 | 0.983 | 1.004 |
| all | 1.001 | 1.007 | 0.998 | 1.002 |

  The check is part of the build (config `back_check_low`/`back_check_high`); a value outside stops it. Items with actual sale and no price: 0.
- Share of the first forecast month's baht from Market Price items: 0 baht, 0.0 percent (the one Market Price item has a forecast of zero in that month).
- d. Worked examples (seed 20261008 for the two drawn; months 2026-09 to 2027-02; the forecast is flat so every month is the same):

| item | division / Type | units per month | unit price (source) | baht per month | Type total per month | division total per month |
|---|---|---|---|---|---|---|
| EEE-F-FC-1040010002 | PEM101 / High Voltage Distribution Fuse Cutout | 2,526.7676 | 1,872.3752 (12-month window) | 4,731,057 | 10,067,494 | 33,257,728 |
| HS-F-99-02110 | PEM101 / Medium Voltage Surge Arrester | 363.3064 | 728.5337 (12-month window) | 264,681 | 9,153,870 | 33,257,728 |
| HS-F-99-0213 | PEM101 / Medium Voltage Surge Arrester | 265.4534 | 798.9714 (12-month window) | 212,090 | 9,153,870 | 33,257,728 |
| HS-F-99-0215 (drawn) | PEM101 / Medium Voltage Surge Arrester | 397.0113 | 1,124.7778 (12-month window) | 446,549 | 9,153,870 | 33,257,728 |
| CT-F-99-020503 (drawn) | PEM107 / Current Transformer Type COL | 21.5293 | 12,029.7685 (12-month window) | 258,992 | 5,110,283 | 10,874,992 |

  Hand check: 2,526.7676 x 1,872.3752 = 4,731,057 (rounded).

### VAT (prove, report only)

- **Sale excludes VAT: NOT PROVEN.** Evidence in saved files only (no database session was used): (1) sale − cost = saleGM within 1 baht in 245 of 245 saved rows that hold the three columns (`raw_44groups_full_columns.csv` 131, `task5_actual_mps_full_columns.csv` 11, `task5_normal_contracts_sample.csv` 103); this is a small sample and an identity that holds with or without VAT if cost is on the same basis. (2) Against Cube_CES `ActualPrice` for the same contract and item with equal quantity (6,545 pairs, saved files `phase136_valrecompute_*`): sale within 1 baht in 99.5 percent of pairs, sum(sale) / sum(ActualPrice) = 1.0107; no pair is near a VAT-inclusive ratio. Both are the same upstream source, so this shows consistency, not correctness (CONVENTIONS.md). (3) The VAT-inclusive amount in the database is `Cube_Invoice_Report_PMIS.invoice_total_incl_vat`; only its column name is saved, not its rows. Proof needs one read-only session: the share of cube_Sale_APD rows (page scope) with |sale − cost − saleGM| ≤ 1, and the ratio of the sale of a contract to that invoice total.
- Price List Market Price includes VAT: **not stated** (no cell of the visible sheets mentions VAT or tax; the only hits for a text search were the word "Private").
- The method was not changed on these results.

### Validator

An independent subagent recomputed every baht cell from the raw pull, the forward-test log and its metadata, the score file and the Price List file, without seeing these figures: 2,316 table cells compared (summary table, five per-Type tables with item, Type and division rows) and 15 scored-table baht cells; 0 discrepancies. Six cells (PEM101 "Photo Control Switch ", a Type whose name in the log ends in a space) were flagged only because the Validator's own script stripped the space; the implementer checked that the Type's value, 120,488, equals the sum of its items. Counts of items without a price (0) and priced at Market Price (1) agree. Verdict: MATCH (independent recomputation, not a re-read of the same query).

### Rendering (own headless Edge, temp profile, own PID closed)

1440x900 and 390x844, both modes, PEM101 and PEM107 selected: text and layout read from the screenshots in `output/shots_p10/` (untracked); no horizontal page scroll at 390 px in either mode (page width 390); the scored table scrolls inside its own box; no console error. The division selection is kept when the unit is switched (test).

### Tests

New: in `test_build_report.py` (switch and texts verbatim and default, config rule and Market Price column per sheet, every unit price against the raw pull, every baht cell and every identity, a perturbed price and a removed price with the missing-price line and list, the baht columns and note and sign, the back-check and its stop) and `test_sales_report_browser.py` (switch, selection kept in both modes, Type expansion, no horizontal scroll at 390 px in both modes). Two existing assertions changed: the unit tables carry no total row (the baht tables do), and the scored-table row pattern takes the three new cells.

### Found, not done

- Prices follow the forecast-date key and the pull of 2026-10-05; a price drift against the recent months is not reflected in the forecast months (said on the page).
- Proof of VAT treatment needs one read-only session (above): the user to approve, medium, Claude Code.
- The Trend tab's time axis (createDate) is recorded for the next task: next task, medium, Claude Code.


## Prompt 11

The Trend tab of `index.html` rebuilt from current data by `src/build_trend_tab.py` (new file, approved), the VAT evidence for `cube_Sale_APD.sale`, one line on the forecast page, the decisions recorded. Run 2026-10-08. Database sessions: 1 of 1 (the Trend pull, the VAT queries and the Validator's own three statements, one connection, no retry). The test suite made no connection.

### Part 1, the tab

- **Builder.** `--pull` (one session: item x day x status aggregate, most frequent product name per item, completeness query) and `--build` (saved pull and Price List to the data of the tab, written into `index.html` between the markers `/* TREND-DATA-BEGIN */` and `/* TREND-DATA-END */`; a second run changes nothing). The monthly runner pulls it in step 1 (its own session, a failure keeps the earlier pull) and builds it in new step 7e, whose gate stops the run when the tab's totals differ from the completeness query; `index.html` is now one of the run's generated files. Scope, cut-offs and file names are in config `trend_tab`.
- **Items.** 445 codes (446 rows; one CI101 code has two rows). No code is on more than one visible sheet; the prompt's "136 CT codes on both PEM103 and PEM107" does not hold for the visible sheets (PEM107's own sheet has 136 codes; PEM103's has 87). The hidden `PEM103-Version 2` sheet is excluded. The three codes of the August build that left the Price List are gone (one ok, two nodata).
- **Pull.** 2026-10-08 17:25; createDate 2024-01-03 to 2026-10-08; 34 months, 33 complete (2024-01 to 2026-09).
- **Totals = completeness query: YES, exactly.** 38,298 rows, Σqty 3,630,615, Σsale 2,145,775,776.55. Σ daily = monthly per item; Σ items = KPI "ยอดขายรวม" 2,145.8 million.
- **Classes.** Smooth 49, Erratic 34, Intermittent 172, Lumpy 86, ไม่มียอดขาย 104 (August: 50, 39, 172, 79, 107 + 1 "no sales 31 months"). Of 29 class changes: the base grew from 31 to 33 months; late postings restated the earlier months of 69 items; two items had their first sales.
- **Agreement with the forecast pipeline's class** (the same rule on its series, forecast-date key, 2024-02 to 2026-08, 335 items): 289 of 335 = 86.3 percent. Differences: Intermittent in the pipeline and Lumpy here 20, Erratic and Lumpy 10, Lumpy and Intermittent 7, six smaller. The recorded class file of an earlier phase (128 items, other window) agrees on 93 of 128.
- **Spec badges** ok 309, conflict 16, nospec 16, nodata 104 over 445 codes; August 2026: 309 / 16 / 16 / 107 over 448. Explained item by item: the three removed codes; DS-F-99-0310 ok to conflict and DS-F-99-0311 conflict to ok (their database names changed); EEE-F-FL-5920-353-06600 nodata to ok (first sale). 26 database names differ from August's (most frequent name changed with new sales, or repeated spaces collapsed). One item has a tie in its most frequent name (alphabetical first taken).
- **Text.** Rendered under the tab bar: "ยอดนับตามวันที่รับ PO จึงไม่เท่ากับยอดในหน้าพยากรณ์ ซึ่งนับตามเดือนที่ต้องส่งของ · ข้อมูลถึง 8 ต.ค. 69". The heading now shows "Price List Q3'2026 (445 รหัส)", the legend, the faded-month hint and the axis range hint are filled from the data. The yellow note about the S&OP tab was left as instructed; typed values left in it: "Pricelist Q4'2025 426 รหัส", "ม.ค.–ก.ค. 2026", "เดือน ส.ค. 2026 ยังไม่จบเดือน", "ม.ค. 2024 – ก.ค. 2026" (the last two now contradict the computed 33 months; the user to decide). The caption of chart 4 keeps its typed verification date 2026-09-24 ("no code counted twice"), which the build now also confirms (no code on more than one sheet).
- **Rendering** (own headless Edge, temp profile, own PID closed): 1440x900 and 390x844; KPIs (445, 2,145.8, 49, 34, 172, 86, 104), charts 1, 2 and 4, the SKU table (400 rows shown), the drill-down from a month to days (September 2026: 60 bars) and the SKU modal, the badge tooltips (database names; spec details on Check spec), the faded last month (opacity .45); no console error; no horizontal page scroll at 390 px. Screenshots in `output/shots_p11/` (untracked).

### Part 2, VAT (one session, aggregates only)

- Scope rows: |sale - cost - saleGM| <= 1 for 38,298 of 38,298 (100 percent; within a cent too; no nulls).
- Cube_Invoice_Report_PMIS: 18,432 rows, invoice dates 2025-10-08 to 2026-10-08, one revision value. Non-null: `invoice_total_incl_vat` 100 percent, `line_total_incl_vat` 99.97 percent, `vat_amount` 99.99 percent, `before_vat_amount` 99.97 percent. Lines with VAT = 7 percent of the before-VAT amount: 17,881 of 18,212 (98.2 percent); the sums are not consistent with that (vat 7.5 million, before VAT 2,075.9 million), cause not found.
- Join on contract and item: scope pairs 37,861; invoice pairs 9,039; joined 3,256; joined with equal quantity 3,218.
- **Sale / VAT-inclusive total: median, p10, p90 and the share within 0.93 to 0.94 were not obtained.** The four statements failed with "'PERCENTILE_CONT' is not a recognized built-in function name"; the session was spent. **Verdict: NOT PROVEN** (testable). Needed: one more read-only session with a bucketed histogram of sale / line_total_incl_vat for the 3,218 equal-quantity pairs.
- Recorded in DATA_MAP.md with the user's statement; no method changed.

### Part 3

Every item's forecast is identical across the vintage's six months (335 of 335, from the log). The line "ยอดทายทุกเดือนเท่ากัน เพราะวิธีทายตอนนี้ให้ค่าระดับเดียวกับทุกเดือนข้างหน้า ยังไม่คิดช่วงขายดีขายน้อยตามฤดูกาล" is under the tables in section 2 in both unit modes; the build leaves it out when any item differs (tested).

### Part 4, record

STATUS.md: the two decisions, the Part 2 verdict, and the plan row "first model-tuning item after the 2026-12-05 criteria decision": no seasonality (May to October share 52.2 and 53.4 percent for Surge Arrester, 56.9 and 55.2 for Drop-out Fuse Cutout, DATA_MAP.md entry 45, audit Part D; August 2026 PEM101 forecast 28,868,690 against actual 40,099,829 baht = 28.0 percent below, the scored table of the sales report, Prompt 10). METRICS.md Sec.47; DATA_MAP.md.

### POR cross-check

Sheet POR of the target workbook (no row or customer value copied): rows 2024-01-01 to 2026-05-08. Omni Channel, Actual + MPS, Price List items, by month of createDate, 29 months compared. The tab is higher than POR in every month. Sale ratio (tab / POR) 1.0004 to 1.121 for 2024-01 to 2026-04, total ratio 1.041 (largest difference 8.24 million, 2024-03); quantity ratio 1.000 to 1.069. 2026-05 up to the 8th: sale 2.75, qty 10.5 (the workbook holds 1,803 pieces for those days, the database 18,858). Not explained here: the likely reading is back-dated lines posted after the workbook was made, not verified. 6,661 Omni Actual + MPS rows of POR are for codes not on the Price List.

### Validator

Phase 1 wrote its own SQL from the stated scope without seeing the builder (the three statements ran in the same session); phase 2 recomputed from those results and the Price List, in its own code: **MATCH** on 60,520 item-month cells (445 items x 34 months x four measures), division x month (6 x 34 x 4), month totals, grand totals (diff 0.0), daily to monthly sums (22,578 daily rows), ADI, CV2 and class of all 445 items, spec status of all 445 items (the database name read from the implementer's saved names file, so not independent for that one input), and the item and sheet lists. Independent of the tab code, not of the database.

### Tests

Existing files extended: `test_index_w3.py` (the approved line verbatim and first in the tab; typed values replaced by data and following a changed source; the line hidden without a pull date; one fixed example per badge outcome including kV against V and a comma number; classes, months and totals from a fixture; the stop when totals differ from the completeness query; markers and a second run unchanged; the embedded data equal what the builder makes from the saved pull), `test_monthly_refresh.py` (step 7e after the vintage gate, `index.html` a generated path, the staged copy, the stop), `test_build_report.py` and `test_sales_report_browser.py` (the flat line present only when the VERIFY holds, visible under the tables in both modes). `test_dynamic_values.py`: the perturbed build keeps the real price window and skips the back-check and the baht columns it cannot score. The old hash test of the embedded data became the rebuild-equality test.

### Found, not done

- VAT distribution (second aggregate session): the user to approve, medium, Claude Code.
- Yellow note of the Trend tab: typed August 2026 month and range: the user to decide, low, Claude Code.
- Chart 4 caption's typed date 2026-09-24: low, Claude Code.
- POR difference in the days of May 2026 and the higher Trend values in earlier months: cause open, low, Claude Code with the target owners.
- The user manual (`docs/user_manual.md`, the Trend chart note) still shows the typed months "ม.ค. 2567 - ส.ค. 2569"; `config/manual_notes.yaml` now holds the line with the first and last month as values the tab fills: with the manual update of 2026-10-19 to 10-21, low, Claude Code.


## Prompt 12

Accuracy against Naive on the forecast page, the Trend tab's typed months, the reader-text rule, and the list of confusing Thai terms. Run 2026-10-09. Database sessions: 0. The test suite made no connection. New files: none.

### Parts 1 and 2, measures and verdicts (METRICS.md Sec.48)

Naive = the last observed month before each origin, all six horizons; the cells are the main table's item x origin cells (2,328 in all). Relative MAE = sum of the model's window MAE / sum of Naive's over the same cells; Horizon 3 = the third month ahead only; Tracking Signal = sum e / mean |e|, e = forecast - actual of the division's (group's) total at horizon 1, 7 backtest origins in order then the scored forward month(s) (8 points per row). Pilot groups: the Type series (sum of the group's items), the Type's Combination forecast (the pilot-group block's series), Naive = the series' last month; 7 cells. Thresholds from `maxmin_v1.pending_criteria_values` (draft). Sanity: the model MAE recomputed from the cells equals the main table's MAE for every division (difference below 1e-14) and the cell count equals n_scored; the build stops otherwise.

| division / group | cells | MAE | MAE (Naive) | Relative MAE | verdict | Relative MAE (Horizon 3) | verdict | Tracking Signal (points) | verdict |
|---|---|---|---|---|---|---|---|---|---|
| PEM101 | 1,000 | 315.43 | 394.52 | 0.7995 | ผ่าน | 0.8299 | ผ่าน | -3.33 (8) | ปกติ |
| PEM103 | 343 | 2.85 | 2.74 | 1.0406 | ไม่ผ่าน | 1.0643 | ไม่ผ่าน | -7.84 (8) | เตือน |
| PEM107 | 782 | 11.32 | 13.09 | 0.8644 | ผ่าน | 1.0505 | ไม่ผ่าน | 1.28 (8) | ปกติ |
| PEM102 | 112 | 1.19 | 1.29 | 0.9233 | ผ่าน | 0.8844 | ผ่าน | -1.39 (8) | ปกติ |
| CI101 | 91 | 11.04 | 13.33 | 0.8278 | ผ่าน | 0.7692 | ผ่าน | 6.72 (8) | เตือน |
| Fuse Cutout | 7 | 826.35 | 888.76 | 0.9298 | ผ่าน | 0.8256 | ผ่าน | -4.71 (8) | เตือน |
| Surge Arrester | 7 | 704.73 | 655.67 | 1.0748 | ไม่ผ่าน | 0.9856 | ผ่าน | -6.79 (8) | เตือน |

Forward-test month 2026-08 (horizon 1; Naive = the last month of the vintage's fit window, 2026-07):

| division | items | MAE | MAE (Naive) | Relative MAE |
|---|---|---|---|---|
| CI101 | 13 | 9.76 | 9.08 | 1.075 |
| PEM101 | 144 | 348.76 | 401.00 | 0.870 |
| PEM102 | 16 | 1.17 | 0.75 | 1.559 |
| PEM103 | 48 | 6.11 | 2.65 | 2.308 |
| PEM107 | 112 | 6.10 | 4.21 | 1.451 |

Report only, share of items whose own horizon-1 Tracking Signal is beyond plus or minus 4 (same 8 points): CI101 6 of 13 (46.2 percent), PEM101 64 of 144 (44.4), PEM102 5 of 16 (31.3), PEM103 37 of 48 (77.1), PEM107 52 of 112 (46.4); pilot groups' items (Validator): Fuse Cutout 5 of 10, Surge Arrester 29 of 48. With 8 points an item's signal is noisy.

Readings of the draft criteria (not conclusions): PEM103 and the Surge Arrester group do not beat Naive over the backtest; PEM107 beats it over all horizons but not at Horizon 3; CI101, PEM103, Fuse Cutout and Surge Arrester show a Tracking Signal beyond the limit (a lasting lean one way). The forward month is one month: no verdict is drawn from it.

### Part 3, page

Block "เทียบกับร่างเกณฑ์" (heading, columns, five lines and verdict words verbatim; the thresholds in the lines are filled from config) in the Results section after the pilot-group block, seven rows. Forecast-versus-actual: "MAE (Naive)" and "Relative MAE" after MAE; a new scored month adds its row. The forecast-versus-actual table keeps its scroll box (390 px: no horizontal page scroll).

### Part 4, assumptions tab

Row 1 as rendered: "ยอดทายดีกว่าวิธีง่ายไหม | Relative MAE ต่ำแค่ไหนถึงผ่าน (MAE ของเรา ÷ MAE ของ Naive) | ร่าง: ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี | ผู้บริหาร | หลังรอบ 5 ธ.ค. 69". Config keys `mase_pass`, `mase_good` renamed `relative_mae_pass`, `relative_mae_good` (values 1 and 0.7); the row text's braces follow; the comment's source line names Morlidge's ratio of forecast MAE to naive MAE. `data/assumptions.json` regenerated (also moves the ten rows' updated date to 2026-10-09).

### Part 5, Trend tab

As rendered at 1440 and 390 px: yellow note "... เดือน ต.ค. 69 ยังไม่จบเดือน แสดงเป็นแท่งสีจาง และไม่รวมในการคำนวณ ADI/CV² (ฐาน 33 เดือน: ม.ค. 67 – ก.ย. 69) ..." (the S&OP sentence, "Pricelist Q4'2025 426 รหัส, Actual อย่างเดียว ม.ค.–ก.ค. 2026", is unchanged as instructed); chart 4 caption "... ตรวจสอบแล้ว (8 ต.ค. 69): ไม่มีรหัสสินค้าใดถูกนับซ้ำข้ามหน่วยธุรกิจ ...". The labels are in the tab's data and use the shared Thai month and date formatter (MMM yy, Buddhist year); the old wording gave Gregorian years.

### Part 6, reader-text rule

`.claude/skills/reader-text/SKILL.md` Language paragraph replaced as approved, the line forbidding a whole English sentence removed; CONVENTIONS.md "Reader-facing text" says the same in one clause. `tests/test_reader_text.py`: the rule "a line over 60 characters with no Thai" now passes when the line before or after has Thai (an English term or sentence with a Thai explanation next to it); fixed examples: an English sentence alone fails, with a Thai neighbour passes, next to another line without Thai fails; every other check is unchanged.

Humanizer run over the new Part 3 text (findings only, approved text unchanged): (1) the last line "ผลมาจากการทดสอบย้อนหลัง และเกณฑ์ยังเป็นร่าง ยังไม่ใช่การตัดสินสุดท้าย" says twice that the criteria are not final (the "not X" tail restates "draft"): suggestion "ผลมาจากการทดสอบย้อนหลัง เกณฑ์ยังเป็นร่าง"; (2) "ดี" is a grade in the second line ("ต่ำกว่า 0.7 = ดี") and "ดีกว่า Naive" a comparison in the same line: one word, two senses, suggest keeping "ดีกว่า Naive" and naming the grade "ดีมาก" or leaving it to the manual round; (3) every line starts with ▸, the project's note style (formatting by rule, weak alone), left as is. No dashes, triads, bold, sales language or chatbot residue found.

### Validator

Own recomputation (the model library only; not the new functions): reproduction of the saved Top-down results exact (2,328 cells match the saved per-cell file, maximum difference 4.5e-13); the criteria table and the forecast-versus-actual table MATCH in every column at the page's rounding. Ambiguity noted: a group's forward Tracking Signal point uses the group's scored items (the Type series' own error is the other reading; no outcome changes).

### Part 7, confusing Thai terms (report only; nothing changed on any page)

58 items. Read-only assessment by a subagent from the visible text of index.html (all tabs, the manual from docs/user_manual.md, the assumptions from data/assumptions.json), the four forecast pages (static text; text filled by script was not seen in a browser) and the reader-text rule. The implementer checked that 40 of the 58 quotes are literal text of the pages and that the other 18 are header rows joined with " | "; the ten ranked quotes are literal. Whether a term confuses a reader is the assessor's judgement (not tested with readers). For the manual and text round of 2026-10-19 to 10-21. The ten most likely to confuse:

1. sales report, 5. ข้อมูลที่ใช้: "PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) นับเป็นยอดขาย เพราะลูกค้าสั่งแล้วจริง" while the Trend tab's glossary says MPS is "ยังไม่เป็นยอดขายจริง": say once, as MPS = open PO (backlog), whether it counts.
2. sales report, 1. บทสรุปผู้บริหาร: "อัตราการส่งมอบตรงเวลาปรับตัวขึ้นจาก 57.8% (2023) เป็น 73.2% ในปี 2026": five names for delivery and the exact-day figure read as on-time: use not-late and exact-day delivery.
3. sales report, 6 and 7: "Top-down Combination คือการพยากรณ์ยอดขายในระดับ "Type" ..." against "เก็บไว้เทียบ ไม่ใช่วิธีที่ใช้" for Combination: define Top-down and Combination separately.
4. index, S&OP tab: "ข้อมูลสมมติ (placeholder)": สมมติ means made-up figures, assumption and "suppose": use placeholder, assumption, formula estimate.
5. sales report, freshness line: "ยอดทายรอบ ต.ค. 69 · ใช้ยอดขายถึง ส.ค. 69": ยอดทาย mixed with พยากรณ์ and Forecast; the run month vs the covered months unclear: forecast, with run month and months covered.
6. index, stock panel: "Available" (quantity minus Reserved, still counting QA warehouses): Available (net of Reserved, incl. QA).
7. sales report, forecast-versus-actual: "ยอดจริง (บาท)": actual units x average selling price, not booked revenue: say so in the header.
8. operation plan: "เทียบยอดผลิตสูงสุดที่เคยทำ" and "119.9% สูงกว่ายอดผลิตสูงสุดที่เคยทำ": basis unclear, over 100 percent reads as a capacity warning: percent of historical peak monthly output (not capacity).
9. operation plan: "ผลิตตามความต้องการ | เติมให้ถึง Max | ผลิตตามสั่ง" (the first and third sound alike; "ประเภทสินค้า" also means Product Type and MTS/MTO): demand-driven build, build to Max, MTO; MTS/MTO.
10. inventory: "Value at risk = ถ้า Min ในระบบสูงกว่าที่จำลอง ส่วนเกินคิดเป็นเงินเท่าไหร่" (the term usually means potential loss) and "Stock value (Σ Min×unit_cost)" (the value of the Min level, not stock on hand): Excess Min value; Value of Min level.

The full list:

| # | page | section | current text | why it may confuse | suggested English term with short Thai explanation |
|---|---|---|---|---|---|
| 1 | forecast/sales_report.html | 5. ข้อมูลที่ใช้ | PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) นับเป็นยอดขาย เพราะลูกค้าสั่งแล้วจริง | หน้า index (แท็บ Trend, นิยามศัพท์) เขียนว่า "MPS = PO ที่รับจากลูกค้าแล้ว อยู่ระหว่างรอส่งมอบ (ยังไม่เป็นยอดขายจริง)" ขัดกับหน้านี้ที่นับเป็นยอดขาย; MPS ในงาน planning ปกติแปลว่า Master Production Schedule. also on: index Trend, คู่มือ | MPS = PO ที่รับแล้วยังไม่ส่ง (open PO / backlog) บอกให้ชัดว่านับหรือไม่นับเป็นยอดขาย และใช้คำเดียวกันทุกหน้า |
| 2 | forecast/sales_report.html | 1. บทสรุปผู้บริหาร | อัตราการส่งมอบตรงเวลาปรับตัวขึ้นจาก 57.8% (2023) เป็น 73.2% ในปี 2026 (ข้อมูลบางส่วน) | คำเรียกการส่งของมีหลายแบบ: "ส่งมอบตรงเวลา", "ส่งไม่ช้า", "ส่งไม่ล่าช้า", "ส่งตรงวันพอดี", "ส่งทัน"; ในหัวข้อ 4 บอกว่าห้ามรายงาน "ส่งตรงวันพอดี" เป็นอัตราส่งทัน ผู้อ่านไม่รู้ว่า "ตรงเวลา" ในสรุปคือเส้นไหน. also on: inventory ("เป้าการส่งทัน", "% ส่งไม่ช้า"), assumptions ("เป้าการส่งไม่สาย") | not-late (ส่งทันวันนัดหรือก่อน) ใช้คำเดียว; "ส่งตรงวันพอดี" = exact-day delivery แยกเป็นอีกคำ |
| 3 | forecast/sales_report.html | 6. โมเดลพยากรณ์ / 7. ผลลัพธ์ | Top-down Combination คือการพยากรณ์ยอดขายในระดับ "Type" ... โดยใช้ค่าเฉลี่ยของโมเดลพยากรณ์ 6 แบบร่วมกัน | คำว่า Combination มี 2 ความหมาย: ในส่วนที่ 1 และ 6 ใช้ร่วมกับ Top-down (ค่าเฉลี่ย 6 วิธีแล้วกระจายลงรหัส) แต่ในส่วนที่ 7 "ตารางรอง — วิธี Combination ระดับประเภทสินค้า: เก็บไว้เทียบ ไม่ใช่วิธีที่ใช้" และ "ตารางหลัก — ความแม่นของวิธี Top-down (วิธีที่ใช้จริง)" ทำให้ไม่ชัดว่าวิธีที่ใช้จริงใช้ค่าเฉลี่ย 6 วิธีหรือไม่. also on: คู่มือ | Top-down (ทายระดับ Type แล้วแบ่งลงรหัส) กับ Combination (เฉลี่ยหลายวิธี) เป็นสองแกนต่างกัน อธิบายแยกและบอกว่าตารางหลักใช้อะไรทายระดับ Type |
| 4 | index.html | 1. ภาพรวม (หมายเหตุใต้ตาราง Inventory) | หมายเหตุ: ตัวเลขรายเดือนในหมวดนี้ด้านล่างเป็นข้อมูลสมมติ (placeholder) เพื่อประกอบการนำเสนอเท่านั้น | "สมมติ" ใช้หลายความหมาย: ตัวเลขที่แต่งเพื่อประกอบ (ข้อมูลสมมติ), สมมติฐานที่ตั้งไว้ (หน้า "สมมติฐานที่ใช้อยู่", "ค่าสถานการณ์"), และ "สมมติ" แปลว่า "สมมุติว่า" (ตัวอย่างอ่านค่า: "สมมติแท่ง ≥30 วันสูง 6%"). ยังปนกับ "ค่าประมาณจากสูตร", "ตัวอย่างวิธีคำนวณ", "Placeholder". also on: sales_report, inventory, คู่มือ | แยกคำ: placeholder = ตัวเลขแต่งเพื่อแสดงโครงสร้าง; assumption = สมมติฐานที่ตั้งไว้; formula estimate = ค่าคำนวณจากสูตร; "สมมติว่า" ใช้เฉพาะตัวอย่างการอ่าน |
| 5 | forecast/sales_report.html | ทั่วทั้งหน้า (ส่วน 2, 7) | ยอดทายรอบ ต.ค. 69 · ใช้ยอดขายถึง ส.ค. 69 | "ยอดทาย"/"ทาย" เป็นคำพูดย่อของ forecast ใช้ปนกับ "พยากรณ์", "Forecast", "ยอดพยากรณ์" ในหน้าเดียวกัน; "รอบ ต.ค. 69" ไม่บอกว่าเป็นเดือนที่รันหรือเดือนที่ทาย และตาราง "ยอดทาย ก.ย. 69 ถึง ก.พ. 70" เริ่มก่อนรอบ ต.ค. 69. also on: index, inventory, operation_plan, material_plan, assumptions | forecast (ยอดขายที่คาดไว้) ใช้คำเดียว; ระบุ "forecast รันเมื่อ ต.ค. 69 ใช้ข้อมูลถึง ส.ค. 69 ครอบคลุม ก.ย. 69 ถึง ก.พ. 70" |
| 6 | index.html | แผงสต็อคจริง (ตารางรายสินค้า) | Available | Available = Inventory ลบ Reserved แต่ยังนับคลัง QA ด้วย (tooltip: "qty − Reserved — ยังไม่ตัดคลังที่ไม่ใช่ sellable ออก") จึงสูงกว่าที่หยิบส่งได้จริง ชื่อคอลัมน์ทำให้เข้าใจว่าหยิบได้แน่; ข้อความอธิบายอยู่ใต้ตาราง/ในคู่มือ. also on: คู่มือ | Available (net of Reserved) ใส่คำอธิบายสั้นที่หัวคอลัมน์: "stock หักของที่ถูกจอง รวมคลัง QA แล้ว"; ให้ดู Sellable − Reserved |
| 7 | forecast/sales_report.html | 7. ผลลัพธ์ (ตาราง ยอดทายเทียบยอดขายจริง) | ฝ่าย / เดือน / MAE / Bias / MAE ในการทดสอบย้อนหลัง / ยอดทาย (บาท) / ยอดจริง (บาท) / ต่าง (บาท) | ใต้ตารางมีหมายเหตุว่า "ตัวเลขบาทคิดทั้งยอดทายและยอดจริงด้วยราคาขายเฉลี่ยเดียวกัน" แต่หัวคอลัมน์ "ยอดจริง (บาท)" อ่านเป็นรายได้จริงตามบัญชีได้ (เช่น CI101 ยอดจริง 9,916,552); ไม่ใช่ยอด invoice. also on: sales_report ส่วนที่ 2 (ยอดทายรายเดือน บาท) | ยอดขายจริงคิดเป็นบาทที่ราคาขายเฉลี่ย (actual units x average price) ไม่ใช่ revenue จากบัญชี |
| 8 | forecast/operation_plan.html | ตารางสรุปรายเดือนต่อฝ่าย | เทียบยอดผลิตสูงสุดที่เคยทำ / 92.1% / 119.9%สูงกว่ายอดผลิตสูงสุดที่เคยทำ | คำยาวและฐานไม่ชัด: % ของอะไร (ผลรวมทุกสินค้าไม่แยกขนาดตามหมายเหตุ), และหมายเหตุบอก "ไม่ได้แปลว่าเป็นกำลังผลิตเต็มที่" แต่ตัวเลขที่เกิน 100% ดูเหมือนเตือนว่าเกินกำลัง. also on: assumptions ("กำลังผลิต ... ใช้ยอดนั้นเป็นค่าต่ำสุด") | % of historical peak monthly output (ยอดผลิตเสร็จสูงสุดต่อเดือนในอดีต) ไม่ใช่ capacity; ใช้เป็นตัวอ้างอิงเท่านั้น |
| 9 | forecast/operation_plan.html | ตารางสรุปรายเดือนต่อฝ่าย | ผลิตตามความต้องการ / เติมให้ถึง Max / ผลิตตามสั่ง / รวม | "ผลิตตามความต้องการ" กับ "ผลิตตามสั่ง" ฟังเป็นเรื่องเดียวกัน แต่คอลัมน์แรกคือผลิตตาม forecast ของสินค้า MTS (inferred) ส่วนคอลัมน์หลังคือ MTO; หมายเหตุของ PEM103 เขียนว่า "แผนจึงเป็นการผลิตตามความต้องการทั้งหมด". "ความต้องการ" ยังหมายถึง demand ในแผนวัตถุดิบ. also on: index, inventory (ป้าย "ผลิตตามสั่ง") | Demand-driven build (ผลิตตาม forecast + ออเดอร์ที่รับแล้ว), Build to Max (เติมให้ถึง Max), MTO (ผลิตตามสั่ง) |
| 10 | forecast/inventory.html | ตารางรายรายการ | Value at risk = ถ้า Min ในระบบสูงกว่าที่จำลอง ส่วนเกินคิดเป็นเงินเท่าไหร่ | Value at risk เป็นศัพท์การเงินที่แปลว่าความเสี่ยงขาดทุน (VaR) แต่ที่นี่คือมูลค่าส่วนเกินของ Min ที่ตั้งไว้เทียบกับ Min จำลอง; ไม่ได้บอกว่าเสี่ยงอะไร. also on: คู่มือ | Excess Min value (มูลค่า Min ส่วนเกินที่ตั้งไว้เทียบกับ Min จำลอง) แทน Value at risk |
| 11 | forecast/material_plan.html | ต้องสั่งภายใน 30 วัน / ขาดแล้ว | ขาดแล้ว สั่งตอนนี้ไม่ทัน | "ขาดแล้ว" อ่านได้ว่าของหมด stock แล้ว แต่ความหมายตามคำอธิบายคือ "วัตถุดิบที่แผนต้องใช้ก่อนที่ของจะมาถึงแม้สั่งวันนี้" (lead time ยาวกว่าเวลาที่เหลือ) ซึ่งอาจยังมี stock. คอลัมน์ "ต้องสั่งภายใน" ในตารางนี้เป็นวันที่ผ่านมาแล้ว (เช่น 23 ก.ค. 69) | Late-to-order / past order-by date (เลยกำหนดสั่ง: สั่งวันนี้ของมาไม่ทันแผน) ไม่ใช่ stock-out |
| 12 | forecast/inventory.html | ตัวควบคุม / กล่องผลรวม | Stock value (Σ Min×unit_cost) | ชื่อ "Stock value" ฟังเป็นมูลค่า stock ที่มีอยู่ แต่สูตรคือจำนวน Min x ต้นทุนต่อชิ้น (มูลค่าของระดับ Min ที่จำลอง) ไม่ใช่ stock ในคลัง; หัวข้อกราฟ "มูลค่า stock (บาท)" ก็ใช้คำเดียวกัน. also on: กราฟ Trade-off, คู่มือ | Value of Min level (มูลค่าที่ต้องถือตาม Min จำลอง) แยกจาก On-hand stock value |
| 13 | forecast/inventory.html | ตัวควบคุม | Procurement lead time (days): 60d | ป้ายตัวควบคุมเป็นอังกฤษทั้งบรรทัดพร้อมหน่วยย่อ "d"/"mo" ("Assembly time (days): 3d", "Obsolescence threshold (months): 6mo"); "Cycle service level: 0.95" และ "Annual holding cost rate: 0.2" เป็นทศนิยมแต่หน้าอื่นใช้ % ; 0.2 หมายถึง 20% ต่อปีโดยไม่บอก; "Obsolescence" ไม่ตรงกับคำไทย "ของค้าง" | Procurement lead time, Assembly time, Review interval, Cycle service level (95%), Holding cost (20% ของมูลค่าต่อปี), Obsolete stock threshold: ใส่หน่วยไทยกำกับ |
| 14 | forecast/inventory.html | หัวข้อ / หมายเหตุสำคัญ | ค่าสถานการณ์ (scenario values) | คำบัญญัติ+อังกฤษซ้ำในวงเล็บ; "ค่าแนะนำ" ในหัวข้อ "PEM101 — เลือกเป้าการส่งทัน แล้วดูว่าต้องถือของเท่าไหร่ (ค่าแนะนำ)" ขัดกับ "ไม่ใช่คำแนะนำการสั่งซื้อ (purchase recommendation)" | Scenario (ผลจำลองภายใต้สมมติฐาน) และใช้ "ผลจำลอง" แทน "ค่าแนะนำ" |
| 15 | forecast/inventory.html | ตารางรายรายการ / ตัวกรองประเภท | ประเภทสินค้า: เก็บ stock / ผลิตตามสั่ง / ยังไม่ชัด | "ประเภทสินค้า" ใช้สองความหมาย: Product Type (เช่น High Voltage Distribution Fuse link ในรายงานยอดขาย) กับประเภทการผลิต (เก็บ stock/ผลิตตามสั่ง) ในหน้านี้และ operation_plan คอลัมน์ "ประเภท". "เก็บ stock" และ "ผลิตตามสั่ง" คือ MTS/MTO ที่ทีมพูดเป็นอังกฤษ. also on: operation_plan, index (ตาราง Trend "ประเภท" = Product Type) | MTS / MTO (เก็บ stock / ผลิตตามสั่ง) ใช้ชื่อคอลัมน์ "นโยบายการผลิต" แยกจาก "Product Type" |
| 16 | forecast/operation_plan.html | ตารางรายสินค้า (ป้ายประเภท + tooltip) | ข้อมูลไม่สอดคล้อง [tooltip: ประเภทที่บันทึกในระบบขัดกับวิธีส่งจริง ใช้วิธีส่งจริงตัดสิน] | "วิธีส่งจริง" เป็นคำที่ทีมไม่ได้ใช้ (หมายถึงพฤติกรรมจริงสามอย่างที่ระบบวัด ตามหน้า inventory); "ประเภทที่บันทึกในระบบ" ไม่บอกว่าระบบไหน/ป้ายอะไร; "ไม่สอดคล้อง" อ่านเป็นข้อมูลผิด. also on: inventory ("ยังไม่ชัด"), assumptions ("สินค้า PEM101 20 รหัส ยังไม่ชัดว่าเก็บ stock หรือผลิตตามสั่ง") | Conflict between MTS/MTO label and actual behaviour (ป้าย MTS/MTO ในระบบไม่ตรงกับพฤติกรรมจริง ต้องให้ฝ่ายยืนยัน) |
| 17 | forecast/operation_plan.html | หมายเหตุใต้ตารางฝ่าย | 6 รหัสไม่พบการผลิตในระบบ ไม่นับเป็นภาระผลิต | "ไม่พบการผลิตในระบบ" อ่านเป็นยกเลิกผลิต/ไม่เคยผลิต แต่หมายถึงไม่มีบันทึกการผลิตในระบบ; "ภาระผลิต" เป็นคำบัญญัติ (production load) ที่ทีมไม่ได้พูด; ในตารางแถวขึ้น "ไม่พบการผลิตในระบบ" แทนประเภทและแสดง "-" ไม่ใช่ศูนย์. also on: material_plan ("ไม่พบการผลิตในระบบ 55 รหัส", "ไม่มี BOM ในระบบ") | No production history (ไม่มีบันทึกผลิตในระบบ) / Not in production load; ไม่ใช่ discontinued |
| 18 | forecast/operation_plan.html | หมายเหตุใต้ตารางฝ่าย | 21 รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้ | "ไม่มียอดทาย" ไม่ใช่ forecast = 0 แต่คือไม่มีประวัติพอ (Placeholder); "ออเดอร์ที่รับแล้ว" กับ "ออเดอร์ค้าง" ฟังเหมือนกัน; รายงานยอดขายนับ "รหัสที่ยังไม่มียอดทาย 110 รหัส" แต่ตารางขอบเขตมี Placeholder 92 + ตัดออก 18 (ฐานตัวเลขหลายแบบ). also on: sales_report | No forecast (ไม่มี forecast: ประวัติขายไม่พอ) ใช้เฉพาะ open orders (ออเดอร์ที่รับแล้วยังไม่ส่ง) |
| 19 | forecast/sales_report.html | 3. ขอบเขตข้อมูล | ฝ่าย (Division) / พยากรณ์ (Forecast) / Placeholder / ตัดออก (Excluded) / รวม | "Placeholder" เป็นศัพท์ IT; ผู้อ่านเข้าใจเป็นแค่ตัวยึดที่ว่าง ไม่รู้ว่ามีค่าประมาณ (15% ของค่าเฉลี่ย Category ตามหน้า index); "ตัดออก" ไม่บอกเหตุ (PEM104 ผลิตตามสั่งทั้งหมดถูกตัดออก 12 รหัส). also on: operation_plan, inventory, คู่มือ | No-history item (สินค้าไม่มีประวัติขาย ใช้ค่าประมาณ ห้ามใช้สั่งของ) และ Excluded (ไม่ forecast เพราะเป็น MTO/ข้อมูลไม่พอ) พร้อมเหตุ |
| 20 | forecast/sales_report.html | 4. ข้อค้นพบทางธุรกิจ | Median customer notice: 6 วัน | "notice" คือระยะเวลาระหว่างวันรับ PO กับวันที่ลูกค้าต้องการของ (หัวข้อ "ระยะเวลาแจ้งล่วงหน้า") ซึ่งหน้านี้ไม่บอกนิยาม; "median" เป็นค่ากลางจริง ไม่ใช่ค่าเฉลี่ย; "สัดส่วนออเดอร์ที่แจ้งล่วงหน้า ≥ 1 เดือน: 5.80%" ไม่บอกว่านับ PO หรือบรรทัด PO. มีไทย-อังกฤษปนในบรรทัดเดียว | Customer lead time (จำนวนวันจากรับ PO ถึงวันที่ลูกค้าต้องการของ) ค่า median 6 วัน; ระบุหน่วยนับ (PO line) |
| 21 | forecast/sales_report.html | 4. ข้อค้นพบทางธุรกิจ | ระยะเวลาจัดหาวัตถุดิบ (Procurement lead time): 45-75 วัน (ค่ากลาง 60 วัน) | "lead time" ใช้หลายอย่างในหน้าต่างๆ: customer notice (6 วัน), procurement lead time วัตถุดิบ (45-75), เวลาผลิต/ประกอบ ("Assembly time", "เวลาผลิตสินค้า 26 วัน"), และ lead time นำเข้าในแท็บ S&OP ("Lead Time 60 วัน (2 เดือน)"); "ค่ากลาง 60 วัน" เทียบกับหน้า assumptions ที่ใช้ "1-30 วัน" ทำให้ไม่รู้ว่าเลขไหนใช้จริง. also on: inventory, material_plan, index | Supplier lead time (สั่งวัตถุดิบถึงได้ของ) vs Production lead time vs Customer lead time: ใช้ชื่อเต็มทุกครั้ง |
| 22 | forecast/sales_report.html | 6. โมเดลพยากรณ์ | ไม่ใช้ Neural Network (เช่น TensorFlow) หรือ Prophet เนื่องจากมีข้อมูลย้อนหลังเพียง 31 เดือน และ 73% ของรหัสสินค้ามีลักษณะการขายแบบ Intermittent หรือ Lumpy | ข้อความอธิบายเหตุผลทางเทคนิคเป็นอังกฤษปนไทย (Overfit, continuous, Neural Network, TensorFlow, Prophet) ที่ฝ่ายขาย/วางแผนไม่รู้จัก; "Intermittent หรือ Lumpy" อธิบายไว้ในแท็บ Trend ไม่ใช่ที่นี่. "31 เดือน" เทียบกับ "ยอดขายที่ใช้ทาย ก.พ. 67 ถึง ส.ค. 69" และ "ฐาน เดือน: ม.ค. 2024 – ก.ค. 2026" ในแท็บ Trend นับเดือนต่างกัน | Intermittent / Lumpy (ขายนานๆ ที) ส่วนชื่อโมเดล (Neural Network, Prophet) ตัดหรือเปลี่ยนเป็น "โมเดลซับซ้อนที่ต้องใช้ข้อมูลยาวกว่านี้" |
| 23 | forecast/sales_report.html | 6. โมเดลพยากรณ์ | Naive, MA3, MA6, MA12, Croston, SBA | ชื่อวิธีย่อภายในโปรเจกต์ ไม่มีคำอธิบาย (ผู้อ่านรู้ MA แต่ไม่รู้ Croston/SBA; "Naive" = ใช้ยอดเดือนก่อน แต่หน้านี้เรียก "การใช้ยอดเดือนล่าสุดเป็นค่าทาย"); "โมเดล" กับ "วิธี" ใช้ปนกัน ("โมเดลพื้นฐาน 6 แบบ", "วิธีทายวิธีเดียว"). also on: คู่มือ ("วิธีเดาง่ายๆ") | Naive (ยอดเดือนก่อน), MA3/6/12 (moving average), Croston/SBA (สำหรับสินค้าขายนานๆ ที) แต่ละตัวมี 1 บรรทัดไทย |
| 24 | forecast/sales_report.html | 7. ผลลัพธ์ (ตาราง) | n_scored (item × origin) | เป็นชื่อคอลัมน์ในระบบ (มีขีดล่าง) ไม่ใช่คำที่ผู้อ่านรู้ และไม่รู้ว่า origin คืออะไร; ตารางรองใช้ "จำนวนสินค้า" แทน ซึ่งอาจเป็นคนละฐาน | จำนวนที่ใช้คำนวณ (สินค้า x รอบทดสอบ) ใช้ชื่อไทย; ไม่แสดงชื่อ n_scored |
| 25 | forecast/sales_report.html | 7. ผลลัพธ์ | Rolling-origin MAE (Type level) — คลิก legend เพื่อซ่อน/แสดงแต่ละโมเดล | Rolling-origin เป็นศัพท์วิธีทดสอบ; หน้าเดียวกันเรียก "รอบทดสอบ", "ทดสอบย้อนหลัง 7 รอบ", "rolling origin", "จุดตัดข้อมูล", "เดือนที่ 1-6 หลังจุดตัดข้อมูล"; ไม่มีนิยามบนหน้า (อยู่ในคู่มือ). also on: คู่มือ | Backtest (ทดสอบย้อนหลัง: ตัดข้อมูลที่เดือนหนึ่ง แล้วทาย 6 เดือนถัดไป เทียบของจริง) ใช้ "รอบทดสอบ" คำเดียว |
| 26 | forecast/sales_report.html | 7. ผลลัพธ์ | ฝ่าย / MAE / RMSE / Bias / MASE / n_scored (item × origin) | MASE ไม่มีคำอธิบายบนหน้า ("ต่ำกว่า 1 = ดีกว่าวิธีเดาง่าย" อยู่ในคู่มือ); "MASE_undefined" (คู่มือ) เป็นชื่อภายใน; MAE เทียบข้ามฝ่ายไม่ได้ แต่ตารางวางฝ่ายเรียงกัน (คู่มือเตือน หน้าไม่เตือน). also on: assumptions ("MASE ต่ำแค่ไหนถึงผ่าน") | MASE (เทียบกับ naive; <1 ดีกว่า naive) พร้อมเตือน "MAE เทียบข้ามฝ่ายไม่ได้" ใต้ตาราง |
| 27 | forecast/sales_report.html | 7. ผลลัพธ์ (ข้อสรุปเทียบวิธี) | PEM101 ทายพลาดน้อยกว่าประมาณ 1.4% ทดสอบแล้วความต่างนี้เกิดจริง แม้จะเล็ก | "เกิดจริง" หมายถึง statistically significant แต่คู่มือเขียนว่า "Top-down ชนะวิธีอื่นแบบไม่มีนัยสำคัญทางสถิติ" ขัดกัน (confirmed สองข้อความ; ความหมายเดียวกันหรือไม่เป็น judgement); "ทายพลาดน้อยกว่า 1.4%" ไม่บอกว่า % ของ MAE หรืออะไร. also on: คู่มือ | Statistically significant (ต่างจากความบังเอิญ) หรือ Not significant; บอกว่า % คือ MAE ที่ลดลง |
| 28 | forecast/sales_report.html | 2. ยอดทาย ก.ย. 69 ถึง ก.พ. 70 | ยอดทายทุกเดือนเท่ากัน เพราะวิธีทายตอนนี้ให้ค่าระดับเดียวกับทุกเดือนข้างหน้า ยังไม่คิดช่วงขายดีขายน้อยตามฤดูกาล | "ค่าระดับเดียว" และ "เป็นค่ากลางค่าเดียว ยังไม่มีช่วงสูงต่ำ" เป็นคำบัญญัติของ flat/point forecast; "ค่ากลาง" แปลได้ทั้ง mean, median, midpoint (inventory: "เส้นกลาง = ค่ากลาง"; ส่วนที่ 4: "ค่ากลาง 60 วัน"). also on: inventory | Flat forecast (ค่าเท่ากันทุกเดือน ไม่มี seasonality), Point forecast (ค่าเดียว ไม่มีช่วง); ถ้าเป็น median/mean ให้ระบุ |
| 29 | forecast/sales_report.html | 2. ยอดทาย ก.ย. 69 ถึง ก.พ. 70 | มูลค่าคิดจากราคาขายเฉลี่ยจริงของแต่ละรหัส ก.ย. 68 ถึง ส.ค. 69 · 1 รหัสที่ไม่เคยขายใช้ราคาตั้งใน Price List | "ราคาขายเฉลี่ยจริง" (actual average) ปนกับ "ราคาตั้งใน Price List" ฟังเหมือนกัน; ไม่บอกว่าเฉลี่ยถ่วงน้ำหนักหรือไม่ และ "ยังไม่ได้ตรวจว่านับแบบเดียวกับเป้ารายได้" (ฐานของ "รายได้" ยังไม่กำหนดตามหน้า assumptions) | Average selling price (ราคาขายเฉลี่ยต่อชิ้น 12 เดือนล่าสุด) vs List price (ราคาตั้ง) |
| 30 | forecast/sales_report.html | ทั่วทั้งหน้า | กลุ่มนำร่อง: Fuse Cutout และ Surge Arrester | "กลุ่ม" ใช้หลายความหมาย: กลุ่มสินค้า/Type, "กลุ่มนำร่อง" (pilot) ที่ไม่บอกว่านำร่องอะไร, และ "กลุ่ม" ในแท็บ Trend = Smooth/Erratic/Intermittent/Lumpy ("กลุ่ม ทั้งหมด"). อังกฤษ "(3 focus codes)" กับไทย "สินค้าหลัก 3 ตัว" และ "สินค้า PEM101 กลุ่มนำร่อง" ดูเหมือนเรียกสิ่งเดียวกัน 3 แบบ (judgement). also on: index Trend, คู่มือ | Pilot items (สินค้านำร่อง 3 รหัสที่ใช้เทียบวิธี) และ Demand pattern (รูปแบบการขาย) แทน "กลุ่ม" ในแท็บ Trend |
| 31 | forecast/sales_report.html | 1. บทสรุปผู้บริหาร | โครงการนี้ครอบคลุมสินค้าทั้งหมด 445 รหัส ใน Omni Channel ทุกฝ่าย | "Omni Channel" เป็นชื่อช่องทางขายภายใน (inferred) ที่ไม่มีนิยามบนหน้า ผู้อ่านอาจเข้าใจเป็นช่องทางออนไลน์; หน้า operation_plan บอก "PEM103 นับเฉพาะยอด Omni Channel งานประมูลไม่อยู่ในแผนนี้"; "ฝ่าย" บางหน้าเรียก "Business" ("ค้นหา/กรองตามฝ่าย (Business)"). also on: index, operation_plan, inventory | Omni channel (ช่องทางขายปกติผ่าน PO ลูกค้า ต่างจาก Tender/งานประมูล) บอกนิยามครั้งแรก; Division = ฝ่าย (PEMxxx) |
| 32 | forecast/sales_report.html | หัวหน้า / ตารางข้อมูลแต่ละส่วนดึงเมื่อ | ข้อมูลแต่ละส่วนดึงเมื่อ ... ช่วงข้อมูลหลัก / 2026-10-05 07:41:11 / ใหม่ | สถานะ "ใหม่" อ่านเป็นข้อมูลชุดใหม่/สินค้าใหม่ ที่จริงน่าจะหมายถึงข้อมูลไม่เก่าเกิน 7 วัน (inferred จากคู่มือ); วันที่แบบ ISO ค.ศ. ในตารางต่างจากหัวหน้าที่ใช้ "8 ต.ค. 69"; ชื่อส่วนเป็นชื่อกราฟภายใน ("กราฟส่งตรงวันพอดี", "กราฟ Rolling-origin") | Fresh / Stale (ใหม่ = ดึงไม่เกิน 7 วัน, เก่า = เกิน) ใช้ปี พ.ศ. เหมือนกันทั้งหน้า |
| 33 | index.html | ทั่วทั้งเว็บ (วันที่) | ยอดขายจริง ม.ค.–ก.ค. 2026 / ต.ค. 69 / พ.ค. 2569 / 2025-03 ถึง 2026-08 | ปีเขียนหลายแบบ: พ.ศ. 2 หลัก ("ต.ค. 69"), ค.ศ. ("ม.ค.–ก.ค. 2026", "ส.ค. 2026" ในแท็บ Trend, "2025-03 ถึง 2026-08" ในรายงานยอดขาย), พ.ศ. 4 หลัก ("พ.ค. 2569" ในแผนสต็อค); "69" อ่านผิดเป็น 1969 ได้ และ "ม.ค.–ก.ค. 2026" กับ "ก.ย. 69" อยู่หน้าเดียวกัน. also on: sales_report, inventory, คู่มือ | ใช้ปี พ.ศ. 4 หลักทุกที่ (เช่น ต.ค. 2569) |
| 34 | index.html | แท็บ S&OP Plan (เดิม) / การ์ดสรุป | ยอดขายจริง ม.ค.–ก.ค. 2026 ฿492.4 ลบ. ตามไฟล์ต้นฉบับ (ตรวจสอบย้อนหลังไม่ได้) | "ยอดขายจริง" แต่ตรวจไม่ได้และห้ามใช้ตัดสินใจ (คำเตือนด้านบนแท็บ) ป้ายสถานะอ่านเป็นตรงข้ามได้; "ลบ." หมายถึงล้านบาท แต่ "ลบ" ที่อื่นแปลว่า minus ("ต่างติดลบ", ตาราง Trend "ยอดขาย (ลบ.)"); ตัวย่อต่างจาก "(ล้านบาท)" ในหัวข้อ 2. also on: Trend | Unaudited figure (ตัวเลขจากไฟล์เดิม ไม่ได้ตรวจกับระบบ) และเขียน "ล้านบาท" เต็ม |
| 35 | index.html | แท็บ S&OP Plan (เดิม) / 1. ภาพรวม | จัดแผนแบบ Chase Strategy คือผลิตให้ตรงกับความต้องการแต่ละเดือน | "Chase Strategy" ในส่วนที่ 1 = กลยุทธ์ผลิต แต่ส่วนที่ 4 เขียน "คำนวณสมมติด้วยสูตร Chase Strategy (Lead Time 60 วัน (2 เดือน) / Review 30 วัน / Service Level 95%)" ซึ่งเป็นสูตร Min/Max ต่างความหมาย. also on: index ส่วนที่ 4-5 | Chase strategy (ผลิตตามความต้องการรายเดือน) กับ Min/Max formula (safety stock) เรียกแยกกัน |
| 36 | index.html | แท็บ S&OP Plan (เดิม) / 1. ภาพรวม | คอลัมน์ "Odoo Module" ระบุว่าข้อมูลแต่ละแถวควรดึงจาก Module ใดหากเชื่อมต่อระบบ Odoo (เป็นข้อเสนอแนะเบื้องต้น ยังไม่ได้เชื่อมต่อจริง) | ผู้อ่านอาจเข้าใจว่าระบบเชื่อม Odoo แล้ว; ชื่อ Module เป็นเรื่อง IT; ยังมี "Cube Sale APD2026 — กรอง status = "Actual" จับคู่ด้วยคอลัมน์ itemcode" ในส่วนที่ 5 ซึ่งเป็นชื่อตาราง/คอลัมน์ในระบบ | Proposed data source (แหล่งข้อมูลที่เสนอ ยังไม่ได้เชื่อม) ตัดชื่อไฟล์/คอลัมน์ออกจากหน้า |
| 37 | index.html | แท็บ S&OP Plan (เดิม) / 3. สรุปตาม Product Category | Product Category / Total Code / มีข้อมูลจริง / Coverage | "Code" / "Product Code" / "รหัส" / "SKU" / "Item" / "รายการ" ใช้ปนกัน (แท็บ Trend ใช้ "SKU", รายงานยอดขายใช้ "Item"/"รายการ"); "มีข้อมูลจริง" (= มียอดขาย) กับ "Coverage" ไม่บอกฐาน (แท็บเดิม 426 รหัส; หน้ายอดขาย 445; คู่มือ 448). "รายการ" ยังหมายถึงบรรทัด PO ("กระทบประมาณ 2.5% ของรายการ"). also on: sales_report, index Trend, inventory | Item code (รหัสสินค้า) ใช้ "รหัส" คำเดียว และ PO line (บรรทัด PO) แยกจาก item; Coverage = % ของรหัสที่มียอดขาย |
| 38 | index.html | แท็บ S&OP Plan (เดิม) / 5. วิธีคำนวณ | Service Level 95% (Z=1.645) / Customer Service % / Inventory Target Days of Supply: 20 วัน | ศัพท์สถิติ/ซัพพลายเชน (Z, Safety Stock, Days of Supply) ไม่มีคำอธิบาย; "Customer Service %" ไม่บอกวัดอะไร และเป็นตัวเลข "สมมติ (±10% รอบเป้าหมาย)" | Service level (ความน่าจะเป็นที่ stock ไม่ขาด) และ not-late rate ถ้าหมายถึงการส่งทัน |
| 39 | index.html | แท็บ Trend Omni / นิยามศัพท์ | Smooth = ขายเกือบทุกเดือน ... Intermittent = นานๆ ขายที แต่พอขายจำนวนใกล้เคียงกัน Lumpy = นานๆ ขายที และจำนวนไม่แน่นอน | ศัพท์แบ่งรูปแบบ demand (Smooth/Erratic/Intermittent/Lumpy, ADI, CV², Syntetos-Boylan) ไม่มีคำไทยที่ตกลงกัน และรายงานยอดขายแปลว่า "Intermittent หรือ Lumpy (ขายไม่สม่ำเสมอ ไม่ต่อเนื่อง)" ต่างจากนิยามในแท็บนี้ (Intermittent = ขนาดสม่ำเสมอ); "ADI 1.32 และ CV² 0.49" ผู้อ่านตั้งต่อเองไม่ได้. also on: sales_report, คู่มือ | Demand pattern: Smooth / Erratic / Intermittent / Lumpy (คงอังกฤษ) + ADI (ขายห่างกันกี่เดือน), CV² (ขนาดออเดอร์แกว่งแค่ไหน) บรรทัดเดียวต่อคำ ใช้นิยามเดียวกันทุกหน้า |
| 40 | index.html | แท็บ Trend Omni / ตัวกรอง | (มีผลกับกราฟ ① และ SKU modal เท่านั้น — ไม่มีผลกับกราฟ ②③④) | คำเทคนิค UI "SKU modal", "drill down", "tooltip" ไม่ใช่คำของทีมขาย; หมายเลข ①–④ ไม่เรียงตามตำแหน่งบนหน้า (④ มาก่อน ③ ตามข้อความที่ดึงได้, judgement) | Pop-up รายสินค้า (item detail), drill down (ดูรายวัน) ใช้ชื่อไทยกำกับ |
| 41 | index.html | แท็บ Trend Omni / คอลัมน์ Remark | Match = สเปคสองระบบสอดคล้องกัน Check spec = ตัวเลขสเปคขัดแย้ง ควรตรวจสอบ No spec info = ไม่มีตัวเลขสเปคให้เทียบ No data in DB = ไม่มียอดขายปี | ป้ายสถานะอังกฤษล้วน "สเปคสองระบบ" ไม่บอกว่าระบบไหนกับระบบไหน; "Match" อ่านเป็นตรงกับเป้า/ยอดขายได้; "No data in DB" = ไม่มียอดขาย ไม่ใช่ข้อมูลหาย (DB เป็นศัพท์ไอที); คู่มือบอก "ไม่มีบันทึกว่าคำนวณยังไง ใช้อ้างอิงเท่านั้น" | Spec check (เทียบสเปคสินค้า 2 ระบบ: ตรงกัน / ขัดกัน / ไม่มีข้อมูล) ไทยกำกับ |
| 42 | index.html | แผงสต็อคจริง | not assessed | ป้ายอังกฤษล้วนในช่องตัวเลข อาจอ่านเป็นศูนย์/ผ่านแล้ว; คำอธิบายใต้ตารางบอก "ไม่ใช่ศูนย์" แต่ไม่อยู่ในตาราง. คู่กับ "ไม่มีข้อมูลในระบบ" (ไม่มีบันทึกในระบบคลังเลย ต่างจากสต็อคเป็นศูนย์ ตามคู่มือ) ซึ่งอ่านเป็นสต็อค 0 ได้. also on: คู่มือ | Not assessed (ยังไม่กำหนดคลังขายได้ ไม่ใช่ 0) / No record (ไม่มีบันทึกในระบบคลัง) ไทยกำกับ |
| 43 | index.html | แผงสต็อคจริง (หัวคอลัมน์) | Sellable / Staging (QA/FMTS/FMTO) / Elsewhere / Reserved | อังกฤษทั้งหมด และ "FMTS/FMTO" เป็นรหัสคลังที่ไม่อธิบาย; "Reserved" ตามคู่มือ = จำนวนที่มี PO จองไว้แต่ยังไม่ส่ง (ไม่ใช่ของที่กันไว้ในคลัง); "Staging" ในหมายเหตุแปลว่า "คลังตรวจ QA ที่ยังไม่พร้อม"; ปน "Sellable (รวม)" กับ "คลังที่ขายได้". also on: inventory ("เลือกคลังที่นับเป็นของขายได้"), คู่มือ | Sellable (คลังที่ขายได้), Staging (QA/FMTS/FMTO ยังไม่พร้อมขาย), Reserved (ติด PO จอง) พร้อมอธิบาย 1 บรรทัดที่หัวตาราง |
| 44 | forecast/inventory.html | แถบสถานะฝ่าย | CI101 — ยังไม่เปิด | "ยังไม่เปิด" อ่านเป็นฝ่ายยังไม่เปิดดำเนินการ แต่ตามข้อความคือหน้านี้ยังไม่เปิดให้ใช้กับฝ่ายนี้เพราะข้อมูลคลังไม่พอ; "ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock" เกณฑ์ไม่ได้บอกบนหน้านี้. also on: operation_plan ("ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock") | Not enabled / Not assessed (ยังไม่ประเมินฝ่ายนี้: ข้อมูลไม่พอ) และบอกเกณฑ์ MTS (ป้าย MTS + พฤติกรรม 2 ใน 3) |
| 45 | forecast/inventory.html | หมายเหตุสำคัญ | ตัวเลขบนหน้านี้คำนวณจากยอดขายรายเดือนเพื่อให้หน้าโหลดเร็ว จึงต่างจากที่ระบบคำนวณเต็มจากข้อมูลรายวันประมาณ 4% (PEM101) | "ที่ระบบคำนวณเต็ม" ต้องรู้ว่าระบบ/ส่วนไหนเป็นตัวหลัก (ส่วน PEM101 ด้านล่างหรือ pipeline) และ "ประมาณ 4%" ไม่บอกฐาน; "เพื่อให้หน้าโหลดเร็ว" เป็นเรื่องเทคนิค | Approximation (ค่าประมาณ ต่างจากค่าเต็ม ~4%) ระบุว่าตัวไหนคือค่าอ้างอิง |
| 46 | forecast/inventory.html | ตารางรายรายการ / หัวคอลัมน์ | Min (ค่าที่ตั้งในระบบ) / Max (ค่าที่ตั้งในระบบ) / Months of cover | "ค่าที่ตั้งในระบบ" ไม่บอกว่าระบบไหน (inferred: ระบบคลัง) และ "Min/Max" เขียน 3 แบบ (Min/Max, Min-Max, Max-Min); ความหมาย Min = จุดสั่งเติม / Max = ระดับที่เติมให้ถึง อยู่ในคู่มือเท่านั้น; Months of cover แสดง "∞" เมื่อไม่มี forecast (คู่มือ) | Min/Max ใช้รูปเดียว; Min = reorder point (จุดสั่งเติม), Max = order-up-to level; "Current Min/Max in system" |
| 47 | forecast/inventory.html | กราฟ Trade-off (PEM101) | เส้นกลาง = ค่ากลาง แถบรอบเส้น = ช่วงที่เป็นไปได้ ดาว = จุดที่เราอยู่วันนี้ เพชร = เป้าที่เลือก | "ช่วงที่เป็นไปได้" ไม่บอกว่าเป็นช่วงความเชื่อมั่นหรือช่วงตามสถานการณ์ lead time; "ค่ากลาง" = median หรือไม่; "เรา" = PEM101 ไม่ใช่บริษัท. also on: คู่มือ ("แถบกว้างมากเพราะข้อมูลบอกไม่ได้") | Uncertainty band (ช่วงความไม่แน่นอน) หรือ Scenario range; ระบุ median |
| 48 | forecast/inventory.html | ตัวควบคุม / กราฟ | not_late target: / เส้นแสดง stock_value ที่ระดับ service level ต่างๆ | ชื่อตัวแปรในโค้ด (มีขีดล่าง) โผล่หน้าจอ: "not_late target", "stock_value", "n_scored", "MASE_undefined" และ "on_time_exact" (คู่มือ); "Items with a Min/Max", "Σ Min×unit_cost" เป็นอังกฤษทั้งบรรทัด | not-late target (เป้าส่งไม่ช้า %), stock value, unit cost (ต้นทุนต่อชิ้น) ไทยกำกับ |
| 49 | forecast/inventory.html | ตารางรายรายการ / หัวคอลัมน์ | ของค้าง = stock พอขายเกินจำนวนเดือนที่ตั้งไว้ด้านบน | "ของค้าง" ซ้ำกับ "ออเดอร์ค้าง" (operation_plan: "ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้") และ "Backlog" (ข้อมูล Reserved); ธง "ของค้าง" อ่านเป็นของที่ค้างอยู่รอส่งได้; หัวข้อควบคุมใช้ "Obsolescence threshold" ต่างคำ. also on: operation_plan, คู่มือ | Excess stock (ของเกิน: เกินเกณฑ์เดือนที่พอขาย) แยกจาก Open orders (ออเดอร์ค้างส่ง) |
| 50 | forecast/material_plan.html | ตารางต้องสั่งภายใน 30 วัน (คอลัมน์ ที่มา lead time) | ใบสั่งซื้อจริง / ผู้ขายแจ้ง / ค่าประมาณ | "ใบสั่งซื้อจริง" อ่านเป็นว่าสั่งซื้อแล้ว แต่น่าจะหมายถึง lead time วัดจากใบสั่งซื้อในอดีต (inferred); "ค่าประมาณ" ใกล้กับ "ค่าประมาณจากสูตร" ในแท็บ S&OP (index) แต่ต่างความหมาย; เหตุผลกำกับ "ไม่มีหน่วยซื้อในระบบ", "หน่วยซื้อไม่ตรงกับหน่วยใน BOM" ติดกับรหัสวัตถุดิบโดยไม่มีช่องว่าง | Lead time source: from past POs / supplier quote / estimate (ใช้ประวัติ PO ที่ผ่านมา / ผู้ขายแจ้ง / ประมาณการ) |
| 51 | forecast/material_plan.html | ตารางต้องสั่งภายใน 30 วัน | รหัสวัตถุดิบ / ชื่อ / ใช้ในสินค้า (รหัส) / ต้องสั่งเพิ่ม / ต้องสั่งภายใน / lead time (วัน) / ที่มา lead time | "ต้องสั่งเพิ่ม" ไม่มีหน่วย (ค่าทศนิยม เช่น 0.6, 1.9 ซึ่งหน่วยซื้ออาจเป็นกก. แผ่น ขวด); "ต้องสั่งภายใน" เป็นวันที่ แต่หัวข้อ "ต้องสั่งภายใน 30 วัน" อ่านเป็นจำนวนวันได้; "+7" หลังรายการรหัสสินค้าไม่อธิบาย; ส่วนบนบอก "ยังใช้สั่งซื้อจริงไม่ได้" ขัดกับหัวข้อ "ต้องสั่ง" | Order qty (หน่วยซื้อ) / Order-by date (วันที่ต้องสั่งภายใน) ใส่หน่วย และเตือน "ตัวเลขยังอยู่ระหว่างตรวจ" |
| 52 | forecast/material_plan.html | ส่วนบน | แผนนี้ยังอยู่ระหว่างตรวจสอบ ตัวเลขต้องสั่งยังใช้สั่งซื้อจริงไม่ได้ | ไม่บอกว่าใครตรวจ ตรวจเมื่อไหร่ เกณฑ์ใดถึงใช้ได้ (assumptions: "ตรงกับใบสั่งซื้อจริงแค่ไหนถึงใช้สั่งของได้ ... ยังไม่กำหนด"); ผู้อ่านอาจเข้าใจว่าจะใช้ได้เร็วๆ นี้ (judgement). also on: index (ลิงก์แผนวัตถุดิบ) | Draft / Not for ordering (ร่าง ห้ามใช้สั่งซื้อจนกว่าฝ่ายจัดซื้อยืนยัน) |
| 53 | index.html | แท็บ สมมติฐานที่ใช้อยู่ (ตารางแรก) | ยังไม่รู้อะไร / ตอนนี้ใช้ / กระทบ ... "ได้จากการจำลองให้ตรงผลจริง ไม่ได้วัดตรง" | หัวคอลัมน์ "ยังไม่รู้อะไร" และ "ตอนนี้ใช้" สั้นเกินอ่านเป็นประโยคไม่ได้; "จำลองให้ตรงผลจริง" = calibration; "ช่วงข้อมูลที่ใช้ปรับ Min/Max" ปรับ = calibrate; "กระทบ" ไม่บอกกระทบอย่างไร; "ใช้ยอดนั้นเป็นค่าต่ำสุด" (กำลังผลิต) อ่านเป็นกำลังผลิตต่ำสุด แต่ความหมายคือ lower bound. also on: คู่มือ ("calibrate กับข้อมูลจริง") | Calibration (ปรับค่าให้ตรงผลจริง), Lower bound (ค่าขั้นต่ำที่รู้แน่ ไม่ใช่ค่าที่ตั้ง), Used in (ใช้กับ) |
| 54 | index.html | แท็บ สมมติฐานที่ใช้อยู่ (เกณฑ์ที่รอกำหนด) | ยอดทายเอียงต่อเนื่อง / tracking signal เกินเท่าไหร่ถึงเตือน / ร่าง: ±4 | "เอียง" = Bias (คำบัญญัติ) ต่างจาก "Bias ติดลบ" ที่ใช้ในรายงานยอดขาย; "tracking signal" ไม่เคยอธิบาย; "ร่าง: ±4" ไม่มีหน่วย; "ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี" ต้องรู้ MASE; "หลังรอบ 5 ธ.ค. 69" = รอบ run เดือนไหน | Bias / Tracking signal (ผลรวม error สะสมหารด้วย MAE: เตือนเมื่อทายเอียงทางเดียวต่อเนื่อง) MASE < 1 = ดีกว่า naive |
| 55 | index.html | แท็บ สมมติฐานที่ใช้อยู่ (เกณฑ์ที่รอกำหนด) | เป้ารายได้ / นับจากวันออก invoice หรือวันส่งของ / ใช้วันส่งของไปก่อน | ฐานการนับยอดขาย/รายได้ใช้คำต่างกัน: "วันส่งตามสัญญา", "เดือนที่ต้องส่งของ", "วันส่งของ", "วันที่ส่งมอบ", "วันออก invoice"; "เป้ารายได้" ไม่ปรากฏที่อื่น ยกเว้นข้อความ "ยังไม่ได้ตรวจว่านับแบบเดียวกับเป้ารายได้" ในรายงานยอดขาย. also on: sales_report ส่วน 2 และ 5, คู่มือ | Contract delivery date (วันส่งตามสัญญา) คำเดียว และแยกจาก Invoice date / PO date |
| 56 | index.html | แท็บ สมมติฐานที่ใช้อยู่ (ตารางแรก) | ใบสั่งผลิตที่กำลังทำ / วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง / ไม่นับในแผน | ผู้อ่านอาจเข้าใจว่าแผนไม่รู้ว่ามีงานค้างผลิต (WIP) เลย; "ไม่นับในแผน" อ่านได้ทั้ง "ไม่หักออกจากภาระผลิต" และ "ไม่สนใจ"; "เวลาผลิตสินค้า 26 วัน (87 รายการ)" ไม่บอกฐานนับ | Open production orders (ใบสั่งผลิตค้าง) ไม่ใช้ เพราะ due date ไม่ตรงจริง; ระบุผลต่อแผน |
| 57 | index.html | แท็บ Trend Omni (ตัวกรอง กลุ่ม) | กลุ่ม ทั้งหมดSmoothErraticIntermittentLumpyไม่มียอดขาย | "ไม่มียอดขาย" อยู่ในรายการเดียวกับ Smooth/Erratic/Intermittent/Lumpy ทั้งที่เป็นสถานะไม่ใช่รูปแบบการขาย; "มียอดขาย/ไม่มียอดขาย" ในแท็บ S&OP เดิมใช้คนละช่วงข้อมูล (ม.ค.-ก.ค. 2026 vs ม.ค. 2024 - ก.ค. 2026) | No sales (ไม่มียอดขายในช่วงข้อมูล) ระบุช่วงข้อมูล |
| 58 | forecast/operation_plan.html | หัวคอลัมน์ตารางรายสินค้า | รหัส / ชื่อสินค้า / ประเภท / stock ตอนนี้ / Min / Max / ต.ค. 69 / พ.ย. 69 / ธ.ค. 69 / ม.ค. 70 / ก.พ. 70 | คอลัมน์เดือนคือจำนวนที่แผนให้ผลิต (inferred จากชื่อหน้า) แต่ไม่มีหัวบอกหน่วย/ความหมาย ขณะที่รายงานยอดขายคอลัมน์เดือนเดียวกันคือยอดทาย; ช่องว่างของ "stock ตอนนี้" (หมายเหตุ: "แสดงเฉพาะสินค้าเก็บ stock") ต่างจาก "-" | Planned production (qty) ต่อเดือน; เว้นว่าง = ไม่เก็บ stock ไม่ใช่ 0 |

### Found, not done

- The Part 7 items go to the manual and text round: low to medium, Claude Code with the user's approval of each text.
- The user manual (`docs/user_manual.md`) still shows the typed months in the Trend chart note; `config/manual_notes.yaml` holds the line with values the tab fills: with the manual update of 2026-10-19 to 10-21, low, Claude Code.
- Tracking Signal of a pilot group's forward point: the group's scored items are used; the Type series' own error is the other reading (no outcome changes today): low, Claude Code.
- Forward-test Relative MAE rests on one scored month; the verdicts of the block use the backtest: the first monthly runs add months automatically.


## Prompt 13

The executive summary tab "สรุปผู้บริหาร" of `index.html`, the bar link renamed, one pointer line on the S&OP tab. Run 2026-10-09. Database sessions: 1 of 1 (the revenue targets, aggregates only). The test suite made no connection. New files: none (`src/build_trend_tab.py` now builds both tabs of `index.html`; see the deviations).

### Part 1, bar

As rendered at 1440x900 and 390x844: "S&OP Plan (เดิม) | สรุปผู้บริหาร | Trend Pricelist Omni 2024–2026 | แผนการผลิต (จากยอดทาย) | แผนวัตถุดิบ | สมมติฐานที่ใช้อยู่ | คู่มือการใช้งาน". S&OP opens by default (active, the only visible tab). The new tab is a tab inside `index.html` (button `tb5`, panel `execTab`).

### Part 2, the tab

- Data month 2026-08 (the last month of the pull the forecast uses, equal to the fit window's last month of vintage 2); YTD Jan to Aug 2026; remaining months Sep to Dec, all inside the vintage (2026-09 to 2027-02).
- Cards as rendered: "ยอดขาย ม.ค.–ส.ค. 69 | 542.1 ล้านบาท | เทียบช่วงเดียวกันปีก่อน +54.1%"; "คาดการณ์ทั้งปี 2569 | 852.4 ล้านบาท | ถึงเป้า 92.2% · ยังไม่ยืนยันฐานเทียบเป้า"; "ความแม่นของยอดทาย | 4 จาก 5 ฝ่าย | ดีกว่า Naive"; "เรื่องที่ต้องระวัง | 8 เรื่อง | ดูรายการด้านล่าง".
- Table as rendered (millions of baht, one decimal):

| ฝ่าย | ยอดขาย YTD | ปีก่อน YTD | เปลี่ยน | คาดการณ์ทั้งปี | เป้า (Revenue) | ถึงเป้า | Relative MAE | หมายเหตุ |
|---|---|---|---|---|---|---|---|---|
| PEM101 | 219.0 | 176.7 | +24.0% | 352.1 | 407.8 | 86.3% | 0.80 | |
| PEM103 | 178.5 | 32.2 | +454.1% | 270.8 | 211.0 | 128.3% | 1.04 | |
| PEM107 | 73.8 | 85.7 | -13.9% | 117.3 | 172.9 | 67.8% | 0.86 | |
| PEM102 | 46.5 | 32.8 | +41.7% | 68.3 | 106.5 | 64.1% | 0.92 | |
| CI101 | 24.3 | 24.4 | -0.3% | 44.0 | 26.2 | 168.0% | 0.83 | |
| รวม | 542.1 | 351.7 | +54.1% | 852.4 | 924.4 | 92.2% | – | |
| PEM104 | – | – | – | – | – | – | – | PEM104 ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย |
| PEMC | – | – | – | – | – | – | – | PEMC อยู่นอกขอบเขตสินค้าของ Omni Channel ในโปรเจกต์นี้ |

- Divisions without a target: none (all five have one). The PEMC VERIFY holds: no Price List item (visible sheets) is on a PEMC sheet or has business PEMC, and PEMC is not in the sheet-to-division map.
- Watch-out lines shown (8): PEM103 ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -7.8); CI101 ทายสูงกว่าจริงต่อเนื่อง (Tracking Signal 6.7); Fuse Cutout ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -4.7); Surge Arrester ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -6.8), each with its approved second sentence; แผนผลิต PEM103 เดือน ต.ค. 69 สูงกว่ายอดผลิตสูงสุดที่เคยทำ (119.9%); แผนผลิต PEM102 เดือน ต.ค. 69 สูงกว่ายอดผลิตสูงสุดที่เคยทำ (243.7%); วัตถุดิบ 584 รายการขาดแล้ว สั่งตอนนี้ไม่ทันแผน; PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ พ.ค. 2569 (57.7% ไม่สาย).
- Pending-decision rows shown (4, those whose ใครกำหนด is ผู้บริหาร): ยอดทายดีกว่าวิธีง่ายไหม · Relative MAE ต่ำแค่ไหนถึงผ่าน (MAE ของเรา ÷ MAE ของ Naive); ยอดทายเอียงต่อเนื่อง · tracking signal เกินเท่าไหร่ถึงเตือน; ฝ่ายที่ยอดทายไม่ชนะวิธีง่าย · ใช้วิธีง่ายแทนไหม; เป้าการส่งไม่สาย · บริษัทต้องการกี่ %; the link "สมมติฐานที่ใช้อยู่" opens that tab.
- Footer as rendered: "ยอดขายนับตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) · ไม่รวม VAT · คาดการณ์ = ยอดจริงถึง ส.ค. 69 + ยอดทายเดือนที่เหลือ × ราคาขายเฉลี่ยจริง · เป้ามาจากระบบเป้าของบริษัท (Revenue) · ยังไม่ได้ยืนยันว่าเป้านับจากวันส่งของหรือวันออก invoice".
- Targets: one aggregate query (year, division, revenue type, category, product type, sum of TargetRevenueAmount, row count); 270 rows in 93 groups, THB 2,769.8 million in all, Omni 1,385.3 million. The database's PEM103 rows hold PEM107's products: split by the Price List category of each row (Distribution Transformer to PEM103; the two Instrument Transformer categories to PEM107), nothing unallocated. PEM104 (280.7 million) and the group companies (180.2 million: three labels) are not in the five rows; PEM104 shows dashes as specified.
- Unit: the table's headers carry no unit; one line "หน่วยตัวเลขในตาราง: ล้านบาท" under the cards says it (an addition to the approved text, see the deviations).

### Part 2f, runner

Step 1 pulls the targets in a session of its own (`build_trend_tab.py --pull-targets`), new step 7f rebuilds the tab after the forecast page, operation plan and material plan (and the Trend step) with two gates: the total row equals the sum of the division rows, and each division's projection equals YTD plus the baht for the remaining months read from the rendered forecast page (its baht summary table; the page's months must be the remaining months). A gate failure stops the run before anything is written. `index.html` is a generated file of the run (already, from Prompt 11).

### Part 3, checks (report only)

Received orders (MPS) with forecast_date in the remaining months against the forecast page's baht per month (THB million; the raw pull of 2026-10-05; "delivered" = Actual rows of that month already in the pull):

| division | month | forecast baht | MPS received | already delivered (Actual) |
|---|---|---|---|---|
| PEM101 | 2026-09 | 33.3 | 0.1 | 46.5 |
| PEM101 | 2026-10 | 33.3 | 18.8 | 2.8 |
| PEM101 | 2026-11 | 33.3 | 3.0 | 0.0 |
| PEM101 | 2026-12 | 33.3 | 1.1 | 0.0 |
| PEM103 | 2026-09 | 23.1 | 0.8 | 32.8 |
| PEM103 | 2026-10 | 23.1 | **42.8** | 1.9 |
| PEM103 | 2026-11 | 23.1 | 0.7 | 0.0 |
| PEM103 | 2026-12 | 23.1 | 0.0 | 0.0 |
| PEM107 | 2026-09 | 10.9 | 0.04 | 9.3 |
| PEM107 | 2026-10 | 10.9 | **13.9** | 0.1 |
| PEM107 | 2026-11 | 10.9 | 3.9 | 0.0 |
| PEM107 | 2026-12 | 10.9 | 0.8 | 0.3 |
| PEM102 | 2026-09 | 5.4 | 0.0 | 4.8 |
| PEM102 | 2026-10 | 5.4 | **15.6** | 0.0 |
| PEM102 | 2026-11 | 5.4 | 1.7 | 0.0 |
| PEM102 | 2026-12 | 5.4 | 0.6 | 0.0 |
| CI101 | 2026-09 | 4.9 | 0.0 | 4.1 |
| CI101 | 2026-10 | 4.9 | **14.8** | 0.9 |
| CI101 | 2026-11 | 4.9 | 2.4 | 0.0 |
| CI101 | 2026-12 | 4.9 | 2.0 | 0.0 |

Received orders alone already exceed the forecast in 4 division-months (bold, all October: PEM103, PEM107, PEM102, CI101); counting what was already delivered, 6 (also PEM101 and PEM103 in September, which has ended: September actual 46.5 and 32.8 against a forecast of 33.3 and 23.1). The forecast is flat, so September to December are understated where orders are known; the projection is therefore a floor for those divisions in the near months (not a conclusion for the year).

Forecast_date basis against the Trend tab's createDate basis, Jan to Aug 2026, the 335 forecast-scope items (THB million): PEM101 219.0 against 241.3 (-9.2 percent); PEM103 178.5 against 202.0 (-11.6); PEM107 73.8 against 84.8 (-12.9); PEM102 46.5 against 55.7 (-16.6); CI101 24.3 against 43.0 (-43.6); total 542.1 against 626.8 (-13.5). The createDate figure is higher in every division, as expected: a PO is received before the month it is due. The 110 items outside the forecast scope are 0.11 percent of the createDate YTD (THB 0.7 million, all PEM104).

2025 per division (forecast_date basis, the 335 items, THB million), full year / Jan to Aug: PEM101 287.9 / 176.7; PEM103 64.5 / 32.2; PEM107 148.3 / 85.7; PEM102 53.7 / 32.8; CI101 41.4 / 24.4; total 595.8 / 351.7.

### Part 4, S&OP pointer

Rendered directly under the KPI cards (the next element after the kpi-row), as "ตัวเลขจริงดูที่แท็บสรุปผู้บริหาร" with "สรุปผู้บริหาร" as a link that opens the new tab (clicked in the browser: the new tab opens and is active). Nothing else of the S&OP tab changed (a diff of the file against HEAD shows only the bar, the pointer line, the new tab's CSS and block and the tab switch).

### Validator

Independent recomputation from the raw pull (not the project's monthly series), the Price List, the saved target aggregate and the rendered pages, results written before the tab was read: MATCH on YTD, last-year YTD, change, projection, target, percent to target for each division and the total, the four cards, the eight watch-out lines (and card 4's count), the four pending rows, the PEM104 and PEMC remarks, the bar, the S&OP default and the pointer line, and the diff of the S&OP tab against HEAD. Inputs read from the pages (not recomputed): the baht forecast, Relative MAE and Tracking Signal, the plan flags, the late-material count, the PEM107 alert, the pending rows, the targets file.

### Rendering (own headless Edge, temp profile, own PID closed)

1440x900 and 390x844: the bar, S&OP default, the pointer link opening the new tab, the four cards, the table, the lists, the footer, the link to the assumptions tab, a return to S&OP; no console error; no horizontal page scroll at 390 px in the new tab (the table scrolls inside its own box). Screenshots in `output/shots_p13/` (untracked).

### Tests

Existing files extended: `test_index_w3.py` (seven labels in order and ids; the tab wired into the tab switch; the pointer line verbatim and under the KPI cards; the cards, table, remarks, footer and unit line verbatim from fixed data, a division without a target, no brace; each watch-out line only when its condition holds, with a fixed example for every kind and the limit boundary; the identities and the gate on fixed pages and mismatches; the target split on a fixed aggregate and a division with no row; the PEMC VERIFY and no customer or person identifier; the real tab equal to what the builder makes from the saved pulls), `test_monthly_refresh.py` (step order, gate counted, the staged stop on a projection that differs from the forecast page), `test_monthly_refresh_failure_log.py` and `test_cfix_runner_and_scores.py` (the new stage and step stubs), `test_operation_plan_page_builder.py` (the renamed link on the index bar).

### Found, not done

- **Scope of "ถึงเป้า".** The tab covers the Price List items of the forecast scope (about 64 percent of the database's 2026 Omni value by createDate); the target is for all Omni. Decision for the user (see the summary).
- PEM103's YTD is 5.5 times last year's and its to-target moves with single tender orders; PEM107's target (172.9 million) is derived from the database's PEM103 rows by category: low, the user to confirm the split with the target owners.
- The workbook `target_data.xlsx` (user-stated latest version) is not the target source of this tab (the database table is, as instructed); the two agree at Business totals (Prompt 7) but not by revenue stream: low, Claude Code with the target owners.
- The user manual does not describe the new tab or the renamed link: with the manual update of 2026-10-19 to 10-21, medium, Claude Code.


## Prompt 14

Executive summary tab fixes: scope labels (D1), the remaining months from the larger of the forecast and the orders already on the books (D2), order concentration per division (D3, report only). Run 2026-10-09. Database sessions: 1 of 1 (the order-level totals of D3 were not in a saved pull: the saved sales pull has no contract column; the same session also read the outside-scope bookings). The test suite made no connection. New files: none. No contract, customer or order number was written to any file or to this report: the order-level result stayed in memory and only counts, sums and rank shares were kept.

### Part 1, D1 scope labels

Card 2 as rendered: "คาดการณ์ทั้งปี 2569 (สินค้าใน Price List) | 982.4 ล้านบาท | ถึงเป้า 106.3% · เป้ารวมสินค้า Omni ทุกตัว % นี้จึงน่าจะต่ำกว่าจริง". Footer as rendered: "ยอดขายนับตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) · ไม่รวม VAT · คาดการณ์ = ยอดจริงถึง ส.ค. 69 + เดือนที่เหลือใช้ค่าที่มากกว่าระหว่างยอดทายกับออเดอร์ที่รับแล้ว × ราคาขายเฉลี่ยจริง · เป้ามาจากระบบเป้าของบริษัท (Revenue) · ยังไม่ได้ยืนยันว่าเป้านับจากวันส่งของหรือวันออก invoice · ยอดขายและคาดการณ์นับเฉพาะสินค้าใน Price List แต่เป้ารวมสินค้า Omni ทุกตัว". The texts are in config; nothing else on the tab changed in wording.

### Part 2, D2 remaining months

Definition (METRICS.md Sec.49): per forecast-scope item and remaining month, units = max(forecast units of vintage 2, units on the books), baht = whole baht of units x the item's unit price (the forecast page's prices); units on the books = Actual + MPS units with forecast_date in the month from the saved sales pull of 2026-10-05 (Omni, forecast_date not before createDate, the 335 forecast-scope items; the same scope and key as YTD). Projection = YTD + the sum. The forecast page is unchanged.

| division | YTD (M) | old projection | new projection | difference | Sep | Oct | Nov | Dec | to target old | to target new |
|---|---|---|---|---|---|---|---|---|---|---|
| PEM101 | 219.0 | 352.1 | 380.9 | +28.8 | +19.8 | +8.1 | +1.0 | 0.0 | 86.3% | 93.4% |
| PEM103 | 178.5 | 270.8 | 333.0 | +62.2 | +25.0 | +37.0 | +0.2 | 0.0 | 128.3% | 157.8% |
| PEM107 | 73.8 | 117.3 | 128.7 | +11.4 | +1.9 | +6.7 | +2.5 | +0.3 | 67.8% | 74.5% |
| PEM102 | 46.5 | 68.3 | 81.0 | +12.7 | +1.1 | +11.2 | +0.5 | 0.0 | 64.1% | 76.1% |
| CI101 | 24.3 | 44.0 | 58.7 | +14.7 | +1.2 | +12.6 | +0.7 | +0.2 | 168.0% | 224.3% |
| total | 542.1 | 852.4 | 982.4 | +130.0 | +49.1 | +75.6 | +4.8 | +0.5 | 92.2% | 106.3% |

(Million baht; the difference is new minus old: the booked orders add 130.0, 94 percent of it in September and October.) Old to new baht per month (Sep, Oct, Nov, Dec; million baht): PEM101 33.3 to 53.0, 33.3 to 41.4, 33.3 to 34.2, 33.3 to 33.3; PEM103 23.1 to 48.1, 23.1 to 60.0, 23.1 to 23.3, 23.1 to 23.1; PEM107 10.9 to 12.8, 10.9 to 17.6, 10.9 to 13.3, 10.9 to 11.2; PEM102 5.4 to 6.6, 5.4 to 16.6, 5.4 to 5.9, 5.4 to 5.4; CI101 4.9 to 6.2, 4.9 to 17.5, 4.9 to 5.6, 4.9 to 5.1. The forecast is flat (the forecast page holds the same baht in every month), so the difference is the orders on the books above the flat forecast, item by item. Total to target moves from 92.2 to 106.3 percent. The gate compares each division's projection with YTD plus, per item and month, the larger of the forecast page's baht (read from its per-item rows) and the baht on the books.

On the books for Price List items outside the forecast scope (110 items, Omni, Actual + MPS, forecast_date Sep to Dec 2026, database): two rows only: PEM104 THB 0.14 million (September, Actual) and PEM101 THB 678 (September, Actual); no MPS. Not added to the projection.

### Part 3, D3 order concentration (report only)

An order = one contract: the `contractid` of cube_Sale_APD, the purchase-order document the customer placed; its lines (items) are summed over the lines in the window (forecast_date month Jan to Aug of the year, Omni, Actual + MPS, the 335 forecast-scope items, division by the Price List). Why: it is the document the business receives and the project's existing order key (a contract spans several items); the table's other keys (job, quotation) are not on every line. Every in-scope row has a contract id (0 rows without one). Orders are referred to by rank only.

| division | year | orders | sum (M baht) | largest 1 | largest 3 | largest 5 |
|---|---|---|---|---|---|---|
| CI101 | 2026 | 121 | 24.3 | 12.0% | 26.6% | 34.3% |
| CI101 | 2025 | 115 | 24.4 | 10.4% | 28.9% | 40.4% |
| PEM101 | 2026 | 2,750 | 219.0 | 0.8% | 1.8% | 2.7% |
| PEM101 | 2025 | 2,521 | 176.7 | 1.1% | 2.7% | 3.8% |
| PEM102 | 2026 | 132 | 46.5 | 6.8% | 11.9% | 15.5% |
| PEM102 | 2025 | 96 | 32.8 | 6.5% | 14.1% | 19.0% |
| PEM103 | 2026 | 530 | 178.5 | 2.9% | 6.9% | 9.3% |
| PEM103 | 2025 | 114 | 32.2 | 3.8% | 10.3% | 14.7% |
| PEM107 | 2026 | 694 | 73.8 | 3.7% | 7.2% | 9.5% |
| PEM107 | 2025 | 663 | 85.7 | 3.3% | 9.1% | 13.5% |

(Current YTD = Jan to Aug 2026, previous year = the same months of 2025.) The sums equal the saved monthly series' YTD exactly for every division and year. PEM103: YTD growth +454.1 percent as it stands; +416.0 percent without the three largest orders of 2026 (12.3 million, 6.9 percent of 178.5); +475.4 percent without each year's three largest. The growth comes from the number of orders (114 to 530, 4.6 times) and a larger average order (0.28 to 0.34 million), not from a few large ones. CI101 is the only division where five orders are a third of YTD or more.

### Validator

Independent recomputation of the new projection per division and in total, the cards and the percent to target (from the raw pull, the forward-test log, the Price List and the saved targets; results saved before the tab was read): MATCH on all 36 table cells, the four cards, card 2's label and sub-line and the footer; its old and new projection and the monthly differences equal the above. Concentration: the Validator wrote its own SQL from the stated scope (it ran in the same session; aggregate output only) and its shares equal the implementer's to the last digit; its check total + rows without a contract id = all rows holds for all ten division-years.

### Tests, rendering

Existing files extended (`test_index_w3.py`): the three texts verbatim; the max rule on fixed examples (forecast above the orders, orders above the forecast, an item with no forecast row, half-up rounding, no price) and the on-the-books selection (Omni only, Actual and MPS only, forecast_date not before createDate, scope, months); the gate on a fixed forecast page with a projection that is not the per-item maxima, one that equals the forecast page alone, a wrong total row and wrong months. Rendered at 1440x900 and 390x844: the new card label, sub-line and footer are visible and nothing scrolls sideways; screenshots in `output/shots_p14/` (untracked).

### Found, not done

- With the booked orders the total projection is above the target; the target covers all Omni products and the sales only Price List items (labelled by D1). The all-Omni comparison is the later task (2026-10-21 to 10-23): Claude Code.
- The projection is flat for months with no orders on the books (no seasonality) and the item-wise maximum can only raise the old figure; the user's decision to keep it: low, the user.
- CI101: five orders are 34 to 40 percent of its YTD, so its "ถึงเป้า" (224 percent against a 26.2 million target) rests on a few orders: low, the user.


## Prompt 15

Forecast model experiment on the existing backtest (report only). Run 2026-10-09. Database sessions: 0. No page, recorded output or forward-test log changed; the production model is unchanged; vintage 2 is not recomputed. New file: `src/investigations/model_experiment_2026_10.py` (approved).

### Step 0, pre-registration

The candidates, parameters and the selection rule were written into config (`experiment_2026_10`) and METRICS.md Sec.50 and committed and pushed alone as **8f8ef46** (2026-10-09 10:15:12), before any candidate was computed. Nothing in the rule was changed afterwards; only `proposed` (not active) was added after the run.

### Setup

The main table's setup, unchanged: the saved monthly series (pulled 2026-10-05), the 335 forecast-scope items, 7 rolling origins (train sizes 13 to 25 of 31 months), 6 horizons, the main table's cells (2,328 item x origin cells: CI101 91, PEM101 1,000, PEM102 112, PEM103 343, PEM107 782) and, for the two pilot groups, the Type series with one cell per origin (7 cells each). The current candidate recomputed here equals the main table's cell forecasts exactly (maximum difference 0.0); the current Relative MAE on all 7 origins equals the forecast page's "เทียบกับร่างเกณฑ์" value for every division and group (PEM101 0.80, PEM103 1.04, PEM107 0.86, PEM102 0.92, CI101 0.83, Fuse Cutout 0.93, Surge Arrester 1.07: tested). Origins 1–5 select, 6–7 confirm, all 7 for reference; Tracking Signal on the backtest origins only (5 points on 1–5, 7 on all). Tracking Signal limit 4 (config). Candidates: current; naive; holt (Type level, statsforecast Holt, clipped at 0, top-down allocation); combination_plus_holt (the six models and Holt at equal weight); bias_adjusted (the Combination times the clipped ratio of actual to one-step-ahead in-sample Combination over the last 6 months, clipped to 0.5 to 2.0); seasonal_naive (the value 12 months earlier).

**seasonal_naive cells not available:** none. Every origin has at least 13 months of training, so every target month has a month 12 earlier inside the training window (origin 1 uses months 2 to 7 of the series); 0 target months needed the Naive fallback (the fallback exists and is counted, and a fixed example in the tests shows it).

**Leakage:** every candidate receives the first `train_size` months only (asserted in the code); a test changes every value after the origin, at three origins, for every candidate and shows no forecast changes (and that a change before the origin does move them): PASS.

### Results per group

**PEM101** (1000 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 0.849 | 0.675 | 0.800 | 0.830 | -3.73 | -2.74 | yes |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -0.84 | -1.62 | yes |
| holt | 0.933 | 0.689 | 0.864 | 0.894 | -2.17 | 0.90 | yes |
| combination_plus_holt | 0.855 | 0.665 | 0.801 | 0.832 | -3.58 | -2.26 | yes |
| bias_adjusted | 0.929 | 0.712 | 0.868 | 0.870 | -2.53 | -0.57 | yes |
| seasonal_naive | 0.900 | 0.789 | 0.869 | 1.031 | -4.17 | -5.60 | no |

Rule outcome: **keep current**. current has the lowest Relative MAE on origins 1-5 among the candidates that pass the Tracking Signal filter.

**PEM103** (343 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 1.140 | 0.974 | 1.041 | 1.064 | -4.81 | -6.85 | no |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -5.00 | -7.00 | no |
| holt | 0.967 | 1.055 | 1.020 | 0.972 | -5.00 | -7.00 | no |
| combination_plus_holt | 1.099 | 0.985 | 1.030 | 1.048 | -4.96 | -6.97 | no |
| bias_adjusted | 1.017 | 1.134 | 1.087 | 1.057 | -4.68 | -5.90 | no |
| seasonal_naive | 1.707 | 0.945 | 1.249 | 1.341 | 0.61 | -2.34 | yes |

Rule outcome: **keep current**. seasonal_naive wins origins 1-5 but is not at least 5 percent below current on origins 1-5.

**PEM107** (782 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 0.870 | 0.848 | 0.864 | 1.050 | -0.71 | 0.80 | yes |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -1.26 | 0.10 | yes |
| holt | 0.906 | 0.796 | 0.877 | 1.062 | -1.08 | 0.01 | yes |
| combination_plus_holt | 0.873 | 0.839 | 0.864 | 1.052 | -0.76 | 0.69 | yes |
| bias_adjusted | 0.883 | 0.833 | 0.870 | 1.015 | -0.74 | 0.70 | yes |
| seasonal_naive | 1.235 | 0.984 | 1.169 | 1.494 | 1.67 | 4.65 | yes |

Rule outcome: **keep current**. current has the lowest Relative MAE on origins 1-5 among the candidates that pass the Tracking Signal filter.

**PEM102** (112 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 0.921 | 0.928 | 0.923 | 0.884 | -1.55 | -0.56 | yes |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -2.78 | 0.32 | yes |
| holt | 1.098 | 1.067 | 1.089 | 1.109 | 2.18 | 4.36 | yes |
| combination_plus_holt | 0.940 | 0.946 | 0.942 | 0.916 | -0.93 | 0.36 | yes |
| bias_adjusted | 0.989 | 1.052 | 1.008 | 0.983 | 0.88 | 3.35 | yes |
| seasonal_naive | 1.089 | 1.178 | 1.115 | 1.133 | -3.10 | -0.93 | yes |

Rule outcome: **keep current**. current has the lowest Relative MAE on origins 1-5 among the candidates that pass the Tracking Signal filter.

**CI101** (91 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 1.028 | 0.538 | 0.828 | 0.769 | 5.00 | 7.00 | no |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -0.38 | 3.24 | yes |
| holt | 1.035 | 0.448 | 0.795 | 0.646 | -2.51 | 0.48 | yes |
| combination_plus_holt | 0.976 | 0.515 | 0.787 | 0.696 | 5.00 | 7.00 | no |
| bias_adjusted | 0.928 | 0.602 | 0.795 | 0.670 | 0.90 | 4.72 | yes |
| seasonal_naive | 1.481 | 0.501 | 1.080 | 0.981 | 4.08 | 5.96 | no |

Rule outcome: **keep current**. bias_adjusted wins origins 1-5 but is not lower than current on origins 6-7.

**Fuse Cutout** (7 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 0.809 | 1.053 | 0.930 | 0.826 | -0.12 | 0.82 | yes |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -2.76 | -0.43 | yes |
| holt | 1.609 | 1.103 | 1.357 | 1.394 | -4.00 | -2.35 | yes |
| combination_plus_holt | 0.795 | 1.059 | 0.926 | 0.792 | -0.69 | 0.45 | yes |
| bias_adjusted | 1.222 | 0.941 | 1.082 | 1.108 | -5.00 | -2.38 | no |
| seasonal_naive | 2.640 | 1.531 | 2.089 | 2.187 | 2.69 | 2.23 | yes |

Rule outcome: **keep current**. combination_plus_holt wins origins 1-5 but is not at least 5 percent below current on origins 1-5 and not lower than current on origins 6-7.

**Surge Arrester** (7 cells)

| candidate | Relative MAE (1–5) | Relative MAE (6–7) | Relative MAE (all 7) | Relative MAE Horizon 3 (all 7) | Tracking Signal (1–5) | Tracking Signal (all 7) | passes TS filter |
|---|---|---|---|---|---|---|---|
| current | 1.085 | 1.066 | 1.075 | 0.986 | -3.48 | -4.85 | yes |
| naive | 1.000 | 1.000 | 1.000 | 1.000 | -3.00 | -4.75 | yes |
| holt | 0.980 | 0.878 | 0.925 | 0.900 | -2.49 | -3.06 | yes |
| combination_plus_holt | 1.064 | 1.039 | 1.051 | 0.973 | -3.34 | -4.59 | yes |
| bias_adjusted | 1.051 | 0.881 | 0.961 | 0.944 | -3.11 | -2.99 | yes |
| seasonal_naive | 1.113 | 1.325 | 1.226 | 1.062 | -3.32 | -5.73 | yes |

Rule outcome: **switch** (holt). holt is at least 5 percent below current on origins 1-5 and lower on origins 6-7.


### Rule outcome per group (pre-registered rule)

| group | winner on origins 1–5 among the candidates that pass the Tracking Signal filter | outcome | reason |
|---|---|---|---|
| PEM101 | current | keep current | lowest Relative MAE on 1–5 among those that pass |
| PEM103 | seasonal_naive | keep current | current and four candidates fail the filter (every error has the same sign, Tracking Signal about -5); the only one that passes, seasonal_naive, is 50 percent worse than current on 1–5 |
| PEM107 | current | keep current | lowest on 1–5 |
| PEM102 | current | keep current | lowest on 1–5 |
| CI101 | bias_adjusted | keep current | 9.8 percent below current on 1–5, but not lower on 6–7 (0.602 against current's 0.538); current itself fails the filter (Tracking Signal +5.00 on 1–5) |
| Fuse Cutout | combination_plus_holt | keep current | only 1.7 percent below current on 1–5 and not lower on 6–7 |
| Surge Arrester | holt | **switch to holt** | 9.7 percent below current on 1–5 (0.980 against 1.085) and lower on 6–7 (0.878 against 1.066) |

The proposal is in config `experiment_2026_10.proposed` (not active): every division and Fuse Cutout keep the current method, Surge Arrester holt.

### Effect of the recommended switch on the executive summary (report only; nothing on a page changes)

If Holt had produced vintage 2 for the Surge Arrester group (48 items in PEM101; a refit on all 31 months, the same unit prices and booked-order rule as the tab): the group's remaining-month baht (Sep to Dec) would be 69.0 million instead of 45.6 (+23.3 million: Sep +4.8, Oct +5.6, Nov +6.2, Dec +6.8). PEM101's projection would be 404.2 million instead of 380.9 (99.1 percent of its 407.8 target instead of 93.4), and the total 1,005.7 million instead of 982.4 (108.8 percent of 924.4 instead of 106.3). Holt forecasts a rising trend (4,752 units a month flat for the Type under current against 7,725 rising to 8,262 under Holt), so the forecast would no longer be flat. The current method recomputed here equals the vintage 2 forecast units (maximum difference 5e-5, the log's rounding).

### Validator

An independent recomputation (the models library only; not the experiment script, its output or this report) of all seven groups and all six candidates: **MATCH**. Every Relative MAE (1–5, 6–7, all, Horizon 3), every Tracking Signal and the filter equal the above to four decimals, the rule's outcome is the same for all seven groups (one switch: Surge Arrester to holt), the cells per division (1,000, 343, 782, 112, 91) and the reproduction of the production Top-down MAE for the five divisions to eight digits agree, and the effect on the projection (+THB 23,309,933, by month +4,765,564, +5,593,316, +6,189,038, +6,762,015) is identical.

### Observations the user should have when deciding

- The Tracking Signal filter on origins 1–5 has 5 points, so |TS| cannot exceed 5; a method whose errors all have the same sign scores -5.00 or +5.00. In PEM103 (all errors negative) it removes current and four of five candidates; in CI101 it removes current (+5.00, always above the actual). It is the user's rule and was applied as written.
- The confirmation origins 6–7 share four target months with origins 1–5 (disclosed in METRICS.md Sec.50), so the confirmation is weaker than a fresh test.
- The one switch rests on a single series (the Surge Arrester Type, 7 cells, one per origin) and Holt extrapolates a trend: on the other pilot group Holt is the worst candidate (Fuse Cutout 1.61 on 1–5). Current's Tracking Signal on all 7 origins for Surge Arrester is -4.85, beyond the limit; the filter uses origins 1–5 only (-3.48).
- Not selected by the rule but noted: in CI101 holt has the lowest Relative MAE on 6–7 (0.448) and on all 7 (0.795 against current's 0.828); in PEM101, PEM107 and PEM102 no candidate beats the current method by 5 percent on any subset the rule uses. No result was used to change the rule.

### Found, not done

- Whether and how a Type-level method can differ per group in production (Surge Arrester is a Type inside PEM101; the production model is one method for all) is not part of this task: Claude Code, if the user approves.
- A forward-test month would test the Surge Arrester switch on data the experiment has not seen; the first scored months are 2026-08 and later: low, Claude Code.
