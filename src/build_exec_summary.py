"""The executive summary tab ("สรุปผู้บริหาร", METRICS.md Sec.49) of index.html: figures computed at build time from the saved pulls, the forecast page's data and the recorded
plan outputs, rendered between the markers EXEC-TAB-BEGIN and EXEC-TAB-END. Split out of src/build_trend_tab.py on 2026-10-14 (Prompt 30); the Trend tab stays there, and the code
both tabs need (TrendTabError, load_config) lives there only. Makes no database connection. Run by the monthly runner's step 7f; by hand: python src/build_exec_summary.py --build.
"""
import argparse
import html
import json
import logging
import math
import os
import re
import sys

import pandas as pd

from build_trend_tab import PROJECT_ROOT, TrendTabError, load_config

logger = logging.getLogger("build_exec_summary")


EXEC_BEGIN = "<!-- EXEC-TAB-BEGIN -->"
EXEC_END = "<!-- EXEC-TAB-END -->"


class ExecSummaryError(TrendTabError):
    """The executive summary could not be built or failed its gate; nothing is written."""


def exec_month_units(forecast_units, booked_units) -> float:
    """Units counted for one item in one remaining month: the larger of the forecast units of the vintage and the units already on the books (Actual + MPS with forecast_date
    in the month). An item with no forecast row counts 0 forecast units (decision D2 of the user, 2026-10-09; METRICS.md Sec.49)."""
    return max(float(forecast_units or 0.0), float(booked_units or 0.0))


def exec_month_baht(forecast_units, booked_units, price) -> int:
    """Whole baht of exec_month_units x the item's unit price (rounded half up at item and month level, as the forecast page does); 0 for an item with no price."""
    if price is None:
        return 0
    return int(math.floor(exec_month_units(forecast_units, booked_units) * float(price) + 0.5))


def exec_booked_units(raw: pd.DataFrame, items: set, months: list) -> dict:
    """{(item, month): units} already on the books: Actual + MPS units of the forecast-scope `items` with forecast_date (not before createDate) in `months`, from the saved sales
    pull `raw` (columns itemcode, createDate, forecast_date, qty, status, revenue_type); Omni Channel only, the scope and key of the YTD."""
    d = raw[raw["revenue_type"].eq("Omni Channel") & raw["status"].isin(["Actual", "MPS"]) & raw["itemcode"].isin(items)].copy()
    d["createDate"] = pd.to_datetime(d["createDate"])
    d["forecast_date"] = pd.to_datetime(d["forecast_date"], errors="coerce")
    d = d[d["forecast_date"].notna() & (d["forecast_date"] >= d["createDate"])]
    d["ym"] = d["forecast_date"].dt.strftime("%Y-%m")
    g = d[d["ym"].isin(months)].groupby(["itemcode", "ym"])["qty"].sum()
    return {k: float(v) for k, v in g.items()}


def exec_ts_counts(points: list, limit: float) -> dict:
    """For a Tracking Signal beyond the limit (METRICS.md Sec.49): n = the number of points, k = the points whose error has the sign of the signal, and `month` = the month of the point
    with the largest absolute error when the signal without that one point is within the limit (None otherwise, or when it cannot be computed). `points` = [(month, e)] as the page makes them."""
    import transferability_all_divisions as ta
    errors = [float(e) for _m, e in points]
    ts = ta.tracking_signal(errors)["tracking_signal"]
    k = sum(1 for e in errors if (e < 0 if ts < 0 else e > 0))
    big = max(range(len(errors)), key=lambda i: abs(errors[i]))
    rest = ta.tracking_signal(errors[:big] + errors[big + 1:])["tracking_signal"]
    return {"k": k, "n": len(errors), "month": points[big][0] if rest is not None and abs(rest) <= limit else None}


