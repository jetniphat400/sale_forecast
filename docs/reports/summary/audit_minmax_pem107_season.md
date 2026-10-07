# Audit -- Max-Min as used today, PEM107's 66 items, seasonality of the pilot scope (2026-10-02)

Read-only audit. Nothing in code, config, data, pages or any model was changed. One read-only database session (SELECT and metadata only), 2026-10-02 15:50:13 to 15:50:44; its outputs are saved outside the repository and are not committed. Evidence levels: **V2** = computed by the auditor and independently re-derived by a Validator that read none of the auditor's conclusions and made no database connection (from the same saved query outputs); **inferred** = reading of names or patterns.

## Facts stated by the user (level A), respected throughout

1. People read the Min/Max values and place orders by hand; there is no system MRP.
2. In `Cube_Inventory_Exact`, `maximum` = 0 means the user did not fill it in.
3. Current minimum and maximum are "possibly usable" as a reference only; they are not to be treated as correct.
4. "drop" and "surge" in the original brief are the product categories Drop-out Fuse Cutout and Surge Arrester, the pilot scope, not sales-trend groups. **Phase R's finding on brief item 2 ("partly done, groups not shown to come from the trend") rested on the wrong reading and is corrected: item 2 is done, as the pilot scope of Drop-out Fuse Cutout and Surge Arrester with three items, then extended to 445 codes.** In the pricelist's Product Type column the pilot's two types are `High Voltage Distribution Fuse Cutout` (10 items) and `Medium Voltage Surge Arrester` (58 items) (config.yaml:33-35).

## Thresholds and definitions (written before computing)

