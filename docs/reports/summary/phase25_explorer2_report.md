# Phase 25, Explorer 2: PEM107 — any column, anywhere, that changed around May 2026

**Task**: independent of the batch-linkage (`cube_final.jobno` <-> `Cube_CES.OLMJobCode`) test
another agent is running, search EVERY categorical column across `cube_Sale_APD`, `Cube_CES` and
`cube_final` for a PEM107 change point around May 2026, the month the business says Tendering and
Omni Channel production/stock were separated (DATA_MAP.md, "Business-confirmed, 2026-09-24").

**Scope**: PEM107, 136 codes from `output/data/phaseI_combined_scope_351items.csv` (pricelist-
authoritative; the database's own `division` column is reference-only per CONVENTIONS.md and is
never used as a filter — confirmed applied here: every SQL pull below filters on `itemcode`/
`ItemCode` only).

**Data access**: ONE connection attempt, all queries in one script/session
(`src/investigations/phase25_explorer2_pull.py`) — 3 `INFORMATION_SCHEMA.COLUMNS` schema probes
plus 3 data pulls. Succeeded on the first and only attempt; no retry was needed or used.
Rows pulled: `cube_Sale_APD` 5,687, `Cube_CES` 21,598, `cube_final` 8,723 (all itemcode-scoped, no
date filter at SQL level, per `src/cube_final_pull.py`/`src/cube_ces_pull.py`'s established
pattern). Analysis in a second, DB-free script (`src/investigations/phase25_explorer2_analysis.py`)
reading the saved raw CSVs.

