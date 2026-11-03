# Independent full verification, 2026-10-30 (Prompt 62A)

Snapshot verified: a fresh clone of origin/main, commit `869caeceddfb83d5c576be2c9febc54393707389`. Saved pulls and run logs were read from `D:\sale_forecast\output` (read only). No database connection was made (see "Limits"). Nothing in the repository, the publishing clone, the scheduled tasks or `output/` was changed or committed. These three files are the only things written.

Method: one Orchestrator, four fresh Validators (Teams 1-4), one extra fresh Validator for the part of Team 4's scope it did not reach (Team 4b), and one fresh re-check Validator for the High findings. Each Validator recomputed with its own code and did not import the project's `src/`. Every Validator was told to cite the METRICS/DATA_MAP section it checked and to report a docs-versus-code disagreement as a finding.

Verdict counts below are counts of findings rows in `verify_full_2026-10-30_findings.csv` (78 rows, some of which group many individual checks), not counts of cells.

---

## 1. Summary, with what affects the 2026-11-05 monthly run first

**No wrong figure was found on any published page in the areas traced, and no Critical finding was confirmed.** The forecast, the accuracy figures, the PEM101 and PEM107 Min/Max, the operation plan, the material plan and the lead times all recomputed to the recorded and published values.

**What affects 2026-11-05 (all High, all about the run failing or holding, none about a wrong figure):**

1. **Step 10's six-month gate may hold the push (RC-002).** The gate compares each new vintage with vintage 1, not the previous one, and holds above 25%. CI101 is already +20.2% between vintage 1 and 2 (767.9 to 923.3). The re-check estimates a 40-55% chance that at least one division breaches on 11-05. This is low-confidence: it depends on September actuals that do not exist yet. A breach sets the push to held and the exit code to 4, and vintage 3 is already in the log by then.
2. **A hold or failure leaves the publishing clone dirty and stops daily publishing (RC-003).** Nothing restores tracked files after step 7. The launcher exits 95 on any modified tracked file, so the daily 08:00/12:00 tasks, the Task Scheduler restarts and the next-day make-up run all stop until a person cleans the clone. No STATUS or METRICS text says what to do after a hold.
3. **A re-run after a hold can push vintage 3 with no six-month check (RC-004).** Step 5 skips on a same-month re-run, which turns the gate into "not tested".
4. **Step 8 has a 1800 s test timeout on origin/main (RC-001).** The suite takes about 1,290-1,506 s. A timeout ends the run with exit 1 and leaves the clone dirty (item 2). A fix to 3600 s exists in `D:\sale_forecast` (commit b8c7527), but that working copy is 5 commits ahead of origin/main and the launcher will not pull them.
5. **Other 11-05 points (Medium or lower):**
   - STATUS wrongly says the 08:00 launcher is not held on 11-05 (T4-004). It exits 95, so there is no 08:00 stock publish and 12:00 is the first.
   - The source guard first runs live on 2026-11-02 08:00, not on 10-30 12:00 as STATUS says (T1-006). Step 1 falls back to the files on disk, all 13 readable.
   - `check_new_vintage.py` is a manual extra. It does not replace step 10; the MAE gate becomes live in December (T4-005).
   - 20 tests depend on the author's database environment (T4-006).
6. **Possible wrong decision input, not yet decidable (T1-001, High, needs the database).** The Reserved de-duplication removes 3,939 units (8.3% of Reserved) on a (contract, item) key. If those rows are split lines, Reserved is under-stated, and the operation plan's demand (the larger of forecast and backlog) could be too low. A query on PlanID decides it.

---

## 2. Cross-check between teams, and re-checks

- **Conflicts between teams: none.** Overlapping findings agree:
  - the monthly series (Team 1 and Team 2 rebuilt it independently, both with 0 difference);
  - the vintage-2 fit series being the 10-05 pull (T1-004, T2-017);
  - Reserved 43,410 = 47,349 − 3,939 (T1-001, T4b-007);
  - the guard's first live run (T1-006, T4-007);
  - page figures that Team 2, Team 3 and Team 4b traced from different directions.
