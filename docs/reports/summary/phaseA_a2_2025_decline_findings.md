# Phase A2 — Why did 2025 sales fall (the "26% fall"), Analyst findings

**Role**: Analyst (per `AGENTS.md`) — patterns/statistics from data the Explorer/Validator already
surfaced, plus one fresh whole-population pull where the reused files did not cover it (noted
below). No forecasting model selected, no Max-Min calculated, `config/config.yaml` untouched.

**Scope reused from STATUS.md** (cited, not re-derived): 128-item Fuse/Surge-Arrester category
scope (`output/summary/part1_category_scope_all_codes.csv`); the Jan-Jul same-window comparison
(`part4_jan_jul_driver_breakdown.csv`, `part4_item_level_jan_jul.csv`,
`part4_yearly_driver_breakdown.csv`, `part4_excl_flagged_comparison.csv`); the 2022/2023-break
investigation methodology (STATUS.md, "Root cause of the 2022/2023 break"). Project filters:
`division='PEM101'`, `revenue_type='Omni Channel'`, `status IN ('Actual','MPS')`,
`createDate>=2024-01-01`. Jan-Jul window used throughout for year-on-year comparability, since
2026 data is partial (through 2026-08-28).

**New work this task**: script `src/investigate_2025_decline.py` (all fresh queries below), using
`src/db.py`'s `run_query`. All fresh pulls are **whole-PEM101/Omni-Channel population** (not
restricted to the 128-item scope), matching STATUS.md's existing `part4_item_level_jan_jul.csv`
scope (which already covers ~306 items, confirmed below) and the instruction to test the whole
population, not just the 128 items, for the artifact hypothesis. Outputs listed per task below,
all under `output/summary/phaseA_a2_*.csv` or `output/data/phaseA_a2_*.csv`.

**Cross-validation (done first, per CONVENTIONS "every number must be verifiable")**: the fresh
item-level pull (`phaseA_a2_raw_item_year_qty_sale.csv`) was joined against the existing
`part4_item_level_jan_jul.csv` — **0 of 306 items mismatch by more than ฿1** on 2024/2025/2026 sale
value (`phaseA_a2_item_level_crossvalidation.csv`). The fresh pull is confirmed consistent with
the prior session's work before building anything on top of it.

---

## 1. Decomposition of the 2024→2025 decline (and 2025→2026 recovery)

**Headline numbers reused from STATUS.md, Jan-Jul window**: 2024 = ฿252.20M, 2025 = ฿187.44M
(**-฿64.77M, -25.7%**), 2026 = ฿248.93M (**+฿61.50M, +32.8%** vs 2025). All three years reconciled
exactly against the fresh pull (see cross-validation above).

### By month — the decline is NOT a full-year 2025 phenomenon (new finding, high confidence)

`output/summary/phaseA_a2_monthly_whole_population.csv` (whole population, monthly, 2024-01
through 2026-09-partial).

- **Full calendar year 2025 vs 2024 is only -7.2%** (฿351.22M vs ฿378.57M, from the existing
  `part4_yearly_driver_breakdown.csv`), not -25.7%. The 25.7% figure is specific to the Jan-Jul
  window.
- Splitting the year: **Jan-Jul 2025 was down** (as above), but **Aug-Dec 2025 (฿163.78M) actually
  exceeded Aug-Dec 2024 (฿126.36M) by +29.6%** (computed from the monthly file). The dip is
  concentrated in the first ~7 months of 2025 and had already reversed by the second half of 2025,
  before 2026 began. Framing "2025 was a depressed year that 2026 recovered from" is therefore only
  half right — H2 2025 was already elevated versus H2 2024.
- **Confidence: high** (directly computed from monthly aggregates, reconciles to the existing
  yearly/Jan-Jul totals).

### By product Type / item — heavily concentrated, not broad-based (high confidence)

