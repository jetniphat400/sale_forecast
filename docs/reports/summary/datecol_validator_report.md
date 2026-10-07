# Date-Column Validator Report — was `createDate` misread as the customer order date?

**Task**: single-Validator investigation (2026-09-04), per `AGENTS.md`'s decomposition test (one
coherent question — the date columns must be understood together). Read-only, INVESTIGATION
ONLY: no code/config changed, nothing committed. Script:
`src/datecol_validator_investigation.py`. All figures below are direct query results or direct
recomputations from that script's output CSVs (cited by filename per figure) — none are
estimated or carried over from memory.

**Why this exists**: since Phase 2 Step 1, this project has assumed `createDate` = the date the
customer's PO was received, based on a name-matching test (0 mismatches vs. the table's own
`year`/`month` columns) — never on behavioral proof that it represents a genuine order event.
A separate column, `PODate`, exists in the same table. This task tests the assumption directly.

**Scope**: 128 item codes in Product Cate. "Fuse"/"Surge Arrester" (`division='PEM101'`),
from `output/summary/part1_category_scope_all_codes.csv`. Two scopes are used, stated explicitly
at every figure below:
- **Base scope** (Part 1's raw column behavior): `division='PEM101' AND itemcode IN (128 codes)`,
  no other filter. 27,679 rows.
- **Modelling scope** (Parts 2-3, matches this project's standard pipeline filter):
  `revenue_type='Omni Channel' AND status IN ('Actual','MPS') AND createDate>=2024-01-01`.
  27,665 of the 27,679 base-scope rows.

Three focus codes (`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`) checked individually
throughout.

---

## Part 1 — Every date column, mapped

### 1a. Column inventory (confirmed, high confidence)
Source: `INFORMATION_SCHEMA.COLUMNS` (`datecol_p1a_all_columns.csv`,
`datecol_p1a_date_typed_columns.csv`). `cube_Sale_APD` has 62 columns; **8 are date/datetime
typed**: `createDate`, `PODate`, `forecast_date`, `timeStamp` (datetime), `customer_entry`,
`warranty_date`, `newCustomerDate`, `plan_date`. This is queried directly, not assumed from
memory of earlier sessions' partial lists.

### 1b. Range / null rate / distinct values, base scope (confirmed)
Source: `datecol_p1b_range_nulls_distinct.csv`, `datecol_p1b_status_revenuetype_breakdown.csv`.

| column | n | null% | min | max | n distinct |
|---|---|---|---|---|---|
| createDate | 27,679 | 0.00% | 2024-01-03 | 2026-09-03 | 652 |
| PODate | 27,679 | 0.00% | 2023-11-22 | 2026-09-03 | 652 |
| forecast_date | 27,679 | 0.0036% (1 row) | 2024-01-04 | 2027-05-31 | 738 |
| timeStamp | 27,679 | 0.00% | 2026-09-03 16:59:56 | 2026-09-03 17:01:00.19 | 10,234 |
| customer_entry | 27,679 | 1.44% | 2003-01-01 | 2026-09-03 | 540 |
| warranty_date | 27,679 | **99.99%** | 2026-04-29 | 2026-07-24 | 2 |
| newCustomerDate | 27,679 | 5.71% | 2000-06-01 | 2026-08-31 | 358 |
| plan_date | 27,679 | 0.0036% (1 row) | 2024-01-04 | 2027-05-31 | 743 |

**Note, not silently glossed over**: the task brief cited PODate as having "an identical
observed range" to createDate. Directly measured, the ranges are close but **not identical** —
PODate's minimum (2023-11-22) is 42 days earlier than createDate's minimum (2024-01-03), entirely
explained by 3 rows on one contract (`CTR-2023-08885`, see 1c below). A minor correction to the
prior informal note, not a contradiction of substance.

**Non-transaction date columns, established from behavior (moderate-high confidence)**:
`warranty_date` is populated on only 4 of 27,679 rows in this scope (99.99% null) — not usable
for anything at this scope. `customer_entry` (back to 2003) and `newCustomerDate` (back to 2000)
both range far earlier than any plausible transaction and are consistent with
customer-relationship/onboarding dates, not order dates — matching this project's existing
characterization of these fields (STATUS.md Phase 2 Step 1). `plan_date` matches `forecast_date`
row-for-row in 97.47% of cases (own check, not previously quantified at this exact scope) — a
closely related delivery-planning field, not independently informative; consistent with
`Cube_CES`'s own `PlanDelDate`/`ForecastDelDate` agreeing 97.9% (STATUS.md, prior finding),
cross-confirming the same near-identical-fields pattern in the other table.

### 1c. createDate vs PODate (confirmed, high confidence)
Source: `datecol_p1c_diff_summary.csv`, `datecol_p1c_createdate_podate_mismatch_rows.csv`,
`datecol_p1c_mismatch_by_year.csv`, `datecol_p1c_focus_codes_check.csv`. Chart:
`output/charts/datecol_createdate_podate_gap_histogram.png`.

**createDate == PODate exactly on 27,664 of 27,679 rows (99.9458%).** Only **15 rows** disagree,
across 8 distinct contracts. In **every one of the 15 mismatches, PODate is EARLIER than
createDate** (0 cases the other direction) — median gap 8 days, mean 16.9 days, max 44 days.
By year: 2024 has 11 mismatches (0.1157% of that year's 9,511 rows), 2025 has **zero**, 2026 has
4 (0.0502% of 7,966 rows) — no year shows a material rate. **Focus codes: 100.00% match, 0
mismatches out of 633 rows** — the assumption holds without exception for the 3 codes this
project treats as priority.

### 1d. createDate vs timeStamp — is createDate ALSO a load artifact? (confirmed, high confidence)
Source: `datecol_p1d_loadbatch_concentration.csv`.

| column | n distinct values | mean rows/value | max on one value | % on busiest value | % on busiest 1% of values |
|---|---|---|---|---|---|
| createDate | 652 | 42.45 | 116 | 0.42% | 2.60% |
| PODate | 652 | 42.45 | 116 | 0.42% | 2.60% |
| forecast_date | 738 | 37.50 | 176 | 0.64% | 4.40% |
| **timeStamp** | **10,234** | 2.70 | 9 | 0.033% | 2.34% (but all in 1 calendar day) |

`timeStamp`'s 10,234 distinct sub-second values ALL fall on **one calendar date**
(2026-09-03), spanning **64.2 seconds** total — the textbook signature of a batch ETL/refresh
timestamp re-stamped whenever the table is reloaded (STATUS.md's earlier finding was "one
~17-minute window on 2026-08-30" — the fact that this value has since moved forward to a new,
different date confirms it re-stamps on each reload, it is not a frozen historical record).
`createDate`, by contrast, is spread across 652 distinct calendar dates with no comparable
concentration (max share on any single date is 0.42%, in a business-plausible range for ~33
months of order activity) — **createDate shows no load-batch signature; it behaves like a
recorded business date, not an ETL artifact.**

### 1e. Weekday distribution (confirmed, high confidence in the numbers; interpretation flagged as limited)
Source: `datecol_p1e_weekday_distribution.csv`. Chart: `output/charts/datecol_weekday_distribution.png`.

| weekday | createDate | PODate | forecast_date |
|---|---|---|---|
| Monday | 20.50% | 20.51% | 12.25% |
| Tuesday | 20.03% | 20.04% | 14.43% |
| Wednesday | 19.18% | 19.17% | 20.19% |
| Thursday | 20.82% | 20.81% | 14.84% |
| Friday | 19.48% | 19.47% | **37.43%** |
| Saturday | 0.00% | 0.00% | 0.56% |
| Sunday | 0.00% | 0.00% | 0.30% |

`createDate` and `PODate` are **virtually identical** to each other (as expected given 1c) and
both are a clean 5-business-day spread with **literally zero weekend rows**. `forecast_date` is
a completely different shape — dominated by Friday (37.4%) with a small but nonzero weekend
presence (0.86% combined) — consistent with `forecast_date` being a *scheduled delivery date*
(deliveries batched toward specific preferred days), not a raw event-request date. **Honest
limitation, stated explicitly per instruction**: the createDate/PODate business-day-only pattern
is consistent with EITHER genuine customer ordering behavior (B2B customers largely order on
business days) OR business-side data entry only happening on business days — this test alone
cannot distinguish those two explanations; it only rules out a weekend-batch-load signature.

### 1f. Cross-check against `Cube_CES` (confirmed, high confidence)
Source: `datecol_p1f_ces_crosscheck.csv`, `datecol_p1f_ctrdate_vs_receivectrdate_by_status.csv`,
`datecol_p1f_ctrdate_vs_receivectrdate_fullscope.csv`. Grain check (required before a safe merge
on contractid+itemcode alone): **0 of 70,826 `Cube_CES` (ContractID,ItemCode) pairs have more
than one distinct `CtrDate` or `ReceiveCtrDate`** — the merge below is not a many-to-many
artifact. **99.82% of base-scope rows (27,630 of 27,679) join to `Cube_CES`.**

| cube_Sale_APD column | Cube_CES column | n | % exact match | median offset (days) | mean offset (days) |
|---|---|---|---|---|---|
| createDate | CtrDate | 27,630 | 99.946% | 0.0 | 0.009 |
| createDate | ReceiveCtrDate | 27,630 | 99.946% | 0.0 | 0.009 |
| **PODate** | **CtrDate** | 27,630 | **100.000%** | 0.0 | 0.000 |
| **PODate** | **ReceiveCtrDate** | 27,630 | **100.000%** | 0.0 | 0.000 |
| forecast_date | CtrDate | 27,629 | 6.49% | 6.0 | 10.81 |
| forecast_date | ReceiveCtrDate | 27,629 | 6.49% | 6.0 | 10.81 |

**PODate matches `Cube_CES`'s own `CtrDate` (Contract Date) and `ReceiveCtrDate` at 100.000% —
an independently-populated table, not a copy within the same row.** `createDate` matches at
99.946% (the same 15-row exception from 1c). `forecast_date` matches at only 6.49% with a ~6-10
day median/mean offset — confirming, from an independent source, that `forecast_date` is a
genuinely different concept (delivery date) from the contract/order date, consistent with this
project's existing characterization.

**Re-verifying the task brief's cited "identical range, narrow 3-period sample" note for
`CtrDate` vs `ReceiveCtrDate`, now at full 128-item scope (not assumed)**: on ALL `Cube_CES`
statuses (71,716 rows), only 86.95% match exactly — **this is NOT a contradiction of the prior
finding**, once the by-status breakdown is examined (`datecol_p1f_ctrdate_vs_receivectrdate_by_status.csv`):
pre-contract stages (`P2` 8,834 rows, `MPS`(CES-native) 232, `N/A` 53, `P3` 137 — 43.9% of the
non-Actual/Backlog rows) have **both `CtrDate` and `ReceiveCtrDate` NULL** (not yet "received"),
which a strict day-diff scores as non-equal even though it is not a genuine value disagreement.
**Restricting to `Status IN ('Actual','Backlog')`** — this project's own established `Cube_CES`
status basis (STATUS.md, delivery-performance work) — gives **99.921% identical** (62,166 rows,
49 disagreements, median offset -1 day when they do differ) — this **CONFIRMS, not contradicts**,
the prior narrow-sample 100% finding, now independently re-verified at full scope rather than
assumed to hold.

### Part 1 summary table

| column | what the evidence shows it measures | confidence |
|---|---|---|
| createDate | Order/contract date — matches PODate 99.95%, matches `Cube_CES.CtrDate`/`ReceiveCtrDate` 99.95%, no load-batch signature, business-day-only weekday pattern | **High** |
| PODate | Same order/contract date as createDate (99.95% identical); matches `Cube_CES.CtrDate`/`ReceiveCtrDate` at 100.000% | **High** |
| forecast_date | Contractual delivery date — distinct weekday pattern (Friday-dominant), only 6.49% exact match to CtrDate, median 6-day offset — matches this project's existing characterization | High (pre-existing, re-confirmed) |
| timeStamp | ETL/refresh-load artifact, re-stamped on every table reload (100% of rows always land on one recent calendar date/narrow time window) | High (pre-existing, re-confirmed) |
| plan_date | Near-duplicate of forecast_date (97.47% row-identical) | Moderate |
| customer_entry | Customer-relationship date, not a transaction date (range back to 2003, doesn't track order volume) | Moderate (not deeply tested this task) |
| newCustomerDate | Customer-onboarding date, not a transaction date (range back to 2000) | Moderate (not deeply tested this task) |
| warranty_date | Unused/near-empty in this scope (99.99% null) | High (simple count) |

---

## Part 2 — What is `createDate`, actually?

**Direct answer: createDate is, for practical purposes, the same date as PODate, and both agree
with an independently-populated table's own contract-date field (`Cube_CES.CtrDate`/
`ReceiveCtrDate`) at 99.9%+. High confidence this rules OUT "createDate is a row-creation
timestamp systematically divorced from the true order event"** — that hypothesis predicts
exactly the load-batch weekday/calendar-clustering signature this task tested for (1d, 1e) and
found ABSENT, and predicts a large, one-directional createDate-vs-independent-source gap, which
also was NOT found (createDate agrees with an external system 99.95% of the time, gap ≤44 days
in the rare cases it disagrees at all).

**Caveat, stated honestly, not force-resolved**: this task cannot fully rule out that createDate/
PODate/CtrDate are all really "the date the sales team keyed the contract into these systems,"
occurring very close to but not provably identical to the calendar day the customer's purchase
order was actually placed — no external, non-database record (a scanned PO, an email timestamp,
or direct IT/business confirmation) exists to close that last gap. This is the same class of
"undetectable from this data model" limitation Phase A's A1 task already found for
`forecast_date`'s revision question — reported plainly, not glossed over.
**Net confidence: moderate-to-high that createDate/PODate correctly represent the true
order/contract date** (upgraded from the original Phase 2 Step 1 evidence, which was only a
within-table name-matching test) — this is real behavioral proof, from an independent second
table, that a name-based inference happened to have gotten right, not a reversal.

**One real, narrow exception found, not to be silently dropped**: in the 15 of 27,679 rows
(0.054%) where createDate and PODate disagree, **createDate is ALWAYS later, never earlier**
(median +8 days, up to +44 days) — a small, one-directional data-entry-lag signature, consistent
with createDate occasionally reflecting when a row was recorded rather than when the underlying
event happened. Too rare to matter for any headline figure (see Part 3), but real and worth
recording.

### Re-keying quantification (computed as instructed, regardless of which column is "true")
Source: `datecol_p2_rekeying_quantification.csv`, `datecol_p2_rows_that_would_move_month.csv`.
Same method as the existing createDate-vs-forecast_date comparison (STATUS.md Phase A/B1),
modelling scope, 31-month common window (2024-01 to 2026-07): **only 7 of 27,665 rows (0.0253%)
would move to a different calendar month if keyed on PODate instead of createDate** — qty moved =
27 units (0.0008% of window total qty 3,239,577), sale moved = ₿49,335 (0.0071% of window total
sale ₿655.44M). **This is 3 orders of magnitude smaller than the createDate-vs-forecast_date
re-keying (11.53% qty / 14.98% value, STATUS.md Phase A/B1)** — strong supporting evidence that
createDate and PODate are not meaningfully different fields for any modelling purpose, unlike the
createDate-vs-forecast_date question, which is a genuinely different concept (order date vs.
delivery date).

---

## Part 3 — Recompute what depended on createDate

### 3a. Order notice, recomputed on PODate
Source: `datecol_p3a_notice_comparison.csv`, `datecol_p3a_notice_buckets_comparison.csv`. Chart:
`output/charts/datecol_notice_comparison_histogram.png`. Modelling scope, identical row set both
ways (1 null-forecast_date row excluded; 15 negative-interval rows excluded from each
distribution, same rows both ways since createDate≈PODate).

| basis | n | median | mean | std | skewness | ≥30d | ≥60d | ≥90d |
|---|---|---|---|---|---|---|---|---|
| createDate-based (existing figure, re-derived fresh here) | 27,649 | **6.0** | 10.92 | 24.99 | 9.92 | 5.866% | 2.188% | 1.298% |
| PODate-based | 27,649 | **6.0** | 10.93 | 25.00 | 9.91 | 5.892% | 2.188% | 1.298% |

**The order-notice distribution is, for all practical purposes, IDENTICAL whether measured from
createDate or PODate** — median unchanged at 6.0 days, mean differs by 0.01 days (10.92 vs
10.93), the ≥30-day share differs by 0.026 percentage points. **High confidence: the existing
6-day median notice figure (STATUS.md) is CONFIRMED, not overturned, by this recomputation.**

### 3b. The Feb-Jul 2026 window — is there a back-dated-entry batch?
Source: `datecol_p3b_window_backdating_check.csv`, `datecol_p3b_test_window_gap_rows.csv`. Chart:
`output/charts/datecol_window_backdating_check.png`. Windows are IDENTICAL to `src/backtest_rekeyed.py`'s
TRAIN (2024-01 to 2025-07, 19mo) / VAL (2025-08 to 2026-01, 6mo) / TEST (2026-02 to 2026-07, 6mo).

| window | n rows | rows with any createDate≠PODate gap | % rows | qty affected | sale affected (฿) | % of window qty | % of window sale |
|---|---|---|---|---|---|---|---|
| TRAIN (2024-01 to 2025-07) | 15,274 | 11 | 0.072% | 52 | 80,250 | 0.0029% | 0.0220% |
| VAL (2025-08 to 2026-01) | 5,324 | **0** | **0.000%** | 0 | 0 | 0.0000% | 0.0000% |
| **TEST (2026-02 to 2026-07)** | 5,794 | 4 | 0.069% | 18 | 38,835 | 0.0024% | 0.0237% |

**No batch of back-dated entries found in the TEST window — high confidence in this negative
finding.** The TEST window's affected share (0.069%) is not even the highest of the three
windows (TRAIN's is 0.072%); VAL shows zero such rows at all. All 4 TEST-window-affected rows
trace to a single contract (`CTR-2026-00744`, 4 different items, each with a 22-day
createDate-after-PODate gap) — 18 units and ₿38,835 out of the window's total 755,046 units and
₿164.0 million (a ~0.002-0.024% share). **This is many orders of magnitude too small to plausibly
explain the previously-recorded 10-46% MAE divergence between createDate-keyed and
forecast_date-keyed backtests concentrated in this exact window (STATUS.md Phase B1/B4).**

**Correlation vs. causation, stated explicitly per instruction**: this task can only show
co-occurrence, not mechanism. What is shown here is a clean **negative** result — this
specific candidate mechanism (createDate/PODate back-dating) does NOT explain the B1/B4 anomaly.
It does not identify what DOES — that remains an open question, already recorded as such in
STATUS.md's Phase B follow-up ("what specifically makes the 2026-02-to-2026-07 window
favourable... not tested").

---

## Part 4 — Recommendation

**createDate and PODate are functionally the same field (99.95% identical, 100% identical at the
3 focus codes, 0.025% month-reallocation if swapped) — there is no meaningful choice to make
between them.** Recommend continuing to key order-intake/notice-period metrics on `createDate`
(no code change needed; the existing choice is now independently, behaviorally corroborated,
not merely name-inferred) — or `PODate` interchangeably, since the two are functionally
identical for this purpose.

**This does NOT change STATUS.md's separate Phase A/B1 recommendation to key the
INVENTORY-AVAILABILITY/stockout-timing series on `forecast_date`** (the contractual delivery
date) rather than createDate/PODate. That recommendation addresses a different pair of concepts
entirely (order-intake date vs. delivery-due date) and this task's findings do not bear on it —
`forecast_date` remains confirmed (1f, and consistent with Phase A/B1) as a genuinely distinct
field from createDate/PODate/CtrDate, at only 6.49% exact match and a ~6-10 day offset.

**No contradiction with STATUS.md — flagged explicitly, per instruction, as required whether or
not one is found.** STATUS.md's Phase 1.5/Phase 2 Step 1 assumed `createDate` = PO received based
on a within-table name-matching test; this task **independently confirms, rather than reverses,
that assumption**, using a stronger method (cross-table agreement with `Cube_CES`, an
independently-populated system, plus load-batch and weekday-pattern tests that would have caught
a record-creation-timestamp misread if one existed). The task brief's premise — that this
assumption "was inherited and never tested" — is now closed: it has been tested, and it held up.
The one genuine, narrow finding worth carrying forward is the 15-row (0.054%), always-lagging
createDate-vs-PODate discrepancy (Part 2) — recorded as a new, minor, non-blocking data-quality
note, not a reason to change any pipeline code.

---

## What the data could not resolve (unresolved, non-blocking)

1. **Whether createDate/PODate/CtrDate record the literal moment the customer's purchase order
   was placed, versus the date sales staff keyed the contract into these systems** (which could
   occur very close to, but not provably identical to, the true order event) — no external,
   non-database record exists to close this gap; would need a scanned PO, an email timestamp, or
   direct IT/business confirmation. Same class of limitation as Phase A1's unresolved
   `forecast_date`-revision question.
2. **The mechanism behind the 15 rows (0.054%) where createDate lags PODate by up to 44 days** —
   too rare to investigate further under this project's stopping rule; magnitude is negligible
   (₿0.13M total sale value across all 15 rows, out of a ₿655.4M scope) and non-blocking.
3. **What actually explains the Feb-Jul 2026 rolling-origin-vs-train/val/test divergence
   (STATUS.md Phase B1/B4)** — this task rules OUT the createDate/PODate back-dating mechanism
   specifically (high confidence negative finding) but does not identify the true cause; already
   an open item in STATUS.md's Phase B follow-up, not newly created here.
4. **The business reason two separately-named fields (`CtrDate`/`ReceiveCtrDate` in `Cube_CES`;
   `createDate`/`PODate` in `cube_Sale_APD`) exist for what is, on the Actual/Backlog status
   basis, a >99.9%-identical value** — not investigated further here (minor structural question,
   non-blocking, needs the source system's own documentation or IT confirmation).
