# Phase E1.4 — Historical simulation

## What this simulation CANNOT show (stated here, not buried in a footnote)

**No historical stock-movement/transaction-level time series exists in this database** (confirmed
absent, Phase D / inventory investigations). **Initial stock (2024-01 starting quantity), receipt
timing (when a replenishment order actually arrives), and fulfilment sequence are all ASSUMPTIONS**
recorded in `config['phase_e1_assumptions']` (`simulation_initial_stock_assumption`,
`simulation_receipt_timing_assumption`, `simulation_fulfilment_sequence_assumption`), each with an
owner (Modeler default in every case — no data or business figure exists for any of the three) and
labelled a scenario input, not a fact. **This simulation answers "what would this policy have
produced under these stated assumptions" — it does NOT answer "how much would have been saved"**
(no baseline-vs-policy cost comparison is computed here; that is Phase F's job).

**Scope: the same 66 FG-stock items as E1.3.** Replays **2024-01 through 2026-07** (the full
31-month history this project's data actually covers — NOT all of calendar 2026, which has not
fully happened in the data yet). Script: `src/phaseE1_historical_simulation.py`. Outputs:
`phaseE1_4_simulation_item_scenario.csv` (66×18 = 1,188 rows), `phaseE1_4_scenario_summary.csv`
(18 rows), `phaseE1_4_simulation_default_scenario_monthly.csv`. Chart:
`output/charts/phaseE1_historical_simulation_default_scenario.png`.

**Scope decision, stated explicitly, not a silent shortcut: the FULL 18-scenario grid was
simulated** (66 items × 18 scenarios × 31 months = 36,828 item-months) — this was cheap enough
to run in full, so no reduction to "default + 2-3 alternates" was needed.

## 1. Simulation mechanics

- **Ordering rule**: the classic (s, S) periodic-review interpretation of Min-Max — at each
  monthly review (review interval = 30 days ≈ monthly, matching this project's data
  granularity), if inventory position (on-hand + on-order) ≤ Min, order UP TO Max (order
  quantity = Max − inventory position), arriving after a **deterministic** lead time =
  `ceil((procurement_lead_time_days + assembly_time_days) / 30.44)` months. Chosen because no
  MOQ/lot size exists to fix a literal fixed order quantity (same absence documented in E1.3).
- **Fulfilment sequence**: each month, any scheduled receipt is added to on-hand FIRST; then
  demand is subtracted, backlog (unmet demand carried from prior months) served before that
  month's own new demand. Demand exceeding available stock is BACKORDERED (carried to next
  month), not treated as a lost sale — consistent with STATUS.md's finding that demand is not
  censored by stockouts in this data.
- **Unit fill rate** (computed HERE, distinct from cycle service level, per Section 1 of the
  E1.3 report): the fraction of each month's OWN new demand shipped in that SAME month (not
  counting backorder catch-up) — the closest available analogue to this project's own "on-time
  delivery" business metric.

## 2. Full scenario grid results

| lead (d) | assembly (d) | service level | protection period | mean unit fill rate | total stockout item-months (of 2,046) | mean longest stockout streak (mo) | mean stock qty | total mean stock value (THB) | obsolescence-risk items |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 45 | 3 | 90% | 3 | 0.984 | 11 | 0.167 | 4,542 | 43,420,823 | 4 |
| 45 | 3 | 95% | 3 | 0.991 | 3 | 0.045 | 5,045 | 48,244,623 | 4 |
| 45 | 3 | 98% | 3 | 0.997 | 3 | 0.045 | 5,449 | 52,341,663 | 4 |
| 45 | 7 | 90/95/98% | 3 | *(identical to 45/3 rows — same rounded horizon)* | | | | | |
| **60** | **3** | **95% (DEFAULT)** | **4** | **0.990** | **6** | **0.091** | **5,629** | **55,399,687** | **4** |
| 60 | 3 | 90% | 4 | 0.979 | 20 | 0.288 | 5,099 | 49,473,803 | 4 |
| 60 | 3 | 98% | 4 | 0.996 | 3 | 0.045 | 6,025 | 59,160,483 | 4 |
| 75 | 3/7 | 90/95/98% | 4 | *(identical to 60/x rows — same rounded horizon)* | | | | | |

(Full 18-row table in `phaseE1_4_scenario_summary.csv`. Rows collapse to two distinct outcome
groups because only 2 distinct protection-period horizons exist across the whole 18-scenario
grid, per E1.2 — assembly-time and some lead-time combinations round to the same horizon.)
Category: **verified simulation output under stated assumptions**.

## 3. Default-scenario headline (66 items, 31 months, 2,046 item-months)

- **Mean unit fill rate: 98.99%.**
- **6 of 2,046 item-months (0.29%) experienced a stockout** (that month's own new demand not
  fully shippable that month); mean longest consecutive stockout streak per item: 0.09 months
  (i.e. almost no item ever strings together consecutive stockout months at this scenario).
- **Mean stock quantity: 5,629 units across the 66 items** (mean of month-end on-hand, pooled).
  **Total mean stock value: THB 55,399,687** (0 of 66 items lack a usable cost record — see
  E1.5 for the unit-cost methodology).
- **4 of 66 items flagged obsolescence-risk** (a streak of on-hand stock with zero demand
  longer than the configured 6-month threshold, `config['phase_e1_assumptions']['obsolescence_threshold_months']`).

## 4. Chart

`output/charts/phaseE1_historical_simulation_default_scenario.png` — total simulated stock
quantity and value across the 66 items, month by month, 2024-01 to 2026-07, under the default
scenario.

## 5. What this means for the acceptance criteria (self-check only, not a decision)

- **Fill rate**: 98.99% simulated ≥ 73.2% current on-time rate — **PASSES**, by a wide margin.
  Category: **verified**, but see the caveat above: this is a fill rate under an idealised,
  assumption-heavy simulation (deterministic lead time, no real starting-stock data), not a
  guarantee this would be achieved in practice.
- **Stock value**: THB 55.4M simulated (66 items only) vs THB 37.4M current (FULL 445-item
  scope, Phase D) — **FAILS** even before an apples-to-apples 128-item comparison is applied (see
  `phaseE1_5_current_settings_comparison_report.md` and the top-level report for the full
  reconciliation and explanation). Category: **verified figures, hypothesis for the
  explanation** (a 95%-service-level, 4-month-protection-period policy requires substantial
  safety stock for genuinely variable Erratic/Lumpy demand — this is the expected shape of the
  result for demand this intermittent, not evidence of an error, but it is not proven to be the
  ONLY explanation).