def exec_watch(ts_rows: list, limit: float, plan_above: list, n_late: int, pem107_alert) -> list:
    """The lines of "เรื่องที่ต้องระวัง", each only while its condition holds: a group whose Tracking Signal is beyond plus or minus `limit` (below: forecast below the actual), each
    division-month of the plan above the historical peak, materials already late (n_late above 0), the PEM107 not-late alert (a dict with `since` and `pct`, or None)."""
    watch = []
    for r in ts_rows:
        ts = r["value"]
        if ts is not None and abs(ts) > limit:
            watch.append({"kind": "low" if ts < 0 else "high", "group": r["group"], "value": ts, **exec_ts_counts(r["points"], limit)})
    for r in plan_above:
        watch.append({"kind": "plan", **r})
    if n_late > 0:
        watch.append({"kind": "material", "n": n_late})
    if pem107_alert:
        watch.append({"kind": "pem107", **pem107_alert})
    return watch


def exec_data(root: str = PROJECT_ROOT, plan_dir: str = None) -> dict:
    """Every figure of the tab (see METRICS.md Sec.49). Stops (ExecSummaryError) when the data month is not the last month of the vintage's fit window or the vintage does not cover a
    remaining month of the year."""
    sys.path.insert(0, os.path.join(root, "src"))
    import build_material_plan_page as bmp
    import build_operation_plan_page as bopp
    import build_report as br
    import maxmin_v1
    import operation_plan as op
    import reader_values as rv
    config = br.load_config()
    basis = config["report"]["price_basis"]
    vf = rv.vintage_facts(root)
    forward = br.gather_forward_forecast(vf, br.gather_scope_table())
    codes = sorted({it["item"] for ts in forward["divisions"].values() for t in ts for it in t["items"]})
    price_info = rv.unit_prices(codes, basis, vf["fit_first"], vf["fit_last"], os.path.join(root, "reference", "pricelist.xlsx"), root)
    baht = br.gather_baht(forward, price_info)
    sale = pd.read_csv(os.path.join(root, *basis["sale_file"].split("/")), usecols=["itemcode", "year_month", "sale", "division"])
    data_month = str(sale["year_month"].max())
    if data_month != vf["fit_last"]:
        raise ExecSummaryError(f"the last month of the saved series ({data_month}) is not the last month of the vintage's fit window ({vf['fit_last']})")
    year, mnum = int(data_month[:4]), int(data_month[5:7])
    remaining = [f"{year}-{m:02d}" for m in range(mnum + 1, 13)]
    missing = [m for m in remaining if m not in forward["months"]]
    if missing:
        raise ExecSummaryError(f"the vintage covers {forward['months'][0]} to {forward['months'][-1]}, not the remaining months {missing}")
    last_first = f"{year - 1}-01"
    if str(sale["year_month"].min()) > last_first:
        raise ExecSummaryError(f"the saved series starts {sale['year_month'].min()}, after {last_first} needed for last year's YTD")
    cur = sale[(sale["year_month"] >= f"{year}-01") & (sale["year_month"] <= data_month)].groupby("division")["sale"].sum()
    prev = sale[(sale["year_month"] >= last_first) & (sale["year_month"] <= f"{year - 1}-{mnum:02d}")].groupby("division")["sale"].sum()
    primary = br.gather_primary_results()
    acc = br.gather_accuracy_vs_naive(config, primary)
    rel = {r["label"]: r["relative_mae"] for r in acc["rows"] if r["kind"] == "division"}
    th = acc["thresholds"]
    # the remaining months: per item the larger of the forecast units and the units already on the books (D2), whole baht at the item's unit price
    import forward_test_scoring as fts
    raw = pd.read_csv(fts.RAW_HISTORY_PATH, usecols=["itemcode", "createDate", "forecast_date", "qty", "status", "revenue_type"])
    booked = exec_booked_units(raw, set(codes), remaining)
    prices = price_info["prices"]
    booked_baht = {}
    rows = []
    for d in baht["divisions"]:
        new_by_month = {m: 0 for m in remaining}
        old_by_month = {m: baht["divisions"][d]["total"][forward["months"].index(m)] for m in remaining}
        for t in forward["divisions"][d]:
            for it in t["items"]:
                price = prices[it["item"]]["price"]
                for m in remaining:
                    b = exec_month_baht(0.0, booked.get((it["item"], m), 0.0), price)
                    booked_baht.setdefault(it["item"], {})[m] = b
                    new_by_month[m] += exec_month_baht(it["values"][forward["months"].index(m)], booked.get((it["item"], m), 0.0), price)
        fc_rem = float(sum(new_by_month.values()))
        ytd, ly = float(cur.get(d, 0.0)), float(prev.get(d, 0.0))
        proj = ytd + fc_rem
        rows.append({"division": d, "ytd": ytd, "last_ytd": ly, "change": (ytd / ly - 1) if ly else None, "forecast_remaining": fc_rem, "projection": proj,
                     "relative_mae": rel.get(d), "projection_page_only": ytd + float(sum(old_by_month.values())),
                     "by_month": {m: {"page": int(old_by_month[m]), "used": int(new_by_month[m])} for m in remaining}})
    by_ym = sale[sale["division"].isin([r["division"] for r in rows])].groupby("year_month")["sale"].sum()          # the divisions of the table: the monthly series add up to its YTD rows
    monthly = {"actual": {f"{year}-{m:02d}": float(by_ym.get(f"{year}-{m:02d}", 0.0)) for m in range(1, mnum + 1)},
               "last_year": {f"{year - 1}-{m:02d}": float(by_ym.get(f"{year - 1}-{m:02d}", 0.0)) for m in range(1, 13)},
               "projection": {m: float(sum(r["by_month"][m]["used"] for r in rows)) for m in remaining}}
    tot = {k: sum(r[k] for r in rows) for k in ("ytd", "last_ytd", "forecast_remaining", "projection")}
    tot["change"] = (tot["ytd"] / tot["last_ytd"] - 1) if tot["last_ytd"] else None
    cfg_op = op.load_config(root)
    _im, dm, _meta = op.read_outputs(root, cfg_op, plan_dir)
    plan_above = [{"division": r.division, "month": rv.thai_month_short(r.month), "pct": bopp.fmt_pct(r.share_of_capacity)} for r in dm[dm["above_capacity"].astype(bool)].itertuples()]
    n_late = int(bmp.build_values(root, plan_dir)["n_late"])
    with open(os.path.join(root, "output", "summary", "task2b_part4_pem107_alert.json"), encoding="utf-8") as f:
        alert = json.load(f)
    watch = exec_watch([{"group": r["label"], "value": r["tracking_signal"], "points": r["points"]} for r in acc["rows"]], th["limit"], plan_above, n_late,
                       None if alert.get("not_late_from_may_2026_pct") is None else {"since": rv.thai_month_year(alert["split_date"]), "pct": f"{float(alert['not_late_from_may_2026_pct']):.1f}%"})
    pending = [r for r in maxmin_v1.pending_criteria_rows() if r["who"] == "ผู้บริหาร"]
    return {"data_month": data_month, "data_month_label": rv.thai_month_short(data_month), "year": year, "year_be": int(rv.thai_year_short(year)), "remaining_months": remaining, "booked_baht": booked_baht, "rows": rows, "total": tot, "monthly": monthly,
            "n_forecast_divisions": len(rows), "n_beat_naive": sum(1 for r in rows if r["relative_mae"] is not None and r["relative_mae"] < th["pass"]), "thresholds": th,
            "watch": watch, "pending": pending, "vintage_id": vf["vintage_id"]}


