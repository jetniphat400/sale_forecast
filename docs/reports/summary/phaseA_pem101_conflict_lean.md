# Phase A, A3 — PEM101 §23 conflict-item lean classification

Generated 2026-09-29. Classifies all 41 PEM101 METRICS.md §23 `conflict`-class items (from
`output/summary/task2b_part2_item_level.csv`, task 2b 2026-09-29 corrected version) as leaning
stock, leaning made-to-order, or undetermined. Dispatched as a read-only agent (Phase A, AGENTS.md
rule 10 — no tracked-file edits, no commits); Product Type/Description/Code from
`reference/pricelist.xlsx`'s visible sheets (PRICELIST RULE).

## Method and thresholds (stated before computing, per this task's instruction)

**Reused, not recomputed**: `total_stock` (on-hand now, any warehouse), `S2_share` (share of
delivered contracts tracing to a `cube_final` batch pre-dating `CtrDate`), `S3_median_days`
(median `ActualDelDate − CtrDate`, all-history) — all from `task2b_part2_item_level.csv`.

**Freshly computed this task** (one DB connection, succeeded, no retry needed): `Cube_CES` pulled
for these 41 item codes (`CtrDate, ForecastDelDate, ActualDelDate, ActualQty, Status`; 3,249 rows).
From `Status=='Actual'` rows only, all-history (no date window, matching S3's own convention so
notice and delivery-time are drawn from the same population — CONVENTIONS.md, "compare only like
with like"):
- **median notice** = median(`ForecastDelDate − CtrDate`) in days, negative/NaN dropped.
- **not_late (unit-weighted)** = Σ`ActualQty` where `ActualDelDate ≤ ForecastDelDate` ÷ Σ`ActualQty`
  (METRICS.md §19). Reported per item as descriptive context only — not part of the classification
  rule itself (the task's classification sentence doesn't name it as a criterion).

**Classification rule** (majority vote over up to 4 binary signals):
- *Stock-leaning signals*: notice ≤ day_th; delivery (`S3_median_days`) ≤ day_th; on-hand stock
  > 0; batch-share ≥ batch_th (only when `S2` computable).
- *MTO-leaning signals*: notice ≥ delivery; on-hand stock == 0; batch-share < batch_th (only when
  `S2` computable).
- **Leaning stock**: stock-signal count ≥ 2 and exceeds the MTO count. **Leaning made-to-order**:
  MTO-signal count ≥ 2 and exceeds the stock count. **Undetermined**: tied, or too few signals
  available either way (this bucket mixes genuine 2-vs-2 ties with items that simply have few
  signals present, e.g. no stock plus `S2` not computable — not distinguished further, per the
  task's own wording).
- Primary thresholds: `day_th=14` (matching §23's own S3 cutoff), `batch_th=0.50` (matching §23's
  own S2 cutoff). Neighbouring values tested: day_th ∈ {7,14,21}, batch_th ∈ {0.4,0.5,0.6}.

## Counts at each threshold (level V1, single computation, pending A6 Validator spot-check)

| day_th | leaning stock | leaning MTO | undetermined |
|---|---|---|---|
| 7 | 6 | 14 | 21 |
| **14 (primary)** | **10** | **11** | **20** |
| 21 | 12 | 9 | 20 |

`batch_th` (0.4/0.5/0.6) changes **nothing** at any `day_th` — every one of these 41 items'
`S2_share` is either exactly 0, not computable, or a single non-zero case (0.038) that never
straddles 0.4–0.6. The batch-traceability signal is effectively binary (present/absent) for this
item set, not threshold-sensitive.

## Full per-item table (41 items, sorted by Type then Code)

| Code | Type | Description | Label | Share% | Median notice (d) | Median PO-to-delivery (d) | not_late% | On-hand | Batch pre-PO share | Class | pts(stock/mto) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FC-A-27-00203 | Fuse Holder | 22kV 12kA 200A | MTO | 75.0% | 21.5 | 11.5 | 82.7 | 1428 | - | leaning stock | 2/1 |
| FC-A-38-00202 | Fuse Holder | 38kV New 100A | mixed | 51.6% | 6.5 | 4.5 | 75.0 | 5239 | - | leaning stock | 3/1 |
| EEE-F-FC-1040011002P | High Voltage Distribution Fuse Cutout | 22kV 12kA 100Amp HP | MTS | 100.0% | 7.5 | 18.0 | 14.3 | 0 | - | undetermined | 1/1 |
| EEE-F-FC-1040011100NP | High Voltage Distribution Fuse Cutout | 33kV 8kA 100Amp HP New | MTO | 62.2% | 7.0 | 7.0 | 94.6 | 25 | - | leaning stock | 3/1 |
| EEE-F-FL-5920-353-04100 | High Voltage Distribution Fuse link | 22kV 40Amp (MEA) | mixed | 50.0% | 90.0 | 90.0 | 88.5 | 0 | - | leaning made-to-order | 0/2 |
| FD-F-01-0001 | LED Flood light | 150 Walt Model TGD18-B | MTS | 84.2% | 137.5 | 148.5 | 66.0 | 0 | - | undetermined | 0/1 |
| FD-F-01-0002 | LED Flood light | 350 Walt Model TGD18-D | MTS | 69.6% | 120.5 | 134.0 | 49.3 | 0 | - | undetermined | 0/1 |
| ST-F-01-0005 | LED Street light | 20 Watt Model 435 | mixed | 54.2% | 5.0 | 4.0 | 95.8 | 0 | - | undetermined | 2/2 |
| ST-F-01-0027 | LED Street light | 35 Watt Model FFLDs | mixed | 56.2% | 5.5 | 5.5 | 91.0 | 0 | - | undetermined | 2/2 |
| ST-F-12-0006 | LED Street light | 60 Watt 5570 Straight Stepped Pole 4 m | MTS | 72.2% | 146.0 | 154.0 | 48.8 | 0 | - | undetermined | 0/1 |
| ST-F-12-0007 | LED Street light | 60 Watt 5570 Straight Stepped Pole 6 m | MTS | 62.5% | 150.0 | 154.0 | 45.2 | 4 | - | undetermined | 1/0 |
| CA-F-99-010201 | Low Voltage Capacitor | Cap-3E 5kVAR 400V | mixed | 57.3% | 7.5 | 8.0 | 64.7 | 318 | 0% | leaning stock | 3/1 |
| CA-F-99-010202 | Low Voltage Capacitor | Cap-3E 10kVAR 400V | mixed | 55.7% | 2.0 | 2.0 | 67.8 | 33 | 0% | leaning stock | 3/2 |
| CA-F-99-010203 | Low Voltage Capacitor | Cap-3E 15kVAR 400V | mixed | 51.2% | 2.0 | 2.0 | 74.0 | 45 | 0% | leaning stock | 3/2 |
| CA-F-99-010205 | Low Voltage Capacitor | Cap-3E 25kVAR 400V | mixed | 55.4% | 2.0 | 2.0 | 71.4 | 44 | 0% | leaning stock | 3/2 |
| CA-F-99-010210 | Low Voltage Capacitor | Cap-3E 60kVAR 400V | mixed | 50.0% | 5.0 | 5.0 | 100.0 | 0 | - | undetermined | 2/2 |
| CA-F-99-010211 | Low Voltage Capacitor | Cap-3E 75kVAR 400V | mixed | 59.7% | 1.0 | 1.0 | 75.6 | 19 | 0% | leaning stock | 3/2 |
| CA-F-99-010212 | Low Voltage Capacitor | Cap-3E 40kVAR 400V | mixed | 58.3% | 35.0 | 30.0 | 67.7 | 0 | 0% | leaning made-to-order | 0/3 |
| CA-F-99-020101 | Medium Voltage Capacitor | MV Cap 1Ph 12.7kV 100kVAR | mixed | 53.7% | 31.5 | 31.5 | 93.9 | 2 | 0% | leaning made-to-order | 1/2 |
| CA-F-99-020104 | Medium Voltage Capacitor | MV Cap 1Ph 12.7kV 50kVAR | mixed | 53.1% | 26.5 | 22.0 | 71.0 | 17 | 0% | leaning made-to-order | 1/2 |
| HS-F-99-0061 | Medium Voltage Surge Arrester | 6kV 5kA type LAZ-P06 | mixed | 52.6% | 11.0 | 12.0 | 77.4 | 0 | - | leaning stock | 2/1 |
| HS-F-99-0091 | Medium Voltage Surge Arrester | 9kV 5kA type LAZ-P09 | mixed | 57.1% | 12.0 | 11.0 | 98.3 | 0 | - | undetermined | 2/2 |
| HS-F-99-0151 | Medium Voltage Surge Arrester | 15kV 5kA type LAZ-P15 | MTS | 100.0% | 6.0 | 6.0 | 100.0 | 0 | - | undetermined | 2/2 |
| HS-F-99-0215 | Medium Voltage Surge Arrester | 21kV 5kA type LAZ-P21 Transformer | MTS | 61.1% | 30.0 | 31.0 | 89.7 | 3 | - | undetermined | 1/0 |
| HS-F-99-0301H22 | Medium Voltage Surge Arrester | 30kV 5kA type LAZ-P30 HP | mixed | 53.2% | 18.0 | 14.0 | 97.8 | 0 | 4% | leaning made-to-order | 1/3 |
| HS-F-99-0301H33 | Medium Voltage Surge Arrester | 30kV 5kA type LAZ-P30 Extra HP | mixed | 58.3% | 7.0 | 7.0 | 100.0 | 0 | - | undetermined | 2/2 |
| HS-F-99-0331 | Medium Voltage Surge Arrester | 33kV 5kA type LAZ-P33 | mixed | 57.8% | 25.0 | 18.5 | 88.8 | 0 | 0% | leaning made-to-order | 0/3 |
| HS-F-99-0361 | Medium Voltage Surge Arrester | 36kV 5kA type LAZ-P36 | MTS | 62.5% | 19.0 | 19.0 | 83.9 | 0 | - | leaning made-to-order | 0/2 |
| HS-F-99-1031 | Medium Voltage Surge Arrester | 3kV 10kA Cl.1 type PAZ-P03-1 | mixed | 56.5% | 7.0 | 7.0 | 100.0 | 0 | - | undetermined | 2/2 |
| HS-F-99-1061 | Medium Voltage Surge Arrester | 6kV 10kA Cl.1 type PAZ-P06-1 | mixed | 55.6% | 10.0 | 11.0 | 92.4 | 0 | - | leaning stock | 2/1 |
| HS-F-99-1121 | Medium Voltage Surge Arrester | 12kV 10kA Cl.1 type PAZ-P12-1 | MTS | 78.3% | 14.5 | 14.5 | 62.6 | 0 | - | leaning made-to-order | 0/2 |
| HS-F-99-1301H33 | Medium Voltage Surge Arrester | 30kV 10kA Cl.1 type PAZ-P30-1 Extra HP | mixed | 53.3% | 7.0 | 7.0 | 99.1 | 0 | - | undetermined | 2/2 |
| HS-F-99-2061N | Medium Voltage Surge Arrester | 6kV 10kA Cl.2 type SA206 | MTS | 100.0% | 11.0 | 10.0 | 73.3 | 0 | - | undetermined | 2/2 |
| HS-F-99-2301N | Medium Voltage Surge Arrester | 30kV 10kA Cl.2 type SA230 Private | MTS | 76.8% | 5.5 | 4.0 | 92.6 | 0 | - | undetermined | 2/2 |
| HS-F-99-3061 | Medium Voltage Surge Arrester | 6kV 10kA Cl.3 type PAZ-P06-3 | MTS | 100.0% | 19.0 | 19.5 | 85.7 | 0 | - | undetermined | 0/1 |
| HS-F-99-3211 | Medium Voltage Surge Arrester | 21kV 10kA Cl.3 type PAZ-P21-3 | MTS | 78.9% | 106.0 | 106.0 | 84.9 | 0 | - | leaning made-to-order | 0/2 |
| HS-F-99-3301 | Medium Voltage Surge Arrester | 30kV 10kA Cl.3 type PAZ-P30-3 | MTS | 97.0% | 135.0 | 134.0 | 65.4 | 0 | - | leaning made-to-order | 0/2 |
| HS-F-99-3303 | Medium Voltage Surge Arrester | 30kV 10kA Cl.2 type PAZ-P30-2 HP | MTS | 86.5% | 12.0 | 12.0 | 96.2 | 0 | - | undetermined | 2/2 |
| IS-F-99-0245CE0 | Suspension Insulator | 24kV with 1 Clevis no Shackle type PS-R-061-CE-0 | MTS | 99.3% | 46.0 | 41.0 | 82.8 | 0 | - | leaning made-to-order | 0/2 |
| IS-F-99-0245CE1 | Suspension Insulator | 24kV with 1 Clevis 1 Shackle type PS-R-061-CE-1 | MTS | 82.4% | 42.0 | 49.0 | 49.5 | 0 | - | undetermined | 0/1 |
| IS-F-99-0245EE0 | Suspension Insulator | 24kV with 2 Eye fitting type PS-R-061-EE-0 | MTS | 100.0% | 69.0 | 72.0 | 22.5 | 0 | - | undetermined | 0/1 |

## Undetermined items — full list for business confirmation (20 items)

| Product Type | Product Description | Product Code |
|---|---|---|
| High Voltage Distribution Fuse Cutout | 22kV 12kA 100Amp HP | EEE-F-FC-1040011002P |
| LED Flood light | 150 Walt Model TGD18-B | FD-F-01-0001 |
| LED Flood light | 350 Walt Model TGD18-D | FD-F-01-0002 |
| LED Street light | 20 Watt Model 435 | ST-F-01-0005 |
| LED Street light | 35 Watt Model FFLDs | ST-F-01-0027 |
| LED Street light | 60 Watt 5570 Straight Stepped Pole 4 m | ST-F-12-0006 |
| LED Street light | 60 Watt 5570 Straight Stepped Pole 6 m | ST-F-12-0007 |
| Low Voltage Capacitor | Cap-3E 60kVAR 400V | CA-F-99-010210 |
| Medium Voltage Surge Arrester | 9kV 5kA type LAZ-P09 | HS-F-99-0091 |
| Medium Voltage Surge Arrester | 15kV 5kA type LAZ-P15 | HS-F-99-0151 |
| Medium Voltage Surge Arrester | 21kV 5kA type LAZ-P21 Transformer | HS-F-99-0215 |
| Medium Voltage Surge Arrester | 30kV 5kA type LAZ-P30 Extra HP | HS-F-99-0301H33 |
| Medium Voltage Surge Arrester | 3kV 10kA Cl.1 type PAZ-P03-1 | HS-F-99-1031 |
| Medium Voltage Surge Arrester | 30kV 10kA Cl.1 type PAZ-P30-1 Extra HP | HS-F-99-1301H33 |
| Medium Voltage Surge Arrester | 6kV 10kA Cl.2 type SA206 | HS-F-99-2061N |
| Medium Voltage Surge Arrester | 30kV 10kA Cl.2 type SA230 Private | HS-F-99-2301N |
| Medium Voltage Surge Arrester | 6kV 10kA Cl.3 type PAZ-P06-3 | HS-F-99-3061 |
| Medium Voltage Surge Arrester | 30kV 10kA Cl.2 type PAZ-P30-2 HP | HS-F-99-3303 |
| Suspension Insulator | 24kV with 1 Clevis 1 Shackle type PS-R-061-CE-1 | IS-F-99-0245CE1 |
| Suspension Insulator | 24kV with 2 Eye fitting type PS-R-061-EE-0 | IS-F-99-0245EE0 |

## Scope note (per AGENTS.md rule 3 — reported, not pursued further this task)

1. Why `S2` (batch pre-PO share) is almost never computable or almost always 0 for this whole
   conflict set — possibly a real signal (these genuinely aren't batch-produced-ahead items) or a
   data-coverage gap in `cube_final`. Not investigated further, outside this task's directive.
2. Two items (`EEE-F-FC-1040011002P` at 14.3% not_late and `IS-F-99-0245EE0` at 22.5%) show very
   low `not_late` alongside near-zero notice/large delivery mismatch — they look like they may be
   systematically mis-scheduled rather than simply ambiguous. Flagged for attention, not resolved
   here since `not_late` is not part of this task's classification criteria.

## Validator cross-check (A6, dispatched as a fresh agent, no shared context with A3)

Read none of this report; independently classified 5 items chosen at random (seed 20260929):
`EEE-F-FC-1040011002P`, `HS-F-99-0151`, `HS-F-99-1031`, `HS-F-99-2301N`, `HS-F-99-3303`. Used its
own operationalization, stated before classifying: score = count of {on-hand stock>0 now;
S2_share≥50% (only if computable); median realized PO→delivery≤14 days} that hold; a `mixed`
label routes straight to undetermined; otherwise `MTS` with score≥2 → leaning stock, `MTO`/`ETO`
with score≤1 → leaning made-to-order, any label/signal disagreement → undetermined. Fresh
`Cube_Inventory_Exact` pull confirmed all 5 items have 0 on-hand stock across every warehouse
(reconfirms this report's S1=False, not just re-read). Fresh `Cube_CES`↔`cube_final` join
(one connection attempt, succeeded) for S2.

| Item | Target (A3) | Validator | Verdict |
|---|---|---|---|
| EEE-F-FC-1040011002P | undetermined | undetermined | **MATCH** |
| HS-F-99-0151 | undetermined | undetermined | **MATCH** |
| HS-F-99-1031 | undetermined | undetermined | **MATCH** |
| HS-F-99-2301N | undetermined | undetermined | **MATCH** |
| HS-F-99-3303 | undetermined | undetermined | **MATCH** |

**All 5 MATCH** — same conclusion, independently derived via a different operationalization
(majority-vote-of-3-signals vs. this report's majority-vote-of-4-signals). Level **V2** for these
5 items' classification (independent recomputation, different session, different method,
identical conclusion).

**Sub-finding, minor discrepancy in an underlying count (does not change the classification):**
the Validator's fresh `cube_final` join found 1 linked contract for `HS-F-99-2301N`
(`CTR-2024-06786`, `OLMJobCode=LB240227`, `cube_final.final_date` 2024-11-26, one day after
`CtrDate` 2024-11-25 — so still not pre-existing) where this report's source file
(`task2b_part2_item_level.csv`) records `n_cube_final_linked=0`. This does not affect S2 (still
0% pre-existing either way, far below the 50% threshold) or the classification, but is a genuine,
reportable discrepancy in the underlying linked-contract count, flagged per AGENTS.md rule 4
(report contradictions explicitly, never overwrite silently) rather than smoothed over.
