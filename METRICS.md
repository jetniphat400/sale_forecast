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

### Item lead time, version 1 (added 2026-10-05, week 1 item 1.3; `src/lead_time_v1.py`)

    item lead time = slowest material's lead time + the item's production time

- **Materials:** the item's components in Cube_BOM_Exact, one level, excluding the header row (Sequenceno 0 or a blank component) and the
  `Machine Hour` pseudo-codes. A component with no purchase record and no price-list quote whose code kind is W (an in-house sub-assembly) is not
  walked (its own BOM is not in the saved pull); it is listed and left out of the maximum. An item with no BOM, or left with no purchased material,
  takes the assumed values and is labelled.
- **Per material, one statistic, the median** (per-material samples are small and the 0 to 730 day range holds outliers), from this order:
  (1) observed: the median over the material's purchase orders of the days from PO date to the first receipt (Cube_PO_Exact and Cube_ReceiveRM, key
  PO number plus item, one lead time per PO and item, usable 0 to 730 days); (2) supplier quoted: the median of the non-zero Cube_PriceList.DeliveryTime
  days over the material's suppliers ("0 Days" is not a quote); (3) assumed: config `lead_time_v1.fallback_material_days`, set at the observed 90th
  percentile across materials (63 days on 2026-10-05; an assumption, to be tuned).
- **Production time**, in this order, a source used only where tested: (1) standard time: Cube_Standard_Time is the incoming-inspection plan of raw
  materials, not production time, and is not used; (2) measured: the median over the item's jobs of the days from Cube_Production_Order.start_date
  (the order's release date, within about one day before the first material issue) to the latest cube_final.final_date of the same job and item
  (booked about when the last material is issued), used when the item has at least 3 matched jobs (config `production_min_jobs`; leave-one-job-out
  error 21.4 days against 29.1 for the global median); (3) assumed: config `production_days_assumed`, the median of all 291 matched job-items (26
  days; an assumption). Each job and item counts once. No column marks the actual start of work.
- **Recorded output:** `output/summary/item_lead_time_v1.csv` with its SHA-256 (of the text read back) in `item_lead_time_v1_integrity.json`; per item
  the lead time, bottleneck material, and the source of each part (observed, supplier quoted, assumed; measured or assumed).
- **Limits:** one BOM level; 39 of PEM101's 92 stock_policy items (5 with no BOM, 34 with only in-house sub-assemblies) carry the assumed values;
  the clock starts at the PO date and stops at the first receipt; production time is the throughput of a job lot, not a per-unit assembly time.

### Max-Min v1 lead time (decision of the user, 2026-10-06; `src/maxmin_v1.py`)

PEM101's Min and Max on `forecast/inventory.html` use the lead time the calibration supports: the section 22 ensemble fitted with lead time free (section 20) on the 92 stock_policy items (36 distinct members, replenishment lead 1 to 30 days on 2026-10-06). The item lead time version 1 above is shown beside each item and kept for the material plan; it is not an input to Min or Max. Every figure the page shows from the ensemble is read from the control run's recorded files after a SHA-256 check.

### Max-Min v1 demand input (decision D3 of the user, 2026-10-08)

PEM101's Min and Max keep the history-based demand input in v1: Min = r x 30.44 x the item's mean daily demand, Max = the median over the members of (r + gap) x 30.44 x the same demand, the mean taken over the daily series of `output/data/raw_all_divisions_sales.csv` from 2024-01-01 to the end of the last complete month (`src/maxmin_v1.py` `build_page_inputs`; 92 stock_policy items). The forecast is not used for the PEM101 Min/Max in v1. Evidence (week 4, prompt 5, Part 3, STATUS.md): replacing that level by the latest vintage's monthly forecast, with every other input unchanged, gives Min 93,904 against 81,385 units (+15.4 percent; THB 13.2M against 10.0M, +31.8 percent) and, in the calibration's own simulation over 2026-01 to 2026-09 at the page's default setting, 98.54 percent not late at THB 19.27M against 97.87 percent at THB 13.85M (observed 98.34 percent, THB 15.49M). That run is a level substitution, not a backtest: the vintage is a forward level applied to a past window and the history level is in-sample for it, so it does not show which input predicts better. A backtest of a forecast-based input will be run when enough forecast vintages exist; until then the history-based input stays. (The Min and Max of the other divisions' stock items, section 4 and the page's standard-assumption table, use the vintage's forecast for the lead-time demand and the vintage's series for the percentile, section 28.)

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
- Max of 0 (2026-10-05): a system Max of 0 means nobody filled it in (stated by
  the user, DATA_MAP level A). On forecast/inventory.html it shows as
  `ไม่ได้กรอก`, the total of the system's Max leaves those rows out and says
  how many (`ไม่รวม {n_max_not_filled} รายการที่ไม่ได้กรอก Max`), and an item
  with no inventory record at all shows a dash. The pilot divisions' `fillna(0)`
  had conflated "no record" with 0; the page now carries `current_has_record`
  to tell them apart. No calculation that uses Min changed.

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
- Aggregation, one definition for the backtest and the forward test
  (`src/backtest_rekeyed.py` `compute_metrics`; `src/transferability_all_divisions.py`;
  `src/forward_test_scoring.py`, definition id `backtest_item_mean_v1`):
  the scale is the mean absolute first difference of the series the forecast
  was fitted on; MASE is computed per item and per window (a backtest window
  is an origin's six forecast months, a forward-test window is one target
  month at one horizon); a division's MASE is the plain mean of its items'
  MASE, undefined items left out of that mean. An item whose fitted series is
  all zero is not scored. Pooling items before dividing, or pooling horizons,
  is a different quantity and is never reported under this name.

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
- Added 2026-09-29 (task 2b follow-up, resolving a genuine ambiguity this
  section left open -- METRICS.md previously stated the S2-missing
  fallback only for stock_policy and was silent for
  confirmed_to_order/conflict): if S2 cannot be computed for an MTO/ETO/
  mixed-labelled item, evaluate on S1 and S3 only and require at most 1
  of the two to hold for confirmed_to_order (i.e. NOT both) -- the direct
  structural mirror of the stock_policy fallback above, which requires
  BOTH remaining signals; label = mixed still routes straight to
  conflict regardless. A stricter alternate reading was also considered
  -- require at most 0 of {S1,S3} to hold (treating the dropped S2 slot
  as still counting against the "at most 1 of 3" bar) -- and is recorded
  as the alternate, not adopted, per AGENTS.md rule 9 (a genuine
  ambiguity is reported with both readings, not silently resolved by one
  agent). See DATA_MAP.md's Task 2b (2026-09-28) entry for the item
  counts each reading produces for PEM101 (the only affected division at
  material scale) and the evidence behind preferring the first reading.
- Per-item class decisions (E1 and E3, decided by the user 2026-10-05; the rule above is NOT changed). Config
  `fulfilment_class_decisions` holds (a) PEM107's 41 G3 made-to-order codes (the recommended subset of
  `phaseA_pem107_g3_verification.md`), each already `confirmed_to_order` under this section, the build stops if one is not;
  the other PEM107 items get no Min/Max for now; and (b) per-item overrides of PEM101's conflict items from
  `phaseA_pem101_conflict_lean.md` (day_th 14, batch_th 0.50): the 10 leaning stock become `stock_policy`, the 11 leaning
  made-to-order become `confirmed_to_order`, the 20 undetermined stay `conflict`. PEM101 counts: stock_policy 82 to 92,
  confirmed_to_order 21 to 32, conflict 41 to 20. The page labels each of the 21 beside its class (from
  `class_basis` in the page data). The PEM101 calibration was fitted on the earlier 76-item set and is not recalibrated;
  the calibrated-target note keeps saying so.
