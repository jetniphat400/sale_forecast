# Synthesis — Phase B Three Parallel Open Items (Cross-Division Demand, No-History Items, Forward-Test Log Rebuild)

**Agent**: Synthesizer, per `AGENTS.md`. **Role boundary honoured**: this report merges findings
already produced by the three parallel agents below — it gathers no new data, runs no new query,
and does not decide anything. Where the three source tasks disagree with each other, or with
`STATUS.md`'s existing text, both positions are reported with their evidence; the decision is
left to the human, per `AGENTS.md` rule 9. Every claim below cites the exact source
report/CSV/script it is restated from; confirmed and inferred claims are kept visibly separate;
a confidence level is stated for every conclusion, carried over from the source task where the
source task itself stated one (not invented here).

**Sources merged** (read in full before writing this synthesis):
1. `output/summary/task1_crossdivision_report.md` — Explorer+Analyst — cross-division demand.
2. `output/summary/task2_noHistoryItems_report.md` — Explorer+Validator — no-history/no-sale items.
3. `output/summary/task3_forwardTestRebuild_report.md` — Modeler — forward-test log rebuild.

---

## 1. Task 1 — Cross-division demand

### 1.1 What is now confirmed, and at what confidence

- **Two different, equally legitimate measurements exist for "what the division filter
  excludes," and they give very different answers — both confirmed, high confidence, direct
  query + pandas aggregation on one single raw pull** (`output/data/task1_crossdiv_raw_128items_alldivisions.csv`,
  27,808 rows), per `task1_crossdivision_report.md` §1.1:
  - **Method A** (replicates the original 68-item pilot's methodology — holds nothing constant
    except `itemcode`): **₿85.5M excluded, 10.66% of the all-division total**, 47 of 128 items
    (36.7%) with any exposure.
  - **Method B** (isolates the division variable only, holding `revenue_type='Omni Channel'` and
    `status IN ('Actual','MPS')` fixed — the project's actual channel/status scope): **₿2.96M
    excluded, 0.42% of the all-division total**, 36 of 128 items (28.1%) with any exposure.
  - These are not competing estimates of the same quantity — they answer genuinely different
    questions (all-channel cross-division vs. same-channel cross-division), and the report itself
    presents both rather than picking one (per its own stated instruction, mirroring `AGENTS.md`
    rule 9). **This synthesis does the same — it does not pick a side.**
- **The reason for the gap is identified, not merely observed — moderate-to-high confidence
  (Analyst interpretation layered on a confirmed fact)**: one item, `EEE-F-FC-1040010002`,
  contributes ₿57.67M of Method A's ₿85.5M (67.4%), entirely under division `PPS`, entirely
  `revenue_type='Tendering'` — not Omni Channel. **This means the project's long-standing
  ₿60.6M/14.3% cross-division figure (68-item pilot scope, `STATUS.md` Phase 2 audit note) was
  never a pure cross-division number — it always mixed in a cross-CHANNEL (Omni Channel vs.
  Tendering) effect for this one item**, a distinction not previously separated out in
  `STATUS.md` or the Red Team Review. Under Method B (channel held fixed), this item's exposure
  collapses and no single item dominates (largest is ₿726,500, 2.52% of its own PEM101 total).
- **Reconciliation against the old ₿60.6M/14.3% pilot figure — confirmed, high confidence**:
  the 128-item scope's Method A figure (₿85.5M/10.66%) is larger in absolute value (+41%, more
  items in scope) but a lower percentage (denominator grew proportionally more) — not a
  contradiction, a scope-expansion effect, explained directly in §1.2 of the source report.
- **Stability over time**: Method A is highly volatile (2025-H1 spike to 28.73%, traced to the
  same item/PPS/Tendering concentration); Method B is small and mildly *declining* (1.00% in
  2024-H1 to 0.22-0.29% by 2026) — confirmed, high confidence in the numbers; the "declining, not
  urgent" reading is Analyst interpretation, moderate confidence.
- **No division master table names `PPS`, `PTS`, or `PSS`** — confirmed via two independent
  searches (a column-name scan across all `INFORMATION_SCHEMA.COLUMNS`, and a `cmp`/
  `sale_company` cross-check). `PCE101` and `PPD101` DO resolve in `Cube_PMIS_Organize` and
  belong to different legal entities (`PCE`, `PPD`) than PEM101's own company (`PEM`) — confirmed,
  high confidence.
