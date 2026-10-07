# Phase E1 — Modeler Report (top-level synthesis)

**Role reminder (AGENTS.md): this is the Modeler's report. It reports how the scenario performed
— it does NOT decide whether to adopt it. That decision belongs to the Orchestrator, informed by
this report and the Validator's independent recomputation. This report does not validate its own
figures beyond ordinary sanity checks (row-count reconciliations, overlap checks) — a separate
Validator will independently recompute headline figures from raw data and config alone.**

**Scope, repeated because it governs every number in this phase: PEM101 only, the 128-item
pilot** (`config['adopted_scope_file']`, re-derived and confirmed at exactly 128 rows — NOT
assumed from `config['pilot_categories']`'s 10+58=68 figure, which describes only the original
two pilot Types before the scope was expanded to the full Fuse+Surge Arrester Category level for
backtesting from Phase 3.1 onward). **This is a BOUNDED SCENARIO PILOT. It produces NO
actionable purchase recommendation — it produces a scenario analysis the business can evaluate.**

## 1. What was built

| Sub-phase | Script | Report | Key outputs |
|---|---|---|---|
| Shared data access | `src/phaseE1_common.py` | — | scope/series/cost/inventory/backlog/order-level loaders, reused by every script below |
| E1.1 Segmentation | `src/phaseE1_segment_items.py` | `phaseE1_1_segmentation_report.md` | `phaseE1_1_item_segments.csv`, `_segment_summary.csv`, `_notice_vs_leadtime.csv`, `_ato_sensitivity.csv`, `_segment_verdicts.csv`, `_no_policy_items.csv`; chart `phaseE1_segment_value_count.png` |
| E1.2 Lead-time demand | `src/phaseE1_leadtime_demand.py` | `phaseE1_2_leadtime_demand_report.md` | `phaseE1_2_scenario_horizons.csv`, `_rolling_origin_cumulative.csv`, `_horizon_position_bias.csv`, `_mase_summary.csv`, `_empirical_distribution.csv`; chart `phaseE1_leadtime_demand_distribution_focus_items.png` |
| E1.3 Max-Min scenario | `src/phaseE1_maxmin_scenario.py` | `phaseE1_3_maxmin_scenario_report.md` | `phaseE1_3_scenario_grid.csv`, `_minmax_all_scenarios.csv`, `_minmax_default_scenario.csv`, `_forecast_consumption.csv`, `_forecast_consumption_monthly_summary.csv`, `_sellable_stock.csv`; chart `phaseE1_minmax_scenario_sensitivity.png` |
| E1.4 Historical simulation | `src/phaseE1_historical_simulation.py` | `phaseE1_4_historical_simulation_report.md` | `phaseE1_4_simulation_item_scenario.csv`, `_scenario_summary.csv`, `_simulation_default_scenario_monthly.csv`; chart `phaseE1_historical_simulation_default_scenario.png` |
| E1.5 Current-settings comparison | `src/phaseE1_current_settings_comparison.py` | `phaseE1_5_current_settings_comparison_report.md` | `phaseE1_5_current_vs_scenario.csv`, `phaseE1_5_current_stock_value_128items.csv` |

All scripts are independently re-runnable (`python src/phaseE1_<name>.py`), read
`config/config.yaml` for every tunable value (no magic numbers), use `logging` (not `print`) for
progress, and report rows processed/dropped/why per CONVENTIONS.md.

## 2. Default scenario — headline figures

**Default scenario: 60-day procurement lead time, 3-day assembly time (config default), 95%
cycle service level, 30-day review interval → 4-month protection period.**

| Metric | Value | Category |
|---|---|---|
| Items covered by this scenario | 66 of 128 (the "(other)"-segment, FG-stock-supported items) | verified |
| Mean Min / Max across those 66 items | 8,879.4 / 10,404.3 units | verified computation under stated assumptions |
| Simulated mean unit fill rate (E1.4) | 98.99% | verified simulation output under stated assumptions |
| Simulated stockout item-months | 6 of 2,046 (0.29%) | verified |
| Simulated mean stock value (66 items) | THB 55,399,687 | verified |
| Current stock value, 128-item pilot scope (apples-to-apples, E1.5) | THB 18,071,706.20 | verified |
| Current stock value, FULL 445-item universe (cited, Phase D) | THB 37,399,005.48 | verified citation, different scope |

## 3. Every assumption, with its config key and owner

