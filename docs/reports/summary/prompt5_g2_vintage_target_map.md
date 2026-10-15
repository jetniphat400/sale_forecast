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

Sheet "TargetC1005 12-06-2029" (<target> rows, 28 columns; the latest target version, per the user); an Analyst computed everything from the saved database aggregates (the one session served 20 read-only aggregate queries: cube_Sale_APD by createDate and by forecast_date, its POR-like filter, the database's own target table `Cube_Target_PMIS`, invoiced revenue `cube_revenue`, the catalogue), and a Validator recomputed b, c and d/e for PEM101 and PEM107.

**a. Structure.** Rows per Year: 2026 426; 2027 397; 2028 397; 2029 to 2033 396 each. Business: PEM101 1,185, PEM102 840, PEM104 504, PEM107 260, PEM103 230, PEMC 104, CI101 48, PSS 9, PTS 3, PPS 2, blank 15 (the blank-Business rows are group-company rows of 2026 with no category or type; their Base is 0). Revenue Stream Type: "2. Omni Channel" 2,575, "1. Tendering" 325, "3. Total Customer Solution" 291, "5. PPA /Long Term Contract" 5, "4. Recurring" 3, "6. Investment" 1. Type of Income: "1.1 Sale" 2,920, "1.2 Project" 184, "1.3 Commission & Service" 80, blank 15, one data-entry slip. Blank counts (all years / 2026): PO Receive 28/5, GP 27/5, Revenue-Conting 249/73, GP-Conting 225/72, Revenue-Base 247/73, GP-Base 223/72. 2026 totals (MB): PO Receive <target>, Revenue-Conting <target>, Revenue-Base <target>; Omni rows with a Business: <target> / <target> / <target>. "Responsible section / Person": 24 distinct values, 15 blank (counts only).

**b. Units.** "MB" = million baht is supported as an order of magnitude (high confidence): workbook Omni 2026 PO x 1e6 = THB <target>M against the database's Omni PO by createDate 2026 (Actual + MPS, to date) THB <target>M, ratio <target> (thousand baht would give <target>, billion <target>). Ratio database / (workbook x 1e6), Omni then all revenue types, by Business: PEM101 <target> / <target>; PEM102 <target> / <target>; PEM103 <target> / <target>; PEM104 <target> / <target>; PEM107 <target> / <target>; CI101 <target> / <target> (Business x Product Category ratios range <target> to <target>; PEM101 Fuse <target>, PEM101 Surge Arrester <target>). **The August-project lead (<target> percent for one sales team) is not reproduced** at Business, Business x category or product-type level; the only near hit is an all-division aggregate (all database Omni PO 2026 <target> / workbook Omni PO <target> = <target>), a coincidence by the evidence (low confidence). The database's own target table (`Cube_Target_PMIS`, 2026, 93 rows, one reload stamp 2026-10-07, so it does not date the target version): TargetPOAmount is filled only for PEM104 and group-company rows and equals PO Receive there (Omni <target> against <target>, Tendering <target> against <target>, within <target> to <target> percent); **TargetRevenueAmount (all revenue types) equals the workbook's Revenue (MB)-Conting x 1e6 at Business totals to within <target> percent for PEM101, PEM102, PEM104, CI101 and the database's PEM103 rows (which hold PEM107): PEM101 <target> against <target>, PEM103+PEM107 <target>M against <target>M, PEM102 <target> against <target>, PEM104 <target> against <target>, CI101 <target> against <target> (the Validator's recomputation; against Revenue-Base the ratios are <target> to <target>).** Split by revenue stream the two differ (PEM101 Omni <target>M in the database against <target>M in the workbook, the <target>M being in Tendering; PEM103 Omni equals Base; PEM102, PEM104 and CI101 Omni equal Conting); the cause of that shift is not determined. So the workbook's Conting is the revenue target the database table carries, and the table's PO target is absent except for PEM104, where it equals PO Receive (<target>). **The workbook is newer than the database's target table for PO Receive** (database 2026 PO target THB <target>, PEM104 and group companies only, against workbook <target>).

**c. Dimensions (2026 Omni, createDate, Actual + MPS: 14,725 rows, THB 1,474.3M).** Business follows the pricelist division of the item or the database `division` column, never `sale_division` (pricelist items: pricelist key matches a target Business and Type for 99.37 percent of rows, 99.19 percent of value; database division 98.61 / 96.29; sale_division 1.43 / 6.12); for 31M of items the two disagree and the test cannot choose (undetermined). Product Type: after normalisation and an explicit alias table (all aliases inferred, medium confidence) 13,397 of 14,725 rows (90.98 percent) and THB 1,069.0M of 1,474.3M (72.5 percent) match a target type; on the target side 51 of 65 Omni types match, carrying <target> percent of PO. The names differ systematically: the pricelist's "Medium Voltage Surge Arrester" items carry the database type "High Voltage Surge Arrester" (all 128.42M of 2025-26 value), the workbook calls it "MV Surge Arrester". Unmatched target types (PO / Conting / Base, MB): PEMC Mediuam voltage Instrument Transformer <target> / <target> / <target>; PEM104 MDB Distribution Board (Type test) <target> / <target> / <target>; PEM104 IOT Transformer Box <target> / <target> / <target>; PEMC Low voltage Instrument Transformer <target> / <target> / <target>; PEM103 3 Phase DT Smart Transformer and OLTC <target> / <target> / <target> each; ten zero-value types (SF6-free GIS and similar). Revenue Stream Type: "2. Omni Channel" = `revenue_type` "Omni Channel"; "1. Tendering" and "3. Total Customer Solution" equal their database strings; "4. Recurring", "5. PPA /Long Term Contract" and "6. Investment" map by name only (inferred). The workbook's Type of Income ("1.1 Sale", "1.2 Project", "1.3 Commission & Service") corresponds by name to the database `revenue` flag ("1.1 Sale Revenue", "1.2 Project", "1.3 Service and Commission"; inferred); of the database's 2026 Omni value 1,002M is "1.1 Sale Revenue".

**d. Measures (Omni, Jan-Sep 2026 actual against the full-year 2026 target, the seven Businesses with a target: PO <target> / Conting <target> / Base <target> MB):** PO by createDate (Actual + MPS) <target> MB (<target> of PO, <target> of Conting, <target> of Base); PO Actual only <target> (<target> / <target> / <target>); delivered by forecast_date, Actual <target> (<target> / <target> / <target>), Actual + MPS <target> (<target> / <target> / <target>); invoiced (`cube_revenue`, invoice_date; actual_date equal for Omni 2026) <target> (<target> / <target> / <target>). **No candidate can be proven to reproduce a target column** (a year-to-date actual against a full-year target cannot prove equivalence, the unit-level ratios scatter widely); direct evidence on column meaning comes only from the database target table (TargetPOAmount = PO Receive for PEM104; TargetRevenueAmount = Revenue (MB)-Conting at Business totals). Plausible pairing (inferred, low): PO Receive with PO by createDate; Revenue with delivered by forecast_date or invoiced. **Conting against Base is UNDETERMINED:** they are equal on <target> percent of 2026 Omni rows with both; no tested dimension (Business, stream, Status of Product, Type of Income, Target Customer, Market Segment, AnSoff, Ansoff Matrix, category, company, core product) separates the differing rows; the only structural pattern is the 15 blank-Business group rows (Conting filled, Base 0). The row ratio PO / Base is <target> on <target> percent of rows with both (meaning undetermined). Pilot types (PEM101, delivered Jan-Sep; target PO / Conting / Base): HV Distribution Fuse Cutout <target> against <target> / <target> / <target>; MV Surge Arrester <target> against <target> / <target> / <target> (actuals depend on the unit definition: forecast-scope items only <target> and <target>).

**e. Forecast link.** Our forecast measures **quantity**, keyed on **forecast_date** months (delivery date), from cube_Sale_APD Omni Channel Actual + MPS, Top-down combination, vintage 2 (run 2026-10-02, fit to 2026-08, target months 2026-09 to 2027-02), **flat per item** (335 of 335 items, 123,114.6 units a month in total). To value it: the pricelist standard price (`Market Price/`, positive for 295 of 335 items, but labelled Q4-2023 / Q1-2024 under a Q3'2026 title, so its vintage is unclear) or the realised price (sale / qty, forecast_date Oct 2025 to Sep 2026); realised is used (pricelist never needed; realised / list median 0.942, value-weighted 0.883). Projection = Jan-Sep actual (forecast-scope items) + Oct-Dec forecast x price, against PO / Conting / Base: PEM101 365.5M -> <target>; PEM102 67.5M -> <target>; PEM103 281.3M -> <target>; PEM107 115.8M -> <target>; CI101 43.3M -> <target> (scope items cover PEM101 85.7 percent, PEM102 37.5, PEM103 82.7, PEM107 63.5, CI101 89.7 percent of the database's Omni delivered value year to date; with all database Omni year to date and scope-only Q4: PEM101 410.0M, PEM107 163.7M). Pilot types (realised price): HV Distribution Fuse Cutout 108.3M (list price 111.2M) -> <target> of PO, <target> of Conting and Base; MV Surge Arrester 91.2M (94.0M) -> <target> **Not supported:** PEM104 and PEMC (no forecast), the non-Omni streams, GP measures, group-company rows without a Business, types with no pricelist item (about 29 percent of Omni value). PO Receive (createDate keyed): the forecast is not keyed on createDate; it supports PO only approximately through the short createDate-to-delivery lag on scope items (median 7 days, p90 31 days; 2025 PO by createDate / delivery by forecast_date 0.999), not validated against a PO-keyed forecast and blind to Q4 orders for 2027 delivery.

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

**The table (CONFIRMED).** 24 columns: keys (TargetProductID, TargetHandledByID, Year), product hierarchy (ProductLevel, Type, ProductCateID, ProoductCateName [sic], ProductTypeID, ProductTypeName, ProductID, ProductName), Company, Division, RevenueType, amounts (TargetRevenueAmount, TargetRevenueGP, TargetPOAmount, TargetPOGP; decimal), HandledBy (person), TradeProcessName, MarketSegmentName, CustomerSegementName, BaseON, Timestamp. One row is one product-by-person target, by year only (no month); ProductLevel Core or End; `Type` = "Division" and BaseON = "Revenue" in every row. Rows per year (2021 to 2026): 275, 152, 72, 187, 285, 270; distinct people 275, 152, 69, 187, 279, 260; distinct products 87, 65, 27, 54, 75, 81; divisions 10, 8, 6, 12, 19, 16. **RevenueType is blank in every row of 2021 to 2025** and filled only in 2026 (Omni Channel THB <target>M, Tendering <target>M, Total Customer Solution <target>M, Recurring Revenue Development by MA and SA <target>M). TargetPOAmount is null in all rows of 2021 to 2025 and filled in 2026 only for PEM104 and group-company rows (THB <target>). Revenue target by year (THB): <target>B, <target>B, <target>B, <target>B, <target>B, <target>B. Load stamp 2026-10-07 17:20 on every row (a reload; it does not date the target version). Division labels mix company codes (PPSPPS, PTSPTS, PSSPSS) and "-OLD" tags in 2021 to 2025; the 2025 PEM107-OLD rows hold load-break-switch, recloser and sectionalizer types (THB <target>) that the database types under PEM102.

**Objects that reference it: none (CONFIRMED).** Searched: `sys.sql_modules` definitions (views, procedures, functions) for the table name and `sys.sql_expression_dependencies` for PMIS and target names: both empty. Tables with PMIS or target in the name (all tables, no views): `Cube_Target_PMIS` (created 2026-04-20), `Cube_PMIS_Organize` (2026-04-23; the organisation hierarchy: RevenueStream, Company, DivisionCode, DivisionName; 48 divisions, e.g. PEMCSA = "Sale Admin (PEMC)", PEM105 = a customer-capital and key-account office), `Cube_Invoice_Report_PMIS` (2026-08-25; invoice lines from 2025-10), `Cube_PMIS_Invoice` (created 2019, last modified 2025-11-26; PMIS invoices from 2025-01-02, latest invoice_date 2026-10-14; columns company, division, invoiceid, invoice_date, forecast_date, itemcode, sale, cost, quantity, sale_division, revenue_type). **The database itself stores no pairing of the target with an actual.** Related actual tables: `cube_Sale_APD` (PO by createDate, delivery by forecast_date), `cube_revenue` (invoiced revenue by invoice_date and actual_date, has a company column), the two PMIS invoice tables. The invoice report's `before_vat_amount` per line equals the PMIS invoice sale to within 0 to 1 percent (<target> lines per invoice; <target> lines in 2025, <target> in 2026; `amount_baht` is null on 99 percent of lines and 0 on the rest, unusable), so the two are one measure.

**Candidates against the revenue target (CONFIRMED, one Analyst).** 2025 is the only full year every candidate covers; 2024 only for PO by createDate (a) and delivery by forecast_date (b); 2023 for none (cube_Sale_APD holds no 2023 rows for the Businesses the 2023 target has). Business level, six pricelist Businesses together, 2025 actual / target: PO createDate <target>; delivered by forecast_date <target>; PMIS invoice by invoice_date <target>; cube_revenue (company-aware: PEM101 <target>, PEM103 <target>, PEM104 <target>, PEM107 <target>, CI101 <target>; raw <target>, the difference being cube_revenue's division "101" mixing companies: PEM <target>M, SBP <target>M, CI <target>M, PPD <target>M in 2025). Per Business the ratios still run from <target> to <target> for the PMIS invoice (PEM104 <target>, PEM107 <target>), with <target> percent of Businesses and <target> percent of Business x type cells within the tolerance (part of the target value finds no actual cell with the same type name). Stability over 2024-2025: delivered by forecast_date has median coefficient of variation <target> (<target> after D1), PO createDate <target> (<target>); only 2 of 9 Businesses below <target>. **No candidate reproduces the target; undetermined (high confidence that none does).** Closest: delivered value by forecast_date, then the PMIS invoice; PEM101 is the one Business that fits (b under D1: <target> in 2024, <target> in 2025), which one Business of nine does not make evidence. Pointers (INFERRED, medium): the target looks like a plan (15 of 73 grouped 2025 target cells are non-round, the rest round figures such as <target>M and <target>, and the largest cells are round); one cell, NSPC-CEN, equals the cube_Sale_APD Actual total exactly (<target>), weak evidence only.

**D1 applied (CONFIRMED):** value (THB M) whose Business changes when the pricelist Business replaces the database division, createDate Actual + MPS: 2024 <target>, 2025 <target>, 2026 <target> (rows 849, 185, 138); delivered by forecast_date: <target>, <target>, <target>; PMIS invoice: 2025 <target>, 2026 <target> (main flows 2025: PPS to PEM103 <target>M, PTS to PEM103 <target>M, PPS to PEM101 <target>M, PPD101 to PEM101 <target>M, PPS to PEM107 <target>M). D1 moves the six-Business total ratio for PO createDate from <target> to <target>, delivered from <target> to <target>, PMIS invoice from <target> to <target>; it improves PEM101 (<target> / <target> / <target> for PO / delivered / PMIS invoice) and CI101 and worsens PPS and PTS (the target keeps them as their own Businesses) and PEM103 (<target> delivered); it does not make any candidate reproduce the target. **For the executive summary this means:** until the actual measure is proven, a comparison of the revenue target with any actual is indicative only; the delivered-by-forecast_date measure is the one our forecast can extend (Prompt 6, Part 5e).

## Part 3. Name-inferred type aliases -- for the user to confirm (nothing recorded as fact)

24 of the 2026 Omni workbook types (65 types with a Business) were matched to a database or pricelist type by inference rather than exact (case, spaces and punctuation ignored) equality; they carry **PO Receive <target> MB, Revenue-Conting <target> MB, Revenue-Base <target> MB** (<target> percent of the Omni PO target of <target> MB) and link THB 248.9M of database value (2026 Omni PO by createDate, Actual + MPS, counting the shared LED unit once). 28 types (<target> percent of PO) are exact (13 of those 28 still have THB 161.8M of inferred-linked rows inside their database value); 13 types (<target> percent, PO <target> MB) have no database counterpart (PEMC Mediuam voltage Instrument Transformer <target> MB, PEM104 MDB Distribution Board (Type test) <target> MB, PEM104 IOT Transformer Box <target> MB, two PEM103 variants <target> MB each, PEMC Low voltage Instrument Transformer <target> MB, seven PEM102/PEM104 types with zero target); on the database side THB 404.4M (27.4 percent) has no workbook counterpart (THB 92.8M inside the workbook's Businesses, 311.6M in Businesses the workbook does not have, e.g. PSP103 173.3M, PSP105 85.3M). The PEMC Business itself matches the database division PEMCSA by name only (`Cube_PMIS_Organize`: PEMCSA = "Sale Admin (PEMC)").

| # | Business | Workbook type | PO MB | Conting MB | Base MB | Database type it was matched to (source), rule | DB 2026 Omni value, THB |
|---|---|---|---|---|---|---|---|
| 1 | PEM101 | MV Surge Arrester | <target> | <target> | <target> | Medium Voltage Surge Arrester (pricelist), MV read as Medium Voltage; plus database name High Voltage Surge Arrester, HV read as MV | 81,484,734 |
| 2 | PEMC | 3 Phase Distribution Transformer | <target> | <target> | <target> | four database "Three Phase ... 22kV" names, many-to-one alias | 59,167,927 |
| 3 | PEM104 | Medium Voltage Switchgear | <target> | <target> | <target> | database "Switchgear", qualifier dropped | 330,000 |
| 4 | PEM101 | LED Street light 20W | <target> | <target> | <target> | "LED Street light" (pricelist) and "LED STREET LIGHT", prefix, many-to-one with #7 and #8 | 26,762,840 (shared) |
| 5 | PEM101 | Fuse Switches Disconnectors | <target> | <target> | <target> | pricelist "Low Voltage Fuse Switch Disconectors", qualifier and the pricelist's misspelling | 9,007,700 |
| 6 | PEM101 | STC | <target> | <target> | <target> | database "STC 123-2000", prefix | <target> |
| 7 | PEM101 | LED street lights 94W | <target> | <target> | <target> | as #4 | (shared) |
| 8 | PEM101 | LED street lights 2x20W | <target> | <target> | <target> | as #4 | (shared) |
| 9 | PEM104 | Protection Relay | <target> | <target> | <target> | database "PQM Panel" (alias) | 1,454,800 |
| 10 | PEM102 | 24kV Solid Recloser | <target> | <target> | <target> | "22kV Recloser" and "Recloser 22kV", 24kV Solid read as 22kV | 13,111,550 |
| 11 | PEM101 | LV Surge Arrester | <target> | <target> | <target> | Low Voltage Surge Arrester, LV read as Low Voltage | 17,023,092 |
| 12 | PEM101 | LV Capacitor | <target> | <target> | <target> | Low Voltage Capacitor | 1,861,806 |
| 13 | PEMC | 1 Phase Distribution Transformer | <target> | <target> | <target> | database "Single Phase (22kV Low Loss)" (alias) | 4,238,850 |
| 14 | PEM101 | SLOC/D | <target> | <target> | <target> | database "SLOC/D 125-630", prefix | 330,000 |
| 15 | PEM101 | Photo switch 220V 30A | <target> | <target> | <target> | pricelist "Photo Control Switch" (alias; the database name is equal) | 2,377,960 |
| 16 | PEMC | Mediuam voltage Surge Arrester | <target> | <target> | <target> | Medium Voltage Surge Arrester, spelling fix | 1,134,540 |
| 17 | PEM101 | MVCapacitor | <target> | <target> | <target> | Medium Voltage Capacitor, MV read as Medium Voltage | 947,250 |
| 18 | PEM104 | Unit substation 24kV 500 - 1000 kVA | <target> | <target> | <target> | database "Unit Substation", prefix | 12,056,720 |
| 19 | PEMC | Mediuam voltage Fuse Cutout | <target> | <target> | <target> | "High voltage distribution Fuse cutouts", medium read as high | 1,052,898 |
| 20 | PEM102 | Spare Part & Raw Material PEM102 | <target> | <target> | <target> | "Spare Part and Raw Material (PEM102)", & read as and | 12,857,025 |
| 21 | PEM107 | VT Outdoor Power supply VExL-24,VExL-36 | <target> | <target> | <target> | "Voltage Transformer Type VExL" (alias) | 186,682 |
| 22 | PEM104 | Control Box for Communicate | 0 | 0 | 0 | database "Control Box", prefix | 14,400 |
| 23 | PEM102 | Maintenance | 0 | 0 | 0 | "Maintenance Service", prefix | 20,000 |
| 24 | PEM102 | 36kV Solid Recloser | 0 | 0 | 0 | pricelist "33kV Recloser" (alias; no 2026 value) | 0 |

The weakest inferences (decide first): HV read as MV (#1, #19), 24kV Solid read as 22kV (#10), "Medium Voltage Switchgear" to "Switchgear" (#3, PO <target> MB for THB 0.33M of value), the many-to-one groups (the three LED wattage types to one database type; the PEMC three-phase transformers), PQM Panel to Protection Relay (#9), and the PEMC Business alias. Two items carry a policy flag: #5 moves to an exact type if types are linked by database name instead of pricelist type; #15 and #17 become exact on the database name. Differences from the earlier count: the same 4 of 15 exact PEM101 types and 10 of 11 PEM107 types as before; one zero-value type (#24) is now counted as inferred.

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

- **Rendered (CONFIRMED, 8 rows, under the first table of the tab, after its heading):** row 1 `ยอดทายดีกว่า Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย) ไหม | MASE ต่ำแค่ไหนถึงผ่าน | ร่าง: ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี | ผู้บริหาร | หลังรอบ 5 ธ.ค. 69`; row 2 `ยอดทายเอียงต่อเนื่อง | tracking signal เกินเท่าไหร่ถึงเตือน | ร่าง: ±4 | ผู้บริหาร | ทุกเดือน`; rows 3 to 8 as approved.
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

Sheet POR of the target workbook (no row or customer value copied): rows 2024-01-01 to 2026-05-08. Omni Channel, Actual + MPS, Price List items, by month of createDate, 29 months compared. The tab is higher than POR in every month. Sale ratio (tab / POR) <target> to <target> for 2024-01 to 2026-04, total ratio <target> (largest difference <target> million, 2024-03); quantity ratio <target> to <target>. 2026-05 up to the 8th: sale <target>, qty <target> (the workbook holds <target> pieces for those days, the database <target>). Not explained here: the likely reading is back-dated lines posted after the workbook was made, not verified. <target> Omni Actual + MPS rows of POR are for codes not on the Price List.

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

Row 1 as rendered: "ยอดทายดีกว่า Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย) ไหม | Relative MAE ต่ำแค่ไหนถึงผ่าน (MAE ของเรา ÷ MAE ของ Naive) | ร่าง: ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี | ผู้บริหาร | หลังรอบ 5 ธ.ค. 69". Config keys `mase_pass`, `mase_good` renamed `relative_mae_pass`, `relative_mae_good` (values 1 and 0.7); the row text's braces follow; the comment's source line names Morlidge's ratio of forecast MAE to naive MAE. `data/assumptions.json` regenerated (also moves the ten rows' updated date to 2026-10-09).

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
| 2 | forecast/sales_report.html | 1. บทสรุปผู้บริหาร | อัตราการส่งมอบตรงเวลาปรับตัวขึ้นจาก <target>% (2023) เป็น <target>% ในปี 2026 (ข้อมูลบางส่วน) | คำเรียกการส่งของมีหลายแบบ: "ส่งมอบตรงเวลา", "ส่งไม่ช้า", "ส่งไม่ล่าช้า", "ส่งตรงวันพอดี", "ส่งทัน"; ในหัวข้อ 4 บอกว่าห้ามรายงาน "ส่งตรงวันพอดี" เป็นอัตราส่งทัน ผู้อ่านไม่รู้ว่า "ตรงเวลา" ในสรุปคือเส้นไหน. also on: inventory ("เป้าการส่งทัน", "% ส่งไม่ช้า"), assumptions ("เป้าการส่งไม่สาย") | not-late (ส่งทันวันนัดหรือก่อน) ใช้คำเดียว; "ส่งตรงวันพอดี" = exact-day delivery แยกเป็นอีกคำ |
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
| 38 | index.html | แท็บ S&OP Plan (เดิม) / 5. วิธีคำนวณ | Service Level 95% (Z=<target>) / Customer Service % / Inventory Target Days of Supply: 20 วัน | ศัพท์สถิติ/ซัพพลายเชน (Z, Safety Stock, Days of Supply) ไม่มีคำอธิบาย; "Customer Service %" ไม่บอกวัดอะไร และเป็นตัวเลข "สมมติ (±<target>% รอบเป้าหมาย)" | Service level (ความน่าจะเป็นที่ stock ไม่ขาด) และ not-late rate ถ้าหมายถึงการส่งทัน |
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
- Cards as rendered: "ยอดขาย ม.ค.–ส.ค. 69 | <target> ล้านบาท | เทียบช่วงเดียวกันปีก่อน +<target>%"; "คาดการณ์ทั้งปี 2569 | <target> ล้านบาท | ถึงเป้า <target>% · ยังไม่ยืนยันฐานเทียบเป้า"; "ความแม่นของยอดทาย | 4 จาก 5 ฝ่าย | ดีกว่า Naive"; "เรื่องที่ต้องระวัง | 8 เรื่อง | ดูรายการด้านล่าง".
- Table as rendered (millions of baht, one decimal):

| ฝ่าย | ยอดขาย YTD | ปีก่อน YTD | เปลี่ยน | คาดการณ์ทั้งปี | เป้า (Revenue) | ถึงเป้า | Relative MAE | หมายเหตุ |
|---|---|---|---|---|---|---|---|---|
| PEM101 | 219.0 | 176.7 | +24.0% | 352.1 | <target> | <target> | 0.80 | |
| PEM103 | 178.5 | 32.2 | +454.1% | 270.8 | <target> | <target> | 1.04 | |
| PEM107 | 73.8 | 85.7 | -13.9% | 117.3 | <target> | <target> | 0.86 | |
| PEM102 | 46.5 | 32.8 | +41.7% | 68.3 | <target> | <target> | 0.92 | |
| CI101 | 24.3 | 24.4 | -0.3% | 44.0 | <target> | <target> | 0.83 | |
| รวม | 542.1 | 351.7 | +54.1% | 852.4 | <target> | <target> | – | |
| PEM104 | – | – | – | – | – | – | – | PEM104 ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย |
| PEMC | – | – | – | – | – | – | – | PEMC อยู่นอกขอบเขตสินค้าของ Omni Channel ในโปรเจกต์นี้ |

- Divisions without a target: none (all five have one). The PEMC VERIFY holds: no Price List item (visible sheets) is on a PEMC sheet or has business PEMC, and PEMC is not in the sheet-to-division map.
- Watch-out lines shown (8): PEM103 ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -7.8); CI101 ทายสูงกว่าจริงต่อเนื่อง (Tracking Signal 6.7); Fuse Cutout ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -4.7); Surge Arrester ทายต่ำกว่าจริงต่อเนื่อง (Tracking Signal -6.8), each with its approved second sentence; แผนผลิต PEM103 เดือน ต.ค. 69 สูงกว่ายอดผลิตสูงสุดที่เคยทำ (119.9%); แผนผลิต PEM102 เดือน ต.ค. 69 สูงกว่ายอดผลิตสูงสุดที่เคยทำ (243.7%); วัตถุดิบ 584 รายการขาดแล้ว สั่งตอนนี้ไม่ทันแผน; PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ พ.ค. 2569 (57.7% ไม่สาย).
- Pending-decision rows shown (4, those whose ใครกำหนด is ผู้บริหาร): ยอดทายดีกว่า Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย) ไหม · Relative MAE ต่ำแค่ไหนถึงผ่าน (MAE ของเรา ÷ MAE ของ Naive); ยอดทายเอียงต่อเนื่อง · tracking signal เกินเท่าไหร่ถึงเตือน; ฝ่ายที่ยอดทายไม่ชนะ Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย) · ใช้ Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย) แทนไหม; เป้าการส่งไม่สาย · บริษัทต้องการกี่ %; the link "สมมติฐานที่ใช้อยู่" opens that tab.
- Footer as rendered: "ยอดขายนับตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) · ไม่รวม VAT · คาดการณ์ = ยอดจริงถึง ส.ค. 69 + ยอดทายเดือนที่เหลือ × ราคาขายเฉลี่ยจริง · เป้ามาจากระบบเป้าของบริษัท (Revenue) · ยังไม่ได้ยืนยันว่าเป้านับจากวันส่งของหรือวันออก invoice".
- Targets: one aggregate query (year, division, revenue type, category, product type, sum of TargetRevenueAmount, row count); 270 rows in 93 groups, THB <target> million in all, Omni <target> million. The database's PEM103 rows hold PEM107's products: split by the Price List category of each row (Distribution Transformer to PEM103; the two Instrument Transformer categories to PEM107), nothing unallocated. PEM104 (<target> million) and the group companies (<target> million: three labels) are not in the five rows; PEM104 shows dashes as specified.
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

- **Scope of "ถึงเป้า".** The tab covers the Price List items of the forecast scope (about <target> percent of the database's 2026 Omni value by createDate); the target is for all Omni. Decision for the user (see the summary).
- PEM103's YTD is 5.5 times last year's and its to-target moves with single tender orders; PEM107's target (<target> million) is derived from the database's PEM103 rows by category: low, the user to confirm the split with the target owners.
- The workbook `target_data.xlsx` (user-stated latest version) is not the target source of this tab (the database table is, as instructed); the two agree at Business totals (Prompt 7) but not by revenue stream: low, Claude Code with the target owners.
- The user manual does not describe the new tab or the renamed link: with the manual update of 2026-10-19 to 10-21, medium, Claude Code.


## Prompt 14

Executive summary tab fixes: scope labels (D1), the remaining months from the larger of the forecast and the orders already on the books (D2), order concentration per division (D3, report only). Run 2026-10-09. Database sessions: 1 of 1 (the order-level totals of D3 were not in a saved pull: the saved sales pull has no contract column; the same session also read the outside-scope bookings). The test suite made no connection. New files: none. No contract, customer or order number was written to any file or to this report: the order-level result stayed in memory and only counts, sums and rank shares were kept.

### Part 1, D1 scope labels

Card 2 as rendered: "คาดการณ์ทั้งปี 2569 (สินค้าใน Price List) | <target> ล้านบาท | ถึงเป้า <target>% · เป้ารวมสินค้า Omni ทุกตัว % นี้จึงน่าจะต่ำกว่าจริง". Footer as rendered: "ยอดขายนับตามเดือนที่ต้องส่งของ รวม PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) · ไม่รวม VAT · คาดการณ์ = ยอดจริงถึง ส.ค. 69 + เดือนที่เหลือใช้ค่าที่มากกว่าระหว่างยอดทายกับออเดอร์ที่รับแล้ว × ราคาขายเฉลี่ยจริง · เป้ามาจากระบบเป้าของบริษัท (Revenue) · ยังไม่ได้ยืนยันว่าเป้านับจากวันส่งของหรือวันออก invoice · ยอดขายและคาดการณ์นับเฉพาะสินค้าใน Price List แต่เป้ารวมสินค้า Omni ทุกตัว". The texts are in config; nothing else on the tab changed in wording.

### Part 2, D2 remaining months

Definition (METRICS.md Sec.49): per forecast-scope item and remaining month, units = max(forecast units of vintage 2, units on the books), baht = whole baht of units x the item's unit price (the forecast page's prices); units on the books = Actual + MPS units with forecast_date in the month from the saved sales pull of 2026-10-05 (Omni, forecast_date not before createDate, the 335 forecast-scope items; the same scope and key as YTD). Projection = YTD + the sum. The forecast page is unchanged.

| division | YTD (M) | old projection | new projection | difference | Sep | Oct | Nov | Dec | to target old | to target new |
|---|---|---|---|---|---|---|---|---|---|---|
| PEM101 | 219.0 | 352.1 | 380.9 | +28.8 | +19.8 | +8.1 | +1.0 | 0.0 | <target> | <target> |
| PEM103 | 178.5 | 270.8 | 333.0 | +62.2 | +25.0 | +37.0 | +0.2 | 0.0 | <target> | <target> |
| PEM107 | 73.8 | 117.3 | 128.7 | +11.4 | +1.9 | +6.7 | +2.5 | +0.3 | <target> | <target> |
| PEM102 | 46.5 | 68.3 | 81.0 | +12.7 | +1.1 | +11.2 | +0.5 | 0.0 | <target> | <target> |
| CI101 | 24.3 | 44.0 | 58.7 | +14.7 | +1.2 | +12.6 | +0.7 | +0.2 | <target> | <target> |
| total | 542.1 | 852.4 | 982.4 | +130.0 | +49.1 | +75.6 | +4.8 | +0.5 | <target> | <target> |

(Million baht; the difference is new minus old: the booked orders add 130.0, 94 percent of it in September and October.) Old to new baht per month (Sep, Oct, Nov, Dec; million baht): PEM101 33.3 to 53.0, 33.3 to 41.4, 33.3 to 34.2, 33.3 to 33.3; PEM103 23.1 to 48.1, 23.1 to 60.0, 23.1 to 23.3, 23.1 to 23.1; PEM107 10.9 to 12.8, 10.9 to 17.6, 10.9 to 13.3, 10.9 to 11.2; PEM102 5.4 to 6.6, 5.4 to 16.6, 5.4 to 5.9, 5.4 to 5.4; CI101 4.9 to 6.2, 4.9 to 17.5, 4.9 to 5.6, 4.9 to 5.1. The forecast is flat (the forecast page holds the same baht in every month), so the difference is the orders on the books above the flat forecast, item by item. Total to target moves from <target> to <target> percent. The gate compares each division's projection with YTD plus, per item and month, the larger of the forecast page's baht (read from its per-item rows) and the baht on the books.

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
- CI101: five orders are 34 to <target> percent of its YTD, so its "ถึงเป้า" (<target> percent against a <target> million target) rests on a few orders: low, the user.


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

If Holt had produced vintage 2 for the Surge Arrester group (48 items in PEM101; a refit on all 31 months, the same unit prices and booked-order rule as the tab): the group's remaining-month baht (Sep to Dec) would be 69.0 million instead of 45.6 (+23.3 million: Sep +4.8, Oct +5.6, Nov +6.2, Dec +6.8). PEM101's projection would be 404.2 million instead of <target> (<target> percent of its <target> target instead of <target>), and the total 1,005.7 million instead of 982.4 (<target> percent of <target> instead of <target>). Holt forecasts a rising trend (4,752 units a month flat for the Type under current against 7,725 rising to 8,262 under Holt), so the forecast would no longer be flat. The current method recomputed here equals the vintage 2 forecast units (maximum difference 5e-5, the log's rounding).

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


## Prompt 16

Shadow forecast system, starting with Surge Arrester on Holt. Run 2026-10-09 (Get-Date 11:08 at the start; report written 11:50). `git pull origin main` first: already up to date. Database sessions: 0.

### Step 0 (cited, not repeated)

The earlier Step 0 finding stands: the 2026-09 actual was not used in Prompt 15's selection or confirmation (the series ends at 2026-08), and September cannot be scored yet under `leakage_guard.min_margin_days` (30). No actual of a month that has not passed the guard was printed or read in this task.

### Step 1, pre-registration

Config `shadow` and METRICS.md Sec.51 (rule in words, the disclosure line verbatim) were committed and pushed alone as **717f2cb** (committed 2026-10-09 11:08:59, pushed 11:09), before any shadow forecast was computed or scored. The rule text did not change afterwards. Added after it, outside the rule: config `shadow.min_points_tracking_signal: 3` (when the Tracking Signal is shown) and an "Implementation" paragraph in Sec.51.

### What was built

- `holt_clipped` moved into `src/models.py` once; the experiment imports it. The experiment re-run gives `model_experiment_2026_10.json` identical to before the move (compared as data).
- `src/forward_test_all_divisions.py`: `shadow_rows` (same level and split as the experiment's Holt: the Type series, Holt clipped at 0, times the item's share of the Type in the window), `shadow_group_naive`, `shadow_metadata_entry`, log paths.
- `src/monthly_refresh.py`: step 5 computes (and in a dry run rehearses) the shadow rows of each new vintage; step 6 verifies the shadow log, copies actuals, scores, and prints the rule status; `backfill_shadow_vintage`.
- `src/forward_test_scoring.py`: `shadow_score_rows` (guard checked again, no override), `scoreable_run_date`, `decide_rule`, `shadow_rule_status`.
- `src/build_report.py` and config `report.shadow_*`: one line under the pilot table on forecast/sales_report.html.

### Result

- **MAE definition used:** the forecast page's pilot-group MAE: the group's series (the sum of its 48 items, the Type series) scored as one series; for one target month, the absolute error of the group's monthly total.
- **Rule evaluation run (derived from the guard and the monthly run day 5):** 2027-01-05.
- **Scoreable run per month:** 2026-09 on 2026-11-05; 2026-10 on 2026-12-05; 2026-11 on 2027-01-05. (The existing criteria `decision_date` 2026-12-05 is earlier than the evaluation run; the rule does not use it.)
- **Holt vintage 2 back-fill stored: YES** (288 rows = 48 items x 6 months, `actual_qty` empty). Group total 7,724.8 units in 2026-09 rising to 8,619.3 in 2027-02. **Leakage test: PASS** (changing every value after 2026-08 changes no forecast; changing one inside the window does).
- **Unscored months stayed unscored (no actuals read): YES.** The shadow log has no actuals; a test shows a month inside the margin is never scored even when the log holds an actual (boundary 2026-10-29 refused, 2026-10-30 scored).
- **Gate: YES.** The production log, its metadata, the score record and its integrity file, the three other pages and the inventory, operation and material data are byte-identical before and after (15 files by sha256). Only forecast/sales_report.html changed (the new line and the build time).
- **Experiment Holt cells unchanged after the refactor: YES.**
- **Forward-test log path:** `output/summary/forward_test_shadow_log.csv` with `forward_test_shadow_metadata.json` (next to the production log; generated output, not tracked). Scores: `output/summary/forward_test_scores.csv`, scope `shadow_group` (none yet).
- **Page check (4 pages):** headless Edge on a temporary profile (own PID only, closed, profile deleted): sales_report, inventory, operation_plan and material_plan all load with 0 script errors; the sales page shows the line (visible, pilot table still 2 rows), the other three pages' files are unchanged.

The line on the page reads: Surge Arrester shadow forecast, method Holt, status "ยังไม่มีเดือนที่เทียบได้ ผลเดือนแรกออกในรอบวันที่ 5 พ.ย. 69", "ยังไม่ได้ใช้ในแผน".

### Validator (independent, evaluate only)

**MATCH** on all five checks: its own Holt call on the saved series reproduces all 288 back-filled values (maximum difference 5e-5, the log's rounding); the leakage test; the derived runs (36, 35 and 36 days after the month ends: 2026-11-05, 2026-12-05, 2027-01-05, evaluation run 2027-01-05, the guard passes on each date and refuses one month earlier); the 15-file gate; the page line and its first result run date.

### Tests

730 passed, 0 failed, 0 skipped; database connection attempts 0 (4 blocked deliberate attempts made by the block's own test). New tests: shadow rows equal Holt x share and ignore later months; the stored back-fill equals the experiment's Holt; a month not past the guard is never scored; the scoreable run is derived and agrees with the guard (incl. the exact boundary); the rule on fixed examples (recommend switch, keep current, 2-of-3 with the sum condition failing, 2-of-3 with it holding, ties, 1-of-3); pending, partial and evaluated status counting vintage 2 only; shadow output never reaches a plan input; actuals copied from the production log only and a vintage written once. Existing runner tests were given the shadow stubs and temporary shadow paths.

### Deviations from the prompt

- Shadow rows are in their own log beside the production log, not rows inside it: the production vintage hash covers all rows of a vintage and every plan reader pivots all Item rows of the latest vintage, so rows inside it could change plan inputs. This follows the moving-average comparator's precedent. Scores are in the existing score record under new scopes (columns unchanged).
- Relative MAE against Naive and the Tracking Signal are computed when read (from the stored scores) rather than stored.
- `shadow.min_points_tracking_signal` added to config after the rule (3).

### Need decision

None.

### Found, not done

- The criteria `decision_date` 2026-12-05 is before the first date on which all three months can be scored (2027-01-05): small, user.
- A shadow forecast for the Fuse Cutout group, if wanted, is one more line in `shadow.pairs`: small, user decision.


## Prompt 17

Shadow-log persistence check, then the text and manual pass. Run 2026-10-09 (`git pull` first: up to date at 63b0d9d; Get-Date 11:55 at the start). Database sessions: 0. New files: none. Text only: no number, threshold, logic or layout changed.

### Step 0, shadow-log persistence (report only; nothing changed)

- **a. Production forward-test log.** Not tracked by git (`git ls-files output` lists nothing; `.gitignore` line 2 is `output/`). It lives at `D:\sale_forecast\output\summary\forward_test_log_all_divisions.csv` (+ `_metadata.json`), one local copy, no backup in git.
- **b. Shadow log.** Same: `output/summary/forward_test_shadow_log.csv` and `forward_test_shadow_metadata.json` (written 2026-10-09 11:15), git-ignored, one local copy.
- **c. Where the monthly run executes.** Scheduled task `SaleForecastMonthlyRefresh` (next run 2026-11-05 07:00) runs `git -C D:\sale_forecast_publish pull --ff-only origin main` and then `D:\sale_forecast_publish\src\monthly_refresh.py`, working directory `D:\sale_forecast_publish`. In that clone `output` is a junction to `D:\sale_forecast\output` (and `reference` likewise), so the job reads and writes the same log and shadow log where Prompt 16 wrote them: it finds them. The Prompt 16 code reaches the publishing clone through the pull (pushed as 63b0d9d, so the 11-05 pull brings it; the clone is clean at 26e2e56 plus the daily stock commits).
- **d. Rebuild if the shadow log were lost.** Exactly only until the next pull. The back-fill used `output/data/processed_all_divisions_monthly_qty.csv` (pulled 2026-10-05, cut to 2024-02..2026-08); vintage 2's own series was not saved, and that file is overwritten at every monthly pull (STATUS.md, vintage series entry). Today the file reproduces vintage 2's production forecast (Prompt 15: maximum difference 5e-5), so a rebuild is exact; after the 2026-11-05 pull a late-posted or revised row inside 2024-02..2026-08 would change the Type series and the rebuild could not be proven exact. **At risk: YES** for the back-fill's reproducibility after 11-05 and for any disk loss (no copy anywhere else); the back-fill is found by the job as written.

**Proposal (not implemented), under NEED DECISION:** before the 11-05 run, save the vintage-2 fit series (the saved series cut to 2024-02..2026-08, compressed, with its sha256) under `output/forward_test/vintage_series/` as the job already does for vintage 3 on (`src/vintage_series.py`), record its hash in the shadow metadata entry of vintage 2 (not the production metadata, whose row hashes stay untouched), and copy the two shadow files and the production log to a dated backup folder outside the repo's `output/`. Why it is safe: it adds files and a metadata field only; no forecast row, no production hash and no plan input changes; the folder is already git-ignored.

### Step 1, inputs

- **Confusing-word list:** found at `docs/reports/summary/prompt5_g2_vintage_target_map.md`, heading "Prompt 12", "Part 7" (58 items, ten ranked). Not rebuilt.
- **"ผ่าน" against "บอกไม่ได้ว่าดีกว่า":** 5 places said a division or group passed or was better than Naive (before the change): `forecast/sales_report.html:216` (criteria table verdict cells, from `src/build_report.py:465`, `:1078-1079`); `config/manual_notes.yaml:50` (note "ต่ำกว่า … = ดีกว่า Naive", shown at `forecast/sales_report.html:215`); `config/config.yaml:1201` (executive card 3 "ดีกว่า Naive", shown at `index.html:7644`); `config/config.yaml:1743` (assumptions row "ต่ำกว่า 1 ผ่าน", shown at `data/assumptions.json:98-99` and `index.html:7644`); `METRICS.md:1334` (the verdict words). The place saying it cannot be told: `forecast/sales_report.html:235-236` (from `src/build_report.py:256`: for CI101, PEM102, PEM103 and PEM107 "ใกล้เคียงกันจนบอกไม่ได้ว่าวิธีไหนดีกว่า" against Naive, item-level test on 7 rounds); only PEM101 is shown as different from Naive.

### Step 2, text pass

Changed: the ten ranked items of Part 7 (1, 2, 3, 5, 7, 8, 9, 10, 12, plus 11 and the related line of item 54), and the "ผ่าน" conflict. **Not changed: the other 47 items** (the Part 7 note says each text needs the user's approval; they are reported as FOUND, NOT DONE). The original S&OP Plan tab was not touched.

| page | count | before → after |
|---|---|---|
| sales_report | 12 | "ยอดทายรอบ ต.ค. 69 · …" → "Forecast (ยอดทาย) รันเมื่อ ต.ค. 69 · …"; "PO ที่รับแล้วแต่ยังไม่ส่ง (MPS) นับเป็นยอดขาย เพราะลูกค้าสั่งแล้วจริง" → "MPS (open PO: PO ที่รับแล้วแต่ยังไม่ส่ง) นับรวมในยอดที่ใช้ทาย (Actual + MPS) เพราะลูกค้าสั่งแล้วจริง แต่ยังไม่ใช่ยอดที่ส่งมอบแล้ว"; "อัตราการส่งมอบตรงเวลาปรับตัวขึ้นจาก" → "สัดส่วนส่งตรงวันพอดี (exact-day delivery: ส่งวันนัดเป๊ะ ไม่นับส่งก่อน) ปรับตัวขึ้นจาก" (the figure is the exact-day share: its three shares sum to 100); the Top-down/Combination paragraph (twice) → "Combination คือเฉลี่ยผลของโมเดลพยากรณ์ 6 แบบ … เพื่อทายยอดรวมของแต่ละ Type; Top-down คือการแบ่งยอดทายของ Type นั้นลงสินค้าแต่ละรายการ"; "เก็บไว้เทียบ ไม่ใช่วิธีที่ใช้" → "ผลของส่วน Combination ก่อนแบ่งลงรหัสสินค้า ใช้เทียบเท่านั้น ตัวเลขที่ใช้วางแผนคือตารางหลัก"; verdict words "ผ่าน" → "ถึงเกณฑ์ผ่าน (ร่าง)", "ไม่ผ่าน" → "ยังไม่ถึงเกณฑ์ (ร่าง)", "ดี" → "ถึงเกณฑ์ดี (ร่าง)" (14 cells); criteria note lines (below); baht note adds "(ยอดจริงคือจำนวนที่ขายจริง × ราคาขายเฉลี่ย ไม่ใช่รายได้ตามบัญชี)" |
| inventory | 4 | "ยอดทายรอบ …" → "Forecast (ยอดทาย) รันเมื่อ …"; "Value at risk (THB)" → "Excess Min value (THB)"; hint "Value at risk = …" → "Excess Min value (มูลค่า Min ส่วนเกิน) = …"; "Stock value (Σ Min×unit_cost)" → "Value of Min level (มูลค่าตาม Min จำลอง = Min × ต้นทุนต่อชิ้น รวมทุกรหัส)" |
| operation_plan | 7 | data line "ยอดทายรอบ" → "Forecast (ยอดทาย) รันเมื่อ"; "ผลิตตามความต้องการ" → "ผลิตตามยอดทาย + ออเดอร์ (Demand-driven)"; "เติมให้ถึง Max" → "เติมให้ถึง Max (Build to Max)"; "ผลิตตามสั่ง" → "ผลิตตามสั่ง (MTO: Make to Order)"; "เทียบยอดผลิตสูงสุดที่เคยทำ" → "เทียบกับยอดผลิตสูงสุดต่อเดือนในอดีต (Historical peak)"; flag "สูงกว่ายอดผลิตสูงสุดที่เคยทำ" → "สูงกว่าที่เคยผลิตได้ในอดีต (ไม่ใช่ขีดความสามารถ)"; the no-stock note "… ผลิตตามความต้องการทั้งหมด" → "… ผลิตตามยอดทาย + ออเดอร์ทั้งหมด" |
| material_plan | 1 | "ขาดแล้ว สั่งตอนนี้ไม่ทัน" → "เลยกำหนดสั่ง (Late to order) สั่งวันนี้ของมาไม่ทันแผน" (also the executive summary's material watch-out) |
| index.html | 4 | executive card 3 sub "ดีกว่า Naive" → "Relative MAE ต่ำกว่าวิธีเทียบ Naive (ใช้ยอดเดือนก่อนเป็นค่าทาย) ตามเกณฑ์ร่าง · ฝ่ายที่พิสูจน์แล้วว่าดีกว่าจริงดูในหน้ายอดขาย · ยืนยันเกณฑ์หลังรอบ 5 ธ.ค. 69" (date from config); Trend glossary MPS → "MPS (open PO) = PO ที่รับจากลูกค้าแล้ว รอส่งมอบ ยังไม่ใช่ยอดที่ส่งแล้ว กราฟและโมเดลทายนับรวมเป็นความต้องการ (Actual + MPS)"; the executive material watch-out; assumptions row "ถึงผ่าน" → "ถึงนับว่าถึงเกณฑ์", "ต่ำกว่า 1 ผ่าน, ต่ำกว่า 0.7 ดี" → "ต่ำกว่า 1 ถึงเกณฑ์ผ่าน, ต่ำกว่า 0.7 ถึงเกณฑ์ดี" |

**"ผ่าน" conflicts: 5 found, 5 resolved.** Final wording: a result below the pass line reads "ถึงเกณฑ์ผ่าน (ร่าง)" (it meets the DRAFT criteria); under the criteria table: "▸ ถึงเกณฑ์ร่าง ยังไม่ได้แปลว่าพิสูจน์แล้วว่าดีกว่า Naive: ผลมาจากการทดสอบย้อนหลังเพียง 7 รอบ ดูว่าฝ่ายไหนต่างจาก Naive จริงในหัวข้อ "ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม"" and "▸ เกณฑ์เป็นร่าง ผู้บริหารยืนยันหลังรอบ 5 ธ.ค. 69" (the number of rounds and the date come from config and data at build). Internal verdict keys and thresholds are unchanged. No logic or threshold change was needed.

**Manual (docs/user_manual.md), sections added:** under "ความแม่นของการทาย": Relative MAE, Horizon 3, Tracking Signal; new "เกณฑ์ร่าง (Draft criteria)", "Shadow forecast (ยอดทายทดลอง)", "ราคาที่ใช้แปลงเป็นบาท (Realized average price)", "ฐานวันที่ของข้อมูล (Date basis)"; the MPS line, "Excess Min value" and the secondary-table note were aligned. The new text has no typed number except the marked examples (MAE 8 and 10, Relative MAE 0.8) and "Horizon 3"; thresholds and the decision date are pointed to on the assumptions tab. The manual is a markdown file fetched by the page at runtime and has no build step: its older typed numbers (for example the data date and item counts of the Trend tab, the 5th of the month, the 30 days) stay typed (see FOUND, NOT DONE).

### Checks

- **Numeric gate: identical YES.** Visible text and script numbers of all five pages before (HEAD) and after, compared as multisets by me and independently by the Validator: the only differences are the build timestamps and the numbers inside the new sentences (7, 5 ธ.ค. 69); the inventory page's embedded data differs only in its build time; `data/inventory.json` and `data/stock_daily.json` are unchanged (git diff clean), `data/assumptions.json` differs only in two Thai strings. Production log, its metadata, the score record, the plan outputs and the shadow log (last written 11:15) are unchanged (sha256 against the Prompt 16 snapshot).
- **Page check:** see the result fields in the final message (headless Edge, own PID, temporary profile deleted).
- **Validator:** no numeric mismatch; 7 sentence flags, all applied except where noted: the executive card (contradicted the significance block and was dense: reworded as above), the manual's Horizon 3 clause (unsupported: removed), the manual's field names (removed), the no-stock note term (aligned), the Σ symbol (removed), the manual's executive-summary claim (removed). Flag 2 was a verified OK.

### Deviations, decisions, found not done

- Only the ranked ten and the conflict were implemented (see above); 47 further Part 7 items are not changed.
- `data/assumptions.json` and `index.html` changed in text only; the gate is "numbers identical" rather than "bytes identical" for them, because the task also asks for their text to change.
- **Need decision:** (1) the shadow-log persistence proposal above; (2) whether to give the manual a build step (a token filled from config and data) so its older typed numbers cannot drift.
- **Found, not done:** the other 47 Part 7 items (medium, Claude Code with the user's approval of each text); S&OP Plan tab text (Part 7 items 4, 34 to 38: "สมมติ", "ข้อมูลสมมติ (placeholder)", "Chase Strategy", "Odoo Module" and others) left as it is by the rule (small, user); the manual's typed numbers (small to medium, Claude Code).

### Tests and page check

- Full suite: 729 passed, 1 failed in the first full run (an executive-summary text test still held the old card wording); that test was updated and re-run: 37 passed in its file. Final: 730 passed, 0 failed, 0 skipped; database connection attempts 0 (4 blocked deliberate attempts made by the block's own test).
- Page check (headless Edge on a temporary profile, a local web server for the manual's runtime fetch; only the two PIDs I started were closed, the profile deleted): index.html with the five tabs (S&OP Plan (เดิม), สรุปผู้บริหาร, Trend, สมมติฐานที่ใช้อยู่, คู่มือการใช้งาน) all present and switching, 0 script errors (one 404 for /favicon.ico, which the page never had; the same at HEAD); card 3, the assumptions row and the seven new manual headings render; sales_report (9 sections, new verdict words in all 7 rows, freshness line, shadow line visible), inventory, operation_plan and material_plan load with 0 script errors and show the changed text.


## Prompt 18

Test-suite re-verification, then durable forward-test evidence: vintage series snapshots and an automatic backup. Run 2026-10-09 (`git pull` first: up to date at 7d748a6; Get-Date 13:05 at the start). Database sessions: 0. New repo files: none. Generated (git-ignored): `output/forward_test/vintage_series/vintage_002_fit_series.csv.gz` and the first backup folder.

### Step 0

Full suite before any change, on 7d748a6: **730 passed, 0 failed, 0 skipped**; database connection attempts 0 (4 deliberate blocked attempts made by the block's own test).

### Step 1, backup location (checked before any code)

- **a.** The user-level environment variable `OneDriveCommercial` exists (a registry value in the user's environment, expandable string) and the folder it names exists and is writable (a temporary file was created and removed). Shown as `%OneDriveCommercial%\sale_forecast_backup`.
- **b.** The scheduled task `SaleForecastMonthlyRefresh` (read only, not modified) runs as the same user account as this session, logon type Interactive, run level Limited, next run 2026-11-05 07:00.
- **c.** A process started the way the task starts (`cmd.exe /c <python> <script>`) reads the variable, sees the folder and can write to it. Limit of this evidence: I started it from this user's session, not from Task Scheduler itself; an Interactive task runs in the user's logon session and gets the same user environment, and it runs only while that user is logged on (as before this task).

### Step 2, snapshots

- **Vintage 2: exact YES.** Fitting on the saved snapshot reproduces the vintage's production forecast (2,340 rows: 2,010 Item, 240 Type, 90 Category; 390 series compared) with a largest difference of **0.0** and its stored Holt shadow back-fill (288 rows) with **0.0** (tolerance 6e-5, the log's 4-decimal rounding). Snapshot: 31 months, 2024-02 to 2026-08, 1,103,600 bytes uncompressed, sha256 `c1a9b1a828c799fe8017e03aca83f1f97cde10fbb2445e151486db456a54e236`. The check runs on the bytes that are saved, read back; nothing is saved when it fails (tested).
- **Vintage 1: not reproducible.** Its window is 2024-01 to 2026-07; the first month is no longer in the saved series. Rebuilding it from the sales history pulled 2026-10-05 gives forecasts that differ from vintage 1's stored forecast by up to **0.1411** units over 390 series (the history has been revised since 2026-09-07). Recorded in its metadata as not reproducible with that reason; no file saved.
- **Metadata fields added (exact names).** Production metadata: vintage 2: `fit_series_file`, `fit_series_source`, `fit_series_sha256`, `fit_series_n_bytes`, `fit_series_hash_basis`, `fit_series_provenance`; vintage 1: `fit_series_snapshot` ("not_reproducible"), `fit_series_snapshot_reason`. Shadow metadata, vintage 2: the same six `fit_series_*` fields. No existing field changed and every `row_integrity_hash` is unchanged. For new vintages the shadow metadata now keeps the `fit_series_*` fields it copies from the production entry (vintage 3 on, step 5 already saved the series).

### Step 3, backup

At the end of every real monthly run, after the pages are built and committed, the job copies the production log and metadata, the shadow log and metadata, the score record (and its integrity file, which the record needs to be read) and all snapshots to `%OneDriveCommercial%\sale_forecast_backup\<run date>\`, checks every copy by sha256 against its source and writes `SHA256SUMS.txt` there. Same-day second run: `<run date>_<time>`. Nothing is deleted or overwritten. Only the folder name and the variable name are in config (`backup`).

**First backup, today:** `%OneDriveCommercial%\sale_forecast_backup\2026-10-09`, 8 files (7 evidence files and `SHA256SUMS.txt`), 1,034,337 bytes of evidence (1,035,045 with the sums file); sha256 of all 7 match their sources and the sums file: **YES** (also recomputed by the Validator).

**Failure behaviour (all tested with a temporary folder, no real OneDrive):** a copy that does not match its source fails the backup: YES. A failed backup leaves every step ok, the commit and push done and the pages built, writes `backup.status = FAILED` and the reason (path masked) to the run log, and the command exits non-zero: YES. A missing environment variable (or a folder that does not exist) is a clear error naming the variable, creates nothing anywhere and falls back to no other location: YES. A dry-run, sandbox or offline run makes no backup and says so.

### Checks

- **Gate unchanged: YES.** Production log, shadow log, score record and its integrity file are byte-identical (sha256) to before; the two metadata files differ only by the fields listed above; the operation and material plan outputs are identical; `data/` files and all pages are unmodified (git status).
- **Tests added** (`tests/test_vintage_series.py`): vintage 2 rebuilt from its saved snapshot equals the production forecast and the shadow log; a series that does not reproduce is never saved; backup then restore gives identical sha256 for every file and a second backup does not touch the first; a corrupt copy fails; a missing variable or folder is a clear error with no fallback; a failed backup exits non-zero with the pages built and the reason in the run log; a real run with the variable missing records a failure, not a skip. One outdated test (vintages 1 and 2 have no snapshot) was replaced.
- **Full suite after the change: 736 passed, 0 failed, 1 skipped** (737 collected); database connection attempts 0 (4 deliberate blocked attempts made by the block's own test). The one skip is `tests/test_inventory_page_sources.py:186`, which skips by its own design when the vintage it compares has a saved fit series; vintage 2 now has one, so it no longer runs the file-based comparison. It is listed as skipped, not passed.
- **Page check:** sales_report, inventory, operation_plan and material_plan opened in headless Edge on a temporary profile (own PID closed, profile deleted): 0 script errors, text lengths identical to the pre-task pages (13,937; 25,237; 44,667; 302,185 characters), the shadow line still visible, no visible change.
- **Validator (independent code):** **MATCH** on the snapshot (its own refit gives a largest difference of 0 over the 2,340 production and 288 shadow rows), the metadata, the backup (7 of 7 sha256) and the gate; no path or login name in the diff. Its notes: an aborted run (a step that fails) makes no backup and the run log then has no `backup` key (the exit is non-zero, so not silent); the mask replaces the exact variable value only (an error text with a differently written form of the path would not be masked); a failed run leaves a partial dated folder (no `SHA256SUMS.txt`, so recognisable).

### Deviations, need decision, found not done

- **Deviations.** The backup also copies the score record's integrity file (the record cannot be verified without it); the backup runs after the commit and push, so a failure is reported but does not undo the published pages (as asked).
- **Need decision.** (1) Should an aborted run (a step before the end fails) still try the backup of what exists? Today it does not; the previous backups stay. (2) Task Scheduler's task is Interactive only: if the user is not logged on at 07:00 on 2026-11-05 the run (and the backup) does not happen, as before; changing the task was out of scope.
- **Found, not done.** The moving-average comparator log (`forward_test_comparator_log.csv` and metadata, first rows with vintage 3) is the same kind of git-ignored single copy and is not in the backup list: small, user decision. The backup keeps every dated folder forever (about 1 MB each): none now. Old reports under `docs/reports/summary` contain the login name (five files, predate this task): small, user.


## Prompt 19

Login names out of the public repo, scheduled-task settings (read only), backup hardening and the permanently skipped test. Run 2026-10-09 (`git pull` first: up to date at ad61ed9; Get-Date 13:58 at the start). Database sessions: 0. New repo files: none. No value of any login is written here; locations are file:line only.

### Step 1, login names

- **Scan.** All tracked files, case-insensitive, for the Windows login (environment variable plus the user-profile folder name), the DB login (read from the app's own credential source, `.env`, without connecting) and the git author name as a third candidate. **The DB login is the same value as the Windows login**, so both types hit the same lines.
- **Hits before (8 locations in 5 files, none outside `docs/reports/summary`):**
  - Windows login: `check_v1_v2_v3.md:13` (task event log, user of the scheduled launch); `task2cfix2_validator_report.md:20` and `:25` (the Python path of the scheduled command).
  - DB login: `phaseE0_synthesis_report.md:16`, `:54`, `:124`; `phaseE0_validator1_leakage_report.md:118`; `phaseE0_validator2_cancellations_report.md:49` (the SQL Server login whose password had expired).
  - Other: `check_v1_v2_v3.md:24` holds the git author's first name inside the public GitHub Pages address of this repository (the account name in the URL). It is the repository's own public address, not a login, and is **left as it is** (a placeholder would break the reference; see NEED DECISION).
- **All replaced: YES.** The eight locations now read `<windows-login>` (3) or `<db-login>` (5); the surrounding text is unchanged. A re-scan finds 0 hits of either type.
- **Git history (read only, counts only; nothing rewritten, no force push):** 268 commits in all refs. The login value appears in the content of **8 commits** (the same 8 for both types, since it is one value; `git log -S`, exact case and case-insensitive agree); in 0 commit messages. **In the commit metadata, the author e-mail field contains the login value in 268 of 268 commits and the committer e-mail in 267 of 268** (the author and committer names do not). That metadata cannot be changed without rewriting history.
- **DB login readable without connecting: YES** (parsed from `.env`; no connection).
- **Test added** (`tests/test_guards.py::test_no_windows_login_or_db_login_appears_in_a_tracked_file`): fails, naming file:line only, if any tracked file contains the Windows login or the DB login. When the DB login cannot be read it prints and warns that it checked the Windows login only (never a silent pass), and it fails when even the Windows login cannot be read. Checked that it detects a planted value.

### Step 2, scheduled tasks (read only; nothing modified)

| field | SaleForecastMonthlyRefresh | SaleForecast_PostingDelaySnapshot (the daily job) |
|---|---|---|
| StartWhenAvailable | True | True |
| WakeToRun | False | False |
| DisallowStartIfOnBatteries | False | False |
| StopIfGoingOnBatteries | False | False |
| RunOnlyIfNetworkAvailable | False | False |
| ExecutionTimeLimit | PT72H (72 hours) | PT72H |
| MultipleInstances | IgnoreNew | IgnoreNew |
| logon type / run level | Interactive / Limited, the current user | Interactive / Limited, the current user |
| last run | 2026-10-05 07:40:43 (scheduled 07:00), result 0 | 2026-10-09 12:00:01, result 0 |
| next run | 2026-11-05 07:00 | 2026-10-10 08:00 (two daily triggers) |
| missed runs counted | 0 | 0 |

Only these two tasks of this project matched a search of all scheduled tasks for the project folder and the stock job. The monthly task started 40 minutes late on 2026-10-05, consistent with StartWhenAvailable catching up a missed start.

### Step 3, backup hardening

- **Moving-average comparator log added** to the backup list: `output/summary/forward_test_comparator_log.csv` and `output/summary/forward_test_comparator_metadata.json` (`src/ma_comparator.py` paths). **They do not exist yet** (vintages 1 and 2 predate the comparator; its first rows come with vintage 3 at the 2026-11-05 run), so today's backup cannot hold them; the result says "comparator log: not present yet", and from the first run that creates them they are copied and checked like the rest. A log without its metadata is an error, not a skip (tested).
- **Atomic backup.** The files are copied into `_incomplete_<name>` next to the dated folder, every sha256 is verified, `SHA256SUMS.txt` is written, and only then the folder is renamed to the dated name. Any failure removes the temporary folder (only that one) and raises; no partial dated folder is ever left. Nothing is overwritten or deleted.
- **Masking.** Every message goes through one function that replaces the OneDrive root (back or forward slashes, doubled back slashes, any letter case), the user-profile folder, any `<drive>:\Users\<user>` path and the bare Windows login, with `%OneDriveCommercial%`, `<windows-login-path>` or `<windows-login>`.
- **New backup now:** `%OneDriveCommercial%\sale_forecast_backup\2026-10-09_140327` (a second backup the same day goes to its own folder; the first, `2026-10-09`, is untouched), 7 files plus `SHA256SUMS.txt`, 1,034,337 bytes, sha256 of every file matches its source: **YES**; no leftover temporary folder; all 7 files are identical to the first backup's, so nothing changed since Prompt 18.

### Step 4, the permanently skipped test

`tests/test_inventory_page_sources.py::test_the_tracked_pages_history_equals_the_log_vintages_series_for_every_item` no longer skips when the vintage has a saved fit series. It now reads the saved snapshot, checks its sha256 against the vintage's metadata and compares the tracked inventory page's embedded `actual_history` of every item with the snapshot (values to 0.001 and the number of months equal to `fit_n_months`). It passes for vintage 2. It still skips (and says so) only when the forward-test log or the monthly series is not on the machine.

### Checks

- **Gate unchanged: YES.** The production log, shadow log, score record, their metadata and the vintage 2 snapshot are identical to the Prompt 18 backup (sha256, 7 of 7); the plan outputs are identical to the earlier snapshot; `data/` files and the four pages are unmodified (git status). In the reports only the eight placeholder substitutions changed.
- **Tests added:** an injected copy failure leaves no dated folder and no temporary folder, the reason carries no resolved path, the job exits non-zero with the pages built (and a later backup the same day is a normal dated folder); the comparator log and metadata are in the backup when they exist; masking covers each path form; the login-scan test; the converted inventory test.
- **Full suite: 741 passed, 0 failed, 0 skipped** (exit 0); database connection attempts 0 (blocked attempts only the block's own test). No skip remains: the inventory test that skipped is converted, and one earlier suite run that stopped at 77% without a summary (the process ended, not a test failure) was re-run in full.
- **Page check:** index.html with its five tabs (S&OP Plan (เดิม), สรุปผู้บริหาร, Trend, สมมติฐานที่ใช้อยู่, คู่มือการใช้งาน), sales_report, inventory, operation_plan and material_plan opened in headless Edge on a temporary profile (only my own Edge and local web server PIDs closed, profile deleted): 0 script errors on the four pages (text lengths 13,937; 25,237; 44,667; 302,185 characters, identical to before), the five tabs present and switching, the new manual headings, card 3 and the shadow line render; the only console message on index.html is the /favicon.ico 404 that the page never had (same before).
- **Validator:** **MATCH.** Its own scan of all 384 tracked files finds 0 hits for the Windows login, the DB login (same value), the profile folder name and its 8.3 short form, and the OneDrive path; the five reports hold 3 placeholders for the Windows login and 5 for the DB login, 8 changed lines, each only that substitution; the new backup is 7 of 7 sha256 matches against its sums and the sources, the older folder is intact and identical, no temporary folder exists, the comparator log does not exist yet; the gate files equal the earlier backup. Its notes (not done, small): a stale _incomplete_ folder after a power loss or a locked cleanup is not checked at the next start; the 8.3 short form and the DB login are not in the masking function (the DB login equals the Windows login here); the login-scan test warns instead of checking the DB login when .env is missing; the inventory test's broad except hides a corrupt log as a skip.

### Deviations, need decision, found not done

- **Need decision (1), history rewrite, facts only.** The login value is in the file content of 8 commits (the same 8 for both types) and in the author e-mail field of 268 of 268 commits and the committer e-mail of 267 of 268. Commit metadata (author and committer fields) changes only by rewriting every commit; file content in the 8 commits changes only by rewriting from the earliest of them forward. A rewrite changes every later commit hash, needs a force push to the public repository and invalidates existing clones (the publishing clone and the pre-registration commit hashes quoted in reports, for example 8f8ef46 and 717f2cb). GitHub caches and forks may keep the old commits. The current files are clean. No history operation was run.
- **Need decision (2), task settings that would let the 2026-11-05 07:00 run happen with the user not logged on.** Today logon type is Interactive: the task runs only in a session of the logged-on user; with StartWhenAvailable True a run missed because the user was logged out or the machine was off is started when the conditions are met again (consistent with the 2026-10-05 start 40 minutes late; the logged-out case itself was not tested). The settings that change this are the logon type of the principal:
  - **Run whether the user is logged on or not, password stored** (logon type Password): Windows stores the account password for the task; it is entered once when the task is saved; it must be updated when the account password changes. The task then runs in a non-interactive session with the user's profile.
  - **Run whether the user is logged on or not, password not stored** (logon type S4U): no password stored; the task runs as the user without network credentials of that user. The pull and push to GitHub use the Windows credential store of the user, which an S4U session cannot be assumed to read; this would need a trial run.
  - Both leave the account's rights as they are (run level Limited). Neither wakes a sleeping or shut-down machine: that is WakeToRun (currently False, needs wake timers allowed) and the machine being on. The OneDrive variable lives in the user's environment, which a stored-password session loads (not verified; a trial run would show it). This task did not change any setting.
- **Deviations.** None beyond the comparator files not existing yet (stated above).
- **Found, not done.** The GitHub account name in the public Pages address at `check_v1_v2_v3.md:24` (small, user: it is the repository's address, left as it is). The old `forecast/Chase S&OP Plan 2026 - PEM Group.html` and other generated pages were not scanned beyond the tracked-file scan above (they are included in it: 0 hits).


## Prompt 20

Secret history check, database-login retry safety and three small hardening fixes. Run 2026-10-09 (`git pull` first: up to date at bc62e6d; Get-Date 14:59 at the start). Database sessions: 0 (no connection and no network connection of any kind, not even the preflight against the real host; the preflight was tested with a fake network). New repo files: none. No password, login or host value is written here.

### Step 1, secret history check (read only; no history operation)

Refs scanned: 3 (the local branch and two remote-tracking refs; no tags), 269 commits.

- **(a) Credential-like files ever committed:** one name matches, `.env.example` (1 commit). It is the template: its one version holds no password, no login and no host; the two non-empty values in it are the database name and the ODBC driver name. `.env` itself was never committed (no path of that name in any of 541 distinct paths ever committed).
- **(b) The DB password value of the current `.env`:** 0 commits whose diff adds or removes it, 0 commits whose message contains it.
- **(c) Other secret-like content in every added line of every commit:** two pattern hits, both false positives (`src/db.py`, 1 commit: the code that reads the password from the environment variable; `STATUS.md`, 1 commit: a documentation example of a connection URL with placeholders; neither contains the real password). No private key block, GitHub token, cloud access key or bearer token.
- **Informational (not a secret by the rule, reported for the user):** the DB host value is in `STATUS.md` (current file, 1 commit); the database name is in many documents (37 commits); the DB login is the Windows login value already reported in Prompt 19.

No exposure was found, so Step 2 proceeds.

### Step 2, DB-login retry safety

**DB-connect paths and the logins each can make in one run** (every `run_query` outside a `session()` opens its own connection; a `session()` opens one):

| job | file:function | logins in one successful run | retry found |
|---|---|---|---|
| monthly | `monthly_refresh.py:step1_pull_data` then `load_data_all_divisions.py` (1 query) | 1 | none |
| monthly | `_pull_stage`: `load_data_full.py` (2 queries) | 2 | none |
| monthly | `_pull_stage`: `build_inventory_dataset.py --save-pulls` (5 queries) | 5 | none |
| monthly | `_pull_stage`: `material_plan.py --pull` (3 in a session) | 1 | none |
| monthly | `_pull_stage`: `build_trend_tab.py --pull` and `--pull-targets` (sessions) | 1 each | none |
| monthly | step 4 `_run_regeneration_step`: `investigations/order_leadtime.py`, `delivery_performance.py` | 1 each | none |
| monthly | step 6 `_fill_actuals` then `score_forward_test_all_divisions.pull_actuals_forecastDate` (only when a month passed the guard) | 1 | none |
| daily | `snapshot_daily.py:main` then `db.session()` (posting-delay query, stock snapshot and the stock job's pull, one connection) | 1 | none |
| both | `db.py:get_connection / run_query / session` | one `engine.connect()` per call | none (no retry loop, no pool pre-ping, no connect-retry option in the connection string) |

No retry loop, reconnect-on-failure or sleep-and-retry exists anywhere in the code. **Library level:** nothing configures a retry. The Microsoft ODBC driver has its own connection-resiliency default (a reconnect of a connection that broke after it was established); from the vendor's documentation it does not apply to a refused first login, but that is not verified here (no connection allowed), and a connection-string option to switch it off was not added because an older driver could reject an unknown keyword and break the pull.

**Task-level restarts (read only):** monthly task RestartOnFailure count 0 (interval none). Daily task count 0 (interval none). The daily task does have a second daily trigger at 12:00 (the decided noon start), which in effect is a second login attempt the same day.

**What did violate "one login attempt per run on failure", and the fixes:**
1. After a failed **step 1 auxiliary pull** or a failed **step 4 database analysis script** the runner went on to the next database stage (each its own login). Now the first failed database stage stops every later database stage of the run (they are recorded as skipped with the reason) and the step ends the run with a non-zero exit. (The main pull already aborted at once.) This changes one earlier behaviour: a failing auxiliary pull used to leave the older file in place and let the run finish; it now stops the run. Reason: the stage's failure cannot be told from a login refusal without more machinery, and the account's safety comes first.
2. A script that caught the first connection error and tried again in the same process would have logged in again. `db.py` now remembers the first failed login of a process and refuses every later one at once (`DatabaseLoginAlreadyFailedError`), without connecting.
3. The daily job's **noon start** logged in again after a refused login of the morning. It now reads today's failure logs and, when the server refused the login earlier today, ends non-zero without connecting and records why. After an **unreachable host** (no login was attempted) it may still try again.

**Preflight:** existed in the monthly job (a TCP connect to the host and port with a 5 second timeout before the first login, in step 1). Added in `db.py` (`preflight`, `require_reachable`) and used by the **daily job** before its login, which had none. Timeout 5 seconds, no authentication; unreachable gives exit 1 with "DB host unreachable (off org network?)", a log with kind `unreachable` and no login attempt. The port is 1433 unless `DB_SERVER` names `host,port` (the monthly job ignored an explicit port before; now it uses it). The 1433 assumption is as before and worked on 2026-10-02 and 10-05; if the named instance ever listened elsewhere the preflight would refuse a legitimate run (it would say so and make no login).

**Attempt counts in tests (fake connector and fake network; the real database and network are never touched):**

| test | login attempts |
|---|---|
| monthly, main pull refused | 1 script started, then the run stops (0 further) |
| monthly, a later database stage fails | main pull, pilot file, inventory pull started; the 3 later pulls never started |
| monthly, unreachable host | 0 (no script started), non-zero exit, reason in the run log |
| monthly, success | every stage started once, no abort |
| db helper, failed login then 2 more calls | 1 attempt; the 2 later calls refused without connecting |
| db helper, session with 2 queries | 1 attempt |
| daily, failed login | 1 attempt, non-zero; the second start of the same day: 0 more attempts, non-zero |
| daily, unreachable host | 0 attempts, non-zero; after the network is back the next start makes its 1 attempt |

### Step 3, three small fixes

- **Stale `_incomplete_` backup folders:** at the start of every real monthly run, `check_stale_backup_folders` lists `_incomplete_*` folders in the backup root. A folder is removed when it is older than `backup.stale_after_minutes` (30, config) and the process id in its name is gone; otherwise it is kept and reported with the reason (younger, process still running, or could not be removed). Names only go to the run log (`stale_backup_folders`). A dated folder is never touched. On the real root today: 0 found.
- **Masking of the 8.3 short name:** the mask now also covers the short forms of the user folder and of the OneDrive root (read from Windows at run time), in any slash form and case. Checked on this machine's real short name as well as with a fake one in the test.
- **Inventory test:** the broad `except` is gone. A log that is not on the machine is a skip (it says so); a log that is there but corrupt or unreadable now raises and fails the test (a test proves it for a corrupt metadata file and for a log without the needed columns).

### Checks

- **Gate unchanged: YES.** The production log, shadow log, score record, their metadata and the vintage 2 snapshot are identical (sha256) to the Prompt 18 backup; the pages, `data/` and the plan outputs are untouched.
- **Full suite: 756 passed, 0 failed, 0 skipped** (exit 0); database connection attempts 0 (blocked attempts only the block's own test); no network call was made by any test (the preflight is tested with a fake network).
- **Page check:** index.html with its five tabs, sales_report, inventory, operation_plan and material_plan in headless Edge on a temporary profile (own PIDs closed, profile deleted): 0 script errors on the four pages, text lengths identical to before (13,937; 25,237; 44,667; 302,185), the five tabs present, the manual headings render; the only console message on index.html is the `/favicon.ico` 404 the page never had.
- **Validator:** **MATCH.** Its own scan of all 3 refs (269 commits) reproduces step 1: `.env` never committed, the only credential-named file is the template, the DB password value is in 0 commits (diff, messages and a full tree search of every commit), no key, token or cloud-key pattern; the two pattern hits are code and documentation text. The gate files equal the Prompt 18 backup (7 of 7), only the 9 expected files are modified, 0 hits of either login in tracked files. It confirmed that every database login goes through one function, that no path retries, and that guarantees A to D hold (no further login in a process after a failure; no later database stage after a failed one; unreachable host: zero logins and a non-zero exit in both jobs; the noon start does not log in again after a refusal but may after an unreachable host). Gaps it names, not fixed: the failure memory is per process (a refusal in one task does not stop the other task or a manual re-run); a child script that swallowed a login error and exited 0 would not stop later stages (none does today); the refusal is recognised by text, so a differently worded refusal counts as 'other' and the noon start would try again; 11 hand-run investigation scripts bypass the single login function (not launched by either task); step 4 runs its non-database scripts before the abort; the preflight's 1433 assumption would stop (not log in) if the instance port changed (11 of 11 earlier monthly runs reached it).

### Deviations, need decision, found not done

- **Need decision.** None required by this task. One note for the user: item 1 above makes a failing auxiliary pull stop the monthly run; if the user prefers the earlier tolerant behaviour for non-login failures, the stage's failure would have to be classified (login or connection error against a query error), which needs the child scripts to report it.
- **Found, not done (from the Validator).** The failure memory is per process, so a refusal in one task does not stop the other task or a manual re-run (medium, user decision, a small persisted lock file would do it); the refusal is recognised by its text, so a differently worded refusal would let the noon start try again (small); 11 hand-run scripts in `src/investigations` bypass the single login function (small); a child script that swallowed a login error and exited 0 would not stop later stages (none does today).
- **Found, not done.** The DB host value appears in the current `STATUS.md` (and 1 commit): a server name, not a credential — small — user decision. The DB driver's own connection-resiliency default is not verified (no connection allowed) — small — user. The earlier notes still open: the daily noon start and the monthly task remain Interactive-only (decision of the user: unchanged).


## Prompt 21

Line-level audit of the material plan: labor, subcontract and service charges are not materials to stock. Run 2026-10-09 (`git pull` first: up to date at c8f59a8; Get-Date 15:30 at the start). Items are named by code only; descriptions appear only on the generated page.

### Step 1, evidence for classification

**Local data cannot classify the items.** The saved pulls hold the BOM line type (Standard, Machine Hour or Labor hour), the unit, the item description and the raw-material stock; for the example `LABOR-VT-R-VT-0269` the BOM line is Standard with unit "-", it has stock records in the raw-material warehouses and 50 purchase-order lines, i.e. nothing there marks it as a service. So the item master was read from the database.

**Database, read only, 4 sessions, 4 login attempts, none failed, no retry.** Each session started with the reachability preflight and went through `db.session()` (one login), SELECT only: (1) the schema (information schema tables and columns); (2) the item attributes of the 2,244 components on the material plan; (3) the columns of the purchase-order tables and the stock-movement types of the same items; (4) the item attributes of the 439 items of the operation plan and the inventory page. Tables and columns used: `Cube_ItemList` (ItemCode, Condition, MainWarehouse, ItemGroup, Assortment1, 2, 6, 9, 10), `Cube_Inventory_Aging` (Warehouse, ItemCode, Type, ItemStatus, Unit, GLAccount, GLDescription, Stock), `Cube_Inventory_Exact` (product category and type), `cube_inventory_tran` (movements per item: count, first and last date, receipts, and the movement types). The purchase-order tables (`Cube_PO_Exact`, `Cube_ReceiveRM`, `Cube_tobe_received`, `Cube_PriceList`) hold no item type or service flag. The result is saved under `output/data/material_pull/` (generated, git-ignored) and the same read is now part of the monthly material pull (`material_plan.py pull_item_attributes`, in the session the pull already opens).

**What the item master says (2,238 of the 2,244 plan items have a master record).**
- Item group: 100 for 2,175 items, 2000 for 45, 700 for 7, 300 for 5, 200 for 4, 400 for 1, 4012 for 1.
- Stock account (GL description): Raw materials 2,220, Supplies 7, Finished goods 6, Semi Products 4, Direct Labor Control 1, Contra service 1.
- Item status Active for all, type S for all, condition A for all.
- **Attribute values that mark a non-stock item:** item group 2000 (45 items), 400 (1) and 4012 (1); stock account Direct Labor Control (1) and Contra service (1) (the same two items as groups 400 and 4012). That is 47 items marked in all.
- **What the master does not mark:** most labor and subcontract items are set up as ordinary stocked items: item group 100, stock account Raw materials, normal receipts and issues in `cube_inventory_tran` (movement types do not separate them either).

**Two independent directions on the 2,244 components.** A = the item master marks it: the item group OR the stock account is a marker value (every master row of the item must agree). The 45 group-2000 items carry the stock account Raw materials, so the stock account confirms only 2 items (groups 400 and 4012) and the 28 rest on item group 2000 plus the description; under a stricter reading (both must mark) only 2 would qualify. B = its description holds a keyword (ค่าจ้าง, จ้าง, ค่าแรง, ค่าบริการ, ค่า บริการ, ค่าขนส่ง, LABOR, SERVICE, LOGISTICS COST, SLIT COST, ค่าชุบ; the data also shows OUTSOURCE, which is only listed).

| | items |
|---|---|
| A and B (excluded) | 28 |
| A only | 19 |
| B only | 56 |
| neither (ordinary materials) | 2,135 |
| no master record | 6 |

Excluded by category: labor 15, subcontract 9, service 4, other 0. The excluded codes:
- labor (15): `LABOR-CP-C-00-0207CV`, `LABOR-CP-C-00-0210CV`, `LABOR-LS-R-01-0307`, `LABOR-MC-R-01-0501`, `LABOR-RS-R-10-0004-I`, `LABOR-VT-R-09-0027`, `LABOR-VT-R-VT-0269`, `LABOR-VT-R-VT-0301`, `LABOR-VT-R-VT-0309`, `LABOR-VT-R-VT-0319`, `LABOR-VT-R-VT-0324`, `LABOR-VT-R-VT-0327`, `LABOR_TF-R-08-01090`, `LABOR_TF-R-09-0903`, `LABOR_TF-R-09-0904`
- service (4): `LOGISTICS COST-01`, `LOGISTICS COST-04`, `SLIT COST-PAPER-11`, `SLIT COST-PAPER-5`
- subcontract (9): `LABOR-02-00-R-2031`, `LABOR-02-00-R-2220`, `LABOR-02-00-R-7035`, `LABOR-02-00-R-7036`, `LABOR-DS-R-03-1006`, `LABOR-DS-R-03-1007`, `SLIT COST-COPPER FOIL-3`, `SLIT COST-COPPER FOIL-7`, `SLIT COST-COPPER FOIL-8`

**A only (19, stay in the plan):**
- item group 2000, stock account Raw materials, keyword none (19): `02-00-R-7048`, `LABOR-RS-R-06-0006`, `LABOR-RS-R-06-0017`, `LABOR-RS-R-06-0025`, `SLIT COST-01`, `SLIT COST-04`, `SLIT COST-09`, `SLIT COST-20`, `SLIT COST-26`, `SLIT COST-27`, `SLIT COST-28`, `SLIT COST-29`, `SLIT COST-30`, `SLIT COST-31`, `SLIT COST-35`, `SLIT COST-COPPER FOIL-105`, `SLIT COST-PAPER`, `SLIT COST-PAPER-12`, `SLIT COST-RESIZE`

**B only (56, stay in the plan):**
- item group 100, stock account Raw materials, keyword ค่าจ้าง (20): `LABOR-02-00-R-1951-1`, `LABOR-02-00-R-2184-1`, `LABOR-02-00-R-4361`, `LABOR-02-03-R-8326-1`, `LABOR-02-03-R-8334-1`, `LABOR-03-CC-R-1022`, `LABOR-03-CC-R-1023`, `LABOR-03-CC-R-1034`, `LABOR-03-CC-R-1049`, `LABOR-03-CC-R-1052`, `LABOR-03-CC-R-2071`, `LABOR-03-CC-R-5107`, `LABOR-03-CC-R-9081`, `LABOR-03-CC-R-9084`, `LABOR-03-CC-R-9085`, `LABOR-DS-R-03-0213`, `LABOR-DS-R-03-0232`, `LABOR-DS-R-03-0233`, `LABOR-DS-R-03-0234`, `LABOR_TF-R-03-0122`
- item group 100, stock account Raw materials, keyword ค่าชุบ (3): `LABOR-DS-R-03-0214-1`, `LABOR-DS-R-03-0215-1`, `LABOR-DS-R-03-0216-1`
- item group 100, stock account Raw materials, keyword จ้าง (33): `03-CC-R-2324`, `03-CC-R-2325`, `03-CC-R-2326`, `03-CC-R-5034`, `03-CC-R-5309`, `03-CC-R-5360`, `03-CC-R-5361`, `03-CC-R-5362`, `03-CC-R-5363`, `03-CC-R-5364`, `03-CC-R-5365`, `03-CC-R-5368`, `03-CC-R-5369`, `03-CC-R-5372`, `03-CC-R-5373`, `03-CC-R-5374`, `03-CC-R-5375`, `03-CC-R-5376`, `03-CC-R-5380`, `03-CC-R-5381`, `03-CC-R-5384`, `03-CC-R-5385`, `03-CC-R-5396`, `03-CC-R-5512`, `03-CC-R-5536`, `03-CC-R-5537`, `03-CC-R-5542`, `03-CC-R-5543`, `03-CC-R-5544`, `03-CC-R-5578`, `03-CC-R-6000`, `03-CC-R-9979`, `LABOR-02-00-R-2026-1`

**No master record (6, stay):** `COST OF PAPER`, `LABOR_TF-R-09-0027`, `TF-R-01-0077`, `TF-R-05-0216`, `TF-R-08-0223TF`, `TF-R-08-0224TF`

**Separate flags (not excluded, defined from the data):** never stocked = no row at all in the stock-movement table, any warehouse (15 items): `02-00-IR-6327`, `02-00-IR-6328`, `02-00-IR-7006`, `02-00-IR-7007`, `02-03-R-8011`, `COST OF PAPER`, `LABOR-DS-R-03-1006`, `LABOR-DS-R-03-1007`, `RS-F-99-180004`, `RS-F-99-180047`, `RS-R-00-180047`, `TF-R-04-1084`, `TF-R-05-0216`, `TF-R-09-0243`, `VT-F-99-010207`. Service-like unit = the BOM unit is HOUR, LOT or JOB (3 items): `LABOR-DS-R-03-1006`, `LABOR-DS-R-03-1007`, `LOGISTICS COST-01`. Consumable = the stock account is Supplies (7 items): `00-C-GS-00-006`, `00-C-GS-00-012`, `01-CS-R-0289`, `02-CS-R-0268`, `04-CS-R-0078`, `04-CS-R-0269`, `06-CS-R-0004`.

### Step 2, the rule

Config `material_plan.non_stock_rule` (attribute values, not codes, not a code prefix): excluded only when A and B both hold; A only, B only, no master record or master rows that disagree stay in the plan and are listed. Reason in config: services bought by purchase order, not stocked.

### Step 3, applied to the material plan

Excluded items produce no order quantity or order-by date and are not in any headline count. One line above the order tables, "ค่าแรง (labor) และงานจ้างภายนอก (subcontract) 28 รายการ ไม่นับเป็นวัตถุดิบที่ต้องสต็อก ... (ค่าแรง 15, งานจ้างภายนอก 9, ค่าบริการและค่าขนส่ง 4) กดดูรายการ", opens to the list of every excluded item (code, description, category). All numbers are computed at build. When the item attributes are missing the page says the check was not made and nothing is excluded.

**Reconciliation** (the recorded plan rebuilt with the same date, 2026-10-08, before and after the rule; the old rebuild equals the recorded file):

| | old | new | excluded |
|---|---|---|---|
| material lines (summary) | 2,244 | 2,216 | 28 |
| rows of the month file | 11,220 | 11,080 | 140 |
| lines in the 30-day order list | 156 | 155 | 1 |
| lines in the late order list | 584 | 568 | 16 |
| to order now (items) | 587 | 571 | 16 |
| total net requirement | 2,979,184.280 | 2,964,060.403 | 15,123.878 |
| quantity to order now | 332,629.988 | 330,086.428 | 2,543.560 |
| quantity in the 30-day list | 190,933.363 | 189,416.672 | 1,516.691 |
| quantity in the late list | 332,501.587 | 329,958.028 | 2,543.560 |

New = old minus excluded in every row (the last two differ by 0.001 only through rounding of float sums). The remaining rows of the new files equal the old rebuild exactly (in memory and in the summary file); against the old month file as recorded, 8 lines of 11,222 differ in the sixth decimal (about 1e-6, for example the net columns of `CT-R-01-0001`): a rebuild of the old plan with the rule off shows the same 8 differences, so it is floating-point noise of the rebuild, not an effect of the rule. The page shows no value in baht, so there is none to reconcile. The distinct order-by dates are the same 168 before and after (17 excluded items had a date, 14 distinct dates, all shared with other items): no date disappeared.

### Step 4, other pages

- **operation_plan.html:** 439 items. Direction A: 0 marked, direction B: 0 keyword hits (all 439 have a description). 38 of the 439 have no master record (placeholder-style finished-good codes), so they cannot be classified; they are not service-like by description. **Excluded: 0. Action: none.**
- **inventory.html:** 306 items (PEM101, PEM103, PEM107). A: 0, B: 0. **Excluded: 0. Action: none.** Their stock accounts are Finished goods and Raw materials; item group 300 and 100.
- No change to either page or its inputs.

### Checks

- **Gate unchanged: YES** for the production forecast, the forward-test, shadow and score logs and the operation-plan outputs (sha256 identical); only the material plan's two recorded files and their hash entry in the plan's integrity file changed, as the reconciliation above shows.
- **Full suite: 759 passed, 1 failed, 0 skipped** in the first full run: the executive-summary test found that the executive tab of index.html still said 584 late materials (its watch-out follows the material plan's late list, now 568). I rebuilt that tab from the saved pulls (one number changes on index.html: 584 to 568 late materials, 16 fewer) and re-ran that test file and the other index and text tests: 95 passed, 0 skipped. Database connection attempts 0 (blocked attempts only the block's own test). I did not re-run the whole suite after that one fix.
- **Page check** (headless Edge, own PID, temporary profile deleted): material_plan: 0 script errors, the note renders, closed at first, opens on click and lists 28 rows (15 labor, 9 subcontract, 4 service); `LABOR-VT-R-VT-0269` is in the expanded list and in none of the three order tables; the three tables hold 155, 568 and 2,216 rows; the ambiguous `LABOR-02-00-R-4361` is still in the order tables. operation_plan, inventory and sales_report: 0 script errors, text lengths unchanged (44,667; 25,237; 13,937), no note.
- **Validator:** **MATCH** on the counts: its own reclassification gives the same 28 (labor 15, subcontract 9, service 4), 19 A only, 56 B only, 6 without a master record and 2,135 ordinary materials, with no differing code; the reconciliation matches (2,244 to 2,216, 11,220 to 11,080 month rows, 587 to 571 to-order-now); the page note, its 28 rows and the three tables (155, 568, 2,216) are as described and none of the 28 is in an order table; 0 tracked files contain any description of an excluded or ambiguous item; every pull statement is a SELECT, one session after the preflight, no retry; the gate files are identical. Its notes: (a) 8 lines of the month file as recorded differ in the sixth decimal from a rebuild of the old plan (noise of the rebuild, shown to be independent of the rule); (b) A is the item group OR the stock account; the stock account confirms only 2 of the 28 (the other 26 group-2000 items carry the stock account Raw materials), so under a both-must-mark reading only 2 would be excluded: stated in the report and METRICS as the user's decision point.

### Deviations, need decision, found not done

- **Deviations.** Four database sessions were needed (the schema first, then the pulls). The material plan outputs were rebuilt with the recorded date 2026-10-08 so every date is unchanged. The monthly material pull now also reads the item attributes (8 more SELECTs in its existing session; the time cost of the movement query on the first real run on 2026-11-05 is not measured).
- **Need decision: ambiguous items (stay in the plan).** The 56 B-only and 19 A-only items above are listed with their master values and keyword. Facts: all 56 B-only items have item group 100 and stock account Raw materials, like ordinary materials, and they are received and issued like stock, so the master gives no unambiguous mark; this includes the injection-charge example `LABOR-02-00-R-4361`, which in this data does carry a LABOR prefix. The 19 A-only items are in item group 2000 but their descriptions name no charge (including `02-00-R-7048`, whose group is 2000 although its description reads like a physical part). Each group can be added to the exclusion by the user (for example by accepting the keyword alone for items whose stock account is Raw materials), or left.
- **Also changed (a consequence).** The executive summary tab of `index.html` counts the late materials from the material plan: its watch-out line now says 568 instead of 584 (16 fewer, the excluded items that were late). No other number on any page changed.
- **Need decision (the A reading).** The stock account confirms only 2 of the 28 excluded items; the other 26 rest on item group 2000 plus the description. If the user wants both attributes to be required, 26 of the 28 would stay in the plan.
- **Found, not done.** 38 operation-plan items with no master record (small, user). Whether the "no master record" items on the material plan (6 codes) should be checked in the ERP (small, user).


## Prompt 22

Put every material-plan line back in the tables, tag labor, subcontract and service lines with a remark and leave them out of the summary counts only. Run 2026-10-09 (`git pull` first: up to date at cda62fa; Get-Date 16:10 at the start). Database sessions: 0 (the data pulled in Prompt 21 was used). New repo files: none. Items by code only; descriptions are on the generated pages only. **This supersedes the design of Prompt 21** (its evidence and findings stand; its removal of 28 lines and its expandable note are gone).

### Step 1, the removal is reverted

The plan is rebuilt with the recorded date 2026-10-08 and no line is removed. Against the files recorded before Prompt 21: the same 2,244 lines (same codes), 11,220 month rows, identical `latest_order_date` and `to_order_now` columns, identical summary quantities (largest difference 0), and a few month-file cells that differ by about 1e-6 (the rebuild noise already reported in Prompt 21, not an effect of the remarks; the files are not byte-identical for that reason). The expandable exclusion note is removed from the page.

| table | before Prompt 21 | after Prompt 21 | now |
|---|---|---|---|
| all lines (main table) | 2,244 | 2,216 | 2,244 |
| 30-day order list | 156 | 155 | 156 |
| late order list | 584 | 568 | 584 |
| to order now (meta) | 587 | 571 | 587 |

### Step 2, remarks (config `material_plan.non_stock_rule`: keywords and attribute values, no list of codes)

- **Remark counts (lines):** ค่าแรง 27, ค่าจ้าง 62, ค่าบริการ 4 (93 not-goods lines, not counted); รอตรวจ 26 (counted). Evidence of the paid remarks: จากชื่อ for those found in the description, จากรหัส for 17 found only in the code.
- **Overlap:** 32 lines matched both a paid keyword and a รอตรวจ condition (item group 2000 or 400/4012, no master record or a work unit); the paid remark wins, as the rule says. Four of them (`LABOR-RS-R-06-0006`, `-0017`, `-0025`, `LABOR_TF-R-09-0027`) were then moved to รอตรวจ by the name review below.
- **Matches outside the expected sets** (the 28 of Prompt 21, the 56 keyword-only items, `LABOR-RS-R-06-0006`, `-0017`, `-0025` and `LABOR_TF-R-09-0027`): 10 codes, all with a LABOR- code and a description that has no keyword of the other kind: `LABOR-03-CC-R-1046`, `LABOR-DS-R-03-0196`, `-0200`, `-0201`, `-0202`, `-0203`, `-0212`, `-0214`, `-0215`, `-0216`. The two logistics lines of the Prompt 21 set (`LOGISTICS COST-01`, `-04`) were not matched by the keywords of the task and are covered by one added keyword, "LOGISTICS COST", under ค่าบริการ (a freight charge). Also added to the keyword lists: the spaced form "ค่า บริการ" that the data shows. `OUTSOURCE` is not a keyword (the 16 `03-CC-R-5xxx`/`6xxx`/`9xxx` lines carrying it only stay without remark).
- **รอตรวจ list (26, counted):** by item group (evidence จากกลุ่มสินค้า): `02-00-R-7048` and the 15 `SLIT COST-01`, `-04`, `-09`, `-20`, `-26`, `-27`, `-28`, `-29`, `-30`, `-31`, `-35`, `SLIT COST-COPPER FOIL-105`, `SLIT COST-PAPER`, `SLIT COST-PAPER-12`, `SLIT COST-RESIZE`; no master record (ไม่มีข้อมูลในระบบ): `COST OF PAPER`, `TF-R-01-0077`, `TF-R-05-0216`, `TF-R-08-0223TF`, `TF-R-08-0224TF`; moved by the name review (จากการตรวจชื่อ): the five codes below. No line matched only the work-unit condition (the three lines with a work unit also carry a paid keyword).

### Step 3, Validator name review

The Validator read the description of every one of the first 98 lines tagged as not goods. Judged physical-good: `LABOR-RS-R-06-0006` and `LABOR-RS-R-06-0025` (a part name, the remark rested on the code only). Unclear: `LABOR-03-CC-R-1046`, `LABOR-RS-R-06-0017`, `LABOR_TF-R-09-0027` (no description in the item names). The other 93 read like a charge (61 with explicit fee or labor wording; 32 `03-CC-R-*` lines "hire to make a part" read as subcontract work with lower confidence and stay tagged). No keyword matched inside a physical-good name by accident. No hard mismatch between the remark and the description; three plating charges (`LABOR-DS-R-03-0214-1`, `-0215-1`, `-0216-1`) are tagged ค่าแรง where ค่าบริการ is closer (a judgement call, left). **Moved to รอตรวจ by an explicit config exception (code and a one-line reason, no description):** `LABOR-RS-R-06-0006`, `LABOR-RS-R-06-0025` (the name reads like a physical part), `LABOR-03-CC-R-1046`, `LABOR-RS-R-06-0017` (unclear), `LABOR_TF-R-09-0027` (no description). I moved the unclear ones as well because the user's design keeps uncertain lines visible and counted.

### Step 4, summary counts

Under the 30-day list, the late list and the all-lines table one line, computed at build, for example "ทั้งหมด 2244 รายการ นับ 2151 รายการ · ไม่นับค่าแรง/ค่าจ้าง/ค่าบริการ 93 รายการ (ไม่ใช่สินค้า ไม่ต้อง stock) · รอตรวจ 26 รายการ ยังนับรวมไว้จนกว่าจะมีคนยืนยันว่าเป็นสินค้าหรือไม่". The remark (for example "ค่าแรง · จากชื่อ") sits beside the code in every table. The page showed no count before; these lines are new, and they are the counts the rule applies to. The executive tab's late-materials watch-out is the counted late lines.

| summary | all | counted | excluded (paid remark) | รอตรวจ (inside counted) |
|---|---|---|---|---|
| all lines | 2,244 | 2,151 | 93 | 26 |
| 30-day list | 156 | 154 | 2 | 1 |
| late list | 584 | 548 | 36 | 14 |
| to order now (items, meta) | 587 | 550 | 37 | n/a |
| total net requirement | 2,979,184.280 | 2,904,982.581 | 74,201.699 | included |
| quantity to order now | 332,629.988 | 317,742.392 | 14,887.595 | included |
| quantity in the late list | 332,501.587 | 317,694.006 | 14,807.581 | included |
| quantity in the 30-day list | 190,933.363 | 189,211.080 | 1,722.284 | included |

Counted = all minus the paid-remark lines in every row. **Executive watch-out (index.html): 584 before Prompt 21, 568 after it, 548 now; it equals the counted late lines on the material page: YES.** The dates did not move (the plan is rebuilt with 2026-10-08).

### Checks

- **Gate unchanged: YES.** The production forecast, the forward-test, shadow and score logs and the operation-plan outputs are byte-identical (sha256); the pages `operation_plan.html`, `inventory.html`, `sales_report.html` and `data/` are unmodified; `index.html` changes only in the watch-out number.
- **Tests added** (`tests/test_material_plan.py`, the Prompt 21 exclusion tests replaced): remarks on fixed examples (a LABOR- code, a ค่าจ้าง name without LABOR, a group 2000 item without keyword gives รอตรวจ, a no-master item gives รอตรวจ, a normal raw material has no remark, a work unit gives รอตรวจ, a config exception, a lower-case `labor_` code, a line matching both); every line stays and the recorded plan is unchanged by the remarks; paid-remark lines are in no summary count and รอตรวจ lines are in it (counted = all - paid in all three summaries, the summary text, the remark beside the code); the main table row count equals the input line count with and without the item attributes; the read-only pull test.
- **Full suite (final run, after the last code and test change): 761 passed, 0 failed, 0 skipped**; database connection attempts 0 (blocked attempts only the block's own test). Earlier full runs on the way found three test failures that I fixed in the tests (two reader-text tests flagged the item code `LABOR_TF-R-09-0027` as a config key because a config exception key is an item code; a browser test expected the code cell without the new remark), one Assumptions-tab browser test that failed once under load and passes alone, and two runs that ended early without a summary (the process stopped, not a test). This report file and the final test line were written after that run; the tests that scan documents (guards, reader text, manual notes) are re-run below.
- **Page check** (headless Edge, own PID and the local web server's PID closed, temporary profile deleted): material_plan: 0 script errors; the three tables hold 156, 584 and 2,244 rows; `LABOR-VT-R-VT-0269` (ค่าแรง · จากชื่อ) and `LABOR-02-00-R-4361` (ค่าจ้าง · จากชื่อ) are both visible in the 30-day table and in the all-lines table with their remark; the remark counts in the main table are ค่าแรง 27, ค่าจ้าง 62, ค่าบริการ 4, รอตรวจ 26; the three summary lines show the numbers above; no exclusion note. index.html executive tab: the watch-out reads 548. operation_plan, inventory and sales_report: 0 script errors, text lengths unchanged (44,667; 25,237; 13,937).
- **Validator:** **MATCH.** Own recomputation of all 2,244 remarks: ค่าแรง 27, ค่าจ้าง 62, ค่าบริการ 4 (93), รอตรวจ 26, overlap 32, with 0 codes differing from the page; tables 156 / 584 / 2,244 with no code missing; the recorded files equal the pre-Prompt-21 files in codes, lines, dates and `to_order_now` (summary quantities identical, a few month-file cells at 1e-6); the three summary lines and the quantity totals match (counted = all - paid; รอตรวจ inside the counts; to order now 587 / 550); the executive watch-out 548 equals the counted late lines; the five exception codes show รอตรวจ on the page; 0 tracked files contain a description of a remarked line; the gate files are identical. Name review: no keyword accident; two physical-good codes and three unclear codes moved to รอตรวจ; one note: an exception reason uses the English word the description also contains (left).

### Deviations, need decision, found not done

- **Deviations.** The material page showed no counts before, so the "summary counts" are new lines under the three lists (and the quantity totals are in this report only: summing quantities of different units has no meaning on the page). Added keywords beyond the task's list: "LOGISTICS COST" and "ค่า บริการ". The name review moved five codes (two physical-good, three unclear) instead of two. The evidence label "จากการตรวจชื่อ" was added for the moved codes. The priority between remarks is a config list (ค่าแรง, ค่าจ้าง, ค่าบริการ) because the order of keys in a config file is not reliable.
- **Need decision.** (1) The 32 `03-CC-R-*` "hire to make a part" lines are tagged ค่าจ้าง on the strength of the hire wording; the Validator rates that as lower confidence. If the user wants them counted, they go into the exceptions list. (2) The three plating charges are tagged ค่าแรง; ค่าบริการ is closer. (3) The 15 `SLIT COST-*` lines and `02-00-R-7048` wait for a person's check (รอตรวจ, counted).
- **Found, not done.** None beyond the items of Prompt 21.

## Prompt 23

Date and time of the work: 2026-10-12, started 08:51 (`git pull origin main` first: already at caf2ef4). Method: METRICS.md Sec.51 (dated note), Sec.53, Sec.54. No database session, no network call; the full suite made 0 connection attempts.

**Part A, scheduling.** Tasks found: SaleForecastMonthlyRefresh and SaleForecast_PostingDelaySnapshot, both run from the publishing clone (a `git pull --ff-only origin main`, then the script of that clone at each start, so new code arrives at the next start after a push). Triggers before: monthly = day 5 of each month 07:00; daily = every day 08:00 and 12:00. After (read back from the exported XML): monthly = weekly Monday to Friday 07:00; daily = weekly Monday to Friday 08:00 and 12:00; every other setting and the action are identical (compared). The change was made by me (Set-ScheduledTask, permission present) after the code was pushed (ac2a021). `run_day(year, month)` = first Monday-Friday on or after the 5th: 2026-11 = 2026-11-05, 2026-12 = 2026-12-07, 2027-06 = 2027-06-07, 2027-09 = 2027-09-06, 2027-02 = 2027-02-05. Derived dates: criteria decision (decision_month 2026-12) 2026-12-07; shadow targets 2026-09, 2026-10, 2026-11 scoreable on 2026-11-05, 2026-12-07, 2027-01-05 (30-day guard), the shadow evaluation run 2027-01-05. The typed decision_date is gone from config; pages, manual and assumptions.json show computed dates (7 ธ.ค. 69). The pre-registered Sec.51 text is unchanged; a dated note below it says the evaluation date now comes from the run day.

**Part B, login safety round 2.** LoginRefused (not an Exception subclass) on SQLSTATE 28000 (native codes, then text, as fallbacks); an excepthook in db.py gives exit code 3 in every child script that imports db (7 of the runner's children; the others do not use the database); the monthly cli and the daily job map it to 3. Exit 3 from a stage stops every later database stage and the run; another failure of an auxiliary pull keeps the previous file, writes a WARN line and ends the run with exit 2. Lock `output/state/db_login_refused.lock` (time and job name), checked in db.preflight, db._login, the monthly cli and the daily main, never deleted by code. The DB host is in no tracked file (STATUS.md used it once; now a placeholder); tests/test_guards.py scans for it (read from .env, no connection).

**Part C, remarks (user's answers).** Counts before (Prompt 22) to after: ค่าแรง 27 to 33, ค่าจ้าง 62 to 74, ค่าบริการ 4 to 2, ไม่ใช่สินค้า 0 to 26, รอตรวจ 26 to 0. Summary lines (all / counted / not counted / รอตรวจ): 30-day list 156/154/2/1 to 156/153/3/0; late list 584/548/36/14 to 584/533/51/0; all lines 2244/2151/93/26 to 2244/2109/135/0. Executive watch-out 548 to 533. Re-verify (consistency only, classification unchanged): 48 codes changed remark; 42 have on-hand above 0 in the saved stock (flagged): 02-00-R-7048, 03-CC-R-5159, 03-CC-R-5167, 03-CC-R-5169, 03-CC-R-5170, 03-CC-R-5171, 03-CC-R-5172, 03-CC-R-5173, 03-CC-R-5175, 03-CC-R-5176, 03-CC-R-5177, 03-CC-R-5178, 03-CC-R-6560, 03-CC-R-6561, 03-CC-R-6562, 03-CC-R-9190, 03-CC-R-9957, LABOR-02-00-R-2026-1, LABOR-03-CC-R-1046, LABOR-RS-R-06-0006, LABOR-RS-R-06-0017, LABOR-RS-R-06-0025, and the SLIT COST codes -01, -04, -09, -20, -26, -27, -28, -29, -30, -31, -35, -COPPER FOIL-105, -COPPER FOIL-3, -COPPER FOIL-7, -COPPER FOIL-8, -PAPER, -PAPER-11, -PAPER-12, -PAPER-5, -RESIZE. 6 codes have no description and on-hand 0 (COST OF PAPER, LABOR_TF-R-09-0027, TF-R-01-0077, TF-R-05-0216, TF-R-08-0223TF, TF-R-08-0224TF). The type of the last movement is not in the saved data (only dates).

**Checks.** Full suite after the last code change: 783 passed, 0 skipped, 0 database connection attempts. Validator (assessed only): run-day results and derived dates, code paths, exit codes, lock, remark and summary recomputation (0 differing lines), no description or DB host in a tracked file: all agree. Not verifiable: the saved before-copies of the forward-test logs and the operation plan files were empty, so the gate was checked by file times only (all before today's work) and the row hashes in the log metadata, not byte by byte.

**Disclosures.** (1) The DB host was printed once in a tool output (a log message) while the task files were read; no repo file held it and messages no longer contain it. (2) A test wrote a real lock file once (a fake "Login failed" was now classified as refused); it was deleted and a conftest fixture now redirects the lock path per test. (3) Two subagent tool outputs showed a Windows user path (the task XML) in the session only.

**Deviations.** A `--ignore-run-day` flag exists on the monthly cli for manual runs; the old log-based "refused today" guard of the daily job is replaced by the lock; the headless browser checks are the suite's own Edge page tests, not a separate run.

**Need decision.** The monthly state file does not exist yet. The October run (2026-10-05, task result 0) is therefore not recorded, so the first weekday start (2026-10-13 07:00) would run October again. A permission rule blocked me from seeding the file. Seed it before 07:00 on 2026-10-13: `python -c "import sys; sys.path.insert(0,'src'); import monthly_refresh as m, datetime as d; m.record_monthly_success('seeded 2026-10-12: run of 2026-10-05 ended with result 0', today=d.date(2026,10,12))"` from the project folder, or disable the monthly task for that day.

**Found, not done.** 11 investigation scripts under src/investigations connect with `engine.connect()` directly and bypass the lock and the one-attempt guard (none is run by a job); after an exit 1 the weekday triggers retry on each weekday (only a refusal is locked); an auxiliary pull that exits 0 without rewriting its file is logged "NOT refreshed" but is not marked partial; the daily job ends with exit 1 for an unreachable host.


## Prompt 24

Date and time of the work: 2026-10-12, started 10:04 (`git pull origin main` first: nothing new). No database session, no npm; the full suite made 0 database connection attempts. Items by code only; no description or customer name is in this section.

**Part 7 (confusing words).** Of the 58 items, 8 were fixed by Prompt 17 (items 1, 2, 3, 5, 7, 9, 11, 12). Items 8 and 10 had a residual of the same wording and are counted as still present, so the remaining count is 50, not the 47 of the brief. 6 items sit only on the original S&OP tab and were not touched (4, 34, 35, 36, 37, 38). Remaining 50, still present 44, no longer present 0, S&OP excluded 6. **Fixed: 43 of the 44**, at the generator or the source (src/build_*.py, config/config.yaml, config/manual_notes.yaml, data/assumptions.json through its generator, docs/user_manual.md; the hand-written parts of index.html have no generator and were edited in place). **Not fixed: item 33** (the year written four ways): unifying it changes the numbers shown (2026 to 69 to 2569), which the numeric gate forbids; it needs the user's decision. Partly fixed: 13 (control labels got Thai units and tooltips; longer on-screen labels pushed the control panel out of view and a test caught it), 32 (the status words are explained, the ISO dates stay), 41 (the legend line only), 51 (order qty and order-by date named, the "+n" unexplained). The stock panel (items 6, 42, 43) is a block of index.html outside the S&OP tab and was fixed.

**Sentences changed per page** (final state, the Reviewer's fixes included; one row per source fragment): sales_report 23; inventory 43; operation_plan 10; material_plan 5; index (executive) 2; index (assumptions) 9; index (stock panel) 10; index (Trend) 6; คู่มือ (docs) 44. The before to after table is at the end of this section.

**Manual.** 27 placeholders `{name}` in docs/user_manual.md, filled at runtime by the manual tab from data/assumptions.json key `manual_values` (an existing JSON; the key is written by src/maxmin_v1.py through `reader_values.manual_values`; schema_version stays 2): stale_days, n_rounds, holdout_months, n_focus_items, notice_bucket_first, notice_bucket_second, notice_bucket_last, trend_data_through, trend_first_month, trend_last_month, n_codes_trend, n_codes_pages, lead_grid_first, lead_grid_last, ctl_lead_time, ctl_assembly, ctl_review, ctl_service_level, ctl_holding_cost, csl_min, csl_max, notice_days, signal_count, min_signals, run_day_base, guard_days, lag_months. A name with no value renders as `[ค่าไม่พบ: name]`; tests fail on any unresolved name. Values that changed because the typed number was out of date: Trend data through 25 ส.ค. 2569 to 8 ต.ค. 2569 (and the range end ส.ค. to ต.ค. 2569), 448 codes to 445, the lead time 45-60 to 45-75 (the grid the sales report shows). Two wrong statements are corrected: the stock panel updates every weekday (daily job), the Trend tab updates monthly (step 7e). Typed numbers kept and labelled "ตัวอย่าง": MAE 120, ADI 1 and 4, the Inventory 100/80/20/50 example, the ≥30 วัน 6% example, MAE 10 / Bias +3 / MASE 0.7, "+20.0%". Typed layout facts left as they are (not data or schedule): 5 ส่วน, 2 เส้น, 3 กอง, 4 คอลัมน์, 400 แถว, the three preset buttons, Horizon 3.

**C1 backup.** Latest dated folder (%OneDriveCommercial%\sale_forecast_backup\2026-10-09_140327): forward_test_log_all_divisions.csv MATCH, its metadata MATCH, forward_test_shadow_log.csv MATCH, its metadata MATCH, forward_test_scores.csv MATCH, forward_test_scores_integrity.json MATCH, vintage_002_fit_series.csv.gz MATCH (7 of 7). **C2 task gate.** Before/after sha256 of the same files, of data/ and of the operation plan files: identical, except data/assumptions.json (Part B: manual_values and the reworded assumptions) and the material section of output/summary/operation_plan_v1_integrity.json with the two material plan CSVs (Part D rebuild). data/inventory.json and data/stock_daily.json are unchanged.

**D1.** 02-00-R-7048 leaves the confirmed not-goods list; config exceptions holds it with the reason "user 2026-10-12: probably goods"; its remark is "รอตรวจ · ชื่อเป็นชิ้นส่วน" (counted). Summary lines (all / counted / not counted / รอตรวจ), plan date 2026-10-08: 30-day list 156/153/3/0 to 156/153/3/0; late list 584/533/51/0 to 584/533/51/0; all lines 2244/2109/135/0 to 2244/2110/134/1. Executive watch-out 533 to 533 (the code is in the all-lines list only).

**Numeric gate.** Every number shown on every page is identical before and after, except the D1 counts above, the build and pull time stamps, and digits inside reworded labels. The Validator rechecked it independently (no other difference; the JSON blocks of the sales report are identical; the inventory JSON differs only in label text, three time stamps and the three division status texts).

**Browser check** (headless Edge on a temporary profile, deleted afterwards; only its own Edge PID was closed, the local server ran inside the checking script): index.html (S&OP, executive, Trend, assumptions, manual tabs), sales_report, inventory, operation_plan, material_plan: 0 script errors (the only console line is a 404 for favicon.ico); the manual shows no unresolved placeholder and no "5 ธ.ค."; the assumptions tab shows 7 ธ.ค. 69; the executive tab shows 533 late materials; 02-00-R-7048 shows its new remark; the 59 LABOR codes show ค่าแรง (33) or ค่าจ้าง (26).

**Reviewer flags (A3) and outcome.** Applied: "always" in the MAE-across-divisions line softened; the significance wording ("ไม่น่าเกิดจากความบังเอิญ"); the lead-time sentence; the month-column note and the no-production rows; the operation plan column "ประเภท" renamed "นโยบายการผลิต" (one word, one meaning); the Staging header; the manual's "กลุ่มรูปแบบการขาย"; the assumptions capacity wording; the PEM107 table heads and the chart axis (not_late); "จากใบสั่งซื้อจริง" in the inventory text; tooltips on the control labels. Not applied: "ให้ฝ่ายยืนยัน" in the conflict tooltip (the manual's classification text already says the division confirms before Min/Max is set); the "ส่งทัน" and "ส่งไม่ช้า" vocabulary split (kept, noted); the English-first badge "No data in DB" (low).

**Found, not done.** (1) Item 33, year formats (needs the user's decision; small). (2) The manual's load-failure message and some old off-screen comments still name files or the old date (small). (3) The manual line "ฝ่ายที่ขายเยอะ MAE สูงกว่าเสมอ" is approved text that says "always" (small, user). (4) The config comment says the confirmed procurement range is 45-60 while the page and manual use the grid 45-75 (small, user). (5) The "ส่งทัน" and "ส่งไม่ช้า" split between the manual and the pages (small, user). (6) ISO Gregorian dates in the freshness table (the remainder of item 32, with item 33).

### Before to after (Thai, verbatim; code fragments are shown as they sit in the source)

| หน้า | ข้อ Part 7 | ก่อน | หลัง |
|---|---|---|---|
| sales_report | 19 | เพียงพอสำหรับการพยากรณ์ <b>{placeholder_total}</b> รหัสไม่มีประวัติเพียงพอและใช้ค่า ⏎         Placeholder แทน และ | เพียงพอสำหรับการพยากรณ์ <b>{placeholder_total}</b> รหัสไม่มีประวัติเพียงพอและใช้ค่าประมาณ ⏎         (Placeholder) แทน และ |
| sales_report | 19 | <th>Placeholder</th><th>ตัดออก (Excluded)</th> | <th>Placeholder (ใช้ค่าประมาณ)</th><th>ตัดออก (Excluded)</th> |
| sales_report | 20 | Median customer notice: <b>{fmt_num(biz['median_notice'], 0)}</b> วัน &nbsp;\|&nbsp; | ระยะแจ้งล่วงหน้าของลูกค้า (Customer notice) ค่ากลาง (median): <b>{fmt_num(biz['median_notice'], 0)}</b> วัน &nbsp;\|&nbsp; |
| sales_report | 21 | ระยะเวลาจัดหาวัตถุดิบ (Procurement lead time): <b>{biz['lead_grid'][0]}-{biz['lead_grid'][-1]}</b> วัน ⏎         (ค่ากลาง {biz['lead_default']} วัน) | ระยะเวลาสั่งวัตถุดิบถึงได้ของ (Procurement lead time ต่างจากระยะแจ้งล่วงหน้าของลูกค้า): <b>{biz['lead_grid'][0]}-{biz['lead_grid'][-1]}</b> วัน ⏎         (ค่าที่ใช้ {biz['lead_default']} วัน) |
| sales_report | 22 |     ไม่ใช้ Neural Network (เช่น TensorFlow) หรือ Prophet เนื่องจากมีข้อมูลย้อนหลังเพียง {history_months} เดือน ⏎     และ {intermittent_lumpy_share_pct}% ของรหัสสินค้ามีลักษณะการขายแบบ Intermittent หรือ Lumpy (ขายไม่สม่ำเสมอ ไม่ต่อเนื่อง) ⏎     ทำให้ Neural Network มีความเสี่ยงสูงที่จะ Overfit กับข้อมูลจำนวนน้อย และ Prophet มีสมมติฐาน ⏎     ว่าข้อมูลต่อเนื่อง (continuous) ซึ่งไม่ตรงกับลักษณะข้อมูลจริงของโครงการนี้ |     ไม่ใช้โมเดลซับซ้อนที่ต้องใช้ข้อมูลยาว (Neural Network, Prophet) เนื่องจากมีข้อมูลย้อนหลังเพียง {history_months} เดือน ⏎     และ {intermittent_lumpy_share_pct}% ของรหัสสินค้ามีลักษณะการขายแบบ Intermittent หรือ Lumpy (ขายห่างๆ ไม่ต่อเนื่อง) ⏎     ทำให้ Neural Network มีความเสี่ยงสูงที่จะทายตามข้อมูลเดิมมากเกินไป (Overfit) เมื่อข้อมูลมีน้อย และ Prophet ต้องการ ⏎     ข้อมูลที่ขายต่อเนื่องทุกเดือน ซึ่งไม่ตรงกับลักษณะข้อมูลจริงของโครงการนี้ |
| sales_report | 23 |     (Naive, MA3, MA6, MA12, Croston, SBA) เพื่อทายยอดรวมของแต่ละ |     (Naive = ใช้ยอดเดือนก่อน, MA3/MA6/MA12 = ค่าเฉลี่ยเคลื่อนที่ตามจำนวนเดือน, Croston และ SBA = วิธีสำหรับสินค้าที่ขายห่างๆ) เพื่อทายยอดรวมของแต่ละ |
| sales_report | 24, 26 | <th>MASE</th><th>n_scored (item × origin)</th> | <th>MASE (เทียบกับวิธีเดาง่าย ยิ่งต่ำยิ่งดี)</th><th>จำนวนที่ใช้คำนวณ (สินค้า × รอบทดสอบ)</th> |
| sales_report | 25 | <h3>Rolling-origin MAE (Type level) — คลิก legend เพื่อซ่อน/แสดงแต่ละโมเดล</h3> | <h3>Rolling-origin MAE ระดับ Type (ทดสอบย้อนหลังทีละรอบ: ตัดข้อมูลที่เดือนหนึ่ง แล้วทายเดือนถัดไปเทียบกับของจริง) — คลิก legend เพื่อซ่อน/แสดงแต่ละโมเดล</h3> |
| sales_report | 26 | <p class="hint">ทายยอดรวมระดับประเภทสินค้าก่อน แล้วแบ่งให้แต่ละรหัสตามสัดส่วนที่เคยขาย ทดสอบย้อนหลัง {n_rounds} รอบ</p> | <p class="hint">ทายยอดรวมระดับประเภทสินค้าก่อน แล้วแบ่งให้แต่ละรหัสตามสัดส่วนที่เคยขาย ทดสอบย้อนหลัง {n_rounds} รอบ · MAE เทียบข้ามฝ่ายไม่ได้ ฝ่ายที่ขายเยอะ MAE สูงกว่าเสมอ</p> |
| sales_report | 27 | ทายพลาด{word}ประมาณ {significance_pct_text(r['rel_diff_pct'])}% ทดสอบแล้วความต่างนี้เกิดจริง{small} | ทายพลาด{word}ประมาณ {significance_pct_text(r['rel_diff_pct'])}% (วัดจาก MAE) ทดสอบทางสถิติแล้วว่าต่างจริง ไม่ใช่ความบังเอิญ (statistically significant){small} |
| sales_report | 28 | ยอดทายทุกเดือนเท่ากัน เพราะวิธีทายตอนนี้ให้ค่าระดับเดียวกับทุกเดือนข้างหน้า ยังไม่คิดช่วงขายดีขายน้อยตามฤดูกาล" | ยอดทายทุกเดือนเท่ากัน (flat forecast) เพราะวิธีทายตอนนี้ให้ค่าเดียวกับทุกเดือนข้างหน้า ยังไม่คิดช่วงขายดีขายน้อยตามฤดูกาล (seasonality)" |
| sales_report | 28 | ▸ เป็นค่ากลางค่าเดียว ยังไม่มีช่วงสูงต่ำ ดูว่าพลาดได้แค่ไหนจากส่วนผลลัพธ์ | ▸ เป็นตัวเลขค่าเดียว (point forecast) ยังไม่มีช่วงสูงต่ำ ดูว่าพลาดได้แค่ไหนจากส่วนผลลัพธ์ |
| sales_report | 29 | baht_label: "มูลค่าคิดจากราคาขายเฉลี่ยจริงของแต่ละรหัส {first_month} ถึง {last_month}" | baht_label: "มูลค่าคิดจากราคาขายเฉลี่ยต่อชิ้นของแต่ละรหัส (Average selling price) {first_month} ถึง {last_month}" |
| sales_report | 29 | baht_label_market_part: " · {m} รหัสที่ไม่เคยขายใช้ราคาตั้งใน Price List" | baht_label_market_part: " · {m} รหัสที่ไม่เคยขายใช้ราคาตั้ง (List price) ใน Price List แทน" |
| sales_report | 30 | pilot_heading: "กลุ่มนำร่อง: Fuse Cutout และ Surge Arrester" | pilot_heading: "กลุ่มนำร่อง (Pilot group): ประเภทสินค้า Fuse Cutout และ Surge Arrester" |
| sales_report | 30 | pilot_columns: ["กลุ่ม", "MAE (ชิ้นต่อเดือน)", "Bias"] | pilot_columns: ["ประเภทสินค้า (Type)", "MAE (ชิ้นต่อเดือน)", "Bias"] |
| sales_report | 30 | ({len(FOCUS_ITEMS)} focus codes) | (สินค้าหลัก {len(FOCUS_ITEMS)} รหัส) |
| sales_report | 31 | รหัส ใน Omni Channel ทุกฝ่าย | รหัส ใน Omni Channel (ประเภทรายได้ที่ไม่รวม Tendering หรืองานประมูล) ทุกฝ่าย |
| sales_report | 32 | if label in stale_sections else 'ใหม่'}</td></tr> | if label in stale_sections else 'ใหม่ (Fresh)'}</td></tr> |
| sales_report | 32 | {f'เก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน' if label | {f'เก่ากว่า {STALENESS_THRESHOLD_DAYS} วัน (Stale)' if label |
| inventory | 13 | slider("procurement_lead_time_days", "Procurement lead time (days)", 1, "d") | slider("procurement_lead_time_days", "Procurement lead time (วัน: สั่งวัตถุดิบถึงได้ของ)", 1, "d") |
| inventory | 13 | slider("assembly_time_days", "Assembly time (days)", 1, "d") | slider("assembly_time_days", "Assembly time (วัน: เวลาประกอบ)", 1, "d") |
| inventory | 13 | slider("review_interval_days", "Review interval (days)", 1, "d") | slider("review_interval_days", "Review interval (วัน: ทบทวน stock ทุกกี่วัน)", 1, "d") |
| inventory | 13 | slider("cycle_service_level", "Cycle service level", 0.01) | slider("cycle_service_level", "Cycle service level (โอกาสที่รอบเติมไม่ขาดของ)", 0.01) |
| inventory | 13 | slider("holding_cost_rate_annual", "Annual holding cost rate", 0.01) | slider("holding_cost_rate_annual", "Annual holding cost rate (ต้นทุนถือของต่อปี เป็นสัดส่วนของมูลค่า stock)", 0.01) |
| inventory | 13, 49 | slider("obsolescence_threshold_months", "Obsolescence threshold (months)", 1, "mo") | slider("obsolescence_threshold_months", "Excess stock threshold (เกณฑ์ของค้าง: เดือนที่ stock พอขาย)", 1, "mo") |
| inventory | 14 | <b>ค่าสถานการณ์ (scenario values) ภายใต้สมมติฐานที่ระบุไว้เท่านั้น | <b>ผลจำลอง (scenario values) ภายใต้สมมติฐานที่ระบุไว้เท่านั้น |
| inventory | 14 | เลือกเป้าการส่งทัน แล้วดูว่าต้องถือของเท่าไหร่ (ค่าแนะนำ)</h2> | เลือกเป้าการส่งทัน แล้วดูว่าต้องถือของเท่าไหร่ (ผลจำลอง)</h2> |
| inventory | 15 | <p class="hint" id="segmentation-note">ประเภทสินค้า: เก็บ stock / ผลิตตามสั่ง / ยังไม่ชัด · ดูจากป้ายในระบบ | <p class="hint" id="segmentation-note">นโยบายการผลิต (ไม่ใช่ Product Type): เก็บ stock (MTS) / ผลิตตามสั่ง (MTO) / ยังไม่ชัด · ดูจากป้ายในระบบ |
| inventory | 44 | DISABLED_DIVISION_LABELS = {"CI101": "ยังไม่เปิด", "PEM102": "ยังไม่เปิด", "PEM104": "ผลิตตามสั่ง"} | DISABLED_DIVISION_LABELS = {"CI101": "ยังไม่ประเมิน (Not assessed)", "PEM102": "ยังไม่ประเมิน (Not assessed)", "PEM104": "ผลิตตามสั่ง"} |
| inventory | 44 | f"ยังไม่เปิด มีของในคลังแค่ {n_ci} จาก {t_ci} รหัส | f"ยังไม่ประเมินฝ่ายนี้ มีของในคลังแค่ {n_ci} จาก {t_ci} รหัส |
| inventory | 44 | f"ยังไม่เปิด มีของในคลังแค่ {n_102} จาก {t_102} รหัส | f"ยังไม่ประเมินฝ่ายนี้ มีของในคลังแค่ {n_102} จาก {t_102} รหัส |
| inventory | 45 | จึงต่างจากที่ระบบคำนวณเต็มจากข้อมูลรายวันประมาณ {gap_pct}% (PEM101) | จึงต่างจากค่าเต็มที่คำนวณจากข้อมูลรายวัน (ค่าอ้างอิง) ประมาณ {gap_pct}% ของค่าเต็ม (PEM101) |
| inventory | 46 | <th onclick="sortTable(6)">Min (ค่าที่ตั้งในระบบ)</th><th onclick="sortTable(7)">Max (ค่าที่ตั้งในระบบ)</th> | <th onclick="sortTable(6)">Min (ที่ตั้งในระบบคลัง)</th><th onclick="sortTable(7)">Max (ที่ตั้งในระบบคลัง)</th> |
| inventory | 46, 49 | ส่วนเกินคิดเป็นเงินเท่าไหร่<br>ของค้าง = stock พอขายเกินจำนวนเดือนที่ตั้งไว้ด้านบน</p> | ส่วนเกินคิดเป็นเงินเท่าไหร่<br>ของค้าง (Excess stock) = stock พอขายเกินจำนวนเดือนที่ตั้งไว้ด้านบน ไม่ใช่ออเดอร์ค้างส่ง (open orders)<br>Min = ระดับที่ต้องสั่งเติม · Max = ระดับที่สั่งเติมให้ถึง</p> |
| inventory | 47 | ▸ เส้นกลาง = ค่ากลาง แถบรอบเส้น = ช่วงที่เป็นไปได้ ดาว = จุดที่เราอยู่วันนี้ เพชร = เป้าที่เลือก | ▸ เส้นกลาง = ค่ากลาง (median) แถบรอบเส้น = ช่วงความไม่แน่นอน (uncertainty band) ดาว = จุดที่ PEM101 อยู่วันนี้ เพชร = เป้าที่เลือก |
| inventory | 10 | ▸ ติ๊กเอาคลังเข้าหรือออกจากการนับเป็นของขายได้ stock ที่มี เดือนที่พอขาย value at risk และธงของค้างจะเปลี่ยน | ▸ ติ๊กเอาคลังเข้าหรือออกจากการนับเป็นของขายได้ stock ที่มี เดือนที่พอขาย Excess Min value (มูลค่า Min ส่วนเกิน) และธงของค้างจะเปลี่ยน |
| inventory | 48 | เส้นแสดง stock_value ที่ระดับ service level ต่างๆ (ค่าควบคุมอื่นคงที่ตามที่ตั้งไว้ด้านบน) สำหรับ division ที่เลือก | เส้นแสดงมูลค่า stock ที่ระดับ service level ต่างๆ (ค่าควบคุมอื่นคงที่ตามที่ตั้งไว้ด้านบน) สำหรับฝ่ายที่เลือก |
| inventory | 48 | <label for="notlate-slider">not_late target: <b id="notlate-slider-value"></b></label> | <label for="notlate-slider">เป้าส่งไม่ช้า (not-late target): <b id="notlate-slider-value"></b></label> |
| inventory | 48 | <div class="stat">not_late target<b> | <div class="stat">เป้าส่งไม่ช้า (not-late target)<b> |
| inventory | 48+48 (shortened to keep the panel in view) | <div class="stat">Items with a Min/Max<b id="tot-n-items"> | <div class="stat">สินค้าที่มี Min/Max<b id="tot-n-items"> |
| operation_plan | 16 | "flag_inconsistent": "ข้อมูลไม่สอดคล้อง" | "flag_inconsistent": "ป้ายไม่ตรงกับพฤติกรรมจริง (Conflict)" |
| operation_plan | 16 | "flag_inconsistent_tip": "ประเภทที่บันทึกในระบบขัดกับวิธีส่งจริง ใช้วิธีส่งจริงตัดสิน" | "flag_inconsistent_tip": "ป้าย MTS/MTO ที่บันทึกในระบบไม่ตรงกับพฤติกรรมจริงของสินค้า ใช้พฤติกรรมจริงตัดสิน และให้ฝ่ายยืนยัน" |
| operation_plan | 17 | "no_production_in_system": "ไม่พบการผลิตในระบบ" | "no_production_in_system": "ไม่มีบันทึกผลิตในระบบ" |
| operation_plan | 17 | "line_no_production": "{n} รหัสไม่พบการผลิตในระบบ ไม่นับเป็นภาระผลิต" | "line_no_production": "{n} รหัสไม่มีบันทึกผลิตในระบบ (ไม่ได้แปลว่ายกเลิกผลิต) ไม่นับรวมในยอดผลิตตามแผน" |
| operation_plan | 17 | "no_production_note": "แถวที่ขึ้นว่า ไม่พบการผลิตในระบบ ไม่ได้รวมในยอดผลิตของฝ่าย" | "no_production_note": "แถวที่ขึ้นว่า ไม่มีบันทึกผลิตในระบบ ไม่ได้รวมในยอดผลิตของฝ่าย" |
| material_plan | 17 | "no_production": "ไม่พบการผลิตในระบบ" | "no_production": "ไม่มีบันทึกผลิตในระบบ" |
| material_plan | 17 | ไม่พบการผลิตในระบบ {n_no_production} รหัส | ไม่มีบันทึกผลิตในระบบ {n_no_production} รหัส |
| operation_plan | 18 | "line_no_forecast": "{n} รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้มีออเดอร์ค้าง {k} รหัส" | "line_no_forecast": "{n} รหัสยังไม่มียอดทาย (ประวัติขายไม่พอ) แผนนับเฉพาะออเดอร์ที่รับแล้วแต่ยังไม่ส่ง (open orders) ตอนนี้มีออเดอร์ที่รับแล้วยังไม่ส่ง {k} รหัส" |
| operation_plan | 18 | "line_no_forecast_no_orders": "{n} รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้" | "line_no_forecast_no_orders": "{n} รหัสยังไม่มียอดทาย (ประวัติขายไม่พอ) แผนนับเฉพาะออเดอร์ที่รับแล้วแต่ยังไม่ส่ง (open orders) ตอนนี้ไม่มีออเดอร์ที่รับแล้วยังไม่ส่งในกลุ่มนี้" |
| operation_plan | 58 | "stock_note": "stock ตอนนี้ แสดงเฉพาะสินค้าเก็บ stock" | "stock_note": "stock ตอนนี้ แสดงเฉพาะสินค้าเก็บ stock · คอลัมน์เดือน = จำนวนที่แผนให้ผลิตในเดือนนั้น (สินค้าที่ไม่เก็บ stock = ยอดที่ต้องผลิตตามความต้องการ)" |
| material_plan | 50 | "source": {"observed": "ใบสั่งซื้อจริง", "supplier_quoted": "ผู้ขายแจ้ง", "assumed": "ค่าประมาณ"} | "source": {"observed": "จากใบสั่งซื้อที่ผ่านมา", "supplier_quoted": "ผู้ขายแจ้งเวลา", "assumed": "ประมาณการ (ไม่มีข้อมูลจริง)"} |
| material_plan | 51 | "ต้องสั่งเพิ่ม", "ต้องสั่งภายใน", "lead time (วัน)", "ที่มา lead time"] | "ต้องสั่งเพิ่ม (Order qty)", "สั่งภายในวันที่ (Order-by date)", "lead time (วัน)", "ที่มา lead time"] |
| material_plan | 52 | "notice": "แผนนี้ยังอยู่ระหว่างตรวจสอบ ตัวเลขต้องสั่งยังใช้สั่งซื้อจริงไม่ได้" | "notice": "แผนนี้เป็นร่าง (Draft) ยังอยู่ระหว่างตรวจสอบ ตัวเลขต้องสั่งยังใช้สั่งซื้อจริงไม่ได้ จนกว่าจะกำหนดเกณฑ์ว่าตรงกับใบสั่งซื้อจริงแค่ไหนถึงใช้ได้ (ดูแท็บสมมติฐานที่ใช้อยู่)" |
| index (executive) | 8 | watch_plan: "แผนผลิต {division} เดือน {month} สูงกว่ายอดผลิตสูงสุดที่เคยทำ ({pct})" | watch_plan: "แผนผลิต {division} เดือน {month} สูงกว่ายอดผลิตสูงสุดรายเดือนในอดีต (Historical peak ไม่ใช่ขีดความสามารถผลิต) ({pct})" |
| index (executive) | 2 | watch_pem107: "PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ {since} ({pct} ไม่สาย)" | watch_pem107: "PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ {since} ({pct} ส่งไม่ช้า)" |
| index (assumptions) | 53 | const COLUMNS = [['topic','เรื่อง'],['unknown','ยังไม่รู้อะไร'],['used_now','ตอนนี้ใช้'],['affects','กระทบ']]; | const COLUMNS = [['topic','เรื่อง'],['unknown','ยังไม่รู้อะไร (Unknown)'],['used_now','ตอนนี้ใช้ (Used now)'],['affects','กระทบอะไร (Affects)']]; |
| index (assumptions) | 53 | unknown: "ได้จากการจำลองให้ตรงผลจริง ไม่ได้วัดตรง" | unknown: "ได้จากการปรับค่า (calibration) ให้ตรงผลจริง ไม่ได้วัดตรง" |
| index (assumptions) | 53+53 (review) | used_now: "ใช้ยอดนั้นเป็นค่าต่ำสุด" | used_now: "ใช้ยอดนั้นเป็นค่าต่ำสุดที่กำลังผลิตน่าจะทำได้ (Lower bound ไม่ใช่ขีดความสามารถจริง)" |
| index (assumptions) | 28, 53 | used_now: "ใช้ค่ากลาง" | used_now: "ใช้ค่าเดียวต่อเดือน (point forecast)" |
| index (assumptions) | 54 | {topic: "ยอดทายเอียงต่อเนื่อง", to_decide: "tracking signal เกินเท่าไหร่ถึงเตือน", now_used: "ร่าง: ±{tracking_signal_limit}" | {topic: "ยอดทายเอียงไปทางเดียวต่อเนื่อง (Bias)", to_decide: "Tracking Signal (ความคลาดสะสม ÷ ความคลาดเฉลี่ย) เกินเท่าไหร่ถึงเตือน", now_used: "ร่าง: ±{tracking_signal_limit} (ไม่มีหน่วย)" |
| index (assumptions) | 55 | {topic: "เป้ารายได้", to_decide: "นับจากวันออก invoice หรือวันส่งของ", now_used: "ใช้วันส่งของไปก่อน" | {topic: "เป้ารายได้", to_decide: "นับจากวันออก invoice (Invoice date) หรือวันส่งตามสัญญา (Contract delivery date)", now_used: "ใช้วันส่งตามสัญญาไปก่อน" |
| index (assumptions) | 2 | {topic: "เป้าการส่งไม่สาย", to_decide: "บริษัทต้องการกี่ %" | {topic: "เป้าการส่งไม่ช้า (not-late)", to_decide: "บริษัทต้องการกี่ %" |
| index (assumptions) | 2 | to_decide: "การส่งไม่สายจำลองห่างจากผลจริงได้แค่ไหน" | to_decide: "การส่งไม่ช้าที่จำลองห่างจากผลจริงได้แค่ไหน" |
| index (assumptions) | 56 |       unknown: "วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง" ⏎       used_now: "ไม่นับในแผน" |       unknown: "วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง" ⏎       used_now: "ไม่นำมาหักจากแผน (Open production orders ยังไม่ถูกนับ)" |
| inventory | 50 |     observed: "ใบสั่งซื้อจริง" ⏎     supplier_quoted: "ผู้ขายแจ้ง" ⏎     assumed: "ค่าประมาณ" |     observed: "จากใบสั่งซื้อที่ผ่านมา" ⏎     supplier_quoted: "ผู้ขายแจ้งเวลา" ⏎     assumed: "ประมาณการ (ไม่มีข้อมูลจริง)" |
| index (stock panel) | 6 | <th data-k="available" title="qty − Reserved — ยังไม่ตัดคลังที่ไม่ใช่ sellable ออก">Available<div class="inv-th-note">ของที่หยิบส่งได้จริง ≈ Sellable − Reserved (Available ยังนับคลัง QA ด้วย)</div></th> | <th data-k="available" title="qty − Reserved — ยังไม่ตัดคลังที่ไม่ใช่ sellable ออก">Available (stock หักที่จอง รวมคลัง QA)<div class="inv-th-note">Available ยังนับคลัง QA ด้วย จึงอาจสูงกว่าของที่หยิบส่งได้จริง ให้ดู Sellable − Reserved</div></th> |
| index (stock panel) | 43 | ไม่ใช่ข้อเท็จจริงที่ยืนยันจากข้อมูล">Sellable</th> | ไม่ใช่ข้อเท็จจริงที่ยืนยันจากข้อมูล">Sellable (คลังที่ขายได้)</th> |
| index (stock panel) | 43 | title="ในคลัง QA / FMTS / FMTO โดยเฉพาะ">Staging (QA/FMTS/FMTO)</th> | title="ในคลัง QA / FMTS / FMTO โดยเฉพาะ">Staging (QA/FMTS/FMTO ยังไม่พร้อมขาย)</th> |
| index (stock panel) | 43 | title="ในคลังอื่นนอกเหนือจาก Sellable และ Staging">Elsewhere</th> | title="ในคลังอื่นนอกเหนือจาก Sellable และ Staging">Elsewhere (คลังอื่น)</th> |
| index (stock panel) | 43 | <th data-k="backlog">Reserved</th> | <th data-k="backlog">Reserved (ติด PO จอง)</th> |
| index (stock panel) | 42 | '<td colspan="3" style="color:var(--muted)">not assessed</td></tr>' | '<td colspan="3" style="color:var(--muted)">ยังไม่ประเมิน (not assessed)</td></tr>' |
| index (stock panel) | 42 | sellableCell = stagingCell = elsewhereCell = '<span class="inv-num" style="color:var(--muted)">not assessed</span>'; | sellableCell = stagingCell = elsewhereCell = '<span class="inv-num" style="color:var(--muted)">ยังไม่ประเมิน (not assessed)</span>'; |
| index (stock panel) | 42 | ▸ CI101 / PEM102 / PEM104 ขึ้น not assessed เพราะยังไม่ได้กำหนดคลังขายได้ ไม่ใช่ศูนย์ | ▸ CI101 / PEM102 / PEM104 ขึ้น ยังไม่ประเมิน (not assessed) เพราะยังไม่ได้กำหนดคลังขายได้ ไม่ใช่ศูนย์ |
| index (stock panel) | 42 | ▸ CI101 / PEM102 / PEM104 ขึ้น not assessed เพราะยังไม่ได้กำหนดคลังขายได้ ไม่ใช่ศูนย์ | ▸ CI101 / PEM102 / PEM104 ขึ้น ยังไม่ประเมิน (not assessed) เพราะยังไม่ได้กำหนดคลังขายได้ ไม่ใช่ศูนย์ |
| index (Trend) | 39 |    <li>เกณฑ์แบ่งกลุ่ม: ADI 1.32 และ CV² 0.49 (Syntetos-Boylan)</li> |    <li>เกณฑ์แบ่งรูปแบบการขาย (Demand pattern): ADI (ขายห่างกันกี่เดือน) 1.32 และ CV² (ขนาดออเดอร์แกว่งแค่ไหน) 0.49 (Syntetos-Boylan)</li> |
| index (Trend) | 40 | <span class="hint" style="color:#6b8099;font-size:11px">(มีผลกับกราฟ ① และ SKU modal เท่านั้น — ไม่มีผลกับกราฟ ②③④)</span> | <span class="hint" style="color:#6b8099;font-size:11px">(มีผลกับกราฟ ① และหน้าต่างรายสินค้า (SKU) เท่านั้น — ไม่มีผลกับกราฟ ②③④)</span> |
| index (Trend) | 40 | <b>คลิกแท่งเดือนเพื่อ drill down ดูรายวัน</b> | <b>คลิกแท่งเดือนเพื่อดูรายวัน (drill down)</b> |
| index (Trend) | 41 | <span class="badge st-nodata">No data in DB</span> = ไม่มียอดขายปี | <span class="badge st-nodata">No data in DB</span> = ไม่มียอดขายในระบบสำหรับปี |
| index (Trend) | 30, 57 | <label>กลุ่ม <select id="fCls"> | <label>รูปแบบการขาย (Demand pattern) <select id="fCls"> |
| index (Trend) | 57 | <option value="NoSale">ไม่มียอดขาย</option> | <option value="NoSale">No sales (ไม่มียอดขายในช่วงข้อมูล)</option> |
| คู่มือ (docs) | B1 data-through date | \| แท็บ Trend Omni \| สินค้าแต่ละตัวขายแบบไหน ขึ้นลงยังไง \| ข้อมูลถึง 25 ส.ค. 2569 \| | \| แท็บ Trend Omni \| สินค้าแต่ละตัวขายแบบไหน ขึ้นลงยังไง \| อัปเดตทุกเดือน ข้อมูลถึง {trend_data_through} \| |
| คู่มือ (docs) | wrong schedule | \| แผงสต็อคจริง \| ตอนนี้มีของอยู่เท่าไหร่ อยู่คลังไหน ติดจองเท่าไหร่ \| อัปเดตทุกเดือน \| | \| แผงสต็อคจริง \| ตอนนี้มีของอยู่เท่าไหร่ อยู่คลังไหน ติดจองเท่าไหร่ \| อัปเดตทุกวันทำการ (จันทร์ถึงศุกร์) \| |
| คู่มือ (docs) | B1 stale days | ถ้าข้อมูลเก่ากว่า 7 วันจะมีป้ายเตือนสีเหลือง | ถ้าข้อมูลเก่ากว่า {stale_days} วันจะมีป้ายเตือนสีเหลือง |
| คู่มือ (docs) | B2 example | สมมติ MAE = 120 คือแต่ละเดือน | ตัวอย่าง: MAE = 120 คือแต่ละเดือน |
| คู่มือ (docs) | B1 rounds | ทำซ้ำ 7 จุด ผลที่รายงานคือค่าเฉลี่ย 7 รอบ | ทำซ้ำ {n_rounds} จุด ผลที่รายงานคือค่าเฉลี่ย {n_rounds} รอบ |
| คู่มือ (docs) | B1 holdout | ให้ model ทาย 6 เดือนถัดไป | ให้ model ทาย {holdout_months} เดือนถัดไป |
| คู่มือ (docs) | B1 holdout | เพื่อดูแยกจากผลรวมทั้ง 6 เดือน | เพื่อดูแยกจากผลรวมทั้ง {holdout_months} เดือน |
| คู่มือ (docs) | B2 example | ADI = 1 คือขายทุกเดือน ADI = 4 คือ 4 เดือนขายครั้ง | ตัวอย่าง: ADI = 1 คือขายทุกเดือน ADI = 4 คือ 4 เดือนขายครั้ง |
| คู่มือ (docs) | B2 example | สมมติสินค้าตัวหนึ่ง Inventory 100, | ตัวอย่าง: สินค้าตัวหนึ่ง Inventory 100, |
| คู่มือ (docs) | B1 buckets | ▸ แกน X = ระยะแจ้งล่วงหน้าขั้นต่ำ (≥30 วัน, ≥60 วัน … ≥180 วัน) · แกน Y = % ของออเดอร์ทั้งหมด | ▸ แกน X = ระยะแจ้งล่วงหน้าขั้นต่ำ (≥{notice_bucket_first} วัน, ≥{notice_bucket_second} วัน … ≥{notice_bucket_last} วัน) · แกน Y = % ของออเดอร์ทั้งหมด |
| คู่มือ (docs) | B2 example | ▸ สมมติแท่ง ≥30 วันสูง 6% หมายถึง | ▸ ตัวอย่าง: แท่ง ≥30 วันสูง 6% หมายถึง |
| คู่มือ (docs) | B2 example | ▸ สมมติแท่ง ≥30 วันสูง 6% หมายถึง | ▸ ตัวอย่าง: แท่ง ≥30 วันสูง 6% หมายถึง |
| คู่มือ (docs) | B1 lead grid (the typed 45-60 differed from the 45-75 of the sales report) | แต่สั่งวัตถุดิบใช้ 45-60 วัน | แต่สั่งวัตถุดิบใช้ {lead_grid_first}-{lead_grid_last} วัน |
| คู่มือ (docs) | B1 focus items | ▸ แกน X = รหัสสินค้า 3 ตัว · แกน Y = MAE | ▸ แกน X = รหัสสินค้า {n_focus_items} ตัว · แกน Y = MAE |
| คู่มือ (docs) | A n_scored | คอลัมน์ ฝ่าย / MAE / RMSE / Bias / MASE / n_scored (จำนวนครั้งที่นำมาคำนวณ) | คอลัมน์ ฝ่าย / MAE / RMSE / Bias / MASE / จำนวนที่ใช้คำนวณ (สินค้า × รอบทดสอบ) |
| คู่มือ (docs) | B2 example | สมมติฝ่ายหนึ่ง MAE 10, | ตัวอย่าง: ฝ่ายหนึ่ง MAE 10, |
| คู่มือ (docs) | B1 rounds | ▸ แกน X = รอบทดสอบที่ 1-7 เรียงตามเวลา | ▸ แกน X = รอบทดสอบที่ 1-{n_rounds} เรียงตามเวลา |
| คู่มือ (docs) | B1 holdout | ▸ แกน X = เดือนที่ 1-6 หลังจุดตัดข้อมูล | ▸ แกน X = เดือนที่ 1-{holdout_months} หลังจุดตัดข้อมูล |
| คู่มือ (docs) | A significance wording | - Top-down ชนะวิธีอื่นแบบไม่มีนัยสำคัญทางสถิติ เลือกเพราะนิ่งและทำได้ทั้งระบบ ไม่ใช่เพราะแม่นกว่าชัดเจน | - ความต่างระหว่าง Top-down กับวิธีอื่นส่วนใหญ่ไม่มีนัยสำคัญทางสถิติ (ต่างจากความบังเอิญไม่ได้) เลือกเพราะนิ่งและทำได้ทั้งระบบ ไม่ใช่เพราะแม่นกว่าชัดเจน ฝ่ายไหนต่างจริงดูที่ข้อสรุปใต้ตารางผลลัพธ์ |
| คู่มือ (docs) | B1 typed date removed | ▸ การส่งทันของช่องทาง Omni ก่อนและหลัง พ.ค. 2569 พร้อมจำนวนชิ้นที่ใช้คำนวณ | ▸ การส่งทันของช่องทาง Omni ก่อนและหลังเดือนที่แถบเตือนระบุ พร้อมจำนวนชิ้นที่ใช้คำนวณ |
| คู่มือ (docs) | B1 typed date removed | ระวัง หลัง พ.ค. จำนวนยังน้อย ยังไม่รู้สาเหตุแน่ชัด และยังไม่ยืนยันว่า พ.ค. แยกอะไร stock หรือสายผลิต | ระวัง หลังเดือนนั้นจำนวนยังน้อย ยังไม่รู้สาเหตุแน่ชัด และยังไม่ยืนยันว่าเดือนนั้นแยกอะไร stock หรือสายผลิต |
| คู่มือ (docs) | B1 typed preset | ปุ่ม 1 = ส่งทันเท่าวันนี้ ด้วย stock น้อยสุด ปุ่ม 2 = stock เท่าวันนี้ ส่งทันได้สูงสุด ปุ่ม 3 = เป้า <target>% | ปุ่ม 1 = ส่งทันเท่าวันนี้ ด้วย stock น้อยสุด ปุ่ม 2 = stock เท่าวันนี้ ส่งทันได้สูงสุด ปุ่ม 3 = เป้าสูงสุดที่ปุ่มเสนอ (ดูตัวเลขบนปุ่ม) |
| คู่มือ (docs) | B2 example | ▸ สมมติขึ้น "+20.0% (ช่วง +10.0% ถึง +30.0%)" | ▸ ตัวอย่าง: ถ้าขึ้น "+20.0% (ช่วง +10.0% ถึง +30.0%)" |
| คู่มือ (docs) | B1 control default | \| Procurement lead time \| สั่งวัตถุดิบถึงได้ของกี่วัน \| 60 \| | \| Procurement lead time \| สั่งวัตถุดิบถึงได้ของกี่วัน \| {ctl_lead_time} \| |
| คู่มือ (docs) | B1 control default | \| Assembly time \| ประกอบกี่วัน ไม่มีข้อมูลจริง เป็นค่าเดา \| 3 \| | \| Assembly time \| ประกอบกี่วัน ไม่มีข้อมูลจริง เป็นค่าเดา \| {ctl_assembly} \| |
| คู่มือ (docs) | B1 control default | \| Review interval \| ทบทวน stock ทุกกี่วัน \| 30 \| | \| Review interval \| ทบทวน stock ทุกกี่วัน \| {ctl_review} \| |
| คู่มือ (docs) | B1 control default | \| Cycle service level \| อยากให้แต่ละรอบเติมไม่ขาดของกี่ % \| 0.95 \| | \| Cycle service level \| อยากให้แต่ละรอบเติมไม่ขาดของกี่ % \| {ctl_service_level} \| |
| คู่มือ (docs) | B1 control default | \| Holding cost rate \| ต้นทุนถือของต่อปี % ของมูลค่า \| 0.20 \| | \| Holding cost rate \| ต้นทุนถือของต่อปี % ของมูลค่า \| {ctl_holding_cost} \| |
| คู่มือ (docs) | A 15 | ### ประเภทสินค้า ⏎  | ### นโยบายการผลิต (MTS / MTO) ⏎  |
| คู่มือ (docs) | B1 notice days | ผลิตเป็น batch ไว้ก่อนลูกค้าสั่ง / ส่งได้ภายใน 14 วันหลังรับ PO | ผลิตเป็น batch ไว้ก่อนลูกค้าสั่ง / ส่งได้ภายใน {notice_days} วันหลังรับ PO |
| คู่มือ (docs) | B1 signals | คู่กับพฤติกรรมจริง 3 อย่าง | คู่กับพฤติกรรมจริง {signal_count} อย่าง |
| คู่มือ (docs) | B1 signals | - เก็บ stock = ป้าย MTS และพฤติกรรมตรงอย่างน้อย 2 ใน 3 | - เก็บ stock = ป้าย MTS และพฤติกรรมตรงอย่างน้อย {min_signals} ใน {signal_count} |
| คู่มือ (docs) | B1 signals | - ผลิตตามสั่ง = ป้าย MTO หรือ ETO และพฤติกรรมตรงไม่เกิน 1 | - ผลิตตามสั่ง = ป้าย MTO หรือ ETO และพฤติกรรมตรงน้อยกว่า {min_signals} อย่าง |
| คู่มือ (docs) | B1 notice days | เกณฑ์ 14 วันและสัดส่วนต่างๆ เป็นสมมติฐาน | เกณฑ์ {notice_days} วันและสัดส่วนต่างๆ เป็นสมมติฐาน |
| คู่มือ (docs) | A 10 | ▸ ติ๊กเอาคลังเข้าหรือออกจากการนับเป็นของขายได้ stock ที่มี เดือนที่พอขาย value at risk และธงของค้างจะเปลี่ยน | ▸ ติ๊กเอาคลังเข้าหรือออกจากการนับเป็นของขายได้ stock ที่มี เดือนที่พอขาย Excess Min value (มูลค่า Min ส่วนเกิน) และธงของค้างจะเปลี่ยน |
| คู่มือ (docs) | A 12 | กล่องสรุป — มูลค่า stock (Σ Min × ต้นทุนต่อชิ้น) / ต้นทุนถือของต่อปี / จำนวนสินค้าที่มี Min-Max | กล่องสรุป — Value of Min level (มูลค่าตาม Min จำลอง = Min × ต้นทุนต่อชิ้น) / ต้นทุนถือของต่อปี / จำนวนสินค้าที่มี Min-Max |
| คู่มือ (docs) | B1 service level range | ▸ แกน X = cycle service level (0.80-0.99) · แกน Y = มูลค่า stock (บาท) | ▸ แกน X = cycle service level ({csl_min}-{csl_max}) · แกน Y = มูลค่า stock (บาท) |
| คู่มือ (docs) | B1 data-through, code counts (the typed 448 and 25 ส.ค. were out of date) | ข้อมูลถึง 25 ส.ค. 2569 ไม่อัปเดต ใช้ฐาน 448 รหัส ซึ่งรวม sheet ที่ซ่อนใน pricelist ต่างจากหน้าอื่นที่ใช้ 445 รหัส เทียบตัวเลขข้ามหน้าตรงๆ ไม่ได้ | ข้อมูลถึง {trend_data_through} อัปเดตทุกเดือนพร้อมหน้าอื่น ใช้ฐาน {n_codes_trend} รหัส หน้าอื่นใช้ {n_codes_pages} รหัส ถ้าสองเลขนี้ต่างกัน เทียบตัวเลขข้ามหน้าตรงๆ ไม่ได้ |
| คู่มือ (docs) | B1 Trend months | ▸ แกน X = เดือน (ม.ค. 2567 - ส.ค. 2569) · แกน Y = บาท หรือ ชิ้น ตามปุ่มหน่วย | ▸ แกน X = เดือน ({trend_first_month} - {trend_last_month}) · แกน Y = บาท หรือ ชิ้น ตามปุ่มหน่วย |
| คู่มือ (docs) | B1 schedule | - แผงสต็อค หน้ายอดขาย และหน้า Min-Max อัปเดตอัตโนมัติทุกเดือนในวันธรรมดา (จันทร์ถึงศุกร์) วันแรกตั้งแต่วันที่ 5 | - แผงสต็อคอัปเดตอัตโนมัติทุกวันทำการ (จันทร์ถึงศุกร์) หน้ายอดขาย หน้า Min-Max และแท็บ Trend Omni อัปเดตอัตโนมัติทุกเดือนในวันธรรมดา (จันทร์ถึงศุกร์) วันแรกตั้งแต่วันที่ {run_day_base} |
| คู่มือ (docs) | B1 guard | - ข้อมูลเดือนไหนจะนำมาใช้ต้องรอ 30 วันหลังสิ้นเดือน ให้รายการที่คีย์ช้าเข้าระบบครบ ข้อมูลล่าสุดจึงช้ากว่าปัจจุบันประมาณ 2 เดือน | - ข้อมูลเดือนไหนจะนำมาใช้ต้องรอ {guard_days} วันหลังสิ้นเดือน ให้รายการที่คีย์ช้าเข้าระบบครบ ข้อมูลล่าสุดจึงช้ากว่าปัจจุบันประมาณ {lag_months} เดือน |
| คู่มือ (docs) | wrong schedule | - แท็บ Trend Omni และ S&OP Plan ไม่อัปเดต | - แท็บ S&OP Plan ไม่อัปเดต |
| inventory | 13 | "Procurement lead time (วัน: สั่งวัตถุดิบถึงได้ของ)" | "Procurement lead time (วัน)" |
| inventory | 13 | "Assembly time (วัน: เวลาประกอบ)" | "Assembly time (วัน)" |
| inventory | 13 | "Review interval (วัน: ทบทวน stock ทุกกี่วัน)" | "Review interval (วัน)" |
| inventory | 13+13 (kept short so the control panel stays in view) | "Cycle service level (โอกาสที่รอบเติมไม่ขาดของ)" | "Cycle service level" |
| inventory | 13+13 (kept short so the control panel stays in view) | "Annual holding cost rate (ต้นทุนถือของต่อปี เป็นสัดส่วนของมูลค่า stock)" | "Annual holding cost rate" |
| inventory | 13, 49 | "Excess stock threshold (เกณฑ์ของค้าง: เดือนที่ stock พอขาย)" | "Excess stock threshold (เดือน)" |
| inventory | 10 (shortened) | เดือนที่พอขาย Excess Min value (มูลค่า Min ส่วนเกิน) และธงของค้างจะเปลี่ยน | เดือนที่พอขาย Excess Min value และธงของค้างจะเปลี่ยน |
| คู่มือ (docs) | 10 (shortened) | เดือนที่พอขาย Excess Min value (มูลค่า Min ส่วนเกิน) และธงของค้างจะเปลี่ยน | เดือนที่พอขาย Excess Min value และธงของค้างจะเปลี่ยน |
| inventory | 44 (shortened so the control panel stays in view) | "CI101": "ยังไม่ประเมิน (Not assessed)", "PEM102": "ยังไม่ประเมิน (Not assessed)" | "CI101": "ยังไม่ประเมิน", "PEM102": "ยังไม่ประเมิน" |
| inventory | 44 | f"ยังไม่ประเมินฝ่ายนี้ มีของในคลังแค่ {n_ci} | f"ยังไม่ประเมิน (Not assessed) มีของในคลังแค่ {n_ci} |
| inventory | 44 | f"ยังไม่ประเมินฝ่ายนี้ มีของในคลังแค่ {n_102} | f"ยังไม่ประเมิน (Not assessed) มีของในคลังแค่ {n_102} |
| sales_report | 26 (review) | MAE เทียบข้ามฝ่ายไม่ได้ ฝ่ายที่ขายเยอะ MAE สูงกว่าเสมอ</p> | MAE เทียบข้ามฝ่ายตรงๆ ไม่ได้ เพราะฝ่ายที่ขายเป็นจำนวนมากมักมี MAE สูงกว่า</p> |
| sales_report | 27 (review) | ทดสอบทางสถิติแล้วว่าต่างจริง ไม่ใช่ความบังเอิญ (statistically significant) | ทดสอบทางสถิติแล้วว่าต่างกันอย่างมีนัยสำคัญ (statistically significant ไม่น่าเกิดจากความบังเอิญ) |
| sales_report | 21 (review) | ระยะเวลาสั่งวัตถุดิบถึงได้ของ (Procurement lead time ต่างจากระยะแจ้งล่วงหน้าของลูกค้า) | ระยะเวลาสั่งวัตถุดิบถึงได้ของ (Procurement lead time ไม่ใช่ระยะแจ้งล่วงหน้าของลูกค้า) |
| operation_plan | 58 (review) | (สินค้าที่ไม่เก็บ stock = ยอดที่ต้องผลิตตามความต้องการ)" | (สินค้าที่ไม่เก็บ stock = ยอดที่ต้องผลิตตามความต้องการ) แถวที่ไม่มีบันทึกผลิตในระบบแสดงยอดความต้องการ ไม่ใช่ยอดผลิต" |
| operation_plan | 15 (review: one word, one meaning) | "item_cols": ["รหัส", "ชื่อสินค้า", "ประเภท", "stock ตอนนี้", "Min", "Max"] | "item_cols": ["รหัส", "ชื่อสินค้า", "นโยบายการผลิต", "stock ตอนนี้", "Min", "Max"] |
| index (stock panel) | 43 (review) | Staging (QA/FMTS/FMTO ยังไม่พร้อมขาย) | Staging (QA/FMTS/FMTO ไม่นับเป็นคลังขายได้) |
| คู่มือ (docs) | 30 (review) | ฝ่าย / หมวด / ประเภท / กลุ่มรูปแบบการขาย / ค้นหา | ฝ่าย / หมวด / ประเภท / รูปแบบการขาย / ค้นหา |
| inventory | 48 (review) | <th>not_late (from May 2026)</th><th>not_late (before May 2026)</th> | <th>ส่งไม่ช้า (not-late) ตั้งแต่ May 2026</th><th>ส่งไม่ช้า (not-late) ก่อน May 2026</th> |
| inventory | 48 (review) | title: {{text: 'not_late (%)'}} | title: {{text: 'ส่งไม่ช้า (not-late) %'}} |
| inventory | 50 (review) | lead time วัตถุดิบจากใบสั่งซื้อจริง ค่ากลาง | lead time วัตถุดิบจากใบสั่งซื้อที่ผ่านมา ค่ากลาง |
| inventory | 13 tooltips |     def slider(key, label, step, suffix=""): |     def slider(key, label, step, suffix="", tip=""): |
| inventory | 13 tooltips | <label for="ctrl-{key}">{label}: <span | <label for="ctrl-{key}" title="{tip}">{label}: <span |
| inventory | 13 tooltips | slider("procurement_lead_time_days", "Procurement lead time (วัน)", 1, "d") | slider("procurement_lead_time_days", "Procurement lead time (วัน)", 1, "d", tip="สั่งวัตถุดิบถึงได้ของกี่วัน") |
| inventory | 13 tooltips | slider("assembly_time_days", "Assembly time (วัน)", 1, "d") | slider("assembly_time_days", "Assembly time (วัน)", 1, "d", tip="ประกอบกี่วัน") |
| inventory | 13 tooltips | slider("review_interval_days", "Review interval (วัน)", 1, "d") | slider("review_interval_days", "Review interval (วัน)", 1, "d", tip="ทบทวน stock ทุกกี่วัน") |
| inventory | 13 tooltips | slider("cycle_service_level", "Cycle service level", 0.01) | slider("cycle_service_level", "Cycle service level", 0.01, tip="โอกาสที่แต่ละรอบเติมไม่ขาดของ") |
| inventory | 13 tooltips | slider("holding_cost_rate_annual", "Annual holding cost rate", 0.01) | slider("holding_cost_rate_annual", "Annual holding cost rate", 0.01, tip="ต้นทุนถือของต่อปี เป็นสัดส่วนของมูลค่า stock") |
| inventory | 13 tooltips | slider("obsolescence_threshold_months", "Excess stock threshold (เดือน)", 1, "mo") | slider("obsolescence_threshold_months", "Excess stock threshold (เดือน)", 1, "mo", tip="เกณฑ์ของค้าง: stock พอขายเกินกี่เดือนถือว่าค้าง") |


## Prompt 25

Date and time of the work: 2026-10-12, started 13:23 (`git pull origin main`: nothing new). No database session, no npm. Items by code only; no description or customer name is in this section.

**1. Lead time (the correction of Prompt 24).** config `phase_e1_assumptions` holds the grid [45, 60, 75] and the default 60. The confirmed range is 45-60; 75 is a stress point of the sensitivity grid. New helper `reader_values.confirmed_lead_time_range(config)` returns (smallest grid value, default) = (45, 60) and raises when the default does not lie below the grid's last value. `manual_values` now holds `lead_confirmed_first` = 45 and `lead_confirmed_last` = 60 (the two `lead_grid_*` keys are gone: no manual sentence describes the grid). docs/user_manual.md line 121 reads "สั่งวัตถุดิบใช้ 45-60 วัน" (rendered, checked in the browser). The sales report's lead-time line now reads "45-60 วัน (ช่วงที่ธุรกิจยืนยัน ค่าที่ใช้ 60 วัน · ช่วงทดสอบความไวเพิ่มถึง 75 วัน)", the only place that names 75 and it labels it as the test range. The config comments say plainly that 45-60 is confirmed and 75 is a stress point only (comment change only; no config value changed). No other page, the manual, manual_notes.yaml or any config reader text presents 45-75 as the lead time (searched; the only "45-75" left in a page is part of a product name).

**2. One year format** (decision of the user, 2026-10-12): Thai short month and the Buddhist year as two digits ("ต.ค. 69", "7 ธ.ค. 69", "5 ม.ค. 70"), a time only where one was already shown. Formatter: Python `reader_values.thai_month_short / thai_date_short / thai_datetime_short(seconds=) / thai_year_short`, and for the page scripts one text, `reader_values.JS_THAI_DATES` (`thaiMonthShort`, `thaiDateShort`, `thaiDateTime`, `thaiYearShort`, `thaiQuarter`), which the Python builders write into the sales report and the Min-Max page and which index.html carries once in its own script block between two marker comments (a test checks the copies are the same text). The Min-Max page's own month list, the Trend tab's `beLabel`/`THM` (four-digit year, and a month glued to a Gregorian year in one hint) and the stock panel's own formatter are removed: no page has its own month list or year arithmetic. Places changed (code sites): sales report 11 (the 7 rows of the data-date table with their times, the two years of the executive summary, the delivery heading and the chart axis of both delivery lines, the backtest window); Min-Max page 12 (the page-built, calibrated and data dates and months of every division, the PEM107 alert: split date, window start, data date and two table heads); index.html 20 (tab label, Trend: month labels, three tooltip kinds, daily view hint and title, incomplete-month hint, price list quarter, year range badge and the note about the old tab; the executive card year and the PEM107 month through the Python formatter; the assumptions window; the stock panel's date-time and the dates of its backlog list; the page title); the manual's values (data-through date and Trend range). Operation plan and material plan already used the format and needed none. No date in a data file, log, config or report was touched (display only). The original S&OP tab was not touched. A real date of the backlog list in the stock panel is now formatted; the system's "9999-99-99" (no date) in all 748 rows stays as the data holds it.

**3. Wording.** The manual line now reads "ฝ่ายที่ขายเยอะ MAE มักสูงกว่า" (fixed YES). One term, "ส่งทัน", replaces "ส่งไม่ช้า" (sales report 6 places incl. the chart names, Min-Max page 9, config 3 (executive watch-out, two assumption rows), manual_notes.yaml 3, manual 5) with "ส่งไม่ช้ากว่าวันนัด" at the first use of every manual section that uses it, on the sales report (the delivery heading), the Min-Max page (the control note), the executive tab (watch-out) and the assumptions row; no metric or definition changed.

**4. Leftovers.** The manual's load-failure message is plain Thai with no file name ("ตอนนี้เปิดคู่มือไม่ได้ ลองรีเฟรชหน้านี้อีกครั้ง ..."). Part 7 item 51: the header of the order tables now reads "ใช้ในสินค้า (รหัส · +n คือมีอีก n รหัส)".

**Gates.** Numeric gate with year normalisation (every date, month, year and quarter form turned into one canonical token; my own script on the saved HTML and on the pages as the browser shows them, and the Validator's independent script): date and year tokens equal in count and value on every page; non-year number differences: the lead-time line only (manual 75 to 60, sales report one more 60 because the sentence now also names the confirmed range and the test range), the page-build time, and the age in days of the pull on the Min-Max page (a time-dependent value). Data gate: sha256 of the forward-test, shadow and score logs with their metadata and integrity file, the vintage snapshot and every data/ file are unchanged except data/assumptions.json (the manual values).

**Browser check** (headless Edge on a temporary profile, own PID closed, profile deleted; every tab of index.html except the original S&OP tab, the stock panel and the four pages): 0 script errors (the one console line is a 404 for favicon.ico); no four-digit year and no ISO date in the shown text; samples: "8 ต.ค. 69" (manual data-through date and Trend note), "5 ต.ค. 69 07:41:11" (data-date table), "12 ต.ค. 69 15:03 ICT (UTC+7)" (Min-Max header), "ก่อน 1 พ.ค. 69: 87.1% (n=41,495 ชิ้น, ตั้งแต่ 1 ม.ค. 67)" (PEM107 alert), "ม.ค. 67" (Trend tooltip), "หลังรอบ 7 ธ.ค. 69" (assumptions), "คาดการณ์ทั้งปี 69" (executive card); the manual shows "สั่งวัตถุดิบใช้ 45-60 วัน"; the executive tab shows 533 late materials; 02-00-R-7048 shows "รอตรวจ · ชื่อเป็นชิ้นส่วน".

**Found, not done.** (1) The plan name "Chase S&OP Plan 2026" and the file name of the legacy S&OP page (a tracked file, `forecast/Chase S&OP Plan 2026 - PEM Group.html`) keep the Gregorian year: names, and the S&OP tab is not to be touched (small, user). (2) The headings of older reports under docs/reports keep their old formats by the rule (no change). (3) Product names and codes that contain a year (a specification number, a version) are names, not dates, and are unchanged. (4) The system date "9999-99-99" in the stock panel's backlog list is kept as the data holds it (small, user).


## Prompt 26

Scope audit, read only. Date and time: 2026-10-12, 15:45 +07:00 (`git pull origin main`: nothing new). No database session, no npm, no code, config, page or data change. Items by code only. Four page and pull audits ran as parallel read-only subagents (index.html; sales report and Min-Max page; operation and material plan; database pulls, config, tests, docs). A fifth, the Validator, re-checked 15 claims against the code.

**Step 0 (open check from Prompt 25).** Full suite: 796 passed, 0 failed, 0 skipped (1111 s). Document-scanning tests (`tests/test_guards.py`, `test_reader_text.py`, `test_manual_notes_sync.py`, `test_manual_tab.py`): 56 passed. Database connection attempts in the run: 0.

**Scope rule used.** IN = Price List item codes under revenue_type 'Omni Channel', or derived from them (BOM components of Price List finished goods, their stock and orders). MIXED = Price List data beside or compared with wider data, or a Price List pull without the Omni filter. OUT = wider and not derived. All six divisions come from Price List sheets, so they count as IN.

### Counts by class
| class | page rows | pull rows |
|---|---|---|
| IN | 86 (index 30, sales report 28, Min-Max 16, operation plan 5 sections and material plan 7 sections: 12) | 22 of 31 monthly pulls, daily D3 |
| MIXED | 18 (index 10, Min-Max 5, operation plan 3) | M2, M6, M10, M28 |
| OUT | 1 (executive row "PEMC") and the dormant `omni_tendering` branch | D1, D2 |
| USER-OWNED | 2 (original S&OP tab in index.html; standalone copy in forecast/) | — |
| undetermined | 4 (index 2, operation plan 2) | the original tab's actuals scope |

### Recommendation table (MIXED, OUT, unused, undetermined)
| # | location | what | class | evidence | recommendation | removal touches | size |
|---|---|---|---|---|---|---|---|
| 1 | index.html executive tab, card 2 subtitle | "ถึงเป้า <target>% · เป้ารวมสินค้า Omni ทุกตัว": Price List projection divided by the all-Omni target | MIXED | config.yaml:1204; build_trend_tab.py `exec_render`, `exec_targets` 416-460 (Cube_Target_PMIS, no Price List filter); Validator AGREE | remove | config exec_summary keys 1188-1227, build_trend_tab.py, test_index_w3.py 596-620, 713-754 | M |
| 2 | executive table columns "เป้า (Revenue)", "ถึงเป้า", total row <target> / <target>% | per-division target and attainment; target covers every Omni product; PEM103 target split by category | MIXED | `exec_targets`, `exec_gate` (checks sums only); config.yaml:1204 | remove with row 1 | as row 1, plus METRICS Sec.49 | M |
| 3 | executive remark "ไม่พบเป้าของฝ่ายนี้ในระบบเป้า", footer target sentences | text for rows 1-2 | MIXED | config.yaml:1218, 1227 | remove with rows 1-2 | config, tests | S |
| 4 | executive row "PEMC" | no numbers; says outside Omni scope | OUT | build_trend_tab.py:620-621; config.yaml:1217; test_index_w3.py:736-740; Validator AGREE | remove | config, test | S |
| 5 | assumptions tab pending rows "เป้ารายได้", "จับคู่ประเภทสินค้ากับเป้า" | open criteria about the target | MIXED | config.yaml:1796-1797; data/assumptions.json:139, 146 | remove with row 1 | json, config | S |
| 6 | monthly step 1 `exec_targets_pull`, `pull_targets` | pulls Cube_Target_PMIS for all revenue types and divisions, filters in pandas | MIXED, over-broad | monthly_refresh.py:344-346; build_trend_tab.py:230-233, 430-453; Validator AGREE | remove with row 1 (feeds only rows 1-3) | monthly_refresh.py, build_trend_tab.py, tests | M |
| 7 | stock panel "Reserved", "Available", backlog KPI, backlog modal | Cube_CES Backlog for Price List codes, no revenue filter | MIXED | build_inventory_dataset.py:291-300 `query_backlog_ces`; Validator AGREE. Share of non-Omni rows: undetermined (no data read) | keep, add the Omni filter, then re-check (a data change, not a removal) | build_inventory_dataset.py, inventory.json, stock_daily.json, tests | S |
| 8 | Min-Max page, PEM101 "choose a delivery target": 98.34% "today" and the calibration target | observed not-late from Cube_CES, no RevenueType filter | MIXED | week1_recalibration.py:52-56; Validator AGREE; ces_92.csv: 52 Tendering and 1 other of 29,029 Actual rows (all years; window share undetermined) | keep, add the filter | week1_recalibration.py, lead-time inputs, page | S |
| 9 | Min-Max page, Policy / Label / S2 / S3 columns and class table | S2, S3 signals from Cube_CES, all channels | MIXED | task2b_part2_fulfilment_segmentation.py:177, 516-523; cube_ces_pull.py:34-53; saved pull: 253 of 34,836 rows (0.7%) not Omni (lower bound, inferred) | keep, add the filter | same, tests | S |
| 10 | operation plan division tables (6), "PEM107 backlog above forecast" note, item-table month values | demand = max(forecast, backlog); Omni limit on backlog only for PEM103 | MIXED | operation_plan.py:282-311, 352-360; config.yaml:1884; saved material pull: 23 of 873 backlog rows not Omni or blank; Validator AGREE | keep, extend the limit to the other divisions | config, operation_plan.py, test_operation_plan.py 118, 365-390 | S |
| 11 | material plan quantities | inherit row 10 | MIXED (inherited) | demand comes from the operation plan; Validator: effect not verified | follows row 10 | none | — |
| 12 | operation plan "share of historical peak" and above-capacity flag; executive watch lines on production above peak and raw materials past order date | cube_final output has no revenue-type column | undetermined | operation_plan.py:224-255; the daily backlog pull has no RevenueType column | keep; needs a data check | — | — |
| 13 | `channel_scope: omni_tendering` branch | dormant Tendering scope; no job sets it | OUT | channel_scope.py:21-22; config.yaml:106-121; Validator AGREE (tests not searched for a setter) | remove branch and test | channel_scope.py, load_data_*.py, test_channel_scope.py, METRICS Sec.21, PROJECT_GRAPH Q23 | M |
| 14 | config `cross_division_excluded_value_thb`, `cross_division_excluded_pct` | read by no src or test | OUT (dead) | config.yaml:272-273; Validator grep AGREE | remove | config | S |
| 15 | daily D1: all-Omni posting-delay query; D2: COUNT(*) of the whole cube_final | no Price List filter; `posting_delay.csv` read only by an investigation script and a test | OUT, unused | snapshot_daily.py:106-117; Validator AGREE | remove | snapshot_daily.py, test_daily_stock.py:294-299, investigation script | S |
| 16 | M5 Cube_Backlog (retired table) | feeds only a console print and `old_total_cube_backlog` | unused | build_inventory_dataset.py:236-249; inventory.json:16 | remove (monthly and daily) | build_inventory_dataset.py, json key, tests | S |
| 17 | M7 cube_inventory_tran | warehouse "role" read by no page | unused | build_inventory_dataset.py:573-582, 644, 660 | remove | same | S |
| 18 | M8 `query_backlog_unfiltered` | never called | unused | build_inventory_dataset.py:424 | remove | same | S |
| 19 | M23 "category", M24 "movements" in the material plan pull | saved to pickle only | unused | material_plan.py:658-659; only "master" and "aging" are read | remove | material_plan.py | S |
| 20 | M2 `load_data_full.py:106` | all channels and years, only for a has_any_history flag | MIXED, over-broad | Validator AGREE | keep and narrow | load_data_full.py, part1 file | S |
| 21 | M10 Cube_CES in the class-evidence script | all channels and years | MIXED, over-broad | as row 9 | narrow with row 9 | — | S |
| 22 | M3 against M1 | same rows pulled twice (M3 is a subset of M1) | over-broad | load_data_full.py:127-135; load_data_all_divisions.py:90-98 | keep for now (consumer build_report.py:614); merge later | — | M |
| 23 | Cube_Inventory_Exact pulled 4+ times per monthly run and twice daily; M13 pulls BOM lines only to count them | repeated or over-wide | over-broad | audit D | optional | — | M |
| 24 | M29, M30 add a DB division = PEM101 filter on top of the Price List | narrower than Price List; page text reads as all items | label mismatch | order_leadtime.py:65-71; delivery_performance.py:56-64; build_report.py:1005. Validator did not confirm the constant equals PEM101 | keep and fix the label, or widen | build_report.py text, tests | S |
| 25 | lead-time inputs `prodorder_all.csv`, `cube_final_all.csv` | 2,034 of 2,175 production-order codes are not Price List; read later for listed goods only | over-broad (local files) | lead_time_v1.py:112-125 | keep (filtered before use) | — | — |
| 26 | `forecast/Chase S&OP Plan 2026 - PEM Group.html` and index.html `div#origTab` | original S&OP tab and a standalone copy dated Aug 24; no script, test or config references the copy | USER-OWNED | index.html:255-7440; Validator grep AGREE. Whether its actuals were Omni-only: undetermined | none recommended; the user decides | — | — |
| 27 | METRICS Sec.42 | still says scope is PEM101 and PEM107 only, backlog without channel filter | stale doc | METRICS.md:1110 | correct, not remove | METRICS.md | S |
| 28 | DATA_MAP.md | no Cube_Target_PMIS entry | doc gap | audit D | add, or drop with row 6 | — | S |

**Config, tests and docs that exist only for MIXED or OUT features (rows 1-6, 13, 15).** Config: config.yaml:106-121, 262-275, 1188-1227, 1796-1797, 1884. Tests: test_channel_scope.py (whole file); test_index_w3.py:596-620, 713-754; test_monthly_refresh.py:261-282; test_operation_plan.py:118, 365-390; test_daily_stock.py:294-299; test_maxmin_v1.py:314-315. Docs: METRICS.md Sec.21 (385-409), Sec.45 (1248-1261), Sec.49 (1343-1377); PROJECT_GRAPH.md Q23 (63-76, 166, 254, 265); DATA_MAP.md 390, 495-501, 777-783, 1107, 1158, 1201-1260, 2005-2009, 2048-2052; STATUS.md week 4 prompts 7, 13, 14; docs/user_manual.md:57.

**Not scope problems.** Sales report: 28 rows, all IN; no figure uses a Tendering row. Trend tab: Omni, Price List only (`scope_where`, build_trend_tab.py:166-176). Material plan: no pull of all items; labor, outsource and service lines are BOM lines of Price List finished goods and stay IN (derived). Backtest, transferability, model selection, task2a, report data, reconciliation, comparator and significance scripts open no database.

**Validator.** 15 claims re-checked against the code: 15 AGREE, 0 DISAGREE. Limits it stated: tests not searched for an `omni_tendering` setter; the PEM101 constants in row 24 not confirmed; the effect of row 10 on material quantities not verified. Not classified by it: `phaseE1_common.py:310` `query_backlog` (used by an investigation script).

**Limits.** Consumers traced by grep of src and tests, so dynamic keys could be missed. monthly_refresh.py lines 836-2108 and part of config.yaml were read by grep. Script-rendered parts were read from code and data JSON; no Edge was started (no PID, no profile).

**Found, not done.** Row 24 label mismatch; row 12 needs a data check; whether the original S&OP tab's actuals are Omni-only. Nothing removed.


## Prompt 27

Removal of out-of-scope and unused parts (the pilot covers Price List items only). Date and time: 2026-10-12, started 16:19 +07:00 (`git pull origin main`: nothing new). No database session, no npm. Items by code only. The user approved rows 1–6, 13, 14, 15, 16, 17, 18, 19 and 28 of the Prompt 26 table; rows 7–12 and 20–27 were not touched. One agent did the removal (one coherent change set, so no split); a separate Validator, evaluate-only, re-checked the evidence, the gates and the counts.

### Step 0: evidence per row (grep of src, tests, config, docs, index.html, forecast, data)
| row | what | readers found outside the row | result |
|---|---|---|---|
| 1–3, 5 | executive target text, columns, remarks, two assumptions rows | only `build_trend_tab.py` (`exec_render`, `exec_data`), config `exec_summary`, `tests/test_index_w3.py`, `tests/test_maxmin_v1.py`, `tests/test_maxmin_v1_page.py` (the eight-row table test) | removed; tests updated |
| 4 | PEMC row | `build_trend_tab.py` only; test_index_w3 | removed |
| 6 | `pull_targets`, `exec_targets`, `--pull-targets`, step 1 `exec_targets_pull` | `monthly_refresh.py` (step 1 and its offline stub), 2 tests | removed |
| 28 | DATA_MAP Cube_Target_PMIS | the entry was a gap, not a reader; interpreted as "drop with row 6": no entry added, a dated note put on the two existing target entries | done |
| 13 | `channel_scope`, `omni_tendering` | setter: none in src, config, scheduled-job scripts or tests except `tests/test_channel_scope.py` itself; the Q23 investigation scripts hard-code their own SQL and do not import `channel_scope.py`; readers of the helper functions are `load_data_all_divisions.py` and `load_data_full.py` (IN, default Omni) | branch and key removed; the helper functions stay (IN readers), now returning the Omni value only |
| 14 | `cross_division_excluded_*` | none in src, tests, pages, data (comment and PROJECT_GRAPH text only) | removed |
| 15 | D1, D2 in `snapshot_daily.py` | `posting_delay.csv` is read only by `src/investigations/posting_delay_analysis.py`, which reads the file as it is and does not break when it stops growing; `tests/test_daily_stock.py` pinned the queries | removed; file not deleted |
| 16 | `query_backlog`, `aggregate_backlog`, console comparison, `old_total_cube_backlog` | `phaseE1_common.py` and the investigations hold their own copies; no page, test or script reads the key | removed |
| 17 | `cube_inventory_tran`, `query_transfer_pairs`, `classify_warehouse_roles`, warehouse `role` | the `role` field is read by no page and no test; `warehouses[].code` is still used by the file's own verify step | removed (code list kept) |
| 18 | `query_backlog_unfiltered` | no caller anywhere | removed |
| 19 | material plan `category`, `movements` pulls | only `master` and `aging` are read (`material_plan.py:317-319`); `item_movement_types` does not exist in src, tests or config; the material-plan tests built a `movements` fixture that nothing read | removed; fixtures updated |

### Result
**Removed per row.**
- Rows 1–6 and 28: `pull_targets`, `exec_targets` and `--pull-targets` in `build_trend_tab.py`; the target and attainment fields of `exec_data`, the target columns and card-2 subtitle of `exec_render`, the PEMC row, the target check in `exec_gate`; step 1 `exec_targets_pull` (and its offline stub) in `monthly_refresh.py`; config `exec_summary` keys `target_table`, `target_revenue_type`, `target_pull_dir`, `target_division_same_name`, `target_division_split`, text keys `card2_sub`, `remark_PEMC`, `remark_no_target`, the two columns, the footer target sentences; the two `pending_criteria` rows in config and, regenerated through `maxmin_v1.write_assumptions`, in `data/assumptions.json`; the executive block of `index.html` rebuilt by `build_trend_tab.py --build-exec` (one line changed). METRICS Sec.49 got a dated note (2026-10-12) and the history is kept; DATA_MAP got dated notes on the two target entries.
- Row 13: `channel_scope.py` reduced to the Omni value; config `channel_scope` key and comment; the `omni_tendering` and unknown-scope tests (default-SQL tests kept); the log text of the two loaders.
- Row 14: the two config keys.
- Row 15: `take_snapshot`, `append_snapshot`, `SNAPSHOT_CSV`, `SALE_TABLE`, `CUBE_FINAL_TABLE`, `LOOKBACK_DAYS`, `load_config` and the unused imports in `snapshot_daily.py`.
- Rows 16–18: `query_backlog`, `aggregate_backlog`, `query_backlog_unfiltered`, `query_transfer_pairs`, `classify_warehouse_roles`, `TRAN_TABLE`, `BACKLOG_TABLE`, `BACKLOG_SALE_COMPANIES`; saved pulls now hold two tables (`PULL_NAMES`).
- Row 19: the two entries of `ITEM_ATTRIBUTE_SQL`.

**Kept despite approval, or done differently.**
- METRICS Sec.21 and PROJECT_GRAPH Q23 were annotated with a dated note, not deleted: Q23 is an answered finding that Q22 and other entries cite, and the prompt says not to rewrite history. The selector lines of Sec.21 were replaced by the note. NEED DECISION below.
- `inventory.json`: the removal of M5 and M7 removes more than the one key named in the prompt, because the other keys are computed from the removed pulls: `backlog.reserved_change_report.old_codes_with_reserved`, `n_codes_changed`, `changed_codes_sample`, and `warehouses[].role` (44 entries). The tracked `data/inventory.json` was not rewritten by hand; the daily job drops these on its next run (a build from the saved pull of today differs from the tracked file only by these removals).
- Two tests that tested only removed parts were deleted: `test_the_targets_are_split_by_category_and_a_division_without_a_row_has_no_target` (`test_index_w3.py`) and the two omni_tendering SQL tests plus the unknown-scope test in `test_channel_scope.py`. Everything else was updated, not deleted. Updated: `test_cfix_inventory_pull.py` (two-table fixture; schema assertions added), `test_cfix_runner_and_scores.py`, `test_daily_stock.py` (posting-delay test now asserts the removal), `test_operation_plan.py`, `test_material_plan.py`, `test_monthly_refresh.py` (no skip any more), `test_index_w3.py` (no target text or column, no PEMC row, no <target> or <target>, removed config keys absent; the two skips that depended on the target pull are gone), `test_channel_scope.py`, `test_maxmin_v1.py` and `test_maxmin_v1_page.py` (six criteria rows).

**DB statements per run** (distinct call sites, a chunked loop counts once; counted by me from the audit and by the Validator from `git show HEAD` and the working tree):
- Monthly: 30 before, 25 after (removed Cube_Backlog, cube_inventory_tran, material "category", material "movements", Cube_Target_PMIS).
- Daily: 7 before, 3 after (removed the posting-delay query, the cube_final count, Cube_Backlog, cube_inventory_tran).

**Runner dry runs (fakes, no database).**
- Monthly `python src/monthly_refresh.py --dry-run --offline --skip-tests`: exit 0. Steps: 1_pull_data, 2_validate, 3_frozen_snapshot, 4_backtest, 5_new_forward_test_vintage, 6_fill_and_score, 7_rebuild_pages, 7b_operation_plan, 7c_material_plan, 7d_vintage_gate, 7e_trend_tab, 7f_exec_summary, 8_run_tests (skipped by flag), 9_scan_sensitive_content, 10_change_magnitude, 11_commit_and_push (dry). The exec gate passed (step 7f ran its gate on the rebuilt tab).
- Daily `python src/daily_stock_job.py --dry-run --from-pulls output/data/daily_stock_pull`: exit 0, every gate passed, no tracked file touched.

**Numeric gate.** Rendered text of every page and tab before (the HEAD files) and after, opened in headless Edge: S&OP tab, Trend, manual, stock panel, sales report, Min-Max page, operation plan and material plan are text-identical. Differences, all removals, none added: executive tab: <target>% (twice, card 2 and total row), <target> (total target), <target>, <target>, <target>, <target>, <target> (the five division targets), <target>%, <target>%, <target>%, <target>%, <target>% (the five attainments); the PEMC row. Assumptions tab: the two rows. 982.4 (card 2 value), 542.1 and every other executive figure are unchanged.

**Data gate.**
- `data/stock_daily.json`: working copy sha256 unchanged from the start (945e8181...); a build from the saved pull equals the HEAD blob byte for byte.
- `data/inventory.json`: not modified; build from the saved pull differs from the tracked file only by the removed keys above (no value changed, nothing added).
- `data/assumptions.json`: differs only by the two removed `pending_criteria` rows (8 to 6).
- Forward-test, shadow, score and comparator logs and the vintage snapshot: no file of those kinds was modified during the task (checked by modification time) and none is tracked.

**Files outside the tracked repo for the user to delete (not deleted):** the saved target pull `output/data/exec_pull/` (`targets.csv`, `targets_meta.json`; untracked, in the working folder) and the private copy of the target workbook held outside the repository (path recorded in DATA_MAP only in masked form). `output/snapshots/posting_delay.csv` was kept as asked.

**Browser check** (headless Edge on a temporary profile, both HEAD and new pages): 0 script errors on all five pages; the only console line, one 404, is identical before and after (the page has no icon link, so it is the browser's default icon request). Executive tab: no target text, no target columns, no PEMC row, PEM104 row kept, card 2 shows 982.4 with no subtitle. Assumptions tab: six rows. Stock panel unchanged. The first Edge run left child processes on the temporary profile; only those PIDs (found by their profile path) were stopped and the profile deleted. Two older profile folders from 2026-10-11 and the processes using them are not mine and were left alone.

**Validator: MATCH.** It agreed with the Step 0 evidence, the counts (30 to 25, 7 to 3), the absence of target values, the data gates and the diff review. It found: (a) a test not in my first subset still asserted eight criteria rows (`tests/test_maxmin_v1.py`, `tests/test_maxmin_v1_page.py`): fixed before the final run; (b) stale text, listed under FOUND, NOT DONE; (c) the nested same-quote f-string in `exec_render` needs Python 3.12 or later (3.12.10 here; it was already used elsewhere in the file before this change).

**Tests.** Final full run after the last change (792 tests, about 15 minutes): 792 passed, 0 failed, 0 skipped. Test-suite database connection attempts: 0 (the block's own 4 deliberate attempts were blocked). An earlier full run had 1 failure (the test of the monthly failure log still expected the removed second Trend-tab stage); it was fixed and the whole suite run again. The skips that the old executive tests had (no saved target pull) are gone.

### Found, not done
- `forecast/sales_report.html:101` and `config/config.yaml` `baht_explanation` still say the baht figures were "not checked against the revenue target counting" (a mention of the target on the sales page, asserted by `tests/test_build_report.py:456`). Not in the approved rows. Size S.
- Stale comments: `tests/test_page_timestamps.py:151-156` (says `query_backlog` is kept), `src/snapshot_daily.py` docstring line on `run_query`, the module docstring of `build_inventory_dataset.py` (Step 2B still describes Cube_Backlog; stale before this task). Size S.
- Dead code left in `build_inventory_dataset.py`: `build_backlog_rows` and `classify_negative_causes` (no callers; not in the approved rows). Size S.
- `src/investigations/posting_delay_analysis.py` still works on the old file but can no longer reach its 30 and 60 day minimums. Its purpose is gone. Size S.
- Old pickles `backlog_cube.pkl` and `transfer_pairs.pkl` remain in the local untracked pull folders; harmless.


## Prompt 28

Scope-consistency fixes (Prompt 26 rows 7–10, 20, 21, 24, 27), the last revenue-target sentence, codes missing from the DB item master, DB source wording. Date and time: 2026-10-14, started 07:31 +07:00 (`git pull origin main` brought the daily refresh of 13 October). No database session, no npm. Items by code only. One agent made the changes (one coherent change set); a separate Validator, evaluate-only, re-derived the numbers.

### Step 0: scheduled runs (read only)
- **a. Monthly job.** Task Scheduler ran `SaleForecastMonthlyRefresh` at 07:00 on 2026-10-13 and 2026-10-14; each run lasted about 24 seconds and ended with result 0. No monthly run log was written (a start that is not due writes none), and `output/state/monthly_run_state.json` holds `last_success_month` "2026-10" (seeded 2026-10-12). Read together: the start found the month already done and made no login (the 24 seconds are the `git pull` and the start check; no login is recorded anywhere). The "already done this month" wording itself is inferred, not logged.
- **b. Daily job.** The 08:00 run of 2026-10-13 published (log `daily_stock_20261013T080016`, finished 08:00:32). The 12:00 run of the same day started at 12:00:00 and finished at 12:00:09 with `skipped_success_exists_today`: it did not miss its start and did not run after a wake-up, so there was nothing for StartWhenAvailable to catch (the task has the setting on). The 08:00 run of 2026-10-14 published too (commit 88c2c10, pulled into this work at the end).
- **c. Leftover headless Edge processes and profile folders not from this task** (not stopped): 24 temporary profile folders `page_test_edge_*` still have a running Edge process, started 2026-10-06 to 2026-10-12 (oldest 2026-10-06 11:04; the newest, 2026-10-12 16:43, has 9 processes and a debugging port); two older profile folders (2026-10-06, 2026-10-08) are on disk only. Profile paths are under the user's temporary folder, masked here. These come from earlier test runs: the test helper closes only its root process. This task's own browser run left none (checked).

### Step 1: rows 8, 9, 21 (Omni filter) — recomputed now, from saved pulls that carry RevenueType
The filter is in three places: `observed_not_late` (week1_recalibration.py), `pull_cube_ces_for_items(revenue_type=...)` used by the S2 and S3 pull of the segmentation script (cube_ces_pull.py), and the class-evidence Cube_CES pull (`pull_class_evidence`).
- **Design point for row 21.** The class-evidence Cube_CES pull also feeds the operation plan's backlog (`assemble_inputs`: Status 'Backlog' rows), which row 10 keeps at all channels. So the SQL takes the Omni rows of every status plus the Backlog rows of every channel, and the class signals read the Omni rows only (`omni_rows`, applied in `run_from_frames` before S2 and S3). The backlog bundle still reads the unfiltered frame.
- **Observed not-late, saved 92-item pull of 2026-10-05** (unit-weighted, `ces_92.csv`; 37,505 Omni rows, 66 Tendering, 40 Total Customer Solution, 96 blank): validation window **98.34% → 98.24%** (units 1,126,744 → 1,060,800); calibration window **97.34% → 97.66%** (units 2,549,301 → 2,416,741). The lead-time-free calibration rerun with the new code into a scratch folder: passing members **36 → 37** (the control grid 28/8/28 → 29/8/29 by stock definition), median validation not-late of the members 96.95% unchanged, current stock value unchanged.
- **Classes, saved class evidence of 2026-10-06** (`class_evidence.pkl`; its Cube_CES frame has 69,534 Omni rows, 719 Tendering, 390 Total Customer Solution, 41,658 blank): counts per class used by the pages are identical in every division (PEM101 92 stock_policy / 33 confirmed_to_order / 40 conflict; PEM107 4 / 78 / 54; PEM103 0 / 11 / 76; PEM102 0 / 3 / 23; PEM104 0 / 12 / 0; CI101 0 / 9 / 4). **No item's class used, and so no Min/Max policy, changes.** Changes below that level: the recomputed class (`class_recomputed`, which the kept classes of PEM101 and PEM107 override) differs for 13 codes: HS-F-99-1301H22 (confirmed_to_order → conflict) and 12 codes going conflict → stock_policy: VT-F-99-010721, VT-F-99-010701, CT-F-99-020502, CT-F-99-020505, CT-F-99-020507, CT-F-99-020508, CT-F-99-020510, CT-F-99-020511, CT-F-99-020525, CT-F-99-020527, CT-F-99-020530, CT-F-99-020526. The shown label differs for one code: EEE-F-FL-5920-353-02600 (conflict → too_little_data); label counts too_little_data 73 → 74, conflict 71 → 70.
- **When the pages change.** Not yet. The calibration outputs the Min-Max page reads (`week1_recal_*`) are produced by `week1_recalibration.py`, which no scheduled job runs, so the page keeps 98.34% and its curve until that script is rerun and the outputs are regenerated. The class label and recomputed class reach the pages with the 2026-11-05 monthly pull, which recomputes them from the new filtered logic. NEED DECISION: rerun the recalibration now and regenerate the Min-Max page?

### Step 2: row 20 — NOT narrowed
The has_any_history pull (`load_data_full.py`) asks only whether any row exists. In the saved all-channel sales file (Actual and MPS, 2024 onward) exactly one of the 128 scope codes has rows only in non-Omni channels: EEE-F-FL-5920-353-02600. Narrowing the pull to Omni would flip its flag from True to False, and the saved data covers only Actual and MPS since 2024, so it cannot prove the flag for the others either. The pull stays as it is. The same code is the one whose label changes in Step 1 (it has no Omni delivery history), which is a scope question for you: with the flag True it is treated as having history although it has no Omni sales.

### Step 3: rows 7 and 10 — all channels, labeled
- **Label "รวมทุกช่องทาง"** with the tooltip "stock และออเดอร์ที่รับแล้วใช้ร่วมกันทุกช่องทาง":
  - stock panel (index.html): the Reserved and Available column headers, the line under the panel title ("ยอดจองในระบบ ณ …"), and the backlog pop-up (its sub-line);
  - operation plan page: the demand column header of every division table except PEM103, the division lines that speak of accepted orders (except PEM103), the PEM107 backlog line, and the note under the item table.
  PEM103 keeps its own line ("PEM103 นับเฉพาะยอด Omni Channel…"); it is not labeled all channels because its backlog is still limited to Omni (unchanged, as asked). Material plan quantities inherit the operation plan's demand and carry no label (Found, not done).
- **Why PEM103 is limited.** Config `operation_plan.backlog_channel_scope` came with commit 616a5d9 (2026-10-06, "Week 3 … PEM103 follows Sec.23"). Its config comment says only that PEM103 counts its Omni Channel orders and that the approved page line states it. The reason on record is in STATUS and DATA_MAP: PEM103 is transformers and most of its business is tendering work (65.5% Tendering by item value, Omni Channel 33.3%), and the page line says tender work is not in this plan. METRICS Sec.42 recorded the rule.
- **Effect of removing the limit** (plan rebuilt in memory, nothing written; PEM103, units; "same source" = the saved week-3 rows that carry RevenueType, only the channel filter skipped):
  - same source: one row differs. Backlog due by month (Oct to Feb): 373, 17, 1, 0, 0 → 373, 20, 1, 0, 0; one item changes (TF-F-99-19044211AF1, +3 units in November); PEM103 plan load Nov 205.4 → 208.1, other months unchanged.
  - limit set to empty (what a config change would do): the backlog source also switches from the saved week-3 rows to the latest daily pull, which has no RevenueType column. Backlog due 373, 17, 1, 0, 0 → 322, 107, 1, 0, 0; plan load Oct 485.7 → 434.8, Nov 205.4 → 243.0, Dec to Feb unchanged; 10 PEM103 items change, all conflict-class. Most of that difference is the source and its date (13 October against 6 October), not the channel.
  - No other division changes in either case.

### Step 4: row 24 — PEM101 labels
The data was not changed. Labels: sales report executive summary ("ในสินค้า PEM101 (128 รหัส) ลูกค้าให้เวลาแจ้งล่วงหน้า…", "สัดส่วนส่งตรงวันพอดี ของ PEM101"); a scope line under the heading of section 4 ("ส่วนนี้ … นับเฉพาะสินค้า PEM101 128 รหัส ไม่รวมฝ่ายอื่น") and the notice sentence; the two limitations that use the 128 items ("ตรวจจากสินค้า PEM101 (128 รหัส) แล้วกระทบประมาณ 2.5%…", "46 จาก 128 รายการของ PEM101 ไม่ได้ตั้ง"); the first line of the notice and delivery chart notes (`config/manual_notes.yaml`, the manual). The number 128 is read from the pilot file at build time.

### Step 5: row 27
METRICS Sec.42: the scope line now says the first version (2026-10-05) covered PEM101 and PEM107 and that the plan has covered every item of the six divisions since week 3; the backlog line says no channel filter except PEM103; dated notes (2026-10-14) record the all-channels decision, the Omni-only limit of PEM103 and the item-master remark. METRICS Sec.19 and Sec.23 got dated notes for Step 1.

### Step 6: revenue-target sentence
Removed at its source (config `baht_explanation`), from the rebuilt `forecast/sales_report.html` and from the assertion in `tests/test_build_report.py` (now asserting the sentence is gone). A page and manual scan finds no revenue-target wording outside the original S&OP tab (new test).

### Step 7: codes missing from the DB item master
The saved item-attribute pull of the plan items (2026-10-09, Prompt 21): **38** of the 439 operation-plan codes have no record in Cube_ItemList (PEM103 27, PEM107 8, PEM102 3), as expected. The operation plan page shows "ไม่พบรหัสนี้ใน DB (Cube_ItemList)" next to each (38 marks, equal to the count in the note under the table); no quantity changed. Codes: RS-F-99-010018, RS-F-99-01xxxx-3, RS-F-99-01xxxx-4, RS-F-99-05xxxx-1, RS-F-99-090xxx, SL-F-99-S2461605-01, SR-F-99-3381603, SR-F-99-3381603-01, TF-F-99-19044211AB1, TF-F-99-2107221B1., TF-F-99-2305433B4, TF-F-99-2307221B1, TF-F-99-2507223B1, TF-F-99-2707221B1, TF-F-99-2707223B1, TF-F-99-2807223B1, TF-F-99-2904221B1, TF-F-99-2904223B1, TF-F-99-2905433B4, TF-F-99-2907221B1, TF-F-99-2907223B1, TF-F-99-3004221B1, TF-F-99-3004223B1, TF-F-99-3005433B4, TF-F-99-3007221B1, TF-F-99-3007223B1, TF-F-99-3105433B4, TF-F-99-3107221B1, TF-F-99-3204221B1, TF-F-99-3205433B4, TF-F-99-3207221B1, TF-F-99-3207223B1, TF-F-99-3704221B1, TF-F-99-3705433B4, TF-F-99-3707221B1, VT-F-99-010203., VT-F-99-010303., VT-F-99-01802. 
To keep the remark alive without a new query, the monthly material pull now asks for the plan items together with the components in the same two attribute statements (`codes_requested` in the pickle); a code no saved pull covers is shown as "not checked", never as missing. The count of database statements per run is unchanged (monthly 25, daily 3).

### Step 8: ERP wording
No page, manual line or manual-notes line outside the original S&OP tab names "ERP" as a source (searched index.html outside the original tab, the other pages, `docs/user_manual.md`, `config/manual_notes.yaml`, case-insensitive), so no text changed; a test now guards it. The only "ERP" in tracked text is in older reports under docs/reports (history, not touched). Generic "ระบบ" (for example "ข้อมูล stock ในระบบ ณ …") names no table and was left as it is (Found, not done). To allow the form you asked for, the reader-text guard now accepts a table name inside "DB (<table>)" and still rejects a bare table name.

### Checks
- **Numeric gate** (rendered text of every page and tab before and after, headless Edge): S&OP tab, executive tab, Trend, assumptions, manual, Min-Max page and material plan are text-identical. Stock panel: only the label "รวมทุกช่องทาง" added (two headers). Sales report: no number removed; numbers added by the labels only: 101 (eight times) and 128 (five times) in "PEM101 (128 รหัส)". Operation plan: no number removed; added only the label and the note "38 รหัสไม่พบใน DB (Cube_ItemList) ดึงข้อมูลเมื่อ 9 ต.ค. 69" (38, 9, 69). The sales report was rebuilt with the clock held at the earlier build time (2026-10-12 15:03): a rebuild today would also flip seven "ใหม่ (Fresh)" tags to "เก่ากว่า 7 วัน (Stale)" and add a stale-data box, because the saved pulls are now over seven days old; that is the true state and will show on the next monthly run.
- **Data gate.** No file under `data/` was changed by this task (assumptions.json identical; inventory.json and stock_daily.json differ from the start of the task only through the daily refresh of 2026-10-14 08:00, commit 88c2c10, pulled in before the final checks). Forward-test, shadow, score and comparator logs and the vintage snapshot: none modified (checked by modification time).
- **Runner dry runs** (fakes, no database): monthly `--dry-run --offline --skip-tests` exit 0, all 16 steps present, 5 gates passed, 0 failed (3 not tested, as before); daily `--dry-run --from-pulls` exit 0, 4 gates passed, no tracked file touched.
- **Browser check** (headless Edge, temporary profile, both versions): 0 script errors on all five pages; the one console line (a 404) is the same before and after (the browser's default icon request). My Edge left no process or profile folder.

**Validator.** MATCH. It re-derived every figure above (not-late before and after, class changes, the row 20 proof, the PEM103 numbers, the 38 codes and the page marks, the numeric gate) and found no logic error. Its one risk note: the Backlog rows of every channel reach the operation plan only because of the OR clause in the class-evidence SQL; a test now pins that clause (`tests/test_cube_ces_pull.py`). It also noted that `ces_92.csv` has no producer script in src, so it would have to be regenerated by hand if the pull were ever repeated (added to Found, not done).

**Tests.** Final full run after the last change: 803 passed, 0 failed, 0 skipped (about 17 minutes). Test-suite database connection attempts: 0 (the block's own 4 deliberate attempts were blocked). An earlier full run had 1 failure (the not-late unit test used a frame without RevenueType, which the new code refuses); I fixed it and ran the whole suite again. New tests: the Omni filter in the three Cube_CES paths and the Backlog clause (`test_cube_ces_pull.py`); the all-channels label on the operation plan page and in the stock panel (headers, line, pop-up); the item-master remark (count equals the missing count, unchecked codes never shown as missing, no quantity changes); the PEM101 labels; no revenue-target text and no ERP wording outside the original tab; the reader-text guard's DB form. Existing tests that pinned exact texts were updated, none deleted.

### Found, not done
- Material plan quantities inherit the operation plan's demand (all channels except PEM103) and carry no label. — S — you decide.
- The page keeps 98.34% and the old calibration until `week1_recalibration.py` is rerun and its outputs and the Min-Max page are regenerated. — M — you decide.
- EEE-F-FL-5920-353-02600 has sales history only outside the Omni Channel but is counted as having history (row 20). — S — you decide.
- PEM103's backlog comes from the saved week-3 rows (RevenueType present) because the daily pull has no RevenueType column; those rows are from 2026-10-06. — S — you decide.
- Generic "ระบบ" wording for database sources (no table named) on several pages. — S — you decide.
- 24 leftover Edge profiles and their processes from earlier test runs (Step 0 c); the test helper closes only the root process. — S — you.
- `ces_92.csv` (input of the recalibration) has no producer script in src; it would have to be regenerated by hand if repeated. — S — you decide.
- Stale comments from Prompt 27 (listed there) are still open.


## Prompt 29

Decisions of the user (2026-10-14) from Prompt 28 applied: Omni recalibration, Omni history flag, fresh PEM103 backlog, labels, DB source wording, cadence-based freshness, Edge leak fix. Date and time: 2026-10-14, started 08:53 +07:00 (`git pull origin main`: nothing new). No database session, no npm. Items by code only. One agent made the changes (one coherent change set); a separate Validator, evaluate-only, re-derived the numbers.

### Step 1: Omni recalibration (rows 8, 9, 21 of Prompt 26, decision 1)
`src/investigations/week1_recalibration.py` (Omni-filtered since Prompt 28) was run for real on the saved `ces_92.csv`, then `src/maxmin_v1.py build-inputs`, the Min-Max page through its normal generator (`build_inventory_page.build_page` with the daily snapshot of 2026-10-09, the one the tracked page had been built from, and the monthly pilot sales), `maxmin_v1.write_assumptions`, the operation plan and its page, the material plan and its page, the executive tab and the sales report. **This script is not part of any scheduled job: it is manual.** It was not added to a job.
- **Before → after.**
  - Validation window ("today") not-late: **98.34% → 98.24%** (units 1,126,744 → 1,060,800).
  - Calibration target: **97.34% → 97.66%** (units 2,549,301 → 2,416,741).
  - Passing members: **36 → 37** (control grid by stock definition 28/8/28 → 29/8/29). Median validation not-late of the members 96.95% unchanged; simulated stock value today 14.77 → 14.87 million; current stock value of the 92 items unchanged (15.49 million).
  - Trade-off to 99%: median extra stock 35.7% → 37.1%, range 26.2–81.8% → 26.2–82.1%; stock at 98% 15.64 → 15.77 million, at 99% 21.23 → 21.62 million.
- **Presets on the page.** "Today's not-late at the lowest stock": r 0.7751 → 0.7599, not-late 98.34 → 98.24, median stock value 14,439,372 → 14,170,763. "Highest at today's stock": r 0.8558 → 0.8602, 98.611 → 98.604. "Stretch to 99%": r 1.0098 → 1.0105, stock value 17,497,085 → 17,471,874. The relative-service-cost grid follows (today 98.34 → 98.24; one more excluded point, 2 → 3).
- **Every curve point shown** (20 points; the reorder level r is the same in both): n_members 36 → 37 at all 20; changed stock value and not-late (median) only where listed, the other points keep their value.
  - r 0.1: stock value 5,779,424 → 5,596,620
  - r 0.2: no change besides the member count
  - r 0.3: no change besides the member count
  - r 0.4: stock value 9,497,385 → 9,390,262
  - r 0.5: stock value 10,838,799 → 10,753,496; not-late 96.115 → 96.104
  - r 0.65: stock value 12,808,175 → 12,727,454; not-late 97.708 → 97.691
  - r 0.8: stock value 14,764,579 → 14,696,559; not-late 98.466 → 98.44
  - r 1.0: stock value 17,370,588 → 17,336,224
  - r 1.2: stock value 19,945,713 → 19,913,573; not-late 99.271 → 99.252
  - r 1.4: not-late 99.457 → 99.445
  - r 1.6: stock value 25,123,688 → 25,118,851; not-late 99.582 → 99.572
  - r 1.8: stock value 27,705,506 → 27,694,187
  - r 2.0: stock value 30,282,863 → 30,277,105
  - r 2.25: stock value 33,512,247 → 33,505,424
  - r 2.5: stock value 36,732,689 → 36,728,638
  - r 3.0: stock value 43,187,657 → 43,179,064
  - r 3.5: stock value 49,626,662 → 49,613,433
  - r 4.0: stock value 56,087,111 → 56,082,490; not-late 99.962 → 99.961
  - r 5.0: stock value 68,987,280 → 68,981,306
  - r 6.0: stock value 81,888,966 → 81,885,234
- **Min, Max and policy.** The policy of every item is unchanged (the class used by the pages does not move). PEM101: **92 of 92** stock-policy items change their Min and Max at the page's default preset (Min −2.13% to −1.47%, Max −0.87% to −0.64%); PEM107 0 of 4; PEM102, PEM103, PEM104 and CI101 have no Min or Max (0). Codes, old → new (Min; Max, in units, rounded):
  CA-F-99-010101 Min 0.82 → 0.81; Max 1.88 → 1.87 | CA-F-99-010102 Min 0.47 → 0.46; Max 1.08 → 1.07 | CA-F-99-010104 Min 0.07 → 0.07; Max 0.16 → 0.16 | CA-F-99-010201 Min 16.33 → 16.02; Max 37.4 → 37.09 | CA-F-99-010202 Min 13.3 → 13.04; Max 30.46 → 30.2 | CA-F-99-010203 Min 12.9 → 12.65; Max 29.54 → 29.29 | CA-F-99-010204 Min 1.62 → 1.59; Max 3.72 → 3.68 | CA-F-99-010205 Min 12.99 → 12.74; Max 29.76 → 29.51 | CA-F-99-010206 Min 7.47 → 7.33; Max 17.11 → 16.97 | CA-F-99-010208 Min 2.66 → 2.6; Max 6.08 → 6.03 | CA-F-99-010209 Min 7.96 → 7.81; Max 18.24 → 18.09 | CA-F-99-010211 Min 9.21 → 9.03; Max 21.09 → 20.91 | EEE-F-FC-1040010002 Min 1194.19 → 1170.9; Max 2734.96 → 2711.67 | EEE-F-FC-1040011000 Min 369.59 → 362.38; Max 846.45 → 839.24 | EEE-F-FC-1040011100 Min 434.54 → 426.07; Max 995.2 → 986.72 | EEE-F-FC-1040011100N Min 56.61 → 55.5; Max 129.65 → 128.54 | EEE-F-FC-1040011100NP Min 9.92 → 9.73; Max 22.71 → 22.52 | EEE-F-FC-1040021002 Min 43.29 → 42.44; Max 99.13 → 98.29 | EEE-F-FC-1040021100N Min 8.93 → 8.76; Max 20.45 → 20.28 | EEE-F-FL-1040030000 Min 0.51 → 0.5; Max 1.18 → 1.17 | EEE-F-FL-1040030001 Min 1.65 → 1.61; Max 3.77 → 3.73 | EEE-F-FL-1040030002 Min 7641.45 → 7492.39; Max 17500.6 → 17351.5 | EEE-F-FL-1040030003 Min 4943.75 → 4847.31; Max 11322.2 → 11225.8 | EEE-F-FL-1040030004 Min 3469.23 → 3401.56; Max 7945.27 → 7877.6 | EEE-F-FL-1040030005 Min 4495.83 → 4408.13; Max 10296.4 → 10208.7 | EEE-F-FL-1040030006 Min 6165.11 → 6044.84; Max 14119.4 → 13999.1 | EEE-F-FL-1040030007 Min 3176.53 → 3114.57; Max 7274.92 → 7212.96 | EEE-F-FL-1040030008 Min 4846.32 → 4751.78; Max 11099.1 → 11004.6 | EEE-F-FL-1040030009 Min 1887.72 → 1850.9; Max 4323.28 → 4286.46 | EEE-F-FL-1040030010 Min 2123.54 → 2082.11; Max 4863.35 → 4821.92 | EEE-F-FL-1040030011 Min 342.22 → 335.55; Max 783.75 → 777.08 | EEE-F-FL-1040030012 Min 296.94 → 291.14; Max 680.04 → 674.25 | EEE-F-FL-1040030013 Min 135.21 → 132.57; Max 309.67 → 307.03 | EEE-F-FL-1040030016 Min 74.26 → 72.81; Max 170.06 → 168.61 | EEE-F-FL-1040030020 Min 30.58 → 29.98; Max 70.02 → 69.42 | EEE-F-FL-1040030023 Min 42.46 → 41.64; Max 97.25 → 96.42 | EEE-F-FL-1040030102 Min 2007.61 → 1968.45; Max 4597.86 → 4558.7 | EEE-F-FL-1040030103 Min 1456.8 → 1428.38; Max 3336.38 → 3307.96 | EEE-F-FL-1040030104 Min 774.62 → 759.51; Max 1774.05 → 1758.94 | EEE-F-FL-1040030105 Min 1548.02 → 1517.82; Max 3545.3 → 3515.1 | EEE-F-FL-1040030106 Min 1613.7 → 1582.22; Max 3695.72 → 3664.24 | EEE-F-FL-1040030107 Min 709.13 → 695.29; Max 1624.06 → 1610.22 | EEE-F-FL-1040030108 Min 945.3 → 926.86; Max 2164.93 → 2146.49 | EEE-F-FL-1040030109 Min 148.16 → 145.27; Max 339.32 → 336.43 | EEE-F-FL-1040030110 Min 135.03 → 132.39; Max 309.24 → 306.6 | EEE-F-FL-1040030111 Min 13.35 → 13.09; Max 30.57 → 30.31 | EEE-F-FL-1040030112 Min 15.98 → 15.66; Max 36.6 → 36.28 | EEE-F-FL-1040030113 Min 7.71 → 7.56; Max 17.65 → 17.5 | EEE-F-FL-1040030114 Min 7.92 → 7.76; Max 18.14 → 17.98 | EEE-F-HC-1040020000 Min 175.89 → 172.46; Max 402.82 → 399.39 | EEE-F-HC-1040020001 Min 728.68 → 714.46; Max 1668.84 → 1654.62 | EEE-F-HC-1040020002 Min 4294.05 → 4210.28; Max 9834.28 → 9750.51 | EEE-F-HC-1040020003 Min 4616.31 → 4526.26; Max 10572.3 → 10482.3 | EEE-F-HC-1040020004 Min 3189.26 → 3127.05; Max 7304.09 → 7241.88 | EEE-F-HC-1040020005 Min 622.51 → 610.37; Max 1425.68 → 1413.54 | EEE-F-HC-1040020006 Min 470.85 → 461.67; Max 1078.34 → 1069.16 | EEE-F-HC-1040020007 Min 59.03 → 57.88; Max 135.19 → 134.04 | EEE-F-HC-1040020008 Min 18.78 → 18.41; Max 43 → 42.63 | EEE-F-HC-1040020009 Min 78.02 → 76.5; Max 178.67 → 177.15 | EEE-F-LT-1040020100 Min 837.46 → 821.12; Max 1917.96 → 1901.62 | EEE-F-LT-1040020100P Min 3691.55 → 3619.54; Max 8454.44 → 8382.43 | FC-A-27-00102 Min 18.21 → 17.86; Max 41.7 → 41.35 | FC-A-27-00202 Min 418.28 → 410.12; Max 957.95 → 949.79 | FC-A-27-00203 Min 0.56 → 0.55; Max 1.29 → 1.28 | FC-A-38-00102 Min 1.32 → 1.29; Max 3.02 → 2.99 | FC-A-38-00202 Min 2.23 → 2.19; Max 5.11 → 5.07 | FS-F-99-0003 Min 193.58 → 189.81; Max 443.35 → 439.57 | HS-F-99-0061 Min 0.38 → 0.37; Max 0.86 → 0.85 | HS-F-99-0211 Min 648.88 → 636.22; Max 1486.07 → 1473.41 | HS-F-99-02110 Min 220.94 → 216.63; Max 505.99 → 501.68 | HS-F-99-0213 Min 154.67 → 151.66; Max 354.22 → 351.21 | HS-F-99-0241 Min 440.11 → 431.53; Max 1007.95 → 999.37 | HS-F-99-02410 Min 0.31 → 0.3; Max 0.7 → 0.69 | HS-F-99-0243 Min 27.47 → 26.93; Max 62.92 → 62.38 | HS-F-99-0301 Min 165.79 → 162.55; Max 379.69 → 376.45 | HS-F-99-03010 Min 52.64 → 51.61; Max 120.56 → 119.53 | HS-F-99-0303 Min 14.71 → 14.42; Max 33.69 → 33.4 | HS-F-99-1061 Min 1.27 → 1.24; Max 2.91 → 2.88 | HS-F-99-1211 Min 98.09 → 96.17; Max 224.64 → 222.72 | HS-F-99-1241 Min 62.25 → 61.03; Max 142.57 → 141.35 | HS-F-99-1301 Min 15.81 → 15.5; Max 36.22 → 35.91 | HS-F-99-2121N Min 0.56 → 0.55; Max 1.29 → 1.28 | HS-F-99-2211N Min 22.68 → 22.24; Max 51.93 → 51.49 | HS-F-99-2213N Min 59.08 → 57.93; Max 135.3 → 134.15 | HS-F-99-2241N Min 33.91 → 33.25; Max 77.66 → 77 | HS-F-99-2243N Min 23.05 → 22.6; Max 52.8 → 52.35 | HS-F-99-2303N Min 22.6 → 22.16; Max 51.77 → 51.33 | LS-F-99-1004 Min 6234.71 → 6113.09; Max 14278.8 → 14157.2 | LS-F-99-2001 Min 1786.96 → 1752.1; Max 4092.51 → 4057.66 | PH-F-99-0001 Min 16.59 → 16.26; Max 38 → 37.67 | ST-F-11-0001 Min 455.18 → 446.3; Max 1042.45 → 1033.57 | ST-F-99-0001 Min 149.99 → 147.07; Max 343.52 → 340.59
- **Downstream.** The operation plan reads the page's Min and Max, so it was rebuilt, and so were the material plan and the executive tab. Those pages differ for two reasons: the recalibration, and the stock and backlog pulls of 2026-10-14 (the committed pages used the pull of 2026-10-08). PEM101's five-month plan load went 703,699.7 → 694,926.7 units (−8,773.0); in-memory, with the same new pulls and the old against the new Min/Max, the recalibration share on counted rows is −1,556.6 (October −1,480.4, November −17.6, December −30.4, January −21.7, February −6.5; 65 items change their planned production). PEM107 9,018.3 → 6,917.1 and PEM102 +0.4 come from the newer pulls only. PEM103's backlog still comes from the saved week-3 rows (6 October), because the 14 October daily pull has no RevenueType column, so PEM103 does not move. The executive tab's "แผนผลิต … เกินยอดผลิตสูงสุด" line 243.7% → 244.9% and the late-materials line 533 → 544 follow from the rebuilt plan.

### Step 2: has_any_history on the Omni Channel (row 20, decision 2)
The pull in `load_data_full.py` is now `SELECT DISTINCT itemcode … AND revenue_type = 'Omni Channel'`: channel only, no date and no status condition (every year kept). It takes effect on the next monthly run (2026-11-05). **Known to flip from the saved data:** EEE-F-FL-5920-353-02600 (rows only outside Omni in the saved all-channel file, which holds only Actual and MPS from 2024; other flips cannot be excluded). The full list will be printed by the 2026-11-05 run. **The monthly job now prints it:** step 1 compares the flags of `part1_category_scope_all_codes.csv` before and after the pull, logs "N code(s) lost their history: …; M gained it: …" and records both lists in the run log (`has_any_history_flips`).

### Step 3: fresh PEM103 backlog (decision 3)
- **Column added: YES.** `query_backlog_ces` selects `RevenueType` (same rows, same filters; every channel is still pulled). The daily job builds its files with the column (test with fake rows incl. a Tendering row: the stock file and the reserved totals do not change).
- **Which job rebuilds the operation plan and when.** Only the monthly job (step 7b, then 7c for the material plan); the daily job does not. So the fresh PEM103 numbers appear in the **2026-11-05** monthly run at the earliest, using the daily pull of that morning, which will carry the column from tomorrow's 08:00 run on. The operation plan applies PEM103's Omni limit to the latest pull and falls back to the saved week-3 rows only when the column is missing (the code already did; unchanged). **Fallback note: YES, tested.** Until then (today's rebuild used the 2026-10-14 daily pull, which has no column) the page shows under PEM103's table "ออเดอร์ของ PEM103 ในแผนนี้ใช้ข้อมูลที่ดึงไว้เมื่อ 6 ต.ค. 69 14:49 …". No real pull was run.

### Step 4: labels
- Operation plan page: PEM103's demand column header and its division lines about accepted orders carry **"เฉพาะ Omni (ไม่รวมงานประมูล)"** (tooltip: ออเดอร์ของ PEM103 นับเฉพาะช่องทาง Omni Channel งานประมูลไม่อยู่ในแผนนี้); the other divisions keep "รวมทุกช่องทาง".
- Material plan page: the demand header of each month and the order-quantity header of the two lists carry **"รวมทุกช่องทาง (ยกเว้น PEM103)"** with the tooltip "ปริมาณคิดจากแผนการผลิต ซึ่งนับ stock และออเดอร์ที่รับแล้วรวมทุกช่องทาง ยกเว้น PEM103 ที่นับเฉพาะช่องทาง Omni Channel".

### Step 5: "ระบบ" naming a data source → "DB (<table>)"
Outside the original S&OP tab; other meanings of "ระบบ" were left (for example "ระบบเทียบยอดทายกับยอดขายจริง", "ผู้ดูแลระบบ", "ทำได้ทั้งระบบ", "สเปคสองระบบ", "ระบบไม่มีทางลัดให้ข้ามช่วงนี้", "เพราะระบบเปลี่ยนเมื่อ …"). Tables chosen from the code that reads each source (Cube_Inventory_Exact stock and Min/Max settings; Cube_CES backlog; cube_Sale_APD sales and the MTS/MTO label; cube_final production records; Cube_BOM_Exact; Cube_PriceList and Cube_tobe_received purchase units; Cube_PO_Exact orders; Cube_Production_Order production orders; Cube_ItemList item master). Changes, before → after (count):
- “'ข้อมูล stock ในระบบ ณ '” → “'ข้อมูล stock ใน DB (Cube_Inventory_Exact) ณ '” (1×; index.html)
- “'ยอดจองในระบบ ณ '” → “'ยอดจองใน DB (Cube_CES) ณ '” (1×; index.html)
- “ไม่มีในระบบ stock” → “ไม่มีใน DB (Cube_Inventory_Exact)” (1×; index.html)
- “ไม่มีข้อมูลในระบบ</span>” → “ไม่มีข้อมูลใน DB (Cube_Inventory_Exact)</span>” (2×; index.html)
- “(แสดงตามที่บันทึกไว้ในระบบ ไม่มีการรวบหรือตัดรายการซ้ำออก)” → “(แสดงตามที่บันทึกไว้ใน DB (Cube_CES) ไม่มีการรวบหรือตัดรายการซ้ำออก)” (1×; index.html)
- “ไม่มียอดขายในระบบสำหรับปี” → “ไม่มียอดขายใน DB (cube_Sale_APD) สำหรับปี” (1×; index.html)
- “ค่าที่ตั้งในระบบ” → “ค่าที่ตั้งใน DB (Cube_Inventory_Exact)” (8×; config/manual_notes.yaml, docs/user_manual.md, src/build_inventory_page.py)
- “บันทึกไว้ในระบบคลัง” → “บันทึกไว้ใน DB (Cube_Inventory_Exact)” (2×; config/manual_notes.yaml, docs/user_manual.md)
- “ใส่ค่า Max ไว้ในระบบ” → “ใส่ค่า Max ไว้ใน DB (Cube_Inventory_Exact)” (2×; config/manual_notes.yaml, docs/user_manual.md)
- “วันที่ดึงข้อมูลจากระบบ” → “วันที่ดึงข้อมูลจาก DB” (1×; docs/user_manual.md)
- “ไม่มีข้อมูลในระบบ ซึ่งหมายถึงรหัสนี้ไม่มีบันทึกในระบบคลัง” → “ไม่มีข้อมูลใน DB (Cube_Inventory_Exact) ซึ่งหมายถึงรหัสนี้ไม่มีบันทึกในตารางนั้น” (1×; docs/user_manual.md)
- “คีย์ช้าเข้าระบบครบก่อน” → “คีย์ช้าเข้า DB (cube_Sale_APD) ครบก่อน” (1×; docs/user_manual.md)
- “คีย์ช้าเข้าระบบครบ ข้อมูลล่าสุด” → “คีย์ช้าเข้า DB (cube_Sale_APD) ครบ ข้อมูลล่าสุด” (1×; docs/user_manual.md)
- “ตัดสินจากป้ายในระบบ (MTS / MTO / ETO)” → “ตัดสินจากป้ายใน DB (cube_Sale_APD) (MTS / MTO / ETO)” (1×; docs/user_manual.md)
- “ถ้า Min ในระบบสูงกว่าที่จำลอง” → “ถ้า Min ใน DB (Cube_Inventory_Exact) สูงกว่าที่จำลอง” (2×; docs/user_manual.md, src/build_inventory_page.py)
- “ที่ตั้งในระบบคลัง” → “ที่ตั้งใน DB (Cube_Inventory_Exact)” (2×; src/build_inventory_page.py)
- “ข้อมูล stock ในระบบ ณ ” → “ข้อมูล stock ใน DB (Cube_Inventory_Exact) ณ ” (1×; src/build_inventory_page.py)
- “ยอดจองในระบบ ณ ” → “ยอดจองใน DB (Cube_CES) ณ ” (1×; src/build_inventory_page.py)
- “ระบบไม่ได้บันทึกว่าของที่ส่งออกไปมาจากคลังไหน” → “DB (cube_Sale_APD) ไม่ได้บันทึกว่าของที่ส่งออกไปมาจากคลังไหน” (1×; src/build_inventory_page.py)
- “ดูจากป้ายในระบบ (MTS / MTO / ETO)” → “ดูจากป้ายใน DB (cube_Sale_APD) (MTS / MTO / ETO)” (1×; src/build_inventory_page.py)
- “-->ระบบขายของบริษัท</td>” → “-->DB (cube_Sale_APD)</td>” (1×; src/build_report.py)
- “ไม่มีบันทึกผลิตในระบบ” → “ไม่มีบันทึกผลิตใน DB (cube_final)” (6×; src/build_material_plan_page.py, src/build_operation_plan_page.py)
- “ป้าย MTS/MTO ที่บันทึกในระบบ” → “ป้าย MTS/MTO ที่บันทึกใน DB (cube_Sale_APD)” (1×; src/build_operation_plan_page.py)
- “ไม่มีหน่วยซื้อในระบบ” → “ไม่มีหน่วยซื้อใน DB (Cube_PriceList, Cube_tobe_received)” (1×; src/build_material_plan_page.py)
- “ไม่มี BOM ในระบบ” → “ไม่มี BOM ใน DB (Cube_BOM_Exact)” (2×; src/build_material_plan_page.py)
- “ระบบไม่มีบันทึกการแก้” → “DB (cube_Sale_APD) ไม่มีบันทึกการแก้” (1×; config/config.yaml)
- “Min/Max ที่ตั้งอยู่ในระบบตอนนี้” → “Min/Max ที่ตั้งอยู่ใน DB (Cube_Inventory_Exact) ตอนนี้” (1×; config/config.yaml)
- “no_master: "ไม่มีข้อมูลในระบบ"” → “no_master: "ไม่มีข้อมูลใน DB (Cube_ItemList)"” (1×; config/config.yaml)
- “unknown: "ระบบไม่บันทึกวันเริ่มผลิตจริง"” → “unknown: "DB (cube_final) ไม่บันทึกวันเริ่มผลิตจริง"” (1×; config/config.yaml)
- “unknown: "ไม่มีใบสั่งซื้อในระบบ"” → “unknown: "ไม่มีใบสั่งซื้อใน DB (Cube_PO_Exact)"” (1×; config/config.yaml)
- “unknown: "วันกำหนดเสร็จในระบบไม่ตรงกับวันเสร็จจริง"” → “unknown: "วันกำหนดเสร็จใน DB (Cube_Production_Order) ไม่ตรงกับวันเสร็จจริง"” (1×; config/config.yaml)
The reader-text guard accepts the table name only inside "DB (<table>[, <table>])"; a bare table name still fails. A test pins the old phrases as gone.

### Step 6: freshness by cadence (decision 6)
- **Sources by cadence** (config `page_timestamps`; a source in neither list, or in both, stops the build):
  - monthly-pulled: the seven sections of the sales report (ช่วงข้อมูลหลัก, ผลทดสอบต่อฝ่าย, กราฟ Rolling-origin, กราฟระยะเวลาแจ้งล่วงหน้า, กราฟ MAE โมเดลพื้นฐาน, กราฟส่งตรงวันพอดี, กราฟส่งทัน) and the PEM103 and PEM107 sales of the Min-Max page;
  - daily-pulled: the stock and the reserved figures of the Min-Max page and of the stock panel on index.html.
- **Rule**: monthly source old when its pull date is before the latest run day on or before today; daily source old when its pull date is before the previous weekday. Thresholds in `manual_values`: `stale_monthly` ("5 ต.ค. 69" today) and `stale_daily` (1 weekday back), replacing `stale_days`; the manual line uses both placeholders. `staleness_threshold_days` is gone from src, config and tests. The Min-Max page embeds the cadence and the monthly cutoff; its script (and index.html's panel script, one small function each) judges daily sources against the previous weekday of the day they were pulled. The notices no longer say "page_built_at".
- **Examples tested**: monthly 2026-10-04 (cutoff 2026-09-07, because 5 September 2026 is a Saturday), 10-05 (pull of 10-05 fresh, of 10-04 old), 10-14 (10-05 fresh), 11-05 (10-05 old, 11-05 fresh); daily Monday 2026-10-12 (a Friday pull fresh, a Thursday pull old), Tuesday 10-13 (Monday fresh, Friday old), Saturday and Sunday (Friday), and in the browser for the stock panel and the Min-Max page.
- **Tags before → after, today's build (2026-10-14).** The held clock is removed: the sales report was built with the real clock (14 ต.ค. 69 09:07). Seven monthly sections, all pulled 5 ต.ค. 69: committed page (clock held at 12 October) ใหม่ ×7; under the old 7-day rule with the real clock, as seen in the Prompt 28 rebuild, เก่ากว่า 7 วัน ×7 plus a warning box; **new rule, real clock: ใหม่ (Fresh) ×7, no warning box.** Min-Max page: the monthly pilot sales (pulled 5 October) fresh; the daily stock and reserved notices are evaluated when the page opens (a 13 October load against a 14 October pull: fresh).

### Step 7: Edge leak (decision 7)
- **Before (listed, all started by this repo's test helper, by their profile folder `page_test_edge_*`):** 33 processes in 25 profile groups, started 2026-10-06 12:24 to 2026-10-14 08:41, one profile with 9 processes (PIDs 31176, 52036, 36320, 31284, 51164, 42768, 51448, 16200, 42724), 24 profiles with 1 or 2 processes (first PIDs 26268, 28676, 28116, 27908, 34688, 24584+22400, 4612, 33816, 22124, 3840, 10284, 12820, 5536, 38444, 35924, 36644, 37208, 17680, 10008, 35068, 41832, 43740, 56316); 3 profile folders on disk. Paths under the user's temporary folder (masked). All 33 were stopped by PID, then the folders deleted; the 30 other Edge processes (not using such a profile) were not touched, nothing was stopped by name.
- **After:** 0 processes and 0 folders, checked after the browser check and after the full test run.
- **Cause and fix.** `Edge.close()` ended only the root PID with `taskkill /T`; Edge's helper processes survived it and kept the profile folder. `tests/page_helpers.py` now ends the root, then every process whose command line names this helper's own profile path, by PID (tree), until none is left, then deletes the profile with retries; it is idempotent, runs in the `finally` of every fixture and test that uses it, and is also registered with `atexit` so an interrupted session cleans up. **Test**: `test_the_edge_helper_leaves_no_child_process_and_no_profile_folder_after_a_browser_test_or_a_failed_one` starts a real headless Edge, once ending normally and once after an error raised in the test, and asserts no process names the profile and the folder is gone.

### Checks
- **Numeric gate** (rendered text of every page and tab, headless Edge, before = the HEAD files):
  - S&OP tab: identical. Stock panel: identical (its labels and notices are static until the data is loaded).
  - Executive tab: 243.7% → 244.9% and 533 → 544 (rebuilt plan), nothing else.
  - Trend and assumptions tabs: wording only (DB (cube_Sale_APD); the three assumption rows), no number. Manual: the freshness line and the DB wording; numbers added only by the new line: 69 (5 ต.ค. 69), 5, 1.
  - Sales report: only the build time (12 ต.ค. 69 15:03 → 14 ต.ค. 69 09:07).
  - Min-Max page: the 98.34% family and the curve of Step 1 (every shown number that differs: 98.34% → 98.24% six times, 98.61% → 98.60%, 14,439,372 → 14,170,763, 2,934,029 → 2,828,983, 24,722,224 → 24,535,326, −1,052,111 → −1,320,720, the PEM101 item figures that follow the default preset), the pilot sales pull label (12 ต.ค. 69 15:03, "live pull" → 5 ต.ค. 69 07:41, the monthly pull that holds the data) and the build time.
  - Operation plan and material plan: differ for the two reasons given under Step 1 (recalibrated Min/Max and the newer pulls); the labels and the PEM103 note add words and the numbers 37 (a count in the PEM103 note) and 14/6 (dates).
- **Data gate.** `data/assumptions.json` changed (wording of three assumption rows, `updated_date`, the two thresholds replacing `stale_days`); `data/inventory.json` and `data/stock_daily.json` were not changed by this task (they change only through the daily job). Forward-test, shadow, score and comparator logs and the vintage snapshot were not modified (checked by modification time). Local untracked outputs rewritten by Step 1 (by design): `output/summary/week1_recal_*`, `maxmin_v1_*`, `operation_plan_v1_*`, `material_plan_v1_*` (before copies kept in the scratch folder).
- **Runner dry runs** (fakes, no database): monthly `--dry-run --offline --skip-tests` exit 0, all 16 steps, 5 gates passed, 0 failed (3 not tested, as before); daily `--dry-run --from-pulls` exit 0, 0 failed of 4 gates, no tracked file touched.
- **Browser check** (headless Edge, temporary profile, before and after): 0 script errors on all five pages; the one console line (a 404) is the same before and after (the browser's default icon request). The Edge run left no process and no folder.

**Validator.** MATCH. It re-derived the recalibration values, the Min-Max page differences (92 of 92 PEM101 items change, PEM107 0), the freshness rule and tags, the Edge helper code, the numeric gate and the has_any_history and backlog-column changes, and found no logic error or dead code. Its additions, now in the report: three more page values that follow the recalibration (stretch preset stock value, a label text, one more excluded point), the plan share of the recalibration holds on counted rows only (-1,556.6), and PEM103's backlog still comes from the saved week-3 rows until a daily pull with the column exists. It found 10 Edge processes during its first query, which belonged to my test run in progress, and 0 a few minutes later.

**Tests.** Final full run after the last change: 833 passed, 0 failed, 0 skipped (about 22 minutes); no Edge process and no profile folder was left by the run. Test-suite database connection attempts: 0 (the block's own 4 deliberate attempts were blocked). Earlier full runs found failures that were text expectations of changed wording and the stale threshold; they were updated (not deleted) and the suite rerun. New tests: has_any_history Omni filter and the monthly flip report; the RevenueType column of the daily backlog and the daily job with it; PEM103's limit applied to the latest pull and the fallback note; the two labels; no source named as ระบบ; freshness rule examples (monthly around run days, daily Monday against the previous Friday, in Python and in the browser for the stock panel and the Min-Max page); unclassified source stops the build; the Edge teardown after a normal and a failed browser test.

### Found, not done
- `output/data/lead_time_inputs/ces_92.csv` (the input of the recalibration) has no producer script in src; a re-pull would be by hand. — S — you decide.
- The recalibration still needs a manual start each time the calibration data changes; no job runs it. — S — you decide (not added, as asked).
- The Min-Max page's pilot sales label was "2026-10-12 15:03:45 (live pull, not a frozen file)" in the committed page and is now "2026-10-05 07:41:06" (the monthly pull that holds the data); it was not clear from the code why the earlier build carried a live-pull label with the same data. — S — you.
- Page text that names a source only as "ข้อมูล" or by a file name (not as "ระบบ") was left. — S — you.
- Stale comments from Prompt 27 are still open. — S — next cleanup.


## Prompt 30

Behaviour-preserving refactor and cleanup. Date and time: 2026-10-14, started 10:57 +07:00 (`git pull origin main`: nothing new). No database session, no npm. Items by code only. One agent made the changes; a separate Validator, evaluate-only, re-checked them. The one approved new file is `src/build_exec_summary.py`; no other file was added.

### Step 0: baseline and equivalence
Every page was built from the saved inputs into a scratch folder before any change (index.html with the Trend data and the executive tab written into a copy, the four forecast pages, and `assumptions.json`; the Min-Max page from the same frozen daily snapshot of 2026-10-09 that the tracked page was built from). The baseline equals the tracked pages (build times aside) and two builds in a row are identical, so the comparison method is sound. After the last code change the same script built again. **Differences, all of them:**
- `index.html`: the Trend note script text "ข้อมูลถึง " → "ข้อมูลขายใน DB (cube_Sale_APD) ถึง " (Step 7).
- `forecast/inventory.html`: " · ข้อมูล stock ดึงเมื่อ " → " · ข้อมูล stock จาก DB (Cube_Inventory_Exact) ดึงเมื่อ " (Step 7); the build time.
- `forecast/operation_plan.html`: the data line "ข้อมูล stock ดึงเมื่อ …" → "ข้อมูล stock จาก DB (Cube_Inventory_Exact) ดึงเมื่อ …" (Step 7).
- `data/assumptions.json`: one added manual value `n_calibration_items` = "92" (Step 6, the placeholder of the new manual section).
- Everything else is identical in text and numbers: the sales report and the material plan; the executive tab block of index.html is byte-identical (the PEM104 row included); every other part of index.html, the inventory page and the plan page. No input was refreshed between the two builds.

### Step 1: `build_trend_tab.py` split
Moved to `src/build_exec_summary.py` (275 lines): the markers, `ExecSummaryError`, `exec_month_units`, `exec_month_baht`, `exec_booked_units`, `exec_watch`, `exec_data`, `exec_render` (with its two formatters), `exec_gate`, `write_between`, `run_exec_build` and its own command line (`--build`). `src/build_trend_tab.py` (398 lines) keeps the Trend tab only; its `--build-exec` option and the unused `math` import are gone. The shared code is not copied: `TrendTabError`, `load_config` and `PROJECT_ROOT` live in `build_trend_tab.py` and are imported by the new module. Updated: the runner's step 7f (imports `build_exec_summary`, still stops the run on `TrendTabError`), the comments naming the file (runner, config, METRICS Sec.49), `src/investigations/model_experiment_2026_10.py` (imports the two functions it uses from the new module), and the tests (`test_index_w3.py`, `test_monthly_refresh.py`: `bx` for the executive functions, `bt` for the Trend ones).

### Step 2: PEM104's reason is one config entry
Config top-level `not_forecast_reasons` → `made_to_order: {divisions: [PEM104], line: "{division} ผลิตตามสั่งทั้งหมด จึงไม่ได้ทายยอดขาย", min_max_line: "ไม่มีนโยบาย stock ฝ่ายนี้ผลิตตามสั่งทั้งหมด"}`. Removed: `operation_plan.exclusion_reasons`, `exec_summary.text.remark_PEM104`, the typed text in `build_operation_plan_page.py` (`line_made_to_order`) and in `build_inventory_page_data.py`, and the typed `PEM104` row in the executive builder. Readers (all through `reader_values.not_forecast_reasons`, `division_reason_codes`, `not_forecast_text`): the executive table (one row per configured division, remark = `line`), the operation plan's division line (`line`), the Min-Max page's text for a division without a stock policy (`min_max_line`). The wording is in config twice (the two lines of the one entry) and in no code file; the pages show the same text as before (Step 0).

### Step 3: investigation scripts and the login
**11 scripts** now go through `db.session(preflight=True)` (the lock check, the preflight, one attempt, `LoginRefused` ends with exit code 3): phase23_part0_cubefinal_join, phase24_explorerC_q19q20, phase24_explorerD_pull, phaseI_single_pull, phaseJ2_explorerA_quotation_notice, phaseJ2_explorerB_pull, phaseJ2_explorerD_pull, phaseJ3_explorerBOM_pull, phaseJ3_explorerD_pull, phaseJ_single_pull, task2b_part7_validator. Only their connection lines changed (import, `engine = get_connection()` / `engine.connect()` replaced by the session, an `ExitStack` where they closed the connection in a `finally`); SQL and logic are untouched (Validator checked the diff). `db.session` gained the `preflight` flag (default off, so the jobs behave as before). **None was run.** Static check (ast over every file in src): no call of `get_connection()` or `engine/conn.connect()` outside `src/db.py` (test `test_nothing_outside_db_py_opens_a_connection_itself`); a second test checks that the preflight runs first only when asked.

### Step 4: dead code and stale text
- **Removed** from `build_inventory_dataset.py` (grep on HEAD showed no caller in src, tests, config or docs): `build_backlog_rows`, `classify_negative_causes`. Not removed (not on the list): `flag_duplicate_backlog_rows` and `BACKLOG_DEDUP_KEY`, now orphan siblings with no caller (Found, not done).
- **Stale text fixed:** `tests/test_page_timestamps.py` docstring (said `query_backlog` is kept), the `snapshot_daily.py` docstring (said it calls `run_query`), the module docstring of `build_inventory_dataset.py` (still described Cube_Backlog and the warehouse roles; now describes Cube_CES, the two saved pulls and `--from-pulls`).

### Step 5: a stage that exits 0 without writing
In the monthly runner, `_pull_stage` (step 1) and `_run_regeneration_step` (step 4) now record the declared output file's state before the stage (mtime and sha256, or "missing") and after it. A stage that exits 0 and leaves both unchanged (or leaves the file missing) adds one WARN line to the run log, the run is marked partial and the command ends with **exit code 2** (and the month is not marked done, so the next weekday runs again). A rewritten file does not warn, a non-zero exit keeps its own single WARN. Tests with fakes (`test_monthly_refresh_failure_log.py`): pull stage (unwritten, rewritten, missing, exit 1), regeneration step, and the whole run partial with `mr.cli` returning 2; the earlier test of an auxiliary failure was updated, because its fake stages exit 0 and write nothing (each now warns). Risk, stated by the Validator: a script that skips writing when nothing changed would warn; none of the step 1 and step 4 outputs (all rewritten each run) does that as far as the call sites show.

### Step 6: producer of the recalibration input
`pull_ces_input()` and the option `--pull` in the existing module `src/investigations/week1_recalibration.py` (by hand only, in no job): one session through `db.session(preflight=True)`, `pull_cube_ces_for_items` (no date filter) for the 92 items listed in config `maxmin_v1.ensemble_stock_items_file` (`stock92.json`), Omni Channel only, the ten columns of the saved `ces_92.csv` in the same order, written to `ces_92.csv`. **Its output has not been compared with a real pull**: the earlier file was made by a script that is not in the repository (and held Tendering and blank rows too), and this pull was not run. Test (fakes): the column list equals the saved file's header, the session and the preflight are used, the SQL holds the Omni filter, the item list and no date condition, the written file has exactly the schema. **Manual:** new section "วิธีคำนวณ calibration ใหม่ (PEM101)" before the Trend tab section: the four steps in plain words (no file names: the reader-text guard rejects them; the commands are in METRICS.md Sec.49 note of Prompt 30), that each run changes the Min and Max of all {n_calibration_items} PEM101 stock-policy items, and that a person decides when to run it; the number comes from the new manual value `n_calibration_items`.

### Step 7: source wording
The on-screen Min-Max text was already "Min ค่าที่ตั้งใน DB (Cube_Inventory_Exact)" since Prompt 29; the old words "Min ที่ตั้งในระบบตอนนี้" remain only in an off-screen comment of the page builder and the page. Page, manual and manual-notes text that gave a DB source only as "ข้อมูล": changes, before → after:
- `src/build_operation_plan_page.py` (1x): "ข้อมูล stock ดึงเมื่อ" → "ข้อมูล stock จาก DB (Cube_Inventory_Exact) ดึงเมื่อ"
- `src/build_inventory_page.py` (1x): "ข้อมูล stock ดึงเมื่อ" → "ข้อมูล stock จาก DB (Cube_Inventory_Exact) ดึงเมื่อ"
- `docs/user_manual.md` (2x): "ข้อมูลถึง {trend_data_through}" → "ข้อมูลขายใน DB (cube_Sale_APD) ถึง {trend_data_through}"
- `index.html` (1x): "ซึ่งนับตามเดือนที่ต้องส่งของ · ข้อมูลถึง ' + meta.pull" → "ซึ่งนับตามเดือนที่ต้องส่งของ · ข้อมูลขายใน DB (cube_Sale_APD) ถึง ' + meta.pull"
- Tests that pinned the old text were updated (`test_operation_plan_page_builder.py`, `test_inventory_page_browser.py`, `test_index_w3.py`).
Other meanings of "ระบบ" and "ข้อมูล" were left. A test pins the new wording and that the old phrases are not shown.

### Checks
- **Data gate.** `data/assumptions.json` changed by one line (`n_calibration_items`, Step 6; nothing from Step 2 or 7 is in it). `data/inventory.json` and `data/stock_daily.json` were not touched (the daily job may change them). Forward-test, shadow, score and comparator logs and the vintage snapshot were not modified (by modification time).
- **Runner dry runs** (fakes, no database): monthly `--dry-run --offline --skip-tests` exit 0, all 16 steps, 5 gates passed, 0 failed; daily `--dry-run --from-pulls` exit 0, 0 failed of 4 gates, no tracked file touched. The Step 5 case ends with **exit 2** in `test_the_run_with_such_a_stage_is_partial_and_the_command_ends_with_exit_code_2`.
- **Browser check:** headless Edge on a temporary profile, the working-tree pages: index (S&OP, Executive, Trend, Manual tabs), sales report, Min-Max, operation plan, material plan: **0 script or console errors on every page**; Min-Max and operation plan show "ข้อมูล stock จาก DB (Cube_Inventory_Exact) ดึงเมื่อ"; Trend note and manual show "ข้อมูลขายใน DB (cube_Sale_APD) ถึง"; the executive tab shows the PEM104 made-to-order line. Edge process tree closed by PID: 0 processes and 0 profile folders left.

**Validator.** Read-only subagent (evaluate only, no edit). **MATCH on all five claims**: (1) page equivalence apart from the Step 7 wording and the one manual value; (2) no connection opened outside `src/db.py`; (3) the two removed functions had no caller; (4) Step 5 behaviour; (5) Step 2 is config only. Its notes: `week1_recalibration.py` got new logic (`--pull`) beyond connection lines (Step 6, asked for); the import rename in `model_experiment_2026_10.py`; the orphan `flag_duplicate_backlog_rows`/`BACKLOG_DEDUP_KEY` (listed below); the executive builder had a hard-coded `made_to_order` key (fixed to iterate the configured divisions); a false warn is possible only for a stage that skips writing when unchanged.

**Tests (final full run, after the last change):** 841 passed, 0 failed, 0 skipped (17 min 6 s). Database connection attempts by the suite: 0 (4 blocked, all deliberate, made by the block's own test). An earlier full run had one failure (the manual section named script files, which the reader-text guard rejects); fixed by plain wording and the whole suite rerun. Doc-scan tests (guards, reader_text, manual_notes_sync, manual_tab): 56 passed, rerun after the report is written.

### Found, not done
- `flag_duplicate_backlog_rows` and `BACKLOG_DEDUP_KEY` in `build_inventory_dataset.py` have no caller. — S — you decide.
- The new `--pull` producer has not been run; its output is untested against a real pull. — S — you, at the next recalibration.
- Many investigation scripts still print "DATABASE ACCESS RULE" docstrings that mention `get_connection()` (comments only). — S — next cleanup.
- A script that skips writing its output when nothing changed would now raise the Step 5 warning; none is known. — S — watch the 2026-11-05 run log.


## Prompt 31

Start (Get-Date): 2026-10-14 13:25:36 +07:00. End: 2026-10-14 13:55:19 +0700 (shell clock). No database session, no npm. Nothing deleted, moved or renamed in Part B; no new file in the repo.

### Part A: code cleanup (committed and pushed on its own: 703db04)
- **Removed** from `src/build_inventory_dataset.py`: `flag_duplicate_backlog_rows` and `BACKLOG_DEDUP_KEY` (grep over the whole repo: no caller, no test, no config entry; `is_cross_contract_duplicate` is named nowhere else).
- **Docstring fixed:** `src/investigations/phaseJ2_explorerA_quotation_notice.py` was the only file outside `db.py` that still said `get_connection()` is called; it now says one `db.session(preflight=True)` is opened. No other investigation file mentions it.
- **Equivalence:** all pages and `assumptions.json` built before and after (same frozen inputs): identical (build times ignored).
- **Dry runs after the last change:** monthly `--dry-run --offline --skip-tests` exit 0; daily `--dry-run --from-pulls` exit 0; `git status` clean afterwards.
- **Full suite after the last change:** 841 passed, 0 failed, 0 skipped (15 min 35 s); 0 database connection attempts (4 blocked, all deliberate).

### Part B: inventory of leftover files (read only)

**Method.** Sizes, counts and times come from the file system. "Read by" comes from a scan of every file under `output/` against the names in `src` (jobs and pipeline), `tests`, `config`, the pages, and `src/investigations` (run by hand). Classes: DELETE-SAFE needs both "read by nothing" and a stated way to regenerate; the ALWAYS KEEP set is KEEP. A file named only by a one-off investigation script, or by nothing, is USER DECIDES, never DELETE-SAFE. KEEP means a scheduled job, a page build, a test or a by-hand script of the current work (for example the recalibration) reads it. Paths are masked (`%TEMP%`, `<user>`).

**D:\ top level.** 35 names. In scope (3): `sale_forecast` (the repo), `sale_forecast_publish` (the publishing clone, report only; the two scheduled tasks that name this project run its `src` after a pull), `sale_forecast_private` (named in the task). The other 32 names (21 folders, 11 files, including the loose `tmp_*.csv` files and the `tmp` folder) were left out: no code, config, test, scheduled task or run log of this repo names them (the only mentions are a worker report that searched some of them for a missing file and found nothing). Their names are not listed and none was opened.

**%TEMP%.** Created by this repo's code: `db_block_*` (tests/conftest.py), `monthly_refresh_dry_*` (src/monthly_refresh.py). `page_test_edge_*`, `edge_cdp_verify_*`, `daily_stock_*`, `vintage_rehearsal_*`: 0 folders now; no process names any of them. The pytest base folder (`pytest-of-<user>`, about 595 MB) is made by pytest and shared with any project's pytest runs, so it cannot be attributed to this work and is NOT in the table (see Found, not done).

**Publishing clone.** Everything it tracks, its `output` and `reference` junctions (to the repo's folders) and its `.env` hard link: KEEP, not listed. Only its git-ignored `src/__pycache__` is a candidate.

**Inventory table**

| path | size | files | last modified | evidence of origin | read by now | regenerable | class |
|---|---|---|---|---|---|---|---|
| `%TEMP%\db_block_* (43 folders, made by tests/conftest.py)` | 0.01 MB | 14 | 2026-10-14 13:32 | name pattern created by tests/conftest.py (mkdtemp prefix db_block_) | nothing (the suite reads only its own current folder while it runs; none is running) | yes, every test run makes one | **DELETE-SAFE** |
| `%TEMP%\monthly_refresh_dry_* (117 folders, made by monthly_refresh.py --dry-run)` | 0.00 MB | 0 | 2026-10-14 13:39 | name pattern created by monthly_refresh.py (mkdtemp prefix monthly_refresh_dry_) | nothing (117 folders hold only an empty forecast subfolder; skip any folder a running process names, one was live during the check) | yes, every dry run makes one | **DELETE-SAFE** |
| `D:\sale_forecast\.pytest_cache` | 0.07 MB | 5 | 2026-10-09 11:30 | pytest cache (git status --ignored); the suite is run with -p no:cacheprovider | nothing | yes, pytest recreates it | **DELETE-SAFE** |
| `D:\sale_forecast\src\__pycache__, src\investigations\__pycache__, tests\__pycache__` | 5.72 MB | 151 | 2026-10-14 13:27 | Python bytecode caches; git-ignored (*.pyc, __pycache__/) | Python (rebuilds them on import) | yes, automatically | **DELETE-SAFE** |
| `D:\sale_forecast_publish\src\__pycache__ (publishing clone, git-ignored cache only)` | 0.34 MB | 18 | 2026-10-13 08:00 | bytecode cache of the scheduled jobs, git-ignored; do not remove while a job runs | Python (rebuilds) | yes, automatically | **DELETE-SAFE** |
| `output/charts/ PNGs whose writer script is named in code (phaseE1_*, b4_/datecol_/delivery_/hyp_/leadtime_/link_/task1_/task3_, phaseC_step2_*)` | 2.28 MB | 32 | 2026-10-05 07:42 | name is in a script's log/print or path (the writer); not screenshots | nothing (no page, test or job reads them) | yes: re-run the named script (investigation scripts: some may need a DB session, unverified) | **DELETE-SAFE** |
| `output/runs/<timestamp>/staged/ (dry-run staging copies of pages)` | 10.15 MB | 9 | 2026-09-29 12:15 | written by monthly_refresh.py --dry-run (12 folders, 2026-09-25 to 2026-10-05; 4 hold no file) | nothing (read only inside the dry run that wrote it) | a new dry run makes new staging of the current state, not these past copies | **DELETE-SAFE** |
| `output/runs/dryrun1.log, dryrun2_console.log` | 0.04 MB | 2 | 2026-09-25 15:35 | console logs of dry runs | nothing | yes: monthly_refresh.py --dry-run | **DELETE-SAFE** |
| `D:\sale_forecast\forecast\Chase S&OP Plan 2026 - PEM Group.html (tracked)` | 0.44 MB | 1 | 2026-08-24 11:41 | git-tracked standalone copy of the legacy S&OP page | nothing in code, a page or a link; tests/test_index_w3.py names it only to skip it ("belongs to the user"); index.html carries its own S&OP tab | it is in git | **USER DECIDES** |
| `D:\sale_forecast\src\ 5 tracked modules no code imports (charts_focus_items, migrate_forward_test_hash_scheme, phaseE1_current_settings_comparison, phaseE1_historical_simulation, phaseE1_maxmin_scenario)` | 0.04 MB | 5 | 2026-10-07 08:10 | git-tracked; only docs name them (each is run by hand) | no import in src, tests or the scheduled jobs (tests scan src/*.py as a whole; config comments name two) | it is in git | **USER DECIDES** |
| `D:\sale_forecast_private\target_data.xlsx` | <target> MB | 1 | 2026-08-20 10:29 | folder named sale_forecast_private; the target workbook | nothing (the revenue-target comparison was removed in Prompt 27; no src, config or test names the file) | no (supplied by the business) | **USER DECIDES** |
| `output/charts/ files cited in docs, no code reference` | 0.15 MB | 2 | 2026-10-05 08:11 | screenshots / charts cited by name in reports | nothing | unknown | **USER DECIDES** |
| `output/charts/ screenshots and charts with no named writer (verification folders, week3, daily_stock, ...)` | 43.37 MB | 185 | 2026-10-06 13:38 | browser screenshots of past page states (inventory_verification, manual_baseline, task2c_verification and the rest) | nothing | no (they show past page states) | **USER DECIDES** |
| `output/data/*.csv named only by investigation scripts or by nothing (old saved pulls: phase*, raw_*, processed_* of 2026-08/09)` | 147.96 MB | 82 | 2026-10-05 07:42 | saved pulls / intermediate tables of one-off investigations | only investigation scripts (some as a cache before a DB query) or nothing | re-pull needs DB sessions | **USER DECIDES** |
| `output/data/exec_pull/ (targets.csv + meta)` | <target> MB | 2 | 2026-10-09 09:07 | the revenue-target pull; target comparison removed in Prompt 27 | nothing | needs the target workbook / DB | **USER DECIDES** |
| `output/data/material_pull/ 4 files no code reads (_classification_preview, _remarks_preview, _reverify23, item_movement_types)` | 0.84 MB | 4 | 2026-10-12 09:06 | saved pulls of earlier validation work | nothing (no src, test or config reference) | re-pull needs DB | **USER DECIDES** |
| `output/pem101_evidence/, pem107_evidence/` | 0.02 MB | 2 | 2026-10-05 16:16 | evidence files cited in docs | nothing | no | **USER DECIDES** |
| `output/runs/step8_tail.txt, task2cfix_visual_check*.py (loose scratch files)` | 0.01 MB | 3 | 2026-09-25 15:38 | one-off check files | nothing (no reference) | no (the two .py are not tracked) | **USER DECIDES** |
| `output/shots_p8 .. shots_p14/ (verification screenshots)` | 5.57 MB | 77 | 2026-10-09 09:49 | screenshots of past page states (7 folders) | nothing | no (past states) | **USER DECIDES** |
| `output/snapshots/posting_delay.csv` | 0.01 MB | 1 | 2026-10-12 12:00 | snapshot_daily.py wrote it until 2026-10-12 (Prompt 27); the file no longer grows | nothing (snapshot_daily.py only mentions it in a comment) | no (history of a removed measurement) | **USER DECIDES** |
| `output/snapshots_quarantine_future_dated/` | 0.84 MB | 4 | 2026-10-02 10:22 | snapshots moved aside as future-dated (docs name it) | nothing | no | **USER DECIDES** |
| `output/summary/ files named by no code, config, page or test` | 51.44 MB | 520 | 2026-10-06 09:37 | name matches no reference in src, tests, config or pages; 144 of the 556 files are cited in docs | nothing | unknown (producer not found by name) | **USER DECIDES** |
| `output/summary/ files named only by one-off investigation scripts` | 92.36 MB | 521 | 2026-10-14 09:02 | written by an investigation script under src/investigations | no job, page or test (only that script, which is run by hand) | only by re-running that script (many need a DB session) | **USER DECIDES** |
| `D:\sale_forecast\.env (hard link to the publishing clone copy)` | 0.00 MB | 1 | 2026-09-18 10:17 | credentials file, git-ignored; the publishing clone uses the same file | db.py | no | **KEEP** |
| `D:\sale_forecast\reference\pricelist.xlsx` | 6.36 MB | 1 | 2026-08-21 09:26 | the Price List workbook (scope of the pilot) | build_report.py, build_trend_tab.py, build_exec_summary.py, build_operation_plan_page.py, inventory dataset | no (supplied by the business) | **KEEP** |
| `output/data/*.csv read by the pipeline (processed_*, raw_all_divisions_sales, raw_full_category_sales, ...)` | 23.76 MB | 13 | 2026-10-05 07:42 | named in src (not investigations), config or tests | load_data_*.py, monthly_refresh.py, forward_test*.py, build_report*.py, tests | yes by pipeline (DB for raw_*) | **KEEP** |
| `output/data/.gitkeep` | 0.00 MB | 1 | 2026-08-28 17:11 | placeholder | nothing | n/a | **KEEP** |
| `output/data/daily_stock_pull/ and inventory_pull/` | 1.90 MB | 10 | 2026-10-14 08:00 | saved pulls the daily and monthly runners write | build_inventory_dataset.py, monthly_refresh.py, operation_plan.py, tests | yes, the next job run (DB) | **KEEP** |
| `output/data/lead_time_inputs/ (incl. ces_92.csv, inventory_92.csv, stock92.json)` | 15.48 MB | 9 | 2026-10-05 16:04 | saved inputs of lead_time_v1.py and the recalibration | lead_time_v1.py (7 files), week1_recalibration.py by hand (ces_92.csv, inventory_92.csv), config | pulls need DB (ces_92 via --pull, unverified) | **KEEP** |
| `output/data/material_pull/ (4 files read by config)` | 41.19 MB | 4 | 2026-10-09 15:39 | config operation_plan / material plan inputs | material_plan.py, operation_plan.py, config (class_evidence.pkl: tests only) | pull needs DB | **KEEP** |
| `output/data/trend_pull/` | 1.20 MB | 3 | 2026-10-08 17:25 | Trend tab inputs | build_trend_tab.py, monthly_refresh.py, tests | pull needs DB | **KEEP** |
| `output/data/week2_inputs/ and week3_inputs/` | 11.33 MB | 3 | 2026-10-06 12:01 | config operation_plan input files | operation_plan.py, material_plan.py, tests, config | pull needs DB | **KEEP** |
| `output/forward_test/` | 0.04 MB | 1 | 2026-10-09 13:21 | forward-test vintage series | forward-test scoring | no (history) | **KEEP** |
| `output/runs/daily/ (run logs, last_success.json)` | 0.05 MB | 31 | 2026-10-14 12:39 | daily job logs; last_success.json read by the monthly gate | monthly_refresh.py, daily_stock_job.py, tests | no (audit trail) | **KEEP** |
| `output/runs/monthly_refresh_*.json (run logs)` | 0.56 MB | 32 | 2026-10-14 12:39 | monthly run logs; monthly_refresh.py lists earlier logs | monthly_refresh.py | no (audit trail) | **KEEP** |
| `output/snapshots/inventory_daily_* and inventory_page_pull_*` | 8.90 MB | 45 | 2026-10-14 12:54 | daily stock snapshots and page pulls | inventory_page_sources.py, daily_stock_job.py, build_inventory_page_data.py, tests | no (dated history) | **KEEP** |
| `output/state/` | 0.00 MB | 1 | 2026-10-12 10:00 | written by monthly_refresh.py | monthly_refresh.py, tests | n/a | **KEEP** |
| `output/summary/ files referenced by current code, config, pages or tests` | 11.29 MB | 132 | 2026-10-14 09:07 | name found in src (not investigations), config, a page or a test; some are only written there | see evidence | mostly by re-running the writing script | **KEEP** |
| `output/summary/archive/` | 2.91 MB | 36 | 2026-10-05 07:41 | forward-test logs archived with SHA-256 (ALWAYS KEEP set) | forward-test scripts, a test | no (archive) | **KEEP** |
| `output/summary/forward_test_* and ma_comparator_* (logs, scores, shadow, comparator, metadata)` | 1.74 MB | 11 | 2026-10-09 13:21 | forward-test, score, shadow and comparator logs (ALWAYS KEEP) | monthly_refresh.py, forward_test_*.py, pages | no (history) | **KEEP** |

| class | size | files |
|---|---|---|
| DELETE-SAFE | 18.60 MB | 231 |
| USER DECIDES | 356.22 MB | 1410 |
| KEEP | 126.72 MB | 334 |
| all | 501.54 MB | 1975 |

Notes: the DELETE-SAFE `output/charts` row is PNGs written by a named script; screenshots of past page states are USER DECIDES because re-running a check shows the current page, not the old one. "Regenerable" for the old dry-run staging copies means a new dry run makes new staging, not these copies. The `output/summary` KEEP row includes files that only a by-hand script reads or writes (for example `phaseE1_*`); that is conservative. `lead_time_v1.py` reads 7 of the 9 files in `lead_time_inputs`; `ces_92.csv` and `inventory_92.csv` are read only by the by-hand recalibration script, which is why they are KEEP (a saved input a current script reads).

**Validator (evaluate only, read only): first pass MISMATCH on checks 1 and 2, MATCH on check 3.** Findings and what changed:
1. 13 screenshots in the DELETE-SAFE chart row were not regenerable (`inventory_verification`, `manual_baseline`, `task2c_verification`), and `manual_baseline` had no writer at all (matched through another script's file names): moved to USER DECIDES. The 3 `focus_*_all_candidates.png` charts (written by `charts_focus_items.py` through an f-string) moved the other way, to DELETE-SAFE.
2. Four files in USER DECIDES are read through an f-string name (`build_inventory_page_data.py`, `phaseE2pilot_PEM103/PEM107` `1_item_policy` and `2_minmax_stockvalue_twogroup`): moved to KEEP. Other f-string families the Validator tested were write-only.
3. A live dry run was using one temp folder at the check, so "no process names them" was true at inventory time and false at the check; the row now says to skip any folder a running process names. The 117 other folders hold only an empty `forecast` subfolder. Staging folders are 12, not 13.
4. `%TEMP%\pytest-of-<user>` is outside the allowed scope: removed from the table.
5. Evidence text corrected: a test names the standalone S&OP copy only to skip it ("belongs to the user"); three tests scan `src/*.py` as a whole; `class_evidence.pkl` is read by a test only.
6. Confirmed by the Validator: nothing in the ALWAYS KEEP set is classed otherwise; exec_pull, pem101/107 evidence, `posting_delay.csv`, `snapshots_quarantine_future_dated`, `target_data.xlsx` have no reader. The corrections above were applied by me and the Validator was **not** run a second time.

### Need decision (USER DECIDES)
- `D:\sale_forecast_private\target_data.xlsx` (<target> MB): nothing reads it since the revenue-target comparison was removed (Prompt 27).
- `output/data/exec_pull/` (2 files): the target pull, nothing reads it.
- `output/snapshots/posting_delay.csv`: history of the removed posting-delay measurement; no longer grows.
- `output/data/` old saved pulls and intermediate tables named only by investigation scripts or by nothing (82 files, about 148 MB; re-pull needs DB sessions).
- `output/data/material_pull/` 4 files no code reads (0.8 MB).
- `output/summary/` files named only by one-off investigation scripts (522) or by nothing (523); many of the latter are cited in reports.
- Screenshots of past page states: `output/charts/` (about 42 MB), `output/shots_p8..p14/` (about 5.6 MB); `output/snapshots_quarantine_future_dated/`; `output/pem101_evidence/`, `output/pem107_evidence/`.
- `output/runs/step8_tail.txt` and the two untracked `task2cfix_visual_check*.py`.
- Tracked: `forecast/Chase S&OP Plan 2026 - PEM Group.html` (a test names it as the user's own copy); 5 modules no code imports.

### Found, not done
- `%TEMP%\pytest-of-<user>` is about 595 MB and 7.7 thousand files, made by pytest for every project's runs; not attributable, not in the table. Delete only by the user's decision, with no pytest running.
- This session's own scratch folder under `%TEMP%\claude\D--sale-forecast` (about 204 MB) is not named by any repo file, so it is outside the evidence rule; it is not listed and was not touched.
- Deleting any `%TEMP%` folder or `output/runs` staging folder must happen with no pytest, no dry run and no scheduled job running (a dry run was live during the Validator's check).


## Prompt 32

Start (Get-Date): 2026-10-14 14:07:54 +07:00. End: 2026-10-14 17:30:01 +0700 (shell clock). No database session, no npm. Pages and numbers were not changed by this prompt (only the cleanup of files, two temp-folder fixes with tests, the handover in STATUS.md and this report).

### Step 1: final list and re-validation
**Rule applied (user, 2026-10-14):** a candidate is deleted only if nothing references it. Reference = file name or relative path in code (src and src/investigations), config, tests, pages, scheduled jobs, any tracked document (docs, METRICS, STATUS, DATA_MAP, PROJECT_GRAPH, reports, manual, manual_notes), in this clone and in the publishing clone; names built from templates (f-strings, `{x}`, `*` globs) count; a document that names the screenshot or evidence folder counts for the files in it. Not counted: the Prompt 31 and Prompt 32 sections of this report and the matching STATUS entries (they are the inventory itself); the generic names `__pycache__`, `.pytest_cache` and the `db_block_` and `monthly_refresh_dry_` prefixes (patterns, not references to an instance). Where the rule and the explicit decisions conflict, the rule won (see Need decision).
- **My list:** 566 items: 5 caches, 162 temp folders, 5 DELETE-SAFE output items (2 dry-run logs, 3 staged run folders) and 394 files of the other classes for which my own reference scan found no reference.
- **Fresh Validator (own scan, evaluate only): 284 AGREE, 282 DISAGREE.** It found what my scan missed: names built from templates in `src/investigations` (224 summary files), `whmap_*` (9), prose globs in STATUS (31), a guard test that reads every `output/data/*.csv` (12 files), a documented `output/runs/*.log` (2). No scope or protected-set breach.
- **Dropped after disagreement: 282 items**, plus 2 `.gitkeep` placeholders kept and 2 charts (`manual_baseline`) kept as a precaution (named only by an untracked fact sheet). Item `item_movement_types.pkl` and the 3 staged folders were the Validator's borderline cases and stay.
- **Final list: 280 items: 167 permanent (5 caches + 162 temp folders), 113 to the Recycle Bin.**

### Step 2: execution
- **Nothing was running:** no process named the project, pytest, a job or any listed folder; both scheduled tasks in state Ready (monthly next 2026-10-15 07:00, daily next 2026-10-15 08:00). No task was changed.
- **Permanent:** 167 items, 6,131,972 bytes (6.13 MB): `src/__pycache__`, `src/investigations/__pycache__`, `tests/__pycache__`, `.pytest_cache`, the publishing clone's `src/__pycache__` (git-ignored caches only), 162 temp folders (`db_block_*`, `monthly_refresh_dry_*`).
- **Recycle Bin (restorable):** 113 files, 28,466,734 bytes (28.47 MB). The Shell shows 113 entries from the repo in the Bin.
- **Skipped (in use):** 0. **Already missing:** 0.
- **Verification:** every listed item gone; all 125 protected files (state, forward_test, snapshots, lead_time_inputs, the saved pulls read by jobs, the 4 material_pull files read by config, archive, forward-test/shadow/score/comparator logs and metadata, the Price List) have the same sha256 before and after; Prompt 31 recorded no sha256 values, so the before values were taken at the start of this step.
- **Deleted to the Bin** (file names only; all under `output/`):
- `output/summary/` (40 files, 9.45 MB, Recycle Bin): company_scope_org_reference.csv, company_scope_registry_backlog_by_sale_company.csv, manual_factsheet_v2.md, manual_factsheet_v2_index.md, part6_inventory_tran_item_coverage.csv, part6_inventory_tran_transtype.csv, partB_calendar_month_qty_by_year.csv, partB_calendar_month_sale_by_year.csv, phase136_explorer2_customer_segment_crosstab.csv, phase136_explorer2_customerid_overlap.csv, phase24_explorerA_forward_direction_fullhistory.csv, phase24_explorerB_disagreement_items.csv, phase24_explorerC_candidate_pairs_diagnostics.csv, phase24_explorerC_duration_by_division.csv, phase24_explorerC_duration_by_type.csv, phase24_explorerC_monthly_output_by_division.csv, phase24_explorerC_monthly_output_by_type.csv, phase24_explorerC_top3_months_by_type.csv, phase24_explorerD_flagged.csv, phase24_explorerD_interval_stats.csv, phase24_explorerD_precision_recall.csv, phaseJ2_explorerA_full_merged_createdate.csv, phaseJ2_explorerA_match_rate_by_year.csv, phaseJ2_explorerA_reverse_conversion_days_createdate.csv, phaseJ2_explorerB_by_customer.csv, phaseJ2_explorerB_by_division.csv, phaseJ2_explorerB_distribution_summary.csv, phaseJ2_explorerB_histogram_diff_forecast.csv, phaseJ2_explorerB_spike_vs_decay_fit.csv, phaseJ2_explorerD_ctvt_fanout.csv, phaseJ2_explorerD_olmjobcode_fanout.csv, phaseJ2_explorerD_row_level_first_check.csv, phaseJ2_explorerD_token_stats.csv, phaseJ3_explorerBOM_16items_component_stock_summary.csv, phaseJ3_explorerBOM_component_stock_agg.csv, phaseJ3_explorerD_per_item_summary.csv, phaseQ23_modeler_report.md, phaseQ23_validator_part2_paired_significance.csv, task6_cube_contract_match.csv, task6_cube_contract_reconciliation.csv
- `output/charts/` (57 files, 18.12 MB, Recycle Bin): m1_1440_PEM101.png, m1_1440_PEM101_bottom_panel_scrolled.png, m1_1440_PEM101_bottom_viewport.png, m1_1440_PEM101_scrolled_bottom.png, m1_1440_PEM101_viewport.png, m1_1440_PEM107.png, m1_1440_PEM107_bottom_panel_scrolled.png, m1_1440_PEM107_bottom_viewport.png, m1_1440_PEM107_scrolled_bottom.png, m1_1440_PEM107_viewport.png, m1_1440_blocked_cdn_PEM101.png, m1_390_PEM101_collapsed_full.png, m1_390_PEM101_collapsed_viewport.png, m1_390_PEM101_expanded_full.png, m1_390_PEM101_scrolled_bottom.png, m1_390_PEM101_viewport.png, m1_390_PEM107_collapsed_full.png, m1_390_PEM107_collapsed_viewport.png, m1_390_PEM107_expanded_full.png, m1_390_PEM107_expanded_viewport.png, m1_390_PEM107_scrolled_bottom.png, m1_390_PEM107_viewport.png, 00_nav_colour_check_index.jpg, 01_notice_and_ontime_charts.jpg, 02_model_chart_legend_isolated_croston.jpg, 03_results_section_division_PEM103_origin7.jpg, 06_forecast_vs_actual_origin7_all_items.jpg, 01_index_sop_plan_tab.png, 02_index_omni_trend_tab.png, 03_index_stock_panel.png, 04_sales_report.png, 05_inventory.png, w2_inventory_PEM101.png, w2_inventory_PEM107.png, w2_manual_tab_full.png, w2_sales_report.png, 01_sop_top.png, 02_sop_badges.png, 03_trend_top.png, 04_manual_gap_line.png, 05_stock_panel_top.png, 06_stock_available_header.png, 07_sales_report_limitations.png, 01_sop_top.png, 02_sop_badges.png, 03_trend_top.png, 04_manual_gap_line.png, 05_stock_panel_top.png, 06_stock_available_header.png, 07_sales_report_significance_block.png, warehouse_stage_dwell_time.png, warehouse_stock_by_stage.png, warehouse_top_transfer_routes.png, inventory_PEM101.png, inventory_PEM107.png, sales_report.png, sales_report_blocked.png
- `output/shots_p12/` (10 files, 0.67 MB, Recycle Bin): desk_assump.png, desk_criteria.png, desk_scored.png, desk_trend.png, desk_trend_c4.png, mob_assump.png, mob_criteria.png, mob_scored.png, mob_trend.png, mob_trend_c4.png
- `output/data/material_pull/` (3 files, 0.21 MB, Recycle Bin): _classification_preview.pkl, _remarks_preview.pkl, _reverify23.pkl
- `output/runs/` (3 files, 0.01 MB, Recycle Bin): step8_tail.txt, task2cfix_visual_check.py, task2cfix_visual_check2.py

### Step 3: temp-folder leak fix
- **Cause (confirmed):** `monthly_refresh_dry_*`: the project copy holds a read-only `forecast` folder that `shutil.rmtree(..., ignore_errors=True)` silently could not remove (reproduced), so each dry run left one folder (117). `db_block_*`: `tests/conftest.py` created the folder and never removed it (43).
- **Fix:** `src/monthly_refresh.py`: new `_remove_tree()` (clears read-only attributes, three tries, warns if the folder remains), used in the `finally` of `run_dry_run_in_sandbox`, plus an `atexit` fallback. `tests/conftest.py`: `_remove_block_dir()` run by `pytest_unconfigure` (after the summary and exit-status check read the log) and by `atexit`.
- **Tests (PASS):** `tests/test_monthly_refresh_dry_run_isolation.py`: no folder after a normal run, after an abort (no run log), after an exception, with a read-only folder in the copy; `tests/test_daily_stock.py::test_the_session_leaves_no_db_block_folder_behind`: a real pytest session in a separate temp root, passing and failing, leaves no `db_block_*`.
- **Leftover temp folders after the full suite:** `db_block_*` 0, `monthly_refresh_dry_*` 0, `page_test_edge_*` 0, no process naming them.

### Step 4: final audit (fresh Validators; read only; problems are REPORTED, not fixed)
**4.1 Consistency: PASS with findings** (high confidence, recomputed). All pages use vintage 2 (run 2026-10-02, fit through 2026-08, targets 2026-09 to 2027-02); the forward-test log holds vintages 1 and 2 (2,340 rows each). Repeated numbers match: late materials on the material plan = executive tab (544); item counts 445 = 335 + 92 + 18 and 439 + 6; Min-Max item counts per division; the Min-Max not-late value is the same in all three places of the page and the plan meta; division percentages equal the CSV. 10 numbers (seed 3210) traced to a source file and function and recomputed: 10 PASS. Findings: (1) the PEM107 alert comes from a 2026-09-28 pull by a script no job runs (`src/investigations/task2b_part4_pem107_alert.py`); the page shows the pull date but no "old" flag (medium); (2) the Trend tab pull (2026-10-08) differs from the sales pages' pull (2026-10-05), low; (3) the operation plan meta records the inventory page build time 09:06 while the page on disk is 12:24, low; (4) DATA_MAP.md:1924 and :1944 still quote the old not-late value (98.34%) and 36 members; the page says 98.24% and 37, low; (5) the price note on the sales report does not say that items with no sale in the last 12 months use their fit-window price, low.
**4.2 Scope: PASS with findings** (medium-high). Monthly and daily SQL carries the Price List restriction and the Omni filter; the approved exceptions (stock, backlog all channels; PEM103 Omni only) carry labels on the pages; no revenue-target content outside the original S&OP tab; no "ERP"; table names read "DB (<table>)". Findings: (1) `order_leadtime.py:68` filters on the DB division column and `delivery_performance.py:61` on the manufacturing division column, against the CONVENTIONS rule (medium; they feed the PEM101 charts); (2) `task2b_part4_pem107_alert.py` pulls every channel and filters to Omni in pandas (low); (3) the executive tab says Price List but not Omni, and the Min-Max page states no general scope (low-medium); (4) `operation_plan.html` has a tooltip "ในตาราง Cube_ItemList ของ DB" (38 times, `src/build_operation_plan_page.py:65`) instead of "DB (Cube_ItemList)" (low).
**4.3 Safety: FAIL** (high on the hits; 385 tracked files scanned; nothing is printed here). Clean: DB host, login, password, user folder, OneDrive path, secrets (7 pattern hits, all false positives). Findings: (1) `data/inventory.json` (tracked) holds about 780 backlog rows each with a customer code and a contract number, and the guard tests do not scan `data/`; (2) tracked reports under `docs/reports/summary/` hold customer codes (3 files), contract numbers (7 files) and customer-name column values (1 file); `docs/` is outside the guard scope; (3) revenue-target numbers remain in tracked files: STATUS.md (2 places), DATA_MAP.md (2), the Prompt reports (many) and one literal in `tests/test_index_w3.py` (medium). The guard tests themselves pass (see 4.6).
**4.4 Rehearsal 2026-11-05 07:00: PASS mechanically on 13 of 13 items; 4 problems** (fresh Validator; real runner code of a temp copy with the clock frozen; faked: the DB answers (saved pulls + fake September actuals and a RevenueType column), the TCP check, the test step 8, push to a local bare repo; 0 blocked database attempts; the real project was unchanged by hash). (1) run-day gate "run" PASS; (2) lock check 07:00:03.8, preflight 07:00:04.2, first login 07:00:06.7, and with a lock file present: exit 3, no preflight, no login, PASS; (3) vintage 3 (run date 2026-11-05, fit to 2026-09, targets 2026-10 to 2027-03, 2,340 rows, fit series saved with verified hash) PASS; (4) September scored for production and shadow (shadow rule: 1 of 3 months scored) PASS; (5) comparator first rows (2,010 rows, vintage 3; windows PEM101 MA12, PEM103 MA6, PEM102/PEM107/CI101 MA3) PASS; (6) has_any_history list printed: 1 code lost its history (EEE-F-FL-5920-353-02600), 0 gained PASS; (7) operation plan uses the fresh backlog pull (RevenueType present, no fallback to the old file) PASS; (8) freshness tags (monthly stamps "Fresh"; daily verdicts are judged by the page script when opened, read not executed) PASS; (9) backup 10 files, sha256 all OK, no incomplete folder, a forced mismatch raised and left nothing PASS; (10) state `last_success_month` 2026-11 PASS; (11) exit code 0 PASS; (12) 2026-11-06 "already done this month", exit 0, no DB activity PASS; (13) 2026-11-07 Saturday "not a run day", exit 0 PASS. **Problems:** (A) a failed gate (the six-month forecast gate, with fake data) held the push for human review, yet the run exited 0 and wrote the success state, so the month counts as done and nothing is retried (code behaviour; the failing value may come from the fake rows); (B) the Trend tab gate compares `round(sum, 1)` with the completeness query and failed twice on a 0.01 difference in fake data (the saved real pull passes), so a spurious abort is possible near a rounding boundary; (C) the backtest MAE gate is "not tested" when no earlier success is in the run logs; (D) the Validator left an empty folder `Git\fake` inside the Git install folder (outside this project; the removal was blocked).
**4.5 Manual versus pages: FAIL** (medium-high). All 29 placeholders resolve; schedule, freshness limits, lead time 45-60, scope counts, recalibration steps match. Mismatches: (1) the manual says the dashboard has 5 parts and has no section for the executive tab, the operation plan or the material plan (high); (2) it says every page shows two times (pulled, built) but the operation plan and material plan show only the pulled time, and the executive and Trend tabs show no pair (medium); (3) the stock panel section does not say Reserved and Available count all channels, nor that PEM103 is Omni only in the plan (low-medium); (4) "data about 2 months behind" sits next to the Trend tab, whose data runs to the current month (low); (5) "PEM103 ผลิตตามงานประมูล" in the reliability table vs scope Omni without tenders (low, page wording not checked); (6) tab names differ slightly (trivial).
**4.6 Suite and dry runs: PASS.** Full suite after the last code change: 846 passed, 0 failed, 0 skipped (18 min 47 s), 0 database connection attempts (4 blocked, all deliberate). Monthly `--dry-run --offline --skip-tests` exit 0; daily `--dry-run --from-pulls` exit 0; `git status` unchanged by the dry runs. Doc-scan tests after this report: see the final answer.
**4.7 Browser: PASS.** Headless Microsoft Edge, temporary profile: index (S&OP, executive, Trend, assumptions, manual tabs), sales report, Min-Max, operation plan, material plan: 0 script errors; the new source wording is shown; the Edge tree was closed by PID, profile deleted, 0 processes and 0 profile folders left.

### Step 5: handover
Added to `STATUS.md`: "Handover (ส่งมอบงาน)" with four parts: 1 what runs automatically (the two scheduled tasks, days, times, outputs), 2 what a person must do and when (2026-11-05, 2026-12-07, 2027-01-05, the 38 codes missing from Cube_ItemList, recalibration and its `--pull` check, DB login refused and the lock file), 3 known limitations, 4 backlog after October (seasonality, external factors, service level and material plan against POs, Prompt 26 row 12, merging duplicate pulls, server migration, cleanup).

### Step 6: scratch folder
Removed after the push; see the final answer (path masked).

### Key figures (source)
- 566 -> 280 items: `list32_final.json`, `val32_decisions.json` (Validator), `list32_validated.json`.
- 6,131,972 bytes permanent, 28,466,734 bytes Recycle Bin, 113 Bin entries: execution result `exec32_result.json` and the Shell Recycle Bin listing.
- 125 protected files, 0 differences: `prot_before.json`, `prot_after.json`.
- 846 passed: the final full run output, `final_tests32.txt`.

### Deviations from the prompt
- Where the rule "nothing references it" conflicted with an explicit DELETE decision, the rule won and the item was kept: `target_data.xlsx` (DATA_MAP.md and STATUS.md name it), `output/data/exec_pull/` (docs name it), `item_movement_types.pkl` (a report names its stem), the 2 dry-run logs (a documented `output/runs/*.log`), the staged run folders (9 of 12 are named by DATA_MAP, STATUS or reports; the Validator marked the other 3 borderline because a document names the `output/runs/<run_id>/staged/` template), and the 42 DELETE-SAFE chart PNGs (their writer scripts or reports name them, so they are referenced).
- The Validators ran after the rate limit stopped them once; both were resumed and finished.

### Need decision
- `D:\sale_forecast_private\target_data.xlsx` (<target> MB) and `output/data/exec_pull/` (2 files): you decided DELETE, but tracked documents name them; delete them anyway (to the Recycle Bin), or keep.
- The 42 DELETE-SAFE PNG charts, the 2 dry-run logs, the 3 staged folders and the 12 `output/data` pulls are named only by writer scripts or prose globs: say whether a writer's own log message or a prose glob counts as a reference.
- <target> findings: whether `data/inventory.json` may keep customer codes and contract numbers (the stock panel needs them), and whether reports may keep customer codes, contract numbers and the target tables.
- 4.4 problem A: whether a held push (a failed gate) should leave the month "not done".

### Found, not done
- The 4.1 to 4.5 problems above (each: small to medium, who: you decide, then Claude Code).
- Empty folder `Git\fake` created by a Validator inside the Git install folder: size 0, you can delete it by hand.
- `%TEMP%\pytest-of-<user>` (about 595 MB): shared by all projects, out of scope as instructed, untouched.


## Prompt 33

Start (Get-Date): 2026-10-15 07:46:29 +07:00. End: 2026-10-15 09:25:19 +0700 (shell clock). No database session, no npm. Counts only in this section: no customer code or name, contract number, target value or login name is written here.

### Step 1: the monthly run must not fail silently
- **Exit codes of `src/monthly_refresh.py`:** 0 completed (or not due); 1 abort or failure; 2 completed with an auxiliary pull that failed or did not rewrite its output; 3 database login refused (lock file written); **4 a real run in which a gate failed** (tests, sensitive-content scan, a change-magnitude gate). Documented in `cli()` and in METRICS.md (note of Prompt 33). Order in `cli()`: not due 0, lock 3, publishing setup 1, abort or failed backup 1, **gate held 4**, partial 2, success 0.
- **What a held gate does:** the run log gets `gates_failed` (gate name and reason) and `push_held`; the monthly success state is **not** written; the command ends with exit code 4; the next weekday start is due again (`monthly_run_due` looks only at the success state), one login attempt per run as before. A dry run (also the sandbox child of a dry run) reports the same in its log and exits 0.
- **Trend tab gate:** `build_trend_tab.trend_total_mismatches()` compares unrounded values with the tolerance of one rounding unit of each figure: rows exactly; qty within 0.0001; sale within 0.01; the sums of the tab's rounded cells within 0.001 (qty) and 0.1 (sale). On the real saved pull the largest difference is float noise (about 2e-7). A missing row or a real amount difference above the tolerance still fails.
- **Tests (fakes only), PASS:** a held gate is named in the run log with its reason (tests gate and a step-10 gate); a held gate gives exit 4, no state, the next weekday is due and a later success writes the state and exits 0; a normal run writes the state and exits 0; a dry run never exits 4; the Trend gate passes at the rounding boundary and fails on a real difference (rows, qty, sale, both item sums). 5 new tests.

### Step 2: customer and target data out of tracked documents
- **Sets (in memory only, nothing written):** customer codes (2,444), customer names (4,345) and contract numbers (53,617) from the saved pulls under output/ and from data/inventory.json; revenue-target sums from the saved aggregate, read before it was recycled (about 56 thousand grouping and subset sums, forms in whole units and in millions).
- **Scope scanned:** every tracked file except index.html, forecast/*.html (the standalone S&OP file included) and data/*.json.
- **Hits replaced by `<customer>`, `<contract>`, `<target>`, per file (counts):** audit_minmax_pem107_season.md contract 2, customer 2; datecol_validator_report.md contract 2; phaseA_a1_forecastdate_revision_findings.md contract 9; phaseA_a2_2025_decline_findings.md customer 17; phaseA_a3_date_keying_findings.md contract 2; phaseA_pem101_conflict_lean.md contract 1; phaseA_synthesis.md customer 7; phaseC_revalidation_report.md contract 1; phaseE0_validator2_cancellations_report.md contract 1; task1_crossdivision_report.md names 10 (two prose mentions and the company-name cells of one division table); totals: customer 26, contract 18, names 10. Targets: DATA_MAP.md 28, STATUS.md 105, this report file 168 (older sections), plus the two literals in tests/test_index_w3.py removed from its "gone" list; 5 residual amounts with a million or billion suffix or a fraction next to a placeholder cleaned afterwards (STATUS.md 2, this report file 3). Totals: target 303 replaced plus 5 cleaned. The surrounding text was kept readable.
- **Also found by extending the guard to docs/:** 3 lines with the Windows login in a path (this report file 1, task2cfix2_validator_report.md 2), replaced by `<user>`.
- **`data/inventory.json`:** the stock panel's backlog pop-up (`invOpenBacklogDetail` in index.html) displays 7 fields of each row: `doc_id` (contract), `job`, `customer`, `quantity`, `status`, `delivery_date`, `plan_delivery_date`. The customer and contract fields are `doc_id` and `customer` (780 rows): **both are displayed, so both are kept** and nothing was removed from the JSON or its generator. `job` holds no identifier. `backlog_from` (the source table, not displayed) is neither a customer nor a contract field and stays. The page renders as before (see the browser check).
- **Guard tests (`tests/test_guards.py`), never skipped:** scope now includes docs/ (all files) and the JSON files of data/ (the three displayed fields of data/inventory.json are blanked before scanning); format checks for customer codes and contract numbers on both; a test that the identifier-holding fields of inventory.json are exactly the displayed ones and that index.html still shows each (if the panel stops showing one, the generator must stop writing it); the exact-match test now runs always (customer names, codes, contract numbers from the saved pulls when present; the format checks alone when absent; the old skip is gone); a target test: a line about the revenue target carries no amount (format, always) and no sum of the saved target aggregate appears (exact, when that file exists). No value, list or hash of values is in the repo.
- **Validator (fresh, evaluate only):** first pass MISMATCH. It found 2 company-name hits that my exact match missed (punctuation variants), 1 target amount with a thousands separator and a million suffix and fractions next to placeholders, and a login-name guard blind spot. The name and amount hits were fixed (above) and the amount format rule now also catches a million or billion suffix; the Validator was not run again. My own rescan after the fixes: exact sets 0, patterns 0, target-format lines 0, login names in docs 0.

### Step 3: target copies
- Sent to the Windows Recycle Bin (restorable): the private workbook copy (one file of about 13 MB) in the folder `sale_forecast_private`, and the folder `output/data/exec_pull/` (2 files, under 9 KB). The private folder was then empty and was removed (yes).
- Before deleting: `git grep` over src, tests, config, pages and data finds no code path that opens either; the only code mention is the optional-existence check in the guard (it returns empty sets when the file is absent).

### Step 4: statements corrected (no new section)
- **Manual:** "ทุกหน้ามี 2 เวลาใต้หัวข้อ (ข้อมูลดึงเมื่อ / หน้าสร้างเมื่อ)" -> "แต่ละหน้าแสดงเวลาไม่เหมือนกัน" with one line per page group: Sales and Min-Max show both times; the stock panel shows one time (the time of the data file, stock and Reserved pulled at different times and with separate "old" tags); the production and material plans show the pull time and the forecast round, no build time; the Trend and executive tabs show only the date or month the sales data run to.
- **Manual, stock panel:** "Available = Inventory ลบ Reserved" -> the same plus: Reserved and Available count orders of all channels (stock is shared), and the production plan of PEM103 uses Omni orders only (without tenders).
- **DATA_MAP.md:** the not-late figure 98.34% -> 98.24% (2026-10-14, after the Omni Channel filter of Prompt 29; was 98.34%), 3 places. Nothing else changed.

### Checks
- **Numeric gate: identical YES.** `git diff` of index.html, forecast/*.html and data/*.json is empty (9 files); a rebuild of the Trend block of index.html from the saved pull with the new gate equals the tracked block (line endings aside).
- **Runner checks (fakes):** monthly dry run `--dry-run --offline --skip-tests` exit 0 (all gates passed, 0 failed); rehearsal with a forced gate failure (tests gate and a step-10 gate) exit 4, no state written, next weekday due (the tests of Step 1); daily dry run `--dry-run --from-pulls` exit 0.
- **Full suite, after the last change:** 855 passed, 0 failed, 0 skipped (16 min 25 s); 0 database connection attempts (4 blocked, all deliberate).
- **Browser (headless Edge, temporary profile):** index.html (S&OP, executive, Trend, assumptions, manual tabs), sales report, Min-Max, operation plan, material plan: 0 script errors on every page and tab. The stock panel (served over http because it loads data/inventory.json) loads with 445 rows and 136 Reserved buttons; the backlog pop-up shows 4 rows (3 orders and the total row) with the contract and customer fields displayed as before; the only console message is the missing favicon (404). Edge tree closed by PID, profile deleted: 0 processes and 0 profile folders left.

### Deviations
- During my own review one customer code appeared once in tool output (the head of a diff of a replaced document) and two Python tracebacks printed the Windows user folder into tool output; none of it was written to a repo file, a report or a commit message.
- The Validator's two-word strings that matched the pulls' name columns (about 190 prose hits) are segment labels (`customer_segment` column), not customer names; they were not replaced.

### Need decision
- The guard's Windows-login check misses doubled backslashes and lowercase `users/` (the two synthetic fixtures in `tests/test_vintage_series.py` slip through); fixing it would flag those fixtures: widen it and rename the fixtures?
- The amount format rule only sees lines with revenue-target phrases and the exact check needs the saved aggregate, now in the Recycle Bin: restore it once to run the exact scan, or accept the format check only?
- The values are still in the git history of the public or shared repo: you deferred a history rewrite.

### Found, not done
- Percentages or differences derived from the targets in lines without a target phrase cannot be detected without the aggregate — small — you decide (restore and scan).
- `DATA_MAP.md:1997` shows the private path with a stray tab character — small — Claude Code.
- The Trend tolerances are fixed and absolute; with more decimals in the stored data they could reject a good run, and they let through a total error of 0.1 baht in the item sums — small — Claude Code.
- The vintage, Trend and executive gates abort instead of failing, so they never reach exit 4 (they end with exit 1); an unreachable GitHub holds the push but still ends with exit 0; `--offline` runs never exit 4 — small — Claude Code.
- Whether the Task Scheduler reads exit code 4: the task definitions were not changed (rule) — small — you.


## Prompt 34

Start (Get-Date): 2026-10-15 09:54:36 +07:00. End: 2026-10-15 11:31:03 +0700 (shell clock). No database session, no npm. Counts only in this section: no customer, contract, target value or login name is written here. Item 9 is not part of this prompt (moved to a later one).

### Items
- **1 Target residue, DONE.** The saved aggregate was restored from the Recycle Bin for the work and the Validator passes and sent back afterwards (it is in the Bin again). Targets were built in memory (about 850 grouping, subset and individual sums in the first scan, about 22 thousand in the Validators' scans; whole baht, millions with 1-2 decimals, billions, with and without separators). Replaced by `<target>`: DATA_MAP.md 5, STATUS.md 47, this report file 194 (24 of them table cells in the two target columns, the rest values and derived percentages in prose), 246 in all. The Validator found more than the set-based scan: target figures of the workbook form (PO Receive, Revenue-Conting, Revenue-Base in MB per type, per division, in totals, their shares and projection-against-target ratios), which are not in the database aggregate; these were redacted by hand-written patterns (one table of 21 rows, about 12 prose lines). Known lines 583, 585, 588, 655 and 845 are clean. Five Validator passes: pass 1 FAIL (3 locations), 2 FAIL (1), 3 FAIL (8, workbook form), 4 FAIL (3), 5 PASS (0 amounts or ratios; 2 borderline shares of cells within a tolerance were redacted as well).
- **2 Old label of the Naive method, DONE.** The old label (written วิธี + ง่าย) had 17 occurrences in 5 tracked files (config 3, assumptions 3, index.html 3, a test 3, the earlier reports 5); now 0 in every tracked file. Replacement "Naive (ใช้ยอดเดือนล่าสุดเป็นยอดทาย)" in the three phrases of the config (source), `data/assumptions.json` and the executive tab and Assumptions tab of index.html. Test `test_the_old_label_for_the_naive_method_appears_nowhere_a_reader_or_the_builders_can_see_it` (pages, manual, manual notes, config, data JSON). No other wording changed.
- **3 Exit codes, DONE.** New `MonthlyGateFailed`: step 2 validation, the leakage guard, the vintage gate, the Trend totals gate (`TrendTotalsMismatch`) and the executive gate (`ExecSummaryError`) raise it; a real run ends with exit code 4, the run log names `failed_step` and the error, no success state. Step 11: GitHub unreachable, a refused add, commit or push, tracked changes outside the generated list, a refused publishing setup, a failing git status or reachability check are all a held push (exit 4, `push_held` in the run log). A held gate or push outranks a failed backup; an abort stays 1; a failed backup alone stays 1; a dry run never exits 4. Tests: every raise site is the gate exception (static check), each gate step (5 paths) names itself in the log and gives exit 4 and no state, only the gate errors of Trend and executive count, every held or failed push (10 variants), a held push ends a real run with exit 4 and no state and a later success writes it, a held gate outranks a failed backup. The test of the previous prompt that expected step 11 outside the publishing clone to raise was updated: it is now a held push (exit 4). The STATUS handover row, the exit-code line and METRICS note were updated.
- **4 Login guard, DONE.** The pattern now catches several separators (doubled backslashes), forward slashes and lower case; the allow-list is compared in lower case; 3 cases added to the made-up-values test. The two synthetic fixtures in `tests/test_vintage_series.py` use a name and a path built from parts (no literal user-path form); one docstring in `src/monthly_refresh.py` that the wider pattern flagged was reworded.
- **5 DATA_MAP path, DONE.** 1 line changed: the stray tab replaced by the backslash, and one sentence added (the folder and its copy of the workbook were removed on 2026-10-15). Nothing else in DATA_MAP.md changed by this item.
- **6 Empty folder in the Git installation folder, DONE.** The empty folder named `fake` (0 entries, created 2026-10-14) was deleted; it no longer exists.
- **7 Manual, DONE.** Three new sections (executive tab, production plan, material plan), each with what it shows, where the data comes from as "DB (<table>)", scope and labels, how to read it; three rows added to the table of parts; "Dashboard นี้มี 5 ส่วน" replaced by a sentence without a number. No typed number in the new sections; 0 unresolved placeholders in the rendered manual. After the first Validator pass: the claim that the production plan refreshes its stock every working day was corrected (the page is rebuilt monthly with the latest daily pull), PEMC and an inferred price sentence removed from the executive section, the Cube_PriceList source added to the material plan, the PEM104 wording of the page used, the typed threshold removed.
- **8 Manual, DONE.** The lag sentence now says the sales page and the Min-Max page lag by the placeholder number of months and the Trend tab uses data up to its last pull date; PEM103 in the reliability table now matches the scope (Omni only, tenders excluded); the tab names in the manual equal the tab bar ("S&OP Plan (เดิม)", "Trend Pricelist Omni ปี 67–69", สรุปผู้บริหาร, แผนการผลิต (จากยอดทาย), แผนวัตถุดิบ).
- **10 Scope lines, DONE.** Executive footer (config, rendered into index.html): "... นับเฉพาะสินค้าใน Price List ช่อง Omni Channel". Min-Max page: one line under the heading (config `inventory_page.scope_line`, in the page data and the page template, rendered by the page): Price List items, Omni Channel, the labelled exception (stock and Reserved count all channels).
- **11 Tooltip, DONE.** "ไม่พบรหัสนี้ใน DB (Cube_ItemList) ตัวเลขในแผนไม่เปลี่ยน" at its source (`src/build_operation_plan_page.py`) and in the page (38 places).
- **12 Sales report price note, DONE.** The chain was verified in `reader_values.unit_prices` (order from config: the last 12 months of the fit window, then the whole fit window, then the Market Price of the Price List). The note now reads: 12-month average with its months; "57 codes with no sale in those 12 months use the average of the whole fit window (ก.พ. 67 to ส.ค. 69)"; "1 code with no sale in the fit window uses the List price". Counts come from the builder (`fit_items`, `market_items`). Test of the chain and of the page text.
- **13 Plan meta time, DONE.** `operation_plan.read_outputs` now returns the meta with `page.built_at` taken from the page itself (its embedded `page_built_at`) and keeps the recorded value as `built_at_recorded`; the hash-checked meta file on disk is not edited. Test with a rebuilt page (12:24 against a recorded 09:06) and a test that the recorded plan read back equals the page on disk.

### Numeric gate
Identical YES, except the intended change of item 12 (the price note adds the numbers 12, 69, 57, 67: the 12 months, the end of the fit window, the count of codes and its start). Method: numeric tokens of the visible text and embedded data of every page and data JSON in HEAD against the working tree (index.html, sales report, Min-Max, operation plan, material plan, assumptions, inventory, stock_daily): removed 0 everywhere; added 0 everywhere except the sales report (5 tokens, all in that note). Item 13's time stamp is in an untracked meta file, not on a page.

### Data gate
Forward-test, shadow, score and comparator logs, the vintage snapshot and the other protected files were not touched (no job ran, no pull). `data/assumptions.json` changed only by item 2 (3 lines of text); items 7 and 8 added no manual value.

### Runner checks (fakes, no database)
Monthly dry run `--dry-run --offline --skip-tests`: exit 0. Forced gate failure (each of 5 gate steps and the tests gate, a real run with fakes): exit 4, no success state. Forced push failure (GitHub unreachable, refused push, refused commit, refused publishing setup): exit 4, no state. Daily dry run `--dry-run --from-pulls`: exit 0. The forced cases are the tests of item 3.

### Full suite
871 passed, 0 failed, 0 skipped (17 min 59 s); 0 database connection attempts (4 blocked, all deliberate). It was run after the last code change; later changes were documents only (item 1 placeholders), which the document-scanning tests re-ran. Temp folders left after the suite: `db_block_*` 0, `monthly_refresh_dry_*` 0.

### Browser check (headless Edge, temporary profile, pages served over http)
0 script errors on index.html (S&OP, executive, Trend, assumptions and manual tabs), sales report, Min-Max, operation plan, material plan; the only console message is the missing favicon. Item 2: the executive and Assumptions tabs show the new Naive text, the old label 0. Item 7: the manual headings include the three new sections. Item 8: tab names, PEM103 row and lag sentence as intended. Item 10: the executive footer names Omni Channel; the Min-Max page shows its scope line. Item 11: 38 tooltips with the new text. Item 12: the note shows the three parts. Edge tree closed by PID, profile deleted, 0 processes and 0 profile folders left.

### Validator
5 passes for item 1 (the last PASS); pass 1 also PASS on items 2, 4, 5, 6, FAIL on item 3 (3 residual exit paths, fixed) and on one manual claim (fixed); pass 2 PASS on items 2, 3 and 7/8; the passes were resumed once after a rate limit. Passes needed because each Validator found further workbook-form residue of item 1.

### Backlog lines added to STATUS.md (nothing fixed)
- Other aborts of the monthly run (exit 1) may need to become gates.
- The executive card and the criteria table word the Naive method differently.
- The Min-Max page carries one scope line; PEM103's Omni-only rule is on the production plan page only.

### Deviations
- The saved target aggregate was kept restored until the last Validator pass (it is needed to scan), then sent back to the Recycle Bin.
- Item 1 also covered figures of the target workbook, which are not in the database aggregate.


## Prompt 35

Start (Get-Date): 2026-10-15 11:40:15 +07:00. End: 2026-10-15 12:43:47 +0700 (shell clock). Database: read only, preflight first, one session, one login attempt, 54 statements, all plain SELECT (checked by the driver before each statement; 0 others). The lock file was absent. No target value, customer or contract is written here.

### Step 0: source table (made before the pull)
Rule (fixed): a source may be refreshed now only if (a) it is not used to fit the forecast or to score the forward test or shadow, (b) it is not an input of the Min-Max recalibration or of the class and policy assignment, (c) it describes current state or display-only history: stock, reserved and backlog, BOM, item master, open POs, the Trend tab history, the PEM107 alert. Cadence follows config page_timestamps (monthly job or daily job). "Already current" = refreshed by its own job; no extra pull was needed.

| page / section | DB table(s) | local file | pull date before | cadence | refresh now | rule clause |
|---|---|---|---|---|---|---|
| Sales report: main data range, series for the forecast | cube_Sale_APD | output/data/processed_all_divisions_monthly_qty.csv, processed_all_divisions_monthly_sale.csv, raw_all_divisions_sales.csv | 2026-10-05 07:41 | monthly | NO | (a) fits the forecast, waits for 2026-11-05 |
| Sales report: results per division, rolling origin, MAE of the basic models, forecast against actual | cube_Sale_APD (actuals), forward-test log | output/summary/forward_test_*, phaseC_step2_* | 2026-10-05 | monthly | NO | (a) scores the forward test |
| Sales report: forward forecast table and price note | forward-test log vintage 2, cube_Sale_APD prices, Price List | output/summary/forward_test_log_all_divisions.csv | vintage 2 (2026-10-02) | monthly | NO | (a) |
| Sales report: notice-time and delivery charts (on time, same day) | Cube_CES | output/data/raw_cube_ces_delivery_128items.csv, raw_order_leadtime_128items.csv, output/summary/delivery_* and leadtime_* | 2026-10-05 07:42 | monthly | NO | not in the list of clause (c); the same delivery history feeds the observed not-late of the recalibration, clause (b) |
| Executive tab: year-to-date sales, full-year projection, accuracy, tracking signal | cube_Sale_APD, forward-test log | the same series and logs as above | 2026-10-05 | monthly | NO | (a) |
| Executive tab: watch-outs (production above peak, late materials, PEM107 alert) | none of its own: follows the operation plan, the material plan and the PEM107 alert | their files | follows rows below | follows them | rebuilt, not pulled | follows the rows below |
| Trend tab | cube_Sale_APD (Omni, Price List codes) | output/data/trend_pull/daily.csv, names.csv, completeness.json | 2026-10-08 17:25 | monthly | YES | (c) the Trend tab history |
| Stock panel (index) | Cube_Inventory_Exact, Cube_CES (Backlog, all channels) | data/inventory.json, data/stock_daily.json (from output/data/daily_stock_pull) | published 2026-10-14 08:00 (the 08:00 run of the 15th saved its pulls but failed to build; the 12:00 run published) | daily | already current by the daily job; no extra pull | (c) stock, reserved |
| Min-Max page: stock and reserved (all divisions) | Cube_Inventory_Exact, Cube_CES | latest daily snapshot output/snapshots/inventory_daily_*.csv and data/stock_daily.json | 2026-10-14 08:00 | daily | already current by the daily job; page rebuilt from the latest snapshot | (c) |
| Min-Max page: PEM103 and PEM107 sales (their Min/Max demand) | cube_Sale_APD | output/data/raw_all_divisions_sales.csv | 2026-10-05 07:41 | monthly | NO | (a) and (b): an input of their policy |
| Min-Max page: PEM101 curves, calibration, observed not-late (ces_92, inventory_92) | Cube_CES, Cube_Inventory_Exact | output/data/lead_time_inputs/*, output/summary/week1_recal_*, maxmin_v1_* | 2026-10-05 | manual (recalibration) | NO | (b) |
| Min-Max page: lead times and assembly (lead_time_v1) | Cube_PO_Exact, Cube_ReceiveRM, Cube_PriceList, production orders, cube_final, Cube_BOM_Exact | output/data/lead_time_inputs/* | 2026-10-05 | manual | NO | (b) a policy input; not in the list of clause (c) |
| Min-Max page: PEM107 delivery alert | Cube_CES (Omni) | output/summary/task2b_part4_pem107_alert.json, _items.csv | 2026-09-28 12:43 (a one-off script) | now monthly (step 1) | YES | (c) the PEM107 alert |
| Operation plan: stock | Cube_Inventory_Exact | output/data/daily_stock_pull/inventory.pkl | 2026-10-14 08:00 (used) | daily | already current; rebuilt with the latest daily pull (2026-10-15 12:00) | (c) |
| Operation plan: backlog (orders on the books, with RevenueType) | Cube_CES (Status Backlog, all channels) | output/data/daily_stock_pull/backlog_ces.pkl (latest of the daily and monthly pulls) | used 2026-10-14 08:00 plus a PEM103 fallback from the class-evidence copy of 2026-10-06 | daily | rebuilt from the daily pull; the class-evidence copy is no longer read | (c) and the instruction: backlog comes from the daily pull |
| Operation plan: forecast (vintage 2) | forward-test log | output/summary/forward_test_log_all_divisions.csv | 2026-10-02 | monthly | NO | (a) |
| Operation plan: class and policy per item | cube_Sale_APD, Cube_CES, cube_final, Cube_Inventory_Exact, Cube_BOM_Exact (class evidence) | output/summary/task2b_part2_item_level.csv, output/data/material_pull/class_evidence.pkl | 2026-10-06 14:52 | monthly | NO | (b) class evidence |
| Operation plan: production history, peak, week 2 inputs | cube_final, production orders | output/data/week2_inputs/* | 2026-10-06 | one-off | NO | (b) the cube_final history belongs to the class evidence and the lead-time inputs |
| Operation plan: item master remark "not found in DB (Cube_ItemList)" | Cube_ItemList, Cube_Inventory_Aging | output/data/material_pull/item_attributes.pkl (and a legacy file of 2026-10-09) | 2026-10-09 | monthly | YES | (c) item master |
| Material plan: BOM tree, raw-material stock, open POs, PO and receipt history, price list, item names | Cube_BOM_Exact, Cube_Inventory_Exact, Cube_tobe_received, Cube_PO_Exact, Cube_ReceiveRM, Cube_PriceList, Cube_ItemList | output/data/material_pull/material_inputs.pkl | 2026-10-06 14:49 | monthly | YES | (c) BOM, stock, open POs, item master; the PO history, receipts and price list only serve this plan's purchase evidence (the Min-Max lead times read the lead_time_inputs files) |
| Material plan: backlog copy inside the bundle (class-evidence Cube_CES) | Cube_CES | the same pickle, keys backlog_ces and backlog_pulled_at_local | 2026-10-06 14:49 | monthly | NO (kept) | (b) class evidence; read only for the operation plan's old PEM103 fallback |
| Assumptions tab | none (derived) | data/assumptions.json | built 2026-10-14 | follows the recalibration | NO | (b) |
| Manual tab, original S&OP tab | none (static text) | docs/user_manual.md, the original tab | - | - | NO | not data |

Never refreshed: the sales and actuals of the forecast and of the executive YTD, the forward-test, shadow, score and comparator logs and the vintage snapshot, the recalibration inputs, the class-evidence pull.

### Step 1: the PEM107 alert is production code
- **Where:** `src/cube_ces_pull.py` (`compute_pem107_alert`, `pem107_pricelist_rows`, `pull_pem107_alert`, command `python src/cube_ces_pull.py --pem107-alert`); no new file. Omni Channel is in the SQL (`RevenueType = 'Omni Channel'`, no date filter, no customer column); through `db.py`; one session (`in_open_session` when the caller holds it). The output JSON carries `data_pulled_at`; the Min-Max page tags it old by the monthly cadence (new source label in config page_timestamps, `freshness.cadence.pem107_alert`, and the page script).
- **Monthly runner:** a pull stage of step 1 (`_pull_stage("PEM107 alert pull", "cube_ces_pull.py", ..., ["--pem107-alert"])`): a failure keeps the earlier alert, is a WARN and the run is partial (exit code 2); the offline dry run reports the stage.
- **Investigation script** `src/investigations/task2b_part4_pem107_alert.py` now only calls the production function (no copy of the logic).
- **Also for the one-session refresh:** `build_trend_tab.pull(in_open_session=True)` and `material_plan.pull_inputs_only` (material inputs and item attributes only; no Cube_CES, class evidence and class file untouched, bundle backlog kept).
- **Tests (fakes), PASS:** the alert numbers from fake delivered rows (Omni only, window start, delivered only); the pull takes Omni in the SQL, uses the open session, writes dated files; the investigation script holds no copy; step 1 has the stage and the offline dry run reports it; a failed PEM107 pull is a WARN, partial, exit 2; the freshness cadence; the inputs-only pull leaves the class evidence and the bundle backlog alone.

### Step 2: the pull (one session, 11:48 to 11:52)
Preflight, lock file check, one login attempt, 54 SELECT statements. Rows before → after:
- Trend tab history: daily rows 22,796 → 22,891; item-name rows 387 → 387; rows in scope 38,298 → 38,498; data through 2026-10-08 → 2026-10-14; pulled 2026-10-08 17:25 → 2026-10-15 11:48.
- Material plan inputs: BOM tree 25,710 → 25,849; raw-material stock 18,583 → 18,656; open orders 524 → 483; PO lines 36,262 → 36,488; receipts 49,722 → 50,007; price list 7,440 → 7,463; item names 4,844 → 4,863; pulled 2026-10-06 14:49 → 2026-10-15 11:48. Bundle backlog (class-evidence copy) 873 → 873, kept.
- Item attributes: item master 2,268 → 5,261 rows, aging 61,041 → 100,066 rows (the new pull asks for the plan items and every BOM component); pulled 2026-10-09 → 2026-10-15.
- PEM107 alert: Cube_CES rows 21,610 (every channel, filtered later in pandas) → 12,002 (Omni in the SQL); alert items 71 → 73; pulled 2026-09-28 12:43 → 2026-10-15 11:51.
Not pulled: the stock and backlog (the daily job pulled them at 08:00 and at 12:00; the rebuild used the 12:00 pull after the daily job had published it), every NO row.

### Step 3: pages rebuilt (vintage 2, no recalibration; the sales report and every log untouched)
Order: Trend tab, Min-Max page from the latest daily snapshot, operation plan and page, material plan and page, vintage gate, executive tab. Key numbers before → after:
- **Trend tab:** data through 2026-10-08 → 2026-10-14 (note shows the pull date 8 → 15 Oct); rows 38,298 → 38,498; units 3,630,615 → 3,648,800; the totals gate passed.
- **Min-Max page:** embedded data identical except the PEM107 alert, the build time and the freshness block: alert pulled 2026-09-28 12:43 → 2026-10-15 11:51; not-late before 1 May 87.1% (n 41,495) → unchanged; from 1 May 57.7% → 58.5%; units from 1 May 2,702 → 2,888; items in the alert 71 → 73; page built 2026-10-14 12:24 → 2026-10-15 12:02. Stock figures come from `data/stock_daily.json` at run time (2026-10-14 08:00 → 2026-10-15 12:00 after the daily job's commit was pulled). No Min or Max changed.
- **Operation plan:** stock and backlog pull 2026-10-14 08:00 → 2026-10-15 12:00; PEM103 backlog fallback from the 2026-10-06 class-evidence copy → none (the daily pull carries RevenueType; the fallback note is gone); orders dropped by the Omni scope 1 → 2; item-months with backlog above the forecast 94 → 98; items 439 → 439; items with Min/Max by division unchanged; plan meta page build time 09:06 → 12:02, equal to the page.
- **Material plan:** raw-material stock pulled 6 Oct 14:49 → 15 Oct 11:48; order within the window: 158 → 186 lines (155 → 177 counted); late to order: 596 → 543 lines (544 → 498 counted); stock and open orders: 2,244 → 2,252 (2,110 → 2,116); items in the plan 439, costed 300, not costed 139: unchanged.
- **Executive tab:** the four cards (year-to-date sales, projection, accuracy, watch-outs count) identical; watch-outs: PEM103 above the historical peak 119.9% → 103.2%, PEM102 244.9% → 201.5%, late materials 544 → 498 (equal to the material page), PEM107 57.7% → 58.5% (equal to the Min-Max alert); the other four lines unchanged.

### Step 4
The two target totals in the test sentence near line 1615 of this file were replaced by `<target>`: YES.

### Integrity
- Forward-test, shadow, score and comparator logs, their metadata, the vintage snapshot and series, the archive, the state file, the class evidence, the item-level class file, the lead-time and recalibration inputs, the series of the forecast, the sales report and the assumptions file: 97 files, sha256 before and after identical: YES.
- Vintage 2 on every page: YES (Min-Max data, operation plan meta, material plan header "plan round Oct", sales report unchanged).
- Policies unchanged: YES (the Min-Max embedded data has no policy difference; plan counts per class and Min/Max items per division identical; the class files unchanged by hash).
- Forecast and executive year-to-date unchanged: YES (cards identical, sales report and series unchanged by hash).

### Consistency
YES: late materials 498 on the material plan = 498 on the executive tab; PEM103 and PEM102 above-peak percentages on the executive tab equal the operation plan's division table; PEM107 not-late 58.5% on the executive tab = the Min-Max alert; the operation plan meta build time of the Min-Max page equals that page; items 439 and costed 300 agree on both plans.

### Freshness tags (cadence rule)
Refreshed sources show as new: the PEM107 alert (pulled 15 Oct, no old tag), the Trend tab, the material stock, the stock and backlog (15 Oct 12:00). Monthly sources not refreshed (pulled 5 Oct) are correct for the 2026-10-05 run: 0 "old" notices on any page. One remark still shows the older date: the item-master line of the operation plan (see backlog).

### Runner checks (fakes only)
Monthly dry run `--dry-run --offline --skip-tests`: exit 0 and the run log carries the PEM107 stage; forced PEM107 pull failure (a real run with fakes): partial, one WARN, exit 2, no success state; daily dry run `--dry-run --from-pulls`: exit 0.

### Full suite, browser check, Validator
Full suite after the last change: 878 passed, 0 failed, 0 skipped (15 min 49 s); 0 database connection attempts (4 blocked, all deliberate). The first full run had 4 failures, all fixed: two tests that list the scripts of step 1 now include the PEM107 stage, and `data/assumptions.json` was regenerated by its builder because the Trend refresh moves the manual value "trend data through" (8 -> 14 Oct 69; the 10 build-date stamps of its rows changed to 2026-10-15 as the builder writes them). Browser check (headless Edge, temporary profile, pages over http): 0 script errors on index.html (S&OP, executive, Trend, assumptions, manual tabs, stock panel with 445 rows dated 15 Oct 12:00), sales report, Min-Max (the PEM107 view shows the alert pulled 15 Oct 11:51 with no old tag, headline 87.1% -> 58.5% on 2,888 units), operation plan (stock line 15 Oct 12:00, no PEM103 fallback note), material plan (stock pulled 15 Oct 11:48, 498 late lines); 0 stale notices on any page; the only console message is the missing favicon; Edge tree closed by PID, profile deleted, 0 processes and 0 profile folders left. Validator (fresh, evaluate only, after the rebuild, 1 run): PASS on C1 source table against the rule (no forbidden source refreshed: 97 protected files identical by sha256, mtimes checked for the rest; the refreshed files are exactly the YES ones; refresh driver: preflight, lock check, one session, one login, SELECT-only guard), C2 integrity, C3 consistency, C4 PEM107 integration; its notes: the monthly job's PEM107 stage is its own session (one more login per monthly run), the item-master remark keeps the older date (backlog line), the report placeholders (filled now).

### Notes
- The daily job of 08:00 on 15 Oct saved its pulls but failed in its build stage with an access error (a child python process could not be started); the 12:00 run succeeded and published, so the pages were rebuilt after it.
- Anything else noticed is in the STATUS.md handover backlog (3 lines); nothing else was fixed.
