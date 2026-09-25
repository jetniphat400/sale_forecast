"""Tests for src/score_forward_test_all_divisions.py's ADAPTED consistency check (forward test /
monthly refresh task, Part 1.3).

BEFORE: verify_consistency(metadata, current_config, current_scope_codes, current_divisions)
compared a single flat metadata dict against the CURRENT live config.yaml / CURRENT scope file --
any drift in config.yaml since the log was generated made scoring impossible, even for a vintage
whose own recorded forecasts were untouched (METRICS.md Sec.27 says existing vintages are frozen
and comparing vintages over time IS the forward test, not a reason to block on later config
changes).

AFTER: verify_consistency(log, metadata) checks EACH vintage_id present in `log` against its OWN
recorded metadata entry (never against config.yaml or config_version() at all) via two checks:
  1. internal consistency -- every row of a vintage agrees with that vintage's own recorded
     config_version/date_key/scope_hash/scope_n_items.
  2. integrity hash -- src/forward_test_common.compute_row_integrity_hash, recomputed from the
     log's CURRENT rows for that vintage (excluding actual_qty), must equal the hash recorded in
     that vintage's metadata at generation time.
Same rule as every other guard in this project: a mismatch must raise loudly
(ForwardTestConsistencyError), never warn-and-continue (CONVENTIONS.md).
"""
import pandas as pd
import pytest

from forward_test_common import ForwardTestConsistencyError, compute_row_integrity_hash
from score_forward_test_all_divisions import score_and_summarize, verify_consistency

ROW_COLUMNS = ["itemcode", "division", "level", "category", "type", "forecast_run_date",
               "data_cutoff_date", "fit_last_month", "model", "config_version", "date_key",
               "scope_hash", "scope_n_items", "horizon", "target_month", "forecast_qty"]


def _make_vintage_rows(vintage_id: int, config_version: str, n_items: int = 2) -> pd.DataFrame:
    rows = []
    for i in range(n_items):
        rows.append({
            "vintage_id": vintage_id, "itemcode": f"ITEM-{i}", "division": "PEM101", "level": "Item",
            "category": "Cat", "type": "Typ", "forecast_run_date": "2026-09-07",
            "data_cutoff_date": "2026-09-07", "fit_last_month": "2026-07",
            "model": "Top-down_Combination", "config_version": config_version,
            "date_key": "forecastDate", "scope_hash": "abc123", "scope_n_items": n_items,
            "horizon": 1, "target_month": "2026-08", "forecast_qty": 1.5 + i, "actual_qty": "",
        })
    return pd.DataFrame(rows)


def _metadata_for(rows: pd.DataFrame) -> dict:
    r0 = rows.iloc[0]
    return {
        "config_version": r0["config_version"], "date_key": r0["date_key"],
        "scope_hash": r0["scope_hash"], "scope_n_items": int(r0["scope_n_items"]),
        "row_integrity_hash": compute_row_integrity_hash(rows),
    }


def test_verify_consistency_passes_when_vintage_matches_its_own_metadata():
    rows = _make_vintage_rows(1, "aaa111")
    metadata = {"1": _metadata_for(rows)}
    verify_consistency(rows, metadata)  # must not raise


def test_verify_consistency_does_not_check_against_current_live_config():
    """The adaptation's whole point: a vintage recorded under an OLD config_version that no
    longer matches config.yaml's CURRENT config_version() must still pass, as long as it matches
    ITS OWN recorded metadata/hash. Uses an obviously-fake config_version that cannot possibly
    equal the real config_version() -- if this ever raised, it would mean the old
    against-current-config behaviour crept back in."""
    rows = _make_vintage_rows(1, "obsolete_config_from_a_past_run_000000")
    metadata = {"1": _metadata_for(rows)}
    verify_consistency(rows, metadata)  # must not raise, even though it doesn't match config.yaml


def test_verify_consistency_raises_on_row_integrity_hash_mismatch():
    """Simulates a forecast_qty silently edited after the vintage was generated -- the recorded
    hash was computed BEFORE the edit, so it no longer matches a fresh recompute."""
    rows = _make_vintage_rows(1, "aaa111")
    metadata = {"1": _metadata_for(rows)}
    tampered = rows.copy()
    tampered.loc[0, "forecast_qty"] = 999.0
    with pytest.raises(ForwardTestConsistencyError, match="row_integrity_hash"):
        verify_consistency(tampered, metadata)


def test_verify_consistency_raises_on_internal_inconsistency():
    """One row's config_version disagrees with the rest of the vintage's rows AND with what the
    vintage's own metadata recorded -- a corrupted/half-written vintage, not a config-drift case."""
    rows = _make_vintage_rows(1, "aaa111")
    metadata = {"1": _metadata_for(rows)}
    corrupted = rows.copy()
    corrupted.loc[0, "config_version"] = "different_from_the_rest"
    with pytest.raises(ForwardTestConsistencyError, match="not internally consistent"):
        verify_consistency(corrupted, metadata)


def test_verify_consistency_raises_when_metadata_missing_for_a_vintage_in_log():
    rows = _make_vintage_rows(2, "bbb222")
    metadata = {"1": _metadata_for(_make_vintage_rows(1, "aaa111"))}  # only vintage 1 recorded
    with pytest.raises(ForwardTestConsistencyError, match="no metadata entry"):
        verify_consistency(rows, metadata)


