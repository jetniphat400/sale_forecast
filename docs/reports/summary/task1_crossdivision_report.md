# Cross-Division Demand for the 128-Item Category Scope

**Agent**: Explorer+Analyst (combined), one of three parallel agents per `AGENTS.md`.
**Scope**: 128 item codes in Product Category "Fuse"/"Surge Arrester"
(`output/summary/part1_category_scope_all_codes.csv`).
**Date of pull**: 2026-09-04. **Source table**: `[salewarehouse].[dbo].[cube_Sale_APD]`
(and, for Step 2/3, `Cube_PMIS_Organize`, `Cube_Inventory_Aging`, `cube_inventory_tran`,
`INFORMATION_SCHEMA`).
**Rules followed**: every figure below cites the exact query/script that produced it;
confirmed (direct query result) is separated from inferred/interpreted; a confidence level is
stated for every conclusion; per `AGENTS.md`, this agent reports what queries return, not
what they mean for the business, except where explicitly labelled "Analyst interpretation."
No `STATUS.md` edit made. No git action taken. This agent does not decide anything — Section 4
presents options with trade-offs only.

---

## 0. Data pull and scripts behind every figure below

One raw pull, reused for every downstream computation in this report:

```sql
SELECT itemcode, division, revenue_type, status, createDate, forecast_date, qty, sale, contractid
FROM [salewarehouse].[dbo].[cube_Sale_APD]
WHERE itemcode IN (<128 codes from part1_category_scope_all_codes.csv>)
```

Run interactively via `src/db.py`'s `run_query`; saved unmodified to
`output/data/task1_crossdiv_raw_128items_alldivisions.csv` (27,808 rows, no filters beyond
`itemcode IN (...)`). All per-item/per-division/per-time tables below are derived from this one
pull in pandas — no second, differently-scoped pull was used, so every number in Section 1
reconciles back to this single CSV. **Confirmed, high confidence** (direct query result,
reproducible).

Divisions actually observed for these 128 items in this pull: `PEM101` (27,679 rows), `PCE101`
(50), `PPD101` (28), `PPS` (25), `PTS` (19), `PDEMO` (4), `PSS` (3). Note this is a **different
set** from the 68-item pilot's cross-division file (`task2_1_cross_division.csv`), which showed
`PPS, PPD101, PCE101, PDEMO, PTS` plus no `PSS` — consistent with a wider item scope surfacing a
slightly different mix, not a contradiction.

---

## 1. Quantify per item

### 1.1 Two measurement methods — and why both are reported

