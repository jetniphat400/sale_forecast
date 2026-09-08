# Phase D — Check 2: Value Tied Up in Stock

**Role**: Explorer (`AGENTS.md`). Reports what queries return; does not decide which cost basis,
holding-cost rate, or business action to adopt — that is for the Synthesizer/Orchestrator/business.

**Scope (binding, per task instructions)**: only `[salewarehouse].[dbo].[Cube_Inventory_Exact]`
(current stock quantity) joined to `[salewarehouse].[dbo].[cube_Sale_APD]` (`cost` column) was
queried. No other table was searched.

**Script**: `src/investigations/phaseD_check2_stock_value.py` (run 2026-09-08; live-table
snapshot, not reproducible byte-for-byte on a re-run — see "Caveats" below).

**Inputs read** (not queried, already produced by Phase C): `output/summary/
phaseC_step1revised_item_status_445.csv` (445-item status classification), `output/data/
processed_all_divisions_monthly_qty.csv` (335 forecast-status items, monthly qty, 2024-01 to
2026-07).

---

## 0. Headline finding, load-bearing — `cost` is a LINE TOTAL, not a unit cost

The task brief describes `cube_Sale_APD.cost` as a unit-cost column. **Directly checked before
computing anything and found to be wrong.** Evidence (confirmed, not inferred):

- Item `EEE-F-FC-1040010002`, six rows on 2026-09-07: qty = 2, 21, 45, 60, 70, 100 with
  `cost` = 3,094.36 / 32,490.78 / 69,623.10 / 92,830.80 / 108,302.60 / 154,718.00. `cost / qty`
  equals **1,547.18 exactly** in every one of the six rows.
- Broader check: of 51,059 whole-table rows with qty≠0 and cost non-null, 747 items had ≥5 rows;
  the median within-item coefficient of variation of `cost/qty` across those items is **0.108** —
  consistent with a per-unit price that drifts slowly over calendar time (real cost changes), not
  with `cost` already being a stable unit price.
- Confirmed again on the 343-item project scope: 263 items had ≥5 usable rows; median within-item
  CV of `cost/qty` = **0.061**.

**Conclusion (high confidence, directly evidenced): every unit cost in this report is derived as
`cost / qty` per row, then aggregated. Using the raw `cost` column as a unit price, as the task
wording implied, would have overstated stock value by roughly one to two orders of magnitude for
any high-qty transaction line.** This is reported as a finding, not silently corrected without
comment — flagging it for whoever owns the task-brief wording, since "unit cost" was stated as if
already confirmed.

`qty` was never 0 or null on any of the 37,171 pulled rows, so this derivation is defined for
every row used.

---

## 1. Method implemented

