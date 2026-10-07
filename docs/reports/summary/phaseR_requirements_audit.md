# Phase R -- requirements audit against the original brief (2026-10-02)

> **Correction, 2026-10-02:** the row for brief item 2 and the Part 2 wording below rest on a wrong reading. "drop" and "surge" in the brief are the product categories Drop-out Fuse Cutout and Surge Arrester (the pilot scope), so item 2 is DONE, as the pilot scope extended to 445 codes. See `audit_minmax_pem107_season.md` and STATUS.md.

Scope: audit only; nothing in code, config, data or pages was changed. Two read-only database sessions (SELECT and metadata only; the second authorised by the user after the first was used for the catalog). Query outputs are saved outside the repository (scratch folder `phaseR_db`) and are not committed. Evidence levels: **V2** = checked by the auditor and independently re-derived by a separate Validator with no database access; **V1** = checked by the auditor only; **inferred** = reading of names or patterns.

## Part 1 -- Traceability

| Brief item | Status | Evidence | On the pages | Difference and where its reason is recorded |
|---|---|---|---|---|
| 1. Omni sales trend, pricelist items, 3 years, cube_Sale_APD | **Done**, old basis, not refreshed | Source/filter printed on the tab (index.html:7556); phase 1 done (STATUS.md:401, 1988); metrics METRICS.md Sec.29-38 | `index.html` tab `omniTab` (index.html:7554); not on sales_report or inventory | Window is calendar 2024-2026 (config.yaml:20-21), about 2.7 years; status Actual+MPS; no generator script, labelled stale (index.html:7557-7563; STATUS.md:6280-6292) |
| 2. Use drop and surge groups to set models | **Partly done** | Groups became the pilot scope (config.yaml:33-35; STATUS.md:30-31, 5358; CONVENTIONS.md:175). Phase 2 found no stable winner at any of 10 series and wrote no config (STATUS.md:419-426, 2965-2969) | sales_report section 5 (build_report.py:647), section 6 (:671) | One Top-down Combination for every item, not a model per group; reason STATUS.md:419-426, 5606-5627. That the item-1 trend singled out these two groups is **not found** anywhere in the repository |
| 3.1 Moving average, suitable history | **Partly done** | MA3/MA6/MA12 exist only inside the equal-weight Combination (models.py:17-20, 85-113; config.yaml:136-139, 162-174). No code picks a window per group | sales_report section 5 chart; a standalone "3-month moving average" only in the hand-made S&OP tab (index.html:7371), not reproducible (STATUS.md:7046-7075) | Naive won 35 of 58 pilot items, no stable winner (STATUS.md:2391, 419-426) |
| 3.2 Budgets, sales insight, EGP bids | **Not done** (blocked on data) | No code or config reference (grep of egp, bid, budget, storm, insight, weather, holiday over src/ and config/: no relevant hit); STATUS.md:2976, 5909-5910; PROJECT_GRAPH.md node EF1 "blocked on data" | S&OP tab says "in progress" (index.html:302, 7383) | No data supplied; collection format not agreed. Database survey in Part 6 |
| 4. Inventory model, FG Max-Min from item 3 + vendor lead time + storms | **Partly done, uncalibrated** | Max-Min for `finished_goods_stock` (METRICS.md Sec.5, 73-82), demand = Top-down forecast, stock from Cube_Inventory_Exact (METRICS.md:97-110); calibration banner STATUS.md:3-17 (predicted fill 8.2% / 1.1% / 1.6% vs 86-98% actual) | forecast/inventory.html (build_inventory_page.py) for PEM101/103/107; index.html Inventory Detail panel | **Lead time is an assumption**, uniform: grid [45, 60, 75], default 60 (config.yaml:889-891, 942), slider 30-90 (:1337); "no per-item override" (:877-879); "none is a measured fact" (METRICS.md:35). **Storms appear nowhere** in code, config or docs except a plan note in the S&OP tab (index.html:311, 7384). **No MRP export** exists. Page builder also admits `component_stock_ato` (build_inventory_page_data.py:328) |
| Settings: 2 categories + 3 items | **Partly done, pilot form only** | See Part 2 | -- | No recorded decision retires the category settings |

