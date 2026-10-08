"""Builds forecast/operation_plan.html, the production planners' page for operation plan v1 (week 2; METRICS.md Sec.42; six divisions from week 3).

Every number, date and item code on the page is computed here from the recorded plan (`operation_plan_v1_*`, read after its SHA-256 check), the
forward-test log (the run month of the forecast the plan used) and the price list (product names); nothing is typed. All Thai text is the approved
text of the 2026-10-06 tasks, used verbatim; braces in `TEXT` name the values `compute_values` fills. Where a reader would need Thai text that has not
been approved, the page shows a dash and the place is listed for the user's assistant (STATUS.md, week 3).

The split of stock-item production (METRICS.md Sec.42): per stock item and month, the part that meets demand is the smaller of planned production
and that month's demand, the refill part is the rest. It is computed here from the recorded plan; the plan itself is not changed. Items marked
no_production_in_system are listed with their demand and are not part of any total (the plan does not count them).
"""
import html
import json
import logging
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import operation_plan as op  # noqa: E402
import reader_values as rv  # noqa: E402

logger = logging.getLogger("build_operation_plan_page")
PAGE_RELATIVE = "forecast/operation_plan.html"
MATERIAL_PAGE_RELATIVE = "material_plan.html"        # linked from this page; both pages sit in forecast/
THAI_MONTHS = [rv.THAI_MONTH_ABBR[m] for m in range(1, 13)]   # the abbreviations the Min-Max page uses
CLASS_LABELS = {"stock_policy": "เก็บ stock", "confirmed_to_order": "ผลิตตามสั่ง", "conflict": "ยังไม่ชัด", "mixed": "ผสม (เก็บ stock บางส่วน)",
                "no_production_in_system": "ไม่พบการผลิตในระบบ", "too_little_data": "ข้อมูลไม่พอจัดประเภท"}
CLASS_ORDER = ["stock_policy", "confirmed_to_order", "conflict", "mixed", "too_little_data", "no_production_in_system"]
SHARE_OF_BACKLOG_ITEMS = 0.80          # the items shown reach this share of the sum (approved text of 2026-10-06)
MAX_BACKLOG_ITEMS = 3
DASH = "-"

