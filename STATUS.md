# STATUS

## 1. Project Overview

Sales forecasting and inventory planning for PEM Group Omni Channel products sold to Thai
electrical utilities. 445 product codes (visible pricelist sheets only — see Phase 1 note
below for why earlier documents said 448). Data source: SQL Server table
`[salewarehouse].[dbo].[cube_Sale_APD]`.

Phases:
- **1 — Trend**: exploratory sales trend dashboard. DONE.
- **1.5 — Data quality**: not in the original plan; added because modelling could not safely
  proceed without it. DONE.
- **2 — Model selection**: using Fuse Cutout and Surge Arrester product groups as the pilot,
  then the full Fuse + Surge Arrester category scope. DONE.
- **A — Fix potentially wrong foundations**: three checks against existing data (whether
  `forecast_date` is revised after PO intake, why 2025 sales fell 26%, and which date field the
  demand series is keyed on). NEXT, not blocked.
- **B — Close Phase 2 down to item level**: item-level forecasting, cross-division demand,
  no-history items, forward-test log rebuild, missing tests, and an end-to-end pipeline.
- **C — Expand to all 445 item codes**: PEM102, PEM103, PEM104, PEM107 and CI101.
- **D — Phase 4 groundwork**: finished-goods movement history, assembly time, and which
  warehouse stages hold sellable stock. Runs only after Phase C, never in parallel with it.
- **E — Phase 4 proper**: calculate Max-Min and simulate it against historical demand.
- **F — Measure the value**: compare against the team's current method and the
  no-intervention baseline.

**This phase order is binding (2026-09-02): later phases consume earlier phases' outputs, so no
phase may be skipped or reordered, and Phase D never runs in parallel with Phase C.** Phases 3.1,
3.2 and 4 from the original plan are superseded by this A-F sequence. The detailed log in
Section 2 below records work completed under the prior numbering and is not renamed
retroactively — where it says "Phase 3.1," that work is now part of Phase B or C's foundation,
and where it says "Phase 4," that refers to what is now Phases D/E.

## 2. Phase Status

### Current Status Summary (2026-09-02)

**Phase 1 — Trend: DONE.** Demand classified by ADI and CV²; dashboard published on GitHub
Pages with daily drill-down. The ₿2,015.3 million figure was reproduced exactly once the
snapshot date (2026-08-25) and filter combination (`revenue_type = 'Omni Channel'`,
`status IN ('Actual','MPS')`) were established.

**Phase 1.5 — Data Quality: DONE.** Not in the original plan — proved necessary before
modelling could safely proceed. Key findings: `forecast_date` is the contractual delivery
date, and reading it correctly showed most apparent duplicate rows are split lots, not
errors. MPS means "PO Received" and is confirmed demand — it must never be dropped from any
query or model. `Cube_CES` agrees with `cube_Sale_APD` at 99.79% row level and extends usable
history back to January 2023. All queries must filter on `division = 'PEM101'`, because 72
category names (including Fuse and Surge Arrester) appear under more than one division.

**Phase 2 — Model Selection: DONE.** The selected approach is Combination forecasting — the
arithmetic mean of the six candidate models (Naive, MA3, MA6, MA12, Croston, SBA) — applied at
Category and Type level, monthly granularity. Evidence: no single model won consistently at
any level; rule-based selection (SBC, Kostenko-Hyndman, Petropoulos-Kourentzes) did not beat
combination; median and trimmed-mean variants were directionally better but not statistically
distinguishable from the plain mean. Aggregation to Category/Type level cut zero periods from
39.3% to 0% and the validation-to-test overfitting gap from 127% to under 4%. All methods
under-forecast on average — expected, since point forecasts target the mean while real demand
contains spikes; this must be compensated through safety stock in Phase 4, not by changing the
model.

**Phase A — Fix potentially wrong foundations: NEXT, not blocked.** Three checks, all answerable
with existing data, must run before any further modelling or expansion work:
1. Whether `forecast_date` is revised after the PO is received rather than fixed at intake. This
   matters because the two headline business facts — a 6-day median order notice and 73.2%
   on-time delivery — both depend on it: if delivery dates are rescheduled after intake, the
   improvement from 57.8% to 73.2% on-time may reflect rescheduling rather than genuinely better
   fulfilment.
2. Why 2025 sales fell 26% — open for several rounds already. This matters because every
   forecasting model under-forecasts on average, and that bias may be an artifact of training on
   the depressed 2025 period and testing on the recovered 2026 period; using that bias to size
   safety stock would bake the artifact into the system permanently.
3. Whether the demand series used for forecasting is keyed on `createDate` (the PO receipt date)
   or `forecast_date` (the contractual delivery date). Inventory planning needs the date stock
   must be available by, so if the series is keyed on the wrong field, the timing of every
   inventory parameter downstream is wrong.

**Phase B — Close Phase 2 down to item level.** Design how the Category and Type level results
support item-level forecasting: item level showed 74% of series with no stable rolling-origin
winner and a 127% validation-to-test overfitting gap, while Category level was stable — so
confirm Combination forecasting at item level too, where it already showed the smallest bias
(-216, item level). Resolve three open items: (1) the ₿60.6 million of cross-division demand
currently filtered out, since inventory is shared across divisions and excluding 14.3% of demand
would systematically under-provision; (2) the 16 items with no history and 15 with no sales,
which must not simply be dropped, since new items with no history are often the ones most likely
to stock out; (3) the forward-test log, generated for 58 items and six models, which no longer
matches the current scope. Also clear technical debt: write the tests `CONVENTIONS.md` requires
but which do not yet exist, and build a pipeline that runs end to end, since the 21 committed
scripts currently have no documented run order.

**Phase C — Expand to all 445 item codes**, covering PEM102, PEM103, PEM104, PEM107 and CI101.
Data quality for these divisions has never been checked and may differ from PEM101.

**Phase D — Phase 4 groundwork.** Search across tables at once, not one at a time, for finished
goods movement history, assembly time, and which warehouse stages hold sellable stock. **Runs
only after Phase C, never in parallel with it** — if Phase C changes the forecasting approach,
this groundwork would need redoing.

**Phase E — Phase 4 proper**: calculate Max-Min and simulate it against historical demand.

**Phase F — Measure the value**: compare against the team's current method, and estimate what
would happen with no intervention at all, since on-time delivery has already improved from 57.8%
to 73.2% with no system in place.

*Full evidence, methodology and per-task detail for every finding above is preserved in the
detailed log below, in chronological order. The detailed log uses the phase numbering (3.1, 3.2,
4) in effect at the time each task was completed; that numbering is superseded by the A-F plan
above and is not renamed retroactively.*

---

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

**Phase 3.1 — Category/Type-level top-down expansion: DONE (2026-08-31); no model chosen.**

Decision (user, 2026-08-31): forecasting proceeds top-down — Category, then Type, then item
codes only when a specific code needs attention. Purpose is operations/inventory planning, so
directional error (Bias) matters as much as absolute error. This expands the earlier
Type-level pilot (58/68 items) to the **full Fuse + Surge Arrester category scope** for
aggregation purposes; it does not replace the Type-level pilot's original reason for existing
(see Locked Decisions) — aggregating quantities across dissimilar products for a top-down
series is a different operation from fitting one item-level model to mixed products.

- **Scope (Part 1)**: 128 item codes across 8 Types, 2 Categories (`Fuse`, `Surge Arrester`),
  from visible pricelist sheets. 113 have sales history anywhere in `cube_Sale_APD`; 15 have
  none (`EEE-F-FL-1040030100`, three more `EEE-F-FL-5920-353-...` codes, `FC-A-38-00203`, nine
  `HS-F-99-...` codes — see `output/summary/part1_category_scope_all_codes.csv`). Under the
  established filters (`division='PEM101'`, `revenue_type='Omni Channel'`, status Actual/MPS,
  `createDate >= 2024-01-01`): 112 of 113 forecastable codes have activity (one,
  `EEE-F-FL-5920-353-02600`, has history elsewhere but zero rows under these filters); total
  qty 3,348,542, total value ฿689,580,695. Validated: no negative qty/sale, no out-of-range
  dates, daily-to-monthly reconciliation exact. Per-Type breakdown in
  `output/summary/part1_scope_report_by_type.csv`.
- **Aggregation effect (Part 2)**: item level averages 39.3% zero months and 50% of the 113
  items classify Lumpy/Intermittent. Type level (8 series) averages 5.2% zero months, 12%
  Lumpy/Intermittent. Category level (2 series) is 0.0% zero months, 0% Lumpy/Intermittent —
  both Category series and 7 of 8 Type series are Smooth or Erratic (never zero) at monthly
  grain. This is a large, real effect, not an artifact. One exception: `Low Voltage Fuse
  Switch Disconectors` (2 items, ฿22.1M) stays Intermittent even aggregated to Type level —
  genuinely thin, and cannot be pooled further without violating the hierarchy (its
  Fuse-Category siblings are different products). Full stats:
  `output/summary/part2_{item,type,category}_level_stats.csv`.
- **Granularity (Part 3)**: 9 of 10 Category/Type series already have 0% zero periods at
  monthly grain, so coarsening to 2-month (15 periods) or quarterly (10 periods) buckets only
  throws away data points for no benefit — monthly recommended for those 9. Exception: `Low
  Voltage Fuse Switch Disconectors` — quarterly nudges % zero from 41.9% to 40.0% and ADI from
  1.72 to 1.67 (stays Intermittent either way); a marginal, not decisive, improvement. Not
  written to `config.yaml`. Detail: `output/summary/part3_granularity_test.csv`.
