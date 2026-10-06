"""Builds forecast/material_plan.html, the buyers' page for material plan v1 (week 3; METRICS.md Sec.43).

Every number, date and code on the page is computed here from the recorded material plan (`material_plan_v1_*`, read after its SHA-256 check): the
materials, their stock, open orders, requirements, lead times and order dates. Product and material names come from the item master (Cube_ItemList) through the
plan's summary. All Thai text is the approved text of the 2026-10-06 task, used verbatim; braces in `TEXT` name the values `compute_values` fills.
Where a reader would need Thai text that has not been approved, the page shows a dash and the place is listed for the user's assistant (STATUS.md, week 3).
"""
import html
import logging
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import operation_plan as op  # noqa: E402
import material_plan as mp  # noqa: E402
from build_operation_plan_page import CSS, thai_month, thai_datetime, fmt_cell  # noqa: E402

logger = logging.getLogger("build_material_plan_page")
PAGE_RELATIVE = "forecast/material_plan.html"
DASH = "-"

# Approved Thai text, verbatim. {braces} are computed values.
TEXT = {
    "heading": "แผนวัตถุดิบ {n_months} เดือน",
    "data_line": "จากแผนการผลิตรอบ {plan_month} · stock วัตถุดิบดึงเมื่อ {pull_time}",
    "within_title": "ต้องสั่งภายใน {n_days} วัน",
    "within_line": "วัตถุดิบที่ต้องสั่งภายใน {n_days} วันข้างหน้า ถึงจะได้ของทันตามแผน",
    "late_title": "ขาดแล้ว สั่งตอนนี้ไม่ทัน",
    "late_line": "วัตถุดิบที่แผนต้องใช้ก่อนที่ของจะมาถึงแม้สั่งวันนี้ ควรตรวจของที่มีอยู่จริง หรือเร่งของที่สั่งไว้แล้ว",
    "now_cols": ["รหัสวัตถุดิบ", "ชื่อ", "ใช้ในสินค้า (รหัส)", "ต้องสั่งเพิ่ม", "ต้องสั่งภายใน", "lead time (วัน)", "ที่มา lead time"],
    "source": {"observed": "ใบสั่งซื้อจริง", "supplier_quoted": "ผู้ขายแจ้ง", "assumed": "ค่าประมาณ"},
    "main_cols": ["รหัส", "ชื่อ", "stock ตอนนี้", "ของที่สั่งแล้วรอรับ"],
    "net_col": "ต้องสั่งเพิ่ม",
    "note_open_used": "นับของที่สั่งแล้วรอรับตามวันที่คาดว่าจะได้",
    "note_open_not_used": "ยังไม่นับของที่สั่งแล้วรอรับ เพราะข้อมูลวันรับของยังใช้ไม่ได้ ตัวเลขต้องสั่งเพิ่มจึงอาจสูงกว่าจริง",
    "note_warehouses": "stock วัตถุดิบนับจากคลัง {rm_warehouses}",
    "back_link": "← กลับไปหน้าหลัก (Dashboard)",
    "notice": "แผนนี้ยังอยู่ระหว่างตรวจสอบ ตัวเลขต้องสั่งยังใช้สั่งซื้อจริงไม่ได้",
    "unit_flag": "หน่วยซื้อไม่ตรงกับหน่วยใน BOM",
    "no_unit_flag": "ไม่มีหน่วยซื้อในระบบ",
    "demand_col": "ความต้องการ",
    "divisions_label": "ฝ่ายที่รวมในแผนนี้:",
}


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def fmt_qty(x) -> str:
    """A quantity: a hyphen for none or zero, one decimal below 10, whole from 10 up (the plan page's cell format)."""
    return DASH if x is None or pd.isna(x) else fmt_cell(x)


def fmt_date(s) -> str:
    """'2026-09-28' -> '28 ก.ย. 69' (d MMM yy, Buddhist year, as the plan page writes dates)."""
    if s is None or pd.isna(s) or str(s) == "":
        return DASH
    t = pd.Timestamp(str(s)[:10])
    return f"{t.day} {thai_month(t.strftime('%Y-%m')).split()[0]} {str(t.year + 543)[-2:]}"


def used_in_text(codes: str, n_products: int, shown: int) -> str:
    """The first codes joined by ', ' and '+n' for the rest (n a count)."""
    c = [x for x in str(codes).split() if x]
    extra = int(n_products) - len(c)
    return ", ".join(c) + (f" +{extra}" if extra > 0 else "")


