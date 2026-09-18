# Phase E1.1 — Segment items and compare stocking policies

**Scope: PEM101 128-item pilot only** (`config['adopted_scope_file']`,
`output/summary/part1_category_scope_all_codes.csv`, re-derived and confirmed at 128 rows by
`src/phaseE1_common.py::load_scope`, not assumed from `config['pilot_categories']`'s 10+58=68
figure — the 128-item scope is the **Category**-level Fuse + Surge Arrester scope (8 Types, 2
Categories) that every backtest since Phase 3.1 has used). **This is a BOUNDED SCENARIO PILOT: it
produces NO actionable purchase recommendation, only a scenario analysis for the business to
evaluate.**

Script: `src/phaseE1_segment_items.py`. Outputs: `phaseE1_1_item_segments.csv` (128 rows, one per
item), `phaseE1_1_segment_summary.csv`, `phaseE1_1_notice_vs_leadtime.csv`,
`phaseE1_1_ato_sensitivity.csv`, `phaseE1_1_segment_verdicts.csv`, `phaseE1_1_no_policy_items.csv`.
Chart: `output/charts/phaseE1_segment_value_count.png`.

## 1. Critical exclusion check (done first, per instruction)

Of the 128 items: **6 overlap `config['excluded_item_codes']`** (never sold, zero demand
anywhere) and **10 overlap `config['placeholder_item_codes']`** (sold only outside this
project's scope, or unclassifiable) — **0 overlap `config['placeholder_item_assignments_82']`**
(that 82-item list belongs to a disjoint, non-PEM101/Fuse/Surge-Arrester population from Phase
C, so zero overlap is the expected, verified result, not an omission).

**16 of 128 items (6 + 10) get NO segmentation-driven policy** — `phaseE1_1_no_policy_items.csv`
lists each with its reason, e.g. `"no supported policy: excluded_item_codes — listed in
pricelist but never sold, zero demand history anywhere"` / `"no supported policy:
placeholder_item_codes — sold only outside this project's scope or unclassifiable, no real
item-specific forecast exists"`. **These 16 items receive no Min, Max or purchase quantity
anywhere in Phase E1** (verified — category: **verified**, by construction of every downstream
script, which reads `eligible_for_policy`/`fg_stock_policy_supported` before computing anything).

**112 of 128 items are `eligible_for_policy`.** All 112 have a full 31-month
(2024-01 to 2026-07) history in the forecast_date-keyed monthly series
(`output/data/processed_full_category_sales_monthly_forecastDate.csv`) — confirmed by
`load_monthly_series`'s length check. Category: **verified**.

## 2. Demand classification (ADI/CV², re-derived at this 128-item scope)

Method: SBC (2005) thresholds reused verbatim from `src/investigations/series_features.py`
(`ADI_THRESHOLD=1.32`, `CV2_THRESHOLD=0.49`), computed on each item's own full 31-month qty
series (not assumed unchanged from the Phase 1 dashboard, which classified at the OLD, different
scope). Category: **verified**.

| demand_class | n_items (eligible) |
|---|---|
| Smooth | 33 |
| Erratic | 24 |
| Intermittent | 26 |
| Lumpy | 29 |

(112 total, matches `eligible_for_policy` count.)

## 3. Annual value and order frequency

- **Annual value** = mean monthly `sale` value (cube_Sale_APD's own recorded revenue column,
  already present in the loaded monthly series) × 12. **Stated choice**: uses `sale` (revenue),
  not qty × a separately-queried unit cost — avoids an extra query and is directly available;
  a qty×unit-cost basis would give a related but not identical figure (unit cost is a
  cost/valuation basis, `sale` is a revenue basis — the choice is stated so a reader isn't misled
  about which one this is). Category: **verified** (direct aggregation of a DB column already
  loaded).
- **Order frequency** = distinct order LINES per year, from a fresh raw pull of `cube_Sale_APD`
  (Omni Channel, Actual+MPS, `createDate >= 2024-01-01`) — **28,130 order lines used** (16
  dropped for null/negative-interval `forecast_date`, the same known anomaly class Phase A/B
  already document), divided by 31/12 years. **Stated choice**: order-line count, not
  "distinct months with any demand" — chosen because the same raw pull already needed for the
  notice-vs-lead-time comparison below gives a finer-grained, more literal "how often is this
  item ordered" figure than a months-with-demand proxy. Category: **verified**.
- Cross-check: this pull's **project-wide median notice is exactly 6.0 days and 5.9% of orders
  give ≥30 days' notice** — reproduces STATUS.md's existing Business Findings figures exactly
  from an independent fresh query, confirming the query logic. Category: **verified**.

## 4. Segments

Segment = demand class × a `low_value_low_freq` flag, where the flag is true only for
**eligible** items at or below BOTH the eligible population's own median annual value AND median
order frequency (median splits computed only over the 112 eligible items, not the full 128, per
`assign_segments`). This is a stated methodology choice (median split), not a business rule.

| segment | n_items | total_annual_value (THB) | mean_order_freq/yr |
|---|---:|---:|---:|
| Smooth (other) | 33 | 174,134,063 | 274.4 |
| Erratic (other) | 23 | 50,208,434 | 61.9 |
| Intermittent (other) | 2 | 8,863,645 | 26.3 |
| Lumpy (other) | 8 | 7,892,657 | 18.0 |
| Lumpy (low-value/low-freq) | 21 | 1,856,747 | 6.7 |
| Intermittent (low-value/low-freq) | 24 | 1,591,603 | 2.1 |
| Erratic (low-value/low-freq) | 1 | 168,842 | 21.7 |

(No `Smooth (low-value/low-freq)` segment exists — no Smooth item fell at or below both medians
simultaneously; not an omission, a genuine data outcome.) Category: **verified**.

## 5. Policy evaluation per segment

Three business facts anchor every verdict: median customer order notice 6 days (STATUS.md
Business Findings, reproduced above); procurement lead time 45-60 days (business figure,
configurable per item, `config['phase_e1_assumptions']['procurement_lead_time_days_grid']`);
assembly time NOT in any data source (STATUS.md Section 8.5, a genuine unresolved gap — treated
here as a configurable assumption, default 3 days / alternative 7 days,
`assembly_time_days_default`/`_alternative`, owner: Modeler default).

### Make-to-order feasibility (ruled out for every segment, with the actual gap)

`phaseE1_1_notice_vs_leadtime.csv` — % of each segment's own order lines whose notice clears each
lead-time-grid value:

| segment | median notice (d) | %>45d | %>60d | %>75d |
|---|---:|---:|---:|---:|
| Erratic (low-value/low-freq) | 4.0 | 1.8% | 0.0% | 0.0% |
| Erratic (other) | 6.0 | 3.0% | 2.0% | 1.4% |
| Intermittent (low-value/low-freq) | 8.0 | 6.3% | 6.3% | 4.7% |
| Intermittent (other) | 10.5 | 0.0% | 0.0% | 0.0% |
| Lumpy (low-value/low-freq) | 6.0 | 9.1% | 4.7% | 2.5% |
| Lumpy (other) | 9.0 | 6.2% | 5.7% | 5.4% |
| Smooth (other) | 6.0 | 3.1% | 2.1% | 1.5% |

**Make-to-order is ruled out for every segment**: median notice is 4-10.5 days against a 45-75
day lead-time grid — a gap of roughly **35-70 days** in every segment — and even at the most
generous end (notice > 45 days, the LOW end of the lead-time grid) only 0-9% of order lines would
clear it. Category: **verified**.

### Component stock, assemble-to-order — sensitivity table (`phaseE1_1_ato_sensitivity.csv`)

Feasible when the segment's own median notice (falling back to the project-wide 6-day figure if
the segment has fewer than 10 order lines) ≥ the assumed assembly time:

