# Phase D Synthesis — Phase E Readiness Statement

**Role**: Synthesizer (`AGENTS.md`). Merges findings already produced by the three Phase D
Explorers; gathers no new data, runs no new queries. Per AGENTS.md Rule 9, where two inputs
disagree both positions are reported with their evidence and the decision is left to a human.

**Inputs merged** (read in full):
- `output/summary/phaseD_check1_report.md` + CSVs (prefix `phaseD_check1_`) — sellable-stock stages.
- `output/summary/phaseD_check2_report.md` + CSVs (prefix `phaseD_check2_`) — value tied up in stock.
- `output/summary/phaseD_check3_report.md` + CSVs (prefix `phaseD_check3_`) — CI101/PEM101 stock location.
- `STATUS.md` §2 (2026-09-02 warehouse-flow investigation; Phase C closure), §4 (Locked Decisions),
  §8 (2026-09-04 business resolutions, especially §8.4 "To be derived from `Cube_Inventory_Exact`").

---

## 1. What stock is sellable, and where

**Source**: `phaseD_check1_report.md`, §1-5; CSVs `07`-`11`.

- **Snapshot**: a single frozen batch dated **2026-09-06** (`timestamp` 21:38:25.480-21:39:37.933,
  a ~72-second window, 96,574 rows table-wide) — Check 1's own direct finding. **Confirmed, high
  confidence.**
- **Schema has no sellability/status field.** `Cube_Inventory_Exact`'s 17 columns include no
  stage/hold/ready-to-ship flag; `available` is a quantity (stock minus reservations), not a
  status. **Confirmed, high confidence.**
- **In-scope total**: 158,130 units of on-hand `stock`, across 388 of 445 items (57 items have no
  row at all in the snapshot).
- **Confirmed NOT sellable** (`QA`, `FMTS`, `FMTO` — applying the prior 2026-09-02 movement-ledger
  finding, not re-derived by this check since it has no transaction data): **158 units, 0.10% of
  total.**
- **Confirmed sellable: 0 units, 0.00%.** Stated as plainly as Check 1 itself states it — this is
  not a rounding artifact or a data-pull failure, it is the direct, honest consequence of applying
  the "no code is sellable by assumption" rule strictly to a schema with no sellability field.
- **Undetermined: 157,972 units, 99.90%.** This includes `FG01` (124,192 units, 288 items) and
  `FG21` (24,255 units, 109 items), which sit downstream in the QA→WH01→FG01→FG02 topology and are
  plausible finished-goods stores by name and topology alone — but topology is explicitly not
  sufficient evidence per the project's ground rules, so they stay UNDETERMINED, not sellable.
- **Per-division undetermined share** (CSV `10`): PEM101 99.95%, PEM107 97.36%, CI101 94.44%,
  PEM102 100.00%, PEM104 100.00%, and **PEM103 is a material outlier at 46.32%** — driven by a
  comparatively large share of PEM103's small 95-unit total sitting in QA/FMTS/FMTO. Check 1
  reports this as an observed pattern only, per its Explorer role boundary; it does not interpret
  why. This synthesis does not interpret it further either — flagged as unexplained.

**Confidence**: schema, snapshot date, quantities — high (direct query). QA/FMTS/FMTO = not
sellable — confirmed at the process level by the *prior* (2026-09-02) investigation, carried
forward, not independently re-derived by Check 1 itself (labelled as such per AGENTS.md Rule 7).
Every other code = undetermined — high confidence in the *absence of evidence*, which is a
different, and more defensible, claim than "not sellable" or "sellable."

---

## 2. What it is worth

**Source**: `phaseD_check2_report.md`, §0-8; CSVs `item_stock_value`, `rollup_by_type`,
`rollup_by_division`, `top10_value_items`, `no_forecast_value_breakdown`, `stock_no_cost_items`.

