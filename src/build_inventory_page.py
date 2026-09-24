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

// METRICS.md Sec.6/9: stock_value = Sum(Min x unit_cost) over finished_goods_stock items with a
// usable unit_cost. months_of_cover = on_hand_sellable / mean monthly forecast (protection-period
// horizon mean, Inf when forecast=0). holding_cost = stock_value x holding_cost_rate_annual.
// Takes divisionData explicitly (not a module-level DATA.items) so the SAME function serves
// whichever division is currently selected.
function computeAll(controls, divisionData) {
  let stockValue = 0;
  const perItem = [];
  for (const item of divisionData.items) {
    const r = computeItemMinMax(item, controls);
    const inFg = item.policy === 'finished_goods_stock';
    const contribution = (inFg && !item.no_unit_cost_item && r.min !== null) ? r.min * item.unit_cost : 0;
    if (inFg) stockValue += contribution;
    const monthsOfCover = (r.meanMonthlyForecast && r.meanMonthlyForecast > 0)
      ? item.on_hand_sellable / r.meanMonthlyForecast : Infinity;
    perItem.push({ code: item.code, policy: item.policy, min: r.min, max: r.max,
                   stockValueContribution: contribution, monthsOfCover, unreliable: r.unreliable,
                   currentMin: item.current_min, currentMax: item.current_max,
                   unitCost: item.unit_cost, noUnitCost: item.no_unit_cost_item });
  }
  const holdingCost = stockValue * controls.holding_cost_rate_annual;
  return { stockValue, holdingCost, perItem };
}
if (typeof module !== 'undefined') { module.exports = { computeLTD, rollingWindowSums, percentile, computeItemMinMax, computeAll, DATA }; }
// END_RECOMPUTE_JS
"""


def build_page() -> str:
    data = build_data()
    if not data.get("divisions"):
        raise InventoryPageError("build_inventory_page_data.build_data() returned zero divisions -- "
                                  "refusing to render a page with nothing to show.")
    for div in data["division_order"]:
        if not data["divisions"].get(div, {}).get("items"):
            raise InventoryPageError(f"Division {div} has zero embedded items -- refusing to render "
                                      f"a page with an empty enabled division.")
    data_json = json.dumps(data)

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
        slider("obsolescence_threshold_months", "Obsolescence threshold (months)", 1, "mo"),
    ])

    division_options = "".join(
        f'<option value="{d}">{d} ({len(data["divisions"][d]["items"])} รายการ)</option>'
        for d in data["division_order"]
    ) + "".join(
        f'<option value="{d}" disabled title="{html.escape(reason)}">{d} — excluded</option>'
        for d, reason in data["disabled_divisions"].items()
    )
    disabled_notes = "".join(
        f'<li><b>{html.escape(d)}</b> (disabled): {html.escape(reason)}</li>'
        for d, reason in data["disabled_divisions"].items()
    )

    page = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
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
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px 80px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; margin: 32px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  p.hint, p.scope-note {{ font-size: 12px; color: var(--muted); }}
  p.note-box {{ font-size: 12.5px; color: var(--text-secondary); background: #eef4fb;
    border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }}
  a.back-link {{ color: var(--series-1); text-decoration: none; font-size: 13px; }}
  .plotly-chart {{ width:100%; min-height: 320px; margin: 6px 0 14px; }}
  .division-panel {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin: 10px 0; }}
  .division-panel select {{ font-size: 14px; padding: 5px 8px; border-radius: 6px; border:1px solid var(--border); }}
  ul.disabled-note-list {{ font-size: 12px; color: var(--muted); margin: 4px 0 0; padding-left: 18px; }}
  .ctrl-panel {{ display:grid; grid-template-columns: repeat(2, 1fr); gap: 10px 24px;
    background:#f0efec; border-radius:8px; padding:14px 16px; margin: 10px 0 18px; }}
  .ctrl-row label {{ font-size: 13px; }}
  .ctrl-row input[type=range] {{ width: 100%; }}
  .item-check-list {{ display:flex; gap:10px; flex-wrap:wrap; margin: 6px 0; }}
  label.item-check {{ background:#fff; border:1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-size:12.5px; }}
  .report-table {{ width:100%; border-collapse: collapse; font-size: 12.5px; margin: 6px 0 16px; }}
  .report-table th, .report-table td {{ border: 1px solid var(--border); padding: 5px 7px; text-align: right; }}
  .report-table th:first-child, .report-table td:first-child {{ text-align: left; }}
  .report-table thead th {{ background: #f0efec; cursor: pointer; }}
  .report-table .total-row td {{ font-weight: 700; background: #f0efec; }}
  .totals-box {{ display:flex; gap:24px; flex-wrap:wrap; font-size:14px; margin: 10px 0; }}
  .totals-box .stat {{ background:#fff; border:1px solid var(--border); border-radius:6px; padding:10px 14px; }}
  .totals-box .stat b {{ display:block; font-size:18px; color: var(--series-1); }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back-link" href="../index.html">&larr; กลับไปหน้าหลัก (Dashboard)</a>
  <h1 id="page-title">แผนสต็อค — Inventory Min/Max Scenario</h1>
  <div class="division-panel">
    <label for="division-select"><b>Division:</b></label>
    <select id="division-select" onchange="onDivisionChange()">{division_options}</select>
  </div>
  <ul class="disabled-note-list" id="disabled-note-list">{disabled_notes}</ul>
  <p class="scope-note" id="scope-note"></p>
  <p class="note-box"><b>หมายเหตุสำคัญ:</b> ตัวเลขในหน้านี้เป็น <b>ค่าสถานการณ์ (scenario values) ภายใต้สมมติฐานที่ระบุไว้เท่านั้น
    ไม่ใช่คำแนะนำการสั่งซื้อ (purchase recommendation)</b> — การเปลี่ยนตัวควบคุมด้านล่างเปลี่ยนเฉพาะสิ่งที่แสดงผล ไม่ใช่ตัวแบบพยากรณ์
    (Tier A). การเปลี่ยนแปลงเชิงโครงสร้าง (Tier B, เช่น segment_policy) ต้องแก้ไข <code>config.yaml</code> และรัน pipeline ใหม่.
    รายการ placeholder/excluded จะไม่มี Min/Max และไม่มีปริมาณสั่งซื้อ (purchase quantity) ใดๆ ทั้งสิ้น.
    <b>Sellable-warehouse list ของทุก division (รวม PEM101) เป็นสมมติฐานทางธุรกิจ ไม่ใช่ข้อเท็จจริงที่ยืนยันจากข้อมูล
    — ไม่มีฟิลด์ warehouse บนแถวยอดขายเลย จึงตรวจสอบทิศทางย้อนกลับไม่ได้ (STATUS.md, Phase E2 Part 1).</b></p>
  <p class="note-box" id="proration-note"><b>หมายเหตุวิธีคำนวณ (methodology note):</b> ตัวเลขบนหน้านี้คำนวณจากข้อมูลย้อนหลัง
    <b>รายเดือน</b> ที่ฝังไว้ในหน้านี้ (monthly proration, METRICS.md Sec.4's explicit fallback) ไม่ใช่หน้าต่างข้อมูล
    <b>รายวัน</b> (daily window) ที่ใช้ใน pipeline ฝั่งเซิร์ฟเวอร์ — ที่ scenario ค่าเริ่มต้น ตัวเลข stock_value บนหน้านี้ต่างจากตัวเลขจาก
    pipeline ประมาณ <b>3.3%</b> สำหรับ PEM101 (สังเกตได้จากการรันจริง; PEM103/PEM107 ยังไม่ได้วัดค่านี้แยกต่างหาก).
    On this page, figures use <b>monthly proration</b> (METRICS.md Sec.4's documented fallback, since only monthly
    history is embedded here to keep page size reasonable) — NOT the <b>daily rolling window</b> the server-side
    pipeline uses.</p>

  <h2>Tier A — ตัวควบคุมสถานการณ์ (scenario tool — UNCALIBRATED, assumed mechanics; ปรับได้บนหน้านี้, ใช้ร่วมกันทุก division)</h2>
  <p class="hint">ตัวควบคุมด้านล่างใช้กลไก (mechanics) ที่<b>สมมติไว้</b>จาก METRICS.md Sec.5/16 (LTD + safety stock ตาม forecast) —
    ยังไม่ผ่านการ calibrate กับพฤติกรรมจริง ต่างจากส่วน &quot;PEM101 — Robust Ensemble&quot; ด้านล่าง ซึ่ง calibrate กับผลลัพธ์จริงแล้ว
    (METRICS.md Sec.20/22) — ห้ามใช้ตัวเลขจากส่วนนี้แทนส่วนที่ calibrate แล้ว.</p>
  <!-- source: config.yaml phase_e1_assumptions (defaults), segment_policy (Tier B, not editable here) -->
  <div class="ctrl-panel">
    {controls_html}
  </div>
  <p>คลังสินค้าที่นับเป็น sellable สำหรับ division ที่เลือก (เปลี่ยนตาม division):</p>
  <div class="item-check-list" id="warehouse-checklist"></div>

  <div id="robust-minmax-section" style="display:none;">
    <h2>PEM101 — Robust Ensemble (METRICS.md Sec.22) — <span style="color:#1baf7a;">PARTIALLY CALIBRATED</span></h2>
    <p class="note-box" id="robust-ensemble-summary"></p>
    <div id="chart-robust-curve" class="plotly-chart"></div>
    <p class="hint">Range ratio = max(Min)/min(Min) ข้าม ensemble; robust ถ้า range_ratio &le; 1.25 (แสดง median);
      sensitive ถ้า &gt; 1.25 (แสดงช่วงเต็ม และพารามิเตอร์ที่ทำให้เกิดช่วงนี้)</p>
    <table class="report-table" id="robust-item-table">
      <thead><tr>
        <th>Item</th><th>Range ratio</th><th>Badge (1.25)</th>
        <th>Min (median or range)</th><th>Max (median or range)</th><th>Driver (if sensitive)</th>
      </tr></thead>
      <tbody id="robust-item-table-body"></tbody>
    </table>
  </div>

  <h2>ผลรวม (Totals) — คำนวณใหม่ทุกครั้งที่เปลี่ยนตัวควบคุมหรือ division</h2>
  <div class="totals-box">
    <div class="stat">Stock value (Σ Min×unit_cost)<b id="tot-stock-value">-</b></div>
    <div class="stat">Holding cost (annual)<b id="tot-holding-cost">-</b></div>
    <div class="stat">Items with a Min/Max<b id="tot-n-items">-</b></div>
  </div>

  <h2>Trade-off: Stock value vs. Cycle Service Level</h2>
  <p class="hint">เส้นแสดง stock_value ที่ระดับ service level ต่างๆ (ค่าควบคุมอื่นคงที่ตามที่ตั้งไว้ด้านบน) สำหรับ division ที่เลือก</p>
  <div id="chart-tradeoff" class="plotly-chart"></div>

  <h2>Min เทียบกับค่าปัจจุบัน (current_min_max) — รายรายการ</h2>
  <div id="chart-min-vs-current" class="plotly-chart"></div>

  <h2>ตารางรายรายการ (เรียงตาม Value at Risk ได้)</h2>
  <p class="hint">Value at risk = max(0, current_min − scenario_min) × unit_cost — ค่าประมาณความเสี่ยงจากสต็อคปัจจุบันต่ำกว่าสถานการณ์นี้</p>
  <table class="report-table" id="item-table">
    <thead><tr>
      <th onclick="sortTable(0)">Item</th><th onclick="sortTable(1)">Policy</th>
      <th onclick="sortTable(2)">Min</th><th onclick="sortTable(3)">Max</th>
      <th onclick="sortTable(4)">Current Min</th><th onclick="sortTable(5)">Months of cover</th>
      <th onclick="sortTable(6)">Value at risk (THB)</th>
    </tr></thead>
    <tbody id="item-table-body"></tbody>
  </table>

  <h2>Placeholder / Excluded รายการ (ไม่มี Min/Max)</h2>
  <p class="hint">รายการเหล่านี้ไม่ได้รับ Min, Max หรือปริมาณสั่งซื้อใดๆ (placeholder_hierarchy_treatment) — ถ้าไม่มี แปลว่า division
    นี้ไม่มีแนวคิด placeholder/excluded (PEM103/PEM107)</p>
  <table class="report-table"><thead><tr><th>Item</th><th>Type</th><th>Policy</th></tr></thead>
  <tbody id="no-policy-table-body"></tbody></table>

  <p class="scope-note" id="snapshot-note"></p>
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

function renderTable(perItem) {{
  const tbody = document.getElementById('item-table-body');
  tbody.innerHTML = '';
  for (const r of perItem) {{
    const var_ = (r.currentMin && r.min !== null && r.unitCost) ? Math.max(0, r.currentMin - r.min) * r.unitCost : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{r.code}}</td><td>${{r.policy}}</td><td>${{r.min !== null ? Math.round(r.min).toLocaleString() : '-'}}</td>` +
      `<td>${{r.max !== null ? Math.round(r.max).toLocaleString() : '-'}}</td>` +
      `<td>${{r.currentMin !== null && r.currentMin !== undefined ? Math.round(r.currentMin).toLocaleString() : '-'}}</td>` +
      `<td>${{isFinite(r.monthsOfCover) ? r.monthsOfCover.toFixed(1) : '&#8734;'}}</td>` +
      `<td data-var="${{var_}}">${{fmtTHB(var_)}}</td>`;
    tbody.appendChild(tr);
  }}
}}

function renderNoPolicyTable(divisionData) {{
  const tbody = document.getElementById('no-policy-table-body');
  tbody.innerHTML = '';
  for (const it of (divisionData.no_policy_items || [])) {{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{it.code}}</td><td>${{it.type}}</td><td>${{it.policy}}</td>`;
    tbody.appendChild(tr);
  }}
}}

function renderWarehouseChecklist(divisionData) {{
  const el = document.getElementById('warehouse-checklist');
  el.innerHTML = '';
  for (const w of divisionData.sellable_warehouse_codes) {{
    const label = document.createElement('label');
    label.className = 'item-check';
    label.innerHTML = `<input type="checkbox" class="wh-check" value="${{w}}" checked onchange="onControlChange()"> ${{w}}`;
    el.appendChild(label);
  }}
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
  for (let s = 0.80; s <= 0.991; s += 0.02) slValues.push(Math.round(s * 100) / 100);
  const values = slValues.map(sl => computeAll({{...controls, cycle_service_level: sl}}, divisionData).stockValue);
  Plotly.newPlot('chart-tradeoff', [{{ x: slValues, y: values, mode: 'lines+markers', line: {{color: '#2a78d6'}} }}],
    {{ margin: {{t:10}}, xaxis: {{title: 'Cycle service level'}}, yaxis: {{title: 'Stock value (THB)'}} }},
    {{responsive: true}});
}}

function renderMinVsCurrent(perItem) {{
  const withCurrent = perItem.filter(r => r.min !== null && r.currentMin !== null && r.currentMin !== undefined);
  Plotly.newPlot('chart-min-vs-current', [
    {{ x: withCurrent.map(r => r.code), y: withCurrent.map(r => r.min), name: 'Scenario Min', type: 'bar', marker: {{color:'#2a78d6'}} }},
    {{ x: withCurrent.map(r => r.code), y: withCurrent.map(r => r.currentMin), name: 'Current Min', type: 'bar', marker: {{color:'#eda100'}} }}
  ], {{ margin: {{t:10}}, barmode: 'group', xaxis: {{tickangle: -60, tickfont:{{size:8}}}} }}, {{responsive: true}});
}}

function renderRobustMinMax(divisionData) {{
  const section = document.getElementById('robust-minmax-section');
  const rmm = divisionData.robust_minmax;
  if (!rmm) {{ section.style.display = 'none'; return; }}
  section.style.display = '';

  const perDef = Object.entries(rmm.ensemble_per_definition).map(([k, v]) => `${{k}}=${{v}}`).join(', ');
  document.getElementById('robust-ensemble-summary').innerHTML =
    `<b>Ensemble size: ${{rmm.ensemble_size}}</b> members (${{perDef}}, ${{rmm.ensemble_collapsed}} collapsed by dedup) — ` +
    `<b>${{rmm.n_robust_at_1_25}} robust</b> / <b>${{rmm.n_sensitive_at_1_25}} sensitive</b> at range_ratio&le;1.25. ` +
    `Usable-stock definition ${{rmm.stockdef_matters ? 'DOES' : 'does NOT'}} move PEM101's Min/Max range ` +
    `(see ${{rmm.source_report}}). Today's point: not_late ${{rmm.today_point.not_late_pct}}%, ` +
    `stock value ${{fmtTHB(rmm.today_point.stock_value_thb)}} (${{rmm.today_point.source}}).`;

  const tbody = document.getElementById('robust-item-table-body');
  tbody.innerHTML = '';
  for (const it of rmm.items) {{
    const badge = it.robust_at_1_25
      ? '<span style="color:#1baf7a;font-weight:700;">robust</span>'
      : '<span style="color:#eb6834;font-weight:700;">sensitive</span>';
    const minCell = it.robust_at_1_25 ? Math.round(it.median_Min).toLocaleString() + ' (median)'
      : Math.round(it.min_Min).toLocaleString() + ' – ' + Math.round(it.max_Min).toLocaleString();
    const maxCell = it.robust_at_1_25 ? Math.round(it.median_Max).toLocaleString() + ' (median)'
      : Math.round(it.min_Max).toLocaleString() + ' – ' + Math.round(it.max_Max).toLocaleString();
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${{it.code}}</td><td>${{it.range_ratio.toFixed(2)}}</td><td>${{badge}}</td>` +
      `<td>${{minCell}}</td><td>${{maxCell}}</td><td>${{it.driver_param || '-'}}</td>`;
    tbody.appendChild(tr);
  }}

  const env = rmm.envelope;
  const x = env.map(r => r.not_late_bin_pct);
  Plotly.newPlot('chart-robust-curve', [
    {{ x, y: env.map(r => r.min), name: 'min stock_value', mode: 'lines', line: {{color:'#898781', dash:'dot'}} }},
    {{ x, y: env.map(r => r.median), name: 'median stock_value', mode: 'lines', line: {{color:'#2a78d6'}} }},
    {{ x, y: env.map(r => r.max), name: 'max stock_value', mode: 'lines', line: {{color:'#898781', dash:'dot'}} }},
    {{ x: [rmm.today_point.not_late_pct], y: [rmm.today_point.stock_value_thb], name: "today's point",
       mode: 'markers', marker: {{color:'#eb6834', size:12, symbol:'star'}} }},
  ], {{ margin: {{t:10}}, xaxis: {{title: 'not_late (%)'}}, yaxis: {{title: 'Stock value (THB), envelope across ensemble'}} }},
  {{responsive: true}});
}}

function onDivisionChange() {{
  currentDivision = document.getElementById('division-select').value;
  const divisionData = getDivisionData(currentDivision);
  document.getElementById('page-title').textContent = 'แผนสต็อค — Inventory Min/Max Scenario (' + currentDivision + ', ' + divisionData.n_items_label + ')';
  document.getElementById('scope-note').textContent = divisionData.warehouse_scope_note;
  document.getElementById('snapshot-note').textContent = 'Snapshot pull date: ' + divisionData.snapshot_pull_date;
  renderWarehouseChecklist(divisionData);
  renderNoPolicyTable(divisionData);
  renderRobustMinMax(divisionData);
  onControlChange();
}}

function onControlChange() {{
  const controls = readControls();
  document.getElementById('val-procurement_lead_time_days').textContent = controls.procurement_lead_time_days + 'd';
  document.getElementById('val-assembly_time_days').textContent = controls.assembly_time_days + 'd';
  document.getElementById('val-review_interval_days').textContent = controls.review_interval_days + 'd';
  document.getElementById('val-cycle_service_level').textContent = controls.cycle_service_level.toFixed(2);
  document.getElementById('val-holding_cost_rate_annual').textContent = controls.holding_cost_rate_annual.toFixed(2);
  document.getElementById('val-obsolescence_threshold_months').textContent = controls.obsolescence_threshold_months + 'mo';

  const divisionData = getDivisionData(currentDivision);
  const result = computeAll(controls, divisionData);
  document.getElementById('tot-stock-value').textContent = fmtTHB(result.stockValue);
  document.getElementById('tot-holding-cost').textContent = fmtTHB(result.holdingCost);
  document.getElementById('tot-n-items').textContent = result.perItem.filter(r => r.policy === 'finished_goods_stock' && r.min !== null).length;
  renderTable(result.perItem);
  renderTradeoff(controls, divisionData);
  renderMinVsCurrent(result.perItem);
}}

document.getElementById('division-select').value = DATA.default_division;
onDivisionChange();
</script>
</body>
</html>
"""
    return page


def main():
    os.makedirs(FORECAST_DIR, exist_ok=True)
    page = build_page()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    logger.info("Wrote %s (%d bytes)", OUT_PATH, len(page))
    return OUT_PATH


if __name__ == "__main__":
    main()
