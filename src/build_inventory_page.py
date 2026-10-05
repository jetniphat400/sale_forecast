"""Builds forecast/inventory.html: an interactive Min/Max scenario page with a DIVISION SELECTOR
(PEM101, PEM103, PEM107 -- Phase E2 Part 3, 2026-09-22), Tier A controls recomputed client-side
in JavaScript from the embedded raw data (actual history + forecast) the Python side used -- the
JS recompute functions mirror METRICS.md's formulas exactly (percentile-based safety stock, day/
month prorating at 30.44 days/month) so tests/test_inventory_parity.py can assert Python and JS
agree, at the default scenario and at one non-default control setting, FOR EACH division.

CI101/PEM102/PEM104 appear in the division selector as disabled options with the reason they are
excluded (too few stocked items for a confident sellable-warehouse set) -- never silently omitted.

Raises InventoryPageError (naming exactly what is missing) rather than rendering a blank page,
same fail-loudly convention as src/build_report.py.
"""
import html
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_inventory_page_data import build_data
import reader_values as rv
from manual_notes import render_notes_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_inventory_page")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORECAST_DIR = os.path.join(PROJECT_ROOT, "forecast")
OUT_PATH = os.path.join(FORECAST_DIR, "inventory.html")
PLOTLY_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/4.1.1/plotly.min.js"  # same pinned version as sales_report.html


class InventoryPageError(Exception):
    """Raised when required embedded data is missing -- never caught; refuses to render a blank
    or placeholder page (CONVENTIONS.md: validation failures must be raised loudly)."""


# The client-side recompute engine. Every formula here cites its METRICS.md section, matching
# src/phaseE1fix_recompute.py exactly -- this is the SAME logic reimplemented in JS, not a
# separate approximation; tests/test_inventory_parity.py runs this file (via Node) against the
# same embedded JSON and asserts equality with the Python results, for EACH division.
RECOMPUTE_JS = r"""
const DATA = JSON.parse(document.getElementById('inventory-data').textContent);
const DAYS_PER_MONTH = DATA.days_per_month;
let currentDivision = DATA.default_division;

function getDivisionData(division) { return DATA.divisions[division]; }

// METRICS.md Sec.3: LTD = forecast summed over protection_period months, prorated for the
// partial month.
function computeLTD(forecastArr, protectionDays) {
  const monthsFloat = protectionDays / DAYS_PER_MONTH;
  const full = Math.floor(monthsFloat);
  const frac = monthsFloat - full;
  let ltd = 0;
  for (let i = 0; i < full; i++) ltd += forecastArr[i] || 0;
  if (frac > 0 && full < forecastArr.length) ltd += frac * forecastArr[full];
  return { ltd, full, frac };
}

// METRICS.md Sec.4: empirical distribution of cumulative demand over rolling windows of
// protection_period length, across the item's full ACTUAL history.
function rollingWindowSums(actualArr, full, frac) {
  const windowLen = full + (frac > 0 ? 1 : 0);
  if (windowLen <= 0 || windowLen > actualArr.length) return [];
  const sums = [];
  for (let i = 0; i <= actualArr.length - windowLen; i++) {
    let s = 0;
    for (let j = 0; j < full; j++) s += actualArr[i + j];
    if (frac > 0 && i + full < actualArr.length) s += frac * actualArr[i + full];
    sums.push(s);
  }
  return sums;
}

// numpy-compatible linear-interpolation percentile (matches np.percentile default method).
function percentile(arr, p) {
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

// METRICS.md Sec.4 (corrected 2026-09-22): safety_stock = percentile(dist, sl) - LTD, floored at
// 0 -- NOT percentile - mean(dist). Min = LTD + safety_stock. rollingWindowSums only has the
// embedded MONTHLY actual_history to work from (no daily series is embedded, to keep page size
// reasonable), so this is METRICS.md Sec.4's explicit monthly-prorated fallback -- not the
// daily-preferred path used server-side, which has access to the full daily raw file. Max = Min
// + demand over review_interval_days (Sec.5), taken from the SAME forecast array immediately
// following the protection-period horizon (horizon-invariant per this project's combination
// models, verified in tests/test_inventory_parity.py).
function computeItemMinMax(item, controls) {
  const protectionDays = controls.procurement_lead_time_days + controls.assembly_time_days + controls.review_interval_days;
  const { ltd, full, frac } = computeLTD(item.forecast, protectionDays);
  const windowSums = rollingWindowSums(item.actual_history, full, frac);
  if (windowSums.length === 0) {
    return { min: null, max: null, ltd, safetyStock: null, nNonzero: 0, unreliable: true };
  }
  const mean = windowSums.reduce((a, b) => a + b, 0) / windowSums.length;
  const pctVal = percentile(windowSums, controls.cycle_service_level * 100);
  const safetyStock = Math.max(0, pctVal - ltd);
  const min = ltd + safetyStock;

  const reviewMonthsFloat = controls.review_interval_days / DAYS_PER_MONTH;
  const reviewFull = Math.floor(reviewMonthsFloat);
  const reviewFrac = reviewMonthsFloat - reviewFull;
  let replen = 0;
  for (let j = 0; j < reviewFull; j++) replen += item.forecast[full + j] || 0;
  if (reviewFrac > 0) replen += reviewFrac * (item.forecast[full + reviewFull] || 0);
  const max = min + replen;

  const nNonzero = windowSums.filter(x => x > 0).length;
  const meanMonthlyForecast = item.forecast.slice(0, full + (frac > 0 ? 1 : 0))
    .reduce((a, b) => a + b, 0) / Math.max(1, full + (frac > 0 ? 1 : 0));

  return { min, max, ltd, safetyStock, mean, nNonzero, unreliable: nNonzero < 6,
           meanMonthlyForecast, replenishment: replen };
}

// Task 2b Part 1: on_hand_sellable is now recomputed from item.by_warehouse (per-warehouse qty,
// embedded by src/build_inventory_page_data.py) restricted to whichever warehouse codes are
// CURRENTLY CHECKED on the page -- checkedWarehouses defaults to the division's full
// sellable_warehouse_codes list (the same total the page showed before this control did anything),
// so calling computeAll with no third argument reproduces the exact old behaviour. Min/Max never
// read on_hand at all (see computeItemMinMax above) and are UNCHANGED by this control, by
// construction, not by a special case here.
function onHandSellableFor(item, checkedWarehouses) {
  const set = checkedWarehouses instanceof Set ? checkedWarehouses : new Set(checkedWarehouses);
  return (item.by_warehouse || []).filter(w => set.has(w.code)).reduce((s, w) => s + w.qty, 0);
}

// Stock arrives separately from the page: data/stock_daily.json (src/stock_daily.py) holds the on-hand quantity per item
// and warehouse as [warehouse, qty] pairs and is loaded when the page opens. applyStock puts it into every division's
// items as by_warehouse, the shape onHandSellableFor reads; src/stock_daily.py apply_to_data is the Python twin the tests use.
function applyStock(data, payload) {
  const byCode = payload.items || {};
  for (const division of Object.keys(data.divisions)) {
    for (const item of data.divisions[division].items) {
      item.by_warehouse = (byCode[item.code] || []).map(p => ({ code: p[0], qty: p[1] }));
    }
  }
}

// METRICS.md Sec.6/9: stock_value = Sum(Min x unit_cost) over finished_goods_stock items with a
// usable unit_cost. months_of_cover = on_hand_sellable / mean monthly forecast (protection-period
// horizon mean, Inf when forecast=0). holding_cost = stock_value x holding_cost_rate_annual.
// METRICS.md Sec.40 (excess_stock_flag): excess = months_of_cover > obsolescence_threshold_months;
// a zero-forecast item (infinite cover) is flagged excess only if on_hand_sellable > 0, and is
// additionally marked noForecastDemand so the page can list it separately.
// Takes divisionData explicitly (not a module-level DATA.items) so the SAME function serves
// whichever division is currently selected.
// task 2b Part 2 (METRICS.md Sec.23): 'stock_policy' is the new (PEM101/PEM107) class name for
// what section 15 called 'finished_goods_stock'; PEM103 has no segmentation (task 2b Part 2 scope)
// and keeps the original 'finished_goods_stock'/'component_stock_ato' strings unchanged. Either
// spelling gets a Min/Max; 'confirmed_to_order'/'conflict' NEVER do, even if the item happens to
// have enough history that computeItemMinMax could technically produce a number for it -- the
// computation is skipped outright, not computed then hidden.
function getsMinMax(item) {
  return item.policy === 'finished_goods_stock' || item.policy === 'stock_policy';
}

function computeAll(controls, divisionData, checkedWarehouses) {
  const checked = checkedWarehouses || divisionData.sellable_warehouse_codes;
  const checkedSet = checked instanceof Set ? checked : new Set(checked);
  let stockValue = 0;
  const perItem = [];
  for (const item of divisionData.items) {
    const inFg = getsMinMax(item);
    const r = inFg ? computeItemMinMax(item, controls) : { min: null, max: null, unreliable: true };
    const contribution = (inFg && !item.no_unit_cost_item && r.min !== null) ? r.min * item.unit_cost : 0;
    if (inFg) stockValue += contribution;
    const onHandSellable = onHandSellableFor(item, checkedSet);
    const hasForecast = r.meanMonthlyForecast && r.meanMonthlyForecast > 0;
    const monthsOfCover = hasForecast ? onHandSellable / r.meanMonthlyForecast : Infinity;
    const noForecastDemand = !hasForecast;
    const excess = noForecastDemand
      ? onHandSellable > 0
      : monthsOfCover > controls.obsolescence_threshold_months;
    perItem.push({ code: item.code, policy: item.policy, min: r.min, max: r.max,
                   stockValueContribution: contribution, monthsOfCover, unreliable: r.unreliable,
                   currentMin: item.current_min, currentMax: item.current_max, currentHasRecord: item.current_has_record,
                   unitCost: item.unit_cost, noUnitCost: item.no_unit_cost_item,
                   onHandSellable, excess, noForecastDemand,
                   // task 2b Part 2 (METRICS.md Sec.23) -- undefined for PEM103 (no segmentation)
                   label: item.fulfilment_label, S1: item.S1, S2: item.S2,
                   S2_computable: item.S2_computable, S3: item.S3, type: item.type });
  }
  const holdingCost = stockValue * controls.holding_cost_rate_annual;
  const excessCount = perItem.filter(r => r.excess).length;
  return { stockValue, holdingCost, perItem, excessCount };
}
if (typeof module !== 'undefined') { module.exports = { computeLTD, rollingWindowSums, percentile, computeItemMinMax, onHandSellableFor, applyStock, computeAll, DATA }; }
// END_RECOMPUTE_JS
"""