**Flagged prominently, per instruction**: the task brief described `cube_Sale_APD.cost` as a unit
cost. Check 2 **directly disproved this before computing anything**: for `EEE-F-FC-1040010002`,
`cost / qty` is exactly 1,547.18 across six rows with qty ranging 2-100 — `cost` is a **line
total**, not a unit price. Table-wide, the median within-item CV of `cost/qty` is 0.108 (0.061 on
the 343-item project scope), consistent with a drifting per-unit price, not a stable stored unit
cost. **Using the raw `cost` column as a unit price, as the task wording implied, would have
overstated stock value by roughly one to two orders of magnitude for high-qty transaction lines.**
Confirmed, high confidence, directly reproducible from raw rows.

- **Methodology adopted**: unit cost = `cost / qty` per row, then **median over the trailing 12
  months** (window ending at the table's max `createDate`, 2026-09-07 at pull time). Reasoning:
  this project has repeatedly found outlier rows in `cube_Sale_APD`-family tables; a median is
  robust to a single unusual transaction. Most-recent-transaction cost is computed alongside as the
  required sanity companion, not as the primary basis. **56 of 343 priced items** have cost history
  but no row in the trailing 12 months — for those, most-recent-transaction cost is used as a
  flagged fallback (never silently substituted).
- **Total priced stock value: THB 37,399,005.48** (across all 445 items, all warehouses, no
  sellability filter — deliberately the total-capital-tied-up figure, not Check 1's sellable
  figure). Verified internally: item-level sum = Type rollup sum = division rollup sum.
- **Median-12mo vs. most-recent sensitivity**: 22 of 287 dual-computable items (7.7%) differ by
  more than 20%, but most of those have zero current stock. **Portfolio total would be THB
  39,495,341 under most-recent-transaction costing instead — 5.6% higher.** Top-10 list is stable
  under either basis except one marginal swap (`VT-F-99-010203` in, `LS-F-99-1004` out).
- **Top-10 value items** (CSV `top10_value_items`; full table in Check 2 §4): dominated by PEM103
  transformers (`TF-F-99-...`, 5 of 10) and PEM101 items. Two items carry very large months-of-cover
  by a simple historical-mean demand basis: `FC-A-38-00202` (1,630 months) and `HS-F-99-02410`
  (39,060 months) — both large capital tied up against near-zero recent demand by this measure.
  "Months of cover" here uses the plain 31-month historical mean, not a forecast-model output —
  stated as a moderate-confidence planning number, not a high-confidence one, for that reason.
- **No-forecast-scope value: THB 226,449.90 priced, plus 226 units value-undetermined** (0.61% of
  total priced value) — stock sitting in items with no demand basis to plan against
  (excluded-division, listed-but-never-sold, or placeholder status).
- **5 items with stock but NO cost record at all** (`FC-A-38-00203`, `IS-F-99-0365CE1`,
  `HS-F-99-3121`, `02-05-R-0001`, `TF-F-99-3107223B1`; total 226 units) — value undetermined, **not
  assigned zero and not dropped** from any total; reported as its own line in every rollup.
- **Explicit restatement, per task instruction: this THB 37.4M figure is capital tied up at one
  point in time, not an annual carrying cost.** No annual holding-cost rate exists in this data —
  the 15-25% figure elsewhere in `STATUS.md`/`CONVENTIONS.md` is explicitly flagged there as an
  unverified, uncited assumption and is not used anywhere in Check 2.
- **Deeper unresolved question, stated by Check 2 itself and not answered**: whether `cost`
  economically represents landed cost (material+labour+overhead), material cost only, or something
  else was **not checked** — out of Check 2's two-table scope. If "value tied up" means a different
  cost concept (replacement cost, standard cost), this derived figure would not answer that
  question.

**Confidence**: cost-is-line-total finding, stock quantities, total priced value, no-forecast-scope
value, no-cost-record item list — all high (direct query/recomputation, internally
cross-verified). Median-12mo as "more robust" — moderate (reasoned from this project's documented
history of outlier rows, not statistically proven for this exact item set). Months-of-cover as a
planning number — moderate (simple historical mean, not a forecast).

---

## 3. Whether CI101 items are in scope for stock planning

**Source**: `phaseD_check3_report.md`, all sections; CSVs `01`-`06`.

- **12 of CI101's 13 pricelist codes** have at least one Omni-Channel row tagged
  `division='PEM101'` (`DS-F-99-0109` is the exception — all its sales are CI101-tagged; it is
  excluded from the rest of this check by construction).
- **Aggregate reproduces the known 37.24% figure closely** (37.22% here vs. 37.24% previously
  recorded, a 0.02pp drift attributed to normal live-data movement between query dates, not traced
  row-by-row).
- Of the 12 items: **6 have zero current stock anywhere** (`DS-F-99-0101`, `DS-F-99-0103`,
  `DS-F-99-0107`, `DS-F-99-0221`, `DS-F-99-0312`, `DS-F-99-0320`); **6 have nonzero stock**
  (`DS-F-99-0105`, `DS-F-99-0301`, `DS-F-99-0308`, `DS-F-99-0309`, `DS-F-99-0310`, `DS-F-99-0311`).
- Of the 6 zero-stock items: 4 are fully explained by 100% `status='Actual'` history (already
  fulfilled, zero-stock is not a gap). **2 (`DS-F-99-0101`, `DS-F-99-0221`) carry pending
  `status='MPS'` (backlog) rows with future `forecast_date`s (up to 2026-10-20 and 2026-12-25,
  ฿360,000 and ฿3,230,000) and nothing currently on hand** — a genuine open point Check 3 states it
  cannot resolve from a single-snapshot table (make-to-order fulfilment vs. a real supply gap are
  indistinguishable from this data).
- **PEM101's own warehouse set (from the 335-scope, pricelist-sourced comparison group)**: `FG01,
  FG21, FMTO, FMTS, W4-1, WH21` (6 codes).
- **All 6 CI101 items with stock hold it exclusively within this same 6-code set** — specifically
  only in `FG01`, `FMTO`, or `FMTS` (never `FG21`, `W4-1`, or `WH21`, the 3 codes that are
  distinctively PEM101's table-wide). No item lands as DIFFERENT (stock in a code outside PEM101's
  set) or genuine PARTIAL.
- **Check 3's own stated caveat, load-bearing**: `FG01`, `FMTO`, and `FMTS` are **not
  distinctively PEM101's** — table-wide, they hold nonzero stock for 3-4 of the 6 pricelist
  divisions each (`FG01`: CI101/PEM101/PEM102/PEM107; `FMTS`: CI101/PEM101/PEM103/PEM107; `FMTO`:
  CI101/PEM101/PEM107). This is exactly why Check 3's raw "SAME" verdict for all 6 stocked items is
  downgraded to **`SAME_BUT_UNDETERMINED`** in its final verdict column, not left as a clean "same."
- Two of the six (`DS-F-99-0105`, `DS-F-99-0301`) hold only 1 unit each, sitting entirely in
  `FMTO`/`FMTS` respectively — locations the prior 2026-09-02 investigation already found to be
  production-order WIP staging, not yet available for external/customer use. Practically negligible
  stock, despite technically passing the "same warehouse codes" test.
- **Practical conclusion stated by Check 3**: co-location with PEM101's own stock supports
  including these items in Phase E's shared PEM101 planning pool — but the data does **not**
  support the stronger claim that this pool is dedicated or unique to PEM101; that stronger claim
  is explicitly left UNDETERMINED, not made.

**Confidence**: per-item division breakdown, aggregate reproduction, per-item stock-by-warehouse,
zero-vs-nonzero-stock split — all high (direct query). "Include in the shared PEM101 pool" —
stated by Check 3 itself as a defensible reading, not a data fact, moderate confidence. Whether
`FG01`/`FMTO`/`FMTS` are a shared pool by design or unintended commingling — undetermined, Check 3
does not claim to know.

---

## 4. Cross-checks between the three checks

### 4a. Check 1 vs. Check 3 — do the 6 CI101 items' warehouse/sellability determinations agree?

**Directly verified by this synthesis against both checks' underlying CSVs**
(`phaseD_check1_08_per_item_sellability_summary.csv` and
`phaseD_check3_02_ci101_pem101tagged_by_warehouse.csv`) — **exact agreement, high confidence**:

| itemcode | Check 3 stock location | Check 1 sellability classification |
|---|---|---|
| DS-F-99-0105 | FMTO, 1 unit | confirmed_not_sellable = 1.0, undetermined = 0.0 |
| DS-F-99-0301 | FMTS, 1 unit | confirmed_not_sellable = 1.0, undetermined = 0.0 |
| DS-F-99-0308 | FG01 (13) + FMTO (1) | confirmed_not_sellable = 1.0, undetermined = 13.0 |
| DS-F-99-0309 | FG01, 15 units | undetermined = 15.0 (100%) |
| DS-F-99-0310 | FG01, 9 units | undetermined = 9.0 (100%) |
| DS-F-99-0311 | FG01, 14 units | undetermined = 14.0 (100%) |

The two checks used independent queries against the same table and produced **identical per-item,
per-warehouse quantities** (54 units total across the 6 items, matching CI101's division total in
both Check 1's and Check 2's rollups — see 4b). Check 1's item-level sellability determination
(QA/FMTS/FMTO not sellable, all else undetermined) is fully consistent with, and directly explains,
Check 3's own downgrade of its "SAME" verdicts to "SAME_BUT_UNDETERMINED": the FMTO/FMTS units are
independently confirmed not sellable by Check 1, and the FG01 units are independently kept
undetermined by Check 1, matching Check 3's caution not to assert sellability for FG01 either. **No
conflict found here — the two checks reinforce each other.**

### 4b. Check 1 vs. Check 2 — same universe, same snapshot?

**Quantities: exact agreement, high confidence.** Check 1's total in-scope stock (158,130 units,
all warehouses) equals the sum of Check 2's per-division rollup (`phaseD_check2_rollup_by_division.csv`:
157,179 + 95 + 796 + 54 + 4 + 2 = 158,130). The per-division breakdowns also match unit-for-unit
(PEM101 157,179/157,179; PEM103 95/95; PEM107 796/796; CI101 54/54; PEM102 4/4; PEM104 2/2). Both
checks are drawing the same total quantity from `Cube_Inventory_Exact` for the same 445-item scope.

**Snapshot description: a genuine inconsistency, reported per AGENTS.md Rule 4/9, not
reconciled.** Check 1 states the snapshot is a **single frozen batch, all rows timestamped within a
~72-second window on 2026-09-06**. Check 2 states its pull's rows carry **520 distinct timestamps
spanning 2026-09-06 and 2026-09-07**, and explicitly characterises `Cube_Inventory_Exact` as
**"a live, continuously-updated table, not a frozen snapshot"** whose totals are "not reproducible
byte-for-byte on a later run." Both checks say they ran on 2026-09-08. These two characterisations
of the same table cannot both be describing the identical pull: either the table refreshed with a
new batch between Check 1's and Check 2's queries (most likely, given Check 2 ran a two-table join
that would take longer and could have been run at a different moment than Check 1's), or one
Explorer's timestamp read is imprecise. **This synthesis does not reconcile which is correct — both
positions are reported as found.** Practically, it matters less than it might seem *only* because
the aggregate quantities came out identical to the unit despite the differing timestamp
description (4b above) — but that agreement is itself only reassuring for this specific pull pair,
not a guarantee for any future re-run, and Check 2's own report already warns that re-runs will not
match byte-for-byte. **Flagged as unresolved**, not treated as settled by the quantity match.

### 4c. Item coverage — "388 of 445" cited only by Check 1

Check 1 explicitly measured and reported that 388 of 445 in-scope items (87.2%) have at least one
row in `Cube_Inventory_Exact`, 57 have none. Check 2's report does not state this figure directly,
but its division rollup's `items` column sums to 445 (matching the full scope) and its total
quantity matches Check 1 exactly (4b) — consistent with, but not an independent confirmation of,
the 388/57 split, since Check 2 never reports how many of its 445 items have zero rows versus zero
summed stock (a row with `stock=0` and "no row at all" both yield qty 0 in Check 2's method, and
Check 2's report does not distinguish them). **No contradiction found, but this specific figure
(388/445) is confirmed only by Check 1, not independently cross-verified by Check 2 — reported as a
gap in cross-verification, not a conflict.**

### 4d. Conflicts and inconsistencies found between the three checks — summary

1. **Snapshot freshness/frozen-ness (Check 1 vs. Check 2), described in 4b above — the one genuine,
   unresolved inconsistency found by this synthesis.** Both positions and their evidence are stated
   above; no side is picked.
2. No other numerical or interpretive conflict was found between the three checks. Where they
   overlap (the 6 CI101 items, §4a; total/division stock quantities, §4b), they agree exactly.

---

## 5. Assumptions Phase E must record in `config.yaml` because the data could not answer

Each of these is a genuine gap identified by name in one or more of the three Explorer reports —
not filled in by this synthesis, per the Synthesizer's "does not gather new data" boundary.

1. **Which warehouse codes count as "sellable."** Check 1: confirmed-sellable is 0.00% of in-scope
   stock; 99.90% (157,972 of 158,130 units) sits in warehouse codes with no sellability evidence of
   any kind in `Cube_Inventory_Exact` (no status field exists in the schema — Check 1 §1). Phase E
   cannot compute a sellable-stock figure without either a business-confirmed stage→sellability
   mapping or an explicit, stated modelling assumption recorded here (e.g. "treat `FG01`/`FG02`/
   `FG11`/`FG21`/`WH21`/... as sellable by assumption"), since no query against any table this
   project has access to can resolve it (Check 1 §6, citing the movement-ledger's limited 34/128-
   and 6/34-item coverage as insufficient to extend).
2. **Annual holding-cost carrying rate.** No source exists anywhere in the data (Check 2 §7). The
   15-25% figure referenced elsewhere in `STATUS.md`/`CONVENTIONS.md` is explicitly an unverified,
   uncited figure, not a fact, and was not used in Check 2. A rate must be set as a configurable
   assumption before any annual carrying-cost figure (as opposed to the point-in-time capital-tied-
   up figure Check 2 produced) can be computed.
3. **Which unit-cost basis to use going forward.** Check 2 chose median-trailing-12-month, over
   most-recent-transaction, on reasoned but not statistically proven grounds (moderate confidence);
   the portfolio-level difference is 5.6% (THB 37.40M vs. THB 39.50M) and the top-10 list shifts by
   one item. Beyond the basis choice, **what the underlying `cost` column economically represents
   (landed cost, standard cost, material-only cost, etc.) was never checked** (Check 2 §9) — a
   deeper, unresolved question this project has no evidence to answer without business/finance
   input.
4. **How to handle the 5 items with stock but no cost record at all** (`FC-A-38-00203`,
   `IS-F-99-0365CE1`, `HS-F-99-3121`, `02-05-R-0001`, `TF-F-99-3107223B1`; 226 units total, Check 2
   §2). Currently carried as "value undetermined," neither zero nor dropped — Phase E needs an
   explicit rule (impute a proxy cost from a comparable item, exclude from value totals with a
   flagged caveat, or something else) since no cost record for these exists in `cube_Sale_APD`
   under any filter Check 2 tried.
5. **How to treat the 6 CI101 items with no stock at all**, especially `DS-F-99-0101` and
   `DS-F-99-0221`, which carry pending MPS/backlog demand (฿360,000 and ฿3,230,000, due 2026-10-20
   and 2026-12-25) with nothing currently on hand (Check 3 §"Practical conclusion," "What remains
   unresolved" item 1). Whether this reflects make-to-order fulfilment closer to the delivery date
   or a genuine supply gap cannot be distinguished from a single-snapshot inventory table — Phase E
   needs either a business answer or a stated modelling assumption for how to plan these two items'
   safety stock.
6. **Whether CI101 items sharing warehouse codes with PEM101 (that are ALSO shared with other
   divisions) should be pooled with PEM101's stock or kept separate.** Check 3's own stated
   position: co-location supports pooling as a *defensible reading*, but the shared-code caveat
   (`FG01`/`FMTO`/`FMTS` used by 3-4 of 6 divisions table-wide) means this is not proof of a
   dedicated PEM101 pool — Check 3 explicitly stops short of that stronger claim (Check 3 §"What
   remains unresolved" item 2: whether these codes are a shared pool by design or unintended
   commingling is undetermined). Phase E must record which reading it adopts as an assumption, not
   treat "pooled" as an established fact.
7. **PEM103's much lower undetermined-sellability share (46.3% vs. 94-100% elsewhere) is
   unexplained.** Check 1 reports it as an observed pattern only, explicitly declining to interpret
   it per its Explorer role boundary; this synthesis does not interpret it either. If Phase E treats
   divisions differently for sellability purposes, this pattern's cause should be understood first,
   not assumed to generalize or to be a fluke.
8. **The snapshot freshness/frozen-ness inconsistency between Check 1 and Check 2 (§4b/4d above)
   is unresolved.** Phase E should decide whether to treat `Cube_Inventory_Exact` as a frozen daily
   batch (Check 1's reading) or a continuously live table (Check 2's reading) before relying on any
   single pull as reproducible — this affects whether Phase E's own stock pull needs to be
   timestamped/frozen explicitly, the same way the demand series was frozen via `snapshot_pull_date`
   in Phase B.
9. **Target service level and stockout-cost proxy** — both already recorded as still-open in
   `STATUS.md` §8.5, reaffirmed here as directly load-bearing for Phase E's Max-Min calculation and
   not answered by any of the three Phase D checks (they were out of scope for all three, which
   were restricted to `Cube_Inventory_Exact`/`cube_Sale_APD`).
10. **Assembly time after parts arrive** — reaffirmed open in `STATUS.md` §8.1/8.5, not addressed
    by any Phase D check (none had scope to touch lead-time/production data), but directly needed
    alongside the sellable-stock assumption (item 1 above) for Phase E's total lead-time input.

---

## Confidence summary (all conclusions, in one place)

| Finding | Confidence | Source |
|---|---|---|
| Confirmed-sellable stock = 0.00%; undetermined = 99.90% | High (schema absence of evidence) | Check 1 §1, §4 |
| QA/FMTS/FMTO = not sellable | Confirmed at process level, carried from a prior (2026-09-02) investigation, not re-derived here | Check 1 §3, §5 |
| Total priced stock value THB 37,399,005.48 | High, internally cross-verified | Check 2 §5 |
| `cost` = line total, not unit cost | High, directly reproduced | Check 2 §0 |
| Median-12mo cost basis more robust than most-recent | Moderate (reasoned, not statistically proven) | Check 2 §1, §8 |
| 6/12 CI101 items with PEM101-tagged sales have stock, all SAME_BUT_UNDETERMINED | High (co-location fact); Moderate ("include in pool" as a reading) | Check 3 §"Verdict," §"Confidence levels" |
| Check 1 ↔ Check 3 per-item warehouse/sellability agreement | High, independently re-verified by this synthesis | §4a above |
| Check 1 ↔ Check 2 total-quantity agreement | High, independently re-verified by this synthesis | §4b above |
| Check 1 ↔ Check 2 snapshot frozen-vs-live description | **Conflict, unresolved** — both positions stated, no side picked | §4b, §4d above |
| PEM103's low undetermined share cause | Unexplained — not interpreted by Check 1 or this synthesis | Check 1 §4 |

---

## Deliverables

This report: `output/summary/phaseD_synthesis_report.md`. No CSVs produced (this role does not
gather new data). No code, config, or pipeline files modified.
