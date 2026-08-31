# STATUS

## 1. Project Overview

Sales forecasting and inventory planning for PEM Group Omni Channel products sold to Thai
electrical utilities. 445 product codes (visible pricelist sheets only — see Phase 1 note
below for why earlier documents said 448). Data source: SQL Server table
`[salewarehouse].[dbo].[cube_Sale_APD]`.

Phases:
- **1 — Trend**: exploratory sales trend dashboard.
- **2 — Model design**: using Fuse Cutout and Surge Arrester product groups as the pilot.
- **3.1 — Sales forecasting model**.
- **3.2 — External factors**.
- **4 — Inventory Max-Min for MRP**.

## 2. Phase Status

**Phase 1 — Trend: DONE**
- Linked pricelist to database via item code: **corrected to 343 of 445 matched** (visible
  pricelist sheets only). The dashboard itself was built on 344 of 448, which counted the
  hidden Version1 sheets — this conflicts with the later "visible sheets only" locked
  decision. Both counts are internally consistent with their own sheet universe; 445/343 is
  the current standard going forward.
- Daily sales data 2024–2026, total 2,015.3 million THB. **Fully reproduced and explained on
  2026-08-31** (see Phase 2 note below) — this was not a data-quality problem, just an
  under-documented filter combination.
- Demand classified by ADI and CV²: Smooth 50, Erratic 39, Intermittent 172, Lumpy 79, no
  sales 107 (plus 1 edge-case item tagged "NoSale31M" in the raw dashboard data, not
  previously called out) — that makes 74% Intermittent or Lumpy. Confirmed by parsing the
  dashboard's own embedded data on 2026-08-31.
- Dashboard published on GitHub Pages with daily drill-down.

**Environment setup — DONE**
- Folder structure created (`config/`, `reference/`, `src/`, `output/{data,charts,summary}/`).
- All 8 packages from `requirements.txt` installed.
- ODBC Driver 17 for SQL Server present.
- Python 3.12.10.
- Repository audited: no credentials or data files in git history.
- `.env` filled in with `DB_SERVER`, `DB_USER` (2026-08-31); `DB_PASSWORD` filled in by the
  user directly, never through chat.
- **Bug fixed (2026-08-31, user-approved)**: `src/db.py`'s `get_connection()` built a
  SQLAlchemy URL as `mssql+pyodbc://user:pass@server/db?driver=...`, which does not handle the
  backslash in a named SQL Server instance (`192.168.0.4\WebDB`) and caused a false "server not
  found" error. Fixed by building the connection via an ODBC connection string passed through
  `odbc_connect`, which correctly handles the backslash and any special characters.

**Phase 2 — Step 1 DONE (2026-08-31); pilot scope decided (see Locked Decisions)**

Database schema verified against `cube_Sale_APD` (62 columns, 51,059 rows). Confirmed column
mapping, with evidence:
- **Item code** → `itemcode` (varchar). Evidence: values match the pricelist's Product Code
  format exactly (e.g. `EEE-F-FC-1040010002` appears in both). `productID` is a different,
  higher-cardinality internal surrogate key (4,634 distinct vs. 3,778 for `itemcode`) — not
  the item code.
- **Transaction date** → `createDate` (date). Evidence: 0 mismatches out of 51,059 rows
  against the table's own `year`/`month` columns; 100% non-null. Other date candidates
  (`customer_entry`, `forecast_date`, `plan_date`, `PODate`, `newCustomerDate`,
  `warranty_date`) mismatch `year`/`month` on thousands of rows or have far lower coverage, or
  ranges inconsistent with a transaction date (e.g. `newCustomerDate` back to 1956).
  `timeStamp` is an ETL load timestamp (all 51,059 rows stamped within one ~17-minute window
  on 2026-08-30), not a transaction date.
- **Quantity** → `qty` (decimal).
- **Sales amount** → `sale` (decimal). Note: `revenue` is also decimal-sounding but is
  actually a varchar category label (e.g. "1.1 Sale Revenue", "Wholesale") — not an amount
  field, despite the name.
- **Actual vs. MPS** → `status` (varchar), values are exactly `Actual` (48,901 rows) and
  `MPS` (2,158 rows) — an exact match to the terminology already used in this project.
- **Product hierarchy**: `productCateName`, `productTypeName`, `productName` all exist in the
  database with exactly those names, confirming the pricelist's Category/Type/Description
  hierarchy has a direct database counterpart (this was checked directly against the live
  schema, since this exact wording was not found verbatim elsewhere in this file).
- **Business unit / division — resolved 2026-08-31: use `division`.** Evidence: for all three
  pilot codes, `division = PEM101` matches the pricelist's Business Unit exactly, while
  `sale_division = PEM105` does not (and `PEM105`/`PEM108`/`PDE-SMKT`/`PSP-MOKA` values in
  `sale_division` don't correspond to any pricelist sheet at all — it looks like it tracks
  which team gets sales credit, not which business unit owns the product). `cmp` /
  `sale_company` are a coarser company-level rollup (`PEM`, `PDE`, `PSP`, `CI`, ...) — too
  coarse to distinguish PEM101 from PEM102/103/104/107. `division` does carry two legacy
  values not in the current pricelist (`PEM102-OLD`: 2,402 rows, `PEM107-OLD`: 590 rows) —
  unresolved, flagged for later. **Critically, `division` must be part of any matching key
  built on `productCateName`**: the same category name (e.g. "Fuse" — 21,737 rows under
  `PEM101` but also present under `PEMCSA`, `PPS`, `PPD101`, `PCE101`, `PTS`, `PDEMO`, `PSS`,
  `PPD102`; same pattern for "Surge Arrester" and 70 other category names) is reused across
  divisions for what are presumably different, unrelated products. Filtering by
  `productCateName` alone without `division` would pull in unrelated items from other
  business units. Not yet written into any code or config — this is a recorded finding only.

Pricelist re-read using only `sheet_state == visible` sheets (6 product sheets: PEM101-Version
2, PEM102-Version 2, PEM103-Version2, PEM104, PEM107 CT-Version 2, CI101; the visible
"Forecast Ex-Rate" sheet was also skipped — it has no Product Code column). No product code
appears on more than one visible sheet.

**Phase 1 figures re-verified, then fully explained on 2026-08-31.** Product-code counts (448,
344) are confirmed correct once counted across *all* sheets including hidden Version1
duplicates, not the visible-only set (445 codes, 343 matched) — see the corrected Phase 1
note above.

The 2,015.3 million THB figure, previously unreproduced, **is now fully explained**. Cause:
`index.html`'s embedded dataset (`const OMNI = {...}` in the file, ~1MB single line) carries
its own `meta.pull` field stating the data was pulled **2026-08-25**, and the tab's own
subtitle states the filter as `revenue_type = 'Omni Channel'` and `status = Actual + MPS`. The
git history for `index.html` (last commit 2026-08-26T11:04:44+07:00, "Spec-based remark badges
+ line tooltips", one day after the pull) is consistent with this. Recomputing directly from
the embedded JSON (448 items × 32 months, summing `sa`+`sm` = Actual+MPS) reproduces
**2,015.3M exactly**, and independently, live-querying the database today
(`status IN ('Actual','MPS')`, `revenue_type='Omni Channel'`, `itemcode` in the 448-code
all-sheets pricelist universe, `createDate` 2024-01-01 to 2026-08-25) reproduces **2,015.3M
exactly (0.00% difference)** — full 8-combination grid in
`output/summary/task2_snapshot_hypothesis_grid.csv`. Extending the same query through today
(2026-08-31, 6 more days) gives ₿2,029.2M — **higher**, not lower, consistent with a
monotonically growing sales table and no contradiction of the snapshot explanation. The
embedded data's own classification counts (Smooth 50/Erratic 39/Intermittent 172/Lumpy 79/
NoSale 107, +1 "NoSale31M" edge case) also match STATUS.md exactly, confirming the whole
Phase 1 dataset — not just the total — is internally consistent and now fully traced to its
source query. Lesson: the visible-sheets-only convention was adopted *after* Phase 1 was
built, so Phase 1's own figures legitimately used the older 448-code universe; this is not a
data error, just a documentation gap now closed.

Full outputs: `output/summary/step3_fuse_surge_by_type.csv`, `step5_item_level_stats.csv`,
`step5_type_summary.csv`, `step5_top_items_by_type.csv`, `step6_pilot_codes.csv`,
`task2_snapshot_hypothesis_grid.csv`; raw pulls in `output/data/`; monthly quantity charts per
Product Type in `output/charts/`.

**Data quality audit of the 68 pilot items — DONE (2026-08-31).** Scope: Product Type =
High Voltage Distribution Fuse Cutout (10 items) or Medium Voltage Surge Arrester (58 items),
from visible pricelist sheets. Full detail in `output/summary/task2_*.csv`, `task3_*.csv`,
`task4_*.csv`; script: `src/audit_pilot_items.py`.

- **Retroactive correction to prior Step 5 figures**: the previous session's type-level sales
  totals (₿244.4M Fuse Cutout + ₿178.2M Surge Arrester = ₿422.6M combined) were computed
  **without** the `division` filter — confirmed to the cent against this audit's
  all-division total for the same 68 items. Properly scoped to `division = 'PEM101'`, the
  correct combined total is **₿362.0M**, ₿60.6M (14.3%) lower. This is a direct, now-quantified
  consequence of the division/productCateName finding recorded above — filtering by item code
  and type alone, without division, silently pulls in ₿60.6M of unrelated-division sales for
  12 of the 68 codes.
- **Cross-division exposure**: 12 of 68 pilot codes appear under more than one division (full
  list and per-division values in `task2_1_cross_division.csv`).
- **Exact-duplicate check** (same itemcode+createDate+qty+sale+status): 1,505 rows flagged in
  588 groups, but only **44 groups (76 rows, ₿36.6M) are genuine row-level duplicates** (same
  `contractid` repeated within the group). The other 544 groups (1,429 rows) are legitimately
  **different contracts/customers** that coincidentally share item, date, quantity, and price —
  not duplicates. Do not treat the raw 1,505 figure as a data-quality problem without this
  distinction (`task2_2_duplicate_classification.csv`).
