"""Moving-average comparator for the forward test (phase R1, decided by the user 2026-10-05; METRICS.md Sec.25 and Sec.27).

Top-down stays the production method. Beside it, every monthly vintage also stores a moving-average forecast for every
forecast-status item in a separate append-only log (`output/summary/forward_test_comparator_log.csv`, integrity hashes in
`forward_test_comparator_metadata.json`, the same hash method as the forward-test log) and the scoring step scores both
methods with the same metrics. Nothing is shown on any page.

The window per division is chosen here, from the CURRENT BACKTEST only: among the windows the backtest already computes
(config `moving_average_windows`), the one with the lowest mean item-level MAE over the division's items and all rolling
origins in output/summary/phaseC_step2_rolling_origin_qty.csv; a tie goes to the shorter window. It is recomputed on every
run and never uses forward-test results.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import moving_average_forecast  # noqa: E402

logger = logging.getLogger("ma_comparator")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
ROLLING_ORIGIN_PATH = os.path.join(SUMMARY_DIR, "phaseC_step2_rolling_origin_qty.csv")
WINDOWS_PATH = os.path.join(SUMMARY_DIR, "ma_comparator_windows.csv")
COMPARATOR_LOG_PATH = os.path.join(SUMMARY_DIR, "forward_test_comparator_log.csv")
COMPARATOR_METADATA_PATH = os.path.join(SUMMARY_DIR, "forward_test_comparator_metadata.json")
WINDOW_COLUMNS = ["division", "model", "window", "mean_item_MAE", "n_items", "n_origins", "chosen", "source_file",
                  "snapshot_pull_date", "first_test_month", "last_test_month"]


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def window_of(model: str) -> int:
    """'MA6' -> 6."""
    return int(model[2:])


def choose_windows(rolling_origin: pd.DataFrame, windows: list, source_file: str = None) -> pd.DataFrame:
    """One row per (division, candidate window) with its mean item-level MAE over the backtest, and `chosen` True for the
    lowest per division (a tie goes to the shorter window). `rolling_origin` is the backtest's item x origin x model rows."""
    models = [f"MA{w}" for w in windows]
    items = rolling_origin[(rolling_origin["level"] == "Item") & rolling_origin["model"].isin(models)].copy()
    if items.empty:
        raise ValueError("the backtest has no item-level moving-average rows to choose a window from")
    items["division"] = items["category"].astype(str).str.split("::").str[0]
    grouped = items.groupby(["division", "model"]).agg(mean_item_MAE=("MAE", "mean"), n_items=("key", "nunique"), n_origins=("origin", "nunique"),
                                                      first_test_month=("first_test_month", "min"), last_test_month=("last_test_month", "max"),
                                                      snapshot_pull_date=("snapshot_pull_date", "first")).reset_index()
    grouped["window"] = grouped["model"].map(window_of)
    grouped["chosen"] = False
    for division, g in grouped.groupby("division"):
        best = g.sort_values(["mean_item_MAE", "window"]).index[0]
        grouped.loc[best, "chosen"] = True
    grouped["source_file"] = source_file or os.path.relpath(ROLLING_ORIGIN_PATH, PROJECT_ROOT).replace("\\", "/")
    return grouped.sort_values(["division", "window"]).reset_index(drop=True)[WINDOW_COLUMNS]


def chosen_windows(choice: pd.DataFrame) -> dict:
    """{division: window} from choose_windows' output."""
    return {r["division"]: int(r["window"]) for _, r in choice[choice["chosen"]].iterrows()}


def current_choice(config: dict = None, rolling_path: str = ROLLING_ORIGIN_PATH) -> pd.DataFrame:
    config = config or load_config()
    rolling = pd.read_csv(rolling_path)
    return choose_windows(rolling, config["moving_average_windows"], os.path.relpath(rolling_path, PROJECT_ROOT).replace("\\", "/"))


def moving_average_rows(item_series: dict, scope_info: dict, windows_by_division: dict, target_months: list, base_row, no_history_codes=()) -> list:
    """Comparator rows (Item level) for one vintage: for every item the moving average of its division's chosen window over the
    fitted series, repeated across the horizon (models.moving_average_forecast, the backtest's own function), clipped at zero.
    `item_series` is {code: (qty_array, ...)}; items without history (`no_history_codes`) get zeros, as Top-down does.
    `base_row(code, division, level, category, type)` supplies the identifying columns."""
    horizon = len(target_months)
    records = []
    for code in sorted(set(item_series) | set(no_history_codes)):
        info = scope_info[code]
        window = windows_by_division[info["division"]]
        if code in item_series:
            fc = np.clip(moving_average_forecast(np.asarray(item_series[code][0], dtype=float), horizon, window), 0, None)
        else:
            fc = np.zeros(horizon)
        row = base_row(code, info["division"], "Item", info["category"], info["type"])
        row["model"] = f"MA{window}"
        row["window"] = window
        for h, (tm, val) in enumerate(zip(target_months, fc), start=1):
            records.append({**row, "horizon": h, "target_month": tm, "forecast_qty": round(float(val), 4), "actual_qty": ""})
    return records


def main() -> pd.DataFrame:
    choice = current_choice()
    choice.to_csv(WINDOWS_PATH, index=False)
    logger.info("Wrote %s: %s", WINDOWS_PATH, chosen_windows(choice))
    return choice


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(main().round(4).to_string(index=False))
