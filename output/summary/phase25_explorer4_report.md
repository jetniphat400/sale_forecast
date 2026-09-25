# Phase 25 — Explorer 4: `cube_inventory_tran` physical warehouse movement, PEM107

**Role**: Explorer (1 of 4 parallel, independent agents). **Target node**: Q10, PEM107 branch
(PROJECT_GRAPH.md) — testing the business-confirmed (level A, DATA_MAP.md §7) claim that PEM107's
Tendering and Omni Channel production/stock were shared and then separated around the middle of
2026. This agent's angle: physical warehouse movement history in `cube_inventory_tran` — the one
inventory table in this project that is a genuine historical ledger (QtyIn/QtyOut), not a
snapshot (DATA_MAP.md §1). Independent of, and not coordinating with, the other 3 parallel agents
(production-batch linkage, categorical-column changes).

**AGENTS.md rule 3 (stopping rule) applied**: coverage found in Step 1 is far too thin to say
anything meaningful. Per the task's own instruction, this agent STOPPED after Step 1 and did not
proceed to Steps 2–3 (monthly movement by warehouse/route, May-2026 shift test). This is reported
as the complete, valid answer for this angle, not as an incomplete task.

## Method

- Item scope: `output/data/phaseI_combined_scope_351items.csv`, `division == 'PEM107'` —
  **136 items**, pricelist-authoritative (confirmed by direct count on the file, this task).
- Schema: confirmed via a prior task's own `INFORMATION_SCHEMA.COLUMNS` pull, already on disk at
  `output/summary/task2_schema_cube_inventory_tran.csv` (not re-queried, to keep this task's DB
  access to one connection attempt) — columns include `itemcode`, `trans_date`, `transtype`,
  `orders`, `warehouse`, `QtyIn`, `QtyOut`, `uom`, `location`, plus `company`, `costcenter`,
  `ourref`, `project`, `descriptions`, `Avgprice`, `Debit`, `Credit`, `gl_code`, `gl_desc`,
  `item_desc`, `timestamp`.
- One database session (one connection attempt, per task instructions): a single query —
  `SELECT itemcode, trans_date, transtype, orders, warehouse, QtyIn, QtyOut, uom, location FROM
  cube_inventory_tran WHERE itemcode IN (<136 PEM107 codes>)` — no other SQL-level filter, exactly
  per the task's Step 1 instruction. Script: `phase25_explorer4_pull.py` (run from the session
  scratchpad; output written to the files below). Login succeeded; the query ran once, no retry
  needed.

## Step 1 — Coverage check (confirmed from data, this task)

| Figure | Value | Source |
|---|---|---|
| PEM107 scope items | 136 | `phaseI_combined_scope_351items.csv`, this task's count |
| Items present at all in `cube_inventory_tran` | **24 / 136 (17.6%)** | `phase25_explorer4_coverage_summary.csv` |
| Total rows returned | **47** | same |
| Date range | **2021-12-14 to 2021-12-14 (a single calendar day)** | same, `trans_date` min=max |
| Rows from 2025-01-01 onward | **0** | same |
| Items with any row from 2025-01-01 onward | **0** | same |
| Rows from 2026-05-01 onward | **0** | same |
| `QtyIn` non-null rows | **0 / 47** | direct recount on the pulled CSV, this task |
| `QtyOut` non-null rows | **0 / 47** | direct recount on the pulled CSV, this task |
| `orders` non-null rows | **0 / 47** | direct recount on the pulled CSV, this task |
| `transtype` values present | only `'N'` | same |
| `warehouse` codes present | `FG` (padded), `FG01`, `FG02` only | same |

All figures above are **directly confirmed from data** (V2 — recomputed twice independently in
this task: once during the pull script's own logged summary, once again by re-reading the
resulting CSV in a separate command). No figure here is inferred.

### My stated threshold for "too thin," and why

I treat coverage as too thin to proceed if **either** of these holds: (a) fewer than half the
136-item scope has any row at all, or (b) the date range does not reach into the 2025-01 to
2026-09 analysis window (the window the task asks about, including the May-2026 shift point).
Both conditions are true here, by a wide margin:

- Item coverage is 17.6% (24/136) — far below the 50% bar.
- The entire pull is **one single date, 2021-12-14** — nearly 3.5 years before the window of
  interest even starts, and over 4 years before the May-2026 shift point this task is testing.
  Zero rows exist anywhere in 2025 or 2026, for any of the 136 items.

Beyond thin coverage, the 47 rows that do exist carry **no usable quantity data at all**:
`QtyIn` and `QtyOut` — the two fields DATA_MAP.md §1 identifies as what makes this table a
genuine movement ledger rather than a snapshot — are null in every single row pulled. `orders`
(a candidate "route"/document-reference field) is null in every row too. The only warehouse
codes that appear are the shared `FG01` and two codes not on PEM107's confirmed
exclusive/shared list at all (`FG` padded-blank, `FG02`) — **none of PEM107's four exclusive
sellable codes (FG27, WH22, WH24, FG22) appear even once** in this pull.