def compute_values(material_month: pd.DataFrame, summary: pd.DataFrame, meta: dict, n_days: int) -> dict:
    """Every value the page shows, from the recorded plan read back. Two lists by each material's latest order date (the order date of its first month with a net
    requirement), against the day the plan was built (`meta["today"]`): the first holds the dates from that day to that day plus `n_days` (both included), the second
    the dates before it. A material with no purchase unit in the system, or whose purchase unit differs from its BOM unit, carries a flag and no figure. The quantity to
    order is the net requirement of the months whose order date is in the first list's window (up to its end) or passed (before the day)."""
    months = list(meta["months"])
    today = pd.Timestamp(str(meta["today"])[:10])
    end = today + pd.Timedelta(days=int(n_days))
    s = summary.copy()
    s["name"] = s["name"].fillna("")
    s["latest_order_date"] = s["latest_order_date"].fillna("")
    s["first_dt"] = pd.to_datetime(s["latest_order_date"].replace("", pd.NA), errors="coerce")
    mm = material_month.copy()
    mm["od"] = pd.to_datetime(mm["order_date"].replace("", pd.NA), errors="coerce")
    gross = mm.pivot(index="material", columns="month", values="gross").reindex(columns=months)
    net = mm.pivot(index="material", columns="month", values="net_month").reindex(columns=months)
    short = mm[mm["net_month"] > 1e-9]
    qty_late = short[short["od"] < today].groupby("material")["net_month"].sum()
    qty_window = short[short["od"] <= end].groupby("material")["net_month"].sum()
    s["unit_flag"] = s["unit_vs_purchase"].eq("differs")                 # purchase unit differs from the BOM unit and no conversion can be derived
    s["no_unit_flag"] = s["purchase_unit"].fillna("").astype(str).str.strip().eq("")      # no purchase unit in the system
    s["no_figure"] = s["unit_flag"] | s["no_unit_flag"]
    late = s[s["first_dt"] < today].assign(qty=lambda d: d["material"].map(qty_late))
    within = s[(s["first_dt"] >= today) & (s["first_dt"] <= end)].assign(qty=lambda d: d["material"].map(qty_window))
    order = {"by": ["first_dt", "qty", "material"], "ascending": [True, False, True]}
    late, within = late.sort_values(**order, kind="mergesort"), within.sort_values(**order, kind="mergesort")
    rest = s.assign(_first=s["first_short_month"].replace("", "9999-99")).sort_values(["_first", "total_net", "material"], ascending=[True, False, True], kind="mergesort")
    listed = set(late["material"]) | set(within["material"])
    main = pd.concat([late, within, rest[~rest["material"].isin(listed)]]).drop(columns=["_first", "qty"], errors="ignore")
    return {"n_months": len(months), "months": months, "month_labels": [thai_month(m) for m in months], "n_days": int(n_days), "today": str(today.date()),
            "n_unit_flag": int(s["unit_flag"].sum()), "n_no_unit": int(s["no_unit_flag"].sum()),
            "n_within": int(len(within)), "n_late": int(len(late)), "n_within_flagged": int(within["no_figure"].sum()), "n_late_flagged": int(late["no_figure"].sum()),
            "plan_month": thai_month(str(meta["operation_plan_today"])[:7]), "pull_time": thai_datetime(meta["rm_pulled_at_local"]),
            "rm_warehouses": ", ".join(meta["rm_warehouses"]), "open_orders_used": bool(meta["open_orders_used"]), "divisions": ", ".join(meta["divisions"]),
            "within": within, "late": late, "main": main, "gross": gross, "net": net}


CSS_EXTRA = """
  .notice { background: #fdecea; border: 2px solid #8f2b2b; color: #5b1414; font-weight: 700; font-size: 15px; border-radius: 6px; padding: 12px 16px; margin: 0 0 14px; }
  .flag.unit { display: inline-block; margin: 0 0 0 8px; font-size: 11.5px; }
  .report-table td.num, .report-table th.num { text-align: right; }
  .report-table td.code { text-align: left; white-space: nowrap; }
"""


def flag_html(r) -> str:
    """The flag beside a material's code: no purchase unit in the system, or a purchase unit that differs from the BOM unit with no conversion derivable."""
    if r["no_unit_flag"]:
        return f'<span class="flag unit">{_e(TEXT["no_unit_flag"])}</span>'
    return f'<span class="flag unit">{_e(TEXT["unit_flag"])}</span>' if r["unit_flag"] else ""


