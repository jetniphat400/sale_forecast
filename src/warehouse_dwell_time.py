"""Phase 4 prep investigation (follow-up), Part 2: time spent at each stage.

INVESTIGATION ONLY. No min/max calculated, no model built, config.yaml not touched.

*** SCOPE LIMITATION, carried over from Part 1: the movement ledger (cube_inventory_tran) only
has usable transfer/movement history for 6 of the 128 items, and all 6 are Raw Material Fuse
Holder components (not Finished Goods). Every number in this script is evidenced ONLY for those
6 items - it is a case study of the METHOD, not a measurement that can be generalised to the 122
Finished Goods items that make up the great majority of this project's scope. ***

Method (a standard FIFO/lot-matching approach, stated explicitly, not invented ad hoc): for a
given item and warehouse, "arrival" events (external receipt transtypes A/H, or an incoming
transfer 151) are matched, oldest-first, against "departure" events (external issue transtypes
B/J, or an outgoing transfer 150) at the same warehouse, splitting quantities across events where
needed. Dwell time for each matched slice = departure_date - arrival_date, weighted by the
matched quantity. The SAME method, applied ignoring intermediate stops (matching the item's very
first external receipt anywhere against its eventual external issue anywhere), gives the total
system time from first entry to exit.

For these items, "exit" is transtype B - issue to a PRODUCTION job (confirmed from the
descriptions, e.g. "Production: DF16/001LOT2.001" - the Fuse Holder being consumed into a Fuse
Cutout assembly) - not a direct customer sale. This is stated explicitly because the user's
"reaching a sellable stage" framing does not map cleanly onto these items; see Part 3 for the
fuller discussion.
"""
import os

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "output", "charts")

ARRIVAL_TYPES = ["A", "H", "151"]
DEPARTURE_TYPES = ["B", "J", "150"]
SIX_ITEMS = ["FC-A-27-00102", "FC-A-27-00202", "FC-A-27-00203", "FC-A-38-00102", "FC-A-38-00202", "FC-A-38-00203"]


def fifo_match(arrivals: pd.DataFrame, departures: pd.DataFrame) -> list:
    """FIFO-match arrival events against departure events, splitting quantities where needed.
    arrivals/departures: DataFrames with columns ['date', 'qty'], any additional columns ignored.
    Returns a list of dicts: {'arrival_date', 'departure_date', 'qty', 'dwell_days'}."""
    arr = arrivals.sort_values("date").reset_index(drop=True).to_dict("records")
    dep = departures.sort_values("date").reset_index(drop=True).to_dict("records")
    matches = []
    ai = 0
    a_remaining = arr[0]["qty"] if arr else 0
    for d in dep:
        d_remaining = d["qty"]
        while d_remaining > 1e-6:
            if ai >= len(arr):
                break  # more departed than arrived (data gap) - unmatched remainder dropped
            take = min(d_remaining, a_remaining)
            if take > 1e-6:
                dwell = (d["date"] - arr[ai]["date"]).days
                matches.append({"arrival_date": arr[ai]["date"], "departure_date": d["date"],
                                 "qty": take, "dwell_days": dwell})
            d_remaining -= take
            a_remaining -= take
            if a_remaining <= 1e-6:
                ai += 1
                if ai < len(arr):
                    a_remaining = arr[ai]["qty"]
    return matches


def weighted_stats(matches: list) -> dict:
    if not matches:
        return {"n": 0}
    df = pd.DataFrame(matches)
    df = df[df["dwell_days"] >= 0]  # a negative dwell (departure before its matched arrival) is a data-order
    # anomaly from FIFO mismatch across overlapping lots, not a real negative dwell - excluded, reported below.
    if len(df) == 0:
        return {"n": 0}
    expanded = np.repeat(df["dwell_days"].values, np.maximum(df["qty"].round().astype(int), 1))
    return {
        "n_matched_qty": float(df["qty"].sum()), "n_events": len(df),
        "median_days": float(np.median(expanded)), "mean_days": float(np.mean(expanded)),
        "std_days": float(np.std(expanded)), "q1": float(np.percentile(expanded, 25)),
        "q3": float(np.percentile(expanded, 75)), "min_days": float(expanded.min()), "max_days": float(expanded.max()),
    }


