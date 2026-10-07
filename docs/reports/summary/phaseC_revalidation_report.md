# Phase C — Full-Scope Re-Validation on the Division Source-of-Truth Basis (2026-09-04)

**Why this exists**: the 2026-09-04 "Division source-of-truth correction" (`STATUS.md` Locked
Decisions) removed the database `division` column as a query filter — the pricelist alone now
determines an item's division, and every Omni-Channel row for an item's code counts, `-OLD`-tagged
rows included. All data-quality work up to and including the sheet-mapping task
(`phaseC_sheetmap_report.md`) was performed on the *filtered* basis. Removing the filter admits
rows never examined before. This report re-runs the checks that matter on the new basis, across
all 445 visible-pricelist item codes.

**Script**: `src/investigations/phaseC_full_scope_revalidation.py`. **Run**: 2026-09-04, live
against `[salewarehouse].[dbo].[cube_Sale_APD]` and `[salewarehouse].[dbo].[Cube_CES]`. Every
figure below is cited to its CSV; nothing here is inferred without a query behind it.

**Scope filter applied**: `revenue_type = 'Omni Channel'` AND `status IN ('Actual','MPS')`, no
`division` filter, **no `createDate` date filter** (deliberate — the point is to see the full
history spread, matching the sheet-mapping task's method, not this project's usual
`>=2024-01-01` modelling window). Confirmed: 0 negative qty/sale rows.

## 0. Sheet uniqueness (re-confirmed)

**Confidence: high, directly confirmed.** 446 product rows loaded from the 6 visible sheets; one
already-known within-sheet duplicate (`DS-F-99-0308` on `CI101`) dropped, leaving 445 distinct
codes. **No item code appears on more than one visible sheet** — confirmed by a `groupby(code)`
sheet-count check that would have raised an error and stopped the script if any code had. Source:
`phaseC_revalidation_00a_pricelist_scope.csv`.

## 1. Totals per division, before vs after (Part 3 item "Totals")

**Confidence: high, directly queried.** "BEFORE" = rows where `division_db_raw` equals the item's
pricelist home division only (what every prior loader's `WHERE division = '{division}'` clause
captured). "AFTER" = this pull, no division filter at all. Source:
`phaseC_revalidation_02_totals_before_after_per_division.csv`.

| Division | Rows before | Rows after | Value before (THB) | Value after (THB) | Value delta | Delta % |
|---|---|---|---|---|---|---|
| CI101 | 331 | 694 | 104,089,870 | 166,485,438 | +62,395,568 | **+59.94%** |
| PEM101 | 28,691 | 28,828 | 808,862,328 | 818,722,747 | +9,860,419 | +1.22% |
| PEM102 | 317 | 459 | 116,297,117 | 160,959,175 | +44,662,058 | **+38.40%** |
| PEM103 | 1,245 | 1,289 | 461,680,499 | 475,676,609 | +13,996,110 | +3.03% |
| PEM104 | 12 | 12 | 1,617,300 | 1,617,300 | 0 | 0.00% |
| PEM107 | 3,430 | 5,451 | 218,004,892 | 414,226,834 | +196,221,942 | **+90.01%** |

**Reading this**: PEM107 nearly doubles (its 2024 history, previously invisible under the
`PEM107`-only filter, is now counted), PEM102 gains 38%, CI101 gains 60% (its `PEM101`-tagged
37.2% share, now automatically included — matches the prior sheet-mapping finding, see §5 of
`phaseC_sheetmap_report.md`). PEM101 and PEM103 move only slightly (they were never part of the
`-OLD` mirror pattern; their small deltas are the same kind of minor cross-division residue the
sheet-mapping task already found). PEM104 is unchanged — none of its 12 transactions carry any
non-home division tag.

## 2. Double-counting between `-OLD`-tagged and normally-tagged rows (Part 3 item "highest-risk check")

**Confidence: high, directly queried and classified.** Method: for every `(contractid, itemcode)`
pair with at least one row under an `-OLD`-suffixed `division_db_raw` and at least one row under a
non-`-OLD` `division_db_raw`, the pair is a **CONFIRMED DUPLICATE** only if `qty`, `sale` AND
`forecast_date` all match exactly between the two rows (this project's established split-lot key,
e.g. the "Deep investigation of the 29 remaining confirmed duplicate sets" entry in `STATUS.md`) —
otherwise it is a distinct order or instalment, not a double count.

- 2,049 of 36,733 rows (5.6%) sit under an `-OLD`-suffixed division; 34,684 under a non-`-OLD`
  division.
- **11 candidate `(contractid, itemcode)` row-pairs found** — all involving `PEM102`↔`PEM107-OLD`
  or `PEM107`↔`PEM102-OLD`, consistent with the already-known mirror pattern.
