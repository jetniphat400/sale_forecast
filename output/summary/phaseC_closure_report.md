# Phase C Closure — Transferability Synthesis, Placeholder Rule Set, Scoring Readiness

**Roles**: Synthesizer then Modeler, per `AGENTS.md` — same context, one agent, not split. **Run**:
2026-09-07. Every figure cited to its file.

---

## Part 1 — Final transferability table, all six divisions (Synthesizer)

| Division | Method to use | Evidence | Confidence |
|---|---|---|---|
| PEM101 | Top-down combination | Rolling-origin MAE: Top-down 343.82 < Direct 344.63 < Naive 449.18. Holds a clean advantage over both. (`phaseC_step2_transferability_per_division.csv`) | High |
| PEM102 | Top-down combination | Beats Naive (1.16 vs 1.34); thin, non-significant edge over Direct (1.16 vs 1.15, paired t=0.238, n=16). (`_verdict.csv`, `_significance.csv`) | Moderate |
| PEM103 | Top-down combination | Beats Naive (2.49 vs 2.70); thin, non-significant edge over Direct (2.49 vs 2.43, t=0.545, n=48). Demand entirely Intermittent/Lumpy (0% Smooth/Erratic) — a known caution, not resolved by this result. | Moderate |
| PEM107 | Top-down combination | Beats Naive (11.57 vs 13.61); thin, non-significant edge over Direct (11.57 vs 11.44, t=0.118, n=112). | Moderate |
| CI101 | Top-down combination | **Falls 1.6% behind Naive** (10.27 vs 10.11, not significant, t=0.117, n=13) while significantly beating Direct (10.27 vs 11.07, t=-2.124, borderline given small n). | Moderate-low |
| PEM104 | Excluded (not forecast) | Only 12 transactions across 17 months — insufficient for any model at any aggregation level. Receives a placeholder for Phase 4 instead. | High |

**The honest position, stated plainly, per instruction**: Top-down combination beats Naive in
**4 of 5 forecastable divisions** (all but CI101) and holds a **thin, non-significant edge over
Direct in 3 of 5** (PEM102, PEM103, PEM107 — all `|t|<0.6`). **It is adopted across all five
forecastable divisions for structural reasons — Type-level rolling-origin stability
(`phaseC_step2_report.md` Part 1: mean winner-stability only 34.3% across 40 Types, i.e. no
single model or approach is reliably best) and a single consistent method project-wide — not
because accuracy differences are decisive.** Only PEM101's advantage is clean and unambiguous;
everywhere else the choice is a structural default, not a proven win.

**CI101** is the one division where Top-down actually underperforms Naive (a 1.6% gap, not
statistically significant on 13 items). **It stays on Top-down for consistency**, per config.yaml's
recorded `recheck_instruction`: re-check once CI101's item-level history lengthens beyond the
current 13-item, 31-month evidence base — the gap is small and not settled, not a reason to switch
away from the project's single method today.

**Value-vs-quantity aggregation**: identical zero-inflation reduction by mathematical necessity
(zero qty implies zero sale value for the same rows — not an artifact of which unit is summed);
mixed overfitting-gap results across divisions (2 of 5 smaller under value, 3 of 5 larger); quantity
retained by absence of a reason to change, not a decisive win. **Caveat, stated explicitly**:
summing units across different product kinds at Category level remains physically meaningless
(e.g. fuse cutouts + fuse links summed as one number corresponds to nothing a person could count).
**Top-down allocation itself operates at Type level, where products are of one physical kind** —
Category-level figures are for overview only, never used for allocation, so this caveat does not
undermine the adopted method.

Full detail: `output/summary/phaseC_step2_report.md` Parts 2-3;
`phaseC_step2_transferability_per_division.csv`, `_verdict.csv`, `_significance.csv`.

---

## Part 2 — Placeholder method for the 82 no-history items (Modeler)