- **Negative qty/sale**: none found (0 rows) among the 68 pilot items.
- **Actual/MPS double-counting**: schema IS testable via `contractid`, `quotationid`,
  `ContractPO_NO` (all three agree exactly). Found **3 confirmed cases** (out of 9,058 rows)
  where the same order and the same item appear under both statuses. One case
  (`CTR-2026-02042` / `HS-F-99-0215`) has suspiciously identical Actual and MPS quantities
  (600=600) plus internal exact-duplicate rows — the strongest signal of likely double
  counting. The other two show differing Actual vs. MPS quantities, consistent with (not
  proof of) legitimate partial-shipment tracking (Actual = delivered portion, MPS = pending
  portion of the same order), matching the dashboard's own stated MPS definition. **Not
  resolved** — the schema has no supersede/revision/cancelled flag to distinguish the two
  interpretations. `jobcode` was investigated and rejected as a document identifier for this
  test — it is a coarse "visit" code spanning many unrelated contracts over months, not a
  true order ID (16 false-positive-prone matches vs. 3 for the real order identifiers).
  **Data-integrity note**: `quotationid` stores the literal 4-character string `"None"` (not
  SQL NULL) as a missing-value placeholder for 5,740 of 9,058 pilot rows — confirmed via
  `LEN()`/`ASCII()` against the raw column. Any future query filtering `quotationid IS NOT
  NULL` will not exclude these; must also exclude the literal string `'None'`.
- **Missing key values, out-of-range dates, qty/sale sign mismatches**: none found (0 rows)
  among the 68 pilot items.
- **Cross-channel exposure**: table-wide, 7 distinct `revenue_type` values exist (including 7
  rows with a blank/`None` value, ₿3.1M — minor). Under `division='PEM101'`, the 68 pilot
  items span only 3: Omni Channel (58 items, ₿358.0M), Tendering (1 item, ₿4.0M),
  Total Customer Solution (1 item, ₿5,400). **1 item flagged below 50% Omni share**:
  `HS-F-99-3303` at 43.1% (₿3.06M of ₿7.11M total) — the remaining 57% is a single Tendering
  deal (400 units, ₿4.04M) (`task3_3_omni_share_per_item.csv`, `task3_4_flagged_below_50pct.csv`).
- **Pricelist consistency**: 58 of 68 pilot items exist in the database at all; the other 10
  (all Surge Arrester codes) have zero rows and no sales — full list in the audit output.
  **Product Type name mismatch on all 68 items**, but of two very different kinds: the 10
  Fuse Cutout items differ only in capitalization/pluralization (DB: "High voltage
  distribution Fuse cutouts" vs. pricelist: "High Voltage Distribution Fuse Cutout") — cosmetic.
  The 58 Surge Arrester items differ **substantively**: DB `productTypeName` says **"High
  Voltage Surge Arrester"** (47 items) or "Surge Arrester" (1 mixed item) for items the
  pricelist calls **"Medium Voltage Surge Arrester"** — a voltage-tier disagreement, not a
  formatting quirk. **Not resolved which source is correct** — flagged for decision.
  `productCateName` agrees with the pricelist's Category exactly ("Fuse"/"Surge Arrester") for
  all 58 present items; the only Category mismatches are the 10 items absent from the DB.

**Duplicate-vs-split-lot investigation — DONE (2026-08-31).** Follow-up on the 44-groups /
₿36.6M "genuine duplicate" finding above — the split-lot hypothesis (real instalment
deliveries, not database duplication) had to be tested before treating that value as an
error. Script: `src/investigate_duplicates.py`; outputs: `output/summary/task1_*.csv`,
`task4_44groups_classification.csv`, `task5_*.csv`.

- **Full-column comparison**: the 44 parent groups resolve to 55 exact
  (contractid+itemcode+createDate+status) duplicate sets. **Zero** of the 55 are identical
  across every column — but the only columns that ever differ are `id`/`atid`/`planid`
  (auto-increment row keys, which differ for any two separate rows regardless of cause),
  `timeStamp` (ETL load time, not business time — all rows loaded in one ~17-minute window on
  2026-08-30), and `forecast_date`/`plan_date`. **No PO number, customer, destination
  (district/province), or delivery-date field ever differs** — the schema has no lot number,
  delivery sequence, or line-item number column at all.
- **Contract-level reconciliation**: no contract-quantity, contract-value, or line-total
  column exists in the schema (confirmed by name search, not inferred) — a documented
  "contract total" cannot be checked against. However, **every one of the 54
  (contractid, itemcode) pairs has activity on exactly one calendar date across its entire
  recorded history** — not just the flagged rows, the whole contract+item's life. A genuine
  staggered instalment delivery would be expected to show multiple different dates; none do.
- **Table-wide prevalence**: only 1.02% of all (contractid, itemcode) pairs table-wide
  (494 of 48,411) have any repeated identical (qty, sale) row — rare, not a widespread
  standard practice, spread thin across 213 items and 23 divisions rather than concentrated
  in one place. Rarity argues against "split lots are just how this business operates."
- **Reversal on `forecast_date`**: initially dismissed as noise (consistent with its known
  unreliability elsewhere in the schema), but on inspection several sets show a *regular,
  plausible* multi-week-to-monthly progression across the duplicate rows (e.g. one set's 4
  rows step exactly 30 days apart) — indistinguishable from a genuine multi-tranche delivery
  schedule. Applying a disclosed threshold (`forecast_date` spread ≥ 25 days, or a
  non-bookkeeping business column differing, e.g. `jobcode`/`manufacturing_type`) as the line
  between "no real signal" and "plausible schedule signal": **29 of 55 sets classified
  Confirmed duplicate (₿217,167), 26 of 55 classified Undetermined (₿36,389,599) — 99.4% of
  the flagged value is NOT confirmed as duplication.** Zero sets qualify as Confirmed split
  lot — the schema has no field that can positively prove instalment delivery, only fail to
  rule it out. Full per-set evidence in `task4_44groups_classification.csv`.
- **Undetermined-bucket resolution**: needs a lot/delivery-sequence/GRN number, an
  invoice/delivery-note reference, or business-side confirmation of whether these contracts
  are known recurring-delivery orders, to settle definitively.
- **The 3 Actual/MPS overlap cases re-examined**: all 3 show `forecast_date` increasing
  monotonically and by plausible business intervals across the Actual-then-MPS rows (e.g.
  2026-05-25 → 07-25 → 09-25 → 11-25 → 2027-01-25, a clean 2-month cadence for one case) —
  consistent with earlier tranches already delivered (Actual) and later tranches still
  pending (MPS) on one multi-tranche order, not with simple double counting. Still cannot be
  fully confirmed — the schema has no supersede/cancelled flag to rule out a stale, un-removed
  MPS row sitting alongside its later Actual fulfillment.
- **Practical implication — data quality must be resolved before modelling begins.** Neither
  the duplicate-vs-split-lot question nor the Actual/MPS overlap question, nor the Surge
  Arrester voltage-tier disagreement, is resolved. No cleaning rule has been applied. Any
  forecasting or backtest work started before these are settled with the data team risks
  building on top of an unknown mixture of real sales and duplicated rows.

**Deep investigation of the 29 remaining "confirmed duplicate" sets — DONE (2026-08-31).**
Business confirmed `forecast_date` is the contractual delivery date, resolving 26 of the
original 55 sets as genuine split lots. This investigation covers the remaining 29 sets
(₿217,167) where contractid+itemcode+createDate+forecast_date+qty+sale+status are ALL
identical. Outputs: `output/summary/task1_*.csv` through `task7_final_revised_classification.csv`.

- **Table-wide prevalence**: 178 sets exist table-wide with this exact 5-column match
  (226 extra rows, ₿31.46M, 0.79% of 51,059 contract lines), spread across 14 divisions, 3
  revenue types, 15+ product categories, and nearly the full 2021–2026 history with no
  single-month spike — broad and continuous, arguing against one bad batch load, though 0.79%
  is still too rare to call it obviously "standard practice."
- **Insertion fingerprint — inconclusive, reported honestly**: median id-gap and timeStamp
  spread are IDENTICAL between the 29 sets and the 26 business-confirmed split-lot sets
  (median gap 6, median spread ~0.006–0.007s, both groups). The confirmed-real split-lot group
  actually has larger outlier gaps (up to 9,722) than the 29 sets (up to 1,768). Adjacent
  insertion order does not reliably separate genuine splits from suspected duplicates.
- **Contract context**: on 17 of 19 contracts, a specific subset of 2–4 different items (not
  the whole PO, not just the one flagged item) share the same repeat multiplicity together —
  e.g. a fuse cutout + fuse link + accessory + service line all tripled together on one
  contract while 3 unrelated items on the same contract appear once each.
- **Normal-contract comparison (decisive)**: 91% of the 29-set rows carry a
  comma-concatenated multi-job `jobcode` vs. only 11% in a sample of normal (one-row-per-item)
  contracts; `ansoff_matrix` is missing in 76% of the 29-set rows vs. 27% normally. Both point
  to these rows coming through a different data pathway than typical entries — consistent
  with a database JOIN fanning out against a jobs/activity table.
- **Other tables (major finding)**: `cube_Contract` (108 tables total in the database) has
  `contractid`, `plan_qty`/`actual_qty`, and a genuine `actual_del_date` field that
  `cube_Sale_APD` lacks. Joining on contract + product text: **5 of the 29 sets are
  independently corroborated as genuine split lots** — `cube_Contract` shows 2 distinct real
  delivery dates (e.g. 2025-11-21 and 2025-11-29) for pairs my own `forecast_date`-spread
  threshold (≥25 days) had wrongly classified as duplicates. **This overturns part of the
  prior session's classification** — the threshold was too strict. 21 of 29 have no match at
  all: `cube_Contract` only covers `ctr_date ≥ 2025-01-01` (zero 2024 contracts exist there) —
  a genuine coverage gap, not evidence either way. 3 remain inconclusive even with a
  `cube_Contract` match (it also shows only one repeated date for these).
- **Revised final classification of the 29 sets**: **5 sets (₿24,909) — Confirmed split lot**,
  high confidence, independently corroborated. **3 sets (₿14,898) — Undetermined**, no
  resolving evidence found. **21 sets (₿177,360) — Likely duplicate, moderate confidence, NOT
  independently verified** (same-day-only pattern, no distinguishing field, 91% abnormal
  jobcode concatenation, rare table-wide — but no 2024-era corroborating table exists to
  confirm further). Full detail in `task7_final_revised_classification.csv`.
- **What would settle the remaining 24 sets**: a lot/delivery-sequence/GRN number, extending
  `cube_Contract`-equivalent coverage back to 2024, or direct confirmation from the data team
  on whether any 2024-era process is known to have produced duplicate contract-line
  submissions.

**Full database inventory and re-investigation — DONE (2026-08-31).** User explicitly noted
that reasoning-based conclusions in this project have repeatedly been wrong and corrected
only by new data (rows called duplicates turned out to be split lots; sets called duplicates
were overturned by `cube_Contract`). This pass systematically inventoried all 108 tables
instead of only the ones that sounded relevant, and it **overturns several conclusions from
the previous session** — flagged explicitly below rather than silently replaced. Outputs:
`output/summary/task1_full_database_inventory.csv`, `task1_joinable_tables.csv`,
`task4_CES_reconciliation.csv`, `task5_control_test_26_splitlots.csv`,
`task6_actual_mps_cube_CES_resolution.csv`, `task7_consolidated_status.csv`. Script:
`src/inventory_database.py`.

- **Full inventory**: all 108 tables checked (not a relevance-sounding subset) for
  contractid, itemcode, delivery-date, lot-number, GRN, invoice, jobcode and PO-number-like
  columns, row counts, and date ranges. 22 tables carry a contractid-like column, 49 an
  itemcode-like column, 17 a delivery-date-like column, 2 a lot-number column, 0 a
  GRN-named column, 10 an invoice column, 26 a jobcode column, 10 a PO-number column. Full
  detail per table in `task1_full_database_inventory.csv`.
- **CORRECTION — 2024 contract data exists.** The prior session concluded `cube_Contract`'s
  2025-01-01 floor meant 2024 contract detail could not be verified anywhere. **This is
  wrong.** `Cube_CES` (166,432 rows, `CtrDate` 2012-01-03 to 2029-08-05) carries `ContractID`
  **and** `ItemCode` directly (which `cube_Contract` lacks — it only had a free-text
  `product` field), `ForecastDelDate`/`PlanDelDate`/`ActualDelDate`, and `PlanQty`/
  `ActualQty`/`BacklogQty`. It covers 2024 fully. The prior "no 2024 data exists" conclusion
  should be treated as superseded.
- **CORRECTION — the earlier cube_Contract join undercounted matches.** Re-joining all 29
  "confirmed duplicate" sets on the proper key (`ContractID` + `ItemCode` in `Cube_CES`,
  instead of free-text product matching against `cube_Contract`) gets a **100% match rate**
  (29 of 29), versus 8 of 29 with the old text-based join. Revised breakdown of the 29 sets:
  **9 fully corroborated as genuine split lots** (every repeated row has its own distinct
  `ActualDelDate` — value ₿54,654, up from 5 sets/less coverage previously reported),
  **4 partially corroborated** (some but not all dates distinct — ₿39,000), **16 with no
  distinguishing evidence found anywhere** (₿123,513, down from the previously reported 21/
  ₿177,360 — the correction reduces both the count and value of the unresolved bucket).
- **Cube_CES itself sometimes duplicates.** For one of the 4 "partially corroborated" sets
  (`CTR-2024-06867`/`EEE-F-FC-1040011000`), `Cube_CES` shows 2 rows with IDENTICAL
  `ActualDelDate=2024-12-04` (adjacent `id`s) plus 1 row with a different, genuine
  `ActualDelDate=2024-12-10`. This means whatever produces the duplication is not confined to
  `cube_Sale_APD`'s own construction — it appears to originate upstream, in a source shared by
  at least two independently-populated tables.
- **Control test (Task 5) — the Cube_CES method is imperfect, reported honestly.** Applying
  the identical method to the 26 sets already business-confirmed as genuine split lots: 23 of
  26 (88.5%) are correctly identified as fully distinct in `Cube_CES`; **3 of 26 known-genuine
  split lots are NOT fully distinct in `Cube_CES`** (including the same contract,
  `CTR-2026-02042`, seen again in the Actual/MPS re-examination below). **This means the
  method has an ~11.5% false-negative rate on cases already known to be real** — so the 16
  "no distinguishing evidence" sets above cannot be confidently called duplicates; some
  unknown fraction of them are very likely genuine split lots the method simply cannot see.
  Confidence in labelling those 16 "duplicate" is downgraded from the prior session's
  "moderate, not independently verified" to **low-to-medium, genuinely unresolved**.
- **jobcode — evidence gathered, mechanism still not understood.** Multi-value
  (comma-concatenated) jobcode is a real, quantified, concentrated phenomenon: 1,502 of
  27,029 non-blank jobcodes table-wide (5.6%) are multi-value, **zero before 2024** (0 in
  2021–2023, 672 in 2024, 665 in 2025, 165 in 2026-to-date), and 81% concentrated in
  `division = PEM101` (the pilot division). The individual codes inside the concatenation
  (e.g. `VT240135`, `CT240217`) are real and found in `Cube_CES.OLMJobCode` and
  `cube_final.jobno`. The `jobcode` column allows up to 70 characters but the longest
  observed multi-value string is exactly 30 — a truncation ceiling well below the column
  limit, consistent with an upstream aggregation (e.g. `STRING_AGG`) with its own length cap.
  **However, checking `Cube_CES.OLMJobCode` for the exact rows behind one duplicate set shows
  the SAME complete 4-job list repeated identically across all 3 rows — not one distinct job
  per row, and 4 jobs does not equal 3 rows.** This is evidence AGAINST a clean "one row per
  matching job" JOIN-fanout explanation, contradicting the prior session's leading hypothesis.
  **Honest conclusion: the data supports a strong statistical association between multi-value
  jobcode and row duplication (91% vs. 11%), and rules out one specific mechanical
  explanation (per-job fanout), but does not establish what actually produces either the
  duplication or the concatenation.** What would settle it: visibility into the stored
  procedure or view definition that populates `jobcode`, which is outside what a read-only
  data investigation can determine.
- **CORRECTION — the 3 Actual/MPS overlap cases are now definitively resolved, not just
  "leaning legitimate."** `Cube_CES` has its own explicit `Status` column with values
  `Actual` and **`Backlog`** (its own name for what `cube_Sale_APD` calls `MPS`), plus
  separate `ActualQty` and `BacklogQty` columns. For all 3 cases: `Actual` rows carry a real
  `ActualQty` and a real `ActualDelDate`; `Backlog` rows carry `ActualQty=0`,
  `BacklogQty` = the pending amount, and `ActualDelDate=None` (not yet delivered). Actual+
  Backlog sums match `cube_Sale_APD`'s Actual+MPS sums exactly for all 3 (e.g.
  1,200+1,920=3,120 for `CTR-2026-02042`). **This is ground-truth confirmation from an
  independent table's own dedicated status-tracking fields, not inference from
  `forecast_date` patterns. The prior "cannot rule out a stale un-superseded MPS row" caveat
  no longer applies — these are confirmed legitimate multi-tranche orders, not double
  counting.**
