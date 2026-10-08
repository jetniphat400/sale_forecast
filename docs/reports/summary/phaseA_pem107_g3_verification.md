# Phase A, A2 — Should PEM107 be planned as made-to-order under G3?

Generated 2026-09-29. Dispatched as a read-only agent (AGENTS.md rule 10 — no tracked-file edits,
no commits, no pipeline entrypoints run). This is verification only: **no reclassification, page
edit, or config change was made as a result of this analysis.**

## Criteria (defined before computing, per this task's own instruction)

- **C1 Stability**: share of the 78 `confirmed_to_order` (CTO) items (task2b_part2_class_counts.csv/
  task2b_part2_item_level.csv, corrected 2026-09-29 S2 fix) that stay CTO under every one of the 6
  alternative single-axis threshold configs in §23 (mixed 50%/70%, S2 40%/60%, S3 7d/21d, others
  held at default 60%/50%/14d). Supports at ≥80%; also reported at 70% and 90%.
- **C2 Materiality**: share of PEM107 Omni Channel `cost` (cube_Sale_APD line total, Status='Actual'),
  2024-01-01 through the last **full** calendar month present in the data (2026-08-31 — 2026-09
  excluded as partial; this task's own operationalization of "last eligible month," stated
  explicitly), held by CTO items vs. `stock_policy` items. Material if CTO holds ≥50%; if
  `stock_policy` holds ≥70%, the move changes little.
- **C3 Viability**: per CTO item, before 2026-05-01 (Omni Channel scope): median notice
  (CtrDate→ForecastDelDate), median realized PO-to-delivery (CtrDate→ActualDelDate, delivered rows
  only), not_late (§19, ActualQty-weighted, ActualDelDate≤ForecastDelDate). Viable if median notice
  ≥ median PO-to-delivery **and** not_late ≥85% (also 80%/90%). "Behaves like stock whatever its
  label" = short notice **and** short delivery **and** high not_late.
- **C4 Reverse direction**: share of CTO items with on-hand stock (`Cube_Inventory_Exact`, any
  warehouse) > 0 now, valued at §1 unit_cost. Supports at ≤20%; also 10% and 30%.
- **C5**: of PEM107 Omni units delivered late (ActualDelDate>ForecastDelDate) with
  ForecastDelDate≥2026-05-01, share by §23 class; for late CTO rows, notice vs. realized
  PO-to-delivery.
- **C6 (supplementary, not part of the formal C1-C5 tie)**: Tendering `cost` share of each class's
  total Actual-channel value, same window as C2.

## Method / data access

One `Cube_CES` connection attempt (succeeded, no retry needed): pulled ItemCode/ContractID/Status/
CtrDate/ForecastDelDate/ActualDelDate/ActualQty/RevenueType for all 136 PEM107 pricelist codes
(21,610 rows — matches the pre-existing `task2b_part4_cube_ces_raw.csv` row count exactly, a
cross-check). C2/C6 reused the pre-existing, already-V2-confirmed
`output/data/phaseQ23_raw_sales_allchannels_351full.csv` (`cube_Sale_APD`, cost/qty/revenue_type/
division — division here is pricelist-derived via `config['sheet_to_division']`, confirmed by
reading `phaseQ23_explorer.py`, not a raw DB tag — PRICELIST RULE satisfied). C4 reused
`phaseE2_0_unit_cost.csv`. The classification-recompute function reproduced the stored §23 `class`
for all 112 PEM107 items exactly (0 mismatches) before being trusted for C1.

## Results

**C1 — Stability: 73/78 = 93.6%** remain `confirmed_to_order` under all 6 alternative configs.
Clears both the 80% and 90% bars. Per-axis: mixed_50 100%, mixed_70 94.9%, S2_40 100%, S2_60 100%,
S3_7 100%, S3_21 98.7%. **Supports the move.**

**C2 — Materiality** (2024-01 to 2026-08, Omni Channel Actual value, THB 225,254,636 total, 0
unmatched rows):

| Class | Value THB | Share |
|---|---|---|
| confirmed_to_order | 72,830,606 | 32.3% |
| conflict | 127,592,260 | 56.6% |
| stock_policy | 24,831,771 | 11.0% |

**Neither stated bar is met**: CTO is below the 50% "material" bar, and `stock_policy` is far below
the 70% "changes little" bar. **C2 is inconclusive under its own stated criteria** — most value
(56.6%) actually sits in `conflict`, a class this criterion doesn't address. Reported as a gap in
the criterion, not resolved by re-defining it.

**C3 — Viability** (before May 2026): 77/78 CTO items have all three figures computable (1 item has
zero pre-May `Cube_CES` rows). Viable (notice ≥ delivery **and** not_late ≥ bar):

