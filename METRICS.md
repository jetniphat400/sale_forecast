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
