"""Rule-based selection task, Part 3: implements three published
classification-to-model rule sets, plus an explicit non-intermittent layer
that none of the three cover.

Rule sets (verified against primary/authoritative sources before
implementation — see citations below, not invented thresholds):

1. SBC — Syntetos, Boylan & Croston (2005), "On the categorization of demand
   patterns", J Opl Res Soc 56:495-503. Thresholds ADI=1.32, CV2=0.49.
   VERIFIED via Kostenko & Hyndman (2006) reproducing SBC's own Figure 1
   (https://robjhyndman.com/papers/idcat.pdf): Croston for the SMOOTH
   quadrant only (ADI<1.32 AND CV2<0.49); SBA for Erratic, Lumpy and
   Intermittent (the other three quadrants). This is the opposite of an
   initial instruction in this task ("Croston for Erratic") — the user was
   shown the primary-source quote and confirmed to follow the verified
   source, which is what is implemented here.

2. KH — Kostenko & Hyndman (2006), "A note on the categorization of demand
   patterns", J Opl Res Soc 57:1256-1257. Replaces SBC's straight cutoff
   with the exact non-linear boundary they derive (their eq. 2):
     use SBA whenever v > [4p(2-p) - a(4-a) - p(p-1)(4-a)(2-a)] / [p(4-a)(2p-a)]
   where p=ADI, v=CV2, a=the fitted interval-smoothing parameter (see
   `estimate_interval_alpha` below). For p >= 4/3 the boundary is moot and
   SBA always applies (the corrected quadrant only extends to p=4/3, not
   1.32; v=0.5, not 0.49, at the p=1,alpha=0 corner — both confirmed
   directly from the paper's text, not assumed). Formula and implementation
   cross-checked against Nikolaos Kourentzes' own reference R implementation
   (`idclass.R`, https://github.com/trnnick/tsintermittent, type="KH"),
   which fits `a` the same way described here.

3. PK — Petropoulos & Kourentzes (2015) extension: identical Croston/SBA
   boundary to KH, but overrides to SES whenever ADI <= 1 (demand occurs in
   every period — not intermittent at all). Verified against the same
   reference implementation (`idclass.R`, type="PK": `use.ses <- p <= 1`).

Extended layer (added here, NOT from any of the three papers — none of them
model trend, and none address unreliable/insufficient history):
   - If the series has fewer than 24 months of history, OR its SBC
     classification changes across the first-12/first-24/full-history
     windows (Part 2), the characteristics cannot be trusted: assign Naive
     regardless of what the rule set would say.
   - Else, if the series is SBC-Smooth (ADI<1.32 AND CV2<0.49) — i.e.
     genuinely regular, non-intermittent demand — assign SES if no
     significant trend, or Holt if a significant trend is present (Part 1's
     trend test). This generalises Petropoulos & Kourentzes' own ADI<=1
     principle (use a smoothing method instead of Croston/SBA for regular
     demand) to the whole Smooth quadrant, and adds trend-awareness, which
     none of the three papers provide. This generalisation is OUR reasoned
     addition, not a literal reproduction of any paper's rule — reported as
     such throughout.
   - Otherwise (Erratic, Lumpy or Intermittent, with reliable characteristics):
     use the rule set's own Croston/SBA/SES output unchanged.

Every series maps to exactly one model under each rule set (no gaps): this
is enforced by construction (the Naive/Smooth/base-rule branches are
mutually exclusive and exhaustive).
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
from statsforecast.models import _intervals, _optimized_ses_forecast

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ (moved to src/investigations/)
from feature_analysis import WINDOWS, build_all_series, determine_complete_months
from series_features import ADI_THRESHOLD, CV2_THRESHOLD

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rule_based_selection")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "output", "data")
SUMMARY_DIR = os.path.join(PROJECT_ROOT, "output", "summary")

MIN_HISTORY_FOR_RELIABLE_CLASSIFICATION = 24
DEFAULT_ALPHA_FALLBACK = 0.1  # Croston's classic fixed value — used only when too few
                               # non-zero intervals exist to optimise alpha (< 3 intervals)


def estimate_interval_alpha(qty: np.ndarray) -> float:
    """Fitted smoothing parameter 'a' for the KH/PK formula: the optimised
    alpha of an SES fit to the inter-demand-interval series, matching the
    reference R implementation's `crost(x, type='sba')$weights[2]`
    (interval-component weight). Uses statsforecast's own golden-section
    optimiser (bounds 0.1-0.3, its documented default) on the same
    `_intervals` decomposition statsforecast uses internally for Croston.
    Falls back to the classic fixed alpha=0.1 when there are too few
    non-zero periods (<3 intervals) to fit anything.
    """
    yi = _intervals(qty.astype(float))
    if len(yi) < 3:
        return DEFAULT_ALPHA_FALLBACK
    try:
        _, _, alpha = _optimized_ses_forecast(yi)
        return float(alpha)
    except Exception as e:
        logger.warning("Alpha optimisation failed (%s) — falling back to alpha=%.1f", e, DEFAULT_ALPHA_FALLBACK)
        return DEFAULT_ALPHA_FALLBACK


def sbc_rule(adi: float, cv2: float) -> str:
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        return "Croston"
    return "SBA"


def kh_boundary(adi: float, cv2: float, alpha: float) -> float:
    p, v, a = adi, cv2, alpha
    return (4 * p * (2 - p) - a * (4 - a) - p * (p - 1) * (4 - a) * (2 - a)) / (p * (4 - a) * (2 * p - a))


def kh_rule(adi: float, cv2: float, alpha: float) -> str:
    if adi >= 4 / 3:
        return "SBA"
    boundary_v = kh_boundary(adi, cv2, alpha)
    return "SBA" if cv2 > boundary_v else "Croston"


def pk_rule(adi: float, cv2: float, alpha: float) -> str:
    if adi <= 1:
        return "SES"
    return kh_rule(adi, cv2, alpha)


def apply_extended_layer(base_model: str, adi: float, cv2: float, trend_significant: bool,
                          trend_direction: str, n_periods: int, classification_stable) -> tuple:
    """Returns (final_model, layer_applied) where layer_applied explains any
    override, or 'none' if the base rule's output was kept."""
    reliable = (n_periods >= MIN_HISTORY_FOR_RELIABLE_CLASSIFICATION) and (classification_stable == True)  # noqa: E712 (numpy.bool_ fails `is True`)
    if not reliable:
        reason = (f"history too short ({n_periods}<{MIN_HISTORY_FOR_RELIABLE_CLASSIFICATION} months)"
                   if n_periods < MIN_HISTORY_FOR_RELIABLE_CLASSIFICATION else "classification unstable across windows")
        return "Naive", f"insufficient/unstable characteristics ({reason}) -> Naive"
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        if trend_significant:
            return "Holt", "Smooth + significant trend -> Holt (extended layer, not from source papers)"
        return "SES", "Smooth, no significant trend -> SES (extended layer, generalises P&K's ADI<=1 principle)"
    return base_model, "none"


