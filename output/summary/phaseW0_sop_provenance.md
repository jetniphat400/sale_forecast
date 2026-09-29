# phaseW0 - S&OP Plan tab provenance (verification only)

Written 2026-09-29 (Get-Date 2026-09-29 09:34 at start; git history: tab added in commit 88cd3a1, 2026-08-24).
Written by the orchestrating agent from two agents' reports: `phaseW0_worker_report.md` (Explorer+Analyst,
Parts 2-4) and `phaseW0_validator_report.md` (independent Validator, Part 5). Agent pattern: one worker
(Parts 2-4 share one dataset and are sequential), then one Validator that read none of the worker's files
(AGENTS.md decomposition test). The orchestrator extracted the tab table (Part 1, extraction only).
Graph node: no existing node; this is a labelling question for the S&OP tab (feeds how the tab is described
to readers). Scope: no page edited; index.html untouched.

Levels: CONFIRMED = query/parse result; INFERRED = interpretation. Each DB figure is a state of the tables
on 2026-09-29 (cube_Sale_APD refreshed 2026-09-28; cube_Sale_APD_2016 refreshed 2026-09-09 per worker); the
tab was uploaded 2026-08-24.

## 1. Part 1 - what the tab shows (CONFIRMED, parse of index.html; script `phaseW0_tab_extract.csv`)

- 426 product codes in Section 4 (426 unique strings). Data badge: 204 "ข้อมูลจริง" (real), 222 "ตัวอย่าง"
  (example). All 204 real codes have history > 0; all 222 example codes have history 0. Sum of Hist Qty
  over the 426 rows: 806,935 units (all in the 204 real codes).
- Inventory Source badge: 81 "Max-Min จริง" (all PEM101; 78 of them real-data badge, 3 example) and 345
  "คำนวณตัวอย่าง".
- Section 1 Actual row (million baht, Jan..Jul): 66.2, 67.1, 82.1, 80.1, 84.3, 77.1, 35.4 (sum 492.3; KPI
  card 492.4). The tab's Forecast, Production Plan and Actual Production rows carry the identical
  Jan-Jul numbers (read from the HTML).
- KPI cards: 492.4 million baht total sales Jan-Jul; 426 codes in the price list; 204 with sales (47.9%);
  81 with company Max-Min.
- Parse check: three rows quoted from the source: No.1 `02-05-R-0004` PEM102, hist 0, avg 1.0, example, Min 3,
  Max 4, "คำนวณตัวอย่าง"; No.2 `TF-F-99-0703811G1` PEM103, hist 135, avg 19.3, real, Min 92, Max 111,
  "คำนวณตัวอย่าง"; No.426 `IS-F-99-0365EE0` PEM101, hist 0, avg 3.2, example, Min 10, Max 13,
  "คำนวณตัวอย่าง". The Validator wrote its own parser and got the same counts (426 / 204 / 222) and the same
  Section 1 row. **Limit: the parse is of the static HTML source; the page was not opened in a browser in this
  task, so "against the rendered page" was checked by two independent source parsers, not by a browser.**

## 2. Part 2 - criteria (written before computation, in worker report section 0)

REPRODUCES: >=95% of per-code history quantities exact (on the 204 real codes and on all 426) AND every
monthly total within rounding to 0.1 million baht. PARTLY: >=50% per-code. Otherwise NOT reproducible.

Grid (worker; `phaseW0_worker_grid.csv`, 1,512 combinations): source tables cube_Sale_APD, cube_Sale_APD_2016,
Cube_Sale_APD_2, cube_Sale_APD_test, Cube_CES; every date-typed column (cube_Sale_APD 8, Cube_CES 6) plus the
integer year/month columns; Actual vs Actual+MPS (Cube_CES: Actual vs Actual+Backlog, per DATA_MAP); Omni vs all
channels; company all or each of cmp/sale_company (PEM, PDE, PEMC, PCE, PSP); exact vs normalised code.
Window 2026-01-01..2026-07-31. No table named like cube_Sale_APD2026 exists (18 sale/APD-named tables listed in
the worker report section 2). Repo `reference/pricelist.xlsx` contains 419 of the tab's 426 codes; 7 tab codes
are absent and 26 repo codes are not in the tab, so the tab's list is not that exact file; matching used the
tab's own 426 codes.

Best three combinations (CONFIRMED; all Actual, Omni, company field = PEM, exact code):

| Rank | Source / date field / company | 204 exact | 426 exact | 204 within 5% | months matching |
|---|---|---|---|---|---|
| 1 | cube_Sale_APD_2016 / createDate / cmp=PEM | 118 (57.8%) | 325 (76.3%) | 159 | 0 of 7 |
| 2 | cube_Sale_APD_2016 / createDate / sale_company=PEM | 118 | 325 | 159 | 0 of 7 |
| 3 | cube_Sale_APD_2016 / PODate / cmp=PEM | 118 | 325 | 159 | 0 of 7 |

