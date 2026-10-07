# Week 4, prompt 4 -- end-to-end check G1 -> G2 -> G3 -> material plan, target_data.xlsx, the scheduled daily runs

Checked 2026-10-07 (clock 14:12 to about 15:30, this machine). Assessment only: no forecast, Min/Max, operation plan or material plan figure and no page was changed. No database connection. The checks were run by an Analyst and recomputed independently by a Validator that did not see the Analyst's numbers; both worked from the repository and the saved files, read the pages in their own headless browser (own profile, own PID, closed by PID, profile deleted) and wrote only under %TEMP%. Every figure below comes from a computation run in this task; their scripts and result files are in %TEMP% (`e2e_work`, `e2e_val`), outside the repository. Claims are CONFIRMED (computed now) unless marked INFERRED.

Stages: **G1** forecast page `forecast/sales_report.html`; **G2** Max-Min page `forecast/inventory.html`; **G3** operation plan `forecast/operation_plan.html`; **M** material plan `forecast/material_plan.html`; plus `index.html`. Divisions: PEM101, PEM103, PEM107, PEM102, PEM104 (the sixth in the operation plan's list, config `operation_plan.divisions`), CI101.

## a. Vintage

| Stage | Vintage | Forecast run | Data cutoff / fit | Target months |
|---|---|---|---|---|
| Log, vintage 1 | 1 | 2026-09-07 | pull 2026-09-07; fit to 2026-07 | 2026-08 to 2027-01 |
| Log, vintage 2 (latest) | 2 | 2026-10-02 | pull 2026-10-02; fit 2024-02 to 2026-08 | 2026-09 to 2027-02 |
| G1 page | none stated | not stated | data pulled 2026-10-05 07:41; "usable range" to 2026-07; backtest test months 2025-03 to 2026-08 | no forward forecast shown |
| G2 page | none stated; its embedded forecast equals **vintage 1** | not stated | calibration run 2026-10-05; stock file pulled 2026-10-07 08:00 | 10 flat months, no labels |
| G3 page and files | 2 | 2026-10-02 | plan built 2026-10-06 16:08, stock pull 2026-10-06 12:00 | 2026-10 to 2027-02 |
| M page and files | 2 (through G3) | 2026-10-02 | built 2026-10-07 07:39, raw-material stock pulled 2026-10-06 14:49 | 2026-10 to 2027-02 |

- **G2 is on a different vintage from G3 and M.** 274 of 274 G2 items with a forecast equal vintage 1 (within 0.001); only 8 or 9 equal vintage 2 (coincidences). The same for PEM101, PEM103 and PEM107; CI101, PEM102 and PEM104 have no G2 stage, so for them G1, G3 and M share vintage 2 (YES).
- G1's own page labels the data edge two ways: "usable range" to 2026-07 (read from the older pilot series, max month 2026-07) and a backtest to 2026-08 (the all-division series). INFERRED (medium): from `build_report.py`.
- Stock pulls differ by stage by design (G3 opens from the 2026-10-06 12:00 pull, G2 loads the 2026-10-07 08:00 stock file; 48 of the 92 PEM101 stock items differ between them); each page labels its own pull time.
- Backend text is stale in one place: the material plan's recorded meta says "stock of in-house sub-assemblies is not netted" while the same meta says it is (`subassembly_stock_netted`); the plan reproduces with netting. Not shown on any page.

## b. Item sets per division

| Division | G1 forecast / placeholder / excluded | G2 with a policy | G2 Min/Max | G3 items / counted / with Min-Max | Material plan: exploded (counted, quantity above 0) |
|---|---|---|---|---|---|
| PEM101 | 144 / 21 / 6 | 144 | 92 (calibrated table), 77 (standard-assumption table) | 165 / 159 / 92 | 116 |
| PEM103 | 50 / 37 / 0 | 50 | 0 | 87 / 51 / 0 | 45 |
| PEM107 | 112 / 24 / 0 | 112 | 4 | 136 / 128 / 4 | 113 |
| PEM102 | 16 / 10 / 0 | none (division closed) | none | 26 / 22 / 0 | 16 (15 expand, 1 has no BOM) |
| PEM104 | 0 / 0 / 12 | none | none | 12 / 12 / 0 | 0 |
| CI101 | 13 / 0 / 0 | none | none | 13 / 12 / 0 | 12 |

G3 holds 439 of the 445 price-list items (the other 6 are PEM101 never-sold items, listed by code on G2). The Analyst counted 300 exploded items (own plan quantity above 0), the Validator 302 (two more, HS-F-99-0303 and VT-F-99-010306, have no quantity of their own and are exploded through their parents); the difference is the definition, the PEM101 and PEM107 cells above are the Validator's.

**Drops with a reason shown on a page:** PEM101's 6 never-sold items (on G2 by code; on G3 as a count with the reason); the 55 G3 items "not counted" (PEM101 6, PEM103 36, PEM107 8, PEM102 4, CI101 1; every row carries "ไม่พบการผลิตในระบบ"); PEM101 non-stock items (G2 class table).

**Drops with NO item-level reason shown on the page:**
1. G1 to G2, divisions not open on G2: CI101 13 items, PEM102 26 (16 forecast, 10 placeholder), PEM104 12 excluded. G2 gives a division-level notice with counts, no codes.
2. G1 chart: 30 PEM101 forecast items are not in the 114-item chart and the other divisions' items are not listed; the page says only that the chart is the PEM101 pilot.
3. G2 contradicts G1 and G3 for **32 PEM101 items**: their embedded G2 forecast is empty and the page lists them under "items with stock but no forecast" while the log and G3 hold a nonzero forecast for all 32 (15 are stock-policy items and are missing from the standard-assumption table). The G2 table "items with stock but no forecast" also lists items that do have a forecast (35 of its 67 PEM101 rows, 48 of 50 in PEM103, 108 of 108 in PEM107): it is built from items without a computed Min and Max.
4. G3 to the material plan: the material page states nothing about finished items left out. **138 items** (PEM101 49, PEM103 42, PEM107 23, PEM102 11, PEM104 12, CI101 1): 55 not counted, 82 counted with zero quantity in all five months (PEM101 43, PEM102 6, PEM103 6, PEM104 12, PEM107 15), 1 with a quantity and no BOM (02-05-R-0004, PEM102). PEM104 contributes no item yet the page lists PEM104 as included. G3 names no code for the 6 never-sold PEM101 items.

## c. Demand and requirement

**Same quantity, different value:**
- **M1. G2 demand differs from G3 demand.** 1,325 (Analyst, against G3) to 1,330 (Validator) of 1,370 item-months, 265 to 266 of 274 items (PEM101 560 item-months, PEM103 245, PEM107 520 to 525); median relative difference 6 to 11 percent; largest 912.0 units a month (EEE-F-FC-1040010002: 1,614.7 on G2 against 2,526.8 in G1 and G3). Cause: G2 is vintage 1 (see a). Consequence: PEM107's four Min/Max values come from a vintage 1 forecast while G3's demand for them is vintage 2. Belongs to the G2 Min/Max data build (week 1 Max-Min v1 builder `build_inventory_page_data.py`), consumed by the week 2 operation plan.
- **M2. PEM101's Min/Max basis is not G3's demand.** The calibrated section is r x mean daily history demand (`maxmin_v1.py`), not the forecast: Min divided by G3's monthly forecast ranges 0.36 to 5.70 (median 0.65). INFERRED from code (medium); the numbers are computed.
- **M3. G1 shows no forward forecast** (only backtest forecasts); 0 of 672 backtest values equal any vintage value, so nothing of the same quantity can be compared on the page.

**Explained by the documented method (not mismatches):** G3 forecast = log vintage 2 on all 1,675 forecast-status item-months (0 differences); the other 520 rows (placeholder and PEM104) have forecast 0 and demand from backlog; backlog due recomputed from the saved pulls (2,195 item-months, 0 differences); demand = max(forecast, backlog) on 2,195 of 2,195 rows; the Min/Max loop re-run on 480 stock-item rows (0 differences in planned production and closing); load = demand on 1,715 rows (0); PEM101 Min/Max re-interpolated from the calibrated grid at the default preset (92 items, 0 differences). **Material requirement:** two independent explosions (Analyst's, Validator's) of G3's production quantity through the BOM (hour lines excluded; sub-assembly stock netted; no netting for a plan item with a Min and Max) reproduce `material_plan_v1_material_month.csv` on all 11,220 material-months (gross; the Analyst also net and order dates) with 0 differences (largest 5e-7). Reading the written Sec.43 literally (a component with a purchase record is purchased, even a plan item) gives 828 differing material-months over 168 materials: two counted plan items with receipts, TF-F-99-15044211Q1 and VT-F-99-010202, are expanded by the build; Sec.43 now says so. Never netting plan items would change 133 materials (609 rows); no netting anywhere 688.

**Correction of an earlier statement.** The week 4 prompt 3 entry (STATUS.md, METRICS.md Sec.43, DATA_MAP.md) said none of the 11 counted plan items that are BOM components has a Min and Max. The Validator found that HS-F-99-0303 has one (computed again here: planned production on all 5 months, class stock_policy, stock 0 in the 12 warehouses), so ten are netted and it is not; no figure changes because its stock is 0. Corrected in the three documents.

**Page-internal contradiction (P1, G3):** 7 items labelled "ไม่พบการผลิตในระบบ" show quantities in 33 cells of their item rows (PEM101 FC-A-27-00202; CI101 DS-F-99-0320; PEM103 TF-F-99-10074211AB1, TF-F-99-12044211AB1, TF-F-99-12074211AB1, TF-F-99-2107223B1, TF-F-99-3104223B1). The division totals and the material plan correctly exclude them (the page rule is planned production, else load, counted or not). Belongs to the week 3 page builder.

## d. Page against backend

| Page | How | Result |
|---|---|---|
| G1 | scope, primary and per-division tables against embedded data and the log; chart: all 114 items x 7 origins, 1,596 traces | page = backend, 0 differences; the page cannot show a vintage |
| G2 | three open divisions: curve table (92), standard-assumption tables (77 + 4), on-hand rows against the plan file, stock file and reference engine | page = backend, 0 differences (2 cells differ by display rounding); the defects above are in what the backend holds |
| G3 | all 439 rows x (stock, Min, Max, 5 months) = 3,512 cells; 30 division-month rows; the two first-month sentences; file hashes (5 of 5) | page = file except P1 |
| M | all 2,244 rows x 12 cells; the 150-row and 598-row lists with dates, quantities, lead time, source, flags | page = file; 248 to 265 net cells differ, all "-" for materials flagged for a missing or unlike purchase unit (the documented rule); both lists reproduce, 0 differences |
| index.html | four tabs, links, item table | links go to the operation plan, forecast and Max-Min pages only (**no link to the material plan**); tab 1 is the old one-off S&OP file labelled not for decisions; the item table (426 rows, 413 in G3, no CI101 group) uses formula Min/Max, 1 of 94 compared items equal to G3's, and shares no vintage with G1, G2 or G3 |

The G2 "reference engine" and plan-versus-page comparisons use the repository's own code: they show the recorded data equals what the code gives now, not that the method is right.

## Findings, by phase (not fixed here)

| Finding | Phase | Priority |
|---|---|---|
| G2 forecast is vintage 1, G3 and M vintage 2; feeds PEM107 Min/Max (M1) | week 4/5, G2 page data build | high |
| 32 PEM101 items show "no forecast" on G2 though G1/G3 hold a forecast; the "items with stock but no forecast" table lists items with a forecast | week 4/5, G2 page | high |
| G1 page states no vintage, run date or target months and shows no forward forecast; its two data-edge labels disagree | week 5, G1 page | medium |
| Material page: no statement for 138 omitted finished items; PEM104 listed as included though nothing is exploded; no link to it from index.html | week 4/5, material page and index | medium |
| 51 items of closed divisions have no item-level reason on G2 (counts only) | week 5, G2 page | low |
| P1: 7 items labelled "no production" show quantities on G3 | week 3 page builder, next page task | low |
| PEM101 Min/Max basis is history, not forecast (M2) | design note for the user | medium |
| Material meta text says sub-assembly stock is not netted | next material plan change | low |
| Tests write "skipped" daily logs into the shared run-log folder (two on 2026-10-06, 16:27 and 16:28) | test hygiene, week 5 | low |

## Part 4. target_data.xlsx

**NOT FOUND.** Folders checked: all of `D:\sale_forecast` (including `reference/`, `output/`, `data/`, `docs/`, `config/`, `src/`, `tests/`) and `D:\sale_forecast_publish` (its `output/` and `reference/` are junctions into the first, so the same files). A search for any file whose name contains "target" and "data" found nothing; `reference/` holds `pricelist.xlsx` only.

## Part 5. The daily stock job from the publishing clone

Evidence: Task Scheduler event log (last result, start and finish events), the job's run logs under `output/runs/daily/`, `git log` of `data/stock_daily.json`, and the pages rendered in a headless browser from the committed tree (equal to origin/main for these files).

| Run | Result | Evidence |
|---|---|---|
| 2026-10-06 08:00 | **RAN NOT PUBLISHED** | task ran 08:00:01 to 08:00:54, exit code 2147942401; log: failed at "tracked files clean" (working tree modified), 4 gates passed, nothing committed |
| 2026-10-06 12:00 | **RAN NOT PUBLISHED** | 12:00:00 to 12:00:51, same exit code; same stop |
| 2026-10-07 08:00 | **PUBLISHED** | the task now runs from the clone (started 08:00:01 as cmd, finished 08:00:56, exit code 0); log status published, commit 814a80f ("Daily stock refresh, pulled 2026-10-07 08:00:43") pushed, touching `data/inventory.json` and `data/stock_daily.json` |
| 2026-10-07 12:00 | **RAN NOT PUBLISHED** (by design) | 12:00:01 to 12:00:09, exit code 0; log status `skipped_success_exists_today` (a successful run of today exists), no database connection, no commit |

(The 2026-10-06 stock data was published by a manual run from the clone at 16:25, commit 9bcf00b, not by a scheduled run.) Published pages: `index.html` shows "ข้อมูล stock ในระบบ ณ 6 ต.ค. 69 21:41" (the source table's load time, equal to `stock_source_load_time` of the 2026-10-07 08:00 run) and `forecast/inventory.html` shows the same source time and "ดึงข้อมูลเมื่อ 7 ต.ค. 69 08:00" (the 08:00 run's pull time, equal to `pull_time` in the published file). `index.html` shows the source load time only, not the pull time.