**Script**: `src/placeholder_assignment.py`. **Output**:
`output/summary/phaseC_placeholder_assignment_82items.csv` (82 rows) + written into
`config/config.yaml` (`placeholder_rule_set`, `placeholder_item_assignments_82` — editable by
hand). Population confirmed at 82 (89 minus the 7 PEM104-sheet codes, excluded at division level
instead — see Phase C step 2's Part 0b).

| Rule | Meaning | Count |
|---|---|---|
| A | Type mean monthly demand per item (top sibling < 40% of Type's history-bearing value) | **50** |
| B | Type median monthly demand per item (top sibling ≥ 40% — mean would be pulled toward it) | **29** |
| C | Flag only, value 0, no number invented (zero siblings with history) | **3** |
| D (annotation, not a separate value) | Item under A/B/C ALSO has a 2023 Cube_CES Actual/Backlog Omni-Channel trace with no `cube_Sale_APD` row in any year — noted, value unchanged | **9** |

**Flag-only items (Rule C), listed explicitly**:
- `SR-F-99-3381603` (PEM102-Version 2, Type "33kV Recloser")
- `SR-F-99-3381603-01` (PEM102-Version 2, Type "33kV Recloser")
- `02-05-R-0001` (PEM102-Version 2, Type "FRTU") — **also carries the Rule D 2023-trace annotation**,
  an edge case the instruction's wording did not explicitly address (Rule D was described as
  modifying the sibling rule, but this item has zero siblings) — reported honestly rather than
  dropped: it keeps Rule C's zero/flag, with the 2023 trace noted as additional context only.

**40% threshold — stated as an assumption, per instruction, not derived from this data.** Carried
directly from this task's own instruction. If it produces poor placeholder values in practice
(e.g. a Type where 35% "top share" still behaves like effective dominance), it should be revisited
— recorded as such in `config.yaml`'s `placeholder_rule_set.dominance_threshold_pct` comment.

**Formulas used, stated explicitly since the task described them in words**: "Type mean" = the
mean, across a Type's history-bearing siblings, of each sibling's OWN mean monthly qty over the
2024-01/2026-07 fitting window (equivalent to the Type's pooled total ÷ n siblings ÷ 31 months).
"Type median" = the MEDIAN of those same per-sibling means — not a median of pooled monthly
totals, which would still mostly track the dominant item's own scale.

---

## Part 3 — Forward-test scoring for the 335-item log (Modeler)

**Script**: `src/score_forward_test_all_divisions.py`, extending
`src/score_forward_test_v2.py`'s consistency check (config_version, date_key,
item_level_approach, scope_hash, scope_n_items) with one added field, **`divisions`** — necessary
because the new log spans 5 divisions where v2's spanned one.

**Confirmed by direct test, not assumed**:
- **Refuses the archived 128-item log**: pointed directly at
  `output/summary/archive/forward_test_log_v2_128items_superseded_2026-09-07.csv` and its
  metadata — raised `ForwardTestConsistencyError` citing `config_version`, `scope_hash`
  (`9439fc5dc3f2` vs. current `624905d48bf0`), `scope_n_items` (128 vs. 335), and `divisions`
  (`None` vs. `['CI101', 'PEM101', 'PEM102', 'PEM103', 'PEM107']`) — no scored output was written.
- **Accepts the current log**: `output/summary/forward_test_log_all_divisions.csv` passes the
  consistency check cleanly (config_version, scope_hash, scope_n_items and divisions all match).

**First scoreable month and readiness date**: target months are 2026-08 through 2027-01 (horizon
1-6 from the fitted window's last month, 2026-07). **First target month: 2026-08** (month-end
2026-08-31). **Leakage-guard margin (30 days) clears on 2026-09-30** — today (2026-09-07) is not
yet past that date, so **0 of 6 target months are currently safe to score**; confirmed directly by
running the script, not assumed. Re-running this script after 2026-09-30 will score 2026-08 for
the first time.

**Test added**: `tests/test_score_forward_test_all_divisions.py` (6 tests: passes on a matching
metadata; refuses on config/scope/approach/division mismatch individually; a direct regression
test reproducing the archived 128-item log's actual recorded metadata against the current
335-item scope). **Full suite: 46 passed** (was 40 before this task; 6 new).

---

## Part 4 — Config lock-in

Written into `config/config.yaml` (see the file itself for full comments):
- `division_forecast_method`: per-division method (`topdown_combination` for all five
  forecastable divisions, `excluded` for PEM104), each with a `reason` string; CI101 additionally
  carries `recheck_instruction`.
- `aggregation_value_col: "qty"` + `aggregation_category_level_caveat` (the Category-level
  physical-meaning caveat, stated as a permanent caveat, not a re-litigated question).
- `placeholder_rule_set`: the four-rule definition, the 40% threshold, and the counts table above.
- `placeholder_item_assignments_82`: per-item rule/value/flag/note, one entry per code — editable
  by hand.

No pipeline code was modified to READ these new config keys (out of scope for this task, which
asked to record the decisions in config, not wire them into the loader/forecast scripts) — flagged
as not-yet-done work.
