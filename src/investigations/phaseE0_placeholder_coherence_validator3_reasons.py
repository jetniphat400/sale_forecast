"""Phase E0, Validator 3 (E0.3), part 2: per-item reason category + predecessor/analogue check
for all 82 placeholder items. See phaseE0_placeholder_coherence_validator3.py for part 1
(Type-total additive vs. carve-out arithmetic) and
output/summary/phaseE0_validator3_placeholder_coherence_report.md for the full write-up.

`reason_category` is copied VERBATIM from the existing, already-done characterisation
(output/summary/phaseC_89items_characterization.csv `trace_pattern` column,
phaseC_89items_characterization_report.md) -- not re-derived here.

`predecessor_or_analogue_found` / `predecessor_code_if_any` is a NEW check for this task: for
each of the 82 items, does the pricelist (reference/pricelist.xlsx) contain another code with
Omni-Channel history that is a closer analogue than the item's own flat Type mean/median --
e.g. the same product sub-family (same fitting type, same "with/without VT" option, same
accuracy-class notation, same special-purpose sub-line) differing only in the ONE dimension the
no-history item itself varies on (kVA/kVAR/A/kV rating, a customer-type label, a pole length)?

Method:
  - The 37 `3 Phase Distribution Transformer` (PEM103) items are resolved PROGRAMMATICALLY
    (pem103_family_predecessors in the sibling script) -- description-pattern family key +
    nearest-kVA-rating real sibling with history. Directly reproducible, not manual judgement.
  - The other 45 items are resolved MANUALLY, one at a time, by reading
    reference/pricelist.xlsx's `description` column directly (via
    src/pricelist_reader.load_visible_product_rows) and cross-checking the candidate code's
    history status against output/summary/phaseC_step2_scope_335items.csv (has-history scope)
    -- every assignment below is individually cited with the specific pattern matched. Where no
    narrower-than-Type-average analogue could be identified, `found="no"` is used, not
    "cannot_determine" (a definite negative was reached for every item -- no item was left
    unchecked in this task).

Confidence: the pricelist facts themselves (which codes exist, their descriptions, which have
history) are VERIFIED FROM DATA (direct pricelist_reader.py read + phaseC_step2_scope_335items.csv
lookup). Whether a given analogue would actually forecast BETTER than the current Rule A/B Type
mean/median is a modelling judgement outside a Validator's role (AGENTS.md) and is explicitly
NOT claimed here -- only that a narrower candidate basis exists in the pricelist and is worth a
Modeler's attention, labelled SUPPORTED HYPOTHESIS, not fact.
"""
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pricelist_reader import load_visible_product_rows  # noqa: E402
from phaseE0_placeholder_coherence_validator3 import pem103_family_predecessors  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY = os.path.join(PROJECT_ROOT, "output", "summary")

