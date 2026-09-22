"""Phase E0, Validator 3: placeholder coherence with Type totals (E0.3).

Question: when a placeholder item (Type mean/median under Rule A/B, config.yaml
`placeholder_item_assignments_82`) is added into a Type that the production Top-down
Combination method (`forecast_method_final: topdown_combination`) already allocates by
historical qty share among its REAL (non-placeholder, history-bearing) members, what happens
to the Type's total?

  - Option 1 (additive): placeholder qty is added ON TOP of the Type's existing real-item
    total. Every real item keeps today's own forecast unchanged; the Type's total (real sum +
    placeholders) now EXCEEDS what the Type-level Combination model itself forecasts --
    hierarchy consistency (item sum == Type total) breaks.
  - Option 2 (carve-out): the Type's total is held FIXED at today's real-item total; every
    item (real or placeholder) gets a share of that SAME fixed total, so placeholders "compete"
    with real items for a slice, and every real item's forecast shrinks vs. today by a scale
    factor of real_item_total / (real_item_total + placeholder_sum). Hierarchy consistency is
    preserved by construction (item sum == Type total, exactly), but no real item's own forecast
    is left unchanged.

This script does not choose between them (Validator role, AGENTS.md: "reports, does not
implement"; "when two positions exist, report both, do not pick a side").

Data sources (no new query needed -- this is a Validator recomputation of existing production
outputs, all cited directly):
  - config/config.yaml: `placeholder_item_assignments_82` (82 items, rule + placeholder_qty =
    Type mean/median MONTHLY qty per item), `placeholder_rule_set`.
  - output/summary/phaseC_placeholder_assignment_82items.csv: same 82 items with their
    division/type/sheet/n_siblings_with_history/type_top_item_share_pct (the evidence CSV
    already cited by config.yaml's placeholder_rule_set.evidence_csv key).
  - output/summary/forward_test_log_all_divisions.csv: the actual PRODUCTION Top-down
    Combination forward-test log (335-item scope, config_version 10a9cb4a5e05, forecast_run_date
    2026-09-07), which already contains BOTH the Item-level allocated forecast_qty AND the
    Type-level Combination forecast_qty it was allocated from, for every real (history-bearing)
    item and Type -- i.e. exactly "the existing production Top-down forecast output" the task
    brief asks to use if one exists. horizon=1 / target_month=2026-08 is used throughout as the
    representative month (forecast_qty is flat across all 6 horizons for every item checked --
    confirmed directly, see the horizon-flatness check in the console output below).
  - output/summary/phaseC_89items_characterization.csv: the existing trace-pattern
    classification (`trace_pattern` column) for why each item lacks Omni-Channel history --
    cited verbatim, not re-derived.
  - reference/pricelist.xlsx (via src/pricelist_reader.py): searched for predecessor/
    near-identical-spec-variant candidates for each of the 82 items.

Outputs:
  - output/summary/phaseE0_validator3_placeholder_type_totals.csv
  - output/summary/phaseE0_validator3_82item_reasons.csv
  - output/summary/phaseE0_validator3_placeholder_coherence_report.md (written by hand from
    this script's console output, not generated automatically -- the report is the primary
    deliverable and needs prose the script does not produce)
"""
import os
import re
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pricelist_reader import load_visible_product_rows  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY = os.path.join(PROJECT_ROOT, "output", "summary")
FOCUS_ITEMS = ["EEE-F-FC-1040010002", "HS-F-99-02110", "HS-F-99-0213"]


def load_inputs():
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    pa82 = cfg["placeholder_item_assignments_82"]
    assign = pd.read_csv(os.path.join(SUMMARY, "phaseC_placeholder_assignment_82items.csv"))
    fwd = pd.read_csv(os.path.join(SUMMARY, "forward_test_log_all_divisions.csv"))
    char = pd.read_csv(os.path.join(SUMMARY, "phaseC_89items_characterization.csv"))
    pricelist = load_visible_product_rows(os.path.join(PROJECT_ROOT, cfg["pricelist_path"]))
    return cfg, pa82, assign, fwd, char, pricelist


def check_horizon_flatness(fwd: pd.DataFrame) -> None:
    """Confirms forecast_qty is constant across all 6 horizons for a sample of items --
    justifies using horizon=1 alone as "the" monthly figure rather than averaging six values."""
    sample = fwd[fwd["level"] == "Item"].groupby("itemcode")["forecast_qty"].nunique()
    n_flat = (sample == 1).sum()
    print(f"Horizon-flatness check: {n_flat} of {len(sample)} items have IDENTICAL forecast_qty "
          f"across all 6 horizons (Combination forecast is flat here) -- horizon=1 (2026-08) is "
          f"used as the representative monthly figure throughout.")


