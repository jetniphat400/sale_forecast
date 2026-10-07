# Phase E1 — Validator Report (single Validator, independent recomputation)

**Role**: Validator (per `AGENTS.md`). This report recomputes four Phase E1 headline figures
**independently, from raw data (a fresh live database pull, run 2026-09-18) and `config.yaml`
alone**. No Modeler intermediate file for Phase E1 was read, opened, or grepped at any point —
no `output/summary/phaseE1_*` file, no `output/charts/phaseE1_*` file, and no `src/phaseE1_*.py`
file. The Orchestrator, not this report, is responsible for comparing these figures against the
Modeler's own numbers.

**Script**: `src/investigations/phaseE1_validator.py` (single file, run end to end;
console output captured below). **Raw CSVs**: `output/summary/phaseE1_validator_fig{1,2,3,4}_*.csv`.

**Reused, pre-existing (pre-Phase-E1) building blocks** — read and reused exactly as the task
permits, never copied or adapted from any `src/phaseE1_*.py` file:
- `src/db.py` — DB connection (`run_query`), the only place credentials are touched.
- `src/models.py` — `combination_forecast` (the LOCKED forecasting method: equal-weight mean of
  Naive/MA3/MA6/MA12/Croston/SBA), reused verbatim.
- `src/pricelist_reader.py` — `load_visible_product_rows` (visible-sheet pricelist reader).
- `src/load_data_full.py` — re-implemented pattern (Category-scope derivation, raw-pull
  filters), not its own CSV outputs.
- `src/item_level_reconciliation.py` / `src/transferability_all_divisions.py` — the Top-down
  share pattern (share computed from **train data only**), re-implemented from scratch in this
  script; neither file was imported or copied.
- `src/build_inventory_dataset.py` — the `Cube_Backlog` query pattern (`sale_company IN
  ('PEM','CI')`, no status filter), re-written as a fresh query here.
- `src/investigations/phaseD_check2_stock_value.py` — the unit-cost methodology (`cost/qty` per
  row; median over the trailing 12 months anchored to the global max `createDate`; most-recent-
  transaction fallback). This is a pre-existing **Phase D** script (not Phase E1), explicitly in
  scope to read and reuse.

---

## Step 1 — Independent 128-item scope + overlap check

**Method**: read `reference/pricelist.xlsx` directly (visible sheets only, via
`pricelist_reader.load_visible_product_rows`), filter to `category IN ('Fuse','Surge Arrester')`.
This is **more** independent than reading `config['adopted_scope_file']`'s CSV (itself produced
by `src/load_data_full.py`), and doubles as a cross-check against it.

**Result**: **128 codes, 8 Types, 2 Categories** — exact match (0 symmetric difference) against
`output/summary/part1_category_scope_all_codes.csv` (the file `config['adopted_scope_file']`
names). **Category: VERIFIED.**

**Overlap check** (`config['excluded_item_codes']`, `config['placeholder_item_codes']` vs. the
128-item scope):
- **6 of 6 `excluded_item_codes` fall inside the 128-item scope**: `EEE-F-FL-1040030100`,
  `HS-F-99-0181`, `HS-F-99-1181`, `HS-F-99-1211H22`, `HS-F-99-1241H03`, `HS-F-99-3031`.
- **10 of 10 `placeholder_item_codes` fall inside the 128-item scope**: `EEE-F-FL-5920-353-01100`,
  `EEE-F-FL-5920-353-01600`, `EEE-F-FL-5920-353-02600`, `EEE-F-FL-5920-353-06600`,
  `FC-A-38-00203`, `HS-F-99-1151`, `HS-F-99-2091N`, `HS-F-99-3121`, `HS-F-99-3331`,
  `HS-F-99-3361`.
- No code appears in both lists. **128 − 6 − 10 = 112**, matching the task's own stated figure.
  **Category: VERIFIED.**

---

## Fresh raw pull (used for every figure below)

**Method**: live query against `[salewarehouse].[dbo].[cube_Sale_APD]`, filtered on
`itemcode IN (<128 codes>) AND revenue_type='Omni Channel' AND status IN ('Actual','MPS') AND
createDate >= '2024-01-01'` — **no `division` filter** (per `CONVENTIONS.md` / the division
source-of-truth correction). Pull run 2026-09-18 (this Validator's own frozen
`snapshot_pull_date`). **28,146 rows, 113 of 128 items present** (15 have zero rows anywhere in
this scope/window — consistent with the excluded/placeholder items having no or near-no history).

Monthly series keyed on `forecast_date` (`config['adopted_series_key']`), Actual+MPS, dropping
null/negative-interval `forecast_date` rows (same rule `load_data_full.py` uses), zero-filled over
each item's own observed month range. **Last COMPLETE month = 2026-08** (2026-09 is in progress
on the pull date, excluded from the "actual history" series, same convention
`load_data_full.py` uses for its own trailing partial month). **32 months, 2024-01 to 2026-08.**
**Category: VERIFIED** (direct query + direct recomputation).

**Protection period** (task definition: procurement lead time + assembly time + review interval,
default scenario): `60 + 3 + 30 = 93 days`. **Rounding rule**: `ceil(93 / 30.44) = 4 months` —
the same day→month conversion constant (30.44) `config['phase_e1_assumptions']
['simulation_receipt_timing_assumption']` itself uses, applied here for consistency rather than
inventing a different constant. **Category: stated rounding rule, consistent with config's own
convention, not itself a data fact.**

