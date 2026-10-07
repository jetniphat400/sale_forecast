# Task 2 (Explorer + Validator) — Classifying the no-history / no-sale items in the 128-item scope

**Role**: combined Explorer + Validator, one of three parallel agents on this Phase B open
item ("the 16 items with no history and 15 with no sales" per `STATUS.md`). Per `AGENTS.md`,
this agent does not decide anything — findings and options are presented for a human /
Synthesizer to act on. `STATUS.md` was NOT modified by this task. No git command was run.

Every figure below cites the exact script/query that produced it. Supporting raw CSVs are in
`output/summary/task2_q*.csv`, `task2_master_evidence_16items.csv`,
`task2_per_item_classification_final.csv`, `task2_pricelist_*.csv`, `task2_schema_*.csv`.
Scripts: `src/task2_no_history_investigation.py`, `src/task2_pricelist_version_check.py`,
`src/task2_explore_schema.py`, `src/task2_build_classification.py`.

---

## 1. Reconciliation: the true count is 16, NOT 31 — the brief's premise does not hold

**Confirmed, high confidence.** The task brief hypothesized 31 items (16 with zero rows under
the standard filter, plus "15 more with rows present but zero total qty/sale in the 2024-01-01+
window"). A fresh live query finds this second group **does not exist**.

- Live query (`src/task2_no_history_investigation.py`, Q1): grouping the 128-item scope
  under the project's standard filter (`division='PEM101'`, `revenue_type='Omni Channel'`,
  `status IN ('Actual','MPS')`, `createDate >= '2024-01-01'`), **112 of 128 items have at
  least one row; 16 have zero rows.** (`output/summary/task2_q1_std_filter_per_item.csv`)
- Among the 112 items that DO have rows, the **minimum** `SUM(qty)` is 1.0 and the minimum
  `SUM(sale)` is 720.0 — **no item has rows present that net to zero.** There is no
  "15 more" group; every item either has zero rows under the filter, or has a strictly
  positive sum.
- Cross-checked against `output/summary/part1_category_scope_all_codes.csv` (from
  `src/load_data_full.py`'s `has_any_history` flag, which checks for ANY row in
  `cube_Sale_APD` under NO filter at all — any division, any revenue_type, any status, any
  date): **15 of 128 items have zero rows anywhere in the table, full stop** (Q2,
  `output/summary/task2_q2_any_activity_per_item.csv`). This is a strict subset of the 16
  above.
- The one item present in the 16 but NOT in the 15 is `EEE-F-FL-5920-353-02600` — it DOES
  have rows in `cube_Sale_APD`, just entirely under `revenue_type = 'Tendering'`, not `'Omni
  Channel'` (confirmed directly: `output/summary/task2_q2b_any_activity_breakdown.csv` shows
  2 rows under `division=PEM101` and 2 under `division=PSS`, all 4 tagged `Tendering`,
  2025-2026, 24,000 qty / ~3.05-3.50M THB each).
- This exactly reconciles with the two existing leads named in the brief:
  `output/summary/rule_part7_no_history_items.csv` (16 items, "NoSale" classification at
  Item level) and `output/summary/task3_per_item_classification.csv`'s "15 with zero sales
  history anywhere" — both are now independently re-derived from a live query, not merely
  trusted. The older 68-item pilot's `output/summary/excluded_items_no_history.csv` (10 items)
  is confirmed a proper subset of the 16 (`set(old10) - set(new16) == {}`).

**Conclusion**: the task scope is **16 items**, not 31. This report classifies all 16.

---

## 2. Method and its limits