`output/summary/phaseA_a2_category_type_mix_jan_jul.csv`,
`phaseA_a2_item_level_jan_jul_with_deltas.csv` (adds the missing `delta_2025_vs_2024` column to
the existing item-level file, cross-validated),
`phaseA_a2_item_level_price_volume_decomposition.csv`.

- One product Type — **"High voltage distribution Fuse cutouts"** — moved ฿78.88M (2024) →
  ฿37.64M (2025) → ฿74.33M (2026). Its 2024→2025 drop alone (**-฿41.24M**) is **63.7% of the entire
  -฿64.77M whole-population decline**, and it round-trips back to near its 2024 level by 2026 —
  the same shape as the aggregate.
- Within that Type, one item — **`EEE-F-FC-1040010002`, one of the three focus codes** — drives
  most of it: sale ฿34.76M (2024) → ฿1.77M (2025) → ฿30.38M (2026); qty 18,846 → 958 → 16,328
  units. **This single item is -฿32.99M of the -฿64.77M total decline (51%)**, and (per STATUS.md,
  already established) the *same* item is separately ฿28.6M of the ฿61.5M 2025→2026 recovery
  (46.5%) — it is the dominant swing factor in **both** directions.
- Per-unit price for this item is essentially flat across the dip (฿1,844.40 → ฿1,843.32, -0.06%)
  — **this is a pure volume/demand collapse-and-recovery, not a price change.**
- A second item in the same Type, `EEE-F-FC-1040010100N`, shows the identical shape at smaller
  scale: ฿13.28M → ฿1.35M → ฿9.77M, price flat (฿2,884 → ฿2,800).
- Splitting all 306 items into cohorts: **139 "continuing" items** (sold in both Jan-Jul 2024 and
  2025) net -฿55.08M; **71 items that sold in 2024 but not 2025** ("dropped out") account for
  -฿28.25M; **67 items new to 2025** partially offset with +฿18.57M. Net: -฿64.77M (exact).
- **Confidence: high** — directly computed and internally reconciled (cohort sums equal the
  reused total to the cent).

### Price/volume/mix decomposition — the price collapse is a MIX effect, not a real price cut (new finding, high confidence)

The Jan-Jul driver file already on record shows `avg_price_per_unit` falling ฿397.996 (2024) →
฿251.148 (2025), -36.9%, while `total_qty` rose 17.8%. This task decomposes that using two
independent methods that agree:

1. **Item-level Laspeyres decomposition** (`phaseA_a2_item_level_price_volume_decomposition.csv`,
   `phaseA_a2_price_volume_decomposition_totals.csv`): for the 139 items present in both years,
   `volume_effect = price_2024 × (qty_2025 − qty_2024)` and `price_effect = qty_2025 × (price_2025
   − price_2024)` sum exactly to their -฿55.08M delta. Result: **volume_effect = -฿56.64M,
   price_effect = +฿1.55M** — i.e. for items that sold in both years, per-unit prices were flat to
   very slightly *higher* on average (quantity-weighted), not lower. The apparent price collapse
   is not coming from existing items being sold cheaper.
2. **Category/Type-level mix check** (`phaseA_a2_category_type_mix_jan_jul.csv`): the Types with
   the largest qty *growth* 2024→2025 are all low-unit-price Types with flat own-price — "High
   voltage distribution Fuse links" (+91,498 units, ฿44.45→฿44.82/unit, essentially flat), "Low
   tension H.R.C. Fuses" (+26,204 units, ฿90.51→฿90.21/unit, flat), "Low Voltage Surge Arrester"
   (+10,901 units, flat) — while the high-price "High voltage distribution Fuse cutouts" Type lost
   ~19,519 units at a roughly stable own-price (~฿2,040→฿1,966/unit, -3.6%).
- **Conclusion: the 36.9% avg-price-per-unit collapse is a composition/mix shift** — more volume
  moving through low-price product lines while a high-price line (Fuse Cutouts, dominated by the
  focus item above) lost volume — **not a real per-item price cut, discount, or a change in how
  `sale`/`qty` are recorded.** Both methods agree independently.
- **Confidence: high.**

