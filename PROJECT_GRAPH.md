# PROJECT GRAPH

A dependency graph in four layers: **Evidence** feeds **Questions**, **Questions** feed
**Decisions**, **Decisions** feed **Goals** (G1 sales forecast, G2 inventory policy, G3 operations
plan for purchasing and production). Every fact behind a node's status is cited to DATA_MAP.md or
STATUS.md — this file states status and dependency, not new evidence.

Every future task reads this file first (CONVENTIONS.md, Part 4). When a task changes a node's
status, it updates this file (CONVENTIONS.md, Part 4).

## Critical path

**As of 2026-09-24, the critical path runs: E11 → E12 → Q10 → (blocks D9's resolution and every
downstream G2 figure).** Phase J found the Section 16 model fails calibration against actual
delivery performance (E11); Phase J2's four Explorers each tested a candidate explanation and each
falls short (E12); **how the business actually fulfils orders and how fast it replenishes (Q10)
remains unresolved** — and every G2 figure (Min, Max, stock_value, fill_rate, segment policy) is
marked UNCALIBRATED and depends on Q10 being answered before it can be trusted for a decision.
Q10 is **blocked on a person** (production/warehouse planning — see DATA_MAP.md §5, item 15, for
the exact input named).

## Status legend

| Color | Status |
|---|---|
| Green | done |
| Yellow | in progress |
| Orange-red | blocked on data |
| Purple | blocked on a person |
| Orange, dashed border | uncalibrated |
| Dark grey | closed, no downstream use (dead end) |

## Graph