# Approved Thai text, verbatim. {braces} are computed values.
TEXT = {
    "heading": "แผนการผลิต {n_months} เดือน · ทุกฝ่าย",
    "data_line": "ข้อมูล stock ดึงเมื่อ {pull_time} · ยอดทายรอบ {forecast_run_month}",
    "col_month": "เดือน", "col_demand": "ผลิตตามความต้องการ", "col_refill": "เติมให้ถึง Max", "col_mto": "ผลิตตามสั่ง", "col_total": "รวม",
    "col_capacity": "เทียบยอดผลิตสูงสุดที่เคยทำ", "above_capacity": "สูงกว่ายอดผลิตสูงสุดที่เคยทำ",
    "line_refill": "{first_month} PEM101 ต้องเติมให้ถึง Max {refill_units} หน่วย นอกเหนือจากความต้องการเดือนนั้น เพราะ stock ตอนนี้ต่ำกว่า Max ทยอยเติมในเดือนถัดไปได้",
    "line_backlog": "{first_month} PEM107 มีออเดอร์ที่รับแล้วสูงกว่ายอดทาย {backlog_above_forecast} หน่วย ส่วนใหญ่จาก {top_backlog_items}",
    "line_capacity": "ยอดผลิตสูงสุดที่เคยทำ คือยอดผลิตเสร็จต่อเดือนสูงสุดในอดีต นับทุกสินค้ารวมกันโดยไม่แยกขนาด ใช้ดูทิศทาง ไม่ได้แปลว่าเป็นกำลังผลิตเต็มที่",
    "line_no_stock": "{division} ไม่มีสินค้าที่เข้าเกณฑ์เก็บ stock แผนจึงเป็นการผลิตตามความต้องการทั้งหมด",
    "line_no_forecast": "{n} รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้มีออเดอร์ค้าง {k} รหัส",
    "line_no_forecast_no_orders": "{n} รหัสยังไม่มียอดทาย แผนนับเฉพาะออเดอร์ที่รับแล้ว ตอนนี้ไม่มีออเดอร์ค้างในกลุ่มนี้",
    "line_no_production": "{n} รหัสไม่พบการผลิตในระบบ ไม่นับเป็นภาระผลิต",
    "line_never_sold": "{division} {n} รหัสอยู่ใน Price List แต่ไม่เคยขาย ไม่อยู่ในแผน",
    "line_pem103": "PEM103 นับเฉพาะยอด Omni Channel งานประมูลไม่อยู่ในแผนนี้",
    "units": "หน่วย", "and": " และ ",
    "item_cols": ["รหัส", "ชื่อสินค้า", "ประเภท", "stock ตอนนี้", "Min", "Max"],
    "filter_division": "ฝ่าย", "filter_all": "ทั้งหมด",
    "stock_note": "stock ตอนนี้ แสดงเฉพาะสินค้าเก็บ stock",
    "flag_inconsistent": "ข้อมูลไม่สอดคล้อง",
    "flag_inconsistent_tip": "ประเภทที่บันทึกในระบบขัดกับวิธีส่งจริง ใช้วิธีส่งจริงตัดสิน",
    "no_production_note": "แถวที่ขึ้นว่า ไม่พบการผลิตในระบบ ตัวเลขรายเดือนคือความต้องการ ไม่ได้รวมในยอดผลิตของฝ่าย",
    "back_link": "← กลับไปหน้าหลัก (Dashboard)",       # wording of the same link on the Min-Max page
}


# ------------------------------------------------------------------ formats
def thai_month(ym: str) -> str:
    """'2026-10' -> 'ต.ค. 69' (the shared formatter, src/reader_values.py: Thai month abbreviation, Buddhist year as two digits, as the Min-Max page writes dates)."""
    return rv.thai_month_short(ym)


def thai_datetime(s: str) -> str:
    """'2026-10-06 08:00:40' -> '6 ต.ค. 69 08:00' (the shared formatter, src/reader_values.py: d MMM yy HH:mm, Buddhist year)."""
    return rv.thai_datetime_short(s)


def fmt_units(x: float) -> str:
    return f"{int(round(float(x))):,}"


def fmt_cell(x: float) -> str:
    """Item-table month value: whole units from 10 up, one decimal below, a hyphen for none."""
    x = float(x)
    if abs(x) < 1e-9:
        return "-"
    return f"{x:,.1f}" if abs(x) < 10 else f"{int(round(x)):,}"


def fmt_pct(x: float) -> str:
    return DASH if pd.isna(x) else f"{100 * float(x):.1f}%"


def join_items(parts: list) -> str:
    """One item as is; two joined by ' และ '; three as 'a, b และ c'."""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + TEXT["and"] + parts[1]
    return ", ".join(parts[:-1]) + TEXT["and"] + parts[-1]


# ------------------------------------------------------------------ the split and the braced values
def split_production(production, demand):
    """Per stock item and month: (part that meets demand, refill part) = (min(production, demand), production - that). Works on numbers or arrays."""
    meets = np.minimum(production, demand)
    return meets, production - meets


def top_backlog_items(excess: pd.Series) -> list:
    """The items (code, units) contributing most to the sum, in descending order, until together they reach 80 percent of it, at most three."""
    e = excess[excess > 1e-9].sort_values(ascending=False, kind="mergesort")
    total, picked, run = float(e.sum()), [], 0.0
    for code, v in e.items():
        picked.append((code, float(v)))
        run += float(v)
        if run >= SHARE_OF_BACKLOG_ITEMS * total - 1e-9 or len(picked) == MAX_BACKLOG_ITEMS:
            break
    return picked