| Assumption | Config key | Value | Owner |
|---|---|---|---|
| Procurement lead-time grid | `phase_e1_assumptions.procurement_lead_time_days_grid` | [45, 60, 75] | business (45/60 confirmed); Modeler default (75, sensitivity point) |
| Procurement lead-time default | `...procurement_lead_time_days_default` | 60 | business (middle of confirmed range) |
| Assembly-time default/alternative | `...assembly_time_days_default` / `_alternative` | 3 / 7 | Modeler default — business has not supplied this figure (genuine gap, STATUS.md §8.5) |
| Assembly-time sensitivity range (E1.1) | `...assembly_time_sensitivity_days` | [1,3,5,7,10] | Modeler default |
| Review interval | `...review_interval_days_default` | 30 | Modeler default — no business figure exists at all |
| Cycle service-level grid/default | `...cycle_service_level_grid` / default scenario | [90,95,98]%, default 95% | business must choose (STATUS.md §8.5); 95% used only as this phase's reference point |
| Default scenario designation | `...default_scenario` | lead 60d, assembly 3d, SL 95% | Modeler (middle of every grid) |
| Replenishment-quantity convention | `...replenishment_qty_convention` | review interval's own expected demand | Modeler default — no MOQ/lot size exists (business-confirmed absent) |
| Safety-stock convention | `...safety_stock_convention` | percentile − mean | Modeler (a stated, consistent convention) |
| Sellable warehouse codes | `...sellable_warehouse_codes` | [FG01, FG21, WH21] | business — sellability was never confirmed by any field; this is the best available proxy |
| Unit-cost basis | `...unit_cost_basis` | median-12mo cost/qty, most-recent fallback | Modeler default — reused from Phase D Check 2 for consistency |
| Obsolescence threshold | `...obsolescence_threshold_months` | 6 months | Modeler default — no business figure exists |
| Simulation initial stock | `...simulation_initial_stock_assumption` | start at scenario's own Max | Modeler default — no 2024-01 stock figure exists in any table |
| Simulation receipt timing | `...simulation_receipt_timing_assumption` | deterministic `ceil((lead+assembly)/30.44)` months | Modeler default — real variability documented but not modellable without a movement history |
| Simulation fulfilment sequence | `...simulation_fulfilment_sequence_assumption` | receipts first, then demand; unmet demand backordered | Modeler default |
| Forecast consumption logic | `...forecast_consumption_logic` | confirmed + max(0, forecast − confirmed) | Modeler (worked logic, not a business rule) |
| Backlog-vs-MPS double-count handling | `...backlog_vs_mps_double_count_note` | use MPS for future periods, backlog only for overdue/Period-1 | Modeler — cannot be verified from data (no shared key) |
| Low-value/low-freq segment split (E1.1) | (not a config key — a script-level methodology choice, `phaseE1_segment_items.py::assign_segments`) | median split on both dimensions | Modeler default |
| MASE-undefined / thin-tail threshold (E1.2) | (script-level, `MIN_NONZERO_FOR_UPPER_PERCENTILE=10` in `phaseE1_leadtime_demand.py`) | 10 non-zero windows | Modeler, reused from this project's own Phase 4 prep-investigation precedent |

Every one of the above is written into `config/config.yaml` under `phase_e1_assumptions:`
(added 2026-09-18), each with an inline comment explaining the reasoning — the two script-level
choices (segment median split, MASE/thin-tail threshold) are methodology parameters internal to
one script's own logic rather than externally-facing scenario inputs, and are documented in
their scripts' docstrings and the corresponding sub-phase reports instead.

## 4. Acceptance criteria — self-assessed (Orchestrator will independently confirm with the Validator)

1. **Every item has a supported policy or a stated reason it cannot be assigned — PASS.**
   128 = 66 (FG-stock, E1.1 "(other)" segments) + 46 (Component-ATO, E1.1 low-value/low-freq
   segments) + 16 (no supported policy: 6 excluded_item_codes + 10 placeholder_item_codes, each
   with a cited reason in `phaseE1_1_no_policy_items.csv`). Verified by direct row-count
   reconciliation (66+46+16=128).
2. **Every assumption is in `config.yaml` with an owner and a scenario label — PASS.** See
   Section 3's table; every config key carries an inline comment stating it is a scenario input,
   not a fact, and names an owner.
3. **No placeholder item receives a Min, Max or purchase quantity — PASS, verified directly.**
   Checked by set-intersection between `excluded_item_codes ∪ placeholder_item_codes` and every
   itemcode appearing in `phaseE1_3_minmax_all_scenarios.csv`, `phaseE1_4_simulation_item_scenario.csv`,
   and the non-null `scenario_default_min` rows of `phaseE1_5_current_vs_scenario.csv` — **zero
   overlap found in all three checks.**