The 426 figure is inflated: 207 of the 325 are example codes where tab and DB are both 0. Best per source
(204/426): cube_Sale_APD_2016 118/325; Cube_CES (ActualDelDate, Omni, PEM) 114/317; cube_Sale_APD 111/315;
the two other APD tables 0/222. The project's usual definition (cube_Sale_APD, Omni, Actual, createDate, all
companies): 99/204, 302/426; with cmp=PEM 111/204. Verdict counts over the grid: REPRODUCES 0, PARTLY 220,
NOT 1,292. No combination reaches 95% on either base.

Monthly totals: 0 of 7 months match within 0.1 in all 1,512 combinations, on all rows and on the 426 codes.
Best combination, all rows (million baht, Jan..Jul): 62.57 / 84.57 / 101.51 / 87.25 / 94.10 / 89.78 / 77.87
(597.65); restricted to the 426 codes: 41.68 / 40.62 / 49.10 / 44.37 / 38.42 / 34.87 / 38.59 (287.66). Tab:
66.2 / 67.1 / 82.1 / 80.1 / 84.3 / 77.1 / 35.4 (492.4). The smallest 7-month total absolute error over the grid
is 111.5 million. Codes with sales among the 426: 219 (best), 223 (usual definition) vs the tab's 204. `cost`
and `saleGM` variants also do not match (worker section 3).

Unmatched codes (best combination; `phaseW0_worker_unmatched.csv`): 101 of 426 (86 real, 15 example). In all
101 the DB is higher than the tab and in none lower; over the 204 real codes DB 838,647 vs tab 806,935 (+3.9%).
The gap is not one common cut-off: for 35 of the 101 some createDate prefix reproduces the tab value (implied
dates 2026-01-16..2026-07-22), for 66 no prefix does.

Cut-off dates: no cut-off fits. The createDate cut-off peak is a 27-day plateau (2026-07-30..2026-08-25), i.e. no
effective cut-off. The best any-field cut-off is plan_date <= 2026-08-04/05 at 157/204 (76.9%), which matches
1 of 7 months; forecast_date <= 2026-08-05 gives 154/204. Neither reaches 95%; **no cut-off date is inferred.**
Row-id cut-offs and every single-attribute exclusion also fail (best +4 codes; the usual definition gains +12 by
excluding cmp=PCE, 99 -> 111). Numeric row filters (qty<=0, sale=0) were not tested.

Data drift (CONFIRMED, worker section 4): between cube_Sale_APD_2016 (2026-09-09) and cube_Sale_APD
(2026-09-28), 152 more Omni Actual rows fall in the window and 631 row ids changed status. INFERRED: because the
tab predates both by 5 weeks, drift alone could produce "DB higher than tab"; this could not be tested because no
dated August state was pulled and the DB has no per-row load date.

Prior claims checked (from the database): (1) "106 exact, 98 lower" - PARTLY CONFIRMED: 99 exact, 105
mismatched, all 105 with the tab lower than the DB. (2) "No cut-off between 1 Jul and 25 Aug fits" -
CONFIRMED. (3) "18 zero-history codes had Omni sales Jan-May" - REFUTED as stated: 15 on that definition
(21 for Jan-Jul). (4) "Monthly totals do not match Omni totals" - CONFIRMED.

## 3. Part 3 - example-badge codes that have sales (`phaseW0_worker_part3_codes.csv`, `_part3_rows.csv`)

Under the best combination 15 example-badge codes have Jan-Jul qty > 0; 21 under the usual definition (union
21). By cause (CONFIRMED rows; causes for B and C are INFERRED as explanations):

| Cause | Count | Codes |
|---|---|---|
| Code string (dotted twin; DB stores only the undotted string) | 2 | VT-F-99-010203., VT-F-99-010303. |
| Company (all rows cmp=PCE) | 1 | HS-F-99-0303 |
| Status (Actual now, MPS in the 2026-09-09 table; inferred it was MPS before the tab) | 3 | TF-F-99-2407223B1, RS-F-99-070005, CA-F-99-020102 |
| Unexplained (pass every tested filter: Actual, Omni, PEM, exact code, in window) | 15 | TF-F-99-2804223B1, TF-F-99-3204223B1, TF-F-99-2104223B1, EEE-F-FL-5920-353-00700, RS-F-99-041001, -041002, -041033, -041006, -041035, -041007, -041008, RS-F-99-130011, CT-F-99-020512, CT-F-99-020726, HS-F-99-1031 |

Whether the 15 were loaded after the tab date cannot be seen (no per-row load date). The worker's four causes
listed no date exclusion for any of the 21.

## 4. Part 4 - Min and Max of the 81 codes (`phaseW0_worker_minmax_*.csv`)

- File "Stock ของ PEM101 ณ วันที่ 30-03-2026.xlsx": NOT FOUND (worker searched D:\ work folders to depth 4-5 and
  the user's Downloads, Desktop, Documents; a full-drive Glob timed out at 20 s, so absence is not proven for the
  whole disk). The PEM101 stock team must supply it.