---

## ADDENDUM (2026-09-18, Orchestrator-directed targeted re-check) — Figures 1 & 2 re-run on the FROZEN series

**What triggered this addendum**: the Orchestrator compared this report's original Figure 1/2
numbers against the Modeler's independently-obtained numbers and found a large discrepancy (e.g.
`HS-F-99-02110`: this report's original Min 2,170.80 vs. Modeler's 917.50). The Orchestrator
traced the likely cause: this report's ORIGINAL Figures 1 and 2 were built from **a fresh LIVE
database pull run 2026-09-18** (32 months, 2024-01 to 2026-08), not from this project's LOCKED,
adopted, FROZEN series (`config['adopted_series_key'] = "forecastDate"`, captured as a frozen
snapshot per `STATUS.md` Locked Decisions — the whole point being reproducibility across runs, per
`CONVENTIONS.md`'s reproducibility rule and the Phase E0.1 leakage pre-check). The frozen file
(`output/data/processed_full_category_sales_monthly_forecastDate.csv`) has `snapshot_pull_date =
2026-09-04 16:44:45`, months **2024-01 to 2026-07 (31 months, not 32)** — one month shorter, and
missing whatever confirmed orders were added to the near-boundary months between 2026-09-04 and
this report's original 2026-09-18 live pull.

**Per the Orchestrator's explicit instruction**: Figures 1 and 2 below are RE-COMPUTED using this
frozen file as the input series, with the exact same independent method as originally used (no
formula/logic changes — only the input series and the resulting month boundaries changed).
**Figures 3 and 4 are untouched** (the Orchestrator is handling that comparison separately).
**The original live-pull numbers are kept below, clearly labelled**, so the discrepancy's cause
stays traceable rather than being silently overwritten. New script:
`src/investigations/phaseE1_validator_frozen_recheck.py` (imports this Validator's own already-
written functions from `phaseE1_validator.py` — no `phaseE1_*` Modeler file was read). New CSVs:
`output/summary/phaseE1_validator_fig{1,2}_*_FROZEN.csv`.

**Result — Figure 1, frozen-series Min (this Validator's own method, unchanged; input series only
changed)**:

| Item | n months | n windows | Mean | p95 | Safety stock | **Min (FROZEN)** | Min (original, LIVE pull) |
|---|---|---|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 31 | 28 | 4,337.68 | 10,788.20 | 6,450.52 | **10,788.20** | 10,865.80 |
| `HS-F-99-02110` | 31 | 28 | 290.29 | 917.50 | 627.21 | **917.50** | 2,170.80 |
| `HS-F-99-0213` | 31 | 28 | 347.07 | 763.75 | 416.68 | **763.75** | 1,221.80 |

**This confirms the Orchestrator's root-cause diagnosis directly**: on the frozen series,
`HS-F-99-02110`'s Min is **917.50** and `HS-F-99-0213`'s Min is **763.75** — both now match the
exact values the Orchestrator quoted from the Modeler's own independent computation, to the cent.
The live-pull version's much higher Min for these two items (2,170.80 / 1,221.80) was driven
almost entirely by the one extra month (2026-08) and any qty added to near-boundary months between
the two pull dates, not by any error in this Validator's method — the empirical-distribution
formula itself is identical in both runs. `EEE-F-FC-1040010002` moves much less (10,788.20 vs.
10,865.80, a 0.7% difference) — consistent with that item's much larger absolute volumes making it
less sensitive to one month's addition/removal than the two lower-volume items.
**Category: VERIFIED (frozen-series figure is now the CORRECTED, primary Min for all 3 items;
the original live-pull figure is retained above only as a diagnostic trace, not as a second valid
answer).**

**Result — Figure 2, frozen-series consumption (horizon now 2026-08 to 2026-11, the 4 months
starting right after the frozen series' own last month 2026-07; confirmed MPS/backlog are still
queried live — no frozen equivalent exists for those tables — but the overdue/future backlog
split now uses the frozen file's own `snapshot_pull_date` 2026-09-04 as "now," not today, so the
whole re-check stays internally consistent with a single snapshot moment)**:

| Item | Period | Month | Confirmed qty | Raw forecast (FROZEN) | % of forecast consumed |
|---|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 1 | 2026-08 | 0.0 | 1,614.74 | 0.0% |
| `EEE-F-FC-1040010002` | 2 | 2026-09 | 2,095.0 | 1,614.74 | 129.7% |
| `EEE-F-FC-1040010002` | 3 | 2026-10 | 370.0 | 1,614.74 | 22.9% |
| `EEE-F-FC-1040010002` | 4 | 2026-11 | 0.0 | 1,614.74 | 0.0% |
| `HS-F-99-02110` | 1 | 2026-08 | 0.0 | 186.44 | 0.0% |
| `HS-F-99-02110` | 2 | 2026-09 | 578.0 | 186.44 | 310.0% |
| `HS-F-99-02110` | 3 | 2026-10 | 100.0 | 186.44 | 53.6% |
| `HS-F-99-02110` | 4 | 2026-11 | 0.0 | 186.44 | 0.0% |
| `HS-F-99-0213` | 1 | 2026-08 | 0.0 | 167.66 | 0.0% |
| `HS-F-99-0213` | 2 | 2026-09 | 398.0 | 167.66 | 237.4% |
| `HS-F-99-0213` | 3 | 2026-10 | 100.0 | 167.66 | 59.6% |
| `HS-F-99-0213` | 4 | 2026-11 | 0.0 | 167.66 | 0.0% |

| Item | Confirmed qty (total) | Raw forecast (total, FROZEN) | % consumed (FROZEN) | % consumed (original, LIVE pull) |
|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 2,465.0 | 6,458.97 | 38.2% | 24.3% |
| `HS-F-99-02110` | 678.0 | 745.77 | 90.9% | 47.6% |
| `HS-F-99-0213` | 498.0 | 670.63 | 74.3% | 47.8% |
| **Grand total (3 items)** | **3,641.0** | **7,875.4** | **46.2%** | **28.9%** |

**Confirmed-qty totals are unchanged (3,641.0 in both versions)** — those come from a live query
against current MPS/backlog data regardless of which historical actual-demand series feeds the
forecast, so they were never affected by the live-vs-frozen issue. What changed is the **raw
forecast** denominator: the frozen series' Top-down combination forecast is materially lower
(7,875.4 vs. 12,599.1 total) because it fits on one fewer month of (in this case, apparently
higher-demand) history, and the horizon itself shifted a month earlier (2026-08 to 2026-11 instead
of 2026-09 to 2026-12) — Period 1 (2026-08) is now a fully-elapsed month with 0 confirmed demand
for all 3 items (any August MPS would already have converted to `Actual` status by now), while
Periods 2–3 (2026-09/10) carry all the confirmed demand. **The % of forecast consumed is
materially higher under the frozen series (46.2% vs. 28.9% pooled) — this is the CORRECTED
figure**; the original live-pull figure is retained above only as a diagnostic trace.
**Category: VERIFIED (frozen-series figure is the corrected primary answer for the "raw forecast"
and "% consumed" columns; the confirmed-qty figures were already correct in both versions).**

---

## Figure 1 — Min for the 3 focus items (ORIGINAL, live-pull version — superseded by the Addendum above for the primary answer; kept for the discrepancy trace)

**Method**: for each focus item, build the empirical protection-period cumulative-demand
distribution as **every overlapping 4-month rolling sum of the item's own actual (Actual+MPS)
monthly history** (32 months → 29 overlapping 4-month windows). Confirmed
`config['phase_e1_assumptions']['safety_stock_convention'] == "percentile_value_minus_
distribution_mean"` before computing — i.e. safety stock = (95th percentile of that distribution)
− (its own mean); Min = mean + safety stock, algebraically identical to Min = the percentile
value directly (both stated, per config's own note).

**Note on the "Top-down combination forecast" framing in the task text**: the task's Figure-1
paragraph references the locked Top-down combination method as scene-setting context for how
this project forecasts these items in general. The specific instruction for Min itself says
"build ... from its own actual monthly history" and the safety-stock convention is defined purely
in terms of the empirical distribution's own mean and percentile — no forecast model enters this
calculation. This Validator therefore computed Min directly from real historical demand, with no
model in the loop, which is the literal reading of the instruction and also the simpler,
zero-additional-assumption path. (The Top-down combination method IS used below, in Figure 2,
where the task explicitly asks for "the raw statistical forecast for that item-month.")

**Cycle service level**: 0.95 (`config['phase_e1_assumptions']['default_scenario']
['cycle_service_level']`).

| Item | n months history | n 4-mo windows | Mean protection demand | p95 value | Safety stock | **Min** |
|---|---|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 32 | 29 | 4,718.48 | 10,865.80 | 6,147.32 | **10,865.80** |
| `HS-F-99-02110` | 32 | 29 | 471.07 | 2,170.80 | 1,699.73 | **2,170.80** |
| `HS-F-99-0213` | 32 | 29 | 435.45 | 1,221.80 | 786.35 | **1,221.80** |

**Category: VERIFIED** (direct recomputation from a fresh live pull; the only non-data choices
are the rounding rule above and the cycle-service-level value, both taken directly from config).
**Caveat**: 29 overlapping windows are not 29 independent draws (each window shares 3 of 4 months
with its neighbours) — the empirical percentile is noisier than a 29-observation i.i.d. sample
would be; stated honestly, not adjusted for, since no alternative was specified.

Full detail: `output/summary/phaseE1_validator_fig1_min.csv`.

---

## Figure 2 — Consumption for the 3 focus items over the protection-period horizon (ORIGINAL, live-pull version — superseded by the Addendum above for the primary answer; kept for the discrepancy trace)

**Horizon**: 4 months starting the pull date's own in-progress calendar month (2026-09, the month
right after the last COMPLETE historical month 2026-08) through 2026-12. **Stated choice**: Period
1 = the pull month itself (partial), not the month after it — chosen because (a) the task says the
horizon starts "right after the snapshot pull date" (i.e. from now, not from the next full
calendar month), and (b) this project's own business finding is a 6-day **median** customer order
notice (STATUS.md, Business Findings) — nearly all already-confirmed demand for these items sits
within days of the pull date, and starting Period 1 at the *next* calendar month would have pushed
almost all of it out of the horizon entirely as an artifact of month-boundary bookkeeping, not a
real gap in confirmed demand. This is a stated judgment call, not the only defensible one.

**Confirmed demand — method**:
- **MPS rows**: `SELECT itemcode, forecast_date, qty FROM cube_Sale_APD WHERE itemcode IN (...)
  AND revenue_type='Omni Channel' AND status='MPS'`, bucketed by `forecast_date`'s calendar
  month into the horizon.
- **Cube_Backlog rows**: `SELECT docID, itemcode, quantity, status, sale_company, deliverydate,
  plan_deliverydate FROM Cube_Backlog WHERE itemcode IN (...)`, filtered to
  `sale_company IN ('PEM','CI')` (the pattern `build_inventory_dataset.py`'s `query_backlog`
  uses), effective date = `deliverydate`, falling back to `plan_deliverydate` when null.
  **Rows whose effective date is already PAST the pull date (2026-09-18) count as immediate
  Period-1 demand** (per the task's own instruction). Rows with a FUTURE effective date are
  **NOT** added on top of MPS for their own future period.

**Stated scope decision on double-counting** (verbatim from `config['phase_e1_assumptions']
['backlog_vs_mps_double_count_note']`, confirmed unchanged): *"cannot be determined from data (no
shared key between Cube_Backlog and cube_Sale_APD) — resolved by the scope decision ... not by
verification."* This Validator's own decision, stated plainly: **future-period confirmed demand =
MPS only; Cube_Backlog is used only for overdue (Period-1) rows.** 49 future-dated `Cube_Backlog`
rows exist for the 3 focus items and are deliberately excluded from Periods 2–4 on this basis — an
**assumption**, not a proven de-duplication.

**Raw statistical forecast — method**: Top-down combination forecast, computed independently:
Type-level `combination_forecast` (Naive/MA3/MA6/MA12/Croston/SBA equal-weight mean, from
`src/models.py`, reused verbatim), fit on the Type's aggregated actual monthly qty (summed over
the 112 non-excluded/non-placeholder items in that Type only — placeholders are excluded from Type
totals per `config['phase_e1_assumptions']`'s "Placeholder items sit outside the Top-down
hierarchy entirely" decision) through the last complete month (2026-08), forecast horizon = 4
months. Allocated to the item by **its own share of the Type's total qty over that same training
window** (train-data-only share, the leakage-free pattern `item_level_reconciliation.py` /
`transferability_all_divisions.py` use).

| Item | Period | Month | Confirmed qty | Raw forecast | % of forecast consumed |
|---|---|---|---|---|---|
| `EEE-F-FC-1040010002` | 1 | 2026-09 | 2,095.0 | 2,533.09 | 82.7% |
| `EEE-F-FC-1040010002` | 2 | 2026-10 | 370.0 | 2,533.09 | 14.6% |
| `EEE-F-FC-1040010002` | 3 | 2026-11 | 0.0 | 2,533.09 | 0.0% |
| `EEE-F-FC-1040010002` | 4 | 2026-12 | 0.0 | 2,533.09 | 0.0% |
| `HS-F-99-02110` | 1 | 2026-09 | 578.0 | 356.40 | 162.2% |
| `HS-F-99-02110` | 2 | 2026-10 | 100.0 | 356.40 | 28.1% |
| `HS-F-99-02110` | 3 | 2026-11 | 0.0 | 356.40 | 0.0% |
| `HS-F-99-02110` | 4 | 2026-12 | 0.0 | 356.40 | 0.0% |
| `HS-F-99-0213` | 1 | 2026-09 | 398.0 | 260.29 | 152.9% |
| `HS-F-99-0213` | 2 | 2026-10 | 100.0 | 260.29 | 38.4% |
| `HS-F-99-0213` | 3 | 2026-11 | 0.0 | 260.29 | 0.0% |
| `HS-F-99-0213` | 4 | 2026-12 | 0.0 | 260.29 | 0.0% |

**Totals across the whole 4-month horizon**:

| Item | Confirmed qty (total) | Raw forecast (total) | % of forecast consumed |
|---|---|---|---|
| `EEE-F-FC-1040010002` | 2,465.0 | 10,132.34 | 24.3% |
| `HS-F-99-02110` | 678.0 | 1,425.61 | 47.6% |
| `HS-F-99-0213` | 498.0 | 1,041.17 | 47.8% |
| **Grand total (3 items)** | **3,641.0** | **12,599.1** | **28.9%** |

**Category: VERIFIED for the confirmed-qty figures** (direct query + direct classification into
periods, no modelling); **hypothesis/assumption for the "raw forecast" figures** (depends on the
Top-down combination method, itself the project's locked but non-uniquely-optimal choice — Phase
B3 found no approach beats another with statistical significance); **assumption, explicitly
flagged, for which side of the double-counting question was resolved** (backlog scope decision
above). No confirmed demand at all appears beyond Period 2 for any of the 3 items — consistent
with (not independent proof of) the project's own 6-day median order-notice finding: most
already-placed orders simply do not exist yet that far out.

Full detail: `output/summary/phaseE1_validator_fig2_consumption.csv`.

---

## ADDENDUM 2 (2026-09-18, Orchestrator-directed targeted re-check) — Figures 3 & 4 re-run on the FROZEN series

**What triggered this addendum**: after Addendum 1 above confirmed Figures 1/2's discrepancy
against the Modeler's numbers was caused entirely by the live-vs-frozen input window, the
Orchestrator noted Figures 3 and 4 rest on the SAME live pull (32 months through 2026-08, for all
112 items, not just the 3 focus items) and could not yet be validly compared against the
Modeler's numbers (THB 55,399,687 stock value; 98.99% fill rate) because two things were
confounded at once: the input-window bug, and this Validator's own independent segmentation
methodology (the 68-item FG-stock-supported set). Per the Orchestrator's explicit instruction,
this addendum eliminates ONLY the input-window confound — the demand classification (ADI/CV²),
annual value, order frequency, the empirical protection-period distributions feeding Min/Max, and
the simulation replay window are all re-run on the frozen file
(`output/data/processed_full_category_sales_monthly_forecastDate.csv`, snapshot_pull_date
2026-09-04 16:44:45, 31 months 2024-01 to 2026-07). **Unchanged, per the Orchestrator's
instruction**: `confirmed_known_demand` was never part of Figures 3/4 (Figure 2 only); unit cost
stays a LIVE query (`cube_Sale_APD` cost/qty), exactly as in the original report; and this
Validator's own segmentation judgment call (ADI/CV² classes, the "both low-value AND
low-frequency" median-split exclusion rule) is kept EXACTLY as originally designed — only the
input data window changes. New script:
`src/investigations/phaseE1_validator_frozen_recheck_fig34.py` (imports this Validator's own
already-written functions from `phaseE1_validator.py`; no `phaseE1_*` Modeler file was read). New
CSVs: `output/summary/phaseE1_validator_fig{3,4}_*_FROZEN.csv`.

**Simulation replay window**: capped at the frozen series' own last month, 2026-07 (31 months,
2024-01 to 2026-07) — **not extended** with any live/partial tail, so the whole re-check stays
internally consistent with one snapshot's own natural boundary, exactly as Figures 1/2's Addendum
did.