- **0 of 11 are CONFIRMED DUPLICATES.** Every candidate pair differs on at least one of qty, sale,
  or `forecast_date` — most commonly `forecast_date` (e.g. contract `CTR-2024-06014`, item
  `VT-F-99-010721`: identical qty=1/sale=44,000 under both tags, but `forecast_date` 2024-11-29
  vs. 2024-12-06 — a different delivery tranche, not the same order recorded twice). Full detail:
  `phaseC_revalidation_03_old_tag_candidates.csv` (11 rows, all `distinct_order_or_instalment`);
  `phaseC_revalidation_03_old_tag_confirmed_duplicates.csv` (0 rows).
- **Conclusion: no double-counting was found between `-OLD`-tagged and normally-tagged rows in
  this data.** The 11 candidates are consistent with genuine multi-tranche orders that happened to
  be entered under different division tags at different times (the same phenomenon already
  documented for the `PEM102`/`PEM107` tag transition), not evidence of the same sale being
  recorded twice. This is a **negative finding, stated with high confidence given the method, but
  bounded**: it only tests the specific 5-field exact-match key already established as this
  project's duplicate signal; it cannot rule out a duplicate that happens to differ on one of
  those fields for an unrelated reason (the same limitation this project's `Cube_CES`
  false-negative-rate finding already flagged for its normal within-division duplicate checks).

## 3. Cube_CES reconciliation per division (Part 3 item "re-run on the new basis")

**Confidence: high, directly queried**, using this project's established 5-field key
(`contractid`/`ContractID`, `itemcode`/`ItemCode`, `createDate`/`CtrDate`, mapped
Actual↔Actual/MPS↔Backlog status, `qty`↔`ActualQty`-or-`BacklogQty`), same method as Phase C
step 1's per-division Check 7, now run on the unfiltered pull and grouped by pricelist division.
Source: `phaseC_revalidation_04_cube_ces_reconciliation_per_division.csv` (detail:
`phaseC_revalidation_04_cube_ces_merge_detail.csv`).

| Division | APD rows | Matched in Cube_CES | Match rate |
|---|---|---|---|
| CI101 | 698 | 688 | 98.57% |
| PEM101 | 29,166 | 29,059 | **99.63%** |
| PEM102 | 469 | 463 | 98.72% |
| PEM103 | 1,291 | 1,275 | 98.76% |
| PEM104 | 12 | 12 | 100.00% |
| PEM107 | 5,781 | 5,738 | 99.26% |

PEM101's rate (99.63%) is close to, though not identical to, the 99.79% figure recorded elsewhere
in `STATUS.md` — expected, since this pull's row count (29,166) differs slightly from that
figure's own scope/pull (this table is a live, growing table, already documented elsewhere in
`STATUS.md` as never reproducing exactly pull-to-pull). All six divisions sit in the same
98.5-100% band this project has treated as evidence of a well-understood, low-noise table
throughout Phase C step 1 — **note the same caveat `phaseC_synthesis_report.md` §2 already
raised: these rates are not all computed with identical rigor across every prior report, though
this specific re-run used one consistent method across all six divisions in one pass.**

## 4. Usable date range per division (Part 3 item "re-derive now that -OLD rows are included")

**Confidence: high, directly queried.** Source:
`phaseC_revalidation_05_usable_date_range_per_division.csv`.

| Division | Rows | createDate min | createDate max |
|---|---|---|---|
| CI101 | 694 | 2024-01-08 | 2026-09-02 |
| PEM101 | 28,828 | 2024-01-03 | 2026-09-03 |
| **PEM102** | 459 | **2024-01-24** | 2026-09-01 |
| PEM103 | 1,289 | 2024-01-04 | 2026-09-03 |
| PEM104 | 12 | 2025-03-07 | 2026-08-19 |
| **PEM107** | 5,451 | **2024-01-03** | 2026-09-03 |

**Confirms the expected consequence stated in `STATUS.md` before this re-validation was run**:
PEM102 and PEM107, previously limited to ~January 2025 under the `-OLD`-excluded basis, now show
usable history back to **January 2024** — a full year regained for both, consistent with the
Phase C step 1 finding that each division's real 2024 activity sat under the other's `-OLD` tag.

## 5. No-history recount and consolidated classification (Part 3 item "recount and reconcile")

**Confidence: high for the count itself, directly queried; the classification recommendation
below is out of this check's scope (Explorer/Validator boundary, `AGENTS.md`) and is reported as
an open item, not a decision.** Source:
`phaseC_revalidation_06_consolidated_item_status_445.csv` (one row per code, all 445, columns:
`has_omni_history_new_basis`, `in_config_excluded_item_codes`, `in_config_placeholder_item_codes`,
`status`).

- **105 of 445 codes (23.6%) have zero Omni-Channel rows anywhere in `cube_Sale_APD` on the new
  (unfiltered) basis — unchanged from the 105 figure found under the `-OLD`-excluded basis
  (`phaseC_sheetmap_report.md`).** This is expected, not a coincidence: removing the division
  filter only adds rows for codes that already have *some* `cube_Sale_APD` history under a
  different division tag. It cannot add a code that has zero rows in `cube_Sale_APD` under any
  division — none of these 105 codes' evidence, if any exists at all, lives in that table.