| segment | median notice used (d) | 1d | 3d | 5d | 7d | 10d |
|---|---:|:--:|:--:|:--:|:--:|:--:|
| Erratic (low-value/low-freq) | 4.0 (segment, n=56) | Y | Y | N | N | N |
| Erratic (other) | 6.0 (segment, n=3678) | Y | Y | Y | N | N |
| Intermittent (low-value/low-freq) | 8.0 (segment, n=128) | Y | Y | Y | Y | N |
| Intermittent (other) | 10.5 (segment, n=136) | Y | Y | Y | Y | Y |
| Lumpy (low-value/low-freq) | 6.0 (segment, n=364) | Y | Y | Y | N | N |
| Lumpy (other) | 9.0 (segment, n=371) | Y | Y | Y | Y | N |
| Smooth (other) | 6.0 (segment, n=23,396) | Y | Y | Y | N | N |

At the **default** 3-day assembly assumption, every segment clears the feasibility bar
(median notice ≥ 3 days everywhere) — component stock/ATO is mechanically FEASIBLE for all
segments at 3 days; the sensitivity table shows this stops holding once assembly time reaches
7-10 days for most segments. Category: **verified given the stated assembly-time assumption**
(the feasibility verdict itself is conditional on an unproven assumption, not a fact).

### Final verdicts (not a blanket finished-goods default)

- **"(other)" segments — 66 items, THB 241.1M/yr — Finished-goods stock SUPPORTED.** Their own
  median notice (6-10.5 days) sits far below even the low end of the lead-time grid (gap
  49.5-54 days); make-to-order is ruled out; these segments' own annual value and order frequency
  are high enough that holding assembled stock is worth the capital tied up.
- **"(low-value/low-freq)" segments — 46 items, THB 3.6M/yr total — Component stock,
  assemble-to-order SUPPORTED by these segments' OWN numbers, not a blanket default.** These 46
  items carry a median annual value of roughly THB 67K-169K per item and order 2-22 times/year —
  low enough that holding a full year of assembled finished-goods stock ties up capital for
  demand that materialises rarely, while their own median notice (4-8 days) still clears the
  default 3-day assembly assumption. Finished-goods stock is **not ruled out** for these items —
  it remains available as a fallback if the business does not want to build assembly-on-demand
  capability for a fuse/surge-arrester line — but the segments' own value/frequency numbers do
  not make a strong case for it the way the "(other)" segments do.
- **16 excluded/placeholder items — no supported policy at all** (Section 1 above).

**Per the task's explicit instruction not to default every item to finished-goods stock: the
46-item low-value/low-frequency population above is exactly that case, made from its own
segment numbers, not asserted.** Category for every verdict above: **hypothesis with cited
evidence** (a reasoned policy recommendation from real segment statistics, not a certainty — a
different median-split threshold or a different low-value/low-freq definition could shift some
items across the boundary).

## 6. Downstream consequence for E1.3/E1.4

Only the 66 "(other)"-segment items feed E1.3's Max-Min scenario grid
(`fg_stock_policy_supported == True` in `phaseE1_1_item_segments.csv`) — the 46 low-value/
low-freq items and the 16 excluded/placeholder items get **no Min, Max or purchase quantity**
anywhere in this phase.