| Bar | Viable count | Share of computable (77) | Share of all 78 |
|---|---|---|---|
| 80% | 46 | 59.7% | 59.0% |
| **85%** | **41** | **53.2%** | **52.6%** |
| 90% | 37 | 48.1% | 47.4% |

Median across computable items: notice 30.0 days, PO-to-delivery 33.0 days, not_late 91.7%. Only
**3/77** are flagged "behaves like stock whatever their label" (short notice + short delivery +
high not_late) — not a dominant pattern. **C3 is marginal — roughly half the class passes, not a
strong signal either direction.**

**C5 — Where the 2026 delay sits** (1,144 units delivered late from May 2026, Omni Channel):

| Class | Late units | Share |
|---|---|---|
| conflict | 722 | 63.1% |
| confirmed_to_order | 334 | 29.2% |
| stock_policy | 88 | 7.7% |

The 2026 delay is concentrated in `conflict`, **not** `confirmed_to_order`. For the 15 late CTO
rows (334 units): median notice 93 days, median realized PO-to-delivery 94 days — 100% had
notice < realized-time, but **this is tautological**: any row classified "late" has
ActualDelDate > ForecastDelDate by construction, so realized time exceeding planned time is
guaranteed, not an independent finding. Flagged explicitly so it is not misread as evidence.

**C4 — Reverse direction: 10/78 = 12.8%** hold on-hand stock > 0, value THB 1,522,858 (all 10 have
a computable unit_cost). Within the ≤20% "supports" bar (not within ≤10%; within ≤30%). **Supports
the move** — few CTO items hold stock, and it is a small value relative to the class's ~THB 73M
Omni value (~2%).

**C6 — Tendering value share by class** (same window as C2, supplementary): confirmed_to_order
**73.1%**, stock_policy 64.0%, conflict 35.7%. CTO is the *most* Tendering-driven class —
consistent with an MTO/Tendering-pipeline characterization (supplementary support, not part of the
formal C1-C5 verdict tie).

## 30 conflict items — C3/C4/C5 lean

Own operationalization (stated explicitly): "leaning stock" = holds on-hand stock **and** (short
notice **or** not_late≥85%); "leaning made-to-order" = notice ≥ delivery time **and** no stock;
else "undetermined."

