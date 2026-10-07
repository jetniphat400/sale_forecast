# Phase E1.3 — Max-Min scenario with forecast consumption

**Scope: ONLY the 66 items where E1.1 found finished-goods stock is the segment's supported
policy** (`phaseE1_1_item_segments.csv`, `fg_stock_policy_supported == True`) — the 46
low-value/low-freq items (Component-ATO recommended) and the 16 excluded/placeholder items get
**NO Min, Max or purchase quantity here**, per the task's scope restriction and the hard
acceptance criterion. **Bounded scenario pilot — no actionable purchase recommendation.**

Script: `src/phaseE1_maxmin_scenario.py`. Outputs: `phaseE1_3_scenario_grid.csv` (18 rows),
`phaseE1_3_minmax_all_scenarios.csv` (1,188 = 66×18 rows), `phaseE1_3_minmax_default_scenario.csv`
(66 rows), `phaseE1_3_forecast_consumption.csv`, `phaseE1_3_forecast_consumption_monthly_summary.csv`,
`phaseE1_3_sellable_stock.csv`. Chart: `output/charts/phaseE1_minmax_scenario_sensitivity.png`.

## 1. Cycle service level ≠ unit fill rate (stated once, applies everywhere)

**Cycle service level** (this section's scenario input, 90/95/98%) is the probability of NOT
stocking out during one replenishment cycle. **Unit fill rate** (only computable in E1.4's
simulation) is the % of demand UNITS delivered on time. These are different statistics; this
script only SETS a cycle-service-level TARGET via the percentile choice — whether that target is
actually achieved, and what unit fill rate results, is reported separately in
`phaseE1_4_historical_simulation_report.md`.

## 2. The 18-scenario grid, and the designated default scenario

All 3 (lead time) × 2 (assembly time) × 3 (service level) = **18 scenarios computed**
(`phaseE1_3_scenario_grid.csv`). **Default scenario: 60-day lead time, 3-day assembly time
(the config DEFAULT, not the alternative), 95% cycle service level** — the middle/most-typical
value on every axis (`config['phase_e1_assumptions']['default_scenario']`), not tuned to produce
a favourable result. Protection period = 4 months for this scenario (per E1.2).

## 3. Min/Max formula and conventions

- **Min = mean of the empirical protection-period demand distribution (E1.2, at the exact
  rounded horizon this scenario needs) + safety stock**, where **safety stock = the chosen
  percentile MINUS the distribution's own mean** — the buffer ABOVE the expected value.
  Algebraically, Min = the percentile value directly; both are reported in
  `phaseE1_3_minmax_all_scenarios.csv` (`mean_protection_period_demand`, `safety_stock`,
  `min_qty`) so the convention is auditable, not just asserted.
- **Max = Min + a replenishment quantity**, where the replenishment quantity = this item's mean
  monthly qty (full 31-month history) × (review interval days / 30.44) — i.e. the review
  interval's own expected demand. **Stated explicitly as a convention, not a derived fact**: no
  MOQ or lot size exists in this data (business-confirmed absent, STATUS.md Section 8.3) — a
  different convention (e.g. a fixed round-number lot) would give a different Max.

## 4. Default-scenario headline (66 items)

- **Mean Min across the 66 FG-stock items: 8,879.4 units. Mean Max: 10,404.3 units.**
  (`phaseE1_3_minmax_default_scenario.csv`.) Category: **verified computation under stated
  assumptions** (the formula is exact; the INPUTS — lead time, assembly time, service level,
  review interval — are scenario assumptions, not facts).
- 0 of 66 default-scenario items carry the `too_few_for_upper_percentiles` flag from E1.2 (all
  66 FG-stock items have ≥10 non-zero 4-month windows — the thin-tail flag mainly affects the
  46 low-value/low-freq items excluded from this table, which is the expected pattern: items
  with enough value/frequency to be FG-stocked also tend to have enough history for a
  meaningful upper percentile).

## 5. Forecast consumption — worked logic, reconciled against double-counting

**Logic** (`config['phase_e1_assumptions']['forecast_consumption_logic']`):
`net_period_demand = confirmed_known_demand + max(0, statistical_forecast − confirmed_known_demand)`
— confirmed demand is never added ON TOP of the full forecast (that would double count); only
the REMAINING, not-yet-confirmed portion of the forecast is added on top of what's already known.

**Forward-looking, not a backtest**: uses a genuine Top-down forecast for 2026-08 through
2026-11 (the default scenario's 4-month protection period, starting the month immediately after
the last month in the historical series, 2026-07) — `src/phaseE1_common.py::topdown_item_forecast`
with `fit_end=31` (full history), fit fresh, not reused from any backtest origin.

**No-double-count check on the historical-inclusion channel (verified directly)**: confirmed
future orders are pulled with `status='MPS' AND forecast_date > 2026-07-31` — by construction
these rows cannot already be in the 2024-01..2026-07 historical monthly series (which is
truncated to that exact window), so adding them as "confirmed future demand" cannot double-count
history that has already passed. **291 such rows found for the 66 FG items; 285 fall inside the
4-month forward window used here.**

**Cube_Backlog vs cube_Sale_APD MPS overlap — CANNOT BE DETERMINED from data** (no shared key
exists between the two tables — confirmed by this project's own Reserved/Available investigation
chain, STATUS.md). **Resolved by scope decision, not verification**: future-period confirmed
demand is read from cube_Sale_APD MPS rows ONLY; Cube_Backlog is used ONLY for OVERDUE rows
(delivery/plan date already before the snapshot pull date, 2026-09-04), added as immediate
Period-1 demand per the task's own instruction. This is the ONE place the two sources are
combined, and only additively for the immediate period — stated explicitly as a limitation, not
a proof of no overlap.

**Per-month consumption table** (`phaseE1_3_forecast_consumption_monthly_summary.csv`, sum
across all 66 items):

| month | raw forecast (qty) | confirmed known (qty) | % of forecast consumed | net period demand |
|---|---:|---:|---:|---:|
| 2026-08 | 121,342 | 179 | 0.1% | 121,433 |
| 2026-09 | 121,342 | 23,791 | 19.6% | 123,333 |
| 2026-10 | 121,342 | 6,477 | 5.3% | 121,557 |
| 2026-11 | 121,342 | 2,303 | 1.9% | 121,614 |

(Total raw forecast is identical across months because the Top-down Combination method produces
a constant-level forecast repeated across the horizon, per `src/models.py`'s own documented
behaviour — this is a property of the forecasting method, not a bug in this table.) Category:
**verified computation**, on top of a **stated scope decision** (the Cube_Backlog/MPS overlap
handling above).

## 6. Sellable stock context (FG01/FG21/WH21 — config assumption)

`phaseE1_3_sellable_stock.csv`: of the 66 FG-stock items, **61 have nonzero stock in
{FG01, FG21, WH21}, totalling 121,425 units.** Sellability itself was never confirmed by any
field (Phase D headline: 0.00% confirmed sellable, 99.90% undetermined) — this figure uses the
config assumption `sellable_warehouse_codes` (owner: business), not a verified sellable-stock
fact. Category: **assumption-dependent figure**, cited as such.
