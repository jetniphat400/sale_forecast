"""Top-down against Direct and Naive, per division (METRICS.md section 41): the computation, the verdict rule and the text of
the sales report's block "ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม".

No database and no browser. The computation is checked against the figures of output/summary/check_significance_topdown.md (the
2026-10-05 check, which a separate Validator recomputed) on the backtest rows that check used; those rows are regenerated every
month, so the figures are compared on a frozen copy of the item-level pairs only when the rows on disk are the ones the check
read (same pull date), and otherwise the test skips with a message rather than passing silently.
"""
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import build_report as br  # noqa: E402
import significance_topdown as sig  # noqa: E402

REPORT = os.path.join(PROJECT_ROOT, "output", "summary", "check_significance_topdown.md")
ITEM_ROWS = os.path.join(PROJECT_ROOT, "output", "summary", "phaseC_step2_transferability_item_rolling_origin.csv")
CHECK_PULL_DATE = "2026-10-05 07:41:06"      # the backtest the check report was written from
DIVISIONS = ["CI101", "PEM101", "PEM102", "PEM103", "PEM107"]


def _report_item_level(heading: str) -> dict:
    """{division: (n_items, mean_diff, t, p)} from the check report's table under `heading`."""
    text = open(REPORT, encoding="utf-8").read()
    section = text.split(heading, 1)[1].split("###", 1)[0].split("\n## ", 1)[0]
    out = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] in DIVISIONS and len(cells) >= 11:
            out[cells[0]] = (int(cells[6]), float(cells[7]), float(cells[8]), float(cells[9]))
    return out


# ------------------------------------------------------------------ the computation reproduces the check report
@pytest.mark.parametrize("other,heading", [("Direct", "### Top-down against Direct"), ("Naive", "### Top-down against Naive")])
def test_item_level_figures_reproduce_the_check_report(other, heading):
    if not os.path.exists(ITEM_ROWS) or not os.path.exists(REPORT):
        pytest.skip("SKIPPED, not passed: the backtest rows or the check report are not on disk")
    per_div = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "summary", "phaseC_step2_transferability_per_division.csv"))
    if str(per_div["snapshot_pull_date"].iloc[0]) != CHECK_PULL_DATE:
        pytest.skip(f"SKIPPED, not passed: the backtest on disk is from {per_div['snapshot_pull_date'].iloc[0]}, the check report was written from {CHECK_PULL_DATE}")
    rows = pd.read_csv(ITEM_ROWS)
    out = sig.compute(rows, 2.0, 0.05, CHECK_PULL_DATE)
    expected = _report_item_level(heading)
    assert set(expected) == set(DIVISIONS)
    for division, (n, mean_diff, t, p) in expected.items():
        r = out[(out["division"] == division) & (out["other_method"] == other)].iloc[0]
        assert int(r["n_items"]) == n, division
        assert r["mean_diff"] == pytest.approx(mean_diff, abs=6e-5), division
        assert r["t_stat"] == pytest.approx(t, abs=6e-4), division
        assert r["p_value"] == pytest.approx(p, rel=2e-3, abs=6e-5), division


# ------------------------------------------------------------------ the verdict rule
@pytest.mark.parametrize("t,w_p,median,expected", [
    (-2.5, 0.01, -0.1, "better"),
    (2.5, 0.01, 0.1, "worse"),
    (-2.0, 0.049, -0.1, "better"),            # exactly at the threshold counts
    (-1.99, 0.001, -0.1, "unclear"),          # |t| below the threshold
    (-2.5, 0.05, -0.1, "unclear"),            # Wilcoxon p at the level is not below it
    (-2.5, 0.01, 0.1, "unclear"),             # t says better, the median says worse: sign disagreement
    (2.5, 0.01, -0.1, "unclear"),
    (-2.5, 0.01, 0.0, "unclear"),             # a zero median never agrees
    (-0.4, 0.0001, -0.1, "unclear"),          # Wilcoxon alone never gives a verdict (PEM103 / PEM107 today)
    (np.nan, 0.01, -0.1, "unclear"),
    (-2.5, np.nan, -0.1, "unclear"),
])
def test_verdict_rule(t, w_p, median, expected):
    assert sig.verdict_for(t, w_p, median, 2.0, 0.05) == expected


