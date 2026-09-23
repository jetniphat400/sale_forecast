"""Phase J Part 4 -- apply the robust defaults (config.yaml already edited: procurement lead time
stays 60 days -- comment corrected to say 'upper bound', not 'middle' -- and assembly time changes
3 -> 7 days) and regenerate the pipeline's output CSVs so the inventory page and parity tests see
the new default, WITHOUT a second database connection.

Why this script exists instead of just re-running src/phaseE1fix_recompute.py,
src/phaseE2_pilot_recompute.py and src/phaseE1fix_simulation.py directly: each of those scripts
independently queries the database multiple times (unit_cost, order_level, Cube_Inventory_Exact,
and for phaseE1fix_recompute also Cube_Backlog/MPS/Cube_CES for forecast_consumption) -- this
task's DATABASE ACCESS RULE (one connection attempt only) was already spent on Part 0's Cube_CES
pull. This script instead reuses src/investigations/phaseI_sensitivity_engine.py, which Phase I's
own Validator (output/summary/phaseI_4_validator_comparison.csv) already confirmed reproduces
those scripts' real output to floating-point precision from the SAME cached raw pull -- so
recomputing the new default scenario through it and writing the result to the SAME file paths is
equivalent to a real re-run, without any new database access.

Files regenerated (only the ones build_inventory_page_data.py / phaseE1fix_simulation.py /
test_inventory_parity.py actually read -- verified by grep before writing this script):
  PEM101:  phaseE1fix_1_item_policy.csv, phaseE1fix_2_unit_cost.csv,
           phaseE1fix_2_current_stock_value_inputs.csv, phaseE1fix_2_current_minmax.csv,
           phaseE1fix_2_minmax_stockvalue.csv, phaseE1fix_2_simulation.csv
  PEM103/PEM107: phaseE2pilot_<division>_1_item_policy.csv,
           phaseE2pilot_<division>_2_minmax_stockvalue_twogroup.csv,
           phaseE2pilot_<division>_2_simulation.csv

NOT regenerated (no new DB access possible, and NOT read by the inventory page or parity tests --
verified by grep): phaseE1fix_2_forecast_consumption.csv, phaseE1fix_2_months_of_cover.csv,
phaseE1fix_2_mase.csv, phaseE2pilot_<division>_2_mase.csv. These stay on their PRIOR
(assembly_time_days=3) values -- flagged here and in STATUS.md's Phase J entry, not silently left
stale without disclosure.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng
from phaseE1_common import current_minmax_per_item

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ_apply_robust_defaults")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")

ROBUST_DEFAULTS = dict(eng.DEFAULTS)
ROBUST_DEFAULTS["assembly_time_days"] = 7   # changed from 3 -- config.yaml default_scenario/
                                             # assembly_time_days_default, Phase J Part 4
assert ROBUST_DEFAULTS["procurement_lead_time_days"] == 60  # unchanged, already the upper bound


def write_pem101_files(bundle: dict, result: dict):
    result["facts"].to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_1_item_policy.csv"), index=False)
    result["unit_cost_df"].to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_unit_cost.csv"), index=False)
    result["full_df"].to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_minmax_stockvalue.csv"), index=False)
    result["sim_df"].to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_simulation.csv"), index=False)

    current_mm = current_minmax_per_item(bundle["inv_div"], bundle["codes"])
    current_mm.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_minmax.csv"), index=False)

    cs_df = result["sellable"].rename(columns={"itemcode": "code"}).merge(
        result["unit_cost_df"].rename(columns={"itemcode": "code"}), on="code", how="left").merge(
        result["facts"][["code", "policy"]], on="code", how="left")
    cs_df.to_csv(os.path.join(SUMMARY_DIR, "phaseE1fix_2_current_stock_value_inputs.csv"), index=False)
    logger.info("[PEM101] wrote phaseE1fix_1_item_policy.csv, _2_unit_cost.csv, "
                "_2_minmax_stockvalue.csv, _2_simulation.csv, _2_current_minmax.csv, "
                "_2_current_stock_value_inputs.csv (new default: assembly_time_days=7)")


def write_pilot_division_files(division: str, bundle: dict, result: dict):
    result["facts"].to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_1_item_policy.csv"), index=False)
    result["sim_df"].to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_simulation.csv"), index=False)

    fg_codes = result["fg_codes"]
    cs_df = result["sellable"].rename(columns={"itemcode": "code"}).merge(
        result["unit_cost_df"].rename(columns={"itemcode": "code"}), on="code", how="left").merge(
        result["facts"][["code", "policy"]], on="code", how="left")
    report_df = result["full_df"].merge(cs_df[["code", "sellable_stock"]], on="code", how="left")
    report_df["sellable_stock"] = report_df["sellable_stock"].fillna(0.0)
    report_df["has_onhand_stock"] = report_df["sellable_stock"] > 0
    report_df["gap_to_min"] = report_df["min_qty"] - report_df["sellable_stock"]
    report_df.loc[~report_df["has_onhand_stock"] & report_df["min_qty"].notna(), "gap_to_min"] = report_df["min_qty"]
    report_df["gap_to_min_is_full_min"] = report_df["min_qty"].notna() & (~report_df["has_onhand_stock"])
    report_df.to_csv(os.path.join(SUMMARY_DIR, f"phaseE2pilot_{division}_2_minmax_stockvalue_twogroup.csv"), index=False)
    logger.info("[%s] wrote phaseE2pilot_%s_1_item_policy.csv, _2_minmax_stockvalue_twogroup.csv, "
                "_2_simulation.csv (new default: assembly_time_days=7)", division, division)


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()

    headline_rows = []
    for division in eng.DIVISIONS:
        logger.info("=" * 100)
        logger.info("APPLYING ROBUST DEFAULTS: %s (procurement_lead_time_days=%d, assembly_time_days=%d)",
                    division, ROBUST_DEFAULTS["procurement_lead_time_days"], ROBUST_DEFAULTS["assembly_time_days"])
        logger.info("=" * 100)
        bundle = eng.build_division_bundle(config, division, raw, inv)
        result = eng.run_scenario(bundle, **ROBUST_DEFAULTS)

        counts = result["facts"]["policy"].value_counts().to_dict()
        n_undefined = counts.get("UNDEFINED_BY_METRICS_MD_SEC15", 0)
        if n_undefined:
            logger.warning("[%s] %d items fall into METRICS.md Sec.15's UNDEFINED_BY_METRICS_MD_SEC15 "
                            "bucket -- assembly_time_days=7 > this division's median_notice_days=%.1f. "
                            "KNOWN, DISCLOSED consequence of Part 4's default change (see config.yaml "
                            "comment and STATUS.md Phase J entry), not a bug.", division, n_undefined,
                            bundle["median_notice_days"])

        if division == "PEM101":
            write_pem101_files(bundle, result)
        else:
            write_pilot_division_files(division, bundle, result)

        headline_rows.append({
            "division": division, "stock_value": result["stock_value"], "fill_rate": result["fill_rate"],
            "cycle_service_level": result["cycle_service_level"], "policy_counts": counts,
            "n_undefined_by_metrics_sec15": n_undefined, "median_notice_days": bundle["median_notice_days"],
        })
        logger.info("[%s] NEW default-scenario headline: stock_value=THB %.2f, fill_rate=%.4f, "
                    "cycle_service_level=%.4f, policy=%s", division, result["stock_value"],
                    result["fill_rate"], result["cycle_service_level"], counts)

    headline_df = pd.DataFrame(headline_rows)
    headline_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ_4_new_default_headline.csv"), index=False)

    print("\n" + "=" * 100)
    print("PHASE J PART 4 -- NEW DEFAULT-SCENARIO HEADLINE FIGURES (robust defaults applied)")
    print("=" * 100)
    print(headline_df.to_string(index=False))
    return headline_df


if __name__ == "__main__":
    main()
