# CONVENTIONS

## Code Structure

- Separate data access, computation and presentation into different modules.
- Each function does one thing, takes inputs and returns outputs, without hidden side effects.
- No magic numbers in code; all tunable values belong in `config.yaml`.
- No hardcoded absolute paths; use paths relative to the project root.

## Data Correctness

- Keep raw pulled data separate from processed data and never overwrite raw.
- Validate data before use, checking for negative values, dates outside the expected range,
  unmatched item codes and duplicates.
- Validation failures must be raised loudly, never silently skipped.
- Write tests for invariants such as forecasts never being negative, monthly totals matching
  the sum of daily records, and SKU counts staying consistent before and after processing.
- Every number delivered must be verifiable against a direct recomputation.
- **The pricelist is the authoritative source for product attributes, including category, type
  and division. Database columns for those same attributes are reference-only** — record them for
  inspection, but never filter or classify on them. **When a database value looks unreliable, the
  first question is what the source of truth for that attribute is, not whether to exclude the
  value.** This rule exists because a `division = 'PEM101'` project-scope error was first
  "fixed" by excluding the database's unreliable `-OLD`-suffixed division tags — which would have
  discarded roughly 26-40% of two divisions' real sales — before the actual fix was recognized:
  the pricelist already determines an item's division, so the database's `division` column should
  never have been used as a filter at all. See `STATUS.md` Locked Decisions, "Division
  source-of-truth correction," for the full account.
- **Agreement between two cubes/tables that share an upstream source demonstrates consistency,
  not correctness.** High agreement between two derived views of the same underlying transaction
  system (e.g. `cube_Sale_APD` vs. `Cube_CES`, cross-checked repeatedly in this project at
  99.79%+ row-level match) only shows the two views are consistent with each other — it does not
  independently verify that the underlying transactions are accurate or complete. Two cubes fed by
  the same PO-receipt process would agree with each other just as well whether or not demand that
  never became a recorded order is captured anywhere, because neither cube would ever see it (see
  `STATUS.md` §3, Business Findings, the PO-based-history scope-limitation entry). Any future
  cube-agreement finding in this project should be read and written up as "consistent," never as
  "validated" or "correct," unless a genuinely independent, differently-sourced check (a physical
  stock count, a customer-side record) is also performed. This rule was added during the Phase E0
  pre-check gate (2026-09-18, `output/summary/phaseE0_synthesis_report.md` §3(b)) after review
  found the project's own prior write-ups of Cube_CES/cube_Sale_APD agreement had been read as
  validating correctness rather than merely consistency.
- **`METRICS.md` is the single source of truth for how every reported metric is defined and
  computed.** An agent that needs to compute a metric not defined there must stop and report the
  gap, not improvise a definition — and when two agents compute the same metric independently and
  get different answers, `METRICS.md` itself (not either agent's code) is the first thing to
  check for ambiguity, per its own header. This rule exists because Phase E1's Modeler and
  Validator independently computed `stock_value` two different, both-defensible ways (Min-based
  vs. a time-averaged simulated figure) and a segmentation threshold two slightly different ways
  (66 vs. 68 items) — neither was a bug, but neither had a written definition to be checked
  against, so the disagreement could not be resolved as a simple lookup. See `METRICS.md` itself
  for the locked formulas, and its entries for `stock_value` and `segment_policy criteria`
  specifically for that incident's resolution.

## Reproducibility

- Pin library versions in `requirements.txt`, because different `statsforecast` versions can
  produce different results.
- Set random seeds where any randomness exists.
- Record for every run which data cutoff date and which config were used, so results can be
  compared across runs.

## Git

- Small, focused commits with descriptive messages.
- Never commit data files or credentials.
- Never commit generated output, since it can always be regenerated.

## Logging

- Use the `logging` module rather than `print`.
- Every script must report how many rows were processed, how many were dropped, and why.

## Documentation

- Docstrings state what a function does, what it takes and what it returns.
- Comments explain why, not what.
- Record decisions with their reasoning in `STATUS.md`.
- **When recording any decision, state explicitly whether it applies to the whole project or only
  to a pilot, task or phase.** A condition adopted for a pilot must never be written as a project
  rule. This rule exists because a pilot filter (`division = 'PEM101'`) was recorded in `STATUS.md`
  as project scope and propagated unquestioned into Phase C — see `STATUS.md` Locked Decisions,
  "Project scope correction," for the full account.
- **Any specific figure, threshold or attribution stated without a cited source must be treated
  as unverified until checked.** This applies to a remembered number as much as a guessed one —
  confident recall is not a citation. Two examples from this project: the original SBC (2005)
  model assignment ("Croston for Erratic demand") was stated incorrectly from memory and only
  corrected once the primary paper (Kostenko & Hyndman 2006, reproducing SBC's own Figure 1) was
  actually consulted — see `STATUS.md`, the rule-based selection entry, "Correction made before
  implementation," for the full account. An annual holding cost rate of 15-25% was described as
  an industry standard without a cited source; it must be treated as a configurable assumption
  for Phase 4, not a fact, until a source is checked — see `STATUS.md` §8.4 ("To be derived from
  `Cube_Inventory_Exact` instead of requested," holding cost) for the related Phase 4 holding-cost
  approximation this rate would feed into.

---

**Rule: every task must begin by reading `STATUS.md`, `CONVENTIONS.md` and `METRICS.md`.**