**Result — Figure 3, frozen-series segmentation and stock value**:

| Metric | FROZEN (corrected) | Original (live-pull) | Modeler's number (per Orchestrator) |
|---|---|---|---|
| Median annual value (112-item set) | ฿202,311.23 | ฿236,310.53 | — |
| Median order frequency (112-item set) | 0.774 | 0.781 | — |
| FG-stock-supported item count | **68 of 112** | 68 of 112 | (not yet compared — Orchestrator handling separately) |
| Total scenario stock value (PRIMARY, Σ Max×unit_cost) | **THB 93,935,502.88** | THB 95,834,332.32 | THB 55,399,687 |
| Total scenario stock value (SECONDARY, current sellable on-hand) | THB 11,308,206.80 | THB 11,541,666.37 | — |

**The item COUNT did not change at all (68 of 112 in both versions)** — the frozen series shifted
the median annual value down modestly (฿236,311 → ฿202,311, a ~14% drop, consistent with one fewer
month of generally-growing demand) and the median order frequency barely at all (0.781 → 0.774),
but not by enough to move any item across the median-split boundary in either direction on this
run. The total stock value moved only modestly (**THB 95.8M → THB 93.9M, a 2.0% decrease**) —
nowhere near enough to close the gap against the Modeler's THB 55.4M figure.