def _money(x) -> str:
    return f"{x / 1e6:,.1f}"


def _signed_pct(x) -> str:
    return f"{100 * x:+.1f}%"


def _nice_step(top: float, n: int = 5) -> float:
    """A round axis step (1, 2, 2.5, 5 times a power of ten) giving at most about `n` ticks up to `top`."""
    raw = max(top, 1e-9) / n
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)


def _chart_monthly(d: dict, T: dict) -> str:
    """Chart 1 (inline SVG): monthly sales in million baht, this year's actual (solid), its projection for the remaining months (dashed, from the last actual point) and last
    year's 12 months (thin, muted). Every value comes from d["monthly"]; each point carries a <title> tooltip; the colors and widths come from the classes of index.html."""
    import reader_values as rv
    year, mo = d["year"], d["monthly"]
    W, H, L, R, TOP, BOT = 640, 300, 52, 14, 26, 62
    pw, ph = W - L - R, H - TOP - BOT
    vals = [v / 1e6 for part in mo.values() for v in part.values()]
    step = _nice_step(max(vals))
    ymax = step * math.ceil(max(vals) / step)
    X = lambda i: L + pw * i / 11
    Y = lambda v: TOP + ph * (1 - v / ymax)
    month_label = lambda ym: rv.thai_month_short(ym)
    idx = lambda ym: int(ym[5:7]) - 1
    out = [f'<text class="ec-txt" x="{L - 8}" y="{TOP - 12}">{html.escape(T["chart1_unit"])}</text>']
    for k in range(int(round(ymax / step)) + 1):
        out.append(f'<line class="ec-grid" x1="{L}" y1="{Y(k * step):.1f}" x2="{W - R}" y2="{Y(k * step):.1f}"/><text class="ec-txt ec-end" x="{L - 8}" y="{Y(k * step) + 4:.1f}">{k * step:,.1f}</text>')
    for i in range(12):
        out.append(f'<text class="ec-txt ec-mid" x="{X(i):.1f}" y="{TOP + ph + 16}">{html.escape(month_label(f"{year}-{i + 1:02d}").split(" ")[0])}</text>')

    def series(part, line_cls, dot_cls, start=None):
        coords = ([start] if start else []) + [(X(idx(ym)), Y(v / 1e6)) for ym, v in part.items()]
        line = f'<polyline class="{line_cls}" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in coords)}"/>' if len(coords) > 1 else ""
        dots = "".join(f'<circle class="{dot_cls}" cx="{X(idx(ym)):.1f}" cy="{Y(v / 1e6):.1f}" r="3.5"><title>{html.escape(T["chart1_tip"].format(month=month_label(ym), value=_money(v)))}</title></circle>' for ym, v in part.items())
        return line + dots
    last_ym, last_v = list(mo["actual"].items())[-1]
    out.append(series(mo["last_year"], "ec-last", "ec-dot-last"))
    out.append(series(mo["actual"], "ec-actual", "ec-dot-actual"))
    if mo["projection"]:
        out.append(series(mo["projection"], "ec-proj", "ec-dot-proj", start=(X(idx(last_ym)), Y(last_v / 1e6))))
    ly = H - 14
    for j, (cls, key, yr) in enumerate((("ec-actual", "chart1_legend_actual", year), ("ec-proj", "chart1_legend_proj", year), ("ec-last", "chart1_legend_last", year - 1))):
        x0 = L + j * 170
        out.append(f'<line class="{cls}" x1="{x0}" y1="{ly - 4}" x2="{x0 + 26}" y2="{ly - 4}"/><text class="ec-txt" x="{x0 + 32}" y="{ly}">{html.escape(T[key].format(year=rv.thai_year_short(yr)))}</text>')
    proj_months = f"{month_label(next(iter(mo['projection'])))}–{month_label(next(reversed(mo['projection'])))}" if mo["projection"] else T["dash"]
    aria = T["chart1_aria"].format(year=d["year_be"], last_year=int(rv.thai_year_short(year - 1)), first=month_label(next(iter(mo["actual"]))), last=d["data_month_label"],
                                   ytd=_money(sum(mo["actual"].values())), projection_months=proj_months, total=_money(d["total"]["projection"]), last_total=_money(sum(mo["last_year"].values())))
    return f'<svg id="execChartMonthly" role="img" aria-label="{html.escape(aria)}" viewBox="0 0 {W} {H}">{"".join(out)}</svg>'