**Part A.** Scope: `Cube_CES`, RevenueType `Omni Channel`, Status `Actual`, delivered (ActualDelDate present, ActualQty > 0). Units = ActualQty (METRICS Sec.19, unit-weighted). A row is late if ActualDelDate > ForecastDelDate. "Before May 2026" and "from May 2026" split on ForecastDelDate (the due date) at 2026-05-01. Value = sum of ActualPrice (a line total) over delivered Omni rows due 2024-01-01 to 2026-08-31 (2026-08 is the last full month). On hand = sum of `stock` over all warehouses of `Cube_Inventory_Exact` (S1's rule). The 66 items = the 36 `confirmed_to_order` items that fail criterion C3 plus the 30 `conflict` items. C3 is the PEM107 G3 verification's: over delivered rows due before 2026-05-01, median notice (ForecastDelDate - CtrDate) >= median PO-to-delivery (ActualDelDate - CtrDate) AND not_late >= 85% (unit-weighted); an item is "failed" when it does not meet both. Reproduced independently: 41 of the 78 confirmed_to_order items pass exactly as the recommended list in `phaseA_pem107_g3_verification.md`, 36 fail, and one (RS-F-99-090033) has no pre-May rows and is excluded. Cause of a late row from May 2026: **notice too short** if its notice < the item's median PO-to-delivery time (median over delivered rows due before May 2026; all rows if none), otherwise **late despite notice**. Concentration = the smallest number of items whose late units from May 2026 reach 80% of the total.

**Part B2.** Replenishment event = a day on which the item receives an inflow (QtyIn > 0) of transtype A, H or 151 (151 is the transfer-in half of the 150/151 pair, STATUS.md:3610) into the warehouse(s) where the minimum is set; same-day inflows of an item are one event. On-hand before an event = current stock (export) minus the net movement (QtyIn - QtyOut) of all that warehouse's rows on or after the event's first row, so the reconstruction is anchored on today's stock. Bands: at or below minimum; above minimum up to 1.5 x minimum; above 1.5 x minimum.

**Part D.** Omni Channel, Actual plus MPS, forecast_date not before createDate (the pipeline's own rule), forecast_date 2024-01-01 to 2026-08-31, quantities.

## Part A -- PEM107's 66 items (V2 for the late-unit counts and cause split of the ten items with most late units)

| Figure | Value |
|---|---|
| Items | 66 = 36 confirmed_to_order failing C3 + 30 conflict |
| Delivered units before May 2026 / from May 2026 | 44,030 / 1,880 |
| Late units before May 2026 / from May 2026 | 5,207 (11.8% of delivered) / 891 (47.4% of delivered) |
| Late units from May 2026: CTO failed C3 / conflict | 169 / 722 |
| Items with any late unit from May 2026 | 28 of 66 |
| **Items that make 80% of late units from May 2026** | **9 of 66** (the nine largest hold 82.7%) |
| Cause split of the 891 late units | **notice too short 93 units (10.4%); late despite notice 798 units (89.6%)** |
| Cause split by group | CTO failed C3: 5 short / 164 despite; conflict: 88 short / 634 despite |
| Value 2024-01 to 2026-08 | THB 282.6 million (CTO failed C3 THB 40.8 million; conflict THB 241.8 million) |
| Items holding stock now / units on hand | 31 / 620 |
| Items with no delivery from May 2026 | 20 |

By Product Type (late units from May 2026): Current Transformer Type COL 414 of 971 delivered (33 items), LDB 290 of 296 (4 items), Voltage Transformer Type VOL 94 of 206, VOG 53 of 308, CExL 40 of 78; the other six types have none.

Limits: the cause split compares each row's notice with the item's own median PO-to-delivery time, so it says whether the promised date was shorter than the item's normal lead time, not why the item was late. Some rows have negative notice or PO-to-delivery days (contract date after the due date), kept as recorded. Deliveries from May 2026 are only 1,880 units because the window is four months.

### The 66 items, grouped by Product Type (Product Description and Code from the pricelist)

| Product Type | Code | Product Description | Group | Delivered before May | Late before May | Delivered from May | Late from May | Late from May: notice too short | Late from May: late despite notice | Value 2024-01 to 2026-08 (THB) | On hand now |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Current Transformer Type CEL | RS-F-99-010124 | CEL-24 200/5A 30VA CL0.5Fs10 | CTO, failed C3 | 12 | 2 | 2 | 0 | 0 | 0 | 182,000 | 0 |
| Current Transformer Type CExL | RS-F-99-040004 | CExL-24 : 50:5A, [0.6B0.1,0.2&0.5] | CTO, failed C3 | 14 | 8 | 0 | 0 | 0 | 0 | 361,088 | 0 |
| Current Transformer Type CExL | RS-F-99-040006 | CExL-24 : 200:5A, [0.6B0.1,0.2&0.5] | CTO, failed C3 | 8 | 8 | 0 | 0 | 0 | 0 | 212,160 | 0 |
| Current Transformer Type CExL | RS-F-99-041005 | CExL-24 : 100/5A, 30VA, Cl.0.5Fs10 | CTO, failed C3 | 112 | 16 | 0 | 0 | 0 | 0 | 1,040,485 | 0 |
| Current Transformer Type CExL | RS-F-99-041008 | CExL-24 : 400/5A, 30VA, Cl.0.5Fs10 | CTO, failed C3 | 65 | 2 | 18 | 0 | 0 | 0 | 793,366 | 12 |
| Current Transformer Type CExL | RS-F-99-041001 | CExL-24 : 10/5A, 30VA, Cl.0.5Fs10 | conflict | 372 | 18 | 30 | 20 | 0 | 20 | 3,692,250 | 0 |
| Current Transformer Type CExL | RS-F-99-041033 | CExL-24 : 20/5A, 30VA, Cl.0.5Fs10 | conflict | 294 | 12 | 30 | 20 | 20 | 0 | 3,369,298 | 0 |
| Current Transformer Type CExL | RS-F-99-041003 | CExL-24 : 25/5A, 30VA, Cl.0.5Fs10 | conflict | 69 | 0 | 0 | 0 | 0 | 0 | 629,414 | 0 |
| Current Transformer Type CExL | RS-F-99-041015 | CExL-24 : 75/5A, 30VA, Cl.0.5Fs10 | conflict | 102 | 6 | 0 | 0 | 0 | 0 | 1,108,100 | 0 |
| Current Transformer Type COL | CT-F-99-020514 | COL-24 : 15/5A, 30VA, Cl.0.5 | CTO, failed C3 | 665 | 215 | 58 | 58 | 0 | 58 | 2,141,746 | 2 |
| Current Transformer Type COL | CT-F-99-020706 | COL-36 : 100/5A, 30VA, Cl.0.5 | CTO, failed C3 | 110 | 53 | 12 | 6 | 3 | 3 | 1,908,982 | 0 |
| Current Transformer Type COL | CT-F-99-020705 | COL-36 : 75/5A, 30VA, Cl.0.5 | CTO, failed C3 | 113 | 20 | 3 | 3 | 0 | 3 | 1,675,935 | 0 |
| Current Transformer Type COL | CT-F-99-020509 | COL-24 : 250/5A, 30VA, Cl.0.5 | CTO, failed C3 | 40 | 21 | 0 | 0 | 0 | 0 | 234,000 | 3 |
| Current Transformer Type COL | CT-F-99-020523 | COL-24 : 30:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 36 | 9 | 0 | 0 | 0 | 0 | 311,340 | 0 |
| Current Transformer Type COL | CT-F-99-020532 | COL-24 : 600:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 18 | 3 | 3 | 0 | 0 | 0 | 452,340 | 0 |
| Current Transformer Type COL | CT-F-99-020535 | COL-24 : 500:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 35 | 10 | 0 | 0 | 0 | 0 | 608,150 | 0 |
| Current Transformer Type COL | CT-F-99-020702 | COL-36 : 20/5A, 30VA, Cl.0.5 | CTO, failed C3 | 120 | 21 | 8 | 0 | 0 | 0 | 1,569,522 | 0 |
| Current Transformer Type COL | CT-F-99-020703 | COL-36 : 30/5A, 30VA, Cl.0.5 | CTO, failed C3 | 68 | 18 | 12 | 0 | 0 | 0 | 948,195 | 0 |
| Current Transformer Type COL | CT-F-99-020704 | COL-36 : 50/5A, 30VA, Cl.0.5 | CTO, failed C3 | 144 | 29 | 18 | 0 | 0 | 0 | 2,280,552 | 0 |
| Current Transformer Type COL | CT-F-99-020707 | COL-36 : 150/5A, 30VA, Cl.0.5 | CTO, failed C3 | 54 | 21 | 6 | 0 | 0 | 0 | 598,418 | 0 |
| Current Transformer Type COL | CT-F-99-020710 | COL-36 : 300/5A, 30VA, Cl.0.5 | CTO, failed C3 | 8 | 3 | 0 | 0 | 0 | 0 | 126,000 | 0 |
| Current Transformer Type COL | CT-F-99-020717 | COL-36 : 150:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 33 | 6 | 3 | 0 | 0 | 0 | 668,850 | 0 |
| Current Transformer Type COL | CT-F-99-020723 | COL-36 : 30:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 12 | 3 | 0 | 0 | 0 | 0 | 249,000 | 3 |
| Current Transformer Type COL | CT-F-99-020725 | COL-36 : 75:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 25 | 6 | 0 | 0 | 0 | 0 | 292,940 | 0 |
| Current Transformer Type COL | CT-F-99-020726 | COL-36 : 100:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 36 | 9 | 3 | 0 | 0 | 0 | 904,650 | 6 |
| Current Transformer Type COL | CT-F-99-020728 | COL-36 : 200:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 18 | 9 | 3 | 0 | 0 | 0 | 718,200 | 0 |
| Current Transformer Type COL | CT-F-99-020730 | COL-36 : 300:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CTO, failed C3 | 9 | 6 | 0 | 0 | 0 | 0 | 315,000 | 0 |
| Current Transformer Type COL | CT-F-99-020501 | COL-24 : 10/5A, 30VA, Cl.0.5 | conflict | 2,213 | 362 | 165 | 153 | 3 | 150 | 13,763,190 | 17 |
| Current Transformer Type COL | CT-F-99-020502 | COL-24 : 20/5A, 30VA, Cl.0.5 | conflict | 1,601 | 282 | 128 | 70 | 0 | 70 | 8,520,200 | 8 |
| Current Transformer Type COL | CT-F-99-020505 | COL-24 : 75/5A, 30VA, Cl.0.5 | conflict | 1,161 | 146 | 112 | 33 | 6 | 27 | 10,210,227 | 19 |
| Current Transformer Type COL | CT-F-99-020507 | COL-24 : 150/5A, 30VA, Cl.0.5 | conflict | 973 | 164 | 65 | 23 | 3 | 20 | 8,747,016 | 4 |
| Current Transformer Type COL | CT-F-99-020527 | COL-24 : 100:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 457 | 48 | 36 | 12 | 6 | 6 | 8,316,290 | 6 |
| Current Transformer Type COL | CT-F-99-020524 | COL-24 : 150:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 303 | 52 | 31 | 10 | 7 | 3 | 5,272,340 | 9 |
| Current Transformer Type COL | CT-F-99-020526 | COL-24 : 400:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 194 | 15 | 28 | 9 | 3 | 6 | 4,224,640 | 5 |
| Current Transformer Type COL | CT-F-99-020508 | COL-24 : 200/5A, 30VA, Cl.0.5 | conflict | 795 | 67 | 82 | 7 | 0 | 7 | 7,947,610 | 19 |
| Current Transformer Type COL | CT-F-99-020510 | COL-24 : 300/5A, 30VA, Cl.0.5 | conflict | 530 | 54 | 38 | 6 | 3 | 3 | 5,892,332 | 20 |
| Current Transformer Type COL | CT-F-99-020512 | COL-24 : 500/5A, 30VA, Cl.0.5 | conflict | 56 | 3 | 6 | 6 | 6 | 0 | 550,260 | 0 |
| Current Transformer Type COL | CT-F-99-020531 | COL-24 : 75:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 152 | 9 | 9 | 6 | 0 | 6 | 2,241,920 | 0 |
| Current Transformer Type COL | CT-F-99-020528 | COL-24 : 200:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 518 | 84 | 54 | 6 | 3 | 3 | 10,098,560 | 6 |
| Current Transformer Type COL | CT-F-99-020525 | COL-24 : 50:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 174 | 30 | 12 | 3 | 3 | 0 | 2,005,980 | 8 |
| Current Transformer Type COL | CT-F-99-020530 | COL-24 : 300:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | conflict | 433 | 65 | 58 | 3 | 3 | 0 | 9,222,120 | 7 |
| Current Transformer Type COL | CT-F-99-020511 | COL-24 : 400/5A, 30VA, Cl.0.5 | conflict | 291 | 17 | 18 | 0 | 0 | 0 | 2,864,554 | 11 |
| Current Transformer Type LDB | RS-F-99-070003 | LDB-35 : 200/5A, 5VA, Cl.0.5 | CTO, failed C3 | 9,668 | 1,524 | 100 | 100 | 0 | 100 | 2,771,184 | 0 |
| Current Transformer Type LDB | RS-F-99-070002 | LDB-35 : 150/5A, 5VA, Cl.0.5 | conflict | 5,013 | 108 | 163 | 160 | 0 | 160 | 1,895,527 | 208 |
| Current Transformer Type LDB | RS-F-99-070005 | LDB-35 : 400/5A, 5VA, Cl.0.5 | conflict | 2,296 | 15 | 30 | 30 | 0 | 30 | 535,868 | 101 |
| Current Transformer Type LDB | RS-F-99-070004 | LDB-35 : 250/5A, 5VA, Cl.0.5 | conflict | 3,819 | 45 | 3 | 0 | 0 | 0 | 1,311,270 | 35 |
| Current Transformer Type LExM | RS-F-99-090010 | LExM-35 : 200/5A 5 VA Class 0.5 | CTO, failed C3 | 9 | 3 | 0 | 0 | 0 | 0 | 20,100 | 0 |
| Current Transformer Type LExM | RS-F-99-090011 | LExM-55 : 400/5A 5 VA Class 0.5 | conflict | 12 | 6 | 0 | 0 | 0 | 0 | 36,300 | 0 |
| Current Transformer Type LExM-IOT | RS-F-99-090027 | LExM-155 1000/5 A 5 VA CL.0.5 Fs<5 | CTO, failed C3 | 9 | 6 | 0 | 0 | 0 | 0 | 73,950 | 0 |
| Current Transformer Type LExM-IOT | RS-F-99-090030 | 	LExM-130 150/5A 5 VA CL.0.5 Fs<5 | CTO, failed C3 | 25 | 24 | 0 | 0 | 0 | 0 | 55,500 | 0 |
| Voltage Transformer Type VEG | RS-F-99-100001 | VEG-24 : 22000/√3/110/√3/110/√3V, 50VA, Cl.0.5&3P | CTO, failed C3 | 40 | 21 | 15 | 0 | 0 | 0 | 1,359,900 | 0 |
| Voltage Transformer Type VEG | RS-F-99-100013 | VEG-24 : 22000/√3/110/√3V, 50VA, Cl.0.5 | CTO, failed C3 | 51 | 3 | 0 | 0 | 0 | 0 | 391,500 | 3 |
| Voltage Transformer Type VEL | RS-F-99-130011 | VEL-24 : 24000/120-240V, 25VA, Cl.0.5 | CTO, failed C3 | 2 | 2 | 2 | 0 | 0 | 0 | 101,000 | 0 |
| Voltage Transformer Type VExL | RS-F-99-120002 | VExL-24 : 24000/120V, 0.6WXY&1.2Z | CTO, failed C3 | 65 | 45 | 0 | 0 | 0 | 0 | 1,692,320 | 0 |
| Voltage Transformer Type VExL | RS-F-99-120006 | VExL-24 : 22000/110V, 50VA, Cl.0.5 | CTO, failed C3 | 6 | 4 | 2 | 0 | 0 | 0 | 200,000 | 0 |
| Voltage Transformer Type VOG | VT-F-99-010818 | VOG-362 : 33000/√3:110/√3V 50VA, Cl.0.5 | CTO, failed C3 | 19 | 8 | 4 | 1 | 1 | 0 | 1,061,160 | 0 |
| Voltage Transformer Type VOG | VT-F-99-010820 | VOG-362-P : For LBS Op.7 | CTO, failed C3 | 352 | 81 | 25 | 0 | 0 | 0 | 12,415,667 | 7 |
| Voltage Transformer Type VOG | VT-F-99-010721 | VOG-242 : 22000/√3:110/√3&110/√3V 50VA, Cl.0.5&3P (yn0&yn0) | conflict | 2,103 | 255 | 261 | 50 | 17 | 33 | 69,120,510 | 19 |
| Voltage Transformer Type VOG | VT-F-99-010819 | VOG-362 : 33000/√3:110/√3&110/√3V 50VA, Cl.0.5&3P (yn0&yn0) | conflict | 208 | 54 | 17 | 2 | 2 | 0 | 8,310,614 | 1 |
| Voltage Transformer Type VOG | VT-F-99-010701 | VOG-242 : 22000/√3:110/√3V 500VA, Cl.3 For LBS Op.5 & 6 | conflict | 30 | 6 | 1 | 0 | 0 | 0 | 1,182,000 | 26 |
| Voltage Transformer Type VOL | VT-F-99-010302 | VOL-36 : 33000/230V, 500VA, Cl.3  | CTO, failed C3 | 391 | 98 | 2 | 1 | 1 | 0 | 1,387,600 | 0 |
| Voltage Transformer Type VOL | VT-F-99-010209 | VOL-24 : 24000/120V, 50VA, Cl.0.5 | CTO, failed C3 | 57 | 16 | 0 | 0 | 0 | 0 | 715,922 | 4 |
| Voltage Transformer Type VOL | VT-F-99-010203 | VOL-24 : 22000/110V, 50VA, Cl.0.5 (Private) | conflict | 5,361 | 268 | 143 | 83 | 3 | 80 | 39,970,786 | 31 |
| Voltage Transformer Type VOL | VT-F-99-010202 | VOL-24 : 22000/230V, 500VA, Cl.3 | conflict | 1,804 | 651 | 54 | 10 | 0 | 10 | 7,946,323 | 7 |
| Voltage Transformer Type VOL | VT-F-99-010205 | VOL-24 : 22000/110V, 500VA, Cl.3 For LBS Op.4 | conflict | 36 | 0 | 0 | 0 | 0 | 0 | 119,000 | 8 |
| Voltage Transformer Type VOL | VT-F-99-010303 | VOL-36 : 33000/110V, 50VA, Cl.0.5 (PEA Regional) | conflict | 211 | 32 | 7 | 0 | 0 | 0 | 2,704,446 | 5 |


## Part B1 -- Every use of minimum and maximum in code (20 locations; read by an Explorer, line numbers confirmed)

**One rule governs `maximum` = 0:** nowhere in `src/` is `maximum == 0` special-cased. The project's own `has_current_setting = (summed minimum > 0) OR (summed maximum > 0)` (`src/phaseE1_common.py:288-301`), so a row with a minimum and a maximum of 0 **counts as having a setting**; an item is "no setting" only when both sums are 0. Display fields pass a 0 through as 0.

| File:line | Reads | Maximum = 0 treated as | Numbers and pages it affects | Display or model input |
|---|---|---|---|---|
| `src/phaseE1_common.py:265-275`, `src/snapshot_daily.py:75-77`, `src/inventory_page_sources.py:82-98` | the raw pull, the daily snapshot columns, the page-pull fallback | raw, untouched | feed the rows below | pull and pass-through |
| `src/phaseE1_common.py:288-301` `current_minmax_per_item` | sums of minimum and maximum over **all** warehouses | `has_current_setting` true if either sum > 0 | writes `phaseE1fix_2_current_minmax.csv` (`phaseE1fix_recompute.py:521-522`, `phaseJ_apply_robust_defaults.py:60-61`) | comparison baseline only (its docstring) |
| `src/build_inventory_page_data.py:234-243` (PEM101), `:284-342` (PEM103, PEM107) | `current_total_min`/`current_total_max` into `current_min`/`current_max` | passed through as 0 | `forecast/inventory.html`: per-item "Current Min" column, the value-at-risk column and the Min-versus-current chart (`build_inventory_page.py:613, 620, 717-720`); `current_max` is carried but not shown | display only |
| `src/reader_values.py:55-60` `count_no_current_minmax`, `src/build_report.py:549-552`, `config.yaml:1099` | `has_current_setting` | only items with both sums 0 count as "no setting" | `forecast/sales_report.html` limitation bullet "46 of 128 items have no Min/Max set" (the text says the values are inconsistent and usable only for comparison) | display only |
| `src/phaseE1_current_settings_comparison.py:45-46, 95-125` | current min/max, `has_current_setting` | max 0 gives cover 0 months (counted below the protection period where demand > 0) | writes `phaseE1_5_current_vs_scenario.csv`, `phaseE1_5_current_stock_value_128items.csv` (no page found) | analysis |
| `src/investigations/phaseJ_calibration.py:35-49, 183-199`; `phaseJ_validator.py:72-112, 122-151` | minimum and maximum summed over **sellable** warehouses | **a minimum above 0 with a maximum of 0 never orders** (order quantity = max - position <= 0), with no reactive fallback | baseline fill rate of the Phase J calibration (PEM101: 52 items with a setting, 76 reactive) | **model input** (calibration baseline) |
| `src/investigations/investigate_inventory.py:91-159` and raw pulls in `phaseI_single_pull.py`, `phaseJ3_explorerBOM_pull.py`, `task2_no_history_investigation.py`, `phaseD_check1_sellable_stock.py` | minimum, maximum | counted separately (min > 0, max > 0) | one-off findings, no page | analysis |

**Not readers:** `src/build_inventory_dataset.py` (so `data/inventory.json` and `index.html`) reads stock and reserve only; the page's "stock value" box and its "Items with a Min/Max" figure (`build_inventory_page.py:151-166, 1026`) use the scenario's computed Min and Max, not the table's.

**On today's data the case does not move any page figure:** in `phaseE1fix_2_current_minmax.csv` (128 items) no item has a minimum with a maximum of 0 (82 have a setting, 46 do not, as the page says); in the 445 project codes exactly one warehouse row does (item FC-A-27-00102, warehouse INTR, minimum 9.62), whose item also has WH01 minimum 2070 and maximum 3370. Unverified: whether INTR is in any sellable list (it is not in config.yaml's PEM101 list), and whether the Phase J calibration output reaches the slider default.

## Part B2 -- How the current minimum relates to actual receipts (description only)

**Limit, plainly: only today's minimum is known; there is no history of its changes.** Nothing below says the minimum is right or wrong.

- **By the prompt's definition the set is empty.** Of PEM101's 82 `stock_policy` items, 54 have a minimum above 0 in a sellable warehouse (FG01, FG21, WH21) and 76 have one in some warehouse (rows: FG 72 items, FG01 54, FG11 52, WH01 3, F101 1, INTR 1). `cube_inventory_tran` has rows for only **30** of the 82, and only **3** have any non-zero movement (FC-A-27-00102, FC-A-27-00202, FC-A-38-00102, all Fuse Holder items); the other 27 have no quantity movement (most a single zero-quantity row dated 2021-12-14). None of the three has its minimum in a sellable warehouse: it sits in **WH01** (2,070; 3,990; 3,060). So **zero receipt events** can be reconstructed for the sellable warehouses. (V2)
- **Supplementary description for the only three items with history, at WH01 where their minimum sits** (events = inflows of transtype A, H or 151 into WH01; 423 events from 2016-09-12 to 2025-03-20; the reconstruction is anchored on today's WH01 stock, which equals the sum of history, 0, for all three; 27 events reconstruct to a negative level, a data limit): on-hand just before a receipt was **at or below the minimum in 60.5%, between the minimum and 1.5 times in 14.2%, above in 25.3%**; since 2024-01 (52 events): 71.2% / 13.5% / 15.4%. Per item events: 62, 299, 62; the median level before a receipt was 1,854, 3,533, 1,229 against minima of 2,070, 3,990, 3,060. Three items of one product kind cannot stand for the 82. (V2)
- **Against the J3 calibration ensemble** (`output/summary/phase23_ensemble_distinct_members_PEM101.csv`, 80 distinct members; reorder level 0.25 to 2.0 months of mean demand, median 1.0): for the 76 stock_policy items with a minimum above 0, the minimum summed over all warehouses (the project's own `current_total_min` basis) is **above the ensemble's reorder-level range for 69 items, within it for 7, below it for none**; the median minimum is 4.96 months of mean monthly demand (quartiles 2.8 and 13.9). Mean demand comes from `processed_all_divisions_monthly_qty.csv`. The sum counts stock held in several warehouses and the ensemble is a single reorder level, so the two are not like-for-like; this is a position, not a verdict.

## Part B3 -- Rows with a minimum above 0 and a maximum of 0 (V2)

734 rows, 733 items (PEM 733, CI 1), in 11 warehouses: **WH06 618, QA 51, WH08 38, WH 14, WH07 6**, and EXP 2 and one each in FMTO, WH24, INTR, FG27, W126. Restricted to the 445 project codes: 1 row (INTR). By item (codes trimmed of padding): **1 finished good in the pricelist** (FC-A-27-00102, which is also a raw material in the BOM); **422 further materials in the BOM** (423 BOM raw materials in all); **3 BOM finished goods that are not in the pricelist**; **307 neither**. By warehouse: WH06 = 323 BOM materials + 295 neither; QA = 48 materials, 2 BOM finished goods, 1 neither; WH08 = 30 materials + 8 neither; WH and WH07 = materials only. **533 of the 733 moved in `cube_inventory_tran` since 2025-10-01** (327 of 422 BOM materials, 203 of 307 "neither", the pricelist item and 2 of the 3 BOM finished goods); 494 hold stock now in some warehouse (299 of the BOM materials); **none holds stock in the warehouse that has the minimum** (0 of 734 rows). So this group is mostly production materials and supplies with a warehouse-level reorder point and no maximum, consistent with "maximum 0 = not filled in". Correction made during validation: the first classification compared item codes without trimming the padding and reported 0 materials and 732 "neither"; the Validator's trimmed classification is the one above and was re-run by the auditor with the same result.

## Part C -- Columns of `Cube_Inventory_Exact` (V2)

A base table (not a view), 17 columns: `id` int, `company` varchar, `warehouse` varchar, `itemcode` varchar, `product_category` varchar, `product_type` varchar, `product_description` varchar, `unit` varchar, `stock` decimal(18), `freestock` decimal(18), `tobe_received` decimal(18), `reserve_bywa` decimal(18), `available` decimal(18), `timestamp` datetime, `costPrice_standard` float, `minimum` float, `maximum` float. **No column records who set or changed a value, or when**: `timestamp` is the table's load time (every row within a 98-second batch). Other tables with minimum/maximum columns: `Cube_Inventory_Aging_PSL` (`Minimum`, `Maximum`; company PSL) and `Cube_Production_Control` (`MinVal`, `MaxVal`, production-control measurements, not reorder points). No column anywhere in the 111 objects is named reorder, safety or similar. Columns that record a person or a time exist on unrelated tables (`Cube_Vendor_List.modifier`/`updateDateTime`, `cube_QMS.update_date`, `Cube_Standard_Time.user_edit`, `cube_po.user_id`, the sales tables' `handle_by`), none on stock settings. The source system of `minimum`/`maximum` is therefore not visible from the database.

## Part D -- Seasonality of the original pilot scope (V2 for the shares, correlations and August figures)

Omni Channel Actual plus MPS by forecast_date, quantities, 2024-01 to 2026-08. Product Types from the pricelist: Drop-out Fuse Cutout = `High Voltage Distribution Fuse Cutout` (10 items), Surge Arrester = `Medium Voltage Surge Arrester` (48 of its 58 items sold in the window).

| Group | 2024 total | 2025 total | Jan-Aug 2026 | May-Oct share 2024 / 2025 | Correlation of monthly pattern 2024 vs 2025 | 2026 Jan-Aug vs 2024 / vs 2025 |
|---|---|---|---|---|---|---|
| Drop-out Fuse Cutout | 34,173 | 19,653 | 29,799 | 56.9% / 55.2% | **-0.61** | 0.25 / 0.76 |
| Surge Arrester | 26,274 | 29,936 | 32,795 | 52.2% / 53.4% | **+0.68** | 0.83 / 0.68 |
| EEE-F-FC-1040010002 | 20,294 | 5,802 | 18,517 | 55.3% / 63.7% | -0.70 | 0.10 / 0.54 |
| HS-F-99-02110 | 266 | 449 | 5,971 | 37.6% / 77.7% | 0.23 | 0.21 / 0.52 |
| HS-F-99-0213 | 696 | 1,185 | 3,002 | 55.3% / 67.9% | 0.16 | 0.32 / 0.88 |

Monthly quantities (Jan to Dec):

| Group, year | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fuse Cutout 2024 | 1799 | 3516 | 3795 | 3398 | 4040 | 5121 | 3878 | 3183 | 1507 | 1699 | 924 | 1313 |
| Fuse Cutout 2025 | 955 | 868 | 1079 | 913 | 1358 | 1710 | 1397 | 1544 | 2092 | 2738 | 2703 | 2296 |
| Fuse Cutout 2026 | 1486 | 2154 | 2260 | 2786 | 3600 | 4825 | 4018 | 8670 | | | | |
| Surge Arrester 2024 | 1601 | 2168 | 2266 | 1879 | 1810 | 1740 | 2534 | 2623 | 2882 | 2135 | 2468 | 2168 |
| Surge Arrester 2025 | 2099 | 2315 | 1912 | 2124 | 2104 | 2286 | 3274 | 2514 | 2962 | 2845 | 3102 | 2399 |
| Surge Arrester 2026 | 2419 | 2903 | 3403 | 3368 | 3702 | 3195 | 6259 | 7546 | | | | |
| EEE-F-FC-1040010002 2024 | 1263 | 2712 | 2884 | 2168 | 2237 | 3594 | 2841 | 2020 | 237 | 288 | 3 | 47 |
| EEE-F-FC-1040010002 2025 | 0 | 0 | 0 | 161 | 125 | 572 | 100 | 230 | 916 | 1750 | 1293 | 655 |
| EEE-F-FC-1040010002 2026 | 305 | 914 | 782 | 1135 | 2385 | 3441 | 2587 | 6968 | | | | |
| HS-F-99-02110 2024 | 3 | 10 | 153 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 0 |
| HS-F-99-02110 2025 | 0 | 100 | 0 | 0 | 0 | 169 | 0 | 180 | 0 | 0 | 0 | 0 |
| HS-F-99-02110 2026 | 0 | 200 | 0 | 238 | 200 | 630 | 1838 | 2865 | | | | |
| HS-F-99-0213 2024 | 0 | 39 | 169 | 100 | 0 | 0 | 0 | 185 | 100 | 100 | 3 | 0 |
| HS-F-99-0213 2025 | 0 | 100 | 0 | 0 | 103 | 0 | 185 | 300 | 125 | 92 | 280 | 0 |
| HS-F-99-0213 2026 | 0 | 0 | 50 | 42 | 130 | 350 | 983 | 1447 | | | | |

(Calendar-month shares of each year's volume are these quantities divided by the year's total; for 2026 the shares of the year are not defined yet.)

**What the shapes show (description only).** Surge Arrester has a flat, mildly rising pattern in both years (peak month 11% of the year; May-Oct 52-53%, about a half, so no season) and a repeatable correlation of 0.68; Fuse Cutout's pattern **reverses** between years (peak June 2024, peak October 2025; correlation -0.61), so no stable season can be read from two years. The three items are dominated by single months and a few orders. In both categories **July and August 2026 are far above any month of 2024 or 2025** (Fuse Cutout August 8,670; Surge Arrester August 7,546).

**Can any base model represent seasonality? No.** The Top-down Combination averages Naive, Croston, SBA and moving averages (`src/models.py:85-113`, `combination_forecast` and `get_models`; Naive `:12`, moving average `:17`, Croston `:23`, SBA `:29`); the extended set adds SES, Holt with `season_length=1` (`:46`) and TSB, none seasonal. A seasonal pattern in the data would not be carried into the forecast.

**August 2026 against previous Augusts** (only two previous Augusts exist in the window, 2024 and 2025): Fuse Cutout **8,670 against 3,183 and 1,544: above the range of both**, and 2.7 times the higher; Surge Arrester **7,546 against 2,623 and 2,514: above**, 2.9 times the higher. Largest single order: Fuse Cutout 1,000 units (CTR-2026-03286), **11.5%** of the month's 8,670 (171 orders, 67 customers); Surge Arrester 500 units (CTR-2026-04806), **6.6%** (212 orders, 71 customers). Largest customer: Fuse Cutout 12.6% (CS08333), Surge Arrester 14.7% (CS09293). For the three items: EEE-F-FC-1040010002 largest order 14.4%, customer 15.0%; HS-F-99-02110 17.5% and 35.3%; HS-F-99-0213 20.7% and 44.9%. So the August 2026 level is not one large order or one customer in the two categories; it is broad.

## Gaps, questions and assignments

- **B2 cannot be answered for the stock_policy items**: `cube_inventory_tran` has no usable movement for 79 of PEM101's 82 stock_policy items; receipts of finished goods would need another source (production receipts, `cube_final` batches or `Cube_Production_Order`). Assigned phase K, P2, Claude Code.
- The stock_policy items' minimums sit mostly in FG, FG01 and FG11 while the project's sellable list for PEM101 is FG01, FG21, WH21; whether FG and FG11 are sellable is for the ERP team.
- 89.6% of late units from May 2026 among the 66 items were late although the notice was at least the item's normal lead time: for the business to explain, not derivable from the data.
- Questions for people are listed in the summary and in STATUS.md.

## Part F -- Validator (no database access; read none of the auditor's conclusions; re-derived from the saved query outputs)

| Item | Verdict |
|---|---|
| A: 66 items (36 + 30), 891 late units, cause split 93 / 798, 9 items for 80%, the ten items with most late units | **MATCH** (all ten rows of units, short notice and late despite notice) |
| B2: shares and counts | **MATCH**: 54 items with a minimum in a sellable warehouse, none with movement; 423 events at WH01, 60.5% / 14.2% / 25.3%, 27 negative, 71.2% / 13.5% / 15.4% since 2024-01. Its line on INTR (stock 9.62, minimum 0.0) contradicts the export and its own item (b); the export shows INTR stock 0.0, minimum 9.62, maximum 0 (the auditor re-checked) |
| B3: counts by warehouse | **MATCH** (734 rows, 733 items, 11 warehouses; 1 row in the 445 codes) |
| B3: classification | **DISCREPANCY, resolved in the Validator's favour**: the auditor's first pass did not trim code padding (0 materials, 732 neither); trimmed, 422 materials + the pricelist item, 3 BOM-only finished goods, 307 neither. Movement 533, stock now 494, stock in the minimum's own row 0 match |
| C: 17 columns with types, no who/when column, tables with minimum/maximum | **MATCH** |
| D: monthly quantities, May-Oct shares, correlations, August figures, largest order and customer shares, models | **MATCH** (the Validator reports the two HS items also lie inside the Surge Arrester group, which is so) |

Both sides used the same saved query outputs, so a query-level error would be shared.