### By order count / order size — reused, not recomputed

Already on record in `part4_jan_jul_driver_breakdown.csv`, consistent with the above: n_orders
2024=2,383 → 2025=2,309 (-3.1%), avg_order_value ฿105,834 → ฿81,176 (-23.3%), avg_orders_per_customer
7.03 → 6.45. The order-count drop is modest; the value decline is driven far more by smaller
average order value (consistent with the mix-shift finding above) than by fewer orders.

---

## 2. Which customers stopped buying — broad churn vs. concentrated, and who returned in 2026

`output/data/phaseA_a2_raw_customer_year_sale.csv` (fresh pull, customer × year, Jan-Jul, whole
population), classified in `output/summary/phaseA_a2_customer_classification_jan_jul.csv` /
`_summary.csv`. **Cross-validated**: cohort customer counts sum to the reused `n_customers` figures
exactly (339 in 2024, 358 in 2025; 2026 is 348 vs. the reused 349 — a 1-customer rounding
difference from one customer with a small net-negative 2026 value, immaterial).

| Classification | n customers | 2024 sale | 2025 sale | 2026 sale (Jan-Jul) |
|---|---|---|---|---|
| dropped_after_2024_not_returned | 127 | ฿46.24M | 0 | 0 |
| dipped_out_2025_returned_2026 | 22 | ฿9.60M | 0 | ฿1.29M |
| continuing_all_3_years | 145 | ฿176.92M | ฿150.45M | ฿200.05M |
| active_2024_2025_not_yet_seen_2026 | 45 | ฿19.45M | ฿7.71M | -฿0.80M |
| new_in_2025_continuing | 63 | 0 | ฿19.90M | ฿31.01M |
| new_in_2025_only | 105 | 0 | ฿9.37M | 0 |
| new_in_2026_only | 118 | 0 | 0 | ฿17.39M |

- **127 customers who bought in Jan-Jul 2024 show zero Jan-Jul activity in *both* 2025 and 2026** —
  ฿46.24M gross, 71% of the gross 2024→2025 decline before new-customer additions offset it. One
  customer, **`CS07977`, alone accounts for -฿15.27M (23.6% of the whole net -฿64.77M decline)**
  spread across 17 orders and ≥6 different item codes in H1 2024 — not a single one-off
  transaction.
- **22 customers dipped out entirely in Jan-Jul 2025 and partially returned in Jan-Jul 2026**
  (฿9.60M → 0 → ฿1.29M) — they did come back, but at only ~13% of their prior Jan-Jul level so far
  (2026 is the same Jan-Jul window, so this is a fair comparison, not a partial-year artifact). A
  customer that dips exactly one year and returns at reduced scale is a real, distinct pattern from
  the 127 that show no return signal at all.
- **Confidence: high** for the classification itself (directly computed, cross-validated counts).
  **Moderate** for calling the 127 "genuinely lost" as a group — see the reclassification test in
  Section 3, which shows a meaningful fraction of this group is not actually gone from the
  business, just reclassified.

---

## 3. Recording-artifact test (2022/2023-break method applied to 2024→2025)

Per STATUS.md's 2022/2023-break finding (a >6x Dec→Jan jump traced to `RevenueType` going from
NULL to populated for pre-existing PEM101 business — a classification change, not organic growth),
the same three tests are applied here.

### Test A — does the whole PEM101/Omni-Channel population show a cliff, or a ramp? (high confidence: NO cliff)

`phaseA_a2_monthly_whole_population.csv`: Dec 2024 → Jan 2025 = ฿21.21M → ฿19.88M (-6.3% sale,
-3.5% qty, -9.7% orders, -8.5% customers). This is a **gradual, single-digit-percent month-to-month
move**, categorically different from the 2022/2023 break's >6x jump or the 2023/2024 break's >100x
jump, both of which had zero ramp. **There is no step-change signature at the 2024/2025 boundary.**
This is strong evidence against a single database-wide reclassification/system event dated to that
boundary, the way the 2022/2023 and 2023/2024 breaks were.

