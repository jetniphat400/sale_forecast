# phaseW0 Validator report (independent recomputation)

Label for every figure below: CONFIRMED-BY-INDEPENDENT-RECOMPUTATION (own parser of index.html + one read-only DB
connection, script `phaseW0_validator_script.py` in the scratchpad; analysis in `an.py`). Confidence: high for
counts/sums (direct query and parse); no project verdict is given. Did not read any phaseW0_* file.

## Tables as pulled 2026-09-29
- cube_Sale_APD_2016: 142,058 rows, createDate 2016-01-04 .. 2026-12-01.
- cube_Sale_APD: 52,826 rows, createDate 2021-01-11 .. 2026-12-01.
- Both have a `timeStamp` column; I did not query it (one-connection rule), so refresh time is unverified. Tables refresh, so
  figures could differ from the worker's if a refresh occurred. Nothing below differed from the worker's figures, so no refresh explanation was needed.
- Tab parse: 426 rows, 426 unique codes (204 'ข้อมูลจริง' real, 222 'ตัวอย่าง' example); Section 1 Actual row = 66.2/67.1/82.1/80.1/84.3/77.1/35.4.
  All 204 real codes have hist>0; all 222 example codes have hist=0.

## (1) D* per-code exact match vs tab Hist Qty
| base | mine | worker | verdict |
|---|---|---|---|
| 204 real | 118/204 | 118/204 | MATCH |
| all 426 | 325/426 | 325/426 | MATCH |
- Mismatching real codes: 86, all DB > tab, 0 with DB < tab: MATCH (worker: all DB > tab).
- 204 real codes total qty: DB 838,647 vs tab 806,935: MATCH. (All 426: DB 839,269; DB>tab 101 codes, DB<tab 0.)

## (2) Monthly totals, million baht, D*
- All rows of definition: 62.57/84.57/101.51/87.25/94.10/89.78/77.87, total 597.65: MATCH worker.
- Restricted to the tab's 426 codes: 41.68/40.62/49.10/44.37/38.42/34.87/38.59, total 287.66: MATCH worker.
- Months matching the tab (66.2/67.1/82.1/80.1/84.3/77.1/35.4) within 0.1: all-rows 0/7; 426-code 0/7: MATCH worker (0).
- Codes among the 426 with D* qty>0: 219 (MATCH worker 219); tab KPI/real-badge count: 204 (MATCH).

## (3) D0 (cube_Sale_APD, Omni Channel, Actual, window, all companies, exact code)
- 99/204 real and 302/426 all: MATCH worker (99/204, 302/426). DB>tab for 105 real mismatches, 0 DB<tab; D0 real total 840,907 vs tab 806,935.

## (4) Five zero-history example-badge codes (all have tab hist 0)
Rows pulled from both tables with createDate >= 2026-01-01 (itemcode LIKE prefix, then judged by stored string).
1. VT-F-99-010203. : DB stored string is only `VT-F-99-010203` (no dotted rows in either table). Excluded by code-string matching. **MATCH**.
   Side fact: the undotted twin is itself a tab row (real badge, hist 145; D* 151).
2. HS-F-99-0303 : every row has cmp=PCE (4 rows Apr-Aug); D* requires cmp=PEM. Excluded by company. **MATCH**.
3. RS-F-99-070005 : rows are PPS/PEM Tendering (8 rows May, excluded by channel regardless) plus one Omni Channel PEM row
   (id 275406, 2026-06-29, qty 30). That row is status MPS in cube_Sale_APD_2016 (excluded by status) and Actual in cube_Sale_APD.
   Status comparison (same ids): APD_2016 status differs from APD for ids 272670 and 273493 (Tendering, MPS vs Actual) and 275406; all other rows Actual in both.
   Explanation = status (with channel excluding the Tendering rows). **MATCH**. Note: under D0 (APD, Actual) this code would count 30, yet the tab shows 0.
4. EEE-F-FL-5920-353-00700 : id 271211, 2026-04-21, Actual, Omni Channel, cmp PEM, qty 390 in APD_2016 passes every D* filter (D* qty 390). A second row (id 280559, 2026-09-09) is outside the window. **unexplained (passes every filter); MATCH** worker.
5. RS-F-99-041001 : ids 272880 and 275190 (2026-05-18, Actual, Omni Channel, PEM, qty 20+10) pass every D* filter (D* qty 30); id 277270 (30) is MPS. **unexplained; MATCH** worker.
   Side fact: the `-1` variant (RS-F-99-041001-1, D* qty 100) is not a tab row.

Not established: why the tab (built from an external file per its header) omits these; only which D* filters would exclude the rows.
