# Phase A / Task 3 — Validator Findings: Date-Field Keying of the Monthly Demand Series

**Agent**: Validator. **Date**: 2026-09-02. **Scope**: 128 item codes, Product Cate. Fuse and
Surge Arrester (`output/summary/part1_category_scope_all_codes.csv`), focus items
`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`.

No code, config/config.yaml, or data was modified. No values were committed or pushed. This
report and the CSVs listed at the end are the only outputs written.

---

## Task 1 — Which date field does each pipeline script actually key on?

Read directly, line by line, not inferred from filenames or docstrings:

| Script | Where the date field is used | Field used |
|---|---|---|
| `src/load_data.py` | `aggregate_monthly()`, line 145: `df["year_month"] = df["createDate"].dt.to_period("M")` | `createDate` |
| `src/load_data_full.py` | `aggregate_monthly()`, line 127: identical pattern | `createDate` |
| `src/aggregate_levels.py` | `determine_complete_months(monthly_df, raw_df, date_col="createDate")` (line 46) — `date_col` is a parameter, but it is **never called with any other value** anywhere in this file or in `src/backtest_aggregate.py`, which imports and calls it as `determine_complete_months(monthly, raw)` (positional/default only) | `createDate` (default, unoverridden) |
| `src/backtest.py` | `determine_complete_months()`, line 45: `max_date = pd.to_datetime(raw_df["createDate"]).max()` (hardcoded, not parameterized here) | `createDate` |
| `src/backtest_aggregate.py` | Imports `determine_complete_months` from `aggregate_levels.py` and calls it with defaults only (see above); does not itself reference `forecast_date` anywhere | `createDate` |

I also grepped every `src/*.py` file for `forecast_date` and found it used **only** in
investigation/one-off scripts (`order_leadtime.py`, `leadtime_actual_investigation.py`,
`leadtime_delivery_link.py`, `investigate_stock_availability_hypothesis.py`,
`investigate_leadtime_classification.py`, `verify_ces_*.py`) — none of which feed into
`load_data.py`, `load_data_full.py`, `aggregate_levels.py`, `backtest.py`, or
`backtest_aggregate.py`.

**Confirmed, not corrected: the orchestrator's summary is accurate.** All monthly series that
feed forecasting/backtesting in this project are keyed on `createDate` (PO-received date), and
zero of the production pipeline scripts reference `forecast_date`. **Confidence: high** — this
is a direct code read, not inference.

---

## Task 2 — Validation of `output/data/raw_order_leadtime_128items.csv`