- S1 uses any warehouse because sellability cannot be verified from data.
- Thresholds of 60 percent, 50 percent and 14 days are assumptions. Report
  counts also at 50 and 70 percent, 40 and 60 percent, and 7 and 21 days.
- For G2 item eligibility this supersedes the value and frequency criteria
  of section 15. Mark section 15 accordingly; keep its text.

- **S2 defined (2026-10-06, week 4; this is how `compute_s2_s3` computes it, written down so that it can be reproduced; the rule and its results are unchanged).**
  - *Rows.* The delivered rows of an item are every Cube_CES row with Status 'Actual' and the item's ItemCode (trimmed of leading and trailing spaces before matching, decision D3 of 2026-10-06: 19 rows of two items carry a
    trailing space in the code; the job code below is NOT trimmed): all channels, all dates, and one row per plan line
    (a contract delivered in two plan lines gives two rows). The number of delivered rows is `n_delivered_contracts` in the item-level file (the column keeps its
    old name).
  - *Link to a batch.* A row is linked to a batch when its OLMJobCode is not blank (not null, not empty after trimming, not the text 'none' in any case) and is
    EXACTLY equal, character for character with no trimming and no splitting, to the `jobno` of at least one cube_final row (any item, any date). An OLMJobCode that
    is a comma list of several job codes therefore never links. The batch date is the earliest `final_date` among the cube_final rows of that `jobno`.
  - *Before the order.* A linked row is served from an existing batch (`traceable_pre_existing`) when its batch date is strictly earlier than the row's CtrDate (a
    timestamp compared with a date at 00:00, so a batch finished on the day of the order, at any time after midnight, is not earlier). A row with no CtrDate is
    never served and never counts as linked.
  - *Per item.* n_linked = linked rows with a CtrDate; n_pre = served rows; share = n_pre / n_delivered (the denominator is ALL delivered rows, linked or not);
    S2 holds when share >= 0.50. S2 is not computable when the item has no delivered row or no linked row (n_linked = 0); the fallback of this section for a
    missing S2 then applies.
  - *Where no link exists:* the row stays in the denominator and is never served. Alternative link rules were measured on 2026-10-06: trimming both sides changes S2
    on 2 items, splitting comma lists on 11, both on 13 of 439; no class changes under any of them (DATA_MAP.md, week 4). Two separately written computations agree on
    every item (`tests/test_class_decisions.py`).