- **Stock quantity**: `SUM(stock)` from `Cube_Inventory_Exact`, grouped by `itemcode`, **across
  ALL warehouse codes** — no warehouse excluded. This is deliberately the total-capital-tied-up
  figure, not the sellable-stock figure (Check 1's separate job). Items with zero rows in
  `Cube_Inventory_Exact` are recorded as qty = 0 (confirmed absence of any row, not a data gap).
- **Unit cost basis chosen: median unit cost over the last 12 months of available data**
  (`cube_Sale_APD` rows with `createDate` in the 12 months ending at the table's global max
  `createDate`, 2026-09-07 at pull time → window start 2025-09-07). **Reasoning**: this project's
  own history has repeatedly found isolated one-off/outlier rows in `cube_Sale_APD`-family tables
  (e.g. large-order and duplicate-row investigations logged in `STATUS.md`); a median is robust to
  a single unusually large or small transaction, whereas the most-recent single row is not. The
  most-recent-transaction unit cost is computed alongside for every item as the required sanity
  companion (see §3).
- **Fallback (flagged, never silent)**: 56 of 343 priced items have cost history but **no** row in
  the last 12 months — for those, the most-recent-transaction cost is used instead, and every such
  row is labelled `most_recent_transaction (FALLBACK — no cost row in last 12mo)` in
  `phaseD_check2_item_stock_value.csv`'s `primary_basis` column, so it is never mistaken for the
  primary basis.
- Ties on the max `createDate` (59 of 343 items had >1 row on their own max date) were resolved by
  averaging the derived unit costs of the tied rows.

---

## 2. Items with stock but NO cost record at all

**5 of 445 items** have `stock_qty_all_warehouses > 0` in `Cube_Inventory_Exact` but **zero rows**
in `cube_Sale_APD` (checked table-wide, not window-restricted — no item in this scope had rows
with a null `cost`, so "0 rows with non-null cost" and "0 rows at all" are the same condition
here, confirmed directly: 0 null-cost rows across all 37,171 pulled rows).

| itemcode | category | type | division | status_category | stock qty (all warehouses) |
|---|---|---|---|---|---|
| FC-A-38-00203 | Fuse | Fuse Holder | PEM101 | placeholder – method already assigned | 150.0 |
| IS-F-99-0365CE1 | Suspension Insulator | Suspension Insulator | PEM101 | placeholder – pending method | 62.0 |
| HS-F-99-3121 | Surge Arrester | Medium Voltage Surge Arrester | PEM101 | placeholder – method already assigned | 12.0 |
| 02-05-R-0001 | FRTU | FRTU | PEM102 | placeholder – pending method | 1.0 |
| TF-F-99-3107223B1 | Distribution Transformer | 3 Phase Distribution Transformer | PEM103 | placeholder – pending method | 1.0 |

**Total 226 units, value undetermined — NOT assigned a cost of 0 and NOT dropped from any total.**
These 226 units are reported separately in every rollup CSV as
`unpriced_stock_qty_value_undetermined`. Source: `output/summary/phaseD_check2_stock_no_cost_items.csv`.

(102 of 445 items have no cost record at all, but the other 97 also have zero current stock, so
they contribute nothing to the "value undetermined" total — only the 5 above have both conditions
at once.)

---

## 3. Cost basis sanity comparison — median-12mo vs. most-recent-transaction

- Of 287 items with **both** bases computable: **22 (7.7%) differ by more than 20%** (relative to
  the larger value). Full list: `phaseD_check2_item_stock_value.csv`, columns
  `cost_basis_relative_diff` / `cost_basis_material_diff`.
- Most of those 22 have **zero current stock**, so the difference does not move any stock-value
  total. Two exceptions with stock: `VT-F-99-010715` (2 units, 32.7% diff) and `VT-F-99-010721`
  (17 units, 30.2% diff).
- **Aggregate sensitivity**: total priced stock value is **THB 37,399,005** under the chosen
  median-12mo basis vs. **THB 39,495,341** if every item used its most-recent-transaction cost
  instead — a **5.6% higher** total under the alternative basis. Not a material swing at the
  portfolio level.
- **Top-10 list sensitivity**: the top-10 set is *almost* identical under either basis, with one
  marginal swap: under the most-recent basis, `VT-F-99-010203` (value 895,460) would enter the
  top 10 in place of `LS-F-99-1004` (median-basis value 838,365 vs. its own most-recent-basis
  value 887,598 — `LS-F-99-1004` stays close either way, `VT-F-99-010203` moves from 691,887
  under median to 895,460 under most-recent, a 29% swing driven by its own cost history, not by
  stock quantity). Reported so the choice of basis is not treated as inconsequential at the
  margin, even though it barely moves the portfolio total.

---

## 4. Top 10 items by stock value (primary basis: median-12mo, fallback where flagged)

Source: `output/summary/phaseD_check2_top10_value_items.csv`. Months of cover =
`stock_qty_all_warehouses / mean_monthly_qty_2024_01_to_2026_07`, using the mean monthly qty over
`processed_all_divisions_monthly_qty.csv`'s full window (2024-01 to 2026-07, 31 months) — chosen
because no single "the forecast" file exists yet for all 335 items' future demand in one place
(per the task instructions). All 10 of these items are `forecast`-status, so months of cover is
computable for all of them.

| # | itemcode | type | division | stock qty | unit cost (basis) | stock value (THB) | mean monthly qty (24-01..26-07) | months of cover |
|---|---|---|---|---|---|---|---|---|
| 1 | FC-A-38-00202 | Fuse Holder | PEM101 | 4,996 | 452.84 (median-12mo) | 2,262,388.64 | 3.06 | 1,630.3 |
| 2 | TF-F-99-12044211AF1 | 3 Phase Distribution Transformer | PEM103 | 12 | 120,580.54 (median-12mo) | 1,446,966.48 | 3.26 | 3.7 |
| 3 | HS-F-99-0303 | Medium Voltage Surge Arrester | PEM101 | 564 | 1,970.00 (median-12mo) | 1,111,080.00 | 19.03 | 29.6 |
| 4 | TF-F-99-19044211Q1 | 3 Phase Distribution Transformer | PEM103 | 5 | 206,762.13 (median-12mo) | 1,033,810.63 | 13.32 | 0.4 |
| 5 | TF-F-99-10044211Q1 | 3 Phase Distribution Transformer | PEM103 | 12 | 81,134.04 (median-12mo) | 973,608.42 | 2.84 | 4.2 |
| 6 | TF-F-99-10074211Q1 | 3 Phase Distribution Transformer | PEM103 | 11 | 84,526.95 (most-recent, FALLBACK) | 929,796.45 | 1.32 | 8.3 |
| 7 | TF-F-99-15074211Q1 | 3 Phase Distribution Transformer | PEM103 | 6 | 154,217.39 (most-recent, FALLBACK) | 925,304.34 | 0.03 | 186.0 |
| 8 | TF-F-99-0704811AG1 | 1 Phase Distribution Transformer | PEM103 | 19 | 46,819.02 (median-12mo) | 889,561.38 | 18.90 | 1.0 |
| 9 | HS-F-99-02410 | Medium Voltage Surge Arrester | PEM101 | 1,260 | 669.45 (median-12mo) | 843,507.00 | 0.03 | 39,060.0 |
| 10 | LS-F-99-1004 | Low Voltage Surge Arrester | PEM101 | 7,729 | 108.47 (median-12mo) | 838,364.63 | 7,654.48 | 1.0 |

**Observed (factual, not interpreted)**: two of the top-10 items (`FC-A-38-00202`, `HS-F-99-02410`)
carry very large stock relative to near-zero mean monthly demand (months of cover in the
thousands to tens of thousands) — both a large capital figure and a very slow-moving item by this
demand basis. This is a description of what the two figures show side by side, not a
recommendation.

---

## 5. Rollups

### Per Type
`output/summary/phaseD_check2_rollup_by_type.csv` — 47 types (including "(Unclassified — no
Product Type in pricelist)" for 8 codes with a null Product Type). Highest priced-value types:
3 Phase Distribution Transformer (THB 8,742,720 across 46 priced items), Medium Voltage Surge
Arrester (THB 4,802,585), Fuse Holder (THB 4,326,544), High Voltage Distribution Fuse link
(THB 3,042,525).

### Per Division
`output/summary/phaseD_check2_rollup_by_division.csv`:

| division | items | items w/ stock>0 | total stock qty | items priced | priced stock value (THB) | unpriced qty (value undetermined) |
|---|---|---|---|---|---|---|
| PEM101 | 171 | 98 | 157,179 | 147 | 20,296,313 | 224 |
| PEM103 | 87 | 16 | 95 | 50 | 10,298,558 | 1 |
| PEM107 | 136 | 35 | 796 | 112 | 5,288,361 | 0 |
| CI101 | 13 | 6 | 54 | 13 | 755,334 | 0 |
| PEM102 | 26 | 3 | 4 | 16 | 570,425 | 1 |
| PEM104 | 12 | 1 | 2 | 5 | 190,008 | 0 |

**Total priced stock value across all 445 items: THB 37,399,005.48.** Total unpriced stock
(no cost record, value undetermined): 226 units (§2). **PEM101 holds 99.4% of all on-hand stock
units (157,179 of 158,130 total units across the 445-item scope) and 54.3% of priced stock value**
— both confirmed directly from the rollup CSV, stated as observation only.

---

## 6. Value with NO forecast basis (`status_category` ≠ `forecast`)

Source: `output/summary/phaseD_check2_no_forecast_value_breakdown.csv`. This is stock that
currently has no demand basis to plan against — reported as its own total, broken out by
`status_category` (definitions: `output/summary/phaseC_step1revised_item_status_445.csv`).

| status_category | items | items w/ stock>0 | total stock qty | items priced | priced stock value (THB) | unpriced qty (undetermined) |
|---|---|---|---|---|---|---|
| excluded – division excluded from forecasting (data volume) | 12 | 1 | 2 | 5 | 190,008.00 | 0 |
| excluded – listed but never sold, no plan-against basis | 6 | 0 | 0 | 0 | 0.00 | 0 |
| placeholder – method already assigned | 10 | 2 | 162 | 1 | 0.00 | 162 |
| placeholder – pending method | 82 | 4 | 69 | 2 | 36,441.90 | 64 |
| **Total, no-forecast scope** | **110** | **7** | **233** | **8** | **226,449.90** | **226** |

**No-forecast-basis stock value: THB 226,449.90 priced + 226 units value-undetermined**, out of
the project-wide total THB 37,399,005.48 — **0.61% of total priced stock value** sits in items
with no forecast to plan demand against. Confirmed directly by merging `Cube_Inventory_Exact` +
`cube_Sale_APD` figures against `phaseC_step1revised_item_status_445.csv`'s `status_category`.

Note: `unpriced_stock_qty_value_undetermined` for "placeholder – method already assigned" (162
units) and "placeholder – pending method" (64 of 69 units) overlaps entirely with the 5-item
no-cost-record list in §2 — those 5 items are themselves non-forecast-status items (see the
`status_category` column in §2's table), so the value-undetermined stock is concentrated
specifically in the no-forecast scope, not spread across forecast items.

---

## 7. Explicit framing (per task instructions)

**This is capital tied up (a point-in-time value from a single current-stock snapshot), NOT an
annual carrying cost.** No annual holding-cost rate exists anywhere in this data. The 15-25%
figure referenced elsewhere in `STATUS.md`/`CONVENTIONS.md` is explicitly flagged there as an
unverified, uncited assumption, not a fact — it is not used anywhere in this script or report. An
annual carrying-cost rate must be set as a configurable assumption in Phase E, not derived here.

---

## 8. Confidence levels

| Conclusion | Confidence | Evidence |
|---|---|---|
| `cost` is a line-total, not a unit cost | High — directly confirmed, reproducible from raw rows (§0) | `_diagnose_cost_is_line_total`, run against live data |
| Stock quantity per item (all warehouses) | High — direct `SUM(stock)` from `Cube_Inventory_Exact`, verified row counts logged | `phaseD_check2_item_stock_value.csv` |
| Median-12mo primary cost basis is more robust than most-recent alone | Medium — reasoned from this project's documented history of outlier rows, not statistically proven for this specific item set beyond the CV figures above | STATUS.md prior investigations; §3 comparison |
| Total priced stock value (THB 37.40M) | High — directly recomputed, verified: item-level sum = type rollup sum = division rollup sum (script's Step 8 assertions, all passed) | `phaseD_check2_item_stock_value.csv`, `_rollup_by_type.csv`, `_rollup_by_division.csv` |
| No-forecast-scope value (THB 226,450 priced + 226 units undetermined) | High — direct merge against Phase C's own closed classification file | `phaseD_check2_no_forecast_value_breakdown.csv` |
| 5 items with stock but no cost record | High — directly queried, 0 null-cost rows found table-wide so the two possible definitions coincide | `phaseD_check2_stock_no_cost_items.csv` |
| Top-10 list and its months-of-cover figures | High for the stock/value/demand-basis arithmetic; Medium for "months of cover" as a planning number, since the demand basis is a simple historical mean, not a forecast model output (stated explicitly, per task instructions) | `phaseD_check2_top10_value_items.csv` |

---

## 9. What remains unresolved

- **`Cube_Inventory_Exact` is a live, continuously-updated table**, not a frozen snapshot — this
  run's pull was timestamped 2026-09-06/09-07 (520 distinct timestamps across the 2,484 pulled
  rows), not a single fixed date as an earlier `STATUS.md` entry (2026-08-30) had recorded. A
  re-run on a different day will return different figures; none of the totals in this report are
  reproducible byte-for-byte on a later run. This is a property of the source table, not a defect
  in this script.
- **`cube_Sale_APD` is also live and growing** — the same re-run caveat applies to every cost
  basis computed here (the 12-month window itself will shift on a later run).
- **Whether `cost` is genuinely "landed unit cost" (material + labour + overhead) or something
  narrower (e.g. material cost only) was NOT checked** — this script only established that `cost`
  is a *line total* (cost = qty × some per-unit figure); what that per-unit figure economically
  represents was out of this check's scope (no cost-definition table or business-side
  documentation was queried, per the narrow-scope instruction). If the business's "value tied up"
  question means a different cost concept (e.g. replacement cost, standard cost), this derived
  figure would not answer it — flagged, not resolved.
- **`Cube_Inventory_Exact.costPrice_standard` exists as a column** (confirmed via
  `INFORMATION_SCHEMA.COLUMNS`, float type) and was NOT used, per the task's explicit instruction
  to source cost only from `cube_Sale_APD`. Noted here in case a future check is asked to compare
  it against the derived `cube_Sale_APD`-based unit cost — that comparison was not run.
  `Cube_Inventory_Exact` also has `minimum`/`maximum` float columns (not queried or used — outside
  this check's scope; Phase E's Max-Min calculation, not this one).
  `minimum`/`maximum` are, on their face, plausibly the business's own existing Max-Min
  parameters, not something this check computes — this is an observation of the column's name
  only, not confirmed by any query run here.
- **Annual carrying-cost rate**: as instructed, deliberately not set here — remains a Phase E
  configurable assumption.
- **Whether the 5 no-cost-record items (§2) have ever been sold under a DIFFERENT item code**
  (e.g. a superseded/renamed code) was not checked — out of this check's narrow two-table scope.