- **Consolidated status table** (all open data-quality questions, confidence levels, evidence,
  and what would raise confidence further) in `task7_consolidated_status.csv`.

**Data quality closed out for the pilot scope — DONE (2026-08-31).** Decisions made and
recorded (not further investigation):

- **Actual/MPS overlaps: RESOLVED, decision recorded.** The 3 cases are legitimate
  multi-tranche deliveries, not double counting (see `Cube_CES` evidence above). **MPS means
  "PO Received" — confirmed demand, not tentative** — therefore **MPS rows must never be
  dropped or filtered out at any stage of this project**, including in `src/load_data.py` and
  any future modelling code.
- **The 16 remaining unresolved duplicate-vs-split-lot sets (₿123,513) are KEPT IN FULL — no
  rows removed.** Reason: the control test showed the verification method has an ~11.5%
  false-negative rate on cases already known to be genuine split lots, so a method that misses
  real split lots cannot be trusted to declare these duplicates. The value is 0.03% of the
  pilot total (₿123,513 of ₿362.0M) — under-counting real demand is more damaging than
  over-counting for inventory purposes, so the asymmetric risk favors keeping every row.
- **The 10 pilot items with zero database rows are EXCLUDED from forecasting** — there is no
  history to forecast from. Their codes are recorded for Phase 4 inventory planning (see
  `output/summary/excluded_items_no_history.csv`, written by `src/load_data.py`). **The pilot
  forecasting scope is therefore 58 items**, live-reverified against the database on
  2026-08-31 (58 present, 10 absent — unchanged from the audit).
- **Cross-division exposure: keep filtering on `division = 'PEM101'`.** ₿60.6 million of sales
  for these same 68 item codes sits under other divisions and is excluded from this project's
  forecasting scope — recorded here to be revisited in Phase 4, since inventory is shared
  across divisions regardless of which division's sales record it.
- **`quotationid` values equal to the literal string `"None"` are treated as NULL when read.**
  Applies wherever `quotationid` is read in code going forward (not just this task) — see the
  earlier data-integrity note on why this matters.
- **Recorded as unresolved but non-blocking open questions**: (1) what system `Cube_CES`
  belongs to / how it relates to `cube_Contract` and `cube_Sale_APD` — unprovable from a
  read-only data investigation; (2) why multi-value `jobcode` entries begin exactly in 2024
  and concentrate in `division = PEM101` — evidence gathered (see above) but the mechanism is
  unprovable without the view/procedure definition. Neither blocks modelling.
- **GATE LIFTED (2026-08-31): data quality is closed for the pilot scope.** All three items
  that previously blocked modelling are now resolved by decision or evidence: Actual/MPS
  overlaps resolved and MPS-retention decided; the 16 remaining duplicate-vs-split-lot sets
  are kept in full by decision rather than requiring further proof; the 10-item exclusion and
  58-item scope are settled. The Surge Arrester voltage-tier disagreement remains open but is
  side-stepped for modelling by filtering on `itemcode` rather than `productTypeName` (see
  `src/load_data.py`). Modelling and backtest work may now proceed.

