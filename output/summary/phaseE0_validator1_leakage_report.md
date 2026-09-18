# Phase E0.1 — Validator 1: Point-in-Time Leakage in Rolling-Origin Backtests

**Role**: Validator (per `AGENTS.md`) — checks data quality and verifies figures against direct
recomputation; does not modify data, config, or pipeline scripts. No file outside
`output/summary/` was changed by this task. No re-run of the production backtest was performed,
because no genuine point-in-time leakage was found in shares (Q1) or model settings (Q4) — the
re-run permission in this task's brief is therefore not triggered.

**Scope**: this is the pre-check gate for Phase E (Max-Min calculation), not Phase E itself. It
answers whether the rolling-origin backtest behind the locked `forecast_method_final:
"topdown_combination"` (`config/config.yaml:223`) is contaminated by information from after each
historical origin.

**New files produced by this task** (read-only investigation, nothing else changed):
- `output/summary/phaseE0_q2_revision_risk_per_origin.csv`
- `output/summary/phaseE0_q2_revision_risk_focus_items.csv`
- `output/summary/phaseE0_q2_test_window_knowability.csv`
- `output/summary/phaseE0_q1_share_comparison.csv`
- (scratch scripts used to produce these lived in this session's scratchpad directory, not
  committed to `src/` — they only read existing CSVs and existing, unmodified project functions
  imported from `src/backtest_rekeyed.py`; nothing in `src/` was edited)

---

## Sub-question 1: Historical allocation shares

**Verdict: LEAKAGE ABSENT in every share-computation code path that feeds a number currently
relied on in STATUS.md's Locked Decisions. Confidence: high (direct code read of every script
that computes a Top-down item/Type share, cross-checked against STATUS.md's own citations of
which script produced which number).**

Three scripts compute a Top-down item share; a fourth family (forward-test builders) uses the
same function for a different purpose. All were read end to end:

1. **`src/item_level_reconciliation.py`** (Phase B3), `forecast_all_approaches()` lines 73-111.
   Computes `share = totals[item] / grand_total` where `totals[item] = item_series[item][0][:fit_end].sum()`
   (line 95-98) — a **single split**: `fit_end = TRAIN_MONTHS + VAL_MONTHS` (25 of 31 months) for
   the test-stage score, `fit_end = TRAIN_MONTHS` (19 months) for the validation-stage score
   (call sites at lines 137 and 144). **This is not leakage relative to what it forecasts**: the
   share and the Type-level combination forecast it multiplies are both fit on `qty[:fit_end]`
   only, and the resulting Top-down forecast is scored only against `qty[fit_end:fit_end+horizon]`
   — strictly after the fitting window in every case. The real limitation of B3's number is a
   **generalizability** one, not a leakage one: it is evaluated on a single origin (the same
   origin later shown, in the Modeler-tasks-1-3 log entry, STATUS.md lines 2293-2308, to be
   anomalous — the only one of 7 rolling origins where `forecast_date` beats `createDate`). This
   generalizability caveat was already recorded in STATUS.md and is not a new finding here; it is
   restated only to be precise about what B3's share methodology does and does not risk.

2. **`src/transferability_all_divisions.py`**, `run_transferability_rolling_origin()` lines
   55-89 — the function named in this task's brief. Confirmed directly: `train = qty[:train_size]`
   (line 66), `type_train = type_qty[:train_size]` (line 76), `item_total = train.sum()` (line 79),
   `type_total = type_train.sum()` (line 78), `share = item_total / type_total` (line 80) — **all
   computed fresh inside the `for origin_idx, train_size in enumerate(origins, ...)` loop**, using
   only data through that origin's own `train_size`. `origins` comes from
   `src/backtest_rekeyed.get_origins()` (imported unmodified, line 22), and the leakage guard
   (`check_window_closed`, line 71) is applied before any score is recorded. This is the script
   whose output (`output/summary/phaseC_step2_transferability_item_rolling_origin.csv`,
   `..._per_division.csv`) backs STATUS.md's Phase C step 2 Part 3 per-division transferability
   table (STATUS.md lines 3116-3160) and is the **PRIMARY** evaluation under
   `config/config.yaml`'s `evaluation_policy` (lines 233-236, `primary: "rolling_origin"`).
   **Origin-consistent, confirmed by direct code read — leakage absent.**

