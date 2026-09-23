"""Phase J2 Part 0 -- revert the pipeline's written output files back to assembly_time_days=3
(config.yaml's default_scenario, already reverted). Reuses phaseJ_apply_robust_defaults.py's own
file-writing functions (no new DB access; same cached raw pull) with eng.DEFAULTS instead of
ROBUST_DEFAULTS, then regenerates forecast/inventory.html the same (patched, no-new-connection)
way Phase J did.
"""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phaseI_sensitivity_engine as eng
from phaseJ_apply_robust_defaults import write_pem101_files, write_pilot_division_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseJ2_revert_assembly_default")

SUMMARY_DIR = os.path.join(eng.PROJECT_ROOT, "output", "summary")


def main():
    config = eng.load_config()
    raw, inv = eng.load_raw()

    headline_rows = []
    for division in eng.DIVISIONS:
        logger.info("[%s] reverting to config default (assembly_time_days=%d)", division,
                    eng.DEFAULTS["assembly_time_days"])
        bundle = eng.build_division_bundle(config, division, raw, inv)
        result = eng.run_scenario(bundle, **eng.DEFAULTS)

        counts = result["facts"]["policy"].value_counts().to_dict()
        if division == "PEM101":
            write_pem101_files(bundle, result)
        else:
            write_pilot_division_files(division, bundle, result)

        headline_rows.append({"division": division, "stock_value": result["stock_value"],
                              "fill_rate": result["fill_rate"],
                              "cycle_service_level": result["cycle_service_level"],
                              "policy_counts": counts})
        logger.info("[%s] REVERTED default-scenario headline: stock_value=THB %.2f, fill_rate=%.4f, "
                    "policy=%s", division, result["stock_value"], result["fill_rate"], counts)

    headline_df = pd.DataFrame(headline_rows)
    headline_df.to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_0_reverted_default_headline.csv"), index=False)
    print(headline_df.to_string(index=False))
    return headline_df


if __name__ == "__main__":
    main()