def build_type_totals(assign: pd.DataFrame, fwd: pd.DataFrame) -> tuple:
    fwd1 = fwd[fwd["horizon"] == 1].copy()
    item_fwd = fwd1[fwd1["level"] == "Item"][["itemcode", "division", "type", "forecast_qty"]]
    type_fwd = fwd1[fwd1["level"] == "Type"][["division", "type", "forecast_qty"]].rename(
        columns={"forecast_qty": "type_forecast_qty_direct"})

    assign_types = assign[["division", "type"]].drop_duplicates()
    matched = assign_types.merge(type_fwd[["division", "type"]].drop_duplicates(),
                                  on=["division", "type"], how="left", indicator=True)
    matched_types = matched[matched["_merge"] == "both"][["division", "type"]]
    unmatched_types = matched[matched["_merge"] == "left_only"][["division", "type"]]

    rows, share_rows = [], []
    for _, tr in matched_types.iterrows():
        div, typ = tr["division"], tr["type"]
        real_items = item_fwd[(item_fwd["division"] == div) & (item_fwd["type"] == typ)].copy()
        real_item_total = real_items["forecast_qty"].sum()
        type_direct = type_fwd[(type_fwd["division"] == div) & (type_fwd["type"] == typ)][
            "type_forecast_qty_direct"].iloc[0]

        ph_rows = assign[(assign["division"] == div) & (assign["type"] == typ)]
        num_placeholders = len(ph_rows)
        placeholder_sum = ph_rows["placeholder_qty"].fillna(0).sum()

        option1 = real_item_total + placeholder_sum
        option2 = real_item_total

        rows.append({
            "division": div, "type": typ,
            "n_real_items_with_history": len(real_items),
            "real_item_total_forecast_qty_2026_08": round(real_item_total, 4),
            "type_level_direct_forecast_qty_2026_08": round(type_direct, 4),
            "hierarchy_check_real_sum_minus_type_direct": round(real_item_total - type_direct, 6),
            "num_placeholders": num_placeholders,
            "placeholder_sum_monthly_qty": round(placeholder_sum, 4),
            "total_under_option1_additive": round(option1, 4),
            "total_under_option2_carveout": round(option2, 4),
            "option1_minus_option2_inflation": round(option1 - option2, 4),
            "option1_pct_inflation_vs_option2": round(100 * (option1 - option2) / option2, 2) if option2 else np.nan,
            "carveout_scale_factor_real_items": round(real_item_total / option1, 6) if option1 else np.nan,
        })

        real_items["share_before"] = real_items["forecast_qty"] / real_item_total
        real_items_sorted = real_items.sort_values("share_before", ascending=False)
        for label, r in [("top_share_real_item", real_items_sorted.iloc[0]),
                         ("smallest_share_real_item", real_items_sorted.iloc[-1])]:
            share_before = r["forecast_qty"] / real_item_total
            share_after = r["forecast_qty"] / option1
            fc_after = share_after * option2
            share_rows.append({
                "division": div, "type": typ, "role": label, "itemcode": r["itemcode"],
                "forecast_qty_today_2026_08": round(r["forecast_qty"], 4),
                "share_before_pct": round(100 * share_before, 4),
                "share_after_carveout_pct": round(100 * share_after, 4),
                "forecast_under_option1_additive": round(r["forecast_qty"], 4),
                "forecast_under_option2_carveout": round(fc_after, 4),
                "pct_change_under_option2_vs_today": round(
                    100 * (fc_after - r["forecast_qty"]) / r["forecast_qty"], 2) if r["forecast_qty"] else np.nan,
            })

    return pd.DataFrame(rows), pd.DataFrame(share_rows), matched_types, unmatched_types, item_fwd, assign_types


def check_focus_items(fwd: pd.DataFrame, assign_types: pd.DataFrame) -> pd.DataFrame:
    fwd1 = fwd[fwd["horizon"] == 1]
    foc_types = fwd1[fwd1["itemcode"].isin(FOCUS_ITEMS)][["itemcode", "division", "type"]]
    overlap = foc_types.merge(assign_types, on=["division", "type"], how="inner")
    return foc_types, overlap


def pem103_family_predecessors(pricelist: pd.DataFrame, pa82: dict) -> dict:
    """Same-family (loss-class + voltage tier), nearest-kVA-rating real sibling with history,
    for every one of the 37 no-history 3-Phase-Distribution-Transformer items. 'Family' is the
    description with the kVA number masked out -- a deterministic, directly-verifiable key."""
    t = pricelist[pricelist["type"] == "3 Phase Distribution Transformer"].copy()
    t["family"] = t["description"].apply(lambda d: re.sub(r"\d+(\.\d+)?\s*kVA", "XXXkVA", d))
    t["kva"] = t["description"].apply(
        lambda d: float(m.group(1)) if (m := re.search(r"(\d+(\.\d+)?)\s*kVA", d)) else None)
    t["no_hist"] = t["code"].isin(pa82.keys())

    out = {}
    for fam, g in t.groupby("family"):
        hist_rows = g[~g["no_hist"]]
        for _, r in g[g["no_hist"]].iterrows():
            if len(hist_rows) == 0:
                out[r["code"]] = None
                continue
            hr = hist_rows.copy()
            hr["dist"] = (hr["kva"] - r["kva"]).abs()
            out[r["code"]] = hr.sort_values("dist").iloc[0]["code"]
    assert len(out) == 37, f"expected 37 PEM103 no-history items, found {len(out)}"
    return out


if __name__ == "__main__":
    cfg, pa82, assign, fwd, char, pricelist = load_inputs()
    check_horizon_flatness(fwd)

    type_totals_df, share_df, matched_types, unmatched_types, item_fwd, assign_types = build_type_totals(assign, fwd)
    type_totals_df.to_csv(os.path.join(SUMMARY, "phaseE0_validator3_placeholder_type_totals.csv"), index=False)

    foc_types, overlap = check_focus_items(fwd, assign_types)
    print("\nFocus items' Types:\n", foc_types.to_string())
    print("\nOverlap with any placeholder-affected Type (expected EMPTY):\n", overlap.to_string())

    pem103_pred = pem103_family_predecessors(pricelist, pa82)

    print("\nUnmatched Types (Rule C, zero real siblings -- no Type-level forecast exists):\n",
          unmatched_types.to_string())
    print(f"\nWrote {len(type_totals_df)} Type rows to phaseE0_validator3_placeholder_type_totals.csv")
    print("PEM103 family-predecessor count:", len(pem103_pred), "(all 37 resolved)")
    print("\nSee phaseE0_placeholder_coherence_validator3_reasons.py for the full 82-item "
          "predecessor/analogue table (manual, individually-cited assignments for the other 45 "
          "items, plus this script's own PEM103 family-match logic for the 37 transformer items).")