```mermaid
flowchart TD
    classDef done fill:#b7e4c7,stroke:#2d6a4f,color:#1b4332
    classDef inprogress fill:#ffe08a,stroke:#b08900,color:#5c4400
    classDef blockeddata fill:#ffb4a2,stroke:#a4133c,color:#590d22
    classDef blockedperson fill:#c9b6e4,stroke:#5a189a,color:#3c096c
    classDef uncalibrated fill:#f4a261,stroke:#e63946,color:#5c2a00,stroke-dasharray: 5 3
    classDef closed fill:#6c757d,stroke:#343a40,color:#ffffff

    subgraph EVIDENCE["Evidence (from DATA_MAP.md)"]
        E1["E1: pricelist authoritative\nfor division"]
        E2["E2: -OLD tags swapped\nPEM102/PEM107"]
        E3["E3: cost = line total"]
        E4["E4: createDate = PODate\n(99.95%)"]
        E5["E5: MPS = Cube_CES\nBacklog"]
        E6["E6: Cube_Backlog lags\nCube_CES ~13.6h"]
        E7["E7: jobcode/jobno/OLMJobCode\n= batch reference"]
        E8["E8: 6-day median\ncustomer notice"]
        E9["E9: existing min/max\nunusable as input"]
        E10["E10: item-to-warehouse reverse\nfinds PEM103/PEM107 stock"]
        E11["E11: Phase J calibration_gap\n-84 to -93pp"]
        E12["E12: Phase J2 4 Explorers -\nnone explain the gap"]
        E13["E13: 73.2% was on_time_exact,\nnot fill_rate-comparable"]
        E17["E17: six-model backtest,\nTop-down beats Naive 4/5 divisions"]
    end

    subgraph DEADENDS["Dead ends (closed, no downstream edge)"]
        DE1["DE1: Feb-Jul 2026 window\nanomaly - unresolved, stopped"]
        DE2["DE2: cross-division/Tendering\ncoverage outside pricelist scope\n- documented exclusion, not modelled"]
        DE3["DE3: quantity-clustering\nMOQ signal - business confirmed\nno MOQ data exists"]
    end

    subgraph QUESTIONS["Questions"]
        Q1["Q1: which division does\nan item belong to?"]
        Q2["Q2: is createDate the\nreal order date?"]
        Q3["Q3: what does MPS/Backlog\nmean across tables?"]
        Q4["Q4: which table sources\nconfirmed/open demand?"]
        Q5["Q5: what does jobcode\nrepresent?"]
        Q6["Q6: can existing min/max\nbe a policy input?"]
        Q7["Q7: which warehouses hold\nreal stock per division?"]
        Q8["Q8: what is the real\ncustomer order notice?"]
        Q9["Q9: does Section 16 reproduce\nactual delivery performance?"]
        Q10["Q10: HOW DOES THE BUSINESS\nACTUALLY FULFIL ORDERS?"]
        Q11["Q11: does quotation-based\nnotice explain the gap?"]
        Q12["Q12: are due dates aligned\nto delivery?"]
        Q13["Q13: does delivery come from\ncomponent stock/fast assembly?"]
        Q14["Q14: does production run\nin batches ahead of orders?"]
        Q15["Q15: what would Section 16\nneed to become?"]
        Q16["Q16: is 73.2% a valid\nfill_rate benchmark?"]
        Q17["Q17 (G3, proposed): production\nbatch cadence and size?"]
        Q18["Q18 (G3, proposed): BOM /\nshared components?"]
        Q19["Q19 (G3, proposed): assembly\nand inspection time?"]
        Q20["Q20 (G3, proposed):\nproduction capacity?"]
        Q21["Q21 (G3, proposed): MTS vs\nMTO vs ETO per item?"]
    end

    subgraph DECISIONS["Decisions"]
        D1["D1: pricelist is authoritative\n(CONVENTIONS.md rule)"]
        D2["D2: adopt Top-down Combination\nforecasting at Type level"]
        D3["D3: PEM101 128-item scope\n= pilot, not project-wide"]
        D4["D4: use forecast_date-keyed\nfrozen-snapshot series"]
        D5["D5: sellable warehouse codes\n= stated ASSUMPTION"]
        D6["D6: METRICS.md is the single\nsource of truth for formulas"]
        D7["D7: segment policy formula\n(with zero-P50, infeasible amendments)"]
        D8["D8: robust-upper-bound Tier A\ndefaults REJECTED/deferred"]
        D9["D9: every E0/E1/E2/Phase I\nfigure marked UNCALIBRATED"]
    end

    subgraph TIMETRACKS["Time-bound tracks"]
        T1["T1: forward test first\nscoreable 2026-09-30"]
        T2["T2: posting-delay snapshot\nreaches 60 days ~2026-11-21"]
    end

    subgraph GOALS["Goals"]
        G1["G1: sales forecast"]
        G2["G2: inventory policy"]
        G3["G3: operations plan\n(purchasing + production)"]
    end

    E1 --> Q1
    E2 --> Q1
    Q1 --> D1
    D1 --> D3
    D1 --> G1
    D1 --> G2

    E4 --> Q2
    Q2 --> D4
    D4 --> G1

    E5 --> Q3
    E6 --> Q4
    Q3 --> Q4
    Q4 --> D6

    E7 --> Q5
    Q5 -.-> D7

    E9 --> Q6
    Q6 --> D6
    E10 --> Q7
    Q7 --> D5
    D5 --> G2

    E8 --> Q8
    Q8 --> Q10

    E17 --> D2
    D2 --> G1
    D3 --> G1
    T1 --> G1

    E11 --> Q9
    Q9 --> Q10
    E12 --> Q10
    Q10 -.->|blocked on a person| Q15
    Q11 --> Q10
    Q12 --> Q10
    Q13 --> Q10
    Q14 --> Q10
    T2 --> Q10

    Q15 --> D8
    D8 --> D9
    D9 --> G2
    D6 --> G2
    D7 --> G2

    E13 --> Q16
    Q16 --> D6

    Q10 -.->|proposed| Q17
    Q10 -.->|proposed| Q18
    Q10 -.->|proposed| Q19
    Q10 -.->|proposed| Q20
    Q10 -.->|proposed| Q21
    Q17 -.-> G3
    Q18 -.-> G3
    Q19 -.-> G3
    Q20 -.-> G3
    Q21 -.-> G3
    G2 -.->|needed, not yet in the right form| G3

    class E1,E2,E3,E4,E5,E6,E7,E8,E9,E10,E11,E12,E13,E17 done
    class DE1,DE2,DE3 closed
    class Q1,Q2,Q3,Q4,Q6,Q7,Q8,Q9,Q11,Q12,Q13,Q16 done
    class Q5,Q15 inprogress
    class Q10 blockedperson
    class Q14 blockeddata
    class Q17,Q18,Q19,Q20,Q21 blockedperson
    class D1,D2,D3,D4,D6,D7,D8,D9 done
    class D5 uncalibrated
    class T1,T2 inprogress
    class G1 inprogress
    class G2 uncalibrated
    class G3 blockedperson
```

## Node table

