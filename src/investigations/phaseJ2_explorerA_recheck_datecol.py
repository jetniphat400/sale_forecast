"""Phase J2, Explorer A -- follow-up date-column check, NO new database query.

The first pass (phaseJ2_explorerA_quotation_notice.py) defaulted to Cube_Quotation.report_date
as "the quotation date" because it was the field named in the prior investigation
(investigate_leadtime_classification.py). Inspecting the raw cached pull
(output/data/phaseJ2_explorerA_cube_quotation_raw_351items.csv) shows this was likely wrong:
report_date is 99.90% non-null overall but is NULL on most early-scanned rows, and on the rows
where it IS populated it is IDENTICAL to Cube_Quotation.forecast_date in every sampled case
(e.g. quotation QTN-2025-00350: report_date=2023-08-04, forecast_date=2023-08-04). That looks
like report_date tracks a delivery/disposition date, not a quotation-issued date.
Cube_Quotation.create_date (99.81% non-null, distinct from forecast_date, consistent with the
quotation number's own embedded year) is the more plausible "date the quotation was issued"
field. This script re-tests BOTH, from the already-cached data (no new DB access), and reports
which is defensible.
"""
import os

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")


def dist(s):
    return {"n": int(s.count()), "min": s.min(), "p25": s.quantile(0.25), "median": s.median(),
            "p75": s.quantile(0.75), "max": s.max(), "mean": round(s.mean(), 2),
            "n_negative": int((s < 0).sum()), "pct_negative": round(100*(s < 0).mean(), 2)}


def main():
    quo = pd.read_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_quotation_raw_351items.csv"))
    sales = pd.read_csv(os.path.join(DATA_DIR, "phaseJ2_explorerA_cube_sale_apd_raw_351items.csv"))

    print("=" * 90)
    print("CHECK: does report_date == forecast_date wherever report_date is populated, in Cube_Quotation?")
    print("=" * 90)
    both = quo[quo["report_date"].notna() & quo["forecast_date"].notna()]
    eq = (pd.to_datetime(both["report_date"]) == pd.to_datetime(both["forecast_date"])).mean()
    print(f"Rows with BOTH report_date and forecast_date populated: {len(both)} of {len(quo)}")
    print(f"Of those, report_date == forecast_date (exact date match): {100*eq:.2f}%")
    print("report_date populated but forecast_date null:", (quo['report_date'].notna() & quo['forecast_date'].isna()).sum())
    print("report_date null but forecast_date populated:", (quo['report_date'].isna() & quo['forecast_date'].notna()).sum())

    quo["create_date"] = pd.to_datetime(quo["create_date"], errors="coerce")
    quo["report_date"] = pd.to_datetime(quo["report_date"], errors="coerce")

    sales["quotationid_clean"] = sales["quotationid"].astype(str).str.strip()
    sales["has_quotationid"] = (~sales["quotationid_clean"].isin(["None", "none", "NONE", "", "nan", "NaN"])) & sales["quotationid"].notna()
    sales["createDate"] = pd.to_datetime(sales["createDate"])
    sales["forecast_date"] = pd.to_datetime(sales["forecast_date"], errors="coerce")

    results_all = {}
    for datecol in ["create_date", "report_date"]:
        print("\n" + "=" * 90)
        print(f"USING Cube_Quotation.{datecol} AS THE QUOTATION DATE")
        print("=" * 90)
        quo_dedup = quo.groupby(["itemcode", "quotation"], as_index=False)[datecol].min()

        merged = sales.merge(quo_dedup, left_on=["itemcode", "quotationid_clean"],
                              right_on=["itemcode", "quotation"], how="left", indicator=True)
        matched = merged[merged["_merge"] == "both"].copy()
        n_matched = len(matched)
        print(f"Matched rows: {n_matched} of {len(sales)} total scoped rows "
              f"({100*n_matched/len(sales):.2f}%), {100*n_matched/sales['has_quotationid'].sum():.2f}% of rows with a quotationid")

        matched["quote_to_create_days"] = (matched["createDate"] - matched[datecol]).dt.days
        matched["quote_to_forecast_days"] = (matched["forecast_date"] - matched[datecol]).dt.days
        valid_a = matched["quote_to_create_days"].dropna()
        valid_b = matched["quote_to_forecast_days"].dropna()
        dist_a = dist(valid_a)
        dist_b = dist(valid_b)
        print(f"(a) quote_date -> createDate: {dist_a}")
        print(f"(b) quote_date -> forecast_date: {dist_b}")

        bins = [-np.inf, 0, 6, 14, 30, 60, 90, 180, np.inf]
        labels = ["<0 (quote after PO)", "0-6d", "7-14d", "15-30d", "31-60d", "61-90d", "91-180d", ">180d"]
        hist_a = pd.cut(valid_a, bins=bins, labels=labels).value_counts().sort_index()
        print(f"\nHistogram (a), {datecol}->createDate:")
        print(hist_a.to_string())

        matched[["itemcode", "quotation", datecol, "createDate", "forecast_date",
                  "quote_to_create_days", "quote_to_forecast_days"]].to_csv(
            os.path.join(SUMMARY_DIR, f"phaseJ2_explorerA_matched_rows_using_{datecol}.csv"), index=False)

        results_all[datecol] = {"n_matched": n_matched,
                                 "pct_matched_of_all": round(100*n_matched/len(sales), 2),
                                 "quote_to_create": dist_a, "quote_to_forecast": dist_b}

    pd.DataFrame(results_all).to_csv(os.path.join(SUMMARY_DIR, "phaseJ2_explorerA_datecol_comparison.csv"))
    return results_all


if __name__ == "__main__":
    main()