# Manual, individually-verified assignments for the 45 non-PEM103 items. Every candidate code
# was checked directly against reference/pricelist.xlsx's `description` column (for the spec
# match) and output/summary/phaseC_step2_scope_335items.csv (to confirm it DOES have history).
MANUAL = {
    "CA-F-99-010108": ("yes", "CA-F-99-010104", "Same Cap-1E (single-phase) sub-family, nearest kVAR rating with history"),
    "CA-F-99-010303": ("yes", "CA-F-99-010306", "Same Cap-3E '415V (MEA)' sub-family, nearest kVAR rating with history"),
    "CA-F-99-010304": ("yes", "CA-F-99-010306", "Same Cap-3E '415V (MEA)' sub-family, nearest kVAR rating with history"),
    "CA-F-99-020301": ("no", "", "All 3 history-bearing siblings are a different voltage tier (12.7kV vs this item's 19kV); no closer analogue than the Type median already used"),
    "IS-F-99-0155CE0": ("yes", "IS-F-99-0245CE0", "Same fitting type (CE0), only kV tier differs (15kV vs 24kV, which has history)"),
    "IS-F-99-0155CE1": ("yes", "IS-F-99-0245CE1", "Same fitting type (CE1), only kV tier differs (15kV vs 24kV, which has history)"),
    "IS-F-99-0155EE0": ("yes", "IS-F-99-0245EE0", "Same fitting type (EE0), only kV tier differs (15kV vs 24kV, which has history)"),
    "IS-F-99-0365CE0": ("yes", "IS-F-99-0245CE0", "Same fitting type (CE0), only kV tier differs (36kV vs 24kV, which has history)"),
    "IS-F-99-0365CE1": ("yes", "IS-F-99-0245CE1", "Same fitting type (CE1), only kV tier differs (36kV vs 24kV, which has history)"),
    "IS-F-99-0365EE0": ("yes", "IS-F-99-0245EE0", "Same fitting type (EE0), only kV tier differs (36kV vs 24kV, which has history)"),
    "ST-F-12-0009": ("yes", "ST-F-12-0006", "Same '60 Watt 5570 Straight Stepped Pole' product line, nearest pole length (4m) with history"),
    "LB-F-99-G2261207-01": ("yes", "LB-F-99-G2261207", "Same Option 7, 22kV 630A switch -- only VT presence differs; the 'with VT' code has history"),
    "LB-F-99-G3341004-01": ("yes", "LB-F-99-G3341004", "Same Option 4, 33kV 400A switch -- only VT presence differs; the 'with VT' code has history"),
    "LB-F-99-G3341005-01": ("yes", "LB-F-99-G3341005", "Same Option 5, 33kV 400A switch -- only VT presence differs; the 'with VT' code has history"),
    "LB-F-99-G3341007-01": ("yes", "LB-F-99-G3341007", "Same Option 7, 33kV 400A switch -- only VT presence differs; the 'with VT' code has history"),
    "SL-F-99-S2461604": ("yes", "SL-F-99-S2461604-01", "Same Option 4, 24kV 600A switch -- only VT presence differs; the 'without VT' code has history"),
    "SL-F-99-S2461605-01": ("yes", "SL-F-99-S2461605", "Same Option 5, 24kV 600A switch -- only VT presence differs; the 'with VT' code has history"),
    "SR-F-99-2261203-01": ("yes", "SR-F-99-2261203", "Same 22kV 630A recloser -- only VT presence differs; the 'with VT' code has history (NOTE: already the Type's sole history-bearing member -- n_siblings=1, 100% share -- so this is already the exact basis of the current placeholder value, not an untapped extra signal)"),
    "SR-F-99-3381603": ("yes", "SR-F-99-2261203", "WEAKER, CROSS-TYPE CONFIDENCE: same 'Solid Recloser (CVD Type)' product family as the 22kV Recloser Type's history-bearing item -- only the voltage class differs (33kV vs 22kV). This Type has ZERO siblings with history (Rule C) so this is cross-Type, not same-Type, evidence"),
    "SR-F-99-3381603-01": ("yes", "SR-F-99-2261203", "WEAKER, CROSS-TYPE CONFIDENCE: same reasoning as SR-F-99-3381603 (its own in-Type sibling SR-F-99-2261203-01 also has no history)"),
    "02-05-R-0001": ("no", "", "The only pricelist code of this Type (FRTU) -- no sibling of any kind, same-Type or cross-Type, was identified as a spec analogue in this task's pricelist scan"),
    "RS-F-99-090xxx": ("yes", "RS-F-99-090039", "Same 'LExM-175' sub-line (vs. the Type's other sub-lines LExM-130/155), nearest current rating (1500A) with history"),
    "RS-F-99-040003": ("yes", "RS-F-99-040004", "Same '[0.6B0.1,0.2&0.5]' multi-class metering-CT notation sub-family (distinct from the Type's other 13 protection-class 'Cl.0.5Fs10' siblings), nearest current rating with history"),
    "VT-F-99-010203.": ("yes", "VT-F-99-010203", "Identical VOL-24 22000/110V 50VA Cl.0.5 rating -- only the Private/PEA-Regional customer-type label differs (same code apart from a trailing period); the 'Private' code has history"),
    "VT-F-99-010303.": ("yes", "VT-F-99-010303", "Identical VOL-36 33000/110V 50VA Cl.0.5 rating -- only the Private/PEA-Regional customer-type label differs (same code apart from a trailing period); the 'PEA Regional' code has history"),
    "VT-F-99-010306": ("yes", "VT-F-99-010205", "Same special-purpose 'For LBS Op.4, 500VA Cl.3' sub-line -- only voltage tier differs (VOL-36 vs VOL-24, which has history)"),
    "VT-F-99-01802": ("yes", "VT-F-99-010701", "Same special-purpose 'For LBS Op.5&6, 500VA Cl.3' sub-line -- only voltage tier differs (VOG-362 vs VOG-242, which has history)"),
    "CT-F-99-020533": ("yes", "CT-F-99-020522", "Same COL-24 dual-ratio '(2 Core)' sub-family (distinct from the Type's plain single-ratio siblings), nearest current rating with history"),
    "CT-F-99-020721": ("yes", "CT-F-99-020722", "Same COL-36 dual-ratio '(2 Core)' sub-family, nearest current rating with history"),
    "CT-F-99-020729": ("yes", "CT-F-99-020730", "Same COL-36 dual-ratio '(2 Core)' sub-family, nearest current rating with history"),
    "CT-F-99-020731": ("yes", "CT-F-99-020730", "Same COL-36 dual-ratio '(2 Core)' sub-family, nearest current rating with history"),
}
for _c in ["RS-F-99-050320", "RS-F-99-05xxxx-1", "RS-F-99-050036", "RS-F-99-050235", "RS-F-99-050074",
           "RS-F-99-050050", "RS-F-99-050207", "RS-F-99-050276", "RS-F-99-050101", "RS-F-99-050117"]:
    MANUAL[_c] = ("no", "", "Single sub-family (plain 'CDB X/5A'); only 2 siblings in the whole Type have history (RS-F-99-050128, RS-F-99-050023) and both already feed the Type mean/median directly -- no narrower sub-family split exists in the pricelist")
