# Phase D Explorer report — Check 3: where CI101-sheet items sold under PEM101 are held

**Role**: Explorer (AGENTS.md) — reports what the join/query returns; does not make the Phase E
planning decision itself, only states the plain practical conclusion the task brief asked for
directly.

**Script**: `src/investigations/phaseD_check3_ci101_stock_location.py`. Scope strictly limited to
`[salewarehouse].[dbo].[cube_Sale_APD]` and `[salewarehouse].[dbo].[Cube_Inventory_Exact]`, per the
task brief — no other table queried. The pricelist file (`reference/pricelist.xlsx`, via
`src/pricelist_reader.py`) is also read, only to attach each item's authoritative division
(CONVENTIONS.md: the pricelist is authoritative for division; the database's own `division` column
is reference-only) — this is a local reference file, not "the wider database."

**Question** (STATUS.md Phase D, Check 3): 37.24% of the combined CI101+PEM101 Omni-Channel value
for CI101's 13 pricelist item codes is recorded under `division='PEM101'` in `cube_Sale_APD` —
confirmed genuine current-period demand for CI101's own item codes (`phaseC_sheetmap_report.md`
§5). Not yet known: does the PHYSICAL STOCK for these items sit in the same warehouses PEM101's own
products use, a different set, or nowhere at all in the current snapshot?

---

## Check 1 — per-item PEM101-tagged sales among CI101's 13 codes

**Query**: `cube_Sale_APD`, `itemcode IN (13 CI101 codes)`, `revenue_type='Omni Channel'`,
`status IN ('Actual','MPS')`, grouped by `itemcode, division`. Confirmed directly — high
confidence. CSV: `output/summary/phaseD_check3_01_per_item_division_breakdown.csv` (raw groups),
`..._01_per_item_pem101_summary.csv` (per-item CI101 vs. PEM101 split).

**12 of CI101's 13 pricelist item codes have >=1 row tagged `division='PEM101'`** under this
filter. Only **`DS-F-99-0109`** has none (a single row, all under `CI101`, ฿202,000 — this item is
outside the scope of Checks 2–4 below; it has no PEM101-tagged sales to locate stock for).

| itemcode | rows CI101 | value CI101 | rows PEM101 | value PEM101 | % value under PEM101 |
|---|---:|---:|---:|---:|---:|
| DS-F-99-0101 | 10 | 17,207,550 | 5 | 10,644,000 | 38.22% |
| DS-F-99-0103 | 12 | 4,098,200 | 11 | 4,536,000 | 52.54% |
| DS-F-99-0105 | 15 | 8,304,140 | 7 | 3,056,000 | 26.90% |
| DS-F-99-0107 | 15 | 10,398,020 | 14 | 12,421,000 | 54.43% |
| DS-F-99-0109 | 1 | 202,000 | 0 | 0 | 0.00% (excluded from Checks 2-4) |
| DS-F-99-0221 | 63 | 40,369,320 | 18 | 12,611,000 | 23.80% |
| DS-F-99-0301 | 69 | 8,564,400 | 17 | 377,886 | 4.23% |
| DS-F-99-0308 | 112 | 11,830,840 | 238 | 14,078,790 | 54.34% |
| DS-F-99-0309 | 3 | 290,400 | 2 | 464,400 | 61.53% |
| DS-F-99-0310 | 1 | 171,000 | 1 | 207,900 | 54.87% |
| DS-F-99-0311 | 30 | 2,658,000 | 44 | 3,079,772 | 53.68% |
| DS-F-99-0312 | 1 | 98,000 | 1 | 108,500 | 52.54% |
| DS-F-99-0320 | 0 | 0 | 2 | 187,500 | 100.00% (all sales tagged PEM101) |

Two items also carry a small residual under a third division (reference only, not part of the
37.24% denominator): `DS-F-99-0221` under `PEM104` (฿508,000) and `DS-F-99-0311` under `PCE101`
(฿114,820). Not investigated further here — out of this check's scope.

**Aggregate reproduction check** (CSV: `..._01b_aggregate_reproduction_check.csv`): this pull gives
CI101-tagged=฿104,191,870, PEM101-tagged=฿61,772,748, combined=฿165,964,618, **PEM101 share=37.22%**
— reproduces the prior report's 37.24% (`phaseC_sheetmap_report.md`, ฿104,089,870 /
฿61,772,748 / ฿165,862,618) closely (0.02 percentage-point difference, ฿102,000 difference in the
CI101-tagged total only). Consistent with a live database re-queried on a later date, not a
contradiction — **confirmed, high confidence**.

---

## Check 2 — Cube_Inventory_Exact stock by warehouse, per item

