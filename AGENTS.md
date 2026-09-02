# AGENTS

This file defines how multi-agent work is organised on this project. It applies to every phase
of work (see `STATUS.md` for the current phase plan), not to any single phase.

## Structure

One **Orchestrator** coordinates five worker agents: **Explorer**, **Validator**, **Analyst**,
**Modeler**, **Synthesizer**. The Orchestrator breaks a phase into tasks and dispatches them to
the worker agents; it does not do the work itself.

```
                    Orchestrator
                         |
   -------------------------------------------------------
   |          |            |            |                |
Explorer   Validator    Analyst      Modeler        Synthesizer
```

## Roles and boundaries

### Orchestrator
- Reads `STATUS.md` and `CONVENTIONS.md` before dispatching any task.
- Breaks a phase into tasks and dispatches them to the worker agents.
- Checks whether agents' findings conflict with each other.
- Decides when a phase has enough evidence to close.
- Updates `STATUS.md` at the end of a phase.
- **Does not perform analysis itself.** If a question needs a query, a statistic, a model, or a
  data-quality check, that work belongs to a worker agent, not the Orchestrator.

### Explorer
- Searches the database for the data a task requires.
- Tests joins across tables and reports match rates from actual queries run against the data.
- **Does not interpret business meaning.** Reports what a join or a query returns, not what it
  implies for the business. Interpretation belongs to the Analyst or the Synthesizer.

### Validator
- Checks data quality: completeness, duplicates, contradictions between sources.
- Verifies figures against direct recomputation before they are trusted downstream.
- **Does not modify data.** Reports what is wrong and how confident that finding is; fixing or
  cleaning data is a decision for the Orchestrator/business, not an action the Validator takes
  unilaterally.

### Analyst
- Analyses patterns, computes statistics, answers business questions from data the Explorer
  found and the Validator checked.
- **Does not select models.** Characterising demand, trends, or relationships is in scope; deciding
  which forecasting model to adopt is not — that belongs to the Modeler's performance results and
  the Orchestrator's decision.

### Modeler
- Builds and runs models, backtests them, measures performance (MAE, RMSE, Bias, or whichever
  metrics the phase specifies).
- **Does not decide which model to adopt.** Reports how each candidate performed; the decision to
  lock one in is the Orchestrator's, informed by the Modeler's results and the Synthesizer's
  cross-check.

### Synthesizer
- Merges findings from all other agents for a phase.
- Surfaces conflicts between agents' findings explicitly.
- States plainly what is now known, with what confidence, and what is still missing.
- **Does not gather new data.** Works only from what Explorer, Validator, Analyst and Modeler
  have already produced; if something is missing, it reports the gap rather than filling it.

## Rules binding every agent

1. **Never guess.** If the data does not answer a question, say so. Never infer business meaning
   from a column name alone — a name is a hypothesis about what a column holds, not evidence.
2. **State a confidence level for every conclusion, with the evidence behind it.** A conclusion
   without stated confidence and evidence is incomplete.
3. **Stopping rule.** If a search fails, conclude with what was checked and which team must
   supply the missing data, then stop — do not keep searching. This project has repeatedly
   cycled through rounds ending in "not enough data"; this rule exists to end that cycle rather
   than repeat it.
4. **Report contradictions explicitly.** If a finding contradicts an earlier one, say so directly
   and say what changed. Never overwrite a previous conclusion silently.
5. **Write results to `output/summary/`, in a separate file per agent.** Each agent's output must
   be independently readable and attributable to that agent.
6. **Read `STATUS.md` and `CONVENTIONS.md` before starting any task.**

## Orchestrator rules

- Dispatch independent tasks in parallel; only serialise tasks that genuinely depend on each
  other's output.
- Never skip a phase — later phases consume earlier phases' outputs, so skipping ahead means
  redoing work once the skipped phase's findings arrive.
- When agents' findings conflict, re-check only the specific point in conflict rather than
  re-running everything — a targeted re-check is faster and keeps the rest of the phase's
  evidence intact.
- Close each phase by updating `STATUS.md` with what was found, at what confidence, and what
  remains open.