for _c in ["RS-F-99-010130", "RS-F-99-010018", "RS-F-99-01xxxx-3", "RS-F-99-01xxxx-4"]:
    MANUAL[_c] = ("no", "", "Single sub-family (plain 'CEL-24 X/5A'); all 7 history-bearing siblings (10-300A) already feed the Type mean directly and no narrower sub-family split exists -- these 4 items sit well above that range (400-2000A), a data-quality caveat, not a predecessor-code finding")

assert len(MANUAL) == 45, len(MANUAL)


def build() -> pd.DataFrame:
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    pa82 = cfg["placeholder_item_assignments_82"]
    char = pd.read_csv(os.path.join(SUMMARY, "phaseC_89items_characterization.csv"))
    assign = pd.read_csv(os.path.join(SUMMARY, "phaseC_placeholder_assignment_82items.csv"))
    pricelist = load_visible_product_rows(os.path.join(PROJECT_ROOT, cfg["pricelist_path"]))
    pem103_pred = pem103_family_predecessors(pricelist, pa82)

    char82 = char[char["code"].isin(pa82.keys())]
    div_map = dict(zip(assign["code"], assign["division"]))

    rows = []
    for _, r in char82.iterrows():
        code = r["code"]
        if code in pem103_pred:
            pc = pem103_pred[code]
            found = "yes" if pc else "cannot_determine"
            note = (f"Same product-spec family (loss-class + voltage tier), nearest kVA rating "
                    f"with history: {pc}") if pc else ""
        else:
            found, pc, note = MANUAL[code]
        rows.append({
            "itemcode": code, "division": div_map[code], "type": r["type"],
            "reason_category": r["trace_pattern"],
            "predecessor_or_analogue_found": found,
            "predecessor_code_if_any": pc if pc else "",
            "predecessor_rationale": note,
        })
    out = pd.DataFrame(rows)
    assert len(out) == 82 and out["itemcode"].nunique() == 82
    return out


if __name__ == "__main__":
    out = build()
    out.to_csv(os.path.join(SUMMARY, "phaseE0_validator3_82item_reasons.csv"), index=False)
    print(out["predecessor_or_analogue_found"].value_counts())
    print(f"\nWrote {len(out)} rows to phaseE0_validator3_82item_reasons.csv")
