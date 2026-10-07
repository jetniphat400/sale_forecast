# Phase 25 — Independent Validator Report (PEM107, Q10 branch)

**Role:** Validator (AGENTS.md). This report recomputes three specific figures from scratch, with
my own SQL queries and my own code (`src/investigations/phase25_validator_analysis.py`), without
reading any `phase25_explorer1_`, `phase25_explorer2_`, `phase25_analyst3_` or `phase25_explorer4_`
output file or script. This is an independent second direction, not a re-read of another agent's
work (CONVENTIONS.md's rule on what counts as independent confirmation).

**Scope:** PEM107 = 136 itemcodes from `output/data/phaseI_combined_scope_351items.csv` where
`division == 'PEM107'` (pricelist-derived scope column). Verified count: 136 (matches the
task brief). The database's own `division` column on `cube_Sale_APD`/`cube_final` was NOT used as
a filter anywhere (CONVENTIONS.md).

**Data access:** one database connection session covering all three pulls (`cube_Sale_APD` via my
own query, `cube_final` via `src/cube_final_pull.py`, `Cube_CES` via `src/cube_ces_pull.py` with
`OLMJobCode` added). The pull succeeded on the first attempt; no retry was needed or made.

Raw pulls (row counts, my own script's log):
- `cube_Sale_APD`: 5,687 rows
- `cube_final`: 8,723 rows
- `Cube_CES`: 21,598 rows

Sanitized raw exports (no employee names, no contract/customer IDs):
`output/summary/phase25_validator_raw_cube_final.csv`,
`output/summary/phase25_validator_raw_cube_ces.csv`. `cube_Sale_APD` raw is not exported as a
separate file (it would require the contractid join key to build Figure 1, which is never
persisted to disk); Figure 1's per-month, per-channel aggregates below are the exported form of
that data.

---

## Figure 1 — Link rate around the Sep–Dec 2024 boundary

**Method (own code):** grain = distinct `(contractid, itemcode)` pair in `cube_Sale_APD` (5,428
such pairs found across all history; 0 pairs had inconsistent `revenue_type` within the pair, so
grouping by pair is safe). Month = the pair's earliest `createDate`. A pair is "linked" if EITHER
(a) `cube_Sale_APD.jobcode`, comma-split into tokens, intersects the token set built from
`cube_final.jobno` for this itemcode scope, OR (b) `Cube_CES.OLMJobCode` (joined on the same
`itemcode`+`ContractID`, comma-split into tokens) intersects the same `cube_final.jobno` token set.

**Verified before assuming (per task instruction):**
- `cube_final.jobno`: 8,723 non-null values, **0 contain a comma** — single-token, as assumed.
- `Cube_CES.OLMJobCode`: 17,885 non-null values, **973 (5.4%) DO contain a comma** — multi-token in
  a non-trivial minority of rows. My code comma-splits `OLMJobCode` before matching; a script that
  assumed it was always a single token would under-count links from this side.
- `cube_final` jobno token population for the PEM107 itemcode scope: 2,181 distinct tokens.

**Result** (`output/summary/phase25_validator_figure1_link_rate_by_month.csv`):

| month | revenue_type | n_contracts | n_linked | link_rate_by_count % | qty_total | qty_linked | link_rate_by_qty % |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-09 | Omni Channel | 229 | 227 | 99.13 | 2,982 | 2,976 | 99.80 |
| 2024-09 | Tendering | 12 | 1 | 8.33 | 4,308 | 3,900 | 90.53 |
| 2024-10 | Omni Channel | 172 | 163 | 94.77 | 1,044 | 558 | 53.45 |
| 2024-10 | Tendering | 13 | 1 | 7.69 | 2,319 | 6 | 0.26 |
| 2024-11 | Omni Channel | 236 | 235 | 99.58 | 1,034 | 1,032 | 99.81 |
| 2024-11 | Tendering | 12 | 12 | 100.00 | 15,527 | 15,527 | 100.00 |
| 2024-12 | Omni Channel | 118 | 111 | 94.07 | 932 | 350 | 37.55 |
| 2024-12 | Tendering | 0 | 0 | — | 0 | 0 | — |

**Reading:** Omni Channel's link rate BY COUNT stays high and stable across all four months
(94.1%–99.6%) — no sharp drop, and no sign the linkage method itself goes "blind" at the Oct/Nov
2024 boundary. This directly addresses concern (1) from the task brief: if the general
jobcode/OLMJobCode → jobno matching mechanism had stopped working around this boundary, count-based
link rate would have collapsed for BOTH channels at that point; it did not for Omni Channel.
Tendering's count-based rate is low in Sep/Oct (7.7–8.3%) then jumps to 100% in Nov on a tiny base
(n=12); with only 12–13 Tendering contracts per month this channel's rate is too noisy to read a
trend from on its own. By quantity, Omni Channel is more volatile (37.6%–99.8%) — consistent with
a small number of large-qty lines dominating a given month's linked/unlinked total, not a
channel-wide "goes blind" pattern.

**Note on what this figure does NOT test:** this is a *general* linkage-health check (does
ANY link exist), not the *dual-channel batch-sharing* metric itself (does a single batch serve
BOTH channels) that the November 2024 change point in DATA_MAP.md refers to. My result shows the
general linking mechanism keeps functioning on both sides of that boundary; it does not by itself
rule out or confirm the dual-channel-specific claim, which I did not re-run (out of my three
assigned figures).

**Confidence: V1** (my own independent recomputation, own query, own token-matching code; not yet
cross-checked against another agent's figure for this same question — becomes V2 if the
Orchestrator finds an independently-run figure that matches).

---

## Figure 2 — PEM107 Omni Channel `not_late`, before/after May 2026

**Method (own code, METRICS.md §19):** `Cube_CES`, `Status == 'Actual'`, `RevenueType == 'Omni
Channel'`, PEM107 itemcode scope. `not_late` = `ActualDelDate <= ForecastDelDate`. Unit-weighted =
`Σ ActualQty where not_late / Σ ActualQty`. Rows missing `ForecastDelDate` or `ActualDelDate`
excluded (1 row missing each, out of 8,406 Status=Actual/Omni rows).

**Period result** (`output/summary/phase25_validator_figure2_not_late_period.csv`):

| period | n_rows | qty_total | qty_not_late | not_late unit-weighted % | not_late row-weighted % |
|---|---:|---:|---:|---:|---:|
| 2025-05 to 2026-04 | 2,069 | 13,068 | 11,684 | **89.41** | 86.52 |
| 2026-05 to latest (2026-12) | 751 | 2,675 | 1,531 | **57.23** | 80.69 |

**Data-quality flag (my own finding, not assumed):** "latest available data" by `ForecastDelDate`
extends to **2026-12**, which is 3 months after today's date (2026-09-25, per Get-Date). This is 6
rows / 12 units out of the whole post-May-2026 period (751 rows / 2,675 units) — a forward-dated
`ForecastDelDate` on `Status='Actual'` rows. Excluding this apparently-anomalous tail and using
2026-05 through 2026-09 only: qty_total=2,663, qty_not_late=1,519, unit-weighted **57.04%** —
materially unchanged (the tail is too small to matter here), but the existence of `Status='Actual'`
rows with a due date in the future is itself worth flagging to whoever owns `Cube_CES` data entry.

**Monthly detail** (`output/summary/phase25_validator_figure2_not_late_monthly.csv`, full series
included back to 2019 as a byproduct of no SQL-level date filter): the decline is concentrated from
**2026-05 (84.31%) onward**, with 2026-06 the sharpest single-month drop (46.01%), partial recovery
in 2026-08 (82.40%), and a very low 2026-09 (37.62%, a partial month since today is 2026-09-25 and
the month is not yet complete — flagged, not treated as a stable monthly figure).

**Confidence: V1** (own recomputation, METRICS.md §19 formula applied directly; row-weighted figure
reported alongside per Error-review rule "report shares alongside absolute volumes" — the two
weightings diverge notably in Period 2, 57.23% unit-weighted vs 80.69% row-weighted, meaning the
post-May-2026 lateness is concentrated in a smaller number of HIGH-quantity lines, not spread evenly
across orders).

---

## Figure 3 — `cube_final.division` step change (PEM107 itemcode scope)

**Method (own code):** `cube_final` pulled for the 136 PEM107 itemcodes (itemcode-scoped only, per
`src/cube_final_pull.py` — no date filter at pull). Bucketed by `final_date` month. `division` here
is `cube_final`'s own internal column (DATA_MAP.md §4 Trap 22: a *separate* internal grouping from
the sales-side division taxonomy — its meaning is NOT assumed to equal `PEM107`/`PEM103`/etc. just
because the values happen to look similar; see flag below).

**Dominant `division` value by month, Jan 2025 onward**
(`output/summary/phase25_validator_figure3_dominant_division_by_month.csv`, full distribution in
`..._figure3_division_monthly_distribution.csv`):

| period | dominant `cube_final.division` value | share |
|---|---|---|
| 2025-01 to 2025-04 | `102` | 100% every month |
| 2025-05 | `102` | 73.21% (partial — transition month, 123/168 rows) |
| 2025-06 to 2026-04 | `103` | 100% every month |
| 2026-05 | `107` | 95.39% (partial — transition month, 145/152 rows) |
| 2026-06 to 2026-09 | `107` | 100% every month |

**The specific check the task asked for — does the same KIND of change appear a year earlier
(around May 2025)?** **YES.** There are exactly two transitions in the Jan-2025-onward window, and
BOTH land in May: `102→103` completing in June 2025, and `103→107` completing in June 2026 — same
calendar month, same shape (a partial-share transition month followed by a clean switch the
following month). This is a direct, verified match to what the task said would undercut reading the
May-2026 change as evidence of the May-2026 business separation specifically.

**However, this is NOT a clean "always happens every May" cycle** — I extended the same check
(same script logic, re-run on the already-pulled, already-sanitized `cube_final` CSV) back to
2023-01–2024-12, and found `division = 102` at **100% every single month** across both full years,
with no May transition in either 2023 or 2024. So the pattern is: no May effect in 2023 or 2024, a
`102→103` May transition in 2025, and a `103→107` May transition in 2026 — two instances, one year
apart, not a mechanism that fires every year. The step SIZE also differs (+1 in 2025 vs. the value
jumping from 103 to 107 — not +1 — in 2026), so "the same kind of change" is true in TIMING
(May→June, partial-then-clean) but not in MAGNITUDE.

**A coincidence worth flagging, explicitly NOT interpreted as confirmed:** the three internal
`division` values observed for the PEM107 itemcode scope are exactly `102`, `103`, `107` — the same
digits as the sales-side division codes `PEM102`, `PEM103`, `PEM107`. Per AGENTS.md rule 1 ("never
infer business meaning from a column name/value alone — a name is a hypothesis, not evidence") and
DATA_MAP.md's own Trap 22 warning, I am NOT concluding that `cube_final.division` records which
PEM-division's production organization these PEM107 items' batches were run under. I am reporting
the raw, directly-confirmed fact (the values and their transition dates) and flagging the
numeric coincidence as a hypothesis someone should check against how `cube_final.division` is
actually populated, before it is used as evidence either for or against the business's May-2026
separation claim.

**Confidence:**
- The monthly distribution and transition dates themselves: **V1** (direct recomputation from my
  own pull, deterministic groupby/count — this is arithmetic on data I pulled myself, about as
  close to V2 as a single-agent figure gets, but still awaiting cross-check against another agent's
  independent figure for this same question).
- Any reading of WHAT the `division` values mean (i.e. the PEM10x coincidence): **not verified —
  explicitly flagged as an open question, not a finding**, per rule 1 above.

---

## Summary of 3 recomputed figures

1. **Link rate around Oct/Nov 2024 boundary (Omni Channel, by count):** 99.13% (Sep) → 94.77%
   (Oct) → 99.58% (Nov) → 94.07% (Dec 2024) — **no sharp drop; general linkage mechanism does not
   go blind at this boundary.** By quantity: 99.80% → 53.45% → 99.81% → 37.55% — more volatile, but
   no directional collapse either. Tendering (n=12-13/month) too small to read a trend from.
   Source: `phase25_validator_figure1_link_rate_by_month.csv`.

2. **PEM107 Omni Channel `not_late`, unit-weighted:** **89.41%** (2025-05 to 2026-04, n=2,069 rows
   / 13,068 units) vs. **57.23%** (2026-05 to latest available 2026-12, n=751 rows / 2,675 units;
   57.04% if the anomalous forward-dated 2026-12 tail is excluded). Row-weighted: 86.52% vs. 80.69%
   — the two weightings diverge sharply in Period 2, meaning lateness is concentrated in
   higher-quantity lines. Source: `phase25_validator_figure2_not_late_period.csv` /
   `..._monthly.csv`.

3. **`cube_final.division` dominant value:** `102` (Jan–Apr 2025, majority of May 2025) →
   **`103`** (Jun 2025–Apr 2026) → **`107`** (May 2026 onward, majority from May, 100% from June).
   A same-shaped transition (May partial-share month → June clean switch) occurred exactly one year
   earlier (102→103 in 2025), which is the specific pattern the task asked me to check for and
   which I confirm is present — but no such May transition occurred in 2023 or 2024 (both were
   100% `102` all year), and the 2025 step size (+1) differs from the 2026 step (103→107, not +1).
   Source: `phase25_validator_figure3_dominant_division_by_month.csv`,
   `..._division_monthly_distribution.csv`, `..._dominant_division_changes.csv`.

**Scripts:** `src/investigations/phase25_validator_analysis.py` (single script, one DB connection
session, all three figures). No customer names, contract IDs or employee names appear in any
output file listed above.