- **Whether PEM101 physically shares stock with the other divisions is UNRESOLVED — the database
  cannot show this, high confidence in that negative finding.** No sales row anywhere carries a
  warehouse field; the inventory table's own `Division` field uses an unrelated code space and
  cannot be joined to `cube_Sale_APD.division`; zero of 27,630 (itemcode, contractid) pairs span
  more than one division (decisive negative test); no inter-division transfer table exists. Task 1
  explicitly applies the project's stopping rule here and names the owning teams (IT/ERP or
  Finance for `PPS`/`PTS`/`PSS` identity and inter-company arrangements; Warehouse/Operations for
  physical stock-sharing).

### 1.2 Decisions queued for the human (Task 1 explicitly did not choose)

Three options are presented in the source report §4, with trade-offs, no recommendation:
- **(a) Include all divisions in the demand series** — but which figure, Method A (₿85.5M,
  imports Tendering-channel demand under a "cross-division" label) or Method B (₿2.96M, more
  defensible but only partially identifiable/verifiable)? The two right answers differ by 25x.
- **(b) Keep PEM101 only, add a documented per-item uplift** — calibrated from Method B's stable
  figures; cheapest to build; misses whatever real shared volume `PPS`/`PTS`/`PSS` represent,
  since those divisions cannot be identified at all.
- **(c) Treat other divisions as a separate, independently forecast series** — most defensible
  IF the company-mismatch doubt (PCE101/PPD101 being separate legal entities) means their demand
  shouldn't be combined with PEM101's inventory planning at all; but volumes are thin (18-19
  items, dozens of rows) — likely too sparse for this project's existing models.

### 1.3 What Task 1 itself flagged as unresolved / needing a specific team

- Identity of `PPS`/`PTS`/`PSS` division codes and whether they warrant addition to
  `Cube_PMIS_Organize` — **needs IT/ERP administration or Finance.**
- Whether `PCE101`/`PPD101` (confirmed separate legal entities) have any formal inter-company
  stock-sharing arrangement with PEM — **needs Finance/inter-company accounting.**
- Whether any division's orders for these item codes are physically fulfilled from the same
  warehouse stock as PEM101 — **needs Warehouse/Operations.** (Structurally unanswerable from
  this database's schema — no warehouse field on any sales row, in any division.)

---

## 2. Task 2 — Items with no history / no sales

### 2.1 What is now confirmed, and at what confidence

- **The population is 16 items, not 31 — confirmed, high confidence, direct live re-query**
  (`task2_noHistoryItems_report.md` §1). The task brief's own premise (16 zero-row items PLUS 15
  more items with rows present but summing to zero) does **not hold**: among the 112 of 128 items
  that have at least one row under the standard filter, the *minimum* `SUM(qty)` is 1.0 and the
  *minimum* `SUM(sale)` is 720.0 — **no item has rows that net to zero.** There is no second
  "15 more" bucket at this scope.
- **This is directly relevant to §3 below (the STATUS.md contradiction)** — see that section.
- A related but distinct number also appears and is not confused with the above: **15 of 128
  items have zero rows anywhere in `cube_Sale_APD`, under no filter at all** (any division,
  channel, status, date) — a strict subset of the 16. The one item in the 16 but not the 15 is
  `EEE-F-FC-1040010002`... — **correction, actually `EEE-F-FL-5920-353-02600`** (has rows, but
  100% under `revenue_type='Tendering'`, never Omni Channel).
- **Classification of the 16 (per-item table, `task2_per_item_classification_final.csv`)**:
  - **6 items — "(d) Listed but never sold"** (high-to-moderate confidence): zero `Cube_CES`
    activity of any kind, or only unconverted live quotations (1-9 unit quote sizes).
  - **6 items — "(b) Sold outside this project's filter"** (confidence varies by item, moderate
    to high): each has its own `Cube_CES` sales history (6 to 88,500 lifetime units) under a
    different channel or division. One of these, `EEE-F-FL-5920-353-02600`, is **high
    confidence, sold exclusively via Tendering** — see §3 cross-check with Task 1 below.
  - **4 items — cannot be classified cleanly**: genuine mixed evidence (real pre-2024 Omni
    Channel/PEM101 history that predates the modelling window, mixed with live but unconverted
    quotation activity, or cross-division `ManuDivision` signals).
  - **0 items** land cleanly in "(a) new, not yet sold" or "(c) discontinued" as standalone
    labels — no pricelist-version evidence supports "new" (all 16 exist in both the old and
    current pricelist versions), and no status field anywhere records discontinuation.