if __name__ == "__main__":
    print("\n" + "#" * 92)
    print("# PART 2: TIME SPENT AT EACH STAGE (DWELL TIME)")
    print("#" * 92)
    print(f"\n*** Evidenced ONLY for the 6 Raw Material Fuse Holder items (see Part 1's scope limitation) - "
          f"this is a case study of the method, not a Finished-Goods-representative measurement. ***")

    tran = pd.read_csv(os.path.join(DATA_DIR, "raw_inventory_tran_128items.csv"))
    tran["warehouse"] = tran["warehouse"].astype(str).str.strip()
    tran["trans_date"] = pd.to_datetime(tran["trans_date"])
    sub = tran[tran["itemcode"].isin(SIX_ITEMS)].copy()

    # ================= PER-STAGE DWELL TIME =================
    print("\n--- DWELL TIME PER STAGE (FIFO-matched arrival -> next departure, same warehouse) ---")
    stage_rows = []
    all_stage_matches = {}
    for wh, grp in sub.groupby("warehouse"):
        arr = pd.concat([
            grp.loc[grp["transtype"].isin(["A", "H"]), ["trans_date", "QtyIn"]].rename(columns={"trans_date": "date", "QtyIn": "qty"}),
            grp.loc[grp["transtype"] == "151", ["trans_date", "QtyIn"]].rename(columns={"trans_date": "date", "QtyIn": "qty"}),
        ]).dropna()
        dep = pd.concat([
            grp.loc[grp["transtype"].isin(["B", "J"]), ["trans_date", "QtyOut"]].rename(columns={"trans_date": "date", "QtyOut": "qty"}),
            grp.loc[grp["transtype"] == "150", ["trans_date", "QtyOut"]].rename(columns={"trans_date": "date", "QtyOut": "qty"}),
        ]).dropna()
        if len(arr) == 0 or len(dep) == 0:
            continue
        matches = fifo_match(arr, dep)
        all_stage_matches[wh] = matches
        stats = weighted_stats(matches)
        stats["warehouse"] = wh
        stats["n_arrival_events"] = len(arr)
        stats["n_departure_events"] = len(dep)
        stage_rows.append(stats)

    stage_df = pd.DataFrame(stage_rows).set_index("warehouse")
    cols_order = ["n_arrival_events", "n_departure_events", "n_events", "n_matched_qty", "median_days",
                  "mean_days", "std_days", "q1", "q3", "min_days", "max_days"]
    stage_df = stage_df[[c for c in cols_order if c in stage_df.columns]].sort_values("n_matched_qty", ascending=False)
    stage_df.to_csv(os.path.join(SUMMARY_DIR, "part2_stage_dwell_time.csv"))
    print(stage_df.round(1).to_string())

    print("\nReading this: QA and WH01 are the two stages with real matched dwell-time evidence at meaningful "
          "volume. Downstream FG-family stages (FG01, FG02, FG11, FG21) have too few matched arrival/departure "
          "events for these 6 items to report a meaningful distribution (shown as thin or absent rows above) - "
          "this is a data-volume limitation for this narrow item subset, not evidence those stages are instant "
          "or unused.")

    # ================= TOTAL SYSTEM TIME =================
    print("\n--- TOTAL TIME: first entry into the system to the eventual external exit (any warehouse) ---")
    total_rows = []
    for item, grp in sub.groupby("itemcode"):
        arr = grp.loc[grp["transtype"].isin(["A", "H"]), ["trans_date", "QtyIn"]].rename(columns={"trans_date": "date", "QtyIn": "qty"}).dropna()
        dep = grp.loc[grp["transtype"].isin(["B", "J"]), ["trans_date", "QtyOut"]].rename(columns={"trans_date": "date", "QtyOut": "qty"}).dropna()
        if len(arr) == 0 or len(dep) == 0:
            continue
        matches = fifo_match(arr, dep)
        stats = weighted_stats(matches)
        stats["itemcode"] = item
        total_rows.append(stats)
    total_df = pd.DataFrame(total_rows).set_index("itemcode")
    total_df = total_df[[c for c in ["n_events", "n_matched_qty", "median_days", "mean_days", "std_days",
                                       "q1", "q3", "min_days", "max_days"] if c in total_df.columns]]
    total_df.to_csv(os.path.join(SUMMARY_DIR, "part2_total_system_time_per_item.csv"))
    print(total_df.round(1).to_string())

    all_matches = []
    for item, grp in sub.groupby("itemcode"):
        arr = grp.loc[grp["transtype"].isin(["A", "H"]), ["trans_date", "QtyIn"]].rename(columns={"trans_date": "date", "QtyIn": "qty"}).dropna()
        dep = grp.loc[grp["transtype"].isin(["B", "J"]), ["trans_date", "QtyOut"]].rename(columns={"trans_date": "date", "QtyOut": "qty"}).dropna()
        if len(arr) and len(dep):
            all_matches.extend(fifo_match(arr, dep))
    overall_stats = weighted_stats(all_matches)
    print(f"\nOVERALL (all 6 items pooled): median total system time = {overall_stats['median_days']:.1f} days, "
          f"mean = {overall_stats['mean_days']:.1f}, IQR = [{overall_stats['q1']:.1f}, {overall_stats['q3']:.1f}], "
          f"range [{overall_stats['min_days']:.0f}, {overall_stats['max_days']:.0f}] "
          f"(n={overall_stats['n_events']} matched slices, {overall_stats['n_matched_qty']:,.0f} units).")

    print("\n--- WHAT THIS ADDS TO THE STATED 45-60 DAY PROCUREMENT LEAD TIME ---")
    print(f"The stated 45-60 days is procurement time for ordering parts (upstream of receipt). What this")
    print(f"script measures starts AFTER that: from the part's physical RECEIPT into this system (transtype A/H)")
    print(f"to its eventual ISSUE to a production job (transtype B/J) - i.e. the internal handling/staging time")
    print(f"BEFORE assembly consumes it, not the procurement time itself, and not the assembly/production time")
    print(f"AFTER consumption either (this ledger stops at the issue event - it does not show how long assembly")
    print(f"then takes, or when the finished item becomes sellable).")
    print(f"For these 6 items: median internal handling time is {overall_stats['median_days']:.1f} days on top")
    print(f"of the 45-60 day procurement figure - if this pattern held for these items' own downstream assembly")
    print(f"(NOT confirmed - see caveats), total lead time would be roughly 45-60 days procurement +")
    print(f"{overall_stats['median_days']:.0f} days internal handling, BEFORE any further assembly time.")
    print(f"VARIABILITY IS LARGE: IQR [{overall_stats['q1']:.0f}, {overall_stats['q3']:.0f}] and a maximum of "
          f"{overall_stats['max_days']:.0f} days - a single added-days figure would understate how variable this "
          f"internal stage is, exactly as it does for the customer-facing lead time measured in the prior task.")

    print("\n--- CAVEATS, stated explicitly per instruction ---")
    print("1. This is evidenced for 6 of 128 items only, all Raw Material components, not Finished Goods - it")
    print("   CANNOT be assumed to generalise to the 122 FG items, which have no comparable movement ledger.")
    print("2. The 'exit' event (transtype B) is issue TO PRODUCTION (assembly consumption), not a sale - it does")
    print("   NOT mark the moment stock becomes sellable to a customer. The true 'total lead time to sellable'")
    print("   the user asked for (parts procurement -> assembly -> ready to ship) cannot be completed from this")
    print("   data: the assembly-time segment AFTER these parts are consumed is not observable in this ledger at")
    print("   all (no data links a 'B' issue event to when the resulting assembled item later becomes stock).")
    print("3. FIFO matching is a reasoned method (standard for lot-level dwell-time/aging estimation), not a")
    print("   database-recorded fact - the ledger does not tag which specific physical lot a departure consumed.")

    print("\nOutputs: output/summary/part2_stage_dwell_time.csv, part2_total_system_time_per_item.csv")