**Phase 3.1 — Sales forecasting model: first backtest DONE (2026-08-31); no model chosen.**
Data loading: `src/load_data.py`. Models: `src/models.py`. Backtest: `src/backtest.py`.
Outputs: `output/data/raw_pilot_sales_58items.csv` (raw, untouched),
`output/data/processed_pilot_sales_monthly.csv` (monthly aggregate, reconciled exactly to
the daily source), `output/summary/backtest_*.csv`, `output/charts/forecast_vs_actual_*.png`.

- **Data pull**: 58 items, `division='PEM101'`, `revenue_type='Omni Channel'`,
  `status IN ('Actual','MPS')`, `createDate >= 2024-01-01`. Filtered by `itemcode` (not
  `productTypeName`), per the locked decision above. 9,019 raw rows, 158 of them MPS — kept,
  none dropped. Validation passed: 0 negative qty/sale, 0 out-of-range dates, monthly
  aggregation reconciles exactly to the daily source (qty=182,005.00, sale=₿357,976,933.17,
  matching the earlier audit's Omni Channel total for these items exactly). August 2026
  excluded from backtesting — its max date in the data (2026-08-28) is before that month's
  last day, so it is an incomplete month, determined from the data, not assumed. 31 complete
  months used (2024-01 to 2026-07).
- **Backtest**: 6-month holdout (train on the first 25 months, forecast/compare the last 6).
  Models: Naive, Moving Average (3/6/12), Croston, SBA (`statsforecast`). All 58 items
  backtested successfully, 0 dropped. Demand classification (ADI/CV², Syntetos-Boylan
  thresholds) over each item's full 31-month series: Lumpy 23, Intermittent 18, Erratic 10,
  Smooth 7 (sums to 58).
- **Win counts (lowest MAE per item)**: Naive 35, MA3 6, MA12 6, Croston 5, SBA 3, MA6 3.
  **Naive wins outright on more items than every other model combined** — worth flagging
  plainly rather than glossing over, since it was adopted as the baseline, not expected to
  dominate.
  Beats-Naive rate: Croston/MA3/MA6/SBA each beat Naive on 19 of 58 items (32.8%), MA12 on 18
  (31.0%) — **no model beats Naive on a majority of items**.
- **By demand classification** (mean MAE, lower is better; full detail in
  `backtest_summary_by_classification.csv`): Erratic — MA6 lowest (280.95) vs. Naive worst
  (367.80); Intermittent — MA3 lowest (2.55) and Naive close behind (2.77), Croston/SBA far
  worse (26–28, more than 10x worse) on this classification; Lumpy — Naive lowest (54.49),
  all other models worse; Smooth — MA6 lowest (106.17) vs. Naive worst (192.74). **Croston and
  SBA, the models specifically designed for intermittent demand, perform worst of all six on
  the Intermittent class in this backtest** — a result worth double-checking rather than
  accepting at face value, since it runs against the models' own design intent; not
  investigated further in this pass.
- **The 3 pilot codes' results** (`backtest_pilot_codes_detail.csv`,
  `output/charts/forecast_vs_actual_*.png`): `EEE-F-FC-1040010002` (Erratic) — MA6 lowest MAE
  (1,821), Naive worst (2,344); `HS-F-99-02110` (Lumpy) — Naive lowest MAE (569); `HS-F-99-0213`
  (Lumpy) — MA3/MA6/MA12/Croston/SBA tie exactly on MAE (272.5, all forecasting a similar
  constant level), Naive worst (303).
- **No model was selected. No model choice was written to config.yaml**, per instructions —
  this is a first backtest result for review, not a recommendation.

**Investigation of backtest anomalies (spikes, jobcode join, Croston/SBA, Bias) — DONE
(2026-08-31).** Scripts: `src/investigate_spikes.py` (Tasks 3–4); ad hoc queries for Tasks
1–2, 5–6. Outputs: `output/summary/task1_hs0213_spike_rows.csv`,
`task2_cube_final_jobno_match.csv`, `task3_spike_*.csv`,
`task4_classification_with_without_spikes.csv`, `task5_croston_diagnostic.csv`,
`task6_bias_per_model_*.csv`.