- **Backtest (Part 4)**: Naive, MA3/MA6/MA12, Croston, SBA tested at Category and Type level,
  monthly grain, identical settings to the item-level backtest for direct comparability.
  Rolling-origin: 7 origins (train sizes 13,15,17,19,21,23,25 months). **Stable winner (same
  model at every origin): 0 of 10 series (0%)** — reported directly, not glossed over; see
  `output/summary/part4_rolling_origin_stability.csv` for the full per-origin winner spread
  before treating any single model as settled. Train(19)/Val(6)/Test(6): MAE-best and
  Bias-best model disagree for 6 of 10 series (60%) — see
  `output/summary/part4_model_selection.csv` for which direction each disagreement runs
  (under- vs. over-forecasting risk). Full MAE/RMSE/Bias per series/model/origin:
  `output/summary/part4_rolling_origin_results.csv`, `part4_validation_results.csv`,
  `part4_test_results.csv`.
- **Item-level vs. aggregate comparison (Part 5)**: validation-to-test MAE gap (mean
  gap ÷ mean validation MAE, same method used for the item-level 127% figure) falls from
  **+127.0% at item level to +31.9% at Category/Type level** — a real, large reduction in
  overfitting risk from aggregation. Rolling-origin winner stability does **not** improve
  (25.9% stable at item level → 0% at Category/Type level) — aggregation fixes zero-inflation
  and overfitting risk but not which-model-wins instability; stated plainly since it is not an
  improvement. MAE-best/Bias-best disagreement rate is similar-to-slightly-worse at the
  aggregate level (60% vs. 53%), though n=10 series is too small to treat that comparison
  alone as conclusive. Full comparison table:
  `output/summary/part5_item_vs_aggregate_comparison.csv`.
- **Outputs (Part 6)**: final recommendation table (model, granularity, confidence per
  Category/Type) in `output/summary/part6_final_recommendation_table.csv`. No series reached
  HIGH confidence on model choice, because none had a stable rolling-origin winner; most rated
  LOW or LOW-MEDIUM. 10 forecast-vs-actual charts (2 Category + 8 Type) in `output/charts/`.
  **`config/config.yaml` was not modified** — no model or granularity choice was written to
  it, per instruction.
- **What the data could not resolve**: which single model to lock in per Category/Type (no
  stable winner at any of the 10 series); whether item-level forecasts should be derived by
  disaggregating a Category/Type forecast (e.g. by historical share) — not tested, this task
  covered aggregation and comparison only.

**Phase 3.2 — NOT STARTED. Phase 4 groundwork survey: DONE (2026-08-31); Phase 4 itself not started.**

Survey only, scope = the same 128 items (Fuse + Surge Arrester categories). No min/max values
calculated, no model built or changed, `config.yaml` not touched. Full detail in
`output/summary/phase4_part1_*.csv` through `phase4_part7_*.csv`.

- **Cube_Inventory_Exact (current stock)**: single current-state snapshot (2026-08-30, no time
  dimension — confirmed, only 1 distinct date). Covers 125/128 items. Minimum/maximum are set
  **per warehouse**, not per item (items are stocked across up to 20 warehouses); 81 of 119
  multi-warehouse items have genuinely different min/max per warehouse, so there is no single
  "the" min/max without a business decision on which warehouse(s) count. 82/128 items have any
  nonzero min/max set at all; expressed as months of recent sales cover, these range from
  under 1 month to 1700+ months for thin movers — a strong, concrete sign several existing
  settings are stale rather than actively maintained (7 items have a nonzero min/max but zero
  recent sales, an outright contradiction). **Data-quality caveat**: 8 of the 125 matched items
  carry a DIFFERENT `product_category` inside this table (Suspension Insulator, Power
  Capacitor) than Fuse/Surge Arrester — same class of itemcode-ambiguity issue as the earlier
  pricelist-vs-database Surge Arrester voltage-tier disagreement; not resolved here.
- **Cube_Inventory_Aging**: despite its name, this table has **no age-bucket structure** —
  `Condition`, `Type` and `ItemStatus` are constant across all 441,427 rows. It is actually a
  GL-account-level stock valuation snapshot (single timestamp, no history). It cannot answer
  "how long has this stock been held" as-is. Its `GLDescription` field (Finished
  goods/Raw materials) turned out useful for classification (see below), which was not what
  the table's name suggested it would be useful for.
- **Lead time**: no source has both clean data and full coverage. `Cube_emanu.leadtime` is
  genuine manufacturing job cycle time (proven: `leadtime` exactly equals
  `DATEDIFF(day, createJobDate, lastestReceiptDate)` for every sampled row; no supplier/vendor
  field exists in the table at all) — but it has no itemcode column and no data since March
  2019, so it is unusable regardless. `Cube_PO_Exact` gives clean, real, item-linked observed
  vendor lead time (16–189 days, mean 70) but only for 7/128 items (5.5%).
  `Cube_PriceList.DeliveryTime` covers 62/128 (48.4%), genuinely supplier-linked. Best coverage
  is `Cube_Quotation.ctr_leadtime` at 100/128 (78.1%) usable numeric rows, but 60% of its raw
  values are the placeholder text "Process" and the numeric remainder is highly inconsistent
  per item (78 of 100 items have std > half their mean) — it is a quotation-stage promised
  delivery time, order-circumstance-dependent, not a validated procurement lead time.
  **Conclusion: lead time must be obtained from (or confirmed with) the purchasing team** for
  full coverage; the sources above can only serve as a partial cross-check.
- **Finished goods vs. raw material classification**: **122/128 Finished Goods, 6/128 Raw
  Material — HIGH confidence**, confirmed by three independent tables in exact agreement
  (`Cube_ItemList.Assortment1`, `Cube_Inventory_Aging.GLDescription`, and presence of a bill of
  materials in `Cube_BOM_Exact`: all 117 FG-classified items have a BOM, none of the 6 RM items
  do). The 6 RM items are the `FC-A-...` Fuse Holder codes. **Make vs. buy** (whether any item
  is ever purchased complete from an outside vendor instead of manufactured) is NOT reliably
  answerable from data alone: all FG items have a BOM and none appear in the raw-material PO
  table (`cube_po`) under their own code (suggesting they are manufactured, not bought
  complete), but 48 items have a nonzero `PurchasePrice` in `Cube_ItemList` — ambiguous, could
  mean occasional outside sourcing or just a recorded reference price. `manufacturing_type`
  (MTS/MTO/ETO) in `cube_Sale_APD` covers 113/128 items but is an ORDER-level attribute (100 of
  113 items show more than one value across their own sales rows), not a fixed per-item
  classification, and it describes production strategy, not make-vs-buy.
- **Seasonal pattern**: only 2 complete years (2024, 2025) plus one partial (2026, through
  August) are available. June is high across both categories in all 3 years; a few other
  months disagree year to year. **Stated explicitly: 2 data points cannot statistically
  distinguish a real seasonal cycle from coincidence — no seasonal pattern is confirmed by this
  data**, regardless of what the raw numbers suggest visually.
- **Historical stock-level time series**: does not exist. Both inventory tables are single
  current-state snapshots. `cube_inventory_tran` holds movements (QtyIn/QtyOut), covering
  34/128 items (26.6%, 9,652 rows, 2016–2026 including current data) — re-queried for this
  128-item scope; **this supersedes a prior session's narrower 58-item-scope finding of 13
  items/2017-2021 only, which should not be reused for this wider scope.** A stock-level
  history could in principle be reconstructed from these movements, not attempted here.
  **Unresolved caveat**: all 9,652 matched rows carry `gl_desc = 'Raw materials'`, including 28
  items that are classified Finished Goods everywhere else — a real conflict, flagged but not
  investigated further.
- **Related tables and match rates**: full table in
  `output/summary/phase4_part6_related_tables.csv`. Best additional coverage:
  `Cube_Quotation` 116/128 (90.6%), `Cube_ReceiveRM` 82/128 (64.1%, has Supplier + Receive_date
  but no order date, so cannot alone give lead time), `Cube_PriceList` 62/128 (48.4%).
  `cube_po` (raw-material/component purchase orders) has **zero** overlap with the 128
  finished-goods codes — consistent with these items being manufactured, not purchased
  complete under their own code.
- **What the data could not resolve**: which warehouse(s) should count for each item's Max-Min
  policy; the `cube_inventory_tran` GL-classification conflict; whether any item is genuinely
  make-or-buy dual-sourced; whether the 8 itemcode/category-mismatched items in
  `Cube_Inventory_Exact` are collision or data-entry error; whether a real seasonal pattern
  exists at all.

**Phase 4 (Max-Min build) itself — NOT STARTED.**

**Phase 3.1 — Rule-based model selection vs. empirical selection: DONE
(2026-09-01).** Scope: the same 128 items, 138 series (2 Category, 8 Type,
128 Item, 16 of the items are "NoSale" with zero history — 122 series carry
through the analysis). Full detail in `output/summary/rule_part1_*.csv`
through `rule_part6_*.csv`; charts in `output/charts/rule_strategy_comparison_*.png`.