# The stock file the page loads when it opens, relative to forecast/inventory.html (same site).
STOCK_JSON_URL = "../data/stock_daily.json"


def strip_stock(data: dict) -> dict:
    """Takes every stock-dependent input out of the embedded data: per-warehouse stock, the sellable on-hand figure and the
    stock pull time and metadata. They live in data/stock_daily.json and change daily; what stays embedded (Min, Max, the
    current Min/Max settings, forecasts, every sales-derived input) changes monthly."""
    for division in data["divisions"].values():
        division.pop("stock_pulled_at", None)
        for item in division["items"]:
            item.pop("by_warehouse", None)
            item.pop("on_hand_sellable", None)
    data.pop("stock_meta", None)
    return data


def build_page(**data_sources) -> str:
    """Renders the page. With no arguments it pulls live; data_sources (inventory_source,
    sales_source, pull_labels) pass already-pulled data through to build_data, no database access."""
    data = build_data(**data_sources)
    if not data.get("divisions"):
        raise InventoryPageError("build_inventory_page_data.build_data() returned zero divisions -- "
                                  "refusing to render a page with nothing to show.")
    for div in data["division_order"]:
        if not data["divisions"].get(div, {}).get("items"):
            raise InventoryPageError(f"Division {div} has zero embedded items -- refusing to render "
                                      f"a page with an empty enabled division.")
    strip_stock(data)
    stock_json_url_js = json.dumps(STOCK_JSON_URL)
    # allow_nan=False (task 2b Part 8): fail the BUILD loudly if any float NaN/Infinity ever
    # reaches this point again, instead of silently emitting the invalid-JSON `NaN` token that
    # broke JSON.parse() client-side and blanked the entire page (found by this task's own visual
    # check -- see _load_pem107_alert()'s fix, the actual source of the NaN this caught).
    data_json = json.dumps(data, allow_nan=False)

    # Numbers in reader text come from data, config or recorded outputs (CONVENTIONS.md "Dynamic values").
    gap_pct = f"{data['pipeline_gap_pct']:.0f}"
    notice_days = data["fulfilment_notice_days"]
    signal_count = data["fulfilment_signal_count"]
    split_label = data["pem107_alert"]["split_label"]

    note_values = {
        "sl_min": f"{data['tier_a_ranges']['cycle_service_level'][0]:.2f}",
        "sl_max": f"{data['tier_a_ranges']['cycle_service_level'][1]:.2f}",
        "n_presets": len(data["divisions"]["PEM101"]["curve_target"]["presets"]),
        "split_label": split_label,
    }

    defaults = data["tier_a_defaults"]
    ranges = data["tier_a_ranges"]

    def slider(key, label, step, suffix=""):
        lo, hi = ranges[key]
        val = defaults[key]
        return f"""
        <div class="ctrl-row">
          <label for="ctrl-{key}">{label}: <span id="val-{key}">{val}{suffix}</span></label>
          <input type="range" id="ctrl-{key}" min="{lo}" max="{hi}" step="{step}" value="{val}"
                 oninput="onControlChange()">
        </div>"""

    controls_html = "".join([
        slider("procurement_lead_time_days", "Procurement lead time (days)", 1, "d"),
        slider("assembly_time_days", "Assembly time (days)", 1, "d"),
        slider("review_interval_days", "Review interval (days)", 1, "d"),
        slider("cycle_service_level", "Cycle service level", 0.01),
        slider("holding_cost_rate_annual", "Annual holding cost rate", 0.01),
        # RE-ENABLED, task 2b Part 1 (METRICS.md Sec.40, excess_stock_flag): now drives the
        # item table's Excess column and the totals box's excess count, recomputed live.
        slider("obsolescence_threshold_months", "Obsolescence threshold (months)", 1, "mo"),
    ])

    division_options = "".join(
        f'<option value="{d}">{d} ({len(data["divisions"][d]["items"])} รายการ)</option>'
        for d in data["division_order"]
    ) + "".join(
        f'<option value="{d}" disabled title="{html.escape(reason)}">{d} — {html.escape(data["disabled_division_labels"][d])}</option>'
        for d, reason in data["disabled_divisions"].items()
    )
    disabled_notes = "".join(
        f'<li><b>{html.escape(d)}</b>: {html.escape(reason)}</li>'
        for d, reason in data["disabled_divisions"].items()
    )

    page = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>แผนสต็อค — Inventory Min/Max Scenario</title>
