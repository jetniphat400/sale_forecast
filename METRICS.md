# Metric Definitions — Single Source of Truth

Every figure that appears in an acceptance criterion, a report, or a
STATUS.md entry must be defined here BEFORE it is computed. An agent that
computes a metric not defined here must stop and report, not improvise.
When two agents compute the same metric independently, this file is what
they both read; a mismatch means this file is ambiguous and must be fixed
before either result is accepted.

Each definition states: formula, inputs and their source, edge cases,
and whether any part is a configurable assumption.

---

## 1. unit_cost

    unit_cost[item] = median( cost / qty ) over rows in the trailing 12
                      months, Omni Channel scope, Actual + MPS status

- Source: cube_Sale_APD columns `cost` and `qty`. `cost` is a LINE TOTAL,
  never use it raw.
- Rows with qty = 0 are excluded from the median.
- If fewer than 3 rows exist in the window, fall back to the most recent
  row with qty > 0 and flag the item as `unit_cost_fallback`.
- If no row exists, unit_cost is undefined; the item is excluded from any
  value calculation and listed in `no_unit_cost_items`.
- Assumption: 12-month window (config: `unit_cost_window_months`).

## 2. protection_period

    protection_period_days = procurement_lead_time_days
                           + assembly_time_days
                           + review_interval_days

- All three from config. Defaults 60 / 3 / 30. All are Tier A scenario
  parameters, none is a measured fact.

## 3. lead_time_demand (LTD)

    LTD[item] = expected demand over protection_period,
                taken as the Top-down combination forecast summed over
                the months the period spans, prorated for partial months

- Source: pipeline forecast output, forecast_date-keyed series.
- Placeholder items have no LTD (they are outside the hierarchy).

## 4. ltd_distribution and safety_stock

    ltd_distribution[item] = empirical distribution of cumulative demand
                             over rolling windows of EXACTLY
                             protection_period_days, built on the DAILY
                             series (forecast_date-keyed), advancing one
                             day at a time across the item's full usable
                             history
    safety_stock[item, sl]  = percentile(ltd_distribution, sl) − LTD

- The window is measured in DAYS and is never rounded to whole months.
  LTD (§3) is prorated to the same number of days, so the subtraction
  compares like with like. Rounding the window up to whole months would
  overstate safety stock; rounding down would understate it. Neither is
  permitted.
- If the daily series is not available and only monthly buckets exist,
  the implementation must prorate: weight each partial month by the
  fraction of its days inside the window. Report that proration was used.
- No normal assumption. If safety_stock < 0 it is set to 0.
- If the item has fewer than 6 non-zero windows, percentiles above 90 are
  reported as `unreliable` and the item is flagged.
- sl (service level) is Tier A, config default 0.95.
- Ambiguity resolved 2026-09-22: an earlier reading of "windows of
  protection_period length" was taken as whole months by one agent and
  prorated by another, producing different stock_value results.

## 5. Min and Max

    Min[item] = LTD + safety_stock
    Max[item] = Min + demand over review_interval_days

- Replenishment quantity = review-interval demand because no MOQ or lot
  size exists (business confirmed). Flagged as assumption.
- Only items whose policy is `finished_goods_stock` receive a Min/Max.
  Items with policy `component_stock_ato`, `make_to_order`, `placeholder`
  or `excluded` receive none.

## 6. stock_value  ← the metric that was ambiguous in E1

    stock_value = Σ over items with policy = finished_goods_stock of
                  ( Min[item] × unit_cost[item] )

- Counts Min, NOT current on-hand stock, NOT Max, NOT simulation average.
  It answers "what capital would this policy require the business to hold
  at the reorder point".
- Safety stock is included because it is part of Min.
- Items without unit_cost are excluded and counted in `no_unit_cost_items`.
- A separate metric `current_stock_value` = Σ(on_hand_sellable × unit_cost)
  exists for comparison; never mix the two.

## 7. sellable_stock (on-hand)

    on_hand_sellable[item] = Σ qty in Cube_Inventory_Exact where
                             warehouse ∈ sellable_warehouses

- sellable_warehouses from config; PEM101 default FG01, FG21, WH21
  (verified 100% division dominance; sellability itself unverified —
  Tier A assumption).

## 8. current_min_max

- Source: Cube_Inventory_Exact `minimum` / `maximum`, summed across
  warehouses per item. Comparison baseline only; established as
  unreliable, never an input.

## 9. months_of_cover

    months_of_cover[item] = on_hand_sellable / mean monthly forecast

- Undefined when forecast = 0; reported as `∞` and listed separately.