| Product Type | Product Description | Product Code | Median notice (d) | Median PO→delivery (d) | not_late % | On-hand qty | Stock value (THB) | Late units (May 2026+) | Lean |
|---|---|---|---|---|---|---|---|---|---|
| Current Transformer Type CExL | CExL-24 : 10/5A, 30VA, Cl.0.5Fs10 | RS-F-99-041001 | 41.0 | 34.0 | 95.2 | 0 | 0 | 20 | leaning made-to-order |
| Current Transformer Type CExL | CExL-24 : 25/5A, 30VA, Cl.0.5Fs10 | RS-F-99-041003 | 41.5 | 41.5 | 100.0 | 0 | 0 | 0 | leaning made-to-order |
| Current Transformer Type CExL | CExL-24 : 75/5A, 30VA, Cl.0.5Fs10 | RS-F-99-041015 | 59.0 | 49.0 | 94.1 | 0 | 0 | 0 | leaning made-to-order |
| Current Transformer Type CExL | CExL-24 : 20/5A, 30VA, Cl.0.5Fs10 | RS-F-99-041033 | 64.5 | 51.0 | 95.9 | 0 | 0 | 20 | leaning made-to-order |
| Current Transformer Type COL | COL-24 : 10/5A, 30VA, Cl.0.5 | CT-F-99-020501 | 27.0 | 19.0 | 83.6 | 17 | 108,799 | 153 | undetermined |
| Current Transformer Type COL | COL-24 : 20/5A, 30VA, Cl.0.5 | CT-F-99-020502 | 15.0 | 14.0 | 82.4 | 8 | 55,914 | 70 | undetermined |
| Current Transformer Type COL | COL-24 : 75/5A, 30VA, Cl.0.5 | CT-F-99-020505 | 15.0 | 14.0 | 87.4 | 22 | 149,833 | 33 | leaning stock |
| Current Transformer Type COL | COL-24 : 150/5A, 30VA, Cl.0.5 | CT-F-99-020507 | 15.0 | 14.0 | 83.1 | 4 | 30,036 | 23 | undetermined |
| Current Transformer Type COL | COL-24 : 200/5A, 30VA, Cl.0.5 | CT-F-99-020508 | 16.0 | 13.0 | 91.6 | 22 | 179,872 | 7 | leaning stock |
| Current Transformer Type COL | COL-24 : 300/5A, 30VA, Cl.0.5 | CT-F-99-020510 | 14.0 | 13.5 | 89.8 | 20 | 174,902 | 6 | leaning stock |
| Current Transformer Type COL | COL-24 : 400/5A, 30VA, Cl.0.5 | CT-F-99-020511 | 19.0 | 18.5 | 94.2 | 14 | 125,598 | 0 | leaning stock |
| Current Transformer Type COL | COL-24 : 500/5A, 30VA, Cl.0.5 | CT-F-99-020512 | 30.5 | 28.5 | 94.6 | 0 | 0 | 6 | leaning made-to-order |
| Current Transformer Type COL | COL-24 : 150:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020524 | 18.0 | 18.0 | 82.8 | 9 | 121,317 | 10 | undetermined |
| Current Transformer Type COL | COL-24 : 50:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020525 | 12.0 | 11.0 | 82.8 | 8 | 139,635 | 3 | undetermined |
| Current Transformer Type COL | COL-24 : 400:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020526 | 16.0 | 13.0 | 92.3 | 5 | 96,522 | 9 | leaning stock |
| Current Transformer Type COL | COL-24 : 100:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020527 | 15.0 | 12.0 | 89.5 | 6 | 81,564 | 12 | leaning stock |
| Current Transformer Type COL | COL-24 : 200:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020528 | 15.0 | 15.0 | 83.8 | 6 | 91,177 | 6 | undetermined |
| Current Transformer Type COL | COL-24 : 300:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020530 | 15.0 | 13.5 | 85.0 | 7 | 108,935 | 3 | undetermined |
| Current Transformer Type COL | COL-24 : 75:5/5A, 30VA, Cl.0.5&5P20 (2 Core) | CT-F-99-020531 | 14.0 | 13.0 | 94.1 | 0 | 0 | 6 | leaning made-to-order |
| Current Transformer Type LDB | LDB-35 : 150/5A, 5VA, Cl.0.5 | RS-F-99-070002 | 30.0 | 28.0 | 97.8 | 208 | 90,482 | 160 | leaning stock |
| Current Transformer Type LDB | LDB-35 : 250/5A, 5VA, Cl.0.5 | RS-F-99-070004 | 30.0 | 26.0 | 98.8 | 35 | 10,939 | 0 | leaning stock |
| Current Transformer Type LDB | LDB-35 : 400/5A, 5VA, Cl.0.5 | RS-F-99-070005 | 30.0 | 26.0 | 99.3 | 101 | 31,640 | 30 | leaning stock |
| Current Transformer Type LExM | LExM-55 : 400/5A 5 VA Class 0.5 | RS-F-99-090011 | 9.0 | 12.0 | 50.0 | 0 | 0 | 0 | undetermined |
| Voltage Transformer Type VOG | VOG-242 : 22000/√3:110/√3V 500VA, Cl.3 For LBS Op.5 & 6 | VT-F-99-010701 | 9.0 | 9.0 | 80.0 | 26 | 472,058 | 0 | undetermined |
| Voltage Transformer Type VOG | VOG-242 : 22000/√3:110/√3&110/√3V 50VA, Cl.0.5&3P (yn0&yn0) | VT-F-99-010721 | 14.0 | 13.0 | 87.9 | 21 | 379,332 | 50 | leaning stock |
| Voltage Transformer Type VOG | VOG-362 : 33000/√3:110/√3&110/√3V 50VA, Cl.0.5&3P (yn0&yn0) | VT-F-99-010819 | 27.0 | 25.0 | 74.0 | 1 | 22,249 | 2 | undetermined |
| Voltage Transformer Type VOL | VOL-24 : 22000/230V, 500VA, Cl.3 | VT-F-99-010202 | 28.0 | 24.5 | 63.9 | 9 | 80,382 | 10 | undetermined |
| Voltage Transformer Type VOL | VOL-24 : 22000/110V, 50VA, Cl.0.5 (Private) | VT-F-99-010203 | 11.0 | 11.0 | 95.0 | 31 | 240,994 | 83 | leaning stock |
| Voltage Transformer Type VOL | VOL-24 : 22000/110V, 500VA, Cl.3 For LBS Op.4 | VT-F-99-010205 | 9.0 | 8.0 | 100.0 | 8 | 74,138 | 0 | leaning stock |
| Voltage Transformer Type VOL | VOL-36 : 33000/110V, 50VA, Cl.0.5 (PEA Regional) | VT-F-99-010303 | 24.0 | 24.0 | 84.8 | 5 | 47,794 | 0 | undetermined |

**Counts: 12 leaning stock, 6 leaning made-to-order, 12 undetermined.**

## Verdict — tied explicitly to C1-C5

