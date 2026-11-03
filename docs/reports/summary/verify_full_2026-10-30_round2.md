# Full verification, round 2 (Prompt 62A round 2)

Snapshot: origin/main `2a39447a1f75e4e543b55ee13485e29bb6324589` ("Prompt 64 docs"). The live repository has since moved to `07a6e86` (Prompt 65); nothing after `2a39447` was assessed except where stated.
Method: fresh Validators, each recomputing with its own code, never importing `src/`, read-only. Every Critical or High went to a second fresh Validator. Findings: `verify_full_2026-10-30_round2_findings.csv` (127 rows). Examples with real numbers: appendix in `verify_full_2026-10-30_worked_examples.md`.

## 1. Summary

- **One Critical.** The PEM101 "Value of Min level" box shows THB 65.59M, but 15 of the 92 items have a unit cost and are left out with no note on the page. The Sec.6 figure is about THB 82.36M (page 20% low). Confirmed by two Validators (R2B1-001).
- **Two High.** (a) Reserved de-duplication drops 3,939 units (8.3%) that look like separate plan lines; the inventory page and the operation plan disagree (T1-001). It becomes Critical if the owner confirms they are separate lines. (b) The "today" stock value 15.49M is labelled 92 items but covers 77 (R2B1-002).
- **What affects 2026-11-05:** nothing found that makes the run fail. Step 10's MAE gate will read "not tested" (no successful baseline run exists); the MAE and stock gate tests do not guard sign or threshold; an empty PEM107 pull would give exit 2 after a push (inferred, not executed); the monthly task restarts 4 times at 15-minute intervals while METRICS Sec.53 says 0; the 2026-11-02 12:00 daily rebuild failed its "months and items unchanged" gate (not investigated).
- **Round-1 gaps closed:** database decisions, unit cost and stock value, the PEM101 simulation, Holt/Sec.41, material lists, the four documents, the full test suite (1127 passed) and mutation checks (28, 22 killed). Prompt 64 is correct apart from wording.
- **Counts:** 127 rows: 1 Critical, 2 High, 42 Medium, 69 Low, 13 none; verdicts 12 correct, 103 wrong, 12 unclear.

## 2. Decisions asked for

### T1-001 Reserved de-duplication (High; Critical if owner confirms)
- Cube_CES `Backlog` rows for the 445 Price List codes: 765 rows, 47,349 units (ActualQty+BacklogQty), identical to the saved pull.
- 749 contract+item groups; 13 groups have more than one row (29 rows). The code keeps the first row: 749 rows, 43,410 units; 16 rows and 3,939 units (8.3%) removed.
- In all 13 groups every row has its own PlanID (unique across all 765 rows), its own forecast and plan delivery dates and its own plan quantity and price. True duplicates: 0 rows, 0 units. They are separate plan lines (database evidence, one Validator; the re-check saw different delivery dates in every group but could not test PlanID because saved pulls carry no PlanID).
- Stock available: counting every line lowers the total from 132,363 to 128,424; 13 items change; CA-F-99-010203 flips from +11 to -19; negative-available items 73 to 74.
- Operation plan: it does **not** de-duplicate (matches the recorded file, difference 0). Applying the Sec.14 rule would cut 5-month demand by 816.9 units. The two published outputs disagree.
- The kept row is arbitrary (no ORDER BY): removed units range 3,348 to 3,941 by row order. 12 rows with ActualQty not 0 add 122 units of old residue and 42 of part-delivered over-count.
- **Recommendation:** stop the contract+item de-duplication, key on PlanID (unique), use one rule for page and plan, add PlanID to the pull, correct METRICS Sec.14 and the "ActualQty always 0" comment. Owner decision needed on the 12 rows.

### T1-003 `delivery_performance.py` filter (wrong, Medium)
128 pilot codes, 39,512 Omni Actual/Backlog rows. The script keeps 38,229. The `ManuDivision = PEM101` filter drops 984 rows (2.6%, 34,624 Actual units) that the Price List rule keeps; the 2023 CtrDate floor drops 206 PEM101 Actual rows (140,568 units). 1,283 rows (3.2%) in total. It is an investigation script and the docstring says so, but it conflicts with Trap 2 and 18.

