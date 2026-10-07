# Phase A / Task A1 — Is `forecast_date` a fixed PO-intake promise, or is it revised?

**Role**: combined Explorer + Validator. **Investigation only** — no min/max values calculated,
no model built or changed, `config/config.yaml` not touched, nothing committed or pushed.
**Date**: 2026-09-02. **Script**: `src/investigate_forecastdate_revision.py` (read-only queries via
`src/db.py`'s `run_query()`; credentials never printed/logged).

This resolves the open item STATUS.md flags twice — "whether `forecast_date` ... represents a
fixed PO-intake promise or a continuously-updated latest plan" — and is Phase A item 1. Two
headline figures depend on the answer: the 6-day median order notice
(`output/summary/leadtime_overall_distribution.csv`) and on-time delivery by year
(57.8%/61.0%/68.6%/73.2% in 2023-2026, `output/summary/delivery_by_year.csv`).

All CSV outputs referenced below carry the `phaseA_a1_` prefix in `output/summary/` (summary
outputs) or `output/data/` (raw/processed pulls), per this project's raw-vs-processed convention.

---

## Task 1 — Epoch/future-date anomaly check (independent verification)

**Method**: fresh SQL query against `cube_Sale_APD`, filtered ONLY by `itemcode IN (...)` — no
`division`, `revenue_type`, or `status` filter, matching the orchestrator's own quick check so the
same population is being tested. Run separately for (a) the full 128-item Category/Type/Item scope
(`output/summary/part1_category_scope_all_codes.csv`) and (b) the 3 focus codes
(`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`) specifically. Counted rows with
`forecast_date <= '1971-01-01'`, `forecast_date >= '2030-01-01'`, and `createDate > GETDATE()`.

**Result** (`phaseA_a1_task1_anomaly_check.csv`, `phaseA_a1_task1_anomaly_rows_if_any.csv`):

| scope | n_rows | createDate range | forecast_date range | epoch (≤1971) | far future (≥2030) | createDate>today |
|---|---|---|---|---|---|---|
| full 128-item scope | 27,727 | 2024-01-03 → 2026-09-01 | 2024-01-04 → 2027-05-31 | 0 | 0 | 0 |
| 3 focus codes | 630 | 2024-01-03 → 2026-09-01 | 2024-01-08 → 2026-09-25 | 0 | 0 | 0 |

Zero anomalous rows found anywhere in the 128-item scope under any division/revenue_type/status
combination (`phaseA_a1_task1_anomaly_rows_if_any.csv` is empty). This independently reproduces the
orchestrator's own quick check, run separately, to the row.

**Conclusion — HIGH CONFIDENCE.** Neither `createDate` nor `forecast_date` shows the reported
1970/2032-style anomaly anywhere within the 128-item scope, nor specifically within the 3 focus
codes. Both fields are safe to use for date-based analysis on these items. The reported anomaly, if
real, lives entirely outside this scope (other item codes, divisions, or revenue types not part of
this project) — consistent with, and now independently confirmed rather than merely repeated from,
the orchestrator's own finding. **No contradiction with any STATUS.md finding** — STATUS.md does
not mention this anomaly at all; this is a new check, now closed for this project's scope.

---

## Task 2 — `forecast_date` vs `ForecastDelDate` / `PlanDelDate` / `ActualDelDate`

**Method**: fresh pulls of both tables (not blindly reused from the existing CSVs, though the
result reconciles closely with them — see below): `cube_Sale_APD` under the project's standard
filter (`division='PEM101'`, `revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
`createDate>=2024-01-01`, 27,584 rows, 27,583 with a non-null `forecast_date`), and `Cube_CES` with
`PlanID` added (`ManuDivision='PEM101'`, `RevenueType='Omni Channel'`, `Status IN ('Actual',
'Backlog')`, `CtrDate>=2023-01-01`, 36,444 rows). Joined on `contractid=ContractID,
itemcode=ItemCode`. Because `Cube_CES` has a finer `PlanID` grain (one contract+item pair can carry
several tranches with different dates — confirmed directly, e.g. `CTR-2024-05379` has 3 tranches
per item, each with its own `PlanDelDate=ForecastDelDate` and a distinct, close `ActualDelDate`), a
naive row-by-row cross-join manufactures spurious large "disagreements" whenever an APD row is
compared against the wrong tranche. **This was caught and fixed during the investigation**: an
early pass reported some diffs up to 729 days, which on manual inspection of the underlying rows
turned out to be cross-join artifacts, not real disagreements. The corrected method matches every
APD row to its single best-matching `Cube_CES` row (smallest `|forecast_date - ForecastDelDate|`)
before comparing `PlanDelDate`/`ActualDelDate` from that same row — verified by hand against
`CTR-2024-05379`'s 3-tranche structure before being adopted.

**Result** (`phaseA_a1_task2_join_match_summary.csv`, `phaseA_a1_task2_date_diff_distribution.csv`):

| scope | pairs joinable | exact match vs `ForecastDelDate` | exact match vs `PlanDelDate` |
|---|---|---|---|
| full 128-item scope | 100.0% (27,421/27,421) | **100.0%** | 97.48% |
| `EEE-F-FC-1040010002` | 100.0% (472/472) | **100.0%** | 99.58% |
| `HS-F-99-02110` | 100.0% (88/88) | **100.0%** | 97.73% |
| `HS-F-99-0213` | 100.0% (62/62) | **100.0%** | 96.77% |

`forecast_date` matches `ForecastDelDate` **exactly, on every single joinable row**, in both the
full scope and all 3 focus codes. This is consistent with the two fields being the same underlying
value, tightly synced across the two independently-populated tables (echoing STATUS.md's earlier
99.79% row-level agreement finding — no contradiction, this is a tighter, date-specific version of
the same reconciliation).

`forecast_date` disagrees with `PlanDelDate` on 2.52% of rows overall (695 of 27,583), rising to
3.23% for `HS-F-99-0213` and 2.27% for `HS-F-99-02110`, falling to 0.42% for
`EEE-F-FC-1040010002`. **Direction and magnitude of the disagreement, examined directly**
(`phaseA_a1_task2_plandeldate_disagreement_rows.csv`): mixed, not systematic — 64.0% of
disagreements have `forecast_date` EARLIER than `PlanDelDate`, 36.0% LATER (median -2 days, but a
long tail both directions: min -429, max +729 days). Manual inspection of several large-gap
examples (e.g. `CTR-2024-05463`: `forecast_date`/`ForecastDelDate`=2024-09-27 close to
`ActualDelDate`=2024-11-08, while `PlanDelDate`=2025-11-30 is over a year later and does not track
the actual outcome at all; vs. `CTR-2024-02637`: the opposite pattern, `PlanDelDate` tracks
`ActualDelDate` closely while `forecast_date`/`ForecastDelDate` is the outlier) shows **no
consistent story about which field is "more correct" or "more original"** — sometimes
`ForecastDelDate` tracks the eventual real delivery, sometimes `PlanDelDate` does, sometimes
neither closely.

**Conclusion — HIGH CONFIDENCE on the numbers, LOW CONFIDENCE on what causes the 2.5% disagreement.**
`forecast_date` (cube_Sale_APD) and `ForecastDelDate` (Cube_CES) are, for practical purposes, the
same field. `PlanDelDate` is a materially different field for a small (2.3-3.2%) but non-trivial
share of rows, with no consistent direction — evidence of occasional data inconsistency between two
date fields, not of a systematic "one date field gets revised to match reality" pattern. This alone
neither confirms nor rules out revision-over-time (see Task 3).

---

## Task 3 — Searching for evidence of revision

### 3a. `cube_Sale_APD`: same `(contractid, itemcode, createDate)`, different `forecast_date`

**Method**: grouped the fresh `cube_Sale_APD` pull by `(contractid, itemcode, createDate)` and
counted distinct `forecast_date` values per group. A group with >1 distinct value would mean the
same order, same item, same PO-intake date carries two different recorded delivery promises — a
signature the task specifically asked to distinguish from legitimate multi-tranche split lots
(different `createDate`s or different quantities for genuinely separate shipments, an already-
established normal pattern in this project — STATUS.md's duplicate-vs-split-lot investigation).

**Result** (`phaseA_a1_task3a_summary.csv`, `phaseA_a1_task3a_same_createdate_diff_forecast.csv`):
68 of 27,421 groups (0.25%, 158 rows) have >1 distinct `forecast_date` for the same
`(contractid, itemcode, createDate)`. **Every flagged group inspected has a different `qty`/`sale`
value across its rows** (e.g. `CTR-2024-00427`: 5 units/₿9,000 with `forecast_date`=2024-01-26 vs.
3 units/₿5,400 with `forecast_date`=2024-02-23; `CTR-2024-03524`: 1,000 units vs. 970 units on two
different dates a month apart). This is the exact signature STATUS.md already established as
"legitimate multi-tranche delivery lots recorded on the same PO-intake date," not a duplicated or
re-entered single promise. **None of the 3 focus codes appear in this flagged set at all.**

**Conclusion — HIGH CONFIDENCE this specific test found NO evidence of revision.** The one pattern
this test could have caught (a literal re-entry of the same obligation with a changed date) is not
present — every case found has a business-meaningful explanation (split quantities) already
established elsewhere in this project.

### 3b. `Cube_CES` `PlanID`-level disagreement: revision vs. legitimate multi-tranche

**Method**: pulled `Cube_CES` with `PlanID` for the 128-item scope, this time across ALL 13 status
codes (`Actual`, `Backlog`, `P2`, `Cancel`, `MPS`, `P3`, `N/A`, `None`, `T1`-`T3`, `F`, `Y` — wider
than the project's standard `Status IN ('Actual','Backlog')` delivery-performance scope, stated
explicitly since this is a different question), to see the complete `PlanID` picture rather than
only the assessable subset. Grouped by `(ContractID, ItemCode)`; flagged pairs with more than one
distinct `PlanID`.

An early classification pass used "identical `PlanQty` across PlanIDs" as the revision signal, but
this was **rejected on inspection**: several genuine multi-tranche orders split into equal-sized
batches (e.g. 500 units delivered in July + 500 more booked for October, `CTR-2026-01277`/
`EEE-F-FL-1040030002`) have identical `PlanQty` across PlanIDs purely because the split happened to
be even — normal, not evidence of revision. The revised, decisive test instead uses
`ActualDelDate` — a real, already-happened event: if two PlanIDs for the same pair carry **different**
`ActualDelDate` values, they are provably separate physical deliveries, regardless of whether their
planned quantities coincide.

**Result** (`phaseA_a1_task3b_summary.csv`, `phaseA_a1_task3b_planid_classification.csv`,
`phaseA_a1_task3b_focus_codes_detail.csv`): 159 of 36,287 pairs (0.44%, spanning 370 of 36,498 rows
— 1.01%) have more than one `PlanID`:

| classification | n pairs |
|---|---|
| `MULTIPLE_DISTINCT_ACTUAL_DATES_genuine_separate_tranches` | 90 |
| `different_qty_consistent_with_separate_tranches` | 37 |
| `true_duplicate_rows_same_qty_same_dates` | 26 |
| `REVISION_CANDIDATE_same_qty_same_or_no_actual_but_dates_disagree` | **6** |

Only **6 pairs (12 rows, 0.033% of all rows)** fall into the ambiguous bucket: same `PlanQty`
across PlanIDs, and either a single shared `ActualDelDate` or none at all (still `Backlog`), but
`ForecastDelDate`/`PlanDelDate` disagree across the PlanIDs. **Manually inspecting all 6**:
4 of 6 involve a 1-day date discrepancy between two otherwise near-identical rows (e.g.
`CTR-2026-01446`/`HS-F-99-0241`: `PlanDelDate` 2026-04-09 vs. 2026-04-10, same `ActualDelDate`
2026-04-09 for both) — plausibly a minor duplicate/rounding artifact rather than a meaningful
revision. The other 2 are pairs of `Backlog` rows (not yet delivered) with equal `PlanQty` but
dates ~5 weeks apart (e.g. `CTR-2026-02611`/`EEE-F-LT-1040020100`: 500 units planned 2026-09-10 and
500 more planned 2026-10-15) — this is **structurally indistinguishable** from either "one pending
order's date was pushed back and re-recorded under a new `PlanID`" or "two separate orders of
coincidentally equal size," because neither has an `ActualDelDate` yet to check against.

None of the 3 focus codes fall into the `REVISION_CANDIDATE` bucket; their 3 multi-`PlanID`
occurrences are all `different_qty_consistent_with_separate_tranches` (legitimate split lots).

**Impact-bounding calculation (regardless of how the ambiguous cases resolve)**: even under the
most generous assumption that ALL 159 multi-`PlanID` pairs (not just the 6 truly ambiguous ones)
represent genuine date revision, they cover only 370 of 36,498 rows (1.01%) — far too small a
share to be the primary driver of the observed ~15-percentage-point swing in on-time delivery by
year (57.8% → 73.2%, computed over 35,947 assessable rows). **Conclusion — HIGH CONFIDENCE**: even
if some genuine revision exists in this data, its volume is not large enough to explain the
headline year-over-year on-time-delivery trend by itself.

### 3c. Audit/history/version table check, and independent Timestamp re-verification

**Method**: STATUS.md's Part 6 ("Root cause of the 2022/2023 break") already searched all 108
tables in the database by name for audit/log/ETL-run/migration/version/history keywords and found
none (only pre-existing data-snapshot tables, which are periodic copies, not change logs). Per the
stopping rule, this was **not repeated from scratch**. Instead, a narrower, complementary check was
run: `INFORMATION_SCHEMA.COLUMNS` for `cube_Sale_APD` and `Cube_CES` specifically, searched for
column names suggesting a per-row modification timestamp (`modif`, `updat`, `chang`, `revis`,
`edit`, `version`, `audit`, `log`, `history`) — a check the table-name-only search would not have
caught, since a modification-timestamp column could exist inside either of these two named tables
without being an "audit table" in its own right.

Separately, the user's claim that `Cube_CES.Timestamp` is an ETL load stamp (not a business
modification time) was independently re-verified for the 3 focus items with a fresh query, not
taken on trust.

**Result** (`phaseA_a1_task3c_all_columns.csv`, `phaseA_a1_task3c_column_keyword_hits.csv`,
`phaseA_a1_task3c_focus_timestamp_summary.csv`): only 3 keyword hits, all false positives
(`BacklogQty`, `BacklogPrice`, `BacklogGP` — "log" is a substring of "Backlog", unrelated to
change-logging). No genuine modification-timestamp column exists in either table.

Independent re-verification of `Cube_CES.Timestamp` for the 3 focus items: **2,995 rows, Timestamp
range 2026-09-02 06:56:07.620 → 06:58:03.793, a span of 116.2 seconds, with 2,404 distinct values
within that single ~2-minute window.** This reproduces the orchestrator's reported finding almost
exactly (they reported "clustered within about a 2-minute window ... 06:56-06:58" — my own query,
run independently, confirms this to the second). A single, tight reload batch stamp is consistent
with an ETL load time, not with progressive business-time modification (which would be expected to
spread `Timestamp` values out over the actual months/years these rows' dates span, 2023-2026).

**Conclusion — HIGH CONFIDENCE.** No audit/history/version table or per-row modification-timestamp
column exists anywhere that could timestamp a `forecast_date`/`ForecastDelDate`/`PlanDelDate`
change — this confirms STATUS.md Part 6's conclusion still holds, extended specifically to
date-revision tracking (not simply re-asserted, independently re-checked at both the table-name and
column-name level, plus the Timestamp re-verification). **What this method CANNOT detect, stated
plainly**: there is no way, in any table currently in this database, to determine when a date field
was last written, or what its value was before the most recent write. If a date value is silently
overwritten in place, this data model destroys any trace of the earlier value — revision-over-time
of that kind is **fundamentally undetectable from this data**, not merely "not found."

---

## Task 4 — Recomputation

Per the branching instruction: **no positive, decisive evidence of true date revision was found**
(Task 3a: zero; Task 3b: only 6 of 159 multi-`PlanID` pairs are even ambiguous, and manual
inspection could not resolve them one way or the other; Task 3c: no mechanism exists to detect
revision even if it occurred). Task 2's ~2.5% `forecast_date`-vs-`PlanDelDate` disagreement has no
consistent direction, which argues against (though does not disprove) a systematic "field gets
updated toward the eventual outcome" story.

**Therefore, per the instructions for this branch: no recomputation using an "earliest recorded
date" was performed, since there is no reliable way to establish which of two disagreeing field
values (if either) is "earlier"** — no per-row timestamp exists (Task 3c), and `PlanID`'s numeric
ordering, while plausibly reflecting `Cube_CES` insertion order, was already shown elsewhere in
this project's own investigations (STATUS.md, duplicate-vs-split-lot task) to be unreliable as a
proxy for genuine business chronology. Fabricating an "earliest date" assumption on top of that
unreliable proxy would not be a real verification — it was avoided.

**Stated plainly, per instruction**: this does **not** mean the two headline figures (6-day median
notice; 57.8%→73.2% on-time by year) are confirmed to rest on fixed, never-revised dates. Absence
of detected revision is not evidence of fixed dates — it is reported here as exactly what it is:
revision could not be confirmed, and could not be ruled out, from this data. What the data DOES
support, at high confidence, is a **bound on how much revision (if any exists) could be
contributing** to the headline figures: the total footprint of every case this investigation could
even flag as possibly revision-affected is under 1.1% of rows in every test run (Task 2: 2.52% of
28k rows disagree on `PlanDelDate` specifically, with no systematic direction; Task 3a: 0.25% of
groups; Task 3b: 0.44% of pairs / 1.01% of rows, only 0.033% genuinely ambiguous). None of these
figures are remotely large enough, on their own, to manufacture a 15-percentage-point swing in
on-time delivery across years, or to materially shift a 27,583-row median notice-period
calculation.

**What would settle this definitively** (stated exactly, as required when a search cannot resolve
a question): a genuine per-row audit/change-history table or a periodic snapshot series capturing
`forecast_date`/`ForecastDelDate`/`PlanDelDate` values at multiple points in time for the same
`(contract, item)` obligation (neither exists in this database, confirmed above); or direct
confirmation from IT/the business about the write pattern for these fields — specifically, whether
`forecast_date` is ever updated in place after the PO is first entered, and if so, under what
business circumstance (e.g. customer reschedule requests, internal replanning).

---

## Task 5 — Confidence summary

| Finding | Confidence | Evidence |
|---|---|---|
| No epoch (≤1971) or far-future (≥2030) `forecast_date`/future `createDate` values exist within the 128-item scope or the 3 focus codes | **High** | Fresh, filter-free SQL query, own run, zero anomalous rows found (`phaseA_a1_task1_*.csv`) |
| `forecast_date` (cube_Sale_APD) and `ForecastDelDate` (Cube_CES) are effectively the same field | **High** | 100.0% exact match, full scope and all 3 focus codes, corrected best-match join method verified by hand on a 3-tranche contract |
| `PlanDelDate` disagrees with `forecast_date`/`ForecastDelDate` on ~2.3-3.2% of rows depending on scope, direction mixed (64%/36%) | **High** on the numbers; **Low** on the cause | Direct computation on fresh joined data; manual inspection of outlier rows shows no consistent pattern |
| Same-`createDate` rows with differing `forecast_date` are legitimate split lots, not duplicated promises | **High** | All 68 flagged groups (158 rows) carry differing qty/sale, matching STATUS.md's already-established split-lot signature; 0 focus-code occurrences |
| `Cube_CES` `PlanID`-level disagreement is almost entirely explained by genuine multi-tranche activity | **High** | 90 of 159 multi-PlanID pairs have provably distinct real `ActualDelDate`s; only 6 (0.033% of rows) are genuinely ambiguous |
| No audit/history/version table or modification-timestamp column exists to detect revision directly | **High** | Confirms STATUS.md Part 6 (full 108-table name search) at the column-name level for these 2 tables specifically; independently re-verified `Timestamp` is an ETL load stamp (116-second window) |
| Revision-over-time is fundamentally undetectable from this data, one way or the other | **High** (in the sense that this limitation itself is well-evidenced) | No table/column anywhere can show a date field's prior value; stated as a hard limitation, not glossed over |
| Whatever revision (if any) exists cannot be the primary driver of the 57.8%→73.2% on-time-by-year trend or the 6-day median notice figure | **High** | Every revision-candidate footprint found across 3 independent tests caps out under ~2.5% of rows, most with no consistent direction — too small to produce a 15-point year-over-year swing |
| Whether `forecast_date` is a fixed PO-intake promise (the original question) | **Unresolved — stated plainly, not guessed** | No positive evidence of revision found; absence of evidence is not treated as evidence of fixedness, per instruction |

---

## Files written by this task

- `output/summary/phaseA_a1_task1_anomaly_check.csv`, `phaseA_a1_task1_anomaly_rows_if_any.csv`
- `output/summary/phaseA_a1_task2_join_match_summary.csv`,
  `phaseA_a1_task2_date_diff_distribution.csv`, `phaseA_a1_task2_plandeldate_disagreement_rows.csv`
- `output/summary/phaseA_a1_task3a_summary.csv`, `phaseA_a1_task3a_same_createdate_diff_forecast.csv`
- `output/summary/phaseA_a1_task3b_summary.csv`, `phaseA_a1_task3b_planid_classification.csv`,
  `phaseA_a1_task3b_focus_codes_detail.csv`
- `output/summary/phaseA_a1_task3c_all_columns.csv`, `phaseA_a1_task3c_column_keyword_hits.csv`,
  `phaseA_a1_task3c_focus_timestamp_summary.csv`
- `output/data/phaseA_a1_raw_apd_fresh_pull.csv`, `phaseA_a1_raw_ces_fresh_pull_scoped.csv`,
  `phaseA_a1_raw_ces_fresh_pull_all_status.csv`, `phaseA_a1_processed_apd_ces_joined_dates.csv`,
  `phaseA_a1_processed_apd_ces_best_match.csv`, `phaseA_a1_processed_focus_items_ces_timestamps.csv`
- Script: `src/investigate_forecastdate_revision.py`

Not committed, not pushed, `config/config.yaml` untouched, no min/max values calculated, no model
built or changed.
