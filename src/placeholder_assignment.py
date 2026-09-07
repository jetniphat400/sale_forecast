"""Phase C closeout, Part 2: decide the placeholder method for the 82 no-history items (the 89
found by the 2026-09-04 full-scope re-validation minus the 7 PEM104-sheet codes, which are
excluded at division level instead — see STATUS.md, "Phase C step 2", Part 0b).

Uses the characterisation already produced by
output/summary/phaseC_89items_characterization_report.md /
output/summary/phaseC_89items_characterization.csv — this script does not re-derive sibling
counts, concentration, or trace evidence; it applies a fixed rule set to that already-gathered
evidence and writes the result to config.

RULE SET (as instructed, a fixed threshold, not derived from this data):
  Rule A — Type has >=1 sibling with history, top sibling holds < 40% of the Type's history-bearing
           value: placeholder = the TYPE MEAN monthly demand per item.
  Rule B — Type has >=1 sibling with history, top sibling holds >= 40%: placeholder = the TYPE
           MEDIAN monthly demand per item (the mean would be pulled toward the dominant item).
  Rule C — Type has 0 siblings with history: FLAG ONLY, placeholder = 0, no number invented,
           marked for business input.
  Rule D — an item under Rule A or B ALSO has a Cube_CES trace showing a 2023 delivery (Actual or
           Backlog status, Omni Channel) with no cube_Sale_APD row in any year: same value as
           Rule A/B, with an added note recording the 2023 activity. Not a fourth value rule —
           an annotation layered onto A or B.

FORMULAS, stated explicitly since the task described them in words, not as computations:
  "Type mean monthly demand per item" = mean, across the Type's history-bearing siblings, of each
    sibling's own mean monthly qty over the fitting window (2024-01 to 2026-07, the same 31-month
    window Phase C step 2 forecasts on). Equivalent to (Type's total qty over the window) /
    (n siblings) / 31 months, since every sibling's series is reindexed to the same 31 months.
  "Type median" = the MEDIAN, across the same siblings, of each sibling's own mean monthly qty —
    NOT the median of the Type's pooled monthly totals. Using each sibling's own mean first, then
    taking the median across siblings, is what actually resists being pulled toward one dominant
    item's scale (a median of pooled Type-total months would still mostly reflect the dominant
    item's monthly figures).

The 40% threshold is an ASSUMPTION carried from this task's instruction, not derived from this
data — recorded as such in the output, to be revisited if it produces poor results in practice.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("placeholder_assignment")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

DOMINANCE_THRESHOLD_PCT = 40.0  # STATED ASSUMPTION, from this task's instruction, not derived here


def load_characterization() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_89items_characterization.csv"))
    df82 = df[df["sheet"] != "PEM104"].copy()
    if len(df82) != 82:
        raise ValueError(f"Expected 82 non-PEM104 no-history codes, found {len(df82)} — "
                          f"the 7-item PEM104 overlap resolution may not match this characterization file.")
    return df82


def compute_sibling_monthly_means(monthly: pd.DataFrame, scope: pd.DataFrame) -> dict:
    """{(division, type): [mean monthly qty per sibling with history]} — one number per
    history-bearing item in that division-qualified Type, computed from the same 31-month
    processed_all_divisions_monthly_qty.csv series Phase C step 2 forecasts on."""
    out = {}
    for (div, typ), g in monthly.merge(scope[["code", "division", "type"]].rename(columns={"code": "itemcode"}),
                                        on=["itemcode", "division", "type"]).groupby(["division", "type"]):
        per_item_means = g.groupby("itemcode")["qty"].mean()
        out[(div, typ)] = per_item_means.tolist()
    return out


def assign_rule(row: pd.Series, sibling_means: dict) -> dict:
    n_sib = int(row["n_siblings_with_history"])
    top_pct = row["type_top_item_share_pct"]
    has_2023_trace = (row.get("_last_ctrdate_year") == 2023) and bool(row.get("ces_actual_backlog_has_omni_channel_row"))
    trace_note = ""
    if has_2023_trace:
        trace_note = (f"Cube_CES shows a {int(row['_last_ctrdate_year'])} Actual/Backlog Omni Channel delivery for "
                      f"this item, but no cube_Sale_APD row in any year — see "
                      f"output/summary/phaseC_9item_cubeces_check.csv. Rule D annotation.")

    if n_sib == 0:
        note = "No siblings with history in this Type — flagged for business input, no number invented."
        # Edge case not explicitly covered by the instruction (which describes Rule D as modifying
        # the SIBLING rule, i.e. A or B): an item can have BOTH zero siblings with history AND a
        # 2023 Cube_CES trace. Reported honestly rather than silently dropping the trace note —
        # the item still gets Rule C's value (0, flagged), the trace is additional context only.
        if trace_note:
            note = f"{note} ALSO: {trace_note} (this item has no siblings, so Rule D's own value guidance does not apply here — Rule C's zero/flag stands.)"
        return {"rule": "C", "placeholder_qty": 0.0, "flag_only": True, "note": note, "has_2023_trace": has_2023_trace}

    means = sibling_means.get((row["_division"], row["type"]), [])
    if not means:
        raise ValueError(f"{row['code']}: n_siblings_with_history={n_sib} but no sibling monthly-mean data found "
                          f"for ({row['_division']}, {row['type']}) — characterization and monthly series disagree.")

    if pd.isna(top_pct):
        raise ValueError(f"{row['code']}: type_top_item_share_pct is NaN despite {n_sib} siblings with history.")

    if top_pct >= DOMINANCE_THRESHOLD_PCT:
        value = float(np.median(means))
        rule = "B"
    else:
        value = float(np.mean(means))
        rule = "A"

    note = f"{trace_note} Rule {rule} value used unchanged; this is an annotation (Rule D), not a different value rule." if trace_note else ""
    return {"rule": rule, "placeholder_qty": round(value, 4), "flag_only": False, "note": note, "has_2023_trace": has_2023_trace}


if __name__ == "__main__":
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    char_df = load_characterization()
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "phaseC_step2_scope_335items.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_all_divisions_monthly_qty.csv"))

    sheet_to_division = config["sheet_to_division"]
    char_df["_division"] = char_df["sheet"].map(sheet_to_division)
    unmapped = char_df[char_df["_division"].isna()]
    if len(unmapped):
        raise ValueError(f"{len(unmapped)} codes have a sheet with no config['sheet_to_division'] mapping: "
                          f"{unmapped[['code', 'sheet']].to_dict('records')}")

    char_df["_last_ctrdate_year"] = pd.to_datetime(char_df["last_ctrdate"], errors="coerce").dt.year

    sibling_means = compute_sibling_monthly_means(monthly, scope)

    results = []
    for _, row in char_df.iterrows():
        assignment = assign_rule(row, sibling_means)
        results.append({
            "code": row["code"], "sheet": row["sheet"], "division": row["_division"],
            "type": row["type"], "n_siblings_with_history": int(row["n_siblings_with_history"]),
            "type_top_item_share_pct": row["type_top_item_share_pct"], **assignment,
        })
    result_df = pd.DataFrame(results)
    result_df.to_csv(os.path.join(SUMMARY_DIR, "phaseC_placeholder_assignment_82items.csv"), index=False)

    counts = result_df["rule"].value_counts().to_dict()
    flag_only = result_df[result_df["flag_only"]]
    rule_d_count = int(result_df["has_2023_trace"].sum())

    logger.info("Rule counts: %s (of %d total)", counts, len(result_df))
    logger.info("Flag-only (Rule C): %d items", len(flag_only))
    logger.info("Rule D annotation (2023 Cube_CES trace, no cube_Sale_APD row): %d items", rule_d_count)

    print("\n" + "=" * 78)
    print("PLACEHOLDER ASSIGNMENT — 82 no-history items (PEM104's 7 excluded separately)")
    print("=" * 78)
    print(f"\nRule A (Type mean, top sibling <{DOMINANCE_THRESHOLD_PCT:.0f}%): {counts.get('A', 0)}")
    print(f"Rule B (Type median, top sibling >={DOMINANCE_THRESHOLD_PCT:.0f}%): {counts.get('B', 0)}")
    print(f"Rule C (flag only, no siblings with history): {counts.get('C', 0)}")
    print(f"Rule D annotation (2023 Cube_CES trace, layered on A/B): {rule_d_count}")
    print(f"\nFlag-only items (Rule C):")
    print(flag_only[["code", "sheet", "type"]].to_string(index=False))
    print(f"\nOutput: output/summary/phaseC_placeholder_assignment_82items.csv")