| Node | Status | Depends on | Unblocks | Evidence for status | Blocker type |
|---|---|---|---|---|---|
| E1 | done | — | Q1 | DATA_MAP.md §2, division/-OLD tags; §4 Trap 2 | — |
| E2 | done | — | Q1 | DATA_MAP.md §1 (cube_Sale_APD), §4 Trap 2 | — |
| E3 | done | — | (feeds D6/METRICS.md §1 directly) | DATA_MAP.md §2, cost; §4 Trap 1 | — |
| E4 | done | — | Q2 | DATA_MAP.md §2, createDate/PODate | — |
| E5 | done | — | Q3 | DATA_MAP.md §2, status mapping; §4 Trap 4 | — |
| E6 | done | — | Q4 | DATA_MAP.md §1 (Cube_Backlog); §4 Trap 5 | — |
| E7 | done | — | Q5 | DATA_MAP.md §2, jobcode/jobno/OLMJobCode | — |
| E8 | done | — | Q8 | STATUS.md Business Findings, 6-day median notice | — |
| E9 | done | — | Q6 | DATA_MAP.md §1 (Cube_Inventory_Exact) | — |
| E10 | done | — | Q7 | DATA_MAP.md §3 Joins (warehouse↔division, reverse); §4 Trap 8 | — |
| E11 | done | — | Q9 | STATUS.md Phase J entry, calibration_gap | — |
| E12 | done | — | Q10 | STATUS.md Phase J2 entry; `output/summary/phaseJ2_synthesis_report.md` | — |
| E13 | done | — | Q16 | METRICS.md §19; DATA_MAP.md §4 Trap 12 | — |
| E17 | done | — | D2 | STATUS.md Phase C step 2 report, Top-down transferability | — |
| DE1 | closed, no downstream use | — | (none — investigated and stopped) | STATUS.md, Modeler-tasks-1-3 log entry; reversal persists but is not chased further | — |
| DE2 | closed, no downstream use | — | (none — documented, not modelled) | `config/config.yaml` cross_division_excluded_value_thb comment; STATUS.md Locked Decisions | — |
| DE3 | closed, no downstream use | — | (none — business confirmed absent) | STATUS.md §8.3 "Removed from the data request list" | — |
| Q1 | done | E1, E2 | D1 | Answered — pricelist is authoritative | — |
| Q2 | done | E4 | D4 | Answered — createDate ≈ PODate, usable as order date | — |
| Q3 | done | E5 | Q4 | Answered — MPS = Cube_CES Backlog | — |
| Q4 | done | E6, Q3 | D6 | Answered — Cube_CES Status='Backlog', not Cube_Backlog table | — |
| Q5 | in progress | E7 | D7 (loosely) | Batch-reference meaning established; populating mechanism still unresolved (DATA_MAP.md §5 item 11) | data |
| Q6 | done | E9 | D6 | Answered — no, existing settings unusable as input | — |
| Q7 | done | E10 | D5 | Answered for division/sharing; sellability itself remains a standing assumption (DATA_MAP.md §5 item 9) | — |
| Q8 | done | E8 | Q10 | Answered — 6-day median, but Phase J2 found this doesn't explain real fulfilment speed | — |
| Q9 | done | E11 | Q10 | Answered — no, the model does not reproduce actual delivery performance | — |
| **Q10** | **blocked on a person** | E12, Q8, Q9, Q11, Q12, Q13, Q14, T2 | Q15, D8, D9, G2 | Phase J2 synthesis: not achievable from data alone; exact input named (DATA_MAP.md §5 item 15) | **person** |
| Q11 | done | (Explorer A) | Q10 | Contradicted — `output/summary/phaseJ2_explorerA_report.md` | — |
| Q12 | done | (Explorer B) | Q10 | Contradicted — `output/summary/phaseJ2_explorerB_report.md` | — |
| Q13 | done | (Explorer C) | Q10 | Contradicted as general explanation — `output/summary/phaseJ2_explorerC_report.md` | — |
| Q14 | blocked on data | (Explorer D) | Q10 | Partially supported; decisive test needs a re-pull of `cube_final.final_date` — `output/summary/phaseJ2_explorerD_report.md` | **data** |
| Q15 | in progress | Q10 | D8 | Proposed in words (synthesis report); not implemented, and not finalizable until Q10 answered | — |
| Q16 | done | E13 | D6 | Answered — no, corrected `not_late` figures now used instead | — |
| Q17 | blocked on a person | Q10 (implicitly) | G3 | Proposed this task, Part 3; no data source evaluated yet | **person** |
| Q18 | blocked on a person | Q10 (implicitly) | G3 | Proposed this task, Part 3 | **person** |
| Q19 | blocked on a person | Q10 (implicitly) | G3 | Proposed this task, Part 3 | **person** |
| Q20 | blocked on a person | Q10 (implicitly) | G3 | Proposed this task, Part 3 | **person** |
| Q21 | blocked on a person | Q10 (implicitly) | G3 | Proposed this task, Part 3 | **person** |
| D1 | done | Q1 | D3, G1, G2 | CONVENTIONS.md, Data Correctness rule | — |
| D2 | done | E17 | G1 | STATUS.md Locked Decisions, "Final forecasting method" | — |
| D3 | done | D1 | G1 | STATUS.md Locked Decisions, "Project scope correction" | — |
| D4 | done | Q2 | G1 | STATUS.md Locked Decisions, series key | — |
| D5 | uncalibrated | Q7 | G2 | Standing business assumption, never confirmed by any field (DATA_MAP.md §2, warehouse field) | — |
| D6 | done | Q4, Q6, Q16 | G2 | METRICS.md header; CONVENTIONS.md | — |
| D7 | done | Q5 (loosely) | G2 | METRICS.md §15, incl. 2026-09-22/2026-09-23 amendments | — |
| D8 | done | Q15 | D9 | STATUS.md Phase J2 Part 0 entry (revert) | — |
| D9 | done | D8 | G2 | STATUS.md banner + per-phase tags | — |
| T1 | in progress | — | G1 | STATUS.md, "First scoreable target month is 2026-08, safe to score only from 2026-09-30" | time |
| T2 | in progress | — | Q10 | STATUS.md, "Prospective posting-delay measurement: STARTED 2026-09-22" (+60 days ≈ 2026-11-21) | time |
| **G1** | in progress | D1, D2, D3, D4, T1 | — | Forecasting method adopted and locked; Phase F (compare against the team's current method) not started | time (Phase F) |
| **G2** | **uncalibrated** | D1, D5, D6, D7, D8, D9 | G3 (partially) | Phase J's calibration_gap; every figure banner-tagged in STATUS.md | **person** (Q10) |
| **G3** | blocked on a person | Q17-Q21 | — | No question nodes existed before this task; all proposed, none answered | **person** |

## Time-bound tracks (detail)

- **T1 — forward test.** `output/summary/forward_test_log.csv` logs real forecasts as they are
  made; the leakage-guard margin (30 days) makes 2026-08 the first target month, **safe to score
  only from 2026-09-30** (STATUS.md, "Forward-test scoring for the 335-item log"). Feeds G1's own
  validation, independent of Phase F.
- **T2 — posting-delay snapshot.** `src/snapshot_daily.py`, a Windows Scheduled Task, started
  **2026-09-22**; the leakage-guard margin cannot be revisited until **≥60 days of daily snapshots
  exist and the script's own p99 is known from that data** (STATUS.md, "Prospective posting-delay
  measurement: STARTED 2026-09-22") — reaches 60 days around **2026-11-21**. Feeds Q10 (helps
  characterise real posting/entry lag, one input to the fulfilment-mechanism question).