4. **Default scenario: fill rate ≥ 73.2% — PASS. Stock value ≤ THB 37.4M — FAILS.**
   - **Fill rate: 98.99% simulated ≥ 73.2% current — PASSES by a wide margin.** Category:
     **verified** figure, but qualified: this is a fill rate under an idealised simulation with
     no real starting-stock data (Section 5 caveats below apply).
   - **Stock value: FAILS, and by a large margin, on every comparison basis available.** The
     default scenario's simulated mean stock value for its own 66-item scope is **THB
     55,399,687** — this ALONE exceeds the cited THB 37.4M figure for the FULL 445-item
     universe, before any scope adjustment. The honest apples-to-apples 128-item-pilot-scope
     CURRENT value is **THB 18,071,706.20** — even smaller, making the gap larger still (the
     scenario would need roughly 3x today's 128-item-scope capital tied up, for 66 of the 128
     items alone). **By how much**: scenario (66 items) − current (128 items, full pilot scope)
     = THB 55,399,687 − 18,071,706 = **THB +37,327,981** more capital tied up, even though the
     scenario covers FEWER items (66 vs 128) than the current figure it's being compared against.
     **Best explanation (hypothesis, not proven)**: a 95% cycle-service-level target over a
     4-month protection period requires substantial safety stock for demand this variable
     (24 of 66 default-scenario items are Erratic/Lumpy/Intermittent, not Smooth) — under the
     empirical-distribution method (E1.2), safety stock for a volatile item can be several times
     its own mean protection-period demand (e.g. `EEE-F-FC-1040010002`: mean 4,338, safety stock
     6,451 — safety stock alone exceeds the mean). This is the EXPECTED shape of a
     percentile-based safety-stock policy applied to genuinely lumpy/erratic demand, not
     evidence of a computational error — but it is a real, material finding the business should
     see before adopting this scenario, not something to soften. A lower cycle-service-level
     target (90%, still computed in the 18-scenario grid) would reduce this gap; see
     `phaseE1_3_minmax_all_scenarios.csv` and `phaseE1_4_scenario_summary.csv` for the
     90%/98% alternatives.

**Net self-assessment: 3 of 4 acceptance criteria pass; criterion 4's stock-value half fails,
reported plainly with the actual gap size and a stated (not proven) explanation, per the ground
rules — this failure is not concealed or minimized.**

## 5. What could not be determined / had to be scoped down

- **Assembly time after parts arrive**: a genuine, business-confirmed data gap (STATUS.md §8.5)
  — every figure that depends on it (protection period, Min/Max, the simulation) is built on a
  Modeler-default assumption (3 days), not a fact. The E1.1 sensitivity table and the two-value
  grid in E1.3/E1.4 are the mitigation, not a resolution.
- **Whether Cube_Backlog rows and cube_Sale_APD MPS rows can overlap (double count)**: cannot be
  determined from data (no shared key) — resolved by a stated scope decision (Section 5 of the
  E1.3 report), not verified.
- **Whether FG01/FG21/WH21 stock is genuinely SELLABLE**: never confirmed by any field
  (Phase D: 0.00% confirmed, 99.90% undetermined) — used as the best-available proxy, flagged
  as an assumption, not asserted as fact, throughout E1.3/E1.4.
- **Initial 2024-01 stock, replenishment receipt timing, and fulfilment sequence for the
  historical simulation**: no historical stock-movement time series exists at all — all three
  are stated Modeler-default assumptions (Section 3), and the simulation's results are
  conditional on them, stated as such in Section 1 of the E1.4 report.
- **Scope reduction that was NOT needed**: the full 18-scenario × 66-item × 31-month historical
  simulation (36,828 item-months) was cheap enough to run in full — no reduction to "default +
  2-3 alternates" was required, unlike the task's own anticipated fallback.
- **MOQ/lot size**: confirmed absent by the business (STATUS.md §8.3) — the replenishment-qty
  and ordering-rule conventions in E1.3/E1.4 are explicit substitutes, not derived values.
- **Target service level and stockout-cost proxy**: still not set by the business (STATUS.md
  §8.5) — this phase presents a grid (90/95/98%) rather than picking one, per that section's own
  stated plan.

## 6. Figure-category index (verified / hypothesis / assumption / cannot be determined)

- **Verified**: the 128-item scope count; the 6/10/0 exclusion-list overlaps; the ADI/CV²
  demand classes; annual value and order-frequency figures; the notice-vs-lead-time percentages;
  the rolling-origin cumulative MAE/bias/MASE figures and their horizon-growth pattern; the
  empirical-distribution percentiles and thin-tail counts; the 18-scenario Min/Max arithmetic;
  the forecast-consumption per-month table (given the stated scope decision on Backlog/MPS);
  the historical-simulation fill-rate/stockout/stock-value figures (given the stated
  simulation assumptions); the current Min/Max coverage and cover-flag counts; the 128-item and
  445-item stock-value figures and their scope mismatch.
- **Hypothesis**: every E1.1 policy verdict (a reasoned recommendation from real segment
  numbers, not a certainty); the stock-value acceptance-criterion-4 explanation (safety stock
  for volatile demand as the driver of the gap); the E1.4 "what this means for acceptance
  criteria" framing.
- **Assumption (scenario input, not fact)**: every entry in Section 3's table — lead time
  (per-item uniform application), assembly time (both values), review interval, service-level
  default, replenishment-qty convention, safety-stock convention, sellable warehouse codes,
  unit-cost basis, obsolescence threshold, and all three simulation-mechanics assumptions.
- **Cannot be determined**: assembly time itself as a fact (only a stated default/alternative
  exists); whether Cube_Backlog and cube_Sale_APD MPS rows overlap; whether FG01/FG21/WH21 stock
  is genuinely sellable; the true 2024-01 starting stock, real replenishment receipt timing, and
  real fulfilment sequence (no data source exists for any of the three).