- **Correction made before implementation**: the task's own instructions
  initially stated SBC (2005) recommends Croston for Erratic demand. The
  primary source (Kostenko & Hyndman 2006, reproducing SBC's own Figure 1,
  https://robjhyndman.com/papers/idcat.pdf) was fetched and verified to say
  the opposite — Croston for Smooth ONLY, SBA for Erratic/Lumpy/Intermittent.
  Flagged to the user with the exact quote; user confirmed to follow the
  verified primary source. **Do not use the "Croston for Erratic" framing
  again — it is factually wrong and was corrected here.**
- **Characteristics (Parts 1-2)**: measured ADI, CV², %zero, trend
  (OLS slope, significance = p<0.05 AND fitted change >20% of series mean —
  our own magnitude threshold, not from a published source), a heuristic
  single-changepoint level-shift screen (Welch's t, |t|>3 and >50% mean
  change — explicitly NOT a formal structural-break test), and month-of-year
  strength (eta-squared on de-trended residuals, reported as **observation
  only** — 2 complete years cannot confirm seasonality). Classification is
  stable across first-12/first-24/full-history windows for 100% of Category
  series, 87.5% of Type series, 64.8% of Item series — reported plainly,
  including which item series flip classification across windows
  (`rule_part2_stability_summary.csv`).
- **Rule sets implemented (Part 3)**, each verified against a primary or
  authoritative reference implementation before coding, not invented:
  - **SBC (2005)**: thresholds ADI=1.32, CV²=0.49; Croston for Smooth, SBA
    otherwise.
  - **KH (2006)**: exact non-linear boundary (their eq. 2, using a per-series
    fitted interval-smoothing parameter α — via statsforecast's
    golden-section SES optimiser on the inter-demand-interval series,
    bounds 0.1–0.3), cross-checked against Nikolaos Kourentzes' own
    reference R implementation (`idclass.R`,
    https://github.com/trnnick/tsintermittent). Corrected corner values
    confirmed from the paper: p=4/3 (not 1.32), v=0.5 (not 0.49) at the
    α=0 limit.
  - **PK (2015)**: identical KH boundary, with an SES override whenever
    ADI≤1 (demand in every period) — also verified against the same
    reference implementation (`use.ses <- p <= 1`).
  - **Extended layer (our own addition, explicitly NOT from any of the three
    papers)**: Naive when history <24 months or classification is unstable
    across windows; SES (no trend) or Holt (significant trend) for the
    Smooth quadrant, generalising P&K's ADI≤1 principle to the whole Smooth
    region since none of the three papers model trend. **Consequence worth
    remembering**: because Smooth is exactly the region SBC/KH assign to
    Croston, plain "Croston" never survives as a final recommendation under
    any rule set once this layer is applied — the `*_base` columns in
    `rule_part3_model_assignments.csv` hold the un-layered literature rule
    if that's ever needed instead.
  - **Bug fixed during implementation**: `numpy.bool_(True) is True`
    evaluates to `False` (numpy bools are distinct objects from Python's
    `True`/`False` singletons) — a stability flag read back from CSV via
    `is True` silently forced every series to "Naive". Fixed to `== True`.
    Worth remembering for any future code comparing a CSV-round-tripped
    boolean with `is`.
- **Strategy comparison on the test set (Part 4)**: train=19/val=6/test=6
  months, rule-based classification computed on train+val only (no test
  leakage). **Combination forecasting (equal-weight average of
  Naive/MA3/MA6/MA12/Croston/SBA) has the best MAE and RMSE at ALL THREE
  levels**, and the best MASE at Category and Type level. **Rule-based
  selection (SBC/KH/PK — nearly identical results to each other) does NOT
  outperform Combination, and is WORSE than plain Naive on MASE at Type and
  Item level.** Stated directly per instruction, not softened. MAE-best and
  Bias-best strategy disagree on 0% (Category), 12.5% (Type), 27.7% (Item)
  of series — full detail and direction in `rule_part4_mae_vs_bias_best.csv`.
- **Rolling-origin rule stability (Part 5)**: the **underlying** SBC/KH/PK
  classification-driven choice (before our sufficiency gate) is genuinely
  far more stable across 7 rolling origins than empirical validation-based
  selection was in prior work — 100% (Category), 87.5% (Type), 84-89%
  (Item), vs. empirical's ~0% (Category/Type) and ~26% (Item), established
  previously. **This specific literature premise IS supported.** However,
  the **final, practically-deployable** layered choice is much less stable
  (0-32%), because our own 24-month sufficiency gate mechanically forces a
  Naive→non-Naive flip once a series crosses that threshold — an artifact
  of our gate design, not evidence the underlying rule itself is unstable,
  but it means the practical version tested here does not yet deliver the
  stability benefit in deployable form.
- **Bottom line (Part 6)**: the evidence supports **Combination forecasting**
  over rule-based selection for actual forecast accuracy at all three
  levels. Rule-based selection's genuine advantage — much greater stability
  of the underlying classification across time — is real and measured, but
  was not preserved through to a deployable recommendation because of our
  own sufficiency-gate design, not a flaw in the cited literature. No model
  choice was written to `config/config.yaml`.
- **What the data could not resolve**: the sufficiency-gate design that
  would let rule-based selection realise its stability advantage in
  practice; whether the Smooth-quadrant SES/Holt generalisation (vs. the
  literal ADI≤1-only P&K rule) is the better design choice; whether a
  different combination weighting would beat simple equal-weight averaging;
  whether any real seasonal pattern exists (2 complete years, unconfirmable
  regardless of further analysis of this same dataset).

**Phase 3.1 — Bias, overfitting gap and margin follow-up: DONE (2026-09-01).**
Reporting task on the rule-based-selection results above: re-reported Bias
and MAE-vs-Bias disagreement (both already computed, just not surfaced as
headlines previously), and newly computed the validation-to-test overfitting
gap per strategy (this did NOT exist before — only the empirical-selection
gap had ever been computed) and a winner-margin significance check. Full
detail in `output/summary/rule_part7_*.csv`.

- **Bias**: every one of the 4 strategies UNDER-forecasts on average, at all
  3 levels — consistent with the Increasing trend found in most Smooth
  series (backward-looking models undershoot a growing series). Ranked by
  |Bias| (smallest first), Combination has the smallest bias magnitude at
  every level (Category -12,139; Type -3,045; Item -216 units/month), Naive
  is close behind, and Empirical has the LARGEST bias magnitude at Category
  and Type level (-17,181 and -3,964) — worth remembering when weighing
  stockout risk, since Empirical is chosen for lowest validation MAE with no
  regard for directional bias.
- **MAE-vs-Bias disagreement**: 0% (Category), 12.5% (Type), 27.7% (Item) of
  series have a different best STRATEGY under MAE than under |Bias|. An
  earlier, separate analysis (comparing the 6 base MODELS empirically, not
  these 4 coarser strategies) found 53.4%/60% — the same underlying pattern
  holds (MAE-best and Bias-best often differ) but at a lower rate once
  choices are coarsened to 4 strategies. Largest individual disagreements in
  `rule_part7_mae_bias_disagreement_detail.csv`.
- **Overfitting gap per strategy (NEWLY COMPUTED)**: **Empirical selection has
  the LARGEST validation-to-test gap at every level (32.7% Category, 31.2%
  Type, 9.8% Item)** — the only strategy that tunes on validation error, so
  this is exactly the selection-induced overfitting theory predicts.
  Combination has the SMALLEST gap at Category and Type level (3.8%, 4.2%);
  at Item level most strategies actually score BETTER on test than
  validation (negative gap — Naive -6.6%, Rule-KH/SBC -5.2%, Combination
  -0.9%), meaning noise dominates any true overfitting signal there, while
  Rule-PK (+2.0%) and Empirical (+9.8%) are the only two with a positive
  (worsening) gap. **Rule-based selection and Combination DO reduce
  overfitting relative to Empirical, as theory predicts** — this is now
  directly measured, not assumed.
- **Winner margin / significance check**: Combination has the best point-
  estimate MAE at all 3 levels, but a PAIRED comparison against the
  runner-up (same series, both strategies — more appropriate than an
  unpaired spread since the two are scored on identical series) gives a
  paired t-statistic of only 0.26 (Category), 0.37 (Type) and 1.05 (Item) —
  **none clear a conventional significance bar (~2)**. Combination's edge at
  any single level, taken alone, could plausibly be noise. Combination's
  case rests on being the most CONSISTENT top performer across MAE, RMSE,
  bias magnitude and overfitting gap, across all 3 independent levels
  simultaneously (triangulation), not on any one comparison being
  individually decisive.
- **The 16 no-history items**: unchanged from the prior task — 16 items
  have zero sales in the analysis window (`rule_part7_no_history_items.csv`
  lists them), excluded from every backtest/strategy metric (no train/val/
  test split is possible with zero data). No forecast is currently produced
  for them by this pipeline; they would need a different, no-history-specific
  treatment if needed for Phase 4, out of this pipeline's scope.
- **Stability-gate mechanism explained (not changed)**: the extended layer's
  hard 24-month minimum-history cutoff means 6 of the 7 rolling-origin test
  points (13-23 months) can NEVER pass the gate, mechanically forcing Naive
  at every one of them regardless of the underlying ADI/CV² classification's
  actual stability — this is why "base" (un-gated) stability was 84-100%
  but "final" (gated) stability was only 0-32% in the prior task: almost
  entirely the gate's own hard cutoff, not genuine boundary-crossing.
  Alternatives (not applied, listed for a future decision): lower the
  minimum-history threshold; make the gate continuous/graduated rather than
  a hard on/off switch; relax the stability sub-check so it can evaluate
  before 24 months; drop the stability sub-check entirely; or re-run the
  Part 5 rolling-origin test restricted to origins ≥24 months to isolate the
  gate's own behaviour once it can actually fire.
- **What the data could not resolve**: whether Combination's edge over the
  runner-up at any given level is more than noise (paired t below ~2 at
  every level); which stability-gate alternative would work best (not
  tested, presented as options only).

**Combination-variant test, order-notice lead time, on-time delivery
baseline, and their connection — DONE (2026-09-01).** Three independent
questions plus a connecting analysis, run in one task at the user's request.
No inventory calculation was implemented (out of scope, per instruction). No
model choice was written to `config/config.yaml`. Scripts:
`src/combination_variants.py`, `src/order_leadtime.py`,
`src/delivery_performance.py`, `src/leadtime_delivery_link.py`. Full detail:
`output/summary/combo_variant_*.csv`, `leadtime_*.csv`, `delivery_*.csv`,
`link_*.csv`; charts in `output/charts/` (same prefixes).

- **Part 1 — median/trimmed-mean/robust-subset combination vs. the current
  arithmetic mean: the arithmetic mean is NOT clearly beaten, medium
  confidence.** Reused the existing infrastructure exactly (`build_all_series`,
  the 6 base models, the 19/6/6 train/val/test split, and the paired-t
  methodology already used for the strategy comparison) — nothing rebuilt.
  Tested Mean (current), Median, TrimmedMean (drops 1 highest + 1 lowest of
  6), and RobustSubsetMedian (median of {Naive, MA3, MA6, MA12} only,
  excluding Croston/SBA — reasoned from this project's own prior finding that
  Croston/SBA over-forecast Intermittent items by +25 to +27 units/month and
  showed slow-adapting dormancy behaviour, see the backtest-anomalies note
  above; not a generic literature choice). On point estimates, a variant DOES
  beat Mean's test-set MAE at every level: RobustSubsetMedian at Category
  (13,485 vs. 14,606, +7.7%) and Type (3,760 vs. 4,011, +6.2%); Median at Item
  (384.5 vs. 389.3, +1.3%). **But paired t-tests (same methodology as the
  prior rule-based-selection task) find none of these margins statistically
  distinguishable from Mean at conventional significance**, except at
  Category level where Median and TrimmedMean nominally clear |t|>2 (2.34,
  2.94) — reported with the caveat that Category level has only 2 series, so
  a 2-observation paired test is very weak evidence regardless of the t-value.
  Bias also improves with every non-Mean variant at every level (smaller
  |Bias| than Mean throughout), and the validation-to-test gap is smaller (or
  negative, i.e. test outperforms validation) for every non-Mean variant at
  Category and Type level. **Conclusion, stated directly per instruction:
  the evidence leans toward RobustSubsetMedian/Median being marginally better
  than the current Mean on point estimates, bias and overfitting gap
  simultaneously (the same triangulation logic used to justify Combination
  over rule-based selection previously), but — matching that same prior
  finding's pattern — the margin over the runner-up does not clear a
  significance bar at Type or Item level, and the Category-level significance
  rests on only 2 series. This is NOT strong enough evidence to recommend
  switching away from the arithmetic mean; the current approach is not
  beaten with confidence, but a reasoned case exists for revisiting this with
  more series/history in the future.**
- **Part 2 — order notice is very short overall: high confidence.** Business
  definition used directly (not re-derived): `createDate` = PO received,
  `forecast_date` = contractual delivery date; notice = forecast_date -
  createDate. Scope: 128 items, same filters as the rest of this project
  (division=PEM101, revenue_type=Omni Channel, status Actual/MPS,
  createDate>=2024-01-01) — a scope decision stated explicitly, not a data
  limit. 27,479 rows pulled; 1 row has no forecast_date; 15 rows (0.05%) have
  a negative interval (forecast_date before createDate, a data anomaly,
  excluded and reported separately). **Median notice is only 6 days, mean
  10.9 days, heavily right-skewed (skewness 9.95) — a small minority of
  orders carry very long notice, but the bulk have almost none.** Only
  **5.88% of orders carry at least 1 month's notice, 2.22% at least 2 months,
  1.29% at least 3 months** (full cumulative table in
  `leadtime_notice_buckets_overall.csv`) — the overwhelming majority of
  demand cannot be met by producing/purchasing to order under any reasonable
  lead time; most of it requires stock on hand. By product type, medians
  range 3-10 days (Medium Voltage Surge Arrester shortest at 3, Low Voltage
  Fuse Switch Disconectors longest at 10) — all still far under a month. By
  customer, high dispersion exists (std of per-customer medians = 33.7 days,
  range 0-510 days across 638 customers) — a few customers consistently give
  much longer notice, most do not. **By year, the pattern is STABLE**: median
  notice 6.0 days in both complete years 2024 and 2025 (2026 partial, also
  6-7 days, not used for the stability comparison). **Spike-month orders
  carry statistically significantly longer notice than normal-month orders
  (Mann-Whitney p<0.0001) but the practical difference is small (median 7
  days vs. 6 days)** — value-weighted, spike months hold ₿36.6M in orders
  with <30 days' notice vs. ₿28.1M with ≥30 days, so spike-month demand is
  NOT predominantly long-notice. **Data-quality caveat carried forward
  explicitly**: an earlier investigation found forecast_date sometimes steps
  forward across a contract's repeated rows (multi-tranche updates) — this
  script cannot rule out that forecast_date reflects a continuously-updated
  latest plan rather than a fixed promise made at PO intake, which could bias
  the very short median downward. Not resolved here.
- **Part 3 — on-time delivery baseline (Cube_CES): 64.9% on time, 26.3%
  early, 8.8% late (vs. Plan) — high confidence, 98.8% of rows assessable.**
  Scope: 128 items, ManuDivision=PEM101, RevenueType=Omni Channel, Status IN
  ('Actual','Backlog'), CtrDate>=2023-01-01 (the evidenced Cube_CES boundary
  from the earlier row-level-verification task) — a deliberately LONGER
  window than the 2024+ demand-forecasting scope, since this is a delivery-
  performance baseline, not a model-fitting window. 36,382 rows pulled;
  **98.80% assessable** (Status='Actual' with a non-null ActualDelDate); 434
  rows (1.19%) are Status='Backlog' (not yet delivered — reported as current
  backlog below, not an outcome) and 1 row is an unexplained small gap
  (Status='Actual' but missing ActualDelDate). Results against
  ForecastDelDate are nearly identical (64.0/26.2/9.8%) because PlanDelDate
  and ForecastDelDate are literally identical on 97.9% of assessable rows —
  the two comparisons are not independent checks. Lateness distribution
  (late rows only): median 2 days late, mean 5.8 days, heavily right-skewed
  (skewness 17.0, max 729 days) — most late deliveries are only slightly
  late, with a long tail of a few very late ones. By product type, %% late
  ranges from 1.6% (Low Voltage Fuse Switch Disconectors) to 12.8% (HRC
  fuse). By customer, %% late varies widely across the top 15 (0.6% to
  33.3%) — late deliveries concentrate heavily in specific customers, not
  evenly spread (see `delivery_by_top15_customers.csv`). **By year, on-time
  performance has IMPROVED steadily: 57.8%/61.0%/68.6%/73.2% on-time in
  2023/2024/2025/2026, and %% late has fallen from 24.4% (2023) to 2.8%
  (2026, partial)** — a real, large, monotonic improvement, though 2023's
  figure should be read with the Cube_CES boundary caveat in mind (dense data
  only begins Jan 2023). Spike-month orders are somewhat more likely to be
  late (13.1% vs. 8.6% for normal months; chi-square p<0.0001, statistically
  significant, computed on a spike-month definition recomputed directly on
  Cube_CES's own quantity using the identical 3x-median rule — NOT the exact
  same month list as Part 2's cube_Sale_APD-based spikes, stated explicitly
  since the source table, date field and window differ). **Current backlog**:
  434 rows / 153 contracts / 65 items / 61 customers, total 67,509 units
  outstanding; **only 2.76% of backlog rows are already overdue against
  Plan** (median "age" is -7 days, i.e. most backlog is not yet due) — the
  backlog is not, in aggregate, a large pile of already-broken promises, it
  is mostly still within its planned window. Backlog concentrates in a
  handful of items (`LS-F-99-1004`, the `EEE-F-FL-1040030xxx` family) and
  customers (`CS06836`, `CS03051`) — full detail in
  `delivery_backlog_by_item.csv` / `_by_customer.csv`.
- **Part 4 — late deliveries did NOT have unusually short notice; the
  majority (69.5%) had normal-or-longer notice and were still late —
  moderate-to-high confidence.** Computed self-contained within Cube_CES
  (PlanDelDate - CtrDate, on the identical rows already classified
  on-time/late in Part 3) rather than joining across to Part 2's
  cube_Sale_APD figures, because Cube_CES splits contracts into finer
  PlanID-level rows than cube_Sale_APD, so a cross-table join risked a
  many-to-many mismatch — a reasoned methodology choice, stated explicitly.
  26 of 35,947 rows (0.07%) excluded for a negative notice anomaly, same
  class as Part 2's finding. **Late deliveries had a LONGER median notice (6
  days) than on-time/early deliveries (5 days)** — statistically significant
  (Mann-Whitney p=1.6e-37) due to the very large sample, but the direction is
  the OPPOSITE of "late because of short notice," and the practical
  difference (1 day) is tiny. Using a data-driven cutoff (the overall median
  notice of this scope, 5 days) to classify each of the 3,146 late
  deliveries: **961 (30.5%) had below-median (SHORT_NOTICE) notice; 2,185
  (69.5%) had at-or-above-median notice and were STILL late
  (ADEQUATE_NOTICE_STILL_LATE)**. Weighted by quantity, the pattern holds
  (391,182 units in the ADEQUATE_NOTICE_STILL_LATE bucket vs. 148,351 in
  SHORT_NOTICE). The split is broadly similar across product types (24.5% to
  53.8% SHORT_NOTICE, i.e. ADEQUATE_NOTICE_STILL_LATE is the majority
  category for 7 of 8 types) and stable across years (24-34% SHORT_NOTICE,
  no trend). By customer, the split varies a lot (e.g. `CS07050`: 7 of 79
  late orders were SHORT_NOTICE (8.9%) vs. `CS06836`: 57 of 91 (62.6%)) —
  the demand-timing vs. supply-planning mix is customer-specific, not
  uniform. **Practical conclusion, stated directly**: most of the observed
  late-delivery problem in this scope is NOT explained by customers ordering
  too close to the delivery date — it looks more like a supply/planning
  problem that inventory (Max-Min) could plausibly help address, though this
  analysis does not itself design or validate any such intervention.
- **What the data could not resolve**: whether forecast_date in cube_Sale_APD
  represents a fixed PO-intake promise or a continuously-updated latest plan
  (Part 2's open caveat, unresolved); whether Cube_CES's own PlanDelDate is
  similarly revised over a contract's life (not tested — if PlanDelDate is
  also updated after the fact, "notice" as computed here could understate
  the true original promise, though this would not change the late-vs-
  nonlate DIRECTION already found, since both groups would be equally
  affected); the root cause of WHY the ADEQUATE_NOTICE_STILL_LATE deliveries
  were late (capacity, component shortage, scheduling — no cause field exists
  in Cube_CES to test this); why 2023's on-time rate is markedly lower than
  2024-2026 (could be genuine improvement, or a residual effect of the
  evidenced Jan-2023 Cube_CES data-density boundary — not disentangled here);
  whether the RobustSubsetMedian/Median combination variants' Category-level
  significance would hold up with more than 2 series (structurally
  untestable with only 2 Category series in this scope).

**Stock-availability hypothesis investigation — DONE (2026-09-01).**
INVESTIGATION ONLY, per instruction: no min/max values calculated, nothing
built, `config/config.yaml` not touched. Tests whether late deliveries are
caused by stock being unavailable when the order arrives — motivated by the
prior task's finding that median customer notice is only 6 days, far too
short to produce/procure against. **The data has no field stating why a
delivery was late, and no historical stock-level time series exists
(STATUS.md, Phase 4 groundwork survey) — this hypothesis CANNOT be proven
directly.** This task gathers the strongest available INDIRECT evidence
across four angles. Script: `src/investigate_stock_availability_hypothesis.py`
(reuses `processed_ces_delivery_assessable.csv`, `phase4_part1_minmax_vs_sales.csv`,
`delivery_ces_spike_months.csv`, `processed_order_leadtime_clean.csv` — nothing
rebuilt). Full detail: `output/summary/hyp_part1_*.csv` through `hyp_part5_*.csv`;
charts in `output/charts/hyp_part1_*.png` through `hyp_part4_*.png`.

- **Part 1 — late rate vs. min/max configuration: NO SUPPORTIVE RELATIONSHIP
  FOUND, high confidence in this negative result.** Stated plainly per
  instruction, not spun toward the hypothesis. Item-level (87 of 112 items
  with >=10 assessable orders): configured items (min or max >0) actually
  have a HIGHER mean late rate (9.9%) than unconfigured items (8.3%), though
  not statistically significant (Mann-Whitney p=0.30). Pooled/volume-weighted:
  the same direction, and this one IS statistically significant (8.86% vs.
  5.72%, chi-square p=0.027) — opposite to what the hypothesis would predict.
  Among configured items, months-of-cover vs. late rate: a weak negative
  Spearman correlation (rho=-0.146, p=0.215, i.e. more cover very mildly
  associated with LESS late — the only result pointing the hypothesis's
  direction here — but not statistically significant) and a low-cover vs.
  high-cover split shows LOW-cover items slightly LESS late (8.74% vs. 9.43%,
  p=0.48, not significant). **Conclusion: the item's CURRENT min/max
  configuration status, as recorded in Cube_Inventory_Exact today, does not
  meaningfully predict its historical late-delivery rate — if anything the
  weak signal runs opposite to the hypothesis.** This is not surprising given
  the earlier Phase 4 finding that many existing min/max settings look stale
  (some represent 1700+ months of cover) rather than actively-maintained
  policy — a stale, disconnected-from-demand setting would not be expected to
  correlate with delivery outcomes either way.
- **Part 2 — order size, late vs. on-time: WEAK BUT STATISTICALLY
  SIGNIFICANT SUPPORT, moderate confidence.** Comparing each order's quantity
  to that item's own median order size (67 of 112 items had enough late AND
  on-time orders to compare): late orders average 3.13x their item's typical
  size vs. 2.45x for on-time orders (medians tie at 1.0x for both — the
  effect lives in the upper tail, not a shift in the typical order).
  Mann-Whitney on the full distributions is significant (p<0.0001). Late
  rate rises with order size in a clean, monotonic, statistically significant
  step from the smallest quartile (7.45%) to the largest (9.94%,
  chi-square p<0.0001). **However, this pooled pattern is NOT clearly
  replicated item-by-item**: only 38 of 67 items (56.7%) individually show a
  larger median late-order size than their own on-time median — not
  significantly different from chance (sign-test p=0.33) — so the pooled
  effect may partly reflect pooling across items of different typical sizes
  rather than a uniform per-item mechanism. **Conclusion: large orders
  (relative to an item's own norm) run modestly, but not dramatically, later
  more often — consistent with "stock on hand was insufficient for the
  order's size" rather than "stock was completely absent," but the effect is
  real, not large, and not uniform across items.**
- **Part 3 — timing: STRONG, CONVERGING SUPPORT, high confidence.** Late
  deliveries by month (2023-2026, full table in
  `hyp_part3_late_deliveries_by_month.csv`) show a clear downward trend
  matching Part 3 of the prior task's on-time-improvement finding (late rate
  fell from ~22-31% in early 2023 to 1.4-4.6% by mid-2026). Spike months
  (recomputed directly on Cube_CES quantity, same 3x-median rule used
  throughout this project — 7.4% of item-months, 4.4% of ActualQty volume in
  this scope, NOT the same figure as the original 58-item-pilot 16.6%/3.4%
  finding, which used a different table and narrower item scope) have a
  materially higher late rate (13.05% vs. 8.64% for normal months,
  chi-square p<0.0001). **The NEW lag test — whether an item's late
  deliveries follow shortly (1-2 months) after that item's OWN spike month —
  is also statistically significant**: late rate is 10.78% in the 1-2 months
  immediately following a spike vs. 8.56% at baseline (chi-square p=0.011).
  **This is the single piece of evidence in this task most directly
  consistent with a "stock was drawn down by a spike and not replenished in
  time" mechanism**, since it shows an effect that specifically follows,
  rather than merely coincides with, high-volume periods.