- Cube_Inventory_Exact (one load 2026-09-28 21:40-21:41; 725 rows for the 81 codes in 28 warehouses): tab Min
  non-zero for 58 codes, Max non-zero for 75. **Exact matches where the tab value is non-zero: 0 of 58 (Min) and
  0 of 75 (Max) under every aggregation tried** (sums, max, latest timestamp, each warehouse, any single row).
  The highest raw counts (Min 23/81, Max 6/81) are all 0-equals-0. Limit: the file is dated 2026-03-30 and the
  table is a 2026-09-28 state; a mismatch could reflect six months of change. Confidence high that no
  inventory-table aggregate reproduces the tab; what the tab's Min/Max are is unverified. The repo's
  phaseE1fix_2_current_minmax.csv (66 of the 81 codes) also matches in none (ad-hoc, not pursued).

## 5. Part 5 - Validator (independent recomputation: own parser and own DB connection)

| Figure | Worker | Validator | Result |
|---|---|---|---|
| Best combination exact, real codes | 118/204 | 118/204 | MATCH |
| Best combination exact, all codes | 325/426 | 325/426 | MATCH |
| Mismatch direction / DB vs tab qty | all DB>tab; 838,647 vs 806,935 | same | MATCH |
| Monthly totals all rows | 62.57/84.57/101.51/87.25/94.10/89.78/77.87 | same | MATCH |
| Monthly totals, 426 codes | 41.68/40.62/49.10/44.37/38.42/34.87/38.59 | same | MATCH |
| Months matching tab | 0 of 7 | 0 of 7 | MATCH |
| Codes with sales | 219 | 219 | MATCH |
| Usual definition | 99/204, 302/426 | 99/204, 302/426 | MATCH |
| VT-F-99-010203. (code string) | | code string | MATCH |
| HS-F-99-0303 (company) | | cmp=PCE | MATCH |
| RS-F-99-070005 (status) | | MPS in _2016, Actual in cube_Sale_APD | MATCH |
| EEE-F-FL-5920-353-00700 (unexplained) | | passes every filter | MATCH |
| RS-F-99-041001 (unexplained) | | passes every filter | MATCH |

These are independent recomputations (separate parser, separate pull), not re-reads of the worker's query. The
Validator did not query the tables' timeStamp; the agents pulled about 20 minutes apart (worker files 09:55, Validator report 10:13, file timestamps) on
2026-09-29 and all figures agreed, so no refresh in between is evident.

## 6. Part 6 - verdict per part of the tab

- **Per-code history: real data, partly reproduced.** Known: 99-118 of 204 codes match exactly at the tab's
  own non-round quantities (unlikely by chance), every mismatch has the tab lower than today's DB, and the
  closest definition is Omni, Actual, cmp=PEM, createDate Jan-Jul (118/204, 57.8%, cube_Sale_APD_2016). Not
  known: the exact definition or table behind the tab, and whether an earlier data state (drift) explains the
  remaining gap - untested for lack of a dated August snapshot. Confidence: high for the match counts, low for
  the cause.
- **Monthly company totals (Section 1): not reproducible from the database.** 0 of 7 months in 1,512
  combinations; nearest total error 111.5 million baht. The tab's Forecast, Production Plan and Actual
  Production rows are identical to its Actual row.
- **KPI figures: not reproducible from the database.** 492.4 million total: no combination lands on it
  (best 597.65 all rows, 287.66 on the 426 codes). 204 codes with sales: DB gives 219-223 (204 is the tab's own
  real-badge count, confirmed internally). 426 price-list codes: repo pricelist has 419 of them. 81 Max-Min
  codes: internal count confirmed (81 rows flagged), source unverifiable.
- **Min and Max: not reproducible from the database.** 0 of 58 / 0 of 75 non-zero exact matches; the source
  file was not found.

## 7. Two positions, neither chosen (for the user to decide)

The user's stated understanding is that the tab's figures are hypothetical. The database evidence is that
per-code history is in part real-data-derived (Section 6), while totals, KPIs and Min/Max cannot be tied to any
database definition. Both are stated here; how the tab is labelled for readers is left to the user.

## 8. Further work found, NOT done

1. Ask the cube/ETL owners which table or dated snapshot "Cube Sale APD2026" was (a dated August state would test
   the drift hypothesis); worker did not pull cube_Sale_Snapshot, sale_Fact, cube_Sale (one-connection rule).
2. Obtain the 2026-03-30 PEM101 stock file from the PEM101 stock team and the original "Price List Q4'2025 R.1"
   file (repo file differs by 7+26 codes).
3. Test numeric row filters (qty<=0, sale=0) and the 15 unexplained codes' load dates.
4. Compare the tab's Min/Max with this project's own Max-Min outputs as a separate task.

## 9. Files, commit hygiene

Committed: this report, the worker and Validator reports, scripts, and CSVs whose columns carry no customer
data. **`phaseW0_worker_attr_exclusion_scan.csv` is NOT committed:** it lists customer names/IDs and a handler
tag as exclusion values (public repository); regenerate with `phaseW0_worker_script.py`. The worker report's one
handler tag was redacted. Sensitive-content scan of committed files: see STATUS.md entry.