def test_compute_uses_top_down_minus_other_and_item_level_pairs():
    """Top-down always 1 lower than Direct for every item and origin: better, relative difference negative, t negative."""
    rng = np.random.default_rng(3)
    rows = []
    for i in range(40):
        base = 10 + rng.normal(0, 3)
        for origin in range(1, 8):
            noise = rng.normal(0, 0.2)
            rows.append(("D1", f"I{i}", origin, "Direct", base + noise, "2025-03", "2025-08"))
            rows.append(("D1", f"I{i}", origin, "Top-down", base + noise - 1, "2025-03", "2025-08"))
            rows.append(("D1", f"I{i}", origin, "Naive", base + noise + 2, "2025-03", "2025-08"))
    df = pd.DataFrame(rows, columns=["division", "itemcode", "origin", "approach", "MAE", "first_test_month", "last_test_month"])
    out = sig.compute(df, 2.0, 0.05, "2026-01-01 00:00:00").set_index("other_method")
    assert out.loc["Direct", "mean_diff"] == pytest.approx(-1.0, abs=1e-9) and out.loc["Direct", "t_stat"] < -10
    assert out.loc["Direct", "verdict"] == "better" and out.loc["Direct", "median_sign"] == -1
    assert out.loc["Direct", "rel_diff_pct"] == pytest.approx(100 * -1.0 / df[df.approach == "Direct"].MAE.mean(), rel=1e-6)
    assert out.loc["Naive", "mean_diff"] == pytest.approx(-3.0, abs=1e-9) and out.loc["Naive", "verdict"] == "better"
    # an item with no Top-down forecast is left out of the pairs
    df2 = df[~((df.itemcode == "I0") & (df.approach == "Top-down"))]
    assert sig.compute(df2, 2.0, 0.05).set_index("other_method").loc["Direct", "n_items"] == 39


def test_sign_disagreement_between_t_and_median_gives_unclear():
    """Most items slightly better, a few much worse: median negative but mean (and t) positive and large -> not a verdict."""
    rows = []
    for i in range(30):
        worse = i < 3
        for origin in range(1, 4):
            rows.append(("D1", f"I{i}", origin, "Direct", 10.0))
            rows.append(("D1", f"I{i}", origin, "Top-down", 10.0 + (300.0 if worse else -0.5) + (0.01 * i)))
            rows.append(("D1", f"I{i}", origin, "Naive", 10.0))
    df = pd.DataFrame(rows, columns=["division", "itemcode", "origin", "approach", "MAE"])
    df["first_test_month"] = "2025-03"; df["last_test_month"] = "2025-08"
    r = sig.compute(df, 2.0, 0.05).set_index("other_method").loc["Direct"]
    assert r["median_diff"] < 0 and r["mean_diff"] > 0
    assert r["verdict"] == "unclear"


# ------------------------------------------------------------------ the block's text
def _rows(**by_div):
    """{division: (verdict, rel_diff_pct)} -> rows of one comparison."""
    return pd.DataFrame([{"division": d, "other_method": "Direct", "verdict": v, "rel_diff_pct": p} for d, (v, p) in by_div.items()])


