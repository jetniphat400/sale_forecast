# DATA MAP

Every future task reads this file first (CONVENTIONS.md, Part 4 wiring). It records only what an
existing file in this repository already states — never a fresh inference. Every fact below
carries a citation (file + section/line) and a verification level:

- **V2** — confirmed from two independent directions or by independent recomputation
- **V1** — confirmed from one direction or one agent only
- **A** — business-confirmed statement, not verifiable from data
- **H** — hypothesis or inference
- **X** — superseded — the text is kept, with what replaced it and when

Where two sources disagree, both are recorded with their dates and scopes; neither is chosen for
the reader. No credentials, server names/addresses, customer names or codes, contract IDs, or
employee names appear below (repository is public).

Built 2026-09-24, from files already in the repository — **no database access was used**.

---

## 1. Tables

### cube_Sale_APD
Primary demand-history source (Omni Channel sales order lines). **Grain**: one row per order
line-item — confirmed via `INFORMATION_SCHEMA.COLUMNS` (62 columns) and cross-table row-count
checks (STATUS.md:1326). **Date coverage**: whole-table history from 2021-01-11 (STATUS.md:1894);
2024-onward is the project's "usable" era — pre-2024 rows use a different division-tagging scheme
(`PSP101-105`) and lack current-convention `revenue_type`/`division` values (STATUS.md:1906-1907).
**Row scale**: ~51,000 rows in an early scoped pull (STATUS.md:1326); 35,174 rows for the 351-item
Phase I/J combined scope (Phase J). **Trust note**: reliable for 2024+ Omni Channel/Actual+MPS
scope; `division` is reference-only, never a filter (§2). **V2** for grain/schema (cross-checked
against `Cube_CES` on 99.79-99.94% of rows, STATUS.md:2054-2066, 3330-3343).

### Cube_CES
Independently-populated delivery/contract-tracking table; ground truth for on-time delivery and a
cross-check on `cube_Sale_APD`. **Grain**: finer than `cube_Sale_APD` in places (splits one
`cube_Sale_APD` total across multiple `PlanID` rows, STATUS.md:2060-2062) — no source states a
single "one row per X" rule. **Date coverage**: `CtrDate` 2012-01-03 to 2029-08-05 table-wide
(STATUS.md:1575); dense/comparable data begins January 2023 (STATUS.md:2077,
`delivery_performance.py`). **Row scale**: 166,432 rows table-wide (STATUS.md:1575); 63,032 rows
for the Phase J2 351-item/Omni Channel/Actual+Backlog scoped pull (`output/summary/
phaseJ2_explorerD_cube_ces_raw.csv`, Phase J2, this session). **Trust note**: agrees with
`cube_Sale_APD` on 99.79-100% of fields tested for 2024+ (STATUS.md:2110) — **V2**. Pre-2024 is
only pattern-checked, not row-audited — **V1/H** for that era (STATUS.md:2001-2003).

