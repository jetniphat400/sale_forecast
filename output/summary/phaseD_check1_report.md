# Phase D, Check 1 — Which Warehouse Stages Hold Sellable Stock

**Role**: Explorer (AGENTS.md). **Scope**: `[salewarehouse].[dbo].[Cube_Inventory_Exact]` only,
plus its needed joins (`reference/pricelist.xlsx` for item scope/division/Type,
`output/summary/phaseC_step1revised_item_status_445.csv` for the forecast-status flag). No other
database table was queried, per instruction. Investigation only — no min/max calculated, no model
built, `config/config.yaml` not touched.

**Script**: `src/investigations/phaseD_check1_sellable_stock.py`. **Run**: 2026-09-08.

Per AGENTS.md's Explorer boundary, this report states what queries return, not what it implies for
the business — that interpretation belongs to the Synthesizer/Analyst.

---

## 1. Full structure of `Cube_Inventory_Exact`

**Confirmed by direct query** (`INFORMATION_SCHEMA.COLUMNS`; CSV:
`output/summary/phaseD_check1_01_schema.csv`). 17 columns:

| Column | Type |
|---|---|
| id | int |
| company | varchar(50) |
| warehouse | varchar(20) |
| itemcode | varchar(50) |
| product_category | varchar(150) |
| product_type | varchar(150) |
| product_description | varchar(250) |
| unit | varchar(20) |
| stock | decimal |
| freestock | decimal |
| tobe_received | decimal |
| reserve_bywa | decimal |
| available | decimal |
| timestamp | datetime |
| costPrice_standard | float |
| minimum | float |
| maximum | float |

**No status/stage/sellability flag column exists.** The only candidate columns by name are
`available` (a *quantity* — `stock` minus reservations — not a status flag) and
`product_category`/`product_type` (pricelist-attribute reference fields, per CONVENTIONS.md
reference-only and never used to classify). Neither records a process stage such as
"inspection"/"hold"/"ready-to-ship". **Stopping rule applied**: this is the entirety of the
schema; no field distinguishes a sellable stage from a non-sellable one, and per the task's scope
restriction, no other table was searched to look further.

**Snapshot date** (CSV: `output/summary/phaseD_check1_02_snapshot_date_range.csv`): a single
frozen calendar date, **2026-09-06**. `timestamp` ranges 2026-09-06 21:38:25.480 to 2026-09-06
21:39:37.933 (14,615 distinct sub-second timestamps within a ~72-second window, across 96,574
rows table-wide) — consistent with one batch extraction run, not a range of dates. This is a
**newer snapshot** than the one used in the prior 2026-09-02 warehouse investigation
(`output/data/raw_inventory_exact_128items.csv`, timestamp 2026-08-30) — figures below will not
match that earlier pull exactly; this is expected (stock moves day to day), not a contradiction.

**Full warehouse-code universe, table-wide** (no item filter; CSV:
`output/summary/phaseD_check1_03_warehouse_universe_tablewide.csv`): **76 distinct warehouse
codes**, 96,574 rows total. Top 10 by total `stock` (table-wide, all items/divisions):

| warehouse | n_rows | n_items | total_stock | total_available |
|---|---|---|---|---|
| EXP | 2,490 | 2,370 | 3,886,724 | 3,894,041 |
| WH21 | 661 | 661 | 1,980,685 | 1,567,453 |
| WH23 | 2,873 | 2,873 | 988,878 | 399,758 |
| WH27 | 783 | 783 | 676,779 | 331,962 |
| WH24 | 4,639 | 4,639 | 354,276 | 349,489 |
| WH26 | 1,928 | 1,928 | 243,162 | 138,978 |
| WH22 | 1,059 | 1,059 | 216,576 | 176,776 |
| FG01 | 1,441 | 1,441 | 125,209 | 126,271 |
| WH | 4,006 | 3,984 | 82,300 | 35,301 |
| W3-3 | 1,161 | 1,161 | 54,888 | 51,657 |

Full 76-row table in the CSV. Note `EXP` dominates the table-wide total by a wide margin but (as
found below) **does not appear at all** in the 445-item in-scope pull — none of this project's
items are held there.

---

## 2. In-scope pull (445 pricelist items, 335 forecast-status items highlighted)

**Item scope**: 445 distinct codes from `reference/pricelist.xlsx` visible sheets
(`src/pricelist_reader.load_visible_product_rows`), division attached via
`config.yaml`'s `sheet_to_division` (sheet-uniqueness re-verified: no code appears on two
different sheets). Forecast-status flag: 335 of 445 items have
`status_category == 'forecast'` in `output/summary/phaseC_step1revised_item_status_445.csv`.
Scope CSV: `output/summary/phaseD_check1_04_item_scope_445_with_division_and_forecast_flag.csv`.

**Join column confirmed directly from the schema query above**: `itemcode` (varchar(50)) — matches
`cube_Sale_APD.itemcode`'s naming, and the schema query in §1 shows this is in fact the column
name (not assumed).

