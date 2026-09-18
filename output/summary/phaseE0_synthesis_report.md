# Phase E0 Synthesis — Pre-Check Gate for Phase E1 (Max-Min Calculation and Simulation)

**Role**: Synthesizer (per `AGENTS.md`) — merges the three Phase E0 Validator reports, surfaces
conflicts, states what is known at what confidence, and reports gaps rather than filling them.
**No new data was gathered for this report.** Everything below is drawn from, and cites, the three
Validator reports and their supporting CSVs. Every conclusion is labelled exactly one of
**verified from data**, **supported hypothesis**, **configurable assumption**, or **cannot be
determined** — per this task's ground rules, a Validator's "hypothesis" is never upgraded to a
fact here, and where the Validators presented two sides (E0.3), both are restated, not resolved.

**Sources merged**:
1. `output/summary/phaseE0_validator1_leakage_report.md` (E0.1 — point-in-time leakage), plus
   `phaseE0_q1_share_comparison.csv`, `phaseE0_q2_revision_risk_per_origin.csv`,
   `phaseE0_q2_revision_risk_focus_items.csv`, `phaseE0_q2_test_window_knowability.csv`.
2. `output/summary/phaseE0_validator2_cancellations_report.md` (E0.2 — cancellations). **This
   Validator was BLOCKED** — SQL Server login `jetniphat.boo`'s password had expired
   (`pyodbc.InterfaceError` / SQL error 18487, reproduced on two separate query attempts). All four
   of its sub-questions are "cannot be determined." This is treated below as a genuine, open gap,
   not interpreted around.
3. `output/summary/phaseE0_validator3_placeholder_coherence_report.md` (E0.3 — placeholder
   coherence with Type totals), plus `phaseE0_validator3_placeholder_type_totals.csv`,
   `phaseE0_validator3_82item_reasons.csv`.

---

## 1. Per-gap verdict and consequence for Phase E1

### E0.1 — Point-in-time leakage in rolling-origin backtests

**No re-run of the production backtest happened, and none should be inferred.** Validator 1
states this explicitly: no genuine leakage was found in the two mechanisms that were actually
checkable (shares, model settings), so the re-run permission in its brief was never triggered.
**No Phase C conclusion changes as a result of E0.1** — the backtest numbers behind
`forecast_method_final: topdown_combination` (`config/config.yaml`) stand as previously locked.

Four sub-questions, four different verdicts — not flattened into one number:

