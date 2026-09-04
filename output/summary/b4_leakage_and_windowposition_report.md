# Phase B follow-up — Was the re-keying improvement leakage? Why did the two evaluation methods disagree?

Single Validator task (per `AGENTS.md`: re-examines one series, results must be interpreted
together — not split). Script: `src/leakage_check_forecastdate.py`. Investigation only; no model
choice written to `config.yaml`; no existing file modified (one new file written:
`processed_full_category_sales_monthly_forecastDateNoLeak.csv`).

## Part 1 — Quantify future-dated rows

Pull date (frozen snapshot, cited from `processed_full_category_sales_monthly_forecastDate.csv`'s
`snapshot_pull_date` column): **2026-09-02 15:52:39**.

**472 of 27,584 raw rows (1.71%) have `forecast_date` after the pull date** — qty 77,966, sale
value ฿26,295,546.40, across 66 distinct items. These distribute across `2026-09` (440 rows,
69,706 qty — the overwhelming majority), `2026-10`, `2026-11`, `2026-12`, `2027-01`, and `2027-05`
(full detail: `b4_future_dated_rows_by_month.csv`, `_by_item.csv`, `_by_level.csv`).

**Decisive check, HIGH confidence (direct query, cited: `raw_full_category_sales.csv` joined
against the fixed 31-month window from `src/load_data_full.py`)**: **zero of these 472 rows fall
within the 31-month window (2024-01 to 2026-07) used for every backtest in this project, and
therefore zero fall within the final 6-month test window (2026-02 to 2026-07) or any
rolling-origin test window (all of which are subsets of these 31 months).** This is because the
window was fixed to end at 2026-07 (Phase B1), and the pull happened over a month after that
window's last month had already fully elapsed — every future-dated row is dated **after** the
window ends, not inside it.

## Part 2 — Re-run without the leaked rows

Built a third series, `forecastDateNoLeak`, from the raw pull with `forecast_date > pull_date`
rows additionally excluded (472 rows removed, on top of B1's existing null/negative-interval
exclusions), then re-ran the identical train/val/test and rolling-origin backtest on it.

**Result: the `forecastDateNoLeak` series is numerically IDENTICAL to the existing
`forecastDate` series at every level and every model, confirmed two independent ways**:
1. A row-level merge-based diff between the two monthly grids (`itemcode`+`year_month` join,
   not a naive `.equals()` which gave a misleading "different" result due to a row-alignment
   artifact, corrected here for transparency) shows **0.0 total quantity difference across every
   item-month**.
2. The full backtest re-run confirms **MAE/RMSE/Bias/MASE match to 6 decimal places** for every
   level and model between `forecastDate` and `forecastDateNoLeak` (`b4_three_way_comparison_test.csv`,
   `b4_three_way_comparison_rolling_origin.csv`).

**Conclusion (HIGH confidence): the train/val/test improvement is NOT leakage from this specific
mechanism.** There was no future-dated-relative-to-pull demand inside the evaluated window to
leak in the first place — the exclusion is a mathematical no-op given how the window was already
fixed. **Stated exactly as instructed: it survives, so with respect to this specific hypothesis
the improvement is genuine and this particular proposed leakage mechanism is not what is
happening.** This does not by itself mean the improvement is a stable, generalizable property —
see Part 3.

## Part 3 — Resolve the direction conflict

Compared per-origin Combination test MAE for both keys across all 7 rolling origins (train sizes
13, 15, 17, 19, 21, 23, 25), at all 3 levels (`b4_per_origin_comparison.csv`, chart
`output/charts/b4_per_origin_mae_comparison.png`). Sanity check passed: the last origin
(train_size=25) reproduces train/val/test's own createDate MAE exactly at every level, confirming
the two datasets describe the same underlying computation.

**The pattern is NOT a clean, smooth "window-position" gradient — it is level-dependent, and at
two of three levels it looks like a one-origin anomaly rather than a trend. Reported precisely,
not smoothed into the earlier "window-position" framing:**

| Level | forecast_date % worse than createDate, by origin (train_size 13→25) | Correlation(train_size, %diff) |
|---|---|---|
| Category | +13.2, +28.2, +33.7, +44.6, +45.2, +46.3, **-3.2** | -0.006 (≈none) |
| Type | +12.3, +28.5, +35.5, +36.8, +42.2, +32.0, **-5.0** | -0.178 (weak) |
| Item | +7.5, +22.8, +22.3, +12.2, +8.7, +6.9, **-9.3** | -0.679 (moderate) |

- **Category and Type**: forecast_date gets steadily WORSE from origin 1 through origin 6 (a
  rising, not falling, trend — the opposite of what a "later is better" story predicts), then
  **abruptly reverses only at the final origin** (train_size=25 — the exact split train/val/test
  used). Correlation is essentially zero (Category) to weak (Type) precisely because the trend
  through origins 1-6 runs the wrong way; the sign flip is concentrated entirely in the last
  point. **This does NOT support a gradual window-position effect at these two levels — it looks
  like something specific to this one final 6-month window (2026-02 to 2026-07), not a
  generalizable property of being closer to the present.**