- **Part 4 — customer differences: ITEM MIX DOMINATES, WITH AN IMPORTANT
  UNEXPLAINED RESIDUAL — moderate confidence, genuinely nuanced.** Across the
  top 15 customers, an item-mix-adjusted "expected" late rate (each
  customer's own item purchase mix, weighted by each item's all-customer late
  rate) correlates strongly with their ACTUAL late rate (Spearman rho=0.64,
  p=0.010) — **customers with high late rates are largely the ones who
  happen to buy the items that run late for everyone, not idiosyncratic
  "bad" customers.** This favors an item/stock-level explanation over a
  customer-behaviour explanation, matching the hypothesis's framing. Deep
  dive on the lowest (`CS00089`, 0.59% late) vs. highest (`CS05661`, 33.27%
  late) top-15 customers: the high-late customer orders much larger
  quantities (median 200 vs. 50 units, mean 279 vs. 75) and gives longer
  notice (median 9 vs. 1 day) — notice period is clearly NOT the explanation
  here (the high-late customer already gives MORE notice). **But a
  head-to-head check on the 11 items BOTH customers buy is the most striking
  finding of this task**: the high-late customer is 28-100% late on every
  one of these shared items while the low-late customer is 0% late on the
  IDENTICAL items (mean gap +42.8 percentage points) — a pure item/stock
  effect should hit any customer buying that item similarly, so this residual
  is NOT explained by item identity alone. The most likely visible
  contributor is order size (this pair's median order sizes differ 4x,
  consistent with Part 2's size effect), but **the data cannot confirm this
  is the whole explanation** — some customer- or allocation-specific factor
  (e.g. priority given to certain accounts, or how orders are batched) cannot
  be ruled out from what is available.
- **Part 5 — synthesis estimate: LEANS TOWARD SUPPORTING the hypothesis,
  LOW-MODERATE confidence, presented as a range not a figure.** Evidence
  scorecard: 3 of 4 testable angles point toward the hypothesis (order size,
  spike-timing lag, and item-mix dominance over customer behaviour); Part 1
  (the most directly relevant data — actual current stock policy) does NOT
  support it. **Estimated range: roughly 35-65% of the 3,172 late deliveries
  in this scope could plausibly have been prevented by adequate stock on
  hand** — stated explicitly as a reasoned judgment range built from
  correlational evidence, NOT a measurement, because no historical
  stock-level data exists to verify it directly. Assumptions stated
  explicitly in the script's own output (see console log / STATUS.md summary
  message): (1) Part 1's relationships are assumed causal, but item type,
  customer mix and manufacturing complexity are not controlled for; (2) the
  order-size and spike-lag effects are assumed consistent with a
  stock-drawdown mechanism, but could also reflect genuinely longer
  production time for larger/post-spike orders; (3) the item-mix effect could
  also proxy for item-specific manufacturing difficulty rather than only
  stock availability — this data cannot separate the two; (4) this is not a
  measurement of stockouts coincident with late orders, only an inference
  from correlates — a planning input to prioritize further investigation,
  not a validated figure.
