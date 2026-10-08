# Prompt 5 -- G2 on the latest vintage, PEM101 Min/Max basis, G3-only items, test inputs, target_data.xlsx

Checked 2026-10-08 (clock 08:09 to about 11:30, this machine). Decisions of the user, 2026-10-08: D1 track the class-decision test inputs; D2 rebuild G2 from the latest log vintage and keep it in step every month; `target_data.xlsx`, sheet "TargetC1005 12-06-2029", is the latest target version (user's statement, not verified here). Figures come from computations run in this task by the implementer or by independent agents (Modeler, Explorer, Validator) working read-only from the repository and the saved files; their scripts and result files are in %TEMP% (`g2bak`, `valG2`, `p3_minmax`, `p4_trace`), outside the repository. CONFIRMED = computed now; INFERRED = a reading, with its confidence.

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
