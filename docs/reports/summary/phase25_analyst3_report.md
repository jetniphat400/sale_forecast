# Phase 25 — Analyst 3 report: PEM107 Omni Channel vs Tendering behaviour, Period 1 vs Period 2

**Agent**: Analyst (this task, 1 of 4 parallel independent agents; this agent covers BEHAVIOUR —
timing/delivery/traceability/mix — only. Two other agents separately test batch-linkage blindness
and categorical-column shifts; this report does not touch either question.)

**Target node**: PROJECT_GRAPH.md Q10 (PEM107 branch — "how does the business actually fulfil
orders") / Q23 (PEM107's 2026 Omni Channel delivery decline). Feeds the open question of whether
the business's "Tendering/Omni production and stock were shared, then separated in May 2026"
account (DATA_MAP.md §7, level A) shows up as a **step at May 2026** in behaviour, or not.

**Scope**: PEM107, 136-item scope (`output/data/phaseI_combined_scope_351items.csv`,
`division=='PEM107'`, `is_excluded==False`), Omni Channel vs Tendering, Period 1 (2025-05-01 to
2026-04-30 inclusive) vs Period 2 (2026-05-01 to latest available data, 2026-09-25).

**Data access**: one connection attempt, three queries in one script/session
(`src/investigations/phase25_analyst3_pull.py`) — all three succeeded on the first attempt, no
retry was needed. Raw pulls (customer/contract identifiers stripped after pull, see Data-hygiene
note at the end): `output/summary/phase25_analyst3_cube_ces_raw.csv` (21,598 rows),
`phase25_analyst3_cube_final_raw.csv` (8,723 rows), `phase25_analyst3_sale_apd_raw.csv` (5,687
rows). Analysis code: `src/investigations/phase25_analyst3_analysis.py`. All numbered CSV outputs
below are written by that script to `output/summary/phase25_analyst3_*.csv`.

**Methodology notes that apply across all four measures** (stated once here, not repeated per
measure):
- Measure 1 is windowed by `ForecastDelDate` (the due date — established convention,
  METRICS.md §18/19 and `phase24_explorerA_analysis.py`'s `not_late_by_month`). Measures 2–4 are
  windowed by the order-creation date (`CtrDate`/`createDate` — see next point). Because these are
  different anchor dates, the row/contract counts behind "Period 1"/"Period 2" are **not identical
  across measures** even for the same channel — an order created in April 2026 (Period 1 by
  `CtrDate`) can have a due date that falls in May 2026 (Period 2 by `ForecastDelDate`). This is a
  deliberate, stated choice (each measure uses the date that actually defines it), not an error.
- **`createDate` proxy**: Cube_CES has no `createDate` field. DATA_MAP.md's "Cube_CES date fields"
  entry records `CtrDate` matches `cube_Sale_APD.createDate` at 99.946% (STATUS.md:3333-3334,
  **V2**). Measures 2 and 3 use `Cube_CES.CtrDate` directly as the `createDate` value, rather than
  joining to `cube_Sale_APD` via (ContractID, ItemCode) — that join is separately established at
  only 72.28% match (Q23 Part 1, DATA_MAP.md `Cube_CES.RevenueType` entry), so joining would have
  discarded ~28% of rows for no benefit given the two fields are already known equivalent.
- Channel scope is `RevenueType`/`revenue_type` = 'Omni Channel' or 'Tendering'. Other values
  ("Total Customer Solution", and pre-2023 rows with a null `RevenueType`) are excluded. Their
  share of the Status='Actual', P1+P2-window volume is **0.22% by row count, 0.01% by quantity** —
  well under the 2% flag threshold (METRICS.md §21 convention). **Confirmed** (direct query,
  `report_other_revenue_type_share` in the analysis script).

---

## Measure 1: not_late, unit-weighted (METRICS.md §19)

Status='Actual' only (`ActualDelDate` populated only then), `not_late` = `ActualDelDate` ≤
`ForecastDelDate`, weight = `ActualQty`. 1 row dropped project-wide for missing
`ForecastDelDate`/`ActualDelDate`. Source: `phase25_analyst3_m1_not_late_period.csv` /
`_monthly.csv`.

| Channel | Period | n rows | total qty | not_late (row-weighted) | not_late (unit-weighted) |
|---|---|---|---|---|---|
| Omni Channel | P1 (2025-05→2026-04) | 2,069 | 13,068 | 86.5% | **89.4%** |
| Omni Channel | P2 (2026-05→2026-09) | 751 | 2,675 | 80.7% | **57.2%** |
| Tendering | P1 | 56 | 13,348 | 80.4% | **84.9%** |
| Tendering | P2 | 29 | 24,576 | 62.1% | **44.3%** |

**Both channels decline from P1 to P2** — Omni −32.2pp, Tendering −40.6pp (unit-weighted). This
weakens a purely Omni-specific "capacity was diverted away from Omni" story on this measure alone:
if Omni's share of shared capacity was specifically squeezed, Tendering's own on-time performance
would not necessarily also fall. Tendering's P2 figure rests on only 29 rows — directional only,
per the task brief.

**Reconciliation with the established figures** (not a contradiction, a different window):
DATA_MAP.md/STATUS.md report PEM107 Omni not_late (unit-weighted) at ~88.6% for 2024-2025 and
~76.5% for "2026 overall." My Period 1 figure (89.4%, May 2025–Apr 2026) is consistent with the
88.6% figure (overlapping but not identical window). My Period 2 figure (57.2%, May–Sep 2026 only)
is lower than the "2026 overall" 76.5%, because "2026 overall" also includes the strong
Jan–Apr 2026 months (86–96% unit-weighted per the monthly table below) — isolating May onward pulls
the average down. Both figures are **confirmed from this task's own recomputation** and are
consistent once the window difference is accounted for.

**Monthly pattern (Omni Channel, unit-weighted, selected months around the claimed separation
date)** — full series in `phase25_analyst3_m1_not_late_monthly.csv`:

| Month | not_late (unit-wtd) | n rows |
|---|---|---|
| 2026-03 | 96.2% | 178 |
| 2026-04 | 90.5% | 193 |
| 2026-05 | 84.3% | 119 |
| 2026-06 | **46.0%** | 154 |
| 2026-07 | 53.9% | 161 |
| 2026-08 | 82.4% | 199 |
| 2026-09 (partial) | 37.6% | 112 |

This **independently reproduces** the previously-established "June 2026 drop from ~84.3% to
~46.0%" figure (DATA_MAP.md/Q23) almost exactly (84.3%→46.0%, matched to the first decimal) — a
strong internal validity check that this task's own `not_late` computation is right. It also shows
the pattern is **not a clean step at May 2026**: May itself is still fairly high (84.3%), the crash
happens in June (one month later), performance partially **recovers** in August (82.4%), then falls
again in the partial September figure. A permanent one-time regime change (e.g., capacity
physically separated and never reunited) would not typically produce a recovery-then-relapse
pattern; this looks more like month-to-month operational volatility that happens to start around
June, not a discrete step exactly at May.

Tendering's monthly n is too small (0–15 rows/month, **zero Tendering deliveries recorded in May
2026 at all**) to read a step vs. gradual pattern reliably; reported for completeness in the CSV,
not further interpreted here.

**Confidence**: **V1** for this split (one Analyst pass, this task); the underlying `not_late`
method itself is **V2** (established METRICS.md §19 formula, and this task's May/June figures
independently reproduce the prior task's June 2026 figure to the first decimal).

---

## Measure 2: order-to-delivery interval (createDate proxy → ActualDelDate), days

Status='Actual' only. Median and IQR (p25/p75) reported per CONVENTIONS.md (this project's data is
lumpy; mean is also given but is not the headline figure). 1 row dropped for missing
`CtrDate`/`ActualDelDate`. Source: `phase25_analyst3_m2_order_to_delivery_period.csv` /
`_monthly.csv`.

| Channel | Period | n | median | IQR (p25–p75) | mean |
|---|---|---|---|---|---|
| Omni Channel | P1 | 2,046 | 16.0 | 6.25 – 30.0 | 26.5 |
| Omni Channel | P2 | 624 | **10.0** | 4.0 – 25.0 | 17.2 |
| Tendering | P1 | 54 | 30.0 | 22.0 – 46.5 | 39.6 |
| Tendering | P2 | 29 | **46.0** | 39.0 – 71.0 | 57.7 |

**Critical caveat, stated per the task brief**: this measure requires `ActualDelDate` (delivery
already happened), so orders created late in Period 2 that have **not yet delivered** are
structurally absent — this **right-censors** the most recent months toward shorter observed
intervals (only fast deliveries have had time to complete). The monthly table makes this visible
directly: Omni Channel's median interval **collapses to 10 days in 2026-08 and 2 days in 2026-09**
(n=41, partial month) — far faster than any earlier month (12–38-day medians throughout
2025–mid-2026) — this is very unlikely to be a genuine speed-up and is read as the censoring
artefact, not a real finding. **The Period 2 aggregate for Omni Channel (median 10 days) is
therefore reported but should be read as biased toward "faster," not trusted as a real change.**
Tendering's P2 figure (median 46, n=29) is less exposed to this because Tendering's own interval is
much longer (so fewer of its Period-2 orders have had time to complete at all — meaning Tendering's
Period-2 sample is even more selected toward the fastest-completing few of its already-small order
count; interpret directionally only).

Excluding the two most censoring-exposed months (2026-08, 2026-09) and looking only at 2026-05 to
2026-07 for Omni Channel: medians were 14, 10, 18 days (n=136, 115, 162) — broadly in the same
range as Period 1's monthly medians (11–22 days most months), i.e. **no clear change in this
measure once the censored tail is set aside.**

**Confidence**: **V1**, method reused from this project's established
`ForecastDelDate`/`CtrDate`/`ActualDelDate` field conventions; the right-censoring limitation is a
structural property of the measure, not a computational error, and is reported per AGENTS.md rule 1
(never present a figure without its known limitation).

---

## Measure 3: batch traceability — share of delivered contracts tracing to a pre-existing batch

Concept: same as DATA_MAP.md's established reverse-traceability proxy (§2, jobcode/jobno/OLMJobCode
entry — "all three reference the same underlying concept: a production-batch reference"; §3 Joins).
**Method difference from the established 58.9% pooled PEM107 figure, stated explicitly (AGENTS.md
rule 4 — this is a methodological difference, not a contradiction)**: the established 58.9% figure
(`phaseJ3_explorerD_analysis.py`) used each `OLMJobCode` token's own earliest `CtrDate` (within
Cube_CES) as a stand-in "batch existed" date, because `cube_final` returned **zero rows** in that
session (DATA_MAP.md Trap 7). This task's `cube_final` pull succeeded (8,723 rows; 89.1% of this
scope's distinct `jobno` values also appear as some row's `OLMJobCode` — a similar match rate to
the previously-reported 88.24% PEM107 forward-match figure). This task therefore uses **`cube_final`'s
own `final_date`** (the minimum `final_date` recorded for each `jobno`) as the batch-availability
date, joined to Cube_CES via `jobno` = `OLMJobCode` — a more direct measurement of the same concept,
not a recomputation of 58.9% by the same method. Classification: `traceable_pre_existing` (batch's
earliest `final_date` < this contract's `CtrDate`), `not_pre_existing` (batch link exists but not
pre-existing), `no_cube_final_link` (has an `OLMJobCode` token, but it never appears as a
`cube_final.jobno`), `no_token` (blank `OLMJobCode`). Denominator = all Status='Actual' rows in
scope (matches the established convention's denominator). Source:
`phase25_analyst3_m3_batch_traceability_period.csv` / `_monthly.csv`.

| Channel | Period | n contracts | total qty | traceable (row share) | traceable (qty share) | no cube_final link |
|---|---|---|---|---|---|---|
| Omni Channel | P1 | 2,047 | 12,441 | **54.0%** | 20.5% | 196 (9.6%) |
| Omni Channel | P2 | 624 | 1,678 | **62.2%** | 49.0% | 58 (9.3%) |
| Tendering | P1 | 54 | 10,103 | **0.0%** | 0.0% | 41 (75.9%) |
| Tendering | P2 | 29 | 24,576 | **0.0%** | 0.0% | 19 (65.5%) |

**Tendering: too sparse/unreliable to report a meaningful rate, stated plainly per the task
brief.** 41/54 (P1) and 19/29 (P2) of Tendering's delivered contracts have no `cube_final` link at
all under this join. Of the minority that DO link (13/54 P1, 9/29 P2), **none** show the batch
predating the order — 0 of 54 and 0 of 29 respectively are `traceable_pre_existing`. This is
reported as a genuine **structural** finding (Tendering essentially never traces to a pre-existing
batch under this proxy, in either period), not merely a small-sample artefact, though the small n
means it cannot rule out that a different/undetected linkage mechanism exists for Tendering.

**Omni Channel: traceability did not fall in Period 2 — if anything it rose** (54.0%→62.2% row
share, 20.5%→49.0% qty share). The monthly table (`_monthly.csv`) shows Omni's row-share bouncing
between 40% and 65% throughout 2025 and into 2026 with **no step visible at May 2026** — the
highest monthly values (60–76%) actually occur in June–September 2026, i.e., after the claimed
separation date, the opposite direction from what a "shared batch capacity was cut off" story would
predict.

**Confidence**: **V1** (this task's own computation, a different method from the established
58.9% figure as noted above, not yet independently recomputed by a second agent). The structural
Tendering finding (0% in every month with data, no step) is reported at the same V1 level but is
unusually consistent (flat zero across 15+ distinct months) which raises confidence in the pattern
itself even though the underlying method has not had a second independent pass this task.

---

## Measure 4: manufacturing_type mix (MTS/MTO/ETO), by count and by quantity

Computed directly on `cube_Sale_APD` order rows in scope — `manufacturing_type` is an **order-level
attribute, not a fixed per-item classification** (DATA_MAP.md §2), so no per-item dominant-type
derivation is used here, per the task brief. Status scope: reported at **Actual + MPS**
(METRICS.md §15's established "confirmed order" convention) as primary, since mix is set at
order-creation time, not delivery time, and restricting to delivered-only would right-censor Period
2's most recent orders out of the mix measure for no reason tied to what the mix actually is;
Actual-only is also reported alongside so the reader can see whether this choice matters (it does
not change the qualitative picture). No ETO observed in this scope (consistent with DATA_MAP.md:
"ETO is essentially never the per-item dominant type"). Source:
`phase25_analyst3_m4_manufacturing_mix_period.csv` / `_monthly.csv`.

**Actual + MPS** (primary):

| Channel | Period | MTS (count / qty share) | MTO (count / qty share) | n total | qty total |
|---|---|---|---|---|---|
| Omni Channel | P1 | 83.8% / 40.8% | 15.9% / 58.4% | 2,066 | 14,120 |
| Omni Channel | P2 | 86.0% / 44.8% | 14.0% / 55.2% | 720 | 3,065 |
| Tendering | P1 | 1.9% / 0.01% | 98.1% / 99.99% | 54 | 10,103 |
| Tendering | P2 | 0% / 0% | 78.4% / 95.0%* | 37 | 30,257 |

\* Tendering P2 also has 8 rows (21.6% count, 5.0% qty) with `manufacturing_type` not populated
(blank), reported separately, not folded into MTS or MTO.

**Tendering is essentially 100% MTO throughout both periods** — no shift at May 2026 (98.1%→~100%
of the non-blank rows, both before and after). **Omni Channel's mix is broadly stable in the
P1-vs-P2 aggregate** (MTS/MTO count shares within ~2pp of each other), but the **monthly series
shows a gradual downward drift in Omni's MTO count-share that predates May 2026 and continues
through it** — roughly 20–28% MTO in Jan–Jun 2025, declining to single digits by mid-2026 (6–19%),
with no visible discontinuity exactly at the May 2026 boundary. This is a **gradual drift spanning
the whole ~20-month window**, not a step tied to the claimed separation date.

**Confidence**: **V1** (one Analyst pass, this task). `manufacturing_type` itself is business-
confirmed (MTO=made to order, MTS=made to stock, ETO=engineering to order, DATA_MAP.md §2, level
**A**) but is known to be an order-level, not item-level, attribute — used here exactly as such, per
the task brief, so this figure is not compared against (and does not supersede) the separately-
established per-item dominant-type classification.

---

## Cross-measure summary and STEP-vs-GRADUAL read

| Measure | Change at/around May 2026? | Character |
|---|---|---|
| not_late (unit-weighted) | Yes, a real decline — but starts **June 2026, one month late**, and partially recovers in August before falling again in September | **Lumpy/volatile, not a clean step exactly at May** |
| Order-to-delivery interval | No reliable signal once right-censoring is set aside (2026-05→07 medians sit in the same range as 2025's) | Confounded by censoring; no clear step visible in the usable months |
| Batch traceability | Omni: no decline (rises slightly); Tendering: flat at 0% throughout | **No step in either channel** |
| Manufacturing mix | Omni's MTO share drifts down gradually across the whole ~20-month window; Tendering ~100% MTO unchanged | **Gradual, pre-existing drift (Omni); flat (Tendering)** — not tied to May 2026 |

## Verdict

Across the four behavioural measures tested, **PEM107 does not show a clean STEP in behaviour
exactly at May 2026.** The one measure with a real, substantial change — `not_late` unit-weighted —
begins in **June 2026** (Omni: 84.3%→46.0%, n=119→154 rows), one month after the claimed separation
date, and behaves erratically afterward (partial recovery to 82.4% in August, n=199, before falling
again to 37.6% in the partial September figure, n=112) rather than settling into a new, stable
regime — a pattern more consistent with ongoing operational volatility than a single discrete
structural event. **Both Omni Channel and Tendering decline on this measure in Period 2** (Omni
−32.2pp, Tendering −40.6pp unit-weighted, though Tendering's n=29 is too small to weigh heavily),
which is not what a purely Omni-specific capacity-diversion story would predict on its own. The
other three measures show **no step at all**: batch traceability is flat (Tendering, 0% in every
one of 15+ months with data) or mildly rising (Omni, 54.0%→62.2%), and manufacturing-type mix drifts
gradually across the whole window (Omni) or stays flat (Tendering, ~100% MTO throughout), with no
visible discontinuity at the May 2026 boundary on either.

These behavioural findings are additional to, and consistent in direction with, the already-
recorded data contradiction of the "separated in May 2026" timing (DATA_MAP.md §7: the actual
batch-sharing change point is October/November 2024, ~19-20 months earlier, level **V2**). This
task's contribution is that even setting the timing question aside entirely, the **behavioural**
measures themselves — not just the batch-sharing indicator — do not line up with a May 2026 step
either.

**Overall confidence**: **V1** for every figure in this report (one Analyst pass, this task, not
yet independently recomputed by a second agent) — with the exception of the not_late computation
method itself, which reaches **V2** by virtue of independently reproducing the previously-
established June 2026 figure (84.3%→46.0%) to the first decimal. Per AGENTS.md, this report should
be treated as one input to Q10/Q23, to be checked against the other three agents' independent
findings (batch-linkage blindness and categorical-shift questions) before any conclusion is locked.

---

## Data-hygiene note

The raw pulls (`phase25_analyst3_cube_ces_raw.csv`, `_cube_final_raw.csv`, `_sale_apd_raw.csv`)
were pulled with `ContractID`/`contractid`, `CustomerID`, `CustomerName`, `customer_name`, `ctrno`,
`pono`, `cus_serialno`, and `fg_pack_name` (an employee-name field) included, because the shared
pull helpers (`src/cube_ces_pull.py`'s `CUBE_CES_COLUMNS`, `src/cube_final_pull.py`'s
`CUBE_FINAL_COLUMNS`) return these by default. None of these columns were used by any computation
in this report (verified against `phase25_analyst3_analysis.py`: only `ItemCode`, `Status`,
`CtrDate`, `PlanDelDate`, `ForecastDelDate`, `ActualDelDate`, `ActualQty`, `RevenueType`,
`OLMJobCode` from Cube_CES; only `jobno`, `final_date`, `itemcode` from `cube_final`; only
`itemcode`, `createDate`, `qty`, `status`, `revenue_type`, `manufacturing_type` from
`cube_Sale_APD`). These columns were dropped from the saved CSVs in `output/summary/` after the
pull, before this report was written, per this task's "no customer names/contract IDs/employee
names in anything you write" instruction.
