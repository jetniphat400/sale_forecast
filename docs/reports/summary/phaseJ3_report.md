# Phase J3 — Inverse Calibration (METRICS.md Sec.20)

**Target node:** Q10 (how the business actually fulfils orders and replenishes). **Date:** 2026-09-23
(this file was never committed to git, so `git blame` does not apply to it directly; this date is
taken from the Phase J3 commits' own dates instead — `709645d`/`34bceca`/`d399877`, all
2026-09-23, per `git log --format="%h|%ad" --date=iso -- DATA_MAP.md PROJECT_GRAPH.md STATUS.md`
filtered to the Phase J3 commit messages — stated here as the source, per task instruction).

## Part 1 — Reconciliation and new evidence

**Why 97.8% (Phase J) and 87.9% (Phase J2) both exist, PEM101 unit-weighted `not_late`:** not a
bug either side. Item scope, status filter and weighting are identical between the two
computations. The only real difference is the window: Phase J bounds by `ForecastDelDate` in
[2024-01, 2026-07]; Phase J2 buckets by `CtrDate` calendar YEAR 2023-2026, which pulls in a
genuinely much worse 2023 (55.97% unit-weighted `not_late`, vs. ~97-99% in 2024-2026). Quantified:
-10.29pp from including 2023, +0.35pp from the bucketing-method difference, net -9.93pp — matches
the observed gap almost exactly. `ForecastDelDate` is the METRICS.md Sec.18/19/20-correct field.

**Reconciled targets** (`output/summary/phaseJ3_validator_reconciliation.md`):

| Division | Calib not_late (2024-01/2025-12) | Valid not_late (2026-01+) | Current stock value |
|---|---|---|---|
| PEM101 | 97.70% | 98.28% | THB 18.25M |
| PEM103 | 90.89% | 96.56% | THB 6.06M |
| PEM107 | 86.61% | **76.54% (real degradation)** | THB 3.40M |

**Explorer D** (`output/summary/phaseJ3_explorerD_report.md`): a second, clean `cube_final`
connection still returned zero rows — contradicts Phase J2's "crashed session" theory; genuinely
CANNOT BE DETERMINED why. Reverse-traceable batch share by division: PEM101 2.0%, **PEM103 69.3%,
PEM107 58.9%** (pooled 13.8/14.5% hid this split). Per-item-typical cadence: PEM101 56d, PEM103
36d, PEM107 58d (all wide spreads).

**Explorer BOM** (`output/summary/phaseJ3_explorerBOM_report.md`): `Cube_BOM_Exact` covers 85.8% of
scope (PEM103 only 58.6%); components ARE shared across finished items (141/805, 17.5%) — answers
Q18. Join to `Cube_Inventory_Exact` confirmed both directions (95.0%, V2). 14 of Phase J2's 16
zero-stock-fast-delivery items have a stocked component — PLAUSIBLE, not VERIFIED.

## Part 2/3 — Calibration and independent check

Grid: review interval [1,7,14,30,60,90,130] days; lead time [1,3,5,7,15,30,45,60,75,90] days;
reorder level r and order-up-to S in months of mean demand, r∈[0.25..6], S∈[0.5..8] (S>r) —
extended twice after the first two passes kept clipping their own edge, disclosed in the script.

| Division | Result | Best fit | Identified? |
|---|---|---|---|
| PEM101 | **Partially calibrated** — 59/4,130 combos fit both periods at realistic stock | r=0.5mo, S=2.5mo, review=1d, lead=3d | No parameter uniquely identified (all 4 span >1 grid step) |
| PEM103 | **Not calibratable** at realistic stock — needs 5-12x more capital (best 57.6M vs 6.06M real) | r=3mo, S=7mo, review=1d, lead=7d | N/A |
| PEM107 | **Not calibratable** at all — no policy fits both periods (best joint gap 14-18pp) | r=0.25mo, S=6mo, review=30d, lead=1d | N/A |

Independent Validator (own code from METRICS.md Sec.16/20, never read the Modeler's scripts):
**12/12 figures match** (`output/summary/phaseJ3_validator2_independent_check.md`).

## Part 4 — Gate

- **PEM101 — calibrated with wide uncertainty bands.** May be used for scenarios only with those
  bands stated (r 0.25-2.0mo, S 1.5-3.0mo, review 1-30d, lead 1-30d), not as a single policy.
- **PEM103 — not calibratable from data.** Narrowest question: **does PEM103 fulfil orders
  primarily through production-batch timing rather than finished-goods buffer stock, and if so,
  what governs batch timing/size?**
- **PEM107 — not calibratable from data.** Narrowest question: **what changed operationally for
  PEM107 between 2024-2025 and 2026 that dropped delivery performance from ~87% to ~77%?**
- **Fallback evidence** (Explorer C, Phase J2, pooled across items not per-division): on-hand
  stock tier vs. delivery speed — zero stock 30.5% within 14d (median 25d); some stock 66.0%
  (median 8d); substantial stock 85.6% (median 5d). Monotonic, real, but not a per-division
  calibration.

## Part 5 — Knowledge updates

DATA_MAP.md: new Cube_BOM_Exact table entry, 3 new Joins rows, jobcode/cube_final corrections, 2
new Corrections-log rows. PROJECT_GRAPH.md: Q10 → in progress (answered per-division), Q17 → in
progress (cadence known, size/dates blocked), Q18 → done. STATUS.md: this Phase J3 entry.
