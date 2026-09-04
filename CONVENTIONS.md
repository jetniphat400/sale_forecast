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

---

**Rule: every task must begin by reading `STATUS.md` and `CONVENTIONS.md`.**