- **Reconciliation against the existing 128-item-scope config lists** (`excluded_item_codes`, 6
  codes; `placeholder_item_codes`, 10 codes — both scoped to the PEM101 pilot's Fuse+Surge
  Category, a subset of these 445):
  - All **6 `excluded_item_codes`** are among the 105 no-history codes — **consistent, no
    conflict.**
  - All **10 `placeholder_item_codes`** are also among the 105 no-history codes — **consistent,
    not a conflict**, despite the script's own log initially flagging these as "CONFLICT: needs
    re-check." Checked directly against `output/summary/task2_per_item_classification_final.csv`:
    every one of these 10 items' `has_any_row_cube_Sale_APD_nofilter` column is already `False` —
    their placeholder classification was based on evidence in `Cube_CES`/inventory tables, **not**
    `cube_Sale_APD`, precisely because they have no `cube_Sale_APD` rows under any filter. Their
    presence among the 105 confirms, rather than contradicts, their existing classification. (The
    script's literal "CONFLICT" label was a false alarm from too-simple logic — corrected here,
    not silently left in the raw log.)
  - **0 codes with real history on the new basis are wrongly listed as excluded or placeholder** —
    checked directly, no genuine conflicts exist.
  - **89 of the 105 no-history codes are NOT YET covered by either existing config list** —
    genuinely new information, since the existing lists only ever covered the 128-item PEM101
    pilot scope, not these 445. By sheet: PEM103 37, PEM107 24, PEM101 (non-Fuse/Surge codes) 11,
    PEM102 10, PEM104 7, CI101 0.
- **This resolves the "recount" part of Part 3 cleanly (105, same as before, high confidence) but
  the classification (exclude vs. placeholder vs. something else) for the 89 not-yet-covered codes
  is NOT decided here** — per `AGENTS.md`, classifying real business meaning onto these codes is
  an Orchestrator/business decision, not a Validator/Explorer one, and this project's own
  precedent (`task2_per_item_classification_final.csv`) used multi-table evidence (Cube_CES,
  inventory, quotations) this check did not gather. **This is the same open item Phase C step 1
  already flagged** ("Per-division no-history-item classification... has not been done for any of
  the five divisions") — now quantified precisely for the full 445-code scope rather than left as
  an unquantified gap, but still open.

## Summary table (all conclusions with confidence)

| Finding | Confidence | Evidence |
|---|---|---|
| No item code on more than one visible sheet | High, directly confirmed | 00a_pricelist_scope.csv |
| Totals shift materially for CI101 (+59.94%), PEM102 (+38.40%), PEM107 (+90.01%) once division filter removed; PEM101/PEM103 shift slightly; PEM104 unchanged | High, directly queried | 02_totals_before_after_per_division.csv |
| 0 confirmed duplicates between -OLD-tagged and normally-tagged rows (of 11 candidates) | High, directly queried and classified | 03_old_tag_candidates.csv |
| Cube_CES reconciliation 98.57%-100.00% across all six divisions | High, directly queried, one consistent method | 04_cube_ces_reconciliation_per_division.csv |
| PEM102 and PEM107 usable-from date moves to January 2024 (from ~January 2025) | High, directly queried, confirms the pre-stated expectation | 05_usable_date_range_per_division.csv |
| 105/445 codes have no Omni-Channel history anywhere (unchanged count); 16 already classified (consistent); 89 not yet classified | High for the count; classification itself out of scope | 06_consolidated_item_status_445.csv |

## What remains unresolved

1. **Why** the PEM102/PEM107 `-OLD` tag pattern exists is still not addressed by this check —
   unchanged from Phase C step 1's own finding, still needs IT/business confirmation.
2. **Classification (exclude/placeholder/needs-more-evidence) for the 89 not-yet-covered
   no-history codes** — quantified here, not decided. A future task in the shape of the existing
   `task2_per_item_classification_final.csv` investigation, extended to these 89 codes, would be
   the natural next step, not attempted here (stopping rule, `AGENTS.md`).
3. **The double-counting check's negative finding is method-bound** — it only rules out the exact
   5-field-match signal already established as this project's duplicate key; a duplicate that
   differs on one of those fields for an unrelated reason would not be caught by this check (same
   class of limitation as this project's existing `Cube_CES` false-negative-rate finding).
4. **No date filter (`createDate >= 2024-01-01`) was applied in this check** — deliberately, to see
   the full spread, matching the sheet-mapping task's method. A 2024+-only version of the
   before/after totals was not computed here; the qualitative pattern (which divisions shift
   materially) is expected to persist given how concentrated the PEM102/PEM107/CI101 effects are
   in the date-range evidence above, but the exact percentages would differ under a 2024+-only cut.
5. **`cube_Sale_APD` is a live, still-growing table** (documented repeatedly elsewhere in
   `STATUS.md`) — a re-run on a later date will not reproduce these exact totals; the qualitative
   conclusions are expected to be stable.