- **A genuine data-quality finding surfaced in passing**: `Cube_CES.Status` has 14 distinct
  values table-wide, not just `Actual`/`Backlog` as the project's existing pilot-scope work had
  checked — most (`P1`-`P3`, `T1`-`T3`, `Cancel`, `F`, `Y`, `N/A`) are unconfirmed in meaning,
  flagged as an open question, not guessed at.

### 2.2 Decisions queued for the human

Per-class options presented in source §4, no recommendation made:
- **Class (d), 6 items**: borrow Type-level demand profile (weak fit — would badly over-provision
  given 1-9 unit quote sizes vs. Type averages in the tens of thousands); manual placeholder
  (most defensible, especially the 4 items with live quotes); exclude with justification
  (defensible only for the 2 fully-zero-trace items).
- **Class (b), 6 items**: exclude (correct for this project's own Omni-Channel scope, but wrong
  for Phase 4 inventory planning as a whole, given the already-established shared-stock
  concern); the report also flags a **fourth option beyond the brief's original three** — build a
  Phase-4-specific demand estimate directly from each item's own `Cube_CES` history, already
  retrieved and arguably better-grounded than any of the three generic options.
- **"Cannot classify cleanly", 4 items**: manual placeholder sized to each item's own historical
  order scale is favoured over borrowing a Type average (which would badly overstate demand for
  the two single-digit-unit items).

### 2.3 What Task 2 itself flagged as unresolved / needing a specific team

- Meaning of `Cube_CES.Status` codes `P1`-`P3`, `T1`-`T3`, `Cancel`, `F`, `Y`, `N/A` — **needs
  CRM/ERP or sales operations.**
- Whether blank/NULL `RevenueType` on several items' confirmed "Actual" `Cube_CES` rows means
  "genuinely outside Omni Channel" or "untagged" — **needs sales operations.**
- Meaning of `cube_inventory_tran.transtype` codes `B`/`N`/`150`/`151`/`A` — **needs
  warehouse/ERP.**
- Meaning of warehouse code `NCRM` — **needs the warehouse team.**
- Whether any of the ambiguous items are formally discontinued — **needs the
  product/business team**; no status field anywhere records this.

---

## 3. The STATUS.md "31-item" contradiction — reported explicitly, per `AGENTS.md` rule 4

**`STATUS.md`'s own text (Phase B remaining-work note, Current Status Summary, 2026-09-02)
states**: *"the 16 items with no history and 15 with no sales, which must not simply be
dropped..."* — i.e., a recorded assumption of a **31-item** excluded population (16 zero-row
items + a second, separate bucket of 15 items with rows present but zero total qty/sale).