## Part 2 -- Drop/surge settings and the three items (V2)

- **Category settings are not applied in the current path.** `pilot_categories` (config.yaml:33-35) is read only by `src/investigations/load_data.py:77`; `pilot_item_codes` (config.yaml:130-133) only by one-off scripts (`investigations/backtest.py:198`, `phase22_validator.py:260`, `phaseE1fix_validator.py:760`, `phaseQ23_modeler_part2.py:273`). Neither is read by `monthly_refresh.py`, `load_data_all_divisions.py`, `backtest_all_divisions.py`, `transferability_all_divisions.py`, `forward_test_all_divisions.py` or `models.py`. The current scope is the 335 codes with status `forecast` among the 445 (`load_data_all_divisions.py:55-76`). One method for all series: `models.py:85-113`, `config.yaml:226, 248`. Category and Type only drive aggregation, never the method. No key selects a model by category or by a drop/surge flag.
- **The three items are reporting only.** They add rows and charts (`backtest_all_divisions.py:41, 185-190`; `forward_test_scoring.py:44, 112`; `focus_item_model_selection.py:43`; `build_report.py:57`) but change no forecast or method. No per-item override exists; decision STATUS.md:629-636, 4883-4895: keep Top-down, best |t| < 1.3, override key "NOT created". The August forward test has all three codes worse than their backtest (STATUS.md:161-166); no decision followed.
- **When it stopped.** The category settings were applied in the pilot from 2026-08-31 (commit 8a4b9d7, config keys; e4ec5c1, first backtest) to about 2026-09-04 (b598e3b moved the pilot loader to `src/investigations`; bb53351 division-unfiltered scope), and the all-division path (26abdb3, 2026-09-07) replaced it. No commit "removed" a per-category model setting because none existed in the model path (searched with `git log -S`). The date range is inferred (moderate confidence); the file:line facts are confirmed.

## Part 3 -- Vendor lead time

**Candidates** (database `salewarehouse`, the only database this login can read; 111 tables and views): see the table; rows and date ranges are from the profile query.

| Table | Role (inferred from names) | Rows | Date range | Item column |
|---|---|---|---|---|
| Cube_PO_Exact | purchase-order lines | 94,290 | po_date 2023-01-01 onward (future outliers to 2063); request, planned and fulfilment dates | item_code (13,830 items) |
| cube_po / cube_po_bom | PO approval-flow lines | 165,321 / 312,277 | create 2023-01-03 to 2026-10-01 | itemcode |
| cube_pr / cube_pr_bom | purchase requisitions | 201,275 / 183,715 | 2023-01-03 / 2025-01-02 to 2026-10-01 | itemcode |
| Cube_Receipt | goods receipts | 82,945 | 2023-01-03 to 2026-10-01 | ItemCode |
| Cube_ReceiveRM | raw-material receipts | 607,220 | 2016-01-06 to 2026-10-01 | Itemcode |
| Cube_Incoming_Receipt | incoming/QA | 70,348 | to 2021-10-04 (stale) | itemcode |
| Cube_tobe_received | open PO lines | 1,569 | order 2021-11-12 to 2026-10-01 | itemcode |
| Cube_Incoming, Cube_Incoming_Wait, Cube_Vendor_List, cube_supplier_data_exact_pdem | incoming, vendor change log, supplier master | 23,607 / -- / 225,266 / 8,207 | -- | none or partial |

Join key: PO number plus item (`Cube_PO_Exact.po_no` = `Cube_Receipt.PO` = `Cube_ReceiveRM.PO`; item code on both; trim and upper-case). Of 4,208 PO-items for the BOM's raw materials, 4,031 match a receipt; of 1,287 POs, 1,252 appear in the receipts.

