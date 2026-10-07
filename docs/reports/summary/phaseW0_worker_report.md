# phaseW0 worker report (Explorer+Analyst) - Parts 2-4

Written 2026-09-29. Worker scope: Parts 2-4 only. No tracked file edited, no pipeline run, no commit.

## 0. Pre-registered criteria (written BEFORE any computation)

Per-code comparison: DB sum of qty per code (window 2026-01-01..2026-07-31 by the date field of the combination)
versus the tab's `hist` (Jan-Jul qty, from output/summary/phaseW0_tab_extract.csv).

Two denominators are reported for every combination:
- D204 = the 204 codes with data_flag='real' (tab shows real history).
- D426 = all 426 codes, where example-badge codes have hist as shown in the tab (0 for zero-history codes).

Verdict categories for a definition (combination):
- REPRODUCES the tab: >=95% of per-code hist quantities match exactly on D204 AND, separately, >=95% on D426,
  AND all 7 monthly totals (`sale` column, million baht) match the tab's Section 1 Actual row
  (66.2, 67.1, 82.1, 80.1, 84.3, 77.1, 35.4) within rounding to one decimal.
- PARTLY reproduces: >=50% exact per-code matches (on D204 and on D426).
- NOT reproducible from the database: anything else.

Matching to the tab's 426 codes is done on the tab's own code strings. "Exact" code matching = itemcode string equal;
"normalised" = trailing '.' and whitespace stripped, case folded (applied to both sides).
Within-5% test: |DB - tab| <= 0.05*tab when tab>0; when tab=0 it counts only if DB=0.
Monthly totals are computed both over all rows of the combination and restricted to the 426 codes.

Scripts (all read-only against the DB; ONE connection, one login, succeeded, no retry):
- Pull: `output/summary/phaseW0_worker_pull.py` (copy of scratchpad `phaseW0_pull.py`) -> raw pickle in the scratchpad (not in the repo).
- Analysis (offline, all Parts 2-4 numbers): `output/summary/phaseW0_worker_script.py` (set env `PHASEW0_RAW` to the raw pickle). Its run log: scratchpad `phaseW0_results_log.txt`.
- Pricelist overlap: `output/summary/phaseW0_worker_pricelist_overlap.py`.
Tags: **[C]** = CONFIRMED (query result / direct recomputation by the scripts above); **[I]** = INFERRED (my interpretation, not verified).

## 1. Headline (Part 2 verdict)

**No definition tested REPRODUCES the tab. Best is PARTLY (>=50% per-code): 118/204 real codes exact (57.8%) and 325/426 all codes exact (76.3%); 0 of 7 monthly totals match in any of the 1,512 combinations.** [C] (grid: `phaseW0_worker_grid.csv`). Confidence high that the tab is not reproducible from the current DB with the dimensions listed; medium on why (sec. 4, 9).
- D426 is inflated: 207 of the 325 exact matches are example-badge codes where tab=0 and DB=0. The D204 figure is the informative one. [C]
- Verdict counts over the grid: REPRODUCES 0, PARTLY 220, NOT 1,292. [C]

## 2. Step B - sources and date columns [C] (INFORMATION_SCHEMA + row counts)