**Conclusion (important, and the actual point of this addendum): the live-vs-frozen input-window
bug explains at most ~2% of the gap between this Validator's stock-value figure and the
Modeler's.** The great majority of the ~70% gap (THB 93.9M vs. THB 55.4M) must be attributable to
something else — almost certainly the segmentation methodology (which 68 items are "FG-stock-
supported," or a differently-sized set entirely, is a judgment call this Validator made
independently and the Modeler may have made differently), not to which historical window fed the
demand figures. This report does **not** attempt to resolve that segmentation gap itself — per the
Orchestrator's own framing, that comparison is being handled separately.

**Category: VERIFIED given the stated FG-set and config conventions (frozen-series figure is now
the CORRECTED, primary answer for the stock-value computation ITSELF, superseding the original
live-pull figure) — but the underlying FG-set selection remains a HYPOTHESIS/independent
methodology choice, unresolved by this addendum, and evidently the dominant source of the
remaining gap against the Modeler's number.**

**Result — Figure 4, frozen-series fill-rate simulation**:

| Metric | FROZEN (corrected) | Original (live-pull) | Modeler's number (per Orchestrator) |
|---|---|---|---|
| Replay window | 2024-01 to 2026-07 (31 months) | 2024-01 to 2026-08 (32 months) | — |
| Items simulated | 68 | 68 | — |
| Aggregate unit fill rate | **99.91%** | 99.81% | 98.99% |
| Stockout item-months | 9 of 2,108 | 12 of 2,176 | — |

