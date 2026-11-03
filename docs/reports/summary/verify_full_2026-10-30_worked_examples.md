# Worked examples from the verification of 2026-10-30

Every number below was recomputed by an independent Validator with its own code from the recorded data (snapshot commit 869caeceddfb83d5c576be2c9febc54393707389), then compared with the published page or the recorded file. They are written for a teaching guide. No customer names appear. The three sales examples (1, 5, 6) come from Team 2; the three planning examples (2, 3, 4) come from Team 3.

---

## 1. Top-down split: one item of the Fuse Cutout group

Item EEE-F-FC-1040010002 (PEM101). Vintage 2: the fit window is 2024-02 to 2026-08, which is 31 months.

1. **Add up the group.** The Type "High Voltage Distribution Fuse Cutout" has 10 items. Adding their monthly units gives the Type series: 3516, 3795, 3398, 4040, 5121, 3878, 3183, 1507, 1699, 924, 1313, 955, 868, 1079, 913, 1358, 1710, 1397, 1544, 2092, 2738, 2703, 2296, 1486, 2154, 2260, 2786, 3600, 4825, 4018, 8670.
2. **Forecast the group with six simple methods.** Each method gives one level, repeated for every month ahead.
   - Naive: the last month = 8,670.
   - Moving average of 3 months = 5,837.67.
   - Moving average of 6 months = 4,359.83.
   - Moving average of 12 months = 3,302.33.
   - Croston: smoothed order size divided by smoothed gap, smoothing 0.1; the gap is 1 because every month has sales = 3,306.06.
   - SBA: 0.95 × Croston = 3,140.76.
3. **Combine.** Plain average of the six: (8,670 + 5,837.67 + 4,359.83 + 3,302.33 + 3,306.06 + 3,140.76) / 6 = **4,769.44 units per month** for the whole group.
4. **Find the item's share of the past.** Over the 31 months the item sold 43,350 units and the group sold 81,826. Share = 43,350 / 81,826 = **0.529783**.
5. **Split.** Item forecast = 4,769.4414 × 0.529783 = **2,526.77 units per month**, for each month 2026-09 to 2027-02. The forward-test log row says 2,526.7676. All 10 items' forecasts add back to 4,769.44.

In plain words: forecast the steadier group total first, then give each item its historical slice. The jump to 8,670 in the last month pulls up Naive and the 3-month average, and so the combined figure.

---

## 2. Min and Max: a stocked finished item (PEM101 calibration)

Item EEE-F-FC-1040010002. PEM101 Min/Max does not use the supplier lead time. It uses the calibrated reorder level (decision D2, replenishment lead 1-30 days) and demand history (decision D3).

1. **Demand level.** Add up the item's sales by delivery date from 1 Jan 2024 to 30 Sep 2026: 1,004 days and about 50,819 units. 50,819 / 1,004 = **50.62 units a day**, about 1,541 a month (50.62 × 30.44).
2. **Choose how reliable delivery should be.** The page default is "as on time as today", 98.24% delivered not late. The calibration curve says this needs a reorder level of **0.76 months** of demand. It sits between 0.65 months at 97.69% and 0.80 months at 98.44%.
3. **Min** = 0.7599 × 30.44 × 50.62 = **1,171 units**.
4. **Max.** The 37 calibration members each add a gap of 0.5 to 2.25 months on top of the reorder level; the middle gap is 1.0 month. Max = (0.7599 + 1.0) × 30.44 × 50.62 = **2,712 units**. Across members the Max runs from 1,941 to 4,638, which the page shows as the uncertainty band.
5. **Compare with stock.** On hand (FG01 + FG21 + WH21) is 831, below Min. Months of cover = 831 / 2,526.77 (average monthly forecast) = **0.33 months**. Excess would be more than 6 months of cover, so it is not excess.
6. **Lead time.** The item's own supplier lead time (about 89 days for items like this) is shown beside it and goes to the material plan only. It is not in Min or Max.

Check: a Validator rebuilt the whole calibration grid (7,360 numbers) and got a maximum difference of 0.00 to the recorded grid. Against the page the difference is at most 0.04 units, because the page interpolates on a grid rounded to two decimals.

---

## 3. One operation-plan month: PEM107, October 2026

