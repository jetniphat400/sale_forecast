# Phase A — Synthesizer Report

**Role**: Synthesizer (per `AGENTS.md`). Merges A1 (Explorer+Validator, forecast_date revision),
A2 (Analyst, 2025 decline), A3 (Validator, date-keying) — no new data gathered, no query run, no
script written, per role boundary. Source reports: `output/summary/phaseA_a1_forecastdate_revision_findings.md`,
`phaseA_a2_2025_decline_findings.md`, `phaseA_a3_date_keying_findings.md`. STATUS.md and
CONVENTIONS.md read in full before writing this.

---

## 1. Merged findings and cross-checks between the three investigations

### A1 ↔ A3: does A1's finding let A3's conditional recommendation stand?

A3's report is explicit: its recommendation to key the demand series on `forecast_date` is
"explicitly conditional" on whether A1 finds `forecast_date` is revised after PO intake. A3 states
that if revision is found, the *direction* of its recommendation still holds (delivery-due-date is
still the conceptually correct planning anchor) but the series would need to be captured as a
frozen snapshot rather than treated as a live re-queryable history, to satisfy CONVENTIONS.md's
reproducibility rule.

**What A1 actually found, precisely** (not paraphrased): A1 did **not** confirm `forecast_date` is
a fixed PO-intake promise, and states this explicitly as "Unresolved — stated plainly, not
guessed." Three independent tests found no positive evidence of revision (Task 3a: 0 of 68
same-`createDate` groups show a revised single obligation, all explained by legitimate split-lot
quantity differences; Task 3b: only 6 of 159 multi-`PlanID` pairs are even ambiguous, 0.033% of
rows, and manual inspection could not resolve them either way; Task 3c: no audit/history table or
per-row modification-timestamp column exists anywhere in the database, so **revision-in-place is
fundamentally undetectable from this data, not merely "not found"**). A1 also bounds the impact:
every revision-candidate footprint found across all tests caps out under ~2.5% of rows, with no
consistent direction, which A1 concludes is "high confidence" too small to be the primary driver
of the 15-point on-time-by-year swing or the 6-day median-notice figure.