def compute_values(item_month: pd.DataFrame, division_month: pd.DataFrame, meta: dict, names: dict, forecast_run_date: str, divisions: list) -> dict:
    """Every value the page shows. `item_month`, `division_month`, `meta` are the recorded plan (read back), `names` maps item code to product name,
    `forecast_run_date` is the forecast vintage's run date, `divisions` the divisions in the order shown. The summary total must equal the recorded
    division-month total (checked); rows of items the plan does not count are in the item table but in no total."""
    months = list(meta["months"])
    first = months[0]
    im = item_month.copy()
    im["counted"] = im["counted"].astype(bool)
    a = im["planned_production"].notna()
    im["meets_demand"] = np.nan
    im["refill"] = np.nan
    meets, refill = split_production(im.loc[a, "planned_production"].to_numpy(), im.loc[a, "demand"].to_numpy())
    im.loc[a, "meets_demand"], im.loc[a, "refill"] = meets, refill
    cnt = im[im["counted"]]
    rows = []
    for d in divisions:
        for m in months:
            s = cnt[(cnt["division"] == d) & (cnt["month"] == m)]
            rec = division_month[(division_month["division"] == d) & (division_month["month"] == m)].iloc[0]
            demand_part, refill_part, mto = float(s["meets_demand"].sum()), float(s["refill"].sum()), float(s["load"].sum())
            total = demand_part + refill_part + mto
            if abs(total - float(rec["total_load"])) > 1e-3:
                raise op.OperationPlanError(f"{d} {m}: the page total {total} differs from the recorded division-month total {rec['total_load']}")
            cap = rec["capacity"]
            rows.append({"division": d, "month": m, "demand_part": demand_part, "refill_part": refill_part, "mto": mto, "total": total,
                         "capacity": None if pd.isna(cap) else float(cap), "share": None if pd.isna(cap) else total / float(cap), "above": bool(rec["above_capacity"])})
    summary = pd.DataFrame(rows)
    refill_first = float(cnt[(cnt["division"] == "PEM101") & (cnt["month"] == first)]["refill"].sum())
    p107 = cnt[(cnt["division"] == "PEM107") & (cnt["month"] == first)].set_index("item")
    excess = (p107["backlog_due"] - p107["forecast"]).clip(lower=0)
    picked = top_backlog_items(excess)
    items = []
    for (d, item), s in im.groupby(["division", "item"], sort=False):
        s = s.set_index("month").reindex(months)
        cls = s["class"].iloc[0]
        stock = cls == "stock_policy" and bool(s["min"].notna().iloc[0])
        items.append({"division": d, "item": item, "name": names.get(item, ""), "class": cls, "label": s["class_label"].iloc[0],
                      "inconsistent": bool(s["data_inconsistent"].iloc[0]), "counted": bool(s["counted"].iloc[0]),
                      "stock_now": float(s["opening"].iloc[0]) if stock else None,
                      "min": float(s["min"].iloc[0]) if stock else None, "max": float(s["max"].iloc[0]) if stock else None,
                      "months": [float(s["planned_production"].iloc[i]) if stock else float(s["load"].iloc[i]) for i in range(len(months))]})
    items.sort(key=lambda r: (divisions.index(r["division"]), CLASS_ORDER.index(r["label"]), -sum(r["months"]), r["item"]))
    counts = meta["counts"]
    # Items without a forecast, per division, that have a positive received-order quantity (backlog_due, the confirmed quantity due in the plan's months,
    # from the plan's own item-month input) in the plan's horizon.
    nf = im[im["status_category"] != "forecast"]
    with_orders = nf.groupby(["division", "item"])["backlog_due"].sum().gt(0)
    no_forecast_with_orders = {d: int(with_orders.loc[d].sum()) if d in with_orders.index.get_level_values(0) else 0 for d in divisions}
    division_lines = {}
    for d in divisions:
        lines = []
        if counts["stock_items_by_division"][d] == 0:
            lines.append(TEXT["line_no_stock"].format(division=d))
        if counts["no_forecast_items_by_division"][d] > 0:
            k = no_forecast_with_orders[d]
            lines.append((TEXT["line_no_forecast"] if k > 0 else TEXT["line_no_forecast_no_orders"]).format(n=counts["no_forecast_items_by_division"][d], k=k))
        if counts["no_production_items_by_division"][d] > 0:
            lines.append(TEXT["line_no_production"].format(n=counts["no_production_items_by_division"][d]))
        if counts.get("never_sold_items_by_division", {}).get(d, 0) > 0:
            lines.append(TEXT["line_never_sold"].format(division=d, n=counts["never_sold_items_by_division"][d]))
        if d == "PEM103":
            lines.append(TEXT["line_pem103"])
        division_lines[d] = lines
    values = {
        "n_months": len(months), "months": months, "divisions": divisions,
        "month_labels": [thai_month(m) for m in months],
        "pull_time": thai_datetime(meta["stock_pull"]["pulled_at_local"]),
        "forecast_run_month": thai_month(str(forecast_run_date)[:7]),
        "first_month": thai_month(first),
        "refill_units": fmt_units(refill_first), "refill_first": refill_first,
        "backlog_above_forecast": fmt_units(excess.sum()), "backlog_above_forecast_value": float(excess.sum()),
        "top_backlog_items": join_items([f"{c} ({fmt_units(v)} {TEXT['units']})" for c, v in picked]) if picked else "",
        "top_backlog_picked": picked, "summary": summary, "items": items, "division_lines": division_lines, "no_forecast_with_orders": no_forecast_with_orders,
    }
    return values