<script src="{PLOTLY_CDN_URL}"></script>
<style>
  :root {{
    color-scheme: light;
    --page: #f9f9f7; --surface: #fcfcfb;
    --text-primary: #0b0b0b; --text-secondary: #52514e;
    --muted: #898781; --gridline: #e1e0d9; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-2: #eb6834;
    --series-3: #1baf7a; --series-4: #eda100;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size:14px; line-height:1.6; }}
  .wrap {{ max-width: 1440px; margin: 0 auto; padding: 20px 20px 80px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; margin: 28px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  p.hint, p.scope-note, span.hint, span.scope-note {{ font-size: 12px; color: var(--muted); }}
  p.note-box {{ font-size: 12.5px; color: var(--text-secondary); background: #eef4fb;
    border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }}
  a.back-link {{ color: var(--series-1); text-decoration: none; font-size: 13px; }}
  .plotly-chart {{ width:100%; min-height: 320px; margin: 6px 0 14px; }}
  .chart-fail {{ padding: 24px 12px; text-align: center; background: #f0efec; border-radius: 6px; }}
  .alert-banner {{ background:#fdecea; border:2px solid #d03b3b; border-radius:8px; padding:14px 18px; margin:12px 0; }}
  .alert-banner-title {{ font-size:15px; font-weight:700; color:#8f2b2b; margin-bottom:8px; }}
  .alert-banner .report-table {{ background:#fff; }}
  .alert-banner .hint {{ color:#8f2b2b; }}
  ul.disabled-note-list {{ font-size: 12px; color: var(--muted); margin: 4px 0 0; padding-left: 18px; }}
  .item-check-list {{ display:flex; gap:8px; flex-wrap:wrap; margin: 6px 0; }}
  label.item-check {{ background:#fff; border:1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-size:12.5px; }}
  .table-scroll {{ overflow-x: auto; max-width: 100%; }}
  .report-table {{ width:100%; border-collapse: collapse; font-size: 12.5px; margin: 6px 0 16px; }}
  .report-table th, .report-table td {{ border: 1px solid var(--border); padding: 5px 7px; text-align: right; }}
  .report-table th:first-child, .report-table td:first-child {{ text-align: left; }}
  .report-table thead th {{ background: #f0efec; cursor: pointer; }}
  .report-table .total-row td {{ font-weight: 700; background: #f0efec; }}
  .totals-box {{ display:flex; gap:12px; flex-wrap:wrap; font-size:14px; margin: 10px 0; }}
  .totals-box .stat {{ background:#fff; border:1px solid var(--border); border-radius:6px; padding:8px 12px; }}
  .totals-box .stat b {{ display:block; font-size:18px; color: var(--series-1); }}

  /* Layout: controls in a panel beside what they change (CONVENTIONS.md "Page layout"). */
  .layout {{ display: block; }}
  .control-panel {{ background:#f0efec; border-radius:8px; padding:10px 14px; margin: 10px 0; }}
  .panel-toggle {{ display:block; width:100%; text-align:left; font: inherit; font-size: 16px; font-weight:700;
    background:none; border:none; padding: 4px 0; cursor:pointer; color: var(--text-primary); }}
  .panel-toggle::after {{ content: " \\25BE"; }}
  .control-panel.collapsed .panel-toggle::after {{ content: " \\25B8"; }}
  .control-panel.collapsed #panel-body {{ display: none; }}
  .division-panel {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin: 8px 0; }}
  .division-panel select {{ font-size: 14px; padding: 5px 8px; border-radius: 6px; border:1px solid var(--border); max-width: 100%; }}
  .ctrl-panel {{ display:grid; grid-template-columns: 1fr; gap: 8px; margin: 8px 0 10px; }}
  .ctrl-row label {{ font-size: 12.5px; display: flex; justify-content: space-between; gap: 6px; }}
  .ctrl-row input[type=range] {{ margin: 0; height: 16px; }}
  .ctrl-panel {{ gap: 4px; }}
  #panel-body p {{ margin: 4px 0; }}
  #panel-body p.hint {{ font-size: 11.5px; line-height: 1.4; }}
  .division-panel {{ margin: 4px 0; }}
  .ctrl-row input[type=range] {{ width: 100%; }}
  .summary-box {{ background:#fff; border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin: 10px 0 4px; }}
  .summary-title {{ font-weight:700; font-size: 14px; margin-bottom: 4px; }}
  .summary-box .totals-box {{ display:block; margin: 4px 0; }}
  .summary-box .stat {{ display:flex; justify-content: space-between; align-items: baseline; gap: 8px;
    font-size: 12px; padding: 3px 4px; border: 0; border-bottom: 1px solid var(--border); border-radius: 0; }}
  .summary-box .stat b {{ display:inline; font-size: 14px; white-space: nowrap; }}
  .content {{ min-width: 0; }}
  @keyframes flash-change {{ from {{ background: #ffe27a; }} to {{ background: transparent; }} }}
  .flash {{ animation: flash-change 1s ease-out; }}
  @media (min-width: 900px) {{
    .layout {{ display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 24px; align-items: start; }}
    .control-panel {{ position: sticky; top: 8px; max-height: calc(100vh - 40px); overflow-y: auto; margin-top: 0; }}
    .wrap {{ padding-bottom: 24px; }}
    .panel-toggle {{ pointer-events: none; cursor: default; }}
    .panel-toggle::after, .control-panel.collapsed .panel-toggle::after {{ content: ""; }}
    .control-panel.collapsed #panel-body {{ display: block; }}
  }}
  @media (max-width: 899px) {{
    .control-panel {{ position: sticky; top: 0; z-index: 20; max-height: 75vh; overflow-y: auto; }}
    .wrap {{ padding: 12px 12px 60px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back-link" href="../index.html">&larr; กลับไปหน้าหลัก (Dashboard)</a>
  <h1 id="page-title">แผนสต็อค — Inventory Min/Max Scenario</h1>
  <p class="scope-note" id="page-timestamps-note"></p>

  <div class="layout">
  <aside id="control-panel" class="control-panel">
    <!-- Previous heading: Tier A — scenario tool, UNCALIBRATED, assumed mechanics; adjustable on this page, shared by every division. Previous description: the controls below use mechanics assumed from METRICS.md Sec.5/16 (LTD + safety stock from the forecast), not yet calibrated against real behaviour, unlike the "PEM101 — Robust Ensemble" section below, which is calibrated against real outcomes (METRICS.md Sec.20/22); do not use figures from this section in place of the calibrated section. -->
    <button type="button" id="panel-toggle" class="panel-toggle" aria-expanded="true" onclick="togglePanel()">ตัวควบคุม "ถ้าเป็นแบบนี้ล่ะ"</button>
    <div id="panel-body">
      <div class="division-panel">
        <label for="division-select"><b>Division:</b></label>
        <select id="division-select" onchange="onDivisionChange()">{division_options}</select>
      </div>
      <p class="hint">ใช้สมมติฐานมาตรฐาน ยังไม่ได้เทียบกับผลจริง ใช้ดูทิศทางเท่านั้น · ถ้าจะใช้ตัวเลข ใช้ส่วน PEM101 ด้านล่างซึ่งเทียบกับผลจริงแล้ว</p>
      <!-- source: config.yaml phase_e1_assumptions (defaults), segment_policy (Tier B, not editable here) -->
      <div class="ctrl-panel">
        {controls_html}
      </div>
      <!-- Previous wording, kept off screen: warehouses counted as sellable for the selected division (changes with the division); ticking or unticking recomputes on-hand sellable, months of cover, value at risk and the excess flag at once (no effect on Min/Max, the Min/Max formulas never read on-hand stock, METRICS.md §5). -->
      <p>เลือกคลังที่นับเป็นของขายได้ · Min/Max ไม่เปลี่ยน เพราะคำนวณจากยอดขาย ไม่ได้ใช้ stock ปัจจุบัน</p>
      <div class="item-check-list" id="warehouse-checklist"></div>
      {render_notes_html('inventory.html', 'warehouse-checklist', values=note_values)}
      <p class="hint" id="control-scope">ตัวควบคุมชุดนี้มีผลกับ Min/Max ผลรวม ตาราง และกราฟด้านขวา · ไม่มีผลกับกราฟเป้าการส่งทันของ PEM101</p>
      <!-- previously: ผลรวม (Totals) heading and stat boxes in the page body, recomputed every time a control or the division changes -->
      <div class="summary-box" id="summary-box">
        <div class="summary-title">ผลจากตัวควบคุม</div>
        <div class="totals-box">
          <div class="stat">Stock value (Σ Min×unit_cost)<b id="tot-stock-value">-</b></div>
          <div class="stat">Holding cost (annual)<b id="tot-holding-cost">-</b></div>
          <div class="stat">Items with a Min/Max<b id="tot-n-items">-</b></div>
          <!-- previously: Excess stock items (METRICS.md §40) -->
          <div class="stat">สินค้าที่มีของค้าง<b id="tot-excess-count">-</b></div>
        </div>
      </div>
    </div>
  </aside>

  <main class="content">
  <p class="scope-note" id="scope-note"></p>
  <ul class="disabled-note-list" id="disabled-note-list">{disabled_notes}</ul>

  <div id="pem107-alert" class="alert-banner" style="display:none" role="alert">
    <!-- previously: PEM107 — Omni Channel delivery decline since May 2026 -->
    <div class="alert-banner-title">⚠ PEM107 ส่งของช่องทาง Omni ทันน้อยลงตั้งแต่ {split_label}</div>
    <div id="pem107-alert-headline"></div>
    <div class="table-scroll"><table class="report-table" id="pem107-alert-table">
      <thead><tr>
        <th>Product Type</th><th>Product Description</th><th>Product Code</th>
        <th>Units ordered (from May 2026)</th><th>Units late</th>
        <th>not_late (from May 2026)</th><th>not_late (before May 2026)</th><th>Share of all late units</th>
      </tr></thead>
      <tbody id="pem107-alert-table-body"></tbody>
    </table></div>
    <p class="hint" id="pem107-alert-source"></p>
    <p class="hint" id="pem107-alert-limitations"></p>
    {render_notes_html('inventory.html', 'pem107-alert', values=note_values)}
  </div>
  <!-- Previous wording, kept off screen: changing the controls below changes only what is displayed, not the forecasting model (Tier A); structural changes (Tier B, e.g. segment_policy) need an edit to config.yaml and a pipeline re-run. The sellable-warehouse list of every division (PEM101 included) is a business assumption, not a fact confirmed from data: the sales rows carry no warehouse field, so the reverse direction cannot be checked (STATUS.md, Phase E2 Part 1). -->
  <p class="note-box"><b>หมายเหตุสำคัญ:</b> ตัวเลขในหน้านี้เป็น <b>ค่าสถานการณ์ (scenario values) ภายใต้สมมติฐานที่ระบุไว้เท่านั้น
    ไม่ใช่คำแนะนำการสั่งซื้อ (purchase recommendation)</b> ตัวควบคุมด้านล่างเปลี่ยนแค่ตัวเลขบนหน้านี้ ไม่ได้เปลี่ยนการทายยอดขาย
    รายการ placeholder/excluded จะไม่มี Min/Max และไม่มีปริมาณสั่งซื้อ (purchase quantity) ใดๆ ทั้งสิ้น
    รายชื่อคลังที่ขายได้เป็นสมมติฐาน ระบบไม่ได้บันทึกว่าของที่ส่งออกไปมาจากคลังไหน จึงตรวจจากข้อมูลไม่ได้</p>
  <!-- Previous wording, kept off screen: figures on this page are computed from the MONTHLY history embedded in the page (monthly proration, METRICS.md Sec.4's explicit fallback), not the DAILY window the server-side pipeline uses. The percentage is computed at build time: src/reader_values.py pipeline_gap_pct, page monthly-prorated stock value against output/summary/phaseE1fix_2_minmax_stockvalue.csv (stock_value_contribution) over the same PEM101 items at the default scenario; the earlier typed figure was 3.3% from a run on the older 128-item pilot set (STATUS.md Phase E1-fix-2). -->
  <p class="note-box" id="proration-note">ตัวเลขบนหน้านี้คำนวณจากยอดขายรายเดือนเพื่อให้หน้าโหลดเร็ว จึงต่างจากที่ระบบคำนวณเต็มจากข้อมูลรายวันประมาณ {gap_pct}% (PEM101)</p>

  <h2>ตารางรายรายการ (เรียงตาม Value at Risk ได้)</h2>
  <!-- Stock figures (Months of cover, ของค้าง, the stock-with-no-forecast table, the count in the summary box) come from the stock file loaded when the page opens; the three dates below describe that file. -->
  <p class="note-box" id="stock-labels" style="display:none"></p>
  <!-- Formula: Value at risk = max(0, current_min − scenario_min) × unit_cost, the earlier on-screen hint described the opposite direction (current stock below the scenario) although the formula measures a system Min above the simulated one. Excess = months of cover above the obsolescence threshold set above (METRICS.md §40), recomputed whenever the ticked warehouses or the threshold change. -->
  <p class="hint">Value at risk = ถ้า Min ในระบบสูงกว่าที่จำลอง ส่วนเกินคิดเป็นเงินเท่าไหร่<br>ของค้าง = stock พอขายเกินจำนวนเดือนที่ตั้งไว้ด้านบน</p>
  {render_notes_html('inventory.html', 'excess-threshold', values=note_values)}
  <!-- Previous wording of the class caption, kept off screen: Policy = METRICS.md §23 class (stock_policy/confirmed_to_order/conflict) for PEM101/PEM107, supersedes section 15. Only stock_policy items receive a Min/Max here; confirmed_to_order and conflict items are listed with no Min/Max in the separate table below. Label = dominant manufacturing_type (MTS/MTO/ETO/mixed). Signals = S1 (on-hand stock) / S2 (batch-before-PO share) / S3 (median notice, days), check/cross/dash (dash = S2 could not be computed, S1+S3 both required instead). The number of signals and the notice threshold below are read at build time: src/reader_values.py fulfilment_signal_count (task2b_part2_item_level.csv) and fulfilment_notice_threshold_days (S3_THRESHOLD_DAYS in src/investigations/task2b_part2_fulfilment_segmentation.py). -->
  <div id="policy-class-notes" style="display:none">
    <p class="hint" id="segmentation-note">ประเภทสินค้า: เก็บ stock / ผลิตตามสั่ง / ยังไม่ชัด · ดูจากป้ายในระบบ (MTS / MTO / ETO) คู่กับพฤติกรรมจริง {signal_count} อย่าง: มีของในคลัง · ผลิตเป็น batch ก่อนลูกค้าสั่ง · ส่งได้ภายใน {notice_days} วัน · ✓ ตรง ✗ ไม่ตรง – คำนวณไม่ได้</p>
    {render_notes_html('inventory.html', 'item-policy-classes', values=note_values)}
  </div>
  <div class="table-scroll"><table class="report-table" id="item-table">
    <thead><tr>
      <th onclick="sortTable(0)">Item</th><th onclick="sortTable(1)">Policy</th>
      <th onclick="sortTable(2)">Label</th><th onclick="sortTable(3)">Signals (S1/S2/S3)</th>
      <th onclick="sortTable(4)">Min</th><th onclick="sortTable(5)">Max</th>
      <th onclick="sortTable(6)">Min (ค่าที่ตั้งในระบบ)</th><th onclick="sortTable(7)">Max (ค่าที่ตั้งในระบบ)</th>
      <th onclick="sortTable(8)">Months of cover</th>
      <th onclick="sortTable(9)">Value at risk (THB)</th><th onclick="sortTable(10)">ของค้าง</th>
    </tr></thead>
    <tbody id="item-table-body"></tbody>
    <tfoot><tr class="total-row"><td colspan="7">Total</td><td id="item-total-system-max"></td><td colspan="3"></td></tr></tfoot>
  </table></div>

  <!-- previously: Confirmed-to-order / Conflict รายการ (ไม่มี Min/Max, METRICS.md §23); items classed confirmed_to_order or conflict get no Min/Max however much sales history they have (only PEM101/PEM107 have this grouping; PEM103 shows an empty table). -->
  <h2>สินค้าผลิตตามสั่ง และสินค้าที่ยังไม่ชัด (ไม่มี Min/Max)</h2>
  <p class="hint" id="class-table-note">จัดกลุ่มเฉพาะ PEM101 และ PEM107 ถ้าเลือก PEM103 ตารางนี้จะว่าง</p>
  <div class="table-scroll"><table class="report-table" id="class-table">
    <thead><tr><th>Item</th><th>Type</th><th>Label</th><th>Class</th><th>S1 (on-hand)</th><th>S2 (batch-before-PO)</th><th>S3 (notice, days)</th></tr></thead>
    <tbody id="class-table-body"></tbody>
  </table></div>

  <!-- previously: สต็อคที่ไม่มียอดพยากรณ์ (on-hand exists, no forecast demand); items whose mean monthly forecast = 0 over the current protection period (months of cover = infinity, METRICS.md §9), listed separately as METRICS.md §40 requires. -->
  <h2>สินค้าที่มีของแต่ไม่มียอดทาย</h2>
  <p class="hint">ถ้าไม่มีแถว แปลว่าไม่มีสินค้าแบบนี้ในฝ่ายที่เลือก</p>
  <div class="table-scroll"><table class="report-table" id="no-forecast-table">
    <thead><tr><th>Item</th><th>Policy</th><th>On-hand sellable</th><th>ของค้าง</th></tr></thead>
    <tbody id="no-forecast-table-body"></tbody>
  </table></div>

  <h2>Placeholder / Excluded รายการ (ไม่มี Min/Max)</h2>
  <!-- previously: these items get no Min, Max or purchase quantity (placeholder_hierarchy_treatment); no rows means the division has no placeholder/excluded concept (PEM103/PEM107). -->
  <p class="hint">สินค้าที่ไม่มีประวัติขาย ไม่มี Min/Max และไม่ใช้สั่งของ</p>
  <div class="table-scroll"><table class="report-table"><thead><tr><th>Item</th><th>Type</th><th>Policy</th></tr></thead>
  <tbody id="no-policy-table-body"></tbody></table></div>

  <h2>Trade-off: Stock value vs. Cycle Service Level</h2>
  <p class="hint">เส้นแสดง stock_value ที่ระดับ service level ต่างๆ (ค่าควบคุมอื่นคงที่ตามที่ตั้งไว้ด้านบน) สำหรับ division ที่เลือก</p>
  <div id="chart-tradeoff" class="plotly-chart"></div>
  {render_notes_html('inventory.html', 'chart-tradeoff', values=note_values)}

  <!-- previously: Min เทียบกับค่าปัจจุบัน (current_min_max) — รายรายการ -->
  <!-- label changed: "Min ที่จำลอง เทียบกับ Min ที่ตั้งในระบบตอนนี้" ("ตอนนี้" called the system value current) -->
  <h2>Min ที่จำลอง เทียบกับ Min ค่าที่ตั้งในระบบ</h2>
  <div id="chart-min-vs-current" class="plotly-chart"></div>
  {render_notes_html('inventory.html', 'chart-min-vs-current', values=note_values)}

  <div id="curve-target-section" style="display:none;">
    <!-- Previous heading: PEM101 — Trade-off Curve Target (METRICS.md Sec.22) — PARTIALLY CALIBRATED. Previous note: the data cannot identify the correct reorder level on its own (every item gives the same range ratio, no item-level information); choosing the not_late target is what fixes the reorder level (METRICS.md Sec.22). -->
    <h2>PEM101 — เลือกเป้าการส่งทัน แล้วดูว่าต้องถือของเท่าไหร่</h2>
    <p class="hint" id="curve-own-controls">ส่วนนี้ปรับได้ด้วยปุ่มเป้าและ slider ในส่วนนี้เท่านั้น</p>
    <p class="note-box" id="curve-target-summary"></p>
    <p class="hint">ข้อมูลบอกไม่ได้ว่าบริษัทสั่งเติมเมื่อของเหลือกี่เดือน เป้าการส่งทันที่เลือกคือสิ่งที่กำหนดตัวนี้</p>
    <div id="chart-robust-curve" class="plotly-chart"></div>
    {render_notes_html('inventory.html', 'chart-robust-curve', values=note_values)}
    <div class="preset-controls" style="display:flex; gap:10px; flex-wrap:wrap; margin:10px 0;">
      <button type="button" id="preset-today-lowest" class="preset-btn"></button>
      <button type="button" id="preset-highest-at-today" class="preset-btn"></button>
      <button type="button" id="preset-stretch" class="preset-btn"></button>
    </div>
    <div class="slider-control" style="margin:10px 0;">
      <label for="notlate-slider">not_late target: <b id="notlate-slider-value"></b></label><br>
      <input type="range" id="notlate-slider" step="0.01" style="width:100%;">
    </div>
    <div class="totals-box" id="curve-target-totals"></div>
    <!-- previously: METRICS.md §24 relative_service_cost, computed when a target is chosen above -->
    <p class="note-box" id="relative-service-cost-note">ต้องเพิ่ม stock กี่ % เพื่อไปถึงเป้าที่เลือก</p>
    {render_notes_html('inventory.html', 'relative-service-cost', values=note_values)}
    <div class="table-scroll"><table class="report-table" id="curve-item-table">
      <thead><tr>
        <th>Item</th><th>Min</th><th>Max (median)</th><th>Max range (across members)</th>
      </tr></thead>
      <tbody id="curve-item-table-body"></tbody>
    </table></div>
  </div>

  <p class="scope-note" id="snapshot-note"></p>
  </main>
  </div>
</div>

<script type="application/json" id="inventory-data">{data_json}</script>
<script>
{RECOMPUTE_JS}

function readControls() {{
  return {{
    procurement_lead_time_days: parseFloat(document.getElementById('ctrl-procurement_lead_time_days').value),
    assembly_time_days: parseFloat(document.getElementById('ctrl-assembly_time_days').value),
    review_interval_days: parseFloat(document.getElementById('ctrl-review_interval_days').value),
    cycle_service_level: parseFloat(document.getElementById('ctrl-cycle_service_level').value),
    holding_cost_rate_annual: parseFloat(document.getElementById('ctrl-holding_cost_rate_annual').value),
    obsolescence_threshold_months: parseFloat(document.getElementById('ctrl-obsolescence_threshold_months').value),
  }};
}}

function fmtTHB(x) {{ return 'THB ' + Math.round(x).toLocaleString(); }}

const CHART_FAIL_MSG = 'กราฟโหลดไม่ได้ เครือข่ายอาจบล็อกไลบรารีกราฟ · ตัวเลขและตารางยังใช้ได้ตามปกติ';
// Charts are drawn only when the charting library loaded; totals and tables never depend on it.
function plotSafe(id, draw) {{
  const el = document.getElementById(id);
  if (typeof Plotly === 'undefined') {{
    el.innerHTML = '<p class="hint chart-fail">' + CHART_FAIL_MSG + '</p>';
    return;
  }}
  draw();
}}

function togglePanel() {{
  const p = document.getElementById('control-panel');
  p.classList.toggle('collapsed');
  document.getElementById('panel-toggle').setAttribute('aria-expanded', String(!p.classList.contains('collapsed')));
}}

// Highlights, for about one second, every displayed number that a control change altered.
function snapshotCells() {{
  const m = new Map();
  ['tot-stock-value', 'tot-holding-cost', 'tot-n-items', 'tot-excess-count'].forEach(id =>
    m.set(id, document.getElementById(id).textContent));
  [['item-table-body', 4], ['no-forecast-table-body', 2]].forEach(([tb, from]) =>
    document.querySelectorAll('#' + tb + ' tr').forEach(tr => {{
      for (let i = from; i < tr.children.length; i++) m.set(tb + '|' + tr.children[0].textContent + '|' + i, tr.children[i].textContent);
    }}));
  return m;
}}
function flashEl(el) {{
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1100);
}}
function flashChanged(prev) {{
  ['tot-stock-value', 'tot-holding-cost', 'tot-n-items', 'tot-excess-count'].forEach(id => {{
    const el = document.getElementById(id);
    if (prev.get(id) !== undefined && prev.get(id) !== '-' && prev.get(id) !== el.textContent) flashEl(el);
  }});
  [['item-table-body', 4], ['no-forecast-table-body', 2]].forEach(([tb, from]) =>
    document.querySelectorAll('#' + tb + ' tr').forEach(tr => {{
      for (let i = from; i < tr.children.length; i++) {{
        const k = tb + '|' + tr.children[0].textContent + '|' + i;
        if (prev.has(k) && prev.get(k) !== tr.children[i].textContent) flashEl(tr.children[i]);
      }}
    }}));
}}

// Display names for the internal class values; the underlying values (stock_policy,
// confirmed_to_order, conflict) are unchanged everywhere else.
const POLICY_LABEL = {{ stock_policy: 'เก็บ stock', confirmed_to_order: 'ผลิตตามสั่ง', conflict: 'ยังไม่ชัด',
  finished_goods_stock: 'เก็บ stock (เกณฑ์เดิม)', component_stock_ato: 'เก็บชิ้นส่วน ประกอบตามสั่ง (เกณฑ์เดิม)' }};
// Display names for the placeholder table's status values (matched on their leading words).
function statusLabel(p) {{
  if (String(p).startsWith('placeholder - pending method')) return 'ไม่มีประวัติขาย (รอวิธีประมาณ)';
  if (String(p).startsWith('placeholder - method already assigned')) return 'ไม่มีประวัติขาย (กำหนดวิธีประมาณแล้ว)';
  if (String(p).startsWith('excluded - listed but never sold')) return 'ตัดออก มีใน Price List แต่ไม่เคยขาย';
  if (String(p).startsWith('excluded - division excluded')) return 'ตัดออก ทั้งฝ่ายไม่ใช้นโยบาย stock';
  return p;
}}
function policyLabel(p) {{ return POLICY_LABEL[p] || p; }}

// Builds an HTML comment without a literal comment opener inside this script block.
function htmlComment(t) {{ return '<' + '!-- ' + t + ' --' + '>'; }}

function setTextWithRef(id, text, ref) {{
  const el = document.getElementById(id);
  el.textContent = text;
  if (ref) el.appendChild(document.createComment(' ' + ref + ' '));
}}

function excessBadge(r) {{
  return r.excess ? '<span style="color:#c0392b;font-weight:700">เกิน</span>' : '<span style="color:var(--muted)">-</span>';
}}

function signalMark(v) {{
  if (v === null || v === undefined) return '&ndash;';
  return v ? '<span style="color:#1baf7a">&#10003;</span>' : '<span style="color:#c0392b">&#10007;</span>';
}}

function signalsCell(r) {{
  if (r.label === undefined) return '<span style="color:var(--muted)">n/a</span>'; // PEM103: no segmentation
  const s2 = r.S2_computable ? signalMark(r.S2) : '&ndash;';
  return `S1 ${{signalMark(r.S1)}} &nbsp; S2 ${{s2}} &nbsp; S3 ${{signalMark(r.S3)}}`;
}}

// One rule decides which rows the item table lists and which of them show a Min and Max; the summary
// box counts exactly those rows, for every division.
function isItemTableRow(r) {{
  return !r.noForecastDemand && r.policy !== 'confirmed_to_order' && r.policy !== 'conflict';
}}
function showsMinMax(r) {{ return isItemTableRow(r) && r.min !== null && r.max !== null; }}

function renderTable(perItem) {{
  // task 2b Part 1 (METRICS.md Sec.40): items with no_forecast_demand move to the separate
  // "stock with no forecast demand" table instead of showing months of cover = ∞ in this one.
  // task 2b Part 2 (METRICS.md Sec.23): confirmed_to_order/conflict items move to the class table
  // instead -- this table only ever shows Min/Max for stock_policy/finished_goods_stock items.
  const tbody = document.getElementById('item-table-body');
  tbody.innerHTML = '';
  const noteEl = document.getElementById('policy-class-notes');
  const segmented = perItem.some(r => r.label !== undefined);
  noteEl.style.display = segmented ? 'block' : 'none';
  for (const r of perItem) {{
    if (!isItemTableRow(r)) continue;
    const var_ = (r.currentMin && r.min !== null && r.unitCost) ? Math.max(0, r.currentMin - r.min) * r.unitCost : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{r.code}}</td><td>${{policyLabel(r.policy)}}</td>` +
      `<td>${{r.label !== undefined ? (r.label ?? '-') : '&ndash;'}}</td>` +
      `<td>${{signalsCell(r)}}</td>` +
      `<td>${{r.min !== null ? Math.round(r.min).toLocaleString() : '-'}}</td>` +
      `<td>${{r.max !== null ? Math.round(r.max).toLocaleString() : '-'}}</td>` +
      `<td>${{r.currentMin !== null && r.currentMin !== undefined ? Math.round(r.currentMin).toLocaleString() : '-'}}</td>` +
      `<td data-var="${{r.currentMax === 0 ? 0 : (r.currentMax || 0)}}">${{systemMaxText(r.currentMax, r.currentHasRecord)}}</td>` +
      `<td>${{!STOCK_OK ? STOCK_UNKNOWN : isFinite(r.monthsOfCover) ? r.monthsOfCover.toFixed(1) : '&#8734;'}}</td>` +
      `<td data-var="${{var_}}">${{fmtTHB(var_)}}</td>` +
      `<td data-var="${{STOCK_OK && r.excess ? 1 : 0}}">${{STOCK_OK ? excessBadge(r) : STOCK_UNKNOWN}}</td>`;
    tbody.appendChild(tr);
  }}
  renderSystemMaxTotal(perItem.filter(isItemTableRow));
}}

// The system's Max (Cube_Inventory_Exact maximum, summed over warehouses). A value of 0 on an item that has a record means nobody
// filled it in (stated by the user), so it is shown as ไม่ได้กรอก and left out of every sum; an item with no record at all shows a
// dash and is left out too. Min is not touched.
const MAX_NOT_FILLED = 'ไม่ได้กรอก';
function systemMaxText(v, hasRecord) {{
  if (v === null || v === undefined || hasRecord === false) return '-';
  if (v === 0) return MAX_NOT_FILLED;
  return Math.round(v).toLocaleString();
}}

function renderSystemMaxTotal(rows) {{
  const withMax = rows.filter(r => r.currentHasRecord !== false && r.currentMax !== null && r.currentMax !== undefined && r.currentMax > 0);
  const notFilled = rows.filter(r => r.currentHasRecord !== false && r.currentMax === 0).length;
  const total = withMax.reduce((s, r) => s + r.currentMax, 0);
  document.getElementById('item-total-system-max').innerHTML =
    '<b id="system-max-total">' + Math.round(total).toLocaleString() + '</b><br>' +
    '<span class="hint" id="system-max-note">ไม่รวม ' + notFilled + ' รายการที่ไม่ได้กรอก Max</span>';
}}

function renderNoForecastTable(perItem) {{
  const tbody = document.getElementById('no-forecast-table-body');
  tbody.innerHTML = '';
  for (const r of perItem) {{
    if (!r.noForecastDemand) continue;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{r.code}}</td><td>${{policyLabel(r.policy)}}</td>` +
      `<td>${{STOCK_OK ? Math.round(r.onHandSellable).toLocaleString() : STOCK_UNKNOWN}}</td>` +
      `<td>${{STOCK_OK ? excessBadge(r) : STOCK_UNKNOWN}}</td>`;
    tbody.appendChild(tr);
  }}
}}

function renderClassTable(perItem) {{
  // task 2b Part 2 (METRICS.md Sec.23): confirmed_to_order/conflict items -- no Min/Max under
  // any circumstance, listed here with their signals for transparency. Empty for PEM103 (no
  // segmentation) and for divisions where every item happens to be stock_policy.
  const tbody = document.getElementById('class-table-body');
  tbody.innerHTML = '';
  for (const r of perItem) {{
    if (r.policy !== 'confirmed_to_order' && r.policy !== 'conflict') continue;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{r.code}}</td><td>${{r.type ?? '-'}}</td><td>${{r.label ?? '-'}}</td><td>${{policyLabel(r.policy)}}</td>` +
      `<td>${{signalMark(r.S1)}}</td><td>${{r.S2_computable ? signalMark(r.S2) : '&ndash; (คำนวณไม่ได้)'}}</td><td>${{signalMark(r.S3)}}</td>`;
    tbody.appendChild(tr);
  }}
}}

function renderNoPolicyTable(divisionData) {{
  const tbody = document.getElementById('no-policy-table-body');
  tbody.innerHTML = '';
  for (const it of (divisionData.no_policy_items || [])) {{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{it.code}}</td><td>${{it.type}}</td><td>${{statusLabel(it.policy)}}</td>`;
    tbody.appendChild(tr);
  }}
}}

function renderWarehouseChecklist(divisionData) {{
  // RE-ENABLED, task 2b Part 1: each checkbox's checked state now feeds onHandSellableFor()
  // (see RECOMPUTE_JS's computeAll) via checkedWarehouseCodes() below -- toggling one recomputes
  // on_hand_sellable, months_of_cover, value_at_risk and the excess flag for every item. Min/Max
  // are unaffected by construction (computeItemMinMax never reads on-hand at all).
  const el = document.getElementById('warehouse-checklist');
  el.innerHTML = '';
  for (const w of divisionData.sellable_warehouse_codes) {{
    const label = document.createElement('label');
    label.className = 'item-check';
    label.innerHTML = `<input type="checkbox" class="wh-check" value="${{w}}" checked onchange="onControlChange()"> ${{w}}`;
    el.appendChild(label);
  }}
}}

function checkedWarehouseCodes() {{
  return Array.from(document.querySelectorAll('#warehouse-checklist .wh-check:checked')).map(cb => cb.value);
}}

let sortDir = {{}};
function sortTable(col) {{
  const tbody = document.getElementById('item-table-body');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  sortDir[col] = !sortDir[col];
  rows.sort((a, b) => {{
    const av = a.children[col].dataset.var !== undefined ? parseFloat(a.children[col].dataset.var) : a.children[col].textContent;
    const bv = b.children[col].dataset.var !== undefined ? parseFloat(b.children[col].dataset.var) : b.children[col].textContent;
    const an = parseFloat(av), bn = parseFloat(bv);
    let cmp;
    if (!isNaN(an) && !isNaN(bn)) cmp = an - bn; else cmp = String(av).localeCompare(String(bv));
    return sortDir[col] ? cmp : -cmp;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

function renderTradeoff(controls, divisionData) {{
  const slValues = [];
  const [slLo, slHi] = DATA.tier_a_ranges.cycle_service_level, slStep = DATA.service_level_chart_step;
  for (let s = slLo; s <= slHi + 1e-9; s += slStep) slValues.push(Math.round(s * 100) / 100);
  const values = slValues.map(sl => computeAll({{...controls, cycle_service_level: sl}}, divisionData).stockValue);
  const selectedValue = computeAll(controls, divisionData).stockValue;
  plotSafe('chart-tradeoff', () => Plotly.newPlot('chart-tradeoff', [
      {{ x: slValues, y: values, mode: 'lines+markers', line: {{color: '#2a78d6'}}, showlegend: false }},
      {{ x: [controls.cycle_service_level], y: [selectedValue], mode: 'markers+text', name: 'service level ที่เลือก',
         text: ['service level ที่เลือก'], textposition: 'top left', showlegend: false,
         marker: {{color: '#eb6834', size: 12, symbol: 'diamond'}} }}],
    {{ margin: {{t:30}}, xaxis: {{title: {{text: 'Cycle service level'}}}}, yaxis: {{title: {{text: 'Stock value (THB)'}}}} }},
    {{responsive: true}}));
}}

function renderMinVsCurrent(perItem) {{
  const withCurrent = perItem.filter(r => r.min !== null && r.currentMin !== null && r.currentMin !== undefined);
  plotSafe('chart-min-vs-current', () => Plotly.newPlot('chart-min-vs-current', [
    {{ x: withCurrent.map(r => r.code), y: withCurrent.map(r => r.min), name: 'Scenario Min', type: 'bar', marker: {{color:'#2a78d6'}} }},
    {{ x: withCurrent.map(r => r.code), y: withCurrent.map(r => r.currentMin), name: 'Min (ค่าที่ตั้งในระบบ)', type: 'bar', marker: {{color:'#eda100'}} }}
  ], {{ margin: {{t:10, b:90, l:70}}, barmode: 'group',
       xaxis: {{title: {{text: 'รหัสสินค้า'}}, tickangle: -60, tickfont:{{size:8}}}},
       yaxis: {{title: {{text: 'จำนวน (ชิ้น)'}}}} }}, {{responsive: true}}));
}}

// BEGIN_CURVE_INTERP_JS
function lerp(a, b, t) {{ return a + (b - a) * t; }}

function interpolateGridAtNotLate(grid, targetNotLate) {{
  const g = grid;
  if (targetNotLate <= g[0].not_late_median_pct) return gridPointAsResult(g[0]);
  if (targetNotLate >= g[g.length - 1].not_late_median_pct) return gridPointAsResult(g[g.length - 1]);
  for (let i = 0; i < g.length - 1; i++) {{
    const a = g[i], b = g[i + 1];
    if (targetNotLate >= a.not_late_median_pct && targetNotLate <= b.not_late_median_pct) {{
      const t = (targetNotLate - a.not_late_median_pct) / (b.not_late_median_pct - a.not_late_median_pct);
      return lerpGridPoints(a, b, t);
    }}
  }}
}}

function gridPointAsResult(g) {{
  return {{
    r: g.r, not_late_median_pct: g.not_late_median_pct,
    stock_value_min: g.stock_value_min, stock_value_median: g.stock_value_median, stock_value_max: g.stock_value_max,
    items: g.items.map(it => ({{ code: it.code, Min: it.Min, Max_median: it.Max_median, Max_min: it.Max_min, Max_max: it.Max_max }})),
  }};
}}

function lerpGridPoints(a, b, t) {{
  const items = a.items.map((ai, idx) => {{
    const bi = b.items[idx];
    return {{
      code: ai.code, Min: lerp(ai.Min, bi.Min, t), Max_median: lerp(ai.Max_median, bi.Max_median, t),
      Max_min: lerp(ai.Max_min, bi.Max_min, t), Max_max: lerp(ai.Max_max, bi.Max_max, t),
    }};
  }});
  return {{
    r: lerp(a.r, b.r, t), not_late_median_pct: lerp(a.not_late_median_pct, b.not_late_median_pct, t),
    stock_value_min: lerp(a.stock_value_min, b.stock_value_min, t),
    stock_value_median: lerp(a.stock_value_median, b.stock_value_median, t),
    stock_value_max: lerp(a.stock_value_max, b.stock_value_max, t),
    items,
  }};
}}
// task 2b Part 3 (METRICS.md Sec.24): interpolates the pre-computed ratio_e grid (median/min/max
// across the 80 distinct ensemble members) at an arbitrary target not_late -- same linear
// interpolation convention as interpolateGridAtNotLate above, on a separate (finer, 0.25pp-step)
// grid built by src/investigations/task2b_part3_relative_service_cost.py. Returns null outside
// the grid's own range (never extrapolated).
function interpolateRatioGrid(rsc, targetNotLate) {{
  if (!rsc || !rsc.grid || !rsc.grid.length) return null;
  const g = rsc.grid;
  if (targetNotLate < g[0].not_late_pct || targetNotLate > g[g.length - 1].not_late_pct) return null;
  for (let i = 0; i < g.length - 1; i++) {{
    const a = g[i], b = g[i + 1];
    if (targetNotLate >= a.not_late_pct && targetNotLate <= b.not_late_pct) {{
      const t = (b.not_late_pct === a.not_late_pct) ? 0 : (targetNotLate - a.not_late_pct) / (b.not_late_pct - a.not_late_pct);
      return {{ median: lerp(a.median, b.median, t), min: lerp(a.min, b.min, t), max: lerp(a.max, b.max, t) }};
    }}
  }}
  return g[g.length - 1];
}}
// END_CURVE_INTERP_JS

let curCurveTarget = null;

function applyCurveTarget(targetNotLate) {{
  const state = curCurveTarget;
  if (!state) return;
  const {{ ct, grid }} = state;
  const result = interpolateGridAtNotLate(grid, targetNotLate);

  document.getElementById('notlate-slider').value = targetNotLate;
  document.getElementById('notlate-slider-value').textContent = targetNotLate.toFixed(2) + '%';

  const diff = result.stock_value_median - ct.today_point.stock_value_thb;
  const diffPct = 100 * diff / ct.today_point.stock_value_thb;
  document.getElementById('curve-target-totals').innerHTML = `
    <div class="stat">not_late target<b>${{result.not_late_median_pct.toFixed(2)}}%</b></div>
    <div class="stat">Stock value (median)<b>${{fmtTHB(result.stock_value_median)}}</b></div>
    <div class="stat">Stock value band (min–max)<b>${{fmtTHB(result.stock_value_min)}} – ${{fmtTHB(result.stock_value_max)}}</b></div>
    <div class="stat">Change vs today's on-hand<b style="color:${{diff>=0?'#c0392b':'#1baf7a'}}">${{diff>=0?'+':''}}${{fmtTHB(diff)}} (${{diffPct>=0?'+':''}}${{diffPct.toFixed(1)}}%)</b></div>
  `;

  // task 2b Part 3 (METRICS.md Sec.24): ratio_e across the 80 distinct members, at THIS target,
  // relative to today's REAL not_late (state.rsc.today_not_late_pct) -- never each member's own
  // simulated-at-today point (Sec.24's own reasoning: the unidentifiable reorder level cancels
  // WITHIN a member's ratio of two points on its own curve).
  const rscNote = document.getElementById('relative-service-cost-note');
  const ratio = interpolateRatioGrid(state.rsc, result.not_late_median_pct);
  if (!ratio) {{
    rscNote.innerHTML = htmlComment('METRICS.md §24 relative_service_cost') +
      'ต้องเพิ่ม stock กี่ % เพื่อไปถึงเป้าที่เลือก: ไม่มีข้อมูลสมาชิก ensemble ที่ครอบคลุมเป้าหมายนี้ (นอกช่วงที่คำนวณไว้)';
  }} else {{
    const pct = v => (100 * (v - 1));
    const sg = v => (v >= 0 ? '+' : '\u2212');      // + or the minus sign, so a range crossing zero reads correctly
    const signed = v => sg(pct(v)) + Math.abs(pct(v)).toFixed(1);
    const magnitude = v => Math.abs(pct(v)).toFixed(1);
    const ratioBandPctOfMedian = ratio.median ? 100 * (ratio.max - ratio.min) / ratio.median : null;
    const absBandPctOfMedian = result.stock_value_median ? 100 * (result.stock_value_max - result.stock_value_min) / result.stock_value_median : null;
    const narrower = (ratioBandPctOfMedian !== null && absBandPctOfMedian !== null && ratioBandPctOfMedian < absBandPctOfMedian);
    const bandNote = (ratioBandPctOfMedian === null || absBandPctOfMedian === null) ? ''
      : narrower
        ? ` <span style="color:#1baf7a">ช่วงของอัตราส่วนนี้ (${{ratioBandPctOfMedian.toFixed(1)}}% ของค่ากลาง) แคบกว่าช่วงมูลค่า stock สัมบูรณ์ด้านบน (${{absBandPctOfMedian.toFixed(1)}}%) — เชื่อถือได้มากกว่า</span>`
        : ` <span style="color:#c0392b">ช่วงของอัตราส่วนนี้ (${{ratioBandPctOfMedian.toFixed(1)}}% ของค่ากลาง) ไม่แคบกว่าช่วงมูลค่า stock สัมบูรณ์ (${{absBandPctOfMedian.toFixed(1)}}%) — ห้ามนำเสนอว่าแน่นอนกว่า</span>`;
    const today = state.rsc.today_not_late_pct, target = result.not_late_median_pct.toFixed(2);
    // Two approved sentences, chosen by the sign of the median ratio.
    const sentence = pct(ratio.median) >= 0
      ? `ต้องเพิ่ม stock +${{magnitude(ratio.median)}}% (ช่วง ${{signed(ratio.min)}}% ถึง ${{signed(ratio.max)}}%) เพื่อขยับการส่งไม่ช้าจาก ${{today}}% เป็น ${{target}}%`
      : `ลด stock ได้ ${{magnitude(ratio.median)}}% (ช่วง ${{signed(ratio.min)}}% ถึง ${{signed(ratio.max)}}%) ถ้ายอมให้การส่งไม่ช้าลดจาก ${{today}}% เป็น ${{target}}%`;
    rscNote.innerHTML = htmlComment('METRICS.md §24 relative_service_cost') + sentence + bandNote;
  }}

  const tbody = document.getElementById('curve-item-table-body');
  tbody.innerHTML = '';
  for (const it of result.items) {{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{it.code}}</td><td>${{Math.round(it.Min).toLocaleString()}}</td>` +
      `<td>${{Math.round(it.Max_median).toLocaleString()}}</td>` +
      `<td>${{Math.round(it.Max_min).toLocaleString()}} – ${{Math.round(it.Max_max).toLocaleString()}}</td>`;
    tbody.appendChild(tr);
  }}

  plotSafe('chart-robust-curve', () => Plotly.react('chart-robust-curve', [
    {{ x: grid.map(g => g.not_late_median_pct), y: grid.map(g => g.stock_value_min), name: 'min stock_value', mode: 'lines', line: {{color:'#898781', dash:'dot'}} }},
    {{ x: grid.map(g => g.not_late_median_pct), y: grid.map(g => g.stock_value_median), name: 'median stock_value', mode: 'lines', line: {{color:'#2a78d6'}} }},
    {{ x: grid.map(g => g.not_late_median_pct), y: grid.map(g => g.stock_value_max), name: 'max stock_value', mode: 'lines', line: {{color:'#898781', dash:'dot'}} }},
    {{ x: [ct.today_point.not_late_pct], y: [ct.today_point.stock_value_thb], name: "today's point",
      mode: 'markers', marker: {{color:'#eb6834', size:12, symbol:'star'}} }},
    {{ x: [result.not_late_median_pct], y: [result.stock_value_median], name: 'selected target',
      mode: 'markers', marker: {{color:'#1baf7a', size:11, symbol:'diamond'}} }},
  ], {{ margin: {{t:40, l:90}}, xaxis: {{title: {{text: 'not_late (%)'}}}}, yaxis: {{title: {{text: 'Stock value (THB), median curve + band'}}}} }},
  {{responsive: true}}));
}}

function renderCurveTarget(divisionData) {{
  const section = document.getElementById('curve-target-section');
  const ct = divisionData.curve_target;
  if (!ct) {{ section.style.display = 'none'; curCurveTarget = null; return; }}
  section.style.display = '';
  curCurveTarget = {{ ct, grid: ct.grid, rsc: ct.relative_service_cost }};

  document.getElementById('curve-target-summary').innerHTML =
    `ใช้ชุดค่าที่เป็นไปได้ ${{ct.n_distinct_members}} ชุด · วันนี้ ส่งไม่ช้า ${{ct.today_point.not_late_pct}}% ` +
    `มูลค่า stock ${{Math.round(ct.today_point.stock_value_thb).toLocaleString()}} บาท` +
    htmlComment('previous English wording: N distinct ensemble members (deduplicated on reorder level, order-up-to level, review interval and replenishment lead time). Today point: not_late, stock value THB. Sources: METRICS.md Sec.22, ' + ct.source_report + '; today point: ' + ct.today_point.source) +
    `<br><span style="color:#b45309;">${{ct.item_set_note}}</span>` + htmlComment(ct.item_set_ref || '');

  const slider = document.getElementById('notlate-slider');
  slider.min = ct.not_late_range_pct[0];
  slider.max = ct.not_late_range_pct[1];
  slider.oninput = () => applyCurveTarget(parseFloat(slider.value));

  const p1 = ct.presets.today_lowest_stock, p2 = ct.presets.highest_at_today_stock, p3 = ct.presets.stretch_99pct;
  const b1 = document.getElementById('preset-today-lowest');
  b1.textContent = `Today's not_late, lowest stock (${{p1.not_late_pct.toFixed(2)}}%)`;
  b1.onclick = () => applyCurveTarget(p1.not_late_pct);
  const b2 = document.getElementById('preset-highest-at-today');
  b2.textContent = `Highest not_late at today's stock (${{p2.not_late_pct.toFixed(2)}}%)`;
  b2.onclick = () => applyCurveTarget(p2.not_late_pct);
  const b3 = document.getElementById('preset-stretch');
  b3.textContent = p3.capped ? `Stretch: curve's max (${{p3.not_late_pct.toFixed(2)}}%, 99% not reached)`
                              : `Stretch: 99% not_late`;
  b3.onclick = () => applyCurveTarget(p3.not_late_pct);

  applyCurveTarget(p1.not_late_pct);
}}

function parseYmdHm(s) {{
  // Parses 'YYYY-MM-DD HH:MM[:SS]' (this machine's own clock, ICT/UTC+7 -- confirmed this task
  // via `date`) into a JS Date; returns null if the string doesn't start with that pattern (e.g.
  // the PEM103/PEM107 '... (live pull, not a frozen file)' suffix is ignored for parsing).
  const m = /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}}) (\\d{{2}}):(\\d{{2}})/.exec(s || '');
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
}}

function renderPageTimestamps() {{
  // METRICS.md Sec.26 (page_timestamps) -- page_built_at/model_calibrated_at are constant for
  // the whole page (one build, one calibration run); data_pulled_at is per-division, set in
  // onDivisionChange() below since it differs by division (frozen file vs. live pull).
  const mc = DATA.model_calibrated_at;
  const builtShown = String(DATA.page_built_at).split(' -- ')[0];
  document.getElementById('page-timestamps-note').innerHTML =
    htmlComment('page_built_at; ' + String(DATA.page_built_at).slice(builtShown.length)) +
    '<b>หน้าสร้างเมื่อ:</b> ' + builtShown +
    ' &nbsp;|&nbsp; ' + htmlComment('model_calibrated_at') + '<b>ปรับให้ตรงกับผลจริงเมื่อ:</b> ' + mc.run_date + ' ICT (UTC+7), ' +
    'ข้อมูลถึงเดือน ' + mc.last_month_of_data + ' ' + htmlComment('source: ' + mc.source);
}}

function renderPem107Alert(division) {{
  // task 2b Part 4: alert banner, PEM107 view only. All figures come from DATA.pem107_alert,
  // computed at build time by src/investigations/task2b_part4_pem107_alert.py from Cube_CES --
  // nothing here is typed.
  const banner = document.getElementById('pem107-alert');
  const a = DATA.pem107_alert;
  if (division !== 'PEM107' || !a) {{ banner.style.display = 'none'; return; }}
  banner.style.display = 'block';

  const fmtPct = v => (v === null || v === undefined) ? 'n/a' : v.toFixed(1) + '%';
  document.getElementById('pem107-alert-headline').innerHTML =
    `<b>not_late (unit-weighted, Omni Channel) ก่อน ${{a.split_date}}: ${{fmtPct(a.not_late_before_may_2026_pct)}}</b> ` +
    `(n=${{a.units_before_may_2026.toLocaleString()}} ชิ้น, ตั้งแต่ ${{a.before_window_start}}) ` +
    `&rarr; <b>ตั้งแต่ ${{a.split_date}}: ${{fmtPct(a.not_late_from_may_2026_pct)}}</b> ` +
    `(n=${{a.units_from_may_2026.toLocaleString()}} ชิ้น)`;

  const tbody = document.getElementById('pem107-alert-table-body');
  tbody.innerHTML = '';
  const byType = {{}};
  for (const it of a.items) {{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{it.product_type ?? '-'}}</td><td>${{it.product_description ?? '-'}}</td><td>${{it.product_code}}</td>` +
      `<td>${{Math.round(it.units_ordered_from_may).toLocaleString()}}</td>` +
      `<td>${{Math.round(it.units_late).toLocaleString()}}</td>` +
      `<td>${{fmtPct(it.not_late_from_may_pct)}}</td><td>${{fmtPct(it.not_late_before_may_pct)}}</td>` +
      `<td>${{fmtPct(it.share_of_all_late_units_pct)}}</td>`;
    tbody.appendChild(tr);
    byType[it.product_type] = byType[it.product_type] || {{ord:0, late:0}};
    byType[it.product_type].ord += it.units_ordered_from_may;
    byType[it.product_type].late += it.units_late;
  }}
  for (const [type, sub] of Object.entries(byType)) {{
    const tr = document.createElement('tr');
    tr.style.fontWeight = '700'; tr.style.background = '#f7e0de';
    tr.innerHTML = `<td colspan="3">Subtotal: ${{type ?? '-'}}</td>` +
      `<td>${{Math.round(sub.ord).toLocaleString()}}</td><td>${{Math.round(sub.late).toLocaleString()}}</td>` +
      `<td colspan="3"></td>`;
    tbody.appendChild(tr);
  }}

  document.getElementById('pem107-alert-source').innerHTML =
    `ข้อมูลดึงเมื่อ ${{a.data_pulled_at}}` +
    htmlComment('source: ' + a.source.pricelist + ' · ' + a.source.delivery + ' · ' + a.source.metric);
  const lbl = a.split_label;
  document.getElementById('pem107-alert-limitations').innerHTML =
    'ข้อจำกัด: ' + [
      `ก่อน ${{lbl}} ส่งไม่ช้า ${{a.not_late_before_may_2026_pct.toFixed(1)}}% จาก ${{a.units_before_may_2026.toLocaleString()}} ชิ้น`,
      `หลัง ${{lbl}} จำนวนยังน้อย (${{a.units_from_may_2026.toLocaleString()}} ชิ้น) ตัวเลขรายเดือนจึงแกว่งมาก`,
      'ยังไม่รู้สาเหตุที่ส่งทันลดลง',
      `ยังไม่ยืนยันว่า ${{lbl}} แยกอะไรออกจากกัน stock หรือสายการผลิต`,
    ].map(x => '&bull; ' + x).join('<br>') +
    htmlComment('previous English limitations: ' + (a.limitations_english || []).join(' | '));
}}

function onDivisionChange() {{
  currentDivision = document.getElementById('division-select').value;
  const divisionData = getDivisionData(currentDivision);
  document.getElementById('page-title').textContent = 'แผนสต็อค — Inventory Min/Max Scenario (' + currentDivision + ', ' + divisionData.n_items_label + ')';
  setTextWithRef('scope-note', divisionData.warehouse_scope_note, divisionData.warehouse_scope_ref);
  renderPem107Alert(currentDivision);
  const builtAt = parseYmdHm(DATA.page_built_at);
  const pulledAt = parseYmdHm(divisionData.snapshot_pull_date);
  let staleNote = '';
  if (builtAt && pulledAt) {{
    const ageDays = (builtAt - pulledAt) / 86400000;
    if (ageDays > DATA.staleness_threshold_days) {{
      staleNote = ' <span class="note-box" style="display:inline;padding:2px 8px;">&#9888; ข้อมูลเก่ากว่า ' + DATA.staleness_threshold_days + ' วัน (' +
        ageDays.toFixed(1) + ' วัน) เทียบกับหน้าสร้างเมื่อ</span>';
    }}
  }}
  // A trailing "(live pull, ...)" explanation stays off screen, in an HTML comment.
  const pullShown = String(divisionData.snapshot_pull_date).split(' (')[0];
  const pullNote = String(divisionData.snapshot_pull_date).slice(pullShown.length).trim();
  document.getElementById('snapshot-note').innerHTML =
    htmlComment('data_pulled_at') + '<b>ข้อมูลดึงเมื่อ:</b> ' + pullShown + ' ICT (UTC+7)' + (pullNote ? htmlComment(pullNote) : '') + staleNote;
  renderWarehouseChecklist(divisionData);
  renderNoPolicyTable(divisionData);
  renderCurveTarget(divisionData);
  onControlChange(true);
}}

function onControlChange(noFlash) {{
  const prevCells = noFlash === true ? null : snapshotCells();
  const controls = readControls();
  document.getElementById('val-procurement_lead_time_days').textContent = controls.procurement_lead_time_days + 'd';
  document.getElementById('val-assembly_time_days').textContent = controls.assembly_time_days + 'd';
  document.getElementById('val-review_interval_days').textContent = controls.review_interval_days + 'd';
  document.getElementById('val-cycle_service_level').textContent = controls.cycle_service_level.toFixed(2);
  document.getElementById('val-holding_cost_rate_annual').textContent = controls.holding_cost_rate_annual.toFixed(2);
  document.getElementById('val-obsolescence_threshold_months').textContent = controls.obsolescence_threshold_months + 'mo';

  const divisionData = getDivisionData(currentDivision);
  const checked = checkedWarehouseCodes();
  const result = computeAll(controls, divisionData, checked);
  document.getElementById('tot-stock-value').textContent = fmtTHB(result.stockValue);
  document.getElementById('tot-holding-cost').textContent = fmtTHB(result.holdingCost);
  document.getElementById('tot-n-items').textContent = result.perItem.filter(showsMinMax).length;
  document.getElementById('tot-excess-count').textContent = STOCK_OK ? result.excessCount : STOCK_UNKNOWN;
  renderTable(result.perItem);
  renderNoForecastTable(result.perItem);
  renderClassTable(result.perItem);
  renderTradeoff(controls, divisionData);
  renderMinVsCurrent(result.perItem);
  if (prevCells) flashChanged(prevCells);
}}

// Stock file (data/stock_daily.json): loaded once when the page opens, from the same site. Everything that does not
// depend on stock is drawn whether or not it loads; the stock figures then show STOCK_UNKNOWN and a message.
const STOCK_JSON_URL = {stock_json_url_js};
const STOCK_FAIL_MSG = 'โหลดข้อมูล stock ไม่ได้ · ตัวเลขอื่นในหน้านี้ยังใช้ได้ตามปกติ';
const STOCK_UNKNOWN = '–';
const THAI_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
let STOCK = null, STOCK_OK = false;

function thaiDateTime(s) {{
  // 'YYYY-MM-DD HH:MM[:SS]' (this machine's own clock, ICT) as d MMM yy HH:mm with the Buddhist year.
  const m = /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})[ T](\\d{{2}}):(\\d{{2}})/.exec(s || '');
  if (!m) return 'ไม่ทราบ';
  return Number(m[3]) + ' ' + THAI_MONTHS[Number(m[2]) - 1] + ' ' + String(Number(m[1]) + 543).slice(-2) + ' ' + m[4] + ':' + m[5];
}}

function loadStock(done) {{
  let finished = false;
  function finish(payload) {{
    if (finished) return;
    finished = true;
    STOCK_OK = !!payload;
    STOCK = payload || null;
    if (payload) applyStock(DATA, payload);
    done();
  }}
  const xhr = new XMLHttpRequest();
  xhr.onload = function() {{
    try {{
      if (!(xhr.status === 200 || (xhr.status === 0 && xhr.responseText))) throw new Error('status ' + xhr.status);
      const p = JSON.parse(xhr.responseText);
      if (p.format_version !== 1 || !p.items || typeof p.items !== 'object' || !p.pull_time || !p.stock_source_load_time) throw new Error('format');
      finish(p);
    }} catch (e) {{ finish(null); }}
  }};
  xhr.onerror = xhr.ontimeout = function() {{ finish(null); }};
  xhr.open('GET', STOCK_JSON_URL + '?t=' + Date.now());
  xhr.timeout = 15000;
  xhr.send();
}}

function renderStockLabels() {{
  const el = document.getElementById('stock-labels');
  el.style.display = '';
  if (!STOCK_OK) {{ el.textContent = STOCK_FAIL_MSG; return; }}
  const pull = parseYmdHm(STOCK.pull_time);
  function stale(t) {{
    const at = parseYmdHm(t);
    if (!pull || !at) return '';
    const age = (pull - at) / 86400000;
    return age > DATA.staleness_threshold_days
      ? ' <span style="color:#c0392b">&#9888; ข้อมูลเก่ากว่า ' + DATA.staleness_threshold_days + ' วัน (' + age.toFixed(1) + ' วัน) เทียบกับเวลาที่ดึง</span>' : '';
  }}
  el.innerHTML =
    '<span id="stock-label-stock">ข้อมูล stock ในระบบ ณ ' + thaiDateTime(STOCK.stock_source_load_time) + '</span>' + stale(STOCK.stock_source_load_time) + '<br>' +
    '<span id="stock-label-reserved">ยอดจองในระบบ ณ ' + thaiDateTime(STOCK.reserved_source_load_time) + '</span>' +
      (STOCK.reserved_source_load_time ? stale(STOCK.reserved_source_load_time) : '') + '<br>' +
    '<span id="stock-label-pulled">ดึงข้อมูลเมื่อ ' + thaiDateTime(STOCK.pull_time) + '</span>';
}}

function startPage() {{
  renderPageTimestamps();
  renderStockLabels();
  document.getElementById('division-select').value = DATA.default_division;
  if (window.matchMedia('(max-width: 899px)').matches) {{
    document.getElementById('control-panel').classList.add('collapsed');
    document.getElementById('panel-toggle').setAttribute('aria-expanded', 'false');
  }}
  onDivisionChange();
}}
loadStock(startPage);
</script>
</body>
</html>
"""
    return page


def main(**data_sources):
    os.makedirs(FORECAST_DIR, exist_ok=True)
    page = build_page(**data_sources)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    logger.info("Wrote %s (%d bytes)", OUT_PATH, len(page))
    return OUT_PATH


if __name__ == "__main__":
    main()