- `cube_Sale_APD` (62 cols; 52,826 rows; createDate 2021-01-11..2026-12-01; refreshed 2026-09-28 17:02-17:21). Date-typed columns: forecast_date, customer_entry, createDate, timeStamp (datetime), warranty_date, newCustomerDate, PODate, plan_date. Also integer year, month, week (used as option `ym`). Rows in window Jan-Jul 2026 by field: createDate 12,242; PODate 12,238; forecast_date 11,127; plan_date 10,886; customer_entry 428; newCustomerDate 209; warranty_date 180; timeStamp 0 (whole table is one refresh).
- `Cube_CES` (41 cols; 168,852 rows; refreshed 2026-09-28 06:58-07:00). Date-typed: CtrDate, ReceiveCtrDate, ForecastDelDate, PlanDelDate, ActualDelDate, Timestamp. In-window rows: ForecastDelDate 15,843; ReceiveCtrDate 12,083; CtrDate 12,079; PlanDelDate 10,952; ActualDelDate 10,868; Timestamp 0.
- Tables matching %Sale% / %APD% / %2026% (18): cube_Sale_Snapshot, cube_Sale_PPS, cube_Sale_APD_test, cube_Sale_PTS, cube_Sale_PSP_API, sale_Fact, Cube_OI_SaleForecast, cube_Sale_CI, cube_Sale_PDE, cube_Sale_PMW, Cube_Sale_APD_2, cube_Sale_APD_snapshot, cube_Sale_sView, cube_Sale_APD, cube_Sale_PPD, cube_Sale_APD_2016, cube_Sale, cube_Sale_PSP. **No table named like `cube_Sale_APD2026` exists.** [C]
- Source-table candidates pulled and put in the grid (APD-named, same schema): `cube_Sale_APD` (the project's primary table); `cube_Sale_APD_2016` (142,058 rows, createDate 2016-01-04..2026-12-01, refreshed 2026-09-09; 12,042 rows in window by createDate); `Cube_Sale_APD_2` (31,186 rows, createDate to 2025-09-29, 0 in window by createDate); `cube_Sale_APD_test` (79,518 rows, createDate to 2025-08-27, 0); `cube_Sale_APD_snapshot` (no status column, createDate to 2024-07-30, pull hit my 300,000 TOP cap; excluded from the grid); `Cube_CES`.
- NOT pulled (gap, stopping rule): `cube_Sale_Snapshot`, `sale_Fact`, `cube_Sale`, `cube_Sale_sView`, `Cube_OI_SaleForecast`, `cube_Sale_PPS/PTS/PSP/PDE/PMW/PPD/CI/PSP_API`. The one-connection rule stopped me pulling non-APD names. `cube_Sale_Snapshot` is the only name suggesting dated snapshots; whether it holds an August state is UNKNOWN. The team owning the cube/ETL (data engineering / BI) must say which table or dated snapshot "Cube Sale APD2026" is.
- Distinct values, cube_Sale_APD rows with year=2026 (n=15,779): status Actual 13,983 / MPS 1,796. revenue_type: Omni Channel 14,095; Total Customer Solution 840; Recurring Revenue Development by MA and SA 576; Tendering 198; Investment 33; PPA or Long Term Contract 28; None 9. cmp: PEM 13,649; PDE 728; PEMC 406; PCE 401; PSP 226; CI 97; PPD 80; PTS 44; SBP 42; PCC 33; PPS 30; NSPC 13; PSS 12; PPP 8; PSL 7; SKB 3. sale_company: PEM 13,650; PDE 728; PEMC 406; PCE 401; PSP 226; CI 96; PPD 80; SBP 50; PTS 44; PCC 33; PPS 30; NSPC 13; PSS 12; PSL 7; SKB 3. sale_division: 32 values (largest PEM105 13,016; PDE104 625; PEMCSA 406; PCE101 401; PEM103 196; PEM104 151; PEM101 116; CI101 96; PEM107 90; PEM102 81; full list in the log). Companies at >=1% of rows used in the grid: cmp and sale_company each PEM, PDE, PEMC, PCE, PSP.
- Cube_CES, CtrDate year 2026 (n=15,468): Status Actual 13,845 / Backlog 1,621 / Cancel 2. RevenueType Omni Channel 13,915; Total Customer Solution 744; Recurring Revenue 574; Tendering 164; Investment 33; PPA 28; None 10. Company PEM 13,566; PDE 726; PEMC 408; PCE 397; CI 94; PPD 79; SBP 46; PTS 44; and smaller (grid used the >=1% values PEM, PDE, PEMC, PCE). SaleDivision and ManuDivision lists are in the log.
- MPS = Backlog equivalence: DATA_MAP.md lines 344-347 and 545-548 state Backlog is the true MPS equivalent (158/158 forward, V2); I cited it and did not re-verify it. For Cube_CES I used Actual vs Actual+Backlog, with Backlog-row qty = ActualQty+BacklogQty (DATA_MAP.md:900). Cube_CES `sale` = ActualPrice (+BacklogPrice on Backlog rows) is my INFERENCE that those columns are line totals. [I]
- Pricelist overlap [C] (`phaseW0_worker_pricelist_overlap.py`): repo `reference/pricelist.xlsx` (visible sheets, 446 rows, 445 distinct codes; sheet names are "...Version 2", not the tab's "Q4 2025 R.1") contains 419 of the tab's 426 codes exactly (416 of 423 normalised). 7 tab codes are NOT in the repo file: EEE-F-FC-1040011002, LB-F-99-G2261203, LB-F-99-G2461000, LB-F-99-G2461000-01, LB-F-99-G3341003, Se-F-xxx1, Se-F-xxx2. 26 repo-file codes are not in the tab (CI101 14, PEM103 10, PEM101 2, PEM102 1). So the repo file is NOT the tab's exact 426-code set; **I matched on the tab's own 426 codes (as required).** The tab also has 3 dotted/undotted twin pairs (426 exact codes -> 423 normalised).

## 3. Step C - grid results (`phaseW0_worker_grid.csv`, 1,512 rows, one per combination, ranked)

Ranking key: n426_exact, then n204_exact, then months matched. Dimensions covered: source (cube_Sale_APD, cube_Sale_APD_2016, Cube_Sale_APD_2, cube_Sale_APD_test, Cube_CES); date field (every date-typed column, plus `ym` for APD-schema tables); status (Actual vs Actual+MPS / Actual+Backlog); channel (Omni vs all); company (all, plus each cmp / sale_company value >=1%); code matching (exact vs normalised). Window 2026-01-01..2026-07-31. [C]

**Best three combinations** (all: status Actual, channel Omni, company field = PEM, exact code) [C]:

| Rank | Source / date field / company | D204 exact | D426 exact | D204 within 5% | D426 within 5% | months ok (all rows / 426) | total Jan-Jul M baht (all rows / 426 codes) | codes qty>0 |
|---|---|---|---|---|---|---|---|---|
| 1 | cube_Sale_APD_2016 / createDate / cmp=PEM | 118 (57.8%) | 325 (76.3%) | 159 | 366 | 0 / 0 | 597.65 / 287.66 | 219 |
| 2 | cube_Sale_APD_2016 / createDate / sale_company=PEM | 118 | 325 | 159 | 366 | 0 / 0 | 597.73 / 287.66 | 219 |
| 3 | cube_Sale_APD_2016 / PODate / cmp=PEM | 118 | 325 | 159 | 366 | 0 / 0 | 596.50 / 287.66 | 219 |

(Ranks 4-6 are the same matches under other date fields: PODate, `ym`.) Tab targets: 204 codes with sales, 492.4 M total. Within-5% rule: |DB-tab| <= 5% of tab when tab>0; when tab=0 only DB=0 counts.

Monthly `sale` (M baht, Jan..Jul) versus tab 66.2 / 67.1 / 82.1 / 80.1 / 84.3 / 77.1 / 35.4 [C]:
- Rank 1, all rows: 62.57 / 84.57 / 101.51 / 87.25 / 94.10 / 89.78 / 77.87; restricted to the 426 codes: 41.68 / 40.62 / 49.10 / 44.37 / 38.42 / 34.87 / 38.59.
- Rank 2 all rows: 62.57 / 84.57 / 101.51 / 87.25 / 94.10 / 89.78 / 77.95. Rank 3 all rows: 62.57 / 83.46 / 101.47 / 87.25 / 94.10 / 89.78 / 77.87.
- `cost` variant (rank 1, 426 codes): 23.77 / 24.23 / 29.02 / 25.89 / 21.33 / 19.81 / 22.53 (all rows: 35.21 / 97.14 / 75.51 / 57.71 / 61.14 / 61.43 / 52.41; total 440.55). `saleGM` variant (426 codes): 17.92 / 16.39 / 20.08 / 18.48 / 17.09 / 15.06 / 16.06 (all rows: 27.36 / -12.57 / 26.00 / 29.54 / 32.96 / 28.35 / 25.46; total 157.10). Months matching the tab revenue row: 0 for cost and saleGM (different measures; shown because requested).
- **Across all 1,512 combinations the maximum number of months matching within 0.1 is 0 (all rows and 426-restricted), and no combination has a Jan-Jul total within 492.35-492.45.** The smallest 7-month total absolute error is 111.5 M baht (rank 3, all rows). July is the clearest miss: tab 35.4 vs 77.9 (all rows) / 38.6 (426 codes).
- Reference definition (the usual project one) `cube_Sale_APD`, Omni, Actual, createDate, all companies, exact code: 99/204 and 302/426 exact; within 5%: 136/204, 339/426; total 748.98 M (all rows: 86.67 / 119.90 / 126.70 / 121.10 / 107.55 / 101.14 / 85.93) and 297.73 M (426 codes); 223 codes with qty>0. Same with Actual+MPS: 93/204, 291/426. Restricting that reference to cmp=PEM: 111/204, 315/426, 149/204 within 5%, total 618.16 M. [C]

**Compact table of all combinations** (max over each source x status x channel; counts of combinations per cell; from `phaseW0_worker_grid.csv`) [C]:

| Source | Status | Channel | combos | max D204 exact | max D426 exact | max D204 in 5% | max D426 in 5% | max months ok |
|---|---|---|---|---|---|---|---|---|
| cube_Sale_APD_2016 | Actual | Omni | 144 | 118 | 325 | 159 | 366 | 0 |
| cube_Sale_APD_2016 | Actual | all | 144 | 118 | 321 | 159 | 362 | 0 |
| cube_Sale_APD_2016 | Actual+MPS | Omni | 144 | 108 | 310 | 145 | 347 | 0 |
| cube_Sale_APD_2016 | Actual+MPS | all | 144 | 108 | 306 | 143 | 341 | 0 |
| cube_Sale_APD | Actual | Omni | 176 | 111 | 315 | 149 | 353 | 0 |
| cube_Sale_APD | Actual | all | 176 | 111 | 312 | 149 | 350 | 0 |
| cube_Sale_APD | Actual+MPS | Omni | 176 | 108 | 310 | 145 | 347 | 0 |
| cube_Sale_APD | Actual+MPS | all | 176 | 108 | 306 | 143 | 341 | 0 |
| Cube_CES | Actual | Omni | 50 | 114 | 317 | 153 | 356 | 0 |
| Cube_CES | Actual | all | 50 | 114 | 313 | 151 | 350 | 0 |
| Cube_CES | Actual+Backlog | Omni | 50 | 114 | 317 | 153 | 356 | 0 |
| Cube_CES | Actual+Backlog | all | 50 | 114 | 313 | 151 | 350 | 0 |
| Cube_Sale_APD_2 and cube_Sale_APD_test (8 status x channel cells) | any | any | 4 per cell | 0 | 218-222 | 0 | 218-222 | 0 |

Best Cube_CES: ActualDelDate / Actual (or Actual+Backlog) / Omni / Company=PEM: 114/204, 317/426, total 661.27 M (all rows), months 64.74 / 82.48 / 97.05 / 80.38 / 104.12 / 131.15 / 101.36. Date-field effect (all companies, best of status/channel): createDate = PODate = `ym` = 99/204 in cube_Sale_APD; forecast_date 97; plan_date 98; customer_entry 4; newCustomerDate 0; warranty_date 0; timeStamp no rows. Company effect: cmp/sale_company=PEM lifts cube_Sale_APD from 99 to 111; every other single company alone gives at most 1/204. Code matching: exact beats normalised by 2 codes at D426 (normalising gives the dotted twin the qty of its undotted code, breaking a 0=0 match). [C]

Interpretation [I]: cube_Sale_APD_2016 ranking above cube_Sale_APD is not evidence the tab used APD_2016; it is consistent with the tab being built from an EARLIER, smaller state of the data (sec. 4).

## 4. Step D - unmatched codes under the best combination (`phaseW0_worker_unmatched.csv`) [C]

Best = rank 1 (cube_Sale_APD_2016 / createDate / Actual / Omni / cmp=PEM / exact).
- 101 of 426 codes do not match: 86 real-badge, 15 example-badge (tab 0, DB > 0). **All 101 have DB > tab; none has DB < tab.** Sum(DB - tab) = +32,334 units; over the 204 real codes DB 838,647 vs tab 806,935 (+3.9%); median DB/tab of mismatching real codes 1.054; 41 of the 86 within 5%, 13 more than 25% over.
- All 101 tab code strings exist exactly in the table; the dotted-twin issue affects only 2 example codes (sec. 6).
- DB rows the combination excludes (Actual non-Omni in window: 13 of the codes; MPS rows: 42; other-company rows: 11) would only raise DB further, so they do not explain a DB-too-high gap. [C]
- Date shape: the latest selected row of the mismatching codes is 2026-07-31 for 29 codes and 07-30 for 15. For 35 of the 101 there is a date prefix (cumulative qty of rows dated <= X by createDate) equal to the tab value; the implied X ranges 2026-01-16..2026-07-22 (median 2026-07-02; median 1 row after X); the most common single X (2026-07-03..05) serves 13 of the 35. For the other 66 codes NO prefix reproduces the tab value, i.e. dropping only the latest-dated rows cannot explain them. [C] Conclusion [I]: the gap is not one common cut-off date.
- Table-vs-table (same filters, Jan-Jul createDate, Omni Actual): cube_Sale_APD has 10,513 rows vs cube_Sale_APD_2016 10,368; 152 ids only in cube_Sale_APD (qty 6,961; sale 57.65 M; createDate 2026-01-05..2026-07-30; cmp PEM 77, PSP 53, PEMC 12, PCE 9, PPD 1); 7 only in APD_2016; common ids never differ in qty/itemcode/sale/createDate. Among 50,341 ids in both tables (all rows) status differs on 631 and revenue_type on 15 (status flips between the 2026-09-09 and 2026-09-28 refreshes). [C] So the data changes materially, including back-dated and status-changed rows, within 19 days; the tab (uploaded 2026-08-24) is 36+ days older than the newest refresh. [I] This is the leading explanation for "DB always higher", but it is untested because no dated August snapshot was available.

## 5. Step E - cut-off tests (`phaseW0_worker_cutoff_scan.csv`, `phaseW0_worker_idcut_scan.csv`, `phaseW0_worker_attr_exclusion_scan.csv`) [C]

Rows kept only if the cut-off field <= the tested day (rows null in that field are dropped); each day 2026-07-01..2026-08-25 (56 days); top-3 combinations plus the reference definition; every date column of the table.
- **createDate cut-off, best combo: peak 118/204 (325/426) is a plateau from 2026-07-30 to 2026-08-25 (27 days), i.e. no effective cut-off** (07-01: 94/204; 07-16: 107; 07-22: 114; 07-31: 118). Reference definition: peak 99/204, single day 2026-07-22 (also 99 from 07-31 onward). PODate is identical.
- Other fields (best combo): plan_date <= 2026-08-04..05: 157/204 (76.9%), 370/426, 2-day plateau, 1 of 7 months matching; forecast_date <= 2026-08-05: 154/204, 366/426, single-day peak; customer_entry <= 07-10..07-19: 114/204; newCustomerDate 77; timeStamp and warranty_date 0 (timeStamp is one refresh moment, so a timeStamp cut-off is untestable). Reference definition: plan_date 140/204 (08-04..05), forecast_date 137/204 (08-05).
- **No cut-off on any field reaches 95% (193.8 of 204 needed); the maximum is 157/204. No createDate cut-off makes any month match; the plan_date cut-off makes 1.** The plan_date/forecast_date peaks near 2026-08-05 are narrow and reach only 77%; I do not infer a real cut-off date from them. [I]
- Row-id cut-off (id as insertion-order proxy; Spearman with createDate 0.974; 401 quantile points): peak 327/426 vs 325 with all ids; no id cut-off helps.
- Row-level exclusion of any single attribute value (5,472 exclusions tested for the best combo, 5,744 for the reference): best gain +4 real codes (best combo; exclude sale_division=PEM101 or one handle_by value (redacted: may identify a person/team)) and +12 real codes (reference; exclude cmp=PCE, sale_company=PCE, division=PCE101 or revenue=Wholesale: 99 -> 111). Nothing approaches 95%. Numeric row filters (qty<=0, sale=0) were NOT tested.
- Verdict: **no cut-off or single row filter makes the tab fit; the best-fitting cut-off is indistinguishable from no cut-off.**

## 6. Part 3 - the 18 example-badge codes (`phaseW0_worker_part3_codes.csv`, `phaseW0_worker_part3_rows.csv`) [C]

Example-badge codes (tab hist=0; 222 in the tab) with positive qty: best combination Jan-Jul: **15**; claim definition (cube_Sale_APD, Omni, Actual, createDate Jan-May 2026): **15** (also 15 by the year/month integer columns); reference Jan-Jul (cube_Sale_APD, Omni Actual, all companies): **21**; union of all sets: 21. **The claim of 18 codes is REFUTED as stated: 15 by the stated Jan-May Omni definition on the current DB (21 for Jan-Jul).** The difference may be data drift since the earlier snapshot-file check [I].

Row detail is from cube_Sale_APD (2026 rows, all statuses). Included = passes the best-combo filters (Actual, Omni, cmp=PEM, exact code string, createDate Jan-Jul).

| Cause group | Codes | Evidence |
|---|---|---|
| A. Code string (trailing dot) [C] | VT-F-99-010203. (REF Jan-Jul qty 202), VT-F-99-010303. (12) | The tab lists both `VT-F-99-010203` (real, hist 145) and `VT-F-99-010203.` (example, 0); likewise ...010303 (12 / 0). The DB stores only the undotted string, so an exact join gives the dotted row 0; the sales sit under the undotted twin. |
| B. Company [C rows; I tab rule] | HS-F-99-0303 (39 units, 3 Jan-Jul rows) | All rows cmp=PCE (Actual, Omni). Excluded if the tab excludes PCE; the reference scan shows excluding PCE lifts real matches 99 -> 111 (consistent, not proof). |
| C. Status changed after 2026-09-09 [C rows; I tab] | TF-F-99-2407223B1 (1 unit, id 277230, plus 1 PCE unit), RS-F-99-070005 (30 units, id 275406), CA-F-99-020102 (12 units, id 272480) | Each row is Actual/Omni/PEM/exact now but was MPS in cube_Sale_APD_2016 (2026-09-09). The tab (2026-08-24) predates both; that they were MPS then is INFERRED. |
| D. Unexplained by any tested dimension [C that rows pass every filter] | 15 codes: TF-F-99-2804223B1 (2), TF-F-99-3204223B1 (7), TF-F-99-2104223B1 (1), EEE-F-FL-5920-353-00700 (390), RS-F-99-041001 (30), RS-F-99-041002 (40), RS-F-99-041033 (30), RS-F-99-041006 (51), RS-F-99-041035 (24), RS-F-99-041007 (12), RS-F-99-041008 (18), RS-F-99-130011 (2), CT-F-99-020512 (6), CT-F-99-020726 (3), HS-F-99-1031 (6) | Rows are Actual, Omni Channel, cmp=PEM, itemcode identical to the tab, createDate 2026-02-10..2026-07-31, present as Actual in both refreshes. RS-F-99-0410xx codes also carry MPS rows, correctly excluded; the Actual part still gives positive qty. No date/status/channel/company/code reason explains tab=0. Whether they were loaded after the tab date cannot be seen (timeStamp is one refresh moment; no per-row load date). |

Of the 21: 2 code-string, 1 company, 3 status-timing (inferred), 15 unexplained. The row-level table (dates, status, revenue_type, cmp, sale_company, stored itemcode, id, qty, sale, whether each row is in APD_2016 and its status there) is `phaseW0_worker_part3_rows.csv`. Confidence: high for A and the D counts (direct rows), medium for B and C as explanations.

## 7. The four earlier claims (file-based check vs DB)

1. "Of the 204 real codes, 106 match Omni Actual exactly, the other 98 all lower": **PARTLY CONFIRMED.** DB reference definition (cube_Sale_APD, Omni, Actual, createDate Jan-Jul, all companies): **99 exact, 105 mismatched**; all 105 mismatches have the tab lower than the DB (0 tab higher), so the direction is CONFIRMED (reading lower as tab < DB) but the counts are NOT (99/105, not 106/98). [C]
2. "No single cut-off date 1 Jul-25 Aug makes them match": **CONFIRMED** (sec. 5): best any-field cut-off for the reference is 140/204 (plan_date <= 08-04/05); createDate cut-off peak 99/204. [C]
3. "18 example-badge codes had Omni sales Jan-May 2026": **REFUTED as 18**: 15 (sec. 6). [C]
4. "Monthly totals do not match Omni totals": **CONFIRMED**: 0 of 7 months match in all 1,512 combinations (sec. 3). [C]

## 8. Part 4 - Min/Max of the 81 real-Max-Min codes (`phaseW0_worker_minmax_summary.csv`, `phaseW0_worker_minmax_percode.csv`)

- File "Stock PEM101 as of 30-03-2026.xlsx" (Thai file name in the brief): **NOT FOUND.** Searched (bounded): Glob `**/*PEM101*.xlsx` under the D drive (timed out at 20 s, no hit); `find` (depth 4-5; names *PEM101*, *30-03-2026*, Stock*) under D:/sale_forecast, D:/tmp, D:/dev, D:/c, D:/codex, D:/app, D:/contract_odoo, D:/rfq_system, D:/ID, D:/wht, D:/life-os, D:/digital_swim_lane, D:/bind1_sandbox_review, D:/PCC_invesment_source and the user Downloads, Desktop, Documents. Nothing relevant (only SKILL_pem101.md and StockChart.tsx). Per the stopping rule, whoever produced the 30-03-2026 PEM101 stock sheet (PEM101 warehouse/stock team) must supply it. [C for the search]
- `Cube_Inventory_Exact`: 97,419 rows (PEM 95,832; CI 1,587); load timestamps 2026-09-28 21:40:31.683 .. 21:41:39.590 (one load of about 68 seconds); the 725 rows for the 81 codes span 21:41:01.193 .. 21:41:26.323; all company=PEM; all 81 codes have >=1 row; 28 warehouses (FG02 81 codes, FG01 81, FG21 80, FG 80, FG11 80, FMTS 73, FMTO 69, F109 35, ...). [C]
- Limit, not a finding: the tab Min/Max are dated 2026-03-30 (file name) while the table is a 2026-09-28 state, so a mismatch may be six months of change.
- Tab side: Min = 0 for 23 of 81 codes, Max = 0 for 6; Min>0 for 58, Max>0 for 75. [C]
- Aggregations tried (8 aggregations + 28 single warehouses + any-single-row): sum of all rows; sum PEM; sum CI; sum of FG01+FG21+WH21 (config.yaml sellable set, a business assumption); sum of rows with stock>0; sum of rows with min or max>0; max over rows; sum of rows at latest timestamp. **Best by raw exact count: single warehouse FG02 (tied FG21, and any-single-row): Min exact 23/81, Max exact 6/81, both 6/81 - but every one of those exact matches is a coincidence of zeros (tab value 0 and DB 0; FG02 has minimum=maximum=0 for all 81 codes). Exact matches where the tab value is non-zero: 0 of 58 for Min and 0 of 75 for Max under every aggregation, even any-single-warehouse-row.** Sum of all rows: 0/81 both; sum of sellable warehouses: Min 10/81, Max 4/81 (all zero-zero). [C]
- What differs: DB totals are larger than the tab (mean over the 81 codes of the sum of all rows: Min 3,726 vs tab 706; Max 5,916 vs tab 1,548); in the sellable warehouses the DB Min/Max are 0 for 23 codes while the tab has non-zero values for most. [C] I ranked aggregators by non-zero exact matches, then raw exact; since none has a non-zero match, no aggregator is meaningfully best. Choosing among about 37 options is multiple comparisons, so the zero result is the robust finding. [I] The tab Min/Max (source flag real_maxmin, labelled company Max-Min) are not copies of any Cube_Inventory_Exact minimum/maximum aggregate; what they are (a calculation or the missing stock sheet) is UNVERIFIED. Confidence: high that no inventory-table aggregation reproduces them; low on what they are.
- Beyond-brief observation (not pursued): `output/summary/phaseE1fix_2_current_minmax.csv` (current_total_min/max) covers 66 of the 81 codes and equals the tab Min in 0 and Max in 0 of them (ad-hoc check, same code strings). Comparing the tab to the Max-Min outputs of this project is a separate task.

## 9. Confidence, limits, further work (reported, NOT done)

- All DB figures are from the 2026-09-28 state; the tab is an external file uploaded 2026-08-24. Comparisons are across time; data drift alone (152 more Omni-Actual rows and 631 status flips between two September refreshes) is enough to produce the observed DB-higher pattern [I]. The DB gives no way to reconstruct the 2026-08-24 state.
- Further work for the orchestrator to decide: (1) get from the cube/ETL owners a dated snapshot or the exact table behind "Cube Sale APD2026" and the price-list file "Q4 2025 R.1"; (2) if permitted, one more read-only connection to inspect `cube_Sale_Snapshot` and `sale_Fact`; (3) test numeric row filters (qty<=0, sale=0) and per-code residuals against invoice dates; (4) obtain the 30-03-2026 PEM101 stock file; (5) DATA_MAP.md / PROJECT_GRAPH.md / STATUS.md updates were NOT made (scope rule).
- No tracked file was edited, no pipeline step run, nothing committed. New files, all in output/summary: phaseW0_worker_report.md, _grid.csv, _unmatched.csv, _cutoff_scan.csv, _idcut_scan.csv, _attr_exclusion_scan.csv, _part3_codes.csv, _part3_rows.csv, _minmax_summary.csv, _minmax_percode.csv, _script.py, _pull.py, _pricelist_overlap.py.