**Schema confirmed directly** (not assumed) via `INFORMATION_SCHEMA.COLUMNS`
(`..._00_inventory_exact_schema.csv`): `Cube_Inventory_Exact` columns are `id, company, warehouse,
itemcode, product_category, product_type, product_description, unit, stock, freestock,
tobe_received, reserve_bywa, available, timestamp, costPrice_standard, minimum, maximum`. Item-code
column is `itemcode` (confirmed, matches what prior scripts assumed).

**Query**: `Cube_Inventory_Exact` for the 12 items with PEM101-tagged sales. 85 rows returned,
0 negative-stock rows. CSVs: `..._02_ci101_pem101tagged_inventory_raw.csv` (raw),
`..._02_ci101_pem101tagged_by_warehouse.csv` (summed per item/warehouse).

Of the 12 items: **0 have no `Cube_Inventory_Exact` record at all**; **6 have rows but total stock
= 0 across every warehouse they appear in** (`DS-F-99-0101`, `DS-F-99-0103`, `DS-F-99-0107`,
`DS-F-99-0221`, `DS-F-99-0312`, `DS-F-99-0320`); **6 have nonzero stock**:

| itemcode | warehouse(s) with stock>0 | qty |
|---|---|---:|
| DS-F-99-0105 | FMTO | 1 |
| DS-F-99-0301 | FMTS | 1 |
| DS-F-99-0308 | FG01 (13), FMTO (1) | 14 |
| DS-F-99-0309 | FG01 | 15 |
| DS-F-99-0310 | FG01 | 9 |
| DS-F-99-0311 | FG01 | 14 |

---

## Check 3 — comparison set: PEM101's own products' warehouses

**Comparison-set choice, stated explicitly**: the 335-item forecast scope's `division='PEM101'`
codes (`output/summary/phaseC_step2_scope_335items.csv`, 144 codes) — the pricelist-sourced set,
not a database `division`-tag pull, per CONVENTIONS.md's authoritative-source rule. Used the full
set, not a sample, since it was readily available and gives the most representative picture (the
task brief offered either this or the 3 pilot focus items as a fair choice).

**Query**: `Cube_Inventory_Exact` for these 144 codes — 1,076 rows. CSV:
`..._03_pem101_own_items_inventory_raw.csv` (raw), `..._03_pem101_own_items_by_warehouse.csv`
(summed), `..._03_pem101_own_warehouse_set.csv` (the set below).