## 10. fill_rate (simulation)

    fill_rate = units shipped immediately from stock
              / total units demanded, over the simulation horizon

- Unit-based, not order-based.

## 11. cycle_service_level (simulation)

    cycle_service_level = replenishment cycles with no stockout
                        / total cycles

- Distinct from fill_rate. Both are reported; the config parameter `sl`
  targets cycle service level.

## 12. bias

    bias = mean( forecast − actual ) over the evaluation window

- Negative = under-forecast. Signed, in units. Reported per horizon.

## 13. MASE

    MASE = MAE(model) / MAE(in-sample seasonal-naive with m = 1)

- Undefined when the in-sample naive MAE is 0 (constant or all-zero
  history). Such items are reported as `MASE_undefined` and excluded from
  MASE averages, never assigned 0 or ∞.

## 14. forecast_consumption

Two distinct metrics; never report one under the other's name.

    confirmed[item, month]   = Σ qty of confirmed undelivered orders whose
                               forecast_date falls in that month
    confirmed_total          = Σ confirmed over the horizon
    open_demand[item, month] = max( forecast[item, month]
                                    − confirmed[item, month], 0 )
    open_demand_total        = Σ open_demand over the horizon

- Source of confirmed orders: MPS rows in cube_Sale_APD PLUS rows in
  Cube_CES with Status = 'Backlog', deduplicated on contract + item.
  Do NOT use the separate table Cube_Backlog: verified 2026-09-22 that
  it lags Cube_CES by roughly 14 hours and held 8 pairs already delivered
  (Status = 'Actual' in Cube_CES), which would over-count open demand by
  0.9 percent.
- Overdue backlog (forecast_date before today) is placed in the current
  month.
- open_demand never goes negative.
- Ambiguity resolved 2026-09-22: the section title "consumption" was read
  as confirmed_total by one agent and open_demand_total by another.

## 15. segment_policy criteria