### T1-005 duplicate sales copies (not duplicates, Low)
1,334 extra copies, 976 groups, 35,995 units, THB 53.38M (PEM101 869, PEM107 368, PEM103 64, CI101 18, PEM102 15), reproduced. Adding planid leaves 0 extra rows in every division. They are separate sales; keep them.

### Completeness (correct)
Trend, reserved and PEM107 pulls match the source exactly. Raw sales (+5 rows) and pilot (+1 row) differ only by rows and status changes after the pull. Open items: stock differs by 26 units (0.015%); production orders 4,719 saved vs 4,434 now with start date up to 10-05.

## 3. Results by item

**B1 Unit cost and stock value.** 16 items checked at cut-off 2026-09-22: 128/128 pilot costs and 438/445 full-scope costs match; fallback (fewer than 3 rows, none in window) and no-cost cases reproduced. Recorded stock values for PEM101, PEM103 and the current stock values match exactly; PEM107 within 0.3%. Costs are frozen at the 09-22/09-23 pull and not refreshed by monthly or daily runs (Medium): against the 11-02 pull stock values would move +1.0% to +6.6%.

**B2 PEM101 calibration simulation.** Own simulator matched all 37 members, the 4,130-point grid, the targets 97.66% and 98.24%, the curve and the default preset (r=0.7599, THB 14,170,763). R2B2-001 (Medium): the 98.24% target is validation-only but the curve window is combined; like-for-like gives r=0.899 and about THB 15.37M, so published Min is about 15% lower. R2B2-002: focus items sit at 71.7% and 73.3% not-late against 97.2% for the division.

**B3 Holt, Sec.41, material lists.** 288 Holt rows match (difference 0), hashes match, none scored yet. Sec.41: all 10 rows reproduce, only PEM101 significant. Material lists: 130 and 708 materials, all 838 rows match. R2B3-001 (Medium, unclear): the "too late" quantity omits the in-window months that Sec.43 says it includes (660 of 708 materials, 555,387 units).

**C1 Documents** (STATUS 8,113 lines, METRICS 1,635, DATA_MAP 2,122, PROJECT_GRAPH 561, all read). 80 docs-vs-code or docs-vs-docs findings, none Critical or High, 28 Medium. Main themes: stale line citations (more than 100 `STATUS.md:NNNN` cites), superseded decisions with no marker (lead time, PEM104 reason, cube_final, posting-delay, channel_scope), config keys that record decisions but no code reads them, ~15 evidence reports held only as untracked local files, Handover launcher text stale.

**C2 Tests.** `2a39447` in a throwaway copy with the scheduled task's `.env`: 1127 passed, 0 failed, 0 skipped, 26 min 18 s, 0 database attempts. The 20 round-1 failures happen only without `.env`. 28 mutations: 22 killed, 6 survived. Step 10 gate tests (R2C2-002) do not guard sign or threshold of the three gates (12 of 12 mutants survive); re-check rated it Medium; Prompt 65 now covers the six-month gate, not MAE and stock.

**D Prompt 64.** Step 8 limit 3600 s (`config.yaml:1438`, read at `monthly_refresh.py:1780`); `execWhyForecast` correct; `.gitignore` adds only `Claude outputs/`; hindcast figures match (company total Relative MAE 1.06 for (A) and 0.98 for (B); item level 0.818). Medium: forecasts are flat across horizons, so the horizon reading is confounded with calendar month. 2026-09 actuals could not be verified (temporary series gone).

## 4. Limits

- Anything after `2a39447` (Prompt 65 code and tests) was not assessed, except the step 10 gate mutation re-run.
- T1-001 PlanID evidence is single-sourced. The Oct-30 raw pull and the first database session's files were lost; later figures use 11-02 data where noted.
- R2B1-001: the page figure comes from running the page's own JavaScript under node, not a browser view.
- R2C1c-002 is inferred from code, not executed. R2D: no source for 2026-09 actuals.
- Task Scheduler state (clone junctions, hard link, registered trigger text) was read only by one reader; not independently verified.
- Database statements about row counts and business confirmation in DATA_MAP Sec.1-3 and Traps 1-22 were checked only where re-pulled.