# ------------------------------------------------------------------ rendering
CSS = """
  :root { color-scheme: light; --page: #f9f9f7; --surface: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
    --gridline: #e1e0d9; --border: rgba(11,11,11,0.10); --series-1: #2a78d6; --series-2: #eb6834; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--page); color:var(--text-primary); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size:14px; line-height:1.6; }
  .wrap { max-width: 1440px; margin: 0 auto; padding: 20px 20px 80px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 17px; margin: 24px 0 8px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  p.scope-note { font-size: 12px; color: var(--muted); margin: 2px 0 10px; }
  p.note-line { font-size: 12.5px; color: var(--text-secondary); background: #eef4fb; border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; margin: 6px 0; }
  p.table-note { font-size: 12px; color: var(--muted); margin: 2px 0 12px; }
  a.back-link, a.page-link { color: var(--series-1); text-decoration: none; font-size: 13px; }
  .links { display: flex; gap: 18px; flex-wrap: wrap; margin: 4px 0 8px; }
  .table-scroll { overflow-x: auto; max-width: 100%; }
  .report-table { width:100%; border-collapse: collapse; font-size: 12.5px; margin: 6px 0 16px; }
  .report-table th, .report-table td { border: 1px solid var(--border); padding: 5px 7px; text-align: right; white-space: nowrap; }
  .report-table th:first-child, .report-table td:first-child { text-align: left; }
  .report-table thead th { background: #f0efec; }
  .report-table td.name, .report-table th.name, .report-table td.kind, .report-table th.kind { text-align: left; white-space: normal; }
  .flag { color: #8f2b2b; font-weight: 700; margin-left: 6px; white-space: nowrap; }
  .flag.tip { cursor: help; border-bottom: 1px dotted #8f2b2b; }
  tr.above td { background: #fdecea; }
  .filters { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin: 14px 0 6px; }
  .filters select { font-size: 14px; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--border); }
  @media (max-width: 899px) { .wrap { padding: 12px 12px 60px; } }
""" + rv.NAV_CSS