**This is not merely thin — for PEM107's 136-item scope, `cube_inventory_tran` supplies
essentially no usable movement history at any point covered by this project's analysis window,
and what little it does supply (47 rows, one day in 2021) carries no quantity or order-reference
data.** Confidence: **V2** for the coverage figures themselves (directly queried, then
independently recounted from the saved CSV). This does not mean the table is empty
project-wide — DATA_MAP.md §1 records 2.9M rows table-wide across 2007-2026 for the whole
database — it means these specific 136 PEM107 items are almost entirely absent from it.

## Per AGENTS.md rule 3 (stopping rule): STOPPING HERE

Per this task's own instructions, coverage this thin means I report the coverage figures and
**stop — I did not proceed to Step 2 (monthly QtyIn/QtyOut by warehouse/route) or Step 3 (May-2026
shift test)**. There is no meaningful monthly series to build: zero rows exist in the entire
Jan-2025-to-present window for any of the 136 items, so no warehouse/route pattern — before, at,
or after May 2026 — can be observed from this table for this item scope. Any attempt to describe
a "shift around May 2026" from zero rows would be guessing, which AGENTS.md rule 1 forbids.

## What this does and does not say about the May-2026 separation claim

- It does **not** confirm or contradict the business's "separated around the middle of 2026"
  claim (DATA_MAP.md §7, level A) — there is simply no physical-movement signal here to test it
  against, in either direction.
- It does **not** contradict the other angle already recorded in DATA_MAP.md §7 (production-batch
  linkage via `cube_final.jobno`/`Cube_CES.OLMJobCode`, which found a change point at
  October/November 2024, not May 2026) — that finding used a different table and mechanism
  entirely; this agent's null result neither supports nor undermines it.
- It is a **negative/gap finding about this table for this item scope**, not a finding about
  PEM107's operations. Per AGENTS.md rule 3, the correct action on a search this thin is to stop
  and name the gap, not to substitute inference for missing data.

## What would be needed to test this angle properly (gap to name, per rule 3)

- Confirmation of which itemcode format/level `cube_inventory_tran` actually tracks for PEM107 —
  the 24 items that DID match used the exact pricelist code, so the join mechanism itself works;
  the gap is that most PEM107 finished-goods codes and virtually all 2025-2026 activity simply
  are not recorded as ledger movements in this table, for reasons this task cannot determine from
  the data alone (a different logging system for PEM107, a different itemcode granularity used in
  practice, or the table genuinely not being used to track PEM107's finished-goods movement).
- If the business or IT can confirm which table (if any) logs PEM107's day-to-day physical
  warehouse movement between Tendering and Omni Channel stock, that table — not
  `cube_inventory_tran` — would be the one to re-run this test against.

## Files written (this task, prefix `phase25_explorer4_`)

- `phase25_explorer4_raw_pull.csv` — all 47 raw rows (no PII: only itemcodes, dates, warehouse
  codes, and Thai-language physical building/location descriptors such as "BUILDING6",
  "FG-อาคาร7"; no customer names, contract IDs, or employee names).
- `phase25_explorer4_per_item_rowcounts.csv` — row count per itemcode (24 rows).
- `phase25_explorer4_coverage_summary.csv` — the one-row coverage summary table above.
- `phase25_explorer4_warehouse_counts_all.csv`, `phase25_explorer4_transtype_counts_all.csv` —
  distinct-value counts across the full (thin) pull.

## Verdict

**Coverage summary**: 24 of PEM107's 136 pricelist-scope items (17.6%) appear at all in
`cube_inventory_tran`; only 47 rows total; every row falls on a single date, 2021-12-14; zero rows
fall anywhere in the Jan-2025-to-present analysis window; `QtyIn`, `QtyOut` and `orders` are null
in all 47 rows; none of PEM107's four exclusive sellable warehouse codes (FG27, WH22, WH24, FG22)
appear. **Confidence: V2** (directly queried once, independently recounted from the saved output).

**Whether a warehouse/route shift appears around May 2026**: **Cannot be determined from this
table for this item scope — no data exists in or near that window to check.** Per the task's own
stopping rule, this agent stopped after the Step 1 coverage check and did not attempt Steps 2-3.
This is a reported data gap, not a negative finding about PEM107's operations, and it neither
confirms nor contradicts the business's "separated ~mid-2026" claim or the other angle's
"change point at Oct/Nov 2024" finding (DATA_MAP.md §7) — it simply has nothing to test either
against.
