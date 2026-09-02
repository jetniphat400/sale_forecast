# AGENTS

This file defines how multi-agent work is organised on this project, when it applies. It applies
to every phase of work (see `STATUS.md` for the current phase plan) — but **multiple agents are
not the default**. Whether a given phase (or task within a phase) uses one agent or several is a
decision the Orchestrator must justify with the decomposition test below, not an assumption.

## Multi-agent systems are not universally better

Research on multi-agent systems shows they do not automatically outperform a single agent.
Coordination failures account for roughly 37% of all failures in common multi-agent frameworks;
running multiple agents costs around 15x the tokens of a single interaction; and a single
well-prompted agent often matches or beats a multi-agent setup on tasks that fit inside one
context window. Multiple agents pay off only when work genuinely splits into independent
subtasks that need different skills — not by default, and not just because a task is large or a
phase has several parts.

## Decomposition test (apply before splitting any work)

Before the Orchestrator splits a task across multiple agents, it must apply this test:

- **Split only when both hold**: (a) the subtasks are independent of each other's *results* —
  none needs to know what another found before it can start or finish its own work; and (b) the
  subtasks require *different capabilities* (e.g. database search vs. statistical analysis vs.
  model backtesting), not the same kind of work merely chunked into pieces.
- **If subtasks share the same context, or one genuinely must run before another can start
  (a real sequential dependency), use a single agent** for that piece of work instead of
  splitting it across agents that would only end up passing state back and forth.
- **Default to a single agent when unsure.** The burden of proof is on splitting, not on staying
  single: an unnecessary split costs roughly 15x the tokens for no accuracy benefit, and adds a
  coordination-failure risk that a single agent does not carry.

## Structure (when the decomposition test says to split)

One **Orchestrator** coordinates up to five worker agents: **Explorer**, **Validator**,
**Analyst**, **Modeler**, **Synthesizer**. The Orchestrator breaks the split-worthy part of a
phase into tasks and dispatches them to the worker agents that fit; it does not do the work
itself. Not every phase uses every role, and several phases use only one worker agent for most or
all of their work — see "Per-phase agent pattern" below for what this project actually does.

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
- Applies the decomposition test above before splitting any task — does not split by default.
- Breaks a phase into tasks and dispatches them to the worker agents (one agent, if the
  decomposition test says so).
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
7. **Separate what is confirmed from data from what is inferred.** Every output must mark each
   claim as either directly confirmed (a query result, a direct recomputation) or inferred/
   interpreted from it. **A receiving agent must never treat another agent's inference as fact**
   — it must independently verify before relying on it as established, or carry it forward
   explicitly labelled as "inferred by [agent]," never stated as settled.
8. **Cite the source of every figure passed between agents.** Every number one agent hands to
   another agent, to the Orchestrator, or to the Synthesizer must cite the query, script, or file
   it came from, so it can be checked independently rather than taken on trust.
9. **When agents disagree, the Synthesizer reports both positions with their evidence and leaves
   the decision to the human. It does not pick a side.** Resolving a genuine disagreement between
   two agents' findings is not the Synthesizer's job — surfacing it clearly enough for a human to
   decide is.

## Orchestrator rules

- Apply the decomposition test before splitting any task; default to a single agent when unsure.
- Dispatch independent tasks in parallel; only serialise tasks that genuinely depend on each
  other's output.
- Never skip a phase — later phases consume earlier phases' outputs, so skipping ahead means
  redoing work once the skipped phase's findings arrive.
- When agents' findings conflict, re-check only the specific point in conflict rather than
  re-running everything — a targeted re-check is faster and keeps the rest of the phase's
  evidence intact.
- Close each phase by updating `STATUS.md` with what was found, at what confidence, and what
  remains open.

## Per-phase agent pattern

Which pattern a phase uses, and why, decided by applying the decomposition test above — not a
fixed default. Recorded here so the reasoning is not re-litigated each time; see `STATUS.md` for
the phases' actual status and findings.

- **Phase A** used **three parallel agents** because the three questions (is `forecast_date`
  revised, why did 2025 fall, which date field keys the series) were independent of each other's
  results and needed different capabilities (Explorer+Validator, Analyst, Validator). **Done.**
- **Phase B is mixed.** Designing how Category level supports item level, and confirming
  combination forecasting, uses a **single Modeler**, because it needs all three aggregation
  levels (Category, Type, Item) in one view to reason about consistently — splitting them would
  mean passing shared context back and forth, which the decomposition test rules out. The three
  open items — cross-division demand, items with no history, and the stale forward-test log —
  run as **three parallel agents**, because they are independent of each other's results (each can
  be resolved without knowing the others' outcome). Writing tests and the pipeline uses a **single
  agent**, because it needs the whole codebase in view to place tests and wire a run order
  consistently, not a chunk of it in isolation.
- **Phase C** uses **five parallel Validators**, one per division (PEM102, PEM103, PEM104,
  PEM107, CI101), for data-quality checks that are independent of each other and identical in
  kind — then a **single Modeler** runs all forecasts in one pass (needs the combined dataset in
  one view), then a **Synthesizer** compares divisions against PEM101.
- **Phase D** uses **three parallel Explorers**, one each for finished-goods movement history,
  assembly time, and sellable-stock stages — independent searches needing the same capability
  (database search) but over disjoint questions — with the stopping rule applied strictly (each
  Explorer must stop and report a gap rather than keep searching), then a **Synthesizer**.
- **Phase E** uses a **single Modeler** for Max-Min calculation and simulation, since it combines
  forecast, lead time and variability in one calculation that cannot be usefully split (the three
  inputs share context and feed one result), with a separate **Validator** recomputing every
  figure independently as a check.
- **Phase F** uses a **single Analyst** — one coherent comparison (this project's method vs. the
  team's current method vs. no intervention), not a task that splits into independent pieces.