- **Sent to a fresh Validator for an independent re-check:** the three High findings of Team 4 (timeout, step 10 baseline, dirty clone). Results: step 8 timeout PARTLY confirmed (fix exists but is unpushed), step 10 PARTLY confirmed (the mechanics and the +20.2% reproduced; the breach probability is an estimate), dirty clone CONFIRMED. The re-check also found RC-004 and that the 1,392 s test time quoted by Team 4 is not in the repository (it was Team 4's own run).
- **Not re-checked:** T1-001 (High, needs the database).
- **Early alert:** given to the user during the work (before this report), as a High, with the note that it becomes Critical if "the run would fail" is read to include a held push.

---

## 3. Results per area

Counts of findings rows by verdict. The full list with evidence is in the CSV.

| area | correct | wrong | unclear |
|---|---|---|---|
| Extraction (SQL filters) | 2 | 2 | 1 |
| Completeness (offline) | 1 | 0 | 0 |
| Cleaning | 2 | 0 | 2 |
| Monthly series and leakage guard | 1 | 1 | 0 |
| Forecast models and placeholders | 5 | 1 | 2 |
| Accuracy (MAE, RMSE, Bias, Relative MAE, Tracking Signal) | 5 | 0 | 0 |
| Backtest leakage | 1 | 0 | 0 |
| Forward-test log, hashes, scoring | 3 | 0 | 0 |
| Min-Max (PEM101, PEM107, disabled states) | 4 | 0 | 3 |
| Operation plan | 1 | 0 | 0 |
| Material plan | 2 | 1 | 0 |
| Lead time v1 | 1 | 0 | 0 |
| Pages | 8 | 2 | 2 |
| Automation | 3 | 4 | 4 |
| Tests | 0 | 1 | 1 |
| Docs vs code vs config | 3 | 8 | 1 |
| **Total (78 rows)** | **42** | **20** | **16** |

Severities across the 78 rows: High 5 (RC-001 to RC-004 and T1-001), Medium 15, Low 29, none (correct) 29. No row is Critical.

### Area notes (what was checked and what the evidence shows)

**Extraction (Team 1).** Every SQL statement of the daily job, monthly step 1 and the pull helpers was listed with file and line. Omni Channel scope, Actual + MPS, `Status='Backlog'` in Cube_CES, no Cube_Backlog in the pipeline, `forecast_date` as the series key, and the Price List visible sheets are all as the docs say. Division equals the Price List sheet for all 335 scope items. Wrong or unclear: `order_leadtime.py:68` filters on the DB division column (T1-002, Medium; 81 rows or 0.28% dropped), `delivery_performance.py:61` uses another DB division column and a 2023 floor (T1-003, needs the database), and two one-off scripts have no Omni filter (T1-008, not scheduled).

**Completeness (Team 1).** Offline, every saved pull's row count equals the DATA_MAP/STATUS figure (raw sales 38,013 rows; pilot 28,668; stock 2,499; reserved 765; Trend 39,210; material inputs 18,698 / 689 / 25,843 / 36,619 / 50,223 / 7,460 / 4,863) with no null keys. The comparison with the source tables was not run (see Limits).

**Cleaning (Team 1).** Each rule was re-applied to the raw pull:
- createDate before 2024: 0 rows.
- `forecast_date` null or earlier than createDate: 16 rows, 47 units, THB 66,290; 10 sampled, all correctly removed.
- 31-month window, MPS kept, `-OLD` rows kept (2,049 rows, 25.8% of PEM102 and 38.9% of PEM107 sale value, matching DATA_MAP's 26-40%).
- Cost as a line total is handled in code; no data check was possible offline.
- Exact duplicates: 1,334 extra copies, 35,995 units (1.00% of quantity) and THB 53.38M (2.51% of sale), all kept (T1-005). For the 128-item pilot 93.6% are different contracts, which supports keeping them. This is larger than the 16 sets the recorded decision covered, and it needs the database for the other divisions.

**Monthly series (Teams 1 and 2).** Both rebuilt the `forecast_date` series from the raw pull. Quantity: 10,385 cells, maximum difference 0.0, total 3,340,200 units. Sale: maximum difference 5.8e-11, total THB 1,878,390,980.57. The leakage guard passes on vintage 1 (38 days) and vintage 2 (32 days); the margin is 30 days. The saved "vintage 2" fit series is the 2026-10-05 pull, not the data vintage 2 was fitted on (T1-004).

**Forecast (Team 2).** All 390 series × 6 horizons of vintage 2 recomputed to within 5e-5, which is the log's 4-decimal rounding. This covered the Fuse Cutout Type (4769.4414), the Surge Arrester Type (4751.5231), a PEM107 Type (87.7841) and the three focus items. The MA comparator windows match. The 82 placeholder values in config are correct (rules A/B/C, 82 of 82), but STATUS's 2026-09-04 statement that placeholders get a forecast is not what the code does (T2-005, docs). `models.py` silently drops a model that fails (T2-004); this did not happen.

**Accuracy (Team 2).** MAE, RMSE and Bias per division match the files and `sales_report.html` to under 1e-9. Relative MAE including Horizon 3 and the Tracking Signal points match the page and the executive tab (see worked examples 5 and 6). The backtest has no leakage (7 of 7 origins, tested by perturbing data at or after each origin). Forward-test log hashes recompute under the documented schemes and the scoring of eligible months is correct.

**Min-Max (Team 3, with the user's three corrections applied).**
- PEM101's 92 items use the lead-time-free calibration (D2/D3). Item lead time v1 is only displayed, and it feeds the material plan. The full grid (7,360 numbers) matches the record with a maximum difference of 0.00; the three focus items match the page within 0.04 unit.
- PEM107's 4 items use the standard formula (60 + 3 + 30 days, 95%). A port of it equals the page to full precision.
- PEM103 has no stock items, and CI101, PEM102 and PEM104 are disabled. All four states are consistent with Sec.23.
- Unclear: the page opens PEM101 with the uncalibrated table (7.4× higher Min for one item; T3-001), and Sec.22's robust class is empty because every item's range ratio is 8.0 (T3-002), so a robust example could not be recomputed.

**Operation plan (Team 3).** Seven stock items over 5 months and the division totals for PEM101, PEM103 and PEM107 match; the PEM101 difference is at most 2.1 on 109,000-184,000. The capacity references (249,080 / 405 / 6,221) match.

**Material plan and lead time (Team 3).** All 2,246 materials match on gross need, net need, order date, lead time and lead-time source. Item lead time v1 matches on all 92 items for bottleneck days and on 91 for production days (the one difference is a documented rule). The meta text "sub-assembly stock is not netted" is wrong; netting is applied (T3-004).

**Pages (Teams 4, 4b).** Traced and matched: the executive tab, the Trend tab (445 items, qty 3,707,367.0, THB 2,227,220,843.55), header dates, baht per item (334 of 334), division and total baht, the forecast-versus-actual table, stock and backlog (890 values), operation plan (439 item rows, 30 division-months) and material plan (2,181 material rows). Mismatched figures: 0, apart from display rounding of 1 or 0.1. Untraceable by design: the S&OP tab (no source date, T4b-002).

**Automation (Teams 4, 4b and the re-check).** Monthly steps, exit codes, the source guard's bands, the launcher's exit codes and lock, and the 2026-10-29 revert state all match STATUS and METRICS. The 11-05 risks are in section 1.

**Tests (Team 4).** About 31 tests across 6 files were read. The tests in `test_check_new_vintage.py` and `test_task_launcher.py` check real behaviour with independent expected values. Weak: four tests in `test_page_timestamps.py` check strings or use the same config as the code. 20 tests fail without the author's database environment (T4-006). The full suite was not sampled beyond this, so "at least 20 tests" is met but broad coverage is not claimed. No mutation checks were run.

**Docs vs code vs config.** 8 mismatches are listed in the CSV (for example: Sec.42/43 on who rebuilds the plans, 36 vs 37 ensemble members, the Sec.28 step list, the VAT wording, the stale code comment on Backlog `ActualQty`). Config values for the monthly gates (25/20/30), the daily gates and the source guard bands equal METRICS Sec.28.

---

## 4. Findings table

All 78 rows, with evidence and recommendations, are in `verify_full_2026-10-30_findings.csv`. The rows to read first:

| id | severity | verdict | one line |
|---|---|---|---|
| RC-002 | High | UNCLEAR | Step 10 six-month gate vs vintage 1, 25%; CI101 already +20.2% |
| RC-003 | High | WRONG | Hold or failure leaves the clone dirty; launcher exits 95; daily publishing stops |
| RC-004 | High | WRONG | Re-run after a hold skips step 5; the six-month gate becomes not tested |
| RC-001 | High | UNCLEAR | Step 8 timeout 1800 s on origin; the 3600 s fix is unpushed |
| T1-001 | High | UNCLEAR | Reserved dedup removes 8.3% of Reserved; needs PlanID from the database |
| T1-002 | Medium | WRONG | `order_leadtime.py` filters on the DB division column |
| T1-003 | Medium | UNCLEAR | `delivery_performance.py` filters on ManuDivision with a 2023 floor |
| T1-004 | Medium | WRONG | Saved vintage-2 fit series is the 10-05 pull |
| T1-005 | Medium | UNCLEAR | 1,334 duplicate copies (1.0% of quantity) all kept |
| T1-006 | Medium | WRONG | Guard's first live run is 11-02, not 10-30 12:00 |
| T2-004 | Medium | UNCLEAR | Combination silently drops a failed model |
| T2-005 | Medium | WRONG | Placeholder forecast in the STATUS decision is not in code |
| T3-001 | Medium | UNCLEAR | PEM101 inventory page opens with the uncalibrated table |
| T3-002 | Medium | UNCLEAR | Sec.22 robust class is empty; page follows the target-chosen reorder level |
| T3-003 | Medium | WRONG | Sec.42/43 say only the monthly run rebuilds plans |
| T4-004 | Medium | WRONG | STATUS on the 11-05 08:00 launcher is wrong |
| T4-005 | Medium | WRONG | `check_new_vintage.py` does not replace step 10 |
| T4-006 | Medium | WRONG | 20 tests depend on the author's database environment |
| T4b-002 | Medium | WRONG | S&OP tab has no source date (Sec.26) |
| T4b-003 | Medium | WRONG | Material count band gate passes silently with no earlier count |

---

## 5. Goal fit, against "The brief" in STATUS.md

**What serves the goal (done and verified).**
- Item 1 (3-year trend of Price List items from `cube_Sale_APD`, Omni): the Trend tab and the monthly series are correct and traceable.
- Items 2 and 3.1 (Drop-out Fuse Cutout and Surge Arrester, then all Price List codes; moving-average comparator with a per-division window): verified, including the three named items.
- Item 4, Max-Min for finished goods and MRP: PEM101 (92 items) and PEM107 (4 items) have Min/Max. The operation plan covers the divisions, and the material plan explodes the BOM with lead times and order dates, all recomputed.
- The user's three scope corrections hold in code: PEM101 Min/Max is lead-time-free, and item lead time v1 only feeds the material plan.

**What goes beyond the brief.**
- The executive tab, the shadow forecasts, the forward-test log with hashes and the Tracking Signal.
- The source guard, the task launcher and the daily rebuild.
- The PEM107 delivery alert.
- These serve reliability and checking. Their cost is complexity: the 2026-11-05 risks in section 1 come from this machinery, not from the forecast.

**What is missing.**
- Brief item 3.2 (utility budgets, sales insight, EGP bids) and the storms in item 4. STATUS records that no such data is in the database. They remain not done.
- Brief item 4 wanted Max-Min with vendor lead time. The project chose a lead-time-free calibration because the material lead time did not reproduce observed service. That is documented in STATUS and applied consistently. It is a deliberate departure from the brief's wording, so the user should be aware of it.
- Min-Max exists only for PEM101 (92 items) and PEM107 (4). Other divisions are disabled or have no stock items.

**Things worth knowing that nobody asked about.**
- **The forecast barely beats the simple baseline.** Relative MAE against Naive is 0.80-0.93 for four divisions but 1.04 for PEM103 and 1.07 for Surge Arrester (above 1 means worse than Naive). The Fuse Cutout Tracking Signal (−4.70) comes from one month, August 2026 (forecast 3,215 against actual 8,670). Every forecast is flat across the six months (no seasonality), and the page says seasonal-naive did not do better.
- **Reserved and duplicate handling affect decision inputs.** Reserved de-dup (T1-001) and the 1% duplicate copies (T1-005) are unresolved, and the data cannot settle them offline.
- **One machine, one user session.** Both tasks run as the interactive user with Wake off. If the machine is asleep or logged off at 07:00 on 11-05, the run starts late and the 08:00 daily collides with the monthly lock (T4-010).
- **The 11-04 checklist covers a clean clone, not the working copy being ahead of origin.** `D:\sale_forecast` is 5 commits ahead, including the timeout fix. A check on "ahead/behind" of the working copy would have caught it.
- **Sec.22's robust/sensitive split no longer does anything** (every item is sensitive), yet STATUS and METRICS still describe it.

---

## 6. Limits of this verification

- **No database access.** Another session was using the database (a Python process started 11:36 was running; the monthly run logs of the day were being written), and the user did not confirm it had finished. I made zero database logins and zero queries. Everything compared with "the source" was compared with saved pulls. The seven read-only statements that Team 1 prepared (D1-D7: Reserved by PlanID and total, `ManuDivision` share, duplicate groups with contract, cost per unit, source COUNT/SUM, Cube_CES status counts) are **not run**. They are in the Team 1 report and need the user's go-ahead. Until they run, T1-001, T1-003, T1-005 and "saved pulls equal the source" stay UNCLEAR.
- **The snapshot is origin/main, not the working copy.** `D:\sale_forecast` has 5 further local commits (Prompt 64, including the 3600 s timeout fix) that were not verified. Where a Validator looked at them it is stated in the finding.
- **Team 4 did not read all four large documents in full** (STATUS 936 KB, DATA_MAP 244 KB, METRICS 157 KB, PROJECT_GRAPH). Team 4b and the other teams read their own sections. Findings in sections nobody read are possible.
- **Not recomputed:** unit costs and THB stock values; the calibration simulation itself (only Min/Max from the recorded members); the Holt shadow forecasts and Sec.41 significance; the full material first and second lists; the browser behaviour of JavaScript-filled tables (the embedded JSON was traced instead).
- **Not run:** the monthly job, the pipeline, or the full test suite (Team 4 ran it only in a throwaway copy, with no database environment). No mutation checks.
- **Not inspected:** Task Scheduler beyond read-only definitions; origin's push state from the clone.
- **Not independent of the same upstream:** CONVENTIONS' rule applies. Agreement between a Validator and the saved pulls shows the recorded outputs are consistent with those pulls, not that the pulls equal the source system.
- **Estimates:** the 40-55% breach chance for step 10 (RC-002) is a crude model replica plus resampling; it should be read as "a real chance", not a prediction.
- **Subagent report files could not be saved** by the Validators (their Write tool refused). Their reports were returned as text, and this report and the CSV were written from them by the Orchestrator.

---

## 7. Final report items

1. **Summary.** No wrong published figure; every recomputed figure matches. Five High items, all about the 2026-11-05 run holding or failing, or one unresolved decision input. Seven database statements wait for the user's go-ahead.
2. **Critical/High findings.** RC-001 to RC-004 and T1-001 (section 1 and the CSV).
3. **Counts per area.** Table in section 3.
4. **Database logins used.** None (zero logins, zero queries).
5. **Clone hash verified.** `869caeceddfb83d5c576be2c9febc54393707389` (equal to origin/main at the time of cloning).
6. **Could not be verified.** Section 6.