- **Added 2026-10-06 (week 3; `src/investigations/task2b_part2_fulfilment_segmentation.py`, config `week3_classification`). The rule above is not
  changed;** it is applied to every forecast-status and placeholder item of CI101, PEM102 and PEM103, and PEM101's and PEM107's forecast-status items keep
  their classes (the rule's result of 2026-09-29 and the user's per-item decisions of 2026-10-05, column `class_used`; a fresh recomputation is recorded beside
  it as `class_recomputed`). PEM104's items are business-confirmed made-to-order (level A, as stated above); the rule's own result for them is recorded in
  `class_recomputed`. Six PEM101 codes the price list lists but that were never sold are not in the universe. Three definitions are added per item, in every
  division:
  - `data_inconsistent`: the recorded label contradicts the observed behaviour: the label is MTS while none of S1 to S3 holds, or the label is MTO or ETO while
    all of S1 to S3 hold (when S2 cannot be computed, S1 and S3 only, as above). It is a flag, not a class. Tested on the items whose class is known (PEM101's and
    PEM107's stock_policy and confirmed_to_order items) before it is shown; for the items the rule itself classed it flags none by construction (a stock_policy item
    has at least two signals, a confirmed_to_order item at most one), so only the user's per-item decisions can be flagged.
  - `no_production_in_system`: no Cube_BOM_Exact entry (any row with the item as ItemFG) and no cube_final record (itemcode). The item is listed with its
    demand in the operation plan and is not counted as production load; its material requirement is not exploded.
  - `too_little_data`: fewer than 3 delivered contracts in the analysis window (Cube_CES Status 'Actual', distinct ContractID, CtrDate on or after 2024-01-01;
    config `min_delivered_contracts`); counts are also reported at 2 and 5.
  - **Mixed items** (a per-item test of the fact that manufacturing_type is held per order): the delivered lines of an item (cube_Sale_APD status Actual joined to
    Cube_CES on contract, item and plan id, days = ActualDelDate - createDate, negative days dropped) are split by label, MTS against MTO or ETO. An item is mixed
    when it has at least 3 delivered lines of each kind, the MTS-labelled median is at most 14 days, the MTO- or ETO-labelled median is above 14 days, and the two
    medians differ by at least 7 days (config `mixed_rule`, fixed before it was computed). Before it is applied it is tested on the known items (stock_policy and
    confirmed_to_order of PEM101 and PEM107); if it calls more than one in ten of them mixed it is not adopted. When adopted it is applied to every conflict item and
    every mixed-label item in every division and records the MTS share of ordered quantity over the last 12 months; a mixed item gets no Min or Max and its whole
    demand is made-to-order load. A class decided by the user or the business keeps its class even when the rule calls the item mixed.
  - **Label an item shows** (`class_label`), in this order: no_production_in_system; a class decided by the user or the business (PEM101 and PEM107 stock_policy or
    confirmed_to_order, PEM104) keeps its class; too_little_data; mixed; otherwise the class.

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
- The backtest's division RMSE is the mean of the items' own RMSE; one forecast
  month per item gives an item RMSE equal to |error|, so the forward-test score
  record keeps two columns: `RMSE` (the backtest's mean of per-item RMSE) and
  `RMSE_pooled` (the formula above taken over all the division's items).
- MASE follows section 13. Where it is undefined, any output shown to a
  user displays MASE_undefined, never NaN, 0 or infinity.
- Moving-average comparator (R1, decided by the user 2026-10-05): the
  comparator's forecasts are scored with exactly these metrics, one row per
  vintage, division or focus code, target month and horizon, under the scopes
  `comparator_division` and `comparator_focus_code` with key
  `<division or code>|<model>` (for example `PEM101|MA12`), so the existing
  score rows, keys and batch hashes are untouched. Top-down's rows are
  unchanged.

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
- Where a page's sections draw on inputs with different pull dates, each
  section shows its own data_pulled_at. The staleness notice is evaluated
  per section, not from the single oldest input on the page, so one stale
  section never marks a whole page stale.

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

- `data_cutoff_date` holds the PULL DATE: the day the data the vintage was
  fitted on was pulled (vintage 1: 2026-09-07; vintage 2: 2026-10-02). It is
  not the last month of data. `fit_last_month` holds the last month of
  actuals the fit used (vintage 1: 2026-07; vintage 2: 2026-08). Wherever a
  page or report shows a vintage's cutoff it shows `fit_last_month`, labelled
  as the last month of data used. No existing row was edited to change this.
- The log in existence today is vintage 1 and keeps its original cutoff.
- Scores are kept in `output/summary/forward_test_scores.csv`, append-only: one
  row per vintage, division or focus code, target month and horizon, with
  MAE, RMSE, RMSE_pooled, Bias, MASE, item count, run id and the definition id
  of section 13. Each run's rows carry an integrity hash in
  `forward_test_scores_integrity.json`, computed after the rows were written
  and read back, and verified before any row is appended. Existing rows are
  never edited. A score uses the vintage's own fit series, rebuilt from the
  raw pull; items whose fit series is all zero are not scored.
- A monthly run appends one new vintage. Comparing vintages over time is
  the forward test; no single scored month is treated as proof.
- Fit series saved (decided 2026-10-05, from vintage 3 on; `src/vintage_series.py`). Vintages 1 and 2 cannot be
  reproduced because `output/data/processed_all_divisions_monthly_qty.csv` is overwritten each month. Step 5 now
  saves the bytes of that file exactly as the vintage read them, gzip-compressed (mtime 0), as
  `output/forward_test/vintage_series/vintage_<id>_fit_series.csv.gz` before the vintage is appended (a file is never
  overwritten), and records `fit_series_file`, `fit_series_sha256` (of the uncompressed bytes) and `fit_series_n_bytes`
  in the vintage's metadata. Step 6 verifies every recorded hash before it scores and stops the run on a missing file or
  a different hash. Vintages without a recorded hash (1 and 2) are listed as not saved, never as verified, and are not
  touched. The folder is under `output/`, which git ignores, so the files live on the machine that runs the job.
- Moving-average comparator (R1, decided by the user 2026-10-05; Top-down
  stays the production method). From vintage 3 on, every monthly run also
  stores a moving-average forecast for every forecast-status item
  (`src/ma_comparator.py`) in `output/summary/forward_test_comparator_log.csv`
  with integrity hashes in `forward_test_comparator_metadata.json`: the same
  hash method as the log above (`csv_readback_v1`, computed after the rows are
  written and read back, verified before any append). Append-only; the
  forward-test log is never edited. The window per division is chosen on every
  run from the CURRENT BACKTEST only: among the windows the backtest computes
  (config `moving_average_windows`: 3, 6, 12), the one with the lowest mean
  item-level MAE over the division's items and all rolling origins in
  `output/summary/phaseC_step2_rolling_origin_qty.csv`; a tie goes to the shorter
  window; never forward-test results. The choice and its source file are written
  to `output/summary/ma_comparator_windows.csv` and into the vintage's
  metadata. On the backtest of 2026-10-05: CI101 MA12, PEM101 MA12, PEM102 MA3,
  PEM103 MA6, PEM107 MA3. The forecast is `models.moving_average_forecast`
  (the backtest's own function), repeated across the horizon and clipped at 0;
  items with no history get 0, as Top-down does. Vintages 1 and 2 were fitted
  on monthly series that were not saved (the processed and raw files are
  overwritten each month), so they are NOT reconstructed: the comparison starts
  with vintage 3. Nothing is shown on any page.

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
      7b recompute operation plan v1 (section 42) from the page just built and the saved pulls
      7c recompute material plan v1 (section 43) from the operation plan
      7d vintage gate: G1 (the latest vintage of the forward-test log), G2 (`forecast_vintage` in forecast/inventory.html's data), G3 (the operation
         plan's meta) and the material plan (its meta) must carry the same forecast vintage id, else the run stops before step 8
      8 run the full test suite
      9 scan staged files for sensitive content
      10 check change magnitude against the previous run
      11 commit and push only if steps 8 to 10 all pass

    where the jobs run (decision D1, option A, 2026-10-06): the scheduled daily stock job (SaleForecast_PostingDelaySnapshot, 08:00 and 12:00) and this runner
      (SaleForecastMonthlyRefresh) run only from a separate clone of origin, `D:\sale_forecast_publish`, never from the working copy `D:\sale_forecast`. Each task first
      runs `git pull --ff-only origin main` in the clone and starts the job only if that succeeded. The clone's `output/` and `reference/` are junctions to the working copy's
      folders and its `.env` is a hard link to the working copy's, so saved pulls, snapshots, run logs and the lock file stay in one place (config `publishing`:
      `clone_root`, `shared_output_root`); both jobs refuse to publish from anywhere else. Commits and pushes are made only from the clone (the daily job: its two data
      files; this runner: the files of GENERATED_PATHS); work in progress in the working copy cannot stop them, and the working copy takes the published commits with `git pull`.

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
- Saved pulls: the page builders pick "the latest saved pull" only among files dated today or earlier (`inventory_page_sources.not_after_today`); a file dated later, which only a moved clock can produce, is ignored and quarantined (2026-10-08).
- G2 (the Max-Min page's data) takes each item's forecast from the latest vintage of the forward-test log (decision D2 of the user, 2026-10-08):
  the vintage's monthly forecasts in target-month order, extended to the page's 10 months by repeating the last month, and the demand history behind its percentile is the series and fit window of that vintage (the saved fit series when its metadata records one, else `processed_all_divisions_monthly_qty.csv` cut to `fit_first_month`..`fit_last_month`; decision D2, 2026-10-08); Min and Max are computed from them exactly as
  before (Sec.4, Sec.20-23). Step 7 rebuilds it after step 5 (the new vintage) and before steps 7b and 7c.
- Every run writes a run log stating each step's outcome, the figures
  checked at step 10, and whether it pushed. A held or failed run is
  reported in the log, never silently skipped.
- Tests must not modify tracked output files; a test that regenerates a
  page writes to a temporary location.
- Step 4 also regenerates every analysis input the pages display, including
  the order-notice distribution and delivery timeliness by year, so that a
  monthly run leaves no section stale by design. An input the pipeline
  cannot regenerate is listed in the run log and labelled on its page as
  not refreshed.
- The backtest in step 4 follows the rolling_origin_evaluation section.
- Step 4 also regenerates `ma_comparator_windows.csv` (section 27); step 5 writes
  the comparator log beside the vintage and step 6 fills its actual_qty from
  the forward-test log and scores both methods.
- Step 10 gates (changed 2026-10-05). Each of the three checks records
  `passed`, `failed` or `not_tested` with a reason; a check that compared
  nothing is never `passed`:
      six_month_forecast  not tested when step 5 skipped (the one-vintage-per-month
                          guard) or vintage 1 holds no total to compare with
      backtest_mae        not tested when there is no earlier successful run log
      on_hand_stock       the monthly pull's total on-hand units against the total
                          the latest successful daily stock run published
                          (`output/runs/daily/last_success.json`); not tested
                          when there is no daily run or no saved pull
  The step passes when no gate failed. The run log's `gate_outcomes` lists every
  gate of the run (tests, sensitive-content scan, the three above) and counts
  passed, failed and not tested separately; a skipped test run is not tested.

### Daily stock cycle (added 2026-10-05)

The monthly cycle above is unchanged. Beside it, stock and reserved quantities refresh every day; forecasts, Min and
Max and every sales-derived figure stay monthly.

    scheduled task SaleForecast_PostingDelaySnapshot, 08:00 daily and a retry at 12:00 (2026-10-06), start-when-available;
      a run that starts when a daily run of today already finished as published or nothing_to_publish exits at once and logs the skip
      (no database connection); `--force` overrides; a failed, held or dry run never counts as a success
    src/snapshot_daily.py, one database session, in order:
      1 posting-delay snapshot and the stock snapshot — exactly as before, written first
      2 pull the four tables data/inventory.json needs (stock, Cube_CES backlog, old backlog, transfers)
      3 build data/inventory.json and data/stock_daily.json from that one pull, in a temporary folder
      4 gates (below)
      5 publish: git pull; stop if any tracked file is modified or staged; stage only the two files; commit
        naming the pull time; push
    published files: data/inventory.json (index stock panel), data/stock_daily.json (Min-Max page stock figures)

    gates, thresholds in config.yaml `daily_stock`, each an assumption:
      row_count_band        (item, warehouse) rows of the stock pull within +/-20% of the last successful daily run
      on_hand_total_band    total on-hand units within +/-30% of the last successful daily run
      no_null_item_codes    no null or empty item code in the stock or the reserved pull
      pull_newer_than_published   the pull time is later than the pull time of the published stock file

- The base for the two bands is the last successful daily run (`output/runs/daily/last_success.json`); before one
  exists, the latest daily stock snapshot.
- `data/stock_daily.json` holds the on-hand quantity per item and warehouse and three times: the source load time of
  the stock (earliest `timestamp` of the Cube_Inventory_Exact rows pulled), the source load time of the reserved
  quantities (earliest `Timestamp` of the Cube_CES Status='Backlog' rows pulled), and the pull time. The page shows each
  on its own line and states no load schedule. Stock and reserved load at different times, so the reserved date can be
  older than the stock date; each is judged against the staleness threshold separately.
- The monthly runner's step 7 writes the same file from its own saved pull with the same builder (`src/stock_daily.py`),
  so one pull gives byte-identical JSON on both paths; step 11 stages it with the other generated files.
- While the monthly runner runs (lock file `output/runs/monthly_refresh.lock` naming a live process) the daily job
  publishes nothing and says so in its log.
- Every run writes a log under `output/runs/daily/`. A failed gate or step writes the failed gate or step and the error,
  makes no commit or push and exits non-zero; the posting-delay measurement written in step 1 is kept.

## 29. omni_trend_demand_classification

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    ADI[item] = 31 / count(months, of the first 31 calendar months
                2024-01..2026-07, where that item's Actual+MPS qty > 0)
    CV2[item] = population_variance(monthly Actual+MPS qty, over only the
                nonzero months within that same 31-month window)
                / mean(the same nonzero months)^2
    class[item]:
      Smooth       : ADI < 1.32 and CV2 < 0.49
      Erratic      : ADI < 1.32 and CV2 >= 0.49
      Intermittent : ADI >= 1.32 and CV2 < 0.49
      Lumpy        : ADI >= 1.32 and CV2 >= 0.49
      NoSale       : zero Actual+MPS qty in all 32 months (2024-01..2026-08)
      NoSale31M    : zero qty in the 31-month window above, but nonzero in
                     the 32nd (current, partial) month, 2026-08

- Source: `index.html`'s embedded `OMNI` object (script `#omniTabJs`, line 7595) carries each
  item's `adi`/`cv2`/`cls` fields already computed; the tab's own JS reads them, it does not
  compute them at runtime. No generator script for this data exists anywhere in the repo
  (confirmed by a repo-wide search, task 2a; restated in the page's own note, `index.html` line
  7534), so the exact generating code cannot be inspected directly.
- The formula above is the tab's own stated definition, in its "นิยามศัพท์" (glossary) block —
  `index.html` lines 7542-7543 (ADI: "31 เดือน ÷ จำนวนเดือนที่มียอดขาย"; CV²: "ความผันผวนของขนาด
  ออเดอร์ในเดือนที่ขายได้") and line 7549 ("เกณฑ์แบ่งกลุ่ม: ADI 1.32 และ CV² 0.49
  (Syntetos-Boylan)") — and the same threshold is repeated in chart c2's own hint text, line
  7669 ("เส้นแบ่ง ADI 1.32 / CV² 0.49").
- This formula was independently reverse-engineered from the embedded `qa`/`qm` (quantity,
  Actual/MPS) arrays this task and checked against every item in `OMNI.items` carrying a
  non-null `adi` (340 of 448 items, the rest being NoSale/NoSale31M with `adi:null`): **0
  mismatches** on `adi` and `cv2` (population-variance form, matched to 3 decimal places as
  stored) and **0 mismatches** on the resulting `cls` label, for all 340 items. This is strong
  evidence the formula above is what the embedded data is consistent with, not proof of the
  generating script's exact code (which does not exist in the repo to inspect).
- The 31-month window always excludes 2026-08 (the current, partial month) from ADI/CV²,
  distinct from the revenue/quantity totals used elsewhere on the tab (§30/§34 below), which sum
  over all 32 months including the partial one.

## 30. omni_trend_kpi_row

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    item_count        : count of items passing the current filter bar
                        (division/category/type/class/search text)
    total_sales_value : sum of (Actual sale + MPS sale), in THB, over ALL
                        32 months (2024-01..2026-08, including the partial
                        current month), across the filtered items — always
                        the value figure, never affected by the chart-unit
                        (qty/baht) toggle
    class_counts      : count of filtered items per section 29 `cls` label
                        (Smooth / Erratic / Intermittent / Lumpy), plus a
                        combined NoSale count (NoSale + NoSale31M together)

- Source: `index.html` functions `agg()` (lines 7612-7620) and `kpis()` (lines 7780-7789),
  `#omniTabJs`. `pass()` (lines 7604-7611) defines which items are "filtered."
- `total_sales_value` sums `it.sa[i]+it.sm[i]` for every month index (line 7617: `tot+=it.sa[i]
  +it.sm[i]`, looped over all `NM` = 32 months) — this is unconditional on `F.unit1`, unlike
  chart 1's own bars (section 31), which follow the qty/baht toggle.

## 31. omni_trend_chart1_monthly

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    per month        : stacked bar of Actual (qty or value, per the u1_b/
                        u1_q toggle) plus MPS on top, over the filtered
                        items, for all 32 months; the 32nd (current,
                        partial) month's bar is rendered at reduced opacity
    moving_average    : a trailing simple moving average of (Actual+MPS)
                        per month, window = 3, 6, or 12 months, or a
                        user-entered custom width from 1 to 24 months —
                        plotted only from the point where a full window is
                        available (no average for the first window-1
                        months)
    drill-down        : clicking a month's bar opens the daily view for
                        that month (section 36) over the same filtered
                        item set

- Source: `chart1()` (lines 7633-7648) and `maLine()` (lines 7623-7632), `#omniTabJs`. The
  moving average is a trailing window (each point averages itself and the `window-1` months
  before it — line 7625: `for(let k=0;k<win;k++)s+=tot[i-k]`), not centered.

## 32. omni_trend_chart2_map

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    x-axis    : ADI (section 29), clamped for display at 8 (values above 8
                are plotted at the axis edge)
    y-axis    : CV2 (section 29), clamped for display at 6
    per point : one filtered item with non-null adi/cv2 (NoSale/NoSale31M
                items are not plotted)
    radius    : 3 + 7 × sqrt(item's total sale value over all 32 months ÷
                the largest such total among the filtered, plotted items)
    color     : by section 29 class (Smooth/Erratic/Intermittent/Lumpy)
    reference lines: ADI = 1.32 (vertical), CV2 = 0.49 (horizontal)

- Source: `chart2()`, lines 7649-7671, `#omniTabJs`. Display clamping (8/6) affects only where a
  point is drawn on this chart — it does not change the stored `adi`/`cv2` values used elsewhere
  (section 29, the SKU table, or the drill-down modal).

## 33. omni_trend_chart4_division_split

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    per division (PEM101/102/103/104/107/CI101):
      bar   : Actual (qty or value, per the u1_b/u1_q toggle) plus MPS on
              top, summed over all 32 months
      count : number of items in that division passing the current filter
              (other than the division filter itself, which this chart
              overrides one division at a time)

- Source: `chart4()`, lines 7673-7696, `#omniTabJs`. Clicking a bar sets the page's division
  filter to that division (or clears it, on a second click of the same bar).
- The chart's own code comment (lines 7674-7678) records that a 2026-09-24 audit checked whether
  any item appears under more than one division bar (double-counting risk) and found every
  item's `sh` (division) list contains exactly one division, with the six bars' item counts
  summing to the dataset's total distinct item count — no overlap, for the data as embedded
  today.

## 34. omni_trend_sku_table

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    per row (one filtered item): code, pricelist name, category, product
    type, division(s), section 29 class, ADI, CV2, Qty รวม, ยอดขาย (ลบ.),
    Remark

    Qty รวม    = sum of (Actual qty + MPS qty) over ALL 32 months
                (2024-01..2026-08, including the partial current month)
    ยอดขาย (ลบ.) = sum of (Actual sale + MPS sale) over the same 32 months,
                in millions of THB
    Remark     = section 37 match-status badge, plus section 38's
                duplicate-pricelist note when present

- Source: `table()`, lines 7764-7779, `#omniTabJs`. Default sort is by `ยอดขาย` (sale)
  descending; sortable also by Qty, ADI, or code (ascending/descending toggle on repeat click,
  `sortK`/`sortD`, lines 7755, 7766-7769, 7812). Only the first 400 rows (by current sort) are
  rendered; the panel below the table states how many of the total filtered rows are shown
  (line 7777).
- As in section 30, these totals are unconditional on the qty/baht chart toggle — the table
  always shows both quantity and value columns together, never one substituted for the other.

## 35. omni_trend_drilldown_sku

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    per month        : the clicked item's own Actual+MPS bar (qty or
                        value, per a LOCAL toggle inside the modal that
                        starts on quantity by default, independent of the
                        page-level chart-1 toggle), over all 32 months
    mean line         : arithmetic mean of the item's own (Actual+MPS)
                        total, computed ONLY over months, within the first
                        31-month window (section 29's window, i.e. index
                        < 31), that are individually nonzero — the partial
                        32nd month and any zero month are excluded from
                        this average, even though they are still plotted
                        as bars
    moving_average    : same trailing-window definition as section 31,
                        applied to this one item's monthly total
    info line         : category, product type, division(s), class badge,
                        ADI/CV2 (when not null), and section 38's
                        duplicate-pricelist note (when present)
    drill-down        : clicking a month's bar opens the daily view for
                        that month for this item alone (section 36)

- Source: `openSku()`, lines 7697-7728, `#omniTabJs`; the "months in the mean" filter is line
  7706: `act=tot.map(...).filter(o=>o.v>0&&o.i<N31)`.

## 36. omni_trend_drilldown_daily

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    per day of the clicked month : Actual qty/value and MPS qty/value,
    summed from the raw daily records of either:
      - one item (`it.dd`), if opened from the per-SKU drill-down
        (section 35), or
      - every item currently passing the page filter, if opened directly
        from chart 1's monthly bar (section 31)
    a day with no matching raw record shows no bar (no PO received that
    day, per the tab's own hint text, line 7750)

- Source: `openDaily()`, lines 7729-7754, `#omniTabJs`. Each raw daily record is a 5-element
  array `[YYMMDD, qty_actual, sale_actual, qty_mps, sale_mps]` (embedded per item as `it.dd` in
  the `OMNI` object, line 7595) — confirmed by inspecting the embedded data directly this task
  (e.g. item `02-05-R-0004`'s first record `[241128, 2.0, 50000.0, 0.0, 0.0]` = 2024-11-28,
  qty 2, sale value 50,000 THB, Actual status). As with section 29, no generator script exists
  in the repo to show how these raw records were themselves produced from the source database;
  this describes only the structure the page's own JS reads and how it aggregates it.

## 37. omni_trend_match_status

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    Match (badge)        : this item code's `MATCH[code].s == 'ok'`
    Check spec (badge)   : `MATCH[code].s == 'conflict'` — tooltip shows
                           the pricelist spec (`pl_spec`) vs. the DB spec
                           (`db_spec`) and the DB name (`dbn`)
    No spec info (badge) : `MATCH[code].s == 'nospec'` — DB has a matching
                           name (`dbn`) but no spec field to compare
    No data in DB (badge): the item code has no entry in `MATCH` at all
                           (default, `s: 'nodata'`)

- Source: `matchBadge()`, lines 7756-7763, `#omniTabJs`; displayed in the SKU table's "Remark"
  column (section 34) and the per-SKU drill-down's info line (section 35).
- **Could not determine how the match status itself was computed.** The display logic above
  (which badge/tooltip a given status value produces) is fully readable in `index.html`, but the
  `MATCH` object itself (line 7594) is static embedded data — which comparison logic assigned
  `s`/`dbn`/`pl_spec`/`db_spec` to each of the 448 item codes is not present anywhere in
  `index.html`, and no generator script for it exists anywhere in the repo (same repo-wide
  search as section 29/36, task 2a). This is flagged per instruction rather than guessed.

## 38. omni_trend_duplicate_pricelist_flag

**Drafted from the existing Trend Pricelist Omni tab's current implementation, pending user
review — describes what the tab computes today, not a validated or endorsed metric.**

    when present, an item's `rk` text (e.g. "พบซ้ำ 2 รายการ pricelist" —
    "found duplicate 2 pricelist entries") is appended, as a plain hint
    span, after that item's match-status badge, in the SKU table's
    "Remark" column (section 34) and the per-SKU drill-down's info line
    (section 35)

- Source: display logic at lines 7773-7774 (`if(it.rk)rk.push(...)`) and line 7724, `#omniTabJs`.
- **Could not determine how this flag itself was computed.** Only 1 of the 448 embedded items
  (`DS-F-99-0308`) carries an `rk` value in the data checked this task, and no code anywhere in
  `index.html`, nor any generator script in the repo, computes or assigns it — it is static
  embedded data, exactly like section 37's `MATCH` object. Flagged per instruction rather than
  guessed.

**Note on section 26 and this tab**: `index.html`'s own note text for `#omniTab` (lines
7529-7532) already carries `data_pulled_at` (2026-08-25) and `page_built_at` (2026-09-25 12:15
ICT) in the format section 26 defines, and states plainly that this tab is not refreshed by the
pipeline — no new section is needed for this; it is already covered by section 26.

## 39. rolling_origin_evaluation

    series        : the forecast_date-keyed monthly series, from the first
                    usable month to the last eligible month, where eligible
                    means the month has ended and the leakage-guard margin
                    has passed as of the run date
    origins       : K origins with horizon H, spaced as the existing scheme
                    spaces them, placed so the last origin's test window
                    ends at the last eligible month; K, H and the spacing are
                    read from config, not hard-coded
    training      : each origin uses only data before that origin
    metrics       : section 25 and section 13, per origin, then the mean
                    across origins
    run to run    : each monthly run moves the window forward as eligible
                    months accrue; every reported figure states the window's
                    first and last test months

- The Phase C results are the run anchored at their original end month.
  They are kept for comparison and labelled with that window.
- If fewer than K origins fit the available series, use as many as fit and
  report it; below 3 origins, report the backtest as insufficient rather
  than presenting a figure.
- Whether one method forecasts more accurately than another over this
  backtest is decided by section 41, recomputed every monthly run; a single
  split or a frozen pilot result is never cited for it.

## 40. excess_stock_flag

    excess[item] = months_of_cover[item] > obsolescence_threshold_months

- months_of_cover follows section 9, using on_hand_sellable for the
  warehouses currently selected on the page.
- Items with zero forecast have infinite cover and are flagged excess only
  if on_hand_sellable is above zero; they are listed separately as stock
  with no forecast demand.
- The threshold is a Tier A control, default from config.

## 41. topdown_significance

    unit          : the item; each item's MAE (section 25) averaged over its
                    origins of the current backtest (section 39), per method
    pairs         : Top-down against Direct, and Top-down against Naive, per
                    division; items with both forecasts only
    difference    : Top-down minus the other method, so negative = Top-down
                    made the smaller error
    reported      : n items, mean difference, paired t = mean / (sd / sqrt n),
                    two-sided p (t distribution, n - 1 degrees of freedom),
                    Wilcoxon signed-rank p (two-sided) on the same differences,
                    sign of the median difference, relative difference
                    = (mean MAE Top-down - mean MAE other) / mean MAE other
    verdict       : better  when |t| >= paired_t_threshold AND Wilcoxon p <
                    wilcoxon_p_threshold AND t < 0 AND median difference < 0
                    worse   when |t| >= paired_t_threshold AND Wilcoxon p <
                    wilcoxon_p_threshold AND t > 0 AND median difference > 0
                    unclear otherwise, including when t and the median
                    difference have different signs or the median is zero

- Both thresholds are in config.yaml `report_statistics` (2 and 0.05, conventional
  values, an assumption). A Wilcoxon result alone never gives a verdict; where it
  disagrees with the t test the division is unclear.
- Computed by `src/significance_topdown.py` in the monthly runner's step 4 from the
  backtest rows `src/transferability_all_divisions.py` just wrote, into
  `output/summary/topdown_significance.csv`; the sales report block "ใช้วิธี Top-down
  ดีกว่าวิธีอื่นไหม" reads that file. Averaging over origins first keeps pairs of the same
  item across overlapping origins from being counted as independent.
- The 2026-10-05 check (`docs/reports/summary/check_significance_topdown.md`) is the reference:
  its item-level t values per division are reproduced by this computation.

## 42. operation_plan_v1

    scope     : the forecast-status items of PEM101 and PEM107 (the item universe of the Min-Max page: 144 and 112), classes of section 23
    months    : the target months of the latest forward-test vintage (section 27, level Item) from the current month onward; the vintage's
                rows are checked against the hash in its metadata before they are read
    demand[item, month]   = max(forecast[item, month], backlog[item, month])
      backlog = sum of ActualQty + BacklogQty of the Cube_CES rows with Status 'Backlog' whose ForecastDelDate falls in the month;
                a date before the first plan month goes into the first month; a date after the last month is not used and is counted
    part A (class stock_policy; Min and Max exist), per item and month in order
      closing = opening - demand + open orders
      if closing < Min:  planned production = Max - closing;  closing = Max
      opening of the first month = sellable on-hand of the latest daily stock pull (section 7; warehouses of config
      `phase_e1_assumptions.sellable_warehouse_codes` per division); opening of a later month = the previous closing
      Min and Max = those the Min-Max page shows on load: PEM101, the calibrated section at its default preset (`today_lowest_stock`),
      Min and the median Max, interpolated on the section's grid as the page does; PEM107, the item table at the default controls
    part B (classes confirmed_to_order and conflict; no Min or Max): load[item, month] = demand[item, month], recorded with the class
    part C (per division and month):
      total load = planned production (part A) + load (part B)
      capacity reference = the highest sustained monthly output: cube_final transfer_qty summed by the calendar month of final_date,
        items joined to their division by `output/summary/phase24_explorerC_item_type_division_map.csv`; the highest month, passing over
        a month that is at least config `spike_ratio` (2) times the next-highest. It is a lower bound on capacity, not capacity. Units are
        summed across products.
      above capacity = total load > capacity reference
    open production orders: counted only when config `open_orders_usable` is true; the 2026-10-06 test (`src/investigations/
        week2_open_orders_test.py`, criteria in config `operation_plan.open_orders_test`) found they cannot be used: the plan counts none

- Recorded outputs (untracked, `output/summary/`): `operation_plan_v1_item_month.csv`, `operation_plan_v1_division_month.csv`,
  `operation_plan_v1_meta.json`, each with a SHA-256 in `operation_plan_v1_integrity.json`, verified before they are read back. Per
  item and month: forecast, backlog due, demand and its source, opening, open orders, Min, Max, planned production, closing, load.
- Computed by `src/operation_plan.py`; the monthly runner's step 7b recomputes it from the page step 7 built and the saved pulls.
- Assumptions (each also in the meta file): production quantity is not rounded and has no lot size; stock at the start has nothing
  in process added; the sellable warehouses are the configured assumption; capacity is a lower bound; PEM101's Min and Max are the
  lead-time-free calibration's (decision D2, 2026-10-05, window of decision D4, 2026-10-06).
- The capacity recomputed from the saved cube_final pull (2026-10-05) equals the figures DATA_MAP.md records for the same method (PEM101
  249,080 and PEM107 6,221 units per month); config `capacity.data_map_reference` holds them and the plan reports whether they match.

### Week 3: all six divisions (2026-10-06; `src/operation_plan.py`)

    scope     : every item of the item-level file (METRICS.md Sec.23): forecast-status and placeholder items of CI101, PEM101, PEM102, PEM103 and PEM107, and PEM104's
                items; divisions in the order PEM101, PEM103, PEM107, PEM102, PEM104, CI101
    Min, Max  : PEM101 and PEM107 only (read from the inventory page as before); every other item's load equals its demand
    demand    : an item without a forecast (placeholder items and PEM104) uses only the confirmed orders not yet delivered (Cube_CES Status 'Backlog')
    channel   : PEM103 counts only the backlog rows whose RevenueType is Omni Channel (config `backlog_channel_scope`); the latest saved pull's rows are used, and
                for the scoped division the saved week 3 pull's rows while the daily pull has no RevenueType column
    not counted: an item marked no_production_in_system keeps its row (demand, load) with `counted` false and is in no total; the division-month total counts the
                counted rows only, `load_not_counted` is the rest
    capacity  : the method above for every division; items the item-division map file does not hold (CI101 and PEM102) take their price-list division; a division
                with no cube_final output has no capacity (a dash on the page)

- Item-month columns added: status_category, class_label, data_inconsistent, counted. Division-month column added: load_not_counted. `class` stays the Sec.23 class
  used (decisions applied); the page and the plan read the class from the item-level file and stop if a PEM101 or PEM107 forecast-status item's class differs from the page's.

### Split of stock-item production and the planners' page (added 2026-10-06; `src/build_operation_plan_page.py`)

    per stock item and month:
      meets demand = min(planned production, that month's demand)
      refill       = planned production - meets demand
    per division and month on the page:
      produced to meet demand = sum of meets demand over the stock items
      refilled to Max         = sum of refill over the stock items
      made to order           = sum of load over the confirmed_to_order and conflict items
      total                   = the three added; it equals the recorded division-month total_load (the build stops if not)
      against the highest sustained output = total / capacity reference; above 100 percent when total > capacity reference

- Computed in the page builder from the recorded plan (read after its SHA-256 check); the plan and its recorded outputs are not changed. The
  parts add back to planned production exactly (a test checks it).
- The first-month sentences read from the same data: the PEM101 refill part of the first month; for PEM107 the first-month sum over items of
  max(backlog due - forecast, 0), and the items contributing most, in descending order, until together they reach 80 percent of that sum,
  at most three. A sentence is left out when its figure rounds to zero.
- `forecast/operation_plan.html` is built by the monthly runner's step 7b after the plan is recomputed, and is in its staging list. Product
  names come from the price list; the stock pull time and the forecast run month are those of the plan's inputs.


## 43. material_plan_v1

    input    : the operation plan's production quantities per item and month (planned production of an item with a Min and Max, the load of every other item) of the
               counted rows, every division; the plan is read after its SHA-256 check
    explode  : level by level through Cube_BOM_Exact (config `bom_source`); a component with its own BOM and no purchase record (no purchase order line and no
               receipt since config `purchase_evidence_since`) is an in-house sub-assembly and is expanded; every other component is a purchased material (a component
               with a purchase record is purchased even when it has a BOM entry, one with neither is a purchased material of unknown supply); the header row and the
               time pseudo-codes (BOM lines whose Type contains 'hour': Machine Hour and Labor hour) are not components; a BOM that does not end within `max_bom_levels` stops the build
    in-house stock (decision D2, 2026-10-06): parents before children; the requirement that all of a sub-assembly's parents put on it, per month, is netted against its on-hand
               stock in the raw-material warehouses (the net-requirement rule below with no arrivals: stock covers the earliest months first) before it is expanded to its own
               components, so only the net amount goes further; a finished item's own plan quantity is not netted (the operation plan starts from its stock). A finished item that is also a component of another plan item has the requirement its parents put on it netted against its stock only when the operation plan has not used that stock, that is only for an item without a Min and Max (decision of 2026-10-07; 11 counted plan items are components of another plan item and all 11 receive a requirement from their parents (9 also have a quantity of their own); one of them, HS-F-99-0303, has a Min and Max and 0 units in stock, so nothing changes for it, and the other 10 are netted, so the recorded plan did not change; 133 materials would differ if they were never netted; a counted plan item is expanded through its own BOM even when it has a purchase record, as TF-F-99-15044211Q1 and VT-F-99-010202 do; "has its own BOM" is judged on the BOM rows before the hour lines are dropped, so an item whose only rows are the header and hour lines counts as in-house and expands to nothing); item codes are
               trimmed of leading and trailing spaces before matching (decision D3)
    gross[material, month]      = the exploded quantity (BOM quantity per unit of the parent, in the BOM's unit)
    available[material, month]  = stock in the raw-material warehouses (config `rm_warehouses`, a negative total counts as zero)
                                  + the open orders of Cube_tobe_received whose expected date has arrived by the end of the month (a date before the first month counts in
                                  the first month); used because its tests passed (see below)
    net requirement (cumulative) = the running maximum of max(0, cumulative gross - available); the month's net requirement is its increase
    latest order date            = the first day of a month with a net requirement minus the material's lead time in days (a lead time with a half day gives a date at
                                   noon; the order date is that calendar day, so the day itself still counts as a day to order); the material's date is the first of them
    two lists (page, decision of 2026-10-06; `order_window_days` in config `material_plan`, 30)
                                 = by the material's latest order date against the day of the build: from that day to that day plus `order_window_days`, both days included
                                   (order within the window), and before that day (short already, too late to order today). The quantity shown is the sum of the net
                                   requirements of the months whose order date is within the window or has passed. A material with no purchase unit in the system (blank in the
                                   price list and the open orders), or whose purchase unit differs from its BOM unit, is flagged and shows a dash for quantity and date.
    to order now                 = the material's date is the day of the build or has passed (summary column `to_order_now`: 598 on 2026-10-06; the second list takes
                                   only the dates before that day, 596, and the first list starts on that day); the quantity to order now is the sum of the net
                                   requirements of the months whose date has arrived or passed
    lead time per material       = the order of sources of Sec.5 (median observed days from purchase order to first receipt, the supplier's non-zero quoted days, the assumed
                                   fallback), labelled ใบสั่งซื้อจริง, ผู้ขายแจ้ง or ค่าประมาณ on the page

- **Proofs, run before each source was used** (functions `rm_warehouse_proof`, `open_orders_proof`, `bom_source_proof`, `unit_proof` in `src/material_plan.py`; thresholds in config
  `material_plan`, fixed before the tests; results in STATUS.md and DATA_MAP.md, week 3):
  - raw-material warehouses: those that issue to production (type B) at least `rm_warehouse_min_share` of the 12 months' type B issues of the BOM components; the warehouse
    that receives most purchases (QA) issues almost nothing and is reported apart;
  - open orders: usable when at least 90 percent of Cube_tobe_received lines match a purchase-order line, of those at least 90 percent have the open quantity equal to
    ordered minus received and at least 90 percent have the expected date equal to the PO's planned date, and on received history at least 70 percent of lines have their
    first receipt within 14 days of the planned date;
  - BOM source: Cube_BOM_Exact against Cube_BOM_Exact_V2 by the share of materials actually issued to 2026 production orders (Cube_JobCost_Detail actual quantity) that are
    a line of the order item's BOM, and by the issued quantity against produced quantity x BOM quantity (within 5 percent);
  - units: the BOM unit against the stock unit and against the purchase unit (price list, open orders), per material ("same" only when every known unit equals the BOM
    unit; a material that is bought in a second unit as well is "differs"); a unit of '-' or blank is unknown. No conversion factor
    is applied: where the units differ the quantities are netted as they are and the material is marked.
- Recorded outputs (untracked, `output/summary/`): `material_plan_v1_material_month.csv` (per material and month: gross, stock available, cumulative open orders,
  cumulative net, net, order date) and `material_plan_v1_material_summary.csv` (per material: name from the item master Cube_ItemList, the finished goods that use it most,
  units and their check, stock, open orders, lead time and its source, totals, first short month, latest order date, to order now, quantity to order now), each with a
  SHA-256 in `operation_plan_v1_integrity.json` under "material_plan", verified before they are read back. Inputs: the saved week 3 pulls
  (`output/data/material_pull/material_inputs.pkl`, untracked, pulled by the monthly runner's step 1).
- Computed by `src/material_plan.py`; the monthly runner's step 7c recomputes it from the operation plan step 7b just recorded and builds `forecast/material_plan.html`
  (`src/build_material_plan_page.py`).
- Assumptions (each also in the meta of the integrity file): no minimum order quantity or lot size; stock of in-house sub-assemblies is netted (decision D2; before it the gross
  requirement was an upper bound where sub-assemblies are stocked); overdue open orders count in the first month although some arrive later; the stock in the inspection warehouse (QA) is not
  available; the lead time starts at the purchase-order date.

## 44. pilot_categories

    Drop-out Fuse Cutout = the price-list items whose Product Type is "High Voltage Distribution Fuse Cutout"
    Surge Arrester       = the price-list items whose Product Type is the Medium Voltage one, "Medium Voltage Surge Arrester"
                           (decision D3 of the user, 2026-10-07; the Low Voltage Surge Arrester Type is not part of it)

- Defined in config `pilot_categories` (`fuse_cutout`, `surge_arrester`); the view data of the two categories (`src/focus_item_model_selection.py --pilot-view`) reads
  them from there. A category's series is the sum of its items of the forecast scope, its backtest figures are those of Sec.13 and 25 on that series (the Type-level
  combination) and the mean of its items' own figures, both labelled.
- An item on the price list that is not in the forecast scope is listed with its reason from the item status file (`output/summary/phaseC_step1revised_item_status_445.csv`):
  "excluded - listed but never sold" or "placeholder - method already assigned".

## 45. target_comparison

    The executive summary compares the revenue target with an actual measure; decisions of the user, 2026-10-08:
      Business            = the item's pricelist division where it differs from the database's `division` column (D1)
      PO Receive          = not compared for now (D2)
      revenue target      = Revenue (MB)-Conting, as held in `Cube_Target_PMIS` (TargetRevenueAmount; a plan by year, no month), used once the matching actual
                            measure is proven (D2); not yet proven (week 4, prompt 7: no database object pairs them, no candidate reproduces it)
      PEM104 and PEMC     = their targets are shown with a remark saying why they cannot be compared yet (no forecast, no matching database rows); none is left out (D3)

- The workbook's Product Types are matched to database types by exact name or, where marked, by inference; inferred matches are not facts until the user confirms them
  (list in docs/reports/summary/prompt5_g2_vintage_target_map.md, "Prompt 7", Part 3).
- Tests never connect to the database: `tests/conftest.py` blocks every connection and `src/db.py` refuses while `SALE_FORECAST_BLOCK_DB` is set (decision of 2026-10-08).
