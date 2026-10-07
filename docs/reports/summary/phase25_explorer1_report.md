# Phase 25 Explorer 1 Report — PEM107 jobcode/OLMJobCode↔cube_final linkage reliability, before/after late-2024

**Target node**: Q10 (PROJECT_GRAPH.md), PEM107 branch. **Unblocks**: the Synthesizer's read on
whether the prior "0.00% dual-channel batch linkage from Nov 2024 onward" finding
(DATA_MAP.md §7, `phase24_explorerA_report.md`) is a real business change or a measurement
artifact of the linkage itself breaking at the late-2024 PEM102/PEM107 reorganisation.

**Role**: Explorer (1 of 4 parallel, independent agents on this task — no coordination with the
other 3, per instructions). Reports what queries/joins return; does not interpret business
meaning beyond the narrow question assigned (linkage reliability, not actual batch-sharing).

**Scope**: PEM107, 136 items (`output/data/phaseI_combined_scope_351items.csv`, pricelist-
authoritative scope — database `division` column not used as a filter, per CONVENTIONS.md).
Both channels (Omni Channel, Tendering) — not Omni-only.

**Data access**: one connection attempt, three queries in one script/session
(`src/investigations/phase25_explorer1_pull.py`) — the established precedent
(`phase24_explorerA_pull.py`). All three succeeded; no retry was needed.
- `pull_cube_final_for_items`: 8,723 rows, 2,181 distinct `jobno` (PEM107 item scope, all-time).
- `pull_cube_ces_for_items` (+`OLMJobCode`): 21,598 rows, 8,412 distinct `OLMJobCode`.
  `RevenueType`: Omni Channel 11,804, Tendering 302, Total Customer Solution 127.
- Direct query on `cube_Sale_APD` (itemcode filter only, no revenue_type/status/date filter at
  SQL level): 5,687 rows. `revenue_type`: Omni Channel 5,523, Tendering 156, Total Customer
  Solution 8. `status`: Actual 5,558, MPS 129.
- Data range: `cube_Sale_APD.createDate` runs 2024-01-03 to 2026-09-23 — the table itself starts
  at Jan 2024 for this item scope, so "January 2024 to latest" is the table's full range, not a
  truncation. Latest date in both pulls: 2026-09-23. Today is 2026-09-25, so September 2026 is a
  partial month — included in the monthly table but not read as a completed trend point.

Raw pulls, privacy-stripped before saving (this task's instructions forbid customer names,
contract IDs and employee names in anything written): `contractid`/`ContractID` dropped from the
`cube_Sale_APD`/`Cube_CES` raw files (used only in-memory for the contract-grain join); `ctrno`
(a contract ID, DATA_MAP.md §1) dropped from the `cube_final` raw file; and, found on inspecting
the pulled values (not assumed from the column name), `cube_final.fg_check_name`/
`fg_final_name`/`fg_pack_name` hold actual employee names (not role codes — `fg_check_by`/
`fg_final_by` hold role codes like `QA`/`QC` and were kept) and were dropped too. Files:
`phase25_explorer1_cube_final_raw.csv`, `phase25_explorer1_cube_ces_raw.csv`,
`phase25_explorer1_sale_apd_raw.csv`.

## Method

**Contract grain**: a distinct `(contractid, itemcode)` pair from `cube_Sale_APD`. 5,428
contract-item pairs from 5,687 rows; 96.6% (5,245) have exactly one row, 183 have 2-7 rows
(multiple tranches/lines) — these are grouped: `jobcode` tokens unioned across the group's rows,
`qty` summed, `createDate` = the group's earliest row. Zero pairs mix `revenue_type` across their
own rows (checked, not assumed). This grain was chosen because `jobcode`/`qty` are recorded per
`(contractid, itemcode)` line, and `Cube_CES`'s `(ContractID, ItemCode)` is the same join key back
to that line — it lets one linkage test cover both source columns for the same underlying order.
Script: `src/investigations/phase25_explorer1_analysis.py` (`build_contracts`).

**Link test** — a contract-item links to `cube_final` if EITHER:
- (a) any comma-split token of its `cube_Sale_APD.jobcode` value(s) is in the PEM107-scope
  `cube_final.jobno` set (2,181 values, all-time, no date restriction), OR
- (b) any token of the `OLMJobCode` value(s) found in its matching `Cube_CES` row(s) (joined on
  `ContractID=contractid, ItemCode=itemcode`, unbounded time) is in that same `jobno` set.

**Deviation from the task's stated assumption, found in the data**: `OLMJobCode` is described in
the task as "a single token." This is not what the data shows — 5.4% of populated `OLMJobCode`
values (973/17,885) are themselves comma-separated lists (e.g. `CT240254,CT250268`,
`VT11/121,VT12/012,VT12/020,VT12/089.1`), same as `jobcode`'s known format. **V1** (direct count
from this pull). Path (b) above was applied with the same comma-split/any-token-matches rule as
`jobcode`, not literal single-token equality, so the reported link rate is not understated by this.
5,358/5,428 (98.7%) contract-item pairs have at least one matching `Cube_CES` row with a populated
`OLMJobCode`.