### Cube_Contract
Contract/delivery tracking; considered as corroboration for duplicate-vs-split-lot detection.
**Grain**: `contractid`, `plan_qty`/`actual_qty`, `actual_del_date`, but only a free-text
`product` field — **no ItemCode column** (STATUS.md:1535-1536, 1576). **Date coverage**: only
`ctr_date >= 2025-01-01` — zero 2024 contracts exist in this table (STATUS.md:1542). This was
first misread as "2024 contract data doesn't exist anywhere," corrected once `Cube_CES` was found
to cover 2024 fully with a proper key (STATUS.md:1573-1579) — **X, superseded 2026-08-31**.
**Trust note**: its weak free-text join key undercounted matches (8/29 vs. 100% once rejoined via
`Cube_CES`'s `ContractID`+`ItemCode`, STATUS.md:1580-1583) — a Traps entry, §4.

### Cube_Backlog
Was the confirmed-open-demand source in an early METRICS.md §14 draft; since replaced. **Trust
note**: lags `Cube_CES` by ~13.6-14 hours (STATUS.md:557 "~13.6 hours at check time"; METRICS.md
§14 "roughly 14 hours") — using it over-counts open demand by 0.9% (8 already-delivered pairs per
`Cube_CES`'s fresher refresh) (STATUS.md:552-558, METRICS.md:158-163). **V2** for the lag finding
(independently checked twice — STATUS.md:445-451 and 552-560). **X** as the METRICS.md §14 source
specifically — `Cube_CES Status='Backlog'` is used instead (METRICS.md:158-159).

### Cube_Inventory_Exact
Current-state finished-goods/stock snapshot with literal `minimum`/`maximum` columns. **Grain**:
one row per (company, warehouse, itemcode) (columns: company, warehouse, itemcode, stock, minimum,
maximum, reserve_bywa, timestamp, costPrice_standard). **Date coverage**: single-refresh snapshot —
all timestamps within one ~2-minute load window (STATUS.md:2007-2008) — **V1**, "snapshot not
history." **Row scale**: 403 rows for 66/68 pilot codes in an early pull (STATUS.md:2007); 2,057
rows for the 351-item combined scope (Phase I). **Trust note**: the existing min/max VALUES cannot
be used as calculation inputs — 46/128 items have no setting at all, settings range from under 1
month to over 1,700 months of cover, 81/119 multi-warehouse items disagree across warehouses, 7
items carry a setting despite no sales (STATUS.md:4830-4835) — **V1**, one investigation,
comparison-baseline use only (Locked Decisions).

### Cube_Inventory_Aging
Despite its name, **has no age-bucket structure** — `Condition`, `Type`, `ItemStatus` are constant
across all 441,427 rows; it is a GL-account-level stock-valuation snapshot, single timestamp, no
history (STATUS.md:2300-2306) — cannot answer "how long has this stock been held." A naive pull
summing `Stock` across all rows per item showed apparent large hidden stock (236 items /
466,134 units); this is an artifact — the table is GL-account-level and different GL accounts are
NOT additive (proof: one item shows +34,574 under one account, +25,874 under another, −30,677
under a third, same warehouse). GL account `117100` is the physical-stock account (98.8% match to
`Cube_Inventory_Exact`); restricted to it, 61 of 62 items match `Cube_Inventory_Exact` almost
exactly (STATUS.md:763-770) — **V2** for the corrected reading. Its `GLDescription` field
(Finished goods/Raw materials) is independently useful for FG/RM classification (§ below) — **V2**
(three independent tables agree, STATUS.md:2320-2324).

### cube_inventory_tran
A genuine historical movement ledger (QtyIn/QtyOut) — the one inventory table that is NOT a
snapshot. **Date coverage**: 2007-2026 (STATUS.md:2010). **Row scale**: 2.9M rows table-wide
(STATUS.md:2010). **Trust note**: used to verify 1,572 exact-quantity-matched transfers between
warehouse stages, mostly forward but with genuine bidirectional movement, tied to one
order-reference document; aggregate received-minus-issued reconciles with on-hand exactly for 2/6
tested items, within 1.5% for the rest (STATUS.md:4849-4857) — **V2** for the warehouse-stage
finding. At first mention it had not yet been tested against the pilot items (STATUS.md:2010-2011,
**H/V1** at that point) — superseded by the later warehouse-stage verification above; both are
recorded since the later entry doesn't explicitly restate/retire the earlier one by name.

### Cube_Quotation
Pre-order enquiry/quotation records; tested this session (Phase J2 Explorer A) as a possible
source of longer real customer notice. **Grain**: one row per item-line within a quotation
document (inferred from the join: `quotation` document number + `itemcode`,
`output/summary/phaseJ2_explorerA_report.md` §1-2). **Schema**: 47 columns (only `itemcode`,
`ctr_leadtime`, `report_date` were known before this session; full list in the report above) —
**V1**, one Explorer, one session. **Date coverage**: essentially zero rows with a 2024
`create_date` for the 351-item scope (25 rows) vs. 6,742 (2025) and 8,463 (2026); reason **CANNOT
BE DETERMINED** (`phaseJ2_explorerA_report.md` §3). **Trust note / trap**: `report_date` (used by
an earlier investigation, `investigate_leadtime_classification.py`) is **NOT a quotation-issue
date** — 99.94% identical to `forecast_date`, actually a disposition/delivery date; `create_date`
is the defensible quotation date (`phaseJ2_explorerA_report.md` §2) — **V1**, corrects a prior
unlabelled assumption; see §4 Traps.

### cube_final
Production-batch/job tracking; `jobno` values match individual tokens inside
`cube_Sale_APD.jobcode`'s comma-separated lists (STATUS.md:1584-1601). **Schema**: at minimum
`jobno, ctrno, customer_name, project, descriptions, final_date, itemcode, pono, job_qty`
(STATUS.md:1587-1600, `output/summary/task2_cube_final_jobno_match.csv`); a fuller 35-column schema
(including `finalcheck_date`, `finalreceive_date`, `fg_check_date`, `fg_pack_date`,
`fg_final_date`) was discovered but not analysed this session (`output/summary/
phaseJ2_explorerD_cube_final_schema_sample.csv`). **Grain**: `jobno` ties to exactly one itemcode
in 99.5% of cases (17,875 of 17,971 distinct values) but is reused across many contracts/customers/
dates — a production-batch reference, not a per-sale job ID (STATUS.md:1588-1591) — **V1**, one
investigation, project-wide scope. **Match rate**: of 12,952 distinct job/batch tokens in
`cube_Sale_APD.jobcode`, 87.6% match `Cube_CES.OLMJobCode`, 40.0% match `cube_final.jobno`
(STATUS.md:1597-1598). **Trust note / trap**: a 2026-09-23 pull for the 351-item scope returned
**zero rows** — almost certainly an interrupted-process artifact (the pulling agent was killed by
an unrelated rate-limit mid-task, after its database connection had already succeeded), NOT
evidence the table lacks this scope's data — item codes from the prior investigation
(`CT-F-99-020503` etc.) are confirmed present in the 351-item scope file
(`output/summary/phaseJ2_explorerD_report.md`). **Do not read a future empty pull of this exact
query as "no data" — re-attempt it.** See §4 Traps.

### Cube_PO_Exact
Would be the ideal empirical procurement-lead-time source (po_date to fulfilment_date). **Trust
note**: had zero rows for any of the 68 original pilot codes (STATUS.md:2013-2015) — **V1**, one
pull, one (smaller, earlier) scope; not re-tested against the current 351-item scope. A different,
later figure (7/128 items, 5.5%, 16-189 day range, mean 70 days) is recorded once the 128-item
pilot scope was in place (STATUS.md:2307-2309) — both recorded, different scopes/dates, not
reconciled.

### Cube_PriceList
Supplier-item delivery-time reference — distinct from the project's main pricelist reference file
(`reference/pricelist.xlsx`, an Excel workbook, not a database table). Has a literal `DeliveryTime`
field (e.g. "30 Days"). **Coverage, two figures, different scopes, both recorded — do not
choose**: 24 of 68 items (STATUS.md:2012-2013, the original 68-item pilot scope) vs. 62 of 128
items, 48.4% (STATUS.md:2313, the later 128-item pilot scope) — **V1** each.

### Cube_emanu
Candidate manufacturing lead-time source, literal `leadtime` column. **Established, high
confidence**: `leadtime` exactly equals `DATEDIFF(day, createJobDate, lastestReceiptDate)` for
every sampled row (an exact-formula match) — genuine manufacturing job cycle time, not a
supplier/vendor lead time (no such field exists in the table at all) — **V2** (exact-formula
proof). **Trust note**: unusable regardless — no itemcode column, and no data since March 2019
(STATUS.md:2307-2309).

### Other tables a report relies on
- **Cube_ItemList** — `Assortment1` field, used with `Cube_Inventory_Aging.GLDescription` and
  `Cube_BOM_Exact` presence to establish Finished-Goods-vs-Raw-Material classification: 122/128
  Finished Goods, 6/128 Raw Material (STATUS.md:2320-2324) — **V2**, three independent tables in
  exact agreement. Also has a `PurchasePrice` field: 48 items show a nonzero value, ambiguous
  (outside sourcing vs. a recorded reference price only) — **H**.
- **Cube_BOM_Exact** — bill-of-materials table; all 117 FG-classified items (of the 122) have a
  BOM entry, none of the 6 RM items do (STATUS.md:2322-2323) — **V1**, corroborating evidence for
  the FG/RM split. **Fully investigated 2026-09-23 (Phase J3 Explorer BOM,
  `output/summary/phaseJ3_explorerBOM_report.md`)**: 20 columns; `ItemFG` = finished item,
  `ItemRawmat` = component code, `Quantity`+`Unit` = per-unit consumption rate, `Sequenceno`
  numbers BOM lines (0 = header row, not a component; `Type='Machine Hour'` flags 3 non-stock
  labor/overhead pseudo-codes mixed into the component-code column). **Grain: one row per
  (finished item, component) pair** — confirmed, zero duplicate keys across 1,751 scope rows —
  **V1**. **Coverage of the 351-item inventory-model scope: 301/351 (85.8%)** — PEM101 95.3%,
  PEM107 94.1%, **PEM103 only 58.6%** (new, no prior figure existed) — **V1**. **Components ARE
  shared across finished items (Q18, confirmed): 141 of 805 distinct components (17.5%) appear on
  more than one finished item's BOM**, concentrated in fuse/surge-arrester families — **V1**. **Join
  to `Cube_Inventory_Exact`, both directions, mutually consistent: 765/805 (95.0%) component codes
  exist as their own itemcode in inventory (forward); a targeted pull of exactly those 765 codes
  returned 1,796 real stock rows (reverse, confirming genuine separate stock records, not a
  coincidental string match)** — **V2**. 176/765 matched components (23.0%) carry nonzero on-hand
  stock today.
- **cube_po** — raw-material PO table; none of the FG items appear in it under their own code —
  weak, one-directional evidence they are manufactured rather than bought complete
  (STATUS.md:2325-2327) — **H**.

---

## 2. Columns with established meaning

**cube_Sale_APD.createDate** — the PO-received date (order intake), not a record-creation
artifact: no load-batch/weekend-clustering signature (652 distinct calendar dates, max 0.42% of
rows on any one date); 99.95% agreement with the independently-populated `Cube_CES.CtrDate`
(STATUS.md:3323, 3330-3334, 3344-3347). **V2** (cross-table, two-direction). Caveat kept explicit
in the source: cannot fully rule out "keyed into the system" vs. "literal moment of customer
intent" (STATUS.md:3348-3351) — this narrows the claim's scope, not its match-rate confidence.

**cube_Sale_APD.PODate** — matches `createDate` exactly on 99.9458% of rows (27,664/27,679); all 15
disagreements have `PODate` earlier, never later, median gap 8 days (STATUS.md:3317-3319). Matches
`Cube_CES.CtrDate` at 100.000% (STATUS.md:3333). **V2**. Practical conclusion in the source:
`createDate` and `PODate` are not meaningfully different fields for this project's purposes
(STATUS.md:3358).

**cube_Sale_APD.forecast_date** — a scheduled-delivery-date concept, not a raw event date: weekday
distribution is a completely different shape from `createDate`/`PODate` (37.4% Friday, nonzero
weekend share vs. zero for the other two, STATUS.md:3326-3327); matches `Cube_CES.CtrDate` at only
6.49% (median/mean offset 6.0/10.8 days), confirming it is a genuinely different concept from the
order date (STATUS.md:3334-3335). **V2** for "different concept from order date." Whether
`forecast_date` is ever revised in place after intake is **explicitly unresolved** — no audit
trail exists; every test bounds any possible revision at under 2.5% of rows with no consistent
direction (STATUS.md:4588-4592) — **H**, stated as an assumption, never proven.

**cube_Sale_APD.timeStamp** — a pure ETL/refresh artifact, not a business date: all rows in a
scoped pull land on one calendar date, spanning ~17 minutes to 64.2 seconds depending on the pull
(STATUS.md:1337, 1469, 3320-3322); re-stamps on every reload (the date itself moved forward between
two checks, one earlier date to a later one, STATUS.md:3321-3322). **V2** (re-confirmed
independently at least twice).

**status (cube_Sale_APD Actual/MPS) ↔ Cube_CES.Status (Actual/Backlog)** — **`Backlog` is the true
MPS equivalent**, proven both directions: 158 of 158 MPS-linked pairs (2024+) carry `Cube_CES`
Status='Backlog'; reverse direction, of 155 Backlog-linked pairs, 158 are MPS vs. 6 Actual in
`cube_Sale_APD` (STATUS.md:2044-2050). **V2** (both directions). `Cube_CES`'s own literal `"MPS"`
status (504 rows table-wide) is **unrelated** — a naming coincidence, not the same concept
(STATUS.md:2051-2053). See §4 Traps.

**division (cube_Sale_APD.division) and the `-OLD` tags** — the database's `division` column is
reference-only, never a filter; the pricelist is authoritative for which division an item belongs
to (STATUS.md:4756-4772, CONVENTIONS.md) — **A/decision** (a corrected project rule, not itself a
raw data fact). The underlying data fact: PEM102's real 2024 activity sits under
`division='PEM107-OLD'` and PEM107's under `division='PEM102-OLD'`; the mechanism producing this
swap is still unexplained (`output/summary/phaseC_synthesis_report.md` §5) — **V1**, one
investigation, mechanism itself unresolved. This is the single most costly Traps entry in the
project — see §4.

**revenue_type** — a sales-channel classification; 7 distinct values exist table-wide
(STATUS.md:1441). Project scope is fixed to `Omni Channel`, project-wide, confirmed from the start
(STATUS.md:4684-4685) — **A**, business-confirmed scope decision. Other observed values include
Tendering, Total Customer Solution, and PPS-routed Tendering (STATUS.md:4870-4874) — **V1**.

**cube_Sale_APD.cost** — a **LINE TOTAL, not a unit cost** (METRICS.md §1; STATUS.md:4271-4272,
Phase D Check 2: `cost/qty` is exactly constant across rows of varying qty for a test item; median
within-item CV of `cost/qty` is 0.061 at project scope, consistent with a per-unit price that
drifts, not a stored line total held constant). Using it raw as a unit price would have overstated
stock value by roughly one to two orders of magnitude. **V2** (locked into METRICS.md as the
formula's own input note, independently re-derived from the Phase D investigation). The single
highest-severity Traps entry by stated magnitude — see §4.

**jobcode (cube_Sale_APD) / jobno (cube_final) / OLMJobCode (Cube_CES)** — all three reference the
same underlying concept: a **production-batch reference**, not a per-sale job identifier. An
individual token ties to exactly one itemcode 99.5% of the time but
is reused across many unrelated contracts/customers/dates (STATUS.md:1584-1601) — **V1**, one
investigation, project-wide scope. `cube_Sale_APD.jobcode` stores this as a comma-concatenated
list, one token per distinct item-batch on a contract — this explains an earlier, now-superseded
reading that an identical full list repeating across a contract's rows meant "one job per row"
(STATUS.md:1591-1594) — **X** for that earlier reading, superseded same investigation. **Narrower,
later finding, different scope, both recorded**: restricted to the 351-item PEM101/103/107 scope
(Phase J2 Explorer D, this session), only 13.8% of tokens serve more than one contract — narrower
than the project-wide "reused across dozens" finding; the two are not directly comparable
(`output/summary/phaseJ2_explorerD_report.md`). **Refined further, 2026-09-23 (Phase J3 Explorer
D, `output/summary/phaseJ3_explorerD_report.md`), independently recomputed on the `OLMJobCode`
proxy (V2, matches Phase J2's pooled 13.8%/14.5% almost exactly when pooled the same way)**: the
13.8%/14.5% pooled figures hide a LARGE division split in the reverse-traceability share (share of
delivered contracts tracing to a pre-existing batch token) — **PEM101 only 2.0%, PEM103 69.3%,
PEM107 58.9%**. Batch/cadence-based fulfilment looks weak for PEM101 but substantial for
PEM103/PEM107. Per-item-typical cadence (median days between an item's own batches, a candidate
Section 20 review-interval value): PEM101 56 days (p25 31, p75 124), PEM103 36 days (p25 15, p75
133), PEM107 58 days (p25 22, p75 98) — wide spreads, reported as such, not collapsed to one
number. A narrow, stale, 4-item legacy sample (`task2_cube_final_jobno_match.csv`, pre-existing,
not scope-representative) gives one further qualitative lean, kept at low confidence given the
sample size: `job_qty` looks like a fixed nominal lot size (e.g. always 20 or 30 units) unrelated
to the 1-17 units actually delivered per order (supports batching qualitatively), but `final_date`
is per-allocation (each row sharing a `jobno` has its own distinct `final_date`) and typically
falls AFTER, not before, that allocation's own PO date (median lag -4 days in that small sample) —
a genuine complication for a simple "batch precedes order" reading, reported plainly — **H**, 4
items, not scope-representative.

**manufacturing_type (cube_Sale_APD)** — MTS/MTO/ETO values, covers 113/128 pilot items, but is an
**ORDER-level attribute, not a fixed per-item classification**: 100 of 113 items show more than one
value across their own sales rows (STATUS.md:2329-2332), re-confirmed later (STATUS.md:2852) —
**V2**. It describes production strategy per order, not a fixed make-vs-buy classification
(STATUS.md:2332).

**warehouse field (sales-order tables)** — **no sales-order-level table checked (cube_Sale_APD,
Cube_CES, or any other) carries a warehouse field at all** — repeated, independently re-affirmed
across at least five separate STATUS.md entries/dates (STATUS.md:829, 874, 3591, 4861, 4876, 5190).
This is why sellability of any warehouse code is a standing, never-verifiable-from-data business
assumption, for every division (STATUS.md:872-878) — **V2** for the absence-of-field finding
itself (the two-direction rule is explicitly invoked in the source: the item-to-warehouse direction
IS checkable via `Cube_Inventory_Exact`/pricelist joins; the reverse — which warehouse a given sale
shipped from — has no field to check at all, so sellability itself stays unverifiable in either
direction).

**Cube_Inventory_Exact.warehouse / warehouse_roles (config.yaml)** — all 44 warehouse codes ever
seen in the 445-item pricelist registry classified from the item-to-warehouse direction, using two
independent live pulls 13 days apart (2026-09-09 and 2026-09-21/22): 30 EMPTY, 11 EXCLUSIVE to one
division, 3 SHARED across divisions, 0 UNRESOLVABLE (STATUS.md:862-871) — **V2** (two independent
pulls, same result both times). This is a division/sharing map only — **not** a sellability
determination (see warehouse field, above).

**Cube_CES date fields** — `CtrDate` (contract/order date, matches `cube_Sale_APD.createDate`/
`PODate` at 99.946%/100.000% respectively, STATUS.md:3333-3334); `PlanDelDate` and
`ForecastDelDate` are identical on 95.79-97.9% of rows depending on scope/window — **three
independent measurements, all mutually consistent, recorded together**: 97.9% (STATUS.md:2614,
original Phase 3.1/delivery-baseline scope); 100% exact agreement between
`cube_Sale_APD.forecast_date` and `Cube_CES.ForecastDelDate` on joinable rows, 2.3-3.2%
disagreement with `PlanDelDate` depending on scope, no consistent direction (STATUS.md:3037-3043,
Phase A); 95.79% (`output/summary/phaseJ2_explorerB_report.md` §6, n=34,580, 2024+, 351-item
scope, this session). **V2** (three independent measurements, different scopes/dates, mutually
consistent). `ActualDelDate` is the actual delivery date, populated only for `Status='Actual'`
rows.

**Cube_CES.RevenueType** — `Cube_CES` carries its own NATIVE `RevenueType` column (full 36-column
schema confirmed this session: ..., `RevenueType`, `SaleDivision`, `Status`, `Timestamp`, `id`) —
no join to `cube_Sale_APD` is needed to know a CES row's channel. Cross-checked against
`cube_Sale_APD.revenue_type` via (ContractID, ItemCode): 72.28% of CES rows join to a
`cube_Sale_APD` row; of those matched, 100.00% agree on revenue_type; 0 of 36,168 matched
(contractid, itemcode) pairs carry more than one revenue_type in `cube_Sale_APD` (checked, not
assumed). **V2** for "the native column exists and is usable directly" (same-table field, no join
uncertainty); **V1** for the cross-table agreement rate (one pull, one direction, consistency only
per CONVENTIONS.md). Found: Q23 Part 1, Explorer, 2026-09-24
(`output/summary/phaseQ23_explorer_report.md`).

**cube_Sale_APD.customer_segment** — a real, informative customer-classification field (values seen:
`Contractor`, `Dealer`, `Smart Shop`, `End User`, `Local Utility`, `Inside Group`, `PEA Regional
Office`, and several Thai-language utility-region labels). Institutional/utility segments
(`Local Utility`/`Inside Group`/PEA-region) dominate Tendering-tagged rows; retail-type segments
(`Contractor`/`Dealer`/`Smart Shop`/`End User`) dominate Omni-tagged rows, STABLY across both 2025
and 2026 for both PEM103 and PEM107 — this project's first-established customer-type field, and
the field that most directly explains why `revenue_type` tracks a real distinction rather than an
arbitrary tag (see §7, PEM103/PEM107 channel-shift finding). `typeOfSale` also exists but is
constant (`Sale` for every row in the scope tested) — uninformative. `customerid` is 100% populated
in the scope tested. **V1** (one Explorer, one pull; not yet independently recomputed by a second
agent, though the Validator's separate pull of the same scope did not contradict it). Found: this
task, Explorer 2 (`output/summary/phase136_explorer2_report.md`), 2026-09-24.

---

## 3. Joins

| Left | Right | Match rate | Scope | Verified | Directions | Level |
|---|---|---|---|---|---|---|
| `cube_Sale_APD.itemcode` | pricelist `Product Code` (visible sheets) | 343/445 (77.1%) | Full 445-code registry | 2026-08-31 | Pricelist→DB checked; reverse not separately reported | V1 |
| `cube_Sale_APD.division` | pricelist Business Unit | 3/3 sample match exactly; `PEM105` value matches no sheet; `-OLD` tags (`PEM102-OLD` 2,402 rows, `PEM107-OLD` 590 rows) not in pricelist at all | 3-code sample, then project-wide | 2026-08-31, reinforced 2026-09-04 | Sample check one direction; project-wide rule reinforced by the independent -OLD mirror-pattern finding | V1 sample → V2 as a project-wide rule once combined with the -OLD finding |
| `cube_Sale_APD.jobcode` tokens | `cube_final.jobno` | 5,187/12,952 tokens (40.0%) | Project-wide | 2026-08-31 | Token→table only; no reverse ("do all jobno values appear in some jobcode") reported | V1 — candidate trap if ever treated as bidirectional |
| `cube_Sale_APD.jobcode` tokens | `Cube_CES.OLMJobCode` | 11,350/12,952 tokens (87.6%) | Project-wide | 2026-08-31 | Token→table only, same caveat as above | V1 |
| `cube_final.ctrno` | `cube_Sale_APD.contractid` / `Cube_CES.ContractID` | Not exercised — `cube_final` pull returned 0 rows this session (see §1, §4) | 351-item scope | 2026-09-23 attempted | Not checked either direction | H (hypothesis only, never confirmed by a successful query) |
| Warehouse code | division (division→warehouse) | Full 445-item, 6-division crosstab, ≥60% dominance threshold | Project-wide | 2026-09-09 | This direction only | V1 at the time |
| Warehouse code | division (item→warehouse, reverse) | All 44 codes resolved, 0 UNRESOLVABLE, two independent pulls 13 days apart agree | Project-wide | 2026-09-21/22 | Reverse direction added — closes the Phase D gap | **V2** combined with the row above |
| `Cube_Backlog` | `Cube_CES` (Status='Backlog') | 273/273 (100%) CES pairs corroborated; the 8 extra Backlog-only pairs independently confirmed Status='Actual' in CES's fresher refresh | PEM101 128-item scope | 2026-09-22 | Full pair-level diff, both directions | V2 |
| `Cube_CES.PlanDelDate` | `Cube_CES.ForecastDelDate` (internal identity) | 97.9% / 100%-exact-with-cube_Sale_APD-2.3-3.2%-disagreement / 95.79% — three measurements, see §2 | Three different scopes/dates | 2026 (multiple dates) | N/A (internal field identity, not a cross-table join) | V2 (mutually consistent across 3 independent checks) |
| `division='CI101'` items | `division='PEM101'` tag (value split) | 37.2% of combined CI101+PEM101 Omni Channel value for CI101's 13 codes recorded under `PEM101`, not `CI101` | CI101's 13 item codes | Phase C | One investigation cited, no explicit second-direction check in this passage | V1 |
| `cube_Sale_APD.quotationid` | `Cube_Quotation.quotation` | Join key itself: 2,374/3,987 distinct quotationid values overlap (59.5%); `Cube_Quotation.id` overlaps 0% (not the key) | 351-item scope | 2026-09-23 (Phase J2, this session) | Data-driven discovery, one direction for key discovery | V1 |
| ↳ forward (PO→quotation), match once found | | 17.26% of all 35,174 PO rows overall; 0.00% for 2024 specifically (near-zero table coverage that year); 95.54-98.67% for 2025/2026 | 351-item scope | 2026-09-23 | Forward | V1 (2025-2026); CANNOT BE DETERMINED for 2024 |
| ↳ reverse (quotation→PO) | | 5,975/15,199 distinct quotations converted (39.31%), median 3 days to conversion | 351-item scope | 2026-09-23 | Reverse — independently confirms the forward-direction median (3 days each way) | **V2** for the join mechanism and 2025-2026 match rate (both directions, mutually confirming) |
| `Cube_Inventory_Exact.itemcode` | `cube_Sale_APD.itemcode` | No report found testing this as an independent join with a stated match-rate figure — inventory pulls are always scoped by a pre-existing item-code list | — | — | Not tested as a join | **Gap, not a number** — flagged, not asserted |
| `Cube_BOM_Exact.ItemRawmat` (component code) | `Cube_Inventory_Exact.itemcode` | 765/805 distinct components (95.0%) forward; reverse pull of exactly those 765 codes returned 1,796 real stock rows, confirming genuine separate stock records | 351-item inventory-model scope | 2026-09-23 | Both directions checked, mutually consistent | V2 |
| `cube_final.ctrno` | `cube_Sale_APD.contractid` / `Cube_CES.ContractID` | Still not exercised — a second, clean, uninterrupted `cube_final` pull (Phase J3) STILL returned 0 rows for this scope, contradicting the earlier "crashed-agent artifact" explanation | 351-item scope | 2026-09-23 attempted (Phase J3 Explorer D) | Not checked either direction (no rows to join) | H (hypothesis only; the join itself remains untested — see §4 Trap 7, revised) |
| `Cube_CES.OLMJobCode` token → first prior contract with that token (reverse-direction batch-traceability proxy) | delivered contracts (`Status='Actual'`) | Pooled 14.48% (median lag 29 days); **by division: PEM101 2.0%, PEM103 69.3%, PEM107 58.9%** — a large, division-dependent spread not visible in the earlier pooled figure | 351-item scope | 2026-09-23 (Phase J3 Explorer D, `output/summary/phaseJ3_explorerD_report.md`) | Reverse direction only (this IS the reverse-traceability check itself; no separate forward check performed beyond the existing token-match-rate entries above) | V2 by independent recomputation (matches Phase J2's own pooled 13.8-14.5% almost exactly when pooled the same way) |

---

## 4. Traps

*This section matters most (task instruction) — every case where a naive reading of the data
produced a wrong result, with the correct handling and the report that found it.*

1. **`cost` is a line total, not a unit price.** Naive reading: use `cube_Sale_APD.cost` directly
   as a per-unit cost. Reality: `cost/qty` is exactly constant across rows of varying qty for a
   test item; it is qty × unit price. Using it raw would have overstated stock value by roughly
   one to two orders of magnitude. **Correct handling**: unit_cost = median(`cost`/`qty`) over the
   trailing window (METRICS.md §1). Found: Phase D Check 2 (STATUS.md:4271-4272). **V1**
   (downgraded from V2 by Validator, 2026-09-24: the source is one investigation, one test item
   proven exactly plus a project-scope CV statistic from the same pass — not an independent
   second direction or a recomputation by a separate agent).

2. **The database's `division` column, including its `-OLD` tags, was first "fixed" by excluding
   the unreliable value instead of asking what the source of truth is.** Naive reading: rows tagged
   `PEM102-OLD`/`PEM107-OLD` look unreliable, so exclude them from scope. Reality: PEM102's real
   2024 activity sits under `PEM107-OLD` and vice versa (a mirror swap, mechanism unexplained) —
   excluding those rows would have discarded roughly 26-40% of PEM102's and PEM107's real
   Omni-Channel sales value. **Correct handling**: the pricelist is authoritative for an item's
   division; the database's `division` column (every value, including `-OLD` tags) is kept only as
   a reference column, never a filter. Found: STATUS.md Locked Decisions, "Division source-of-truth
   correction" (STATUS.md:4756-4801); CONVENTIONS.md. **V1** for the underlying data pattern, **A**
   for the corrected project rule.

3. **A pilot-scope filter (`division='PEM101'`) was written into STATUS.md as if it were the whole
   project's scope**, and propagated unquestioned into Phase C, causing confusion when
   PEM102/103/104/107/CI101 needed their own division values. Not caught until Phase C. **Correct
   handling**: `division='PEM101'` was only ever the Fuse/Surge-Arrester pilot's condition (those
   products exist only on that sheet); `revenue_type='Omni Channel'` and the Actual+MPS status
   basis remain, and remain correctly, project-wide. CONVENTIONS.md's rule that every decision must
   state whether it is project-wide or pilot/task-scoped was added because of this exact error.
   Found/corrected: STATUS.md Locked Decisions, "Project scope correction" (STATUS.md:4673-4685).
   **V1**, one traced incident, but the corrected rule is now **A** (adopted convention).

4. **`Cube_CES`'s own literal `"MPS"` status is unrelated to `cube_Sale_APD`'s `MPS` status** — a
   naming coincidence, not the same concept. Naive reading: join/equate the two tables on the
   literal string "MPS". Reality: `cube_Sale_APD` MPS rows map to `Cube_CES` **`Status='Backlog'`**
   (proven both directions: 158/158 forward, 158-of-164 reverse); `Cube_CES`'s own 504 `"MPS"` rows
   table-wide are a different thing entirely — this fully explained an original count gap (2,158
   vs. 504) that had prompted the investigation. Found: STATUS.md:2044-2053. **V2**.

5. **Using `Cube_Backlog` for confirmed/open demand would over-count it.** Naive reading:
   `Cube_Backlog` is the obvious table name for backlog demand. Reality: its snapshot lags
   `Cube_CES` by ~13.6-14 hours; 8 pairs it holds are already delivered per `Cube_CES`'s fresher
   refresh — using it would over-count open demand by 421 units (0.9% of scope qty) at the checked
   snapshot. **Correct handling**: METRICS.md §14 sources confirmed demand from `Cube_CES
   Status='Backlog'`, never the `Cube_Backlog` table. Found: STATUS.md:552-560; METRICS.md §14.
   **V2**.

6. **`Cube_Quotation.report_date` looks like a quotation-issue date but is not.** Naive reading (an
   earlier investigation, `investigate_leadtime_classification.py`): treat `report_date` as when
   the quotation was raised. Reality: 99.94% identical to `forecast_date` — it is a
   disposition/delivery date. **Correct handling**: `create_date` is the defensible quotation date.
   Found: Phase J2 Explorer A, this session (`output/summary/phaseJ2_explorerA_report.md` §2).
   **V1**.

7. **A `cube_final` pull returning zero rows was nearly indistinguishable from "this table has no
   data for this scope" — and the natural explanation (a crashed session) turned out to be wrong
   too.** Naive reading #1: zero rows means the table doesn't cover these items. Reality (Phase J2):
   the pulling agent was killed by an unrelated infrastructure rate-limit mid-task, after its
   database connection had already succeeded — this looked like the explanation. Naive reading #2
   (Phase J2's own correction): therefore a clean re-attempt would return real data. **This was
   tested and CONTRADICTED, 2026-09-23 (Phase J3 Explorer D): a fresh, uninterrupted, full-column
   connection attempt — no crash, correct 35-column schema returned — STILL returned zero rows for
   the same 351-item scope.** A follow-up diagnostic query (row count table-wide; whether 4
   previously-confirmed item codes still exist) was attempted but blocked by this task's own
   one-connection-per-agent rule, so it is **CANNOT BE DETERMINED** whether `cube_final` is now
   empty table-wide or just for this item scope — neither the original "artifact" theory nor a
   simple "just re-attempt" fix is confirmed. **Correct handling, revised**: do not assume a repeat
   empty pull will resolve itself; the next attempt should run the three specific diagnostic
   queries first (row count; a handful of known-historical item codes; a date-unbounded, no-filter
   `SELECT COUNT(*)`) before spending a connection on the full 351-item pull again. Found: Phase J2
   Explorer D (`output/summary/phaseJ2_explorerD_report.md`) and Phase J3 Explorer D
   (`output/summary/phaseJ3_explorerD_report.md`, which itself lists the exact diagnostic queries).
   **V1** for both the original artifact theory (now known incomplete) and this correction (one
   Explorer, one clean re-attempt) — genuinely **CANNOT BE DETERMINED** for the underlying question
   of why the table is empty for this scope.

   **Update, 2026-09-24 (this task's Part 0 diagnostic, `src/investigations/phase22_cubefinal_diagnostic.py`,
   one connection attempt, unfiltered/no itemcode restriction):** `cube_final` is **NOT empty
   table-wide** — `INFORMATION_SCHEMA.COLUMNS` returned the same 35-column schema (`output/summary/
   phase22_cubefinal_columns.csv`), and a `TOP 10` query for its own most recent month
   (`final_date >= start of the month containing MAX(final_date)`) returned 10 real rows, dated
   2026-09-23 (`output/summary/phase22_cubefinal_top10.csv` — contains real customer names, not
   committed/quoted per this file's own privacy rule). **This resolves the narrow "is the table
   empty" question — it is not.** It does **NOT** resolve why the earlier itemcode-filtered
   351-item-scope pulls (Phase J2/J3) returned zero rows: this diagnostic ran no itemcode filter at
   all, so the original filtered-query failure remains unexplained (still **CANNOT BE DETERMINED**
   for that narrower question). A `SELECT COUNT(*)` (table-wide row count) was also run in the same
   session per the script, but no artifact captured its numeric result for later citation, so that
   figure is **not** recorded here (per CONVENTIONS.md "Verify, never recall" — an unverifiable
   recalled number is not reported as fact). **Level V1** (one diagnostic pass, this task); the
   itemcode-filtered-query question remains **CANNOT BE DETERMINED**, unchanged from above.

8. **A one-direction "no stock" conclusion (warehouse-named-for-a-division → stock) was wrong for
   two divisions.** Naive reading: if a warehouse code is named for a division and shows no stock,
   that division holds no stock anywhere. Reality: the reverse direction (item → warehouse) found
   PEM103 and PEM107 hold real stock (over ฿12 million combined) in codes not named for them.
   **Correct handling**: CONVENTIONS.md's two-direction rule — any absence conclusion needs both
   directions checked before being recorded as a conclusion, not just a finding; a Validator
   "confirmation" only counts as a second direction when it is an independent recomputation, not a
   re-read of the same query. Found: STATUS.md:790-802 (Phase E2 readiness). **V2** once the
   reverse direction was added.

9. **The literal `>=` P50 rule silently classified every item `finished_goods_stock` when a
   division's P50 annual value was exactly zero.** Naive reading: apply METRICS.md §15's
   `annual_value >= P50` criterion literally in every case. Reality: PEM103 has 57% of its 87 items
   with zero trailing-12-month sales, pushing its P50 to exactly ฿0 — under the plain rule, EVERY
   item cleared the value threshold regardless of frequency, defeating the segmentation entirely.
   **Correct handling**: METRICS.md §15 now states that a zero P50 makes the value criterion
   undefined; classify by `order_frequency >= 6/yr` alone in that case, and report that the rule
   was used. PEM103's split changed from 87/0 to 14 finished_goods_stock / 73 component_stock_ato.
   Found: STATUS.md:938-954, `output/summary/phaseE1fix2r3_part1_zero_p50_report.md`. **V2**
   (independently recomputed by Modeler and Validator, exact match).

10. **A safety-stock formula subtracted the wrong baseline.** Naive/buggy reading (present in three
    places — the Modeler's script, the Validator's script, and the interactive page's embedded JS):
    `safety_stock = percentile(ltd_distribution, sl) − cum.mean()` (the empirical distribution's
    own historical mean). METRICS.md §4's literal text requires `percentile(...) − LTD` (the
    forecast-based point estimate) — these differ whenever the forecast and the historical average
    disagree, a confirmed code defect, not a modelling ambiguity. Found and fixed: STATUS.md
    Phase E1-fix / E1-fix-2 Part 2 (STATUS.md:473-481, 561-578). **V2** (independently re-derived
    and fixed in all three locations, regression test added).

11. **`query_sale_cost` omitted a filter the Modeler's own unit-cost function already applied,**
    letting non-Omni-Channel rows leak into two items' trailing-12-month unit-cost medians and
    accounting for 97.0% of a 6.34% Modeler/Validator stock_value gap for PEM107. **Correct
    handling**: added the same `revenue_type`/`status` filter METRICS.md §1 requires. Found and
    fixed 2026-09-22: STATUS.md, "PEM107's 6.34% stock_value gap" entry;
    `output/summary/phaseE1fix2r3_part2_pem107_trace_report.md`. **V2** (traced item-by-item to the
    exact root cause).

12. **The project's long-cited "73.2% on-time" figure was compared directly against `fill_rate`, an
    unlike measure.** Naive reading: 73.2% is a general on-time/fill-rate benchmark, usable as an
    acceptance-criterion ceiling. Reality: it is `on_time_exact` (delivered exactly ON the due
    date), row-weighted, 2026-only, PEM101-only, computed against `PlanDelDate` — it excludes early
    deliveries entirely and is not comparable to a unit-based fill rate. Corrected `not_late`
    figures (2023-2026, both weightings, per division) are far higher (PEM101 90.2%/87.9%, PEM103
    84.7%/88.6%, PEM107 86.3%/88.7%, row/unit-weighted). Found and corrected 2026-09-23: STATUS.md
    banner and Phase J2 entry; METRICS.md §19. Seven prior acceptance-criterion usages were tagged
    superseded, not deleted. **V2** for the corrected figures (independently recomputed by a
    Validator in the same task).

13. **Setting `assembly_time_days` above the median customer notice silently removed 36 items'
    entire policy.** Naive reading: raising a Tier-A default to its "robust upper bound" (7 days)
    is a conservative, safe change. Reality: METRICS.md §15's `component_stock_ato` criterion
    requires `assembly_time_days <= median_notice_days` (6 days for PEM101) — exceeding it made
    every one of PEM101's 36 `component_stock_ato` items match neither defined policy category,
    silently reported under a generic undefined label. **Correct handling**: reverted the default to
    3 days; METRICS.md §15 now names this state `component_stock_ato_infeasible` explicitly instead
    of leaving it undefined. Found and reverted same day: STATUS.md Phase J2 Part 0 entry. **V1**
    (downgraded from V2 by Validator, 2026-09-24: the "36 items" figure is computed once, when
    `assembly_time_days=7` was adopted in Phase J Part 4, and the same figure is cited again in
    Phase J2 Part 0 to justify reverting it — STATUS.md does not show a fresh, independent
    recomputation confirming the 36-item count after the revert, only pipeline parity tests
    (76/76 + 6/6) that check general output consistency, not this specific figure).

14. **`numpy.bool_(True) is True` evaluates to `False`** — a stability flag read back from a CSV via
    Python's `is True` silently forced every series to "Naive" instead of the intended model. Fixed
    to `==`. Found: STATUS.md:2413-2417 (rule-based-selection implementation). **V1** (one incident,
    code-level not data-level, kept because it produced a wrong RESULT from a naive reading of a
    round-tripped value, exactly the class of trap this section is for).

15. **An initial warehouse-classification pass wrongly flagged every code with zero issue-events
    among the 6 raw-material items (including FG01/FG11/FG21) as "not available."** Naive reading:
    no issue events recorded for an item in a warehouse means that warehouse holds none of it.
    Reality: those 6 items hold almost none of FG01's stock in the first place (144,094 units
    across the full 128-item scope belong to other items) — the ledger's silence there proves
    nothing about the Finished Goods actually sitting there. Found and corrected: STATUS.md
    Locked Decisions, "Warehouses are STAGES" investigation (STATUS.md:2985-2995). **V1**.

16. **A duplicate-detection join on `cube_Contract`'s free-text `product` field undercounted real
    matches.** Naive reading: 8 of 29 "confirmed duplicate" sets corroborated. Reality: rejoining on
    `Cube_CES`'s proper key (`ContractID`+`ItemCode`) gets a 100% match rate (29/29), fully
    reversing the earlier conclusion for most of the 29 sets (9 fully corroborated as genuine split
    lots vs. 5 previously, 16 unresolved vs. 21 previously). Found and corrected: STATUS.md:1580-1588.
    **V1** (downgraded from V2 by Validator, 2026-09-24: the source is one investigation's
    corrected re-join on the proper key, not a second independent agent or direction reconfirming
    the 29/29 match rate; a related control test in the same investigation (STATUS.md:1595-1600)
    found the underlying method has an ~11.5% false-negative rate, which argues against treating
    this as doubly confirmed).

17. **A test for whether `createDate` was ever revised after the fact could not fully rule it out,
    but also found no evidence for it beyond a small, one-directional lag** — recorded as a
    limitation, not resolved either way, and every later figure that depends on `createDate`/
    `forecast_date` being fixed at intake states this explicitly rather than treating it as settled.
    Found: STATUS.md, Date-column Validator investigation (STATUS.md:3303-3319). **H**, an
    assumption the project keeps flagging rather than quietly relying on.

18. **A fresh `Cube_CES` pull built for a channel-mix task added a `CtrDate >= '2023-01-01'` filter
    that looked harmless but was NOT equivalent to this project's established `not_late` method
    (METRICS.md Sec.18/19/20: `ForecastDelDate`-windowed, no `CtrDate` filter).** Naive reading: any
    date floor wide enough to cover the scope should give the same `not_late` figure. Reality: the
    `CtrDate` filter cut the pulled row count from 8,524 to 5,686 for PEM107 and produced a blended
    `not_late` (94.8%→52.8%) unrecognizable against this project's own already-established headline
    (86.6%→76.5%, Phase J3). **Correct handling**: recompute `not_late` from the older, unfiltered
    `output/data/phaseJ_cube_ces_351items.csv` pull for the Omni-channel figures (reproduces the
    established target almost exactly, 88.6%/76.5%); the new pull's Tendering-channel figures were
    kept but flagged directional-only, not precision-grade, since no unfiltered equivalent existed
    for Tendering. Found: Q23 Part 4, Analyst (`output/summary/phaseQ23_analyst_report.md`), this
    task, 2026-09-24. **V1** (one Analyst, one investigation; the affected script,
    `src/investigations/phaseQ23_explorer.py`, was not itself corrected — a downstream agent worked
    around it instead, so the query bug remains live in that file for any future reader).
    **FIXED AT SOURCE, 2026-09-24 (this task, Part 3)**: `phaseQ23_explorer.py`'s inline query
    replaced with a shared helper, `src/cube_ces_pull.py`, that pulls Cube_CES for an item-code
    scope with NO date filter at the SQL level, ever — the established, working pattern already
    used by `phaseJ_cube_ces_351items.csv`/`phaseJ3_validator_reconciliation.py`. A regression test
    (`tests/test_cube_ces_pull.py`) fails against the old filter and passes against the fix. Two
    downstream agents (Explorer 1 and the independent Validator, this task's Part 1/4) re-pulled
    Cube_CES via the fixed helper for PEM103/PEM107's full scope and report figures consistent with
    each other and with the pre-existing headline — no figure changed materially once the fix was
    in place, since the only prior "recorded" figures already used the pre-bug unfiltered file, not
    the buggy pull. **V2** for the fix itself (code change + passing regression test + two
    independent downstream re-pulls with no anomaly).

19. **It looks like the still-unresolved "which warehouses count as PEM101's usable/sellable stock"
    standing assumption (§5 item 9) must materially affect the robust Min/Max policy range METRICS.md
    §22 computes for PEM101 — it does not.** Naive reading: since the three candidate usable-stock
    definitions (`current` {FG01,FG21,WH21}; `fg_prefixed_only`; `all_stockholding_except_qa_fmto_fmts`
    {FG01,FG21,WH21,W4-1}) resolve to different warehouse-code sets, using a different one should
    move an item's computed Min/Max. Reality: `Min_e`/`Max_e` (METRICS.md §22) depend only on
    `r_months`/`s_months` and an item's own mean daily demand — the usable-stock definition enters
    nowhere in that formula, it only gates which (r,s,review,lead) combinations pass the Sec.20
    calibration tolerance. For PEM101, `current` alone already spans the full ensemble's `r_months`
    range (0.25–2.0); the other two definitions' extra/narrower passing sets contribute nothing
    beyond what `current` already covers. Comparing `range_ratio` computed from the full 139-member
    ensemble vs. the `current`-only 59-member subset gives a difference of exactly 0.0 for all 112
    eligible PEM101 items (`output/summary/phase22_modeler_stockdef_effect.csv`). **Correct handling:
    for PEM101 specifically, this open standing assumption can be set aside when reasoning about
    Min/Max policy ranges — it is not a live source of uncertainty for that question, even though it
    remains open for other purposes (e.g. actual on-hand stock value).** Found: this task, 2026-09-24,
    `src/investigations/phase22_modeler_part2.py`; independently re-derivable from the same two facts
    (the verified `Min_e` formula and the ensemble's own `r_months` range) rather than merely an
    empirical coincidence. **Level V2** (mathematically forced given the two verified facts, not
    just an observation that could differ by chance).

---

## 5. Unknowns

Facts the project needs but the data cannot supply, with the party that would know (as the source
itself names it).

1. **Assembly/production time** (raw-material consumption → assembled item becoming stock). No
   field in any table links these events. STATUS.md §6 (Missing Data by Phase), reaffirmed §8.5
   "Still open." Owner: **production / the business**.
2. **Target service level.** Not yet set anywhere in the data. STATUS.md §6, §8.5. Owner: **the
   business** (Phase 4 presents levels, does not pick one).
3. **Stockout cost.** No source identified; a `saleGM`-based lost-margin proxy was suggested by the
   business but is explicitly "an assumption if adopted, not a measured figure." STATUS.md §7
   (Red Team Review Findings), §8.5. Owner: not named beyond "the business."
4. **Make-versus-buy per item** (whether any Finished Goods item is ever bought complete instead of
   made in-house). Ambiguous from data (§1, Cube_ItemList.PurchasePrice note). STATUS.md §6. Owner:
   not named.
5. **Minimum order quantities / lot sizes.** Business confirmed this data does not exist at all.
   STATUS.md §8.3 "Removed from the data request list."
6. **Finished-goods movement history.** Business confirmed this does not exist. STATUS.md §8.3.
7. **Whether Tendering-channel stock for one focus item is the same physical stock as Omni Channel
   items.** Business confirmed this data does not exist. STATUS.md §8.3. Owner: was "the warehouse
   team" before being confirmed non-existent.
8. **Whether `forecast_date` is ever revised in place after PO intake.** Undetectable in this
   schema; no audit trail. STATUS.md §5 (Open Questions), Date-column Validator residuals. Owner:
   **IT / business**.
9. **Sellability of any "sellable warehouse" list, for every division without exception.** Cannot
   be verified from this data — no sales row carries a warehouse field, so the reverse direction to
   check it does not exist. STATUS.md Phase E2 readiness entry. Owner: **warehouse/operations
   team**.
10. **What system `Cube_CES` belongs to / what populates it.** Currently unprovable from read-only
    data. STATUS.md §5. Owner: not named.
11. **`jobcode`'s populating mechanism** (why it concatenates, why duplication correlates with it).
    Needs visibility into the stored procedure/view that populates it. STATUS.md §5, dated log
    correction. Owner: **IT / whoever owns the view or procedure**.
12. **The 2024 `Cube_Quotation` coverage gap** (25 rows vs. thousands in 2025/2026 for the same
    351-item scope) — real absence, different numbering scheme, or retention gap is undetermined;
    no further query was available under this session's one-connection rule. `output/summary/
    phaseJ2_explorerA_report.md` §3. Owner: not named (implicitly IT/whoever owns Cube_Quotation).
13. **What causes the real, anomalous day-0 delivery-date spike**
    (`ActualDelDate=PlanDelDate=ForecastDelDate` far more often than the surrounding distribution
    would predict), if not after-the-fact date revision — explicitly left open.
    `output/summary/phaseJ2_explorerB_report.md`. Owner: not named.
14. **The true production-batch date** (`cube_final.final_date` and neighbouring
    `fg_check_date`/`fg_pack_date`/`fg_final_date`) — this session's pull returned zero rows,
    almost certainly an interrupted-agent artifact; a fresh, uninterrupted pull is needed.
    `output/summary/phaseJ2_explorerD_report.md`. Owner: re-attemptable from data — no business
    input needed, just a connection that survives to completion.
15. **The real fulfilment/replenishment mechanism
    exactly in the source: a direct description from whoever runs production/warehouse planning of
    (1) real review frequency/trigger, (2) which physical stock (including non-"sellable"
    warehouses and component buffers) is actually treated as available, (3) whether/how production
    runs ahead of orders for the fuse/surge-arrester families that dominate fast delivery.
    `output/summary/phaseJ2_synthesis_report.md`. Owner: **production/warehouse planning**.
    **Partially corrected 2026-09-23 (kept, not deleted): the "not achievable from data alone"
    framing was itself premature.** Phase J's calibration replayed settings already known to be
    unfollowed, so it never actually tested whether the data supports a fitted (not assumed) set of
    Section 16 parameters. METRICS.md §20 (inverse calibration) proposes exactly that test,
    scheduled as J3, before concluding business input is the only route — see §6 Corrections log
    and PROJECT_GRAPH.md's critical path.
    **RESOLVED PARTIALLY, 2026-09-23 (Phase J3, Part 2, independently confirmed V2 — see §6):**
    PEM101 IS fittable to a realistic stock level (partially — no single parameter uniquely
    identified). **PEM103 and PEM107 are NOT fittable to a stationary reorder/order-up-to policy at
    a realistic stock level at all** — for different, well-evidenced reasons (PEM103: matching
    reality needs 5-12x more capital than the business holds; PEM107: no fixed policy fits both the
    2024-2025 and 2026 periods simultaneously, implying a real operational change between them, not
    a parameter-search failure). This is now a real, quantified answer, not an open unknown — see
    §6 Corrections log's new J3 entry and STATUS.md's Phase J3 entry for the full account. The
    business-input question named above is NARROWED, not closed: for PEM103, specifically whether
    production-batch timing (not warehouse stock) governs fulfilment; for PEM107, specifically what
    changed operationally between 2024-2025 and 2026.
16. **PEM103's Tendering-channel scope decision** — 65.5% of item-code value sits outside the
    Omni-Channel-only scope; a business call on whether it belongs in this project. STATUS.md §5,
    Phase C step 1 residual item 4. Owner: business.
17. ~~**PEM104's true volume** — whether 12 transactions is the complete picture, or real volume flows
    through an uncaptured division/channel. STATUS.md §5, item 5. Owner: not named.~~
    **RESOLVED, 2026-09-23 (business-confirmed): PEM104 is made to order.** 12 transactions across
    17 calendar months, and near-zero stock (STATUS.md:780-781), are consistent with a made-to-order
    business model, not evidence of a data gap or an uncaptured channel — see §7. The volume
    question is closed; no stock policy applies to PEM104 (PROJECT_GRAPH.md, dead end DE4).
18. **Whether the `PEM102-OLD`/`PEM107-OLD` tag mechanism is one reorganisation or two unrelated
    relabelings** — resolved at the filter level (business said which tag means which division)
    but the mechanism/reason itself was never explained. STATUS.md §5 item 1, cross-ref §8.1.
19. **Procurement/vendor lead time, full coverage.** No source has both clean data and full item
    coverage (§1: `Cube_emanu` unusable, `Cube_PO_Exact` 5.5-7.5% coverage, `Cube_PriceList`
    24/68-62/128 coverage, `Cube_Quotation.ctr_leadtime` inconsistent/order-circumstance-dependent).
    STATUS.md:2307-2316. Owner: **the purchasing team**, stated explicitly as needed for full
    coverage.

---

## 6. Corrections log

| Old claim | New claim | Date | Evidence |
|---|---|---|---|
| All queries filter on `division='PEM101'`, recorded as project-wide scope | That was only ever the pilot's condition; project scope is Omni Channel across every pricelist division, `division` is a grouping key not a filter | 2026-09-04 | STATUS.md Locked Decisions, "Project scope correction" |
| Exclude any row with a `-OLD` division suffix from scope | Never filter on `division` at all — pricelist is authoritative; database `division` (incl. `-OLD`) kept only as reference | 2026-09-04 (same day, later) | STATUS.md Locked Decisions, "Division source-of-truth correction" |
| `cube_Contract`'s 2025-01-01 floor means 2024 contract detail cannot be verified anywhere | Wrong — `Cube_CES` carries `ContractID` and `ItemCode` and covers 2024 fully | 2026-08-31 | STATUS.md:1573-1579 |
| Duplicate-set join via `cube_Contract`'s free-text `product` field: 8/29 matchable | Rejoin via `Cube_CES` `ContractID`+`ItemCode`: 100% (29/29) match; revised to 9 fully corroborated / 4 partial / 16 unresolved | 2026-08-31 | STATUS.md:1580-1588 |
| 3 Actual/MPS overlap cases leaning legitimate, not fully proven | Definitively resolved as legitimate multi-tranche orders via `Cube_CES`'s own Status/Qty fields; source of the MPS↔Backlog mapping fact | 2026-08-31 | STATUS.md:1624-1635 |
| jobcode mechanism hypothesis: a database JOIN fanout (one row per matching job) | Contradicted — the same complete job list repeats identically across a duplicate set's rows; mechanism still not understood beyond ruling this out | 2026-08-31 | STATUS.md:1605-1623 |
| `safety_stock = percentile(ltd_distribution, sl) − cum.mean()` (distribution's own mean), in the Modeler script, Validator script, and page JS | `percentile(...) − LTD` (forecast-based point estimate), per METRICS.md §4's literal text — a confirmed code defect | 2026-09-22 | STATUS.md Phase E1-fix / E1-fix-2 Part 2 |
| METRICS.md §4/§15 window wording ambiguous (whole-month rounding vs. exact days; item's own span vs. fixed window) | §4 requires exact days on the daily series, never rounded; §15 fixes both facts to the same trailing-12-months-ending-at-cutoff window | 2026-09-22 | STATUS.md Phase E1-fix-2 Part 0 |
| METRICS.md §14 confirmed demand sourced from the `Cube_Backlog` table | `Cube_CES Status='Backlog'` is the correct source — `Cube_Backlog` lags by ~13.6 hours, would over-count by 0.9% | 2026-09-22 | STATUS.md Phase E1-fix-2 Part 1 |
| METRICS.md §15: no zero-P50 special case; a division with P50=฿0 classified every item `finished_goods_stock` | If P50=0 exactly, the value criterion is undefined; classify by order_frequency alone | 2026-09-22 | STATUS.md, "zero-P50 rule" entry; `phaseE1fix2r3_part1_zero_p50_report.md` |
| PEM107's 6.34% Modeler/Validator stock_value gap: unattributed | Root cause: `query_sale_cost` missing the `revenue_type`/`status` filter, 97.0% of the gap from 2 items | 2026-09-22 | STATUS.md, "PEM107 stock_value gap" entry; `phaseE1fix2r3_part2_pem107_trace_report.md` |
| 73.2%/57.8% on-time figures cited project-wide as a general fill-rate benchmark | Was `on_time_exact`, row-weighted, 2026-only, PEM101-only, vs. `PlanDelDate` — not comparable to `fill_rate`; corrected `not_late` figures recorded per division, both weightings, 2023-2026 | 2026-09-23 | STATUS.md banner + Phase J2 entry; METRICS.md §19 |
| `assembly_time_days` default changed 3→7 ("robust upper bound") | Reverted 7→3 — made `component_stock_ato` infeasible for all 36 of PEM101's affected items; deferred until the real fulfilment mechanism is known | 2026-09-23 (same day) | STATUS.md Phase J2 Part 0 entry |
| `Cube_Quotation.report_date` treated as a usable quotation date | 99.94% identical to `forecast_date` — a disposition date, not a quotation-issue date; `create_date` is the defensible one | 2026-09-23 | `output/summary/phaseJ2_explorerA_report.md` §2 |
| Phase J's calibration_gap (baseline_fill_rate 8.2-1.6% vs. actual_on_time 86-98%, an 84-93pp gap) read as showing the Section 16 model's own mechanics (review cadence, lead time, min/max logic) fail against reality | **SUPERSEDED, kept not deleted.** The calibration design itself was flawed: it replayed the CURRENT min/max settings, which the project had already established nobody follows (existing settings are known-unusable as an input — see §1 Cube_Inventory_Exact trust note). The 89-point gap therefore shows today's settings are disconnected from real practice, not that Section 16's own mechanics are wrong — that question is still open. Explorer D's batch data was lost mid-task (§4 Trap 7), not resolved either way. Inverse calibration (METRICS.md §20) had not been attempted; the data route is not exhausted, pursued in J3. | 2026-09-23 | This task (Q10 correction); METRICS.md §20; PROJECT_GRAPH.md critical-path note |
| Explorer B (due dates aligned to delivery) — CONTRADICTS, moderate-high confidence | **SUPERSEDED, kept not deleted.** UNDETERMINED: a day-0 delivery spike appearing equally on `ForecastDelDate` and `PlanDelDate` is consistent both with due dates being set to match delivery AND with the business scheduling shipment on the promised day (normal practice) — the data available cannot separate the two. The original CONTRADICTS verdict overstated what the evidence rules out. | 2026-09-23 | STATUS.md Phase J2 entry, Explorer B (corrected); `output/summary/phaseJ2_explorerB_report.md` |
| Phase J's 97.8% actual_on_time (PEM101, unit-weighted) vs. Phase J2's 87.9% not_late (PEM101, unit-weighted) — an unexplained 9.9pp gap between two figures both in the repo | **RECONCILED, not a bug either side.** Item scope, Status filter and weighting are identical between the two computations; the ONLY real difference is the window: Phase J bounds by `ForecastDelDate` in [2024-01, 2026-07]; Phase J2 bucketed by `CtrDate` YEAR 2023-2026, which pulls in 2023 (55.97% unit-weighted not_late, a genuinely much worse year) alongside 2024-2026 (~97-99%). Quantified: -10.29pp from including 2023, +0.35pp from the bucketing-method difference, net -9.93pp — matches the observed gap almost exactly. `ForecastDelDate` is the METRICS.md Sec.18/19/20-correct field going forward. | 2026-09-23 | `output/summary/phaseJ3_validator_reconciliation.md` (independent recomputation, one Validator, one session — V1) |
| "The data route is not exhausted" (this file's own 2026-09-23 correction, above) — an open question, not yet a result | **ANSWERED, per-division, 2026-09-23 (Phase J3 Part 2, METRICS.md Sec.20 inverse_calibration, independently confirmed — Part 3 Validator, own code, 12/12 figures match).** PEM101: partially calibratable — 59 of 4,130 grid combinations reproduce both the 2024-2025 and 2026+ periods within tolerance (not_late ±3pp, stock value ±15%) at a realistic capital level, but no single parameter is uniquely identified (r_months ambiguous 0.25-2.0 months, s_months 1.5-3.0, review interval 1-30 days, lead time 1-30 days — all four span more than one grid step). PEM103: NOT calibratable to a stationary policy at a realistic stock level — a fit exists for `not_late` alone (117 combinations), but every one needs 5-12x more capital than the business holds (best: THB 57.6M simulated vs. THB 6.06M real on-hand). PEM107: NOT calibratable at all — no single parameter set fits both periods simultaneously (the best joint compromise is still 14-18 percentage points off on one side), implying a genuine operational change between 2024-2025 and 2026, not a search failure. | 2026-09-23 | `output/summary/phaseJ3_2_calibration_summary.json`, `phaseJ3_2_grid_{PEM101,PEM103,PEM107}.csv`, `phaseJ3_validator2_independent_check.md` |
| PEM104's exclusion reason recorded as "insufficient data" (12 transactions across 17 calendar months, too few to fit any forecasting model at any aggregation level) | **SUPERSEDED, kept not deleted.** The underlying reason is that PEM104 is made to order by business model — no stock policy is applicable, and the low, sporadic transaction count is a structural consequence of that business model, not a data-collection gap. "Insufficient data" was a correct symptom, not the cause. | 2026-09-23 | STATUS.md Locked Decisions, "Exclusion — PEM104" (STATUS.md:4817-4824); this task, §7 below |
| Q23 open: "does the Omni Channel scope explain observed stock/delivery behaviour, or must combined Omni+Tendering be included?" | **ANSWERED, 2026-09-24 (this task, METRICS.md §21, four agents — Explorer/Modeler/Analyst/independent from-scratch Validator).** NO accuracy or calibration case for widening scope: Omni+Tendering forecasts Omni demand no more accurately in any of 3 divisions (worse for PEM107, t=2.43, and PEM103's dominant focus item, t=2.61 — independently reproduced by the Validator, same direction/significance in all 3, MAE within 3%); PEM103's combined-demand calibration gap WIDENS to 27-37x real capital (vs J3's Omni-only 5-12x), reinforcing Q22's tender-pipeline finding rather than a shared-stock one. PEM107's 2026 not_late decline (86.6%→76.5%) DOES coincide with a real, twice-independently-confirmed channel-mix reversal (Tendering value share 28-39%→72.3-72.4%) and a genuine drop in Omni's own not_late (88.6%→76.5%, not a compositional artifact) — supported (not proven), level H. Omni Channel remains the project's default scope. | 2026-09-24 | `output/summary/phaseQ23_{explorer,modeler,analyst,validator}_report.md`; PROJECT_GRAPH.md Q23/Q22 rows; STATUS.md Q23 entry |
| "Phase 1 reported 136 codes present on both the PEM103 and PEM107 sheets" (premise stated in this task's own instructions; no prior STATUS.md/DATA_MAP.md passage matching this exact claim could be located) | **CHECKED AGAINST THE FILE AS IT CURRENTLY EXISTS, 2026-09-24: ZERO overlap.** An exhaustive, both-direction re-read of every sheet in `reference/pricelist.xlsx` (visible AND hidden `Version1`/differently-spaced-name duplicates) finds no item code shared between any PEM103-named sheet and any PEM107-named sheet. 136 is simply PEM107's own total code count (consistent across its own hidden/visible sheet pair) — not, and apparently never was correctly, an overlap figure; the likely origin is a conflation of "PEM107 has 136 codes" with an overlap claim. Does not rule out the pricelist file having been edited since whenever the original claim was made (no version history available) — a residual limitation, not resolved further. | 2026-09-24 | This task, Explorer 1 (`output/summary/phase136_explorer1_report.md`) |
| PEM103/PEM107's 2026 channel-mix reversal (Q23, above): cause not yet investigated at the point Q23 closed | **INVESTIGATED, 2026-09-24 (this task): supports a BUSINESS change, not a recording change, for BOTH divisions — V2, three independent checks converge** (two Explorers, different angles, plus an independent from-scratch Validator): customer channel identity is essentially fixed (0 switchers in PEM103, at most 1 noise-level switcher in PEM107, independently reconfirmed); order size and customer segment directly contradict a same-order-relabeling reading; no clean step-change date exists in either division (lumpy, contract-driven spikes in both years, independently reconfirmed); PEM107's Tendering notice days genuinely grew 40→60 between years. **The business's stated view (level A, recorded 2026-09-23: "most likely a recording-method change") is recorded as stated, alongside this direct data contradiction — both stated, neither chosen** (AGENTS.md rule 4/9). No reconstruction/reassignment rule proposed (not warranted); no G1/forward-test correction needed on these grounds; the PEM107 capacity-diversion hypothesis (Q23) SURVIVES and is strengthened on its "is the surge real" dimension, still level H. | 2026-09-24 | This task: `output/summary/phase136_explorer1_report.md`, `phase136_explorer2_report.md`, `phase136_synthesis_report.md`, `phase136_validator_report.md`; DATA_MAP.md §7 |

---

## 7. Division business models (business-confirmed)

Business-confirmed statements about what a division's underlying business actually is — not
themselves derived from data, but consistent with data already recorded elsewhere in this file.
**A** level (business-confirmed, not independently verifiable from data alone).

**PEM103 is transformers, and most of its business is tendering work for electricity utilities**
— business-confirmed 2026-09-23. Consistent with data already recorded in this file:
- Under Phase C, the Omni Channel filter captured only 33.3% of PEM103's item-code value; 65.5%
  was Tendering-channel (STATUS.md:3894-3895) — §5 Unknowns item 16.
- Under Phase J3, 69.3% of PEM103's delivered contracts trace to a production-batch token that
  existed before the PO — far higher than PEM101's 2.0% (STATUS.md:1328; §2, jobcode/jobno/
  OLMJobCode entry).
- A stock-based reorder policy could not reproduce PEM103's observed delivery performance without
  5-12x more capital than the business actually holds (STATUS.md:1351; §6 Corrections log, Phase
  J3 entry; §3 Joins, batch-traceability row).
- **Q23, 2026-09-24: PEM103's Omni/Tendering split swings sharply year to year, not a stable
  ratio** — Tendering dominated 2025 (88.5% of value) but Omni Channel dominated the partial 2026
  (96.6% of value, 3.4% Tendering); 2024 sat in between (37.7% Omni / 62.3% Tendering). This is NOT
  a contradiction of the 33.3%/65.5% Phase C figure above (a different, earlier aggregate window)
  — both are recorded, neither chosen for the reader. **V2** (independently recomputed twice from
  two separate fresh DB pulls — Explorer and Validator, `output/summary/phaseQ23_explorer_report.md`,
  `phaseQ23_validator_report.md` — exact agreement to 2 decimal places). Feeding this combined
  (Omni+Tendering) demand into a stock-based-policy calibration makes PEM103's capital gap WORSE
  (27-37x real stock, vs 5-12x Omni-only, J3) — reinforcing, not weakening, the tender-pipeline
  finding above. See §6 Corrections log, Q23 entry.

**PEM107's Omni/Tendering split also reverses, in the opposite direction, in exactly the year its
delivery performance drops** — Omni Channel dominated 2025 (71.6% of value) but Tendering dominates
2026 (72.3%); Omni's OWN not_late fell from 88.6% (2024-2025) to 76.5% (2026) in the same period —
not merely a compositional artifact of more orders shifting into a channel with different baseline
performance. **V2** for the channel-mix reversal (independently recomputed twice, Explorer and
Validator, exact agreement). **H** (supported, not proven) for the causal reading that shared
capacity/stock was diverted toward Tendering — an alternative explanation (an independent 2026
capacity constraint affecting both channels, no actual resource competition) cannot be ruled out
from this data alone. Found: Q23 Part 4, Analyst, 2026-09-24
(`output/summary/phaseQ23_analyst_report.md`). See §4 Trap 18 for a data-quality issue found and
worked around while establishing this.

**Business view, recorded 2026-09-23 (level A): the PEM103/PEM107 2026 channel-mix reversal "most
likely reflects a change in recording method, not a change in what the divisions sell."** This is
recorded as stated, per this project's convention that a business-confirmed statement is level A
regardless of what independent analysis later finds. **It is recorded here alongside a direct
data-derived contradiction, per AGENTS.md rule 4/9 (report contradictions explicitly, do not pick a
side):**

**Data finding, 2026-09-24 (this task): the evidence supports a BUSINESS change for BOTH divisions,
not a recording change** — **V2**, converging from three independent checks (two Explorers on
different angles, order-side and attribute-side, neither reading the other's files, PLUS an
independent from-scratch Validator recomputation reading none of the Explorers' files):
- **Customer channel identity is essentially fixed, not flipped.** Of customers active in both 2025
  and 2026, 0/46 (PEM103, Explorer 1) or 0/43 (PEM103, Validator, a slightly different both-years
  customer count from an independently-derived pull — same zero-switch conclusion) changed their
  dominant channel; PEM107 shows at most 1 switcher out of 86-87 (Explorer 1: 2.13% of qty;
  Validator: 0.02-0.03% of qty — both agree the switch is noise-level, not a Tendering↔Omni flip at
  all in the Validator's re-read). If a database recording rule had flipped in place, existing
  customers' recorded channel is exactly what would change — it did not, independently confirmed
  twice.
- **Order size and customer segment directly contradict a same-order relabeling** (Explorer 2):
  PEM103's 2026 Omni orders (median contract THB 295,000) match 2025's OWN Omni scale, not 2025's
  Tendering scale (THB 142.5M, ~483x larger) as a relabeling would require; PEM107's 2026 Tendering
  orders (median THB 7.5M) are ~12x LARGER than 2025's own Tendering, not smaller/Omni-like.
  Customer-segment composition (a real field, `customer_segment` — institutional/utility for
  Tendering, retail/dealer/contractor for Omni) is stable across both years for both divisions, and
  customer overlap between the channels that supposedly swapped is ~0%.
- **No clean step-change date; timing is lumpy and contract-driven, in both years, independently
  reconfirmed** (Explorer 1 AND Validator, separately): PEM103's 2025 Tendering share comes from two
  isolated giant months (Jan 97.9%, Jun 98.9%, each 1-2 large transformer contracts); PEM107's
  Tendering-heavy months land in DIFFERENT calendar months in 2025 vs 2026, not a single date after
  which the series changes character and stays changed. A recording-rule flip (like the historical
  `-OLD` division-tag swap, which touched thousands of rows continuously) would not naturally
  produce this pattern.
- **A genuine attribute shift, not attributable to relabeling** (Validator, one attribute,
  independently chosen): PEM107's Tendering-order notice (`forecast_date - createDate`) grew from a
  median 40 days (2025) to 60 days (2026) on comparable sample sizes (45 vs 49 rows) — a real
  lead-time change a pure relabeling of the same orders would not produce.
- **The "136 codes present on both the PEM103 and PEM107 sheets" premise does not hold against the
  pricelist file as it currently exists** — an exhaustive, both-direction re-read of every sheet
  (visible AND hidden `Version1`) finds ZERO codes shared between any PEM103-named and PEM107-named
  sheet (Explorer 1). 136 is simply PEM107's own total code count. This rules out a pricelist
  reference-data artifact as a third explanation for either division's item-level channel flips.
  **V2** (exhaustive, both-direction check). See §6 Corrections log.

**Both positions stand recorded, neither chosen for the reader**: the business says recording
change (level A); the data, from three independent angles, says business/composition change (level
V2). **Recommendation (not a decision): this should go back to the business as a specific,
falsifiable question** — was there a named system/process/form change to how Tendering orders are
entered or classified, and on what date? If no such specific change can be named, the
recording-change hypothesis has no remaining mechanism to point to. Found: this task's Explorer 1
(`output/summary/phase136_explorer1_report.md`), Explorer 2
(`output/summary/phase136_explorer2_report.md`), Synthesis
(`output/summary/phase136_synthesis_report.md`), and independent Validator
(`output/summary/phase136_validator_report.md`), 2026-09-24.

**PEM107 capacity-diversion hypothesis (above): SURVIVES, and is strengthened on one dimension —
still level H, not proven.** The prior task's own conditional ("if the channel shift is a recording
artifact, the hypothesis loses its basis and must be downgraded") does not fire, since its
antecedent is false (the shift is not an artifact, per the finding above). A CONFIRMED-REAL
Tendering surge (genuine institutional/utility demand, not relabeled retail orders) is, if
anything, a more concrete basis for a capacity-diversion story than a merely apparent one — real
large orders genuinely compete for real finished-goods stock and production time. The unresolved
question is unchanged: whether shared capacity was actually diverted (a causal mechanism, still not
directly observed) versus an independent 2026 operational constraint affecting both channels
without real resource competition. Neither this task nor the prior one distinguishes those two
readings.

**No effect on the G1 Omni forecast or forward-test log for PEM103/PEM107 on the grounds
investigated here** — the project's forecast scope has always been Omni-Channel-only, and this
task finds that tag to be real and customer-linked, not a database artifact contaminating which
rows count as Omni; there is nothing to retroactively reassign. A separate, pre-existing caution
survives and is reaffirmed, not newly created: PEM103/PEM107's demand (including within the
Omni-only series the forecast consumes) is driven by a churning customer population placing lumpy,
large, tender-adjacent orders — grounds for continued wide uncertainty bands on these two
divisions' G1 point forecasts, not for treating the 2026-09-30 scoring as provisional. See
`output/summary/phase136_synthesis_report.md` §4.

**PEM104 is made to order** — business-confirmed 2026-09-23. Consistent with data already recorded
in this file:
- Only 12 transactions across 17 calendar months exist for PEM104's item codes (STATUS.md:4819,
  Phase C step 1 log entry) — a low, sporadic count expected of a made-to-order business, not a
  data gap.
- PEM104 shows essentially no stock anywhere, HIGH confidence, independently confirmed by
  `Cube_Inventory_Aging` (STATUS.md:780-781, Phase E2 readiness) — consistent with holding no
  finished-goods buffer because nothing is produced until an order exists.

This changes the stated reason for PEM104's exclusion from stock/inventory-policy work: **made to
order by business model, with no stock policy applicable** — not "insufficient data" (§6
Corrections log, above; PROJECT_GRAPH.md, dead end DE4).