**Observed lead time** (order date to first receipt; V2): the 82 PEM101 `stock_policy` finished goods link through `Cube_BOM_Exact` to 79 FG codes and **209 raw-material codes**; **132 of the 209 (63%) have purchase orders**; 5,413 PO rows, 4,208 PO-items, **4,030 usable (0 to 730 days)**.

| Group | n | p10 | p25 | median | p75 | p90 | mean |
|---|---|---|---|---|---|---|---|
| All PO years 2023-2026 | 4,030 | 8 | 19 | **41** | 60 | 86 | 44.6 |
| PO 2023-2024 | 2,309 | 7 | 21 | 45 | 68 | 91 | 48.7 |
| PO 2025-2026 | 1,721 | 8 | 18 | 37 | 53 | 65 | 38.9 |

The planned date minus PO date has median 33 to 38 days.

**Against the model's assumption.** The model uses 60 days (grid 45/60/75): about the observed **p75**, above the observed median of 41 (37 in 2025-2026). Limits: the clock starts at the PO date, not the requisition or approval; it stops at the first receipt, not the full quantity; 63% of the raw materials are observed and **no finished good has all its raw materials observed** (0 of 79; a finished good's observed share is 48% on average); import and local suppliers are not separated; 177 recent PO-items have no receipt yet. Confidence: medium (inferred comparison; counts V2). Note: DATA_MAP.md's earlier statement that `Cube_PO_Exact` has 5.5-7.5% coverage refers to coverage of the finished-goods scope, which is a different population from the BOM raw materials here.

**What the purchasing team would need to supply:** which of the PO date, requisition date or approval date starts the lead time; whether the 63% of raw materials with orders are the ones that matter; lead times for materials never ordered since 2023; import versus local flags; and the raw-material list for stock-policy items they treat as critical.

## Part 4 -- How MRP reads Max-Min (V2)

- `Cube_Inventory_Exact` has **minimum and maximum columns at the grain item x warehouse x company** (97,524 rows, one row per company, item and warehouse; companies PEM and CI; one load batch 2026-10-01 21:45-21:47).
- Non-zero minimum: 2,201 rows / 1,905 items; non-zero maximum: 1,511 rows / 1,249 items; either: 2,245 rows / 1,941 items, across 23 warehouses (WH06 618, WH01 480, WH02 391, WHPG 152, FG 124, WH03 100, WH 100, FG01 68, FG11 58, QA 57, WH08 38, W121 30, WH07 11, F101 7, others 1-2).
- **734 rows have a minimum but a maximum of 0** (618 of them in WH06), so Min and Max are not always set as a pair.
- Of the 445 project codes, 388 appear in the table; **113 items carry a non-zero value, in 229 rows** (FG 105, FG01 62, FG11 54, WH01 6, F101 1, INTR 1).
- Match with the repository: `phaseE1fix_2_current_minmax.csv` (128 items, summed over warehouses) matches the live table on both columns for 125 of 128, and 128 of 128 counting the 3 items absent from the table as 0/0 (checked by the Validator). So the project's "current Min/Max" is this table's values; **the project does not yet write any Max-Min to the ERP**.
- Other tables with min/max-like columns: `Cube_Inventory_Aging_PSL` (Minimum, Maximum; company PSL, 2,298 rows, same load day as aging), `Cube_Production_Control` (MinVal, MaxVal: production-control measurements, not reorder points), `Cube_Quotation` (ctr_leadtime, a contract lead time), `Cube_emanu` (leadtime; job data 2015-2019). No table holding reorder points or MRP parameters was found; no MRP table exists in the 111 objects.
- **Questions only the ERP team can confirm:** (1) Does MRP read `minimum` and `maximum` from this table, per warehouse, or from the ERP's own item or warehouse master? (2) Which warehouses does MRP plan against (the FG, FG01, FG11 and WH01 rows, or others)? (3) What does a minimum with no maximum (734 rows) mean for MRP? (4) Is a Max-Min to be loaded per item or per item and warehouse, in which unit, and through what interface? (5) Does MRP use a separate lead-time or safety-stock field? (6) Are these values set by hand, and how often are they reviewed?

