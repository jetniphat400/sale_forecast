# Phase E1.5 — Compare against current settings

Script: `src/phaseE1_current_settings_comparison.py`. Outputs:
`phaseE1_5_current_vs_scenario.csv` (128 rows), `phaseE1_5_current_stock_value_128items.csv`
(128 rows). Current Min/Max are used **only as a comparison baseline**, per STATUS.md's locked
finding that they cannot be used as calculation inputs — this script does exactly that and
nothing more.

## 1. Current Min/Max coverage, re-derived fresh at this 128-item scope

**82 of 128 items have a current Min or Max setting** in `Cube_Inventory_Exact` (summed across
all warehouses per item, the same convention as the earlier Phase 4 groundwork investigation).
STATUS.md's earlier finding (46/128 with no setting) is consistent with this (128−82=46).
Category: **verified**.

## 2. 128-item pilot-scope CURRENT stock value — computed directly, flagged against the 445-item figure

**The task's acceptance criterion literally cites THB 37,399,005.48 — but that figure is for the
FULL 445-item universe, not this 128-item PEM101 pilot scope** (Phase D, `phaseD_check2_report.md`).
Recomputing directly from `Cube_Inventory_Exact` (all warehouses, no sellability filter) using
the IDENTICAL unit-cost methodology (cost/qty per row, median over trailing 12 months, most-recent
fallback) for exactly these 128 items:

- **128-item pilot-scope current stock value: THB 18,071,706.20** (114 of 128 items priced; 14
  items / 162.0 units have no cost record at all, value undetermined for those, never assumed
  zero).
- **445-item full-universe current stock value (cited, not recomputed here): THB 37,399,005.48.**

**These two figures are NOT the same thing and must not be conflated** — the 128-item pilot
scope holds roughly 48% of the full 445-item universe's stock value. Category: **verified**
(the 128-item figure; the 445-item figure is a citation from Phase D, not re-derived here).

## 3. Current vs default-scenario Min/Max (the 66 FG-stock items)

Of the 66 items with a default-scenario Min/Max (E1.3), all 66 also have a current-setting
comparison row in `phaseE1_5_current_vs_scenario.csv` (some with `current_total_min/max = 0`,
i.e. no current setting at all — reported as `0`, not conflated with a genuine zero-target
policy).

- **Min: 48 of 66 items would go UP under the default scenario, 18 would go DOWN.**
- **Max: 40 of 66 items would go UP, 26 would go DOWN.**
- **Value implication**: summing `(scenario_default_min − current_total_min) × unit_cost` over
  only the items where Min goes UP: **THB +46.35M** of additional capital implied by raising
  those 48 items' Min to the default-scenario level (partially offset by the 18 items where Min
  would fall — full per-item figures in `phaseE1_5_current_vs_scenario.csv`,
  `value_change_min_thb`/`value_change_max_thb` columns). Category: **verified computation**,
  built on the scenario assumptions from E1.3 (not a fact about what SHOULD happen).

## 4. Obsolescence-threshold and protection-period cover flags

- **(a) Current setting implies cover ABOVE the obsolescence threshold** (today's Max ÷ mean
  monthly demand > 6 months, `config['phase_e1_assumptions']['obsolescence_threshold_months']`):
  **50 of 128 items.** This matches the spirit of STATUS.md's existing finding that current
  min/max values "range from under 1 month to over 1,700 months of cover" — re-confirmed at this
  scope, from a fresh query, not assumed unchanged.
- **(b) Current setting implies cover BELOW one full default-scenario protection period**
  (today's Max ÷ mean monthly demand < 4 months): **15 of 128 items** — these items' current
  policy would not even cover lead time + assembly + review under the default scenario's own
  assumptions, regardless of any safety-stock consideration.

Both flags and the underlying `current_max_months_of_cover` are in
`phaseE1_5_current_vs_scenario.csv`. Items with zero mean monthly demand get `cover_note =
"undefined — zero mean monthly demand"` rather than a silently wrong division-by-zero result; items
absent from the forecast_date-keyed monthly series (the 15 no-history codes) get `cover_note =
"N/A — item not in the forecast_date-keyed monthly series"`. Category: **verified**.

## 5. Reminder of what current min/max ARE and ARE NOT good for

STATUS.md's Locked Decision stands unchanged and is reaffirmed here, not contradicted: current
Min/Max values are unusable as calculation INPUTS (81 of 119 multi-warehouse items disagree
across warehouses, per the original finding) — this report uses them ONLY as a comparison
baseline against a new scenario, exactly what that finding says they remain good for.