| Sub-question | Verdict | Confidence | Consequence for Phase E1 |
|---|---|---|---|
| 1. Historical Top-down allocation shares | **Verified from data**: leakage absent in every script whose output feeds a cited backtest number (`item_level_reconciliation.py`, `transferability_all_divisions.py`, `focus_item_model_selection.py` — all confirmed by direct code read to compute shares only from data through each origin's own `train_size`) | High | **No impact — fully resolved.** Phase E1 may use the existing shares as-is. |
| 2a. `forecast_date` revision-in-place timing | **Cannot be determined** (re-affirms Phase A; Validator 1 could not independently re-verify today — the same DB login failure that blocked Validator 2 also stopped Validator 1's own `INFORMATION_SCHEMA.COLUMNS` re-check) | High confidence in the *negative* finding (no audit table exists) | **Does not block E1.** Phase A already bounded any revision at <2.5% of rows with no consistent direction — small relative to Phase E1's inputs. Carry forward as a documented assumption ("`forecast_date` is fixed at intake"), per the Gap Register below. |
| 2b. Training/test-window leakage channel specifically | **Verified from data**: structurally absent (0.0000% at all 7 origins, pooled and per focus item) — a mechanical consequence of `load_data_full.py`'s existing `forecast_date >= createDate` cleaning rule, not a new safeguard | High | **No impact — fully resolved** for this specific channel. |
| 3. Pricelist version history for backtest-consistent classification | **Cannot be determined**: no dated historical pricelist snapshots exist anywhere (not in git — `reference/` is `.gitignore`d; not on disk — single file, single mtime) | High confidence in the *absence* | **Requires a documented assumption to proceed, non-blocking.** If an item's division/Type/status changed between a past origin and today, today's classification is silently applied retroactively in any rolling-origin evaluation. This cannot be measured or bounded with what exists today. Phase E1 should proceed on the assumption that classification has been stable, stated explicitly as an assumption, not proven. |
| 4. Model settings tuned on future data | **Verified from data** for leakage: absent for all six adopted models (MA windows are fixed untuned constants; Croston/SBA constants are hardcoded in the third-party `statsforecast` library, never touched by project data). **Configurable assumption** for the MA windows' *rationale* (3/6/12 was never shown to be selected by observing full-dataset performance, but there is also no evidence it was tuned that way — absence of a documented selection process, flagged per `CONVENTIONS.md`'s unsourced-figure rule) | High | **No leakage impact.** The MA-window provenance gap is a documentation matter, not a blocker. |

**Overall E0.1 verdict**: no leakage found in either checkable mechanism (shares, model settings).
Two items remain open in the same category as pre-existing Phase A open items (revision timing,
pricelist version history) — both **non-blocking for E1**, to be carried forward as documented
assumptions, not new discoveries requiring a re-run.

### E0.2 — Cancellations in the demand series

**Verdict: cannot be determined, entirely, for all four sub-questions.** Validator 2 was blocked
before any query could run: `pyodbc.InterfaceError` — "Login failed for user 'jetniphat.boo'...
The password of the account has expired" (SQL error 18487), reproduced on two independent attempts
(a trivial `SELECT 1` and an `INFORMATION_SCHEMA.COLUMNS` lookup). This is an infrastructure
failure, not a data finding — Validator 2's own report is explicit that "no number in this report
should be read as a finding."

| Sub-question | Verdict |
|---|---|
| 1. `Cube_CES` Cancel rows: count, value, date range (fresh pull) | Cannot be determined |
| 2. Cancelled (contract, item) pairs still `Actual`/`MPS` in `cube_Sale_APD`, by division/month | Cannot be determined |
| 3. Share of total/Type demand; effect on the 3 focus items | Cannot be determined |
| 4. Partial cancellations (`PlanQty > ActualQty + BacklogQty`) bucketing | Cannot be determined |

**Consequence for Phase E1: this is BLOCKING**, not merely a documented-assumption gap. Phase
E1's Max-Min calculation and simulation consumes the demand series as-is; if cancelled orders
remain counted as `Actual`/`MPS` demand, Phase E1 would size safety stock and reorder points
against inflated demand — a policy error, not a rounding error, and one whose direction (over-
provisioning) and magnitude are both currently unknown. Validator 2 declined to substitute the
stale table-wide `Cancel = 2,423` figure (STATUS.md, 2026-08-31) for this task's specific
questions, correctly per the ground rules: that figure predates the pricelist-based division
correction, has no value/date breakdown, and does not answer the cancelled-pair-overlap or
partial-cancellation questions this task asked, which no prior session ever ran. Table 1's own
existing finding that "demand is not censored by stockouts" (STATUS.md §3, Business Findings) is
a *different* question — that a stockout does not suppress a demand record — and does not bear on
whether a *cancelled* order still counts as demand once entered. The two should not be conflated.

### E0.3 — Placeholder coherence with Type totals

**Verdict: verified from data for the arithmetic; genuinely two-sided (not resolved) for which
treatment to adopt.** No side is picked here, per `AGENTS.md` rule 9 — both positions are restated
with their evidence.

| Sub-part | Verdict | Confidence |
|---|---|---|
| Production Top-down is hierarchy-consistent today, before any placeholder is added | Verified from data (sum of item-level forecasts = Type-level direct forecast to within 0.0005 on 16 checked Types) | High |
| Option 1 (additive) vs. Option 2 (carve-out) numeric consequences | Verified from data (direct recomputation from `forward_test_log_all_divisions.csv` + `phaseC_placeholder_assignment_82items.csv`) | High |
| Which option is "better" | **Not determined — a genuine open decision, not a data gap.** Both are internally consistent arithmetic treatments with different, real trade-offs (see below) | N/A — decision, not a fact |
| Focus items (`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`) | Verified from data: unaffected by either option — none of their Types appear in the 82-item placeholder population | High |
| 66 of 82 items have an identifiable pricelist analogue/predecessor as a possible narrower forecast basis than the flat Type mean/median | Verified from data (pricelist facts) that a candidate exists; **supported hypothesis only** that using it would improve the forecast — not tested, explicitly flagged as outside a Validator's role | Verified (existence) / hypothesis (improvement) |

**The two positions, restated (neither picked)**:
- **Option 1 (additive)**: every real item's forecast is unchanged from today. Cost: the Type
  total (real + placeholder) now *exceeds* what the Type-level Combination model itself forecasts,
  by +0.8% to **+707.3%** depending on Type (worst: `Suspension Insulator`, PEM101, 6 placeholders
  outnumbering 3 real items at 7x their combined volume; also severe at `Current Transformer Type
  CDB`, PEM107, +513.8%). Any downstream Type-level use (capacity planning, roll-ups) silently
  disagrees with the Type model's own number.
- **Option 2 (carve-out)**: the Type total stays exactly fixed at today's real-item total by
  construction. Cost: every real item in an affected Type shrinks by the same proportion — from
  a 0.8% shrink (`LED Street light`) to an **83.7% shrink** (`Current Transformer Type CDB`) —
  with no change in that item's own historical demand. A planner would see a smaller number than
  "what my own history says," for a reason (other placeholder items in the same Type) they may not
  be aware of.

**Consequence for Phase E1**: **blocking, but only for the specific Types affected** — the 16
(division, Type) pairs with at least one placeholder item and at least one real sibling (see
Validator 3's table), plus the 2 Rule C Types with zero real siblings (`33kV Recloser`, `FRTU`,
which have no Type-level forecast to be additive-to or carved-out-of at all — an even more open
sub-case). **Every Type not touched by the 82-item placeholder population, including both Types
containing all three focus items, is fully unaffected and not blocked.** Phase E1's Max-Min for
the 22 affected (division, Type) groups' items cannot be finalized until a human chooses Option 1
or Option 2 (or another treatment), because the two options produce materially different item-
level and Type-level numbers to plan Max-Min against.

---

## 2. Gap register

| Gap | Decision affected | Evidence required | Owner | Blocking or non-blocking |
|---|---|---|---|---|
| **E0.2 — DB login `jetniphat.boo` password expired**, all four cancellation sub-questions unanswered | Whether the demand series double-counts cancelled orders as `Actual`/`MPS`; magnitude and direction of any resulting demand inflation feeding Phase E1's Max-Min | IT/DBA resets the expired SQL Server password (or issues a longer-lived service account) and updates `.env`; then Validator 2's task must be re-run in full (queries are already scoped in its report — join key `(ContractID/contractid, ItemCode/itemcode)`, `Cube_CES` value = `ActualPrice+BacklogPrice`, division attached via `sheet_to_division`, never filtered on `ManuDivision`/`division`) | IT/DBA (password reset); Validator/Orchestrator (re-run) | **Blocking.** Phase E1 cannot rule out cancelled-order contamination of the demand series until this runs. |
| **E0.1 — `forecast_date` revision-in-place timing** ("cannot be determined," re-affirmed by both Phase A and this re-check) | Whether the demand series' month-keying is trustworthy at every historical origin, or whether some rows' dates were silently revised after intake | An audit/history table or per-row modification-timestamp column (confirmed absent from the schema by two independent searches — Phase A and E0.1); absent that, direct IT/business confirmation of whether `forecast_date` is ever edited in place post-intake | IT/business (whoever administers `cube_Sale_APD`'s upstream system) | **Non-blocking**, per Validator 1's magnitude-bound finding: every test run (Phase A and this re-check) bounds any possible revision at under ~2.5% of rows with no consistent direction — too small, on the existing evidence, to overturn Phase E1's inputs. Carry forward as a documented assumption ("`forecast_date` fixed at intake"), not a proven fact. |
| **E0.1 — pricelist version-history gap**: no dated historical snapshots exist (not in git, not on disk; only the hidden-Version1-vs-visible-Version2 sheet pair shows item *existence* across two internal snapshots, never a date or an attribute value) | Whether an item's division/Type/status classification was different at a past rolling-origin than it is today — cannot be measured or bounded either way with what exists | Prospective snapshot collection going forward — this cannot be fixed retroactively. Validator 1 proposes either (a) archiving a dated, immutable copy of `reference/pricelist.xlsx` on every update, or (b) a small append-only `(item_code, division, type, status, effective_date)` table | Whoever maintains the pricelist workbook | **Non-blocking** for E1 (no measured effect found, only an unbounded theoretical channel), but should be started now since it cannot be closed retroactively — every month without it is unrecoverable history. |
| **E0.3 — Option 1 (additive) vs. Option 2 (carve-out)** for the 22 (division, Type) groups touched by the 82 no-history placeholder items | Which item-level and Type-level numbers Phase E1's Max-Min plans against, for every item in those 22 Types (up to ±83.7% swing in a real item's own forecast between options, and up to +707.3% swing in a Type's planned total) | A business/Orchestrator decision on which treatment to adopt (or a third alternative) — this is a policy choice, not something further data analysis resolves | Business/Orchestrator decision-maker | **Blocking for the specific 22 Types' items** (see list in Validator 3's report / §1-3 table above); **non-blocking for every other Type**, including both Types containing all three focus items. |
| **E0.3 — 2 Rule C Types with zero real siblings** (`33kV Recloser`, `FRTU`) have no Type-level forecast at all today, so neither Option 1 nor Option 2's arithmetic even applies | Whether/how to forecast a Type with zero history-bearing members | A modelling/business decision on what a Type-level forecast means when there is no real-item data to build one from | Business/Orchestrator, informed by a Modeler if a numeric treatment is wanted | **Blocking for these 2 Types' items specifically** (3 items total: `SR-F-99-3381603`, `SR-F-99-3381603-01`, and the `FRTU` item) — currently `placeholder_qty = null`, i.e. zero forecast. |
| **E0.3 — 66 of 82 items have an untested pricelist analogue/predecessor** as a possible narrower forecast basis than the flat Type mean/median | Whether a better item-specific placeholder basis exists than the currently-assigned Type mean/median, for those 66 items | A Modeler would need to backtest each candidate-based forecast against the current Type-mean/median placeholder — not attempted, explicitly out of a Validator's role | Modeler (future work, not yet scheduled) | **Non-blocking.** The current Type mean/median stands as the interim basis; this is an improvement opportunity, not a defect requiring resolution before E1. |
| **E0.3 — 14 items (10 `Current Transformer Type CDB` + 4 `Current Transformer Type CEL`) plus 2 more (`Medium Voltage Capacitor`, `FRTU`) have no identified analogue at all** | Whether any basis better than the flat Type mean/median exists for these 16 items | Cannot be determined from the pricelist data available — the sub-family structure genuinely has no narrower split to offer | N/A (structural limit of the data, not an assigned owner) | **Non-blocking** — these already fall under the general Option 1/2 decision above; no separate action is implied. |
| **E0.1 — MA window (3/6/12) selection rationale undocumented** | Whether the moving-average windows were chosen defensibly or are an arbitrary convention | No selection-process record exists in STATUS.md beyond "standard quarterly/half-year/annual" convention (`config.yaml`'s own comment) | Whoever owns the model configuration going forward (Orchestrator/Modeler) | **Non-blocking** — no leakage mechanism exists regardless of how the windows were chosen (structurally incapable of leaking, per Validator 1); this is a documentation/rigor gap, not a correctness gap. |

---

## 3. Documentation corrections requested by the review

Per the task brief, these are recommended wording additions for the Orchestrator to apply to
`STATUS.md`/`CONVENTIONS.md` — not applied here.

**(a) Recommended addition — scope limitation of the whole demand series, not a bug:**

> **The demand series is built from PO receipts, not from all customer demand.** `createDate`
> records when a purchase order is received, and every downstream figure (forecasts, Max-Min,
> simulation) is built from rows that reached that stage. This means the series is systematically
> blind to demand that never became a recorded order — a customer who asked and was turned away
> for lack of stock, a quote that was never converted, or a sale lost to a competitor before a PO
> was ever raised. This is a structural scope limitation of this project's entire modelling
> approach, not a data-quality defect and not something any cleaning step can fix, because the
> missing demand was never recorded anywhere in the first place. (This is distinct from, and should
> not be conflated with, the already-recorded finding that the series is *not* censored by
> stockouts once an order is placed — STATUS.md §3, Business Findings, "the demand series is built
> from PO receipts, not shipments": that finding is about orders that *were* placed still being
> recorded even when stock could not fulfil them on time; this addition is about demand that never
> reached the point of becoming an order at all.)

**(b) Recommended addition — what cross-cube agreement does and does not prove:**

> **Agreement between two cubes that share an upstream source demonstrates consistency, not
> correctness.** This project has repeatedly cross-checked `cube_Sale_APD` against `Cube_CES` (e.g.
> STATUS.md's "Cube_CES deep dive, reconciliation..." entry: 99.79% row-level match; qty/value
> agreement within 0.003%/0.12%) and treated high agreement as validating the underlying figures.
> High agreement between two cubes/views that are both derived from the same underlying
> transaction system only shows the two views are consistent with each other — it does not
> independently verify that the underlying transactions themselves are accurate, complete, or free
> of the kind of systemic gap described in (a) above (e.g. two cubes fed by the same PO-receipt
> process would agree with each other just as well whether or not lost/unconverted demand is
> captured anywhere, because neither cube would ever see it). Any future cube-agreement finding
> in this project should be read as "consistent," not as "independently validated," unless a
> genuinely independent, differently-sourced check (e.g. a physical stock count, a customer-side
> record) is also performed.

---

## 4. Overall recommendation

**Phase E1 can begin now, but only partially — not in full, and not at all is too strong a
statement.** Concretely:

- **Blocked, project-wide, until E0.2 is unblocked**: any Phase E1 output should be treated as
  provisional with respect to demand-series integrity until the SQL Server login is restored and
  Validator 2's four cancellation sub-questions are actually answered. This is the one gap in this
  synthesis that is blocking for the *whole* series, not a specific slice of it, because a
  cancelled-order contamination effect (if it exists) would affect every division and Type, not
  just the ones already flagged elsewhere. Whether the Orchestrator treats this as a hard stop or
  proceeds with an explicit caveat (recording current E1 output as "subject to revision pending
  E0.2") is a judgment call outside this Synthesizer's role — the ground-rules-driven fact remains
  that E1's core input is unverified in a specific, named way for as long as this gap stands open.
- **Blocked, item-specific, until a human chooses Option 1 or Option 2**: the 82 placeholder
  items across the 22 (division, Type) pairs identified in Validator 3's report (roughly a sixth
  of the 445-code universe touched, none of it overlapping the three focus items), plus the 3
  items in the two Rule C zero-real-sibling Types, cannot have a final Max-Min computed until this
  decision is made — the two options diverge by up to 83.7% (real-item shrink under carve-out) or
  707.3% (Type-total inflation under additive) for the worst-affected Types.
- **Acceptable to carry forward as documented assumptions, not blocking**: E0.1's two open items
  (`forecast_date` revision-in-place timing, bounded at <2.5% of rows with no consistent
  direction; and the absent pricelist version history, an unbounded but currently unmeasured
  theoretical channel) — both are already the same category of caveat this project has carried
  since Phase A, and Validator 1 found no new evidence to change their non-blocking status.
- **Fully resolved, no impact**: E0.1's checkable mechanisms — historical allocation shares and
  model settings — both came back clean (leakage absent, high confidence), so no part of the
  locked `topdown_combination` method needs to be revisited on point-in-time-leakage grounds.

**In practice**: Phase E1 could proceed today, in full, for every item **outside** the 22
placeholder-affected Types and **with an explicit, dated caveat** that its demand-series inputs
are pending E0.2's cancellation check — that is the narrowest honest reading of "partially." A
stricter reading — waiting for both the DB password reset and the Option 1/2 decision before any
Phase E1 number is produced — is also defensible and is the Orchestrator's call, not this
Synthesizer's, per `AGENTS.md`'s division of roles.