## Dead ends (detail)

- **DE1 — the February to July 2026 window anomaly.** The createDate-vs-forecast_date reversal in
  rolling-origin backtesting was tested against three candidate causes (back-dating, the dominant
  focus item, order-timing/concentration) and none fully explained it; STATUS.md records this as a
  **known limitation, not chased further** — it directly motivated treating rolling-origin as
  PRIMARY and the single train/val/test split as SECONDARY ONLY, but has no further downstream
  investigation node.
- **DE2 — cross-division demand / coverage outside the pricelist-based Omni-Channel scope.**
  ₿60.6M (14.3%) of sales for the pilot codes sits under other divisions/channels; once
  channel/status are held fixed, the real Omni-Channel-scope exclusion is only ₿2.96M (0.42%) —
  **documented as a known exclusion, not modelled further** (`config/config.yaml`
  `cross_division_excluded_value_thb`).
- **DE3 — minimum order quantity / lot size.** 68 of 82 testable items showed quantity-clustering
  suggestive of a lot size, but the business confirmed this data does not exist at all — **removed
  from the data request list**, the suggestive evidence is kept on record but no value was ever
  set from it (STATUS.md §8.3).

## Part 3 — G3's question nodes (proposed, pending business confirmation)

G3 (operations plan for purchasing and production) has had no question nodes until this task —
which itself means it was unknown what an operations plan needs from G2. Working backwards from
what a purchasing/production plan must decide (what to order or produce, how much, and when), five
question nodes are proposed below. **All five are PROPOSED ONLY — none is answered here, per task
instruction.**