def select_models_for_series(qty: np.ndarray, months: list) -> dict:
    """Leakage-safe classification + rule application for an ARBITRARY prefix
    of a series (used as-is for Part 3's full-history report, and re-called
    on train-only / train+val-only prefixes for Parts 4 and 5, so that no
    future data — validation or test — ever informs the classification that
    picks the model). Returns a dict with ADI, CV2, alpha, trend, stability
    and the three rule sets' base and final (layered) model choices, or a
    'NoSale' record if the slice has no positive demand at all.
    """
    from series_features import compute_all_features

    if len(qty) == 0 or qty.sum() == 0:
        return {"classification": "NoSale", "ADI": None, "CV2": None, "alpha": None,
                "SBC_final": "Naive", "KH_final": "Naive", "PK_final": "Naive",
                "note": "no (or zero) sales in this window — Naive by default"}

    n = len(qty)
    full_feat = compute_all_features(qty, months)
    cls_by_window = {"full": full_feat["classification"]}
    for window_name, window_months in (("first_12", 12), ("first_24", 24)):
        if n >= window_months:
            cls_by_window[window_name] = compute_all_features(qty[:window_months], months[:window_months])["classification"]
    stable = len(set(cls_by_window.values())) == 1 if len(cls_by_window) == 3 else None

    adi, cv2 = full_feat["ADI"], full_feat["CV2"]
    if adi is None:
        return {"classification": full_feat["classification"], "ADI": None, "CV2": None, "alpha": None,
                "SBC_final": "Naive", "KH_final": "Naive", "PK_final": "Naive", "note": "NoSale"}
    alpha = estimate_interval_alpha(qty)

    sbc_base, kh_base, pk_base = sbc_rule(adi, cv2), kh_rule(adi, cv2, alpha), pk_rule(adi, cv2, alpha)
    sbc_final, _ = apply_extended_layer(sbc_base, adi, cv2, full_feat["trend_significant"], full_feat["trend_direction"], n, stable)
    kh_final, _ = apply_extended_layer(kh_base, adi, cv2, full_feat["trend_significant"], full_feat["trend_direction"], n, stable)
    pk_final, _ = apply_extended_layer(pk_base, adi, cv2, full_feat["trend_significant"], full_feat["trend_direction"], n, stable)

    return {
        "classification": full_feat["classification"], "ADI": adi, "CV2": cv2, "alpha": alpha,
        "n_periods": n, "stable": stable, "trend_direction": full_feat["trend_direction"],
        "SBC_base": sbc_base, "KH_base": kh_base, "PK_base": pk_base,
        "SBC_final": sbc_final, "KH_final": kh_final, "PK_final": pk_final,
    }