- **BOTTOM-LINE VERDICT: the evidence LEANS TOWARD SUPPORTING the stock-
  availability hypothesis, but is not strong enough to treat as confirmed,
  and one of the four angles (Part 1, arguably the most directly relevant)
  does not support it at all.** This is reported as a genuinely mixed,
  leaning-supportive picture — not a confirmation — consistent with the
  instruction not to read a supportive conclusion into weak or absent
  relationships.
- **What the data could not resolve**: whether stock was actually unavailable
  at the moment any specific late order arrived (no historical stock-level
  data exists — the core, unfixable limitation of this whole investigation);
  why Part 1 shows no supportive relationship despite Parts 2-4 leaning
  supportive (possible explanations — stale/disconnected min-max settings,
  warehouse-level aggregation blurring the true per-item picture, or the
  hypothesis being wrong for the min-max mechanism specifically even if right
  in general — not distinguishable here); whether the Part 4 head-to-head
  residual (+42.8 points on identical items) is fully explained by order size
  or partly by a customer-/allocation-specific factor; whether the Part 2
  item-level order-size effect (56.7% of items, not significant) would
  strengthen with more data or is genuinely a pooling artifact; whether the
  Part 3 post-spike-lag effect reflects stock drawdown specifically or a
  general capacity/scheduling strain following any high-volume period.