## Part 1 — Link rate, by count and by quantity, per month, per channel

Full table: `output/summary/phase25_explorer1_monthly_link_rate.csv` (63 month×channel rows).
Before/after pooled summary: `phase25_explorer1_before_after_summary.csv`. Split point: 2024-10-01,
the change point DATA_MAP.md §7 already established (last dual-channel batch `final_date`
2024-10-03; zero dual-channel from Nov 2024 onward) — used here only as the boundary to test link
*reliability* across, not re-derived.

**Omni Channel** (the channel this project's forecast actually consumes):

| | n_contracts | n_linked | rate (count) | qty_total | qty_linked | rate (qty) |
|---|---|---|---|---|---|---|
| Before 2024-10 | 1,435 | 1,400 | **97.56%** | 17,416 | 15,169 | **87.10%** |
| On/after 2024-10 | 3,867 | 3,727 | **96.38%** | 26,483 | 21,133 | **79.80%** |

Count-based link rate is essentially unchanged (97.6% → 96.4%, a 1.2-point difference). Qty-based
link rate drops modestly (87.1% → 79.8%, a 7.3-point difference) but this is **not** a collapse,
and — checked against the full monthly series, not just the two pooled halves — qty-based rate is
volatile throughout the *entire* 2024-01 to 2026-09 window (driven by whether a few large-quantity
contracts happen to link), with equally low months on both sides of the boundary: e.g. 2024-03
43.0%, 2024-06 78.1%, 2025-02 39.3%, 2025-05 54.1%, 2026-06 43.7% — none of these are near the
Oct-Dec 2024 boundary. The three individual Oct/Nov/Dec 2024 Omni Channel months themselves:
2024-10 n=172, rate 94.77% (qty 53.45%); 2024-11 n=236, rate 99.58% (qty 99.81%); 2024-12 n=118,
rate 94.07% (qty 37.55%). **Count-based rate stays high (94-99.6%) across all three months — no
sharp drop appears specifically in Oct-Dec 2024**; the qty swings visible in Oct/Dec are within
the range seen repeatedly elsewhere in the series, not a new pattern starting at the boundary.

**Tendering** (small-N, noisy — flagged, not a basis for a monthly trend statement):

| | n_contracts | n_linked | rate (count) | qty_total | qty_linked | rate (qty) |
|---|---|---|---|---|---|---|
| Before 2024-10 | 25 | 7 | 28.00% | 9,319 | 4,636 | 49.75% |
| On/after 2024-10 | 93 | 36 | 38.71% | 58,232 | 35,118 | 60.31% |

Tendering's link rate is low in *both* periods (consistent with Tendering's known weaker
batch/cadence linkage generally — DATA_MAP.md §2 cites PEM107's reverse-traceability at 58.9%
project-wide, a different but related figure) and is, if anything, slightly **higher** after
2024-10 than before, by both count and quantity. No collapse; the pre-existing low rate is not new.
Individual months have n as small as 1-13 contracts, so month-to-month swings (0%, 50%, 100%) are
sampling noise, not signal — reported in the full CSV but not read as a trend.

**Other revenue types** (`phase25_explorer1_other_revenue_type_summary.csv`): "Total Customer
Solution" — 8 contracts, 10 units, 0.009% of total quantity across both channels. Well under the
2%-share flag threshold (METRICS.md §21 convention); excluded from the two-channel comparison
above and reported here for transparency only.

**Confidence: V1** (one Explorer pass; not yet independently recomputed by another agent — the
task specifies 4 independent parallel Explorers on this same question, so cross-checking against
the other 3's figures is the Synthesizer's job, not mine).

## Part 2 — Format check, before vs. after 2024-10-01

Full detail: `output/summary/phase25_explorer1_format_check.txt`. Summary:

**`cube_Sale_APD.jobcode`** (split by `createDate`):
- Token length: BEFORE — 1,552/1,576 tokens (98.5%) are 8 characters; a handful at 3/7/10/14 chars.
  AFTER — 4,150/4,281 (97.0%) are 8 characters; similar tail (3/6/7/9/10/14/17/30 chars). No shift
  in the dominant length.
- Prefix: BEFORE — CT (797), VT (608), RS (169), plus 2 singletons (Ha, LB). AFTER — CT (2,212),
  VT (1,725), RS (294), plus new-but-minor prefixes SS (19), J2 (16), LB (8), FO/SR/DB (2 each),
  SL (1). The three dominant prefixes (CT/VT/RS) are unchanged and still dominant; a few new
  low-volume prefixes appear after, but they do not displace the existing format.
- Separator: comma, both periods (no other separator character found in either window).
- Tokens per row: BEFORE 5.45% of rows have >1 token; AFTER 3.50% — a small *decrease*, not an
  increase, in multi-token rows.