**The fill rate moved in the OPPOSITE direction from what would close the gap** — dropping one
partial/live month (2026-08) actually pushed the simulated fill rate slightly HIGHER (99.81% →
99.91%), not lower toward the Modeler's 98.99%. This confirms the same conclusion as Figure 3: the
live-vs-frozen input-window bug is not the source of the remaining gap against the Modeler's fill
rate — it moves the number by about 0.1 percentage point, in the wrong direction to explain a
~1 percentage-point gap. The 68-item FG-set (or whatever set the Modeler simulated) is the more
likely source of the remaining difference, again outside this addendum's scope to resolve.

**Category: SIMULATED, scenario output, conditional on this Validator's own stated assumptions —
unchanged from the original report's caveats; only the input window and its modest consequence
are new here.**

---

## Figure 3 — Total scenario stock value at the default scenario (ORIGINAL, live-pull version — superseded by Addendum 2 above for the primary answer; kept for the discrepancy trace)

### Step A — Independently determining the FG-stock-policy-supported set (of the 112)

**Method** (independent methodology choice, stated and justified, not looked up anywhere):
1. Classify each of the 112 items by ADI (average inter-demand interval) / CV² (squared
   coefficient of variation of non-zero demand sizes) using the standard Syntetos-Boylan-Croston
   (2005) thresholds (ADI/CV² < 1.32/0.49 boundaries) → Smooth / Erratic / Intermittent / Lumpy /
   `insufficient_nonzero_periods` (fewer than 2 non-zero months in the 32-month history).
   Result: Smooth 37, Erratic 28, Lumpy 25, Intermittent 14, insufficient 8.