## Part 5 -- Freshness of every source table (V2)

Read on 2026-10-02 10:50. Each table's timestamp column shows **one narrow load batch**, so each is a truncate-and-reload snapshot (inferred); no table holds its own load history.

| Table | Latest load | Group |
|---|---|---|
| cube_Sale_APD (timeStamp) | 2026-10-01 17:17:33 | 17:00 group |
| Cube_Backlog | 2026-10-01 17:02:28 | 17:00 group |
| Cube_Quotation | 2026-10-01 17:03:08 | 17:00 group |
| cube_Contract | 2026-10-01 17:04:34 | 17:00 group |
| Cube_Inventory_Exact | 2026-10-01 21:47:21 | 21:45 group |
| cube_inventory_tran | 2026-10-01 21:54:04 | 21:45 group |
| Cube_PriceList | 2026-10-01 21:56:00 | 21:45 group |
| **Cube_CES** | **2026-09-28 07:00:34** | 06:00-07:00 group |
| Cube_BOM_Exact | 2026-09-28 06:19:06 | 06:00-07:00 group |
| Cube_Inventory_Aging | 2026-09-28 06:15:10 | 06:00-07:00 group |
| information_state | 2023-07-11 (stale) | dead |

Earlier Cube_CES loads recorded in the repository: 2026-08-31 (Mon) 07:11, 2026-09-02 (Wed) 06:56-06:58, 2026-09-22 (Tue) 07:00-07:02, 2026-09-25 (Fri) 10:04 (the backlog block's `loaded_at` in `data/inventory.json`, commit 8650cac), 2026-09-28 (Mon) 06:58-07:00. Inventory_Exact was loaded about 21:40 on 09-06, 09-09, 09-24 and 10-01.

**Cadence conclusion: not established.** Cube_CES, Cube_BOM_Exact and Cube_Inventory_Aging were all last loaded on Monday 2026-09-28 and not since (four days), while the 17:00 and 21:45 groups loaded on 2026-10-01. Each repository observation is a snapshot of a table that is overwritten, so it shows that a load happened that day, not that none happened in between; the 09-25 10:04 value does not fit the 07:00 pattern. It is therefore **not known** whether the 06:00-07:00 group runs on a schedule longer than daily (weekly on Mondays would fit 08-31 and 09-28; 09-02 and 09-22 do not) or has stopped. A direct test exists: the group should show a new load on Monday 2026-10-05 if weekly. **Questions for the ETL team:** (1) What is the schedule of the job that loads Cube_CES, Cube_BOM_Exact and Cube_Inventory_Aging, and of the 17:00 and 21:45 jobs? (2) Did the 06:00-07:00 job run on 09-29, 09-30 and 10-01 and fail, or is it not scheduled on those days? (3) What happened at 2026-09-25 10:04 for Cube_CES? (4) Why has `information_state` not loaded since 2023-07-11? (5) Is the source system's own change time available, apart from the load time?

## Part 6 -- External factors, survey only

Nothing was fetched from outside and nothing analysed. From the table and column catalog of the 111 objects (row counts and date ranges of these tables were **not** queried, the two sessions being used):

| Factor | What the database holds |
|---|---|
| Utility budgets (PEA, MEA, EGAT) | **No table or column found.** `Cube_OI` has a `budget` column (an opportunity's budget, 33 columns incl. product, customer, forecast delivery date, sign date) and `Cube_Target_PMIS` has company revenue targets by product and year (TargetRevenueAmount, TargetPOAmount): possibly partial proxies, not utility budgets |
| EGP bid announcements | **Nothing found** in names or columns. `Cube_Enq` (enquiries, delivery date, quantity), `Cube_OQ` (quotations) and `Cube_Opp_PSP` (opportunities, PSP) hold the company's own pipeline, not public bids |
| Sales team insight | `Cube_OI_SaleForecast` (EMLID, Year, SalePerson, CustomerSegment, ProductType, Manufacturer, ActualSaleLastYear_Revenue, ActualSaleLastYear_GM: 8 columns) suggests a per-salesperson forecast sheet whose forecast values are not among its columns; `Cube_OI`, `Cube_Enq`, `Cube_OQ` carry the pipeline with expected dates |
| Storms | **Nothing found** |
| Chinese holidays, shipping disruption from China | **Nothing found** (no calendar, holiday, freight, container, customs or port table or column) |
| Thai long holidays | **Nothing found** (no calendar table; the only calendar-like table name, `Cube_Calendar`, does not exist) |

The prior survey in PROJECT_GRAPH.md node EF1 (job names as a partial supplement) stands. Backlog item: profile `Cube_OI`, `Cube_OI_SaleForecast`, `Cube_Enq`, `Cube_OQ`, `Cube_Target_PMIS` (row counts, date range, fill rate, link to item codes) in one read-only session.

## Part 7 -- Validator

A separate Validator, which read none of the auditor's conclusions and made no database connection, re-derived from the saved query outputs and the repository:

| Item | Verdict |
|---|---|
| Part 2 finding (readers of `pilot_categories`, `pilot_item_codes`, the three-item constants; no model selection by category or item) | **Match.** Adds: the current path is 335 of the 445 codes (335 forecast, 82 placeholder-pending, 10 placeholder-assigned, 12 excluded-division, 6 excluded-never-sold), and `adopted_scope_file` (config.yaml:234) still points at the older 128-item scope, which feeds only the pilot outputs |
| Part 3 candidate-table list | **Match**; also lists `Cube_pr_monitoring` (not profiled) and notes `Cube_PO_Received_PSP` looks like customer PO data, not supplier PO |
| Part 3 lead-time figures | **Match** to the figure: n 4,030, p10 8, p25 19, median 41, p75 60, p90 86, mean 44.55; 2023-24 median 45; 2025-26 median 37; 132 of 209 raw materials observed; 0 of 79 finished goods with all raw materials observed |
| Part 4 counts | **Match**; adds: 76 warehouses overall, 128-item match is 125 literal and 128 with absent items as 0/0 |
| Part 5 load times | **Match**; adds the repository's earlier Cube_CES load list and states that the cadence cannot be established from snapshots of overwritten tables |

No discrepancy between auditor and Validator. Both are one-source results: the Validator re-derived from the same saved query outputs, not from a new database query (it had no access), so a query-level error would be shared.

## Gaps and assignment

| Gap | Assigned |
|---|---|
| Drop/surge and three-item settings not applied in the 445-code path, no recorded decision retiring them | R1 (user decides whether to restore per-category or per-item settings; Claude Code implements) |
| 3.1: no standalone moving average with a per-group history window | R1 (same decision) |
| 3.2: no budget, EGP or storm data; sales-insight and pipeline tables found but unprofiled | EF1 / X1 profile of the pipeline tables; budgets, EGP, storms: people to supply |
| Inventory lead time assumed (60 days) while 4,030 observed PO-to-receipt lead times exist | K (replace the assumption with the observed distribution, by material where the data allows); purchasing team confirms the clock start |
| Max-Min not written to the ERP; MRP format unknown | G2 / R2 (MRP hand-off) with the ERP team's answers |
| Cube_CES / BOM / Aging load cadence unknown | C3 (check on 2026-10-05) and the ETL questions |
| Trend tab (item 1) stale, no generator, 2.7-year window | F (index generator) |