def test_line_for_each_verdict_combination():
    heading = br.SIGNIFICANCE_LINES["Direct"]
    assert heading == "เทียบกับการทายรายรหัสตรงๆ:" and br.SIGNIFICANCE_LINES["Naive"] == "เทียบกับการใช้ยอดเดือนล่าสุดเป็นค่าทาย:"
    assert br.SIGNIFICANCE_HEADING == "ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม"
    assert br.SIGNIFICANCE_CLOSING == "ที่เลือกใช้ Top-down เพราะแม่นใกล้เคียงหรือดีกว่าวิธีอื่น และใช้วิธีเดียวได้ทุกฝ่าย"
    # all unclear: one phrase, divisions joined by ", "
    assert br.significance_line(_rows(A=("unclear", 1.0), B=("unclear", -3.0)), "Direct") == \
        heading + " A, B ใกล้เคียงกันจนบอกไม่ได้ว่าวิธีไหนดีกว่า"
    # better only, large and small
    assert br.significance_line(_rows(A=("better", -20.0)), "Direct") == \
        heading + " A ทายพลาดน้อยกว่าประมาณ 20% ทดสอบแล้วความต่างนี้เกิดจริง"
    assert br.significance_line(_rows(A=("better", -1.38)), "Direct") == \
        heading + " A ทายพลาดน้อยกว่าประมาณ 1.4% ทดสอบแล้วความต่างนี้เกิดจริง แม้จะเล็ก"
    # worse only
    assert br.significance_line(_rows(A=("worse", 12.4)), "Direct") == \
        heading + " A ทายพลาดมากกว่าประมาณ 12% ทดสอบแล้วความต่างนี้เกิดจริง"
    # everything: better first (one per division, data order), then worse, then the unclear group, joined by " · "
    mixed = br.significance_line(_rows(Z=("unclear", 0.5), A=("worse", 7.26), B=("better", -4.9), C=("better", -30.0), D=("unclear", 9.0)), "Direct")
    assert mixed == (heading + " B ทายพลาดน้อยกว่าประมาณ 4.9% ทดสอบแล้วความต่างนี้เกิดจริง แม้จะเล็ก"
                     " · C ทายพลาดน้อยกว่าประมาณ 30% ทดสอบแล้วความต่างนี้เกิดจริง"
                     " · A ทายพลาดมากกว่าประมาณ 7.3% ทดสอบแล้วความต่างนี้เกิดจริง"
                     " · Z, D ใกล้เคียงกันจนบอกไม่ได้ว่าวิธีไหนดีกว่า")


@pytest.mark.parametrize("value,text", [(1.38, "1.4"), (9.94, "9.9"), (9.96, "10"), (10.4, "10"), (20.0, "20"), (19.5, "20"), (0.04, "0.0"), (-1.38, "1.4")])
def test_percentage_rounding(value, text):
    assert br.significance_pct_text(value) == text


def test_small_phrase_threshold_is_five_percent():
    assert "แม้จะเล็ก" in br.significance_line(_rows(A=("better", -4.99)), "Direct")
    assert "แม้จะเล็ก" not in br.significance_line(_rows(A=("better", -5.0)), "Direct")


def test_block_on_the_recorded_output_reads_as_expected_today():
    path = os.path.join(PROJECT_ROOT, "output", "summary", "topdown_significance.csv")
    if not os.path.exists(path):
        pytest.skip("SKIPPED, not passed: output/summary/topdown_significance.csv is not on disk (the monthly runner writes it)")
    df = pd.read_csv(path)
    html_block = br.significance_block_html(df)
    for other in ("Direct", "Naive"):
        line = br.significance_line(df[df["other_method"] == other], other)
        assert line in html_block.replace("&amp;", "&")
    assert html_block.startswith("<h3>ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม</h3>") and "<!-- source: output/summary/topdown_significance.csv" in html_block
    assert html_block.rstrip().endswith("<p>ที่เลือกใช้ Top-down เพราะแม่นใกล้เคียงหรือดีกว่าวิธีอื่น และใช้วิธีเดียวได้ทุกฝ่าย</p>")


def test_the_sales_report_no_longer_cites_the_frozen_pilot_result():
    text = open(os.path.join(PROJECT_ROOT, "forecast", "sales_report.html"), encoding="utf-8").read()
    assert "b3_paired_significance" not in text
    assert "ใช้วิธี Top-down ดีกว่าวิธีอื่นไหม" in text and "Direct และ Naive" not in text


# ------------------------------------------------------------------ the monthly runner computes it every run
def test_monthly_runner_step4_computes_the_significance_and_dry_runs_reach_it():
    import inspect
    import monthly_refresh as mr
    source = inspect.getsource(mr.step4_backtest)
    assert '"significance_topdown.py", "topdown_significance.csv"' in source
    # it follows the transferability script (its input) in the same step, and takes no skip reason (no database), so
    # dry runs and offline runs execute it too
    assert source.index("transferability_all_divisions.py") < source.index("significance_topdown.py")
    call = source[source.index('_run_regeneration_step("Top-down significance'):source.index('"topdown_significance.csv"))') + 30]
    assert "skip_reason" not in call
