# Phase C — Sheet-to-Division Mapping (Explorer role)

**Question**: does each visible pricelist sheet name (PEM101, PEM102, PEM103, PEM104, PEM107,
CI101) safely stand in for the database `division` column, so Phase C can group its per-division
work by *sheet* instead of by `division`? Prior Phase C step-1 work (five parallel Validators,
one per division) found real division-tag problems at the edges of this assumption but never
tested it directly, consistently, across all six sheets with one method. This investigation does
that.

**Script**: `src/investigations/phaseC_sheet_division_mapping.py`. **Run**: 2026-09-04, against
the live `[salewarehouse].[dbo].[cube_Sale_APD]` table (still growing — see "Reproducibility"
note at the end). All figures below are cited to their exact CSV; nothing here is inferred
without a query behind it.

**Scope filter applied to every query**: `revenue_type = 'Omni Channel'` AND
`status IN ('Actual','MPS')`. This is this project's already-established Omni-Channel scope
convention (`STATUS.md` Locked Decisions: "All queries filter on `division='PEM101'` and
`revenue_type='Omni Channel'`... Status basis is Actual plus MPS"), applied here without the
`division='PEM101'` part (since `division` is exactly what this investigation is testing) so
these figures are directly comparable to every other Omni-Channel-scoped figure already recorded
in this project. **No date filter was applied** — every query is unrestricted by `createDate`, so
these figures cover the full history of the table, not just 2024+. This is a deliberate choice
for this task (which asks for "the full spread to detect mismatches"), not an oversight; it means
these totals are not directly comparable to any 2024+-only figure elsewhere in `STATUS.md`
without adjustment.

**Prior CSVs used for context only, not as this task's answer**: `output/summary/
phaseC_PEM102_check3_itemcode_division_split.csv`, `phaseC_PEM107_check3_itemcode_by_division.csv`
and `phaseC_CI101_check3_itemcode_by_division.csv` were glanced at for sanity-checking (they
correctly show the same qualitative pattern — PEM102/PEM107 legacy-tag crossover, CI101/PEM101
split). They are channel-blind (no `revenue_type` filter) and were computed by three different
Validators, so their exact numbers are not quoted as this task's figures; every number in this
report comes from this script's own fresh query.

## 1. Pricelist scope (Step 0)

`load_visible_product_rows("reference/pricelist.xlsx")` returned 446 product rows across the 6
visible sheets. One within-sheet duplicate was dropped (`DS-F-99-0308` on the `CI101` sheet,
appears twice — already known, `STATUS.md` Phase C step 1), leaving **445 distinct (sheet, code)
rows**. Confirmed directly (not assumed): no item code appears on more than one visible sheet, so
each code maps to exactly one sheet. The pricelist's own `business` column was cross-checked
against this task's stated sheet→home-division mapping and matches exactly for all 6 sheets
(script raises an error and stops if it doesn't — none did). Source: `output/summary/
phaseC_sheetmap_00_pricelist_scope.csv`.

| Sheet | Home division | Codes |
|---|---|---|
| PEM101-Version 2 | PEM101 | 171 |
| PEM102-Version 2 | PEM102 | 26 |
| PEM103-Version2 | PEM103 | 87 |
| PEM104 | PEM104 | 12 |
| PEM107 CT-Version 2 | PEM107 | 136 |
| CI101 | CI101 | 13 |

## 2 & 4. Per-sheet division breakdown and clean/not-clean verdict

**Confidence: high** for every figure in this table — each is a direct `GROUP BY itemcode,
division` query result (`output/summary/phaseC_sheetmap_01_raw_itemcode_division_query.csv`,
571 (itemcode, division) rows), aggregated per sheet
(`output/summary/phaseC_sheetmap_per_sheet_division_breakdown.csv` for the full division-by-
division breakdown; `output/summary/phaseC_sheetmap_per_sheet_summary.csv` for the summary below).

**Threshold, stated explicitly**: a sheet is **CLEAN** if ≥95% of its total Omni-Channel
(Actual+MPS) sale value falls under its own home division; **NOT CLEAN** otherwise.
`SHEET_CLEAN_THRESHOLD_PCT = 95.0` (named constant in the script, with the reasoning in its
comment): chosen as a round cut that sits clearly above the noise band this project already
treats as "small enough to document" (PEM101 itself is 99.58% clean under its own established
0.42%-excluded figure) and clearly below the two structural problems this investigation exists to
catch (CI101's prior-reported ~37% split, PEM102/PEM107's tag swap) — so a sheet only fails for a
large, structural mismatch, not ordinary small-value noise. This is a stated judgment call, not
derived from the data itself; a stricter or looser cut would move only the CI101/PEM102/PEM103/
PEM107 rows around within the "clearly not near 100%" vs "clearly near 100%" groups they already
fall into, not reverse any verdict below.

| Sheet | Home division | Total Omni-Channel value | Home-division value | Home % | Other divisions present | Verdict |
|---|---|---|---|---|---|---|
| PEM101-Version 2 | PEM101 | ฿818,722,747 | ฿808,862,328 | **98.80%** | PCE101, PDEMO, PPD101, PTS | **CLEAN** |
| PEM102-Version 2 | PEM102 | ฿160,959,175 | ฿116,297,117 | **72.25%** | PDEMO, PEM107-OLD, PPD101 | **NOT CLEAN** |
| PEM103-Version2 | PEM103 | ฿475,676,609 | ฿461,680,499 | **97.06%** | PCE101, PPD101 | **CLEAN** |
| PEM104 | PEM104 | ฿1,617,300 | ฿1,617,300 | **100.00%** | (none) | **CLEAN** |
| PEM107 CT-Version 2 | PEM107 | ฿414,226,834 | ฿218,004,892 | **52.63%** | PCE101, PDEMO, PEM102, PEM102-OLD, PEMCSA, PPD101, PPD102, PTS | **NOT CLEAN** |
| CI101 | CI101 | ฿166,485,438 | ฿104,089,870 | **62.52%** | PCE101, PEM101, PEM104 | **NOT CLEAN** |

Full division-by-division split for each sheet (row counts included) is in
`output/summary/phaseC_sheetmap_per_sheet_division_breakdown.csv`. Highlights (all figures from
that CSV):

- **PEM102-Version 2**: 116,297,117 (72.25%) under `PEM102`, **42,593,458 (26.46%) under
  `PEM107-OLD`**, small residuals under `PDEMO`/`PPD101`.
- **PEM107 CT-Version 2**: 218,004,892 (52.63%) under `PEM107`, **164,371,003 (39.68%) under
  `PEM102-OLD`**, 12,529,440 (3.02%) under `PPD101`, 12,315,144 (2.97%) under the *current*
  `PEM102` tag, plus small residuals under `PDEMO`/`PCE101`/`PTS`/`PPD102`/`PEMCSA`.
- **CI101**: 104,089,870 (62.52%) under `CI101`, **61,772,748 (37.10%) under `PEM101`**, small
  residuals under `PEM104`/`PCE101`.

**Conclusion (high confidence, directly confirmed)**: `PEM101`, `PEM103`, and `PEM104` sheets are
clean enough (≥95%) to use as the grouping key for Phase C's per-division scope without falling
back to `division`. `PEM102`, `PEM107`, and `CI101` sheets are **not** — for these three, the
database's own `division` column (with the specific cross-division values it actually carries)
must be used, not the sheet name alone, or a material share of each sheet's real Omni-Channel
demand will be missed.

## 3. Flagged codes

All figures directly confirmed from `output/summary/phaseC_sheetmap_per_item_division.csv` (571
rows) unless noted. Full lists are in the CSVs named below, not just counts.

### (a) Codes appearing under more than one division (within Omni-Channel scope)

**175 of 445 codes (39.3%)** appear under more than one division. By sheet:
CI101 11/13, PEM101-Version 2 50/171, PEM102-Version 2 12/26, PEM103-Version2 17/87,
PEM107 CT-Version 2 85/136, PEM104 0/12. Full list with each division and its row
count/value per code: `output/summary/phaseC_sheetmap_flagged_multi_division.csv`.

### (b) Codes with zero rows under their own sheet's home division, but rows under a different division

**13 codes**, all with a non-home division only:

| Sheet | Code | Home division (0 rows) | Division found instead | Rows | Sale |
|---|---|---|---|---|---|
| PEM107 CT-Version 2 | CT-F-99-020534 | PEM107 | PEM102-OLD | 1 | ฿85,500 |
| PEM107 CT-Version 2 | CT-F-99-020718 | PEM107 | PEM102-OLD | 1 | ฿83,744 |
| CI101 | DS-F-99-0320 | CI101 | PEM101 | 2 | ฿187,500 |
| PEM102-Version 2 | LB-F-99-G2261204-01 | PEM102 | PEM107-OLD | 3 | ฿1,128,000 |
| PEM102-Version 2 | LB-F-99-G2261205-01 | PEM102 | PEM107-OLD | 2 | ฿439,900 |
| PEM107 CT-Version 2 | RS-F-99-070019 | PEM107 | PEM102-OLD | 2 | ฿20,384 |
| PEM107 CT-Version 2 | RS-F-99-070021 | PEM107 | PEM102-OLD | 1 | ฿11,174 |
| PEM107 CT-Version 2 | RS-F-99-070024 | PEM107 | PEM102-OLD | 1 | ฿6,359 |
| PEM107 CT-Version 2 | RS-F-99-090002 | PEM107 | PEM102-OLD | 1 | ฿28,800 |
| PEM107 CT-Version 2 | RS-F-99-090038 | PEM107 | PEM102-OLD | 1 | ฿11,400 |
| PEM107 CT-Version 2 | RS-F-99-090039 | PEM107 | PEM102-OLD | 1 | ฿47,700 |
| PEM102-Version 2 | SL-F-99-S2461604-01 | PEM102 | PEM107-OLD | 1 | ฿610,000 |
| PEM107 CT-Version 2 | VT-F-99-010205 | PEM107 | PEM102-OLD | 2 | ฿119,000 |

By sheet: PEM107 CT-Version 2 (9), PEM102-Version 2 (3), CI101 (1). None on PEM101, PEM103, PEM104.
Source: `output/summary/phaseC_sheetmap_flagged_wrong_division.csv`.

### (c) Codes with no Omni-Channel (Actual/MPS) rows at all, under any division

**105 of 445 codes (23.6%)**, by sheet: PEM103-Version2 37, PEM101-Version 2 27,
PEM107 CT-Version 2 24, PEM102-Version 2 10, PEM104 7, CI101 0. Full list:
`output/summary/phaseC_sheetmap_flagged_no_division.csv`. This is a broader "no history in this
scope" flag, not a division-mapping problem per se — reported because the task asked for it, and
it overlaps conceptually with items already flagged elsewhere in this project's Phase B/Phase C
work as no-history candidates (`excluded_item_codes` / `placeholder_item_codes` in
`config/config.yaml`), which this script does not re-derive or reconcile — that reconciliation is
out of this task's scope (see "unresolved" below).

## 5. CI101 re-derivation (independent, not quoted from the prior report)

**Confidence: high**, directly confirmed by this script's own query.

- CI101-tagged Omni-Channel value for CI101's 13 codes: **฿104,089,870** (331 rows)
- PEM101-tagged Omni-Channel value for the same 13 codes: **฿61,772,748** (360 rows)
- Combined (CI101 + PEM101): **฿165,862,618**
- **PEM101 share of combined: 37.24%**

Source: `output/summary/phaseC_sheetmap_CI101_pem101_split_summary.csv` and
`output/summary/phaseC_sheetmap_CI101_detail.csv` (full per-code breakdown, all divisions).

**This matches the prior Phase C step-1 finding of 37.2% closely (37.24% vs. 37.2%, a 0.04
percentage-point difference)** — consistent with the earlier CI101 Validator's figure, computed
independently with this task's own fresh query and Omni-Channel/status scope (the prior figure's
exact filter combination was not re-verified line-by-line against this script's, so the near-exact
match is itself the evidence of consistency, not an assumption that the methods were identical).
CI101 also carries a further ฿622,820 (0.31% of its ฿166.5M total scope value) under `PEM104` and
`PCE101` not previously highlighted at this granularity — small in proportion, noted for
completeness (`output/summary/phaseC_sheetmap_CI101_detail.csv`).

**CI101's row in the per-sheet table above**: home_pct 62.52% (CI101-tagged) vs. 37.10%
(PEM101-tagged, matching the 37.24%-of-combined figure once PCE101/PEM104's small residual is
excluded from the denominator) — **NOT CLEAN** under the 95% threshold. Sheet cannot be used
alone as CI101's grouping key; `division IN ('CI101','PEM101')` (at minimum) is needed to capture
its real Omni-Channel demand, consistent with `config/config.yaml`'s current
`divisions_in_scope` note that "37.2% of its product value is recorded under division PEM101 and
is genuine Omni Channel demand — must be counted, not discarded."

## Summary table (all conclusions with confidence)

| Finding | Confidence | Evidence |
|---|---|---|
| PEM101 sheet clean (98.80%) | High, directly confirmed | per_sheet_summary.csv |
| PEM103 sheet clean (97.06%) | High, directly confirmed | per_sheet_summary.csv |
| PEM104 sheet clean (100.00%, n=12 items, very low value ฿1.6M) | High for the figure itself; low statistical weight given n=12 and PEM104's already-documented "blocked" status (STATUS.md) | per_sheet_summary.csv |
| PEM102 sheet NOT clean (72.25%, 26.46% under PEM107-OLD) | High, directly confirmed | per_sheet_summary.csv, per_sheet_division_breakdown.csv |
| PEM107 sheet NOT clean (52.63%, 39.68% under PEM102-OLD) | High, directly confirmed | per_sheet_summary.csv, per_sheet_division_breakdown.csv |
| CI101 sheet NOT clean (62.52%, 37.10% under PEM101) | High, directly confirmed | per_sheet_summary.csv, CI101_detail.csv |
| CI101/PEM101 37.24% split reproduces prior 37.2% figure | High, directly confirmed, independently re-derived | CI101_pem101_split_summary.csv |
| 175/445 codes span >1 division | High, directly confirmed | flagged_multi_division.csv |
| 13 codes exist only under a non-home division | High, directly confirmed | flagged_wrong_division.csv |
| 105/445 codes have zero Omni-Channel rows anywhere | High, directly confirmed | flagged_no_division.csv |
| *Why* PEM102/PEM107 tags swapped, or why CI101 splits across two divisions | **Not addressed here — out of Explorer scope per AGENTS.md.** STATUS.md already records this as unresolved, needing IT/business input; not re-litigated. | STATUS.md Phase C step 1 residual items |

## What remains unresolved

1. **Why** the PEM102/PEM107 legacy-tag pattern and the CI101/PEM101 split exist is not addressed
   here, per the Explorer role's boundary (AGENTS.md: "does not interpret business meaning") and
   `STATUS.md`'s own note that this needs IT/business confirmation, not further data digging.
2. **No date filter was applied** in this investigation (see scope note above) — these totals mix
   all history in the table, including pre-2024 rows. This project's other Omni-Channel figures
   are usually scoped to `createDate >= 2024-01-01`; a 2024+-only version of this same breakdown
   was not computed here (out of this task's stated scope) and could shift the exact percentages,
   though the qualitative pattern (which divisions each sheet's codes fall under) is unlikely to
   reverse given how large the PEM102/PEM107/CI101 splits are.
3. **The 105 "no Omni-Channel history anywhere" codes are not reconciled against this project's
   existing `excluded_item_codes`/`placeholder_item_codes` lists** in `config/config.yaml` (those
   lists cover only the PEM101 pilot's 128-item Category scope, a much smaller set than these 445
   codes) — that reconciliation was not requested by this task and was not attempted.
4. **The 13 "wrong-division-only" codes and the multi-division codes are reported as a pattern,
   not diagnosed** — some of the 13 may simply be low-volume codes whose sparse history happens
   to land under a neighbouring division; this script does not have enough evidence to distinguish
   that from a systematic mismatch at the individual-code level, and does not guess.
5. **Reproducibility caveat**: `cube_Sale_APD` is a live, still-growing table (documented
   repeatedly elsewhere in `STATUS.md`, e.g. Phase B's pull-to-pull growth notes). A re-run of
   this script on a later date will not reproduce these exact totals — the qualitative verdicts
   (which sheets are clean vs. not) are expected to be stable, but the percentages will drift by a
   small amount, consistent with every other pull-to-pull comparison already documented in this
   project.