**Provenance confirmed**: this file is the exact, unmodified output of `src/order_leadtime.py`
(run 2026-09-01), which pulls `itemcode, contractid, customerid, createDate, forecast_date, qty,
sale, status` from `cube_Sale_APD` for the 128-item scope, filtered
`division='PEM101'`, `revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
`createDate>=2024-01-01`. Row count in the file: **27,479** (27,480 lines including header) —
matches STATUS.md's own previously-reported figure for this exact script/scope to the row.
Reused as instructed rather than re-pulled, since its provenance and filters are independently
traceable and match.

**Checks performed directly on the file:**
- 27,479 rows. 0 null `createDate`. **1 null `forecast_date`** (0.0036% of rows) —
  `EEE-F-FL-1040030002`, `CTR-2024-02887`, createDate 2024-05-20, qty=3, sale=135 — matches
  STATUS.md's "1 row has no forecast_date" exactly.
- `createDate` range: **2024-01-03 to 2026-08-31**. `forecast_date` range (excluding the 1
  null): **2024-01-04 to 2027-05-31**.
- **Zero rows near 1970 or 2032 in either field**, and **zero createDate rows in the future**
  (max createDate 2026-08-31, one day before the stated "today" of 2026-09-02). This directly
  reproduces the orchestrator's quick check.
- **15 rows (0.05% of the 27,478 assessable rows) have a negative interval**
  (`forecast_date < createDate`) — matches STATUS.md's previously reported "15 rows (0.05%)"
  exactly. Sample inspected (see script output): these are small-quantity rows (mostly qty=3-4
  units) where `forecast_date` predates `createDate` by anywhere from 3 days to over a year
  (e.g. `CTR-2025-03513`: createDate 2025-07-03, forecast_date 2024-07-09, an 11-month negative
  gap). None of the 3 focus items appear among these 15 rows.
- 0 negative `qty`, 0 negative `sale`.
- **53 rows are exact full-column duplicates** (same itemcode+contractid+customerid+createDate+
  forecast_date+qty+sale+status) in this specific 8-column extract. This is a new count for this
  particular column combination and scope — not previously reported in exactly this form — but
  it is consistent with, and does not override, STATUS.md's already-recorded project-wide
  decision to keep all such rows in full (the false-negative rate of every duplicate-detection
  method tried previously was too high to safely drop rows). It does not bias the createDate-vs-
  forecast_date comparison below, since a duplicated row carries the same pair of dates in both
  keyings.
- 112 of the 128 scope items appear in this specific division/revenue_type/status/date-filtered
  pull; `part1_category_scope_all_codes.csv` shows 113 of 128 have history *anywhere* in the
  table (unfiltered). The 1-item gap means one code has sales recorded only outside this
  project's established division/revenue_type/status/date filters — consistent with, not
  contradicting, the already-documented cross-division and cross-channel exposure findings.

**Independent re-verification (not just reuse) — fresh, unfiltered live query** against
`cube_Sale_APD`, same 128 itemcodes, **no** division/revenue_type/status/date filter at all
(27,727 rows returned): `createDate` range 2024-01-03 to 2026-09-01, `forecast_date` range
2024-01-04 to 2027-05-31, **zero rows in either field near 1970 or near 2032**, 1 null
`forecast_date`. This independently reproduces the orchestrator's broader claim to the row and
confirms the 1970/2032 anomaly reported elsewhere for `cube_Sale_APD` **does not reach this
128-item scope**, with or without the project's standard filters.

**Conclusion: the file is validated and safe to reuse for tasks 3-5. Confidence: high** — both
the file's own content and a fresh independent DB query agree, and both reconcile exactly to
previously published STATUS.md figures with no contradiction found.

---

## Task 3 — Building both monthly series from the same rows

- **createDate-keyed** (matches current pipeline exactly): every row has a non-null
  `createDate`, so all 27,479 rows are used, grouped by `itemcode` + `createDate.dt.to_period("M")`.
- **forecast_date-keyed**: the 1 null-`forecast_date` row (qty=3, sale=135) is **excluded**,
  reported explicitly here (0.0036% of rows, negligible), rather than silently dropped. The 15
  negative-interval rows are **kept** in the forecast_date-keyed series — a negative interval is
  a business-meaning anomaly (delivery apparently promised before the order existed), not a
  missing or unparseable date, so there is no basis to drop them from a date-keyed aggregation.
- Both series are built over the same underlying 27,479 rows (minus the 1 null, for series B
  only) with the same qty/sale reconciliation logic used elsewhere in this project (grouped sums
  must equal the ungrouped total — checked and confirmed).
- **Structural difference found and reported**: `createDate`-keyed months stop at 2026-08 (the
  last complete calendar month by the pipeline's own `determine_complete_months()` rule — max
  createDate 2026-08-31 equals that month's last day). `forecast_date`-keyed months extend to
  2027-05, **9 months beyond** the createDate window. These trailing months are **right-censored
  by construction**: they only contain demand from orders *already placed* by the data cutoff
  (2026-08-31/09-01) that happen to have a far-future delivery promise; orders that will be
  placed later for the same future delivery months are not yet in the data. This means
  `forecast_date`-keyed totals for any month at or beyond September 2026 will keep growing on
  every future re-pull — they are not a frozen "actual" the way a past createDate-keyed month is.
  This point is used in Task 4 and flagged again in Task 5/6.

---

## Task 4 — How much demand shifts, and does classification change?

**Comparison window** (apples-to-apples, both series computed over the identical 32-month
calendar grid 2024-01 to 2026-08, the pipeline's own complete-months rule): 112 items × 32
months = 3,584 item-month cells.

**Aggregate shift**:
- createDate-keyed total qty in-window: 3,359,079. forecast_date-keyed total qty in-window:
  3,286,187 (**-72,892 units, -2.17%**).
- This -2.17% is fully explained, to the unit: **72,889 units** (2.15% of the createDate total)
  belong to rows whose `forecast_date` falls *after* the window (i.e. real contractual delivery
  obligations due September 2026 or later, already placed but not yet due) — see
  `phaseA_a3_future_dated_backlog_beyond_window.csv`. The remaining 3-unit gap is exactly the 1
  excluded null-`forecast_date` row. **This reconciles exactly** — no unexplained residual.
- Of that future-shifted demand, **64,134 units (₿16.77M) alone are due in September 2026** —
  the single month immediately after the current data window — with smaller amounts in October
  2026 through as late as May 2027.
- **Gross reallocation** (half the sum of absolute item-month qty differences, a standard
  "how much moved" measure): **387,281 units, 11.53%** of the createDate-keyed in-window total.
  By value: **₿103.58 million reallocated, 14.98%** of the createDate-keyed in-window sale total
  — a larger percentage than the quantity shift, consistent with longer-notice orders tending to
  carry higher unit value (also consistent with the earlier lead-time investigation's finding
  that spike-month/large orders carry only modestly longer notice on average).

**Materiality (my own definition, stated explicitly)**: an item-month is "material" if
`|qty_forecast − qty_create| ≥ max(5 units, 20% of that item's own mean non-zero monthly qty in
the window)`. Rationale: a flat 20% threshold alone would flag trivial absolute swings for
very-low-volume items (a 1-unit change on a 2-unit-average item is a 50% swing but operationally
meaningless), so a 5-unit floor is added; conversely a flat unit floor alone would under-flag
high-volume items with a real but proportionally modest reallocation. This is a Validator-defined
materiality bar for this report only, not a project-wide standard.
- **940 of 3,584 item-months (26.2%) are material** by this definition.
- **97 of 112 items (86.6%) have at least one material item-month** — i.e. re-keying changes
  the monthly picture for the large majority of the scope, not a handful of outliers.

**Classification (ADI/CV², Syntetos-Boylan thresholds ADI=1.32, CV²=0.49 — confirmed identical
across `src/aggregate_levels.py`, `src/backtest.py`, `src/series_features.py`, the last of which
`src/rule_based_selection.py` imports its thresholds from)**, computed over the same 32-month
common window for both keyings:
- **11 of 112 items (9.8%) change classification** when re-keyed
  (`phaseA_a3_classification_comparison_common_window.csv`). 7 of the 11 are
  Intermittent↔Lumpy flips (a CV² threshold crossing only — the less consequential kind of
  reclassification, since it doesn't change whether the item is "smooth-like"). The other 4
  cross the ADI threshold (Smooth↔Erratic ×2, Erratic→Lumpy, Lumpy→Erratic) — a more
  consequential change, since it reflects a real change in how many months have zero recorded
  demand once demand is dated by delivery-due-date instead of order-placed-date.
- As a **contrast-only** check (not the primary comparison, because of right-censoring), I also
  computed classification using the full 41-month tail through 2027-05 for the forecast_date
  series against the same 32-month createDate series: 13 of 112 items (11.6%) differ — close to
  the common-window figure, suggesting right-censoring is not badly distorting the headline
  count, but the common-window (32-month) figure is the one I rely on as primary.

**The 3 focus items — explicitly, as requested**:

| Item | Classification (createDate) | Classification (forecast_date) | Changed? |
|---|---|---|---|
| `EEE-F-FC-1040010002` | Erratic (ADI 1.10, CV² 1.13) | Erratic (ADI 1.10, CV² 0.99) | **No** |
| `HS-F-99-02110` | Lumpy (ADI 2.29, CV² 2.67) | Lumpy (ADI 2.46, CV² 2.77) | **No** |
| `HS-F-99-0213` | Lumpy (ADI 1.60, CV² 2.21) | Lumpy (ADI 1.60, CV² 2.08) | **No** |

All three keep the same classification under both keyings (confirmed in both the 32-month
common window and the 41-month full-tail contrast). **However, all three do have material
item-month reallocation** (`phaseA_a3_focus_items_month_detail.csv`), e.g.
`EEE-F-FC-1040010002` shows a -4,368-unit swing in June 2026 alone (7,809 createDate-keyed vs.
3,441 forecast_date-keyed) against a materiality threshold of 330 units — the classification
label is stable, but the month-by-month shape that any model would actually be fit against is
not.

**Reconciliation check against the existing pipeline's own output** (not previously compared):
`output/summary/part2_item_level_stats.csv` (produced 2026-08-31 by `src/aggregate_levels.py`,
using a 31-month window ending 2026-07 from an earlier, separate DB pull) reports for the 3
focus items: `EEE-F-FC-1040010002` ADI 1.107/CV² 1.171 Erratic, `HS-F-99-02110` ADI
2.385/CV² 2.838 Lumpy, `HS-F-99-0213` ADI 1.632/CV² 1.394 Lumpy. My 32-month createDate-keyed
figures (ADI 1.103/1.132, 2.286/2.668, 1.600/2.208 respectively) are close but not identical —
fully explained by one extra month of data (this file's snapshot is one day newer, so it
includes the now-complete August 2026 that the earlier pull did not). **Same classifications in
both, no contradiction** — the small numeric drift is attributable to snapshot timing, reported
here rather than silently smoothed over.

**Confidence: high** for all quantitative figures above (direct recomputation from the validated
file, reconciles exactly to the unit where checked). **Moderate** for the classification-change
count specifically, because 7 of the 11 changes are borderline CV² crossings sensitive to exactly
which months are included — a slightly different window choice could move a few items back and
forth across that particular line.

---

## Task 5 — Consequences for inventory timing if `createDate` is the wrong field

**Direction, measured directly**: demand that the current pipeline attributes to the month a PO
was *received* is, for a material share of the scope, actually due for delivery in a
*different* month — predominantly *later*, per Task 4. Concretely:
- 72,889 units (2.15% of scope demand already on the books) are contractually due for delivery
  **after** the current pipeline's most recent complete month, with 64,134 of those units due
  in the very next month (September 2026). Under the current createDate-keyed approach, this
  demand is invisible as a September requirement — it is scattered across whatever earlier
  months those particular POs happened to be placed in.
- More broadly, 11.53% of quantity and 14.98% of value moves to a *different* calendar month
  than the one createDate would assign it to, and 86.6% of items have at least one materially
  affected month.

**Practical meaning**: if inventory must be on hand by `forecast_date` (the contractual delivery
date — the established business definition, not re-derived here), then a createDate-keyed
model is trained on, and would forecast against, a timeline that is systematically shifted
relative to when stock is actually required. The direction found here is that a real, already-
committed slice of demand is deferred later than the createDate-keyed model can see — i.e. the
current approach risks **under-recognizing near-term future requirements that are already
contractually locked in**, which is a stockout-risk direction, not an overstock-risk direction,
for the specific 2.15% of demand that falls in the future-shift bucket. For the other ~9.4% of
gross reallocation that moves *within* the observed window (rather than past its edge), the
direction is mixed item-by-item (see the signed `qty_diff` column in
`phaseA_a3_item_month_comparison_common_window.csv` — some months increase, some decrease), so
no single blanket direction ("always early" or "always late") applies to the whole scope — this
is stated explicitly rather than overclaiming a uniform bias.

**Confidence: high** on the measured magnitude and the future-shift direction (directly computed,
reconciles to the unit). **Moderate** on the broader "which way is inventory mistimed" framing,
because I have not modeled how a real Max-Min/safety-stock policy would actually respond to this
shift (that is explicitly out of scope for the Validator role and belongs to Phase E).

---

## Task 6 — Recommendation (for the Orchestrator/Synthesizer, not enacted here)

Based on what was measured, not just the stated business definition: **`forecast_date` should
key the demand series used for inventory-timing purposes**, because a material, directly-
measured share of demand (11.53% of qty, 14.98% of value, materially affecting 86.6% of items)
moves to a different calendar month when re-keyed, and part of that shift (2.15% of qty) is
currently invisible altogether to a createDate-keyed model because it falls beyond the model's
observed window. This is a measured effect, not solely a restatement of the business definition
already recorded in STATUS.md.

**This recommendation is explicitly conditional on Phase A Task 1** (a different check, run by
another agent per STATUS.md: whether `forecast_date` is revised after PO intake rather than
fixed). If `forecast_date` is found to be continuously updated rather than fixed at intake, a
series keyed on it would not be reproducible in the CONVENTIONS.md sense (a past month's
`forecast_date`-keyed total could change on every re-pull, not just extend forward) — that
would not overturn the *direction* of this finding (delivery-due-date is still the conceptually
correct planning anchor), but it would mean the series needs to be captured at a fixed point in
time (a frozen snapshot) rather than treated as a live re-queryable history the way `createDate`
currently is. I did not re-verify that check myself — it is out of this task's scope — and flag
it here as a dependency the Synthesizer should resolve before finalizing this recommendation.

Also note for whoever acts on this: forward-looking (future) months of a `forecast_date`-keyed
series are inherently right-censored (Task 3) and must not be treated as "final" the way a past
`createDate`-keyed month is — this affects how ADI/CV² classification and any backtest window
would need to be defined if this change is adopted.

**Confidence: moderate-to-high** on the recommendation direction; **explicitly conditional** on
the Task 1 revision-question above, which this report does not resolve.

---

## Task 7 — Confidence summary

| Finding | Confidence | Evidence |
|---|---|---|
| All 5 named pipeline scripts key on `createDate`, none reference `forecast_date` | High | Direct code read + grep, cited line numbers |
| `raw_order_leadtime_128items.csv` is safe to reuse (no 1970/2032 anomaly, nulls/negatives match prior report) | High | File inspection + independent fresh unfiltered DB query, both reconcile exactly |
| 1 null forecast_date, 15 negative-interval rows, handling decisions | High | Direct recomputation, reconciles to STATUS.md's prior figures to the row |
| Gross qty/value reallocation (11.53% / 14.98%) and future-shift (72,889 units / 2.15%) | High | Direct recomputation, reconciles to the unit (72,889 + 3 = 72,892 exactly explains the in-window total gap) |
| 940/3,584 material item-months, 97/112 items affected | High (for the stated definition) | Direct computation; materiality threshold is a stated Validator choice, not a project standard |
| 11/112 items change classification (common window); 3 focus items do NOT change | Moderate (count), High (focus items) | Direct computation; most changes are borderline CV² crossings sensitive to window choice |
| Direction of inventory mistiming (future-shift = under-recognized near-term requirement) | High (magnitude), Moderate (general framing) | Direct computation; no inventory policy was modeled |
| Recommendation to key on forecast_date | Moderate-to-high, conditional | Grounded in measured shift; explicitly depends on the unresolved Task-1 revision question (another agent's check) |

**What this report could not resolve** (stopping rule applied, not chased further): whether
`forecast_date` is a fixed promise or a continuously-revised plan (Phase A Task 1, a different
agent's assigned check — flagged as a dependency above, not re-investigated here); how a real
Max-Min policy would respond to the measured shift (Phase E, out of Validator scope); whether the
53 exact-duplicate rows found in this specific extract include any of the previously-flagged
duplicate-vs-split-lot sets (not cross-referenced against `task7_final_revised_classification.csv`
— would need a targeted join on contractid+itemcode if the Orchestrator wants this checked).

---

## Files written by this task (all in `output/summary/`, prefixed `phaseA_a3_`)

- `phaseA_a3_date_keying_findings.md` — this report
- `phaseA_a3_future_dated_backlog_beyond_window.csv` — qty/sale by month for the 72,889-unit future-shift bucket
- `phaseA_a3_item_month_comparison_full.csv` — full item×month grid (both keyings), all months through 2027-05
- `phaseA_a3_item_month_comparison_common_window.csv` — same, restricted to the 32-month common window, with materiality flag
- `phaseA_a3_classification_comparison_common_window.csv` — per-item ADI/CV²/classification under both keyings, common window
- `phaseA_a3_classification_comparison_full_tail.csv` — contrast version using the full 41-month forecast_date tail
- `phaseA_a3_focus_items_month_detail.csv` — item-month detail for the 3 focus codes