- Samples BEFORE: `VT230234, RS190335, CT240217, RS240151, CT240123`. Samples AFTER:
  `CT250246, RS250369, CT260097, CT250002, VT260006`.

**`Cube_CES.OLMJobCode`** (split by `CtrDate`): same pattern — dominant 8-character token length
both before (14,200/14,650, 96.9%) and after (4,185/4,309, 97.1%); same dominant prefixes
CT/VT/RS both sides, with the same small set of new low-volume prefixes appearing after
(SS/J2/LB/FO/SR/DB/SL — the same set as `jobcode`'s, consistent with both columns describing the
same underlying batch-reference system); comma-separated share 6.00% before vs. 3.56% after (again
a decrease). Samples BEFORE: `RM230280, CT16/151, RM221391, VT180066`. Samples AFTER:
`CT250126, CT240254,CT250268, VT260050, CT240235`.

**`cube_final.jobno`** (split by `final_date`, for reference only — this column was already known
to be near-uniformly 8 characters): 4,157/4,157 (100%) before, 4,565/4,566 (99.98%) after; same
CT/VT/RS prefixes before, with CV/CR/CC appearing as new low-volume prefixes after (again the same
kind of small addition, not a format break).

**Finding: no format break at the boundary.** Token length, prefix distribution, and separator
character are essentially unchanged before vs. after 2024-10-01 across all three columns. A few
new low-volume prefixes appear after the boundary in both `jobcode` and `OLMJobCode` (and in
`jobno`) — consistent with new production lines/departments being added at the reorganisation, not
with the linkage mechanism breaking. The share of multi-token (comma-separated) values *decreases*
slightly after the boundary in both `jobcode` and `OLMJobCode`, the opposite of what a broken
linkage (e.g. batches no longer being tagged with all their contracts) would predict.

**Confidence: V1** (one Explorer pass, direct tabulation from the raw pulls — no interpretation of
what a new prefix organisationally means, which is out of scope here).

## Part 3 — Verdict on this task's own question

**The link rate does not collapse around October-December 2024, for either channel, by either
count or quantity.** Omni Channel count-based link rate: 97.56% before → 96.38% after (essentially
flat). Omni Channel quantity-based rate: 87.10% before → 79.80% after (a modest, not a collapsing,
decline — and one within the range of swings seen throughout the whole series, not concentrated at
the boundary). Tendering: low in both periods (28.0%→38.7% count, 49.7%→60.3% qty) — no collapse,
if anything slightly better after. Format (token length, prefix, separator, tokens-per-contract) is
essentially unchanged across the boundary in both source columns.

**Per the task's own framing: the linkage-blindness hypothesis FAILS.** The linkage mechanism
(`jobcode`/`OLMJobCode` ↔ `cube_final.jobno`) looks equally reliable before and after the late-2024
reorganisation — it did not go blind at that point. This supports reading the prior task's
"0.00% dual-channel batch linkage from Nov 2024 onward" finding (DATA_MAP.md §7) as a **real**
change in how PEM107's batches are shared across channels, not a measurement artifact of the
linkage breaking.

**Explicit scope limit, stated per the task's instructions**: this only establishes that the
*linkage rate itself* did not change. It does **not** independently establish that batches were
actually shared or not shared — that is the prior task's own finding (DATA_MAP.md §7,
already V2, independent Validator match), which this task does not re-test. It also does not rule
out some other form of production/stock sharing that would never surface as a shared `jobno`/
`OLMJobCode` token at all (DATA_MAP.md §7 already flags this as an open possibility) — this
Explorer's scope is the token-linkage mechanism only.

## Stopping point

All three queries succeeded on the one permitted connection attempt; no data gap was hit and no
further searching was needed. Both the format check and the link-rate check were completed for
the full Jan-2024-to-latest window requested. Nothing here is blocked on missing data.

## Files produced (all under `output/summary/`, prefix `phase25_explorer1_`)

- `phase25_explorer1_cube_final_raw.csv`, `phase25_explorer1_cube_ces_raw.csv`,
  `phase25_explorer1_sale_apd_raw.csv` — raw pulls (privacy columns dropped).
- `phase25_explorer1_contract_link_detail.csv` — per contract-item pair: linkage flags, tokens
  counts, month, channel.
- `phase25_explorer1_monthly_link_rate.csv` — Part 1's full month×channel table.
- `phase25_explorer1_before_after_summary.csv` — Part 1's pooled before/after summary.
- `phase25_explorer1_other_revenue_type_summary.csv` — Total Customer Solution share.
- `phase25_explorer1_format_check.txt` — Part 2's full token-length/prefix/sample detail.
- Scripts: `src/investigations/phase25_explorer1_pull.py` (DB access, one connection attempt),
  `src/investigations/phase25_explorer1_analysis.py` (all computation, no further DB access).