3. **`src/focus_item_model_selection.py`**, `score_all_candidates_at_origin()` lines 94-122 and
   `run_rolling_origin_all_candidates()` lines 127-145: `item_total, type_total = train.sum(),
   type_train.sum()` (line 114), `share = item_total / type_total` (line 115) — same pattern,
   computed inside the per-origin loop from `train`/`type_train` slices that are themselves
   `qty[:train_size]`-style slices from the calling loop. This backs STATUS.md's focus-item
   11-candidate comparison (lines 3208-3260, `focus_items_rolling_origin_all.csv`).
   **Origin-consistent, leakage absent.**

4. **`src/forward_test_v2.py`** and **`src/forward_test_all_divisions.py`** call
   `item_level_reconciliation.forecast_all_approaches()`'s Top-down branch with `fit_end =
   TOTAL_MONTHS` (the full 31-month history) — confirmed by the `TOTAL_MONTHS` import and the
   `n_fit_months != TOTAL_MONTHS` guard in both files. **This is a different kind of evaluation,
   not a backtest**: these are genuine forward-looking forecasts for periods beyond all available
   history, later scored by `src/score_forward_test_v2.py` against real future demand once it
   arrives. Using "all data up to today" is exactly correct here — there is no future period
   being peeked into, because "today" (the pull date) *is* the origin. This path does **not**
   feed any of the rolling-origin/train-val-test MAE/RMSE/Bias numbers STATUS.md cites for the
   method-selection decision, so it is out of scope for "point-in-time leakage in rolling-origin
   backtests," but is reported here for completeness since it is the fourth script identified by
   the brief's grep instruction (`src/backtest_all_divisions.py` was also checked — it does not
   compute any item-level share at all, Category/Type level only, confirmed by a content grep
   returning zero matches for "share"/"topdown").

**Magnitude, if full-history share had been used instead of per-origin share (a hypothetical,
since no code path that feeds a locked figure actually does this)**: computed directly
(`output/summary/phaseE0_q1_share_comparison.csv`), comparing each item's share at each of the 7
real origins against its share if computed on the full 31-month series:

| Item | Type | Full-history share | Share range across the 7 real origins | Max \|relative diff\| vs. full-history |
|---|---|---|---|---|
| `EEE-F-FC-1040010002` (dominant, focus) | High Voltage Distribution Fuse Cutout | 0.5022 | 0.4773 – 0.5777 | 15.0% |
| `HS-F-99-0213` (mid-rank, focus) | Medium Voltage Surge Arrester | 0.0422 | 0.0244 – 0.0350 | 42.1% |
| `HS-F-99-02110` (minor, focus) | Medium Voltage Surge Arrester | 0.0469 | 0.0094 – 0.0149 | 80.0% |
| `FC-A-27-00202` (near-saturated) | Fuse Holder | 0.9498 | 0.9079 – 0.9509 | 4.4% |
| `FS-F-99-0003` (near-saturated) | Low Voltage Fuse Switch Disconectors | 0.9931 | 0.9989 – 1.0000 | 0.7% |

**Reading this table**: the two adopted, cited scripts never take this shortcut, so this is not a
measured leakage effect — it is a sensitivity check showing *how much it would have mattered had
the shortcut been taken*. It would matter most for minor-share, still-recovering focus items
(`HS-F-99-02110`, `HS-F-99-0213`, 42-80% relative share swing) and least for near-saturated or
already-dominant items (<15%). This is directionally consistent with STATUS.md's own B3 finding
that Top-down's benefit is share-dependent (lines 2248-2256).

---

## Sub-question 2: `forecast_date` revision risk

**Verdict on revision timing itself: CANNOT BE DETERMINED FROM THIS DATA, high confidence in that
negative finding — this is a re-confirmation of Phase A's existing conclusion, not a new result.**
STATUS.md (lines 2076-2078, restated at lines 2338-2341) already establishes, from a table/column
search extended to `INFORMATION_SCHEMA.COLUMNS`, that no audit/history table or per-row
modification-timestamp column exists anywhere in this schema for `cube_Sale_APD` or `Cube_CES`.
**I attempted to re-verify this independently** with a fresh `INFORMATION_SCHEMA.COLUMNS` search
(`LIKE '%modif%'/'%audit%'/'%revis%'/'%version%'/...`) via `src/db.py`'s `run_query()`, but the
database connection in this session failed (`pyodbc.InterfaceError: Login failed for user
'jetniphat.boo'` — a credentials/environment issue in this session, not a finding about the
schema). I am not able to independently confirm this negative finding today; I am relying on the
prior Validator's high-confidence result, carried forward explicitly labelled as such (per
`AGENTS.md` rule 7), not re-stated as newly verified.

**Best-available lower-bound proxy, computed as instructed (createDate vs. forecast_date), using
the actual production rolling-origin windows.** Used `src/backtest_rekeyed.get_origins(31, 6)` —
the exact, unmodified function — giving the 7 real origins (`train_size` = 13, 15, 17, 19, 21, 23,
25), against `output/data/raw_full_category_sales.csv` (the same frozen row-level pull, snapshot
`2026-09-04 16:44:45`, that backs `processed_full_category_sales_monthly_forecastDate.csv`).

- **Training-window check** (of the demand a model at origin *t* actually fits on, what share was
  `createDate`'d *after* that origin's own training cutoff month?): **0.0000% at every one of the
  7 origins, pooled across all 128 items and individually for all 3 focus items**
  (`output/summary/phaseE0_q2_revision_risk_per_origin.csv`,
  `..._focus_items.csv`). **This is not an accident of the data — it is a structural guarantee**:
  `src/load_data_full.py`'s `aggregate_monthly()` (line 230) already drops every row where
  `forecast_date < createDate` before building the forecast_date-keyed series, so `createDate ≤
  forecast_date` holds for every remaining row by construction. Since a row's month bucket is its
  `forecast_date`'s month, and `createDate ≤ forecast_date` implies `createDate`'s month ≤
  `forecast_date`'s month, **no row placed in a training window by this pipeline can have been
  created after that window closes — this specific mechanism cannot produce point-in-time leakage
  into the training data, by the same validation rule that already exists for a different reason
  (Phase A/B1's negative-interval exclusion).** This is a genuine, positive finding, not a null
  result: the proxy returns zero because the invariant makes the leak structurally impossible for
  this specific channel, not because no risk exists at all (the deeper "was forecast_date's VALUE
  ever silently revised after being set" question remains the separate, undetectable one above).
- **Test-window check** (of the demand scored as "actual" in a given test window, what share was
  `createDate`'d *after* the test window's own last month — i.e., entered only once the whole
  period had already elapsed?): also **0.0000% at every origin**, for the same structural reason
  (`createDate ≤ forecast_date` ⟹ a row inside the test window's `forecast_date` months cannot
  have a `createDate` later than the test window's own end either, since the test window's last
  month is itself later than or equal to every row's `forecast_date` month inside it... more
  precisely: rows with forecast_date inside the test window necessarily have createDate on or
  before their own forecast_date, which is on or before the test window's end). **This proxy, as
  literally specified in the brief, is mathematically guaranteed to read zero given this
  pipeline's own existing data-cleaning invariant — it provides no additional discriminating
  signal beyond confirming that invariant holds** (spot-checked: it does — 27,730 of 27,746 raw
  rows pass the forecast_date-keyed filters, matching `load_data_full.py`'s own logged rates).
- **A more informative supplementary metric** (not explicitly requested but computed because the
  two requested proxies are tautological, as shown above): of each origin's TEST-window demand,
  what share was already **on the order book** (createDate on or before the origin's training
  cutoff, i.e., a real "known future order" the model could in principle have seen coming) versus
  **genuinely new** (createDate falls within the test window itself, i.e., an order that did not
  exist yet at the origin)? Result
  (`output/summary/phaseE0_q2_test_window_knowability.csv`): **mean 5.2% already on the books at
  the origin, 94.8% genuinely new during the test window**, consistent across all 7 origins
  (range 2.6%–7.5% "already known"). This is consistent with, not a contradiction of, this
  project's own already-recorded 6-day median order-notice finding (STATUS.md, Business
  Findings) — it independently confirms that this demand series is overwhelmingly short-notice,
  and that the ~2.5%-of-rows revision bound Phase A found is small relative to the ~95% of
  test-window demand that is inherently unknowable in advance regardless of any revision question.

**Overall Q2 verdict**: revision-in-place timing remains **cannot be determined** (re-affirmed,
not re-verified today due to a DB connectivity failure in this session — flagged as a limitation,
not papered over). The specific point-in-time-leakage channel the brief asked to probe (training
or test window demand secretly created after its own window) is **structurally absent**, confirmed
by direct computation and explained by an existing, unrelated data-cleaning rule
(`forecast_date >= createDate`) that happens to also rule this out. This does **not** resolve
whether an individual row's `forecast_date` value could have been silently changed in place after
being set — that remains bounded at <2.5% of rows with no consistent direction (Phase A, high
confidence, unchanged by this task).

---

## Sub-question 3: Product mappings and eligibility (pricelist version)

**Verdict: CANNOT BE DETERMINED FROM THIS DATA — no dated historical pricelist snapshots exist,
confirmed directly. Confidence: high.**

- `reference/` is listed in `.gitignore` (`.gitignore:3`, confirmed by `git check-ignore -v
  reference/pricelist.xlsx` → matched), so `reference/pricelist.xlsx` **has never been tracked in
  git** — `git log --all -- reference/pricelist.xlsx` returns zero commits. No prior version of
  the file is recoverable from this repository's history.
- On disk, exactly **one copy** of the file exists, with a single filesystem modification
  timestamp (2026-08-21 09:26:32) — no dated backups, no `pricelist_vN.xlsx`-style archive found
  anywhere under the project directory (`find . -iname "*pricelist*"` was run and returned only
  this one workbook plus derived CSVs/scripts, none of which are independent historical
  snapshots).
- **One partial mitigation already exploited by a prior task, re-confirmed here**: the workbook
  itself contains, per division, both a **hidden** "Version1" sheet and a **visible** "Version 2"
  (current) sheet (confirmed directly via `openpyxl`, e.g.
  `PEM101-Version1 Stock...เดือน 6` (hidden) vs. `PEM101-Version 2` (visible) —
  `src/investigations/task2_pricelist_version_check.py`,
  `output/summary/task2_pricelist_version_evidence_16items.csv`). This lets you tell whether an
  item **existed** in an older internal snapshot vs. the current one (already used for
  Phase C's 16 no-history items). **It does not carry a date, and it does not tell you what an
  item's division/Type/status attribute VALUE was in that older snapshot** — only presence/absence
  of the row, per the script's own docstring (line 1-5: "this can only show 'already existed in a
  prior version' vs 'new to the current version', never a calendar date, since the workbook
  carries no date field for when a row was added"). This was already noted as a limitation in
  STATUS.md (line 3020: "PEM104's 7 no-history codes cannot be checked against a hidden pricelist
  version (no hidden PEM104 sheet exists)"), consistent with, not contradicting, this finding.

**Practical consequence for Phase E0.1**: if an item's division/Type/status changed between an
earlier historical origin and today, the pricelist as currently read by
`src/pricelist_reader.py` would silently apply **today's** classification retroactively to every
past origin in a rolling-origin backtest — this is a genuine, plausible leakage channel in
principle, but **it cannot be measured, bounded, or even detected as present/absent with what
exists today**, because no historical attribute values survive anywhere (git, filesystem, or
database — `CONVENTIONS.md` already establishes DB division/category/type columns are
reference-only, not authoritative, so they cannot substitute either).

**What a prospective snapshot-collection process should capture from now on** (cannot close this
gap retroactively, but can close it for future origins):
1. On every pricelist update, archive a **dated, immutable copy** of `reference/pricelist.xlsx`
   (e.g. `reference/archive/pricelist_YYYY-MM-DD.xlsx`), outside `.gitignore`'s current blanket
   `reference/` exclusion or via a separate small binary-artifact store — CONVENTIONS.md's "never
   commit data files" rule can be satisfied by storing archives outside git (e.g. a dedicated
   `output/`-style location already excluded from the "never commit generated output" rule since
   archives are not regenerable) while still keeping them off git if that is the project's
   preference; the key requirement is a **timestamped, append-only copy per update**, not git
   tracking specifically.
2. Alternatively/additionally, maintain a small structured table (`item_code, division, type,
   status, effective_date`) appended to (never overwritten) every time the pricelist changes —
   this is cheaper to diff and query than re-parsing whole workbook archives, and would let a
   future rolling-origin backtest look up "what was this item's division/Type/status as of
   month t" exactly, closing this leakage channel for every future origin going forward.

---

## Sub-question 4: Model settings tuned on future data

**Verdict: LEAKAGE ABSENT for all six adopted models. Confidence: high — direct read of
`src/models.py` in full, cross-checked against the installed `statsforecast` library's own
source code (not assumed from memory or docs alone), and against `config/config.yaml` and
STATUS.md's Phase 3.1 log for when the MA windows were first used.**

| Model | Parameter | Fixed once on full data (leakage) or refit fresh per `train` call (safe)? | Evidence |
|---|---|---|---|
| Naive | none | N/A — repeats `train[-1]` | `src/models.py:12-14` |
| MA3/MA6/MA12 | window length (3, 6, 12) | **Fixed, untuned constant** — `config/config.yaml:112-115` `moving_average_windows: [3, 6, 12]`, passed into every call of `combination_forecast`/`get_models` (`src/backtest_rekeyed.py:52`, `:145,182`; `src/item_level_reconciliation.py:32,81,87`; `src/transferability_all_divisions.py:22,73,77`). The window itself never changes across origins; only the `train` slice it averages over does — `moving_average_forecast(train, horizon, window)` (`src/models.py:17-20`) always computes `train[-window:].mean()` on whatever `train` it is given, so it is origin-consistent by construction. **Not tuned via any fitting process at all** — a chosen constant, per `CONVENTIONS.md`'s "no magic numbers... all tunable values belong in config.yaml." **Not leakage, but flagged as a configurable assumption**: STATUS.md's Phase 3.1 log (line 724-725, the project's *first* backtest) already tested exactly these three windows (3/6/12) alongside Naive/Croston/SBA — i.e., these specific values were in use **before** any backtest result existed to have "looked at which performed best," so there is no evidence in STATUS.md that they were chosen by observing full-dataset performance. No entry in STATUS.md documents a selection process for 3/6/12 beyond "standard quarterly/half-year/annual moving-average conventions" (config.yaml's own comment, line 111). Absence of a documented selection rationale is itself notable — per `CONVENTIONS.md`'s rule that an unsourced figure must be treated as unverified — so this is recorded as a **configurable assumption**, not a verified-safe choice, even though no leakage mechanism was found. |
| Croston | smoothing parameter | **Fixed at 0.1, hardcoded inside the `statsforecast` library itself**, confirmed by reading the installed library's source directly (`CrostonClassic.__init__` docstring: "The smoothing parameter of both components is set equal to 0.1"). `src/models.py:23-26` calls `CrostonClassic().forecast(y=train...)` fresh every time with whatever `train` is passed — the constant itself is never tuned by this project's data at all, at any origin. |
| SBA | smoothing parameter + 0.95 debias factor | Same as Croston — both constants (0.1 smoothing, 0.95 debias) are hardcoded in `statsforecast.models.CrostonSBA`, confirmed from source. `src/models.py:29-32`. |
| SES (extended-candidate comparison only, **not** in the adopted 6-model combination — `config/config.yaml:144-150`'s `combination_models` list has no SES) | smoothing alpha | `SimpleExponentialSmoothingOptimized` — statsforecast optimizes alpha internally, refit fresh on whatever `train` is passed each call (confirmed: its `__init__` takes no alpha argument at all, meaning it must estimate it at `.forecast()`/`.fit()` time from the data given). `src/models.py:35-39`. Used only in `get_extended_models()` (`:116-123`), called by `src/focus_item_model_selection.py`'s per-origin loop — origin-consistent. |
| Holt (extended-candidate comparison only, same non-adoption note as SES) | alpha, beta (trend) | Statsforecast's `Holt` class optimizes its own state-space parameters via MLE per fit call (confirmed from source: `__init__` only stores `season_length`/`error_type`, no smoothing parameters — they are estimated at fit time). `src/models.py:42-47`. Same per-origin call pattern as SES. |
| TSB (extended-candidate comparison only; **not** in the adopted combination) | `alpha_d`, `alpha_p` | **Grid search over `_TSB_ALPHA_GRID = [0.05, 0.1, 0.2, 0.3, 0.4]`** (`src/models.py:50`), but the grid search itself runs **inside `tsb_forecast(train, horizon)`** (`:60-82`), scoring each `(alpha_d, alpha_p)` pair by **in-sample fitted error on `train` only** (`:73-74`, `fitted = TSB(...).fit(y=train)`; `in_sample = fitted.predict_in_sample()["fitted"]`) — never touching `test`. Since `tsb_forecast` is called fresh at every origin with that origin's own `train` slice (confirmed at its only call sites, `src/focus_item_model_selection.py`), **the grid search itself is re-run per origin, using only pre-origin data** — origin-consistent. The 5×5 grid range is a stated, literature-derived choice (Teunter, Syntetos & Babai 2011), not derived from this project's own backtest results, per the code comment at `src/models.py:56-57`. |
| Combination (the adopted method) | equal weights (arithmetic mean) | Not a fitted/tuned weight at all — `combination_forecast` (`src/models.py:85-100`) is an unweighted `np.mean` of the six base models' outputs, each computed fresh from that call's own `train`/`horizon`. No weight-fitting step exists anywhere to leak into. |

**Summary for Q4**: no model parameter in the adopted six-model combination (Naive, MA3, MA6,
MA12, Croston, SBA) was ever fit once on the full 31-month series and reused unchanged — MA
windows are fixed, untuned config constants (not verified against a "what performed best"
selection process, hence a configurable assumption, but structurally incapable of leaking future
information since the *window length* doesn't change, only the *data it's applied to*, which is
always the caller's origin-appropriate `train` slice); Croston/SBA's internal constants are
hardcoded in the third-party library, never touched by this project's data. TSB, SES and Holt (not
part of the adopted combination, only used in the 11-candidate focus-item comparison) all refit or
re-grid-search fresh per origin, using only that origin's own `train` slice.

---

## Summary table

| # | Input | Verdict | Confidence | Key evidence |
|---|---|---|---|---|
| 1 | Historical Top-down allocation shares | **Leakage absent** in every script whose output feeds a cited backtest number (`item_level_reconciliation.py`, `transferability_all_divisions.py`, `focus_item_model_selection.py`) — all confirmed by direct code read to use only pre-test-window data at the origin they score against. Full-history share (never actually used for a cited number) would have swung 15–284% relative for minor/mid-rank items had it been used. | High | `src/transferability_all_divisions.py:55-89`, `src/item_level_reconciliation.py:73-111`, `src/focus_item_model_selection.py:94-145`, `output/summary/phaseE0_q1_share_comparison.csv` |
| 2 | `forecast_date` revision risk | Revision-in-place timing: **cannot be determined** (re-affirms Phase A; could not independently re-verify today, DB login failed in this session). The specific training/test-window-created-after-the-fact leakage channel: **structurally absent**, confirmed by direct computation (0.0000% at all 7 origins), explained by the pipeline's own pre-existing `forecast_date >= createDate` cleaning rule. Supplementary finding: 94.8% of test-window demand is genuinely new (not yet on the books) at the origin, consistent with the 6-day median order-notice finding. | High (structural-absence check); unchanged from Phase A (revision-timing question) | `src/load_data_full.py:230`, `output/summary/phaseE0_q2_revision_risk_per_origin.csv`, `phaseE0_q2_test_window_knowability.csv`, STATUS.md lines 2076-2078 |
| 3 | Product mappings / pricelist versioning | **Cannot be determined from this data** — no dated historical pricelist snapshots exist anywhere (not in git, `reference/` is `.gitignore`d; not on the filesystem, single copy/mtime). Partial mitigation: workbook's own hidden Version1 vs. visible Version2 sheets show item *existence* across two internal snapshots, but no date and no attribute-value history. | High | `.gitignore:3`, `git log --all -- reference/pricelist.xlsx` (0 commits), `src/investigations/task2_pricelist_version_check.py`, `output/summary/task2_pricelist_version_evidence_16items.csv` |
| 4 | Model settings tuned on future data | **Leakage absent** for all six adopted models. MA windows are fixed, untuned config constants (flagged as a configurable assumption, not a verified-safe choice, since no documented "which window worked best" selection process was found — but structurally incapable of leaking since only the window *length* is fixed, not the data). Croston/SBA constants are hardcoded in the third-party library. TSB/SES/Holt (comparison-only, not adopted) all refit per origin from `train` only. | High | `src/models.py` (full file read), installed `statsforecast` source (`CrostonClassic`, `CrostonSBA`, `Holt`, `SimpleExponentialSmoothingOptimized`), `config/config.yaml:111-150` |

**Overall gate recommendation for the Orchestrator**: nothing found here blocks Phase E on
point-in-time-leakage grounds for the two mechanisms that are actually checkable (shares, model
settings) — both come back clean. Two items remain genuinely open, in the same category as
several already-recorded Phase A open items: (a) `forecast_date` revision-in-place timing is
undetectable from this data model (unchanged conclusion, re-affirmed not re-verified this
session due to a DB connectivity failure — a follow-up re-check with working DB credentials would
be low-cost and is recommended before treating this as permanently closed); (b) no historical
pricelist snapshot exists, so a real division/Type/status drift between an old rolling-origin and
today could not be ruled out even in principle — recorded as a known, currently-unbounded gap for
Phase E's Max-Min inputs that draw on item classification, with a concrete forward-looking fix
proposed above.