**Task 2's live re-derivation directly contradicts this.** Per `task2_noHistoryItems_report.md`
§1 (confirmed, high confidence, live query against the current 128-item scope under the
project's own standard filter): among the 112 of 128 items that have any row at all, the minimum
`SUM(qty)` is 1.0 and the minimum `SUM(sale)` is 720.0 — **no item exists with rows present that
net to zero.** The "15 with rows-but-zero-sales" bucket that `STATUS.md` assumes **does not exist
at this scope.**

What Task 2 actually found is **16 total items** with zero rows under the standard filter (not
16 + 15 = 31), of which **15 of those 16** also have zero rows anywhere in the table under no
filter at all (any division/channel/status/date), and the remaining 1 (`EEE-F-FL-5920-353-02600`)
has rows, but 100% of them are tagged `revenue_type='Tendering'`, never `'Omni Channel'` — a
different reason for exclusion (wrong channel, not "no sales"), not a second bucket of
zero-summing rows.

**Stated plainly, per instruction, correcting the record rather than silently overwriting it**:
**STATUS.md previously recorded a 31-item excluded population (16 zero-row + 15 rows-but-zero-
sales). This is now found to be incorrect** — the true, live-reconciled population is **16
items total**, not 31, per `output/summary/task2_noHistoryItems_report.md` §1 and
`output/summary/task2_q1_std_filter_per_item.csv`/`task2_q2_any_activity_per_item.csv`. The
"15" figure that does independently exist (items with zero rows anywhere, any filter) is a
**subset of the 16**, not an additional 15 on top of it. This correction is being written into
`STATUS.md` as a new, explicitly-flagged log entry (§7 below) — the old text is left in place,
per `AGENTS.md` rule 4 ("never overwrite a previous conclusion silently").

**Confidence in this contradiction-finding: high** — it rests on a direct live SQL query result
(minimum SUM(qty)/SUM(sale) across 112 items, both strictly positive), not an inference.

---

## 4. Task 1 / Task 2 overlap — checked for consistency, one genuine near-touch found, no contradiction

Both tasks separately handle cross-division/cross-channel exposure for a subset of items in the
same 128-item scope. Checked directly for whether they are consistent where they touch the same
ground:

- **`EEE-F-FC-1040010002`** (Task 1's dominant Method-A item, ₿57.67M under division `PPS`,
  `revenue_type='Tendering'`) is **not** one of Task 2's 16 no-history items — it has abundant
  Omni Channel/PEM101 history and is one of this project's three locked focus codes. **No
  overlap, no tension** — the two tasks are discussing different items that happen to share the
  same underlying phenomenon (Tendering deals recorded under division `PPS`).
- **The genuine overlap point is the phenomenon itself, not the item**: Task 2 separately and
  independently classifies `EEE-F-FL-5920-353-02600` as **"(b) Sold, exclusively via Tendering
  channel"** (high confidence — 10 `Cube_CES` rows, 88,500 lifetime units, 4 explicitly tagged
  Tendering, plus a `Cube_Quotation` record showing `revenue_type='Tendering'` deals with two
  named customers [redacted -- business-sensitive, not committed to this public repo; see the
  un-redacted CSV in output/summary/]). This item also appears in **Task 1's own Method-A per-item
  table** (`task1_per_item_methodA_alldivrevtype.csv`, cited in the source report's §1.4 top-item
  table): PEM101 sale ₿3.05M, other-division sale ₿3.50M (53.40%), division `PSS` — i.e. Task 1
  independently confirms this item has a large Tendering-channel presence recorded under a
  different division (`PSS`), the same conclusion Task 2 reached from `Cube_CES`/`Cube_Quotation`
  evidence. **The two tasks are consistent with each other on this item** — one via
  `cube_Sale_APD` cross-division rows, the other via `Cube_CES`/quotation records — despite using
  different source tables and different filters (Task 1: all-division/all-revenue_type pull from
  `cube_Sale_APD`; Task 2: `Cube_CES`/`Cube_Quotation` lookups). **Confidence: high** that both
  figures describe the same real-world fact (this item sells mostly via Tendering, recorded under
  division `PSS`), moderate confidence that this generalizes as a pattern beyond this one item,
  since only one item was checked for this specific cross-task consistency question — neither
  source report ran a full item-by-item reconciliation between the two tasks' outputs, and this
  synthesis does not manufacture one (no new data gathered, per this agent's role boundary).
- **No contradiction found between the two tasks' methods or figures on any item both reports
  actually discuss.** The apparent risk (different filters producing different-looking answers
  for the same item) did not materialize here — where the two reports overlap, they corroborate.
  This is reported as-is; it is not evidence the two methods would always agree on other items
  neither report examined in this cross-task manner.

---

## 5. Task 1's own internal tension — both positions reported, no side taken

Task 1's own two methods answer the same underlying question ("how much cross-division demand
exists?") and land on very different magnitudes:

| | Method A | Method B |
|---|---|---|
| Excluded value | ₿85.5M | ₿2.96M |
| Excluded % | 10.66% | 0.42% |
| Items with any exposure | 47/128 (36.7%) | 36/128 (28.1%) |
| Trend | volatile, 2025-H1 spike to 28.73% | small, mildly declining (1.00%→0.22-0.29%) |

**Both are internally valid, confirmed computations from the identical raw pull — they are not
in error relative to each other, they simply hold different variables constant** (Method A varies
division AND channel/status together; Method B isolates division alone). The source report
itself declines to pick one as "the" answer, explicitly instructing readers to "report both, do
not average or pick one without stating which method." **This synthesis carries that position
forward unchanged** — a nearly 29x difference in the headline number depending on method is a
genuine, load-bearing fact for whatever Phase 4 decision follows, not a discrepancy to resolve.

---

## 6. Task 3 — Forward-test log rebuild

### 6.1 What is now confirmed, and at what confidence

- **The old log (`forward_test_log.csv`, 2,088 rows) was wrong on three independent axes
  simultaneously — confirmed, high confidence, direct file/code inspection**: wrong scope (58
  items vs. current 128; 70 of 128 current items never appeared in it), wrong date key
  (`createDate`, not the adopted `forecast_date`), wrong model (six models scored separately, not
  the adopted Combination / Top-down approach). It was **archived, not deleted**
  (`output/summary/archive/forward_test_log_58items_createDate_superseded_2026-09-04.csv` +
  a README explaining why), consistent with `AGENTS.md` rule 4.
- **The new log** (`output/summary/forward_test_log_v2.csv`, **828 rows**) covers 128 items × 6
  horizons (Item level, 768 rows: 113 real Top-down forecasts + 15 forced-exact-zero rows for
  items with no sales history anywhere — mathematically identical to what Top-down would produce
  for a zero-history item, not a placeholder), plus 8 Types × 6 horizons (48 rows, plain
  Combination) and 2 Categories × 6 horizons (12 rows, plain Combination). Uses the existing
  frozen `forecast_date`-keyed pull (`snapshot_pull_date` 2026-09-02 15:52:39, 31 months
  2024-01 to 2026-07) rather than a fresh pull — **confirmed reasoned choice, not an oversight**:
  a fresh pull would not unlock any additional fittable month (August's month-end is only 4 days
  behind today, nowhere near the 30-day leakage-guard margin) while introducing a second,
  inconsistent pull-timing baseline.
- **0 negative `forecast_qty` values; `actual_qty` empty for all 828 rows (nothing fabricated)**
  — confirmed by direct read of the written CSV.
- **The consistency guard works — confirmed by direct execution against real production files,
  not described behaviour.** `score_forward_test_v2.py`'s `verify_consistency()` was tested with
  three deliberate mismatches (stale `config_version`, wrong `date_key`, stale `scope_hash`/
  `scope_n_items`) run against copies in a session scratchpad outside the repo — all three
  correctly raised `ForwardTestConsistencyError` and refused to score (exit code 1); the stale-scope
  test also confirmed multiple simultaneous mismatches are all reported together, not just the
  first one found. The control run against the real, current log/metadata passed cleanly.
- **First scoreable target month: 2026-08, but not yet — becomes safe to score from 2026-09-30**,
  under the leakage-margin rule this rebuild actually enforces (re-using the project's existing
  `leakage_guard.check_window_closed`, `min_margin_days=30`), not the old script's looser
  plain-calendar rule (which would have already called 2026-08 "complete" today, 2026-09-04 —
  precisely the gap the leakage guard exists to close). Confirmed live: as of today the script
  correctly reports 0 of 6 target months safe to score yet.

### 6.2 Decisions queued for the human

**None** — Task 3 was a build task, not a decision task, and its report states plainly that no
model/policy choice was written to `config.yaml` beyond the three already-adopted, previously-
decided values it needed to reference (`adopted_series_key`, `adopted_item_level_approach`,
`adopted_scope_file`). For awareness, not decision, the human should note these schema/config
choices the Modeler made on its own initiative while building:
- The `forecast_date`-keyed series and Top-down item-level approach were **given instructions**
  for this specific rebuild, not re-derived or re-justified here — they carry forward the
  existing Phase B1/B3 findings (themselves already flagged elsewhere as having an unresolved
  rolling-origin-vs-train/val/test direction conflict, per `STATUS.md`'s Phase B follow-up
  entries — Task 3 does not re-litigate that, it only reuses the adopted choice).
  Note: this synthesis flags that Top-down's own edge over Direct was found (in the Modeler
  tasks 1-3 log entry, `STATUS.md`) to be directionally favoured but NOT statistically
  significant (t=-1.23) — the forward-test log is therefore built on a **not-yet-decisively-
  proven** item-level approach, worth the human's awareness even though Task 3 itself was not
  asked to re-litigate it.