**Phase 4 prep investigation: production strategy, warehouse structure, actual lead time,
lot-size evidence — DONE (2026-09-02).** INVESTIGATION ONLY, per instruction: no min/max
calculated, no model built, `config/config.yaml` not touched. Scope: the same 128 items (Fuse
+ Surge Arrester). Business context supplied by the user for this task: lead time is roughly
1.5-2 months as a working default (to be made configurable per item later); products are a mix
of made in-house and assembled from purchased parts; MOQ depends on make-to-stock vs.
make-to-order; warehouses are separated by business unit and planning should work per warehouse
first, then roll up company-wide. Scripts: `src/production_strategy_investigation.py` (Parts
1-2), `src/warehouse_structure_investigation.py` (Part 3), `src/leadtime_actual_investigation.py`
(Part 4), `src/order_quantity_patterns_investigation.py` (Part 5). Full detail and confidence
levels: `output/summary/phase4_prep_investigation_report.md`; per-item/per-type CSVs:
`output/summary/part1_*.csv` through `part5_*.csv` (this task's numbering restarts at part1,
distinct from the earlier Phase 4 groundwork survey's `phase4_part*.csv` files, which this task
does not replace).

- **Part 1 — manufacturing_type re-confirmed as an order-level, not item-level, field, high
  confidence.** Whole-table distinct values: MTS 69.7%, MTO 22.7%, blank 5.3%, ETO 2.3% (read as
  the standard Make-to-Stock/Make-to-Order/Engineer-to-Order abbreviations — no lookup table
  defines them explicitly). Covers 113/128 items (88.3%), but 100 of those 113 (88.5%) show MORE
  THAN ONE value across their own rows — this matches and extends the earlier Phase 4 groundwork
  survey's finding, now with the exact per-item mixed-value rate measured. **New corroborating
  evidence**: `Cube_Inventory_Exact` has two production-order WIP staging locations literally
  named `FMTS`/`FMTO`; 69 of 128 items have rows under BOTH, independently confirming the same
  item is staged under both strategies depending on the order. **No other table in the database
  has an item-level production-strategy field** (re-confirmed against the earlier
  `src/investigate_leadtime_classification.py` survey).
- **Part 2 — inferring production strategy from Cube_CES delivery timing: reasoned inference,
  not fact, moderate confidence on the classification, high confidence on the underlying
  statistics.** Interval = ActualDelDate - CtrDate, Status='Actual', PEM101/Omni Channel,
  CtrDate >= 2023-01-01 (reusing the existing Cube_CES pull). 35,930 valid observations (17 rows,
  0.05%, excluded for a negative-interval anomaly, same class as previously documented). Bands
  used (own reasoned judgment, stated explicitly): Likely MTS <= 14 days; Likely MTO 30-75 days
  (brackets the stated 45-60 day default with a +/-15 day buffer); else Cannot determine
  (including when IQR exceeds the median, i.e. spread as large as the central value).
  **Result: 32 items (25.0%, ₿348.5M/50.5% of scope value) Likely MTS; ZERO items (0.0%) Likely
  MTO; 92 items (71.9%, ₿337.3M/48.9% of value, plus the remaining no-value items) Cannot
  Determine.** MTS items' median interval is 2-11 days. **No item lands confidently in the
  make-to-order band** - this reinforces, at item level, the project's existing finding that
  customer notice (median 6 days) is far too short to produce against, so even nominally-MTO
  items are in practice delivered fast. Stated explicitly per instruction: this is inference from
  delivery timing, not a recorded fact - the data cannot confirm WHY a delivery was fast or slow.
- **Part 3 — warehouse structure: transfers CONFIRMED, business-unit mapping CANNOT be
  determined, high confidence on both conclusions.** No warehouse master/lookup table exists
  anywhere in the database (0 tables named like `%warehouse%`) - codes are only ever a short
  string on inventory/transaction rows. 34 distinct warehouse codes hold the 128-item scope in
  the current `Cube_Inventory_Exact` snapshot (76 table-wide). **Business unit mapping: no
  reliable answer exists.** `company` has only 2 values table-wide (PEM, CI) - too coarse.
  Joining warehouse to sales `division` (table-wide) shows 33 of 34 codes used across MULTIPLE
  divisions, even codes whose numeric suffix visually resembles a division (e.g. `F101` mostly
  PEM101 but also PPD101/PEM102-OLD/PCE101/PTS) - though this test is itself confounded by the
  project's already-documented itemcode-reuse-across-division issue, so it is not fully
  decisive either way; no positive evidence of a clean mapping was found regardless. **Where
  items are held**: 125/128 items appear in the snapshot; 119 of those 125 (95.2%) are held in
  MORE THAN ONE warehouse (median 7, max 20) - multi-warehouse stocking is the norm, matching
  the earlier groundwork survey's min/max-per-warehouse finding. **Stock transfers: CONFIRMED,
  decisively.** `cube_inventory_tran`'s `transtype` codes 150/151 behave as an exact
  transfer-out/transfer-in pair (150 = 100% QtyOut-only, 151 = 100% QtyIn-only, table-wide).
  1,572 matched (item, order reference, date) groups, **100% with an EXACT quantity match**
  between the paired rows - decisive, not coincidental. Spans 2016-09-12 to 2026-08-28 (present
  day). Dominant route: QA -> WH01 -> FG01 -> FG02 (quality hold -> main warehouse -> finished-
  goods branches). Coverage caveat: `cube_inventory_tran` covers only 34/128 items at all, and
  only 6 of those 34 show a confirmed transfer - a lower bound, not proof the rest never
  transfer. **Practical conclusion: warehouses cannot be treated as fully independent for
  planning - goods routinely move between them.**
- **Part 4 — actual lead time vs. the stated 45-60 day default: observed reality is far faster
  for nearly all items, high confidence in the measurement, explicit scope caveat on what it
  means.** Same 35,930 observations as Part 2. **108 of 112 items with data (96.4%) are FASTER
  than 45 days; only 2 (1.8%) fall within 45-60 days; 2 (1.8%) are slower.** Overall
  median-of-item-medians is 6.0 days (p10=2, p25=3, p75=8, p90=19.3, max=196). At product-type
  level, all 8 types have a median faster than 45 days (range 3-9 days); none exceed 60.
  **Spread is large**: item-level IQR ranges 0-305 days; 67 of 112 items (59.8%) have an IQR
  LARGER than their own median - the spread is at least as big as the typical value for a
  majority of items, so a single point lead-time estimate would understate real variability for
  most of this scope. **Explicit scope caveat**: this measures order-to-delivery time (PO
  received to delivered), NOT procurement or production lead time. Since most orders are filled
  from stock (Part 2), this measure mostly reflects allocation/logistics speed for those orders
  and likely UNDERSTATES true production/procurement lead time for items rarely actually
  produced-to-order in this window; for the few genuinely slow items it cannot say how much of
  the delay was production vs. an unrelated cause (no cause field exists). It is a useful
  cross-check on the stated default, not a replacement for a purchasing/production-confirmed
  figure.
- **Part 5 — order quantity patterns: suggestive lot-size/MOQ evidence, moderate confidence,
  not proof.** 82 of 112 items with any 2024+ sales have >=10 orders (the minimum treated as
  meaningful). 40 of 82 (48.8%) have a single quantity value covering >=25% of that item's
  orders; 53 of 82 (64.6%) have >=80% of orders landing on an exact multiple of some number >1;
  68 of 82 (82.9%) show EITHER signal, 14 (17.1%) show neither. Recurring values: **3** is
  extremely common (many Fuse Cutout/Surge Arrester items order overwhelmingly in 3s or
  multiples of 3); **10** is a common base multiple for larger-volume items (orders commonly
  100/200/500). By product type, 5 of 8 types show a strong signal in >=80% of their items.
  **Not strong enough to set an actual lot size/MOQ value for any item from data alone** - round
  quantities could reflect a real production/purchasing constraint OR customer ordering habit
  (buying in round tens); the data cannot distinguish these. Must be confirmed by the business.