- **HS-F-99-0213's two spikes (June/July 2026, 651/896 units) are fully explained — high
  confidence.** June = 5 separate orders summing exactly to 651; July = 8 separate orders
  summing exactly to 896 (verified to the unit). 12 distinct customers across 13 rows; no
  single order exceeds 46% of its month. `jobcode` is literally the string `"None"` for all
  13 rows — unrelated to the earlier duplication investigation. `ctr_name` holds genuine
  order descriptions (e.g. "ล่อฟ้า 21/5 (งาน กฟจ.น่าน)" = "Surge Arrester 21/5, PEA Nan
  provincial branch") — routine equipment orders to many different Thai provincial
  electricity-utility branches, not one project or tender.
- **CORRECTION — the jobcode mechanism from the prior session's inventory pass is now
  understood, high confidence.** `cube_final.jobno` and `Cube_CES.OLMJobCode` both give EXACT
  single-code matches (not just substring) to the individual codes inside
  `cube_Sale_APD.jobcode`'s comma-separated lists. Each individual code (e.g. `VT240135`) is
  tied to one specific itemcode in 99.5% of cases (17,875 of 17,971 distinct `jobno` values in
  `cube_final` map to exactly one itemcode) and is **reused across dozens of unrelated
  contracts, customers and dates** — this is a **manufacturing/production-batch reference**,
  not a per-sale job identifier. The comma-concatenated list in `cube_Sale_APD.jobcode`
  appears to aggregate one batch-code per distinct item on a contract (explaining why the
  identical full list repeated across a contract's rows in the earlier investigation — it
  wasn't "one job per row," it was "all of this contract's item-batches, listed once per
  row"). This does not by itself explain the earlier row-duplication finding — it explains
  what the codes mean, not why some rows repeat. Match rate: of 12,952 distinct individual
  job/batch-code tokens found in `cube_Sale_APD.jobcode`, 11,350 (87.6%) match exactly in
  `Cube_CES.OLMJobCode`, 5,187 (40.0%) in `cube_final.jobno`. `cube_final` and `Cube_CES` both
  also carry genuine job/project names and customer names (`JobName`/`CustomerName` in
  `Cube_CES`; `project`/`customer_name`/`descriptions` in `cube_final`) — reportable verbatim,
  not investigated exhaustively here.
- **Spikes are a general pattern, not isolated to HS-F-99-0213 — high confidence.** Threshold
  used (stated explicitly): a month is a spike if its qty exceeds 3x that item's own median
  non-zero monthly qty. Found **62 spike months across 26 of 58 items (44.8%)**. Spike months
  hold **₿55.4M of ₿333.0M total (16.6%) in just 3.4% of item-months** — a disproportionate
  concentration, the classic signature of lumpy demand. Order composition is mixed: most
  spikes are broad-based (many orders, many customers — e.g. one spike had 55 orders from 22
  customers), but a few are single-order-driven (several spikes are >90% one order). One
  customer (`CS02411`) recurs across 16 of the 62 spike months with 96 orders — a clearly
  identifiable regular large buyer; several others recur across 5-7 spike months each.
- **Spikes measurably drive forecasting difficulty for a meaningful minority of items —
  high confidence in the direction, exact magnitude is scenario-dependent.** Recomputing
  ADI/CV² with spike months excluded (comparison only — no data was modified) changes the
  demand classification for **18 of 58 items (31%)**. All but one move toward a calmer class
  (Lumpy→Intermittent: 11 items; Erratic→Smooth: 6 items; one exception, Erratic→Lumpy, moved
  the other direction). For these 18 items, mean CV² drops from 1.34 to 0.35 (a ~74%
  reduction) once spikes are excluded. This indicates that for roughly a third of the pilot
  scope, difficult-looking demand behaviour is substantially attributable to occasional large
  or broad-based order months rather than to persistently erratic underlying demand.
- **The Croston/SBA underperformance on Intermittent items is genuine model behaviour
  interacting with a real evaluation limitation, not a coding bug — high confidence.**
  Directly verified: the input series correctly includes explicit zero-demand months (not
  skipped — confirmed by inspecting the actual arrays passed to each model); the model output
  is read correctly as the documented constant per-period demand rate (`result['mean']`,
  matching `statsforecast`'s own documentation, verified against the library directly).
  Systematic check across all 18 Intermittent items: **87% of test months are exactly zero on
  average**; 16 of 18 items have Naive forecasting exactly 0 (matching the recent zero-run
  perfectly by construction), while 16 of 18 have Croston forecasting a positive constant
  (ranging from 0.04 up to 470.8, driven by one large historical demand event persisting in
  Croston's slow-adapting smoothed estimate — the class docs state its smoothing parameter is
  fixed at 0.1). **Conclusion: this is a real interaction between (a) Croston/SBA's known
  slow adaptation to items that have gone recently dormant, and (b) a well-documented
  limitation of period-by-period MAE for comparing a constant-rate forecast against
  zero-heavy sparse actuals — not a misapplication or scoring error.** Not fixed in this
  pass, per instructions.
- **Bias reported for the first time.** Overall (all 58 items, all models are net
  under-forecasting): Naive least negative (-45.7), MA12 most negative (-71.0). By
  classification: Erratic — all models strongly under-forecast (-218 to -277); **Intermittent
  — Naive/MA are near-zero (-1.5 to +1.0), but Croston/SBA over-forecast substantially (+25.5,
  +27.0)**, consistent with the dormancy finding above; Lumpy — all models under-forecast
  similarly (-41 to -45); Smooth — Naive over-forecasts (+74.8), MA12/Croston/SBA
  increasingly under-forecast (-54 to -86). **For Phase 4 inventory planning, this means**:
  Croston/SBA on Intermittent items would systematically build excess stock; any model on
  Erratic/Lumpy items would systematically under-provision, likely because none of these
  simple models anticipate the large/broad spike months identified above; Naive on Smooth
  items would over-provision.
- **What the data could not resolve**: whether spikes follow a predictable seasonal calendar
  pattern (not tested — would need a longer history than 31 months to distinguish "seasonal"
  from "coincidental clustering"); the exact mechanism behind the still-unresolved
  row-duplication question from the prior session (the jobcode finding here explains the
  codes' meaning but not the duplication itself); whether `HS-F-99-03010`'s outsized Croston
  estimate (470.8) traces to a specific real large order or to the 16-sets duplicate-vs-split
  question — not cross-checked in this pass.

**Customer profiling, calendar patterns, rolling-origin/train-val-test validation, and
forward-test infrastructure — DONE (2026-08-31).** Scripts: `src/investigate_customers.py`
(Part A), `src/rolling_origin.py` (Part C), `src/train_val_test.py` (Part D),
`src/forward_test.py` + `src/score_forward_test.py` (Part E). Outputs:
`output/summary/partA_*.csv` through `partD_*.csv`, `forward_test_log.csv`.

- **Part A — CS02411 identified, high confidence.** Join key `customerid` against
  `ref_customer` (100% match rate: all 772 distinct customers in the pilot scope's sales
  matched). Note `ref_customer` is a customer×business-unit interaction table, not one row
  per customer (62 rows for this one customerid) — identifying fields (name, taxid, country,
  class) are stable across all rows, segment/business_group vary by context. **CS02411 is a
  company based in Rayong province, class "4. Client", segment predominantly "M&E
  Contractor/Main Contractor" (also tagged "Local Industry" and "Smart Shop" in some division
  contexts) — a contractor, not a utility, not a pure dealer. (Company name redacted before
  publishing — see `output/summary/partA_top10_customer_identity.csv`, gitignored, for the
  full name if needed locally.)**
  ₿68.3M / 6.7% of pilot-scope sales value, 113 distinct items, 1,730 orders. **Orders in
  every single one of 32 months (2024-01 to 2026-08)**, 37–81 orders/month — continuously
  active, not cyclical or project-based. It appears in "spike" months simply because of its
  constant high-volume, broad-portfolio activity, not deliberate large periodic orders.
  Checked 2 more of the top 10 buyers (CS06091, CS03198) — **both also active in all 32 of 32
  months**, same pattern. Top 10 customers = 31.9% of total pilot value; **none of the top 10
  are utilities directly — all are classified Contractor or Dealer**, spread across many
  different Thai provinces (Rayong, Nonthaburi, Surat Thani, Samut Prakan, Bangkok, Chonburi,
  Maha Sarakham, Ubon Ratchathani, Nakhon Pathom) — consistent with the Task 1 finding that
  end-use sites are utility branches but direct customers are intermediary
  contractors/dealers.
- **Part B — calendar observations, low confidence, explicitly not seasonality.** December is
  the lowest or near-lowest month in both fully-observed years (2024: ₿7.0M, 2025: ₿6.2M).
  April–July is elevated in 2024 and 2026 but only moderate in 2025. 2026 (partial year) runs
  substantially higher overall than 2024/2025, especially April–July (up to ₿22.5M vs.
  ₿9.9–14.0M in prior years) — could reflect real growth, or could reflect the still-unresolved
  duplicate-vs-split-lot and spike questions; not disentangled here. Spike months cluster
  somewhat in March (10 of 62), June–July (17 of 62) and are rare in December (2) and August
  (1), roughly tracking the same pattern. **Stated explicitly per instructions: 31 months of
  history covers at most two full annual cycles (2026 is partial) — this is nowhere near
  enough to confirm seasonality. These are observations to guide what external data to look
  for (e.g. Thai utility fiscal-year/budget cycles, rainy-season equipment demand), not a
  validated seasonal pattern. No seasonal model was fit or applied.**
- **Part C — rolling-origin validation exposes real instability, high confidence.** 7 origins
  used (train sizes 13/15/17/19/21/23/25 months, stepped every 2 months; minimum 13 so MA12
  has more than just its own window; last origin matches the original single-holdout split).
  **Only 15 of 58 items (26%) have a stable winning model across all 7 origins — 43 of 58
  (74%) have a winner that changes depending on which window is evaluated**, including 2
  items with 6 distinct winners across 7 origins (no consistency at all). Aggregate win count
  (Naive 241, SBA 47, Croston 37, MA6 30, MA12 26, MA3 25) is dominated by Naive as before,
  but **for the 74% of items with an unstable winner, reporting "the most frequent winner" as
  if it were meaningful would misrepresent the evidence** — flagged explicitly per
  instructions, not glossed over.
- **Part D — validation-to-test gap quantified, high confidence.** Split: train=19 months,
  validation=6 months, test=6 months (19+6+6=31). Model selected per item on validation only
  (lowest MAE), then measured once on test (never touched before). **Mean validation MAE =
  37.54; mean test MAE = 85.23 — a gap of +47.69, meaning the single-holdout-style result was
  roughly 127% more optimistic than genuine unseen-data performance.** Selecting by MAE alone
  vs. by lowest |Bias| **disagree for 31 of 58 items (53%, a majority)**. Example:
  `EEE-F-FC-1040011000` — MAE-best is MA12 (Bias -56.1, moderate systematic under-forecast),
  but MA6 has nearly zero bias (-7.2) despite a higher MAE; picking by MAE alone would select
  the model more likely to cause under-stock. For Phase 4 inventory planning, where a
  persistent directional error compounds into permanent overstock or stockout, this
  disagreement rate means MAE-only model selection is a materially incomplete criterion for
  over half the pilot items.
- **Part E — forward-test infrastructure built, first forecasts logged.** File:
  `output/summary/forward_test_log.csv` (2,088 rows: 58 items × 6 models × 6-month horizon,
  target months 2026-08 through 2027-01, fit on the 31 complete months through 2026-07).
  Columns: itemcode, forecast_run_date, data_cutoff_date, model, config_version (md5 hash of
  config.yaml, since no version field was added to the file), horizon, target_month,
  forecast_qty, actual_qty (empty — never fabricated). Scoring script
  `src/score_forward_test.py` tested and confirmed working correctly: run immediately after
  generation, it correctly reports 0 of 6 target months complete and scoreable, and produces
  no fabricated numbers. Documented in the script's own header: forward testing is the only
  evaluation method in this project immune to hindsight, since rolling-origin and train/val/
  test all reuse history that existed before the model was chosen, while forward-test target
  periods did not exist at forecast time. **Re-run `score_forward_test.py` periodically as
  target months complete.**
- **What the data could not resolve**: whether the 2026 sales-level increase (Part B) is real
  growth or an artifact of the still-open duplicate-vs-split-lot question; whether calendar
  patterns are genuinely seasonal (explicitly out of scope with 31 months); the underlying
  cause of instability for the 43 items with no stable rolling-origin winner (only that it
  exists, not why any specific item is unstable) — not investigated further.

**History depth, older-data trustworthiness, granularity, and the 2026 growth question —
DONE (2026-08-31).** Scripts: `src/investigate_history_depth.py` (Part 1),
`src/investigate_data_quality_by_year.py` (Part 2), `src/investigate_granularity.py`
(Part 3); ad hoc queries for Part 4. Outputs: `output/summary/part1_*.csv` through
`part4_*.csv`.

- **Part 1 — none of the 58 pilot items have any row in `cube_Sale_APD` before 2024 (high
  confidence, directly queried).** `cube_Sale_APD` whole-table history runs 2021-01-11 to
  2026-12-08, but 2021-2023 total just 213/286/264 rows/year with **0 distinct customers**
  each year (customerid 100% null), vs. 17,824+ rows/year from 2024 on. **`Cube_CES` is a
  materially deeper source for the same items** — 61 of 68 pilot codes have real `Cube_CES`
  history before 2024, several back to 2013-2017 (`HS-F-99-0211` to 2013-09-03,
  `EEE-F-FC-1040011000` to 2016-07-22); only 1 of 68 codes (`HS-F-99-1241H03`) has zero rows
  there. `Cube_CES` uses its own field names (`ManuDivision`, `RevenueType`) but the
  equivalent values `'PEM101'` and `'Omni Channel'` do exist there, with real volume from
  2017-2018 onward (948 PEM101 rows in 2017, 5,668 in 2018, growing steadily). **This is a
  genuine untapped historical extension for future consideration — not acted on, per
  instructions not to change the analysis period.**
- **Part 2 — the 2024 boundary is proven, not assumed, high confidence.** `division='PEM101'`
  and `revenue_type='Omni Channel'` **do not exist as values at all in 2021, 2022, or 2023**
  in `cube_Sale_APD` (2021-2023 divisions are exclusively `PSP101-105`; revenue types are only
  "Total Customer Solution"/"Tendering"/"Recurring Revenue Development" — "Omni Channel" first
  appears in 2024 with 16,420 rows). This means the current filters cannot select 2021-2023
  data at all — not "unreliable," structurally absent. Independently confirmed by column
  completeness: `customerid` and `productCateName` are 100% null in 2021-2023, ~98.7%+
  populated from 2024. A sharp discontinuity: December 2023 = 15 rows/6 items → January 2024 =
  1,533 rows/400 items/206 customers, a >100x jump with no ramp-up. Pre-2024 rows average
  ₿17-80M each vs. ~₿300K in 2024+ — consistent with aggregated/summary entries, not
  individual transactions, though this was not further tested. No item-code renaming found:
  2021-2023 `productTypeName` values (Circuit Switchers, Substation Automation, Solar PV,
  etc.) contain zero Fuse/Arrester-related products — this product line is not merely
  absent from PEM101 before 2024, it did not exist under any code in this table.
  **Conclusion: data is safe to use with the current filters from 2024-01-01 onward — this is
  proven with four independent lines of evidence (value absence, completeness, the row-count
  break, and product-line absence), not an assumption.** 2021/2022 numbers reported above as
  observed, with no cause attributed, per instructions.
- **Part 3 — granularity trade-off quantified, high confidence in the numbers, judgment call
  on the recommendation.** Because Part 2 established usable history starts 2024-01-01 and
  the 58 items have no earlier rows anyway, the "2024 onward" and "full usable history"
  scenarios asked for are identical here — both are the same 31 months.
  | Granularity | Periods | Mean %% zero | Items moved calmer vs. monthly |
  |---|---|---|---|
  | Monthly | 31 | 56.1% | — (baseline) |
  | 2-month | 15 | 44.3% | 10 |
  | Quarterly | 10 | 37.9% | 17 |
  | 6-month | 5 | 25.5% | 27 |
  6-month buckets cut zero-inflation the most but leave only 5 points/item — too few to fit
  and validate anything (no room for a holdout, let alone train/val/test or rolling-origin).
  Quarterly (10 points) is also thin. **2-month granularity is the better-evidenced trade-off
  point**: a meaningful reduction in zero-inflation and 10 items moved to a calmer class,
  while retaining enough periods (15) for a reduced but workable holdout scheme. Not
  implemented, per instructions.
- **Part 4 — the 2026 "growth" is not a duplicate-row artifact, high confidence; the more
  accurate framing is a 2025 dip followed by recovery, not unprecedented growth.**
  Comparing the same Jan-Jul window across years (the only fair comparison, since only 7
  months of 2026 exist): 2024 = ₿252.2M, **2025 = ₿187.4M (a dip)**, 2026 = ₿248.9M —
  **2026 is close to 2024's level, not dramatically above all prior history.** The 2025→2026
  rise is driven by more orders (+12%), larger average orders (+18.6% avg order value), and
  higher average unit prices (+11.5%) — but from *fewer* distinct customers (349 vs. 358) and
  *fewer* distinct items (192 vs. 206): existing customers buying more and bigger, not
  portfolio or customer-base expansion. Top single item `EEE-F-FC-1040010002` alone accounts
  for ₿28.6M of the ₿61.5M total 2025→2026 Jan-Jul delta (46.5%). **Overlap with the 55
  duplicate-vs-split-lot flagged rows: only 18 rows, ₿4.86M, 1.95% of the 2026 Jan-Jul
  total.** Recomputing Jan-Jul totals with all 55 flagged rows excluded entirely (comparison
  only, no data modified): 2024 ₿252.2M→₿252.2M, 2025 ₿187.4M→₿185.9M, 2026
  ₿248.9M→₿244.1M — **the pattern survives essentially unchanged. The 2026 level is not an
  artifact of the flagged rows.**
- **What the data could not resolve**: why 2025 specifically dipped (no cause investigated);
  whether `Cube_CES`'s pre-2024 aggregated-looking rows in `cube_Sale_APD` represent genuine
  historical summary postings or something else — not tested beyond the average-value
  observation; whether extending history via `Cube_CES` (using its own PEM101/Omni Channel
  equivalent fields) would actually improve forecasting — flagged as a possibility, not
  evaluated.

**Cube_CES deep dive, reconciliation, and inventory/lead-time table discovery — DONE
(2026-08-31).** Confirms the business framing the user gave ("Cube_CES consolidates delivery
status in one place") and adds detail the framing didn't cover. Script:
`src/investigate_cube_ces.py`; ad hoc queries for Part 4. Outputs: `output/summary/part1_ces_*.csv`
through `part5_extended_*.csv`, `part4_inventory_leadtime_relationship_map.csv`.

- **Part 1 — Status is richer than "Actual vs Backlog," high confidence.** 14 distinct
  `Status` values table-wide (Actual 137,298; P2 21,095; Backlog 3,152; Cancel 2,423; N/A 649;
  **MPS 504 — a separate code from Backlog**; plus P3/T1-T3/F/Y/None, all small). The
  consolidation identity `ActualQty + BacklogQty = PlanQty` holds at **exactly 100.0% for
  Actual, Backlog, and Cancel** (142,873 of 166,432 rows, 85.85%) but **0-15% for every other
  status** (P1-P3, T1-T3, N/A, MPS, F, Y) with large mean discrepancies (up to 5,000+ units for
  T2). What P1-P3/T1-T3/F/Y/N/A actually represent **could not be determined from this data**
  — no lookup/description table found; not guessed. **Grain proven, not assumed**: one row per
  delivery plan/instalment, keyed by a unique `PlanID` — a single (ContractID, ItemCode) pair
  can have multiple `PlanID` rows with different dates/quantities (verified directly:
  `CTR-2025-06153` has 9 rows / 7 items / 9 distinct PlanIDs, with `EEE-F-FC-1040011000`
  alone having 2 rows on different `ActualDelDate`s).
- **Part 2 — the two sources reconcile almost exactly for 2024+, high confidence.** Using
  `division='PEM101'`/`revenue_type='Omni Channel'`/`status IN ('Actual','MPS')` on
  `cube_Sale_APD` vs. `ManuDivision='PEM101'`/`RevenueType='Omni Channel'`/
  `Status IN ('Actual','Backlog')` on `Cube_CES`: qty 182,005 vs. 181,999 (0.003% difference),
  value ₿357.98M vs. ₿357.55M (0.12% difference). At the contract-item level: 8,920 of 8,923
  distinct pairs appear in **both** sources (2 only in `cube_Sale_APD`, 1 only in `Cube_CES`),
  and of the 8,920 overlapping pairs, **100% have exactly matching quantity**. **The two
  sources are not just similar, they describe the same underlying reality — this fully
  validates the earlier resolution of the 3 Actual/MPS overlap cases via `Cube_CES`.**
- **Part 3 — pre-2024 `Cube_CES` data for the pilot items looks like genuine transaction-level
  records, moderate-to-high confidence.** This reverses the speculative "aggregated/summary
  postings" language used for `cube_Sale_APD`'s pre-2024 rows in an earlier session — that
  speculation was about a different table and does not transfer here. Evidence: row/contract/
  qty/value counts grow smoothly and organically year over year from 2017 (316 rows) through
  2023 (3,654 rows), comparable in scale and pattern to 2024-2025 (~3,200-3,250 rows/year,
  ~₿144M/year both eras). `CustomerID` is **100% populated in every year from 2013 onward**
  (unlike `cube_Sale_APD`'s 0% for PEM101 pre-2024) and `ActualDelDate` is 98-100% populated
  throughout. Pre-2024 rows use almost exclusively the three well-behaved statuses (Actual
  15,115; Cancel 137; Backlog 8) — the messier P1-P3/T1-T3/MPS/N/A/None codes are a 2024+
  phenomenon. 2013-2016 is negligible (2-7 rows/year) and should be treated as noise, not
  usable history. A separate 3,804-row bucket has null `CtrDate` (no year, `ActualDelDate`
  0% populated) — an unresolved anomaly, excluded from the yearly comparison. **What the data
  could not settle**: whether 2017-2023 rows are individually as reliable as 2024+ at the
  per-transaction level (only aggregate-pattern comparability was tested, not row-by-row
  audit as was done for `cube_Sale_APD`'s 2024+ era).
- **Part 4 — inventory and lead-time tables identified.** Full map in
  `part4_inventory_leadtime_relationship_map.csv`. **`Cube_Inventory_Exact`** has literal
  `minimum`/`maximum` columns — a Max-Min-shaped deliverable may already exist as a current
  reference point (66 of 68 pilot codes present, 403 rows) — but it is a **single-refresh
  snapshot** (all timestamps within one ~2-minute load window), not a history. **
  `Cube_Inventory_Aging`** gives full 68/68 coverage of current stock-on-hand by warehouse,
  also snapshot-only. **`cube_inventory_tran`** (2.9M rows, 2007-2026) is a genuine historical
  movement ledger — not yet tested against the 58 pilot items, a clear next step for Phase 4.
  **`Cube_PriceList`** has a literal `DeliveryTime` field per supplier-item ("30 Days" etc.)
  but only 24 of 68 pilot codes are covered — a partial lead-time source. **`Cube_PO_Exact`**
  would be the ideal empirical lead-time source (po_date to fulfilment_date) but has **zero**
  rows for any of the 68 pilot codes — not usable for this scope. **`Cube_emanu`** has a
  literal `leadtime` column but no confirmed itemcode join key was found — it looks like
  internal manufacturing job lead time, not vendor/procurement lead time, but this is not
  confirmed either way.
- **Part 5 — extending history via `Cube_CES` would give more usable data at every
  granularity, high confidence in the numbers.** Building the same monthly series from
  `Cube_CES` (2018-01 through 2026-07, 103 months, using the equivalent PEM101/Omni
  Channel/Actual+Backlog filter) shows a **higher** zero-period percentage than the current
  31-month window at every granularity (monthly 80.4% vs. 56.1%; 6-month 66.2% vs. 25.5%) —
  but because the total period count is so much larger, the **absolute** number of non-zero
  periods per item is higher throughout: 6-month 5.7 vs. 3.7; quarterly 9.5 vs. 6.2; 2-month
  12.7 vs. 8.4; monthly 20.2 vs. 13.6. **This directly addresses the specific objection that
  ruled out 6-month buckets before (5 data points was too few to fit and validate anything)
  — extended history gives 17 six-month periods instead of 5**, enough for a genuine holdout
  or even a thin rolling-origin check. Not implemented, per instructions.
- **What the data could not resolve**: the meaning of the 11 minor `Cube_CES` status codes;
  row-by-row reliability of 2017-2023 `Cube_CES` data (only aggregate patterns checked); the
  nature of the 3,804 null-`CtrDate` rows; whether `cube_inventory_tran` or `Cube_emanu`
  actually cover the 58 pilot items (not tested this session).

**Row-level Cube_CES verification — DONE (2026-08-31).** Follows the user's decision: if
history is extended, only MPS and Actual (`cube_Sale_APD`) will be used, matching the current
basis. This pass verifies row by row rather than in aggregate, and **corrects an overreaching
conclusion from the previous session.** Scripts: `src/verify_ces_status_mapping.py`,
`src/verify_ces_pre2024_detail.py`. Outputs: `output/summary/part1_status_mapping_*.csv`,
`part2_row_level_*.csv`, `part2_rows_only_in_*.csv`, `part3_ces_*_2018_2026.csv`,
`part3_ces_price_pre_vs_post_2024.csv`, `part4_unknown_status_check.csv`,
`part5_corrected_*.csv`.

- **Part 1 — the MPS-to-Backlog mapping is proven empirically, high confidence.** Matching
  `cube_Sale_APD` MPS rows to `Cube_CES` by (contractid, itemcode) for 2024+: **158 of 158
  MPS-linked pairs carry `Cube_CES` Status = 'Backlog'** (a few pairs also separately have
  'Actual' rows, expected given `Cube_CES`'s finer per-instalment grain). Reverse direction:
  of 155 `Backlog`-linked pairs, their `cube_Sale_APD` rows are 158 MPS vs. 6 Actual. For
  `cube_Sale_APD` Actual: 8,871 of ~8,876 matched `Cube_CES` rows are 'Actual' (99.94%). **The
  user's hypothesis is confirmed from the data: `Backlog` is the true MPS equivalent.**
  `Cube_CES`'s own literal `"MPS"` status (504 rows table-wide) is unrelated — a naming
  coincidence, not the same concept; this fully explains the original count gap (2,158 vs.
  504) that prompted this task.
- **Part 2 — row-level agreement is very high, high confidence.** Matching on
  (contractid, itemcode, createDate/CtrDate, mapped status, qty): **99.79% of 9,019
  `cube_Sale_APD` rows match a `Cube_CES` row on all 5 fields exactly.** Of matched rows: value
  agrees at 99.95% (5 exceptions, all `Cube_CES` showing ₿0 where `cube_Sale_APD` has a real
  value — isolated gaps, not systematic); customerid agrees at **100%**. The 19 `cube_Sale_APD`
  -only and 25 `Cube_CES`-only rows were traced individually: **18 of 20 distinct
  (contractid, itemcode) pairs reconcile exactly once totaled** — the mismatch is `Cube_CES`
  splitting the same total across multiple finer `PlanID` rows (e.g. 12→9+3, or 500 split into
  370 Actual + 130 Backlog) or a 1-5 day date offset between `CtrDate` and `createDate`, not a
  real disagreement. The 1 remaining pair (`CTR-2023-08885`) exists in `Cube_CES` with matching
  items and status but its `CtrDate` falls in 2023, outside the query's 2024+ filter, while
  `cube_Sale_APD`'s transaction `createDate` is 2024-01-05 — a definitional date-field
  difference, not missing data. **All 20 pairs are fully explained; none represent a genuine
  disagreement. Row-level agreement is high enough to treat `Cube_CES` as reliable for the
  overlap period.**
- **Part 3 — CORRECTS the previous session's Part 3, high confidence.** The prior session's
  "smooth organic growth from 2017" finding used `Cube_CES` **without** the
  `ManuDivision='PEM101'`/`RevenueType='Omni Channel'`/`Status` filters that actually matter —
  it was describing a different, broader population. Under the correct filters, month-by-month
  for the 58 pilot items: **45 of 58 months from 2019 through mid-2022 have literally zero
  rows**; the months that do have data show only 1-11 rows. A clean, sharp break: **December
  2022 = 38 rows/15 items/13 customers → January 2023 = 244 rows/28 items/63 customers**, a
  >6x jump with no ramp-up — the same signature as the 2023→2024 break found for
  `cube_Sale_APD` itself, just one table and one year earlier. **Evidenced boundary: dense,
  2024-comparable `Cube_CES` data for the pilot items begins January 2023, not 2017-2018 as
  previously stated.** Unit price check (pre-2024 vs. 2024+ average per item, using the
  corrected window): ratio median 1.03, range 0.63-2.50 across 49 items — most items are
  close to stable, a handful drift meaningfully (`HS-F-99-1061` 2.50x, `HS-F-99-3061` 2.08x,
  `HS-F-99-2061N` 0.63x) but this alone does not disqualify the data (multi-year price
  movement is plausible). **Column completeness pre- vs. post-2024 (58 items): `CustomerID`,
  `CustomerName`, `ForecastDelDate`, `PlanDelDate`, `PlanID`, `Status`, `ContractPrice` all
  100% in both periods; `ActualDelDate` 99.1% pre vs. 98.1% post (better, not worse, in the
  earlier period); `JobName` 89.5% pre vs. 96.1% post; `OLMJobCode` 38.9% pre vs. 42.8% post
  (both sparse, comparable).**
- **Part 4 — unknown statuses excluded by construction, high confidence.** For the 58 pilot
  items under PEM101/Omni Channel (all time): `Actual` 11,966 rows (spans 2017-2026); `P2`
  3,379 rows (**all null `CtrDate`**); `Backlog` 158 (2025-2026 only); `Cube_CES`'s literal
  `MPS` 113 rows (all null date); `P3` 77 (null date); `Cancel` 25 (real dates 2021-2024, but
  excluded by the status filter itself); `N/A` 25 (null date); `None` 20 (null date). **Every
  one of the 11 unknown-meaning status codes either has no date at all (so a date-range filter
  excludes it regardless) or is excluded by the `Status IN ('Actual','Backlog')` filter by
  construction. They do not need special handling and can be safely ignored for this
  purpose.**
- **Part 5 — CORRECTS the previous session's Part 5, high confidence.** Recomputing with the
  evidenced Jan-2023 boundary (43 months, not the previous session's incorrect 2018-based 103
  months): mean %% zero periods is now **close to or slightly better than** the current
  31-month baseline at every granularity (monthly 55.3% vs. 56.1%; 2-month 43.4% vs. 44.3%;
  quarterly 36.9% vs. 37.9%; 6-month 25.9% vs. 25.5% — essentially unchanged). Absolute period
  counts increase throughout (monthly 43 vs. 31; 2-month 21 vs. 15; quarterly 14 vs. 10;
  6-month 7 vs. 5) and so do absolute non-zero periods (monthly 19.2 vs. 13.6; 6-month 5.2 vs.
  3.7). **This is a more modest but far better-evidenced extension than the previous
  session's claim of 103 months / 17 six-month periods — that claim is superseded.** The
  6-month-bucket case improves from 5 to 7 periods — a real but smaller gain than previously
  stated.
- **Recommendation on extending history**: the evidence supports extending `Cube_CES`
  (Actual+Backlog, PEM101/Omni Channel) back to **January 2023**, not further. Row-level
  agreement with `cube_Sale_APD` is very high (99.79-100% across every field tested) for the
  overlap period, and the pre-2023 v. post-2023 comparison inside `Cube_CES` itself shows
  comparable density, completeness, and pricing. This has **not been implemented** — no
  change to the analysis period, granularity, or config.yaml.
- **Part 6 — `cube_inventory_tran` does NOT provide usable coverage for the 58 pilot items,
  high confidence.** Only **34 rows across 13 of 58 items**, dates almost entirely clustered
  on a single day (2021-12-14), one item's rows from 2017-07-26/08-02. `transtype`: 32 of 34
  rows are `'N'` with no `QtyIn`/`QtyOut` recorded at all; 1 `'A'` (QtyIn=6), 1 `'B'`
  (QtyOut=6). **This table cannot reconstruct historical stock levels for the pilot item
  scope from what is present — coverage is negligible, not comparable to a usable inventory
  history.** Columns (from the prior session's inventory): id, company, itemcode, costcenter,
  trans_date, ourref, project, transtype, orders, descriptions, QtyIn, QtyOut, Avgprice,
  Debit, Credit, warehouse, gl_code, gl_desc, item_desc, uom, location, timestamp. Joins on
  `itemcode`. This is a negative result for Phase 4 groundwork, reported plainly rather than
  reframed as more useful than it is — Phase 4 will need a different inventory data source.
- **What the data could not resolve**: row-by-row transaction-level audit of 2023 specifically
  (only monthly aggregates and unit-price ratios were checked, not a full field-by-field
  comparison like the 2024+ period got, since there is no independent 2023 `cube_Sale_APD`
  source to check against); the cause of the 5 isolated ₿0-value rows in `Cube_CES`; why 8
  items show unit-price ratios beyond +/-10%; where usable historical inventory-level data for
  the pilot items actually lives, if not `cube_inventory_tran` — not identified this session.

**Root cause of the 2022/2023 break — DONE (2026-08-31).** The business could not explain the
break; this investigation determines from the data alone whether it is a system/recording
change or a genuine business change. Script: `src/investigate_2023_break.py`. Outputs:
`output/summary/part1_jan2023_timestamp_detail.csv` through `part5_whole_pem101_monthly_2022_2023.csv`.

- **Part 1 — inconclusive on its own, low-moderate confidence.** `Timestamp` is confirmed
  (again) to be an ETL load time, not a record-entry time — both Jan 2023 and Jan 2024 rows
  show `Timestamp` values from today's single reload, so it cannot distinguish batch-load from
  progressive entry. `ReceiveCtrDate` is identical to `CtrDate` in 100% of rows checked across
  three periods (Jan 2023, Jan 2024, Dec 2022) — no extra signal. `CtrDate` itself is spread
  across 21 distinct days within January 2023 (vs. 20 in the Jan 2024 control, 11 in Dec
  2022) — not clustered on one date, which is at least consistent with day-by-day recording,
  though this alone cannot rule out a system cutover that was itself live daily from day one.
- **Part 2 — points strongly to reclassification, high confidence.** Of the 63 January 2023
  customers (pilot items, PEM101/Omni Channel): **62 of 63 (98%) have prior `Cube_CES`
  activity before 2023-01-01** under some other classification, and 59 of 63 have a
  `ref_customer.entry_date` before 2023. Only 1 customer is genuinely new to the database.
  `cube_Sale_APD` shows zero prior activity for any of them, but that is expected — the whole
  table has no rows before 2024 regardless.
- **Part 3 — inconclusive, largely tautological, low confidence.** 0 of 152 January 2023
  contracts have an earlier `CtrDate` under the same ContractID. This does not discriminate
  well: `ContractID` embeds the year (`CTR-2023-nnnnn`), so a contract dated January 2023 is
  mechanically guaranteed to have no "earlier" record under that same ID regardless of whether
  the underlying business relationship is new or continuing. Reported as required, but not
  treated as strong evidence either way.
- **Part 4 — the decisive finding, high confidence.** The 58 pilot items themselves have
  **11,606 `Cube_CES` rows across 54 of 58 items before 2023-01-01** (zero in `cube_Sale_APD`,
  which has no pre-2024 rows at all regardless of item). Breaking this down: **90.3% of those
  pre-2023 rows (10,477 of 11,606) already carry `ManuDivision='PEM101'` — the correct,
  unchanged division — but `RevenueType` is NULL, not a different value.** The products and
  the division were already there. What is new from January 2023 is that `RevenueType`
  started being populated as `'Omni Channel'` for transactions that were already happening.
  A small residual (100 rows, 16 items) even shows `PEM101`/`Omni Channel` explicitly tagged
  before 2023, confirming the label existed and was used occasionally, just not consistently
  applied. **This is the clearest single piece of evidence in the whole investigation.**
- **Part 5 — the same break hits the whole PEM101/Omni Channel scope at once, high
  confidence.** Pilot items: Dec 2022 (38 rows/13 customers/₿3.51M) → Jan 2023 (244
  rows/63 customers/₿17.76M), a step change with no visible ramp in the preceding months.
  **The identical pattern, same month, appears in the whole PEM101/Omni Channel population
  (not just pilot items)**: Dec 2022 (119 rows/29 customers/₿9.05M) → Jan 2023 (708
  rows/85 customers/₿34.38M). A step change that hits an entire division/revenue-type
  combination simultaneously, across many unrelated product lines at once, is far more
  consistent with a classification or tagging change than with organic demand growth, which
  would not plausibly move every product category in the same division by a similar multiple
  in the same single month.
- **Part 6 — no audit trail exists, high confidence in the absence.** No table in the
  database's 108-table inventory has a name suggesting an audit log, ETL run log, migration
  record, or change history (checked against log/audit/etl/migrat/version/history/load/batch/
  import/sync/snapshot/archive/change keywords — only pre-existing data-snapshot tables like
  `cube_Sale_APD_snapshot` matched, which are periodic data copies, not change logs). Nothing
  beyond the data pattern itself (the `RevenueType` NULL-to-populated transition) dates the
  change to late 2022/early 2023 — there is no independent corroborating record.
- **Conclusion (Part 7): the evidence supports a recording/classification change, not a
  genuine business change — high confidence.** The customers (98% pre-existing), the items
  (54 of 58 already selling under PEM101 before 2023), and the division itself (`PEM101`
  unchanged) were all already there; only the `RevenueType='Omni Channel'` tag started being
  consistently applied from January 2023, and the same-month, whole-division step change
  pattern is inconsistent with organic growth. This mirrors the same kind of finding as the
  2023→2024 break in `cube_Sale_APD` itself (a field going from unpopulated/absent to
  populated), suggesting a broader pattern of classification fields being backfilled or
  newly adopted across this reporting system over this period, though the specific mechanism
  (a coding change, a new reporting policy, an ERP module going live) **could not be
  identified from the data — no audit trail exists to name it.**
- **Practical answer: 2023 data should NOT be combined with 2024+ under the current
  `RevenueType='Omni Channel'` filter as-is, but the underlying business activity is real and
  the boundary is well evidenced.** Combining them directly would not straightforwardly "mix
  incomparable periods" in the sense of the 2023 transactions being fake or different in
  kind — Part 2-4's evidence says the *business* is continuous — but the *filter* silently
  excludes real pre-2023 activity because of the labeling gap, meaning naively extending the
  date range without addressing this would UNDER-count 2022 and earlier while suddenly
  including all of 2023, producing an artificial discontinuity at the boundary. **If history
  is extended, January 2023 remains the correct, evidenced starting point given the current
  filter definition** (consistent with the prior session's row-level verification); extending
  further back would require deciding whether to also treat `PEM101` + `RevenueType IS NULL`
  rows as Omni-Channel-equivalent for the pre-2023 period — a policy decision, not something
  this investigation can settle, since the NULL bucket is not 100% homogeneous (a small number
  of pre-2023 rows are explicitly tagged `Tendering` or `Total Customer Solution`, meaning not
  every NULL-tagged row would necessarily qualify as Omni Channel today).
- **What the data could not resolve**: the specific mechanism behind the classification change
  (system upgrade, new manual tagging policy, etc. — no audit trail exists to name it); whether
  the pre-2023 NULL-`RevenueType` rows are homogeneously Omni-Channel-equivalent or a mixed
  bucket (a small counter-example of explicitly-tagged Tendering/Total Customer Solution rows
  exists alongside them, so this cannot be assumed either way).

**Phase 3.2, Phase 4 — NOT STARTED**

## 3. Locked Decisions (with reasons)

- **Run all real work in Claude Code on the local machine, connecting directly to SQL Server.**
  CSV exports are deprecated because they go stale and require re-exporting every month.
- **Configuration lives in `config/config.yaml`, never hardcoded in scripts**, so
  non-programmers can adjust values.
- **The dashboard stays static with pre-computed JSON.** No backend is needed because
  forecasts are batch-computed, not calculated on demand.
- **Model progression is Naive baseline, then Moving Average, then Croston and SBA.**
  TensorFlow and Prophet are excluded: only 31 months of history and 74% of SKUs have
  intermittent or lumpy demand, so neural networks would overfit and Prophet assumes
  continuous data.
- **Error metrics are MAE, RMSE and Bias.** MAPE is excluded because months with zero demand
  cause division by zero.
- **The pricelist reader must use only sheets where `sheet_state` equals `visible`.** All
  `Version1` sheets are hidden in the workbook, which indicates Version 2 is authoritative.
  Note that PEM103 has two similarly named sheets differing only by a space; the visible one
  is `PEM103-Version2` with no space (verified directly against the file on 2026-08-29).
- **"Drop" and "Surge" are product names, not analytical terms.** Drop means Drop Out Fuse
  Cutout, Surge means Surge Arrester.
- **Pilot item codes are `EEE-F-FC-1040010002`, `HS-F-99-02110` and `HS-F-99-0213`.** All
  three were confirmed present in the pricelist. **Confirmed sufficient (2026-08-31)**: they
  cover two distinct demand patterns found in Phase 2 Step 1 — one Erratic item
  (`EEE-F-FC-1040010002`) that dominates its type at ~60% of its type's total sales value, and
  two Lumpy items (`HS-F-99-02110`, `HS-F-99-0213`) sitting mid-rank (9th and 11th of 58) in
  their type, representative of the bulk of that group.
- **Pilot scope is the Type level (2026-08-31)**: `High Voltage Distribution Fuse Cutout`
  (10 items) and `Medium Voltage Surge Arrester` (58 items). Reason: the Category level (Fuse,
  Surge Arrester) would also pull in Fuse link, HRC fuse, Low Tension Fuse Switch and Fuse
  Holder — different products with different demand behaviour — and mixing them into one
  model would fit none of them well.
- **All queries filter on `division = 'PEM101'` and `revenue_type = 'Omni Channel'`
  (2026-08-31, written into `config/config.yaml`)**. `division` is required because 72
  `productCateName` values, including Fuse and Surge Arrester, appear under more than one
  division, so category/type name alone is not a safe key — confirmed to matter in practice:
  omitting it overstated the pilot group's total sales by ₿60.6M (14.3%), see the audit note
  above. `revenue_type` is fixed to Omni Channel because this project's forecasting scope is
  the Omni Channel business unit; other channels (Tendering, Total Customer Solution, etc.)
  are out of scope. Status basis is Actual plus MPS, matching the Phase 1 convention.
- **GATE LIFTED (2026-08-31).** Originally: data quality must be fully resolved before any
  modelling or backtest work begins. Resolution, by decision where evidence ran out: (1) of
  the original 55 duplicate-vs-split-lot sets, 35 (64%) are confirmed genuine (26
  business-confirmed via `forecast_date`, 9 via `Cube_CES`); 4 partially corroborated; the
  remaining **16 sets (₿123,513) are KEPT IN FULL by decision**, not further evidence — the
  verification method has an ~11.5% false-negative rate on known-genuine cases, so it cannot
  be trusted to declare these duplicates, and the value (0.03% of pilot total) makes
  under-counting demand the worse risk. (2) The 3 Actual/MPS overlaps are resolved as
  legitimate multi-tranche orders (`Cube_CES` ground truth) — **MPS rows are confirmed demand
  and must never be dropped**. (3) The Surge Arrester voltage-tier disagreement remains
  unresolved but is side-stepped for modelling by filtering on `itemcode`, not
  `productTypeName` (see `src/load_data.py`). See the "Data quality closed out" note above for
  full detail. **Modelling and backtest work may now proceed.**

## 4. Open Questions

- The repository is public and `index.html` contains embedded sales figures (confirmed
  2026-08-31: a full 448-item, 32-month dataset including sales values, quantities, and daily
  drill-down records is embedded as plain JSON in the page — not obfuscated). Decision for now
  is to leave it as is, to be revisited later.
- The `division` column carries two legacy values not present in the current pricelist
  (`PEM102-OLD`, `PEM107-OLD`) — whether these should be merged into their current counterpart
  for any future division-based matching is unresolved.
- **Surge Arrester voltage-tier disagreement (found 2026-08-31)**: the pricelist calls all 58
  pilot Surge Arrester items "Medium Voltage Surge Arrester"; the database's own
  `productTypeName` calls the same items "High Voltage Surge Arrester" (or plain
  "Surge Arrester") for every one of the 47 that have any sales data. Not a formatting
  difference — a substantive disagreement on which voltage tier these items belong to. Which
  source is correct is not decided here.
- ~~Actual/MPS same-order overlap~~ — **RESOLVED 2026-08-31**, moved out of Open Questions.
  `Cube_CES`'s own `Status`/`ActualQty`/`BacklogQty` fields confirm all 3 cases are legitimate
  multi-tranche orders, not double counting. See the full-database-inventory note above.
- ~~16 duplicate-vs-split-lot sets unresolved~~ — **CLOSED BY DECISION 2026-08-31**, not a
  blocker. Kept in full rather than removed; see "Data quality closed out" note above for the
  reasoning. Not proven genuine or proven duplicate — the decision to keep them does not
  claim otherwise, it only reflects that the asymmetric risk favors keeping the rows.
- **What system `Cube_CES` belongs to (2026-08-31)** — unresolved, non-blocking. Currently
  unprovable from a read-only data investigation; no further action planned unless it becomes
  relevant to a future task.
- **jobcode mechanism (2026-08-31)** — unresolved, non-blocking. Strongly associated with row
  duplication (91% vs. 11% in normal contracts) and structurally interesting (zero before
  2024, 81% concentrated in PEM101, truncated at 30 of 70 available characters), but the
  specific "JOIN fanout" mechanism hypothesized earlier is contradicted by evidence (the same
  complete job list repeats identically across all duplicate rows, and job count doesn't match
  row count). What would settle it: visibility into the view/procedure that populates
  `jobcode` — currently unprovable from a read-only data investigation.

## 5. Missing Data by Phase

- **Phase 2 and 3.1**: need nothing beyond the sales data already available.
- **Phase 3.2**: needs utility budget data from PEA, MEA and EGAT, EGP bid announcements, and
  sales team insight. Collection format not yet agreed.
- **Phase 4**: needs the inventory cube table name and columns, vendor lead times, the list of
  which codes are genuinely finished goods, and storm season impact data.

---

**Rule: this file must be updated as the final step of every completed task.**