def _chart_relative_mae(d: dict, T: dict, config: dict) -> str:
    """Chart 2 (inline SVG): Relative MAE per division as horizontal bars in the table's order, the value at each bar end, a vertical line at the pass threshold
    (d["thresholds"]["pass"]); a division with no value has no bar (a dash); a division that is not forecast shows its reason as text; the total row has none."""
    import reader_values as rv
    th = d["thresholds"]["pass"]
    rows = [(r["division"], r.get("relative_mae")) for r in d["rows"]]
    reasons = list(rv.division_reason_codes(config).items())
    W, L, R, TOP, RH = 440, 64, 52, 34, 30
    top = max([v for _d, v in rows if v is not None] + [th]) * 1.1
    step = 0.5 if top <= 3 else 1.0
    xmax = step * math.ceil(top / step)
    pw = W - L - R
    X = lambda v: L + pw * v / xmax
    H = TOP + RH * (len(rows) + len(reasons)) + 10
    out = [f'<line class="ec-grid" x1="{X(k * step):.1f}" y1="{TOP - 6}" x2="{X(k * step):.1f}" y2="{H - 10}"/><text class="ec-txt ec-mid" x="{X(k * step):.1f}" y="{H + 2}">{k * step:.1f}</text>' for k in range(int(round(xmax / step)) + 1)]
    out.append(f'<line class="ec-ref" x1="{X(th):.1f}" y1="{TOP - 6}" x2="{X(th):.1f}" y2="{TOP + RH * len(rows)}"/><text class="ec-txt ec-mid" x="{X(th):.1f}" y="{TOP - 12}">{html.escape(T["chart2_ref"])}</text>')
    for i, (division, v) in enumerate(rows):
        y = TOP + RH * i
        out.append(f'<text class="ec-txt ec-end" x="{L - 8}" y="{y + 19}">{html.escape(division)}</text>')
        if v is None:
            out.append(f'<text class="ec-txt" x="{L + 6}" y="{y + 19}">{T["dash"]}</text>')
        else:
            out.append(f'<rect class="{"ec-bar-pass" if v <= th else "ec-bar-above"}" x="{L}" y="{y + 5}" width="{X(v) - L:.1f}" height="{RH - 10}"/><text class="ec-val" x="{X(v) + 6:.1f}" y="{y + 19}">{v:.2f}</text>')
    for j, (division, code) in enumerate(reasons):
        entry = rv.not_forecast_reasons(config)[code]
        text = entry.get("chart_line", entry["line"]).format(division=division)
        out.append(f'<text class="ec-txt" x="0" y="{TOP + RH * (len(rows) + j) + 19}">{html.escape(text)}</text>')
    aria = T["chart2_aria"].format(values=", ".join(f"{dv} {'–' if v is None else format(v, '.2f')}" for dv, v in rows), threshold=f"{th:.2f}")
    return f'<svg id="execChartMae" role="img" aria-label="{html.escape(aria)}" viewBox="0 0 {W} {H + 8}">{"".join(out)}</svg>'