def order_table(rows_df: pd.DataFrame, table_id: str) -> str:
    """One list: the approved columns; a flagged material shows a dash for its quantity and date."""
    th = "".join(f'<th class="{"name" if i in (1, 2) else ""}">{_e(c)}</th>' for i, c in enumerate(TEXT["now_cols"]))
    rows = []
    for _, r in rows_df.iterrows():
        rows.append(f'<tr data-material="{_e(r["material"])}"><td class="code">{_e(r["material"])}{flag_html(r)}</td><td class="name">{_e(r["name"] or DASH)}</td>'
                    f'<td class="name">{_e(used_in_text(r["used_in"], r["n_products"], 3))}</td><td>{DASH if r["no_figure"] else fmt_qty(r["qty"])}</td>'
                    f'<td>{DASH if r["no_figure"] else _e(fmt_date(r["latest_order_date"]))}</td><td>{fmt_qty(r["lead_days"])}</td>'
                    f'<td class="name">{_e(TEXT["source"][r["lead_source"]])}</td></tr>')
    return f'<div class="table-scroll"><table class="report-table" id="{table_id}"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render(values: dict) -> str:
    """The page as one HTML string. Reader-facing text is the approved text; comments hold what must stay off screen."""
    T, v = TEXT, values
    heading = T["heading"].format(n_months=v["n_months"])
    parts = [f'<div class="notice" id="verification-notice">{_e(T["notice"])}</div>', f'<a class="back-link" href="../index.html">{_e(T["back_link"])}</a>',
             f'<h1 id="page-title">{_e(heading)}</h1>',
             f'<p class="scope-note" id="data-line">{_e(T["data_line"].format(plan_month=v["plan_month"], pull_time=v["pull_time"]))}</p>',
             f'<p class="scope-note" id="divisions-covered">{_e(T["divisions_label"])} {_e(v["divisions"])}</p>',
             f'<h2 id="within-title">{_e(T["within_title"].format(n_days=v["n_days"]))}</h2>',
             f'<p class="note-line" id="within-line">{_e(T["within_line"].format(n_days=v["n_days"]))}</p>', order_table(v["within"], "within-table"),
             f'<h2 id="late-title">{_e(T["late_title"])}</h2>', f'<p class="note-line" id="late-line">{_e(T["late_line"])}</p>', order_table(v["late"], "late-table")]
    notes = [T["note_open_used"] if v["open_orders_used"] else T["note_open_not_used"], T["note_warehouses"].format(rm_warehouses=v["rm_warehouses"])]
    parts.append("".join(f'<p class="note-line material-note">{_e(n)}</p>' for n in notes))
    head1 = "".join(f'<th rowspan="2" class="{"name" if i == 1 else ""}">{_e(c)}</th>' for i, c in enumerate(T["main_cols"]))
    head1 += "".join(f'<th colspan="2">{_e(l)}</th>' for l in v["month_labels"])
    head2 = "".join(f'<th>{_e(T["demand_col"])}</th><th>{_e(T["net_col"])}</th>' for _ in v["month_labels"])
    body = []
    for _, r in v["main"].iterrows():
        m = r["material"]
        cells = "".join(f'<td>{fmt_qty(v["gross"].loc[m, ym])}</td><td>{DASH if r["no_figure"] else fmt_qty(v["net"].loc[m, ym])}</td>' for ym in v["months"])
        body.append(f'<tr data-material="{_e(m)}"><td class="code">{_e(m)}{flag_html(r)}</td><td class="name">{_e(r["name"] or DASH)}</td><td>{fmt_qty(r["stock_now"])}</td>'
                    f'<td>{fmt_qty(r["open_orders_total"])}</td>{cells}</tr>')
    parts.append(f'<div class="table-scroll"><table class="report-table" id="material-table"><thead><tr>{head1}</tr><tr>{head2}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')
    comment = ("<!-- Source: the recorded material plan (output/summary/material_plan_v1_*, SHA-256 checked in operation_plan_v1_integrity.json): the operation plan's "
               "production quantities of every division exploded through Cube_BOM_Exact level by level, netted against raw-material stock and open orders "
               "(Cube_tobe_received); lead times by the order of sources of METRICS.md Sec.5; names from the item master (Cube_ItemList). Two lists by "
               "latest order date: within the next order_window_days days (config) and already past. A material with no purchase unit in the system, or whose "
               "purchase unit differs from its BOM unit, carries a flag beside its code and a dash in place of its order quantity, order date and net requirement. Net columns are the month's own net requirement (the increase of the cumulative net requirement). -->")
    return (f'<!DOCTYPE html>\n<html lang="th">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{_e(heading)}</title>\n<style>{CSS}{CSS_EXTRA}</style>\n</head>\n<body>\n{comment}\n<div class="wrap">\n' + "\n".join(parts) + "\n</div>\n</body>\n</html>\n")


def build_values(root: str = PROJECT_ROOT, out_dir: str = None) -> dict:
    cfg = mp.load_config(root)
    mm, sm, meta = mp.read_outputs(root, cfg, out_dir)
    return compute_values(mm, sm, meta, int(cfg["order_window_days"]))


def build_page(root: str = PROJECT_ROOT, out_dir: str = None, out_path: str = None) -> str:
    """Builds the page from the recorded material plan under `root` (outputs in `out_dir` when given) and writes it to `out_path` (default
    forecast/material_plan.html under root). Returns the path."""
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
