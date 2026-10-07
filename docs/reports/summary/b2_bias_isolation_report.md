# Phase B, B2 — Re-measure bias with EEE-F-FC-1040010002 separated

Single Modeler task, continuing directly from B1. Script: `src/bias_item_isolation.py`. Uses both
date keyings (B1's re-keyed series) for completeness. No model choice written to `config.yaml`.

## Method

- **Item level**: "with" = mean bias across all 113 items (test set, Combination + 6 base
  models); "without" = mean across the other 112 (this item's own row simply excluded from the
  average — item-level series are not summed, so exclusion here means removing it from the
  cross-item mean, not rebuilding a series).
- **Type level** (`High Voltage Distribution Fuse Cutout`, the item's own Type, 10 items): rebuilt
  the Type's aggregate monthly series with and without this item's contribution, and re-ran the
  identical train/val/test backtest on both.
- **Category level** (`Fuse`, 6 Types incl. the item's own): same rebuild-and-rerun, at Category
  scope. **Control check**: `Surge Arrester` category (untouched by this item, since it belongs
  to Fuse) is also scored, as a sanity check that the method isn't introducing spurious drift.

## Result: the answer is level-dependent — reported exactly, not averaged into one verdict

**At Type level (`High Voltage Distribution Fuse Cutout`), excluding this one item removes
80-92% of the Combination bias magnitude, at BOTH keyings:**

| Date key | Bias with item | Bias without item | % removed |
|---|---|---|---|
| createDate | -2,198.5 | -212.0 | **90.4%** |
| forecastDate | -1,393.7 | -177.1 | **87.3%** |

**HIGH confidence: at this Type's level, the earlier bias measurement was SUBSTANTIALLY AN
ARTIFACT of this one item** — consistent with Phase A's hypothesis and with this item dominating
its Type at ~48-60% of value. Every one of the 6 base models shows the same pattern (77-124%
removed, full detail in `b2_bias_comparison.csv`).

**At Category level (`Fuse`, which also contains HRC fuse, Fuse Holder, Fuse link, Low Tension
Fuse Switch, Low Voltage Fuse Switch Disconnectors — 5 other Types untouched by this exclusion),
the bias barely moves:**

| Date key | Bias with item | Bias without item | % removed |
|---|---|---|---|
| createDate | -21,054.6 | -19,068.0 | 9.4% |
| forecastDate | -25,606.2 | -24,389.7 | 4.8% |

**HIGH confidence: at Category level, the negative bias PERSISTS beyond this one item — it is a
genuine, broad property of the wider Fuse category demand, not explained by one item.** Control
check: `Surge Arrester`'s own bias (-3,223.0 createDate / -2,286.5 forecastDate) is reported for
reference and is unaffected by construction (it never contained this item).

**At Item level (mean across all items), excluding it moves the mean only slightly** (Combination:
-216.1→-200.3 createDate, -6.5% to -249.0→-240.4 forecastDate, -3.5%) — expected, since one item's
extreme value carries limited weight in an equal-weighted mean of 113 items.

## What this implies for safety stock

- **Do not use the Category-level or Item-level (cross-item-mean) bias figures as if they were
  driven by this one item — they are not.** The persisting Category-level bias (-19,068 to
  -24,390 units/month even with the item excluded) is a real, general under-forecasting property
  of the rest of the Fuse category and should still inform safety stock sizing at that level.
- **Do treat the Type-level bias figure for `High Voltage Distribution Fuse Cutout` with caution**
  — 80-92% of it is this one item's collapse-recovery cycle landing in the test window, not a
  stable property of the other 9 items in that Type. Sizing safety stock for that Type from the
  unadjusted figure would substantially overstate the general buffer the other 9 items need.
- **For the item itself**, its own individual bias (below) is real and large — it needs
  item-specific handling (e.g. a longer/more representative evaluation window, or business input
  on whether the 2025 collapse is expected to recur), not a Type-level blanket policy.

## Focus items individually (Combination, test set)

| Date key | Item | MAE | Bias |
|---|---|---|---|
| createDate | EEE-F-FC-1040010002 | 1970.8 | -1970.8 |
| createDate | HS-F-99-02110 | 611.6 | -562.9 |
| createDate | HS-F-99-0213 | 272.5 | -222.7 |
| forecastDate | EEE-F-FC-1040010002 | 1206.1 | -1206.1 |
| forecastDate | HS-F-99-02110 | 503.8 | -496.9 |
| forecastDate | HS-F-99-0213 | 228.5 | -180.5 |

The other two focus items (`HS-F-99-02110`, `HS-F-99-0213`, both Lumpy, mid-rank in Medium
Voltage Surge Arrester) are NOT part of the excluded item's Type or Category test above (they sit
in Medium Voltage Surge Arrester / Surge Arrester) — their own bias is reported for completeness
but is untouched by this specific exclusion; both carry a real, substantial under-forecasting
bias of their own that is not explained by `EEE-F-FC-1040010002` at all.

## Confidence levels

- Type-level bias is substantially (80-92%) an artifact of this one item: **HIGH** (direct
  recomputation, consistent across both keyings and all 7 models, plus a working control check).
- Category-level bias persists as a genuine, broad property: **HIGH** (same evidence basis).
- Item-level (cross-item mean) bias is only marginally affected: **HIGH**.
- Practical safety-stock implication (use Type-level figure cautiously, Category-level figure as-is):
  **MODERATE** — the direction is clear, but this report does not itself design a safety-stock
  policy, only characterises the bias.

## Unresolved

- Whether the Type's *other* 9 items (excluding this one) have their own, unrelated bias problem
  worth investigating individually — not tested here (only the Type-level aggregate "without"
  bias was examined, not each of the 9 items separately).
- Root cause of `EEE-F-FC-1040010002`'s own collapse-recovery cycle remains unresolved (carried
  over from Phase A — needs stock/supply/contract data this project cannot see).