**Coverage**: 388 of 445 in-scope items (87.2%) have at least one row in `Cube_Inventory_Exact`;
**57 of 445 (12.8%) have NO row at all** — 4 items have a blank `Product Type` cell in the
pricelist itself (`CM-F-99-447003`, `RL-F-99-440002`, `RL-F-99-440004`, `RL-F-99-440018`; not a
join failure — their division still resolves) and are kept in the Type-level summary under
`(blank in pricelist)`. Raw pull: `output/summary/phaseD_check1_05_raw_inventory_pull_445items.csv`
(2,484 item×warehouse rows). Per-item-per-warehouse quantity grid (388 items × warehouse columns,
with division/Type/forecast-flag attached):
`output/summary/phaseD_check1_06_per_item_per_warehouse_qty_grid.csv`.

Of the 388 present items, **329 are forecast-status** and **59 are non-forecast** (placeholder/
excluded/PEM104). 6 of the 335 forecast-status items have no snapshot row at all.

Total in-scope `stock` across all warehouses: **158,130 units**. Forecast-status items hold
157,897 of these (99.85%); non-forecast items hold 233 (0.15%).

---

## 3. Per-warehouse-code sellability determination

**Confirmed NOT sellable — applying the prior investigation's finding, not re-derived** (this
check's permitted scope, `Cube_Inventory_Exact` alone, has no transaction/issue-event data and
cannot reproduce a movement-based finding):

> STATUS.md, "Warehouse flow, stage dwell time, sellable stock, and double-counting verification"
> (DONE 2026-09-02), Part 3: **QA** = pass-through inspection gate (567,306 units handled in the
> prior 6-item movement-ledger scope, only 22 — 0.004% — ever issued externally). **FMTS/FMTO** =
> production work-in-progress staging (negligible settled stock, large `tobe_received`, evidenced
> broadly across 69-103 of the prior 128-item scope).

In the 445-item in-scope pull: `QA` holds 0 units of `stock` (but 27,300 `available` — reserved/
in-transit quantity, not settled stock) across 19 items; `FMTS` holds 82 units across 237 items;
`FMTO` holds 76 units across 259 items. **Total confirmed-not-sellable stock in scope: 158 units
(0.10% of the 158,130-unit total)** — see
`output/summary/phaseD_check1_07_warehouse_sellability_determination.csv`.

**Every other warehouse code present in the in-scope pull: UNDETERMINED.** 41 other codes appear
in the in-scope pull (44 total minus QA/FMTS/FMTO), including all 11 of the remaining
behaviourally-role-assigned codes from the prior 14-code list (`CL`, `F101`, `FG`, `FG01`, `FG02`,
`FG11`, `FG21`, `INTR`, `W121`, `WH01`, `WH21`) and 30 codes outside that list entirely (`AST`,
`F103`, `F106`, `F107`, `F109`, `F2-1`, `F2-2`, `F-RD`, `FG03`, `FG12`, `FG13`, `FG16`, `FG17`,
`FG22`, `FG23`, `FG24`, `FG27`, `NCRM`, `P104`, `W101`, `W121`, `W122`, `W124`, `W4-1`, `WH04`,
`WH05`, `WH06`, `WH07`, `WH22`, `WH23`, `WH24`).

**No code was newly determined beyond the already-known QA/FMTS/FMTO exclusions.** As found in §1,
`Cube_Inventory_Exact`'s schema has no sellability/status field, so this check cannot move any
code out of UNDETERMINED — including `FG01`/`FG02`/`FG11`/`FG21`, which hold the great majority of
in-scope stock (`FG01` alone: 124,192 units across 288 items; `FG21`: 24,255 units across 109
items; `WH21`: 9,084 units across 6 items) and sit downstream in the QA→WH01→FG01→FG02 topology.
**Per the ground rules, topology alone is explicitly not sufficient evidence and these are marked
UNDETERMINED, not sellable.** Full per-code table, with an `evidence` column stating the reasoning
for every single code, in
`output/summary/phaseD_check1_07_warehouse_sellability_determination.csv`.

---

## 4. Sellable quantity per item, Type, division

Because no warehouse code beyond QA/FMTS/FMTO could be confirmed sellable, **confirmed-sellable
quantity is 0 for every item, Type, and division in this scope** — this is the honest result of
applying the ground rule ("do not mark any code sellable by assumption") strictly, not a
data-pull error. The summaries below instead report the three buckets that the data actually
supports: confirmed-not-sellable, undetermined, and their totals.

- Per item: `output/summary/phaseD_check1_08_per_item_sellability_summary.csv` (388 rows)
- Per Type (within division): `output/summary/phaseD_check1_09_per_type_sellability_summary.csv` (44 rows)
- Per division: `output/summary/phaseD_check1_10_per_division_sellability_summary.csv` (6 rows)
- Overall: `output/summary/phaseD_check1_11_overall_summary.csv`

**Per division** (total_stock / confirmed_not_sellable / undetermined / undetermined_pct):