| Node | Question | Evidence in the database | Notes |
|---|---|---|---|
| Q17 | What production batch cadence and size does each item/family run on? | **Partial.** `cube_final.jobno`/`Cube_CES.OLMJobCode` establish that batching happens and that one batch serves many contracts (DATA_MAP.md §2, jobcode), but the true batch date/size fields (`cube_final.final_date`, `job_qty`, `fg_pack_date`) were not successfully pulled this session (§4 Trap 7) — cadence and size are not yet computable even where the mechanism is confirmed. | Directly blocked by Q10/Q14's open data gap. |
| Q18 | What bill of materials and shared components exist across items? | **Partial.** `Cube_BOM_Exact` exists and was used once to corroborate a Finished-Goods/Raw-Material split (DATA_MAP.md §1, "Other tables") — it has not been read for its own content (which components, shared across which items) at all. | A real table exists; this project has never queried it for BOM content itself. |
| Q19 | What is assembly and inspection time per item? | **Absent.** No field in any table links a raw-material consumption event to an assembled item becoming stock — a confirmed, hard gap (DATA_MAP.md §5, item 1). `cube_final`'s undiscussed `fg_check_date`/`qacheck_date`/`fg_final_date` columns (found, not analysed, this session) are the nearest untested lead. | Needs the business, or a successful, deeper `cube_final` pull. |
| Q20 | What is production capacity (lines, labour, equipment) over time? | **Absent.** No table found anywhere in this project's investigations records a capacity figure of any kind. | Needs the business entirely. |
| Q21 | Which items are made-to-stock vs. made-to-order vs. engineer-to-order? | **Partial, and known to be unreliable at face value.** `manufacturing_type` (MTS/MTO/ETO) exists in `cube_Sale_APD` but is an ORDER-level attribute, not a fixed per-item classification — 100 of 113 items show more than one value across their own sales rows (DATA_MAP.md §2, manufacturing_type). Using it directly as a per-item classification would repeat a known trap. | A per-item MTS/MTO/ETO classification would need to be derived (e.g. a mode or business rule) or confirmed by the business — not read off this column directly. |

### What G3 would consume from G2, and whether the current form fits

G3 (an operations plan for purchasing and production) would consume, from G2: **Min, Max, and
segment policy (finished_goods_stock / component_stock_ato / component_stock_ato_infeasible /
placeholder / excluded) per item**, and ideally `stock_value` and `fill_rate` as decision-quality
signals.

**The current G2 outputs are not yet in the form G3 needs, for three stated reasons:**

1. **G2's own figures are UNCALIBRATED** (D9, this graph) — Phase J found the model that produces
   Min/Max/stock_value/fill_rate does not reproduce actual delivery performance. An operations plan
   built on uncalibrated Min/Max would be planning against a policy the business doesn't actually
   run. G3 cannot safely consume G2's numbers until Q10 is answered.
2. **G2's segment policy answers "how should this item be stocked," not "when and how much to
   produce."** Min/Max describes a target inventory POSITION; it says nothing about batch timing,
   batch size, or production sequencing — the actual decisions G3 needs to make (Q17-Q20 above).
   Even a fully calibrated G2 would need to be paired with the G3 question nodes' answers before it
   becomes an operations plan.
3. **Segment policy is a per-item, not a per-batch or per-production-line, unit.** G3 likely needs
   items GROUPED by shared component/BOM (Q18) and by production line/family (Q17, Q20) — a
   different aggregation than G2's per-item Min/Max, which would need to be re-rolled-up, not used
   item-by-item, once that grouping is known.

**What is missing, stated plainly**: everything in the Q17-Q21 row above that is "Absent" or
"Partial" — assembly/inspection time, capacity, batch cadence/size, and a reliable (not
order-level) make-to-stock/make-to-order classification. None of this can be manufactured from the
tables already queried by this project; each needs either a successful deeper pull (the `cube_final`
production-stage dates) or business input (capacity, BOM content read in full, assembly/inspection
time, the real MTS/MTO/ETO split).