**Supported for a subset, not the full 78-item class.** C1 (93.6% stable) and C4 (12.8% hold
stock, small value) both clearly support treating `confirmed_to_order` as made-to-order. But C2 is
inconclusive under its own stated bars (most value, 56.6%, sits in `conflict`, which this criterion
doesn't cover), and C3 — the direct viability test — only clears the 85% bar for 41/77 computable
items (53%), meaning roughly half the class does not currently meet the stated viability bar. C5
shows the 2026 delay problem is **not** concentrated in this class (only 29.2% of late units), so
it is not evidence for reclassification either way. **The verdict holds without C6** (supplementary,
not part of the C1-C5 tie) but **does not hold uniformly across all 78 items**, given C3's 47%-fail
rate.

**Recommended subset (41 codes, those passing C3 viability at the 85% bar)**: CT-F-99-020513,
CT-F-99-020522, CT-F-99-020529, CT-F-99-020534, CT-F-99-020701, CT-F-99-020708, CT-F-99-020709,
CT-F-99-020714, CT-F-99-020718, CT-F-99-020722, RS-F-99-010114, RS-F-99-010122, RS-F-99-010123,
RS-F-99-010127, RS-F-99-010128, RS-F-99-010129, RS-F-99-041002, RS-F-99-041004, RS-F-99-041006,
RS-F-99-041007, RS-F-99-041010, RS-F-99-041034, RS-F-99-041035, RS-F-99-050023, RS-F-99-050128,
RS-F-99-070006, RS-F-99-070007, RS-F-99-070019, RS-F-99-070021, RS-F-99-070024, RS-F-99-090002,
RS-F-99-090003, RS-F-99-090026, RS-F-99-090028, RS-F-99-090038, RS-F-99-090039, RS-F-99-090041,
VT-F-99-010105, VT-F-99-010615, VT-F-99-010616, VT-F-99-010722.

The other 37 CTO items are stable under §23's own alternative thresholds (C1) and mostly don't hold
stock (C4), but fail the direct delivery-viability test (C3) — a genuine open question for the
business, not resolved by this analysis alone.

## Noticed but out of scope (reported, not pursued — per SCOPE RULE)

The `conflict` class carries both the most Omni value (56.6%, C2) and the most 2026 late-delivery
volume (63.1%, C5) — a materially bigger open question than the CTO/G3 question this task
addresses. Reported here, not acted on.

## Validator cross-check (A6, dispatched as a fresh agent, no shared context with A2)

Read none of this report; independently recomputed from METRICS.md's own definitions plus
pre-existing (pre-Phase-A) data files. 3 database connection attempts, all succeeded, no retries.

| Check | Target (A2) | Validator recompute | Verdict |
|---|---|---|---|
| C2 class shares | conf_to_order THB 72,830,606 (32.3%); conflict THB 127,592,260 (56.6%); stock_policy THB 24,831,771 (11.0%); total THB 225,254,636 | THB 72,830,605.65; 127,592,259.91; 24,831,770.67; total 225,254,636.23 | **MATCH** (exact to the THB) |
| C4 reverse stock | 10/78 = 12.8%, value THB 1,522,858 | 10/78 = 12.8%, value THB 1,522,857.60 (same 10 items named) | **MATCH** (exact) |
| C5 late units by class | conflict 722 (63.1%); confirmed_to_order 334 (29.2%); stock_policy 88 (7.7%); total 1,144 | conflict 722 (63.1%); confirmed_to_order 334 (29.2%); stock_policy 88 (7.7%); total 1,144 | **MATCH** (exact) |

**C3 for the 5 highest-value confirmed_to_order items** (no target given — the Validator was asked
to compute this fresh and independently re-derive the top-5 set itself): it re-derived the
identical top-5 items in the identical value order (VT-F-99-010722 THB 26.0M, VT-F-99-010820
THB 8.2M, RS-F-99-090028 THB 4.6M, RS-F-99-041002 THB 2.6M, RS-F-99-070006 THB 2.3M), confirming
the item set used in this report is correct. Its own C3 computation:

| Item | n | Median notice (d) | Median realized PO→delivery (d) | not_late | Clears 85% bar |
|---|---|---|---|---|---|
| VT-F-99-010722 | 48 | 31.0 | 29.0 | 99.88% | YES |
| VT-F-99-010820 | 16 | 35.5 | 34.5 | 98.42% | YES |
| RS-F-99-090028 | 10 | 31.0 | 28.5 | 98.20% | YES |
| RS-F-99-041002 | 13 | 43.0 | 40.0 | 100.00% | YES |
| RS-F-99-070006 | 25 | 66.0 | 63.0 | 89.58% | YES |

All 5 of the highest-value confirmed_to_order items independently clear the viability bar —
reinforces (does not by itself resolve) the C3 finding that a real subset of the class is viable
for reclassification, even though roughly half the full 78-item class does not clear that bar.

**Overall**: every Validator-checked figure in this report MATCHES exactly. Level **V2** for C2,
C4, C5 and C3-on-the-top-5 (independent recomputation, different session, exact or near-exact
agreement).