def exec_render(data: dict, config: dict) -> str:
    """The tab's HTML (cards, table, the lists and the footer) from `data`; every text is the approved text of config exec_summary.text with its braces filled."""
    import reader_values as rv
    T = config["exec_summary"]["text"]
    esc = html.escape
    d, tot = data, data["total"]
    dash = T["dash"]
    month = d["data_month_label"]
    n_watch = len(d["watch"])
    cards = [
        (T["card1_label"].format(data_month=month), T["million_value"].format(value=_money(tot["ytd"])), T["card1_sub"].format(change=dash if tot["change"] is None else _signed_pct(tot["change"]))),
        (T["card2_label"].format(year=d["year_be"]), T["million_value"].format(value=_money(tot["projection"])), ""),
        (T["card3_label"], T["card3_value"].format(n=d["n_beat_naive"], N=d["n_forecast_divisions"]),
         T["card3_sub"].format(n_rounds=rv.backtest_rounds(config), decision_date=rv.thai_date_short(rv.criteria_decision_date(config["maxmin_v1"]["pending_criteria_values"])))),
        (T["card4_label"], T["card4_value"].format(n=n_watch), T["card4_sub"]),
    ]
    cards_html = "".join(f'<div class="kpi" id="execCard{i}"><div class="k">{esc(a)}</div><div class="v">{esc(b)}</div>{f'<div class="s">{esc(c)}</div>' if c else ''}</div>' for i, (a, b, c) in enumerate(cards, 1))

    def cells(r, remark):
        change = dash if r["change"] is None else _signed_pct(r["change"])
        rel = dash if r.get("relative_mae") is None else f"{r['relative_mae']:.2f}"
        return (f"<td>{_money(r['ytd'])}</td><td>{_money(r['last_ytd'])}</td><td>{change}</td><td>{_money(r['projection'])}</td>"
                f"<td>{rel}</td><td>{esc(remark)}</td>")

    body = []
    for r in d["rows"]:
        body.append(f'<tr data-division="{esc(r["division"])}"><td>{esc(r["division"])}</td>{cells(r, "")}</tr>')
    body.append(f'<tr class="total-row" id="execTotalRow"><td>{esc(T["total_label"])}</td>{cells(dict(tot, relative_mae=None), "")}</tr>')
    import reader_values as rv
    for division, code in rv.division_reason_codes(config).items():                        # every division that is not forecast: dashes and its configured reason
        body.append(f'<tr data-division="{esc(division)}"><td>{esc(division)}</td>' + f"<td>{dash}</td>" * 5 + f"<td>{esc(rv.not_forecast_text(code, 'line', division, config))}</td></tr>")
    head = "".join(f"<th>{esc(c)}</th>" for c in T["columns"])
    watch_lines = []
    for w in d["watch"]:
        if w["kind"] in ("low", "high"):
            suffix = T["watch_suffix"].format(month=rv.thai_month_short(w["month"])) if w["month"] else ""
            watch_lines.append(T["watch_" + w["kind"]].format(group=w["group"], value=f"{w['value']:.1f}", k=w["k"], n=w["n"], suffix=suffix))
        elif w["kind"] == "plan":
            watch_lines.append(T["watch_plan"].format(division=w["division"], month=w["month"], pct=w["pct"]))
        elif w["kind"] == "material":
            watch_lines.append(T["watch_material"].format(n=w["n"]))
        else:
            watch_lines.append(T["watch_pem107"].format(since=w["since"], pct=w["pct"]))
    watch_html = "".join(f"<li>{esc(x)}</li>" for x in watch_lines)
    decide_html = "".join(f"<li>{esc(r['topic'])} · {esc(r['to_decide'])}</li>" for r in d["pending"])
    charts_html = (f'<div class="ec-row" id="execCharts"><div class="ec-chart ec-chart1"><h3>{esc(T["chart1_title"])}</h3>{_chart_monthly(d, T)}<p class="hint">{esc(T["chart1_note"])}</p></div>'
                   f'<div class="ec-chart ec-chart2"><h3>{esc(T["chart2_title"])}</h3>{_chart_relative_mae(d, T, config)}</div></div>')
    return (f'<div class="kpis" id="execCards">{cards_html}</div>'
            f'{charts_html}'
            f'<p class="hint" id="execUnit">{esc(T["unit_note"])}</p>'
            f'<div class="table-scroll"><table id="execTable"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<h3 id="execWatchTitle">{esc(T["watch_heading"])}</h3><ul id="execWatch">{watch_html}</ul>'
            f'<h3 id="execDecideTitle">{esc(T["decide_heading"])}</h3><ul id="execDecide">{decide_html}</ul>'
            f'<p><a id="execToAssump" href="#" onclick="omniShowTab(4);return false">{esc(T["decide_link"])}</a></p>'
            f'<p class="hint" id="execFooter">{esc(T["footer"].format(data_month=month))}</p>')