Rule: each item's demand is the larger of its forecast and the orders already accepted for that month. Stock items are produced up to Max when stock would fall below Min. Other items' load equals their demand.

1. **One stock item, CT-F-99-020503.** Opening stock 7. Forecast 21.53 and accepted orders 3, so demand is 21.53. Stock would be 7 − 21.53 = −14.53, below Min 114.04. So produce up to Max 135.25: 135.25 − (−14.53) = **149.78 units**, closing 135.25. In November: opening 135.25, demand 21.53, stock would be 113.72, still below Min 114.04, so produce 21.53 to get back to 135.25.
2. **All four PEM107 stock items together:** 18.65 + 149.78 + 218.73 + 198.73 = **585.90 units**.
3. **Made-to-order items** load their demand: **365.24**. **Items of unclear class** also load their demand: **452.97**.
4. **Total load** = 585.90 + 365.24 + 452.97 = **1,404.11 units**.
5. **Capacity reference.** PEM107's highest month of finished output in history was 6,221 units (Nov 2024). It is a lower bound for capacity, not real capacity. 1,404.11 / 6,221 = **22.6%**. The page shows the same total split as 103 demand-driven, 483 refill to Max and 818 made to order. Units of different products are simply added.

---

## 4. One material explosion with a latest order date

Finished item HS-F-99-0211 (PEM101, stocked). Planned at 2,378.2 units in October 2026 (a stock refill) and 1,414.8 a month after.

1. **Bill of materials, one unit each:** HS-W-03-0016, HS-W-07-0211-2 and HS-W-08-0211. All three are in-house sub-assemblies: they have their own bill of materials and no purchase record.
   - HS-W-08-0211 needs HS-R-00-0806 (also in-house) and three bought materials.
   - HS-W-07-0211-2 needs HS-R-00-0802 × 1, HS-R-01-0716 × 1 and three SP parts × 2.
2. **Netting a sub-assembly.** All parents together ask for 6,972.81 of HS-R-00-0806 in October. The raw-material warehouses hold 2,563. Only **4,409.81** goes further down.
3. **One bought material, HS-R-00-0802.** This item needs 2,378.2 of it in October. With its 41 other products the whole plan needs 6,734.23 in October, then 4,427.03, 4,264.49, 4,351.22 and 4,264.49 in the next four months.
4. **Available.** Stock 5,492 + open purchase orders of 5,000 due by October = 10,492. The running need reaches 6,734.23 in October (no shortage) and 11,161.26 in November. So it is short by **669.26** from November, growing to 13,549.45 by February.
5. **Lead time.** The median of past purchase orders from order date to first receipt is **18 days** (source: actual purchase orders; the other sources, in order, are the supplier-quoted days and then 63 days assumed).
6. **Latest order date** for the first shortage month: 1 Nov 2026 − 18 days = **14 Oct 2026**. Today is 30 Oct 2026, so that date has passed. The material is on the "too late to order today" list with **669.26 units to order now**. December's date (13 Nov) and January's (14 Dec) are not yet due. The material's date is the earliest of these.

Check: a Validator rebuilt the whole explosion for all 2,246 recorded materials. Gross need differed by at most 5e-7; net need, order date, lead time and lead-time source matched 2,246 of 2,246.

---

## 5. Relative MAE with Horizon 3: the Fuse Cutout group

MAE is the average size of the forecast miss. Relative MAE divides the model's MAE by the Naive method's MAE (Naive = last month repeated). Below 1 means the model missed by less than Naive. There are 7 test windows ("origins"), each forecasting 6 months ahead.

| origin | first test month | model MAE of window | Naive MAE of window | month-3 miss, model | month-3 miss, Naive |
|---|---|---|---|---|---|
| 1 | 2025-03 | 428.8 | 465.5 | 404.3 | 490.0 |
| 2 | 2025-05 | 373.5 | 893.5 | 157.8 | 484.0 |
| 3 | 2025-07 | 599.2 | 578.0 | 445.5 | 382.0 |
| 4 | 2025-09 | 688.3 | 720.2 | 1111.2 | 1159.0 |
| 5 | 2025-11 | 441.4 | 473.2 | 530.1 | 1252.0 |
| 6 | 2026-01 | 932.1 | 885.2 | 123.4 | 36.0 |
| 7 | 2026-03 | 2321.2 | 2205.8 | 1561.3 | 1446.0 |
| sum | | 5784.5 | 6221.3 | 4333.7 | 5249.0 |