| division | total_stock | confirmed_not_sellable | undetermined | undetermined_pct |
|---|---|---|---|---|
| PEM101 | 157,179 | 83 | 157,096 | 99.95% |
| PEM107 | 796 | 21 | 775 | 97.36% |
| PEM103 | 95 | 51 | 44 | 46.32% |
| CI101 | 54 | 3 | 51 | 94.44% |
| PEM102 | 4 | 0 | 4 | 100.00% |
| PEM104 | 2 | 0 | 2 | 100.00% |

**PEM103 is a material outlier** — its undetermined share (46.3%) is far below every other
division (94-100%) because a comparatively large fraction of its small 95-unit total sits in QA/
FMTS/FMTO (51 units). This is a real, directly-observed pattern in the data (small absolute
numbers, so a few units of QA/FMTS/FMTO stock move the percentage a lot) — reported factually, not
interpreted further per the Explorer role boundary.

**Overall (all 445-item scope, all divisions combined)**:
- Total on-hand `stock`: **158,130 units**
- Confirmed sellable: **0 units (0.00%)**
- Confirmed NOT sellable (QA/FMTS/FMTO): **158 units (0.10%)**
- **Undetermined: 157,972 units (99.90%)**

Restricting to the 335 forecast-status items only (329 of which are present in the snapshot):
157,897 of 158,130 total-scope units (99.85%) belong to forecast-status items; within that
subset, 158 units are confirmed not-sellable and 157,739 are undetermined (99.90% undetermined,
essentially identical to the whole-scope figure since forecast items dominate total stock).

---

## 5. Confidence levels

- **Schema, snapshot date, table-wide warehouse universe (§1)**: **confirmed**, direct query
  result, high confidence.
- **In-scope item pull, coverage, item/Type/division totals (§2, §4 stock totals)**: **confirmed**,
  direct query result joined against the pricelist, high confidence. The 57-item snapshot-absence
  and 4-item blank-Type findings are also direct/confirmed, not inferred.
- **QA/FMTS/FMTO = confirmed not sellable (§3)**: **confirmed at the process level** by the prior
  investigation (STATUS.md, 2026-09-02), applied here rather than re-derived — this check's own
  evidence is limited to the in-scope quantities sitting there today (158 units), which is
  consistent with, not independent proof of, that prior finding. Stated per AGENTS.md rule 7:
  carried forward explicitly labelled as the prior investigation's finding, not re-verified by
  this check.
- **Every other warehouse code = UNDETERMINED (§3, §4)**: **confirmed absence of evidence**, high
  confidence — the schema was checked directly (§1) and has no sellability field. This is not the
  same as "not sellable" or "sellable"; it means the data available to this check cannot settle
  the question, stated plainly per the stopping rule.

---

## 6. What remains unresolved

- **Whether `FG01`/`FG02`/`FG11`/`FG21`/`WH01`/`WH21` (and every other UNDETERMINED code) hold
  genuinely sellable Finished Goods stock is still not confirmed by any data this project has
  access to.** `Cube_Inventory_Exact` has no status/stage field (§1); the movement ledger
  (`cube_inventory_tran`, out of this check's scope) only covers 34/128 of the prior narrower
  scope and 6/34 Raw-Material items with any transfer at all. This must come from business/
  operations input (e.g. warehouse staff who know which locations orders are physically picked
  and shipped from) — not resolvable from data alone, per the stopping rule.
- **99.90% of in-scope on-hand stock (157,972 of 158,130 units) sits in warehouse codes whose
  sellability cannot be determined from any table this project has queried.** Only 0.10% (QA/
  FMTS/FMTO) is confirmed not sellable, and 0% is confirmed sellable. Any downstream Phase E/F
  calculation that needs a "sellable stock" figure will need either a business-confirmed mapping
  of stage → sellability, or an explicit assumption stated as such (not derived from this data).
- **PEM103's much lower undetermined share (46.3% vs. 94-100% elsewhere)** is reported as an
  observed pattern only — this Explorer report does not interpret why, per the AGENTS.md role
  boundary (interpretation belongs to Analyst/Synthesizer).
- **`EXP`, table-wide the single largest warehouse code by stock (3,886,724 units), holds zero
  units of any of the 445 in-scope items** — confirmed by direct query (§1 vs. §3), not
  interpreted further here.

---

## Deliverables

- Script: `src/investigations/phaseD_check1_sellable_stock.py`
- CSVs (all in `output/summary/`, prefix `phaseD_check1_`):
  `01_schema.csv`, `02_snapshot_date_range.csv`, `03_warehouse_universe_tablewide.csv`,
  `04_item_scope_445_with_division_and_forecast_flag.csv`,
  `05_raw_inventory_pull_445items.csv`, `06_per_item_per_warehouse_qty_grid.csv`,
  `07_warehouse_sellability_determination.csv`, `08_per_item_sellability_summary.csv`,
  `09_per_type_sellability_summary.csv`, `10_per_division_sellability_summary.csv`,
  `11_overall_summary.csv`
- This report: `output/summary/phaseD_check1_report.md`