**PEM101's own products hold nonzero stock in 6 distinct warehouse codes**: `FG01, FG21, FMTO,
FMTS, W4-1, WH21`.

---

## Check 4 — table-wide warehouse ambiguity (independent re-check for these specific codes)

STATUS.md already records a Phase 4 finding that most warehouse codes are shared across multiple
divisions table-wide ("33 of 34 codes used across MULTIPLE divisions"). This check independently
re-verifies that, restricted to the 6 warehouse codes actually in play here (PEM101's own set),
using `Cube_Inventory_Exact` joined to the full pricelist registry's division (445 codes, 6
divisions: PEM101/PEM102/PEM103/PEM104/PEM107/CI101). CSV:
`..._04_warehouse_division_ambiguity_tablewide.csv`.

| warehouse | divisions with nonzero stock here (table-wide) | n divisions |
|---|---|---:|
| FG01 | CI101, PEM101, PEM102, PEM107 | 4 |
| FMTS | CI101, PEM101, PEM103, PEM107 | 4 |
| FMTO | CI101, PEM101, PEM107 | 3 |
| FG21 | PEM101 only | 1 |
| W4-1 | PEM101 only | 1 |
| WH21 | PEM101 only | 1 |

**Judgment call, stated explicitly**: a warehouse is treated as "table-wide shared / ambiguous —
not distinctively PEM101's" if it holds nonzero stock for items from 3 or more of the 6 pricelist
divisions. This threshold is not derived from the data; it is this Explorer's reading of "used
broadly" vs. "essentially exclusive." Under it, **FG01, FMTS and FMTO are ambiguous; FG21, W4-1 and
WH21 are distinctively PEM101's** (only PEM101 items hold stock there, table-wide).

**Directly relevant prior finding, cited not re-derived** (out of this check's own table scope, so
not verified here): the Phase 4 warehouse investigation
(`output/summary/phase4_warehouse_flow_investigation_report.md` / Part 3 of
`src/investigations/warehouse_sellable_stock.py`) already confirmed, from `cube_inventory_tran`
movement evidence, that `FMTS` and `FMTO` are production-order WIP staging locations —
near-zero settled stock, large `tobe_received` — **not yet available for external/customer use**,
i.e. not sellable Finished Goods stock. This is directly relevant to `DS-F-99-0105` and
`DS-F-99-0301` below, whose only nonzero stock sits entirely in FMTO/FMTS respectively.

---

## Verdict — per item, same/different/partial/no-stock/undetermined

CSV: `output/summary/phaseD_check3_05_per_item_verdict.csv` (full evidence per item, including the
per-warehouse ambiguity detail dict). Supplementary status check (Actual vs. MPS/backlog) for the
6 zero-stock items: `output/summary/phaseD_check3_06_zerostock_items_status_breakdown.csv`.

| itemcode | item's stock-holding warehouse(s) | overlap with PEM101's own set | raw verdict | final verdict |
|---|---|---|---|---|
| DS-F-99-0101 | none | — | NO_STOCK | no `Cube_Inventory_Exact` record shows any stock (4 rows, all warehouses 0) |
| DS-F-99-0103 | none | — | NO_STOCK | same (5 rows, all 0) |
| DS-F-99-0105 | FMTO | FMTO | SAME (raw) | **SAME_BUT_UNDETERMINED** — FMTO is table-wide ambiguous (3 divisions); also a known WIP-staging location (not sellable), and only 1 unit |
| DS-F-99-0107 | none | — | NO_STOCK | same (7 rows, all 0) |
| DS-F-99-0221 | none | — | NO_STOCK | same (9 rows, all 0) |
| DS-F-99-0301 | FMTS | FMTS | SAME (raw) | **SAME_BUT_UNDETERMINED** — FMTS is table-wide ambiguous (4 divisions); also a known WIP-staging location, only 1 unit |
| DS-F-99-0308 | FG01, FMTO | FG01, FMTO | SAME (raw) | **SAME_BUT_UNDETERMINED** — both warehouses table-wide ambiguous |
| DS-F-99-0309 | FG01 | FG01 | SAME (raw) | **SAME_BUT_UNDETERMINED** — FG01 table-wide ambiguous (4 divisions) |
| DS-F-99-0310 | FG01 | FG01 | SAME (raw) | **SAME_BUT_UNDETERMINED** |
| DS-F-99-0311 | FG01 | FG01 | SAME (raw) | **SAME_BUT_UNDETERMINED** |
| DS-F-99-0312 | none | — | NO_STOCK | same (5 rows, all 0) |
| DS-F-99-0320 | none | — | NO_STOCK | same (2 rows, all 0) |

**No item lands as DIFFERENT or genuine PARTIAL.** No item's stock sits in a warehouse code
*outside* PEM101's own 6-code set. But equally, no item's stock sits *exclusively* in one of the
3 warehouse codes (`FG21`, `W4-1`, `WH21`) that are distinctively PEM101's (table-wide) — every
item with any stock has it only in `FG01`, `FMTO` or `FMTS`, the 3 codes shared with other
divisions too.

---

## Practical conclusion, per item — directly stated

**6 items with zero stock anywhere** (`DS-F-99-0101`, `DS-F-99-0103`, `DS-F-99-0107`,
`DS-F-99-0221`, `DS-F-99-0312`, `DS-F-99-0320`): `Cube_Inventory_Exact` is a single current-state
snapshot (2026-08-30, no time series — STATUS.md), not a history, so zero current stock cannot by
itself say whether stock existed and was consumed, or never existed. The supplementary status
check narrows this:
- `DS-F-99-0103`, `DS-F-99-0107`, `DS-F-99-0312`, `DS-F-99-0320` — **100% of their PEM101-tagged
  rows are `status='Actual'`** (already recorded/delivered sales, most from 2024 or early 2026).
  Zero current stock is fully consistent with fulfilled, already-shipped orders — **not a gap**,
  no open question raised by this alone.
- `DS-F-99-0101` and `DS-F-99-0221` each carry a small number of **`status='MPS'` (backlog,
  pending) rows** with `forecast_date` still in the future (up to 2026-10-20 and 2026-12-25
  respectively, ฿360,000 and ฿3,230,000) — pending demand with **nothing currently on hand** in
  this snapshot. **This is a genuine open point for these two items specifically**: either their
  pending demand will be fulfilled from stock produced closer to the delivery date (make-to-order,
  consistent with the project's earlier production-strategy finding), or there is a real supply
  gap — this snapshot cannot distinguish the two, and it is not this check's job to guess which.

**6 items with nonzero stock, all in warehouse codes matching PEM101's own set**
(`DS-F-99-0105`, `DS-F-99-0301`, `DS-F-99-0308`, `DS-F-99-0309`, `DS-F-99-0310`, `DS-F-99-0311`):
**directly, their stock is co-located with PEM101's own products** — same warehouse codes, not a
separate location. Per the task's own framing, that supports **including them in Phase E planning
within the shared warehouse pool used for PEM101 planning** — there is no evidence in this data of
a separate stock location for these items. The one caveat that must not be dropped: the specific
codes involved (`FG01`, `FMTO`, `FMTS`) are **not exclusively PEM101's** — they hold stock for
CI101, PEM102, PEM103 and PEM107 items too, table-wide. This does not contradict the "include in
the shared pool" conclusion; if anything it reinforces it, since it means CI101's own items already
physically coexist with PEM101's, PEM102's and PEM107's stock in these same locations as a matter
of course — consistent with, not contradicted by, the project's prior finding that no warehouse
code in this company is exclusive to one business unit. **What this data does NOT support is a
claim that these 6 items sit in a warehouse pool dedicated or unique to PEM101** — that stronger
claim is UNDETERMINED, and is not made here.

Two further, item-specific caveats:
- `DS-F-99-0105` and `DS-F-99-0301` hold only **1 unit each**, and it sits entirely in `FMTO`/
  `FMTS` respectively — locations the prior Phase 4 investigation already found to be
  production-order WIP staging, not yet available for external/customer use. Practically, these
  two items currently have **negligible-to-no sellable stock** despite technically passing the
  "same warehouse codes" test.
- `DS-F-99-0308`/`0309`/`0310`/`0311` hold more substantial quantities (9-15 units) in `FG01`,
  which is a more credible finished-goods location by the project's earlier warehouse-flow
  mapping, though `FG01` too is shared with CI101/PEM102/PEM107 items table-wide.

**`DS-F-99-0109`**: has no PEM101-tagged sales at all under this filter — this check does not
apply to it; its stock location relative to PEM101 is not a meaningful question for this item.

---

## Confidence levels

| Finding | Confidence | Basis |
|---|---|---|
| 12 of 13 CI101 codes have PEM101-tagged Omni-Channel sales (Actual/MPS) | High | Direct query, `..._01_per_item_pem101_summary.csv` |
| Aggregate reproduces the known 37.24% figure (37.22% here) | High | `..._01b_aggregate_reproduction_check.csv`, 0.02pp difference explained by later query date |
| `Cube_Inventory_Exact` schema / `itemcode` column name | High | Directly queried `INFORMATION_SCHEMA.COLUMNS`, not assumed |
| Per-item stock-by-warehouse figures (Check 2) | High | Direct query, 0 negative-stock rows found |
| PEM101's own warehouse set = {FG01, FG21, FMTO, FMTS, W4-1, WH21} | Moderate-high | Direct query on the chosen comparison set (335-scope PEM101 codes); the comparison-set choice itself is a judgment call, stated explicitly, not a project-locked definition |
| 6 of 12 items have zero stock anywhere in the current snapshot | High | Direct query, cross-checked against status (Actual vs. MPS) |
| 6 of 12 items have stock, all in warehouse codes matching PEM101's own set | High (the co-location fact) | Direct query |
| Those 6 items' warehouses are NOT distinctively PEM101's (shared 3-4 divisions table-wide) | High | Independent re-derivation for these exact codes, Check 4, consistent with the pre-existing Phase 4 finding |
| "Include in Phase E's shared PEM101 pool" is a defensible reading, not proof of dedicated PEM101-only stock | Stated conclusion, not a data fact — Moderate | Follows from the co-location finding plus the ambiguity caveat, both high-confidence individually |
| FMTO/FMTS are WIP-staging, not sellable | Cited from a prior, out-of-scope investigation (not re-verified here) | `phase4_warehouse_flow_investigation_report.md` / `warehouse_sellable_stock.py` |

## What remains unresolved

1. **Whether the 2 items pending on MPS/backlog status with zero current stock
   (`DS-F-99-0101`, `DS-F-99-0221`) have a genuine supply gap or will be produced/stocked closer to
   their forecast delivery date.** Not answerable from `Cube_Inventory_Exact` alone (a single
   snapshot, no history) or from `cube_Sale_APD` (no warehouse field) — needs either a historical
   inventory series (not evidenced to exist in this database — STATUS.md notes
   `Cube_Inventory_Exact` is a single current-state snapshot) or a direct answer from
   production/warehouse staff.
2. **Whether `FG01`/`FMTO`/`FMTS` genuinely function as a shared cross-division Finished Goods
   pool by design, or whether this is an unintended commingling.** This check only establishes that
   the codes are used by multiple divisions' items table-wide — it cannot and does not determine
   business intent. Same open point as the pre-existing Phase 4 finding, now specifically confirmed
   for these codes too.
3. **The comparison-set choice for "PEM101's own products" (335-scope, pricelist-sourced) was not
   cross-checked against an alternative definition** (e.g. items tagged `division='PEM101'` in raw
   `cube_Sale_APD`, without the pricelist filter) — the task brief permitted either approach and
   this Explorer used the pricelist-sourced set per CONVENTIONS.md's authoritative-source rule; a
   second Explorer or Validator could re-run Check 3 on the alternative definition as a
   cross-check, if the Synthesizer judges it material.
4. **The exact 0.02-percentage-point drift between this pull's 37.22% and the previously-recorded
   37.24%** was attributed to normal live-data movement between query dates, not independently
   traced row-by-row — low-materiality, not pursued further per the stopping rule.