2. Compute **annual value** = mean monthly qty × 12 × unit cost (unit cost per Step B below).
3. Compute **order frequency** = fraction of the 32 months with non-zero demand.
4. **Threshold used (median split, stated and justified)**: an item is **excluded** from the
   FG-stock-supported set **only if it is BOTH low-value (annual value < the 112-item median,
   ฿236,310.53) AND low-frequency (order frequency < the 112-item median, 0.781)** — i.e. only the
   bottom-value/bottom-frequency quadrant is excluded. **Justification**: the confirmed procurement
   lead time (45–60 days, business-confirmed) so greatly exceeds the confirmed median customer
   order notice (6 days, STATUS.md Business Findings) that finished-goods stock is needed to meet
   realistic delivery expectations for essentially every item that sells often enough or is worth
   enough to matter — a "make-to-order-only" policy is only defensible for items that are both cheap
   and infrequently ordered, where the capital/effort of holding safety stock is least justified. A
   plain single-variable median split (value alone, or frequency alone) was rejected because it
   would exclude roughly half of all 112 items regardless of the other variable — e.g. a genuinely
   high-value item ordered only occasionally would be wrongly excluded by a frequency-only split.
5. Cross-check: the resulting FG-supported set (68 items) is 34/25/8/1 Smooth/Erratic/Lumpy/
   Intermittent — overwhelmingly Smooth/Erratic, as expected; the excluded set (44 items) has a
   median annual value of ฿10,910 and median order frequency 0.17, an order of magnitude below the
   included set's median (฿668,189 / 1.00) — the split behaves as intended, not as an arbitrary cut.

**Result: 68 of 112 items are FG-stock-policy-supported.** Full list with class/value/frequency:
`output/summary/phaseE1_validator_fig3_fg_classification.csv`.
**Category: HYPOTHESIS / independent methodology choice** — the classification itself (ADI/CV²)
is a direct, verified recomputation from data; the median-split threshold and the "both low-value
AND low-frequency" combination rule are this Validator's own stated judgment call, not a business-
confirmed or previously-adopted rule.

### Step B — Min/Max and unit cost for the 68-item set

**Min**: same empirical percentile method as Figure 1, per item, using each item's own 32-month
actual history and the same 4-month protection period / 95th percentile. **Max = Min + replenishment
quantity**, where replenishment quantity = "the review interval's own expected demand"
(`config['phase_e1_assumptions']['replenishment_qty_convention']`) = mean monthly qty ×
(30 days / 30.44) ≈ mean monthly qty × 0.9855.

**Unit cost**: reuses `src/investigations/phaseD_check2_stock_value.py`'s exact methodology —
`unit_cost = cost / qty` per `cube_Sale_APD` row (`cost` is a LINE TOTAL, not a unit cost, per that
script's own verified finding, re-used here rather than re-derived); primary basis = median
`unit_cost` over the trailing 12 months, anchored to the global max `createDate` across the pulled
rows for these 68 items; falls back to the most-recent-transaction `unit_cost` when no row exists
in that window. **All 68 of 68 FG-supported items have a usable cost basis** (query:
`SELECT itemcode, qty, cost, createDate FROM cube_Sale_APD WHERE itemcode IN (<68 codes>)`).

**Scenario stock value — PRIMARY interpretation**: Σ (Max_qty × unit_cost) over the 68 items —
"capital tied up under this policy," the standard reading of "value of holding stock at the
scenario's Max level."

**= THB 95,834,332.32** (68 of 68 items priced).

**Scenario stock value — SECONDARY interpretation** (explicitly NOT primary, computed only
because the task allows/invites a second interpretation if one is believed more defensible; this
Validator does **not** consider it more defensible, but reports it for comparison): value of the
same 68 items' **current** sellable on-hand stock (warehouses FG01/FG21/WH21 only, per
`config['phase_e1_assumptions']['sellable_warehouse_codes']`), from `Cube_Inventory_Exact`
directly, at the same unit costs.

**= THB 11,541,666.37.**

