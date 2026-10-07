# Phase E1.2 — Lead-time demand, not next-month accuracy

**Scope: PEM101 128-item pilot, 112 `eligible_for_policy` items** (the 16 excluded/placeholder
items are excluded from this evaluation because they have no real forecast to evaluate — listed
in `output/summary/phaseE1_1_no_policy_items.csv`, not silently dropped). **Bounded scenario
pilot — no actionable purchase recommendation.**

Script: `src/phaseE1_leadtime_demand.py`. Outputs: `phaseE1_2_scenario_horizons.csv`,
`phaseE1_2_rolling_origin_cumulative.csv`, `phaseE1_2_horizon_position_bias.csv`,
`phaseE1_2_mase_summary.csv`, `phaseE1_2_empirical_distribution.csv`. Chart:
`output/charts/phaseE1_leadtime_demand_distribution_focus_items.png`.

## 1. Protection period definition and rounding rule

Protection period (days) = procurement lead time + assembly time + review interval, all read
from `config['phase_e1_assumptions']`. **Rounding rule (stated explicitly): total days ÷ 30.44
(average month length, 365.25/12), rounded UP (ceiling)** — under-covering the protection period
is the riskier direction for a stockout-avoidance policy, so fractions round toward MORE
coverage, not less.

Across the full lead-time (45/60/75d) × assembly-time (3/7d) grid, with review interval fixed at
30 days (`phaseE1_2_scenario_horizons.csv`), only **two distinct horizon lengths occur: 3 months**
(45+3, 45+7) **and 4 months** (60+3, 60+7, 75+3, 75+7). The **default scenario** (60d lead, 3d
assembly, 30d review) has a **4-month protection period**.

## 2. Rolling-origin backtest of the Top-down forecast over the full protection-period horizon

Method: at every leakage-guard-cleared rolling origin (`src/leakage_guard.py::check_window_closed`,
`min_margin_days=30`; **0 of 17 origins across both horizons were refused** — the existing
30-day margin, already validated in Phase E0.1/B4, clears every window used here), the Top-down
combination forecast (`src/phaseE1_common.py::topdown_item_forecast` — Type-level Combination
forecast fit on TRAIN data only, allocated to items by each item's OWN train-only qty share,
recomputed fresh at every origin — the exact leakage-free pattern E0.1 verified in
`src/item_level_reconciliation.py`/`src/transferability_all_divisions.py`) is summed over the
FULL protection-period horizon and compared against the item's own actual cumulative demand over
the same horizon. Category: **verified**.

| horizon (months) | origins scored | item×origin cells | mean cumulative MAE | mean cumulative bias |
|---:|---:|---:|---:|---:|
| 3 | 9/9 | 1,008 | 391.9 | -98.2 |
| 4 | 8/8 | 896 | 397.7 | -95.6 |

(Cumulative MAE/bias are in raw quantity units, summed over the whole horizon, not per-month —
larger than a single-month MAE by construction.)

### Does bias grow with horizon? — YES, and the numbers say by how much

Per-relative-month bias (mean of forecast − actual at relative month 1, 2, ... of the horizon,
pooled across all items and origins, `phaseE1_2_horizon_position_bias.csv`):

| horizon | bias at month 1 | bias at last month | growth |
|---:|---:|---:|---:|
| 3 months | -37.5 | -134.0 | -96.4 (grows ~3.6x from month 1 to month 3) |
| 4 months | -39.4 | -161.0 | -121.6 (grows ~4.1x from month 1 to month 4) |

**Bias is negative throughout (under-forecasting, consistent with STATUS.md Phase 2's existing
finding that point forecasts target the mean while real demand contains spikes) and grows in
magnitude the further into the horizon you look — the forecast error compounds with horizon
length, it does not stay flat.** Category: **verified**. This directly motivates E1.3's use of
the EMPIRICAL demand distribution (Section 3 below) for safety stock, rather than trusting the
point forecast's own accuracy at the far end of the horizon.

## 3. MASE — undefined cases handled explicitly, never silently

MASE's denominator (mean absolute first difference of the training series) is zero for an
item/origin whose training window has constant or all-zero demand. Handled via
`src/phaseE1_common.py::mase_with_flag`, which returns `(NaN, True)` rather than letting a
silent NaN/Inf poison an aggregate:

| horizon | n item×origin cells | n MASE undefined | % undefined | mean MASE (excl. undefined) |
|---:|---:|---:|---:|---:|
| 3 | 1,008 | 43 | 4.27% | 1.396 |
| 4 | 896 | 42 | 4.69% | 1.373 |

**43 (h=3) / 42 (h=4) item×origin cells were excluded from the mean MASE, counted and reported
separately, never dropped silently or averaged in as 0/Inf.** A MASE > 1 (mean, excluding
undefined cells) means the Top-down protection-period forecast is, on average, WORSE than a
naive one-step first-difference benchmark at this horizon — consistent with this project's
existing finding that Naive wins outright on many pilot items (STATUS.md §9, Forecast Value
Added). Category: **verified**.

## 4. Empirical protection-period demand distribution (NOT a normal-distribution assumption)

For each eligible item, ALL overlapping H-month rolling sums are built from the item's own
ACTUAL 31-month history (31−H+1 windows; H=3 → 29 windows, H=4 → 28 windows) —
`phaseE1_common`/`phaseE1_leadtime_demand.py::empirical_distribution`. The 50th/90th/95th/98th
percentiles of this distribution, and its mean, are what E1.3's Min/Max scenario grid draws
safety stock from. Category: **verified** (direct computation from history, no distributional
assumption).

### How many items have too few non-zero periods for the upper percentiles to be meaningful

**Threshold: fewer than 10 non-zero windows** — reused explicitly from this project's own
existing precedent (STATUS.md Phase 4 prep investigation, Part 5: "≥10 orders... the minimum
treated as meaningful" for order-quantity-pattern evidence), not invented fresh for this task.

| horizon | items flagged too few (out of 112 eligible) |
|---:|---:|
| 3 months | 18 (16.1%) |
| 4 months | 16 (14.3%) |

**These 18/16 items' 90th/95th/98th percentiles in `phaseE1_2_empirical_distribution.csv` carry
`too_few_for_upper_percentiles = True`** and are flagged (not excluded) in every downstream use in
E1.3 — their Min/Max is still computed (an item cannot be left with no policy just because its
tail is thin), but the resulting Min/Max should be read with lower confidence for these items.
Category: **verified** count, **assumption** for the threshold value itself (10 is a stated,
precedent-based choice, not derived from this data specifically).

## 5. Focus-item distribution chart

`output/charts/phaseE1_leadtime_demand_distribution_focus_items.png` shows the 4-month
(default-scenario) rolling-sum demand histogram for the three focus items
(`EEE-F-FC-1040010002`, `HS-F-99-02110`, `HS-F-99-0213`), with the 50th/90th/95th/98th
percentiles marked — the direct input to E1.3's Min/Max for these three items.
