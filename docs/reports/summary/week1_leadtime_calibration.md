# Week 1, items 1.3 and 1.4: production time, lead time per item, PEM101 recalibration on 92 items (2026-10-05)

Plan: STATUS.md, "Work plan, decided 2026-10-05", week 1. Code: `src/lead_time_v1.py`, `src/investigations/week1_recalibration.py`; definition in
METRICS.md Sec.5 ("Item lead time, version 1"). One database session (one connection, SELECT only, closed after the last query; 19 queries); the
saved outputs (outside the repository, for the Validator) are in the session scratch folder `scratchpad\week1b\dbout\` with `query_log.jsonl`.
Recorded outputs (kept local, git-ignored, hashes in the integrity files): `output/summary/item_lead_time_v1.csv` (+ `_integrity.json`),
`output/summary/week1_recal_*` (+ `week1_recal_integrity.json`). Nothing was switched on any page, builder or job.

Levels: **V1** one computation by the investigating agent, **V2** re-derived by the Validator (see the end).

## Part 0. Production time: proving the sources before use

**Cube_Production_Order** (4,719 rows; job, item, planned quantity, status Printed / Released / open, start_date, end_date, actual_date). The table
repeats the same job and item on several rows, so each (job, item) is counted once: 229 job-items of the 445 scope items with start_date from
2023-01-01. Tests against the job's material issues (cube_inventory_tran type B, `project` = job number, sub-jobs `ROOT.001.002` included; 205 of the
229 have issues), the materials' receipts (type A) and cube_final's final_date (131 job-items with issues and a final date):

| Column | Against the job's first material issue | Against the last issue | Against cube_final.final_date | Reading |
|---|---|---|---|---|
| start_date | median -1 day (p10 -5.6, p25 -2, p75 0, p90 0) | before the last issue in 100% (median -28) | final_date after start_date in 100% (median 40 days) | **Order release date**: the day the order is opened, within about a day before the first material is issued (before it for 58%, on the same day for 41%, after it for 1%). It is not a time stamp of work. |
| end_date | median +36 days | median +5 | final_date median 0 days from it, 47% before it | **Planned finish.** |
| actual_date | **differs between repeated rows of the same job and item in 111 of 229 job-items**; equals end_date in 62% to 74% of rows depending on which repeated row is kept | median -3 (first row kept) | final_date median +17 days later (first row kept) | **Not a reliable finish date**: it varies by row and the final record follows it; meaning *undetermined*. Every figure for it depends on the row choice (Validator: first row 62%, latest row 74%). |
| cube_final.final_date | median +40 days | **median 0 days (p25 -3, p75 +2.5)** | | **Booked about when the last material is issued**: the job lot's completion record. |

The last material receipt before start_date is a median 1 day earlier (p75 5): materials are received continuously, so it tells nothing about when a
job starts. **No column marks the actual start of work.** What the tests support is the interval from the order's release (start_date, about the first
material issue) to the completion record (final_date, about the last issue): the **throughput time of a job lot**, not a per-unit assembly time. **V1.**
(An earlier count that did not remove repeated job rows inflated the number of jobs; the figures above count each job and item once.)

**Cube_Standard_Time** (12,847 rows; 12,815 distinct `rmid`; columns id, rmid, user_edit, wino, dwgno, test_method, wi_check, test_report, std1..std4):
**one row per raw-material code** with a work instruction (`QWI-08-03-900INC-nn`, an incoming-inspection instruction), a test method (100%
inspection 4,302 rows, AQL sampling 8,545) and four numbers (std1 0 to 30, std2 0 to 90, std3 0 to 240, std4 0 to 15; units *undetermined*). It is the
**incoming-inspection plan of materials**, not production time. Coverage of the 92 stock_policy items: **6 of 92 as rmid** (five purchased fuse-cutout
parts and one surge arrester, with empty std values); of the 228 BOM materials: 109. No product-type key. **Not used.** **V1.**

**Source of production time per item**, in the order standard, measured, assumed:
- standard: **0** items (Standard_Time is not production time);
- measured (own median start_date to latest final_date over at least 3 matched jobs): **5** items (EEE-F-FL-1040030005 44 days, -1040030006 24,
  -1040030010 36, EEE-F-HC-1040020001 65, EEE-F-LT-1040020100P 61). Test of the rule before use: leave-one-job-out over the 19 items (of all 445 scope
  items) with at least 3 jobs, 71 jobs: item median error 21.4 days against 29.1 for the global median of all 291 matched job-items (26 days). The rule is
  better than the global value but modestly, and few items qualify (on the 445-scope items alone, 9 items and 27 jobs, the item median is not better: 31.3 against 30.2 days, so the support rests on the all-item test) (6 of the 92 have 3 or more jobs; one of them has no usable BOM and takes the
  assumed values);
- assumed: **87** items, one configured value, `lead_time_v1.production_days_assumed` = 26 days (median of the 291 matched job-items), commented
  in config as an assumption.

## Part 1. Lead time per item

Walk: Cube_BOM_Exact, one level; header rows (Sequenceno 0, blank component) and the 104 `Machine Hour` rows (B101-DL1, B101-OH1) excluded.
92 items: **87 have a BOM, 5 have none** (no row in Cube_BOM_Exact). 525 component lines, 228 distinct materials. Statistic per material: the
**median** (small samples, 0 to 730 day outliers); order: observed, supplier quoted (non-zero Cube_PriceList.DeliveryTime), assumed.

- Observed lead times (PO date to first receipt, one per PO and item): **4,166** for 138 of the 228 materials; per-material medians p50 41.8, p75 52.4,
  **p90 63.2**, max 103. The assumed fallback for a material with no record and no quote is therefore **63 days** (`fallback_material_days`).
- **Limit found while building this, 36 items: 114 component lines (82 materials) are in-house sub-assemblies (code kind W, e.g. CA-W-99-010101) with
  no purchase record. Their own BOMs are not in the saved pull (they were not read in the single database session).** They are listed and left out of
  the maximum. **34 items have only such components and, with the 5 items that have no BOM, 39 of 92 items carry the assumed values (63 + 26 days =
  89).** This is a real limitation of version 1: for those 39 the lead time is an assumption, not data.

**Result** (`output/summary/item_lead_time_v1.csv`, SHA-256 `e83de686b194e005e359987f0857cc04c44a831a21be5410b25803d4e4a3c621`):
- item lead time, all 92: median **89 days**, range **43 to 129** (p25 74.4, p75 89, mean 84.5); the 53 items with a walkable BOM: median 75.5, range
  43 to 129;
- the 53 walkable items: bottleneck material observed for 50, assumed for 3 (no record or quote; 2 items have one supplier-quoted material but their
  bottleneck is observed); **any supplier-quoted: 2 items; any assumed material: 3 items; all materials observed: 48 items**;
- no BOM: 5 items; BOM holding only in-house sub-assemblies: 34 items (assumed values, labelled in the `note` column);
- most frequent bottleneck materials: **FC-A-38-00201 (4 items), FL-R-00-38002 (3), FC-R-CP-00002 (2)**, then FL-R-00-00202 and HC-R-01-0035 (2 each).
**V1.**

## Part 2. PEM101 recalibration on the 92 stock_policy items (METRICS Sec.20, unchanged method)

Same simulation, grid, windows, tolerance (not_late within 3 points and stock value within 15 percent, both windows) and three stock definitions as
phaseJ3_run_calibration.py; imported, not copied. Changes, all deliberate: (a) the 92 items; (b) each item's replenishment lead time fixed at its Part 1
value (rounded to whole days, 43 to 129) instead of a grid dimension; (c) ForecastDelDate as the due date (it was already the J3 convention; the
J3 targets 97.70% and 98.28% were reproduced to four digits with the new function on the cached 128-item data before use); (d) data of 2026-10-05
(validation to 2026-09-30, cached phase I data ended 2026-08-31); (e) unit cost from the frozen phase I cache, 77 of the 92 items have one, the other
15 (outside the 128-item pilot) count 0 in stock value on both sides. A **control** run repeats the old method (lead time a grid dimension, 1 to 90 days)
on the same 92 items and data, so the lead time's effect can be read apart from the item set and the data.

**Observed (today's point):** not_late (unit-weighted, ForecastDelDate) calibration 2024-01 to 2025-12 **97.34%** (20,195 rows, 2.55M units); validation
2026-01 to 2026-09 **98.34%** (8,775 rows, 1.13M units); current stock value (sellable warehouses FG01, FG21, WH21) **THB 15,491,483** (fg_prefixed
11,724,643; all stock-holding 15,507,308). Current calibration for comparison: 98.28% and THB 18,247,625 on the 128-item pilot scope.

**Result with per-item lead times: the calibration FAILS to match observed behaviour. Distinct ensemble members after deduplication: 0** (passing
combinations by stock definition: 0, 0, 0 of 413 grid points). Nothing was adjusted to force a match. The figures:
- 27 of 413 points are within the not_late tolerance in both windows; none of them is near the observed stock: the closest (r 5 months, S 6, review 14
  days) gives not_late 95.9% (calibration) and 96.1% (validation) at stock value **THB 33.8M and 29.7M against 15.5M observed (+118% and +92%)**;
- 15 points are within the stock tolerance in both windows; the best of them reaches validation not_late **83.7%** (r 3, S 5, review 7), against 98.34%
  observed;
- so with a lead time of 43 to 129 days per item the simulated policy needs about **twice the observed stock value to reach 96% service**, and
  matching the observed stock gives 84% or less. The calibrated today's point and the trade-off from today to 99% are **undetermined** (no ensemble).

**Control (old method, lead time free 1 to 90 days, same 92 items and data): 36 distinct members** (passing 28, 8, 28 by definition): reorder level 0.25 to
2.0 months, order-up-to 1.5 to 2.5, review interval 1 to 14 days, **replenishment lead 1 to 30 days (median 3)**. The members' median simulated validation
point is 96.95% at THB 14.77M (observed 98.34% and 15.49M). Trade-off (locked config grid, window 2024-07-01 to 2026-09-30, median over members):
at the 98% bin THB 15.64M (min 10.56M, max 23.38M) against observed 15.49M (-1.0%); the median curve gives 97.9% at today's stock; **to 99%: THB 21.23M,
+35.7% over the 98% bin (members' range +26.2% to +81.8%)**.

**What this says (inferred):** the data reproduce today's service and stock only if replenishment takes **1 to 30 days effectively**, not the 43 to 129
days that the slowest purchased material plus job throughput imply. Likely reasons, none tested here: raw materials are held in stock, so a finished-goods
reorder does not wait for a new purchase; and 39 of the 92 lead times are the assumed 89 days. The method was not changed.

**Against the current calibration** (grid fitted on the 128-item pilot scope; curve and Min/Max on 112 items, **not 76: the 76 in the page note and STATUS
is the count of `finished_goods_stock` policy items, the simulation covered the 112 `eligible_for_policy` items; verified in
`phaseJ3_2_grid_PEM101.csv` n_items_simulated and `phase23_dense_grid_PEM101.json`**): 80 distinct members, lead 1 to 30 days (median 5), reorder 0.25 to
2.0, order-up-to 1.5 to 3.0, review 1 to 30; median curve THB 17.21M at the 98% bin against 18.25M today (today +6.0% above), 98.2% at today's stock; to 99%:
THB 23.67M (+37.5%, range +26.1% to +50.5%). The control on the 92 items (36 members, same lead range 1 to 30) lands in the same place: stock at 98% and the
cost of 99% (+35.7% against +37.5%) agree within two points. Only the per-item lead time breaks the fit.

Saved beside the current outputs, hashed, not read by any page or builder: `week1_recal_grid_PEM101_92.csv` (413 points), `week1_recal_members_PEM101_92.csv`
(empty), `week1_recal_control_grid_PEM101_92.csv` (4,130), `week1_recal_control_members_PEM101_92.csv` (36), `week1_recal_control_tradeoff_*`,
`week1_recal_targets.json`; hashes in `week1_recal_integrity.json`.

## Part 3. PEM101 evidence file (local, git-ignored)

`output/pem101_evidence/PEM101_undetermined_20261005.xlsx` updated in place, sheet "สรุป": header of the label column changed; "mixed" values read
"ปนกัน · <type> <share>", all percentages whole numbers (label shares and the 14-day share); the column on production before the order removed; last
column "ฝ่ายตอบ" with a dropdown (เก็บ stock, ผลิตตามสั่ง, ไม่ขายแล้ว) on the 20 rows; the English notes replaced by the four approved lines. The
sales note says the figures include orders received but not yet delivered: checked, status MPS rows are 762 of 818 dated after 2026-10-05, so the
Actual + MPS basis does include them.

## Validator

A separate Validator (no database; it did not read the code, the lead-time file or this report) re-derived from the saved pulls and then compared with the figures:
- **Part 0:** start_date minus first issue, minus last issue, end_date minus first and last issue, the counts (229, 205, 139, 131), the share before the first issue and the last-receipt test: **MATCH**. **Discrepancy: actual_date** (it differs between repeated rows of a job-item; the figures depend on which row is kept: first row 62.4% equal to end_date, latest row 74%); the report now says so. The Validator's reading of the other columns agrees (start = release near the first issue; end = planned; final about the last issue); it marks the readings *inferred*, as here.
- **Production time:** the leave-one-job-out test (19 items, 71 jobs, 21.4 against 29.1 days, global median 26) and the source for ten items: **MATCH**. The two HS items it was given (HS-F-99-0151, HS-F-99-0361) are not among the 92 and take the assumed values.
- **Lead time and bottleneck:** all 92 lead times **MATCH** (0 differences; median 89, min 43, max 129); bottleneck material identical for the 53 items with a material; for the 39 without one the labels differ ("(assumed)" and "(none)") for the same value; source counts 50 observed, 0 quoted, 42 assumed.
- **Targets and the per-item-lead grid:** observed not_late 0.9734 and 0.9834, stock value THB 15,491,483.08, 77 of 92 items with a cost: **MATCH** to four digits; its 16 grid points reproduce the claimed nearest points and **no point passes**. Its extra test with one 5-day lead for every item gives service of 98% or more but 2.7 to 4.6 times the observed stock.
- **Control** (old method, lead free 1 to 90 days, 36 members): **not independently re-derived** (the Validator ran different grid points); level V1.

## What remains undetermined

- Whether a finished-goods reorder waits for raw-material purchase (why effective replenishment is 1 to 30 days); the sub-assembly BOMs of 36 items
  (version 1 does not walk them); the unit of Cube_Standard_Time's std1..4; what Cube_Production_Order.actual_date records.

## Found, not done (assigned to a week)

- Week 1: read the BOMs of the in-house sub-assemblies (82 W-codes) so that the 39 items with assumed lead times can be walked; this needs a database
  read the single session of this task did not include.
- Week 1: decide how Max-Min v1 uses a lead time (89 days) that the calibration does not support (control: 1 to 30 days); the item lead times and the
  calibrated effective lead differ and both are recorded.
- Week 2: Cube_Production_Order release dates and planned finish dates as production load (the dates' meaning is now established).