The roughly 8.3× gap between the two figures is expected and informative, not a discrepancy to
resolve: the Max-level figure is a **forward-looking capital target** under a 95th-percentile
safety-stock policy across a 4-month protection period, while the on-hand figure is a **point-in-
time snapshot** of what is actually sitting in the 3 sellable warehouse codes today — the two are
not meant to be close, and their gap is itself a plausible read on how under-stocked these items
currently are relative to the scenario's own target (consistent with, though not proof of, the
project's separate finding that 92 of 445 codes show negative Available).

**Category: VERIFIED computation** given the stated FG-set (Step A) and the stated Max/unit-cost
conventions (both taken directly from `config['phase_e1_assumptions']`, not invented here).

Full detail: `output/summary/phaseE1_validator_fig3_minmax.csv`,
`output/summary/phaseE1_validator_fig3_fg_classification.csv`.

---

## Figure 4 — Fill rate at the default scenario (ORIGINAL, live-pull version — superseded by Addendum 2 above for the primary answer; kept for the discrepancy trace)

**Method**: lightweight historical simulation, 2024-01 through 2026-08 (32 months — the same
"through the present" window as every other figure in this report; 2026-09 was excluded above as
an in-progress partial month, so it is excluded here too for the same reason), per item in the
68-item FG-supported set, under an order-up-to-Max (base-stock) periodic-review policy:

- **Initial stock** (own stated assumption, per `config['phase_e1_assumptions']
  ['simulation_initial_stock_assumption']`): each item starts 2024-01 with on-hand stock equal to
  its own scenario Max (computed in Figure 3).
- **Receipt timing** (own stated assumption, per `config['phase_e1_assumptions']
  ['simulation_receipt_timing_assumption']`): deterministic, `lead_months =
  ceil((60 + 3) / 30.44) = 3` months after an order is placed — lead time + assembly time only
  (the review interval is the reorder cadence, not part of the pipeline delay).
- **Fulfilment sequence** (own stated assumption, per `config['phase_e1_assumptions']
  ['simulation_fulfilment_sequence_assumption']`): within each simulated month, any scheduled
  receipt is added to on-hand FIRST; any carried-forward backorder is paid off first from
  available stock; then that month's own historical demand is served; any shortfall is
  BACKORDERED (carried into next month's demand, never treated as a lost sale).
- **Reorder rule** (this Validator's own stated choice, not itself named in config, needed to make
  the base-stock policy concrete under a monthly review cadence ≈ the 30-day review interval):
  each month, place an order of `max(0, Max − (on_hand + outstanding pipeline orders))` — a
  standard base-stock/order-up-to-S policy with pipeline tracking, so multiple outstanding orders
  (since `lead_months=3` exceeds the ~1-month review interval) are never double-ordered against.
- **Unit fill rate metric** (this Validator's own stated definition, since the task specifies the
  concept — "% of demand quantity fulfilled without stockout" — but not its exact formula): for
  each item-month, the shortfall = `max(0, that month's own historical demand − available stock
  after paying off any carried backorder)` counts against fill rate, even if the shortfall is
  later paid off via backorder catch-up in a subsequent month. `fill_rate = 1 − (Σ shortfall) /
  (Σ historical demand)`. A "stockout month" = any item-month with shortfall > 0.

**Result**: pooled across all 68 items × 32 months (2,176 item-months):

- **Unit fill rate: 99.81%**
- **Stockout count: 12 of 2,176 item-months (8 of 68 items ever stock out)**

The two most notable stockout items are, notably, **two of the three Figure-1 focus items**:
`HS-F-99-0213` (69.3% own-item fill rate, 2 stockout months) and `HS-F-99-02110` (52.8% own-item
fill rate, 2 stockout months) — both far below the 99.81% pooled average, i.e. the aggregate figure
is dominated by a majority of well-behaved items and masks these two. `EEE-F-FC-1040010002` itself
fares much better (98.3% fill rate, 1 stockout month) despite being the largest-volume item.

**Category: SIMULATED, scenario output, conditional on this Validator's own stated initial-
stock/receipt-timing/fulfilment-sequence/reorder-rule assumptions** — explicitly not a
computational fact. A different, equally reasonable set of choices (e.g. a different reorder
trigger, a different treatment of the review interval) would very plausibly produce a different
fill rate. The very high pooled figure (99.81%) is itself an expected consequence of starting
every item already stocked at its own Max under a 95th-percentile safety-stock policy — it should
not be read as evidence the *current, real* inventory position performs this well (see Figure 3's
secondary/primary stock-value gap above, which shows current on-hand is far below scenario Max for
this set).

Full detail: `output/summary/phaseE1_validator_fig4_simulation.csv`.

---

## What could not be determined

- Whether a genuinely different, unrecorded "true" future demand exists beyond what MPS/backlog
  currently record for Periods 3–4 of Figure 2 — cannot be determined from data (orders that will
  be placed between now and those months, by definition, do not exist in the system yet).
- Whether Cube_Backlog and cube_Sale_APD MPS rows for the SAME physical order could still overlap
  in some way this Validator's scope decision does not catch — cannot be determined from data (no
  shared key exists, as the project has established repeatedly; see `backlog_vs_mps_double_count_
  note`).
- Whether the FG-stock-supported/excluded split (Figure 3, Step A) matches any business intent —
  this Validator's median-split threshold is an independent methodology choice, not validated
  against any business input; a different, equally reasonable threshold would move items across
  the boundary.

---

## Summary table