def test_verify_consistency_raises_when_vintage_id_column_missing():
    rows = _make_vintage_rows(1, "aaa111").drop(columns=["vintage_id"])
    with pytest.raises(ForwardTestConsistencyError, match="vintage_id"):
        verify_consistency(rows, {"1": {}})


def test_verify_consistency_checks_multiple_vintages_independently():
    """A log with two vintages: vintage 1 is fine, vintage 2 has a tampered row. Must raise,
    naming vintage 2 specifically, without vintage 1's own validity affecting the outcome."""
    rows1 = _make_vintage_rows(1, "aaa111")
    rows2 = _make_vintage_rows(2, "bbb222")
    metadata = {"1": _metadata_for(rows1), "2": _metadata_for(rows2)}
    combined = pd.concat([rows1, rows2], ignore_index=True)
    combined.loc[combined["vintage_id"] == 2, "forecast_qty"] = combined.loc[
        combined["vintage_id"] == 2, "forecast_qty"] + 100
    with pytest.raises(ForwardTestConsistencyError, match="vintage 2"):
        verify_consistency(combined, metadata)

    # And the same combined log with BOTH vintages untouched must pass.
    verify_consistency(pd.concat([rows1, rows2], ignore_index=True), metadata)


# ---------------------------------------------------------------------------------------------
# Part 1.5: synthetic fixture proving scoring produces correct METRICS.md Sec.25 metrics
# (MAE = mean(|error|), RMSE = sqrt(mean(error^2))) once a target month IS eligible -- score_and_
# summarize() is the extracted pure-computation step (no DB call, no leakage-guard call), so this
# needs no real forward-test log, no config.yaml, and no database connection at all.
# ---------------------------------------------------------------------------------------------

def test_score_and_summarize_produces_correct_mae_and_rmse_synthetic_fixture():
    log = pd.DataFrame([
        {"itemcode": "ITEM-A", "division": "PEM101", "level": "Item", "target_month": "2026-01",
         "model": "M1", "forecast_qty": 10.0, "actual_qty": ""},
        {"itemcode": "ITEM-B", "division": "PEM101", "level": "Item", "target_month": "2026-01",
         "model": "M1", "forecast_qty": 20.0, "actual_qty": ""},
        # Not yet eligible -- must be excluded from both actual_qty-filling and the summary.
        {"itemcode": "ITEM-A", "division": "PEM101", "level": "Item", "target_month": "2099-01",
         "model": "M1", "forecast_qty": 7.0, "actual_qty": ""},
    ])
    actuals = pd.DataFrame([
        {"itemcode": "ITEM-A", "division": "PEM101", "level": "Item", "target_month": "2026-01",
         "realised_actual_qty": 8.0},   # error = 10 - 8 = 2
        {"itemcode": "ITEM-B", "division": "PEM101", "level": "Item", "target_month": "2026-01",
         "realised_actual_qty": 25.0},  # error = 20 - 25 = -5
    ])
    safe_months = ["2026-01"]

    scored, summary = score_and_summarize(log, actuals, safe_months)

    # ---- scored: actual_qty filled ONLY for the eligible month ----
    eligible_rows = scored[scored["target_month"] == "2026-01"]
    assert sorted(eligible_rows["actual_qty"].tolist()) == [8.0, 25.0]
    not_yet_eligible = scored[scored["target_month"] == "2099-01"].iloc[0]
    assert not_yet_eligible["actual_qty"] == "" or pd.isna(pd.to_numeric(not_yet_eligible["actual_qty"], errors="coerce"))

    # ---- summary: hand-computed expected MAE/RMSE/Bias, METRICS.md Sec.25's exact formulas ----
    errors = [2.0, -5.0]  # forecast - actual, per row above
    expected_mae = sum(abs(e) for e in errors) / len(errors)          # mean(|error|) = 3.5
    expected_rmse = (sum(e ** 2 for e in errors) / len(errors)) ** 0.5  # sqrt(mean(error^2)) ~= 3.8079
    expected_bias = sum(errors) / len(errors)                          # mean(error) = -1.5

    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["division"] == "PEM101" and row["level"] == "Item" and row["model"] == "M1"
    assert row["n"] == 2
    assert row["MAE"] == pytest.approx(expected_mae)
    assert row["RMSE"] == pytest.approx(expected_rmse)
    assert row["Bias"] == pytest.approx(expected_bias)
    # Sanity: RMSE >= MAE always holds (Cauchy-Schwarz) except when all errors are equal magnitude.
    assert row["RMSE"] >= row["MAE"]


def test_score_and_summarize_returns_none_summary_when_nothing_eligible():
    log = pd.DataFrame([
        {"itemcode": "ITEM-A", "division": "PEM101", "level": "Item", "target_month": "2099-01",
         "model": "M1", "forecast_qty": 7.0, "actual_qty": ""},
    ])
    actuals = pd.DataFrame(columns=["itemcode", "division", "level", "target_month", "realised_actual_qty"])
    scored, summary = score_and_summarize(log, actuals, safe_months=[])
    assert summary is None
    assert len(scored) == 1