- **What the data could not resolve**: why 92 of 128 items (72%) cannot be classified MTS/MTO
  from delivery timing (insufficient or too-inconsistent observed deliveries, not a fixable
  data-quality defect); the true meaning of several low-volume warehouse codes (`CL`, `AST`,
  `NCRM`, `F-RD`) - read from abbreviation/usage pattern only, not documented anywhere; whether
  round order quantities reflect a genuine constraint or customer habit; which warehouse(s)
  should count toward each item's inventory policy (carried over from the earlier Phase 4
  groundwork survey, still open).
- **Updated Phase 4 missing-data picture (see Section 6 below)**: lead time and MOQ/lot size
  still must come from the business - this task could only produce indirect, partial,
  non-authoritative cross-checks for both, not the figures themselves. Make-vs-buy and
  warehouse-to-business-unit ownership are similarly still not answerable from data.

**Warehouse flow, stage dwell time, sellable stock, and double-counting verification — DONE
(2026-09-02).** INVESTIGATION ONLY, per instruction: no min/max calculated, no model built,
`config/config.yaml` not touched. Follow-up to the same-day Phase 4 prep investigation above,
after the user corrected two assumptions: **(1) the 45-60 day figure is upstream parts
procurement time (ordering parts for assembly), not delivery time** — this is why observed
order-to-delivery time is much shorter, since customer orders are filled from stock already
held; **(2) warehouses are STAGES of one process (inspection -> storage -> ready to ship), not
separate locations or business units** — summing a per-warehouse min/max would double-count the
same goods moving through stages; planning must be at item level across all warehouses combined,
distinguishing which stages hold sellable stock. Scripts:
`src/warehouse_flow_mapping.py` (Part 1), `src/warehouse_dwell_time.py` (Part 2),
`src/warehouse_sellable_stock.py` (Part 3), `src/warehouse_double_counting_check.py` (Part 4).
Full detail: `output/summary/phase4_warehouse_flow_investigation_report.md`; CSVs
`output/summary/part1_all_transfer_routes.csv` through `part4_conservation_check.csv`.

- **Critical scope limitation, applies to Parts 1/2/4**: `cube_inventory_tran` (the only movement
  ledger in the database) covers 34/128 items at all, and of those, only **6 show any confirmed
  transfer — all 6 are the Raw Material Fuse Holder codes** (`FC-A-27-00102/00202/00203`,
  `FC-A-38-00102/00202/00203`), not Finished Goods. **Every finding on warehouse flow, stage
  dwell time, and transfer-based double-counting is evidenced ONLY for these 6 items (4.7% of
  the 128-item scope) and cannot be confirmed to hold for the 122 Finished Goods items that carry
  the great majority of this project's value.**
- **Part 1 — full flow map, high confidence within the 6-item scope.** All 41 observed routes
  reported (not just the dominant path) in `part1_all_transfer_routes.csv`. **Movement is
  predominantly forward but NOT strictly one-way**: 10 of 31 warehouse pairs show CONFIRMED
  bidirectional movement at meaningful volume (e.g. WH01->QA = 96,450 units, 21% of the QA->WH01
  direction) — not just the dominant QA->WH01->FG01->FG02 path. 14 of 34 warehouse codes present
  in the current snapshot have movement evidence and could be assigned a role; **20 have ZERO
  movement evidence and are listed UNIDENTIFIED, per instruction — no role assigned by inference
  from the name** (`AST`, `F-RD`, `F103`, `F106`, `F107`, `F109`, `F2-2`, `FG03`, `FG12`, `FG16`,
  `FG17`, `FG23`, `FG24`, `NCRM`, `W4-1`, `WH04`, `WH05`, `WH06`, `WH07`, `WH24`) — most likely
  the ledger's narrow coverage, not proof of inactivity.
- **Part 2 — stage dwell time, moderate confidence on the 6-item numbers, cannot generalise to
  FG.** FIFO lot-matching (standard aging technique, stated explicitly as a method, not a
  recorded fact): median dwell QA=4 days, WH01=37, WH21=58, FG01=27, FG02=~0, CL=8 (full table
  `part2_stage_dwell_time.csv`). **Total system time (first receipt to eventual issue-to-
  production), pooled: median 42 days, mean 69.3, IQR [24,90], range [0,962]** — per-item medians
  range from 34 to 650 days, huge variability. **What this adds to the 45-60 day procurement
  default**: median +42 days of internal handling AFTER procurement, BEFORE any assembly time —
  variability this large means a single point figure would badly understate real total lead
  time. **Hard gap, stated explicitly**: the ledger's exit event (issue to a production job,
  confirmed from descriptions like "Production: DF16/001LOT2.001") is NOT a sale — the
  assembly-time segment from raw-material consumption to the resulting Finished Good becoming
  stock is not observable anywhere in this data. **The full chain the user asked for (procurement
  + internal handling + assembly = total lead time to sellable) cannot be completed from data —
  the assembly segment is a hard, unrecoverable gap, not a matter of writing a different query.**
- **Part 3 — which stock is sellable: high confidence this cannot be directly measured, and a
  self-caught methodology error corrected before reporting.** Neither `cube_Sale_APD` nor
  `Cube_CES` has a warehouse column (checked directly) — no sales record can ever be tied to the
  warehouse it shipped from, for any item. **An initial classification pass wrongly flagged every
  code with zero issue-events among the 6 RM items (including FG01/FG11/FG21) as "not
  available"** — caught and corrected: those 6 items hold almost none of FG01's stock (144,094
  units across the full 128-item scope), so the ledger's silence there proves nothing about the
  Finished Goods sitting there. **Only 2 exclusions are actually justified: `QA`** (567,306 units
  handled, only 22 — 0.004% — ever issued externally, a pass-through inspection gate matching the
  business's own description) **and `FMTS`/`FMTO`** (evidenced broadly across 74/103 of 128
  items — negligible settled stock, large `tobe_received`, production WIP). **Confirmed NOT
  available: QA, FMTS, FMTO — 1,639 of 179,135 total on-hand units (0.91%). The remaining 99.09%
  sits in warehouses where availability CANNOT be confirmed either way** — not the same as
  calling it sellable. Whether FG01/FG02/FG11/FG21 hold genuinely sellable Finished Goods stock
  is plausible from topology (Part 1) but **not confirmed by behaviour — must come from the
  business.**
- **Part 4 — no-double-counting conclusion: CONFIRMED, high confidence for the 6-item scope.**
  All 1,572 transfer groups have exactly 2 legs and an exact quantity match (re-confirmed); each
  pair shares one order-reference document (a single business event, not two independent
  stock-creation events); 3 harmless same-warehouse self-transfers found (net zero, flagged not
  investigated further). **New aggregate conservation check**: (total received - total issued)
  matches current on-hand stock EXACTLY for 2 of 6 items, within 1.5% for the other 4, with no
  systematic over-recovery in any consistent direction (the opposite of what duplication would
  produce). The 8 previously-flagged itemcode/category-collision items hold only 6 units total,
  spread across ordinary codes — negligible, no warehouse exclusion warranted on that basis.
  **Item-level planning summed across all warehouses is CONFIRMED CORRECT; no warehouse should
  be excluded from the total on data-quality grounds** (though FMTS/FMTO should be reported
  separately as work-in-progress, not available stock, per Part 3). Directly verified only for
  the 6-item subset; the same structural/conceptual argument extends to the rest of the scope
  but is not independently ledger-tested there, since no ledger covers those items.
- **What the data could not resolve**: assembly/production time from raw-material issue to the
  resulting Finished Good becoming stock (a hard, unrecoverable gap — no field links these
  events); which warehouse stage(s) hold sellable Finished Goods stock, confirmed by behaviour
  rather than topology (needs business/operations input); the true meaning/role of the 20
  unidentified warehouse codes.

## 3. Business Findings

These describe how this business actually operates, established from data investigation (not
assumption) during Phase 1.5 and the Phase 3.1 follow-on tasks. They shape every downstream
phase, particularly Phase 4. Full methodology, confidence levels and caveats are in the
"Combination-variant test, order-notice lead time, on-time delivery baseline" and
"Stock-availability hypothesis investigation" entries above.

- **Customers give almost no order notice.** Median notice is 6 days; only 5.9% of orders give
  a month or more. This is far too short to produce or procure against — orders can only be
  filled from stock already held.
- **On-time delivery has improved but is not yet good.** 73.2% on-time in 2026 (partial year),
  up from 57.8% in 2023. 8.8% of deliveries are late, with a median lateness of 2 days.
- **Late deliveries are not, in the main, an order-timing problem.** 69.5% of late deliveries
  had adequate notice (at or above the overall median) and were still late — pointing to
  supply/stock availability rather than customers ordering too close to the delivery date.
- **Late rates stay elevated for 1-2 months after an item's own demand spike** (10.78% vs.
  8.56% baseline, p=0.011) — the clearest available signal of stock being drawn down by a
  spike and not replenished in time.
- **Roughly 35-65% of late deliveries could plausibly be prevented by stock availability** —
  stated as a range, not a point estimate, because this is inferred from correlational
  evidence (order size, spike timing, item-mix effects), not measured directly: no historical
  stock-level time series exists in the database.