**Resolution (my judgment, since A3 asked the Synthesizer to make this call)**: A3's recommendation
**stands, with a caveat, not blocked**. Reasoning: A3's own stated condition for "blocked" was
finding that `forecast_date` **is** revised; A1 did not find that — it found an inability to rule
revision out, combined with a high-confidence bound that any revision is small (≤2.5% of rows,
no consistent direction). A3's own fallback for the "revision found" branch (capture the series as
a frozen snapshot at time of use, not a live re-query) is a reasonable, low-cost defensive practice
regardless of which way the unresolved question eventually settles, and is already consistent with
CONVENTIONS.md's "record data cutoff date" rule. **Practical instruction for whoever implements
this**: re-key the demand series on `forecast_date`, but freeze/snapshot the `forecast_date` values
used for any past period at the time of that computation (do not silently re-pull and let past
months' figures drift), and re-run this bound periodically if the volume of multi-`PlanID`/
disagreement cases grows. **Confidence: moderate-to-high** on this resolution (inherits A1's
"high confidence" bound and A3's "moderate-to-high" direction; the residual uncertainty is that
neither agent could positively confirm fixedness, only bound its practical consequence).

### A2 ↔ Phase 2/3.1 bias question: does A2's decline driver support or complicate the "artifact vs. real" question?

STATUS.md frames the Phase A2 question as: is the well-below-average 2025 demand that every model
is trained on a real property of demand, or a reporting/classification artifact — because if
models are trained on a depressed 2025 and tested on a recovered 2026, the observed under-
forecasting bias (Phase 2/3.1: all six models under-forecast on average) may itself be a train/test
regime-shift artifact rather than a stable property to size safety stock against.

A2's answer is **not a clean yes/no** and genuinely complicates the bias question rather than
settling it:

- **Mostly real, not an artifact, at the aggregate level.** No whole-population step-change/cliff
  exists at the 2024/2025 boundary (unlike the 2022/2023 and 2023/2024 breaks); no aggregate
  `revenue_type`/`status` shift explains it; the whole PEM101 division fell similarly (-29.1%), not
  just the Omni-Channel slice. 51% of the entire decline traces to one item
  (`EEE-F-FC-1040010002`, also one of this project's three locked focus items) with a **flat unit
  price throughout** — a genuine volume collapse-and-recovery, not a price, mix, or classification
  effect. This item is separately the largest driver (46.5%) of the 2025→2026 recovery — i.e. it is
  the same real item swinging both directions.
- **But a real, non-trivial customer-reclassification confound exists underneath that.** Of the 127
  customers who appear to have "dropped" after Jan-Jul 2024, 26 (20% by count, but 58.5% of that
  cohort's ฿46.24M value) in fact continued doing business at growing scale, just relabeled from
  Omni-Channel/PEM101 to `Tendering` or another division — driven by 2-3 large accounts, notably
  `CS07977` (-฿15.27M of the -฿64.77M headline decline, 23.6% of it alone), whose company-wide
  Omni-Channel activity fell to zero while its Tendering activity rose to ~฿263M. This is a genuine
  scope-boundary artifact, not lost demand.

**How this bears on the bias question (my synthesis, not stated by any single agent)**: the
dominant driver of the "depressed 2025" training data is a real, single-item volume swing, so the
bias is not manufactured by a reporting error — but the fact that one item, sitting inside the
Phase 2/3.1 backtest's actual test window (last 6 of 31 months, which falls inside the
2025→2026 recovery period A2 examined), swung by tens of millions of baht on its own, means a
material share of the *measured bias magnitude* specifically (not its mere existence) is plausibly
inflated by this one atypical collapse-recovery cycle landing inside the train/test split, separate
from the item-agnostic reason already recorded in STATUS.md (point forecasts target the mean while
real demand contains spikes). **Neither A2 nor any other agent isolated this — no one recomputed
bias with this item held out, or checked whether its own per-model bias is disproportionate to the
rest of the scope.** This is a genuine, currently-untested gap connecting the two workstreams (see
§5). Additionally, the reclassification confound means a portion of the *customer-level* narrative
behind the depressed 2025 (as opposed to the item-level narrative) is a scope artifact, which could
also bias any customer-segmented analysis of the training data — again not tested here.

### No direct conflicts between the three reports

A1, A2 and A3 investigate different mechanisms and do not contradict each other on any shared
factual claim. Where they touch the same ground (A1's and A3's shared reliance on `forecast_date`
being the contractual delivery date; A1's finding that `forecast_date`≈`ForecastDelDate` at 100%
match, consistent with A3 treating them interchangeably) they reinforce rather than conflict.

---

## 2. Direct answers

### 2a. Can the 6-day median order notice and 73.2% on-time delivery figures still be relied on?

**Yes, at high confidence, for the direction and rough magnitude — but the underlying "is
forecast_date ever revised" question remains formally open, not closed.** A1 found no positive
evidence of revision anywhere it could test, and — more importantly for this specific question —
bounded the *maximum plausible footprint* of any revision (found or not) at under ~2.5% of rows in
every test, with no consistent direction. A 15-percentage-point swing (57.8%→73.2%) or a 27,583-row
median calculation cannot plausibly be manufactured by a sub-2.5%, directionless effect.
**Confidence: high** that revision is not the explanation for these headline figures, evidenced by
three independent tests (Task 3a/3b/3c) all bounding the effect small. **Confidence: unresolved
(explicitly, per A1)** on whether `forecast_date` is fixed at intake at all — this is undetectable
from the current data model (no audit/history table exists), so it cannot be marked "confirmed,"
only "not shown to matter at the observed scale."

### 2b. Is the models' negative forecasting bias a real property of demand, or a train/test artifact?

**Mixed — genuinely both, not cleanly one or the other, at moderate confidence.** The demand pattern
underlying the bias (depressed 2025, recovered 2026) is substantially real (A2: no aggregate
reporting/classification cliff, dominant driver is a flat-price genuine volume swing in one item),
which argues the bias is not simply manufactured by a data artifact. But: (a) a meaningful minority
of the "depressed 2025" customer-level narrative is a scope/classification artifact (A2: 58.5% of
one dropped-customer cohort's value, ~23.6% of the whole headline decline from one account alone,
is relabeling not loss); and (b) the exact backtest window used to measure bias overlaps the same
period as the dominant item's real, unusually large recovery swing, which no agent has isolated
from the bias measurement. **Confidence: moderate** that the bias is a mix of a real structural
property (point forecasts vs. spiky demand, as already recorded in STATUS.md) and a magnitude
inflated by this specific, largely one-item-driven regime shift landing inside the test window.
**This specific quantitative decomposition (how much of the measured bias is attributable to this
one item/window vs. general demand shape) was not tested by any of A1/A2/A3 and is a genuine gap**
(see §5) — treating the current bias figures as a permanent, stable basis for safety-stock sizing
without this check carries real risk, exactly as STATUS.md's Phase A framing anticipated.

### 2c. Is the demand series currently keyed on the right date field?

**No, not currently — high confidence on the current state, moderate-to-high confidence
(conditional, see §1) on what it should be instead.** A3's direct code read (not inference) confirms
every production pipeline script (`load_data.py`, `load_data_full.py`, `aggregate_levels.py`,
`backtest.py`, `backtest_aggregate.py`) keys monthly aggregation on `createDate` (PO-received
date); `forecast_date` appears only in one-off investigation scripts that do not feed the pipeline.
Given the business need (stock available by the contractual delivery date), this is the wrong key:
re-keying on `forecast_date` moves 11.53% of quantity and 14.98% of value to a different calendar
month, materially affects 86.6% of the 112 comparable items in at least one month, and — most
importantly for inventory risk direction — makes 72,889 already-placed, already-contractually-due
units (2.15% of scope demand, 64,134 of them due the very next month) **invisible** to a
`createDate`-keyed model because they fall beyond its observed window. **Confidence: high** on all
of the above (direct recomputation, reconciles to the unit). Per §1, the recommendation to switch
now stands with the stated caveat (freeze/snapshot forecast_date values at time of use) rather than
being blocked by A1's unresolved revision question.

---

## 3. What must change in the project's conclusions / STATUS.md

(For the user/Orchestrator to apply — not applied by this report.)

- **Phase A status line** ("NEXT, not blocked") should move to done/answered, with the three
  answers above (2a/2b/2c) recorded, including their confidence levels and the residual open items
  in §5 — not a clean "resolved," since none of the three questions closes without caveat.
- **Section 3 "Business Findings"** — "Customers give almost no order notice" (6-day median) and
  "On-time delivery has improved... 73.2%... up from 57.8%" should get an added note: A1
  (2026-09-02) bounds any date-revision effect at under 2.5% of rows with no consistent direction,
  too small to explain either figure — the figures are reinforced, not overturned — but whether
  `forecast_date` is ever revised in place remains formally unresolved and is, by construction,
  undetectable in this database (no audit trail exists).
- **The Phase 3.1 "Data-quality caveat carried forward"** note (STATUS.md, "an earlier investigation
  found forecast_date sometimes steps forward across a contract's repeated rows... Not resolved
  here") should be **updated, not silently left as-is**: A1's Task 3a specifically re-tested this
  exact pattern and found every flagged case (68 groups, 158 rows) carries a different qty/sale
  value across rows — the established split-lot signature, not a revised single obligation. This
  narrows the caveat considerably (it is very likely explained, not merely "not resolved"), but does
  not fully close it — 2 of A1's 6 ambiguous `Backlog`-status multi-`PlanID` pairs remain
  structurally indistinguishable from genuine revision (no `ActualDelDate` yet to check against).
- **Phase 2's "all methods under-forecast on average... must be compensated through safety stock in
  Phase 4"** claim needs an added caveat, not a retraction: per §2b, a meaningful but unquantified
  share of the measured bias magnitude may be inflated by one real, large, item-specific
  collapse-recovery cycle sitting inside the backtest's test window, rather than being a stable
  general property of demand. Locking a Phase 4 safety-stock policy to the current bias figures
  without first isolating this item's contribution risks baking in a one-time event's magnitude, not
  just its direction — the risk STATUS.md's own Phase A framing already anticipated is now partly,
  not fully, confirmed.
- **New concrete action item for Phase B** (not previously in STATUS.md as a code-change item): the
  demand series feeding forecasting/backtesting is keyed on the wrong field per business need.
  Before Phase B closes Phase 2 down to item level, `src/load_data.py`, `load_data_full.py`,
  `aggregate_levels.py`, `backtest.py`, and `backtest_aggregate.py` should be re-keyed to
  `forecast_date` (with the snapshot/freeze caveat from §1), since Phase B's item-level rebuild will
  otherwise inherit the same 11.53%/14.98% misallocation and the 2.15% invisible-future-demand gap
  A3 quantified.
- **Section 7 Red Team point** ("the problem may be smaller than assumed... 57.8%→73.2% with no
  system in place") is **reinforced, not weakened**, by A1: the improvement does not appear to be an
  artifact of date rescheduling. Phase F's planned no-intervention-baseline comparison remains
  necessary regardless.
- **Phase A item 2 ("why did 2025 sales fall 26%")** should record: not a full-year phenomenon (only
  -7.2% for calendar 2025 vs. 2024; the -25.7%/-26% figure is specific to the Jan-Jul window); 51%
  of the decline traces to one item's real, flat-price volume collapse-then-recovery; no aggregate
  classification/reporting artifact found, but a real, quantified, partial customer-reclassification
  effect exists for a minority of large accounts (driven by 2-3 accounts, notably `CS07977`); root
  cause of the dominant item's buyer-base pause is unresolved and needs business input (stock,
  supply, or contract-cycle data this project cannot see).

---

## 4. Explicit contradictions with what STATUS.md currently records

Checked deliberately, per the Synthesizer's obligation not to silently reconcile: **no direct
factual contradiction was found** between any of A1/A2/A3 and STATUS.md's existing content. The
closest candidates, examined and resolved as **refinements, not contradictions**:

- STATUS.md's Phase 3.1 caveat says forecast_date "sometimes steps forward across a contract's
  repeated rows... this script cannot rule out that forecast_date reflects a continuously-updated
  latest plan." A1 does not contradict this — it directly investigated the same stepping-forward
  pattern and found a specific, evidenced explanation (legitimate split-lot quantity differences)
  for the cases it could test, which **sharpens** the earlier caveat toward "very likely explained"
  rather than overturning it. Both statements can be true: the pattern exists, and its most likely
  cause is now identified, but not with 100% certainty (2 ambiguous cases remain).
- A1's Task 2 (~2.5% `forecast_date` vs. `PlanDelDate` disagreement) and STATUS.md's existing
  "PlanDelDate and ForecastDelDate are literally identical on 97.9% of assessable rows" (Phase 3.1
  delivery baseline) are **consistent, not contradictory** — 97.9% match ≈ 2.1% mismatch, close to
  A1's 2.52% on a fresh, slightly different pull/scope; the small numeric gap is attributable to
  scope/sample differences (A1 states this class of drift explicitly elsewhere in its own report),
  not a conflicting finding.

**Verdict: no unresolved contradiction to flag as an either/or choice between agents or against
STATUS.md.** Confidence: high (both reports were read in full specifically to check for this).

---

## 5. Unresolved items across all three investigations (stopping-rule outputs)

| # | What was checked | What would settle it | Which team must supply it |
|---|---|---|---|
| 1 | Whether `forecast_date` is ever revised in place after PO intake (A1) | A genuine per-row audit/change-history table, or a periodic snapshot series capturing the field's value at multiple points in time for the same obligation (neither exists today) — or direct confirmation from IT/the business of the write pattern | IT (schema/audit capability) or the business (confirm whether dates are ever rescheduled and under what circumstance) |
| 2 | The ~2.3-3.2%-of-rows `forecast_date` vs. `PlanDelDate` disagreement's cause (A1) — direction is mixed, no pattern found | Business-side explanation of why these two fields, both meant to represent planned delivery, occasionally diverge by up to hundreds of days | The business/IT team owning `Cube_CES` and `cube_Sale_APD`'s source systems |
| 3 | 2 of A1's 6 ambiguous `Backlog`-status multi-`PlanID` pairs, equal `PlanQty`, ~5 weeks apart, no `ActualDelDate` yet | Wait for these to deliver (an `ActualDelDate` will appear) and re-check, or business confirmation of whether these specific contracts are known to have had a reschedule | Time (re-check later) or the business |
| 4 | Root cause of why ~36 buyers of `EEE-F-FC-1040010002` paused in H1 2025 and ~30 resumed in H1 2026 — the single largest driver of the whole "26% decline" (A2) | Stock-availability/stock-out history, supply/production disruption records, or contract-renewal cycle information for this item in H1 2025 | The business (stock, supply, or sales/contract team) — no stock-level or supply table exists in this database (confirmed, Phase 4 groundwork) |
| 5 | Whether the 101 of 127 "dropped" customers with zero activity anywhere post-2024 are genuinely lost or simply dormant (A2) | Account-status confirmation for at least the largest few (`CS07521` -฿5.88M, `CS01191`'s PEM101 slice -฿4.59M, `CS05938` -฿3.25M) | The sales/account-management team |
| 6 | The specific mechanism behind `CS07977`'s and `CS00477`'s Omni Channel → Tendering relabeling (A2) | No audit trail exists (confirmed, same 108-table search as the 2022/2023 break) — needs direct confirmation of whether the underlying purchasing basis genuinely changed or this is a classification-convention change | The sales team who classifies `revenue_type` |
| 7 | How much of the Phase 2/3.1 measured forecasting bias is attributable to the `EEE-F-FC-1040010002` collapse-recovery cycle landing inside the backtest's test window, vs. a general demand-shape property (my own synthesis gap, §2b/§1 above — not tested by any of A1/A2/A3) | Re-run/decompose the existing bias calculation with this item (and/or its Type) held out or isolated, and check whether its per-model bias is disproportionate to the rest of the scope | The Modeler (this is model/backtest work, outside Analyst/Validator/Synthesizer scope) |
| 8 | How a real Max-Min/safety-stock policy would actually respond to A3's measured re-keying shift (A3) | Simulate both keyings against a candidate policy | The Modeler, in Phase E (explicitly out of Validator/Synthesizer scope) |
| 9 | Whether A3's 53 exact-duplicate rows (in this specific 8-column extract) overlap with the project's previously-classified duplicate-vs-split-lot sets (A3) | A targeted join on `contractid`+`itemcode` against `task7_final_revised_classification.csv` | Explorer/Validator, a small targeted follow-up if the Orchestrator wants it — not chased here per the stopping rule |

---

## 6. Confidence-level index (all conclusions stated above, gathered in one place)

| Conclusion | Confidence | Evidence basis |
|---|---|---|
| A3's forecast_date-keying recommendation stands, with a caveat (not blocked) | Moderate-to-high | A1's high-confidence bound on revision impact (≤2.5% of rows, no consistent direction) + A3's own stated fallback (snapshot/freeze) |
| A2's decline driver is mostly real (item-specific volume swing), with a real but partial customer-reclassification confound | High (real vs. artifact split); moderate (58.5%/26-customer ratio generalizing) | A2's direct computation, cross-validated; explicitly flagged by A2 as driven by 2-3 large accounts |
| 6-day median notice / 73.2% on-time figures are not explained by date revision | High | A1: three independent tests, all bounding revision footprint under 2.5% of rows |
| Whether `forecast_date` is fixed at PO intake | Unresolved (explicitly, not guessed) | A1: no audit/history table or modification-timestamp column exists anywhere; fundamentally undetectable |
| Under-forecasting bias is a mix of real demand shape and train/test-window inflation, not cleanly either | Moderate | A2 (real volume swing) + STATUS.md's existing structural explanation + an unquantified gap (§5, item 7) neither closes nor confirms |
| Demand series is currently keyed on the wrong field (`createDate` instead of `forecast_date`) for inventory-timing purposes | High (current state); moderate-to-high (recommendation) | A3: direct code read of all 5 pipeline scripts; direct recomputation of the reallocation magnitude |
| No direct contradictions exist between A1/A2/A3 or against STATUS.md | High | Both reports and STATUS.md's relevant sections read in full specifically to check |