def exec_gate(data: dict, sales_report_path: str) -> dict:
    """The tab's checks: (1) the total row equals the sum of the division rows (YTD, last-year YTD, projection); (2) each division's projection equals its YTD plus, per item and
    remaining month, the larger of the baht on the rendered forecast page (its per-item baht rows) and the baht already on the books (data["booked_baht"]). Raises ExecSummaryError on any difference."""
    import reader_values as rv
    rows, tot = data["rows"], data["total"]
    for k in ("ytd", "last_ytd", "projection", "forecast_remaining"):
        if abs(tot[k] - sum(r[k] for r in rows)) > 1e-6:
            raise ExecSummaryError(f"the total row's {k} differs from the sum of the division rows")
    with open(sales_report_path, encoding="utf-8") as f:
        text = f.read()
    labels = [rv.thai_month_short(x) for x in data["remaining_months"]]
    booked = data["booked_baht"]
    checked = 0
    for r in rows:
        m = re.search(r'id="fwd-baht-table-' + re.escape(r["division"]) + r'">.*?<thead><tr>(.*?)</tr></thead><tbody>(.*?)</tbody>', text, re.S)
        if not m:
            raise ExecSummaryError(f"the forecast page has no baht table for {r['division']}")
        heads = re.findall(r"<th>(.*?)</th>", m.group(1))[1:]
        if heads[:len(labels)] != labels:
            raise ExecSummaryError(f"the forecast page's first months {heads[:len(labels)]} are not the remaining months {labels}")
        total = 0
        for code, cells in re.findall(r'<tr class="fwd-bitem"[^>]*><td>(.*?)</td>((?:<td>[^<]*</td>)+)</tr>', m.group(2), re.S):
            code = html.unescape(re.sub(r"<[^>]+>", "", code.split(" <span")[0])).strip()
            vals = [0 if c == "-" else int(c.replace(",", "")) for c in re.findall(r"<td>(.*?)</td>", cells)]
            for i, mm in enumerate(data["remaining_months"]):
                total += max(vals[i], booked.get(code, {}).get(mm, 0))
            checked += 1
        if abs(r["projection"] - (r["ytd"] + total)) > 1e-6:
            raise ExecSummaryError(f"{r['division']}: the year-end projection {r['projection']} differs from YTD plus the larger of the forecast page's baht and the baht on the books per item and month {r['ytd'] + total}")
    return {"passed": True, "divisions": [r["division"] for r in rows], "months": labels, "items_checked": checked}