**Methodology / date keys used (stated explicitly, since none is dictated by METRICS.md for this
question)**:
- `cube_Sale_APD`, `Cube_CES`: bucketed by `forecast_date` / `ForecastDelDate` (the scheduled-
  delivery-date concept, DATA_MAP.md Sec.2) — chosen for consistency with this project's
  established forecast_date-keyed `not_late`/June-2026 delivery-performance drop (METRICS.md
  Sec.16/19; DATA_MAP.md's June 2026 `not_late` 84.3%→46.0% finding).
- `cube_final`: bucketed by `final_date` (the production-batch completion date used throughout this
  project's cube_final work, e.g. Trap 21/22 and the prior Explorer A jobno/OLMJobCode test).
- Channel: `revenue_type` (`cube_Sale_APD`) / `RevenueType` (`Cube_CES`, native). **`cube_final` has
  no channel field of its own**, and `cube_final.ctrno` <-> `contractid`/`ContractID` is still "H"
  (never confirmed, DATA_MAP.md §3) — joining it to a channel-bearing table was out of scope for
  this task's one-connection budget. `cube_final` findings below are reported **unsplit by
  channel**; this limitation is stated, not silently worked around.
- Comparison window: April 2026 vs June 2026 (the months bracketing the claimed May 2026 split),
  but every column was also plotted month-by-month from January 2025 to the latest available data
  (through 2026-09, plus a thin tail of forward-dated 2026-10 to 2027-03 rows that are excluded
  from interpretation as low-n future bookings) so an April-vs-June difference could be checked
  against the whole series, not read off two isolated months.

**Privacy scrub**: raw CSVs below have customer names/IDs, contract IDs (`contractid`/`ContractID`),
PO/contract reference numbers (`ctrno`, `pono`), the customer-serial field (`cus_serialno`) and
employee-name fields (`fg_check_by/name`, `fg_pack_name`, `fg_final_by/name`) removed before being
written (repo is public, per this task's instructions).

Full data: `phase25_explorer2_cube_Sale_APD_raw.csv`, `phase25_explorer2_Cube_CES_raw.csv`,
`phase25_explorer2_cube_final_raw.csv`, `phase25_explorer2_schema_*.csv` (three full live schemas),
`phase25_explorer2_apr_vs_jun_2026_comparison.csv`, `phase25_explorer2_monthly_distributions_jan2025_onward.csv`,
`phase25_explorer2_cube_final_division_monthly.csv`, `phase25_explorer2_cube_final_division_item_flips.csv`,
`phase25_explorer2_row_counts_by_month_channel.csv` — all in `output/summary/`.

---

## 1. Warehouse/location field — CONFIRMED still absent (V2, direct schema check)

Full live schema pulled via `INFORMATION_SCHEMA.COLUMNS` this session: `cube_Sale_APD` 62 columns,
`Cube_CES` 41 columns, `cube_final` 35 columns. Searched every column name (case-insensitive) for
`warehouse`, `wh`, `stock`, `location`, `plant`, `line`: **zero matches in all three tables.** This
directly re-confirms DATA_MAP.md's existing claim ("no sales-order-level table... carries a
warehouse field at all") against this session's own live pull, not by assuming it still holds.

## 2. HEADLINE FINDING: `cube_final.division` shows a clean, item-level step change — and it lands in May 2026

`cube_final`'s own `division` field (DATA_MAP.md Trap 22: **a separate internal grouping from the
sales-side division taxonomy**, values are bare numeric codes like `'102'`, `'103'`, `'107'`, not
`PEM10x` strings) shows the single clearest change point found in this entire search:

| month range | `division` value | share |
|---|---|---|
| 2023-01 through 2025-04 (28 months) | `102` | 100% every month |
| 2025-05 | `102` / `103` | 73.2% / 26.8% (transition month) |
| 2025-06 through 2026-04 (11 months) | `103` | 100% every month |
| **2026-05** | `103` / `107` | **4.6% / 95.4% (transition month)** |
| 2026-06 through 2026-09 | `107` | 99.3% → 100% |

(Full monthly counts: `phase25_explorer2_cube_final_division_monthly.csv`.)

**This is an item-level flip, not a compositional artifact.** Of the 71 PEM107-scope itemcodes with
`cube_final` rows on both sides of the 2026-04/2026-05 boundary, **65 (91.5%) flip cleanly from
`{102,103}` to exactly `{107}`, and 6 more show a partial flip (both codes present in the
transition), 0 show no change and 0 show any other pattern** — i.e. every single common item moves
toward `107`, none stays on `103`. (Evidence: `phase25_explorer2_cube_final_division_item_flips.csv`.)
Row counts stay in a normal range through the transition (April 187, May 152, June 150 — no
volume collapse), so this is not an artifact of items dropping out of scope.

**Confidence and caveats — read together, not separately:**
- The distributional fact itself (V1 — one Explorer pass this session, straightforward groupby,
  independently re-checkable from the raw CSV; not yet cross-checked by a second agent).
- **A near-identical step change happened exactly one year earlier, in May 2025** (`102`→`103`),
  with no business-confirmed reorg claimed for that date anywhere in DATA_MAP.md/STATUS.md as of
  this task. Both transitions land in May, one year apart, and the numeric jump the second time
  (`103`→`107`, skipping `104`/`105`/`106`) is not a simple "+1 per year" counter. **This is reported
  as a direct tension with treating the 2026-05 change as uniquely evidence of the business's
  specific claim: if this field relabels on some internal annual cycle unrelated to any one
  business event, the May 2026 coincidence could be pattern, not proof — per AGENTS.md rule 4, both
  readings are stated, neither chosen.**
- Per Trap 22, this field's true business meaning (a production line? a cost center? something
  else?) has never been confirmed, and it is NOT validated to correspond to "Tendering vs Omni" or
  to "PEM107" in the sales-side sense — the fact that its 2026 value happens to be the literal
  string `107` is suggestive (it is the same number as PEM107) but not proof the code means "PEM107
  sales division."
- **Level H (hypothesis, well-evidenced but not proven)** for the reading "this reflects the
  business's claimed May 2026 production separation." **Level V1** for the raw fact that the field
  changed value, cleanly, at item level, in May 2026.
- Recommendation (not a decision): ask the business what `cube_final.division` codes `102`/`103`/
  `107` denote, and specifically whether a system/process change happened in May 2025 as well as
  May 2026 — a "yes" for May 2025 would materially weaken this as evidence for the May 2026 claim.

## 3. Everything else checked: NO clean May-2026 change point found

For every column below, the April-2026-vs-June-2026 gap was checked against the full Jan-2025-to-
latest monthly series, not read off two months in isolation. All of them show ordinary month-to-
month noise of comparable or larger size in *other* month-pairs that have no connection to any
claimed business event — i.e. the April/June gap is not distinguishable from background noise.
Reported here explicitly, per AGENTS.md rule ("a clean 'checked, no change' list is as valuable as
a 'found a change' list").

**`cube_Sale_APD`** (channel = `revenue_type`; 5,687 rows, forecast_date 2024-01-10 to 2027-03-25):
- `division` (reference-only) — PEM107 share of rows noisily ranges 91.8%–100% every month
  Jan 2025–Sep 2026 with no break at Apr/May/Jun 2026 (e.g. 100% in Apr 2025 and Sep 2025, 91.8% in
  Sep 2026). **No change.**
- `status` (Actual/MPS) — 100% Actual every month Jan 2025 through Jul 2026; MPS only appears from
  Aug/Sep 2026 (54 rows in Sep 2026), which is explained by these being the most recent,
  not-yet-actualized orders relative to today's cutoff (2026-09-25), not a channel-separation
  signal. **No change attributable to May 2026.**
- `manufacturing_type` (MTS/MTO) — Omni MTO share oscillates between 7% and 42% across individual
  months with no trend break at May 2026 (e.g. 31.1% in Mar 2025, 9.4% in Apr 2026, 24.1% in Sep
  2026); the naive Apr-vs-Jun-only comparison shows +10pp, but that gap is smaller than several
  other adjacent-month swings in the same noisy series. **No change point identified.**
- `typeOfSale` — 100% `Sale` for every row in the entire pull. **No change (constant).**
- `jobcode` prefix (first alphabetic token, comma-lists split) — CT/VT/RS/CTR/SS/J shares all
  fluctuate month to month with no break at May 2026 (e.g. RS share: 21.5% Mar 2025, 0.5% Apr 2026,
  9.2% May 2026, 3.9% Jun 2026 — noisy, not a clean step). **No change point identified.**
- `revenue_type` (channel mix itself, contextual) — Omni share stays 92–100% every month in this
  itemcode scope; "Total Customer Solution" is a third, rare revenue_type (0.14% of rows overall,
  well under METRICS.md §21's 2% flag threshold). **No change at May 2026.**

**`Cube_CES`** (channel = `RevenueType`, native; 21,598 rows, ForecastDelDate 2011-12-27 to
2027-03-30 — note this itemcode-scoped pull spans many more divisions than PEM107 alone, see §4):
- `Status` (Actual/Backlog/MPS/P2/P3/T2/F) — Actual/P2 shares oscillate all year with no May 2026
  break; Backlog only appears from Sep 2026 (65 rows), again explained by the "today" cutoff, not a
  channel event. **No change attributable to May 2026.**
- `SaleDivision` (native) — dominated by `PEM105` throughout (95–100% of rows most months); `PEM107`
  itself is 0% in most months including April 2026 and only 2–2.9% in June 2026 — a real but tiny,
  thin-sample shift (n≈200–270/month) that does not read as a change in an already-dominant
  category. **No clean change point** (see §4 for why `SaleDivision` is unreliable here at all).
- `ManuDivision` — PEM107 share of this itemcode-scoped pull fluctuates 95–98% most months with no
  break at May 2026.
- `Company` — dominated by `PEM` (97–100%) every month, no break.
- `ProductType` / `PrdTypeID` (identical distributions, PrdTypeID is ProductType's code) — long-tail
  product-mix categories shift by a few points month to month (e.g. VOG/VOL/COL shares) with no
  clean step at May 2026; largest Apr-vs-Jun gaps (≈5-6pp) are smaller than typical month-to-month
  noise elsewhere in the series. **No change point identified.**
- `OLMJobCode` prefix — same pattern as `cube_Sale_APD.jobcode` prefix (expected, same underlying
  batch-reference concept per DATA_MAP.md Sec.2): noisy, no break at May 2026.

**`cube_final`** (no channel field; 8,723 rows, final_date 2023-01-03 to 2026-09-24):
- `transfer_type` — ~100% one dominant value every month throughout (values are Thai-language
  strings that came back mojibake/garbled through this pull's encoding — see §4 caveat; distinct
  strings are still trackable as categories even though their Thai meaning could not be read here).
  **No change.**
- `fg_check_status` — ~100% `Pass` every month (1 `Fail` row total, in Apr 2026, not a pattern).
  **No change.**
- `fg_final_status` — coverage collapses from ~95%+ `Pass` to <10% starting Aug/Sep **2025**, over a
  year before the claimed split; this is the pre-existing Trap 21/22 finding (division='102'
  contamination in this field), not a new May-2026 signal. **No new change found here.**
- `job_qty` — monthly median stays flat at 20–50 units throughout Jan 2025–Sep 2026 with no level
  shift at May 2026 (mean is noisier due to large-order outliers, e.g. a 2,000-unit June 2026 job,
  but medians are stable). Bucketed distribution shows only a few-point wobble Apr vs Jun, smaller
  than other month-pairs. **No change point identified**, aside from §2's `division` finding.
- `company` — 100% `PEM` for every row. **No change (constant).**
- No plant/line-like field exists beyond `division` and `company` in `cube_final`'s full 35-column
  live schema (confirmed identical to the shared loader's documented 35-column list — no undocumented
  36th column found).

## 4. Data-quality notes surfaced along the way (not new findings, but worth recording)

- **This itemcode-scoped `Cube_CES` pull spans far more than PEM107**: `SaleDivision` shows
  `PEM105` as the dominant value (not `PEM107`) in most months, and `ManuDivision`/`Company` include
  `PMW101`, `PPD101`, `PTS`, `PPS`, `PCE101`, `PEMCSA`, etc. This is the same pattern DATA_MAP.md
  Trap 22 already documents for `cube_final.division` — an itemcode-scoped pull can return rows
  whose internal grouping columns belong to a different internal taxonomy than the sales-side
  division these 136 codes are scoped by. Per CONVENTIONS.md this is recorded as reference-only,
  not used to re-filter the scope. **V1** (this session's direct observation).
- **`cube_final.transfer_type` values came back as mojibake** (non-UTF-8 Thai text misdecoded through
  this pull's connection). The three distinct garbled strings are still usable as categorical labels
  for distribution tracking (same string ⇒ same category, consistently), but their actual Thai
  meaning could not be read in this session. Flagged, not resolved.
- **Gap, explicitly not filled (per the stopping rule):** `Cube_CES`'s full 41-column live schema
  includes `OLMBusinessProcess`, `OLMTradeBusinessProcess`, `OLMRevStream`, `PrdCateID`,
  `ProductCate`, and `HandledBy` — columns not pulled in this session because they were only
  identified as "possibly process/type-related" after the one-connection budget for this task was
  already spent on the columns explicitly named in the task plus the ones the schema probe flagged
  by keyword match (`status`/`type`/`division`/`plant`/`line`/`location`/`warehouse`/`company`/
  `dept`/`factory` — `OLMBusinessProcess`/`OLMTradeBusinessProcess` contain neither "status" nor
  "type" as a substring and were missed by that keyword filter). **This is a real gap, not a "no
  change" finding** — these columns are unexamined, not confirmed unchanged. Flagged for a follow-up
  task with its own connection attempt, per AGENTS.md's stopping rule (rule 3): stated here rather
  than spending a second connection attempt in this task.

---

## Verdict

**One column changed at a clean, item-level, near-total step point that lands in May 2026:
`cube_final.division` (internal code `103` → `107`).** Every categorical column checked in
`cube_Sale_APD` and `Cube_CES` — division, status, manufacturing_type, typeOfSale, jobcode/
OLMJobCode prefix, SaleDivision, ManuDivision, Company, ProductType/PrdTypeID, revenue_type/
RevenueType itself — showed only ordinary month-to-month noise with no distinguishable break at
May 2026, and no warehouse/location field exists in any of the three tables' full live schema
(re-confirmed this session).

This does **not** confirm the business's claim outright: `cube_final.division` is a documented
separate internal taxonomy (Trap 22), not validated to mean "channel" or even "sales division," and
the same field shows a nearly identical step change exactly one year earlier (May 2025, `102`→`103`)
with no known business event attached — so a periodic/annual relabeling explanation cannot be ruled
out, and `cube_final` carries no channel field so this cannot be attributed to Omni vs Tendering
specifically. It is reported as the strongest lead this search found, at **level H** for the
causal reading and **level V1** for the raw distributional fact, alongside the counter-evidence
(the May-2025 precedent) that a receiving agent must weigh, not silently drop, per AGENTS.md rule 4.
A specific, falsifiable question for the business would resolve it: what do `cube_final.division`
codes `102`/`103`/`107` mean, and did anything change in May 2025 as well as May 2026?

Six columns/fields (`OLMBusinessProcess`, `OLMTradeBusinessProcess`, `OLMRevStream`, `PrdCateID`,
`ProductCate`, `HandledBy` in `Cube_CES`) remain unexamined — a stated gap, not a "no change" claim.