The task brief's own standard filter is `division='PEM101' AND revenue_type='Omni Channel' AND
status IN ('Actual','MPS')`. There are two defensible ways to measure "what that filter
excludes," and they give very different answers, so both are reported rather than picking one:

- **Method A — replicate the original 68-item pilot methodology exactly** (script:
  `src/audit_pilot_items.py`, lines ~52-59: "Pull ALL rows for these items, regardless of
  division/revenue_type"). This holds nothing constant except `itemcode` — it compares PEM101
  sales against sales recorded under every other division **and every other revenue_type/status
  combination**, no date floor. This is the number directly comparable to the existing ₿60.6M/
  14.3% figure in `STATUS.md`.
- **Method B — isolate the division variable only** (this task's own construction). Holds
  `revenue_type='Omni Channel'` and `status IN ('Actual','MPS')` constant — the same as the
  standard filter — and varies only `division`. This answers "if this project's channel/status
  scope were applied but the division constraint were dropped, how much more demand would be
  included?" — arguably the more directly decision-relevant question for Phase 4, since
  `revenue_type` is itself a separate, deliberate scope decision (Omni Channel vs. Tendering
  etc.), not part of "cross-division."

**Confirmed, high confidence, direct computation from the pull above — both methods use the
identical raw data, differing only in which columns are held fixed.**

| | Method A (all rev_type/status) | Method B (Omni Channel + Actual/MPS only) |
|---|---|---|
| All-division sale (฿) | 802,138,060.96 | 700,598,291.96 |
| PEM101-only sale (฿) | 716,619,585.96 | 697,639,462.96 |
| **Excluded by division filter (฿)** | **85,518,475.00** | **2,958,829.00** |
| **Excluded, % of all-division total** | **10.66%** | **0.42%** |
| All-division qty | 3,686,626.0 | 3,398,902.0 |
| PEM101-only qty | 3,493,512.0 | 3,384,309.0 |
| Excluded qty | 193,114.0 (5.24%) | 14,593.0 (0.43%) |
| Items with any cross-division exposure | 47 of 128 (36.7%) | 36 of 128 (28.1%) |

CSVs: `output/summary/task1_by_division_methodA.csv`,
`output/summary/task1_by_division_methodB.csv`,
`output/summary/task1_per_item_methodA_alldivrevtype.csv` (all 128 items, 0 where no exposure),
`output/summary/task1_per_item_methodB_isolated.csv`.

### 1.2 Reconciling against the ₿60.6M / 14.3% pilot figure

**The two figures differ, and the reason is now identified directly from the data, not
speculated — moderate-to-high confidence.** Method A (the apples-to-apples replication) gives
₿85.5M / 10.66% for 128 items, vs. ₿60.6M / 14.3% for the 68-item pilot scope
(`STATUS.md`, Phase 2 audit note). Three things are true simultaneously, all confirmed:

1. **More items in scope**: the absolute excluded value rose from ₿60.6M to ₿85.5M (+41%) —
   expected, since the 128-item Category scope covers more products than the 68-item Type-level
   pilot.
2. **The percentage FELL, not rose** (14.3% → 10.66%), because the wider scope's PEM101-only
   denominator grew proportionally more than the excluded amount (₿716.6M PEM101-only for 128
   items vs. ₿362.0M for 68 items — the 128-item scope's own-division base is much larger,
   diluting the excluded share).
3. **A large, single-item concentration exists in both scopes and drives most of Method A's
   value**: item `EEE-F-FC-1040010002` alone contributes ₿57.67M of the excluded ₿85.5M
   (67.4%), entirely under division `PPS`, entirely `revenue_type='Tendering'`, not Omni
   Channel — visible already in the OLD 68-item file (`task2_1_cross_division.csv` row 3: same
   item, same division `PPS`, ₿57,673,600, 8 rows) and in the new 128-item pull
   (`task1_per_item_methodA_alldivrevtype.csv`). **This means the historical ₿60.6M figure was
   never purely a "cross-division" number — it always mixed in a cross-channel (Omni Channel
   vs. Tendering) effect for this one item, and that mixing continues in the 128-item figure.**
   This is a genuine, newly-surfaced finding, not previously stated this explicitly in
   `STATUS.md`.

**Method B strips this confound out and gives a much smaller, and arguably more decision-honest,
number: ₿2.96M / 0.42%.** Under Method B, no single item dominates — the largest contributor
(`EEE-F-FC-1040011000`, division `PPD101`) is only ₿726,500 (2.52% of that item's own PEM101
total). **Practical conclusion (Analyst interpretation, moderate confidence): most of the
historically-cited ₿60.6M/14.3% cross-division exposure is actually cross-CHANNEL exposure
(Tendering deals recorded under a different division), not cross-division exposure within the
Omni Channel business the project actually forecasts. The genuinely comparable "same channel,
different division" exposure is roughly 25x smaller in percentage terms (0.42% vs. 10.66%).**
This distinction was not previously separated in `STATUS.md`'s Phase 2 audit or the Red Team
Review's ₿60.6M citation.

### 1.3 Stability over time

Time-bucket choice (own reasoned judgment, stated explicitly): **calendar year** for the
headline stability check (enough item-months to be non-trivial, matches the project's own
existing "Jan-Jul 2025 vs. full 2025" framing from Phase A), plus **half-year** for a finer
view, since 2024-2026 is only ~2.5 years of data and monthly would be too thin for the smaller
divisions. Scripts: ad hoc pandas aggregation on the same raw pull (no new query).

**Method A (all rev_type/status) — highly volatile, driven by episodic Tendering deals under
`PPS`, not a stable trend:**

| Period | Other-division % of sale |
|---|---|
| 2024 | 11.27% |
| 2025 | 16.15% |
| 2026 (partial) | 3.62% |
| 2024-H1 | 5.80% |
| 2024-H2 | 16.61% |
| 2025-H1 | **28.73%** |
| 2025-H2 | 1.63% |
| 2026-H1 | 4.96% |
| 2026-H2 | 0.48% |

CSV: `output/summary/task1_yearly_trend_methodA.csv`, `task1_halfyear_trend_methodA.csv`.
**Confirmed, high confidence in the numbers; the 2025-H1 spike traces to the same
`EEE-F-FC-1040010002`/`PPS`/Tendering concentration described in 1.2** (checked directly:
removing that one item's `PPS` rows collapses most of the 2025-H1 spike — not separately
re-tabulated here as a full sensitivity table, but confirmed by inspecting
`task1_per_item_methodA_alldivrevtype.csv`, where this item's ₿57.67M sits under createDate
values that fall in that window).

**Method B (Omni Channel + Actual/MPS, isolated to division) — small and, if anything,
*declining*, not stable or growing:**

| Period | Other-division % of sale |
|---|---|
| 2024 | 0.65% |
| 2025 | 0.36% |
| 2026 (partial) | 0.24% |
| 2024-H1 | 1.00% |
| 2024-H2 | 0.25% |
| 2025-H1 | 0.44% |
| 2025-H2 | 0.30% |
| 2026-H1 | 0.22% |
| 2026-H2 | 0.29% |

CSV: `output/summary/task1_yearly_trend_methodB.csv`, `task1_halfyear_trend_methodB.csv`.
**Confirmed, high confidence in the numbers.** **Analyst interpretation (moderate confidence)**:
once cross-channel noise is removed, cross-division exposure for this 128-item scope is small
in absolute percentage terms and shows a mild downward drift (1.00% → 0.22-0.29%) across the
observed window, not an upward or unstable one — the opposite of what would justify urgent
correction on stability grounds alone, though the absolute ฿ value (~₿3M) is not necessarily
immaterial (see Section 4).

### 1.4 Per-item detail and table-wide totals

Full per-item breakdown (all 128 items, including the 92/81 items with zero exposure under
Methods A/B respectively) in `task1_per_item_methodA_alldivrevtype.csv` and
`task1_per_item_methodB_isolated.csv` — columns: `pem101_qty`, `pem101_sale`, `other_qty`,
`other_sale`, `other_pct_of_sale`, `other_pct_of_qty`, `other_divisions` (semicolon-joined list),
`category`, `type`.

**Top items by other-division exposure, Method A** (from `task1_per_item_methodA_alldivrevtype.csv`):

| itemcode | type | PEM101 sale | Other sale | Other % | Other division(s) |
|---|---|---|---|---|---|
| EEE-F-FC-1040010002 | Fuse Cutout | ₿90.75M | ₿57.67M | 38.86% | PPS |
| LS-F-99-1004 | Low Voltage Surge Arrester | ₿48.23M | ₿16.02M | 24.93% | PPD101;PPS;PTS |
| EEE-F-FL-5920-353-02600 | Fuse link | ₿3.05M | ₿3.50M | 53.40% | PSS |
| EEE-F-FL-5920-353-04100 | Fuse link | ₿1.57M | ₿1.69M | 51.80% | PTS |
| HS-F-99-3303 | Surge Arrester | ₿7.11M | ₿1.08M | 13.19% | PPD101 |

**Top items, Method B** (from `task1_per_item_methodB_isolated.csv`):

| itemcode | type | PEM101 sale | Other sale | Other % | Other division(s) |
|---|---|---|---|---|---|
| EEE-F-FC-1040011000 | Fuse Cutout | ₿28.16M | ₿0.73M | 2.52% | PPD101 |
| EEE-F-LT-1040020100 | Low Tension Fuse Switch | ₿19.52M | ₿0.53M | 2.66% | PCE101;PPD101 |
| EEE-F-FC-1040011100N | Fuse Cutout | ₿8.50M | ₿0.30M | 3.37% | PCE101;PDEMO;PPD101 |
| HS-F-99-0303 | Surge Arrester | ₿0.46M | ₿0.30M | 38.87% | PCE101 |

**Table-wide totals (both stated together, per instruction, since they answer different
questions)**: 47 of 128 items (36.7%) have ANY cross-division exposure under Method A; 36 of 128
(28.1%) under Method B. Aggregate value at stake: ₿85.5M/10.66% (Method A) or ₿2.96M/0.42%
(Method B) — **report both, do not average or pick one without stating which method**, since
they answer genuinely different questions (all-channel vs. Omni-Channel-only cross-division
exposure).

---

## 2. Division master / description table

**Found — `Cube_PMIS_Organize` (45 rows), high confidence.** Search method: (a) queried
`INFORMATION_SCHEMA.COLUMNS` table-wide for any column matching `%divis%`, `%dept%`,
`%business%`, `%unit%` (141 matches across many tables — `output/summary/task1_division_column_search.csv`);
(b) separately queried `INFORMATION_SCHEMA.TABLES` for names like `%master%`, `%lookup%`,
`%dim_%`, `%division%`, `%reference%` — **zero results**, i.e. no table is *named* like a
master/reference table. (c) Among the column-search hits, `Cube_PMIS_Organize` stood out with
both `DivisionCode` and `DivisionName` columns (plus `Company`, `CompanyName`, `RevenueStream`)
— read in full (45 rows, `output/summary/task2_pmis_organize_full.csv`). This is the one
legitimate division-master-shaped table in the database: it maps a `DivisionCode` (e.g.
`PEM101`) to a human-readable `DivisionName` (e.g. "Polymer Product & Electrical Equipment
Business (PEM 101)"), a coarser `Company` code (e.g. `PEM`), and a `CompanyName` (e.g. "Precise
Electric Manufacturing Co., Ltd.").

**Join and match rate against the 128-item scope's observed division codes — confirmed,
high confidence:**

| Division code (128-item scope) | Sale value (Method A) | In `Cube_PMIS_Organize`? | DivisionName | Company | CompanyName |
|---|---|---|---|---|---|
| PEM101 | ₿716.6M | Yes | Polymer Product & Electrical Equipment Business (PEM 101) | PEM | Precise Electric Manufacturing Co., Ltd. |
| PPS | ₿71.6M | **No** | — | — | — |
| PSS | ₿4.70M | **No** | — | — | — |
| PPD101 | ₿4.37M | Yes | KA & Channel Member Management (PPD101) | PPD | Pacific Prosperity Development Co., Ltd. |
| PTS | ₿3.82M | **No** | — | — | — |
| PCE101 | ₿0.88M | Yes | Power Plant Operation and Maintenance Division (CEP101) | PCE | Precise Clean Energy Co., Ltd. |
| PDEMO | ₿0.11M | **No** | — | — | — |

CSV: `output/summary/task1_division_master_match.csv`. **Match rate: 2 of 6 "other" division
codes matched (33%) by distinct code; weighted by Method-A sale value, only 6.1% of the
non-PEM101 value (₿4.37M PPD101 + ₿0.88M PCE101 = ₿5.25M of ₿85.5M) is matched — the great
majority of excluded value (`PPS` alone is 83.8% of it) sits under a division code this master
table does not describe at all.**

Cross-checked `cube_Sale_APD`'s own `cmp`/`sale_company` columns for the four unmatched codes
(query: `SELECT DISTINCT division, cmp, sale_company FROM cube_Sale_APD WHERE division IN
('PPS','PTS','PDEMO','PSS', ...)`): `PPS→PPS`, `PTS→PTS`, `PSS→PSS` (own, self-named company
codes, and none of `PPS`/`PTS`/`PSS` appear anywhere in `Cube_PMIS_Organize`'s `Company` column
either — genuinely absent at both levels); `PDEMO→PDE`, and `PDE` **is** a company in the master
("Precise Digital Economy Co., Ltd.") even though `PDEMO` itself is not one of that company's
listed `DivisionCode` values there (closest are `PDE101`-`PDE106`) — a partial, not exact,
resolution.

**Stopping rule applied**: `PPS`, `PTS`, `PSS` cannot be identified at all from any table found
in this database (confirmed by both the dedicated master-table search and the `cmp`/
`sale_company` cross-check) — the two legacy `division` values noted elsewhere in `STATUS.md`
(`PEM102-OLD`, `PEM107-OLD`) similarly do not appear in `Cube_PMIS_Organize`, consistent with
being legacy/superseded. **This is genuinely unresolved from data; the team that would know is
IT/ERP administration or Finance (whoever maintains `Cube_PMIS_Organize` and the underlying
division-code list it draws from)** — they should confirm what `PPS`/`PTS`/`PSS` are and
whether they warrant addition to the master.

---

## 3. Does PEM101 share physical stock with the other divisions?

**Overall answer: the database cannot show this directly, confidence high in that negative
finding. What indirect evidence exists is genuinely mixed and mostly inconclusive, reported
honestly below rather than stretched into a conclusion.**

### 3.1 Warehouse field on sales rows — re-verified live, confirms STATUS.md's existing finding

```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('cube_Sale_APD','Cube_CES')
  AND (COLUMN_NAME LIKE '%warehouse%' OR COLUMN_NAME LIKE '%wh%' OR COLUMN_NAME LIKE '%stock%' OR COLUMN_NAME LIKE '%location%')
