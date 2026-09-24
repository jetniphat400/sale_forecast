# STATUS

> **CALIBRATION WARNING (2026-09-23, Phase J2, Part 0) — READ BEFORE USING ANY FIGURE BELOW.**
> Phase J found that replaying the current inventory policy through the Section 16 simulation
> predicts single-digit fill rates (8.2% PEM101, 1.1% PEM103, 1.6% PEM107) while the business
> actually delivers 86-98% of units not-late — a calibration failure of 84-93 percentage points.
> **Every `stock_value`, `Min`, `Max` and `fill_rate` figure from Phases E0, E1, E1-fix, E1-fix-2,
> E2 (readiness and scoped pilot) and Phase I, wherever it appears in this document, is therefore
> marked UNCALIBRATED and must not be used for any inventory decision** until Phase J2 (below)
> establishes the real fulfilment mechanism. This is a blanket annotation covering every
> occurrence of these terms in every phase entry listed above — individual occurrences are not
> separately re-marked, and none of the historical text is deleted or rewritten. See the Phase J
> entry (calibration_gap) and the Phase J2 entry (this task) for the full account. This warning
> also applies to the widely-cited "73.2% on-time" figure: Phase J2 found it was `on_time_exact`
> (delivered exactly ON the due date), row-weighted, 2026 only — it excluded early deliveries and
> must never be used as a fill-rate benchmark; see METRICS.md Sec.19 and the Phase J2 entry for
> the corrected `not_late` figures that supersede it wherever it was used as a comparison.

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
  demand series is keyed on). **DONE (2026-09-02), answered with caveats — none of the three
  closes with full certainty; see Current Status Summary and the detailed log entry below.**
- **B — Close Phase 2 down to item level**: item-level forecasting, cross-division demand,
  no-history items, forward-test log rebuild, missing tests, and an end-to-end pipeline.
- **C — Expand to all 445 item codes**: PEM102, PEM103, PEM104, PEM107 and CI101.
- **D — Phase 4 groundwork**: **narrowed 2026-09-04 by business input (see Section 8)** — three
  checks against `Cube_Inventory_Exact` (which warehouse stages hold sellable stock, an
  approximate holding-cost figure, whether CI101-sheet products sold under PEM101 are held in
  PEM101 stock), not a search across all tables. Finished-goods movement history is no longer
  sought — business confirmed it does not exist. Assembly time stays open, still needs business/
  production input. Runs only after Phase C, never in parallel with it.
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

### Current Status Summary (2026-09-24)

**PROJECT_GRAPH.md is the authoritative source for goal/question/node status; this summary is a
regenerated snapshot of it, not an independent status record kept by hand.**

- **G1 (sales forecast)** — in progress. Top-down Combination forecasting method adopted and
  locked (D1-D4); Phase F (compare against the team's current method) not started. PEM103/PEM107
  were checked for a channel-mix recording bug that would require correcting the forecast/
  forward-test log before 2026-09-30 scoring — none found. (PROJECT_GRAPH.md, node G1.)
- **G2 (inventory policy)** — uncalibrated, scope split 2026-09-23; PEM101 robust ensemble built
  2026-09-24. Now covers PEM101 and PEM107 only; PEM103 moved out (feeds G3 via Q22); PEM104 was
  never in scope (see DE4). PEM101's METRICS.md §22 robust_minmax ensemble (139 members, all 3
  usable-stock definitions, 0 collapsed by dedup) is built: all 112 eligible items are SENSITIVE
  (range_ratio≈8.0, driver `r_months`) at every threshold tested (1.10/1.25/1.50) — zero robust
  items. The usable-stock-definition choice does not move any item's Min/Max (V2). The stock_value
  vs. not_late trade-off curve is built and shown on the inventory page with today's point (98.28%
  not_late, THB 18.25M) marked inside the envelope — choosing a target point on it is blocked on a
  person. (PROJECT_GRAPH.md, node G2.)
- **G3 (operations plan)** — blocked on a person. Needs business input on Q19 (assembly/
  inspection time), Q20 (capacity) and Q21 (MTS/MTO/ETO split) — each blocked on a person; Q17
  (batch cadence/size) is separately in progress, blocked on data (a working `cube_final`
  connection), not on a person; Q18 (BOM/shared components) is resolved. (PROJECT_GRAPH.md, node
  G3 and nodes Q17-Q21.)
- **PEM101** — G1 method locked. G2: partially calibratable (59 of 4,130 grid combinations fit
  both periods within tolerance; no single parameter uniquely identified). Robust ensemble
  (METRICS.md §22, 2026-09-24): 0 of 112 eligible items robust at range_ratio≤1.25 — every item is
  sensitive, driven by the reorder level (`r_months`); the usable-stock-definition assumption does
  not affect this. Trade-off curve ready; a target service level is blocked on a person.
  (PROJECT_GRAPH.md, nodes Q10, G2.)
- **PEM102** — covered only by the project-wide G1 forecasting-method decision (D2, Top-down
  Combination); PROJECT_GRAPH.md carries no division-specific open question for PEM102.
- **PEM103** — moved out of G2. Q22: answered (level A) — transformers/tendering-pipeline
  business; the production mechanism itself is still pending EF1 (blocked on data). Q10: not
  calibratable to a stock-based policy (would need 5-12x more capital than the business holds).
  (PROJECT_GRAPH.md, nodes Q10, Q22.)
- **PEM104** — closed, dead end (DE4). Made to order by business model; no stock policy
  applicable. (PROJECT_GRAPH.md, node DE4.)
- **PEM107** — in G2's scope, but Q10: not calibratable under any tested parameter set (implies a
  genuine operational change between 2024-2025 and 2026, not a search failure). Q23: the 2026
  channel-mix reversal is a business change, not a recording change; the capacity-diversion
  hypothesis survives, at level H, not proven. (PROJECT_GRAPH.md, nodes Q10, Q23.)
- **CI101** — covered only by the project-wide G1 forecasting-method decision (D2); PROJECT_GRAPH.md
  carries no division-specific open question for CI101.

**This summary is regenerated from PROJECT_GRAPH.md at the close of every task** — it is not
hand-maintained between tasks, and must not be edited without first re-checking PROJECT_GRAPH.md
is itself current.

*Full evidence, methodology and per-task detail for every phase is preserved in the detailed log
below, in chronological order. The detailed log uses the phase numbering (3.1, 3.2, 4) in effect at
the time each task was completed; that numbering is superseded by the A-F plan and is not renamed
retroactively.*

---

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
**Correction (2026-09-04): `division = 'PEM101'` was this pilot's condition, not the project's
scope — this sentence was later wrongly generalized into a project-wide rule; see Locked
Decisions, "Project scope correction," for the fix. The underlying point (queries need the
`division` column, not just category/type name, because names collide across divisions) still
stands project-wide; only the single fixed value `'PEM101'` was wrong as a universal rule.**

**Phase 2 — Model Selection: DONE.** The selected approach is Combination forecasting — the
arithmetic mean of the six candidate models (Naive, MA3, MA6, MA12, Croston, SBA) — applied at
Category and Type level, monthly granularity. Evidence: no single model won consistently at
any level; rule-based selection (SBC, Kostenko-Hyndman, Petropoulos-Kourentzes) did not beat
combination; median and trimmed-mean variants were directionally better but not statistically
distinguishable from the plain mean. Aggregation to Category/Type level cut zero periods from
39.3% to 0% and the validation-to-test overfitting gap from 127% to under 4%. All methods
under-forecast on average — expected, since point forecasts target the mean while real demand
contains spikes; this must be compensated through safety stock in Phase 4, not by changing the
model. **Phase A caveat (2026-09-02, moderate confidence)**: a meaningful but UNQUANTIFIED share
of this measured bias's magnitude may be inflated by one item's (`EEE-F-FC-1040010002`) real,
large 2025-collapse/2026-recovery swing landing inside the backtest's actual test window — see
the Phase A log entry below. The bias's existence is not in doubt (the structural reason above
still holds), but its exact SIZE should not be locked into a Phase 4 safety-stock policy before
this is isolated (flagged for the Modeler, not yet done).

**Phase A — Fix potentially wrong foundations: NEXT, not blocked.** Three checks, all answerable
with existing data. **Answered 2026-09-02** by a three-agent Explorer+Validator/Analyst/Validator
investigation, merged by a Synthesizer (per `AGENTS.md`) — full detail in the dated log entry
below and in `output/summary/phaseA_synthesis.md`; none of the three closes with full certainty:
1. **Whether `forecast_date` is revised after the PO is received rather than fixed at intake —
   UNRESOLVED, and found to be fundamentally undetectable from this data (no audit/history table
   or per-row modification timestamp exists anywhere in the schema), high confidence in that
   negative finding.** However, every test run bounds any possible revision at under ~2.5% of
   rows with no consistent direction — high confidence this is too small to explain either the
   6-day median notice or the 57.8%→73.2% on-time improvement. **Practical conclusion: the two
   headline figures are NOT overturned by this finding, but "forecast_date is fixed at intake"
   remains an assumption, not a proven fact.**
2. **Why 2025 sales fell 26% — ANSWERED, moderate-to-high confidence, mostly real not an
   artifact, but with a genuine partial confound.** The "26%" is a Jan-Jul-window-only figure
   (full calendar 2025 vs. 2024 is only -7.2%). 51% of the Jan-Jul decline traces to ONE item
   (`EEE-F-FC-1040010002` — one of this project's three focus codes) with a flat unit price
   throughout: a real volume collapse-then-recovery, not a price or classification effect, and
   the same item is separately the largest driver (46.5%) of the 2025→2026 recovery. No
   whole-population reporting/classification cliff was found (unlike the 2022/2023 and
   2023/2024 breaks). **But a real, partial customer-reclassification confound exists**: 26 of
   127 "dropped" customers (58.5% of that cohort's ฿46.24M value) actually continued doing
   business, just relabelled from Omni Channel/PEM101 to Tendering or another division — one
   account alone (`CS07977`) accounts for 23.6% of the whole headline decline this way. **Bias
   consequence, not resolved by this task**: since the dominant item's real recovery swing sits
   inside the Phase 2/3.1 backtest's actual test window, a meaningful but UNQUANTIFIED share of
   the measured forecasting bias may be inflated by this one item/window, separate from the
   already-recorded structural reason (point forecasts vs. spiky demand). Locking Phase 4 safety
   stock to the current bias figures without isolating this item's contribution risks baking in
   a one-time event's magnitude — flagged as a new, untested gap for the Modeler.
3. **Which date field the demand series is keyed on — ANSWERED, high confidence.** Direct code
   read confirms every pipeline script (`load_data.py`, `load_data_full.py`, `aggregate_levels.py`,
   `backtest.py`, `backtest_aggregate.py`) keys monthly aggregation on `createDate`, never
   `forecast_date`. **This is the wrong field for inventory-timing purposes.** Re-keying on
   `forecast_date` moves 11.53% of quantity and 14.98% of value to a different calendar month,
   materially changes at least one month for 86.6% of comparable items, and — most importantly —
   makes 72,889 already-placed, already-contractually-due units (2.15% of scope demand, 64,134 of
   them due the very next month) INVISIBLE to a `createDate`-keyed model, since they fall beyond
   its observed window. Recommendation (moderate-to-high confidence, conditional on item 1
   above): **re-key the series on `forecast_date`, captured as a frozen snapshot at time of use
   (not a live re-query)**, since item 1 could not rule out revision, only bound its impact as
   small. No code was changed to implement this — see the new Phase B action item below.

**Phase B, B1/B2/B3 — DONE (2026-09-02), single Modeler (per `AGENTS.md`: all three
aggregation levels needed in one view, each step depends on the previous — not split).** Full
detail, confidence levels and CSVs in `output/summary/b1_rekeying_report.md`,
`b2_bias_isolation_report.md`, `b3_item_level_approach_report.md`, and the dated log entry
further down.
- **B1 (re-key and re-run)**: `load_data.py`/`load_data_full.py` now pull `forecast_date`
  (frozen snapshot, recorded) alongside `createDate`, building BOTH monthly series (the
  createDate one kept as an exact alias under its original filename, nothing deleted). Fresh
  pull confirms Phase A's re-keying magnitude (-2.52% in-window qty this run, vs. -2.17% in
  Phase A — the small difference is real data growth between pulls, stated explicitly, not
  drift in method). **Re-run backtest result is genuinely mixed, not a clean improvement or
  regression**: train/val/test (the last 6 of 31 months) IMPROVES under forecast_date at every
  level (Item Combination MAE 389.4→353.2, -9.3%), but rolling-origin (7 origins across the
  whole series) WORSENS at every level (Item Combination MAE 391.4→432.2, +10.4%) — 21 of 21
  level/model cells material in BOTH evaluations, in OPPOSITE directions. High confidence in
  the numbers (cross-checked exactly against the existing `rule_part4_test_results_per_series.csv`
  before trusting the new pipeline); moderate confidence only in a proposed explanation (the
  test window sits where forecast_date's smoothing effect concentrates; not proven). **CORRECTED
  2026-09-02 (see the dated log entry below, and `output/summary/b4_leakage_and_windowposition_report.md`):
  this "window-position" framing was too generous — direct per-origin testing found the
  improvement is NOT a smooth gradient at Category/Type level (correlation ≈0, and the trend
  through 6 of 7 origins actually runs the WRONG way, getting worse as origins approach the
  present, before an abrupt reversal only at the exact final origin); only Item level shows a
  genuine, moderate gradual trend. The more accurate, narrower finding: the improvement is
  concentrated in one specific 6-month test window, not demonstrated to generalize.**
- **B2 (bias with item isolated)**: level-dependent, not one answer. At the item's own Type
  (`High Voltage Distribution Fuse Cutout`), excluding it removes 87-90% of Combination's bias —
  **substantially an artifact at that level, high confidence**. At Category level (`Fuse`),
  excluding it removes only 5-9% — **the negative bias PERSISTS as a real, broad property of the
  rest of the category, high confidence**. Control check (`Surge Arrester`, untouched) behaves
  as expected.
- **B3 (aggregation approach for item-level forecasting)**: compared Direct / Top-down /
  Reconciled at item level (forecast_date-keyed, test set). Top-down has the best point estimate
  (MAE 341.6 vs. 350.0 Direct vs. 350.0 Reconciled) but **no pairwise difference clears
  significance** (paired t all under 2) — stated directly, no approach is clearly better in
  general. **The one clear, well-evidenced finding: the benefit DOES depend on the item's share
  of its Type** — the dominant focus item (`EEE-F-FC-1040010002`, 48.3% of its Type) improves
  16.1% under Top-down; the two minor/mid-rank focus items barely move. High confidence in
  direction, moderate in magnitude (only one genuinely dominant item exists in this scope to
  test).

**Phase B — Close Phase 2 down to item level. B1/B2/B3 (the single-Modeler portion, per
`AGENTS.md`) DONE 2026-09-02** — re-keying, bias re-measurement, and the aggregation-level
question are answered below (full detail and confidence levels in the Current Status Summary
and the dated log entry further down). **Remaining Phase B work, NOT YET DONE**: the three
parallel-agent open items (₿60.6 million cross-division demand currently filtered out, since
inventory is shared across divisions and excluding 14.3% of demand would systematically
under-provision; the 16 items with no history and 15 with no sales, which must not simply be
dropped, since new items with no history are often the ones most likely to stock out; the
forward-test log, generated for 58 items and six models, which no longer matches the current
scope) and the single-agent technical-debt work (writing the tests `CONVENTIONS.md` requires,
and building a pipeline that runs end to end, since the 21+ committed scripts still have no
documented run order). **CORRECTED 2026-09-04 (see the dated log entry further down, and
`output/summary/synthesis_report.md` §3): the "16 items with no history and 15 with no sales"
figure above assumed a 31-item excluded population. A live re-derivation found this is WRONG --
the true population is 16 items total (the 15 are a SUBSET of the 16, not an additional 15 on
top); no second bucket of "rows present but zero total sales" items exists at this scope. All
three parallel open items in this paragraph (cross-division demand, no-history items, forward-test
log) are now DONE as of 2026-09-04 -- see the dated log entry below for full findings.**
**Phase B CLOSED 2026-09-04**: the remaining single-agent technical-debt work (tests, end-to-end
pipeline) is also DONE -- see the "Phase B closeout" dated log entry near the end of this section,
and the new Locked Decisions below (cross-division scope, the 6 excluded items, the 10 placeholder
items, and the final Top-down combination method with its evaluation policy). Phase C may now
begin.

**Phase C — Expand to all 445 item codes**, covering PEM102, PEM103, PEM104, PEM107 and CI101.
**Step 1 (data quality) DONE 2026-09-04** — five parallel Validators plus a Synthesizer, per
`AGENTS.md`; full detail in the dated log entry below and `output/summary/phaseC_synthesis_report.md`.
**Every one of the five divisions differs from PEM101 in some material way — none is ready to
forecast unchanged.** Four (PEM102, PEM103, PEM107, CI101) need an explicit scope/filter decision
first; PEM104 is blocked on data volume. **Step 2 (Modeler backtest) is NOT yet started.**
**Scope corrected 2026-09-04, then corrected again the same day (Locked Decisions, "Project scope
correction" then "Division source-of-truth correction")**: the first correction decided to
exclude `-OLD`-suffixed divisions; the second reversed that — the pricelist is authoritative for
an item's division, and `division` is never used as a query filter at all, `-OLD` tags included.
PEM102's and PEM107's scope/filter question is resolved by this reversal (no filter, so no
combine/exclude decision needed); CI101's cross-division question is likewise resolved (include,
automatically, since `division` is no longer filtered); PEM104 stays confirmed excluded from
**forecasting** specifically (placeholder for Phase 4, unrelated to the division-tagging
question); PEM103's Tendering-**channel** scope question remains open, unaffected by either
correction (it concerns `revenue_type`, not `division`).
**[SUPERSEDED — Q22, 2026-09-23 (business-confirmed, DATA_MAP.md §7), then Q23, 2026-09-24
(METRICS.md §21, this file's Phase Q23 and Phase 136 entries below): this question was later
picked up and answered. PEM103 is transformers, tendering-pipeline-driven business (Q22, level A);
PEM103 moved out of G2 (inventory policy) into G3 via Q22 (PROJECT_GRAPH.md); the 2026 channel-mix
reversal itself was tested and found to be a genuine business change, not a recording change (Q23/
Phase 136, level V2). Kept, not deleted — this sentence was accurate at the time it was written.]**
A full-scope re-validation on the
corrected basis (445 codes) is DONE — see the dated log entry below and
`output/summary/phaseC_revalidation_report.md`: no double-counting found between `-OLD`-tagged
and normally-tagged rows, PEM102/PEM107 regain their 2024 history, CI101's totals rise 59.94%,
PEM102's 38.40%, PEM107's 90.01%. **Broader per-division readiness verdicts (collisions, pricelist
mismatches, demand classification) are RE-DERIVED for PEM102, PEM107 and CI101 (DONE 2026-09-07,
see the dated log entry below and `output/summary/phaseC_step1revised_synthesis_report.md`) — the
three divisions whose value changed materially (38-90%). PEM101, PEM103 and PEM104 were NOT
re-run (their value changed under 3%); their step 1 verdicts stand as originally recorded.**
Headline: **CI101 upgraded to "ready as-is"** (its only real blocker was the cross-division scope
question, now resolved automatically); **PEM102 and PEM107 keep the same verdict wording ("ready
after specific fixes") but each division's single biggest original blocker — the `-OLD`-tag
combination question — is now moot**, narrowing what "specific fixes" actually means for both. A
445-code consolidated item-status list and an 89-item no-history characterization are also DONE —
see the dated log entry below; the placeholder MECHANISM for those 89 items (Step 2 task list
item 2, below) is still not chosen.

**Phase C Step 2 — DONE (2026-09-07)** for the forecast-scope items (335 across 5 divisions; see
the dated log entry below and `output/summary/phaseC_step2_report.md`):
1. ~~Test Category and Type aggregation using value as well as quantity.~~ Summing units across
   different products within a category — e.g. fuse cutouts and fuse links — produces a figure
   without physical meaning (already flagged in Section 7, Red Team Review Findings,
   "Aggregating quantities across different products within a category has no physical meaning").
   Value aggregation is dimensionally consistent (currency sums regardless of product mix) and
   should be compared against the existing quantity-based aggregation, since part of the apparent
   benefit measured for quantity aggregation (the zero-inflation and overfitting-gap reduction
   reported in Phase 2) may be an artifact of that specific choice, not evidence that aggregation
   itself is meaningful for planning. **DONE 2026-09-07: zero-inflation reduction is IDENTICAL
   under both bases (a mathematical necessity, not an artifact of units); the overfitting-gap
   comparison is mixed (2 of 5 divisions better under value, 3 of 5 worse) — no evidence found to
   switch from quantity. Quantity basis is kept, by absence of a reason to switch, not a decisive
   win.**
2. ~~For the 89 items with no Omni Channel history~~ (found by the 2026-09-04 full-scope
   re-validation, `output/summary/phaseC_revalidation_report.md` §5), **the placeholder method is
   still not chosen.** The Validator will report, for each item: its Type, the number of sibling
   items in that Type with history, and how concentrated the Type is — so the placeholder logic
   can be chosen on evidence, not assumed. Candidate methods to record, not yet chosen between:
   Type mean; Type median (preferred where one item dominates the Type, as with the Fuse Cutout
   Type's focus item at roughly 60% of its Type's total sales value — see Locked Decisions,
   "Focus item codes"); mean of similarly-priced siblings; or flag-only for items with no usable
   siblings. **DONE 2026-09-07** — 7 of these 89 resolved earlier (the PEM104 overlap, excluded at
   division level, never part of this question). For the remaining 82, a fixed rule set was
   applied and written into `config/config.yaml` (`placeholder_rule_set`,
   `placeholder_item_assignments_82`): **Rule A (Type mean, top sibling <40%) — 50 items; Rule B
   (Type median, top sibling ≥40%) — 29 items; Rule C (flag only, value 0, no siblings with
   history) — 3 items**, listed explicitly in the dated log entry below. See
   `output/summary/phaseC_closure_report.md` Part 2 for the full evidence and the 40% threshold's
   status as a stated assumption, not a derived value.

**PHASE C — CLOSED (2026-09-07).** All Phase C work is done: step 1 (data quality, all six divisions), the division source-of-truth
correction and its full-scope re-validation, step 1 revised (PEM102/PEM107/CI101 readiness
re-derived), step 2 (forecast all 335 in-scope items, value-vs-quantity test, transferability),
and this closure (final transferability table, placeholder rule set for the 82 no-history items,
forward-test scoring readiness, config lock-in). Full detail in the dated log entry below and
`output/summary/phaseC_closure_report.md`.

**Consolidated item status, all 445 codes** (updated 2026-09-07, see the dated log entry below for
the full breakdown): **forecast 335; placeholder Rule A (Type mean) 50; placeholder Rule B (Type
median) 29; placeholder Rule C / flag-only 3 (no number invented); placeholder — method already
assigned 10 (pre-existing, PEM101-pilot-scope decision, unaffected by the new rule set); excluded
18** (12 PEM104 division-level + 6 listed-but-never-sold). **335 + 50 + 29 + 3 + 10 + 18 = 445**,
reconciling exactly against the full pricelist item-code universe (Rule A/B/C together are the 82
no-history codes; Rule C's 3 are a subset of that 82, listed separately only because the task
asked for the flag-only count named explicitly, not because it is a further, separate bucket).

~~Remaining work before Phase D: the item-specific model check for the three focus codes~~
(`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`) — Phase C's transferability work was
division-level (Top-down vs. Direct vs. Naive, per division); it had not yet specifically
re-examined whether Top-down remains the right choice for these three codes individually, given
they are this project's designated focus items for every phase. **DONE (2026-09-08)** — see the
dated log entry below and `output/summary/focus_item_model_selection_report.md`. **Verdict: keep
Top-down combination for all three** — no candidate (of 11 evaluated: Naive, MA3/6/12, SES, Holt,
Croston, SBA, TSB, Combination, Top-down) beats it with statistical significance on any item.
Phase D may now proceed.

**Phase D — Phase 4 groundwork — DONE (2026-09-08).** Narrowed 2026-09-04 by business input
(Section 8) to three checks against `Cube_Inventory_Exact`, run as three parallel Explorers plus a
Synthesizer (per `AGENTS.md`). Full detail: `output/summary/phaseD_synthesis_report.md` and the
three Explorer reports (`phaseD_check1_report.md`, `phaseD_check2_report.md`,
`phaseD_check3_report.md`). Headline, stated as plainly as the checks themselves state it:
**confirmed-sellable stock is 0.00% of the in-scope snapshot; 99.90% is undetermined** (the
schema has no sellability field — this is a genuine data limit, not a data-pull failure). Total
priced stock value: **THB 37,399,005.48** (capital tied up, not an annual cost — Check 2 also
caught that `cube_Sale_APD.cost` is a line total, not a unit cost, before computing anything, a
correction that matters by 1-2 orders of magnitude). CI101/PEM101 stock: 6 of 12 relevant CI101
items co-locate with PEM101's own warehouse codes, downgraded to `SAME_BUT_UNDETERMINED` since
those codes are shared across 3-4 divisions table-wide, not distinctively PEM101's. **10
assumptions Phase E must record in config, since the data could not answer them** — see the dated
log entry below for the full list. Phase E may now proceed, with those assumptions stated
explicitly rather than buried in code.

**Follow-up, DONE (2026-09-09)**: tested the business's warehouse-trailing-digit hypothesis
(`FG01`/`FG21`→PEM101, `FG02`→PEM102, `FG07`→PEM107, etc.) against a full division×warehouse
cross-tab. **Holds on the 3 codes it can actually be tested on (FG01/FG21/WH21→PEM101), but that's
narrow — most of its other predicted codes hold zero current stock, so it's untested (not
confirmed) for 4 of 6 divisions. Moderate confidence, not clean; does not resolve sellability.**
`FG21` and `FG02` are confirmed **distinct** (moderate-to-high confidence), not the same code
recorded two ways. See the dated log entry below ("Warehouse/division trailing-digit mapping
hypothesis test") and `output/summary/whmap_report.md` for the full six-part evidence.

**Inventory panel — DONE (2026-09-08), extended with Reserved/Available (2026-09-10).** Not a
phase deliverable — a live detail view built on top of Phase D's own source table
(`Cube_Inventory_Exact`), opened from the "Inventory — แผนสต็อค" row on Tab 1 (Tab 2/`#omniTab` is
untouched by any of this work). One script, `src/build_inventory_dataset.py`, reproduces
`data/inventory.json` in a single run: the full 445-code pricelist registry (every visible sheet,
not just the 335-item forecast scope), on-hand quantity summed across warehouses per code, and —
added 2026-09-10 — outstanding backlog and Available. See the two dated log entries below
("Inventory detail view added to Tab 1" and "Reserved/Available added to the Inventory panel, plus
the Reserved-source investigation chain") for full detail, and "Business Findings" and "Open
Questions" for what the investigation behind Reserved actually settled and what it left open.
**The panel's own current numbers** (this repository's committed `data/inventory.json`): 166
has_stock / 222 zero_stock / 57 no_db_record of 445 codes; 92 codes show negative Available.

**Phase E — Phase 4 proper**: calculate Max-Min and simulate it against historical demand.
**Phase E0 (pre-check gate) — three parallel Validators + a Synthesizer, then a single-Validator
E0.2 re-run — CLOSED (2026-09-18).** **[Any stock_value/Min/Max/fill_rate figure this phase feeds
into is UNCALIBRATED — Phase J2, see banner at top of file.]** See the dated log entries near the end of Section 2 and
`output/summary/phaseE0_synthesis_report.md` for full detail. Headline: no point-in-time leakage
found in allocation shares or model settings (E0.1); the DB login was reset and E0.2's cancellation
re-run found **zero** cancelled `Cube_CES` contracts resurfacing as `Actual`/`MPS` demand anywhere
in `cube_Sale_APD` (0 of 548 pricelist-scope pairs, 0 of 2,150 table-wide, positive-control-verified
join), so no change to the demand series is needed; the placeholder-vs-Type-total question (E0.3)
is resolved by a third option — placeholders excluded from Top-down hierarchy reconciliation
entirely (see Locked Decisions). **Phase E1 may now begin in full** — no remaining blocking gap;
the two non-blocking documented assumptions (`forecast_date` revision timing, absent pricelist
version history) carry forward unchanged from Phase A/E0.1.

**Phase E1 — bounded scenario pilot, PEM101's 128 items, single Modeler + independent Validator
(per `AGENTS.md`) — DONE 2026-09-18, with the Validator recomputation only PARTIALLY matching.**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance. See banner at top of file.]**
**This phase produces no actionable purchase recommendation — it is a scenario analysis for the
business to evaluate, not a locked policy.** Full detail: `output/summary/phaseE1_modeler_report.md`,
the five `phaseE1_{1..5}_*.md` sub-reports, and `output/summary/phaseE1_validator_report.md`
(including its two in-place addenda from the Orchestrator's targeted re-checks).
- **Scope, verified**: 128-item PEM101 pilot (Fuse Cutout + Surge Arrester categories), confirmed
  independently by both the Modeler (from `config['adopted_scope_file']`) and the Validator (from
  the pricelist directly) — exact match, 0 symmetric difference. 16 of 128 (6 `excluded_item_codes`
  + 10 `placeholder_item_codes`) get **no supported policy, no Min, no Max, no purchase quantity
  anywhere** — verified by direct set-intersection checks against every output file, zero overlap
  found by both agents independently.
- **E1.1 segmentation, hypothesis (reasoned recommendation, not certainty)**: of the 112 real
  items, 66 (Modeler) / 68 (Validator) — **65 of these in common, 95-97% agreement** — are
  FG-stock-policy-supported; the remainder are Component-stock/assemble-to-order candidates from
  their own segment numbers, not a blanket default. Make-to-order was ruled out project-wide (median
  6-day notice never exceeds the 45-60 day procurement lead time in this data). Assembly time
  (genuinely absent from any data source, business-confirmed gap) is a stated default (3 days) +
  alternative (7 days) + a 1/3/5/7/10-day sensitivity table.
- **E1.2 lead-time demand, verified**: protection period = lead + assembly + review interval = 4
  months at the default scenario. Empirical (not normal-assumption) protection-period demand
  distributions built per item; MASE-undefined items counted and excluded from aggregates
  explicitly, not silently dropped.
- **E1.3/E1.4 Max-Min and simulation, verified under stated assumptions — default scenario (60d
  lead, 3d assembly, 95% service level)**: **Min for the three focus items matches EXACTLY between
  the Modeler and the independent Validator once both used this project's own locked frozen-snapshot
  series** (`EEE-F-FC-1040010002` 10,788.20; `HS-F-99-02110` 917.50; `HS-F-99-0213` 763.75 — all
  three exact matches), as does the **forecast-consumption total for those three items (3,641.0
  units over the 4-month horizon — exact match)**. This is strong, high-confidence validation of
  the core forecast/consumption engine. Forecast consumption implemented as `net_period_demand =
  confirmed_known_demand + max(0, raw_forecast − confirmed_known_demand)` — confirmed orders never
  double-added to the statistical forecast. Sellable stock = on-hand qty in `FG01`/`FG21`/`WH21`
  only (config assumption, sellability itself never confirmed by any field).
- **Aggregate stock value and fill rate — genuine, reported discrepancy, not fully resolved
  (criterion 5 below).** Modeler: 66 items, mean *simulated, time-averaged* stock value THB
  55,399,687, simulated fill rate 98.99%. Validator (after two targeted re-checks corrected an
  initial live-vs-frozen data-window bug): 68 items, *static Max-level* stock value THB
  93,935,502.88, fill rate 99.91%. **Root cause identified, not a calculation bug in either agent**:
  (a) a small residual item-set disagreement (65 of 66/68 items in common — a segmentation-boundary
  effect, not a data error); (b) **a definitional ambiguity this Orchestrator introduced across the
  two independent briefs** — "total scenario stock value" meant *time-averaged simulated on-hand
  stock* to the Modeler vs. *static stock valued at the scenario's Max level* to the Validator; these
  are two different, both legitimate, statistics (an order-up-to-Max sawtooth policy's time-average
  is naturally well below its own Max, consistent with the ~1.7x ratio observed) that were never
  pinned to one definition before both agents computed them independently. **This must be resolved
  by picking ONE definition before Phase E1's stock-value figure is treated as fully validated** —
  not decided here, flagged for the next task/human decision.
- **Acceptance criteria — Orchestrator's verdict** (self-assessed by the Modeler, informed by the
  Validator; see the dated log entry below for full detail):
  1. Every item has a policy or a stated reason — **PASS** (128 = 66/68 FG-stock + 46/44
     Component-ATO + 16 excluded/placeholder, verified by both agents).
  2. Every assumption in `config.yaml` with an owner and scenario label — **PASS**, verified
     directly (`config['phase_e1_assumptions']`, every key comment-labelled, most with an explicit
     `_owner` field).
  3. No placeholder item ever receives a Min/Max/purchase quantity — **PASS**, verified by both
     agents independently (zero overlap in both checks).
  4. Default-scenario fill rate ≥ 73.2% AND stock value ≤ ฿37.4M — **fill rate PASSES by a wide
     margin under either agent's number (98.99% / 99.91% ≫ 73.2%); stock value FAILS under either
     agent's number and either comparison basis** (55.4M or 93.9M, for only 66-68 of 128 items, both
     exceed ฿37.4M — the cited full-445-item current figure — and both exceed ฿18.07M, the honest
     apples-to-apples current 128-item-pilot value computed directly in E1.5). **This conclusion is
     robust to the stock-value definitional ambiguity above — under EITHER definition, the default
     scenario ties up substantially more capital than today**, for FEWER items than today's 128.
     **[SUPERSEDED — Phase J2, 2026-09-23: 73.2% was on_time_exact, row-weighted, 2026-only —
     not comparable to fill_rate (METRICS.md Sec.19). The corrected not_late benchmark and the
     fill_rate figure itself are both UNCALIBRATED regardless (Phase J) — this criterion cannot
     be re-scored as a pass/fail without a calibrated model. Not re-evaluated here, per
     "do not delete" — see banner at top of file.]**
     Best explanation (hypothesis, not proven): a 95% cycle-service-level target over a 4-month
     protection period requires large safety stock against genuinely Erratic/Lumpy/Intermittent
     demand (e.g. `EEE-F-FC-1040010002`'s safety stock alone, 6,450.5, exceeds its own mean
     protection-period demand, 4,337.7) — the 90% service-level alternative (also computed in the
     18-scenario grid) narrows this gap, not adopted here since that choice is a business/Orchestrator
     call, not this phase's to make.
  5. **Validator recomputation matches — PARTIAL, not a clean pass.** Two of four figures (Min for
     the 3 focus items; the consumption total) match EXACTLY, high confidence — strong validation of
     the core engine. Two of four (aggregate stock value; fill rate) do NOT match under direct
     comparison; the gap has an identified, non-bug explanation (segmentation-boundary + definitional
     ambiguity, above), but per this task's own rule ("a mismatch stops the task"), **Phase E1 is NOT
     declared fully validated** — the stock-value definition must be pinned down and re-checked
     before this phase's aggregate figures (as opposed to its per-item Min/consumption figures) are
     treated as settled.
- **Net verdict: 3 of 5 acceptance criteria PASS cleanly (1, 2, 3); criterion 4 FAILS on stock value
  (robustly, under either agent's number) while passing on fill rate; criterion 5 PARTIALLY passes
  (exact match on 2 of 4 figures, an identified-but-unresolved definitional gap on the other 2).**
  This scenario, as currently specified (95% service level, 60-day lead time), is **not
  recommended for adoption as-is** — it costs substantially more capital than today for coverage of
  fewer items, and its own aggregate figures are not yet independently confirmed to one definition.
  The 90%-service-level alternative and the stock-value-definition question are the two most
  actionable next steps, both business/Orchestrator decisions, neither made here.

**Phase E1-fix — recompute under `METRICS.md`, single Modeler + independent Validator (per
AGENTS.md), 2026-09-21 — NOT fully validated; two root causes found, one is a genuine METRICS.md
ambiguity, one is a confirmed code defect.**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance. See banner at top of file.]** `METRICS.md` (new, 2026-09-19) was written as this
project's single source of truth for every metric formula, specifically to close the definitional
gaps (`stock_value`, the 66-vs-68 item segmentation) the original Phase E1 left open. This task
applied it. Full detail: `src/phaseE1fix_recompute.py` (Modeler), `output/summary/
phaseE1fix_validator_report.md` (Validator, independent, read none of the Modeler's files).
- **Part 0 — `METRICS.md` §14's confirmed-demand source, resolved by both agents independently,
  same direction, different magnitudes.** `Cube_Backlog` and `Cube_CES` (`Status='Backlog'`) are
  **not the same population** for PEM101 items (Modeler: 94-95% item overlap, qty differs 1.5%;
  Validator: 93.1% pair-level match, 3 items only in `Cube_Backlog`). Both agents independently
  chose **`Cube_CES`**, since §14 names it literally — this is a genuine convergent finding, not
  a coincidence. `METRICS.md` itself was **not edited** (per the task's own instruction) — this
  finding is reported for the human to fix the wording by hand if `Cube_Backlog` was actually
  intended.
- **Part 1 — segmentation, 76 (Validator) vs. 77 (Modeler) finished_goods_stock items — a
  near-exact, well-explained match, not a fresh instance of the original bug.** Both agents
  independently computed the SAME P50 annual value (**฿414,419.83**, exact match — strong
  confirmation the underlying annual-value methodology is now consistent). The single item of
  disagreement, `EEE-F-FC-5920-383-1000`, sits 2.01% below the 6/year frequency cutoff — traced to
  a plausible order-frequency-annualization span-end-date difference (a live "today" vs. a fixed
  reference date), not the old tie-break bug (confirmed fixed: `METRICS.md` §15's literal `≥`
  sidesteps the old `<=`-vs-`<` divergence entirely). Recorded in `config['segment_policy']`.
- **Part 2 — recomputation, MISMATCH on every item-level headline figure, root-caused to two
  distinct issues, not resolved by picking one agent's number (per the task's own rule: "a
  mismatch stops the task").**
  1. **A genuine, unresolved `METRICS.md` ambiguity (§3/§4): does the `ltd_distribution` rolling
     window use the SAME prorated (fractional-month) length as `LTD`, or round up to a whole
     number of months?** The Modeler applied the prorated length (~3.055 months, consistently, to
     both LTD and the distribution). The Validator prorated `LTD` by exact calendar days but used
     a **ceiling-rounded 4-month window** for `ltd_distribution` specifically (`ceil(93/30.44)=4`)
     — a shorter LTD point estimate paired with a longer empirical-percentile window. Neither
     agent's code is wrong relative to what `METRICS.md`'s text actually says, because the text
     does not say which. **This clause needs a human decision before Min/Max/stock_value/
     consumption can be called settled.**
  2. **A confirmed code defect, not an ambiguity: the Modeler's `safety_stock` implementation
     does not match its own cited formula.** `src/phaseE1fix_recompute.py`'s docstring states
     `safety_stock = percentile(ltd_distribution, sl) − LTD` (METRICS.md §4's literal text,
     correctly cited) but the actual code (line ~255) computes `percentile − cum.mean()` — the
     empirical distribution's OWN mean, not `LTD` (the forecast-based point estimate from §3).
     These are not the same quantity whenever the forecast and the historical average disagree.
     The Validator's implementation (`percentile − LTD`, matching §4 literally) is the one that
     actually follows `METRICS.md` as written — **this is not left as "ambiguous, don't pick
     one": the Modeler's code should be corrected to match METRICS.md before re-comparison.**
  - **Resulting figures, both reported, NEITHER treated as settled**: `stock_value` ฿72,138,975.38
    (Modeler) vs. ฿82,026,651.31 (Validator); focus-item Min `EEE-F-FC-1040010002` 9,993.27 vs.
    10,788.20, `HS-F-99-02110` 867.13 vs. 917.50, `HS-F-99-0213` 835.00 vs. 763.75 (mixed
    direction — consistent with two compounding, not one directional, causes); consumption total
    (3 focus items) 4,243.0 vs. 2,956.87; `fill_rate` 99.93% vs. 99.87%; `cycle_service_level`
    99.75% vs. 98.98%.
  - **What IS robust despite the mismatch**: acceptance criterion 4's verdict does not change
    under either agent's numbers — `fill_rate` clears 73.2% by a wide margin either way;
    `stock_value` fails the comparison ceiling by a wide margin either way (both ฿72.1M and
    ฿82.0M exceed both the same-scope `current_stock_value` figure and the previously-cited
    ฿37.4M full-445-item figure). The directional finding from the original Phase E1 — this
    scenario ties up materially more capital than today — **stands confirmed under a second,
    independent implementation**, even though the exact magnitude is not yet settled.
    **[SUPERSEDED — Phase J2, 2026-09-23: the 73.2% comparison used on_time_exact, row-weighted,
    2026-only (not comparable to fill_rate — METRICS.md Sec.19); both fill_rate and stock_value
    here are also UNCALIBRATED (Phase J). Not re-scored — see banner at top of file.]**
  - Cross-check counts (Modeler / Validator): `unit_cost_fallback` 24/7 (eligible-112 scope
    differs — not reconciled further, secondary to the two root causes above); `no_unit_cost_items`
    15/0 (FG-76-set) — flagged, not resolved; `MASE_undefined` 0/16 — the Validator's 16 is exactly
    the 6 excluded + 10 placeholder items (a scope-definition difference in what population MASE
    was averaged over, not a calculation disagreement); `unreliable` §4 percentiles 12/0 (FG-set) —
    also not reconciled, likely downstream of the same window-length ambiguity.
- **Acceptance criteria re-evaluated**: 1 (every item has a policy) — **PASS**, both agree
  (128 = FG + ATO + placeholder + excluded, counts differ only by the 1 boundary item). 2 (every
  assumption in config with owner+label) — **PASS**. 3 (no placeholder/excluded item gets a
  Min/Max) — **PASS**, verified by both. 4 (fill_rate ≥73.2%, stock_value ≤ comparison ceiling) —
  **fill_rate PASSES, stock_value FAILS, both robust to the unresolved ambiguity** (see above).
  **[SUPERSEDED — Phase J2, 2026-09-23: see the annotation on the entry directly above.]**
  5 (Validator recomputation matches) — **FAILS as literally asked**: item-level figures do not
  match; per the task's own rule, this is reported, not papered over, and the root causes are
  named precisely enough to be fixed rather than re-guessed.
- **Part 3 (inventory page) — built.** `forecast/inventory.html` (`src/build_inventory_page.py` +
  `_data.py`), 112 items embedded (77 FG + 35 ATO per the Modeler's own segmentation — will shift
  by ≤1 item once Part 1's boundary case is settled), 16 no-policy items in a separate list, 6
  Tier A controls (lead/assembly/review/service-level/holding-cost-rate/obsolescence-threshold +
  a sellable-warehouse checklist), 3 charts (stock_value-vs-service-level trade-off, Min-vs-current,
  sortable value-at-risk table), Thai scenario/non-recommendation disclaimer present. New
  assumption added: `holding_cost_rate_annual: 0.20` (midpoint of the already-flagged-unverified
  15-25% figure — Modeler default, not sourced).
- **Part 4 (Node/Python parity) — 2 of 2 passed, but this validates internal consistency of the
  Modeler's OWN code, not cross-agent correctness** — the page's JS and `src/phaseE1fix_recompute.py`
  agree with each other because both implement the SAME (currently-buggy) `safety_stock` formula;
  this test will need to be re-run once the code defect above is fixed.
- **Part 5 (mandatory visual verification) — NOT DONE.** Chrome extension was not connected when
  checked (both by the Modeler and independently by the Orchestrator, twice). No screenshots exist;
  `output/charts/inventory_verification/` was never created. **This remains an open requirement**,
  not silently waived.
- **Part 6**: dashboard "Inventory — แผนสต็อค" row now carries an additional `oplink`-styled
  sub-link to `forecast/inventory.html` (`stopPropagation()`-guarded so the row's existing
  click-to-open-panel behaviour is untouched) — reported, not silently overridden. Full test
  suite: 67 passed (65 + the 2 new parity tests, which per the note above need re-running after
  the code fix). PII scan of `forecast/inventory.html`: zero matches.
- **Net verdict: this task is NOT closed.** Two concrete, named follow-ups block full validation:
  (1) a human decision on `METRICS.md` §3/§4's `ltd_distribution` window-length wording (and
  optionally §14's Cube_CES/Cube_Backlog wording, per Part 0); (2) fixing
  `src/phaseE1fix_recompute.py`'s `safety_stock` line to match `METRICS.md` §4 literally, then
  re-running both the Node/Python parity tests and the Modeler-vs-Validator comparison. Separately,
  Part 5's mandatory browser verification still needs a working Chrome connection.

**Phase E1-fix-2 — close the two named follow-ups, 2026-09-22 — CLOSED for the items in scope;
two new, smaller, precisely-named ambiguities surface and are left for a human decision, not
picked.**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance. See banner at top of file.]** Directly continues the entry above; both named blockers are resolved.
- **Part 0 — `METRICS.md` §4 and §15 rewritten to remove the two ambiguities by hand** (user-
  authored replacement text, applied verbatim, only those two sections touched). §4 now requires
  the `ltd_distribution` window to be measured in exact DAYS, on the DAILY series when available,
  never rounded to whole months (monthly-bucket proration only as an explicit, reported fallback).
  §15 now fixes `annual_value`/`order_frequency` to the SAME trailing-12-month window ending at
  the data cutoff (not an item's own active span, not a calendar year).
- **Part 1 — Cube_Backlog vs Cube_CES(Status='Backlog'), PEM101 128-item scope, full pair-level
  diff — Cube_CES confirmed as the correct source, evidence strengthened beyond the prior
  aggregate-only check.** 273 of 273 Cube_CES(Backlog) pairs (100%) are corroborated in
  Cube_Backlog; the 8 pairs Cube_Backlog has that Cube_CES lacks are ALL independently confirmed
  `Status='Actual'` (already delivered) in Cube_CES's more current refresh (Cube_Backlog's
  snapshot lagged Cube_CES's by ~13.6 hours at check time) — using Cube_Backlog would have
  over-counted open demand by 421 units (0.9% of scope qty) at this snapshot. Full detail and
  recommended `METRICS.md` §14 wording (not applied, per the task's own instruction):
  `output/summary/phaseE1fix2_part1_report.md`.
- **Part 2 — `safety_stock` code defect fixed in all THREE places it existed**, not just the one
  named: `src/phaseE1fix_recompute.py` (Modeler), `src/investigations/phaseE1fix_validator.py`
  (Validator — was ALSO wrong, in a different way: `ceil(protection_period_days/30.44)`,
  explicitly forbidden by the corrected §4), and `src/inventory_recompute_reference.py` +
  `src/build_inventory_page.py`'s embedded JS (the interactive page's own client-side recompute
  engine carried the identical `percentile - mean` bug). A true DAILY rolling window (one day at
  a time) is now built server-side from the existing frozen raw snapshot
  (`output/data/raw_full_category_sales.csv`, unchanged, never a live pull) by two independently
  written loaders — `phaseE1fix_recompute.load_daily_series` and
  `phaseE1fix_validator.load_daily_history` — covering all 112 items with history (0 fell back to
  monthly proration). The page's own JS still uses the monthly-prorated fallback deliberately
  (only monthly `actual_history` is embedded, to keep page size reasonable) — flagged explicitly
  in its own comments, not silently narrower than the server-side computation. New regression
  test: `tests/test_phaseE1fix_safety_stock.py` (3 tests, fail under the old `percentile - mean`
  formula, pass under the corrected `percentile - LTD` one). `config['phase_e1_assumptions']
  .safety_stock_convention` corrected from the wrong `"percentile_value_minus_distribution_mean"`
  (previously documented as "algebraically identical" to the correct formula — it is not) to
  `"percentile_value_minus_LTD"`.
- **§15's trailing-12-month fix ALSO required code changes** (found while re-running Part 3, not
  originally scoped to Part 2): both the Modeler's `build_item_facts` and the Validator's
  `compute_annual_value`/`compute_order_frequency` still annualized over the FULL 31-month window
  (Modeler) or a live, ever-growing span from `date_range.start` to `today` (Validator) — neither
  matches corrected §15's literal "trailing 12 months ending at the data cutoff" wording, and
  this exact pair of behaviours is what the corrected §15 text's own resolution note names as the
  76-vs-77 root cause. Both fixed to the identical trailing-12-month window (2025-08 to 2026-07,
  derived from the frozen series' own last month, not hardcoded). `config['segment_policy']`
  updated (`p50_annual_value_thb`: 414,419.83 → 344,835.50; `result_counts`: 76/36/10/6).
- **Part 3 — Modeler-vs-Validator recompute: segmentation, P50, and all 3 focus-item Mins now
  match EXACTLY** (previously 76-vs-77 items, ฿72.1M-vs-฿82.0M stock_value).
  `stock_value` near-exact (Modeler ฿65,101,264.10 vs Validator ฿65,044,358.87, 0.09% apart,
  plausibly explained by each agent's own independent `unit_cost` median-window implementation,
  not re-traced item-by-item). Items within ±5% of a §15 threshold (both agents, exact match):
  `HS-F-99-0331`, `HS-F-99-1091` (both exactly at the 6/year frequency cutoff).
  **Two figures still differ, each traced to a specific, named, non-bug cause, not silently
  resolved:** (a) `fill_rate`/`cycle_service_level` (Modeler 99.94%/99.75% vs Validator
  97.90%/95.63%) — both scripts' own docstrings already say `METRICS.md` §10/11 define the
  formulas but not the historical-replay reorder-policy mechanics feeding them, and the two
  agents used genuinely different, both-reasonable policies (Min-triggered reorder vs periodic
  order-up-to-Max with different stockout-month accounting); (b) "consumption total" (Modeler
  4,371.0 units = `Σ confirmed`; Validator 2,956.87 units = `Σ open_demand`) — traced to a genuine
  `METRICS.md` §14 wording gap: the section is titled `forecast_consumption` (suggesting `Σ
  confirmed`, the amount "consumed") but its only formula produces `open_demand` (the
  complementary, NOT-yet-confirmed remainder); §14 never names which one "consumption total"
  means. Underlying per-item-month `raw_forecast` figures matched exactly between agents; a small
  (≤70-unit) secondary drift in `confirmed` for the current month was traced to the two scripts'
  live Cube_CES pulls using different "overdue" reference dates (frozen `snapshot_pull_date` vs a
  near-live `TODAY` constant) against a table that itself refreshes daily (Part 1's finding).
  Acceptance criteria: 1/2/3 PASS (unchanged); 4 fill_rate PASSES / stock_value FAILS under both
  agents (same directional verdict as before, now on near-exact figures); 5 (Validator match) —
  segmentation/P50/focus-Min/stock_value now match or near-match, fill_rate and consumption total
  still differ for the two named, non-bug reasons above. Full detail:
  `output/summary/phaseE1fix2_part3_report.md`.
- **Part 4 — inventory.html data rebuilt, Node/Python parity 2 of 2 PASS** at the default scenario
  and one non-default setting (45d/7d/14d/90%/15%), now validating the CORRECTED formula (both
  `src/build_inventory_page.py`'s JS and `src/inventory_recompute_reference.py` were fixed
  together, per Part 2). Disclosed, not silently hidden: the interactive page's OWN stock_value
  at the default scenario (฿62,928,846, monthly-prorated-fallback method) differs from the
  server-side Modeler headline (฿65,101,264.10, true-daily method) by ~3.3% — an expected,
  documented consequence of the page only embedding monthly history (daily would materially grow
  page size), not a defect; both are internally consistent with `METRICS.md` §4's own explicit
  fallback allowance.
- **Part 5 — mandatory visual verification DONE** (previously blocked on "Chrome extension not
  connected"; resolved here via a from-scratch raw-CDP script, not the extension). Own Edge
  instance launched (`--remote-debugging-port=9222`, `--user-data-dir` under the system temp
  folder, `--headless=new`), PID recorded and confirmed closed by PID only afterward (never by
  image name — verified live: the user's own pre-existing `msedge.exe` processes were confirmed
  still running, untouched, before and after). 10 of 10 applicable checks PASS on
  `forecast/inventory.html` (both Plotly charts rendered, disclaimer visible, a Tier A control
  change moves the displayed stock_value and redraws the trade-off chart, the item table sorts on
  header click) and `forecast/sales_report.html` (charts rendered, disclaimer visible, the Rolling
  Origin control redraws `chart-fva`); one check (sortable-table on `sales_report.html`) correctly
  reported N/A rather than a fabricated pass, since that page has no click-to-sort table. Dashboard
  Inventory/Sales links both resolve. Screenshots:
  `output/charts/inventory_verification/{inventory_default,inventory_changed_scenario,
  sales_report_default}.png`. Script: `src/investigations/phaseE1fix2_part5_cdp_verify.py`.
- **Part 6 — full suite 70 passed** (67 prior + 3 new `test_phaseE1fix_safety_stock.py` tests).
  Customer/company-name scan of all three rendered pages (`index.html`, `forecast/inventory.html`,
  `forecast/sales_report.html`): zero genuine matches (a few incidental hits on the generic words
  "customer"/"บริษัท"/"จำกัด" in explanatory prose and one product spec field, "Supply by
  Customer" — none is an actual customer or company identity).
- **Still open, left for a human decision, not picked here**: (1) whether `METRICS.md` §14's
  "consumption total" should mean `Σ confirmed` or `Σ open_demand` (Part 3); (2) whether
  `METRICS.md` should define the historical-replay reorder-policy mechanics behind `fill_rate`/
  `cycle_service_level`, or leave it an acknowledged Tier B modelling convention (Part 3); (3) the
  recommended §14 Cube_CES/Cube_Backlog wording from Part 1, so a future agent cannot reintroduce
  the Cube_Backlog-table convention by re-reading the section literally.

**Phase E1-fix-2 (round 2) — close both named ambiguities from the entry above, 2026-09-22 —
CLOSED.**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance. See banner at top of file.]**

`METRICS.md` §14 rewritten (confirmed_total and open_demand_total now two explicitly
distinct, separately-reported metrics, source clarified as Cube_CES not Cube_Backlog with the
Part 1 evidence cited inline) and §16 added (a fully-specified daily historical-replay
simulation, closing the reorder/receipt-timing gap §10/11 left open). Both scripts recomputed,
independent Validator confirmed, per AGENTS.md.**
- **Part 0** — the six commits from the prior entry were pushed to `origin/main`
  (`5cc4cad..2e04995`); this round's own six commits are pushed at the end of this entry.
- **Part 1** — `METRICS.md` §14/§16 replaced/added verbatim (user-authored text), only those two
  sections touched.
- **Part 2 — a genuine double-counting code defect was found and fixed while implementing §14's
  now-literal "deduplicated on contract + item."** The Modeler's first-pass implementation
  deduplicated MPS rows against themselves and Cube_CES Backlog rows against themselves, but
  never checked whether the SAME (item, contract) pair appeared in BOTH sources — which it
  routinely does (a contract committed as MPS typically also carries Cube_CES
  `Status='Backlog'`, Phase A). This doubled the 3 focus items' `confirmed_total` exactly 2x
  (8,602.0 instead of 4,301.0) until fixed to dedupe Cube_CES rows against the MPS set first,
  matching the Validator's already-correct method. A second, smaller inconsistency (the
  consumption horizon's final partial month used the full un-prorated forecast value, while LTD
  §3 prorates that same month by `frac_month`) was found and fixed for internal consistency.
  - **confirmed_total (3 focus items): EXACT MATCH after the fix** — Modeler 4,301.0, Validator
    4,301.0. **open_demand_total: near-exact** — Modeler 2,999.9, Validator 2,956.87 (1.4% apart),
    traced precisely to the two agents' different (both pre-existing, disclosed) horizon LENGTHS
    for the consumption calc specifically (Modeler 4 periods, Validator 5 — `METRICS.md` §14 says
    "over the horizon" without pinning an exact length). Full-scope (76 items, Modeler):
    `confirmed_total` = 31,326.0, `open_demand_total` = 344,564.5.
  - **fill_rate / cycle_service_level: near-exact, a dramatic convergence from the pre-§16 run.**
    Modeler 99.70% / 97.20%; Validator 99.72% / 97.25% (was 99.94% / 99.75% vs 97.90% / 95.63%
    before §16 existed — a ~2-point gap collapsed to ~0.02–0.05 points). **The tiny remaining
    residual is precisely traced, not left unexplained**: per-item Min matches exactly for 72 of
    76 items (§4's daily percentile, independently reproduced); Max matches exactly for 0 of 76
    (up to 214 units apart), because Max = Min + review-interval demand (§5) still uses each
    agent's own valid but different day-to-month proration convention (30.44-day average vs exact
    calendar days) — a difference that predates and is unrelated to §16, which is now identically
    implemented by both agents (independently coded: `src/phaseE1fix_simulation.py
    ::simulate_item_daily` vs `src/investigations/phaseE1fix_validator.py::simulate_item`).
  - **Unchanged, reconfirmed**: segmentation 76/36/10/6, P50 ฿344,835.50, stock_value
    ฿65,101,264.10 (Modeler) / ฿65,044,358.87 (Validator), focus-item Min 8568.5/858.0/610.0 —
    all identical to the round-1 entry above, as expected since §4/§15 were not touched this
    round. Full detail: `output/summary/phaseE1fix2_part2_report.md`.
- **Part 3 — page note added, page regenerated, parity re-passed, visual re-verification done.**
  `forecast/inventory.html` now carries a second, distinct note box (`#proration-note`, bilingual)
  stating explicitly that the page's own figures use monthly proration (not the daily window the
  pipeline uses) and citing the observed **3.3%** default-scenario `stock_value` gap (recomputed
  fresh this round: ฿62,928,846 page vs ฿65,101,264.10 pipeline = 3.34%, matches). Node/Python
  parity: 2 of 2 PASS (default + non-default). CDP visual re-check (own Edge instance, PID
  recorded and closed by PID only, temp profile deleted): 6 of 6 checks PASS — note present and
  visible, note contains "3.3", scenario disclaimer still visible, both charts rendered, the
  page's own displayed totals (stock_value/holding_cost/n_items) show real values, and a Tier A
  control change updates them live. **Scope note**: the page has never displayed
  confirmed_total/open_demand_total/fill_rate/cycle_service_level — those four are produced by
  the standalone scripts (console + CSV, verified in Part 2) — so "the four recomputed figures
  display" was read as this page's own always-displayed totals, flagged explicitly rather than
  silently assumed. Screenshots: `output/charts/inventory_verification/r2_inventory_{default,
  changed_scenario}.png`. Script: `src/investigations/phaseE1fix2r2_part3_cdp_verify.py`.
- **Part 4 — acceptance criteria re-evaluated.** 1 (every item has a policy) PASS — 128 = 76+36+
  10+6, both agents. 2 (every assumption owned+labelled) PASS, unaffected. 3 (no placeholder/
  excluded item gets a Min/Max) PASS, re-verified directly (0 violations). 4 (fill_rate ≥73.2%,
  stock_value ≤ comparison ceiling) — fill_rate PASSES by a wide margin under both agents
  (99.70%/99.72% ≫ 73.2%); stock_value FAILS under both (₿65.1M/₿65.0M ≫ the ₿12.1M
  current_stock_value ceiling) — same directional verdict as every prior run.
  **[SUPERSEDED — Phase J2, 2026-09-23: 73.2% was on_time_exact, row-weighted, 2026-only, not
  comparable to fill_rate; both figures are also UNCALIBRATED (Phase J). Not re-scored — see
  banner at top of file.]**
  5 (Validator
  recomputation matches) — **every figure now either matches exactly (segmentation, P50, focus
  Min, confirmed_total) or matches within a small, fully-traced tolerance attributable to two
  disclosed, non-blocking methodology choices `METRICS.md` still leaves as legitimate agent
  discretion (§5's day-to-month proration convention; the §14 consumption-horizon length) — no
  figure is left as an unexplained mismatch.** Full test suite: 70 passed. Customer/company-name
  and credential scan of all changed/new files: zero matches.
- **Net verdict: Phase E1 is CLOSED.** Both concrete, named blockers this round targeted (§14's
  confirmed-vs-open-demand wording, §16's undefined simulation mechanics) are resolved in
  `METRICS.md` and reflected in both independent implementations, collapsing every remaining
  Modeler/Validator gap from either "unexplained" or "large" (76-vs-77 items, ₿10M+ stock_value
  gaps, 2-point fill_rate gaps) down to either exact matches or small, precisely-traced,
  non-blocking residuals. **Nothing is reported here as still ambiguous** — the two items the
  prior round left open (§14 wording, §16 mechanics) are both now resolved; the two residuals
  found this round (proration convention, horizon length) are disclosed assumptions, not
  unresolved definitional gaps, and do not block adoption of the scenario's directional finding
  (this configuration ties up materially more capital than today, confirmed under yet another,
  now much tighter, independent cross-check).

**Phase E2 readiness — PEM102/PEM103/PEM104/PEM107/CI101 warehouse investigation, single
Explorer, 2026-09-22 — DONE, "other divisions have no stock" narrowed to a per-division, evidenced
picture.**
**[Any stock_value/Min/Max/fill_rate figure this phase feeds into is UNCALIBRATED — Phase J2, see
banner at top of file.]** Follow-up to Phase D's finding that warehouse codes named for these divisions hold
zero stock and 30/44 codes hold nothing — reversed the direction (item → warehouse, not
warehouse → division) across a verified, pricelist-sourced scope. Full detail:
`output/summary/phaseE2_readiness_report.md`; data `output/summary/phaseE2_*.csv`; scripts
`src/investigations/phaseE2_readiness_investigation.py`, `e2_deepdive.py`. Single DB connection
attempt, succeeded first try.
- **Scope discrepancy, reported not reconciled**: the task's stated "317 codes for PEM102+PEM103+
  PEM107+CI101" does not match the current pricelist (262 codes for those 4 divisions:
  26+87+136+13). 445 − 128 (the PEM101 pilot subset) = 317 exactly — "317" appears to mean
  "everything outside the 128-item PEM101 pilot," a different set. Used the **verified** 262 +
  PEM104's 12 = **274-code scope** throughout, not a fabricated 317.
- **Headline: 74–92% of each division's items have ZERO stock anywhere in `Cube_Inventory_Exact`**
  (CI101 46.2% stocked / PEM102 11.5% / PEM103 20.7% / PEM107 25.0% / PEM104 8.3%). Where stock
  exists: CI101 concentrated 95.7% in `FG01` (PEM101's own dominant code — co-location, not a
  CI101 location, matching Phase D Check 3's prior identical finding); PEM102 similarly small and
  mostly in `FG01`; **PEM103 and PEM107 have real, non-trivial stock in verified
  division-EXCLUSIVE warehouse codes found directly from the data, not from naming** — `FG23`
  (PEM103, 43 of its 70 units) and `FG27`/`WH22`/`WH24`/`FG22` (PEM107, 296 of its 707 units) —
  none of which match the trailing-digit naming hypothesis (PEM107's own predicted codes,
  `F107`/`WH07`, hold zero stock).
- **Shared warehouses (`FG01`, `FMTO`, `FMTS`, cross-checked against the FULL 445-item registry,
  all 6 divisions)**: all three are **shared locations holding separate stock, never genuinely
  pooled** — 0 item codes appear under more than one division in any of them (verified directly,
  not assumed from the pricelist's one-division-per-code rule).
- **Self-caught methodology correction, `Cube_Inventory_Aging`**: a naive pull summing `Stock`
  across all rows per item showed 236 items / 466,134 units — apparent large hidden stock. This
  is an artifact: the table is GL-account-level (one row per item×warehouse×`GLAccount`), and
  different GL accounts are NOT additive (proof: item `RS-F-99-090003` shows +34,574 under one
  account, +25,874 under a different account, and −30,677 under a third, all in the same
  warehouse). Matched against `Cube_Inventory_Exact`, `GLAccount 117100` is the physical-stock
  account for these divisions (98.8% match rate). **Restricted to that account: 61 items match
  `Cube_Inventory_Exact`'s 62 almost exactly (61/62 identical) — `Cube_Inventory_Aging`
  independently CONFIRMS `Cube_Inventory_Exact`'s picture, it does not reveal hidden stock.**
- **10 other tables checked** (systematic `INFORMATION_SCHEMA` search, 41 candidates narrowed to
  9 plausible + `cube_Contract` added by hand since its item column, `product_id`, is not
  `itemcode`-like and was missed by the search pattern — a reported gap): `information_state`
  (189 items present) is a sales/production order log (`state`∈{sale_actual, actual production},
  `company`='PMW' — not PEM/CI — has `forecast_date`/contract references), NOT stock.
  `Cube_tobe_received`/`Cube_Incoming_Receipt` are PO-receiving-pipeline logs, immaterial volume
  (58/123 units). `Cube_Inventory_Aging_PSL`, `Cube_Inventory_Exact_PPD`, `Cube_Inventory_Batch`,
  `Cube_Incoming_Wait`, `Cube_pr_monitoring`, `cube_Contract`: zero rows for this scope.
- **Verdict per division** (full evidence and confidence levels in the report): CI101/PEM102/
  PEM104 — HIGH confidence essentially no stock exists (independently confirmed by Aging); the
  sliver that exists co-locates with PEM101, not a hidden division-specific location. PEM103/
  PEM107 — HIGH confidence real stock exists in verified division-exclusive codes (not
  name-predicted); MODERATE confidence this generalises beyond the specific items tested (18/87,
  34/136). **Unresolved**: whether the 74–92% zero-stock population holds stock in a system
  outside the 11 tables checked here (a business question, not answerable from this data) or
  genuinely holds none.
- **Phase E2 implication**: none of the 5 divisions can reuse PEM101's `sellable_warehouse_codes`
  (`FG01`/`FG21`/`WH21`) unchanged — either the analogous codes are near-empty (CI101/PEM102/
  PEM104, too few items for a confident sellable-set) or a **division-specific
  sellable-warehouse list** is needed (PEM103 should include `FG23`; PEM107 should include
  `FG27`/`WH22`/`WH24`/`FG22` alongside the shared `FG01`) — a Tier A config assumption to record,
  not inferred from a name. PEM103/PEM107 have thin but real, evidenced ground to attempt a
  scoped Max-Min pilot on their stocked-item subset; CI101/PEM102/PEM104 cannot proceed to a
  meaningful on-hand-stock-based Max-Min on this evidence.

**Two-direction verification rule added to CONVENTIONS.md, and applied — 2026-09-22.** Phase D's
stock-absence error (above) was a single-direction check (warehouse-named-for-a-division →
stock) that a reverse check (item → warehouse) overturned for two divisions. `CONVENTIONS.md`
Data Correctness now requires any absence conclusion to be checked from at least two independent
directions before being recorded as a conclusion rather than a finding, and requires every
`STATUS.md` absence entry to name the directions checked; a Validator "confirmation" only counts
as a second direction when it is an independent recomputation, not a re-read of the same query.

- **E0.2 (cancellations) re-verified from the demand side — CONFIRMED, zero-percent finding now
  holds from BOTH directions.** E0.2 (`src/investigations/phaseE0_cancellations_validator2.py`)
  checked Cube_CES Cancel rows → cube_Sale_APD only. A new, independently-written script
  (`src/investigations/phaseE0_cancellations_validator3_demandside.py`, imports none of
  `validator2.py`'s code) checked the reverse: every one of the 128-item PEM101 pilot's 28,235
  demand-series rows (qty 3,448,724.0, value ฿719,767,457.96, Omni Channel, Actual+MPS,
  `createDate>=2024-01-01`) was matched to Cube_CES by `(contractid, itemcode)` and every
  matching Cube_CES status recorded. **Result: 0 demand rows classify as `ONLY_CANCEL` or
  `CANCEL_PLUS_OTHER`** — no demand row's pair is tagged `Cancel` in Cube_CES, under either test
  the task specified. The 3 focus items: 704 demand rows, 0 cancelled-survived. **Third signal**
  (demand pairs with no Cube_CES counterpart at all, a possible cancelled-and-purged contract
  signature): 4 pairs, 48 units, ฿106,920 (0.0014% of series qty) — dates recent and scattered
  (2024-11-08 to 2025-04-04, 3 different contracts), not resembling a cancel-and-purge pattern;
  not investigated further (immaterial, stopping rule). **Verdict: the zero-cancellation-
  contamination finding is now a genuine two-direction CONCLUSION, HIGH confidence** — full
  detail `output/summary/phaseE0_validator3_demandside_report.md`.
- **Audit of other single-direction absence claims in `STATUS.md` — single Explorer, read-only,
  no new checks run (scheduling list only, per this task's own instruction).** Full table:
  `output/summary/phaseE0_two_direction_audit.md`. 10 substantive absence claims found; 2 already
  resolved to two independent directions this session (Phase D stock; E0.2 cancellations, both
  above). Of the remaining 8:
  - **BLOCKING for Phase E2 (2)**: (1) sellable-warehouse determination — still **0.00%
    confirmed sellable, 99.90% undetermined** (Phase D Check 1); only warehouse-code → ledger
    behavioural evidence has ever been checked, and the reverse (sale-record → warehouse) is
    **structurally impossible with current data** (no warehouse field exists on any sales row) —
    this is not an unattempted check but a real data-model gap, and remains the E2
    `sellable_warehouse_codes` blocker named in the Phase E2 entry above. (2) 30 of 44 warehouse
    codes left `UNRESOLVED` by the `whmap` investigation (zero stock at that snapshot, so
    untestable) — Phase E2's own item→warehouse pull covered only the 5 target divisions' items
    against the full 445-item/44-code universe for the *shared-warehouse* check; a full sweep of
    all 44 codes against all 6 divisions from this same already-pulled data
    (`output/summary/phaseE2_0_full_registry_inventory_raw.csv`) would close most of this gap at
    near-zero additional query cost — flagged as a cheap next step, not run here per this task's
    instruction not to run new checks.
  - **Non-blocking (6)**: duplicate-detection tag-pair check (`-OLD` vs. normal, 0/11 confirmed —
    single exact-match key, no fuzzy-match reverse check); PEM103's 0 duplicate groups (same
    method-bound limitation); E0.1 leakage ("structurally absent" — a code-read proof, not an
    independent empirical recomputation); E0.3's partial-cancellation shortfall ("structurally
    empty for confirmed contracts" — Cube_CES-side only, no demand-side cross-check); the 6
    never-sold items (already cross-checked across 5 independent tables, not a single-direction
    relational claim); the PEM102-OLD/PEM107-OLD tag cross-check (already tested both tag
    directions). None of these bear directly on an E2 stock, segmentation, or sellable-warehouse
    input.
- **Full test suite: 70 passed** (unchanged — this task added an investigation script, not a
  pipeline change requiring a new test). Customer/company-name and credential scan of all new/
  changed files: zero matches.

**Phase E2 scoped pilot — PEM103 and PEM107, warehouse-code closure, page extension — 2026-09-22.**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance. See banner at top of file.]**
**[SUPERSEDED FRAMING — Phase J4, 2026-09-23 (STATUS.md Phase J4 entry; PROJECT_GRAPH.md node G2):
this entry treats PEM103 as a co-equal member of the same stock-policy Max-Min pilot as PEM107.
The following day, PEM103 was moved OUT of G2 (inventory policy) entirely and into G3 via Q22
(tender-pipeline/transformers business, level A) — a stock-based Max-Min policy is no longer the
right frame for PEM103 at all, independent of the calibration failure above. Kept, not deleted —
the figures and method below were a legitimate pilot at the time; only the "PEM103 belongs in this
policy" framing is superseded.]**
Closes audit item 4 from the prior entry, records the standing sellability assumption, runs the
first Max-Min scenario pilot outside PEM101, and extends the interactive page with a division
selector. Full detail: `output/summary/phaseE2pilot_report.md`; data
`output/summary/phaseE2pilot_*.csv`, `phaseE0part0_44code_classification.csv`. Scripts:
`src/phaseE2_pilot_recompute.py` (Modeler), `src/investigations/phaseE2_pilot_validator.py`
(independent Validator), `src/investigations/phaseE2_part4_cdp_verify.py` (visual check).

- **Part 0 — all 44 warehouse codes classified, item-to-warehouse direction, no new DB query.**
  Used the two pulls already on disk (`whmap_part1_division_by_warehouse_crosstab.csv`,
  2026-09-09; `phaseE2_0_full_registry_inventory_raw.csv`, 2026-09-21/22 — both full 445-item,
  6-division registries). **30 EMPTY** (zero nonzero rows for any division, both pulls — marked
  as such, not guessed), **11 EXCLUSIVE** to one division (`FG21`/`NCRM`/`W4-1`/`WH21`→PEM101,
  `FG22`/`FG27`/`WH22`/`WH24`→PEM107, `FG23`→PEM103, `FG24`→PEM104, `W122`→PEM102), **3 SHARED**
  across divisions (`FG01`→PEM101/PEM107/CI101/PEM102, `FMTO`→PEM101/PEM107/CI101,
  `FMTS`→PEM107/PEM103/PEM101/CI101). **0 UNRESOLVABLE** — every code resolved cleanly from the
  item-to-warehouse data alone. Recorded in `config.yaml` under the new top-level `warehouse_roles`
  key, one comment-cited entry per code.
- **Part 1 — sellability standing assumption recorded, applies to every division including
  PEM101.** Sellability cannot be verified from this data at all: no sales row carries a
  warehouse field, so the reverse direction (which warehouse a shipment came from) does not
  exist to check against. Every `sellable_warehouse_codes` entry — PEM101's original FG01/FG21/
  WH21 as much as the new PEM103/PEM107 entries — is a **business assumption standing in for a
  fact the data cannot supply**, recorded as such in `config.yaml`'s comment and here, not a
  verified fact. Confirming it requires the warehouse/operations team, not more data mining.
- **Part 2 — Modeler + independent Validator, PEM103 (87 items) and PEM107 (136 items), default
  scenario.** Segmentation, P50, and all 3 top-value items' Min: **EXACT MATCH, both divisions**.
  **Genuine finding, verified independently by both agents, not a bug**: PEM103's P50 annual
  value is exactly ฿0.00 (57% of its 87 items have zero trailing-12-month sales), so METRICS.md
  §15's literal inclusive-boundary formula (`annual_value >= P50`) classifies **all 87 items**
  `finished_goods_stock` — flagged for a human decision on whether §15 needs a zero-P50
  special case, not patched here. stock_value: PEM103 ฿186.4M/฿187.5M (0.58% apart), PEM107
  ฿50.2M/฿53.4M (6.34% apart) — both residuals traced to the same already-disclosed `unit_cost`
  methodology difference from the PEM101 rounds (Modeler: METRICS.md §1 literal; Validator: the
  inherited, looser `phaseE1_common.compute_unit_cost`), not a new or unexplained mismatch.
  fill_rate/cycle_service_level near-exact both divisions, same already-disclosed §5
  Max-proration residual. **Acceptance criteria, both divisions: fill_rate PASSES by a wide
  margin (92–98% ≫ 73.2%); scenario stock_value FAILS against on-hand value by one to two orders
  of magnitude (PEM103: ฿186–187M vs ฿6.06M on-hand; PEM107: ฿50–53M vs ฿3.28M on-hand)** — same
  directional finding as PEM101, not a recommendation to adopt as-is.
  **[SUPERSEDED — Phase J2, 2026-09-23: 73.2% was on_time_exact, row-weighted, 2026-only, not
  comparable to fill_rate; both figures are also UNCALIBRATED (Phase J). Not re-scored — see
  banner at top of file.]** Two-group reporting (items
  WITH on-hand stock vs WITH NONE, Min/Max still computed from demand for the latter, gap_to_min
  flagged as the full Min when on-hand is zero): PEM103 11 WITH / 76 WITHOUT; PEM107 33 WITH /
  103 WITHOUT.
- **Part 3 — division selector added to `forecast/inventory.html`.** Covers PEM101/PEM103/PEM107
  (enabled, own embedded item data + own sellable-warehouse checklist); CI101/PEM102/PEM104
  appear as disabled `<option>` entries with their exclusion reason as both a hover title and a
  permanently visible note list (never silently omitted). Node/Python parity: **6 of 6 pass**
  (default + non-default, all 3 enabled divisions) — `tests/test_inventory_parity.py`
  parametrized over division.
- **Part 4 — CDP visual verification: 24 of 24 checks PASS.** Own Edge instance
  (`--remote-debugging-port`, `--user-data-dir` under the system temp folder, `--headless=new`),
  PID recorded and closed by PID only afterward (verified live: pre-existing user `msedge.exe`
  processes untouched). Confirmed per division: switching updates the title, stock_value total
  (differs from the previous division every time), and warehouse checklist; both charts render;
  a Tier A control change updates the total and redraws the trade-off chart; disabled entries
  carry a non-empty exclusion note. Screenshots:
  `output/charts/inventory_verification/e2_{pem101,pem103,pem107}_default.png`.
- **Part 5 — full suite 74 passed** (70 + 4 net, the 2 old single-division parity tests replaced
  by 6 division-parametrized ones). Customer/company-name and credential scan of all new/changed
  files: zero matches.
- **Direction checks supporting each division's sellable-warehouse list, stated per
  CONVENTIONS.md's two-direction rule**: the DIVISION assignment (which division a warehouse
  code belongs to) is item-to-warehouse-verified, two independent pulls, for all of PEM101's
  FG01/FG21/WH21, PEM103's FG23, and PEM107's FG27/WH22/WH24/FG22/FG01 (Part 0 above). The
  SELLABILITY of those same codes (i.e. that finished, sellable stock — not WIP or a staging
  buffer — is what sits there) has only ever been checked from the warehouse-code → ledger
  behavioural-signature direction (Phase D); the reverse (sale → warehouse) does not exist in
  this schema (Part 1 above) — sellability itself therefore remains a **single-direction finding
  elevated to a stated business assumption, never a two-direction conclusion**, for every
  division without exception.
- **Unresolved / not decided here**: whether METRICS.md §15 should special-case a zero-P50
  division (PEM103); the larger (6.34%) PEM107 `unit_cost`-basis residual was not traced item-by
  -item, only attributed to the same known cause as the smaller PEM103/PEM101 residuals; whether
  PEM103/PEM107 should actually be adopted for any real Max-Min policy (acceptance criterion 4
  fails on stock_value for both, same as PEM101 — a business decision, not made here).

**Follow-up: zero-P50 amendment, PEM107 gap root cause, posting-delay measurement —
2026-09-22.** Resolves the first two "Unresolved" items directly above, and separately measures
the leakage guard's 30-day margin. Single Validator throughout; one DB connection attempt per
script, all succeeded; nothing committed/pushed, per instruction.

- **Part 1 — METRICS.md §15 zero-P50 rule, added verbatim; PEM103 re-segmented, VERIFIED (exact
  match, Modeler + independent Validator).** When a division's P50 annual_value is exactly ฿0
  (as PEM103's is — 57% of its 87 items had zero trailing-12-month sales), the value criterion is
  now undefined and not applied; classification falls back to `order_frequency ≥ 6/yr` alone. A
  second, informational-only P50 is also computed over annual_value>0 items so the reader can see
  what the value threshold would have been. **PEM103's split changes from all 87
  `finished_goods_stock` to 14 `finished_goods_stock` / 73 `component_stock_ato`** (informational
  P50 ฿1,470,200.00). Two items sit exactly at the ±5% frequency cutoff (`TF-F-99-2404223B1`,
  `TF-F-99-19044211AF1`, both 6.0/yr). **stock_value at the default scenario drops from
  ฿186.4M/฿187.5M to ฿80.44M/฿80.41M** (Modeler/Validator now agree to within 0.04%, far tighter
  than the pre-amendment 0.58% gap, since far fewer items now carry a contribution at all).
  PEM107 reconfirmed unaffected (nonzero P50, structural no-op). Implemented in both
  `src/phaseE1fix_recompute.py::assign_policy_metrics15` and
  `src/investigations/phaseE1fix_validator.py::classify_segment` (new optional
  `zero_p50_rule_used` parameter, default False — PEM101's existing caller unaffected, its P50 is
  never zero), reused by the E2 pilot Modeler/Validator scripts. Full detail:
  `output/summary/phaseE1fix2r3_part1_zero_p50_report.md`.
- **Part 2 — PEM107's 6.34% stock_value gap: traced item-by-item, root cause VERIFIED, NOT a
  proration convention.** Min matches exactly on every one of the 17 differing items — the gap is
  entirely in `unit_cost`. 51 of 68 items match exactly; **2 items
  (`VT-F-99-010820`, `VT-F-99-010722`) account for 97.0% of the gap magnitude**; the remaining 15
  are small/bidirectional and trace to the already-known `unit_cost_fallback` (<3-row) rule.
  METRICS.md §1 is explicit ("Omni Channel scope, Actual + MPS status") and not ambiguous — the
  Modeler's `compute_unit_cost_metrics1` applies this filter literally; the Validator's inherited
  `phaseE1_common.compute_unit_cost`/`query_sale_cost` applies no filter at all, so
  non-Omni-Channel rows (`'Total Customer Solution'`, `'Tendering'`, live-verified) leak into the
  trailing-12-month median for both flagged items. **No METRICS.md wording change needed — the
  proposed fix is a code fix**, not applied here per instruction: add
  `WHERE revenue_type = 'Omni Channel' AND status IN ('Actual','MPS')` to
  `src/phaseE1_common.py::query_sale_cost`'s SQL, matching what the Modeler's function already
  does. Full detail: `output/summary/phaseE1fix2r3_part2_pem107_trace_report.md`, per-item CSV
  `output/summary/phaseE1fix2r3_part2_pem107_item_trace.csv`.
- **Part 3 — leakage guard's 30-day margin: measured attempt, VERDICT no reliable signal exists,
  first-appearance cannot be reconstructed from `cube_Sale_APD`.** The 30-day margin
  (`config.yaml`'s `leakage_guard.min_margin_days`, entry above) was set by reasoning from the
  order-notice distribution, never from a measured posting delay — this task measured it directly.
  `timeStamp` re-confirmed, a **fourth** independent time (2026-08-30, 2026-09-03/04, now
  2026-09-21 at full Part-3 scope — createDate ≥ 2024-01-01, all divisions, 51,601 rows), as a
  full-table-reload artifact: 100% of in-scope rows land in one ~15-minute window on the run date,
  regardless of the row's own business age — it records when the table was last refreshed, not
  when a row first appeared, and destroys any historical per-row insert-time signal on every
  reload. A fresh `INFORMATION_SCHEMA.COLUMNS` check found no new insert/modified/audit-date
  column (same 8 date columns as the 2026-09-04 catalogue). `createDate`/`PODate` are themselves
  independently confirmed (cross-validated against `Cube_CES`, entry above) to be genuine
  business/contract dates, not database-write dates, so no "gap to earliest-written date" can be
  computed either — no earliest-written date is recorded anywhere in this table. **Proposed
  (not implemented): a prospective daily snapshot of row counts and max(createDate)/
  max(forecast_date), starting now, to measure the real gap going forward. The 30-day margin
  stays unchanged** — reasoned and evidence-grounded from order-notice, but not yet an empirically
  measured posting delay; `src/leakage_guard.py` and its config value were not touched. Full
  detail: `output/summary/phaseE2r3_part3_posting_delay_report.md`.
- **Full test suite: 74 passed** (unchanged — this task amended segmentation logic behind a
  `zero_p50_rule_used` guard that PEM101's existing tests never trigger, and added one read-only
  investigation script; no pipeline behavior used by any existing test changed).

**PEM107 unit_cost fix applied; snapshot collection started — 2026-09-22.** Applies the code fix
proposed (not applied) in the entry above, and starts the prospective posting-delay measurement
the same entry's Part 3 proposed in place of it. Nothing left unresolved from either.

- **PEM107 residual: RESOLVED, VERIFIED.** `src/phaseE1_common.py::query_sale_cost` now filters
  `revenue_type = 'Omni Channel' AND status IN ('Actual','MPS')`, matching METRICS.md §1 and
  `src/phaseE1fix_recompute.py::compute_unit_cost_metrics1`'s existing implementation exactly.
  Guarded by a new test, `tests/test_phaseE1_common_unit_cost.py` (2 tests, a Tendering-row
  fixture that must be excluded from the trailing-12-month median) — confirmed to FAIL against the
  pre-fix code (`len(result)==4` instead of 3, `unit_cost==25.0` instead of 20.0) and PASS against
  the fix, so the guard is a genuine regression check, not a tautology. Re-ran PEM107 Modeler +
  independent Validator live: **Modeler ฿50,193,755.92 (unchanged, it already filtered correctly)
  vs. Validator ฿50,163,250.39 (was ฿53,372,403.45) — residual now 0.0608% (฿30,505.53)**, below
  the 0.1% ceiling and tighter than PEM101's own 0.09% Modeler/Validator baseline. The remaining
  residual is the already-known, already-disclosed `unit_cost_fallback` (<3-row-window) threshold
  difference (1 of 68 PEM107 items falls back on the Validator's side) — the same residual class
  as PEM101/PEM103, not a new or unexplained gap; not traced further, per METRICS.md's own
  tolerance precedent. PEM103 unaffected (its residual was already the same fallback class, now
  0.036%). Re-ran `src/build_inventory_page.py` (full multi-division regeneration) and
  `tests/test_inventory_parity.py`: **6 of 6 pass** (2 scenarios × 3 divisions, Python/JS parity
  unaffected — the page draws unit_cost from the Modeler's own output files, which were already
  correct; this re-run is a confirming regression check, not a behavior change to the page).
- **Prospective posting-delay measurement: STARTED 2026-09-22.** New script
  `src/snapshot_daily.py` — single DB connection attempt, project-scope-filtered (same filter as
  `phaseE1_common.query_order_level`: `revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
  `createDate >= 2024-01-01`) — records run timestamp, total in-scope row count,
  max(createDate)/max(forecast_date), and per-createDate row counts for the trailing 60 days (one
  JSON-embedded field, so the file stays one row per run), appended to
  `output/snapshots/posting_delay.csv` (gitignored, not committed — generated output). Idempotent
  per calendar day (replaces, does not duplicate, a same-day re-run) — verified directly: ran
  twice, file stayed at 1 row both times, second run's timestamp overwrote the first's. **First
  live run succeeded 2026-09-22: 47,114 rows in scope, max createDate 2026-12-01, max forecast_date
  2027-08-31, 41 distinct createDates observed in the trailing 60 days.** Registered as a Windows
  Scheduled Task, daily at 06:00, current-user context (no stored password —
  "Logon Mode: Interactive only", matching the credential-safety requirement: nothing about the
  task registration writes or stores a password):
  ```
  schtasks /create /tn "SaleForecast_PostingDelaySnapshot" /tr "\"C:\Users\jetniphat.boo\AppData\Local\Programs\Python\Python312\python.exe\" \"D:\sale_forecast\src\snapshot_daily.py\"" /sc daily /st 06:00 /f
  ```
  **Confirmed existing and working**: `schtasks /query` shows the task registered, Enabled, Daily,
  06:00; a forced `schtasks /run` completed with **Last Result: 0** (success) — not run against a
  locked account, nothing removed. Analysis script `src/investigations/posting_delay_analysis.py`
  added (not yet actionable — only 1 snapshot day exists): reports the days-to-stabilize
  distribution (median/p90/p95/p99/max) once ≥30 snapshot days exist, and its own docstring states
  plainly that **the leakage guard's 30-day margin (`config.yaml` `leakage_guard.min_margin_days`,
  `src/leakage_guard.py` — untouched by this or any part of this task) must not change until ≥60
  days of snapshots exist and this script's p99 is known from that data.**
- **Full test suite: 76 passed** (74 + 2 new `test_phaseE1_common_unit_cost.py` tests). Sensitive-
  content scan (customer/company names, credentials) of every new/changed file: zero matches.

**Phase I — Decision-sensitivity sweep on Phase E's Tier A assumptions — DONE (2026-09-23), single
agent (per `AGENTS.md`: sweeping/classifying/reporting on one shared computation share the same
context and cannot be usefully split; a separate Validator ran independently for Part 4 only).**
**[UNCALIBRATED — Phase J2, 2026-09-23: every stock_value/Min/Max/fill_rate figure below failed
calibration against actual delivery performance (Phase J). The sensitivity classifications
(relevant/insensitive) themselves are separate from the absolute figures and are not necessarily
invalidated, but no absolute number here may be used for a decision. See banner at top of file.]**
Measured which of Phase E's unconfirmed assumptions (procurement lead time, assembly time, review
interval, service level, sellable warehouses, unit-cost window, segment thresholds, placeholder
concentration threshold) actually change a Min/Max/stock_value/fill_rate decision, for PEM101,
PEM103 and PEM107, per a new formal metric, `METRICS.md` Sec.17 `decision_sensitivity` (added this
phase, Part 0 of the task). **One database connection attempt for the whole task** (per
DATABASE ACCESS RULE), pulling the combined 351-item scope (0 overlaps) from `cube_Sale_APD` and
`Cube_Inventory_Exact` in one connection (`src/investigations/phaseI_single_pull.py`), cached to
`output/data/phaseI_raw_sales_351items.csv` / `phaseI_inventory_exact_351items.csv` — every sweep
value afterward (dozens of scenarios × 3 divisions) was recomputed purely from that cache, no
further DB access.
- **Engine** (`src/investigations/phaseI_sensitivity_engine.py`) reuses the existing pipeline's
  already-locked functions unmodified (`compute_ltd_and_distribution`, `compute_max_and_stock_value`,
  `simulate_item_daily`, `topdown_item_forecast`), adding only parameterized policy-assignment and
  unit-cost functions (needed to sweep the frequency/window thresholds without a second live
  query). **Verified against the already-frozen/live pipeline outputs before any sweep ran**:
  policy counts matched exactly for all three divisions; PEM101 fill_rate/cycle_service_level
  matched to 10+ decimal places; stock_value matched within 0.01–0.02% (a fresh pull's slightly
  later most-recent-transaction anchor for a few fallback unit costs, not a methodology gap).
- **Part 1/2 classification** (`output/summary/phaseI_2_classification.csv`, full detail in
  `phaseI_1_scenario_results.csv` / `phaseI_1_item_detail_<division>.csv`): **RELEVANT in every
  division at the 10% default threshold** — procurement lead time, review interval, cycle service
  level, segment frequency threshold (the last via real policy flips: 9/6/2 items in
  PEM101/PEM103/PEM107, and a 101% stock_value swing in PEM103 specifically, whose zero-P50 rule
  makes classification depend on frequency alone). Assembly time is RELEVANT in PEM101/PEM103 but
  INSENSITIVE for PEM107 at 10% (division-dependent). **INSENSITIVE everywhere**: sellable
  warehouses (verified by direct recomputation, not just reasoned — Min/Max/stock_value/simulation
  formulas never read on-hand stock at all under current METRICS.md formulas: all three tested
  warehouse-set variants gave identical results to floating-point precision) and unit-cost window
  in PEM101 (RELEVANT only in PEM103/PEM107 at 10%, but never at 20%, and never moves Min/policy —
  a cost-only effect). Placeholder concentration threshold is report-only (placeholders carry no
  Min): PEM101 0/11 flip, **PEM103 all 37/37 flip together between 30% and 40%** (its no-history
  items cluster at exactly 30.71% top-sibling share), PEM107 1/24 flips.
- **Service-level curve and knee** (`output/summary/phaseI_2_service_level_curve.csv`): PEM101/
  PEM107 knee at SL=0.90 (marginal stock_value per fill-rate-point more than doubles beyond it);
  PEM103's knee is at 0.98 — its fill_rate is still only 90.6% at the SL=0.95 default, a genuine
  finding that cycle-service-level and unit fill-rate diverge far more sharply for PEM103's lumpier
  demand than for PEM101/PEM107.
- **Part 3 two-way grid** (`output/summary/phaseI_3_two_way_grid.csv`): top-2-by-value-shift pairs
  per division (PEM101: lead×review; PEM103: freq-threshold×service-level; PEM107: service-level×
  lead) are **dominantly roughly additive** (13/15, 11/15, 19/25 cells) — amplification/dampening
  appears only right at a classification boundary (PEM103's zero-P50 rule switching on/off; PEM107
  around lead=45–90 at SL=0.90), not spread across the grid.
- **Part 4 Validator** (`output/summary/phaseI_4_validator_*.csv`, `src/investigations/phaseI_validator.py`):
  independent re-implementation of policy/unit-cost/LTD/Min/Max/stock_value (own code, reusing only
  pre-existing infrastructure that predates this task — `phaseE1_common`/`phaseE2_pilot_recompute`
  — never the Analyst's new Phase I scripts), from the same single cached pull. **19/19 checked
  scenarios matched to floating-point precision** (default row + the extreme end of every RELEVANT
  assumption, all three divisions, division totals, and the three focus items' Min/policy). One
  real bug was caught and fixed during Validator development (first draft skipped PEM101's
  excluded/placeholder overrides, producing a 1.3–1.4% discrepancy on two scenarios) — fixed, then
  re-verified to exact match; recorded per CONVENTIONS.md as an independent recomputation, not a
  re-read of the same query.
- **Full test suite: 76 passed** (unchanged from the prior baseline — this phase added only new
  `src/investigations/phaseI_*.py` scripts, touching no existing pipeline module).
- **Assumptions that genuinely need a human answer** (full reasoning and per-division flip
  brackets in `output/summary/phaseI_report.md`): cycle service level (never set — STATUS.md
  Sec.8.5), procurement lead time (business confirmed only a 45–60 day *range*, and that range
  itself spans a relevant swing), review interval (pure Modeler default), segment frequency
  threshold (Modeler default, causes real policy flips everywhere), assembly time
  (division-dependent). Sellable warehouses, unit-cost window and the placeholder concentration
  threshold can remain assumptions — verified decision-insensitive for the Min/Max/stock_value/
  fill_rate decisions this project computes.

**Phase J — Calibrate the scenario model against reality, and adopt robust defaults — DONE
(2026-09-23), single agent (per `AGENTS.md`: calibration/curve/frontier/default-change all share
one computation and cannot be usefully split), with a separate Validator for Part 5.** Built
`METRICS.md` Sec.18 (`baseline_replay`, `actual_on_time`, `calibration_gap`) and used it to check
whether Phase I's scenario figures can be trusted before being treated as an action plan.
- **One new database connection attempt** (Cube_CES, `src/investigations/phaseJ_single_pull.py`)
  — everything else reused Phase I's cached raw pull. **Process error, disclosed not hidden:**
  Part 6's page regeneration initially made an UNINTENDED second live query (a call site inside
  `build_inventory_page_data.build_data()` — `phaseE2_pilot_recompute.pull_raw_sales` — not
  covered by the first monkeypatch draft). Caught immediately; read-only, no data modified; both
  call sites are now patched (`src/investigations/phaseJ_regenerate_page.py`) and the page was
  rebuilt cleanly on the corrected run. Recorded here as a genuine rule violation, not minimised.
- **Part 1 calibration — the model is DRAMATICALLY PESSIMISTIC in every division, the OPPOSITE
  direction this task's own Purpose section anticipated** (stated plainly per CONVENTIONS.md's
  contradiction-reporting rule): baseline_fill_rate 8.2%/1.1%/1.6% (PEM101/103/107) vs.
  actual_on_time 97.8%/94.1%/86.1% — calibration_gap -89.6/-93.0/-84.5 percentage points.
  **Root causes, verified**: PEM103 and PEM107 have ZERO items with any current Min/Max setting
  in their sellable warehouses (100% reactive under Sec.18's definition); PEM101's settings are
  the ALREADY-KNOWN-unreliable ones (Locked Decisions: 46/128 no setting, up to 1,700 months of
  cover) -- several of its highest-demand items hold a Min/Max a 30-day review cycle exhausts in
  10-15 days, guaranteeing 15-20 stockout days between reviews. **Hypothesis, not verified**: real
  replenishment almost certainly does not follow a rigid 30-day review the way Section 16
  mechanically assumes -- no historical stock-movement/reorder-event log exists to confirm this
  directly (same absence Phase D/E1 already documented).
- **Part 2 — same money would NOT buy better delivery, in any division, by any margin.** Even
  extending the search to SL=0.01 (near-zero safety stock, Min=LTD only), the model's stock_value
  (THB 44.9M/31.5M/16.0M) still exceeds each division's current on-hand (THB 18.07M/6.06M/3.28M)
  by 2.4-5.2x -- **no service level in the model's valid range matches today's capital level**; the
  model's structural minimum already costs more than the business holds today. RAW model fill_rate
  at this floor (91%/44%/32%) is already below actual_on_time in every division -- the direct
  answer is no even before any correction. **The instructed calibration correction produces
  figures above 100% in every division and is reported as NOT MEANINGFUL here, not silently
  applied** -- the calibration_gap does not transfer additively from today's broken-settings
  regime to a near-zero-safety-stock scenario; this divergence is itself informative.
- **Part 3 — frequency-threshold Pareto frontier**: PEM101's current threshold (6) is DOMINATED
  (frontier = {11,12} only -- a higher threshold gives lower stock_value AND marginally higher
  fill_rate); PEM103/PEM107's current threshold (6) IS on the frontier (every value 2-12 is a
  genuine trade-off there). No threshold recommended, per task instruction -- frontier reported,
  decision left to the business, especially since PEM101's fill-rate cost of its current
  (dominated) choice is under 0.01pp, arguably too small to act on without a firmer stockout-cost
  basis (still absent, STATUS.md Sec.8.5).
- **Part 4 — robust defaults adopted in `config.yaml`**: `procurement_lead_time_days` unchanged
  at 60 (already the confirmed range's upper bound; comment corrected from a prior mislabel of
  "middle"); `assembly_time_days` changed 3 -> 7 (upper end of the Modeler's own plausible [3,7]
  range), both commented with the under-provisioning-costs-more reasoning and Phase I's
  decision-relevance finding. New default-scenario headline: PEM101 stock_value THB 67.41M (+3.6%),
  fill_rate 99.62%; PEM103 THB 82.44M (+2.5%), 91.14%; PEM107 THB 51.08M (+1.7%), 98.06%.
  **Material, foreseen, disclosed consequence: PEM101's entire former 36-item
  `component_stock_ato` population now falls into `UNDEFINED_BY_METRICS_MD_SEC15`** (assembly=7 >
  PEM101's median customer notice of 6 days trips METRICS.md Sec.15's own documented structural
  gap) -- these items get no Min/Max, no stock_value, and do not appear on the inventory page,
  same treatment as placeholder/excluded. Not a new bug (the code already refuses to invent a 5th
  category, logs a warning) -- but a real operational gap this default change opens for PEM101
  specifically. PEM103 (median notice 30d) and PEM107 (16d) are unaffected.
  **[REVERTED — Phase J2, 2026-09-23, Part 0: `assembly_time_days` set back to 3.** Making
  `component_stock_ato` infeasible for all 36 of PEM101's affected items was too costly a side
  effect to accept for an assumption this uncertain, especially once Phase J itself showed the
  whole model fails calibration against actual delivery performance (this same Phase J entry,
  above) -- assembly time may not even be the binding constraint on real fulfilment at all (see
  Phase J2's Explorer findings). The robust-upper-bound change is DEFERRED, project-wide, until
  the real fulfilment mechanism is known, not abandoned -- it can be revisited once Phase J2's
  open question (what actually governs delivery timing) is answered. `procurement_lead_time_days`
  is NOT reverted (still 60, was already the range's upper bound regardless). Headline figures
  above (67.41M etc.) are therefore themselves now superseded by the reverted figures: PEM101
  THB 65.10M / 99.70%, PEM103 THB 80.45M / 90.58%, PEM107 THB 50.20M / 97.74% (identical to
  Phase I's own default-scenario figures, since assembly_time_days=3 is unchanged from Phase I) --
  still UNCALIBRATED regardless, per the banner at the top of this file.]**
- **Part 5 Validator**: independent implementation (own control flow for the baseline replay;
  reused only Phase I's own already-cross-validated `phaseI_validator.py` functions for Min/Max/
  stock_value, never Phase J's Modeler scripts) -- **every figure matched to floating-point
  precision**: baseline_fill_rate, actual_on_time, the SL-at-current-onhand crossing (all three
  divisions independently confirmed "<0.01"), and the new default-scenario stock_value.
- **Inventory page regenerated** (`forecast/inventory.html`, under the new default) and
  **`tests/test_inventory_parity.py`: 6/6 pass**. **Full test suite: 76 passed** (unchanged count).
- **Bottom line**: the scenario model does not simply need minor calibration -- Phase J found (1)
  today's actual settings/review cadence are themselves so broken that replaying them looks far
  worse than reality (a data problem, not a scenario-model problem), and (2) separately, the
  model's own recommended stock levels are structurally far above what the business holds today at
  every tested service level, meaning adopting this model at any service level is a capital
  increase, not a reallocation of today's money. Both findings should reach the business before any
  scenario figure (Phase I's or Phase J's) is treated as an action plan. Full detail:
  `output/summary/phaseJ_report.md`.

**Phase J2 — Why the model fails calibration: four parallel Explorers + a Synthesizer — DONE
(2026-09-23).** Phase J found the model dramatically pessimistic (calibration_gap -84 to -93pp);
this phase tests four specific hypotheses for why, corrects the long-cited 73.2% benchmark, and
retracts Phase J Part 4's default change. Per `AGENTS.md`: the four hypotheses are independent of
each other's results and need the same capability (database search) over disjoint questions —
matching the Phase D precedent (three parallel Explorers) — so four parallel Explorers were used,
each with its own single database-connection attempt, then a Synthesizer (the Orchestrator) merged
their findings without gathering new data.
- **Part 0 corrections**:
  - Every `stock_value`/`Min`/`Max`/`fill_rate` figure from Phases E0, E1, E1-fix, E1-fix-2, E2 and
    Phase I is now marked **UNCALIBRATED** throughout this document (a banner at the top of this
    file plus a tag on each phase's own entry) — not deleted, per instruction.
  - `METRICS.md` Sec.19 (`delivery_timeliness`) added: `on_time_exact` / `not_late` / `late`, always
    both row- and unit-weighted. **The project's long-cited 73.2% figure was `on_time_exact`,
    row-weighted, 2026-only** — it excludes early deliveries and must never be compared against
    `fill_rate`. **Corrected `not_late`, 2023-2026** (`output/summary/phaseJ2_0_not_late_overall.csv`,
    `_byyear.csv`, due date = `ForecastDelDate`, year = `CtrDate` year, matching
    `delivery_performance.py`'s own precedent): **PEM101 90.2%, PEM103 84.7%, PEM107 86.3%**
    (row-weighted); **87.9%/88.6%/88.7%** (unit-weighted, `ActualQty`). 7 comparison-usages of
    73.2% in this document are individually tagged SUPERSEDED, pointing here.
  - `assembly_time_days` **REVERTED 3→7→3** (Phase J Part 4's change is retracted): 7 days made
    `component_stock_ato` infeasible for all 36 of PEM101's affected items under METRICS.md
    Sec.15, and Phase J's own calibration failure means assembly time may not even be the binding
    constraint — compounding an uncalibrated model with a further speculative change was not
    justified. The robust-upper-bound change is **deferred, not abandoned**, until Phase J2's open
    question (the real fulfilment mechanism) is answered. `METRICS.md` Sec.15 gained an addendum:
    this state is now named `component_stock_ato_infeasible` explicitly (code updated to match,
    `phaseE1fix_recompute.py`/`phaseI_sensitivity_engine.py`) rather than left undefined. Pipeline
    outputs and `forecast/inventory.html` regenerated to match (no new DB access — reused Phase
    I's cache); 76/76 + 6/6 parity tests pass.
- **Part 1 — four parallel Explorers, each own DB connection attempt** (per the task's own DB rule:
  each agent attempts once, no retries, a failure in one does not authorise retries in another):
  - **Explorer A (real notice via quotation) — CONTRADICTS, moderate-high confidence.**
    Data-driven join-key discovery found `Cube_Quotation.quotation` (not `id`) is the real key, and
    corrected a prior investigation's date-column choice (`report_date` tracks a disposition date,
    99.94% identical to `forecast_date` — NOT a quotation-issue date; `create_date` is). Even in
    2025-2026 (the only years with usable `Cube_Quotation` coverage — 2024 is essentially empty,
    CANNOT BE DETERMINED why), only ~25-29% of orders carry any quotation trace, and matched
    quotations precede the PO by a median of just 3 days (confirmed independently from both
    directions). `output/summary/phaseJ2_explorerA_report.md`.
  - **Explorer B (due dates aligned to delivery) — UNDETERMINED, corrected 2026-09-23 (was:
    CONTRADICTS, moderate-high confidence — kept below, superseded, not deleted).** The day-0
    delivery spike is real and anomalous (3.8-37.6x what the surrounding spread predicts —
    genuinely not just "naturally fast deliveries") and is NOT specific to `ForecastDelDate`:
    `PlanDelDate` shows an equal-or-larger zero-day share (64.6% vs 62.5%), and in the 4.2% of
    rows where the two fields diverge, `PlanDelDate` ends up closer to `ActualDelDate` far more
    often (62.6% vs 11.1%). **Correction: this pattern does not actually distinguish the
    hypothesis from the alternative.** A spike of deliveries exactly on the due date, appearing
    equally on `ForecastDelDate` and `PlanDelDate`, is consistent BOTH with due dates being set to
    match delivery AND with the business simply scheduling shipment on the promised day — normal
    practice, not an artifact. The data available cannot separate these two explanations; the
    original CONTRADICTS verdict overstated what the evidence rules out. **What actually causes
    the real day-0 spike remains an open question, not resolved by any Explorer, now under either
    reading.** `output/summary/phaseJ2_explorerB_report.md`.
    ~~Explorer B (due dates aligned to delivery) — CONTRADICTS, moderate-high confidence.~~
  - **Explorer C (component stock/fast assembly) — CONTRADICTS as a general explanation,
    moderate-high confidence.** Decisive reverse-direction test: on-hand stock strongly,
    monotonically correlates with FASTER delivery (order-level 30.5% fast at zero stock vs 85.6%
    at substantial stock) — the opposite of the hypothesis. **Recorded explicitly (2026-09-23): at
    the same moderate-high confidence level Explorer C itself established, this finding — items
    holding stock deliver fast 85.6% of the time against 30.5% without — supports stock as the
    driver of timely delivery**, not merely "contradicts Hypothesis C." Both framings describe the
    same evidence; stated as a positive finding here so it is not read only as a negative result
    for the hypothesis it was testing. A narrow, real pocket (16 items, 0.31% of order volume,
    concentrated in Medium Voltage Surge Arrester and fuse types) does fit the hypothesis and is
    worth its own follow-up. `output/summary/phaseJ2_explorerC_report.md`.
  - **Explorer D (production batching ahead of orders) — PARTIALLY SUPPORTS, low-moderate
    confidence (data gap).** Within this 351-item scope, only 13.8% of job/batch tokens serve more
    than one contract (narrower than the project-wide prior finding) with a real median 32-day
    time spread where they do; by a proxy measure (since the true batch-date field,
    `cube_final.final_date`, returned **zero rows** — the query is verified correct and the table
    is verified to hold matching item codes from a prior investigation, so this is almost certainly
    an artifact of the subagent being killed mid-task by an unrelated rate-limit error, not a real
    absence of data), ~14.5% of delivered contracts trace to a batch token that already existed via
    an earlier contract. **The decisive test could not be completed this session and needs a fresh
    connection attempt in a follow-up task** — this agent's own connection had already succeeded,
    so no retry was available under this task's DB rule. `output/summary/phaseJ2_explorerD_report.md`
    (completed by the Orchestrator from the crashed agent's already-cached pulls, no new DB access).
- **Part 2 Synthesis** (`output/summary/phaseJ2_synthesis_report.md`): **no single hypothesis, nor
  all four combined, is large enough to explain an 84-93 percentage-point calibration gap.** Best-
  evidenced pattern across all four reports: real delivery is fast (PEM101 median 5 days) and
  correlates with SOME stock existing, turning over far faster than the model's 30-day review
  would predict — but no Explorer tested "faster real review cadence" as its own hypothesis.
  PEM103 stands out unexplained: 84.7% not_late but only 17.8% on_time_exact, the slowest median
  delivery (24 days), and zero items with any current Min/Max setting — structurally different
  from PEM101/PEM107 in a way this task's four hypotheses do not specifically explain. **Section 16
  would need**: a much shorter review cadence (event-triggered, not calendar-triggered), a broader/
  different definition of usable stock than the assumption-labelled "sellable" warehouses (plus
  possibly a distinct batch-production supply channel), and a realistic lead time far shorter than
  60+3+30=93 days for the bulk of order volume (worded change proposed only, not implemented, per
  task instruction). ~~**Calibration is NOT achievable from data alone.**~~ **CORRECTED 2026-09-23,
  kept not deleted: this was premature.** Phase J's calibration replayed the CURRENT min/max
  settings, already established as unfollowed (existing settings are known-unusable — Locked
  Decisions), so it tested an unused policy, not whether Section 16's own mechanics could be fitted
  to reality. `METRICS.md` §20 (inverse calibration) proposes exactly that fit, scheduled as J3;
  see this Phase J2 entry's own annotation and `DATA_MAP.md` §5 item 15 / §6. The specific business
  input Phase J2 named is not withdrawn — it may still be needed if J3 cannot identify Section 16's
  parameters from data — but it is no longer the ONLY route, until J3 reports back. The specific
  missing input, as originally named: a direct description from production/warehouse planning of
  (1) real review frequency/trigger, (2) which physical stock (including non-"sellable" warehouses
  and component buffers) is actually treated as available, and (3) how/whether production runs
  ahead of orders
  for the fuse/surge-arrester families that dominate fast delivery. One narrower piece remains
  achievable from data alone without business input: a successful, uninterrupted `cube_final`
  re-pull to complete Explorer D's core test.
- **Full test suite: 76 passed** (unchanged) plus **6/6** `test_inventory_parity.py`. Sensitive-
  content scan of every new/changed file: zero matches (see commit).

**Phase J3 — Inverse calibration (METRICS.md Sec.20), target node Q10 — DONE (2026-09-23).**
Three parallel agents (Validator, Explorer D, Explorer BOM — independent, per `AGENTS.md`: same
capability, disjoint questions), then a single Modeler (grid search needs all inputs together in
one view, per the decomposition test), then a separate Validator for the independent check.
- **Part 1 Validator — reconciled the 97.8%-vs-87.9% PEM101 discrepancy.** Not a bug either side:
  item scope, status filter and weighting are identical; the only real difference is the window
  (Phase J bounded by `ForecastDelDate` 2024-01/2026-07; Phase J2 bucketed by `CtrDate` calendar
  YEAR 2023-2026, pulling in a genuinely much worse 2023 — 55.97% unit-weighted `not_late` vs.
  ~97-99% in 2024-2026). Quantified: -10.29pp from including 2023, +0.35pp from the bucketing
  method, net -9.93pp, matching the observed gap almost exactly. **Reconciled calibration/
  validation targets** (`ForecastDelDate`-windowed, unit-weighted, `output/summary/
  phaseJ3_validator_reconciliation.md`): calibration (2024-01 to 2025-12) `not_late` PEM101 97.70%,
  PEM103 90.89%, PEM107 86.61%; validation (2026-01 onward) PEM101 98.28%, PEM103 96.56%, **PEM107
  76.54% — a real degradation, not noise**. Current on-hand stock value (single snapshot, flagged
  as an assumption that stock was broadly stable across the period): PEM101 THB 18.25M, PEM103
  THB 6.06M, PEM107 THB 3.40M.
- **Part 1 Explorer D — completed the lost Phase J2 test, with an important correction.** A fresh,
  clean, uninterrupted `cube_final` connection (full 35-column schema, no crash) **still returned
  zero rows** for the 351-item scope — this CONTRADICTS Phase J2's "almost certainly a
  process-kill artifact" theory; a follow-up diagnostic query was blocked by this task's own
  one-connection-per-agent rule, so it is genuinely CANNOT BE DETERMINED whether the table is now
  empty table-wide or just for this scope. What WAS computed (from the `Cube_CES` `OLMJobCode`
  proxy, independently recomputed, matching Phase J2's pooled figures almost exactly): the pooled
  13.8%/14.5% reverse-traceable-batch-share figures hide a large division split — **PEM101 only
  2.0%, PEM103 69.3%, PEM107 58.9%** — and per-item-typical cadence (PEM101 56d, PEM103 36d, PEM107
  58d median, all with wide spreads). No lead-time value could be derived at all (the decisive
  `cube_final` field never returned data either session).
- **Part 1 Explorer BOM — `Cube_BOM_Exact` investigated for the first time.** Structure/grain
  confirmed (one row per finished-item/component pair); **85.8% coverage of the 351-item scope
  (PEM103 only 58.6%)**; components confirmed **shared across finished items** (141 of 805, 17.5%,
  concentrated in fuse/surge-arrester families) — answers Q18. Join to `Cube_Inventory_Exact`
  confirmed both directions (V2, 95.0% match). Of Phase J2's 16 zero-finished-stock-fast-delivery
  items, 14 have at least one stocked component — **PLAUSIBLE, not VERIFIED**, support for a
  component-stock explanation of that narrow pocket; does not overturn Explorer C's project-wide
  verdict.
- **Part 2 Modeler — METRICS.md Sec.20 grid search, per division** (review interval extended
  beyond the originally-suggested 30-day cap to span Explorer D's actual observed cadence, up to
  130 days; lead time bounded by Cube_PO_Exact/business-confirmed figures since Explorer D's
  batch-date route failed again; r/s_months extended twice after the first two grids kept
  clipping their own edge — disclosed, not silently widened):
  - **PEM101: PARTIALLY CALIBRATED.** 59/4,130 combinations fit both periods within tolerance
    (`not_late` ±3pp, stock value ±15%) at a realistic capital level. No parameter uniquely
    identified: r = 0.25-2.0 months of mean demand, S = 1.5-3.0 months, review interval = 1-30
    days, lead time = 1-30 days, all span more than one grid step. Best fit: r=0.5mo, S=2.5mo,
    review=1d, lead=3d (calib `not_late` 98.9% vs. target 97.7%; valid 98.3% vs. 98.3%; calib
    stock value THB 18.42M vs. THB 18.25M target).
  - **PEM103: NOT CALIBRATABLE at a realistic stock level.** `not_late` alone is matchable (117
    combinations) but every one needs 5-12x more capital than the business holds (best: THB 57.6M
    simulated vs. THB 6.06M real on-hand, +850%).
  - **PEM107: NOT CALIBRATABLE at all.** No parameter set fits both periods simultaneously — the
    closest joint compromise is still 14-18 percentage points off on one side (a policy generous
    enough for the 86.6% calibration target overshoots the 76.5% validation target by ~15-20pp,
    and vice versa).
- **Part 3 independent Validator — 12/12 figures (4 per division x 3 divisions) MATCH**, own code
  written from METRICS.md Sec.16/20's literal text, never reading the Modeler's scripts
  (`output/summary/phaseJ3_validator2_independent_check.md`). The one nonzero gap (PEM103 stock
  value, ~0.06-0.09%) is well inside the 1% tolerance and traced to a handful of extremely
  high-value, low-volume transformer items, not a methodology disagreement.
- **Part 4 Gate:**
  - PEM101: **calibrated with wide uncertainty bands** — may be used for scenarios only with those
    bands stated, not as a single confident policy.
  - PEM103: **not calibratable from data** at a realistic stock level. Single narrowest question:
    **does PEM103 fulfil orders primarily through production-batch timing rather than
    finished-goods buffer stock, and if so, what governs when a batch is run and how large it
    is?** (Ties directly to Q17, still blocked on a working `cube_final` connection.)
  - PEM107: **not calibratable from data.** Single narrowest question: **what changed
    operationally for PEM107 between 2024-2025 and 2026 — capacity, a supplier, a customer-mix
    shift — that dropped delivery performance from ~87% to ~77%?**
  - Fallback evidence (PEM103/PEM107, project-wide/pooled, not per-division): Explorer C's
    (Phase J2) already-verified stock-tier-vs-delivery-speed relationship — zero on-hand stock:
    30.5% delivered within 14 days (median 25 days); some stock: 66.0% within 14 days (median 8
    days); substantial stock: 85.6% within 14 days (median 5 days). Monotonic, real, but pooled
    across items, not a per-division calibration.
- **Full test suite: 76 passed** (unchanged — this task added only new `phaseJ3_*.py` scripts).
- Node statuses updated in `PROJECT_GRAPH.md`: **Q10** in progress (answered per-division, two of
  three narrowed to one named business question each); **Q17** in progress (cadence known, batch
  dates/sizes still blocked on `cube_final`); **Q18** done.

**Phase J4 — PEM103/PEM104 business facts, G2/G3 scope split, channel-scope decision — DONE
(2026-09-23).** Documentation only: no database access, no analysis, no code/config changes.

- **PEM103 is transformers, and most of its business is tendering work for electricity
  utilities** (business-confirmed). Consistent with data already in the repository: Phase C found
  the Omni Channel filter captures only 33.3% of PEM103's item-code value, with 65.5% Tendering
  (STATUS.md:3894-3895); Phase J3 found 69.3% of PEM103's delivered contracts trace to a
  pre-existing production batch (vs. PEM101's 2.0%, STATUS.md:1328); and Phase J3's inverse
  calibration found a stock-based policy cannot reproduce PEM103's delivery without 5-12x more
  capital than the business holds (STATUS.md:1351). Recorded at level A: DATA_MAP.md §7.
- **PEM104 is made to order** (business-confirmed). Consistent with only 12 transactions across 17
  calendar months (Phase C step 1, STATUS.md:4819) and essentially no stock anywhere (Phase E2
  readiness, STATUS.md:780-781). This changes PEM104's exclusion reason from "insufficient data"
  (STATUS.md:4817-4824) to "made to order, no stock policy applicable" — the old reason is
  superseded, not deleted, in DATA_MAP.md §6 Corrections log.
- **PROJECT_GRAPH.md updated**: G2 (stock policy) now scoped to PEM101/PEM107 only. PEM103 moved
  out of G2, feeding G3 instead through a new node, Q22 (tender-pipeline governs PEM103's
  production/stock behaviour — answered). PEM104 closed as a dead end, DE4 (made to order, no
  stock policy). The external-factors node (utility budgets, EGP bid announcements — STATUS.md
  §6, Phase 3.2 missing-data note) is raised from deferred to **relevant for PEM103, blocked on
  data**, since the tender pipeline is now PEM103's understood primary production driver. A new
  question node, Q23, is proposed (in progress, next task): does the Omni Channel scope explain
  observed stock/delivery behaviour, or does production/stock shared with Tendering need to be
  included? It feeds PEM103's G3 path (Q22) and PEM107's still-unexplained 2026 delivery decline
  (Q10).
- **Decision: the official requirement remains Omni Channel, and stays the project default.** A
  combined Omni Channel + Tendering scope (`channel_scope = omni_tendering`, METRICS.md §21) will
  be built as a **contingency** and compared against the default — this does not change the
  default, and nothing is re-scoped until Q23 is actually run and a decision is made from its
  result.
- **METRICS.md §21 (channel_scope and cross-scope comparison) added**, defining `omni` (default)
  and `omni_tendering` (contingency) scopes, the same-target comparison rule (omni_tendering's
  forecast allocated to Omni by historical share, point-in-time, before scoring against actual Omni
  demand), and the rule that MASE/relative_bias per scope describe predictability, never a
  cross-scope accuracy claim.
- No database access, no code changes. Full test suite unaffected (no code touched).

**Phase Q23 — channel_scope comparison (METRICS.md Sec.21), target node Q23 — DONE (2026-09-24).**
Four agents: a single Explorer (Part 1, one DB connection, channel-mix crosstab + Cube_CES pull),
a single Modeler (Parts 2-3, same capability, needs both inputs in one view per the decomposition
test), a single Analyst in parallel with the Modeler (Part 4, different capability, independent of
the Modeler's results), then a separate from-scratch Validator (Part 6, own DB connection, no
Modeler/Analyst/Explorer file read).

- **Part 1 — channel mix, PEM101 (171 codes)/PEM103 (87)/PEM107 (136), 2024-2026** (2023: zero
  usable rows for this scope, confirmed independently twice — consistent with the known pre-2024
  tagging-scheme change, `DATA_MAP.md` §1). No revenue type besides Omni Channel/Tendering exceeds
  2% of any division-year's value (`Total Customer Solution` stays under 0.09%). **PEM101's full
  171-code scope is LESS Omni-dominated than the 128-item Fuse/Surge-Arrester pilot** (78.77% vs.
  87.68% Omni value share, an 8.9pp gap) — the pilot's high Omni purity does not generalise to the
  whole division. **PEM103 and PEM107 both show a sharp year-over-year channel-mix REVERSAL, not a
  stable split**: PEM103 was Tendering-dominated in 2025 (88.5% of value) but Omni-dominated in the
  partial 2026 (96.6%); PEM107 was Omni-dominated in 2025 (71.6%) but Tendering-dominated in 2026
  (72.3-72.4%). **V2** for both reversals — independently recomputed twice from two separate fresh
  DB pulls (Explorer and Validator), exact agreement to 2 decimal places.
- **Part 2 — same-target accuracy comparison**: Method A (top-down on Omni-only) vs. Method B
  (top-down on Omni+Tendering, allocated back to Omni by each item's point-in-time historical Omni
  share of its own combined demand, with a disclosed fallback for zero-history items). **B is never
  more accurate than A for forecasting Omni demand, and is measurably, statistically distinguishably
  WORSE for PEM107** (division-wide, paired t=2.43 Modeler / t=2.43 Validator) **and for the single
  dominant focus item EEE-F-FC-1040010002** (t=2.61, Modeler only — not separately re-tested by the
  Validator, which checked divisions not individual focus items). PEM101 and PEM103 (division-wide)
  show no statistically distinguishable difference (PEM103 borderline, t=1.88-1.98, just under the
  |t|>2 threshold in both independent runs). **Independently reproduced**: Modeler and Validator's
  MAE figures agree within 3% and reach the identical significance verdict in every division —
  **V2** for the overall verdict (same direction, same significance conclusion, two independent
  implementations); **V1** for the exact MAE values (small, disclosed differences from each
  agent's own choice of zero-history fallback rule, never specified by METRICS.md §21 itself).
  Separately (never mixed into the accuracy claim, per §21's own warning): the omni_tendering
  series is far less predictable on its own terms (MASE 3-58x worse than the omni series across
  divisions) — a predictability description, not an accuracy comparison.
- **Part 3 — combined-demand calibration re-run (METRICS.md Sec.20), PEM103/PEM107 only, same
  grid/tolerance/targets as Phase J3**: **neither division calibrates.** PEM103: 0/4,130 combinations
  pass both-window tolerance (unchanged from J3); relaxing to `not_late` alone, the best fit needs
  **27-37x more capital than the real THB 6.06M target** (Modeler: 27.5-37.0x, cost-basis-invariant;
  Validator: 33.5x calib/27.4x valid) — **WORSE than J3's Omni-only 5-12x gap**, not better. Per
  this task's own conditional instruction, since PEM103 does not calibrate under either scope, no
  shared-stock finding is stated — this **reinforces**, rather than overturns, Q22's tender-pipeline
  finding. PEM107: 0/4,130 pass even `not_late` alone (worse than PEM103), unchanged from J3 — its
  2024-2025-to-2026 operational change is not a demand-scope artifact either. **V2** for "neither
  division calibrates, and the PEM103 gap widens under combined demand" (Modeler and Validator,
  independent grid searches, same 4,130-point count, same qualitative and order-of-magnitude
  result); **V1** for the exact best-fit capital multiple (differs by choice of tie-break among
  passing grid points, disclosed by both agents).
- **Part 4 — PEM107's 2026 not_late decline (86.6%→76.5%) vs. channel mix**: recomputed
  independently of Part 1 (Analyst), confirms the same reversal (Tendering value share 35.0%→72.3%,
  2024-2025→2026). Critically, **Omni's OWN `not_late` also fell substantially, 88.6%→76.5%
  (-12.1pp)** — not merely a compositional artifact of more orders shifting into a channel with a
  different baseline rate. **Verdict: SUPPORTED HYPOTHESIS, not proven (level H)** — the timing
  coincidence (large Tendering-volume months concentrated in 2026: Jan 5,398 units, May 18,620, Jul
  4,610, Aug 7,027 units) and both channels degrading together in the same year both point toward
  shared capacity/stock being diverted to Tendering, but an independent 2026 capacity constraint
  affecting both channels with no actual resource competition cannot be ruled out from this data
  alone. Tendering's own `not_late` figures (99.3%→48.3%) carry a data-quality caveat — see Trap
  below — and are reported as directional only.
- **Trap found and worked around, not fixed at the source**: the Explorer's fresh `Cube_CES` pull
  added a `CtrDate >= '2023-01-01'` filter that is NOT equivalent to this project's established
  `ForecastDelDate`-windowed `not_late` method (METRICS.md Sec.18/19/20) — it silently cut PEM107's
  row count (8,524→5,686) and produced an unrecognizable blended `not_late` (94.8%→52.8%) versus
  the already-established 86.6%/76.5% headline. The Analyst traced this and used the older,
  unfiltered `output/data/phaseJ_cube_ces_351items.csv` pull for the Omni-channel figures instead
  (reproduces the established target almost exactly). **`src/investigations/phaseQ23_explorer.py`
  itself was NOT corrected** — the bug remains live in that file for any future reader. See
  `DATA_MAP.md` §4 Trap 18.
- **Part 6 — independent Validator, from scratch, own DB connection, no Modeler/Analyst/Explorer
  file read**: reproduced the channel-mix figures exactly (Part 1) and reached the identical
  qualitative verdict on Parts 2 and 3, with small, explained numerical differences (disclosed
  fallback/tie-break choices, never a data or methodology disagreement). No discrepancy found that
  changes any conclusion above.
- **Decision (unaffected by this finding, per task instruction): Omni Channel remains the project's
  default and official scope.** The `omni_tendering` scope exists only as the contingency METRICS.md
  §21 always said it was — this task's own result argues against, not for, ever promoting it to the
  default: it does not forecast Omni demand more accurately, and it does not make either
  under-calibrating division's stock policy more explainable.
- **Config**: `channel_scope` added to `config.yaml` (`omni` default / `omni_tendering`
  contingency, cited to METRICS.md §21), read by `src/load_data_full.py` and
  `src/load_data_all_divisions.py` via a shared `src/channel_scope.py` helper. Default query text is
  byte-for-byte unchanged (a single-value `IN`-list is logically identical to the old equality
  filter). Two new tests added (`tests/test_channel_scope.py`, 8 cases: default-unchanged at both
  the config-function and generated-SQL level, `omni_tendering` selects both revenue types, unknown
  scope raises).
- **Node statuses updated in `PROJECT_GRAPH.md`**: **Q23 done — answered.** **Q22 changed from
  "done" to "answered (level A) — production mechanism pending EF1"**, since the business-confirmed
  tender-pipeline statement is level A (not itself derived from data) and how the pipeline governs
  batch timing against that pipeline is still unestablished, blocked on EF1. Also corrected a
  date typo on the G2 node row (read "corrected 2026-09-25" on a row committed 2026-09-23, a
  date-in-the-future-relative-to-its-own-commit error — corrected to 2026-09-23, matching the
  neighbouring "scope split 2026-09-23" text in the same cell).
- **Full test suite: 84 passed** (76 existing + 8 new `test_channel_scope.py` cases; unaffected by
  the Q23 investigation scripts themselves, which are one-off `src/investigations/` tools, not
  pipeline code under test).

**Phase 136 — does PEM103/PEM107's 2026 channel-mix reversal reflect a recording change or a
business change?, target node Q23 (through it, Q10's PEM107 branch and the G1 forecasts for
PEM103/PEM107) — DONE (2026-09-24).** Two parallel Explorers (order side, attribute side — per
this task's own instruction; the decomposition test is satisfied since the two angles need
different data/methods and neither depends on the other's result), then a Synthesizer, then a
separate independent Validator; plus a source-level bug fix (Part 3) done directly.

- **Part 3 (done first, unblocks clean data for the rest) — fixed the Cube_CES `CtrDate` filter bug
  at source (DATA_MAP.md Trap 18).** The prior Q23 task's Analyst had found and worked around, but
  not fixed, a stray `CtrDate >= '2023-01-01'` filter in `phaseQ23_explorer.py`'s Cube_CES pull.
  Added a shared helper, `src/cube_ces_pull.py`, that pulls Cube_CES for an item-code scope with NO
  date filter at the SQL level, ever (the already-working pattern `phaseJ_cube_ces_351items.csv`
  used); switched `phaseQ23_explorer.py` to use it; added a regression test
  (`tests/test_cube_ces_pull.py`, 2 cases) that fails against the old filter. No previously
  *recorded* figure changed, since the only figures ever published from that pull already used the
  pre-bug unfiltered file as a workaround — but both this task's Explorer 1 and the independent
  Validator re-pulled Cube_CES via the fixed helper for real, and neither found an anomaly.
- **Part 1, Explorer 1 (order side)** — one DB connection (Cube_CES, fixed helper). **Customers**:
  of customers active in both 2025 and 2026, 0/46 (PEM103) and 1/87 (PEM107, 2.13% of qty — noise)
  changed their dominant recorded channel; both divisions show large customer turnover instead
  (PEM103: 26 only-2025/42 only-2026; PEM107: 136 only-2025/88 only-2026). **Items**: PEM103 1/21
  items flipped dominant channel (63.95% of value — one transformer item behind both 2025 spikes);
  PEM107 19/82 flipped, bidirectionally (59.63% of value). **Timing**: no clean step-change date for
  either division — PEM103's 2025 Tendering share comes from two isolated giant months (Jan 97.9%,
  Jun 98.9%, each 1-2 large contracts); PEM107's Tendering-heavy months land in different calendar
  months in 2025 vs 2026. Every spike traces to 2-5 large, normally-sequenced contracts, never mass
  relabeling. **136-code overlap**: ZERO overlap found between any PEM103-named and PEM107-named
  pricelist sheet (visible or hidden), both directions — 136 is simply PEM107's own code count; the
  task's stated premise does not match the file as it exists, and this rules out a pricelist
  reference-data artifact as a third explanation.
- **Part 1, Explorer 2 (attribute side)** — one DB connection (`cube_Sale_APD`, fresh pull).
  Discovered a real, informative `customer_segment` field (Contractor/Dealer/Smart Shop/End User vs.
  Local Utility/Inside Group/PEA Regional Office). Order size directly contradicts a relabeling
  reading: PEM103's 2026 Omni orders (median THB 295K) match 2025's OWN Omni scale, not 2025's
  Tendering scale (THB 142.5M, ~483x larger) as a relabeling would require; PEM107's 2026 Tendering
  orders (median THB 7.5M) are ~12x LARGER than 2025's own Tendering, not smaller/Omni-like. Notice
  days and customer-segment mix stay consistent with the TAG, not the flip, in both years. Customer
  overlap between the swapped channels is ~0% (PEM103: 0/3, 0/2; PEM107: 0/7, one weak 1/7
  exception). Contract numbering is uniform (`CTR-YYYY-#####`) everywhere — uninformative.
- **Part 2, Synthesizer** — merged both Explorers, found no conflict between them (fully
  reconcilable: customer channel identity is stable, but which customers are active turns over
  substantially each year, so item-level dominance can flip without any single customer's channel
  ever changing). **Verdict: BOTH divisions show a BUSINESS change, not a recording change (V2 —
  two independent angles converge, not yet a from-scratch recomputation of one shared figure).**
  Recorded the business's stated view (level A, 2026-09-23: "most likely a recording-method
  change") alongside this direct contradiction — both positions stated, neither chosen (AGENTS.md
  rule 4/9); recommended the business be asked a specific, falsifiable follow-up question (was there
  a named system/process change, and on what date?). **No reconstruction/reassignment rule
  proposed** (not warranted by a business-change finding) — 0% of PEM103's 2026 Omni demand or
  PEM107's 2026 Tendering demand reassigned. **No G1/forward-test correction needed** on these
  grounds; a pre-existing, separate caution (PEM103/PEM107's demand is driven by a churning customer
  population placing lumpy, tender-adjacent orders) is reaffirmed, not newly created — recommended
  the 2026-09-30 scoring for these two divisions NOT be labelled provisional on the grounds
  investigated here. **PEM107 diversion hypothesis (prior Q23 task): SURVIVES, strengthened on its
  "is the surge real" dimension** — the prior task's downgrade conditional does not fire (its
  antecedent, a recording artifact, is false); a confirmed-real Tendering surge is, if anything, a
  more concrete basis for a capacity-diversion story. Still level H, not proven — the causal
  mechanism (actual diversion vs. an independent operational constraint) remains undistinguished.
- **Part 4, independent Validator** — one DB connection, read none of the Explorers'/Synthesizer's
  files. **Independently reconfirmed all three headline findings**: customer switch counts
  near-identical in substance (PEM103 0/43 vs. Explorer 1's 0/46; PEM107 1/86 at 0.02-0.03% of qty
  vs. Explorer 1's 1/87 at 2.13% — both agree the switch is noise-level in both cases, small
  differences from independently-derived both-years customer counts); no clean step-change month in
  either division (same lumpy, contract-driven spikes independently described); and one NEW
  attribute check (its own choice, not asked to reproduce Explorer 2's): PEM107's Tendering notice
  days grew from a median 40 to 60 days between 2025 and 2026 on comparable sample sizes (45 vs. 49
  rows) — a genuine lead-time change a pure relabeling would not produce. **No discrepancy found
  with either Explorer's substantive conclusion.**
- **Node statuses updated in `PROJECT_GRAPH.md`**: Q23's node and critical-path narrative extended
  with the channel-shift-cause finding (still "done", not reopened); **G1 flagged explicitly** —
  checked for a channel-mix recording bug that would require correcting the Omni forecast/
  forward-test log before 2026-09-30 scoring, none found, no correction made, pre-existing
  volatility caution for PEM103/PEM107 reaffirmed.
- **DATA_MAP.md**: business view recorded at level A (§7); data-derived business-change finding
  recorded at V2 alongside it, explicitly as a contradiction, not a resolution; new
  `customer_segment` column fact (§2); Trap 18 marked FIXED AT SOURCE with the fix location (§4);
  new corrections-log entries for the 136-code-overlap premise and the channel-shift-cause finding
  (§6).
- **Full test suite: 86 passed** (84 existing + 2 new `test_cube_ces_pull.py` cases).
- **Privacy**: raw `CustomerID`/`CustomerName` values were read by both Explorers and the Validator
  but never printed in any report or committed file — only aggregated counts/shares, per
  DATA_MAP.md's own rule (no customer names/codes in project documentation, repository is public).
  Raw pulls with identifiers are cached under `output/data/` (gitignored, never committed).

**METRICS.md Sec.22 (robust_minmax) added — DONE (2026-09-24).** Documentation only: no database
access, no code changes, no node status changes. Defines `robust_minmax` (robust_ensemble,
per-item Min/Max per ensemble member, range_ratio, robust/sensitive item split at range_ratio ≤/>
1.25 with 1.10/1.50 sensitivity counts also required, and the section 16/19 trade-off curve feeding
the D2 service-level decision) ahead of Max-Min actually being computed with it, per CONVENTIONS.md.

**Part 1 — PEM101 ensemble counts confirmed from the record, not computed here.** The record gives
**one** number for PEM101, not two: **59 of 4,130** grid combinations (`stock_definition="current"`)
within tolerance (`not_late` ±3pp, stock value ±15%) **on both the calibration and validation
periods jointly** — STATUS.md's own Phase J3 entry above ("**PEM101: PARTIALLY CALIBRATED.** 59/
4,130 combinations fit both periods within tolerance..."); `output/summary/phaseJ3_report.md` line
46 ("PEM101 | **Partially calibrated** — 59/4,130 combos fit both periods at realistic stock");
`output/summary/phaseJ3_2_calibration_summary.json` (`"division":"PEM101","stock_definition":
"current","n_passing":59,"n_total":4130`). **No source anywhere in the record separately states a
calibration-period-ONLY count** (i.e., before the validation-period filter is applied) — the
Modeler's own grid-search code (`src/investigations/phaseJ3_run_calibration.py`) computes
`n_passing` as combinations meeting BOTH windows' tolerance at once, and every narrative report
(STATUS.md, the Phase J3 report, the independent Validator's check) cites only that joint figure.
Per this task's own instruction (do not compute anything), no calibration-only count is derived
here from the underlying grid CSV — this is reported as a gap in the record, not filled. Two other
`stock_definition` variants exist in the same JSON for PEM101 (`fg_prefixed_only`: 21/4,130;
`all_stockholding_except_qa_fmto_fmts`: 59/4,130, identical to `current`) — noted for completeness;
`current` is the variant every narrative report headlines.

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
  only begins Jan 2023).
  **[SUPERSEDED — Phase J2, 2026-09-23: this table is on_time_exact (delivered exactly on the due
  date), row-weighted, vs. PlanDelDate — not comparable to fill_rate (METRICS.md Sec.19). The
  corrected `not_late` figure (delivered on or before the due date, PEM101, row-weighted, vs.
  ForecastDelDate, `output/summary/phaseJ2_0_not_late_byyear.csv`) is 76.0%/94.1%/95.5%/95.9% for
  2023/2024/2025/2026 — still improving, but starting much higher than the on_time_exact series
  above implies, because most "misses" here are early deliveries, not late ones.]** Spike-month orders are somewhat more likely to be
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
  (Part 2's open caveat — **re-tested in the Phase A investigation, 2026-09-02: still formally
  unresolved and undetectable in this schema, but every test bounds any revision at under ~2.5%
  of rows with no consistent direction, too small to explain the 6-day notice or the 57.8%→73.2%
  on-time swing — see the Phase A log entry below**); whether Cube_CES's own PlanDelDate is
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

**Phase A — Fix potentially wrong foundations: DONE (2026-09-02), answered with caveats.** First
task run under the `AGENTS.md` multi-agent structure: three agents dispatched in parallel
(A1 = Explorer+Validator combined, A2 = Analyst, A3 = Validator), then a Synthesizer merged their
findings. INVESTIGATION ONLY: no min/max calculated, no model built, `config/config.yaml` not
touched, no code changed. Scripts: `src/investigate_forecastdate_revision.py` (A1),
`src/investigate_2025_decline.py` (A2); A3 worked from existing pulls, no new script. Reports:
`output/summary/phaseA_a1_forecastdate_revision_findings.md`,
`phaseA_a2_2025_decline_findings.md`, `phaseA_a3_date_keying_findings.md`,
`phaseA_synthesis.md`. Supporting CSVs: `output/summary/phaseA_a{1,2,3}_*.csv`;
raw/processed pulls: `output/data/phaseA_a{1,2}_*.csv`.

- **A1 — is `forecast_date` fixed at PO intake or revised later? Unresolved, high confidence in
  the negative finding, high confidence the effect (if any) is too small to matter.** Anomaly
  check (Part 0, requested by the user): independently re-verified, with a fresh unfiltered
  query, that the reported table-wide 1970/2032 epoch anomaly and future-dated `createDate` do
  NOT reach the 128-item scope or the 3 focus codes (0 rows found in either direction) — both
  fields are safe to use for this scope. Cross-table comparison: `cube_Sale_APD.forecast_date`
  matches `Cube_CES.ForecastDelDate` EXACTLY on 100% of joinable rows (effectively the same
  field); it disagrees with `PlanDelDate` on 2.3-3.2% of rows depending on scope, with NO
  consistent direction (64% earlier/36% later) — consistent with STATUS.md's existing
  "PlanDelDate and ForecastDelDate identical on 97.9% of rows" finding, not a contradiction.
  Revision search: (a) same-`createDate`-different-`forecast_date` cases in `cube_Sale_APD`
  (0.25% of groups, 68 groups/158 rows) ALL show differing quantities — the established
  split-lot signature, zero cases at the 3 focus codes, **this sharpens (not resolves) the
  Phase 3.1 "cannot rule out a continuously-updated plan" caveat toward "very likely explained"**;
  (b) `Cube_CES`'s finer PlanID grain: only 6 of 159 disagreeing pairs (0.033% of rows) are
  genuinely ambiguous and irresolvable from the data (2 of the 6 have no `ActualDelDate` yet —
  will resolve on their own once delivered); (c) **confirmed, extending the earlier
  108-table/Root-cause-of-2022/2023-break search to the column level: no audit/history table or
  per-row modification-timestamp column exists anywhere for either table** — revision-in-place is
  fundamentally UNDETECTABLE from this data model, not merely "not found." **Net conclusion,
  stated plainly per instruction (absence of evidence is not evidence of fixedness)**: whether
  `forecast_date` is ever revised remains an open, unprovable question, but every test bounds any
  possible revision at under ~2.5% of rows with no consistent direction — too small to be the
  primary driver of the 15-point on-time swing or the 6-day median notice figure. **The 6-day
  notice and 73.2% on-time figures are NOT overturned by this finding.**
- **A2 — why did 2025 sales fall 26%? Answered, moderate-to-high confidence, mostly real with a
  genuine partial confound.** The "26%" is specific to the Jan-Jul window (full calendar-year
  2025 vs. 2024 is only -7.2% — Aug-Dec 2025 actually exceeded Aug-Dec 2024 by 29.6%, meaning the
  recovery began within 2025 itself, before 2026). **51% of the Jan-Jul decline traces to ONE
  item, `EEE-F-FC-1040010002`** (one of the 3 focus codes) — flat unit price throughout, a
  genuine volume collapse (buyers ~36→9) then recovery (→~30 buyers by 2026), not a price/mix/
  classification effect; this same item is separately the largest driver (46.5%) of the
  2025→2026 recovery per the earlier "History depth" task — i.e. one real item swinging both
  directions. **Recording-artifact test (same method as the 2022/2023 break): no whole-population
  cliff found** — the decline is gradual (-6.3% at the Dec2024→Jan2025 boundary, unlike the
  prior breaks' >6x/>100x jumps), no aggregate `revenue_type`/`status` shift, and the WHOLE
  PEM101 division declined similarly (-29.1%) regardless of revenue_type. **But a real, partial
  customer-reclassification confound exists underneath**: of 127 customers who appear to have
  "dropped" after Jan-Jul 2024, 26 (58.5% of that cohort's ₿46.24M value) in fact continued doing
  business, just relabelled from Omni Channel/PEM101 to Tendering or another division — one
  account, `CS07977`, accounts for 23.6% of the ENTIRE headline decline this way (its Omni
  Channel activity fell to ~zero while its Tendering activity rose to ~₿263M). The other 101 of
  127 dropped customers show zero activity anywhere post-2024 (likely genuine churn, not
  independently confirmed). **The 2 Lumpy focus items (`HS-F-99-02110`, `HS-F-99-0213`) both
  GREW through the 2025 dip window** — contrary to the aggregate pattern, too small in scale to
  move the total. **Unresolved (stopping rule applied)**: why `EEE-F-FC-1040010002`'s buyer base
  broadly paused in H1 2025 — no stock/supply/contract-cycle data exists in this database to test
  this (consistent with the Phase 4 groundwork finding that no historical stock-level series
  exists); needs business confirmation.
- **A3 — which date field keys the demand series? Answered, high confidence.** Direct code read
  (not inference) of `src/load_data.py`, `load_data_full.py`, `aggregate_levels.py` (default
  `date_col="createDate"`, never overridden), `backtest.py`, and `backtest_aggregate.py`: **all
  five key monthly aggregation on `createDate`**; zero references to `forecast_date` in any
  pipeline script (only in one-off investigation scripts). Validated the reusable pull
  (`raw_order_leadtime_128items.csv`, 27,479 rows) directly: reconciles exactly to STATUS.md's
  prior figures (1 null forecast_date, 15 negative-interval rows), zero epoch/future-date
  anomalies in this scope (independently reproduced A1's Part-0 check), 53 exact full-row
  duplicates flagged (consistent with this project's existing "keep all rows" decision, not a
  new problem). **Built both series and compared over the common 32-month window**: total qty
  createDate-keyed 3,359,079 vs. forecast_date-keyed 3,286,187 (-2.17%), fully reconciled to the
  unit — 72,889 units (64,134 of them due September 2026 alone) shift to real future delivery
  dates beyond the current window. Gross month-to-month reallocation: **11.53% of qty, 14.98% of
  value**; **940 of 3,584 item-months (26.2%) change materially** (threshold: ≥5 units or ≥20% of
  the item's own mean monthly qty, stated explicitly); **97 of 112 items (86.6%) affected in at
  least one month**. Demand classification (ADI/CV²) changes for 11 of 112 items (9.8%, 7
  borderline Intermittent↔Lumpy, 4 more consequential ADI-crossing changes) — **all 3 focus items
  KEEP their classification (Erratic, Lumpy, Lumpy) under both keyings**, though all three still
  show materially reshuffled individual months. **Consequence**: `createDate`-keying
  under-recognises near-term future contractual demand (the invisible 72,889 units above) — a
  stockout-risk-direction bias, not a uniform one. **Recommendation: key the series on
  `forecast_date`**, explicitly conditional on A1's revision finding (see Synthesizer resolution
  below).
- **Synthesizer — merged conclusions, no direct contradictions found (high confidence in that
  specific check).** A3's conditional recommendation is resolved: **it STANDS, with a caveat, not
  blocked** — A1 did not find revision, only failed to rule it out, and bounded its impact as too
  small to matter; A3's own fallback (capture `forecast_date` as a frozen snapshot at time of use,
  never a live re-query, consistent with `CONVENTIONS.md`'s reproducibility rule) should be
  applied regardless of how the unresolved question eventually settles. **A2's decline driver and
  the Phase 2/3.1 under-forecasting bias question connect in a way no single agent tested
  directly**: since `EEE-F-FC-1040010002`'s real, large recovery swing sits inside the actual
  6-month backtest test window, a meaningful but UNQUANTIFIED share of the measured bias
  MAGNITUDE (not its mere existence) is plausibly inflated by this one item/window overlap,
  separate from the already-recorded structural reason (point forecasts vs. spiky demand). No
  agent recomputed bias with this item held out — **flagged as a new, untested gap for the
  Modeler**, not resolved here. Checked deliberately for contradictions against STATUS.md: **none
  found** — the closest candidates (the Phase 3.1 forecast_date-stepping caveat; the 97.9%
  PlanDelDate/ForecastDelDate match) are refinements/consistent numbers, not contradictions.
- **What the data could not resolve (9 items, full detail with owning team in
  `phaseA_synthesis.md` §5)**: whether `forecast_date` is ever revised in place (needs a genuine
  audit/snapshot table or IT/business confirmation — undetectable otherwise); the cause of the
  2.3-3.2% `forecast_date`/`PlanDelDate` disagreement; 2 remaining ambiguous `Backlog`-status
  PlanID pairs (will resolve once delivered); root cause of `EEE-F-FC-1040010002`'s H1-2025
  buyer-base pause (needs stock/supply/contract data); whether the 101 zero-post-2024-activity
  "dropped" customers are genuinely lost (needs account-status confirmation, largest few named in
  the synthesis report); the mechanism behind `CS07977`'s/`CS00477`'s Omni Channel→Tendering
  relabelling (needs the sales team who classifies `revenue_type`); how much of the measured
  forecasting bias traces to the one-item/window overlap (needs the Modeler); how a real
  Max-Min policy would respond to the re-keying shift (needs the Modeler, in Phase E); whether
  A3's 53 flagged duplicate rows overlap the project's previously-classified duplicate-vs-split-
  lot sets (small targeted follow-up, not chased here per the stopping rule).

**Phase B, tasks B1/B2/B3 — DONE (2026-09-02).** Single Modeler, per `AGENTS.md` (this part of
Phase B needs all three aggregation levels — Category, Type, Item — in one view, and each step
depends on the previous, so it is not split across agents). Scope: the 128 item codes in Product
Cate. Fuse and Surge Arrester, at Category/Type/Item level, with the three focus codes
(`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`) given particular attention throughout.
Modified: `src/load_data.py`, `src/load_data_full.py`. New: `src/backtest_rekeyed.py`,
`src/bias_item_isolation.py`, `src/item_level_reconciliation.py`. Full reports:
`output/summary/b1_rekeying_report.md`, `b2_bias_isolation_report.md`,
`b3_item_level_approach_report.md`; CSVs `output/summary/b1_*.csv`, `b2_*.csv`, `b3_*.csv`; charts
`output/charts/b1_focus_*.png`, `b3_*_approach_comparison.png`. No model choice written to
`config/config.yaml`.

- **B1 — re-key the demand series and re-run every backtest.** `load_data.py`/`load_data_full.py`
  now pull `forecast_date` alongside `createDate` in the same query, validate it (nulls and
  negative-interval rows excluded from the forecast_date-keyed series only — 0.004%/0.05% of
  rows respectively on this fresh pull, matching Phase A's rates; epoch/future-date anomaly
  re-checked on the fresh pull, 0 found, Phase A's negative finding re-confirmed not assumed),
  and build monthly series BOTH ways: `processed_..._createDate.csv` / `..._forecastDate.csv`.
  **The original unsuffixed filename is kept as an exact alias of the createDate-keyed series —
  every existing script that reads it keeps working unmodified, nothing deleted.**
  `forecast_date` is frozen as a snapshot at pull time (a `snapshot_pull_date` column is written
  into the output, e.g. 2026-09-02 15:52:39 for the 128-item pull), never re-queried live, since
  Phase A could not rule out revision after intake. Both keyings are restricted to the identical
  **31-month window (2024-01 to 2026-07)** that every existing backtest result was computed on —
  32 complete months were actually available on this run (real time has advanced since the
  original pull), and the newest month was deliberately excluded and stated explicitly, not
  silently absorbed, to keep this a true apples-to-apples comparison.
  - **Re-keying magnitude, this fresh pull**: in-window qty createDate=3,239,577 vs.
    forecast_date=3,157,956 (**-2.52%**) — close to but not identical to Phase A's -2.17%,
    explained by real data growth between pulls on a live database, stated explicitly.
  - **Pipeline validation re-confirmed passing**: 0 negative qty in either keyed series; every
    item has exactly 31 months in both; monthly totals reconcile exactly to their own filtered
    daily source (the aggregation function raises loudly otherwise — did not raise).
  - **Cross-check, high confidence**: this run's freshly recomputed createDate-keyed Combination
    test-set MAE/RMSE/Bias/MASE match the EXISTING `rule_part4_test_results_per_series.csv`
    (from the earlier `evaluate_strategies.py` task) EXACTLY, to the decimal, at all 3 levels —
    validates the new pipeline before trusting anything computed on the new key.
  - **Backtest result is genuinely mixed, not a clean improvement or regression — reported
    plainly, not smoothed into one verdict.** Train/val/test (last 6 of 31 months) IMPROVES under
    forecast_date at every level for every model except Naive (Item Combination MAE
    389.4→353.2, -9.3%; Category 14,606.4→14,143.4, -3.2%; Type 4,010.8→3,808.4, -5.0%). Naive
    gets dramatically WORSE (Item 437.6→566.1). **Rolling-origin (7 origins across the whole
    series) WORSENS at every level for every model** (Item Combination MAE 391.4→432.2, +10.4%;
    Category 14,392.3→18,601.9, +29.3%; Type 3,946.8→4,974.1, +26.0%). **21 of 21 level/model
    cells are material in BOTH evaluation methodologies, in OPPOSITE directions** — high
    confidence in the numbers, moderate confidence only in a proposed (not proven) explanation
    that the train/val/test window sits where forecast_date's demand-smoothing effect
    concentrates while earlier rolling-origin windows do not benefit the same way. **CORRECTED
    2026-09-02, see the follow-up log entry below**: direct per-origin testing found this was too
    generous a framing — not a smooth gradient at Category/Type level, but improvement
    concentrated in one specific final test window.
  - **Bias**: Combination's bias gets slightly MORE negative under forecast_date at every level
    in train/val/test (Category -12,138.8→-13,946.4; Type -3,045.1→-3,496.2; Item
    -216.1→-249.0, a 13-15% worsening) despite MAE improving — picked up directly by B2.
  - **Validation-to-test gap**: createDate's gap stays small (+3.8% to -0.9%); forecast_date's
    gap is large and NEGATIVE (-19.9% to -30.5%, test much better than validation predicted) —
    reported, not investigated further (flagged for the Modeler).
  - **Focus items** (Combination, test set): all three improve on both MAE and \|Bias\| under
    forecast_date-keying (`EEE-F-FC-1040010002` MAE 1970.8→1206.1; `HS-F-99-02110` 611.6→503.8;
    `HS-F-99-0213` 272.5→228.5).
  - **No STATUS.md conclusion is overturned**: Combination remains competitive under both
    keyings and both evaluation methods (Phase 2's selection stands); every existing backtest
    output in `output/summary/` (rule_part4_*, part4_*, combo_variant_*) should be treated as
    superseded once forecast_date-keyed results are adopted, per the Phase A action item.
- **B2 — re-measure bias with `EEE-F-FC-1040010002` separated, high confidence, level-dependent
  answer.** At the item's own Type (`High Voltage Distribution Fuse Cutout`, 10 items),
  excluding it removes **87-90% of Combination's bias** at both keyings (createDate -2,198.5→
  -212.0; forecastDate -1,393.7→-177.1) — every one of the 6 base models shows the same pattern
  (77-124% removed). **Earlier bias measurement at this Type's level was substantially an
  artifact of this one item.** At Category level (`Fuse`, 6 Types including this one), excluding
  it removes only **5-9%** of Combination's bias (createDate -21,054.6→-19,068.0; forecastDate
  -25,606.2→-24,389.7) — **the negative bias PERSISTS as a real, broad property of the rest of
  the Fuse category, not explained by this one item.** Control check (`Surge Arrester`, which
  never contained this item) behaves as expected, unaffected. At Item level (mean across all
  113 items), excluding it moves the mean only slightly (-3.5% to -6.5%) — expected, since one
  item carries limited weight in an equal-weighted mean of 113. **Practical implication**: use
  the Category-level bias figure for Fuse as-is for safety stock; treat the
  `High Voltage Distribution Fuse Cutout` Type-level bias figure with caution (mostly this one
  item's collapse-recovery cycle, not the other 9 items' stable behaviour); the item itself
  needs individual handling, not a Type-level blanket policy.
- **B3 — how aggregate levels should support item-level forecasting.** Compared Direct /
  Top-down (allocate Type-level Combination forecast by each item's historical qty share of its
  Type) / Reconciled (Direct forecasts rescaled per Type per month to sum to the Type forecast),
  all at item level, forecast_date-keyed series (B1's recommendation — a stated scope choice,
  not re-tested against createDate here), test set. **Top-down has the best point estimate**
  (mean item MAE 341.6 vs. 350.0 Direct vs. 350.0 Reconciled) **but no pairwise difference
  clears significance** (paired t = -1.52, -0.34, +1.51, all \|t\|<2, same paired-t methodology
  as the prior winner-margin check) — stated directly per instruction, no approach is clearly
  better in general. **The one clear, well-evidenced finding: the benefit is share-of-Type-
  dependent.** The one focus item that is genuinely dominant in its Type
  (`EEE-F-FC-1040010002`, 48.3% of `High Voltage Distribution Fuse Cutout`'s train+val qty)
  improves 16.1% in MAE and 19.4% in \|Bias\| under Top-down (1206.1→1011.9 MAE); the two
  minor/mid-rank focus items (`HS-F-99-02110` 1.2% share, `HS-F-99-0213` 3.2% share) barely move
  (503.8→497.3 and 228.5→228.5). Splitting all 113 items by a 30%-dominance threshold shows the
  same pattern at smaller scale (minor items -2.5% MAE under Top-down, dominant items' pooled
  MAE also favours Top-down). **High confidence in direction, moderate in exact magnitude**
  (only one genuinely dominant item exists in this 128-item scope to test the sharpest case).
  A conditional/blended policy (Top-down for dominant items, Direct for minor ones) is better
  supported by this evidence than picking one approach uniformly, but was not itself built or
  tested here.
- **What the data could not resolve**: why rolling-origin and train/val/test disagree in
  direction under re-keying (a plausible mechanism offered, not proven); the cause of
  forecast_date's large negative validation-to-test gap; whether the Type's other 9 items
  (excluding `EEE-F-FC-1040010002`) have their own unrelated bias problem worth investigating
  individually; whether a conditional Top-down/Direct policy by item dominance would outperform
  either approach used uniformly (not built); item-level rolling-origin stability was not
  re-tested on the forecast_date key (out of this task's scope).

**Phase B follow-up — was the re-keying improvement leakage? Why did rolling-origin and
train/val/test disagree? — DONE (2026-09-02).** Single Validator (per `AGENTS.md`: re-examines
one series, results must be interpreted together, not split). Script:
`src/leakage_check_forecastdate.py`. Full detail:
`output/summary/b4_leakage_and_windowposition_report.md`; CSVs `output/summary/b4_*.csv`; chart
`output/charts/b4_per_origin_mae_comparison.png`. No model choice written to `config.yaml`; no
existing file modified.

- **Part 1 — future-dated rows quantified, high confidence.** Pull date (cited from the
  `snapshot_pull_date` column): 2026-09-02 15:52:39. **472 of 27,584 raw rows (1.71%) have
  `forecast_date` after the pull date** (qty 77,966, ฿26.3M, 66 items) — overwhelmingly dated
  2026-09 (440 rows), with a small tail through 2027-05. **Decisive check: ZERO of these 472
  rows fall inside the 31-month window (2024-01 to 2026-07) used for every backtest, and
  therefore zero fall inside the final 6-month test window or any rolling-origin test window** —
  the window ends more than a month before the pull happened, so every future-dated row is
  necessarily dated after the window closes, not inside it.
- **Part 2 — the train/val/test improvement is NOT leakage from this mechanism, high
  confidence.** Built a third series (`forecastDateNoLeak`) excluding the 472 future-dated rows
  and re-ran the identical backtest: **results are numerically IDENTICAL to the existing
  `forecastDate` series at every level and model** (confirmed two ways: a row-level
  itemcode+year_month merge-diff shows 0.0 total quantity difference; the full backtest re-run
  matches MAE/RMSE/Bias/MASE to 6 decimal places). This is a mathematical consequence of Part 1's
  finding (nothing was actually excluded within the window), not a new discovery, but it directly
  answers the question asked: **the train/val/test improvement survives unchanged — it is not
  explained by this specific leakage mechanism.**
- **Part 3 — the direction conflict is NOT well explained by a smooth "window-position" effect
  at Category/Type level; only partially at Item level — high confidence in the numbers,
  corrects the earlier framing.** Per-origin Combination MAE, createDate vs forecast_date, across
  all 7 rolling origins: at **Category and Type level, forecast_date gets steadily WORSE from
  origin 1 through origin 6** (Category: +13% to +46% worse, monotonically worsening — the
  opposite of a "closer to present is better" trend), **then abruptly reverses only at the exact
  final origin** (train_size=25, the same split train/val/test used: Category -3.2%, Type
  -5.0%). Correlation(train_size, %diff) is essentially zero at Category (-0.006) and weak at
  Type (-0.178) — precisely because the trend runs the wrong way for 6 of 7 origins and the sign
  flip is concentrated entirely in the last point. **Item level shows a real, moderate declining
  trend** (correlation -0.679, +23% down to -9% roughly monotonically from origin 2 onward) —
  genuine partial support for a gradual effect at this level only. **Verdict, stated directly:
  the improvement is concentrated in ONE SPECIFIC 6-month test window (2026-02 to 2026-07), not
  demonstrated to be a generalizable property of forecast_date-keying.** The prior "window-
  position effect, moderate confidence, not proven" note (B1) is corrected, not silently
  replaced — flagged explicitly in both places it was recorded, above.
- **Part 4 — recommendation for future-dated rows (reasoning only, nothing implemented).** For
  backtesting: add an explicit, automatic guard asserting the pull date is at least `HOLDOUT`
  months past the test window's last month before scoring any window (a config-level check,
  e.g. `backtest.require_closed_test_window: true`, enforced in code) — this task had to build
  ad hoc tooling to confirm the window happened to be closed; that verification should be
  automatic going forward, not manual. For Phase 4 live forecasts: future-dated rows are
  confirmed, deterministic demand and should be treated like this project's existing MPS/Backlog
  rows (Phase 1.5 locked decision — never dropped) — Phase 4's demand figure for a future period
  should explicitly separate (a) already-booked order quantity (read from the order book) from
  (b) a statistical forecast for the not-yet-placed remainder, reported as two components, not
  blended into one number. Concrete enough to write into `config.yaml`/code next task; not done
  here, per instruction.
- **What the data could not resolve**: what specifically makes the 2026-02-to-2026-07 window
  favourable to forecast_date-keying when 6 of 7 other windows are not (candidate factors — a
  specific demand event, a seasonal effect, a data-completeness artifact — not tested); whether
  this favourable window would persist if rolled forward as new data accrues (cannot be tested
  without more data); the mechanism behind Item level's stronger but still moderate trend versus
  Category/Type's near-absence of one.

**Date-column Validator investigation — was `createDate` misread as the customer order date?
DONE (2026-09-04).** Single Validator, per `AGENTS.md` (one coherent question, the date columns
must be understood together, not split across agents). Motivated by the fact that
`createDate` = PO-received was accepted at Phase 2 Step 1 from a within-table name-matching test
(0 mismatches vs. the table's own `year`/`month` columns), never from behavioral proof, and a
separate column `PODate` exists in the same table. INVESTIGATION ONLY: no code/config changed,
nothing committed. Script: `src/datecol_validator_investigation.py`. Full report with every
figure's source citation: `output/summary/datecol_validator_report.md`; supporting CSVs
`output/summary/datecol_p*.csv`; charts `output/charts/datecol_*.png`.

- **Part 1 — every date column mapped, high confidence.** `INFORMATION_SCHEMA.COLUMNS` confirms
  (not assumed from memory) `cube_Sale_APD` has exactly 8 date/datetime columns: `createDate`,
  `PODate`, `forecast_date`, `timeStamp`, `customer_entry`, `warranty_date`, `newCustomerDate`,
  `plan_date`. Base scope (128 items, `division='PEM101'`, no other filter): 27,679 rows.
  **createDate == PODate exactly on 99.9458% of rows (27,664 of 27,679); only 15 rows disagree,
  ALL 15 with PODate EARLIER than createDate (never the reverse), median gap 8 days, max 44
  days** — a small, one-directional data-entry-lag signature, not a systematic misread. **Focus
  codes: 100.00% match, 0 mismatches out of 633 rows.** `timeStamp` is reconfirmed as a pure
  ETL/refresh artifact (all 27,679 rows land on ONE calendar date spanning 64.2 seconds, and that
  date has itself moved forward since the last check — 2026-08-30 in the earlier Phase 2 finding,
  now 2026-09-03 — confirming it re-stamps on every reload). **createDate shows NO comparable
  load-batch signature** (652 distinct calendar dates, max 0.42% of rows on any single date) —
  createDate is NOT also a load artifact. **Weekday distribution**: createDate and PODate are a
  clean 5-business-day spread with zero weekend rows; `forecast_date` is a completely different
  shape (37.4% Friday, small nonzero weekend share) — confirming forecast_date is a scheduled
  delivery-date concept, not a raw event date (honest limitation noted: the business-day-only
  createDate/PODate pattern cannot itself distinguish "genuine customer ordering behavior" from
  "business-side data entry only happening on business days"). **Cross-check against `Cube_CES`
  (an independently-populated table, not a copy within the same row)**: 99.82% of rows join on
  (contractid, itemcode); grain confirmed safe (0 of 70,826 pairs have >1 distinct `CtrDate`/
  `ReceiveCtrDate`). **PODate matches `Cube_CES.CtrDate` and `.ReceiveCtrDate` at 100.000%**;
  createDate matches both at 99.946% (same 15-row exception); `forecast_date` matches at only
  6.49% (median/mean offset 6.0/10.8 days) — independently confirming forecast_date is a
  genuinely different concept from the order/contract date. **Re-verified the task brief's cited
  narrow-sample "`CtrDate`==`ReceiveCtrDate` 100%" note at full 128-item scope (not assumed
  still true)**: on ALL `Cube_CES` statuses it drops to 86.95%, but this is explained, not a
  contradiction — pre-contract stages (`P2`/CES-native-`MPS`/`N/A`/`P3`) have BOTH fields NULL
  (not yet "received"), scored as non-equal by a strict day-diff without being a genuine
  disagreement. Restricted to `Status IN ('Actual','Backlog')` (this project's established
  `Cube_CES` basis): **99.921% identical (62,166 rows)** — confirms, at full scope, what the
  prior narrow 3-period sample suggested.
- **Part 2 — what is createDate, actually? Moderate-to-high confidence it is the true
  order/contract date, not a record-creation artifact.** The record-creation-artifact hypothesis
  predicts a load-batch/weekend-clustering signature and a large, one-directional gap against an
  independent source; neither was found (createDate agrees with `Cube_CES.CtrDate`, populated by
  a different process, 99.95% of the time). **Honest caveat, not force-resolved**: this cannot
  fully rule out that createDate/PODate/CtrDate all really represent "when the contract was keyed
  into these systems" rather than the literal moment of customer intent — no external,
  non-database record exists to close that gap (same class of limitation as Phase A1's
  unresolved `forecast_date`-revision question). **Re-keying quantification (same method as the
  existing createDate-vs-forecast_date comparison, Phase A/B1, for direct comparability)**: only
  7 of 27,665 modelling-scope rows (0.0253%) would move to a different calendar month if keyed on
  PODate instead of createDate — qty moved 27 units (0.0008% of window total), sale moved
  ₿49,335 (0.0071% of window total) — **three orders of magnitude smaller than the
  createDate-vs-forecast_date re-keying (11.53% qty / 14.98% value)**, itself strong evidence
  createDate and PODate are not meaningfully different fields.
- **Part 3 — order notice recomputed on PODate: CONFIRMS, does not overturn, the existing 6-day
  median, high confidence.** Same modelling scope and row set both ways: median 6.0 days
  (createDate) vs 6.0 days (PODate); mean 10.92 vs 10.93; ≥30-day share 5.866% vs 5.892%; ≥60-day
  and ≥90-day shares identical to 3 decimals. **Feb-Jul 2026 test window back-dated-entry check
  (was there a batch of createDate-much-later-than-PODate rows explaining the Phase B1/B4
  divergence?): NO, high confidence in this negative finding.** TEST window (2026-02 to
  2026-07, 5,794 rows): only 4 rows (0.069%) show any createDate≠PODate gap, 18 units/₿38,835
  affected (~0.002-0.024% of the window) — not even the highest of the three rolling windows
  (TRAIN's rate is 0.072%; VAL shows zero such rows at all). This rules OUT the createDate/PODate
  back-dating mechanism specifically as an explanation for the B1/B4 anomaly; it does not
  identify the true cause, which remains open (already recorded as such in the B4 log entry
  above) — stated explicitly as correlation-not-mechanism, per instruction.
- **Part 4 — recommendation: no change needed, and NO CONTRADICTION with STATUS.md.** createDate
  and PODate are functionally the same field for every purpose tested here; continue keying
  order-intake/notice-period metrics on createDate (or PODate, interchangeably). **This finding
  does not touch the separate, already-recorded Phase A/B1 recommendation to key the
  INVENTORY-AVAILABILITY series on `forecast_date`** — that recommendation concerns a completely
  different pair of concepts (order date vs. delivery date), reconfirmed here as genuinely
  distinct (6.49% exact match, ~6-10 day offset). Per instruction, explicitly flagging whether
  this reverses STATUS.md's Phase 1.5/Phase 2 Step 1 assumption that createDate = PO received:
  **it does not reverse it — it independently CONFIRMS it**, now via cross-table behavioral
  evidence rather than a within-table name-matching test. The task brief's premise that this
  assumption "was inherited and never tested" is now closed: it has been tested, and held up,
  with one narrow (0.054% of rows, always-lagging, non-blocking) exception recorded above.
- **What the data could not resolve**: whether createDate/PODate/CtrDate record the literal
  moment of customer order intent vs. contract-entry date (needs an external non-database record
  or IT/business confirmation — undetectable otherwise, same class as Phase A1's open item); the
  mechanism behind the 15 rows (0.054%) where createDate lags PODate by up to 44 days (too rare
  to chase further, ₿0.13M total value, non-blocking); what actually explains the Feb-Jul 2026
  rolling-origin-vs-train/val/test divergence (this task rules out one specific candidate
  mechanism, does not identify the true cause — already an open item, not newly created here);
  the business reason two separately-named fields (`CtrDate`/`ReceiveCtrDate` in `Cube_CES`;
  `createDate`/`PODate` in `cube_Sale_APD`) exist for what is, on the Actual/Backlog basis, a
  >99.9%-identical value (needs the source system's own documentation or IT confirmation).

**Modeler tasks 1-3 (window explanation, leakage guard, conditional item policy) — DONE
(2026-09-04).** Single Modeler, per the task brief's own decomposition note (the three tasks are
sequential/dependent -- Task 1's finding about window representativeness bears directly on how
Task 3 must be interpreted, so not split across agents). Scripts:
`src/task1_item_isolation_rolling_origin.py`, `src/task1_large_order_examination.py`,
`src/leakage_guard.py` (+ edits to `src/backtest_rekeyed.py`, `src/leakage_check_forecastdate.py`),
`src/task2_leakage_guard_test.py`, `src/task3_conditional_item_policy.py`. Outputs:
`output/summary/task1_*.csv`, `task3_*.csv`; charts `output/charts/task1_seven_origin_with_without_item.png`,
`task1_large_order_concentration.png`, `task3_rolling_origin_approach_comparison.png`,
`task3_share_distribution.png`. Per role boundary (`AGENTS.md`): this Modeler reports performance
only -- no model/policy choice is written to `config/config.yaml` for Task 1 or Task 3; Task 2's
config change is the one explicitly-instructed exception.

- **Task 1 -- does excluding `EEE-F-FC-1040010002` explain the origin-7 (Feb-Jul 2026) reversal?
  NO, high confidence, at every level tested -- the item is not the cause.** Full 7-origin
  rolling-origin rerun (`output/summary/task1_rolling_origin_item_excluded.csv`,
  `task1_per_origin_with_without_comparison.csv`, `task1_reversal_verdict.csv`), Combination
  model, both date keys, Category="Fuse" and Type="High Voltage Distribution Fuse Cutout"
  rebuilt with vs. without the item (reusing `bias_item_isolation.build_group_series`), Item
  level via the existing cross-item mean (112 vs. 111 items, same convention as B2).
  - **Correction/clarification to how `b4_per_origin_comparison.csv`'s existing Category/Type
    rows should be read**: those rows are POOLED means across BOTH categories (Fuse, Surge
    Arrester) and all 8 Types in scope respectively -- NOT Fuse-specific or Fuse-Cutout-Type-
    specific figures, confirmed by direct recomputation (mean of Fuse's and Surge Arrester's own
    origin-7 Combination MAE, 25534.86 and 3677.86, averages to exactly the 14606.36 the existing
    b4 "Category" row reports). This is not a contradiction of B4's numbers (they are correct as
    computed) but a reading-caveat future use of that file should carry forward.
  - **Category level, isolated to "Fuse" alone**: origin 7 is essentially a WASH, not a
    reversal -- WITH the item, createDate MAE=25534.86 vs. forecast_date MAE=25606.21 (forecast_date
    +0.3%, i.e. very slightly WORSE, not better); WITHOUT the item, +3.3% (still not better). The
    "Category-level reversal" the pooled b4 figure showed is driven by Surge Arrester (the
    control, structurally unrelated to this item), not by Fuse.
  - **Type level (the item's own Type), isolated**: WITH the item, origin 7 forecast_date is
    38.9% better (MAE 2281.55->1393.69); WITHOUT the item, forecast_date is 68.7% better
    (590.50->185.03) -- the advantage gets LARGER, not smaller, once the item is excluded. Also
    found: WITH the item, the per-origin pattern at this isolated Type is already mixed (origins
    2-4 show forecast_date better by 25-30%), not the clean "worse-then-reverse" the pooled
    8-Type b4 figure showed -- another consequence of the pooling-across-groups artifact above.
  - **Item level (cross-item mean)**: origin 7, WITH the item -9.3% vs. WITHOUT -7.9% -- barely
    moves (1 of 112 items in an arithmetic mean), reversal persists essentially unchanged.
  - **Verdict: the reversal does NOT disappear at any level -- it persists everywhere tested and
    actually STRENGTHENS at Type level. `EEE-F-FC-1040010002` is not the explanation for the
    aggregate-level origin-7 anomaly.**
- **Task 1, part 2 -- order-timing examination: a real, item-and-window-SPECIFIC smoothing
  pattern exists, moderate-to-high confidence, but does not by itself explain the aggregate
  finding above.** `output/summary/task1_large_order_concentration_summary.csv`,
  `task1_orders_anomalous_window_detail.csv`, `task1_orders_contrast_window_detail.csv`. "Large
  order" defined explicitly as row qty >= the item's own 90th percentile of row qty over its full
  history (192.7 units) -- used as a labelled secondary/robustness check only, since it leaves too
  few rows (6 in-window, 1 in the contrast window) to be the primary evidence; the PRIMARY
  analysis uses ALL orders in each window (116 rows anomalous, 11 contrast), which gives the same
  qualitative answer.
  - Anomalous window (forecast_date in Feb-Jul 2026), ALL orders: createDate-month HHI=0.284 (7
    months touched) vs. forecast_date-month HHI=0.213 (6 months) -- forecast_date IS more spread
    out (lower HHI = less concentrated) than createDate here. Large-orders-only (n=6): same
    direction, HHI 0.500->0.389.
  - Contrast (same item, Feb-Jul 2025, non-anomalous per Task 1 part 1): the pattern REVERSES --
    createDate HHI=0.325 vs. forecast_date HHI=0.413 (forecast_date is MORE concentrated here,
    not less).
  - Contrast (other two focus items, SAME Feb-Jul 2026 window): both also show the opposite
    direction (`HS-F-99-02110`: createDate 0.300 vs. forecast_date 0.405; `HS-F-99-0213`: 0.356
    vs. 0.459) -- forecast_date is MORE concentrated for these items in the identical window.
  - **The smoothing pattern is real and specific to this item AND this window** (confirmed on
    both the all-orders and large-orders lenses), consistent with Task 1's brief. Also noted:
    total order-row volume for this item is far higher in the 2026 window (116 rows) than the
    2025 contrast window (11 rows) -- the 2026 window is this item's Phase-A-documented demand
    recovery period, so there is simply more order-level granularity available to smooth,
    itself a plausible contributing structural reason this pattern shows up only here.
  - **Overall Task 1 conclusion, stated plainly per instruction: the origin-7 window is NOT
    explained.** The item shows a genuine, specific order-timing signature in exactly this
    window (part 2) -- real evidence it contributes something -- but removing it from every
    aggregate level tested does not make the aggregate-level reversal disappear, and it actually
    strengthens at Type level (part 1). The two findings do not contradict each other (an
    item can have a real micro-level pattern without being the dominant driver of an aggregate
    statistic averaged over ~113-128 other series), but together they rule OUT this item as the
    explanation for the anomaly without providing a replacement one. High confidence in both
    individual computations; the anomaly itself remains UNRESOLVED, consistent with -- not a
    reversal of -- B4's own "what the data could not resolve" note above.
- **Task 2 -- leakage guard: built, wired in, and verified working; the pre-existing backtest
  numbers are unchanged, high confidence.** `config/config.yaml` gained a new documented
  `leakage_guard.min_margin_days: 30` section (reasoning: this project's own order-notice
  evidence below -- median 6-day notice, only 5.9% of orders give >=30 days -- means the
  overwhelming majority of orders due in a given month are already entered well within 30 days of
  that month's end, so 30 days is the smallest margin that safely clears this project's monthly
  granularity while staying evidence-grounded, not arbitrary; the real data's actual gap is 33
  days, so the real default passes by a deliberately narrow margin, not a generous one). New
  module `src/leakage_guard.py` (`check_window_closed`, `LeakageGuardError`,
  `load_min_margin_days`) wired into `src/backtest_rekeyed.py`'s `run_rolling_origin` and
  `run_train_val_test` (both now REQUIRE `pull_date`/`min_margin_days`, raising loudly -- never
  skipping/warning -- if `pull_date - window_end < min_margin_days`, stating the window end date,
  pull date, required margin and actual gap in the exception message) and into the only other
  caller of those two functions, `src/leakage_check_forecastdate.py`.
  - **Normal run unchanged, confirmed by direct diff**: re-ran `src/backtest_rekeyed.py` with the
    real config (30) and real data (pull_date=2026-09-02 15:52:39, real gap=33 days, passes) --
    the regenerated `b1_rolling_origin_results_{key}.csv`, `b1_test_results_{key}.csv`, and
    `b1_val_results_{key}.csv` are BYTE-FOR-BYTE IDENTICAL to the pre-guard versions (diffed
    directly): only a refusal path was added, no scoring numbers changed.
  - **Guard tested without touching config.yaml** (`src/task2_leakage_guard_test.py`, output
    captured verbatim): a direct override `min_margin_days=1000` and a boundary override of 34
    (exactly 1 day more than the real 33-day gap) both raised `LeakageGuardError` with the
    required message -- e.g. "Window end (last month of the test window): 2026-07-31 (month
    2026-07). Data snapshot pull date: 2026-09-02. Required margin ...: 1000 day(s). Actual
    margin: 33 day(s)." An override of exactly 33 (the real gap) PASSED with no exception,
    confirming the boundary (`actual_gap_days < min_margin_days`) is exact, not off-by-one. An
    end-to-end call through `backtest_rekeyed.run_train_val_test` itself (not just the standalone
    unit function) with the same override=1000 also raised correctly, proving the guard is wired
    into the real backtest function, not only tested in isolation. `config/config.yaml` was
    verified unchanged (re-read after the test) throughout -- every violating scenario passed its
    override as a function argument, never by editing the file.
- **Task 3 -- Conditional (share-of-Type-dependent) item-level policy: does NOT earn its added
  complexity, high confidence for the more aggressive thresholds, moderate for the Direct-vs-
  Top-down question itself.** `src/task3_conditional_item_policy.py`, forecast_date-keyed (B3's
  own choice, reused here for direct comparability -- **explicitly NOT an endorsement of
  forecast_date's absolute performance level**: Task 1 above and the existing B4 finding show
  forecast_date's rolling-origin advantage is concentrated in origin 7 alone and reverses across
  the other 6 origins, which is exactly why this task treats all-7-origin rolling-origin as
  PRIMARY and the single train/val/test split -- the SAME origin-7 window -- as SECONDARY ONLY,
  per instruction, rather than picking a policy off the one window already flagged as
  unrepresentative). Not re-tested against createDate here (a stated scope choice, same
  convention B3 itself used).
  - **Thresholds tested: 5/10/20/30/50%** of an item's share of its Type's qty, recomputed FRESH
    at every origin's own training window (never a fixed global share) -- chosen to spread across
    the observed share distribution (median 0.5%, 90th pct 22.2%, 95th pct 32.9%) so each
    threshold classifies a genuinely different number of items Top-down-eligible: 24, 17, 13, 7,
    4 of 113 items respectively (`output/summary/task3_per_item_classification.csv`, all 128
    scope codes covered -- 113 scored, 15 with zero sales history anywhere marked excluded, same
    convention as `src/load_data.py`). **Correction to this task's own brief**: direct
    recomputation of B3's exact share_of_type methodology finds 7 of 113 items >=30% share at the
    train+val window, not "only 1" as the brief stated -- flagged explicitly; does not change the
    instruction to test multiple thresholds.
  - **PRIMARY evaluation (rolling-origin, pooled across all 7 origins x 113 items,
    `output/summary/task3_rolling_origin_summary_overall.csv`)**: pure Top-down has the lowest
    point-estimate MAE (424.20) vs. Direct (428.40) and EVERY Conditional threshold (427.5-429.9)
    -- every Conditional variant is worse, not better, than applying Top-down uniformly to all 113
    items.
  - **Significance testing** (`output/summary/task3_paired_significance_primary_per_item.csv`):
    PRIMARY aggregation = mean-per-item-across-origins (n=113 items) before pairing, justified
    because the 7 origins for the same item are not independent draws (overlapping training
    windows over the same autocorrelated series -- pairing at item x origin grain would
    pseudo-replicate and understate the true standard error); item x origin grain (n up to 791)
    also computed as an explicitly-flagged, likely-anti-conservative robustness check
    (`task3_paired_significance_robustness_item_x_origin.csv`), same qualitative pattern.
    Direct vs. Top-down: t=-1.23, NOT significant. Top-down vs. Conditional at 5/10/20%: t=2.14/
    2.38/2.32 -- ALL clear |t|>2, Conditional is MEASURABLY WORSE than pure Top-down at these
    thresholds. Top-down vs. Conditional at 30/50%: t=1.16/1.01, not significant (converges
    toward pure Top-down as fewer items get reverted to Direct). Direct vs. any Conditional
    threshold: never significant.
  - **SECONDARY (single train/val/test split, B3's original window -- flagged as the SAME window
    Task 1 shows is not representative)**: Top-down still best (341.6) vs. Direct (350.0) and
    Conditional variants (343.2-350.1), consistent with B3's original result, but now explicitly
    known to be drawn from an atypical origin, not a stand-alone confirmation.
  - **Verdict, stated directly per instruction: no Conditional threshold earns its complexity.**
    It never beats Direct or Top-down with statistical confidence, and at the more aggressive
    thresholds (5/10/20%) it is measurably WORSE than simply applying Top-down uniformly. Pure
    Top-down has the best rolling-origin point estimate, but its own edge over Direct does not
    clear conventional significance (|t|=1.23) -- so even the simpler Direct-vs-Top-down choice
    is directionally favourable to Top-down but NOT decisively proven by this evidence. **No
    policy choice is written to `config.yaml`, per instruction.**
  - **Extends, does not contradict, B3's "no approach clearly better" finding** -- with a full
    7-origin rolling-origin re-test and a new Conditional approach added, still no approach beats
    Direct with significance, and Conditional specifically is now shown to be significantly worse
    than pure Top-down at several thresholds -- a new, more decisive negative finding for
    Conditional that B3's single split could not have produced (B3 never built a Conditional
    approach).
- **What Tasks 1-3 could not resolve**: the true cause of the origin-7 (Feb-Jul 2026)
  createDate-vs-forecast_date reversal (Task 1 rules out the dominant item as sole cause, a new
  negative finding, but does not identify a replacement cause -- consistent with, not a reversal
  of, B4's existing "what the data could not resolve" note). **CLOSED WITHOUT FURTHER PURSUIT,
  2026-09-04, see STATUS.md Section 8** -- recorded as a known limitation, not investigated
  further; whether pure Top-down (applied to
  every item, not just share-dominant ones) is genuinely better than pure Direct at item level --
  directionally favoured by the rolling-origin point estimate but not statistically confirmed;
  whether createDate-keyed data would show a different Task 3 ranking (not tested, stated scope
  choice matching B3).

**Phase B's three remaining parallel open items (cross-division demand, no-history/no-sale items,
forward-test log rebuild) -- DONE (2026-09-04), three parallel agents per `AGENTS.md` (independent
of each other's results, different capabilities: Explorer+Analyst / Explorer+Validator / Modeler),
merged by a Synthesizer.** Full detail, every figure's citation, and confidence levels in
`output/summary/synthesis_report.md`; source reports `output/summary/task1_crossdivision_report.md`,
`task2_noHistoryItems_report.md`, `task3_forwardTestRebuild_report.md`. No git action taken; no new
data gathered by the Synthesizer.

- **Cross-division demand (Task 1, Explorer+Analyst) -- two valid measurements, genuinely
  different magnitudes, both reported per `AGENTS.md` rule 9, no side taken.** Method A
  (replicates the original 68-item pilot methodology, holds only `itemcode` fixed): **₿85.5M
  excluded, 10.66%** of the all-division total for the 128-item scope, 47/128 items exposed.
  Method B (isolates division only, holding `revenue_type='Omni Channel'`+`status IN
  ('Actual','MPS')` fixed -- this project's actual channel/status scope): **₿2.96M excluded,
  0.42%**, 36/128 items exposed. High confidence in both, direct query + pandas aggregation on one
  shared raw pull (`output/data/task1_crossdiv_raw_128items_alldivisions.csv`). **New finding,
  moderate-to-high confidence**: the historical ₿60.6M/14.3% figure (68-item pilot, Phase 2 audit
  note above) was never purely cross-division -- 67.4% of Method A's ₿85.5M traces to ONE item
  (`EEE-F-FC-1040010002`, division `PPS`, 100% `revenue_type='Tendering'`, not Omni Channel), i.e.
  it always mixed in a cross-CHANNEL effect, not previously separated out here. Method B is small
  and mildly declining over time (1.00% in 2024-H1 to 0.22-0.29% by 2026), not growing. **Whether
  PEM101 physically shares stock with the other divisions is UNRESOLVED -- the database cannot
  show this** (no warehouse field on any sales row; the inventory table's own Division field uses
  an unrelated code space; zero contracts span more than one division; no transfer table exists) --
  stopping rule applied, owning teams named (IT/ERP or Finance for identifying `PPS`/`PTS`/`PSS`
  and any inter-company arrangement with `PCE101`/`PPD101`, confirmed separate legal entities from
  PEM; Warehouse/Operations for physical stock-sharing). **Three options queued for the human, not
  decided**: include all divisions (but which method's figure -- a 25x difference), keep PEM101
  only plus a documented per-item uplift, or forecast other divisions as a separate series.
- **No-history/no-sale items (Task 2, Explorer+Validator) -- true population is 16, not 31.**
  **CORRECTION to this file's own Phase B remaining-work text above** ("the 16 items with no
  history and 15 with no sales"): a fresh live query (`output/summary/task2_q1_std_filter_per_item.csv`,
  `task2_q2_any_activity_per_item.csv`) finds **no second bucket of 15 items with rows present but
  zero total qty/sale exists at this scope** -- among the 112 of 128 items with any row under the
  standard filter, the minimum `SUM(qty)` is 1.0 and minimum `SUM(sale)` is 720.0; nothing nets to
  zero. The true excluded population is **16 items total** (zero rows under the standard filter),
  of which 15 have zero rows anywhere in the table under any filter at all (a SUBSET of the 16, not
  an additional 15), and the 16th (`EEE-F-FL-5920-353-02600`) has rows but 100% tagged
  `revenue_type='Tendering'`. **This directly contradicts the "31-item" figure previously recorded
  in this file's Phase B remaining-work note -- stated explicitly here per `AGENTS.md` rule 4, not
  silently corrected.** High confidence (direct live SQL query, both SUM floors strictly positive).
  Of the 16: **6 classified "(d) Listed but never sold"** (high-to-moderate confidence); **6
  classified "(b) Sold outside this project's filter"** (confidence varies by item, moderate to
  high -- one, `EEE-F-FL-5920-353-02600`, high confidence, sold exclusively via Tendering, and this
  independently CORROBORATES Task 1's own per-item finding for the same item under Method A --
  ₿3.05M PEM101 vs. ₿3.50M other-division/PSS/53.4% -- the two tasks agree where they touch, no
  contradiction found); **4 cannot be classified cleanly** (genuine mixed evidence: real pre-2024
  Omni-Channel/PEM101 history predating the modelling window, or live unconverted quotes mixed with
  ambiguous channel history). **0 items** land cleanly as "(a) new" or "(c) discontinued" -- no
  pricelist-version or status-field evidence supports either label for any of the 16. Per-class
  options (borrow Type profile / manual placeholder / exclude / a fourth option Task 2 itself
  added -- build from the item's own `Cube_CES` history) presented with trade-offs, not decided.
- **Forward-test log rebuild (Task 3, Modeler) -- built, tested, working; no decision queued, a
  build task.** Old log (58 items, `createDate`-keyed, 6 models scored separately -- all three now
  wrong given current scope/keying/adopted-model decisions) archived, not deleted
  (`output/summary/archive/`). New log `output/summary/forward_test_log_v2.csv`, **828 rows** (768
  Item-level [113 real Top-down forecasts + 15 forced-exact-zero for items with no sales history
  anywhere -- mathematically identical to what Top-down produces for zero history, not a
  placeholder] + 48 Type-level + 12 Category-level, all Combination/Top-down-Combination per the
  already-adopted Phase 2/B3 choices), built on the existing frozen `forecast_date`-keyed pull
  (2026-09-02 15:52:39, 31 months through 2026-07) rather than a fresh pull, since a fresh pull
  would not unlock any additional fittable month given the 30-day leakage-guard margin -- reasoned,
  not an oversight. 0 negative forecasts; `actual_qty` empty for all 828 rows, nothing fabricated.
  **The new consistency guard (`score_forward_test_v2.py`) is confirmed working, not just built**:
  tested with 3 deliberate mismatches (stale config, wrong date key, stale scope) against real
  production files copied to a scratch location -- all 3 correctly refused to score
  (`ForwardTestConsistencyError`); the real, current log passes cleanly. **First scoreable target
  month is 2026-08, safe to score only from 2026-09-30** (per the project's own 30-day leakage-guard
  margin, re-used here for scoring, not just backtesting -- stricter than the old script's
  plain-calendar rule, which would have already called 2026-08 "complete" today). No model/policy
  choice newly decided; the item-level Top-down approach it builds on remains, per the existing
  Modeler-tasks-1-3 log entry above, directionally favoured but NOT statistically significant over
  Direct (t=-1.23) -- flagged again here for the human's awareness since this log is the first
  artifact that will actually get scored against it.
- **Unresolved / queued for human decision, consolidated across all three tasks**: (1) which
  cross-division figure/method (₿85.5M Method A vs. ₿2.96M Method B) and which of the three
  presented options should feed Phase 4 planning; (2) whether PEM101 physically shares stock with
  PCE101/PPD101/PPS/PTS/PSS -- needs IT/ERP, Finance, and Warehouse/Operations, not resolvable from
  this database; (3) which per-class treatment applies to each of the 16 no-history/no-sale items,
  and business confirmation for the 4 that cannot be classified cleanly; (4) meaning of several
  `Cube_CES.Status`/`cube_inventory_tran.transtype`/warehouse-code values surfaced by Task 2, not
  previously documented at this granularity -- needs CRM/ERP, sales operations, and the warehouse
  team respectively; (5) nothing queued from Task 3 (a build task), but its dependence on a
  not-yet-statistically-confirmed Top-down choice is flagged for awareness, not re-decided here.

**Phase B closeout: decisions recorded, tests written, end-to-end pipeline built — DONE
(2026-09-04).** Single agent, per `AGENTS.md` ("Writing tests and the pipeline uses a single
agent, because it needs the whole codebase in view to place tests and wire a run order
consistently, not a chunk of it in isolation"). No new investigation performed — this task
closes Phase B by recording the decisions already evidenced above (see the four new Locked
Decisions: cross-division scope, the 6 excluded items, the 10 placeholder items, and the final
Top-down combination method) into `config/config.yaml`, then writes the tests `CONVENTIONS.md`
has required since the start, and builds `src/run_pipeline.py`.

- **Tests (`tests/`, pytest)**: 31 tests across three files — `test_data_invariants.py` (9,
  `src/load_data_full.py`'s `validate_raw`/`aggregate_monthly`: negative qty/sale rejected,
  out-of-range/anomalous dates rejected, monthly totals reconcile exactly to the daily source
  under both date keys, item counts stay consistent before/after processing including a
  zero-history item), `test_model_invariants.py` (10, `src/models.py`/
  `src/item_level_reconciliation.py`: no base-model or Combination forecast is ever negative
  including all-zero/mostly-zero edge cases, Combination equals the exact arithmetic mean of
  the six adopted base models, Top-down item forecasts sum EXACTLY to their Type's forecast,
  a zero-history Type does not produce NaN), `test_guards.py` (12, `src/leakage_guard.py`/
  `src/score_forward_test_v2.verify_consistency`: the leakage guard raises on an insufficient
  margin and on an exact-one-day-short boundary, passes on an exact-boundary and generous
  margin, and raises loudly on a missing config section; the forward-test consistency check
  raises on a config-hash, series-key, item-approach, or scope mismatch, and passes when
  everything matches the current state). **All 31 pass; none required a fix to the underlying
  code** — every invariant the tests check was already correctly enforced by the code written
  during Phase B, so this task only added the tests, it did not find or fix a bug. Uses small
  synthetic DataFrames/arrays, not committed output files (CONVENTIONS.md: never commit
  generated output; a fresh clone has none) or a live database connection, so the suite is
  deterministic and runs in under 4 seconds without credentials. `pytest==9.1.1` pinned in
  `requirements.txt` (CONVENTIONS.md: pin library versions).
- **Pipeline (`src/run_pipeline.py`)**: runs six stages in order, each an existing,
  already-tested script from `src/` run as a subprocess of the same interpreter (so a stage
  failure raises loudly with the full stdout/stderr attached, never silently continues) —
  `load_data_full.py` (pull + validate + aggregate to monthly, both date keys) ->
  `aggregate_levels.py` (Category/Type/Item level stats) -> `item_level_reconciliation.py`
  (Direct/Top-down/Reconciled item-level forecasts) -> `backtest_rekeyed.py` (rolling-origin +
  train/val/test backtest, per the evaluation policy above) -> `forward_test_v2.py` (the
  production forward-test log, Top-down combination) -> `score_forward_test_v2.py` (scores
  whatever target months are safe to score). Every parameter comes from `config/config.yaml`
  via the stage scripts themselves; `run_pipeline.py` only sequences them. Every run appends
  one row to `output/summary/pipeline_run_log.csv` (config hash, the frozen
  `snapshot_pull_date`, row counts at every stage's key outputs, per-stage duration) and
  overwrites `output/summary/pipeline_run_log_latest.json` with the full detail of that run,
  plus `output/summary/pipeline_run_manifest.csv` listing every output file the run produced.
  Two full runs on 2026-09-04 (14:42:47 and 14:51:11, ~9 minutes apart, before and after the
  script reorganisation below) both completed in 25-35 seconds with identical
  `config_hash=5be9f3abfc9d` and identical row counts at every stage.
- **Reproducibility check (2026-09-04, per this task's instruction — compared against
  STATUS.md's own recorded figures, not adjusted to force a match either way)**:
  - **Raw pull row count matches exactly.** The pipeline's fresh pull under the standard
    filter (division=PEM101, revenue_type=Omni Channel, status Actual/MPS, createDate>=
    2024-01-01) returned **27,665 rows**, identical to the "27,665 modelling-scope rows"
    figure the same-day (2026-09-04) `datecol_validator_investigation.py` pull independently
    reported (see that dated log entry above) — an exact match between two independent pulls
    made hours apart the same day, both against a live, still-growing table.
  - **The 16-item no-history/no-sale classification reproduces exactly.** The pipeline's
    `get_category_scope` (`has_any_history`, a broader "any row anywhere in the table"
    check) marks 15 items as having zero history at all, and its narrower
    division/channel/status filter leaves 112 of the remaining 113 with any in-scope
    activity (`EEE-F-FL-5920-353-02600` has table-wide rows but zero under the Omni Channel
    filter, since its only rows are Tendering) — the identical 15/112/1 split Task 2's
    classification work found on 2026-09-04, and the same 6 excluded / 10 placeholder codes
    now recorded in `config.yaml` reproduce exactly against `task2_per_item_classification_
    final.csv`.
  - **Total demand does NOT match exactly, and this is reported rather than adjusted.** The
    pipeline's fresh pull totals **3,384,309 units / ฿697,639,463**, against the **3,348,542
    units / ฿689,580,695** recorded in this file's "Phase 3.1 — Category/Type-level top-down
    expansion" section for the 2026-08-31 pull — a +1.07% / +1.17% difference. **Cause: real
    growth in the live source table over the ~4 days between pulls**, consistent with the
    magnitude of every other pull-to-pull difference already documented in this project (e.g.
    B1's "-2.52% in-window qty this run, vs. -2.17% in Phase A — the small difference is real
    data growth between pulls, stated explicitly, not drift in method"). Not investigated
    further here, per the stopping rule — this is the same, already-understood phenomenon,
    not a new one.
  - Item-level test-score row count (339 = 113 items x 3 approaches) and rolling-origin/
    train-val-test row counts are structurally consistent with the scope sizes recorded
    throughout Phase B; not cited individually since STATUS.md never recorded them as
    standalone headline figures to check against.
- **Script reorganisation (`src/investigations/`)**: of 71 scripts in `src/`, **13 are
  pipeline components** (kept in `src/`: `db.py`, `pricelist_reader.py`, `models.py`,
  `leakage_guard.py`, `load_data_full.py`, `aggregate_levels.py`,
  `item_level_reconciliation.py`, `backtest_rekeyed.py`, `forward_test.py` [still imported
  for `config_version()`], `forward_test_common.py`, `forward_test_v2.py`,
  `score_forward_test_v2.py`, `run_pipeline.py`) and **58 were one-time investigations**,
  moved to `src/investigations/` with a README mapping each to what it examined and which
  STATUS.md entry it supports (`src/investigations/README.md`). Nothing deleted. Moving
  changed each moved script's `PROJECT_ROOT` (now three directory levels up, not two) and
  `sys.path.insert(...)` (now pointing at `src/`, so sibling imports like `from db import
  run_query` still resolve) — mechanical fixes only, no logic changed. **Verified, not
  assumed**: every moved script still imports cleanly from its new location, and a sample
  script (`granularity_test.py`) was executed directly from `src/investigations/` after the
  move and completed successfully, confirming the path fixes work end to end, not just at
  import time.

**Phase C step 1 — data quality for PEM102, PEM103, PEM104, PEM107, CI101 — DONE (2026-09-04).**
Five parallel Validators (one per division) plus a Synthesizer, per `AGENTS.md`'s Phase C
pattern (data-quality checks are independent of each other and identical in kind). Each Validator
re-ran, on its own division, every check PEM101 went through before forecasting began: filter
definition, usable date range, name/code collisions, duplicates/split lots, pricelist agreement,
items without history, Cube_CES cross-check, and demand profile — no PEM101 finding was assumed
to carry over. Reports: `output/summary/phaseC_PEM102_report.md`, `phaseC_PEM103_report.md`,
`phaseC_PEM104_report.md`, `phaseC_PEM107_report.md`, `phaseC_CI101_report.md` (each with its own
supporting CSVs and script under `src/investigations/phaseC_validator_*.py`), merged in
`output/summary/phaseC_synthesis_report.md`. **No config or pipeline code was changed by this
step** — every filter/scope recommendation below is a Validator/Synthesizer recommendation, not
an applied decision.

- **Headline: none of the five divisions is ready to forecast unchanged.** Readiness verdicts:
  PEM102 "ready after specific fixes", PEM103 "ready after specific fixes", PEM107 "ready after
  specific fixes", CI101 "ready after specific fixes", **PEM104 "not ready" (blocked)**.
- **PEM104 — BLOCKED, high confidence.** Only 5 of its 12 pricelist items have any sales history
  at all: **12 transactions total across 17 calendar months**, every nonzero month exactly 1 unit
  per item. Too little to fit MA12 (needs 12 non-zero months; no item has that) or run this
  project's train/val/test or 7-origin rolling-origin evaluation at any aggregation level.
  Blocking question for the business, not resolvable from this data: is 12 transactions genuinely
  the whole picture, or does PEM104 volume flow through an uncaptured division/channel?
- **The single biggest cross-division finding: a PEM102 ↔ PEM107 legacy division-tag pattern,
  found independently by the two Validators, moderate-to-high confidence in the pattern's
  existence, cause unresolved.** PEM102's real 2024 Omni-Channel activity (137 rows, ₿42.6M) sits
  under `division='PEM107-OLD'`, not `division='PEM102'` (nearly empty for 2024); `division=
  'PEM102-OLD'` returns zero rows for PEM102's codes. PEM107's real 2024-through-October activity
  sits under `division='PEM102-OLD'`; `division='PEM107-OLD'` returns zero rows for PEM107's
  codes. Both tags cross over cleanly in Nov-Dec 2024, 90 of PEM107's 136 codes appear under both
  tags, and a coincident `productTypeName` wording-convention change accompanies the transition.
  **Both figures were independently re-verified against the underlying CSVs in synthesis and
  match exactly.** This is consistent with a single company-wide division-code reorganization
  around November-December 2024 that reassigned these two divisions' numeric tags — but this is
  an inference from a well-evidenced pattern, not provable from read-only data (no audit/change
  log exists, same class of limitation as the earlier `forecast_date`-revision question).
  **Unresolved, flagged for IT/business, not guessed at.** Practical consequence, also unresolved:
  whether to use the combined filter `division IN ('PEM102','PEM107-OLD')` for PEM102 (usable-from
  moves from January 2025 to January 2024, a full year more history) and `division IN ('PEM107',
  'PEM102-OLD')` for PEM107 (usable-from moves from ~8 months to 32 months, and the demand
  classification mix changes materially — PEM107-only: Smooth 1/Erratic 0 of 103 active vs.
  combined: Smooth 12/Erratic 4 of 112 active).
- **CI101 ↔ PEM101 overlap — a separate, unrelated finding, high confidence.** 37.2% of the
  combined CI101+PEM101 same-channel (Omni Channel) value for CI101's 13 item codes is recorded
  under `division='PEM101'`, not `CI101` — an ongoing, current-period split of real demand across
  two live division tags, not a rename artifact (no `CI101-OLD` tag exists). Contrast: PEM101's
  own comparable cross-division exclusion (Method B, same-channel) is 0.42% (Locked Decisions
  above) — CI101's 37.2% is nearly two orders of magnitude larger as a proportion and cannot
  simply inherit PEM101's "small enough to document" decision without re-examining the magnitude
  specifically for CI101.
- **PEM103 — the Omni Channel filter captures only 33.3% of value.** Of ₿1,385.9M found across
  PEM103's 87 item codes, 65.5% is Tendering-channel (spread across PEM103/PPS/PTS divisions) —
  for PEM101 the same "Omni Channel only" convention excluded just 0.42% of value; for PEM103 it
  excludes the majority of the business. A genuine scope question (utilities commonly tender for
  transformers, unlike PEM101's hardware), not a data defect — needs an explicit business
  decision. PEM103's data mechanics are otherwise the cleanest of the five: 0 duplicate groups
  (vs. PEM101's 44), 0 pricelist category/type mismatches (vs. PEM101's Surge Arrester
  disagreement), 98.71% Cube_CES row match. Its demand profile is starkly different from PEM101's
  though: 0% Smooth or Erratic among 50 active items (mean ADI 12.5, vs. PEM101's pilot mix of
  12.1%/17.2% Smooth/Erratic) — flagged as a "may not transfer without re-validation" candidate
  for the Top-down combination method, moderate confidence, not yet backtested.
- **PEM102 and CI101 — thinner-history caution, no evidenced structural blocker.** Both are small
  (13-16 and 12-13 active items), 0% Smooth demand profile, but Combination forecasting was
  explicitly designed to be robust on sparse data and PEM101's own method-selection evidence
  wasn't specific to PEM101's mix — reported as an untested caution (low-to-moderate confidence),
  not a verdict; no Modeler has backtested any of the five divisions yet.
- **Cube_CES agreement rates across the table are NOT apples-to-apples, high confidence this is
  a methodology inconsistency, not a data-quality ranking.** PEM101's 99.79%/99.95% and PEM103's
  98.71% were computed by fully tracing every mismatch; CI101's 97.27% (330 keys) explicitly did
  not individually trace its mismatches; PEM104's "100%" is n=12, explicitly flagged by its own
  Validator as far weaker evidence than PEM101's ~9,000-row figure; PEM107's 99.48%/99.38% was
  computed only under the `PEM107`-only scope, not the recommended combined scope. All five sit in
  the same 95-100% band PEM101 established, but the table should not be read as a precise
  cross-division ranking.
- **No genuine factual contradiction found between any two of the five division reports** — each
  covers a disjoint item-code population. The PEM102/PEM107 pattern above is a structural echo
  (mirror-image legacy-tag evidence), not two Validators disagreeing about the same rows.
- **Pricelist data-quality notes, not investigated further per the stopping rule**: a within-sheet
  pricelist duplicate (`DS-F-99-0308`, CI101 sheet, same code/category/type but a different
  Description — same/PEA-spec vs. private-spec variant — this also explains the project's
  existing 446-rows-vs-445-codes note in Section 1); PEM107 carries 4 likely placeholder ("xxx")
  pricelist codes and 2 trailing-period near-duplicates; PEM103 has one near-duplicate code
  (`TF-F-99-2107221B1` / `TF-F-99-2107221B1.`); PEM102 has 3 items carrying an unrelated
  "Instrument Transformer" category on some rows.
- **Full cross-division comparison table, every cell cited to its source report/CSV, in
  `output/summary/phaseC_synthesis_report.md` §1** — filter to use, usable-from date, collision
  count/value, duplicate value, pricelist mismatch count, items without history, Cube_CES
  agreement, demand-profile summary, and readiness verdict, for all five divisions plus a PEM101
  reference column.
- **What Phase C step 1 could not resolve** (carried to Open Questions below): the PEM102/PEM107
  tag-rename mechanism; whether to combine the legacy tags into PEM102's and PEM107's filters;
  CI101's cross-division scope decision; PEM103's Tendering-channel scope decision; PEM104's
  volume question; per-division no-history-item classification (exclude vs. placeholder, PEM101's
  Phase B precedent not yet applied to any of the five); the pricelist near-duplicate/placeholder
  codes noted above; and — the biggest remaining step — no Modeler has yet backtested any of the
  five divisions, so every transferability judgment above is based on data-quality/demand-shape
  evidence only, not measured model performance.

**Phase C sheet-to-division mapping (Explorer) — DONE (2026-09-04).** Fresh, single-method,
Omni-Channel-scoped query across all 445 codes (no reuse of the five Validators' channel-blind
figures). Full detail in `output/summary/phaseC_sheetmap_report.md`. PEM101 (98.80%), PEM103
(97.06%) and PEM104 (100.00%, n=12) map cleanly (≥95% threshold) from sheet to same-named
division; **PEM102 (72.25%), PEM107 (52.63%) and CI101 (62.52%) do not** — the database's
`division` column, not the sheet name, would be needed as a grouping key under a
division-filtered design. This finding is what directly motivated the division source-of-truth
correction below: rather than adding "use `division`, not sheet, for these three" as another
special case, the pricelist-is-authoritative principle removes the need to choose a grouping key
from the database at all.

**Division source-of-truth correction and full-scope re-validation — DONE (2026-09-04).** The
`-OLD`-suffix exclusion decision (recorded above the same day) is reversed — see Locked
Decisions, "Division source-of-truth correction," for the reasoning. This entry records the
re-validation run on the corrected (no-`division`-filter) basis, across all 445 visible-pricelist
codes, per the six checks specified for this task. Script:
`src/investigations/phaseC_full_scope_revalidation.py`. Full detail, every figure cited to its
CSV: `output/summary/phaseC_revalidation_report.md`.

- **Sheet uniqueness — RECONFIRMED, high confidence.** No item code appears on more than one
  visible sheet (445 distinct codes; the script raises an error and stops if any code did — none
  did).
- **Totals per division, before (division_db_raw == home division only) vs. after (no division
  filter) — high confidence, directly queried, no date filter applied (full history).** Value
  shifts materially for **CI101 (+59.94%, ₿104.1M→₿166.5M)**, **PEM102 (+38.40%,
  ₿116.3M→₿161.0M)**, and **PEM107 (+90.01%, ₿218.0M→₿414.2M)** — PEM107 very nearly doubles.
  PEM101 (+1.22%) and PEM103 (+3.03%) shift only slightly (neither was part of the `-OLD` mirror
  pattern). PEM104 is unchanged (0.00%) — none of its 12 transactions carry a non-home division
  tag. Full table: `phaseC_revalidation_02_totals_before_after_per_division.csv`.
- **Double-counting between `-OLD`-tagged and normally-tagged rows — the highest-risk check,
  NEGATIVE FINDING, high confidence.** 11 `(contractid, itemcode)` candidate pairs found with
  activity under both an `-OLD` tag and a normal tag (all PEM102↔PEM107-OLD or
  PEM107↔PEM102-OLD, consistent with the known mirror pattern). Using this project's established
  split-lot key (exact match on qty, sale AND forecast_date = confirmed duplicate; any difference
  = distinct instalment), **0 of the 11 are confirmed duplicates** — every pair differs on at
  least one field, most often `forecast_date` (consistent with genuine multi-tranche orders
  entered under different tags at different times, the same phenomenon already documented for the
  tag transition itself). **No double-counting was found.** This is method-bound (it only tests
  the exact-match signal already established as this project's duplicate key; see
  `phaseC_revalidation_report.md` §2 for the stated limitation), so it is reported as a strong
  negative finding, not an absolute guarantee. Full detail:
  `phaseC_revalidation_03_old_tag_candidates.csv`.
- **Cube_CES reconciliation per division, re-run on the new basis — high confidence, one
  consistent method across all six divisions.** All six divisions sit in a **98.57%-100.00%**
  band: CI101 98.57%, PEM101 99.63%, PEM102 98.72%, PEM103 98.76%, PEM104 100.00% (n=12, low
  weight), PEM107 99.26%. PEM101's 99.63% here differs slightly from the 99.79% recorded
  elsewhere in this file — expected pull-to-pull drift on a live, growing table, not a
  discrepancy in method. Full table: `phaseC_revalidation_04_cube_ces_reconciliation_per_division.csv`.
- **Usable date range per division, re-derived — high confidence, confirms the pre-stated
  expectation.** **PEM102 and PEM107 regain their full 2024 history**: PEM102's earliest usable
  `createDate` moves from ~January 2025 to **2024-01-24**; PEM107's moves from ~January 2025 to
  **2024-01-03** — each division's real 2024 activity, previously sitting only under the other's
  `-OLD` tag, is now counted under its own pricelist division. Full table:
  `phaseC_revalidation_05_usable_date_range_per_division.csv`.
- **No-history recount — 105 of 445 (23.6%), UNCHANGED from the `-OLD`-excluded basis, high
  confidence.** Expected: removing the division filter only adds rows for codes that already have
  *some* `cube_Sale_APD` history under a different tag; it adds nothing for a code with zero rows
  in that table under any division. **Reconciled against the existing 128-item-scope config
  lists**: all 6 `excluded_item_codes` and all 10 `placeholder_item_codes` are among the 105 —
  consistent, **0 genuine conflicts** (double-checked directly against
  `task2_per_item_classification_final.csv`: every placeholder item's own
  `has_any_row_cube_Sale_APD_nofilter` was already `False`, so their absence here confirms rather
  than contradicts their existing classification). **89 of the 105 are NOT YET covered by either
  list** (by sheet: PEM103 37, PEM107 24, PEM101-non-Fuse/Surge 11, PEM102 10, PEM104 7, CI101 0)
  — genuinely new information (the existing lists only ever covered the 128-item PEM101 pilot
  scope). **Classifying these 89 (exclude/placeholder/other) is NOT done here** — an
  Orchestrator/business decision needing multi-table evidence this check did not gather, per
  `AGENTS.md`'s Explorer/Validator boundary; carried to Open Questions below. One consolidated
  list for all 445 codes: `phaseC_revalidation_06_consolidated_item_status_445.csv`.
- **What this does NOT re-derive**: the broader Phase C step 1 readiness verdicts (category/type
  name collisions, pricelist mismatches, ADI/CV² demand classification, readiness wording) still
  reflect the division-filtered basis and are **not** re-run by this entry — only the six checks
  this task specified. Re-deriving full readiness per division against the new basis is separate,
  not-yet-done work.

**Phase C step 1 REVISED — full readiness re-derivation for PEM102, PEM107, CI101 — DONE
(2026-09-07).** Three parallel Validators (per `AGENTS.md`) re-ran every Phase C step 1 check for
the three divisions whose value changed materially (38-90%) once the division filter was removed;
PEM101/PEM103/PEM104 were not re-run (changed <3%). A Synthesizer then merged the three reports
with the unchanged PEM101/PEM103/PEM104 findings and the 445-code aggregate re-validation. Full
detail in `output/summary/phaseC_step1revised_PEM102_report.md`, `..._PEM107_report.md`,
`..._CI101_report.md`, `phaseC_89items_characterization_report.md`, and the merged
`phaseC_step1revised_synthesis_report.md` (+ `phaseC_step1revised_item_status_445.csv`); scripts
under `src/investigations/phaseC_step1revised_validator_*.py` and
`phaseC_89items_characterization.py`.

- **Consolidated readiness table, all six divisions, same basis — replaces the step 1 table.**
  PEM101 (Proven/locked), PEM103 ("ready after specific fixes"), PEM104 ("not ready," blocked)
  carry forward UNCHANGED, not re-examined this round. PEM102, PEM107, CI101 re-derived:
  - **CI101: UPGRADED, "ready after specific fixes" → "ready as-is."** High confidence — the
    Validator's own stated reasoning: the original's one consequential blocker (the cross-division
    scope decision) is resolved automatically by the project-wide correction, not by new
    data-cleaning work. Usable-from date unchanged (2024-01-01, no filtered-vs-unfiltered gap
    existed for CI101); duplicates 2 split-lot groups, 0 unexplained (up from 1 group, the extra
    one only visible once `PEM101`-tagged rows are included); Cube_CES 98.71% (690/699, up from
    97.27%, and this round individually traced all 9 mismatches, closing the original's stated
    "not traced" gap); all 13 items now active (`DS-F-99-0320` resolves from NoSale to
    Intermittent); demand classification materially unchanged (0% Smooth, still no evidenced
    structural blocker to Top-down transfer). **New finding, flagged not resolved**: a minority
    share of CI101 codes' `PEM101`-tagged rows carry a category/type label matching neither the
    pricelist nor that code's own `CI101`-tagged rows (e.g. `DS-F-99-0107`) — for IT/business, not
    investigated further here.
  - **PEM102 and PEM107: verdict WORDING unchanged ("ready after specific fixes" both), but the
    REASONS narrowed materially — high confidence, checked per-Validator, not assumed.** For both,
    the single biggest original open item (whether to combine the `-OLD` tag) is now moot, since
    the corrected query pattern includes both tags by construction. PEM102 gains January 2024
    (usable-from 2024-01-24, was ~Jan 2025 filtered); PEM107 gains January 2024 (usable-from
    2024-01-03, was ~Jan 2025 filtered/~8 months). Cube_CES: PEM102 98.72% (exact match to the
    445-code aggregate revalidation's independent figure — a strong cross-check), PEM107 99.36%
    (consistent with the 98.5-100% band this project has established throughout). Demand
    classification for both now matches what each original report's own "combined-filter"
    supplementary view had already found (PEM102: 0/4/8/4 of 16 active; PEM107: 12/6/69/25 of 112
    active) — **confirming those original combined-filter figures, not stale ones, were already
    the right answer**, and the previously-flagged "conservative PEM107-only fallback"
    classification (1/0/71/31) is now conclusively the wrong scope to have used. Both divisions'
    remaining open items are unchanged from step 1 and were never about the division filter:
    PEM102's voltage-tier naming disagreement (24kV/36kV pricelist vs. 22kV/33kV DB); PEM107's 4
    "xxx"-placeholder and 2 near-duplicate pricelist codes, and its 36 unexplained-duplicate groups
    (₿3,006,792, 0.72% of scope — identical count/value to the original's own combined-filter
    finding, kept in full per established precedent, not newly discovered).
  - **Correction surfaced, not a new finding**: PEM102's original report (`phaseC_PEM102_report.md`)
    characterised contract `CTR-2024-03290` as "very likely 1 real transaction, 3 duplicate rows."
    This round's direct re-query found 3 DIFFERENT `forecast_date` values across those rows — under
    this project's own established split-lot test, a genuine 3-tranche split lot, not a duplicate.
    **The original characterisation is superseded** (per `AGENTS.md` Rule 4, reported explicitly,
    not silently overwritten).
  - **A pull-to-pull discrepancy, not resolved**: CI101's original report stated all 9 of its
    category names were shared with another division ("9/9"); this round's fresh query (3 days
    later) found only 6 of 9. Most likely explanation stated by the Validator: ordinary growth on a
    live table — not confirmed, since no snapshot of the original pull date was kept.
- **Consolidated item status, all 445 codes** (`phaseC_step1revised_item_status_445.csv`): **335
  forecast**, **82 placeholder — pending method**, **12 excluded — PEM104 division-level
  (data-volume) exclusion**, **10 placeholder — method already assigned** (existing
  `placeholder_item_codes`), **6 excluded — listed but never sold** (existing
  `excluded_item_codes`). The existing 16 config-list codes reconcile with 0 genuine conflicts.
  **PEM104 overlap flagged as an UNRESOLVED, genuinely two-sided question, not resolved by this
  report, per instruction**: 7 of the 89 no-history codes sit on the PEM104 sheet, which is already
  excluded from forecasting entirely for an unrelated data-volume reason. Whether that
  division-level exclusion already covers these 7 items' placeholder question, or whether they
  still separately need the same exclude/placeholder-mechanism decision as the other 82 (in case
  PEM104's volume question is ever revisited), is left to a human — both readings are stated in
  full in the synthesis report.
- **89-item no-history characterization** (`phaseC_89items_characterization_report.md`/`.csv`,
  done by the CI101 Validator, confirmed population = 89): grouped by sibling/concentration
  pattern — **balanced Type 57**, **dominated Type 22** (≥60% share or a single sibling, the same
  shape as the Fuse Cutout Type's focus item), **no siblings with history 6**, **Type-undefined 4**
  (blank pricelist field, all PEM104). Grouped by trace evidence — **Cube_CES Actual/Backlog trace
  29**, **quotation-only trace 23**, **weak pipeline/inventory-only trace 12**, **no trace anywhere
  25**. Also found: 4 items are literal "xxx" placeholder pricelist codes (matching PEM107's
  already-known placeholder-code note); **9 items have a `Cube_CES` Omni-Channel Actual/Backlog row
  with NO `cube_Sale_APD` counterpart** — an unresolved cross-table gap, not folded into any
  classification; PEM104's 7 no-history codes cannot be checked against a hidden pricelist version
  (no hidden PEM104 sheet exists). **No placeholder mechanism was chosen** — that decision is
  Phase C Step 2 task list item 2 (Current Status Summary above), deferred until now-available
  evidence lets it be made on evidence rather than assumed.
- **Which divisions may not transfer Top-down combination — restated on the new basis, still
  entirely untested by any Modeler backtest.** PEM104 still does not transfer (high confidence,
  volume problem, unaffected by the division correction). PEM103 still "may not transfer without
  re-validation" (moderate confidence, unaffected — its issue is a Tendering-channel scope
  question, not a division-tag one). **PEM107's caution changes in KIND, not degree**: the original
  risk was specifically that an uncorrected filter would misclassify PEM107's demand mix (Smooth
  1→12, Erratic 0→4 under the old PEM107-only-vs-combined comparison) — that risk no longer exists
  by construction, but PEM107's mix still differs materially from PEM101's pilot mix (far more
  Intermittent-skewed, materially fewer Erratic), so the caution persists on demand-mix grounds
  alone, not a filter-correctness risk. PEM102 and CI101 remain "thinner-history caution, no
  evidenced structural blocker" (low-to-moderate confidence, unchanged in substance) — CI101's
  sharply improved data-quality readiness verdict this round is explicitly a SEPARATE axis from
  its (unchanged) demand-profile transferability caution; the two must not be conflated.
- **Confidence and what remains unresolved**: every figure above is cited to its Validator/
  Synthesizer report and CSV. Explicitly unresolved, carried to Open Questions below: the PEM104
  overlap; the exclude/placeholder-mechanism decision for the 82 non-PEM104 no-history codes; the
  9-item Cube_CES cross-table gap; whether PEM101's own production pipeline (`src/load_data_full.py`
  etc.) has actually been updated to drop its `division='PEM101'` filter (not checked by this
  round — the aggregate revalidation shows PEM101's own value already shifts +1.22% under the
  corrected basis, so this is not purely a PEM102/PEM107/CI101 concern); PEM103's and PEM104's
  specific readiness items were not re-examined and their step 1 conclusions are not re-confirmed
  by this entry; the PEM102/PEM107 legacy-tag mechanism itself remains an inference, not a
  confirmed fact; no Modeler has backtested any of the six divisions under either basis. **This
  task made no changes to `config/config.yaml` or any pipeline code, and nothing from this task was
  committed or pushed**, per instruction.

**Phase C step 2 — forecast all in-scope items, value-vs-quantity test, transferability — DONE
(2026-09-07).** Single Modeler (per `AGENTS.md`: forecasting all divisions is one continuous run
needing identical settings throughout, not split). Full detail, every figure cited:
`output/summary/phaseC_step2_report.md`. New scripts: `src/load_data_all_divisions.py`,
`src/backtest_all_divisions.py`, `src/transferability_all_divisions.py`,
`src/forward_test_all_divisions.py`, `src/charts_all_divisions.py` — additive, alongside (not
replacing) the existing 128-item PEM101-sheet Fuse+Surge pipeline (`load_data_full.py` etc.),
which STATUS.md still records as "Proven, method locked" for its own scope.

- **Part 0 preconditions — confirmed clean, no fix needed, high confidence.** Grepped every
  active pipeline script (not the archived `src/investigations/*.py` one-off scripts) for a
  `division = '...'` filter: none found. `load_data_full.py`, `src/investigations/load_data.py`
  (the file this project calls `src/load_data.py`), and `score_forward_test_v2.py` all confirmed
  filter-free (the 2026-09-04 fix is intact); `aggregate_levels.py`, `item_level_reconciliation.py`,
  `backtest_rekeyed.py`, `forward_test_v2.py`, `forward_test_common.py`, `leakage_guard.py`,
  `models.py`, `run_pipeline.py` don't reference `division` at all. 40/40 tests pass, before and
  after. **PEM101's previously-flagged 1.22% aggregate shift is explained, not a missed filter**:
  that figure covers all 171 PEM101-sheet codes; `load_data_full.py`'s own 128-item Fuse+Surge
  Category scope, freshly re-run, shows a consistent, smaller 0.29% (81 of 27,746 rows) — same
  direction, smaller/different scope, not a contradiction.
  - **The 7-item PEM104 overlap is now decided, not just flagged**: treated as excluded under
    PEM104's whole-division exclusion (data volume, unrelated to division tagging) — a
    division-level exclusion subsumes the item-level placeholder question for these 7. This
    ratifies "Reading A" from the 2026-09-07 Synthesizer's own two-sided framing (§8 below is
    updated accordingly); the 89-item placeholder-pending population's actionable count is now
    **82**, not 89.
  - **The 9-item `Cube_CES`-trace-only codes — explained, high confidence, single check per
    instruction.** All 19 matching `Cube_CES` rows across the 9 codes are `Status='Actual'`
    (delivered, NOT Backlog/pending), dated entirely in 2023 (`CtrDate` 2023-03-04 to 2023-10-25;
    `ActualDelDate` 2023-03-20 to 2023-11-15) — before `cube_Sale_APD`'s 2024-01-01 modelling
    window and before several divisions' own structurally-absent-before-2024 boundary. **A
    table-coverage-window gap, not a data-integrity problem.**
- **Part 1 — 335 forecast-status items, 5 of 6 divisions (PEM104 contributes zero — all 12
  excluded), forecast on the corrected basis.** Top-down combination (division-qualified Type-level
  Combination, allocated by historical qty share), rolling-origin primary, forecast_date-keyed,
  frozen snapshot, leakage guard enforced (excluded 2026-08 from the common window at LOAD time,
  not just at scoring time — 7-day margin, needed 30). Common window: 31 months, 2024-01 to
  2026-07 — the same window every other Phase B/C backtest uses. Per-division Type-level
  Combination rolling-origin MAE/MASE: **CI101 13.01/0.74, PEM101 2895.82/1.29, PEM102 1.98/1.17,
  PEM103 36.96/2.16, PEM107 69.18/0.72.** All Bias small/negative (under-forecasting, the
  established structural reason). **No stable rolling-origin winner across 40 division-qualified
  Types (mean winner-stability 34.3%, Combination itself the outright winner in only 3 of 40)** —
  reproduces Phase 3.1's original finding at 4x the scope, reinforcing Combination as the robust
  choice. **Focus codes (Top-down, adopted method)**: `EEE-F-FC-1040010002` MAE 1016.37/MASE 2.08;
  `HS-F-99-02110` MAE 497.28/MASE 8.52 (small-scale outlier, already-documented Lumpy
  classification); `HS-F-99-0213` MAE 228.50/MASE 2.62 — all three under-forecast.
  - **Forward-test log extended to all 335 items**: `output/summary/
    forward_test_log_all_divisions.csv` (2,340 rows), schema extended with one `division` column
    (necessary — Type/Category names collide across divisions). **128-item version archived, not
    deleted**: `output/summary/archive/forward_test_log_v2_128items_superseded_2026-09-07.csv` (+
    scored/metadata copies) with a README — **a scope-only supersession, date key and method
    unchanged**, unlike the earlier 58-item log's three-way supersession. Confirmed before
    archiving: 0 of 828 rows had a filled `actual_qty`. **No scoring script exists yet for the new
    log** — flagged, not attempted.
- **Part 2 — value-based vs. quantity-based aggregation: no evidence to switch, moderate
  confidence.** Zero-inflation reduction (Category 25.59%, Type 37.18%, down from Item-level
  58.1%) is **identical under both bases by mathematical necessity** (zero qty ⟺ zero sale value
  for the same rows) — this part of the original concern was never really about which unit is
  summed. The validation-to-test gap comparison is **mixed**: 2 of 5 divisions show a smaller gap
  under value aggregation (PEM101, CI101), 3 show a larger one (PEM102, PEM103, PEM107); MASE is
  very similar between bases for every division. **Quantity basis is kept for Top-down
  allocation** — not because value was tested and lost decisively, but because it was tested and
  found no consistent advantage. Note also: the original 128-item PEM101-only finding of
  zero-inflation cut "to 0%" does NOT reproduce exactly at this 335-item, 5-division scope (25.59%/
  37.18%, not 0%) — a genuinely weaker result at the broader scope, reported honestly, not
  papered over.
- **Part 3 — transferability, per division, moderate confidence throughout.** Top-down vs. Direct
  vs. Naive, rolling-origin, all 335 items: **PEM101 holds its Top-down advantage cleanly** (beats
  both). **PEM102, PEM103, PEM107: Top-down beats Naive but its edge over Direct is thin and not
  statistically significant** (\|t\|<0.6 for all three) — the step 1 demand-mix flags for these
  three do not show up here as a measured Top-down failure; evidence suggests Top-down can stay
  the default, though Direct would be an equally defensible, simpler fallback given the thin
  margin. **CI101 is the one division where Top-down falls behind Naive** (+1.6%, small, not
  significant, t=0.12) while still significantly beating Direct (t=-2.12, borderline given n=13
  items) — consistent with Phase C step 1's own "thin-history caution" flag for CI101; evidence
  suggests Direct or Naive may be worth considering ahead of Top-down for CI101 specifically if
  this margin persists, **not implemented, per instruction.**
- **What remains unresolved**: no scoring script for the new forward-test log; the 82 (of 89)
  non-PEM104 no-history items' placeholder mechanism is still not chosen (Phase C Step 2 task
  list item 2, Current Status Summary above); CI101's small-n transferability result should be
  re-checked as more history accumulates; the PEM102/PEM107 legacy-tag mechanism remains an
  inference; `cube_Sale_APD` is a live, growing table, so a re-run will not reproduce these exact
  figures though the qualitative conclusions are expected to be stable.

**PHASE C CLOSED — final transferability table, placeholder rule set, scoring readiness, config
lock-in — DONE (2026-09-07).** Synthesizer then Modeler, same context, one agent (per `AGENTS.md`:
not split). Full detail: `output/summary/phaseC_closure_report.md`.

- **Final transferability table, all six divisions**:

  | Division | Method | Evidence | Confidence |
  |---|---|---|---|
  | PEM101 | Top-down combination | Rolling-origin MAE: Top-down 343.82 < Direct 344.63 < Naive 449.18 — clean advantage over both | High |
  | PEM102 | Top-down combination | Beats Naive (1.16 vs 1.34); thin, non-significant edge over Direct (t=0.238, n=16) | Moderate |
  | PEM103 | Top-down combination | Beats Naive (2.49 vs 2.70); thin, non-significant edge over Direct (t=0.545, n=48); demand entirely Intermittent/Lumpy | Moderate |
  | PEM107 | Top-down combination | Beats Naive (11.57 vs 13.61); thin, non-significant edge over Direct (t=0.118, n=112) | Moderate |
  | CI101 | Top-down combination | **Falls 1.6% behind Naive** (10.27 vs 10.11, not significant, t=0.117, n=13); significantly beats Direct (t=-2.124, borderline, small n) | Moderate-low |
  | PEM104 | Excluded (not forecast) | 12 transactions/17 months, insufficient for any model **[SUPERSEDED — see note below]** | High |

  **[SUPERSEDED reason, not deleted — business-confirmed 2026-09-23 (DATA_MAP.md §7; STATUS.md
  Phase J4 entry; PROJECT_GRAPH.md dead end DE4): PEM104's exclusion reason is "made to order by
  business model, no stock policy applicable," not "insufficient data."** The 12-transactions/
  17-months figure in the row above is real and correctly counted, but "insufficient for any
  model" was a correct SYMPTOM, not the cause — the low, sporadic transaction count is a
  structural consequence of a made-to-order business model, not a data-collection gap. The
  exclusion decision itself (PEM104 excluded from forecasting) is unchanged by this correction.]**

  **The honest position, stated plainly**: Top-down combination beats Naive in **4 of 5
  forecastable divisions** and holds a **thin, non-significant edge over Direct in 3 of 5**
  (PEM102/PEM103/PEM107, all `|t|<0.6`). **Adopted across all five for structural reasons — Type-
  level rolling-origin stability (mean winner-stability only 34.3% across 40 Types) and a single
  consistent method project-wide — not because accuracy differences are decisive.** Only PEM101's
  advantage is clean and unambiguous. **CI101 falls behind Naive by 1.6% (not significant, n=13)
  and stays on Top-down for consistency**, with an explicit `recheck_instruction` recorded in
  `config.yaml` to revisit once its history lengthens.
- **Value-vs-quantity, restated with the Category-level caveat added**: identical zero-inflation
  reduction by mathematical necessity; mixed overfitting-gap results; quantity retained by absence
  of a reason to change. **Caveat recorded explicitly**: summing units across product kinds at
  Category level remains physically meaningless — Top-down allocation itself operates at Type
  level, where products are of one physical kind, so Category figures are for overview only, never
  for allocation. Written into `config.yaml` (`aggregation_value_col`,
  `aggregation_category_level_caveat`).
- **Placeholder rule set applied to the 82 no-history items** (`src/placeholder_assignment.py`,
  `output/summary/phaseC_placeholder_assignment_82items.csv`, written into `config.yaml`
  `placeholder_rule_set` + `placeholder_item_assignments_82`, editable by hand): **Rule A (Type
  mean monthly demand per item, top sibling <40% of Type's history-bearing value) — 50 items;
  Rule B (Type median, top sibling ≥40% — resists being pulled toward the dominant item) — 29
  items; Rule C (flag only, value 0, no number invented, zero siblings with history) — 3 items;
  Rule D annotation (a 2023 `Cube_CES` Actual/Backlog Omni-Channel trace with no `cube_Sale_APD`
  row in any year, layered on A/B/C, not a separate value) — 9 items.** The 40% dominance
  threshold is a **stated assumption carried from instruction, not derived from this data** —
  recorded as such, to be revisited if it produces poor placeholder values in practice.
  **Flag-only items (Rule C), listed explicitly**: `SR-F-99-3381603` and `SR-F-99-3381603-01`
  (PEM102-Version 2, Type "33kV Recloser"), `02-05-R-0001` (PEM102-Version 2, Type "FRTU" — this
  one also carries the Rule D 2023-trace annotation despite having zero siblings, an edge case the
  instruction's wording did not explicitly cover; reported honestly, Rule C's zero/flag stands).
- **Forward-test scoring for the 335-item log**: `src/score_forward_test_all_divisions.py`
  extends `score_forward_test_v2.py`'s consistency check with one added field, `divisions`.
  **Confirmed by direct test**: refuses the archived 128-item log (raises
  `ForwardTestConsistencyError` citing `config_version`, `scope_hash` 128-item-vs-335-item,
  `scope_n_items`, and `divisions` None-vs-5-divisions — no scored output written); accepts the
  current 335-item log cleanly. **First target month: 2026-08** (month-end 2026-08-31).
  **Leakage-guard margin (30 days) clears 2026-09-30** — as of this task's run date (2026-09-07),
  **0 of 6 target months are safe to score yet**, confirmed by direct run, not assumed. Re-running
  after 2026-09-30 will score 2026-08 for the first time.
- **Test added**: `tests/test_score_forward_test_all_divisions.py` (6 tests: passing-metadata
  case; config/scope/approach/division-mismatch refusals; a direct regression test reproducing
  the archived 128-item log's own recorded metadata against the current 335-item scope). **Full
  suite: 46 passed** (was 40 before this task).
- **Config lock-in** (`config/config.yaml`, every entry commented with its reason): per-division
  `division_forecast_method` (method + reason + CI101's `recheck_instruction`);
  `aggregation_value_col`/`aggregation_category_level_caveat`; `placeholder_rule_set`
  (thresholds, rule text, counts); `placeholder_item_assignments_82` (per-item rule/value/flag/
  note). **No pipeline code was modified to read these new keys** — recording the decisions in
  config was this task's scope; wiring them into the loader/forecast scripts is separate,
  not-yet-done work.
- **What remains unresolved**: ~~the item-specific model check for the three focus codes (not yet
  done, see Current Status Summary above)~~ — **DONE 2026-09-08, see the dated log entry below**;
  wiring the new config keys into pipeline code; CI101's small-n transferability result awaiting
  more history; the PEM102/PEM107 legacy-tag mechanism remains an inference; `cube_Sale_APD` is a
  live, growing table, so a re-run will not reproduce these exact figures though the qualitative
  conclusions are expected to be stable.

**Focus-item model selection (EEE-F-FC-1040010002, HS-F-99-02110, HS-F-99-0213) — DONE
(2026-09-08).** Single Modeler (per `AGENTS.md`: three items, same candidate set/evaluation, one
context). Full detail, every figure cited: `output/summary/focus_item_model_selection_report.md`.
New script `src/focus_item_model_selection.py`; `src/models.py` gains `tsb_forecast` (TSB has no
auto-optimized variant in `statsforecast`, so `alpha_d`/`alpha_p` are grid-searched over
`{0.05,0.1,0.2,0.3,0.4}` minimizing in-sample fitted error — a stated assumption, not derived);
charts `src/charts_focus_items.py` → `output/charts/focus_<item>_all_candidates.png` (11-panel
small-multiples, actual vs. each candidate's rolling-origin forecasts).

- **Candidate set — all 11 fit successfully on all three items, at all 7 origins, zero fitting
  failures** (Naive, MA3/6/12, SES, Holt, Croston, SBA, TSB, the adopted six-model Combination
  unchanged, Top-down). Confidence: high, directly confirmed (`focus_items_rolling_origin_all.csv`
  `error` column null throughout).
- **Demand classification, directly confirmed**: `EEE-F-FC-1040010002` = **Erratic** (ADI=1.107,
  CV²=0.718, 9.7% zero months — matches this project's existing classification, NOT Lumpy).
  `HS-F-99-02110` = **Lumpy** (ADI=2.583, CV²=2.510, **61.3% zero months**). `HS-F-99-0213` =
  **Lumpy** (ADI=1.632, CV²=1.410, **38.7% zero months**).
- **Verdict, all three items: keep Top-down combination. No candidate beats it with statistical
  significance on any item** (paired t-test across the 7 origins, same methodology as
  `transferability_all_divisions.py`; best candidate per item has \|t\|<1.3 in every case; the one
  significant result is MA12 being WORSE than Top-down for `EEE-F-FC-1040010002`, t=3.649).
  - **EEE-F-FC-1040010002** (confidence: moderate): TSB has the lowest full-series MAE (580.57 vs.
    Top-down's 605.86, not significant) but Top-down's mean Bias (18.90) is far smaller than
    every other candidate's (60-525) — a genuine advantage on the user's explicit bias criterion
    that a pure-MAE ranking misses. **No candidate is sign-consistent across origins, including
    Top-down** (3 positive/4 negative) — this item has no steadily-biased candidate at all, and
    the rolling-origin winner is a DIFFERENT model at every one of the 7 origins.
  - **HS-F-99-02110** (confidence: moderate): Naive has the best MAE (121.21) and is
    sign-consistent (always under-forecasting, one of only 3 sign-consistent candidates), but the
    margin over Top-down is not significant (t=-1.203) and the whole 11-candidate set is
    clustered within a 10% MAE band.
  - **HS-F-99-0213** (confidence: high — the clearest case): **Top-down is already the outright
    rolling-origin MAE winner** (112.26) with a smaller val-test gap than Combination's own
    (104.5% vs. 116.8%). No candidate offers a better fit on either criterion.
- **EEE-F-FC-1040010002 pre-recovery supplementary split (confidence: high for what it directly
  shows, n=1 split not 7 origins)**: standard rolling-origin cannot isolate the pre-recovery
  period at all (every origin's test window already reaches into the 2025-04-onward recovery, by
  construction — `MIN_TRAIN_MONTHS=13`). A separate single split (train 2024-01/09, test
  2024-10/2025-03, ending at the confirmed zero-qty trough) **inverts the full-series ranking
  entirely**: Naive (MAE 197.67) and SES (209.61) win by a wide margin; TSB — the full-series
  winner — is **7.9x worse** (1531.70) here, and Top-down is **8.9x worse** (1767.02), the
  second-worst of all 11. **The full-series ranking for TSB/MA-family/Combination/Top-down is
  materially inflated by the easy-to-track recovery ramp, not genuine collapse-period skill.**
- **HS-F-99-02110 and HS-F-99-0213 side by side (same Type, "Medium Voltage Surge Arrester")**:
  **Croston/SBA rank 2nd-3rd of 11 for BOTH items — competitive, not the worst**, contradicting
  the aggregate pooled-Intermittent-class finding that Croston/SBA were worst-of-six there
  (confidence: high, directly computed; the two findings are at different scales, a magnitude
  comparison is not directly transferable, but the RELATIVE ranking difference is real and
  evidenced). **"A fitting model for one fits the other" does NOT hold**: Top-down ranks 7th of
  11 for `HS-F-99-02110` but 1st of 11 for `HS-F-99-0213`, despite same Type/division/
  classification — plausibly explained by `02110`'s much higher zero-rate (61.3% vs. 38.7%,
  confidence: moderate, not independently verified further per the stopping rule).
- **What would need recording in config for an item-level override (not created, no item's
  evidence supported one)**: a new per-item key analogous to `placeholder_item_assignments_82`'s
  shape (e.g. `item_forecast_method_override: {ITEMCODE: {method, reason}}`), since
  `division_forecast_method` (Phase C closure) only records method at division level today.
- **What remains unresolved**: why `HS-F-99-02110`/`HS-F-99-0213` diverge so much on best-fitting
  model beyond the plausible zero-rate explanation; the TSB alpha grid is a stated assumption, not
  exhaustively searched; the pre-recovery split's n=1 evidence base is smaller than the primary
  7-origin results; `cube_Sale_APD` is live and growing, so a re-run will not reproduce these exact
  figures though the qualitative conclusions (no significant override for any item) are expected
  to be stable. **No config was written in this task, per instruction. Nothing was committed or
  pushed.**

**Phase D — Phase 4 groundwork, three checks against `Cube_Inventory_Exact` — DONE (2026-09-08).**
Three parallel Explorers (per `AGENTS.md`'s Phase D pattern) plus a Synthesizer. Scope deliberately
narrow, per instruction: `Cube_Inventory_Exact` and the tables it joins to only — no wider database
search, since earlier exhaustive searches already established finished-goods movement history, MOQ
and assembly time do not exist, business-confirmed. Full detail:
`output/summary/phaseD_synthesis_report.md`, `phaseD_check1_report.md`, `phaseD_check2_report.md`,
`phaseD_check3_report.md`; scripts `src/investigations/phaseD_check1_sellable_stock.py`,
`phaseD_check2_stock_value.py`, `phaseD_check3_ci101_stock_location.py`.

- **Check 1 — which warehouse stages hold sellable stock, high confidence, stated plainly.**
  Snapshot: a single frozen batch, **2026-09-06** (96,574 rows table-wide, a ~72-second timestamp
  window). Schema confirmed to have **no sellability/status/stage field at all** (17 columns,
  `INFORMATION_SCHEMA.COLUMNS`) — `available` is a quantity (stock minus reservations), not a
  status. In-scope: 158,130 units across 388 of 445 items (57 absent from the snapshot). Applying
  the prior 2026-09-02 movement-ledger finding (not re-derived here, that ledger has no coverage
  for this scope): `QA`/`FMTS`/`FMTO` = **confirmed NOT sellable, 158 units, 0.10%**. **Confirmed
  sellable: 0 units, 0.00%.** **Undetermined: 157,972 units, 99.90%** — including `FG01` (124,192
  units, 288 items) and `FG21` (24,255 units, 109 items), plausible by topology alone, which is
  explicitly not sufficient evidence per this project's ground rules. Per-division undetermined
  share: 94-100% for PEM101/PEM102/PEM104/CI101/PEM107; **PEM103 is a material, unexplained
  outlier at 46.32%** (driven by a comparatively large share of its small 95-unit total sitting in
  QA/FMTS/FMTO) — reported as an observed pattern, not interpreted, per the Explorer role boundary.
- **Check 2 — value tied up in stock, high confidence on the headline figures.** **Self-caught
  methodology correction before computing anything**: the task's own premise that `cube_Sale_APD.
  cost` is a unit cost is **wrong** — directly disproved (`cost/qty` is exactly constant, 1,547.18,
  across 6 rows of varying qty for one test item; median within-item CV of `cost/qty` is 0.061 at
  project scope, consistent with a per-unit price that drifts, not a stored line total held
  constant). **`cost` is a line total (qty × unit price).** Using it raw as a unit price would have
  overstated stock value by roughly one to two orders of magnitude. Corrected method: unit cost =
  `cost/qty` per row, then the **median over the trailing 12 months** (moderate confidence this is
  more robust than most-recent-transaction — reasoned from this project's documented history of
  outlier rows, not statistically proven for this item set; most-recent gives 5.6% more, THB
  39.50M vs. 37.40M, with the top-10 list stable except one marginal swap). **Total priced stock
  value: THB 37,399,005.48** (all 445 items, all warehouses, no sellability filter — deliberately
  the total-capital-tied-up figure). Top-10 dominated by PEM103 transformers and PEM101 items; two
  items (`FC-A-38-00202`, `HS-F-99-02410`) carry very large months-of-cover (1,630 and 39,060
  months by a plain 31-month historical-mean demand rate, moderate confidence since it is not a
  forecast-model output) against near-zero recent demand. **No-forecast-scope value: THB 226,449.90
  priced + 226 units value-undetermined (0.61% of total)** — stock in placeholder/excluded items
  with no demand basis. **5 items have stock but no cost record at all** (`FC-A-38-00203`,
  `IS-F-99-0365CE1`, `HS-F-99-3121`, `02-05-R-0001`, `TF-F-99-3107223B1`; 226 units) — carried as
  value-undetermined, never assigned 0 or dropped. **Restated explicitly, per instruction: this is
  capital tied up at one point in time, not an annual carrying cost** — no annual rate exists in
  this data; the 15-25% figure elsewhere in this file remains an unverified assumption, not used
  here.
- **Check 3 — CI101/PEM101 stock location, high confidence on the facts, moderate on the reading.**
  **12 of CI101's 13 pricelist codes** have PEM101-tagged Omni-Channel sales (`DS-F-99-0109` is the
  exception, entirely CI101-tagged). Aggregate reproduces the known 37.24% figure closely (37.22%
  here, a 0.02pp drift attributed to ordinary live-data movement, not row-traced). Of the 12: **6
  have zero stock anywhere** (4 fully explained by 100% already-delivered `Actual` history; **2 —
  `DS-F-99-0101`, `DS-F-99-0221` — carry pending `MPS`/backlog demand, ฿360,000 and ฿3,230,000 due
  2026-10-20/2026-12-25, with nothing on hand — a genuine open point, make-to-order timing vs. a
  real supply gap cannot be distinguished from a single-snapshot table**). **6 have nonzero stock,
  all of it sitting exclusively within PEM101's own 6-code warehouse set** (`FG01`, `FG21`, `FMTO`,
  `FMTS`, `W4-1`, `WH21`) — specifically only in `FG01`/`FMTO`/`FMTS`. **But those three codes are
  not distinctively PEM101's**: table-wide they hold stock for 3-4 of the 6 pricelist divisions
  each — so Check 3's own raw "SAME" verdict is downgraded to **`SAME_BUT_UNDETERMINED`**, not left
  as a clean match. Practical conclusion, stated by Check 3 directly: co-location supports
  including these 6 items in Phase E's shared PEM101 planning pool as a defensible reading; it does
  **not** prove a PEM101-exclusive pool, since none exists company-wide on this evidence.
- **Cross-checks between the three checks, directly re-verified by the Synthesizer**: Check 1 and
  Check 3 agree **exactly**, unit-for-unit, on all 6 stocked CI101 items' warehouse/sellability
  determination. Check 1 and Check 2 agree **exactly** on total (158,130 units) and per-division
  stock quantities. **One genuine, unresolved conflict found**: Check 1 describes the snapshot as a
  single frozen 2026-09-06 batch; Check 2 describes the same table as live/continuously updated,
  with timestamps spanning 2026-09-06 and 09-07. **Both positions are reported; neither is
  resolved** — most likely explanation offered (not confirmed) is the table refreshed between the
  two Explorers' queries, but this is not verified.
- **10 assumptions Phase E must record in `config.yaml`, because the data could not answer them**
  (full detail and citations in `phaseD_synthesis_report.md` §5): (1) which warehouse codes count
  as sellable — currently 0.00% confirmed, 99.90% undetermined, Phase E cannot proceed without
  either a business-confirmed mapping or an explicit, named modelling assumption; (2) the annual
  holding-cost carrying rate — no source exists; (3) which unit-cost basis to use going forward
  (median-12mo vs. most-recent, a 5.6% portfolio swing) and what `cost` economically represents
  (landed/standard/material cost — never checked, out of this task's two-table scope); (4) how to
  handle the 5 no-cost-record items; (5) how to treat the 2 CI101 items with pending backlog demand
  and zero stock; (6) whether to pool CI101/PEM101 shared-warehouse stock or keep it separate; (7)
  PEM103's unexplained low-undetermined-share pattern (46.3% vs. 94-100% elsewhere); (8) the
  Check-1-vs-Check-2 snapshot frozen-vs-live conflict; (9) target service level and the stockout-
  cost proxy (already open, Section 8.5, reaffirmed load-bearing for Phase E here); (10) assembly
  time after parts arrive (already open, Section 8.1/8.5, reaffirmed).

**Warehouse/division trailing-digit mapping hypothesis test — DONE (2026-09-09).** Follow-up to
Phase D assumption (1) above (which warehouse codes are sellable/whose are they), run as a single
Explorer, one cross-tabulation examined from six angles in one context (`AGENTS.md` "Single
Explorer" pattern — no agent split). Script: `src/investigations/warehouse_division_mapping_hypothesis.py`.
Full write-up: `output/summary/whmap_report.md`; data: `output/summary/whmap_part1..part6_*`.
User's hypothesis: warehouse codes are separated by division via trailing digits (`FG01`/`FG21`→
PEM101, `FG02`→PEM102, `FG07`→PEM107, generalised to `03`→PEM103, `04`→PEM104). Scope: all 445
pricelist items, all 6 divisions, division sourced from the pricelist (`sheet_to_division`), never
`cube_Sale_APD`'s own `division` column — an earlier pre-2026-09-04-correction file,
`part3_warehouse_division_test.csv`, used the raw DB column and shows up to 17 "divisions" per
warehouse including `-OLD` variants and a non-existent `PEM106`; that file is superseded and was
not reused here. **Scope note**: this pull found **44** distinct warehouse codes in the 445-item
snapshot (matching Phase D Check 1's own count), not the 34 the user's brief referenced (34 is
from the earlier, narrower 128-item pilot-scope investigation) — used 44 throughout, stated
explicitly rather than silently reconciled. Value reuses Check 2's already-corrected unit-cost
methodology (`phaseD_check2_item_stock_value.csv`), not re-derived.
- **Part 1 (cross-tab)**: mean per-division concentration in its single largest warehouse code is
  75.4% of qty / 68.0% of value — but **the table is NOT diagonal**: `FG01` is the single largest
  code for 3 of 6 divisions at once (CI101, PEM101, PEM107), `FMTO`/`FMTS` each hold stock for 4
  divisions. High concentration ≠ exclusivity. Only PEM102/PEM103/PEM104's clean top-1 codes are a
  thin-sample artifact (14/70/2 total units respectively, not a structural signal).
- **Part 2 (per-code dominant division vs. hypothesis)**: of 44 codes, only **3 are literally
  testable** (have both a hypothesis prediction AND current nonzero stock) — **all 3 match**
  (`FG01`, `FG21`, `WH21` → PEM101, dominance ≥60%, a stated judgment threshold). The other 3
  literal predictions (`FG02`→PEM102, `FG03`→PEM103, `WH04`/`P104`→PEM104, `F107`/`WH07`→PEM107)
  are **untestable**, not confirmed or refuted — every one of those codes holds zero current
  stock. **Secondary finding (inferred, LOW-MODERATE confidence, small samples 2-226 units)**: a
  `2X`-family pattern (`FG22/23/24/27`, `WH22/24`) tracks division better than the empty `0X`
  series — one exception found (`FG22`→PEM107, not PEM102).
- **Part 3 (item warehouse spread)**: 73/167 stocked items sit in exactly one code; 64/167 sit in
  several codes within one division's hypothesis-defined set (all 64 are PEM101); **0/167 items
  literally span two divisions' sets** — but this is **not strong confirmation**: PEM102/103/104/
  107's own predicted codes are almost all empty, so the check had almost no chance to find a
  spanning item either way. The cross-check against `phaseC_sheetmap_flagged_multi_division.csv`
  (175 sales-multi-division-tagged items) is therefore inconclusive — nothing to compare.
- **Part 4 (FG21 vs FG02)**: **DISTINCT, MODERATE-TO-HIGH confidence, not a recording variant.**
  FG21 holds 78 items/17,496 units now with almost no ledger history (13 `cube_inventory_tran`
  rows, 2025-09-26 to 2026-08-21); FG02 holds **zero** current items/stock despite 2,307 ledger
  rows spanning 2017-10-19 to **2026-09-08** (through the present day) — a high-throughput
  pass-through signature like `QA`'s confirmed role, not a storage one. Zero item-set overlap; zero
  of 7,650 checked 150/151 transfer pairs (for the 131 itemcodes touching either code) directly
  link FG21↔FG02. **Inferred, not proven**: consistent with FG02 being an older/superseded
  pass-through code with FG21 now serving a related role — no data links them to one migration
  event.
- **Part 5 (pattern across all 44 codes, proposed mapping)**: prefixes do NOT behave uniformly
  (`FG` alone spans 4 dominant divisions depending on trailing digits) — trailing digits are the
  stronger signal. **14 of 44 codes placed** (table in `whmap_part5_proposed_mapping.csv` /
  `whmap_report.md` Part 5), each with an explicit confidence level and whether its division came
  from the hypothesis or from this cross-tab's own empirical dominant-division reading (the two
  are recorded as different `division_source` values, never conflated). No code beyond the
  already-confirmed `QA`=inspection/`FMTS`,`FMTO`=production WIP (2026-09-02 finding) could be
  given a process stage — this snapshot has no arrival/departure event data to distinguish further
  stages. **30 of 44 codes are UNRESOLVED** (zero current stock in this scope — not a hypothesis
  failure, nothing to test), including the literal-hypothesis codes `WH01`, `F101`, `W101`, `W121`,
  `QA`.
- **Snapshot-drift reconfirmed, not newly discovered**: this pull (2026-09-09) totals 154,893
  units/฿36,095,868, vs. Check 1's 158,130 units (2026-09-06) and Check 2's ฿37,399,005 — a ~2-3.5%
  drift over 3 days, consistent with the table being live (already an open, unresolved conflict in
  Phase D, not newly raised here).
- **Overall verdict, stated plainly**: the trailing-digit hypothesis **holds on every code it can
  actually be tested on (3/3), but that is a narrow test** — most of its predicted codes hold no
  current stock, so the hypothesis is **untested for 4 of 6 divisions, not confirmed for them**.
  **MODERATE confidence overall, not clean.** Does not decide which codes are sellable (Phase D
  assumption 1 remains open) — presents the mapping for the business/Orchestrator to act on.
  **Unresolved, listed separately**: 30/44 codes' division; process stage beyond QA/FMTS/FMTO;
  whether the FG21/FG02 succession is a real historical event; CI101's own digit convention (none
  exists — its sheet name carries no numeric suffix).

**Inventory detail view added to Tab 1 — DONE (2026-09-08).** Commits `88622c4` (dataset),
`a9cc60f` (view), `e98db48`/`0521d71`/`73c1283`/`a961568`/`3300400` (follow-up fixes and the lead
time column). `src/build_inventory_dataset.py` builds the **full 445-code pricelist registry**
(every visible sheet, per the same visibility convention `pricelist_reader.py` already used —
`sheet_state == 'visible'` — not the 335-item forecast scope), and reconciles it against that
335-item scope: every one of the 110 codes outside it carries a recorded `exclusion_reason`
(PEM104 division exclusion, `excluded_item_codes`, `placeholder_item_codes`, or
`placeholder_item_assignments_82` — no code is unexplained). On-hand quantity is
`Cube_Inventory_Exact.stock` summed across every warehouse per code, keeping `has_stock`/
`zero_stock`/`no_db_record` as distinct states throughout (a `no_db_record` code has no row in the
table at all — its quantity is written `null`, never `0`, so it cannot be silently read as "in
stock at zero"). A warehouse-breakdown popup shows the per-warehouse split behind any non-zero
total. Warehouse role (staging/holding/unknown) is derived only from `cube_inventory_tran`
paired-transfer evidence, per Phase D's own method — never from the warehouse code's name — and,
after `e98db48`, is kept in the JSON but **no longer rendered in the panel** (removed as
information the panel could not act on, not as a data change). The panel fetches the JSON at
runtime (never inlined into `index.html`, unlike the pre-existing `#omniTab` `OMNI`/`MATCH`
blobs), renders all 445 rows without virtualization (measured ~10-20ms per re-render), and is
sortable/filterable by Business/Category/Type/Description/Code. **Lead time (วัน)**: one editable
input per code, validated on blur (0-999, at most one decimal place — widened from an initial
whole-number-only rule in `3300400` after same-day/sub-day lead times were found to be valid
cases), persisted to a single namespaced `localStorage` key
(`saleForecast.inventoryPanel.leadTimeDays.v1`) — **deliberately browser-only, not written to
`data/inventory.json` or read by any pipeline script; see Locked Decisions for why.**

**Reserved/Available added to the Inventory panel, plus the Reserved-source investigation chain
— DONE (2026-09-10).** Commits `f4f55a4` (dataset), `fb00b87` (panel columns), `31b650f`
(per-row backlog drill-down + Available sort fix). Three read-only investigations preceded the
implementation, run as single Explorers (per `AGENTS.md`), each read-only and each confirming
nothing was written to `index.html`/`data/inventory.json`/the build script by the investigation
itself:

- `output/summary/reserved_available_investigation_report.md` (first in the chain) searched the
  whole schema for a dedicated reserved/allocated-quantity field and found
  `Cube_Inventory_Exact.reserve_bywa` — sitting in the exact same row as on-hand `stock`, same
  table, same snapshot batch. **Headline recommendation: prefer `reserve_bywa` over any
  backlog/order table for a column literally labelled "Reserved."**
- `output/summary/reserve_backlog_relationship_report.md` (second) tested that recommendation
  against a fuller comparison (445-registry cross-tab, correlation analysis, per-division
  breakdown) and **confirmed it, but on narrower grounds, with a new caveat**: `reserve_bywa`
  itself regularly exceeds on-hand stock, sometimes against zero stock entirely, on the staging
  warehouses (`QA`/`FMTS`/`FMTO`) Phase D already flagged as not sellable — so it is not a clean
  "physically set aside" figure either. **Moderate, not high, confidence either way.**
- `output/summary/company_scope_investigation_report.md` (third) checked whether backlog's
  company scope matches on-hand's, given the decision to use `Cube_Backlog` regardless of which
  field ultimately ships. Confirmed `Cube_Inventory_Exact` holds exactly two company values
  (`PEM`, `CI`) table-wide, and that `sale_company IN ('PEM','CI')` is the matching backlog scope
  — see "Business Findings" and "Evidence established" below for what this settled.

**The panel as shipped uses `Cube_Backlog`, filtered to `sale_company IN ('PEM','CI')` with no
status filter, not `reserve_bywa`** — stated here as a fact about what was built, not a
correction of the investigation: both reports' own fallback guidance, if backlog ships anyway, was
to avoid describing it as "physically set aside," which the panel follows (its own text calls it
"Reserved (Backlog)," names the source table and its separate load timestamp, and states plainly
that the figure is still pending verification — see `index.html`'s `invBacklogLabel` text).
**Choosing between the two fields for good is not decided by either investigation** — see "Open
questions" below for exactly what would need a person's answer first.

Per-item, `build_inventory_dataset.py` now also carries the individual `Cube_Backlog` rows behind
each code's Reserved total (`doc_id`, `job`, `customer`, `quantity`, `status`, `delivery date`,
`plan delivery date`, `backlog_from`), written exactly as the source holds them and never
de-duplicated — collapsing them would remove the thing this view exists to let a person judge.
Every item's rows are asserted, in-script, to sum exactly to that item's Reserved total (445/445
pass on the committed file). The panel opens these on a click of any non-zero Reserved value,
flagging rows that share quantity/status/delivery-date as **possibly** duplicate — stated in the
popup as a flag for review, not a conclusion, since two genuine orders can coincide (confirmed in
the committed data itself: `LS-F-99-1004`'s two flagged 100-unit/`MPS`/2026-09-11 rows,
`CTR-2026-05118` and `CTR-2026-05335`, are recorded under two different customer names — the flag
correctly surfaces this pair for a person to judge, it does not itself decide they are duplicates).
Sorting Available now sinks the `no_db_record` (unknown) rows to the bottom in both directions,
so the most negative values surface first ascending, rather than the previous behaviour where
unknowns sorted as the lowest value and buried the real negatives beneath them.

**Current committed snapshot (`data/inventory.json` at `31b650f`)**: on-hand snapshot loaded
2026-09-09 21:39:47 (`Cube_Inventory_Exact`); backlog snapshot loaded 2026-09-09 17:02:06
(`Cube_Backlog`) — **two different load timestamps, roughly 4.5 hours apart on the same
calendar day**, because the two tables refresh independently (see "Evidence established" below).
92 of 445 codes show negative Available; 147 codes have some Reserved quantity; 195 backlog rows
inside the `sale_company IN ('PEM','CI')` filtered set still match the cross-contract-duplicate
signature (`itemcode`, `quantity`, `status`, `deliverydate`, `plan_deliverydate` shared across
different `docID`s) and are counted anyway, per the decision to show as-is figures rather than
silently de-duplicate.

**Phase E0 — pre-check gate before Phase E1, three parallel Validators + a Synthesizer (per
`AGENTS.md`, 2026-09-18).** An external review identified three gaps that could make every Phase
E result untrustworthy if left unchecked: point-in-time leakage in rolling-origin backtests
(E0.1), unchecked cancellations in the demand series (E0.2), and placeholder items' coherence
with Type totals under Top-down allocation (E0.3). Full detail: `output/summary/phaseE0_
validator1_leakage_report.md`, `phaseE0_validator2_cancellations_report.md`,
`phaseE0_validator3_placeholder_coherence_report.md`, and the merged
`output/summary/phaseE0_synthesis_report.md`.

- **E0.1 (leakage) — no leakage found in either checkable mechanism, high confidence; no backtest
  re-run performed because none was triggered.** Historical Top-down allocation shares are
  **verified from data** to be computed only from data through each rolling-origin's own
  `train_size` in every script whose output feeds a cited backtest number
  (`src/item_level_reconciliation.py`, `src/transferability_all_divisions.py`,
  `src/focus_item_model_selection.py` — confirmed by direct code read). The specific
  training/test-window leakage channel is **verified from data** to be structurally absent
  (0.0000% at all 7 origins), a mechanical consequence of `load_data_full.py`'s existing
  `forecast_date >= createDate` cleaning rule. Model settings (MA windows, Croston/SBA constants,
  TSB grid search) are **verified from data** to carry no leakage for all six adopted models. Two
  items remain **cannot be determined**, both non-blocking, carried forward as documented
  assumptions rather than new discoveries: (a) whether `forecast_date` is ever revised in place
  after intake — re-affirms Phase A's own finding, unverifiable today (see E0.2's DB blocker
  below, which also stopped this re-check); bounded at <2.5% of rows with no consistent direction,
  too small to overturn Phase E1's inputs; (b) no dated historical pricelist snapshots exist
  anywhere (not in git, not on disk), so whether an item's division/Type/status classification
  differed at a past origin cannot be measured — **prospective snapshot collection must start now
  because this cannot be closed retroactively** (archive a dated copy of `reference/pricelist.xlsx`
  on every update, or an append-only `(item_code, division, type, status, effective_date)` table).
- **E0.2 (cancellations) — RESOLVED 2026-09-18, re-run after the DB password was reset. Verdict:
  no cancellation contamination found, verified from data; no change to the demand series
  recommended.** After the initial blocked attempt (SQL error 18487, expired password), the human
  reset the SQL Server login and the same Validator re-ran the full task on a live connection (Part
  0 connectivity confirmed first). Full detail: `output/summary/phaseE0_validator2_cancellations_report.md`,
  script `src/investigations/phaseE0_cancellations_validator2.py`.
  - **Cube_CES Cancel rows (fresh, table-wide): 2,423 rows** (matches the 2026-08-31 count, now
    with value/date detail that pull never captured), qty 151,865,368.2, value ฿9,903,099,704.17,
    `CtrDate` 2013-08-22 to 2026-02-25. Of these, only **553 rows (136 distinct item codes,
    qty 49,861, value ฿68,283,214.86)** are for pricelist-scope items that could ever enter this
    project's demand series at all — the remaining ฿9.83B is non-pricelist items that
    `load_data_full.py` can never load.
  - **Cancelled pairs still counted as Actual/MPS demand: ZERO** — verified from data. Joined 548
    pricelist-scope and, as a robustness check, all 2,150 table-wide cancelled `(ContractID,
    ItemCode)` pairs against `cube_Sale_APD` Actual/MPS rows: 0 matches in both. A positive control
    (non-cancelled Cube_CES Actual/Backlog pairs, same itemcodes) matched at 99.52%, confirming the
    join key works and the null result is real, not a broken join.
  - **Share of demand and effect on the three focus items: 0.0000%, verified from data.**
    Denominator (full pricelist scope, Omni Channel, Actual/MPS, 2024-01-01+): 3,536,958 qty /
    ฿2,075,984,031.45. `EEE-F-FC-1040010002` (38 Cancel rows), `HS-F-99-02110` (3), `HS-F-99-0213`
    (4) all have Cancel rows only in 2018-2023, none matching Actual/MPS. Stated negligibility
    threshold: <0.5% of series qty/value (an order of magnitude below the smallest effect this
    project treats as material elsewhere, e.g. the 0.42% cross-division exclusion) — the measured
    effect is exactly zero, not merely below threshold.
  - **Partial cancellations (`PlanQty > ActualQty+BacklogQty`): structurally empty for confirmed
    contracts, verified from data.** 23,633 rows meet this condition table-wide, but 100% carry
    quotation-stage prefixes (`QTN-`/`OQ-`/`ENQIN-`/`OPP-`) — 0% are confirmed (`CTR-`) contracts.
    An exhaustive check of all 143,936 confirmed-contract rows with non-null `PlanQty` (Actual
    138,487, Backlog 3,026, Cancel 2,423) shows `PlanQty == ActualQty+BacklogQty` exactly on every
    one — the shortfall condition cannot fire on a confirmed contract with this data model, so the
    cancellation/adjustment/cannot-be-determined bucketing has zero rows to classify.
    **Cannot be determined**: whether a genuinely different, unrecorded "original plan quantity
    before reduction" ever existed — `Cube_CES` appears to retain only current reconciled state,
    not history.
  - **Recommendation (configurable assumption, backed by the verified findings above): no change
    to the demand series' cancellation handling.** Explicitly does not rule out an unrecognized
    mechanism outside this task's two checked channels (join-key resurfacing; the literal
    `PlanQty` shortfall signal).
- **E0.3 (placeholder coherence) — arithmetic verified from data; RESOLVED 2026-09-18, see Locked
  Decisions, "Placeholder items sit outside the Top-down hierarchy entirely."** Of the 22
  (division, Type) pairs touched by the 82 no-history placeholder items, 16 have at least one real
  (history-bearing) sibling; production Top-down is confirmed hierarchy-consistent today (Type
  total = sum of item forecasts, before placeholders are added). Two options were computed, both
  verified from data: **Option 1 (additive)** leaves every real item's forecast unchanged but
  inflates the Type's total beyond what its own Type-level model forecasts, by +0.8% to **+707.3%**
  (worst: `Suspension Insulator`, PEM101 — 6 placeholders outnumbering 3 real items at 7x their
  combined volume); **Option 2 (carve-out)** keeps the Type total exactly fixed but shrinks every
  real item's forecast, from 0.8% (`LED Street light`) to **83.7%** (`Current Transformer Type
  CDB`, PEM107), with no change in that item's own history. **Neither was adopted** — a third
  option (exclude placeholders from hierarchy reconciliation entirely) was chosen instead, see
  Locked Decisions. **All three focus items are unaffected regardless** — neither of their Types
  appears in the 82-item placeholder population (verified from data). Two Rule C Types with zero
  real siblings (`33kV Recloser`, `FRTU`, 3 items total) had no Type-level forecast at all under
  either option — resolved the same way, by exclusion from reconciliation. Separately, **66 of 82
  items have an identifiable pricelist analogue/predecessor** (verified from data that a candidate
  exists; a **supported hypothesis only**, not tested, that using it would forecast better than the
  flat Type mean/median) — future Modeler work, non-blocking, recorded as the preferred future
  basis in the Locked Decision. Full per-Type table: `output/summary/
  phaseE0_validator3_placeholder_type_totals.csv`; per-item reasons and analogues:
  `phaseE0_validator3_82item_reasons.csv`.
- **Overall verdict and consequence for Phase E1, updated 2026-09-18: Phase E1 may now begin in
  full — no remaining blocking gap.** E0.2's re-run cleared the project-wide blocking gap (zero
  cancellation contamination found); E0.3's third-option decision cleared the item-specific
  blocking gap (placeholders excluded from hierarchy reconciliation, rather than either distorting
  option being adopted). Non-blocking, carried forward as documented assumptions, unchanged from
  Phase A/E0.1: `forecast_date` revision-in-place timing (bounded <2.5% of rows) and the absent
  pricelist version history (prospective snapshot collection should still start now). Fully
  resolved, no impact: allocation-share leakage, model-setting leakage, and (as of this re-run)
  cancellation contamination.
- **Two documentation corrections requested by the review, applied 2026-09-18**: see Business
  Findings §3 (PO-based history scope limitation) and `CONVENTIONS.md` (cube-agreement-shows-
  consistency-not-correctness rule).

## 3. Business Findings

These describe how this business actually operates, established from data investigation (not
assumption) during Phase 1.5 and the Phase 3.1 follow-on tasks. They shape every downstream
phase, particularly Phase 4. Full methodology, confidence levels and caveats are in the
"Combination-variant test, order-notice lead time, on-time delivery baseline" and
"Stock-availability hypothesis investigation" entries above.

- **Customers give almost no order notice.** Median notice is 6 days; only 5.9% of orders give
  a month or more. This is far too short to produce or procure against — orders can only be
  filled from stock already held. **Phase A caveat (2026-09-02, high confidence)**: this figure
  depends on `forecast_date` not being revised after PO intake; revision-in-place cannot be
  proven or disproven from this data (no audit trail exists), but every test run bounds any
  possible revision at under 2.5% of rows with no consistent direction — too small to explain
  this figure, so it stands, though "forecast_date is fixed at intake" remains an assumption.
- **On-time delivery has improved but is not yet good.** 73.2% on-time in 2026 (partial year),
  up from 57.8% in 2023. 8.8% of deliveries are late, with a median lateness of 2 days. **Phase A
  caveat (2026-09-02, high confidence)**: same caveat as above — this 15-point improvement is
  not explained by date rescheduling (bounded effect too small), reinforcing this finding rather
  than weakening it, but the underlying fixedness of `forecast_date` remains unproven.
  **[SUPERSEDED as a fill-rate benchmark — Phase J2, 2026-09-23: 73.2%/57.8% are on_time_exact
  (delivered exactly on the due date), row-weighted, PEM101 only — see METRICS.md Sec.19. The
  improvement trend itself is not overturned (see the corrected by-year `not_late` series in the
  by-year entry above), but this figure must never be compared against `fill_rate` again.]**
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
- **Data-source strength (found by a 2026-09-07 best-practice review): the demand series is built
  from PO receipts, not shipments.** `createDate` records when a purchase order is received, and
  `status` (`Actual` + `MPS`, "PO Received" — see Locked Decisions, "MPS means confirmed demand")
  is populated at that point regardless of whether stock is available to fulfil it immediately —
  consistent with this project's own finding above that late deliveries are primarily a stock-
  availability problem, not an order-timing one: the order is still recorded even when the
  business cannot fill it on time. This means demand is **not censored by stockouts** — published
  forecasting guidance warns that models trained on stockout-suppressed zero-demand periods
  under-forecast systematically, because a stockout month reads as "no demand" instead of
  "unmet demand." This project is not exposed to that problem, since demand is captured at PO
  receipt, not at the point of shipment or fulfilment. Recorded as a strength of the data source,
  not something this project did — the demand-capture design (whichever system feeds
  `cube_Sale_APD`) already avoids it.
- **Documentation correction (Phase E0 review, 2026-09-18): the demand series is built from PO
  receipts, not from all customer demand — this is a structural scope limitation of the whole
  modelling approach, distinct from the stockout finding above, not something any cleaning step
  can fix.** `createDate` records when a purchase order is received, and every downstream figure
  (forecasts, Max-Min, simulation) is built from rows that reached that stage. The series is
  therefore systematically blind to demand that never became a recorded order — a customer turned
  away for lack of stock before ordering, a quote never converted, a sale lost to a competitor
  before a PO was raised. None of this is recorded anywhere in the database, so no query against
  this data can find it or bound its size. **This must not be conflated with the finding
  immediately above**: that finding is about orders that *were* placed still being recorded even
  when stock could not fulfil them on time (not censored by stockouts); this correction is about
  demand that never reached the point of becoming an order at all. See
  `output/summary/phaseE0_synthesis_report.md` §3(a).

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
- **SUPERSEDED IN PART, corrected 2026-09-04 — see "Project scope correction" below.**
  ~~All queries filter on `division = 'PEM101'` and `revenue_type = 'Omni Channel'`
  (2026-08-31, written into `config/config.yaml`)~~. **The `division = 'PEM101'` part of this
  entry was wrong and is superseded**: `division = 'PEM101'` was the *pilot's* condition (Phase 2
  used PEM101 because Fuse and Surge Arrester products exist only in that sheet), and this entry
  wrongly wrote it down as if it were the whole project's scope. That error was not caught until
  it caused confusion in Phase C, when PEM102/PEM103/PEM104/PEM107/CI101 needed their own
  division values and this entry read as if only PEM101 was ever in scope. Left here, struck
  through rather than deleted, so the mistake and how it happened are traceable — see
  `CONVENTIONS.md`'s new rule (2026-09-04) requiring every decision to state whether it is
  project-wide or pilot/task-scoped, added because of this exact error. **The
  `revenue_type = 'Omni Channel'` and Actual+MPS status-basis parts of this entry were, and
  remain, correctly project-wide** — see the corrected scope decision immediately below, which
  restates them alongside the fixed division scope. `division` (as a column, not the single
  value `'PEM101'`) is still required in every query: 72 `productCateName` values, including
  Fuse and Surge Arrester, appear under more than one division, so category/type name alone is
  not a safe key — confirmed to matter in practice: omitting it overstated the pilot group's
  total sales by ₿60.6M (14.3%), see the audit note above.
- **Project scope correction (2026-09-04): the project's scope is Omni Channel across every
  division in the pricelist's visible sheets, not `division = 'PEM101'` alone.** Corrected by
  the user after the error above caused confusion in Phase C. The scope is:
  - **Revenue type**: `revenue_type = 'Omni Channel'` (unchanged from above, project-wide,
    correctly recorded originally).
  - **Divisions in scope**: every division that appears in the pricelist's visible sheets —
    `PEM101`, `PEM102`, `PEM103`, `PEM104`, `PEM107`, `CI101`. **`division` is a grouping key
    for products, not a scope filter** — it identifies which sheet/business-unit a product
    belongs to, it does not narrow which products are in scope. `PEM101` was used alone in the
    pilot only because Fuse and Surge Arrester products — the pilot's chosen Type-level scope —
    happen to exist exclusively in that one sheet; nothing about that pilot choice restricts the
    project as a whole.
  - **Exclusion — `-OLD` suffix — SUPERSEDED 2026-09-04, see "Division source-of-truth
    correction" below. Reversed the same day it was written, kept here struck through, not
    deleted, so the mistake is traceable.** ~~any `division` value carrying the suffix `-OLD`
    (e.g. `PEM102-OLD`, `PEM107-OLD`) is excluded from the project scope, confirmed by the user.
    Reason: Phase C step 1 found these rows carry swapped or legacy tags whose meaning could not
    be established from data — `PEM102`'s real 2024 activity sits under `division='PEM107-OLD'`
    and `PEM107`'s real 2024 activity sits under `division='PEM102-OLD'` (see the Phase C step 1
    log entry above and `output/summary/phaseC_synthesis_report.md` §5), and no audit trail exists
    to confirm which tag is authoritative for which period. This decision explicitly overrides the
    Phase C step 1 Validators' recommendation to combine `PEM102`+`PEM107-OLD` and
    `PEM107`+`PEM102-OLD` (open question 2, Section 5 below) — the combine option is not adopted.
    Consequence, stated plainly: PEM102's usable history stays at ~January 2025 rather than
    extending back to January 2024, and PEM107's stays at ~January 2025 rather than extending back
    to January 2024, since each division's pre-2025 activity sits under the excluded `-OLD` tag of
    the other division. This is a real loss of usable history, accepted in exchange for not
    guessing which of two contradictory tag conventions is correct.~~
  - **Exclusion — PEM104**: `PEM104` is in scope for product identification (its codes are part
    of the 445) but **excluded from forecasting**, confirmed by the user. Reason: Phase C step 1
    found only 12 transactions across 17 calendar months for PEM104's codes — too few to fit any
    model at any aggregation level (see the Phase C step 1 log entry above). PEM104 receives a
    **placeholder for Phase 4** (following the same principle as the existing 10-item
    `placeholder_item_codes` precedent — real activity exists, just not enough to forecast) rather
    than being dropped outright, and its codes are recorded in `config/config.yaml`
    (`divisions_excluded_from_forecasting`).
  - **Inclusion — CI101**: `CI101` is in scope, confirmed by the user, correcting an earlier
    framing (Section 5 below, "Phase C step 1 residual items" item 3) that treated it as a
    candidate for exclusion pending a scope decision, and an even earlier framing in
    `output/summary/phaseC_CI101_report.md`/`phaseC_synthesis_report.md` that had described CI101
    as if it might be a separate company to drop. **CI101 is in the pricelist, so it is in
    scope** — there was never a data-driven reason to treat it as external to the project, only an
    unexamined assumption. The 37.2% of CI101-sheet product value that is recorded under
    `division = 'PEM101'` (Phase C step 1 finding, `output/summary/phaseC_synthesis_report.md`
    §5) is genuine Omni Channel demand for CI101's own item codes and **must be counted, not
    discarded** — it does not become out-of-scope merely because it is tagged under a different
    division than the sheet it's listed on, per the "division is a grouping key, not a scope
    filter" principle above.
  - This resolves Section 5's "Phase C step 1 residual items" open question 3 (CI101's
    cross-division scope decision) as **include, count the PEM101-tagged share** — see Section 5
    below for the corresponding strike-through. It does not resolve open questions 1/2 (the
    PEM102/PEM107 tag mechanism) — those remain unresolved on the *mechanism*, but are now
    resolved on the *filter decision* (exclude `-OLD`, do not combine), as stated above. It does
    not resolve open question 4 (PEM103's Tendering-channel scope) — PEM103 stays
    `revenue_type = 'Omni Channel'`-only under this correction, unchanged.
  - **Written into `config/config.yaml`**: `division` changed from a single value to a list
    (`divisions_in_scope`), with the `-OLD`-suffix exclusion and the PEM104 forecasting exclusion
    recorded as explicit, commented fields — see `config/config.yaml`. **Not yet done**: no
    pipeline script (`load_data.py`, `load_data_full.py`, etc.) has been updated to read the new
    list-shaped config instead of the old scalar `division` value — those scripts still filter on
    `PEM101` alone until updated. This entry documents the corrected scope decision; wiring it
    into the data-loading code is separate, not-yet-done work. **SUPERSEDED 2026-09-04 — see
    "Division source-of-truth correction" immediately below: `divisions_in_scope` is itself
    replaced by a sheet→division mapping, and the wiring described as "not yet done" here has now
    been done, on the corrected basis, not the `-OLD`-excluded basis this bullet describes.**
- **Division source-of-truth correction (2026-09-04): the pricelist is authoritative for which
  division a product belongs to; the database's `division` column is reference-only and is never
  used to filter which rows count as an item's sales.** Reverses the `-OLD`-suffix exclusion above
  **the same day it was written**, per the user's direct correction. Recorded plainly: the
  exclusion decision was wrong not because the underlying evidence was wrong (the PEM102/PEM107
  tag-swap pattern is real and still unexplained — see Phase C step 1 above), but because it
  answered the wrong question. Faced with an unreliable database column, the prior entry asked
  "should we exclude the unreliable values?" instead of "what is the source of truth for this
  attribute, and does the database even need to agree with it?" The pricelist already *is* the
  source of truth for which division a product belongs to — that was true before the `-OLD`
  question ever came up, it was simply never applied to this decision. Once asked correctly, the
  fix is not exclusion but **not filtering on `division` at all**: an item's division is whatever
  pricelist sheet it appears on; its sales are every Omni Channel row for its item code,
  regardless of what division tag that row happens to carry, `-OLD` included. This gap is why
  `CONVENTIONS.md` now also carries a rule (2026-09-04) that the pricelist is the authoritative
  source for product attributes and that "what is the source of truth" must be asked before "should
  this value be excluded."
  - **The corrected rule**: pull Omni Channel sales for an item code with no `division` filter in
    the query at all. Attach the item's division as a lookup from the pricelist sheet it belongs
    to (`PEM101`→PEM101, `PEM102`→PEM102, `PEM103`→PEM103, `PEM104`→PEM104,
    `PEM107 CT-Version 2`→PEM107, `CI101`→CI101). The database's own `division` value on each row
    is kept as a separate reference column for inspection, never used as a filter or as the
    division of record.
  - **Expected consequences, stated before re-validation so they can be checked against it**:
    PEM107 and PEM102 regain their full 2024 history (previously only visible by explicitly
    combining with the other's `-OLD` tag, which was itself rejected above before this reversal);
    CI101 automatically includes its `PEM101`-tagged 37.2% share, with no special-case scope
    decision needed (it was never really a CI101-specific exception — it is the same "don't filter
    on division" rule already required for PEM102/PEM107); every readiness verdict in
    `output/summary/phaseC_synthesis_report.md` and `phaseC_sheetmap_report.md` that was computed
    under a `division`-filtered pull (PEM101, PEM102, PEM103, PEM107, CI101 — everything except the
    already-unfiltered totals) must be treated as **not yet re-derived on this basis** until the
    re-validation below is complete.
  - **Written into `config/config.yaml`**: `divisions_in_scope` (the list from the entry above) is
    removed. Replaced with a `sheet_to_division` mapping (which division to record for an item
    found on a given sheet) and a `division_source: "pricelist"` flag stating explicitly that
    `division` is attached from the pricelist and never used to filter a query. See
    `config/config.yaml`.
  - **Written into code**: `src/load_data_full.py`, `src/investigations/load_data.py` (the
    original pilot loader this project has always called `src/load_data.py` in prose — moved to
    `src/investigations/` in the 2026-09-04 reorg, flagged here rather than silently assumed to be
    the same path) and `src/score_forward_test_v2.py` all built their SQL `WHERE` clause with
    `AND division = '{division}'`, sourced from `config["division"]`. All three are fixed: the
    `division` clause is removed from the query; `load_data_full.py` and
    `src/investigations/load_data.py` now attach each row's division from the pricelist and keep
    the database's own value as a separate `division_db_raw` reference column.
    `src/score_forward_test_v2.py`'s actuals pull needed the same filter removed but does not
    carry a division column downstream, so nothing was attached there. Confirmed by direct search
    (not assumed): no other script in `src/` builds a SQL `WHERE` clause on `division`; the only
    other file matching the old pattern is `src/investigations/score_forward_test.py`, the
    superseded v1 of the scoring script (replaced by `score_forward_test_v2.py`, not called by
    `src/run_pipeline.py`) — left unmodified as dead/archived code, flagged here rather than
    silently fixed or silently ignored.
  - **Re-validation status**: see the dated Phase C step-1 re-validation log entry below (this
    file, added 2026-09-04) for the checks re-run on this new basis (double-counting between
    tagged variants, Cube_CES reconciliation, usable date ranges, no-history recount, totals
    before/after) and their results and confidence levels.
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
  resulting Finished Good becoming stock. **REAFFIRMED BY THE BUSINESS, 2026-09-04 (Section 8):
  the 45-60 day procurement figure stands as previously stated, and is configurable per item.
  Assembly time after parts arrive remains open** — not resolved by this reaffirmation.
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
  of current on-hand stock); ~~which of the remaining warehouse codes hold genuinely SELLABLE
  Finished Goods stock could not be confirmed from data (no sales table has a warehouse field)
  and must be confirmed by the business~~. **CHANGED 2026-09-04 (Section 8): no longer a question
  for the business — to be DERIVED by reading `Cube_Inventory_Exact` directly.**
- **Cross-division demand: keep the Omni Channel scope (2026-09-04).** Under this project's
  actual channel/status filter (`revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
  the same Method B measurement as the 2026-09-04 Task 1 log entry above), demand excluded by
  the `division='PEM101'` filter is **₿2.96 million, 0.42%** of the 128-item scope total — small
  enough to document as a known exclusion rather than model. This supersedes the earlier
  ₿60.6 million (14.3%) figure as the basis for this decision: that larger number (Method A,
  which holds only `itemcode` fixed, ignoring channel) was found on 2026-09-04 to be mostly
  **Tendering-channel sales of `EEE-F-FC-1040010002` through division `PPS`** (67.4% of Method
  A's ₿85.5M full-scope figure), which is outside this project's Omni Channel scope **by
  design**, not an omission — mixing in a cross-channel effect the original ₿60.6M figure never
  separated out. ~~Whether that Tendering demand draws from the same physical stock as this
  project's Omni Channel items is an open question for the warehouse team, not something the
  data can answer~~ (no warehouse field exists on any sales row, and no transfer table links
  divisions) — carried forward in Open Questions below, not resolved here. **REMOVED FROM THE
  DATA REQUEST LIST, 2026-09-04 — moved to Section 8: business confirmed this data does not
  exist. Phase 4 must be designed without it.**
- **Six pricelist items excluded from Max-Min: never sold (2026-09-04).** These 6 codes are
  listed in the pricelist but have **zero rows in `cube_Sale_APD` under any filter, zero rows in
  `Cube_CES`, `cube_inventory_tran`, `Cube_Inventory_Exact`, and `Cube_Quotation`** — classified
  "(d) Listed but never sold" by the 2026-09-04 no-history-items investigation
  (`output/summary/task2_per_item_classification_final.csv`). Excluded from Max-Min because
  there is nothing to plan against — no demand history of any kind exists anywhere in the
  database to build a policy from. Codes: `EEE-F-FL-1040030100`, `HS-F-99-0181`,
  `HS-F-99-1181`, `HS-F-99-1211H22`, `HS-F-99-1241H03`, `HS-F-99-3031`. Recorded in
  `config/config.yaml` (`excluded_item_codes`).
- **Ten items given a placeholder forecast: sold only outside this project's filter, or
  unclassifiable (2026-09-04).** These 10 codes have real transaction history somewhere (unlike
  the 6 above), but either outside this project's division/channel scope (6 codes, classified
  "(b) Sold outside this project's filter" — Tendering channel, a different division, or both)
  or with genuinely mixed evidence that cannot be classified cleanly (4 codes — a real
  pre-2024 Omni Channel/PEM101 history predating the modelling window, or live unconverted
  quotes mixed with ambiguous channel history; see the same classification CSV for the
  per-item evidence and confidence level). Until the business confirms their status, each
  receives a **placeholder forecast equal to the average demand profile of its own Type**
  (i.e. treated the same way a Top-down allocation would treat an item with a typical share of
  its Type, rather than the zero a true no-history item gets) — not zero, and not a real
  item-specific forecast, since real sales activity exists for all 10. Codes:
  `FC-A-38-00203`, `EEE-F-FL-5920-353-01100`, `EEE-F-FL-5920-353-01600`,
  `EEE-F-FL-5920-353-02600`, `EEE-F-FL-5920-353-06600`, `HS-F-99-1151`, `HS-F-99-2091N`,
  `HS-F-99-3121`, `HS-F-99-3331`, `HS-F-99-3361`. Recorded in `config/config.yaml`
  (`placeholder_item_codes`).
- **Final forecasting method: Top-down combination (2026-09-04, closing Phase B).** Forecast at
  Type level using the arithmetic mean of the six base models (Naive, MA3, MA6, MA12, Croston,
  SBA — `src/models.py combination_forecast`), then allocate to items by each item's historical
  qty share of its Type over the fitting window (`src/item_level_reconciliation.py`'s Top-down
  branch). Reason: Phase B3 (2026-09-02) found no approach (Direct/Top-down/Reconciled)
  statistically beats another with significance, but Top-down had the best point estimate at
  every level tested, and the Modeler-tasks-1-3 re-test (2026-09-04) reconfirmed pure Top-down
  beats every Conditional (share-threshold) variant with significance while never losing to
  Direct — the simplest defensible choice, not a decisively proven one (recorded as such, not
  overstated). **Evaluation policy**: rolling-origin (all 7 origins pooled) is the PRIMARY
  measure; the single train/validation/test split is SECONDARY only, because Task 1
  (2026-09-04) showed the final train/val/test window (origin 7, Feb-Jul 2026) behaves
  anomalously for reasons that remain unresolved (the createDate-vs-forecast_date reversal
  persists at every level tested and could not be explained by the dominant focus item alone —
  see the Modeler-tasks-1-3 log entry above) — a single window already flagged as
  unrepresentative must not be the primary basis for locking in a method. **Series key**: the
  demand series is keyed on `forecast_date`, captured as a **frozen snapshot at time of use**
  (the `snapshot_pull_date` column written by `src/load_data_full.py`), never a live re-query —
  Phase A could not rule out `forecast_date` being revised after PO intake, so treating it as
  ever-changing would make results non-reproducible across runs. All four of method, evaluation
  policy, and series key are recorded in `config/config.yaml` (`forecast_method_final`,
  `evaluation_policy`, `adopted_series_key`).
- **Placeholder items sit outside the Top-down hierarchy entirely (2026-09-18, closing Phase E0.3's
  open decision).** E0.3 found that both naive ways of folding the 82 no-history placeholder items'
  Type-mean/median values into Top-down's Type-level totals distort the hierarchy: **adding them ON
  TOP of a Type's existing total inflated some Types by up to +707.3%** (worst: `Suspension
  Insulator`, PEM101 — 6 placeholders outnumbering 3 real items at 7x their combined volume; also
  severe at `Current Transformer Type CDB`, PEM107, +513.8%); **carving them OUT of the existing
  total (redistributing real items' shares to make room) shrank real items' own forecasts by up to
  -83.7%** (worst: `Current Transformer Type CDB`) with no change in those items' actual sales
  history. Neither is acceptable as a silent default — both distort a number a planner would
  otherwise trust unchanged. **Decision: placeholder items are excluded from Top-down hierarchy
  reconciliation.** A placeholder item's value never adds to, and is never carved out of, any Type
  total, and never changes any real item's allocated share — it exists as a standalone reference
  estimate only, outside the Type-level/item-level aggregation the rest of the hierarchy must sum
  correctly through. Placeholder values must be clearly flagged wherever displayed and **must never
  feed a purchase/reorder recommendation** (Phase E1's Max-Min for a placeholder item, if computed
  at all, must be visibly marked as built on a reference estimate, not a real forecast). **For the
  66 of 82 items with an identified pricelist analogue or predecessor code** (E0.3,
  `output/summary/phaseE0_validator3_82item_reasons.csv`), that analogue is the **preferred basis**
  once a placeholder value is actually needed for planning, in place of the flat Type mean/median —
  recorded here as **future work, not yet implemented** (no Modeler has backtested whether an
  analogue-based estimate actually forecasts better; this is a supported hypothesis about a better
  basis, not a proven one). Evidence: `output/summary/phaseE0_validator3_placeholder_coherence_report.md`
  and `phaseE0_synthesis_report.md`. Written into `config/config.yaml`
  (`placeholder_hierarchy_treatment`).

## 5. Open Questions

- **Phase E0 gap register (found 2026-09-18, full detail `output/summary/phaseE0_synthesis_report.md`
  §2)** — the pre-check gate before Phase E1 closed with one project-wide blocking gap and one
  item-specific blocking decision, both requiring action outside this codebase:
  1. ~~**BLOCKING, project-wide** — SQL Server login `jetniphat.boo`'s password has expired (SQL
     error 18487), reproduced independently 3 times across 2 agents. Owner: IT/DBA (password
     reset, update `.env`). Until fixed, E0.2's four cancellation sub-questions (Cube_CES Cancel
     rows still counted as Actual/MPS demand in the series; their share of total/Type demand;
     effect on the three focus items; partial-cancellation bucketing) remain **cannot be
     determined**, and Phase E1's demand-series inputs must be treated as provisional. The query
     plan is fully scoped in `output/summary/phaseE0_validator2_cancellations_report.md` and needs
     no redesign, only execution once connectivity is restored.~~ **RESOLVED 2026-09-18 — password
     reset by IT, E0.2 re-run in full on a live connection. Verdict: zero cancellation
     contamination found (0 of 548 pricelist-scope and 0 of 2,150 table-wide cancelled pairs
     resurface as Actual/MPS demand, positive-control-verified; partial-cancellation signal
     structurally empty for confirmed contracts). No change to the demand series recommended. See
     the Phase E0 dated log entry and `output/summary/phaseE0_validator2_cancellations_report.md`.**
  2. ~~**BLOCKING, item-specific** — Option 1 (additive) vs. Option 2 (carve-out) for how the 82
     no-history placeholder items' Type-mean/median values interact with Top-down's Type totals,
     across 22 (division, Type) pairs (up to +707.3% Type-total inflation under Option 1, or up to
     83.7% real-item forecast shrink under Option 2 — see the Phase E0 dated log entry). Owner:
     business/Orchestrator decision-maker; this is a policy choice, not resolvable by further data
     analysis. Also blocking: the 2 Rule C Types with zero real siblings (`33kV Recloser`, `FRTU`,
     3 items), which have no Type-level forecast at all today under either option. None of this
     overlaps the three focus items.~~ **RESOLVED 2026-09-18 — see Locked Decisions, "Placeholder
     items sit outside the Top-down hierarchy entirely": neither Option 1 nor Option 2 was adopted.
     A third option was chosen instead (exclude placeholders from hierarchy reconciliation
     entirely, reference-estimate only, never feeds a purchase recommendation), which also resolves
     the 2 zero-real-sibling Rule C Types (they now correctly have no reconciled Type-level number
     to produce, rather than an undefined one).**
  3. **Non-blocking, carried forward as documented assumptions**: `forecast_date` revision-in-place
     timing (re-affirms Phase A, bounded <2.5% of rows, could not be independently re-verified
     today due to gap 1's same DB outage); absent pricelist version history (no dated snapshots
     exist anywhere — prospective collection should start now, since this cannot be closed
     retroactively); 66 of 82 placeholder items have an untested pricelist analogue that might
     forecast better than the flat Type mean/median (future Modeler work); the MA window
     (3/6/12) selection rationale is undocumented (no leakage risk, a rigor/documentation gap
     only).
- **Phase A residual items (found 2026-09-02)** — unresolved, non-blocking for the phases that
  follow, but flagged for specific owning teams (full detail with owner per item in
  `output/summary/phaseA_synthesis.md` §5): whether `forecast_date` is ever revised in place
  after PO intake (undetectable in this schema — needs a genuine audit/snapshot table or IT/
  business confirmation); the cause of the 2.3-3.2% `forecast_date`/`PlanDelDate` disagreement;
  ~~root cause of `EEE-F-FC-1040010002`'s H1-2025 buyer-base pause~~ (needs stock/supply/contract
  data the business holds, not this database) — **CLOSED WITHOUT FURTHER PURSUIT, 2026-09-04,
  moved to Section 8: cannot be answered from internal data; deferred to Phase 3.2, where
  external factors will be examined**; whether the 101 zero-post-2024-activity "dropped"
  customers are genuinely lost (needs account-status confirmation from the sales team); the
  mechanism behind `CS07977`'s and `CS00477`'s Omni Channel→Tendering relabelling (needs the
  sales team who classifies `revenue_type`); **how much of the measured Phase 2/3.1 forecasting
  bias traces to the `EEE-F-FC-1040010002` collapse-recovery cycle landing inside the backtest
  window, vs. general demand shape — needs the Modeler, not yet attempted, and should happen
  before Phase 4 locks in a safety-stock policy from the current bias figures.**
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

- **Date-column Validator residual items (found 2026-09-04)** — unresolved, non-blocking; see
  `output/summary/datecol_validator_report.md` for full detail. Whether createDate/PODate/
  `Cube_CES.CtrDate` record the literal moment of customer order intent vs. contract-entry date
  (undetectable from this data model — needs an external non-database record or IT/business
  confirmation); the mechanism behind the 15 rows (0.054% of the 128-item scope) where createDate
  lags PODate by up to 44 days (too rare to investigate further, ₿0.13M total value, non-blocking);
  ~~what actually explains the Feb-Jul 2026 rolling-origin-vs-train/val/test divergence first
  found in Phase B1/B4~~ (this task ruled OUT the createDate/PODate back-dating mechanism
  specifically, high confidence negative finding, but did not identify the true cause); the
  business reason two separately-named fields (`CtrDate`/`ReceiveCtrDate` in `Cube_CES`;
  `createDate`/`PODate` in `cube_Sale_APD`) exist for what is, on the Actual/Backlog status basis,
  a >99.9%-identical value. **CLOSED WITHOUT FURTHER PURSUIT, 2026-09-04 — moved to Section 8:
  three candidate causes were ruled out (createDate/PODate back-dating, the
  `EEE-F-FC-1040010002` item, and — insufficient by itself — an item/window-specific
  order-timing pattern); no further investigation will be made. Recorded as a known limitation;
  this is the reason rolling-origin evaluation is PRIMARY and the single train/val/test split is
  SECONDARY (see the "Final forecasting method" and "Evaluation policy" Locked Decisions above).**

- **Phase C step 1 residual items (found 2026-09-04)** — unresolved, BLOCKING for the specific
  division noted, non-blocking for the others; full detail, confidence levels and per-division
  evidence in `output/summary/phaseC_synthesis_report.md`:
  1. ~~The PEM102 ↔ PEM107 legacy division-tag mechanism~~ — is this one company-wide
     division-code reorganization around Nov-Dec 2024, two unrelated relabelings, or something
     else? Unprovable from read-only data (no audit/change-log table exists) — needs IT/business
     confirmation. Blocks a firm filter decision for both PEM102 and PEM107. **RESOLVED BY THE
     BUSINESS, 2026-09-04 — moved to Section 8 ("Resolved by the business"): the two divisions
     were reorganised; `PEM102-OLD`-tagged rows are `PEM107` products, `PEM107-OLD`-tagged rows
     are `PEM102` products. Confirms the pricelist-as-source-of-truth decision and explains the
     mirror pattern directly.**
  2. ~~Whether to combine `division IN ('PEM102','PEM107-OLD')` and `division IN ('PEM107',
     'PEM102-OLD')`~~ — **SUPERSEDED again, same day, see Locked Decisions, "Division
     source-of-truth correction": the question itself no longer applies.** The intermediate
     answer ("do not combine, exclude both `-OLD` values") is itself superseded — the corrected
     rule filters on `division` not at all, so there is nothing to combine or exclude; `-OLD` rows
     are counted like any other row once the item's pricelist division matches. **The mechanism
     behind the tag swap (item 1 above) is now resolved by the business (Section 8)** — no filter
     decision depends on it either way.
  3. ~~CI101's cross-division scope decision~~ — **RESOLVED 2026-09-04, see Locked Decisions,
     "Project scope correction": CI101 is in scope, and the 37.2% recorded under
     `division='PEM101'` is genuine Omni Channel demand for CI101's item codes and must be
     counted**, not excluded by default the way PEM101's own much-smaller 0.42% exclusion was.
  4. **PEM103's Tendering-channel scope decision** — 65.5% of its item-code value is currently out
     of the Omni-Channel-only scope; a business call on whether Distribution Transformer
     tendering activity belongs in this project's forecasting scope.
  5. **PEM104's volume question** — is 12 transactions genuinely the complete picture for these
     12 item codes, or does real PEM104 volume flow through an uncaptured division/channel? This
     is the blocking question for PEM104 specifically.
  6. **Per-division no-history-item classification** (exclude vs. placeholder, following PEM101's
     own Phase B precedent) has not been done for any of the five divisions — each Validator only
     identified the candidate items and their trace status. **Quantified precisely for the full
     445-code scope by the 2026-09-04 full-scope re-validation**: 105 of 445 codes have no
     Omni-Channel history anywhere, 16 already covered by the existing 128-item-scope config lists
     (consistent, no conflicts), 89 not yet classified by any list. **CHARACTERIZED (not yet
     classified) 2026-09-07** — see the Phase C step 1 REVISED dated log entry above and
     `output/summary/phaseC_89items_characterization_report.md`: sibling/concentration groups
     (balanced 57, dominated-by-one-item 22, no siblings with history 6, Type-undefined 4) and
     trace-evidence groups (Cube_CES trace 29, quotation-only 23, weak trace 12, no trace 25) are
     now known, but the exclude/placeholder/other MECHANISM decision itself is still not made —
     this is Phase C Step 2 task list item 2 (Current Status Summary above).
  7. Minor pricelist data-quality items not investigated further, per the stopping rule: the
     `DS-F-99-0308` within-sheet pricelist duplicate (CI101; also explains the project's existing
     446-rows-vs-445-codes note in Section 1); PEM107's 4 likely "xxx"-placeholder codes and 2
     trailing-period near-duplicates; PEM103's `TF-F-99-2107221B1`/`.` near-duplicate; PEM102's 3
     items carrying an unrelated "Instrument Transformer" category on some rows.
  8. **No Modeler has yet backtested any of the five divisions** — every readiness and
     transferability judgment from Phase C step 1 (and its 2026-09-07 revision for PEM102/PEM107/
     CI101) is based on data-quality/demand-shape evidence only, not measured model performance.
     This is Phase C's next step, not yet started.
  9. ~~The PEM104 overlap (found 2026-09-07)~~ — 7 of the 89 no-history codes (item 6 above) sit on
     the PEM104 sheet, which is already excluded from forecasting entirely for an unrelated
     data-volume reason (item 5 above). Whether that division-level exclusion already covers these
     7 items' placeholder question, or whether they still separately need the same
     exclude/placeholder-mechanism decision as the other 82, was left as a genuinely two-sided
     question (both readings stated in full in `phaseC_step1revised_synthesis_report.md`
     Deliverable 2). **DECIDED 2026-09-07 (Phase C step 2, Part 0b): treated as excluded under
     PEM104 — the division-level exclusion subsumes the item-level placeholder question for these
     7.** The 89-item placeholder-pending population's actionable count is now 82.
  10. ~~A 9-item `Cube_CES`/`cube_Sale_APD` cross-table gap (found 2026-09-07)~~ — 9 of the 89
      no-history codes have a real `Cube_CES` Omni-Channel Actual/Backlog row with NO counterpart
      anywhere in the full-history `cube_Sale_APD` pull. **EXPLAINED 2026-09-07 (Phase C step 2,
      Part 0c), high confidence, single direct check**: all 19 matching rows are `Status='Actual'`
      (delivered, not Backlog), dated entirely in 2023 (`CtrDate` 2023-03-04 to 2023-10-25;
      `ActualDelDate` 2023-03-20 to 2023-11-15) — before `cube_Sale_APD`'s 2024-01-01 window and
      several divisions' own structurally-absent-before-2024 boundary. A table-coverage-window
      gap, not a data-integrity problem. Full list: `phaseC_9item_cubeces_check.csv`.
  11. **Whether PEM101's own production pipeline query has been updated** to drop
      `division='PEM101'` as a filter, consistent with the 2026-09-04 correction. **RESOLVED
      2026-09-07 (Phase C step 2, Part 0a): confirmed clean by direct grep of every active
      pipeline script — no fix was needed, the 2026-09-04 fix was never reverted.** PEM101's
      +1.22% aggregate shift (all 171 sheet codes) and `load_data_full.py`'s own +0.29% (its
      128-item Fuse+Surge Category subset) are consistent, different-scope figures, not a
      contradiction.

## 6. Missing Data by Phase

- **Phase 2 and 3.1 (item-level pilot)**: needed nothing beyond the sales data already
  available.
- **Phase 3.2**: needs utility budget data from PEA, MEA and EGAT, EGP bid announcements, and
  sales team insight. Collection format not yet agreed.
- **Phase 4**: must be requested externally — none of the following exist in the database as an
  authoritative, item-level figure (updated 2026-09-02 after the warehouse-flow follow-up
  investigation, which corrected two earlier assumptions — see Locked Decisions above — and
  RESOLVED the planning-unit question below):
  - ~~Confirmed procurement lead time per item, from purchasing.~~ The stated 45-60 days is the
    business's own figure for ordering parts, not something this project can derive or verify
    end-to-end from data. Still needed as the authoritative starting segment of total lead time.
    **RESOLVED BY THE BUSINESS, 2026-09-04 — moved to Section 8: 45-60 days confirmed as
    previously stated, and configurable per item.** Assembly time after parts arrive stays open
    (see next item).
  - **Assembly/production time, from raw-material issue to the resulting Finished Good becoming
    stock.** Confirmed a HARD gap (2026-09-02): no field in any table links a raw-material
    consumption event to the resulting assembled item later becoming stock. Cannot be derived
    from data under any query design — must come from production/the business. **STILL OPEN as of
    2026-09-04 (Section 8) — the business reconfirmed lead time (above) but left this
    unanswered.**
  - ~~Minimum order quantities and lot sizes.~~ No field states these directly. 68 of 82
    testable items show quantity-clustering evidence consistent with a lot size (2026-09-02
    prep investigation) — suggestive, not sufficient to set a value. **REMOVED FROM THE DATA
    REQUEST LIST, 2026-09-04 — moved to Section 8: business confirmed this data does not exist.
    Phase 4 must be designed without it.**
  - **Make-versus-buy classification per item.** FG/RM split is known with high confidence
    (122/128 FG, 6/128 RM, earlier Phase 4 groundwork survey); whether any FG item is genuinely
    dual-sourced (made in-house AND sometimes bought complete) remains unanswerable from data.
  - **Target service level.** No data source addresses this at all. **STILL OPEN as of
    2026-09-04 (Section 8) — the business has not set one; Phase 4 will present several levels
    for the business to choose from.**
  - ~~Whether stock is planned per warehouse, per business unit, or company-wide~~ —
    **RESOLVED 2026-09-02 by business correction, confirmed by data.** Warehouses are process
    stages, not business units or independent planning locations. Phase 4 plans at ITEM LEVEL
    across all warehouses combined; confirmed transfers between warehouses mean a per-warehouse
    model would double-count. ~~Which specific stage(s) hold sellable Finished Goods stock (as
    opposed to `QA`/`FMTS`/`FMTO`, confirmed not-yet-available) still needs business
    confirmation — no sales table has a warehouse field to verify this from data.~~ **CHANGED
    2026-09-04 — moved to Section 8: no longer requested from the business as a question; to be
    DERIVED directly by reading `Cube_Inventory_Exact` (the current-stock snapshot) for these
    items.**
  - **Finished-goods movement history** (Phase D groundwork item, Section 1/Current Status
    Summary). **REMOVED FROM THE DATA REQUEST LIST, 2026-09-04 — moved to Section 8: business
    confirmed this data does not exist. Phase 4 must be designed without it.**
  - **Whether stock for `EEE-F-FC-1040010002`'s Tendering-channel sales (division `PPS`, see the
    Cross-division-demand Locked Decision above) is the same physical stock as this project's
    Omni Channel items** — previously an open question for the warehouse team.
    **REMOVED FROM THE DATA REQUEST LIST, 2026-09-04 — moved to Section 8: business confirmed
    this data does not exist. Phase 4 must be designed without it.**

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
  **UPDATED 2026-09-04 (Section 8): holding cost now has an approximation method from the
  business (current stock qty × unit cost from the sales table, `Cube_Inventory_Exact` +
  `cube_Sale_APD`) — capital tied up, not an annual carrying cost, so an annual carrying rate is
  still needed as a Phase 4 configurable assumption. Stockout cost still has no source; the
  business suggested a lost-margin-from-`saleGM` proxy, to be used as a stated assumption, not
  measured. Target service level is still not set — Phase 4 will present several levels for the
  business to choose from, per Section 8.**
- **The project has never been compared against the team's current working method.** Every
  result so far (model accuracy, bias, on-time delivery) is reported in isolation; none of it has
  been measured against what the team already does without this project. Its value is therefore
  unproven, not just unquantified. This is what Phase F is for.
- **The problem may be smaller than assumed, and is already improving without intervention.**
  On-time delivery rose from 57.8% to 73.2% (2023 to 2026, partial year) with no forecasting or
  inventory system in place. Phase F must estimate what a no-intervention baseline looks like
  going forward, since some or all of the apparent opportunity may already be closing on its own.
  **[SUPERSEDED as a fill-rate benchmark — Phase J2, 2026-09-23: on_time_exact, row-weighted,
  PEM101 only — see METRICS.md Sec.19 and the corrected `not_late` by-year series above.]**

## 8. Resolved and Closed Questions (Business Input, 2026-09-04)

The user answered several previously-open questions and closed others on 2026-09-04. Recorded
here as a dedicated resolved section, per instruction — the original open-question and
Locked-Decision entries above are **not deleted**, only annotated in place with a pointer to this
section, so the history of what was asked and when is not lost. **Every item below is a
business-confirmed answer, not independently verified against data by this project (this was a
documentation task only, per instruction — no analysis or code changes were made to check these
claims) — each may be revised if new information arrives.**

### 8.1 Resolved by the business

- **PEM102 ↔ PEM107 `-OLD` division-tag mechanism (open since 2026-09-04, resolved 2026-09-04).**
  The two divisions were reorganised: rows tagged `PEM102-OLD` are `PEM107` products; rows tagged
  `PEM107-OLD` are `PEM102` products. This directly confirms the pricelist-as-source-of-truth
  decision (`CONVENTIONS.md`; STATUS.md Locked Decisions, "Division source-of-truth correction")
  and explains the mirror pattern Phase C step 1 found (each division's real activity sitting
  under the *other* division's `-OLD` tag) — it is exactly what a division-code reorganisation
  would produce. Originally recorded as Phase C step 1 residual item 1 (Section 5) and referenced
  in the Phase C step 1 dated log entry and the "Division source-of-truth correction" Locked
  Decision (Section 4) — both left in place, annotated, not deleted.
- **Lead time: 45-60 days from ordering parts to assembly, as previously stated (reaffirmed
  2026-09-04).** Configurable per item — not a single fixed value across all items. **Assembly
  time after parts arrive remains open** — the business reaffirmed the procurement segment but
  did not answer the assembly segment; see §8.5 below. Originally recorded in the "45-60 day lead
  time" Locked Decision (Section 4) and Section 6's Phase 4 missing-data list — both annotated,
  not deleted.

### 8.2 Closed without pursuit

- **The February-July 2026 (origin-7) rolling-origin-vs-train/val/test window anomaly (found
  Phase B1/B4, closed 2026-09-04).** Three candidate causes were tested and ruled out: the
  createDate/PODate back-dating mechanism (Date-column Validator, high-confidence negative
  finding); the dominant focus item `EEE-F-FC-1040010002` as sole cause (Modeler Task 1, the
  reversal persists — and actually strengthens at Type level — once the item is excluded); and an
  item-and-window-specific order-timing/large-order concentration pattern (Modeler Task 1 part 2 —
  real and specific to this item and window, but explicitly found insufficient to explain the
  aggregate-level reversal by itself). **No further investigation will be made.** Recorded as a
  **known limitation** of this project's data/modelling — and it is the direct reason this
  project's evaluation policy treats rolling-origin (all 7 origins pooled) as PRIMARY and the
  single train/val/test split (which happens to land on this exact anomalous window) as SECONDARY
  ONLY (Section 4, "Final forecasting method" and "Evaluation policy" Locked Decisions). Originally
  recorded in the "Date-column Validator residual items" open question and the "What Tasks 1-3
  could not resolve" log entry (both Section 5 / the dated log above) — both annotated, not
  deleted.
- **Why `EEE-F-FC-1040010002` fell in 2025 (found Phase A, closed 2026-09-04).** Cannot be
  answered from internal data — the business has confirmed this, not merely this project's own
  read-only-data limitation. **Deferred to Phase 3.2**, where external factors (utility budgets,
  EGP bid announcements, sales team insight — see Section 6, Phase 3.2 missing-data note) will be
  examined. Originally recorded as part of the "Phase A residual items" open question (Section 5)
  — annotated, not deleted.

### 8.3 Removed from the data request list

Business has confirmed the following data does not exist. **Phase 4 must be designed without
them** — they are not merely unanswered, they are no longer being requested:

- **Finished-goods movement history.** Was part of Phase D's original three-item groundwork scope
  (Section 1, Current Status Summary) — both updated to reflect Phase D's narrower scope (§8.4
  below).
- **Minimum order quantities and lot sizes.** Was part of Phase 4's missing-data list (Section 6)
  — annotated, not deleted. The 2026-09-02 quantity-clustering evidence (68 of 82 testable items)
  remains recorded as suggestive-but-unused evidence; no value will be set from it since the
  authoritative figure will never be provided.
- **Which stock serves the Tendering channel for `EEE-F-FC-1040010002`.** Was recorded as an open
  question for the warehouse team in the "Cross-division demand" Locked Decision (Section 4) —
  annotated, not deleted.

### 8.4 To be derived from `Cube_Inventory_Exact` instead of requested

Rather than asking the business, these three are to be read directly from `Cube_Inventory_Exact`
(the current-stock snapshot table, Section 2 database inventory). **This is a data-source
decision, not yet an executed analysis** — reading the table and deriving the actual values is
separate, not-yet-done work (this task made no code changes or queries, per instruction):

- **Which warehouse stages hold sellable stock.** Previously an open item needing business
  confirmation (Section 4, "Warehouses are STAGES of one process" Locked Decision; Section 6) —
  both annotated, not deleted. To be read from the inventory snapshot rather than asked.
- **Holding cost.** Approximate as current stock quantity × unit cost from the sales table —
  giving the capital value tied up in inventory. **This is capital tied up, not an annual
  carrying cost** — an annual carrying rate will still need to be set as a configurable
  assumption in Phase 4, since it is not available from any source. Previously recorded as part
  of "No cost data exists" (Section 7, Red Team Review Findings) — annotated, not deleted.
- **Whether CI101-sheet products sold under `PEM101` are held in `PEM101` stock.** Relevant to
  the CI101↔PEM101 cross-division finding (Phase C step 1; STATUS.md Locked Decisions, "Project
  scope correction"). To be checked directly against the inventory snapshot for those items, not
  asked of the business.

### 8.5 Still open (reaffirmed, not resolved)

- **Stockout cost.** No source identified. A proxy using lost margin from `saleGM` may be used,
  noted explicitly as an assumption if adopted, not a measured figure.
- **Target service level.** Not yet set. Phase 4 will present several levels for the business to
  choose from, rather than this project picking one.
- **Assembly time after parts arrive.** Still unknown — see §8.1 above (lead time was reaffirmed,
  assembly specifically was not answered).

### Consequence for Phase D

The data search for Phase 4 groundwork is now **narrower**: three checks against
`Cube_Inventory_Exact` (§8.4 above) rather than a search across all tables. Phase D's description
is updated accordingly in Section 1 and the Current Status Summary (Phase D entries) — both
directly rewritten to reflect this narrower scope, per instruction, rather than only annotated
here.

## 9. Framework Alignment (Best-Practice Review, 2026-09-07)

A best-practice review compared this project against established forecasting frameworks, so the
project's position is visible before Phase C continues. Recorded factually — deviations are
stated plainly, not softened.

### CRISP-DM lifecycle

The project followed the standard sequence — data understanding, data preparation, modelling,
evaluation — and has deployment infrastructure in place (the GitHub Pages dashboard, Phase 1;
`src/run_pipeline.py`, Phase B closeout).

**One deviation: business understanding came late.** Facts about how the business actually
operates were discovered during Phases B and C, not established at the start:
- 6-day median customer order notice (Section 3, Business Findings — found investigating Phase 2
  bias, not at project start).
- 73.2% on-time delivery, up from 57.8% (Section 3, Business Findings — same origin).
  **[SUPERSEDED as a fill-rate benchmark — Phase J2, 2026-09-23, METRICS.md Sec.19.]**
- The existing min/max inventory settings are unusable as an input (Locked Decisions, "The
  existing min/max values in the inventory system cannot be used as inputs to any calculation" —
  found 2026-09-02, well into the project).
- The actual planning purpose (item-level Max-Min inventory policy, not a monthly sales accuracy
  target) only became fully clear once these facts were known.

Several rounds of this project's early work (the Phase 2/3.1 model-selection backtests, the
rule-based-selection investigation) were spent searching for the most accurate monthly forecast.
Knowing these facts earlier would likely have redirected that effort sooner — toward the
item-level, stock-availability-driven planning problem this project now understands itself to be
solving, rather than monthly forecast accuracy as an end in itself. **Recorded as a lesson, not a
blocker**: none of the Phase 2/3.1 work is discarded (Combination forecasting and the six-model
comparison remain the adopted method — Locked Decisions, "Final forecasting method"), but the
sequencing cost real effort that a more CRISP-DM-faithful business-understanding-first start would
likely have avoided.

### Hierarchical forecasting

The project tested three of the four standard reconciliation approaches: **Direct**, **Top-down**,
and **Reconciled** (Phase B3, Locked Decisions "Final forecasting method: Top-down combination").
**Minimum-trace (MinT) optimal reconciliation was not tested.**

**Decision: not pursued, deliberately, not by oversight.** MinT requires estimating an error
covariance matrix across the reconciled series, which would be unstable on this project's series
lengths (31 to 43 months, depending on which backtest window) — too few observations relative to
the matrix's parameters to estimate it reliably. Recorded as a deliberate scope choice with its
reason, not a gap left unexplained.

### Forecast Value Added (FVA)

The project has consistently used a naive benchmark throughout — Phase 3.1's original backtest,
every subsequent re-test (B1, B3, Modeler Tasks 1-3), all included Naive — in line with FVA
practice (the benchmark a "value-adding" model must beat is a naive forecast, not a null model).

**The finding that Naive won outright on 35 of 58 pilot items (Phase 3.1 backtest) is consistent
with published FVA evidence that roughly half of real-world forecasts fail to beat a random walk,
and is not, by itself, a failure of this project's method** — it is the expected shape of the
result for demand this intermittent/lumpy (74% Intermittent or Lumpy at the Phase 1 classification
stage), not evidence the modelling work was done wrong.

**The FVA step this project has not yet done: comparison against the team's current working
method** — not against a naive statistical benchmark, but against what the planning team actually
does today without this project. **This is Phase F** ("Measure the value" — Section 1; also
Section 7, Red Team Review Findings, "The project has never been compared against the team's
current working method").

### Intermittent-demand practice

Standard intermittent-demand practice is in place: ADI/CV² classification (Phase 1 onward), the
Croston and SBA models (Phase 2/3.1 onward), and combination forecasting as the adopted method
(Locked Decisions, "Final forecasting method").

**The missing step: evaluation on inventory metrics, not forecast accuracy alone.** This project's
evaluation to date is entirely in forecast-accuracy terms (MAE, RMSE, Bias) — it has not yet
measured what those forecasts do to an actual inventory policy (service level achieved, stockouts
prevented, capital tied up in safety stock). **This is Phase E** ("Phase 4 proper: calculate
Max-Min and simulate it against historical demand" — Section 1).

---

**Rule: this file must be updated as the final step of every completed task.**