if __name__ == "__main__":
    raw = pd.read_csv(os.path.join(DATA_DIR, "raw_full_category_sales.csv"))
    monthly = pd.read_csv(os.path.join(DATA_DIR, "processed_full_category_sales_monthly.csv"))
    monthly = determine_complete_months(monthly, raw)
    scope = pd.read_csv(os.path.join(SUMMARY_DIR, "part1_category_scope_all_codes.csv"))
    series = build_all_series(monthly, scope)

    features_df = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part1_series_features_full_history.csv"))
    stability_df = pd.read_csv(os.path.join(SUMMARY_DIR, "rule_part2_stability_summary.csv"))

    rows = []
    for (level, key, cat), (qty, months) in series.items():
        feat_row = features_df[(features_df["level"] == level) & (features_df["key"] == key)]
        if feat_row.empty:
            continue
        feat_row = feat_row.iloc[0]
        if feat_row["classification"] == "NoSale" or pd.isna(feat_row["ADI"]):
            rows.append({"level": level, "key": key, "category": cat, "classification": "NoSale",
                         "ADI": None, "CV2": None, "alpha": None,
                         "SBC_base": "N/A", "KH_base": "N/A", "PK_base": "N/A",
                         "SBC_final": "N/A (no history)", "KH_final": "N/A (no history)", "PK_final": "N/A (no history)",
                         "layer_note": "no sales history — no model applies"})
            continue

        adi, cv2 = float(feat_row["ADI"]), float(feat_row["CV2"])
        n_periods = int(feat_row["n_periods"])
        trend_sig = bool(feat_row["trend_significant"])
        trend_dir = feat_row["trend_direction"]
        alpha = estimate_interval_alpha(qty)

        stab_row = stability_df[(stability_df["level"] == level) & (stability_df["key"] == key)]
        stable = stab_row.iloc[0]["stable"] if len(stab_row) else None
        if isinstance(stable, str):
            stable = stable == "True"

        sbc_base = sbc_rule(adi, cv2)
        kh_base = kh_rule(adi, cv2, alpha)
        pk_base = pk_rule(adi, cv2, alpha)

        sbc_final, sbc_note = apply_extended_layer(sbc_base, adi, cv2, trend_sig, trend_dir, n_periods, stable)
        kh_final, kh_note = apply_extended_layer(kh_base, adi, cv2, trend_sig, trend_dir, n_periods, stable)
        pk_final, pk_note = apply_extended_layer(pk_base, adi, cv2, trend_sig, trend_dir, n_periods, stable)

        rows.append({
            "level": level, "key": key, "category": cat, "classification": feat_row["classification"],
            "ADI": round(adi, 3), "CV2": round(cv2, 3), "alpha": round(alpha, 3),
            "SBC_base": sbc_base, "KH_base": kh_base, "PK_base": pk_base,
            "SBC_final": sbc_final, "KH_final": kh_final, "PK_final": pk_final,
            "layer_note": sbc_note if sbc_note != "none" else (kh_note if kh_note != "none" else "none"),
        })

    result_df = pd.DataFrame(rows)
    result_df.to_csv(os.path.join(SUMMARY_DIR, "rule_part3_model_assignments.csv"), index=False)

    print("\n" + "=" * 90)
    print("PART 3: RULE-BASED MODEL ASSIGNMENTS")
    print("=" * 90)
    for level in ["Category", "Type"]:
        sub = result_df[result_df["level"] == level]
        print(f"\n--- {level} level ---")
        print(sub[["key", "classification", "ADI", "CV2", "alpha", "SBC_final", "KH_final", "PK_final", "layer_note"]].to_string(index=False))

    print(f"\n--- Item level (128 series) ---")
    valid = result_df[result_df["level"] == "Item"]
    print(f"NoSale (no model applies): {(valid['classification']=='NoSale').sum()}")
    for rule in ["SBC_final", "KH_final", "PK_final"]:
        print(f"\n{rule} distribution (items with history):")
        print(valid[valid["classification"] != "NoSale"][rule].value_counts().to_string())

    print(f"\nExtended-layer overrides applied (any rule set, Category+Type+Item, excl. NoSale):")
    has_history = result_df[result_df["classification"] != "NoSale"]
    n_overridden = (has_history["layer_note"] != "none").sum()
    print(f"{n_overridden} of {len(has_history)} series had at least one override (insufficient/unstable -> Naive, "
          f"or Smooth -> SES/Holt) applied to at least one rule set's base recommendation.")

    print("\nWhere SBC and KH disagree on Croston vs SBA (base rule, before the extended layer):")
    disagree = has_history[has_history["SBC_base"] != has_history["KH_base"]]
    print(f"{len(disagree)} of {len(has_history)} series")
    if len(disagree) and len(disagree) <= 30:
        print(disagree[["level", "key", "ADI", "CV2", "alpha", "SBC_base", "KH_base"]].to_string(index=False))

    print("\nFull detail: output/summary/rule_part3_model_assignments.csv")