**Superseded for G2 item eligibility by §23 `fulfilment_segmentation` (added 2026-09-25); this
section's formula/text is kept unchanged below, per §23's own instruction ("Mark section 15
accordingly; keep its text").**

    annual_value[item]     = sum of sale over the trailing 12 months
                             ending at the data cutoff, Omni Channel,
                             Actual + MPS
    order_frequency[item]  = count of distinct (contractid, createDate)
                             in the SAME trailing 12 months

    finished_goods_stock : annual_value >= P50(annual_value across the
                           division's forecast items)
                           OR order_frequency >= 6
    component_stock_ato  : otherwise, AND assembly_time_days <= 6
                           (median customer notice)
    make_to_order        : never (notice never exceeds procurement)
    placeholder / excluded : per config item status

- Both value and frequency use the same fixed 12-month window ending at
  the data cutoff, never an item's own first-sale-to-last-sale span, and
  never a calendar year. An item with 3 months of history is measured
  over 12 months and will have a low frequency; that is intended.
- Boundaries are INCLUSIVE. An item exactly at P50 is
  finished_goods_stock.
- P50 is computed over forecast-status items only; placeholder and
  excluded items are not in the pool.
- Thresholds are assumptions; record in config segment_policy.
- Every item within plus or minus 5 percent of either threshold must be
  listed in the run report so the sensitivity of the split is visible.
- Ambiguity resolved 2026-09-22: one agent measured frequency over the
  item's own active span, another over a fixed window, producing a
  one-item difference at 2.01 percent below the cutoff.
- If P50 across the division's forecast items is zero, the value criterion
  is undefined and must not be applied. In that case classify by
  order_frequency alone: finished_goods_stock if order_frequency ≥ 6,
  otherwise component_stock_ato. Report that the zero-P50 rule was used.
- Separately, compute P50 over items with annual_value > 0 and report it,
  so the reader can see what the value threshold would have been had the
  inactive items been excluded. This second figure is informational and
  does not drive classification.
- Added 2026-09-23 (Phase J2, Part 0): if assembly_time_days exceeds the
  notice threshold (6 days, median customer notice), component_stock_ato
  is INFEASIBLE under this criterion — report it explicitly as
  `component_stock_ato_infeasible`, not as an undefined/unclassified
  policy. This replaces the prior silent `UNDEFINED_BY_METRICS_MD_SEC15`
  label with a named, explicit state; it does not change which items are
  affected, only how the affected state is reported.

## 16. simulation_mechanics

The historical replay in Phase E uses these rules; any deviation must be
recorded in config and reported.

    review          : every review_interval_days (config), starting at
                      day 0 of the replay
    reorder trigger : on a review day, if on_hand + on_order ≤ Min,
                      place an order of (Max − on_hand − on_order)
    receipt         : an order placed on day d arrives at the start of
                      day d + procurement_lead_time_days
                      + assembly_time_days
    demand          : daily, from the forecast_date-keyed actual series
    fulfilment      : if on_hand ≥ demand, ship in full; otherwise ship
                      on_hand and record the shortfall as a backorder
                      that is filled first from the next receipt
                      (backorders are never lost)
    initial stock   : Max at day 0, with no order in flight — recorded
                      as an assumption because no historical stock
                      level exists
    fill_rate       : per section 10, units shipped on the demand day
                      ÷ units demanded; backordered units count as NOT
                      shipped on the demand day
    cycle_service   : per section 11; a cycle is the interval between
                      two consecutive receipts

- Ambiguity resolved 2026-09-22: two agents replayed the same demand
  with different reorder and receipt timing, producing fill rates of
  99.94 and 97.90 percent from identical inputs.

## 17. decision_sensitivity

For an assumption swept across its range, holding all others at default:

    min_shift[item]      = |Min(swept) − Min(default)| / Min(default)
    policy_flip[item]    = segment policy differs from default
    value_shift          = |stock_value(swept) − stock_value(default)|
                           / stock_value(default)
    fill_rate_shift      = fill_rate(swept) − fill_rate(default)

An assumption is DECISION-RELEVANT if, anywhere in its range, any of:
    - policy_flip occurs for any item, or
    - min_shift > 10% for items holding ≥ 20% of the division's
      stock_value, or
    - value_shift > 10%, or
    - |fill_rate_shift| > 2 percentage points.

Otherwise it is DECISION-INSENSITIVE and may remain an assumption.

- Thresholds (10%, 20%, 2pp) are themselves assumptions; report results at
  5% and 20% as well so the classification's own sensitivity is visible.
- Items with Min(default) = 0 are excluded from min_shift and counted.

## 18. baseline_replay and calibration_gap

    baseline_replay : the section 16 simulation run with the CURRENT
                      policy instead of the scenario policy:
        - Min and Max = current minimum and maximum from
          Cube_Inventory_Exact summed across the division's sellable
          warehouses
        - items with no current setting: reactive — no reorder until a
          backorder exists, then order exactly the backorder quantity
        - initial stock = current on-hand in sellable warehouses
        - all other section 16 rules unchanged
    actual_on_time  : share of units, for the same items and the same
                      replay horizon, delivered on or before their
                      forecast_date, from Cube_CES ActualDelDate against
                      ForecastDelDate
    calibration_gap = fill_rate(baseline_replay) − actual_on_time

- Section 16 fill_rate measures availability on the forecast_date, which
  is the delivery due date, so it is comparable to actual_on_time.
- Replaying today's min and max over 2024 to 2026 assumes those settings
  applied throughout. They may not have. Report this as an assumption.
- Rows lacking ActualDelDate are excluded from actual_on_time and counted.

## 19. delivery_timeliness

    on_time_exact  = share delivered ON the due date
    not_late       = share delivered on or before the due date
    late           = share delivered after the due date

Each reported both row-weighted and unit-weighted, and the weighting
always stated.

- Only not_late is comparable to section 10 fill_rate, since an early
  delivery is a satisfied order.
- Correction 2026-09-22: the project's long-cited 73.2 percent figure was
  on_time_exact, row-weighted, 2026 only. It excluded early deliveries
  and must never be used as a fill-rate benchmark. Acceptance criteria
  that used it were comparing unlike measures.

## 20. inverse_calibration

    Fit the parameters of the section 16 simulation so that it
    reproduces observed outcomes, instead of assuming them.

    targets   : not_late (unit-weighted, section 19) per division
                AND average on-hand stock value per division
    parameters: effective review interval, effective replenishment
                lead time, reorder level and order-up-to level
                expressed as months of mean demand, usable-stock
                definition
    fit       : calibrate on 2024-01 to 2025-12; the first 6 months
                are warm-up and excluded from scoring; validate
                out-of-sample on 2026-01 onward
    tolerance : not_late within ±3 points AND stock value within ±15%
    identified: a parameter is identified if every combination within
                tolerance on the calibration period, which also stays
                within tolerance on the validation period, agrees on
                that parameter within one grid step

- Two targets are required. Fitting service alone leaves stock level
  free and many combinations will match; the observed stock value is
  what pins the policy down.

## 21. channel_scope and cross-scope comparison

    channel_scope ∈ { omni, omni_tendering }
      omni           : revenue_type = 'Omni Channel'
                       — project default and official requirement
      omni_tendering : revenue_type IN ('Omni Channel', 'Tendering')
                       — contingency scope
    relative_bias    = bias / mean(actual) over the same window, in %

    same-target rule: two scopes are compared for accuracy ONLY on the
    same target series. To test whether the combined scope forecasts
    Omni demand better, the omni_tendering forecast is allocated to Omni
    by Omni's historical share of the combined series per item and Type,
    computed from data before each origin only; both scopes' Omni
    forecasts are then scored against actual Omni demand.

- MASE and relative_bias may be reported per scope to describe how
  predictable each series is, but never to claim one scope forecasts
  more accurately than the other, since the series differ.
- Other revenue types are excluded from both scopes; report their share
  of each division's value, and flag any above 2 percent.
- The allocation share obeys the point-in-time rule: no data after the
  origin.
- The historical initial stock is unknown; the warm-up absorbs it.

## 22. robust_minmax

    robust_ensemble : the parameter combinations recorded in the
                      division's section 20 calibration report as within
                      tolerance on BOTH the calibration and validation
                      periods. If that set is empty, the calibration-only
                      set may be used, labelled calibration-only in every
                      output.

    SUPERSEDED, 2026-09-24: the deduplication rule below treated two
    members as distinct whenever their usable-stock definitions differed,
    even when every other parameter matched. For PEM101 this produced a
    139-member ensemble (59 `current` + 21 `fg_prefixed_only` + 59
    `all_stockholding_except_qa_fmto_fmts`) in which the 59 `current` and
    59 `all_stockholding_except_qa_fmto_fmts` members shared the exact
    same (reorder level, order-up-to level, review interval, replenishment
    lead) tuple and therefore simulated to numerically identical Min_e/
    Max_e — only 80 tuples were actually distinct for that purpose
    (independent Validator, `output/summary/phase22_validator_report.md`
    Part 1, lines 81-95). Min_e/Max_e do not read on-hand stock at all, so
    the usable-stock definition cannot affect them or range_ratio — the
    same run's `phase22_modeler_stockdef_effect.csv` found a difference of
    0.0 for every item (DATA_MAP.md §4 Trap 19). Counting such members
    twice biased the reported medians toward whichever definition happened
    to contribute more passing combinations. Replaced by the two rules
    below.

    per item, for each ensemble member e:
                      Min_e, Max_e per sections 5 and 16, using e's review
                      interval, replenishment lead, reorder level,
                      order-up-to level and usable-stock definition
    range_ratio     = max_e(Min_e) / min_e(Min_e), over members with
                      Min_e > 0; items where every Min_e is 0 are reported
                      separately
    robust item     : range_ratio ≤ 1.25 — report median Min and median
                      Max across the ensemble as the recommended values
    sensitive item  : range_ratio > 1.25 — report the full range; no single
                      value is recommended, and the parameter whose variation
                      drives the range is named
    trade-off curve : for each ensemble member, hold its review interval,
                      replenishment lead and usable-stock definition fixed,
                      and vary its reorder level across a grid while keeping
                      the member's gap between reorder and order-up-to level
                      constant; simulate per section 16 and record
                      stock_value and not_late (section 19, unit-weighted)
                      at each grid point. The curve reported is the
                      envelope across members: minimum, median and maximum
                      stock_value at each not_late level.

- The 1.25 threshold is an assumption; also report robust and sensitive
  counts at 1.10 and 1.50 so the split's own sensitivity is visible.
- The trade-off curve is the input for the service-level decision D2. It
  is valid only for divisions with a non-empty robust_ensemble.
- Placeholder and excluded items receive no Min or Max, as before.
- Deduplicate ensemble members on the parameters that affect the quantity
  being computed. For Min, Max, range_ratio and the trade-off curve, these
  are reorder level, order-up-to level, review interval and replenishment
  lead time; usable-stock definition does not enter them. For quantities
  that read on-hand stock — the order quantity needed today (Min minus
  on-hand) and current_stock_value — usable-stock definition matters and
  members stay distinct.
- Every output states which deduplication applied and the resulting
  member count.

## 23. fulfilment_segmentation

    label[item]   = dominant manufacturing_type by quantity over the
                    analysis window if its share is at least 60 percent;
                    otherwise mixed
    stock signals:
      S1 on-hand stock above zero in Cube_Inventory_Exact, any warehouse,
         at the current snapshot
      S2 at least 50 percent of the item's delivered contracts trace to a
         cube_final batch that existed before the PO
      S3 median days from createDate to ActualDelDate at most 14

    stock_policy        : label = MTS and at least 2 of S1 to S3 hold
    confirmed_to_order  : label in {MTO, ETO} and at most 1 of S1 to S3
                          hold — no Min or Max; planned under G3
    conflict            : every other combination, and every mixed item —
                          no Min or Max until confirmed; listed separately
    PEM104              : every item confirmed_to_order, level A

- If S2 cannot be computed for an item because no batch links, evaluate
  on S1 and S3 and require both to hold for stock_policy.
- S1 uses any warehouse because sellability cannot be verified from data.
- Thresholds of 60 percent, 50 percent and 14 days are assumptions. Report
  counts also at 50 and 70 percent, 40 and 60 percent, and 7 and 21 days.
- For G2 item eligibility this supersedes the value and frequency criteria
  of section 15. Mark section 15 accordingly; keep its text.

## 24. relative_service_cost

    For each distinct ensemble member e, deduplicated per section 22:
      ratio_e(target) = stock_value_e(at target not_late)
                        ÷ stock_value_e(at today's not_late)
    Report the median, minimum and maximum of ratio_e across members for
    each target.

- Valid only for divisions with a non-empty robust_ensemble.
- This is the primary figure for the service-level choice, because the
  reorder level the data cannot identify largely cancels within each
  member. Absolute stock values remain reported with their band.
- If the ratio's band is not narrower than the absolute band, say so
  rather than presenting the ratio as more certain.

## 25. error_metrics

    MAE   = mean(|forecast − actual|)
    RMSE  = sqrt(mean((forecast − actual)²))

- Both in quantity units, over the same window and series as bias.
- MASE follows section 13. Where it is undefined, any output shown to a
  user displays MASE_undefined, never NaN, 0 or infinity.

## 26. page_timestamps

Every dashboard page and panel displays, near its title:

    data_pulled_at     : the time the underlying data was queried from the
                         database, taken from the data itself — its
                         snapshot_pull_date or the source table's load
                         timestamp — never typed
    page_built_at      : the time the page was generated, from the build
                         run's clock
    model_calibrated_at: on pages showing calibrated results, the date of
                         the calibration run and the last month of data it
                         used — distinct from data_pulled_at, because data
                         is refreshed more often than calibration is re-run

- All three are shown in Thai local time, UTC+7, with the date and time.
- A page whose content comes from an external file the project cannot
  refresh — such as the S&OP Plan tab — shows that file's source date and
  says it is not refreshed by this pipeline.
- If data_pulled_at is more than 7 days older than page_built_at, the
  page shows a visible staleness notice.
- The forward-test log is never refreshed or rewritten; it keeps the
  cutoff it was generated at.

## 27. forward_test_vintage

    vintage          : the set of forecasts produced by one generation run
    each row         : item code, forecast_run_date, data_cutoff_date,
                       config hash, model, horizon 1 to 6, target_month,
                       forecast_qty, actual_qty
    rows are appended, never modified or deleted, except that actual_qty is
    filled once the target month becomes eligible
    eligible         : the target month has ended and the leakage-guard
                       margin has passed since its last day
    scoring          : per vintage and per horizon, using section 25 metrics,
                       only over eligible months

- The log in existence today is vintage 1 and keeps its original cutoff.
- A monthly run appends one new vintage. Comparing vintages over time is
  the forward test; no single scored month is treated as proof.

## 28. monthly_refresh

    steps, in order:
      1 pull data — one connection attempt, abort on failure, no retry
      2 validate — zero-row guard and data invariants
      3 rebuild the forecast_date-keyed series as a frozen snapshot
      4 re-run the sales-model backtest; record each division's change
        against the previous run
      5 append a new forward-test vintage per section 27
      6 fill actual_qty and score any months that became eligible
      7 rebuild every page with section 26 timestamps
      8 run the full test suite
      9 scan staged files for sensitive content
      10 check change magnitude against the previous run
      11 commit and push only if steps 8 to 10 all pass

    frozen, never touched by the monthly run:
      existing forward-test vintages; the Phase J3 calibration outputs and
      the robust ensemble; locked decisions in STATUS.md

    change-magnitude gate — hold the push for human review if any of:
      the six-month total forecast for a division changes by more than 25%
      a division's backtest MAE changes by more than 20%
      total on-hand stock across the pricelist scope changes by more than 30%

- The three thresholds are assumptions and live in config.yaml, each
  commented.
- Calibration is not re-run automatically; pages keep showing
  model_calibrated_at from the last calibration.
- Every run writes a run log stating each step's outcome, the figures
  checked at step 10, and whether it pushed. A held or failed run is
  reported in the log, never silently skipped.
- Tests must not modify tracked output files; a test that regenerates a
  page writes to a temporary location.