- The new `level` column, `scope_hash`/`config_version` metadata-based consistency check, and
  the reuse of the leakage guard for scoring (not just backtesting) are new conventions
  introduced by this task, not previously specified in `CONVENTIONS.md` — worth the human noting
  they now exist as project convention going forward.

### 6.3 What Task 3 itself flagged as unresolved

Task 3's own report does not carry a "what the data could not resolve" section distinct from the
existing, still-open Phase B/B4/Modeler-tasks-1-3 items already in `STATUS.md` (the origin-7
reversal cause, the rolling-origin-vs-train/val/test conflict) — it explicitly reuses those
adopted choices without re-opening them. Nothing new is queued from Task 3 beyond what §6.2 notes
for awareness.

---

## 7. Cross-cutting: what remains missing across all three tasks

- Nobody has resolved **which of Task 1's two cross-division figures (₿85.5M/10.66% or
  ₿2.96M/0.42%)** should feed Phase 4 planning, nor which of the three presented options (include
  all, uplift, separate series) to adopt.
- Nobody has resolved **which per-class treatment** (borrow Type profile / manual placeholder /
  exclude / build from own `Cube_CES` history) applies to Task 2's 16 items, nor whether the 4
  "cannot classify cleanly" items need business confirmation before any treatment is chosen.