- **Standard filter** (per `config/config.yaml`, used throughout this project):
  `division='PEM101'`, `revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
  `createDate >= '2024-01-01'`.
- **Pricelist version evidence** (`src/task2_pricelist_version_check.py`): reads ALL sheets
  in `reference/pricelist.xlsx`, visible and hidden, via `openpyxl`'s `ws.sheet_state`
  (not filtered to `"visible"`, unlike `pricelist_reader.load_visible_product_rows()`).
  **Limit, stated per the task brief**: the workbook has no date field for when a row was
  added — this method can only show "already existed in the prior (Version1) sheet" vs. "new
  to the current (Version2) sheet," never a calendar date. **Finding: all 16 items appear in
  BOTH the hidden `PEM101-Version1` sheet AND the visible `PEM101-Version 2` sheet.** None are
  new to the current pricelist version — confirmed directly
  (`output/summary/task2_pricelist_version_evidence_16items.csv`). Separately noted: PEM101's
  Version1 and Version2 sheets are otherwise identical (171 codes each) except one unrelated
  code substitution (`EEE-F-FC-1040011002` → `EEE-F-FC-1040010002`, one of this project's own
  three pilot focus codes) — not one of the 16.
- **Tables checked for ANY activity** (schemas confirmed live, not assumed —
  `output/summary/task2_schema_*.csv`): `cube_Sale_APD` (no filter, i.e. any
  division/revenue_type/status/date), `Cube_CES` (`ItemCode`, `Status`, `CtrDate`,
  `ForecastDelDate`/`ActualDelDate`, `PlanQty`/`ActualQty`/`BacklogQty`, `ManuDivision`,
  `SaleDivision`, `RevenueType`), `cube_inventory_tran`, `Cube_Inventory_Exact`, and
  `Cube_Quotation` (confirmed the actual quotation table by name — `Cube_Quotation_Customer`
  and `Cube_Quotation_PSP` also exist; `Cube_Quotation` is the one with `itemcode`,
  `division`, `quotation_status`, matching STATUS.md's reference).
- **A genuine data-quality finding, not previously documented at this granularity**:
  `Cube_CES.Status` has **14 distinct values table-wide** (`P1`,`P2`,`P3`,`T1`,`T2`,`T3`,
  `Actual`,`Backlog`,`Cancel`,`F`,`Y`,`N/A`,`None`/blank — confirmed,
  `output/summary/task2_q3b_cube_ces_distinct_status.csv`), not only `Actual`/`Backlog` as
  the 3 cases previously checked in STATUS.md's pilot-scope work showed. This task only needed
  `Actual` and `Backlog` specifically (per the task's own definition of "open contract/
  backlog"), so it does not block classification here, but the meaning of `P1`/`P2`/`P3`
  (pipeline/quotation stage numbers, inferred from context — `ActualQty` is always NULL on
  these rows and `ForecastDelDate` is populated with no `CtrDate`, consistent with an
  unsigned quotation/opportunity stage) and `T1`/`T2`/`T3`/`Cancel`/`F`/`Y` is **not confirmed
  from data** — flagged as an open question for the business/data team, not guessed.
- **RevenueType is blank/NULL for a meaningful share of Cube_CES's real "Actual" rows** for
  these 16 items (see per-item table) — a genuine data gap, not an inference. Where blank,
  this report says so explicitly rather than assuming it means "a different channel."
- **`cube_inventory_tran.transtype` codes** (`B`, `N`, `150`, `151`, `A`, seen for
  `FC-A-38-00203`) are not decodable from the schema or any documentation found in this
  investigation — flagged, not guessed at.

---

## 3. Per-item table (all 16 items)

Full machine-readable version: `output/summary/task2_per_item_classification_final.csv`.
Raw supporting evidence: `task2_q3c_cube_ces_raw_rows_16items.csv` (every Cube_CES row for
all 16 items), `task2_q6c_quotation_raw_rows_6items.csv` (every Cube_Quotation row for the 6
items that have one), `task2_q5_inventory_exact_per_item.csv` (every warehouse stock row).

| itemcode | Type | Cube_CES: Actual (n, lifetime qty, last date) | Cube_CES: pipeline (P/T stage) rows | Current stock (Y/N, qty) | Open Backlog (Cube_CES Status='Backlog') | Cube_Quotation (Y/N, last date) | Classification | Confidence |
|---|---|---|---|---|---|---|---|---|
| `EEE-F-FL-1040030100` | Fuse link | 0 | 0 | No stock ROW at all (not even zero) | No (no CES row at all) | No | (d) Listed but never sold | High |
| `HS-F-99-1241H03` | Surge Arrester | 0 | 0 | No stock ROW at all | No (no CES row at all) | No | (d) Listed but never sold | High |
| `HS-F-99-0181` | Surge Arrester | 0 | 2 (2024, 2026) | Y, 0 (2 warehouses) | No | Y, 2026-07-13 (qty 1, named customer) | (d) Listed but never sold (live unconverted quote) | Moderate |
| `HS-F-99-1181` | Surge Arrester | 0 | 4 (2024-2026) | Y, 0 (1 warehouse) | No | Y, 2026-07-22 (qty 9) | (d) Listed but never sold (live unconverted quote) | Moderate |
| `HS-F-99-1211H22` | Surge Arrester | 0 | 1 (2024-12-19) | No stock ROW at all | No | No | (d) Listed but never sold | Moderate-High |
| `HS-F-99-3031` | Surge Arrester | 0 | 2 (2025-04) | Y, 0 (1 warehouse) | No | No | (d) Listed but never sold | Moderate |
| `EEE-F-FL-5920-353-01100` | Fuse link | 6, 54,000 units, 2022-06-30 (2 rows tagged Omni Channel/PEM101, 20,000 units) | 2 (2023, 2024) | Y, 0 (1 warehouse) | No | No | **Cannot classify cleanly** — closest (c) apparent dormancy since 2022; excluded by the **date window**, not division/channel | Moderate |
| `EEE-F-FL-5920-353-01600` | Fuse link | 3, 12,503 units, 2022-05-11 (RevenueType blank throughout) | 2 (2023, 2024) | Y, 0 (3 warehouses) | No | No | (b)-leaning, not fully confirmed (channel unconfirmed) | Low-Moderate |
| `EEE-F-FL-5920-353-02600` | Fuse link | 10, 88,500 units, 2026-04-24 (4 recent rows explicitly Tendering) | 2 (2023, 2024) | Y, 0 stock but FMTO warehouse shows 17,000 reserved / -17,000 available | No | Y, 2026-01-21, status=Success x4 (Tendering, 2 named customers [redacted]) | **(b) Sold, exclusively via Tendering channel** | **High** |
| `EEE-F-FL-5920-353-06600` | Fuse link | 4, 18,500 units, 2023-06-30 (2 rows explicitly Tendering) | 3 (2023, 2024, 2026-09-18*) | Y, 0 (1 warehouse) | No | Y, 2026-08-18 (qty 1, Omni Channel, unconverted) | (b) Sold via Tendering (2023) + live unconverted Omni-Channel quote | Moderate-High |
| `FC-A-38-00203` | Fuse Holder | 1, 6 units, 2022-12-19 (SaleDivision=PEM105, RevenueType blank) | 1 (2025-05-31) | **Y, 150 (WH21, available 101)** | No | No | (b)-leaning, not fully confirmed | Moderate |
| `HS-F-99-1151` | Surge Arrester | 2, 12 units, 2021-11-30 (SaleDivision=PEM105, RevenueType blank) | 4 (2024-2025) | Y, 0 (5 warehouses) | No | No | (b)-leaning, not fully confirmed | Low-Moderate |
| `HS-F-99-2091N` | Surge Arrester | 2, 6 units, 2021-05-27 (1 row ManuDivision=PMW101 — a genuinely different division) | 5 (2025-2026) | Y, 0 (1 warehouse) | No | Y, 2026-07-22 x2 (2 named customers [redacted]) | **Cannot classify cleanly** — mixed cross-division + live-pipeline evidence | Low-Moderate |
| `HS-F-99-3121` | Surge Arrester | 3, 19 units, 2022-04-20 (earliest row, 2020, tagged Omni Channel/PEM101) | 2 (2024, 2025) | **Y, 12 (warehouse "NCRM")** | No | No | **Cannot classify cleanly** — closest (c) apparent dormancy; excluded by the **date window**, not channel | Moderate |
| `HS-F-99-3331` | Surge Arrester | 1, 6 units, 2021-05-19 (ManuDivision AND SaleDivision = PPD101) | 4 (2023-2025) | Y, 0 (1 warehouse) | No | No | **(b) Sold under a different division (PPD101)** | Moderate |
| `HS-F-99-3361` | Surge Arrester | 2, 6 units, 2022-04-20 (RevenueType blank) | 4 (2024-2026) | Y, 0 (3 warehouses) | No | Y, 2026-07-17 x2 (2 named customers [redacted]) | **Cannot classify cleanly** — mixed same-division/blank-channel + live-pipeline evidence | Low-Moderate |

\* `EEE-F-FL-5920-353-06600`'s 2026-09-18 pipeline `ForecastDelDate` is after today
(2026-09-04) — a live, still-open forecast entry, not a data anomaly.

**Every item's `Cube_CES` `Backlog` count is 0** (`output/summary/task2_q3_cube_ces_per_item.csv`)
— none of the 16 currently sit in an open backlog by this project's own definition of that
term. Two items (`EEE-F-FL-1040030100`, `HS-F-99-1241H03`) have zero `Cube_CES` rows at all, so
"no backlog" is really "no contract record of any kind," stated separately from the 14 items
that have some `Cube_CES` history but no `Backlog`-status row specifically.

### Classification counts (n=16)
- **(d) Listed but never sold**: 6 items — `EEE-F-FL-1040030100`, `HS-F-99-1241H03`,
  `HS-F-99-0181`, `HS-F-99-1181`, `HS-F-99-1211H22`, `HS-F-99-3031`.
- **(b) Sold outside this project's filter** (confirmed or leaning): 6 items —
  `EEE-F-FL-5920-353-02600` (high confidence), `EEE-F-FL-5920-353-06600` (moderate-high),
  `HS-F-99-3331` (moderate), `EEE-F-FL-5920-353-01600`, `FC-A-38-00203`, `HS-F-99-1151`
  (all low-to-moderate, channel not fully confirmed).
- **Cannot classify cleanly into any one of the 4 buckets, evidence genuinely mixed**:
  4 items — `EEE-F-FL-5920-353-01100`, `HS-F-99-3121` (both: real historical Omni-Channel/
  PEM101 demand exists, but predates the 2024-01-01 window — a scope-boundary/recency effect
  distinct from being sold in a different channel), `HS-F-99-2091N`, `HS-F-99-3361` (both:
  a mix of unconfirmed-channel past sales plus live, currently-unconverted Omni-Channel
  quotation activity from named customers).
- **(a) New and not yet sold, or (c) discontinued, as a clean standalone label**: **0 items.**
  Per the pricelist-version evidence (Section 2), none of the 16 are new to the current
  pricelist version, which weighs against a pure "(a) new" reading for any of them, though it
  cannot rule out "new to the market since Version1 was created" since Version1 itself carries
  no date. No item shows unambiguous, data-confirmed discontinuation (no status field anywhere
  says "discontinued" or similar) — where dormancy is suspected, it is labelled "cannot
  classify cleanly, closest (c)... NOT confirmed," never asserted as fact.

---

## 4. Phase 4 options per class (presented, not decided — per `AGENTS.md`)

### Class (d) — Listed but never sold (6 items)
- **Borrow the same Product Type's demand profile**: weakly justified. For the 2 fully-blank
  items (no trace anywhere), there is zero item-specific evidence to weigh against a Type
  average, but the Type-level average (built from items selling in the tens to tens of
  thousands of units) is likely a poor size proxy for something with a 100% non-conversion
  history. For the 4 items with live 2024-2026 quotations, the actual quoted quantities are
  1-9 units — far below a typical Type-level average — so borrowing risks large
  over-provisioning.
- **Manual placeholder set by the business**: the most defensible option for all 6, and
  especially for the 4 with live pipeline activity — a small buffer sized to the observed
  quotation quantities (1-9 units) reflects the "listed, occasionally quoted, never won"
  reality better than either alternative.
- **Exclude with justification**: defensible for the 2 fully-zero-trace items
  (`EEE-F-FL-1040030100`, `HS-F-99-1241H03`) if the business confirms these are effectively
  inactive listings. Less defensible for the 4 items with live 2024-2026 quotes
  (`HS-F-99-0181`, `HS-F-99-1181`, `HS-F-99-1211H22`, `HS-F-99-3031`) — excluding them risks a
  stockout if, e.g., `HS-F-99-1181`'s qty-9 quote (forecast_date 2026-08-28) converts.

### Class (b) — Sold outside this project's filter (6 items, varying confidence)
- **Borrow the same Product Type's demand profile**: not well justified — every one of these
  6 items already has its OWN historical quantity data in `Cube_CES` (ranging from 6 units to
  88,500 units lifetime), so substituting an unrelated Type average would discard usable,
  item-specific evidence that this task has already retrieved.
- **Manual placeholder**: partially wasteful for the same reason — a placeholder ignores
  directly available quantitative history for these items specifically.
- **Exclude with justification**: correct for THIS project's Omni Channel-specific forecast
  (these items genuinely belong to a different scope), but **not** correct for Phase 4
  inventory planning as a whole — `STATUS.md`'s own existing cross-division finding
  (₿60.6 million currently filtered out) already establishes that inventory is shared across
  divisions/channels regardless of which one recorded the sale.
- **A fourth option beyond the three listed in the brief, worth flagging for the human to
  weigh**: build a Phase-4-specific demand estimate directly from each item's own `Cube_CES`
  history (already retrieved here), since it is item-specific, already exists, and is more
  grounded than any of the three generic options above for this class specifically.

### "Cannot classify cleanly" (4 items)
- **Borrow the same Product Type's demand profile**: weakest fit for `EEE-F-FL-5920-353-01100`
  and `HS-F-99-3121` — both have their OWN real, evidenced pre-2024 Omni-Channel/PEM101
  history (20,000 and 13 units respectively on their largest confirmed orders); using their
  own (if old) history is more grounded than an unrelated Type average. For `HS-F-99-2091N`
  and `HS-F-99-3361`, actual historical/quoted scale is single-digit-to-low-double-digit
  units — a Type-level average would likely overstate demand by orders of magnitude.
  Borrowing may still be reasonable if the business judges the pre-2024 history too stale to
  trust on its own.
- **Manual placeholder**: reasonable given the genuine ambiguity, ideally sized to each item's
  own historical order sizes (up to 20,000 units for `EEE-F-FL-5920-353-01100`; single digits
  to low teens for the other 3) rather than a generic Type-level number.
- **Exclude with justification**: weakest option for these 4 specifically — each has direct
  evidence of real (if old, small, or channel-ambiguous) demand; excluding ignores confirmed
  evidence, unlike the class-(d) items where evidence of any real demand is genuinely absent
  or limited to unconverted quotes.

---

## 5. What the data could not resolve — stated per the stopping rule

- **`Cube_CES.Status` values `P1`/`P2`/`P3`, `T1`/`T2`/`T3`, `Cancel`, `F`, `Y`, `N/A`**: their
  precise business meaning is not confirmed from data. Inferred (not confirmed) that
  `P2`/`P3` represent pre-contract quotation/opportunity stages, based on the pattern that
  every such row has `ActualQty=NULL` and a populated `ForecastDelDate` with no `CtrDate` —
  but this is an inference, not a verified fact. **Would need**: the CRM/ERP or sales
  operations team to confirm what each status code means.
- **Blank/NULL `RevenueType` on multiple confirmed `Cube_CES` "Actual" rows** (items
  `EEE-F-FL-5920-353-01600`, `FC-A-38-00203`, `HS-F-99-1151`, one row each of `HS-F-99-2091N`
  and `HS-F-99-3361`): cannot confirm whether these historical sales were genuinely outside
  Omni Channel or simply untagged. **Would need**: the sales operations team to confirm
  whether blank `RevenueType` in `Cube_CES` has a specific meaning (e.g., a legacy record
  predating the field's use).
- **`cube_inventory_tran.transtype` codes `B`, `N`, `150`, `151`, `A`** (seen for
  `FC-A-38-00203`, 126 rows spanning 2019-2026): cannot confirm which of these represent real
  sales issues versus internal transfers, scrap, or samples. **Would need**: the
  warehouse/ERP team to decode these transaction-type codes.
- **Warehouse code `NCRM`** (holding `HS-F-99-3121`'s 12-unit current stock): meaning not
  confirmed from the schema. **Would need**: the warehouse team to confirm what this
  warehouse code represents (a normal stocking location vs., e.g., non-conforming/return
  material).
- **Whether any of the "cannot classify cleanly" or "(b)-leaning, not fully confirmed" items
  are formally discontinued**: no status field anywhere in the tables checked records product
  discontinuation. **Would need**: direct confirmation from the product/business team.