def write_between(path: str, begin: str, end: str, block: str) -> None:
    """Replaces the text between two markers of `path` by `block` (the markers stay); the markers must each be present exactly once."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    if text.count(begin) != 1 or text.count(end) != 1:
        raise TrendTabError(f"{os.path.basename(path)} does not hold the markers {begin} and {end} exactly once")
    a, b = text.index(begin) + len(begin), text.index(end)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text[:a] + block + text[b:])


def run_exec_build(root: str = PROJECT_ROOT, index_path: str = None, sales_report_path: str = None, plan_dir: str = None) -> dict:
    """Builds the executive summary tab: data, gate, HTML written into index.html (or `index_path`) between the markers. Returns the build report (figures and gate)."""
    config = load_config(root)
    data = exec_data(root, plan_dir)
    gate = exec_gate(data, sales_report_path or os.path.join(root, "forecast", "sales_report.html"))
    write_between(index_path or os.path.join(root, config["trend_tab"]["index_file"]), EXEC_BEGIN, EXEC_END, "\n" + exec_render(data, config) + "\n")
    return {"data_month": data["data_month"], "year": data["year"], "total": data["total"], "n_watch": len(data["watch"]), "n_beat_naive": data["n_beat_naive"], "gate": gate,
            "vintage_id": data["vintage_id"]}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true", help="builds the executive summary tab of index.html from the saved pulls and the recorded outputs")
    a = ap.parse_args(argv)
    if not a.build:
        ap.error("give --build")
    try:
        run_exec_build()
    except TrendTabError as e:
        logger.error("EXECUTIVE SUMMARY: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