**Figures 1 and 2 below show the CORRECTED (frozen-series) value as primary, per the 2026-09-18
Orchestrator-directed targeted re-check (see Addendum above); the original live-pull value is
shown alongside for traceability, not as an alternative answer.**

| Figure | Validator's value (CORRECTED, frozen series) | Original live-pull value | Method / citation | Category |
|---|---|---|---|---|
| Min — `EEE-F-FC-1040010002` | **10,788.20** | 10,865.80 | Empirical 4-month rolling-sum distribution of actual (Actual+MPS) history, forecast_date-keyed; p95; frozen file `processed_full_category_sales_monthly_forecastDate.csv`, snapshot_pull_date 2026-09-04, 31 months (2024-01 to 2026-07) | Verified |
| Min — `HS-F-99-02110` | **917.50** | 2,170.80 | Same method | Verified — matches the Modeler's independently-obtained value exactly |
| Min — `HS-F-99-0213` | **763.75** | 1,221.80 | Same method | Verified — matches the Modeler's independently-obtained value exactly |
| Consumption — confirmed qty, 3 focus items, 4-month horizon (2026-08 to 2026-11, frozen-series boundary) | **3,641.0 units** (38.2% / 90.9% / 74.3% of each item's own forecast total; 46.2% pooled) | 3,641.0 units (same — confirmed qty is queried live in both versions), 28.9% pooled (different denominator only) | `cube_Sale_APD` MPS rows by forecast_date month + overdue `Cube_Backlog` rows (Period 1 only, split on the frozen snapshot_pull_date); scope decision on double-counting stated explicitly | Verified (confirmed qty) / Assumption (backlog scope decision) |
| Consumption — raw statistical forecast total, 3 focus items | **7,875.4 units** | 12,599.1 units | Top-down combination forecast (`src/models.py combination_forecast`, Type-level, train-only share allocation), fit on the frozen 31-month series through 2026-07 | Hypothesis (locked but not uniquely-optimal method) |
| FG-stock-policy-supported set | **68 of 112 items** (unchanged) | 68 of 112 items | ADI/CV² classification + median split on annual value AND order frequency (both-low exclusion rule); re-run on the frozen series (Addendum 2) — same result | Hypothesis / independent methodology choice |
| Total scenario stock value (PRIMARY) | **THB 93,935,502.88** | THB 95,834,332.32 | Σ(Max_qty × unit_cost) over the 68-item set; Max=Min+replenishment qty; unit cost = median-last-12mo cost/qty with most-recent fallback (Phase D Check 2 methodology reused, LIVE query, unchanged); demand inputs from the frozen 31-month series (Addendum 2) | Verified (given the stated FG-set and config conventions) |
| Total scenario stock value (SECONDARY, current on-hand) | **THB 11,308,206.80** | THB 11,541,666.37 | Σ(sellable on-hand qty in FG01/FG21/WH21 × unit_cost) over the same 68 items (LIVE query, unchanged) | Verified, alternate interpretation, not primary |
| Fill rate (default scenario, 68-item FG-set) | **99.91%**, 9 of 2,108 item-months stocked out — replay window 2024-01 to 2026-07 (31 months, frozen-series boundary) | 99.81%, 12 of 2,176 item-months (8 of 68 items) — replay window 2024-01 to 2026-08 (32 months) | Order-up-to-Max simulation, own stated initial-stock/receipt-timing/fulfilment/reorder assumptions | Simulated, scenario output, not a fact |

**Note on the Modeler comparison for stock value / fill rate** (per the Orchestrator's 2026-09-18
follow-up): the Modeler's own numbers are THB 55,399,687 and 98.99%. Addendum 2 shows the
live-vs-frozen input-window bug explains only a small fraction of these gaps (stock value moved
~2% toward the Modeler's number, ~THB 1.9M of the ~THB 38.5M gap; fill rate moved 0.1 point in the
WRONG direction). **The great majority of both gaps is therefore attributable to something other
than the input window — most likely this Validator's independently-derived 68-item FG-stock-
supported segmentation differing from whatever set the Modeler used** — a question this report
does not resolve, per the Orchestrator's own framing that the segmentation comparison is being
handled separately.

**Scripts**: `src/investigations/phaseE1_validator.py`,
`src/investigations/phaseE1_validator_frozen_recheck.py` (Addendum 1: Figures 1/2),
`src/investigations/phaseE1_validator_frozen_recheck_fig34.py` (Addendum 2: Figures 3/4).
**Raw CSVs (original, live-pull)**: `output/summary/phaseE1_validator_fig1_min.csv`,
`phaseE1_validator_fig2_consumption.csv`, `phaseE1_validator_fig3_fg_classification.csv`,
`phaseE1_validator_fig3_minmax.csv`, `phaseE1_validator_fig4_simulation.csv`.
**Raw CSVs (frozen-series, corrected/primary)**: `output/summary/phaseE1_validator_fig1_min_FROZEN.csv`,
`phaseE1_validator_fig2_consumption_FROZEN.csv`, `phaseE1_validator_fig3_fg_classification_FROZEN.csv`,
`phaseE1_validator_fig3_minmax_FROZEN.csv`, `phaseE1_validator_fig4_simulation_FROZEN.csv`.

No file was modified: `config.yaml`, `STATUS.md`, and every pre-existing pipeline script were
read-only inputs. Nothing was committed or pushed.