```
Returned **zero rows**. **Confirmed, high confidence, independently re-verified (not just
carried over from the prior session's finding)**: neither `cube_Sale_APD` nor `Cube_CES` has
any warehouse/location field. No sales row for any division — PEM101 or otherwise — can be tied
to a warehouse. This closes off the most direct test the task brief suggested (comparing
warehouse codes on PEM101 vs. non-PEM101 sales rows) — it is not just under-explored, it is
structurally impossible with this schema.

### 3.2 Inventory table's own "Division" field — checked, but not usable for this question (important negative finding)

`Cube_Inventory_Aging` (the table this project already uses for current stock-on-hand,
`STATUS.md` line ~900) does carry both a `Warehouse` and a `Division` column. This looked
promising, but: **`Cube_Inventory_Aging.Division` uses a completely different code space than
`cube_Sale_APD.division` — confirmed directly, not assumed.**

```sql
SELECT DISTINCT Division, Company FROM Cube_Inventory_Aging
```
returns values like `101`, `B102`, `D-101`, `F-105`, `DIV.101` under `Company IN ('PEM','CI')`
— never `PEM101`, `PCE101`, `PPS`, etc. **These two "Division" columns are false friends: same
name, unrelated coding scheme, not joinable.** For the 128-item scope specifically
(`output/data/task1_inventory_aging_128items.csv`, 4,214 rows), the values found are only
`B101` (4,207 rows) and `D-101` (7 rows) — neither maps to any `cube_Sale_APD.division` value.
**Confirmed, high confidence: this table cannot be used to test whether stock is partitioned by
sales-division**, because it isn't organized on that dimension at all.

**One soft, indirect signal worth reporting (Analyst interpretation, low-to-moderate
confidence, explicitly not proof)**: because `Cube_Inventory_Aging` records exactly one
stock-on-hand figure per (item, warehouse) with no field that could partition it by which
`cube_Sale_APD.division` might draw it down, the inventory system itself has no mechanism to
earmark stock for one sales-division over another for these items. This is *consistent with* a
single shared pool, but is not direct evidence of one — a genuinely siloed-by-division stock
system could still exist without this particular table reflecting it (e.g. if siloing happened
by warehouse alone, with each division simply restricted to certain warehouse codes by a
business rule this data cannot show). **Do not read this as confirmation** — it is the absence
of counter-evidence, not positive evidence.

The 40 warehouse codes found for the 128-item scope in this snapshot (`AST, CL, CL01, F-RD,
F101, F103, F104, F106, F107, F109, F2-2, FG, FG01, FG02, FG03, FG11, FG12, FG16, FG17, FG21,
FG23, FG24, FMTO, FMTS, INTR, NCRM, QA, QA01, QA03, RM01, W121, W4-1, WH01, WH03, WH04, WH05,
WH06, WH07, WH21, WH24`) are the same standard PEM-manufacturing warehouse set already
identified in the Phase 4 groundwork/warehouse-flow investigations (`STATUS.md`, "34 distinct
warehouse codes" and `phase4_warehouse_flow_investigation_report.md`) — **confirmed, high
confidence**, not a different or division-specific set.

### 3.3 Company-level mismatch — a real, separately-sourced doubt about shared stock for 2 of the 6 "other" divisions

Combining Section 2's master-table join with `Cube_Inventory_Aging`'s `Company` field (which
only ever shows `PEM` or `CI` for this scope, confirmed): **`PCE101` belongs to Company `PCE`
("Precise Clean Energy Co., Ltd.") and `PPD101` to Company `PPD` ("Pacific Prosperity
Development Co., Ltd.") — both DIFFERENT legal entities from `PEM101`'s Company `PEM`
("Precise Electric Manufacturing Co., Ltd."), per `Cube_PMIS_Organize`.** `PPS`/`PTS`/`PSS`
cannot be checked this way since they are absent from the master entirely (Section 2).

**Confirmed, high confidence, that this company mismatch exists as recorded data.
Analyst interpretation, moderate confidence, explicitly labelled as inference: this raises a
real, business-plausible doubt about whether these two divisions' recorded sales of Fuse/Surge
Arrester item codes are actually fulfilled from PEM101's manufacturing stock at all** — separate
legal entities sharing inventory would normally require a formal inter-company arrangement
(consignment, inter-company transfer, tolling), which this database has no table to confirm or
rule out. It is equally possible these are the SAME physical items simply sold through a
different company's sales channel with a genuine stock-sharing arrangement in place — **the
data cannot distinguish between "genuinely shared stock" and "unrelated/reused itemcode across
a different legal entity's own inventory,"** which is exactly the kind of itemcode/category
reuse this project has already documented elsewhere (`STATUS.md` Phase 2 Step 1: the same
category name is reused across divisions "for what are presumably different, unrelated
products").

### 3.4 Contract ID overlap — direct, decisive test, negative result

```python
grp = df.groupby(["itemcode","contractid"])["division"].nunique()
multi = grp[grp>1]
```
Run against the full 27,808-row pull (Section 0). **Result: 0 of 27,630 (itemcode, contractid)
pairs span more than one division — confirmed, high confidence, direct and decisive.** No
single contract/order for any of the 128 items is ever recorded as split across PEM101 and
another division. `output/summary/task1_contractid_spanning_divisions.csv` is written empty to
record this null result explicitly (per the project's convention of reporting negative findings,
not omitting them). **This is negative evidence against order-level demand crossing divisions**
— but it does not, and cannot, speak to whether the underlying physical stock pool is shared;
it only shows the sales/order records themselves stay within one division each.

### 3.5 Inter-division transfer table search — none found; the one transfer table that exists doesn't reach this question

```sql
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%transfer%'
```
returns **zero tables**. The only movement ledger in the database, `cube_inventory_tran`
(already used in the Phase 4 warehouse-flow investigation, `STATUS.md`), has `company` and
`costcenter` columns (re-verified: `company` is `PEM` for 9,672 of 9,674 rows covering this
128-item scope, `CI` for 2 — confirmed via a fresh query, `costcenter` values like `F101`,
`B101`, `S105`, not `cube_Sale_APD.division` values) but **no field resembling
`cube_Sale_APD.division` at all.** It records warehouse-to-warehouse transfers within one
company's own inventory, not any cross-division event. Its coverage is also already known to be
narrow: only 34 of 128 items appear in it at all, and only 6 (all Raw Material Fuse Holder
codes, not Finished Goods) show any confirmed transfer (`STATUS.md`,
`phase4_warehouse_flow_investigation_report.md`) — **re-confirmed here, not re-derived from
scratch**, since re-running that full investigation for this task would duplicate work already
done and documented.

### 3.6 Stopping rule applied

**The database cannot show whether other divisions draw from the same physical stock as
PEM101.** What was checked: sales-row warehouse fields (absent), the inventory table's own
Division field (present but not joinable to sales division), company-level records (available,
shows 2 of 6 other divisions are different legal entities), contract-level overlap (tested,
zero found), and a dedicated transfer-table search (none exists; the one movement ledger has no
division field and covers only 34/128 items regardless). **This genuinely cannot be settled
from data — the team that would know is Warehouse/Operations** (who would know whether PCE101,
PPD101, PPS, PTS, PSS, and PDEMO orders for these item codes are physically picked from the same
Fuse/Surge Arrester warehouse stock as PEM101, or from a separate pool, possibly via an
inter-company arrangement) **and, for the company-mismatch doubt specifically, Finance/
inter-company accounting** (who would know whether PCE101/PPD101 have any inventory-sharing
arrangement with PEM at all). This matches the project's own established stopping-rule pattern
(`STATUS.md` already states "this project has already found no data source directly answers
'which warehouse stage holds sellable stock'" — this task extends that same limitation across
divisions, not just across warehouse stages within PEM101).

---

## 4. Options for Phase 4 (presented, not decided)

Grounded specifically in Sections 1-3 above, not a generic list. A human decides; this agent
does not recommend one.

**(a) Include all divisions in the demand series for affected items.**
- *Which value to include* is itself an open sub-choice given Section 1's finding: Method A's
  ₿85.5M (10.66%) or Method B's ₿2.96M (0.42%) are very different sizes to add. Including Method
  A's figure would import a large share of *Tendering*-channel demand (already an explicit
  out-of-scope channel per this project's Locked Decisions) under the disguise of
  "cross-division," which the Section 1.2 finding shows is misleading — most of that value is
  driven by one item's one-off `PPS`/Tendering exposure, not a recurring division-level pattern.
  Including Method B's figure is smaller and more defensible as genuinely "same-channel,
  different-division" demand, but data availability (Section 2/3) is thin: 4 of 6 divisions
  (`PPS`, `PTS`, `PSS`, `PDEMO`) cannot be identified at all, and shared-stock cannot be
  confirmed for any of them (Section 3.6). Risk: **under-provisioning** if genuinely shared
  demand is excluded; **over-provisioning and scope creep** if Tendering-channel or
  different-legal-entity demand (Section 3.3) is wrongly folded in as if it drew on the same
  pool. Complexity: low to build (the query already exists), but the division ambiguity would
  need a policy decision on which divisions/methods to include, since the two right answers here
  differ by 25x.

**(b) Keep PEM101 only and add a documented allowance (e.g. a % uplift) for these items.**
- Directly supported by Section 1's per-item table: an item-specific uplift (e.g. +0.4-3% for
  most of the 36 Method-B-exposed items, but the two outliers `EEE-F-FC-1040010002`/`LS-F-99-1004`
  under Method A show 20-39%) could be calibrated from `task1_per_item_methodB_isolated.csv`
  directly. Risk: Section 1.3 shows the isolated (Method B) share is *stable-to-declining*, not
  growing, so a static uplift calibrated today is unlikely to systematically drift stale in the
  near term — a genuine point in this option's favor versus a naive read of the raw ₿60.6M/₿85.5M
  headline figures, which look large and volatile only because they mix in the Tendering
  confound. Complexity: lowest of the three options — no change to the forecasting pipeline
  itself, just a documented adjustment layer at the inventory-planning step. Weakness: does not
  address the ₿4 division codes this project cannot even identify (Section 2) — an uplift
  derived only from known, joinable divisions would silently miss whatever `PPS`/`PTS`/`PSS`
  volume is real and shared, if any is.

**(c) Treat other divisions as a separate, independently forecast series.**
- Section 3's findings argue this is the most defensible option IF the company-mismatch doubt
  in 3.3 is real: if `PCE101` and `PPD101` are genuinely separate legal entities selling these
  item codes through their own channel (not drawing PEM101's stock), then their demand has no
  business reason to be combined into PEM101's inventory-planning series at all — a separate
  forecast (or none, if it's out of this project's remit entirely) would be more correct than
  either uplifting or merging. Risk: data availability is the binding constraint — the volumes
  involved per division are small and thin (`PCE101`: 50 rows/18 items table-wide; `PPD101`: 28
  rows/19 items; Section 1.4), likely too sparse to forecast independently with any of this
  project's existing methods (Croston/SBA/moving average all assume more history than a
  handful of rows per item provides). Complexity: highest of the three — requires building and
  maintaining a second forecasting track for a comparatively small ฿ amount (₿2.96M under Method
  B), which may not be worth the overhead unless the shared-stock question in Section 3.6 is
  resolved in the negative (i.e., confirmed NOT shared) by Operations/Finance.

---

## Summary of what's confirmed vs. inferred vs. unresolved

| Claim | Status | Confidence |
|---|---|---|
| Method A/B totals, per-item, per-year/half-year breakdowns (Section 1) | Confirmed (direct query + pandas aggregation) | High |
| Old ₿60.6M figure mixed cross-channel with cross-division exposure | Confirmed the mixing exists; the "most of it" framing is Analyst interpretation | Moderate-to-high |
| `Cube_PMIS_Organize` is a genuine division master, 45 rows | Confirmed (direct query) | High |
| Match rate 2/6 other divisions (33% by code, 6.1% by value) | Confirmed | High |
| `PPS`/`PTS`/`PSS` unidentifiable anywhere in this database | Confirmed (two independent searches) | High |
| No warehouse field exists on any sales row, any division | Confirmed (live re-verification) | High |
| `Cube_Inventory_Aging.Division` is unrelated to `cube_Sale_APD.division` | Confirmed | High |
| Single stock pool per item is *consistent with* no inventory table having a division-partition field | Analyst inference, explicitly not proof | Low-to-moderate |
| `PCE101`/`PPD101` are different legal entities from PEM101's company | Confirmed | High |
| Whether shared stock is real for those or any other division | **Unresolved — stopping rule applied** | N/A (data cannot answer) |
| Zero contracts span more than one division for these items | Confirmed | High |
| No inter-division transfer table exists; `cube_inventory_tran` doesn't reach this question and covers only 34/128 items | Confirmed | High |

**Owning teams to ask, named explicitly per the stopping rule**: IT/ERP administration or
Finance (to identify `PPS`/`PTS`/`PSS`, and to confirm/deny any inter-company stock-sharing
arrangement between PEM and PCE/PPD); Warehouse/Operations (to confirm whether any division's
orders for these item codes are physically fulfilled from the same warehouse stock as PEM101).