## 4. Locked Decisions (with reasons)

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
- **Focus item codes are `EEE-F-FC-1040010002`, `HS-F-99-02110` and `HS-F-99-0213`, and remain
  the focus codes throughout every phase (A-F), not just the pilot.** All three were confirmed
  present in the pricelist. **Confirmed sufficient (2026-08-31)**: they cover two distinct
  demand patterns found in Phase 2 Step 1 — one Erratic item (`EEE-F-FC-1040010002`) that
  dominates its type at ~60% of its type's total sales value, and two Lumpy items
  (`HS-F-99-02110`, `HS-F-99-0213`) sitting mid-rank (9th and 11th of 58) in their type,
  representative of the bulk of that group. **Reaffirmed 2026-09-02**: any item-level check,
  backtest, or worked example in Phase A onward should use these three codes first, before
  generalising to the wider scope.
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
- **Follow the phase order; do not skip ahead (2026-09-02).** Later phases consume the outputs
  of earlier ones — calculating inventory parameters (Phase 4) before forecasting is complete
  and stable across all SKUs (Phase 3.1) would mean rebuilding Phase 4 on a changed foundation.
  **Phase 3.1 must complete before Phase 4 begins.**
- **The existing min/max values in the inventory system cannot be used as inputs to any
  calculation (2026-09-02).** Evidence: 46 of 128 items have no setting at all; settings range
  from under 1 month to over 1,700 months of cover; 81 of 119 multi-warehouse items disagree
  across warehouses; 7 items carry a setting despite having no sales. They may be used only as
  a comparison baseline to show what would change under a new policy. There is currently no
  systematic inventory planning system — that is what Phase 4 will create.
- **The stated 45-60 day lead time is upstream parts-procurement time, not delivery time
  (business correction, 2026-09-02).** This is why observed order-to-delivery time (median 6
  days, measured 2026-09-02) is much shorter than the stated default — customer orders are
  filled from stock already held, not produced/procured against per order. True total lead time
  to a sellable Finished Good = procurement (45-60 days, business figure) + internal
  handling/staging time after receipt (median +42 days for the 6 raw-material items with any
  movement evidence, highly variable, see the warehouse-flow investigation) + assembly time
  (not observable in any data source — a hard gap). **Phase 4 must use a total lead time built
  from all three segments, not the 45-60 day procurement figure alone**, and the assembly
  segment must come from the business since no data links raw-material consumption to a
  resulting Finished Good becoming stock.
- **Warehouses are STAGES of one process, not separate locations or business units (business
  correction, 2026-09-02).** Confirmed by data: goods transfer between warehouse codes (1,572
  exact-quantity-matched transfers), predominantly forward (inspection -> storage -> downstream
  stocking) but with genuine bidirectional movement too. **Phase 4 will therefore plan inventory
  at ITEM LEVEL across all warehouses combined, never per warehouse** — summing independently-
  sized per-warehouse min/max would double-count the same goods as they move through stages.
  This was verified, not just assumed: transfer-pair quantities match exactly, each pair ties to
  one order-reference document, and aggregate received-minus-issued reconciles with current
  on-hand stock (exact for 2 of 6 tested items, within 1.5% for the rest) — the signature of
  sequential movement, not duplication. Within the item-level total, **only `QA` (inspection)
  and `FMTS`/`FMTO` (production work-in-progress) are confirmed NOT yet available for use** (0.91%
  of current on-hand stock); which of the remaining warehouse codes hold genuinely SELLABLE
  Finished Goods stock could not be confirmed from data (no sales table has a warehouse field)
  and must be confirmed by the business.

## 5. Open Questions

- **Rule-based selection's sufficiency-gate design (found 2026-09-01)** — unresolved,
  non-blocking. Our 24-month hard-cutoff gate (Naive below it) erases the classification
  stability advantage that the underlying SBC/KH/PK rules otherwise show — a smoother/rolling
  confidence check might preserve it, not attempted here. Also unresolved: whether the
  Smooth-quadrant SES/Holt generalisation (our own addition) should be scoped more narrowly to
  match Petropoulos & Kourentzes' literal ADI≤1 condition instead. See the Phase 3.1 rule-based
  selection note above.
- **Phase 4 groundwork gaps (found 2026-08-31)** — unresolved, non-blocking for now. Which
  warehouse(s) should count toward each item's Max-Min policy (min/max genuinely differ by
  warehouse for the same item); the `cube_inventory_tran` GL-classification conflict (28 of 34
  covered items show `gl_desc='Raw materials'` there despite being Finished Goods everywhere
  else); whether any of the 128 items are genuinely make-or-buy dual-sourced; whether the 8
  itemcode/category-mismatched items in `Cube_Inventory_Exact` (Suspension Insulator, Power
  Capacitor labels on Fuse/Surge Arrester codes) are itemcode collision or a data-entry error;
  whether a real seasonal pattern exists (only 2 complete years available — cannot be settled
  without more history). See the Phase 4 groundwork survey note above for full detail.
- **Which model to use per Category/Type (found 2026-08-31)** — unresolved, non-blocking for
  now. None of the 10 Category/Type series had a stable rolling-origin winner (0/10), so no
  single model choice is currently evidenced as reliable enough to lock in. Would need either
  more history (more origins to test stability against) or a different evaluation design
  (e.g. ensembling) before a production choice is defensible. See the Phase 3.1 note above.
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

## 6. Missing Data by Phase

- **Phase 2 and 3.1 (item-level pilot)**: needed nothing beyond the sales data already
  available.
- **Phase 3.2**: needs utility budget data from PEA, MEA and EGAT, EGP bid announcements, and
  sales team insight. Collection format not yet agreed.
- **Phase 4**: must be requested externally — none of the following exist in the database as an
  authoritative, item-level figure (updated 2026-09-02 after the warehouse-flow follow-up
  investigation, which corrected two earlier assumptions — see Locked Decisions above — and
  RESOLVED the planning-unit question below):
  - **Confirmed procurement lead time per item, from purchasing.** The stated 45-60 days is the
    business's own figure for ordering parts, not something this project can derive or verify
    end-to-end from data. Still needed as the authoritative starting segment of total lead time.
  - **Assembly/production time, from raw-material issue to the resulting Finished Good becoming
    stock.** Confirmed a HARD gap (2026-09-02): no field in any table links a raw-material
    consumption event to the resulting assembled item later becoming stock. Cannot be derived
    from data under any query design — must come from production/the business.
  - **Minimum order quantities and lot sizes.** No field states these directly. 68 of 82
    testable items show quantity-clustering evidence consistent with a lot size (2026-09-02
    prep investigation) — suggestive, not sufficient to set a value.
  - **Make-versus-buy classification per item.** FG/RM split is known with high confidence
    (122/128 FG, 6/128 RM, earlier Phase 4 groundwork survey); whether any FG item is genuinely
    dual-sourced (made in-house AND sometimes bought complete) remains unanswerable from data.
  - **Target service level.** No data source addresses this at all.
  - ~~Whether stock is planned per warehouse, per business unit, or company-wide~~ —
    **RESOLVED 2026-09-02 by business correction, confirmed by data.** Warehouses are process
    stages, not business units or independent planning locations. Phase 4 plans at ITEM LEVEL
    across all warehouses combined; confirmed transfers between warehouses mean a per-warehouse
    model would double-count. Which specific stage(s) hold sellable Finished Goods stock (as
    opposed to `QA`/`FMTS`/`FMTO`, confirmed not-yet-available) still needs business
    confirmation — no sales table has a warehouse field to verify this from data.

## 7. Red Team Review Findings (2026-09-02)

Weaknesses identified in a red-team review of the project, recorded here so they are not lost.
None of these are resolved by this entry — they are the reason Phases A, B and F exist in the
revised plan (Section 1/2 above), and Phase F in particular exists specifically to answer the
last two points.

- **Aggregating quantities across different products within a category has no physical
  meaning.** Summing, for instance, fuse cutouts and fuse links into one Category-level series
  adds together units of different physical products — the resulting number does not correspond
  to anything a person could count. Part of the apparent benefit of aggregation (the
  zero-inflation and overfitting-gap reduction reported for Category/Type level in Phase 2) may
  be an artifact of summing many series together — a well-known statistical smoothing effect —
  rather than evidence the aggregated series is itself meaningful for planning. This is the
  reason Phase B exists: to design how Category/Type results actually support item-level
  forecasting, rather than treating the aggregate result as an end in itself.
- **Cross-division demand is filtered out while inventory is shared.** ₿60.6 million (14.3%) of
  sales for the pilot item codes sits under divisions other than PEM101 and is currently excluded
  from every forecast, even though inventory is not divided by division — the same physical stock
  can fill an order recorded under any division. Excluding this demand systematically
  under-provisions. Carried into Phase B as an open item to resolve, not yet fixed.
- **No cost data exists.** Holding cost, stockout cost and unit cost are all absent from every
  table surveyed so far. Without them, a target service level cannot be chosen on an economic
  basis (the trade-off between holding more stock and risking a stockout has no cost basis to
  optimise against) — it can only be picked as a policy choice, not derived from data.
- **The project has never been compared against the team's current working method.** Every
  result so far (model accuracy, bias, on-time delivery) is reported in isolation; none of it has
  been measured against what the team already does without this project. Its value is therefore
  unproven, not just unquantified. This is what Phase F is for.
- **The problem may be smaller than assumed, and is already improving without intervention.**
  On-time delivery rose from 57.8% to 73.2% (2023 to 2026, partial year) with no forecasting or
  inventory system in place. Phase F must estimate what a no-intervention baseline looks like
  going forward, since some or all of the apparent opportunity may already be closing on its own.

---

**Rule: this file must be updated as the final step of every completed task.**
