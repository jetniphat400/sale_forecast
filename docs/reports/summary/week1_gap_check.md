# Week 1 gap check (read-only), 2026-10-05

Plan: STATUS.md, "Work plan, decided 2026-10-05". Goal: what the database already holds for Week 1 (Max-Min v1 with lead time per item) and
Weeks 2 and 3 (operation plan, material plan). One database session, one connection, SELECT and metadata queries only (isolation level READ
UNCOMMITTED, no writes), opened 2026-10-05 and closed after the last query. Date filters on every large table (cube_inventory_tran from
2025-10-06 or 2024-01-01); no table was read whole except the small ones (Cube_Production_Order 4,719 rows; cube_final 45,671 rows; distinct id
lists of Cube_CES and cube_Sale_APD).

**Saved query outputs (outside the repository, for the Validator):** the session's scratch folder `scratchpad\week1\` under the Claude Code
session temp folder: `dbout\` (99 CSV files named `a01_...` to `n02_...`) and `query_log.jsonl` (96 queries: name, SQL text, columns, rows,
seconds). No customer names, contract ids or employee names are written in this report.

Levels: **V1** = one computation by the investigating agent; **V2** = the Validator re-derived it from the saved outputs (see "Validator").
Rule: where the evidence is insufficient the word is *undetermined* with what was tried.

---

## 2a. Catalogue

- Databases on the server: 15 listed; 4 online and accessible to this login: `master` (5 objects), `tempdb` (0), `msdb` (21), `salewarehouse`
  (111: 108 tables, 3 views). All 137 objects in the accessible databases carry SELECT permission (`HAS_PERMS_BY_NAME`). Only
  `salewarehouse` holds project data; `master` and `msdb` are system objects and not relevant. The other 11 databases are not accessible.
  (`a01_databases.csv`, `a02_all_objects.csv`, `n01_object_select_perm.csv`, `n02_msdb_master_perm.csv`.) **V1.**
- Row counts are from `sys.partitions` (metadata). Of the 111 `salewarehouse` objects, **21 are named in DATA_MAP.md** (exact name, whole word),
  14 more only in STATUS.md, 76 in neither.
- **Relevant tables not in DATA_MAP.md** (names suggest production, jobs, receipts, purchasing, suppliers, delivery time or capacity). Item
  joins are to the 445-code project scope ("FG scope") and, for components, to the 231 raw-material codes on the BOMs of PEM101's 92
  stock_policy items ("RM"); forward = scope codes found in the table / scope size, reverse = table's distinct codes that are in scope /
  table's distinct codes.

| Table | Rows | Date columns (min..max) | Item key | FG scope forward / reverse | RM forward / reverse |
|---|---|---|---|---|---|
| Cube_Production_Control | 146,717 | ReceiptDate = ControlDate 2026-01-06..2026-10-02 | Itemcode | 72/445 (16.2%) / 72/114 (63.2%) | 0/231 / 0/114 |
| Cube_production | 104,336 | receiptdate 2026-01-05..2026-10-02 | itemcode | 90/445 (20.2%) / 90/174 (51.7%) | 0/231 / 0/174 |
| Cube_Production_Order | 4,719 | start_date 2011-09-21..2026-10-02; end_date, actual_date to 2029-01-30 | itemcode | 141/445 (31.7%) / 141/2,175 (6.5%) | 43/231 (18.6%) / 43/2,175 |
| Cube_JobCost | 30,665 | none (load time only) | Item | 282/445 (63.4%) / 282/10,617 (2.7%) | 75/231 (32.5%) / 75/10,617 |
| Cube_JobCost_Detail | 277,284 | none | Item | 57/445 (12.8%) / 57/16,726 (0.3%) | 217/231 (93.9%) / 217/16,726 |
| Cube_BOM_Exact_V2 (levels 1-18) | 518,501 | none | ItemFG | 389/445 (87.4%) / 389/39,520 (1.0%) | 85/231 (36.8%) / 85/39,520 |
| Cube_Compare_Plan_Actual_Bom (ledger lines) | 274,163 | Date 2025-10-06..2026-10-30 | Item | 266/445 (59.8%) / 266/9,304 (2.9%) | 135/231 (58.4%) / 135/9,304 |
| Cube_FG_Temp / ItemFG_Temp (item lists) | 11,581 / 5,340 | none | ItemFG | 324/445 (72.8%) / 318/445 (71.5%) | 0/231 |
| cube_po_bom (PO lines, ref_job) | 312,616 | create_datetime 2023-01-03..2026-10-02; deldate | itemcode | 81/445 (18.2%) / 81/13,889 | 138/231 (59.7%) / 138/13,889 |
| cube_pr_bom (PR lines) | 183,965 | create_datetime 2025-01-02..2026-10-02; delivery | itemcode | 10/445 / 10/7,884 | 125/231 (54.1%) / 125/7,884 |
| Cube_Incoming_Receipt | 70,348 | income_date 2016-07-21..2021-10-04 | itemcode | 18/445 | 109/231 (47.2%) |
| Cube_tobe_received (open PO lines) | 1,580 | order_date 2021-11-12..2026-10-02 | itemcode | 8/445 | 77/231 (33.3%) |
| Cube_Standard_Time | 12,847 | none | none (columns rmid, wino, dwgno, test_method, std1..std4) | not testable | not testable |
| Cube_Vendor_List | 225,644 | createDate 2003-07-03..2026-10-04 | none (supCode, AVL change log) | not testable | not testable |
| cube_supplier_data_exact_pdem | 8,208 | updated_at | none (supplier master) | not testable | not testable |
| Cube_Incoming / Cube_Incoming_Wait | 23,636 / 2,243 | none / 2018-01-23..2022-09-29 | none / itemcode | not testable / 6/445 | |

  Also seen and judged not relevant: Cube_Inventory_Batch (597 rows, 0/445), cube_pr (201,426 rows, no scope item), Cube_pr_monitoring
  (2019-2023, 1/445), Cube_Facility_Request, Cube_QMS, GL, invoice and AR/AP tables. **V1** for every row.
- Notes: Cube_BOM_Exact_V2 holds 87.4% of the 445 scope codes as finished items; DATA_MAP records 301/351 (85.8%) for Cube_BOM_Exact (a
  different scope, so the two are not compared here). Cube_JobCost has planned and actual quantity and cost per production order and item but
  no date column.

## 2b. Cube_PriceList.DeliveryTime

**What it is.** One row per **supplier and item** price-list line: Company, ItemCode, Description, SupplierNumber, SupplierName, Condition, Unit,
Price, SupplierItemcode, Currency, POSize, **DeliveryTime**, PaymentCondition, timestamp. DeliveryTime is text of the form "N Days" (value list
`j11_deliverytime_values.csv`: 30 Days 17,917 rows, 0 Days 11,503, 15 Days 4,400, 7 Days 4,331, and 95 other values). It is a quoted or
standard delivery time of that supplier for that item, in days, not a per-order figure. **0 Days appears on 11,503 of 48,722 rows (23.6%
table-wide; 25.1% of the rows for the raw materials below)**; whether a 0 means "immediate" or "not filled in" is *undetermined* (no column
says). **V1.**

**Comparison with observed lead times.** Raw materials: the 231 components on the BOMs of PEM101's 92 stock_policy items (Cube_BOM_Exact; 82
rule-based plus the 10 decided on 2026-10-05). Price list rows for them: 467 rows, 143 items (61.9%), 45 suppliers; listed days above 0:
median 30, p25 23, p75 58, max 128. Observed: PO date (Cube_PO_Exact) to first receipt date (Cube_ReceiveRM, key PO number plus item), 0 to 730
days, PO dates from 2023-01-01: **5,373 usable lead times for 138 items, median 42, p75 62**, mean 45.8 (phase R, a different set of 209
materials: median 41, p75 60, DATA_MAP.md; consistent). PO planned date minus PO date: median 37, p75 56 (n 5,558).

| Level | n | Pearson | median (observed minus listed) | observed <= listed | within 7 days |
|---|---|---|---|---|---|
| Item and supplier pair (observed median per pair vs listed days) | 151 | 0.70 | **-15 days** | 80.1% | 23.2% |
| Item, listed median over suppliers | 137 | 0.57 | -7.5 | 70.1% | 27.7% |
| Item, listed minimum over suppliers | 137 | 0.31 | 0 | 53.3% | 38.0% |

The PO's own planned lead (planned date minus PO date) against the listed days for the same pairs: 151 pairs, Pearson 0.67, median planned
minus listed -15 days. **Finding:** DeliveryTime tracks the observed order-to-first-receipt time moderately (r 0.7 per supplier and item), and is
on average **15 days longer** than what was observed for the same supplier and item; it covers 62% of the raw materials and a quarter of its
rows read 0. It cannot replace the observed distribution; it can fill the gap for materials with no PO history (77 of the 209 in phase R).
Confidence: medium; computed on 21 supplier codes that appear in both the PO and the price list (all 21 PO suppliers match). **V1.**

## 2c. Cube_Production_Control

- **What it is:** per-unit quality-control measurements on the shop floor. Columns: id, ReceiptID (barcode of the unit), StationID,
  StationName, Job, Quantity, ReceiptDate, ControlDesc (the dimension or test measured), **MinVal, MaxVal (tolerance limits), Val (measured value)**,
  Unit, Operator_Name, ControlDate, FinishDescription, Itemcode. Grain: one row per unit x control measurement (two to five rows per unit and
  station). 146,717 rows, 114 items (72 of the 445 scope codes, all PEM107-type CT/VT/RS items), 29 stations, 1,506 distinct item x station x
  control combinations. Units: mm 95,230 rows, turns (รอบ) 26,985, % 7,029, kilo-ohm, gram, G-ohm and others. **V1.**
- **MinVal and MaxVal against Cube_Inventory_Exact minimum and maximum:** not comparable. The 72 scope items in both tables: 990 control specs,
  **0 equal the item's inventory minimum or maximum**, and none of those 72 items carries a non-zero minimum or maximum in Cube_Inventory_Exact
  (summed over warehouses); the table has no warehouse column. Every spec has MinVal <= MaxVal (a tolerance band around Val). They are
  measurement limits, not reorder points (agrees with phase R). **V1.**
- **Production dates:** ReceiptDate and ControlDate are the same time stamp (the measurement time at a station), 2026-01-06 to 2026-10-02. There
  is **no production start or finish date** in this table. Station-level records with times are in Cube_production (below).

## 2d. cube_inventory_tran

**Transaction types, last 12 months (trans_date from 2025-10-06, all items, `e01`):**

| Type | Rows | Quantity | Warehouses | Classification (evidence) |
|---|---|---|---|---|
| B | 160,319 | out 19.62M (in 63) | 26 | **Issue.** 156,376 of 156,982 raw-material rows (99.6%) carry a job number in `project`; 97,025 (61.8%) read "Production: <job>"; issues from FG02, FMTO and FMTS with "CTR-<contract>" text (597 raw-material rows, 11 supplies) are issues to a customer contract. So B = issue to a production job, or to a customer when the text is a contract. |
| 150 / 151 | 26,405 each | out 21.90M / in 21.90M | 33 / 29 | **Transfer between warehouses** (an out row and an in row with the same document, item, date and quantity). |
| A | 20,544 | in 19.57M | 24 | **Receipt.** 18,205 rows (88.6%) have `orders` equal to a PO number in Cube_PO_Exact for the same item = **purchase receipt**. 2,339 rows have no `orders` and a job number in `project` = **receipt from a job** (810 items; warehouses W126 1,496 rows, QA 364, W121 78, WH22 76, W122 75, FG24 51, FG01 16). |
| H | 4,955 | in 977k (out 18) | 22 | **Return of issued material from a job.** 4,894 rows carry a job; of the 4,422 (job, item) pairs, 3,786 were also issued by B to the same job and item, and the quantity received is <= the quantity issued in 3,747 of them (99.0%; median ratio 0.92); 0 of 4,422 (job, item) pairs match a Production_Order (job, itemcode); descriptions include the Thai word for "return" (ส่งคืน). Not a finished-goods receipt. |
| N | 9,455 | in 2.8k, out 8.7k | 36 | Journal adjustments (JV vouchers: stock adjustment, move of RM into a job, cost); near-zero quantity. |
| J | 273 | out 14,788 | 5 | Issue at CL and W126 with invoice or claim texts; meaning *undetermined*. |
| T | 31 | none | 5 | Cost-only lines (freight, import duty, service); no quantity. |
| 190 | 86 | in 527 / out 527 | 8 | "Change of stock" (item re-coding); net zero. |

**Warehouse pairs (150 to 151, 12 months, `g05`):** QA to WH23 5,531 transfers (6.52M units), QA to WH26 3,609, QA to WH24 2,650, QA to WH21 2,451
(8.91M), QA to WH22 1,572, QA to WH27 1,056 (inspection released to the stores); WH24 to W124 1,025; WH23 to W3-2 847, to WH27 653, to W3-3 616, to
W3-1 392 (store to production line); FG01 to FG02 120 (9,905 units); WH21 to FG01 35. **Issues to production: type B with a job number. Receipts from
production: no type holds finished-goods receipts for the scope items;** type A rows without a PO and with a job number exist for semi-finished
R-coded items (tanks, clamps) but for **none of the 445 scope items**, and the finished items of Cube_Production_Order (start 2025 on) show only B, A,
150/151, N, H and J rows in the ledger (`k02`), the same types as components. The ledger's GL is "Raw materials" or "Supplies" only; finished goods
are not ledgered here (STATUS records the same: movement for 3 of 82 items). **V1.**

**Assembly time per finished item from the issue-to-receipt link: NOT estimable.** The 1,443 jobs (the Validator counts 1,426 with a different key trimming; every other figure agrees) that have both a B issue and an A job receipt give
first issue to receipt days median 0, p25 -5, p75 10, with 487 (33.8%) negative (the receipt precedes the first issue), because one job number is
shared across levels and sub-assemblies; and none of the scope items is among them. Other elapsed times that exist, with what they are:
- **Cube_Production_Order start_date to cube_final.final_date** (matched on job and item): 139 job-items for 103 scope items, median 36 days (p25 7, p75
  75, p90 131); this includes waiting and the date of the final record. **Cube_Production_Order** has job, item, planned qty, start_date, end_date,
  actual_date (equal to end_date in 30% of scope rows), status (Printed, Released, open); planned end minus start median 38 days (scope).
- **Cube_production** (PEM107 CT/VT items only, division 102): per unit (barcode) the time stamps of each station; first to last station per unit
  median 27 days (n 15,931 units), median over items 3.5 days; it includes waits between stations. standardtime and usedtime columns exist; their
  unit is *undetermined*.
Neither is an assembly time per finished item. **V1.**

## 2e. cube_final.ctrno against Cube_CES.ContractID

The join works (DATA_MAP recorded it as never exercised): the keys have the same format (`CTR-yyyy-nnnnn`).

| Direction | Match |
|---|---|
| cube_final distinct non-blank ctrno (11,860; 20,137 of 45,671 rows have a blank ctrno) found in Cube_CES ContractID (all dates) | **11,533 / 11,860 = 97.2%** (forward) |
| the same ctrno found in cube_Sale_APD contractid | 8,426 / 11,860 = 71.0% |
| Cube_CES distinct ContractID (71,453, all items and years) found in cube_final | **11,533 / 71,453 = 16.1%** (reverse; cube_final tracks production only) |
| cube_Sale_APD distinct contractid (20,957) found in cube_final | 8,426 / 20,957 = 40.2% |
| contracts of the 445 scope items, CtrDate from 2024-01-01 (14,875), found in cube_final by ctrno | 6,669 / 14,875 = 44.8% |
| (contract, item) pairs of those (37,826) found in cube_final | 11,403 / 37,826 = 30.2% |
| cube_final rows of scope items with final_date from 2024 (6,684 ctrno) found in Cube_CES | 6,579 / 6,684 = 98.4% |

Delivered contract-items 2024 on (Status Actual) that have a cube_final row, by item class (METRICS 23): PEM101 stock_policy **14.6%** (n 28,321),
PEM101 confirmed_to_order 89.8% (186), PEM101 conflict 70.3% (716); PEM107 confirmed_to_order 86.9% (726), conflict 96.4% (3,574), stock_policy 97.6%
(1,039). So stock items are mostly delivered with no production record on the contract; made-to-order items mostly have one.

**Times (contract-item level, 11,246 matched, delivered; production finish = latest `final_date` of the pair):** contract date to final_date median 6
days (p25 1, p75 18); final_date to ActualDelDate median 3 (0 to 6); contract to delivery median 12 (6 to 27). **PEM107 confirmed_to_order (n 631):
contract to final_date median 23 days (p25 16, p75 39); final_date to delivery 4 (1 to 7); contract to delivery 30 (21 to 49).** PEM101 stock_policy
(n 4,143): 4, 2, 8. Caveats: 1,349 pairs (12.0%) have final_date after delivery and 29 have final_date before the contract, so `final_date` is the
date of the final record (final inspection or booking), not necessarily the end of assembly; one contract line can span several lots. Estimable
for made-to-order items: **YES** as a contract-to-final and final-to-delivery elapsed time, with those caveats. **V1.**

## 2f. Warehouse roles, PEM101's 92 stock items (82 by the rule, plus the 10 decided on 2026-10-05), last 12 months

Snapshot (Cube_Inventory_Exact, 2026-10-05 pull; `j07`) and movements (`h01`, scope items). Only **5 of the 92 items** appear in the ledger in the
last 12 months (FC-A-27-00102, -00202, -00203, FC-A-38-00102, -00202: purchased fuse-cutout parts); the other 87 have no ledger movement, so any
movement-based role below rests on those 5 items.

| Warehouse | Rows of the 92 | With stock > 0 | Units | With Min and Max set | Evidence | Role |
|---|---|---|---|---|---|---|
| FG01 | 92 | 85 | 109,378 | 59 | 28 transfers in from WH21 (7,803 units, "W-101" documents), 66 transfers out to FG02, one per customer contract (7,898 units) | **Finished-goods store that releases to FG02 for customer contracts** (supported for 4 to 5 items with movements; inferred for the rest) |
| FG21 | 84 | 69 | 18,701 | 0 | 2 movements in 12 months (WH21 to FG21 400; FG21 to FG01 400) | Holds stock; role **undetermined** |
| FG11 | 84 | 0 | 0 | 52 | no movement of scope items since 2024-06-26 (last transfer 2024-04) | No stock and no movement in the last 12 months (last scope movement mid-2024); carries Min and Max records; role **undetermined** |
| FG | 89 | 0 | 0 | 77 | last scope movement 2024-12-18 | No stock and no movement in the last 12 months (last scope movement 2024-12); carries Min and Max records; role **undetermined** |
| WH21 | 5 | 5 | 9,202 | 0 | receipts from QA after inspection (59 transfers, 67,020 units); issues to production jobs (701 issues, 57,243 units); 28 transfers to FG01, 8 to FMTS | Receives inspected purchased parts from QA, issues to production jobs, supplies FG01 (these 5 items only); role **not established** for other items |

Other: FG02 shows 0 stock but a reserve of 65,844 units and is the destination of every FG01 customer transfer; type B rows at FG02 carry the contract
text: **customer shipping staging** (supported by 65 B rows; reserve column meaning *inferred*). Receipts from purchase: type A at QA, 65 rows, 70,720
units for the 5 items. Receipts from production for these items: none. Issues to customers: B with "CTR-" at FG02 (65 rows), FMTO, FMTS. The
sellable list was not changed. **V1.**

## 2g. PEM101's 20 undetermined items

Evidence added: for each item the delivered contract-items since 2024-01-01, the share with a production record on the contract (cube_final by
ctrno and item), and the median days from contract to that record. Reference (items of known class with >=10 delivered contract-items): PEM101
stock_policy 76 items, median share linked 7%; confirmed_to_order 6 items, 82% to 100%. The share alone does not separate the classes at high
values (6 of 12 items with a share of 80% or more are stock_policy; their median contract-to-final is 0 to 4 days, the same as the
confirmed_to_order items, 1.5 to 5.5 days); no reference item has both a share of 80% or more and a median of 14 days or more.

**Rule used (stated before applying):** at least 10 delivered contract-items, at least 80% linked, median contract-to-final at least 14 days. It
separates the 20 items from every reference item with a high share, because those finish within 5.5 days.

| Item | Delivered contract-items | Linked | Median contract-to-final (days) | On hand | Result |
|---|---|---|---|---|---|
| FD-F-01-0001 | 12 | 100% | 124.5 | 0 | **made after the order** |
| ST-F-12-0006 | 11 | 91% | 119.5 | 0 | **made after the order** |
| ST-F-12-0007 | 11 | 100% | 123.0 | 4 | **made after the order** |
| HS-F-99-0215 | 42 | 100% | 15.5 | 3 | **made after the order** |
| FD-F-01-0002 | 15 | 93% | 17.0 | 0 | **made after the order** |
| IS-F-99-0245CE1 | 9 | 100% | 27.0 | 0 | undetermined (fewer than 10) |
| HS-F-99-1301H33, HS-F-99-2301N, ST-F-01-0005, HS-F-99-0301H33, HS-F-99-3303, HS-F-99-0091, HS-F-99-1031 | 9 to 46 | 82% to 100% | 0 to 6 | 0 | undetermined (finish within days, like both known classes) |
| ST-F-01-0027, CA-F-99-010210, EEE-F-FC-1040011002P, HS-F-99-0151, HS-F-99-2061N, HS-F-99-3061, IS-F-99-0245EE0 | 1 to 6 | 100% | 1 to 9.5 | 0 | undetermined (too few contracts) |

**Result: the investigator proposed 5 of 20; the Validator classifies none; both positions are recorded and the decision is the user's.**
- *Investigator (inferred):* the 5 items above, finished a median 15 to 125 days after the contract date, which a stock item would not need.
- *Validator:* the rule was never validated on PEM101: no PEM101 reference item meets it (0 of 6 confirmed_to_order, 0 of 76 stock_policy); the 14-day threshold fits PEM107 confirmed_to_order (median 23), a different division; on the reference items neither the linked share nor the days separate the classes; 9 of the 20 have fewer than 10 contract-items. The five with 120-day medians (FD-F-01-0001, ST-F-12-0006, ST-F-12-0007) stand apart from every reference item: a **candidate list for the business to confirm**, not a classification the evidence supports.
- *Adopted in this report (EVIDENCE RULE):* **classified 0 of 20; 20 remain undetermined; 5 are candidates** (the five above). Weaknesses common to both: `final_date` is the date of the final record; HS-F-99-0215 and FD-F-01-0002 are only 15.5 and 17 days; two have a little stock on hand. The ledger holds no movement of these items and Cube_production / Cube_Production_Control cover PEM107-type items only.

---

## What remains undetermined (and what was tried)

- Meaning of "0 Days" in DeliveryTime (immediate or not filled in): no column says; compared with observed times only for nonzero rows.
- Assembly time per finished item: not in the ledger (no finished-goods receipt type, job numbers shared across levels); closest are Production_Order
  start to cube_final final_date (median 36 days, 103 scope items), contract to final_date (PEM107 made-to-order 23 days), and Cube_production station
  times (PEM107 CT/VT items, units of standardtime and usedtime unknown).
- Meaning of `final_date` (end of assembly, final inspection or booking): 12% of pairs are after delivery.
- Role of FG21; roles of every warehouse for the 87 of 92 stock items with no ledger movement; meaning of type J.
- All 20 undetermined PEM101 items (5 candidates; see 2g).
- Whether Cube_BOM_Exact_V2 (levels 1 to 18, 87.4% of scope codes) supersedes Cube_BOM_Exact for Week 3: not compared (different scope bases).

## Found, not done (assigned to a week of the 2026-10-05 plan; no code, config, page or data was changed)

- Week 1: use Cube_PriceList.DeliveryTime (15 days longer than observed on average) only as a labelled fallback for raw materials with no PO history.
- Week 1: lead time per item and assembly time: use contract-to-final and final-to-delivery for made-to-order PEM107 items, and show what is used where
  the data does not answer (the plan's approach).
- Week 3: compare Cube_BOM_Exact_V2 with Cube_BOM_Exact before the BOM explosion; Cube_JobCost (planned and actual cost per production order and item,
  282 scope items) may give actual material use per job.
- Week 2: Cube_Production_Order (open and printed jobs with start and planned end dates) is a candidate source of current production load.

## Validator

A separate Validator (read none of this report, no database connection) re-derived 2a to 2g from the saved outputs and only then opened the figures:

| Part | Result |
|---|---|
| 2a catalogue and item joins | MATCH (objects per database; 21 named in DATA_MAP; forward and reverse rates for six tables) |
| 2b DeliveryTime vs observed | MATCH on every figure (467 rows, 143 items, 45 suppliers, 25.05% zero, 5,373 lead times median 42 p75 62, 151 pairs r 0.695, -15 days, 80.1%, 23.2%) |
| 2d transaction types | MATCH on B, A, 150/151 and H evidence and on "assembly time not estimable"; minor: 1,426 jobs with an issue record against 1,443 here (negatives 487, median 0, p25 -5 agree); N, J, 190, T not determinable |
| 2e ctrno to ContractID | MATCH on every figure (11,533 / 11,860 = 97.24%; 8,426 = 71.05%; reverse 16.14%; 36,994 delivered pairs; times 6 / 3 and 23 / 4 for PEM107 confirmed_to_order) |
| 2f warehouse roles | MATCH on the figures; the Validator labels FG, FG11, FG21 undetermined and WH21 not established, and FG01 inferred from 4 to 5 items; roles above are softened to match |
| 2g classification | **DISCREPANCY**: figures match; classification 5 (investigator) against 0 (Validator); see 2g |