### Test B — did classification fields shift? (high confidence: no aggregate shift found)

- **`revenue_type` composition within `division='PEM101'`** (not filtered to Omni Channel),
  Jan-Jul by year (`phaseA_a2_revenue_type_composition_pem101.csv`): Omni Channel's *share* of the
  division actually **rose** (78.8% → 82.5% → 84.4%), while Tendering's *share* **fell** (21.2% →
  17.5% → 15.6%) and Tendering's *absolute* Jan-Jul value also fell (฿67.9M → ฿39.6M). If the
  aggregate decline were explained by transactions being relabelled out of Omni Channel into
  Tendering, Tendering's value should have risen as Omni Channel's fell — it did not. **The
  aggregate whole-division decline is not explained by an Omni↔Tendering relabelling.**
- **Whole-division check** (`phaseA_a2_division_wide_pem101_jan_jul.csv`, any revenue_type):
  ฿320.09M (2024) → ฿227.06M (2025), a **-29.1% decline** — slightly *larger* than the
  Omni-Channel-only -25.7%. **The decline hits the whole division, not just the Omni-Channel
  slice** — consistent with a real, broad effect rather than a channel-specific artifact.
- **`status` (Actual/MPS) composition** (`phaseA_a2_status_composition.csv`): MPS is negligible in
  both Jan-Jul 2024 (0 rows) and Jan-Jul 2025 (7 rows, ฿57,727) — no Actual↔MPS shift explains
  anything here. MPS becomes more material only in 2026 (105 rows, ฿20.37M, 1.6% of 2026 qty),
  unrelated to the 2024→2025 question.
- **Conclusion: no aggregate/whole-population classification artifact was found** analogous to the
  2022/2023 break. **Confidence: high** for the absence of a whole-population effect.

### Test C — individual customers: reclassified vs. genuinely gone (new finding, moderate-to-high confidence, a real but partial effect)

Even with no *aggregate* artifact, the 2022/2023-break method also asks whether customers who look
"gone" actually moved to a different classification. Tested directly for all 127
"dropped_after_2024_not_returned" customers by pulling their **entire table-wide activity (any
division, any revenue_type) for 2025-2026**
(`output/data/phaseA_a2_dropped_customers_elsewhere_activity.csv`,
`output/summary/phaseA_a2_dropped_customer_reclassification_test.csv`):

- **26 of 127 customers (20% by count) have real activity elsewhere in 2025/2026** — representing
  **฿27.05M of their combined ฿46.24M 2024 value (58.5% of the value)**. The larger "dropped"
  customers are disproportionately represented in this reclassified group.
- **The single largest example: `CS07977`** (-฿15.27M of the total decline, see Section 2). Its
  full company-wide record shows Omni-Channel activity in 4 divisions in 2024 (~฿132M combined) that
  becomes **zero** Omni-Channel activity anywhere in 2025, while its **Tendering**-classified
  activity (mostly `PEM103`, `PEM101`, `PEM107`) rises to **~฿263M** — the underlying business
  relationship *grew*, it was relabelled out of this project's Omni-Channel/PEM101 scope, not lost.
  A second case, `CS00477`, shows the identical pattern at smaller scale (฿26.1M Omni Channel 2024
  → ฿0 Omni Channel / ฿12.3M Tendering 2025).