- **Item**: shows a real, moderate declining trend from origin 2 onward (22.8→22.3→12.2→8.7→6.9→
  -9.3) — **this level DOES show genuine partial support for a window-position-type effect**,
  though the correlation (-0.68) is moderate, not definitive, and the effect still culminates in
  the same sharp final-origin reversal seen at the other two levels.

**Verdict, stated directly per instruction**: **the window-position hypothesis, in the sense of
"forecast_date's relative accuracy gradually improves the closer the origin sits to the present,"
is NOT well supported at Category or Type level (near-zero correlation, wrong-direction trend
for 6 of 7 origins) and only partially supported at Item level (real but moderate trend).** What
the data supports instead, at every level: **the entire train/val/test improvement is
concentrated in ONE SPECIFIC 6-month window (2026-02 to 2026-07)** — every other tested window
(6 of 7 origins, spanning 2024-02 through late 2025/early 2026) shows forecast_date performing
WORSE, often substantially so (up to +46%). **Practical implication: this specific test window's
improvement should not be assumed to generalize to the next 6-month window once more data
arrives** — it is evidence of one favourable window, not a demonstrated general property of
forecast_date-keying's forecastability. This is a genuine, if partial, correction to the earlier
"window-position effect, moderate confidence" note recorded after Phase B1 — the mechanism is
narrower and less reassuring than that phrase implied.

## Part 4 — Correct treatment of future-dated rows going forward

Future-dated rows are real, confirmed demand (already-placed, contractually promised orders) —
exactly what inventory planning needs to know about — but Part 1-3 show the CURRENT backtest
windows happen not to contain any, purely because of how the window was fixed relative to the
pull date. That will not always be true — a future re-run closer to the present, or a shorter
gap between window end and pull date, could easily place future-dated rows inside a test window.
**Recommendation, reasoned explicitly, concrete enough to implement in the next task:**

1. **For backtesting**: add an explicit, automatic guard — before scoring any test window
   (train/val/test or any rolling-origin holdout), assert that `pull_date` is at least
   `HOLDOUT` months after the test window's last month (i.e., the test window must be fully
   "closed" relative to the snapshot). If this assertion would fail, either (a) shrink the test
   window so it ends early enough to be fully closed, or (b) explicitly exclude rows with
   `forecast_date > pull_date` from the test-window "actual" totals AND flag exactly how much
   demand was excluded (as this task did), never silently include them. This should become a
   config-level check (e.g. `config.yaml: backtest.require_closed_test_window: true`) enforced in
   code (`src/backtest_rekeyed.py` and any successor), not a manual one-off verification — this
   task had to build ad hoc tooling to confirm it holds; that should not be needed every time.
2. **For producing live forecasts for Phase 4**: future-dated rows are NOT something to
   forecast away — they are already-known, deterministic demand and should be treated the same
   way this project already treats MPS/Backlog rows (STATUS.md, Phase 1.5 locked decision:
   confirmed demand, never dropped). Concretely: Phase 4's demand-for-planning figure for any
   future period should be **(a) the already-booked, already-forecast_date-stamped order
   quantity for that period, read directly from the order book, PLUS (b) a statistical forecast
   for the *not-yet-placed* portion of that period's demand** (the gap between total expected
   demand and what's already booked) — not a single statistical forecast that ignores known
   bookings, and not the known bookings alone (which would ignore demand not yet placed by orders
   still to come). This mirrors how the rest of this project already separates "confirmed" from
   "inferred" (per `AGENTS.md` rule 7) and should be implemented as two explicit, separately
   reported components in Phase 4, not blended into one number.
3. **Do not implement either of these now** — this task is a recommendation only, per
   instruction; both are concrete enough to write into `config.yaml` and code in the next task.

## Confidence levels

- Future-dated-row quantification (Part 1): **HIGH** (direct query, reconciled to the row).
- Zero overlap with any evaluated window: **HIGH** (direct query, decisive).
- Train/val/test improvement is not leakage from this mechanism: **HIGH** (confirmed two
  independent ways: row-level diff and full backtest re-run, both showing exact equality).
- Window-position hypothesis is not well supported at Category/Type, partially supported at
  Item: **HIGH** in the numbers (direct per-origin computation), **MODERATE** in the
  characterization of "why" (the mechanism behind the single-origin reversal is not identified).
- Recommendation for future-dated-row handling: **MODERATE** — reasoned from this project's
  existing MPS/Backlog precedent and standard order-book-plus-forecast practice, not itself
  tested against real Phase 4 outcomes (Phase 4 doesn't exist yet).

## Unresolved

- **What specifically makes the final 6-month window (2026-02 to 2026-07) favourable to
  forecast_date-keying, when 6 of 7 other windows are not** — not identified. Candidate factors
  not tested here: a specific demand event in that window, a seasonal effect, or a
  data-completeness artifact specific to recently-elapsed months. Flagged for further
  investigation, not resolved.
- Whether this pattern would persist if the window were rolled forward by a few more months as
  new data accrues (i.e., is the "favourable window" fixed to these specific calendar months, or
  does it track "closest to the present" generally) — cannot be tested without waiting for more
  data or obtaining a materially different historical pull.
- The exact mechanism behind Item level's stronger (but still moderate, not definitive) trend
  vs. Category/Type's near-absence of one — not investigated beyond the correlation reported.