- **Relative MAE** = 5,784.5 / 6,221.3 = **0.930**. Below 1, so the draft wording is "pass".
- The model's own MAE = 5,784.5 / 7 = 826.4, the value in the pilot table.
- **Relative MAE at Horizon 3** (only the third month ahead) = 4,333.7 / 5,249.0 = **0.826**.
- The page shows 0.93 and 0.83. Caveat shown on the page: 7 overlapping windows are not proof of beating Naive.

---

## 6. One Tracking Signal: the Fuse Cutout group

Tracking Signal = the sum of the signed forecast errors divided by the mean absolute error. It shows whether the forecast is biased one way. The limit is ±4. Here e = forecast minus actual of the first month ahead; negative means the forecast was too low. The 8 points are the 7 backtest origins plus one forward month.

| point | e |
|---|---|
| origin 1 (2025-03) | +683.3 |
| origin 2 (2025-05) | +196.8 |
| origin 3 (2025-07) | +249.5 |
| origin 4 (2025-09) | −500.2 |
| origin 5 (2025-11) | −686.9 |
| origin 6 (2026-01) | +650.6 |
| origin 7 (2026-03) | −221.3 |
| forward month 2026-08 (forecast 3,215.1, actual 8,670) | −5,454.9 |

- Sum of e = −5,083.1. Mean of |e| = 8,643.5 / 8 = 1,080.4.
- Tracking Signal = −5,083.1 / 1,080.4 = **−4.70**. Outside ±4, so the page word is "warning". The page shows −4.7.
- With the 7 backtest points alone the signal is **+0.82**, which is normal. One month, August 2026, causes the warning. The executive tab already says it comes mostly from one month.

---

# Appendix (round 2, snapshot 2a39447)

## 7. One unit cost and the stock value it feeds: FC-A-38-00202 (PEM101 stock item)

Method (METRICS Sec.1): unit cost = median of cost / qty over the last 12 months (Omni Channel, Actual and MPS rows, qty above 0). Cost in the database is a line total, so it is divided by qty first. Window 2025-09-22 to 2026-09-22.

1. Three rows: 2025-12-12 cost 2,916.76 / qty 7 = 416.68; 2026-06-25 905.68 / 2 = 452.84; 2026-07-07 5,886.92 / 13 = 452.84.
2. Exactly 3 rows, so no fallback. Median = **452.84 THB**; the recorded cost is 452.84.
3. Min from the page = 32.25 units (own Python gives 32.25). Contribution to Value of Min level = 32.25 × 452.84 = **14,604.09 THB**, equal to the page.
4. Items with fewer than 3 rows take the last row; items with no row (e.g. 02-05-R-0001) have no unit cost and are listed as no_unit_cost.
5. The gap found: 15 of the 92 PEM101 stock items (e.g. ST-F-11-0001, Min 3,002.5 × 2,388.94 = 7.17M) have a cost by this method but are not priced on the page, so the page adds 65,587,403.56 where Sec.6 gives about 82.36M.

## 8. One calibration member: HS-F-99-0213 (PEM101), member 0 of 37

Unit cost 741.13 THB; mean demand 6.5558 units a day (history 2024-01 to the last complete month). Min = 49.89 units, Max = 399.12 units. Validation not-late rate 73.3% (division 97.2%). Average stock 211.6 units = 156,834 THB. The Validator's own simulator reproduced this member, all 37 members and the 4,130-point grid.

## 9. Reserved de-duplication: the 13 groups

Cube_CES Backlog, 445 codes: 765 rows, 47,349 units. Grouped by contract and item: 749 groups, 13 with more than one row (29 rows). Keeping the first row leaves 749 rows, 43,410 units; 16 rows and 3,939 units go. Example effect: item CA-F-99-010203 available +11 becomes -19 when all lines count; item EEE-F-LT-1040020100 goes from -163 to -2,163. Every row in the 13 groups has a different PlanID and delivery dates, so none is a true duplicate.
