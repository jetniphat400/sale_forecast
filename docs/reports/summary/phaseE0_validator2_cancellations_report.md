# Phase E0.2 — Validator 2: Cancellations in the Demand Series

**This report supersedes the 2026-09-18 blocked attempt** (the SQL Server
login's password had expired at that time; it has since been reset). All
four sub-questions below were run against a live, fresh database connection
on 2026-09-18. No content from the blocked attempt is carried forward as a
finding — every number below is a direct query result, cited by exact SQL.

**Reusable script**: `src/investigations/phaseE0_cancellations_validator2.py`
(re-running it reproduces every figure in this report). **Supporting CSVs**:
`output/summary/phaseE0_validator2_*.csv` (see citations below).

**Role and scope**: Validator, diagnostic only. No data, config, or pipeline
script was modified. No cancelled or partially-cancelled order was removed
from any file or dataset anywhere.

## Method (reused exactly from the prior blocked attempt's scoping — not re-derived)

- Join key: `(ContractID, ItemCode)` on `Cube_CES` ↔ `(contractid, itemcode)`
  on `cube_Sale_APD` — the same key used in the project's prior row-level
  reconciliation (`src/investigations/verify_ces_status_mapping.py`,
  `verify_ces_pre2024_detail.py`, STATUS.md "Row-level Cube_CES verification",
  2026-08-31).
- `Cube_CES` qty = `ActualQty + BacklogQty`, value = `ActualPrice +
  BacklogPrice`. `cube_Sale_APD` qty/value = its own `qty`/`sale` columns.
  Confirmed against `INFORMATION_SCHEMA`-equivalent (`SELECT TOP 0 * FROM
  ...`) before use — column names are exactly as named in `src/load_data_full.py`
  and the `Cube_CES` verification scripts, not assumed.
- Division is attached from the pricelist (`config['sheet_to_division']`),
  never from `Cube_CES.ManuDivision` or `cube_Sale_APD.division` (both
  reference-only, per the locked division source-of-truth rule, STATUS.md
  2026-09-04). Checked: no item code appears on more than one pricelist
  sheet, so this attribution is unambiguous (`load_pricelist_map()`,
  the script's own guard raises if that ever changes).
- Production series definition reused exactly from `src/load_data_full.py`
  and `config/config.yaml`: `revenue_type = 'Omni Channel'`, `status IN
  ('Actual','MPS')`, `source_table = cube_Sale_APD`, `createDate >=
  date_range.start (2024-01-01)`. Item universe widened here to the full
  pricelist (445 codes, all 6 visible sheets), not just the Fuse/Surge
  Arrester 128-code category pilot — this is the project's actual full scope
  per the 2026-09-04 "Project scope correction", and only pricelist items can
  ever appear in the production series at all (`load_data_full.py` raises if
  an item has no pricelist division mapping).

## Part 0 — Database access

**Verified from data.** `run_query('SELECT 1 AS test')` via `src/db.py`
succeeded on the first attempt this session (result: `test=1`). The
previously-expired SQL Server password for `jetniphat.boo` has been reset
(per the human's note); no credential was written, printed, or logged
anywhere in this session or in the script.

## Sub-question 1 — Cube_CES Cancel rows: count, value, date range

**Query** (table-wide, no division/revenue_type/item filter — a fresh pull,
not reused from any prior session):
```sql
SELECT ContractID, ItemCode, CtrDate, ActualQty, BacklogQty, ActualPrice,
       BacklogPrice, PlanQty, RevenueType, ManuDivision
FROM Cube_CES
WHERE Status = 'Cancel'
```
Output: `output/summary/phaseE0_validator2_cancel_rows_tablewide.csv`.

**Verified from data**:
- **2,423 rows** table-wide (matches the count STATUS.md's 2026-08-31
  table-wide pull recorded — same row population, now with the value/date
  detail that pull never captured).
- Total qty (ActualQty+BacklogQty): **151,865,368.2**. Total value
  (ActualPrice+BacklogPrice): **฿9,903,099,704.17**.
- `CtrDate` range: **2013-08-22 to 2026-02-25**.
- **These table-wide totals are dominated by items outside this project's
  scope entirely.** Of the 2,423 rows, only **553 rows (22.8%), covering 136
  distinct item codes**, are for item codes that exist anywhere in the
  pricelist (the project's item universe) — the rest (1,870 rows, ฿9.83
  billion of the ฿9.90 billion total) are for item codes such as
  `SBP101-EG`, `BP-0001`, `NSPC_M` that never appear in the pricelist at all,
  including a single outlier row (`CTR-2023-05384`/`SBP101-EG`) worth ~79.7
  million qty / ฿405 million alone. **Only the 553 pricelist-scope rows can
  ever be relevant to this project's demand series**, since
  `src/load_data_full.py` requires every item to resolve to a pricelist
  division and raises an error otherwise. Pricelist-scope subtotal: qty
  49,861, value ฿68,283,214.86, spanning 2014–2025 (136 distinct codes).
  Source: `output/summary/phaseE0_validator2_cancel_rows_pricelist_scope.csv`.
- Pricelist-scope Cancel rows by division (pricelist-attached, not
  `ManuDivision`): CI101 29 rows/523 qty/฿9.86M; PEM101 330 rows/48,053
  qty/฿30.88M; PEM102 4 rows/4 qty/฿0.90M; PEM103 25 rows/51 qty/฿6.18M;
  PEM107 165 rows/1,230 qty/฿20.47M. Source:
  `output/summary/phaseE0_validator2_cancel_by_division_pricelist_scope.csv`.
  (PEM104 is excluded from forecasting per the locked decision, so its
  absence here is expected, not a gap.)
- Pricelist-scope Cancel rows by `CtrDate` year: almost entirely **before**
  the production series' own data window (2024-01-01+): 2014 (2), 2017 (19),
  2018 (90), 2019 (54), 2020 (60), 2021 (65), 2022 (73), 2023 (141), 2024
  (47), 2025 (2). **Only 49 of 553 rows (8.9%) fall in the production
  series' 2024+ window.** Source:
  `output/summary/phaseE0_validator2_cancel_by_year_pricelist_scope.csv`.

## Sub-question 2 — Do cancelled pairs still count as Actual/MPS demand?

**Query** (pricelist-scope itemcodes, matched to the 548 distinct
pricelist-scope Cancel `(ContractID, ItemCode)` pairs):
```sql
SELECT contractid, itemcode, qty, sale, status, createDate,
       division AS division_db_raw, revenue_type
FROM cube_Sale_APD
WHERE itemcode IN (<136 pricelist-scope Cancel itemcodes>)
  AND revenue_type = 'Omni Channel'
  AND status IN ('Actual','MPS')
```
then joined in pandas on `(contractid, itemcode)` against the 548 cancelled
pairs. A second, wider version was also run using all 2,150 table-wide
Cancel pairs (any item code, not just pricelist-scope) as a robustness
cross-check. Outputs:
`output/summary/phaseE0_validator2_cancelled_pairs_still_actual_mps.csv`
(0 rows, header only).

**Verified from data: ZERO cancelled (contract, item) pairs appear as
Actual/MPS demand anywhere in `cube_Sale_APD`.**
- Pricelist-scope: 0 of 548 distinct cancelled pairs matched; 0 rows, 0 qty,
  0 value.
- Table-wide robustness check (any item code, 2,150 pairs): also 0 matches.
  This rules out the pricelist restriction itself as the cause of the null
  result — even allowing every non-project item code, no cancelled pair
  reappears as Actual/MPS anywhere in `cube_Sale_APD`.
- **Positive control confirms the join key itself works and this is a real
  finding, not a broken join or a naming mismatch**: the same 136
  pricelist-scope itemcodes' *non-cancelled* Cube_CES rows (`Status IN
  ('Actual','Backlog')`, `CtrDate >= 2024-01-01`) match a `cube_Sale_APD`
  Actual/MPS pair at **31,259 of 31,411 pairs (99.52%)** — consistent with
  the project's prior overall ~99.8% row-level Cube_CES↔cube_Sale_APD
  agreement (STATUS.md, 2026-08-31). The join method reliably finds matches
  when they exist; it correctly finds none for cancelled pairs.
- **A structural explanation, offered as a supported hypothesis, not
  verified further**: a contract's `Cube_CES` status appears to be a single
  current-state field per (contract, item) — a contract that is `Cancel` in
  `Cube_CES` does not seem to carry a separate, still-open `Actual`/`MPS`
  record in `cube_Sale_APD` for the same key. This is consistent with, but
  not proven by, the 99.52% positive-control rate (which shows the two
  systems track status consistently for non-cancelled rows too). No
  independent system (e.g. a customer-side order record) was checked, so per
  `CONVENTIONS.md`'s cube-agreement rule this is read as "the two systems are
  consistent with each other on cancellation status," not as proof that
  every genuinely-cancelled order is correctly excluded from demand
  everywhere.

## Sub-question 3 — Share of demand and effect on focus items

**Given the sub-question 2 result (0 matched pairs), the cancellation-share
and focus-item questions have a direct, verified answer: zero.**

**Total production series (denominator), for context** — query:
```sql
SELECT SUM(qty) AS total_qty, SUM(sale) AS total_sale, COUNT(*) AS n_rows,
       MIN(createDate) AS mn, MAX(createDate) AS mx
FROM cube_Sale_APD
WHERE itemcode IN (<all 445 pricelist item codes>)
  AND revenue_type = 'Omni Channel' AND status IN ('Actual','MPS')
  AND createDate >= '2024-01-01'
```
Result: **37,287 rows, qty = 3,536,958.0, value = ฿2,075,984,031.45**,
2024-01-03 to 2026-09-17 (verified from data).

- **Share of total production-series demand (qty and value): 0 / 3,536,958 =
  0.0000% (qty); 0 / ฿2,075,984,031.45 = 0.0000% (value). Verified from
  data.**
- **Share of each Type's demand: 0.0000% for every Type**, for the same
  reason (numerator is 0 everywhere; no Type-level breakdown table is
  produced since there is nothing non-zero to break down).
- **Effect on the 3 focus items — verified from data, effect is NONE**:
  - `EEE-F-FC-1040010002`: 38 Cancel rows found (query:
    `output/summary/phaseE0_validator2_focus_item_cancel_rows.csv`), all with
    `CtrDate` in 2018–2023 (before the production series' 2024-01-01 start).
    0 of these contracts appear as Actual/MPS demand anywhere (already
    covered by the 0-match result above, since these 38 rows are a subset of
    the 548 pricelist-scope pairs tested).
  - `HS-F-99-0213`: 4 Cancel rows, `CtrDate` 2019–2020. Same result: 0 match.
  - `HS-F-99-02110`: 3 Cancel rows, `CtrDate` 2020–2021. Same result: 0
    match.
  - **None of the three focus items' forecasts are affected by cancelled
    orders being miscounted as demand**, because no cancelled contract for
    any of them reappears as Actual/MPS anywhere in `cube_Sale_APD`.

**Negligibility threshold, stated explicitly per the ground rules**: this
report adopts **<0.5% of total production-series qty or value** as the
threshold below which a cancellation effect is called negligible (chosen
because it is an order of magnitude below the smallest effect size this
project has treated as material elsewhere, e.g. the 0.42% cross-division
exclusion documented in STATUS.md's "Cross-division demand" entry). **The
measured effect is 0.0000% — not merely below this threshold but exactly
zero within the checked scope** (pricelist-scope and table-wide,
cross-validated by a working positive control). This is stated as a
finding **about this specific mechanism** (cancelled `Cube_CES` contracts
resurfacing as `Actual`/`MPS` `cube_Sale_APD` rows under the same contract+
item key) — it does not certify that the demand series is free of every
possible over-counting risk (see Part 4 and the Recommendation below).

## Sub-question 4 — Partial cancellations (`PlanQty > ActualQty + BacklogQty`)

**Query** (column names confirmed against `Cube_CES`'s schema before use —
`PlanQty`, `ActualQty`, `BacklogQty` all exist exactly as named, no
substitution needed):
```sql
SELECT ContractID, ItemCode, CtrDate, PlanID, PlanQty, ActualQty, BacklogQty,
       ActualPrice, BacklogPrice, ContractPrice, Status
FROM Cube_CES
WHERE PlanQty IS NOT NULL
  AND PlanQty > (ISNULL(ActualQty, 0) + ISNULL(BacklogQty, 0))
```
Output: `output/summary/phaseE0_validator2_partial_shortfall_all_prefixes.csv`
(23,633 rows); confirmed-contract subset:
`output/summary/phaseE0_validator2_partial_shortfall_ctr_only.csv` (0 rows).

**Verified from data — the literal shortfall condition never occurs for a
single confirmed contract in `Cube_CES`:**
- **23,633 rows total** meet `PlanQty > ActualQty + BacklogQty`, total
  shortfall qty 2,889,944.0 — but **every one of them has a `ContractID`
  prefix of `QTN-` (22,988), `OQ-` (546), `ENQIN-` (97), or `OPP-` (2)** —
  i.e. quotation/enquiry-stage records, not confirmed contracts. **0 of the
  23,633 have a `CTR-` (confirmed-contract) `ContractID`.**
- A second, exhaustive check confirms this is structural, not incidental:
  among **all 143,936** `Cube_CES` rows with a `CTR-` `ContractID` and a
  non-null `PlanQty` (covering every `Status` value on confirmed contracts —
  `Actual` 138,487, `Backlog` 3,026, `Cancel` 2,423), **`PlanQty` equals
  `ActualQty + BacklogQty` exactly on all 143,936 rows — 0 have `PlanQty`
  greater, 0 have it smaller.** This holds even for `Cancel`-status rows: a
  cancelled contract's `PlanQty` is recorded equal to its final
  `ActualQty + BacklogQty` (frequently both near-zero), not to some larger
  originally-quoted amount that a cancellation shrank.
- **Consequence, stated plainly**: `PlanQty` on a confirmed `Cube_CES`
  contract does not behave as an "originally planned, later reduced"
  quantity — it appears to always track whatever `ActualQty + BacklogQty`
  currently is. The task's literal partial-cancellation signal (`PlanQty >
  ActualQty + BacklogQty`) is therefore **not observable on confirmed
  contracts with this data**, and the three-way bucketing
  (cancellation / adjustment / cannot-be-determined) requested in the brief
  has **zero confirmed-contract rows to bucket** — the population it would
  apply to is empty.
- **Cannot be determined**: whether a genuinely different, unrecorded
  "original plan quantity before reduction" ever existed for a confirmed
  contract. `Cube_CES` does not appear to retain that history at the
  contract-row level (only the current, reconciled state); no other table
  checked in this session carries it. This is reported as a data-model
  limitation, not evidence either way about whether partial cancellations
  happen in the business.
- **Supported hypothesis, not verified further**: the 23,633 quotation-stage
  shortfall rows likely represent normal quote-negotiation activity
  (quoted quantity not yet, or never, converted to an order) rather than
  cancellations of confirmed demand — quotations are pre-order records that
  never entered `cube_Sale_APD`'s Actual/MPS series in the first place, so
  even if some of them represent "lost" business, they were never counted as
  demand to begin with and cannot cause the series to overstate demand. This
  is a hypothesis about business process, not confirmed by any additional
  cross-check in this session (e.g. no customer-side record of quote
  conversion was available to test it against).

## Recommendation

**Configurable assumption / no-change recommendation, backed by the evidence
above**: **do not add any cancellation-filtering step to the demand series**
as currently built (`revenue_type='Omni Channel'`, `status IN
('Actual','MPS')`, keyed on `createDate`/`forecast_date`). Reasoning,
stated point by point with its verdict label:

1. **Verified from data**: cancelled `Cube_CES` contracts do not resurface as
   `Actual`/`MPS` `cube_Sale_APD` rows under the same `(contract, item)` key
   — 0 of 548 pricelist-scope pairs, 0 of 2,150 table-wide pairs, with a
   working positive control (99.52% match rate for non-cancelled pairs)
   ruling out a broken join as the explanation. There is no cancellation
   leakage to correct via this mechanism.
2. **Verified from data**: the literal partial-cancellation signal
   (`PlanQty > ActualQty + BacklogQty`) has zero confirmed-contract rows to
   act on; nothing exists to filter, adjust, or flag today under this
   definition.
3. **Cannot be determined**: whether some other, unchecked mechanism could
   let a cancelled or partially-fulfilled order inflate demand (e.g. a
   status value other than `Cancel` used inconsistently, or a data-entry
   error outside this join key's reach). This report only rules out the two
   specific mechanisms the task asked about.
4. If a genuinely independent signal for order cancellation becomes
   available in the future (e.g. a customer-side or ERP-side cancellation
   flag not derived from the same `Cube_CES`/`cube_Sale_APD` upstream
   source), re-running this reusable script against it would be
   straightforward — but per `CONVENTIONS.md`'s cube-agreement rule, a
   second cube fed by the same upstream process would not add real
   independent verification.

**No cancelled or partially-cancelled order has been removed from any file,
config, or dataset by this session** — this is a diagnostic finding only,
per the Validator role.

## Summary table

| Metric | Value | Verdict |
|---|---|---|
| Total Cancel rows (table-wide) / value / date range | 2,423 rows; qty 151,865,368.2; value ฿9,903,099,704.17; CtrDate 2013-08-22 to 2026-02-25 | Verified from data |
| Of which, pricelist-scope (relevant to this project) | 553 rows, 136 distinct item codes; qty 49,861; value ฿68,283,214.86 | Verified from data |
| Cancelled pairs still Actual/MPS in cube_Sale_APD (count/value) | 0 pairs, 0 rows, 0 qty, ฿0 (pricelist-scope AND table-wide) | Verified from data |
| % of total production-series demand (qty/value) | 0.0000% / 0.0000% (denominator: 3,536,958 qty, ฿2,075,984,031.45) | Verified from data |
| Effect on `EEE-F-FC-1040010002` | 38 Cancel rows (2018–2023), 0 matched to Actual/MPS — no effect | Verified from data |
| Effect on `HS-F-99-02110` | 3 Cancel rows (2020–2021), 0 matched to Actual/MPS — no effect | Verified from data |
| Effect on `HS-F-99-0213` | 4 Cancel rows (2019–2020), 0 matched to Actual/MPS — no effect | Verified from data |
| Negligibility threshold used | <0.5% of total series qty or value (this report's chosen threshold, stated explicitly) | Configurable assumption |
| Partial-cancellation shortfall rows (`PlanQty > Actual+Backlog`), any prefix | 23,633 rows, shortfall qty 2,889,944.0 — 100% quotation-stage (`QTN-`/`OQ-`/`ENQIN-`/`OPP-`), 0% confirmed contract | Verified from data |
| Partial-cancellation buckets on confirmed (`CTR-`) contracts: cancellation / adjustment / cannot-be-determined | 0 / 0 / 0 — population is empty (0 of 143,936 confirmed-contract rows meet the shortfall condition at all) | Verified from data |
| Recommendation | No change to the demand series' cancellation handling — no leakage found via either checked mechanism | Configurable assumption (backed by the verified-from-data findings above; does not rule out unchecked mechanisms) |