- Of the 26 reclassified customers' elsewhere-activity, **฿85.79M sits specifically in `PEM101` +
  `Tendering`** (same division, different revenue_type — the exact mechanism the 2022/2023 break
  used, just in reverse direction), and the rest sits under other divisions (`PTS`, `PEM103`,
  `PEMCSA`, `PSP102`, ...) — but that "other division" total is dominated by a couple of large
  accounts (e.g. `CS01191`'s primary relationship is with `PEMCSA`, a different division entirely,
  where its business also grew 2024→2026; its small `PEM101` slice simply didn't recur — this
  looks like a one-off order that didn't repeat, not the same relabelling mechanism as `CS07977`).
- **The remaining 101 of 127 customers (80% by count, 41.5% of the ฿46.24M value, ฿19.19M) show
  zero activity anywhere in the table in 2025 or 2026** — spot-checked individually (`CS07521`,
  `CS05938`, `CS05574`, `CS04917`, `CS05050`, `CS01493`, `CS09067`, ...), each confirmed to have no
  rows at all post-2024, under any division/revenue_type/status. **This is consistent with genuine
  customer loss**, not relabelling, for this majority-by-count group.
- **Conclusion**: reclassification is real and quantified but **partial** — it explains a
  meaningful share of the *value* attributed to a small number of large "dropped" customers
  (~฿27M of ~฿46M in that cohort, ~42% of the total -฿64.77M headline decline if that whole cohort
  were excluded), but does **not** explain the item-level Fuse Cutout volume collapse (Section 1,
  which is a genuine quantity swing with flat prices, no classification change involved) nor the
  majority-by-count customer churn. **Confidence: moderate-to-high** — high confidence in each
  individual customer's traced pattern (direct query evidence), moderate confidence in
  generalizing "58.5% of dropped-customer value is reclassification" as a stable ratio, since it is
  driven by just 2-3 large accounts rather than a broad pattern across the 127.

### Overall answer to "is it a recording artifact" (moderate-to-high confidence)

**No** — not in the whole-population, single-boundary-cliff sense that explained the 2022/2023 and
2023/2024 breaks. There is no step-change, no aggregate revenue_type/status shift, and the
decline hits the whole division similarly. **But partially yes at the account level** for a
minority of large customers (quantified above) whose apparent loss is actually a relabelling to
`Tendering` or to a different division. The dominant driver of the headline number — the
item-specific `EEE-F-FC-1040010002` volume collapse-and-recovery (51% of the decline) — shows no
price change and was not traced to any classification shift; its cause (why ~36 customers paused
buying this specific item in H1 2025 and ~30 resumed in H1 2026) **could not be determined from
`cube_Sale_APD` alone** — there is no stock-level, supply, or pricing-negotiation table joined in
this investigation to test a stock-out or contract-renewal hypothesis.

---

## 4. The three focus items

| Item | Classification (STATUS.md) | Jan-Jul 2024 | Jan-Jul 2025 | Jan-Jul 2026 | Pattern |
|---|---|---|---|---|---|
| `EEE-F-FC-1040010002` | Erratic, ~60% of its Type's value | ฿34.76M (18,846 units) | ฿1.77M (958 units) | ฿30.38M (16,328 units) | **Follows and dominates the aggregate pattern** — pure volume collapse then recovery, flat unit price (~฿1,844 throughout), broad multi-customer effect (36 buyers in 2024 → 9 in 2025 → ~30, overlapping, in 2026) |
| `HS-F-99-02110` | Lumpy, mid-rank | ฿129,830 | ฿207,510 (+59.8%) | ฿2,913,650 | **Diverges** — grew through the 2025 dip, then surged in 2026 |
| `HS-F-99-0213` | Lumpy, mid-rank | ฿246,306 | ฿307,570 (+24.9%) | ฿1,444,775 | **Diverges** — also grew through the 2025 dip, then surged |

- `EEE-F-FC-1040010002` is not just "affected by" the 2025 dip — it is quantitatively the single
  largest driver of it (51% of the whole-population decline) and separately the largest driver of
  the 2025→2026 recovery (46.5%, per STATUS.md), making it the dominant swing item in both
  directions. **Confidence: high** (direct computation, cross-validated).
- Both Lumpy focus items (`HS-F-99-02110`, `HS-F-99-0213`) **did not dip in 2025 at all** — they
  grew modestly through the exact window when the aggregate fell 25.7%, then grew far more in
  2026. At their small scale (~฿0.1-0.3M vs. a ฿250M aggregate) this doesn't move the total, but it
  is a genuine, evidenced divergence from the broader pattern worth reporting as asked.
  **Confidence: high** (direct computation).

---

## 5. What the data could not resolve — stopping rule applied

- **Why `EEE-F-FC-1040010002`'s ~36-customer buyer base broadly paused ordering in H1 2025 and
  ~30 resumed in H1 2026** (the single largest driver of the whole "26% fall") — the price was
  flat throughout, ruling out a price/discount explanation, and no classification shift was found
  for this item. Checked: item-level price, qty, and buyer-count trajectories in `cube_Sale_APD`.
  **Not checked (outside what a read-only sales-table query can show)**: stock availability /
  stock-outs for this item in H1 2025, supplier lead-time or production issues, a contract
  renewal/renegotiation cycle, or a known project-based ordering pattern for this item's typical
  buyers. **What the business would need to supply**: whether this item had a known stock-out,
  price change, or supply disruption in H1 2025, or whether its buyer base is known to order in
  large infrequent batches tied to utility project cycles (which would make a 1-year pause
  unsurprising and unrelated to any data issue).
- **Whether the ~101 customers with zero activity anywhere post-2024 are genuinely lost accounts
  or simply have not re-ordered yet** — the data can only show absence, not intent. **What the
  business would need to supply**: account-status confirmation (closed, dormant, or still
  active-but-not-yet-reordered) for at least the largest few of these 101 (e.g. `CS07521`
  -฿5.88M, `CS01191`'s PEM101 slice -฿4.59M, `CS05938` -฿3.25M).
- **The specific mechanism behind `CS07977`'s and `CS00477`'s revenue_type relabelling** (why their
  business moved from Omni Channel to Tendering) — no audit trail exists in the database (confirmed
  by the same table-name search done for the 2022/2023 break, per STATUS.md Part 6), so this cannot
  be determined from data alone. **What the business would need to supply**: whether these two
  accounts' purchasing genuinely shifted to a tender/project basis, or whether this is a
  data-entry/classification convention change on the sales team's side.
- Per the stopping rule, these three points are not investigated further in this pass — they are
  reported as open items requiring business input, not left silently unresolved.

---

## 6. Confidence summary

| Finding | Confidence | Basis |
|---|---|---|
| Jan-Jul 2024→2025 decline is -25.7%, 2025→2026 recovery is +32.8% | High (reused) | STATUS.md, cross-validated exactly against fresh pull |
| Full-year 2025 vs 2024 is only -7.2%, not -25.7%; H2 2025 exceeded H2 2024 | High | New, directly computed from monthly whole-population pull |
| Decline is concentrated, not broad-based, at the item/Type level | High | 1 Type = 63.7%, 1 item = 51% of the decline; internally reconciled |
| Avg-price-per-unit collapse is a mix/composition effect, not a real price cut | High | Two independent decompositions (item-level Laspeyres, Type-level) agree |
| No whole-population step-change/cliff at the 2024/2025 boundary (unlike 2022/23, 2023/24 breaks) | High | Direct monthly comparison, gradual -6.3% Dec→Jan move |
| No aggregate revenue_type/status reclassification explains the whole-division decline | High | Omni Channel's share of PEM101 rose, not fell; Tendering fell too; whole division fell similarly (-29.1%) |
| A minority of "dropped" customers (by value, not count) are reclassified, not lost | Moderate-to-high | Directly traced for 26/127 customers; driven by 2-3 large accounts, not a broad pattern |
| 127 customers dropped after Jan-Jul 2024; 22 dipped and partially returned in 2026; 101 show no activity anywhere after 2024 | High | Direct classification, cross-validated customer counts |
| `EEE-F-FC-1040010002` is the dominant single driver of both the fall and the recovery | High | Direct computation, consistent with STATUS.md's independent recovery-side finding |
| The two Lumpy focus items (`HS-F-99-02110`, `HS-F-99-0213`) grew, not fell, through the 2025 dip | High | Direct computation |
| Root cause of why this one item's buyer base paused in H1 2025 | **Unresolved** | No supply/stock/contract data available to this investigation — flagged for business input |