JS = """
function applyFilters() {
  const d = document.getElementById('filter-division').value, c = document.getElementById('filter-class').value;
  document.querySelectorAll('#item-table-body tr').forEach(function(r) {
    r.style.display = ((d === 'all' || r.dataset.division === d) && (c === 'all' || r.dataset.class === c)) ? '' : 'none';
  });
}
document.getElementById('filter-division').onchange = applyFilters;
document.getElementById('filter-class').onchange = applyFilters;
applyFilters();
"""


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def render(values: dict) -> str:
    """The page as one HTML string. Reader-facing text is the approved text; comments hold what must stay off screen."""
    T, v = TEXT, values
    divisions = v["divisions"]
    parts = []
    parts.append(f'<a class="back-link" href="../index.html">{_e(T["back_link"])}</a>')
    parts.append(rv.nav_bar_html("operation"))
    heading = T["heading"].format(n_months=v["n_months"])
    parts.append(f'<h1 id="page-title">{_e(heading)}</h1>')
    parts.append(f'<p class="scope-note" id="data-line">{_e(T["data_line"].format(pull_time=v["pull_time"], forecast_run_month=v["forecast_run_month"]))}</p>')
    for d in divisions:
        parts.append(f'<h2>{d}</h2>')
        head = "".join(f"<th>{_e(T[k])}</th>" for k in ("col_month", "col_demand", "col_refill", "col_mto", "col_total", "col_capacity"))
        body = []
        for _, r in v["summary"][v["summary"]["division"] == d].iterrows():
            flag = f'<span class="flag">{_e(T["above_capacity"])}</span>' if r["above"] else ""
            body.append(f'<tr{" class=above" if r["above"] else ""} data-division="{d}" data-month="{r["month"]}"><td>{_e(thai_month(r["month"]))}</td>'
                        f'<td>{fmt_units(r["demand_part"])}</td><td>{fmt_units(r["refill_part"])}</td><td>{fmt_units(r["mto"])}</td>'
                        f'<td>{fmt_units(r["total"])}</td><td>{fmt_pct(r["share"])}{flag}</td></tr>')
        parts.append(f'<div class="table-scroll"><table class="report-table summary-table" id="summary-{d}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')
        parts.append("".join(f'<p class="note-line division-line" data-division="{d}">{_e(l)}</p>' for l in v["division_lines"][d]))
    lines = []
    if v["refill_first"] >= 0.5:
        lines.append(T["line_refill"].format(first_month=v["first_month"], refill_units=v["refill_units"]))
    if v["backlog_above_forecast_value"] >= 0.5:
        lines.append(T["line_backlog"].format(first_month=v["first_month"], backlog_above_forecast=v["backlog_above_forecast"],
                                              top_backlog_items=v["top_backlog_items"]))
    lines.append(T["line_capacity"])
    parts.append("".join(f'<p class="note-line">{_e(l)}</p>' for l in lines))
    div_opts = f'<option value="all">{_e(T["filter_all"])}</option>' + "".join(f'<option value="{d}">{d}</option>' for d in divisions)
    class_opts = f'<option value="all">{_e(T["filter_all"])}</option>' + "".join(f'<option value="{c}">{_e(CLASS_LABELS[c])}</option>' for c in CLASS_ORDER)
    parts.append(f'<div class="filters"><label>{_e(T["filter_division"])} <select id="filter-division">{div_opts}</select></label>'
                 f'<label>{_e(T["item_cols"][2])} <select id="filter-class">{class_opts}</select></label></div>')
    cols = T["item_cols"]
    th = "".join(f'<th class="{"name" if i == 1 else ("kind" if i == 2 else "")}">{_e(c)}</th>' for i, c in enumerate(cols)) + \
        "".join(f"<th>{_e(l)}</th>" for l in v["month_labels"])
    rows = []
    for it in v["items"]:
        flag = f'<span class="flag tip" title="{_e(T["flag_inconsistent_tip"])}">{_e(T["flag_inconsistent"])}</span>' if it["inconsistent"] else ""
        cells = [f'<td>{_e(it["item"])}</td>', f'<td class="name">{_e(it["name"])}</td>', f'<td class="kind">{_e(CLASS_LABELS[it["label"]])}{flag}</td>',
                 f'<td>{fmt_units(it["stock_now"]) if it["stock_now"] is not None else ""}</td>',
                 f'<td>{fmt_cell(it["min"]) if it["min"] is not None else ""}</td>', f'<td>{fmt_cell(it["max"]) if it["max"] is not None else ""}</td>']
        cells += [f"<td>{fmt_cell(x)}</td>" for x in it["months"]]
        rows.append(f'<tr data-division="{it["division"]}" data-class="{it["label"]}">{"".join(cells)}</tr>')
    parts.append(f'<div class="table-scroll"><table class="report-table" id="item-table"><thead><tr>{th}</tr></thead><tbody id="item-table-body">{"".join(rows)}</tbody></table></div>')
    parts.append(f'<p class="table-note" id="stock-note">{_e(T["stock_note"])}</p>')
    parts.append(f'<p class="table-note" id="no-production-note">{_e(T["no_production_note"])}</p>')
    comment = ("<!-- Source: the recorded operation plan (output/summary/operation_plan_v1_*, SHA-256 checked) and its split of stock-item production "
               "(METRICS.md Sec.42); product names from the price list; classes and flags from the Sec.23 item-level file; month columns hold planned "
               "production for stock items and the made-to-order load for the others; stock ตอนนี้, Min and Max are blank where the plan has none; items "
               "marked no_production_in_system are listed with their demand and are in no total; six PEM101 codes listed in the price list but never sold "
               "are not in the plan (the page says how many per division). -->")
    return (f'<!DOCTYPE html>\n<html lang="th">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{_e(heading)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n{comment}\n<div class="wrap">\n' + "\n".join(parts) +
            f'\n</div>\n<script>{JS}</script>\n</body>\n</html>\n')