- Task 1 and Task 2 both independently ran into the **same structural database gap**: no
  warehouse/division-partition field exists anywhere that could confirm or rule out physical
  stock-sharing across divisions — this is not specific to either task, it is a schema-wide limit
  both discovered separately and reported the same way (stopping rule applied, owning team named).
- Task 3's forward-test log currently has **zero scoreable rows** (by design — nothing was
  fabricated); the earliest anything can be scored against real actuals is **2026-09-30**, for
  target month 2026-08. This is not a gap, it is a scheduling fact for the human's awareness.

---

## 8. Confidence summary table (every conclusion above, in one place)

| Conclusion | Confidence | Source |
|---|---|---|
| Method A cross-division exposure ₿85.5M/10.66% | High | task1 §1.1 |
| Method B cross-division exposure ₿2.96M/0.42% | High | task1 §1.1 |
| Old ₿60.6M figure mixed cross-channel with cross-division | Moderate-to-high (interpretation on a confirmed fact) | task1 §1.2 |
| PPS/PTS/PSS unidentifiable in any division master | High | task1 §2 |
| Whether stock is physically shared across divisions | Unresolved — data cannot answer | task1 §3.6 |
| True no-history/no-sale population is 16, not 31 | High | task2 §1 |
| STATUS.md's 31-item assumption is contradicted | High | task2 §1, this synthesis §3 |
| Classification of the 16 items (6/6/4 split) | High for class (d) and the one high-confidence class-(b) item; moderate-to-low for the rest | task2 §3 |
| Task1/Task2 consistency on `EEE-F-FL-5920-353-02600` | High that the underlying fact matches; moderate that it generalizes | this synthesis §4 |
| New forward-test log: 828 rows, 0 negative, 0 fabricated actuals | High | task3 §4 |
| Consistency guard actually refuses to score on mismatch | High (tested against real script, 3 deliberate failures + 1 control pass) | task3 §5 |
| Earliest scoreable target month: 2026-08, safe from 2026-09-30 | High | task3 §6 |
| Top-down's edge over Direct is not statistically significant | High (t=-1.23, carried from existing STATUS.md Modeler-tasks-1-3 entry, not re-derived here) | STATUS.md (Modeler tasks 1-3 log entry), cited by this synthesis §6.2 |

---

*No `STATUS.md` conclusion in Sections 2-4/Business Findings/Locked Decisions is overturned by
this synthesis except the explicit 31-item correction in §3 above. No git action taken. No new
data gathered.*
