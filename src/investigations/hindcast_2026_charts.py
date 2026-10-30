"""Charts of the 2026 hindcast (Prompt 64 step 3): the company total and one small multiple per forecast division, in million baht, from the tables hindcast_2026_run.py wrote.
Colours: the first three slots of the validated categorical palette (blue, orange, aqua; validated for all pairs), the actual in neutral ink. The aqua is below 3:1 contrast on the light
surface, so every line is also labelled at its end and has its own marker, and the same figures are in the tables of the report."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
TABLES = os.path.join(PROJECT_ROOT, "output", "summary", "hindcast_2026_tables")
DOCS = os.path.join(PROJECT_ROOT, "docs", "reports", "summary")
INK, GRID, SURFACE, MUTED = "#0b0b0b", "#d9d8d3", "#fcfcfb", "#52514e"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
LABELS = {m: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"][i] for i, m in enumerate(MONTHS)}


def _panel(ax, a, b, vint, title, big=False):
    """a: main-line monthly totals of one division (columns target_month, actual_baht, f_*_baht); b: the January run; vint: real vintages' totals (target_month, vintage_id, actual, topdown)."""
    x = {m: i for i, m in enumerate(MONTHS)}
    a = a.set_index("target_month").reindex(MONTHS)
    b = b.set_index("target_month").reindex(MONTHS)
    ms = 6 if big else 4
    ax.plot(range(9), a["actual_baht"] / 1e6, color=INK, lw=2.4, marker="o", ms=ms, label="Actual", zorder=5)
    ax.plot(range(9), a["f_naive_baht"] / 1e6, color=ORANGE, lw=1.6, marker="^", ms=ms, label="Naive (simulated, 3 months ahead)", zorder=3)
    ax.plot(range(9), a["f_ma_baht"] / 1e6, color=AQUA, lw=1.6, marker="s", ms=ms - 1, label="Moving average (simulated, 3 months ahead)", zorder=3)
    ax.plot(range(9), a["f_topdown_baht"] / 1e6, color=BLUE, lw=1.8, marker="o", ms=ms, label="Production model, Top-down (simulated, 3 months ahead)", zorder=4)
    ax.plot(range(9), b["f_topdown_baht"] / 1e6, color=BLUE, lw=1.3, ls=(0, (4, 3)), label="Production model from the January run (beyond its 6-month horizon)", zorder=2)
    for vid, g in vint.groupby("vintage_id"):
        gx = [x[m] for m in g["target_month"]]
        ax.scatter(gx, g["topdown_baht"] / 1e6, marker="D", s=70 if big else 40, facecolor=SURFACE, edgecolor=INK, linewidth=1.8, zorder=6,
                   label="Real forecast, vintage %d (out of sample)" % vid)
        for gx_i, gy in zip(gx, g["topdown_baht"] / 1e6):
            ax.annotate("V%d" % vid, (gx_i, gy), textcoords="offset points", xytext=(9 if big else 6, -3), fontsize=9 if big else 7, color=INK, zorder=7)
    ax.set_title(title, fontsize=11 if big else 9.5, color=INK, loc="left")
    ax.set_xticks(range(9))
    ax.set_xticklabels([LABELS[m] for m in MONTHS], fontsize=9 if big else 7.5, color=MUTED)
    ax.tick_params(axis="y", labelsize=9 if big else 7.5, colors=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.set_facecolor(SURFACE)
    ax.set_ylim(bottom=0)


def main():
    a_all = pd.read_csv(os.path.join(TABLES, "A_main_totals_monthly.csv"))
    b_all = pd.read_csv(os.path.join(TABLES, "B_totals_monthly.csv"))
    v_co = pd.read_csv(os.path.join(TABLES, "real_vintages_totals.csv"))
    v_div = pd.read_csv(os.path.join(TABLES, "real_vintages_totals_by_division.csv"))
    # company
    fig, ax = plt.subplots(figsize=(11, 5.6), facecolor=SURFACE)
    _panel(ax, a_all[a_all["division"] == "COMPANY"], b_all[b_all["division"] == "COMPANY"], v_co, "Company total, monthly sales in million baht (one fixed price per item for actual and forecast)", big=True)
    ax.set_ylabel("million baht", color=MUTED, fontsize=9)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2, frameon=False, fontsize=8.5, labelcolor=INK)
    fig.text(0.01, 0.005, "Simulated lines: hindcast on today's complete series, scope and model chosen with 2026 in view (optimistic). Diamonds are the only real forecasts.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(DOCS, "hindcast_2026_company.png"), dpi=140, facecolor=SURFACE)
    plt.close(fig)
    # small multiples
    divs = ["PEM101", "PEM103", "PEM107", "PEM102", "CI101"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), facecolor=SURFACE)
    for ax, d in zip(axes.ravel(), divs):
        _panel(ax, a_all[a_all["division"] == d], b_all[b_all["division"] == d], v_div[v_div["division"] == d].rename(columns={"vintage_id": "vintage_id"}), d + " (million baht)")
    last = axes.ravel()[5]
    last.axis("off")
    h, l = axes.ravel()[0].get_legend_handles_labels()
    last.legend(h, l, loc="center", frameon=False, fontsize=9, labelcolor=INK, title="Each panel has its own scale", title_fontsize=9)
    fig.text(0.01, 0.005, "Simulated lines: hindcast on today's complete series, scope and model chosen with 2026 in view (optimistic). Diamonds are the only real forecasts.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(DOCS, "hindcast_2026_divisions.png"), dpi=130, facecolor=SURFACE)
    plt.close(fig)
    print("charts written to", DOCS)


if __name__ == "__main__":
    main()