# ------------------------------------------------------------------ inputs
def forecast_run_date(root: str, cfg: dict, vintage_id: int) -> str:
    """The run date of the vintage the plan used, from the forward-test log (read as scoring reads it)."""
    import forward_test_common as ftc
    log = ftc.read_forward_test_log(op.path_of(root, cfg["forecast_log_file"]))
    dates = sorted(set(log.loc[log["vintage_id"] == int(vintage_id), "forecast_run_date"]))
    if len(dates) != 1:
        raise op.OperationPlanError(f"vintage {vintage_id} has {len(dates)} run dates in the log: {dates}")
    return dates[0]


def product_names(root: str) -> dict:
    """Item code to product name from the price list (visible sheets; the first row of a repeated code)."""
    from pricelist_reader import load_visible_product_rows
    p = os.path.join(root, "reference", "pricelist.xlsx")
    if not os.path.exists(p):
        raise op.OperationPlanError(f"the price list is missing: {p}")
    df = load_visible_product_rows(p).drop_duplicates("code")
    return {c: " ".join(str(n).split()) if pd.notna(n) else "" for c, n in zip(df["code"], df["description"])}


def build_values(root: str = PROJECT_ROOT, out_dir: str = None) -> dict:
    cfg = op.load_config(root)
    im, dm, meta = op.read_outputs(root, cfg, out_dir)
    return compute_values(im, dm, meta, product_names(root), forecast_run_date(root, cfg, meta["vintage_id"]), list(cfg["divisions"]))


def build_page(root: str = PROJECT_ROOT, out_dir: str = None, out_path: str = None) -> str:
    """Builds the page from the recorded plan under `root` (outputs in `out_dir` when given) and writes it to `out_path` (default
    forecast/operation_plan.html under root). Returns the path."""
    page = render(build_values(root, out_dir))
    out_path = out_path or os.path.join(root, *PAGE_RELATIVE.split("/"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    logger.info("Wrote %s (%d bytes)", out_path, len(page))
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(build_page())
