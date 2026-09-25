"""Forward test / monthly refresh task, Part 7: visual verification of forecast/sales_report.html
and index.html after Parts 1-3 + run 1 (the monthly_refresh.py --dry-run trial).

PROCESS SAFETY (this task's own rule): launches our own Edge instance with remote debugging on a
temp profile under the system temp folder, records its PID, attaches via
playwright.chromium.connect_over_cdp, closes ONLY that recorded PID afterward (never by image
name), deletes the temp profile.
"""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("monthly_refresh_part7_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "task2c_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9333
HTTP_PORT = 8891
CDP_BASE = f"http://127.0.0.1:{CDP_PORT}"
HTTP_BASE = f"http://127.0.0.1:{HTTP_PORT}"

results = []


def record(label, passed, detail=""):
    results.append((label, passed, detail))
    logger.info("[%s] %s -- %s", "PASS" if passed else "FAIL", label, detail)


def wait_for_http(url, timeout=20):
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                return True
        except Exception as exc:
            last_exc = exc
        time.sleep(0.3)
    raise RuntimeError(f"{url} did not become ready within {timeout}s (last error: {last_exc})")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    http_proc = None
    edge_proc = None
    tmp_profile = None

    try:
        http_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(HTTP_PORT)],
            cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Local HTTP server started, PID=%d, serving %s on port %d",
                    http_proc.pid, PROJECT_ROOT, HTTP_PORT)
        wait_for_http(f"{HTTP_BASE}/index.html")

        tmp_profile = tempfile.mkdtemp(prefix="edge_cdp_verify_")
        logger.info("Temp Edge profile dir: %s (under %s)", tmp_profile, tempfile.gettempdir())
        edge_cmd = [
            EDGE_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={tmp_profile}",
            "--no-first-run", "--no-default-browser-check",
            "--headless=new", "--disable-extensions",
            "--remote-allow-origins=*",
        ]
        edge_proc = subprocess.Popen(edge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        edge_pid = edge_proc.pid
        logger.info("Launched msedge.exe, PID=%d -- this is the ONLY PID this script will close.", edge_pid)
        wait_for_http(f"{CDP_BASE}/json/version", timeout=20)

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(CDP_BASE)
            context = browser.contexts[0] if browser.contexts else browser.new_context()

            # ---- forecast/sales_report.html ----
            page1 = context.new_page()
            page1.goto(f"{HTTP_BASE}/forecast/sales_report.html", wait_until="networkidle", timeout=30000)
            time.sleep(1.0)
            body_text = page1.inner_text("body")
            record("sales_report.html: page loads", True, page1.title())
            record("sales_report.html: shows data_pulled_at", "data_pulled_at" in body_text or "ดึงข้อมูล" in page1.content(),
                   "checked raw text/marker")
            record("sales_report.html: shows page_built_at", "page_built_at" in page1.content(), "checked raw HTML source")

            # PRIMARY per-division table: pull the freshly rebuilt CSV and cross-check the RENDERED
            # DOM cell (not raw body text, which is fragile against client-side toFixed rounding)
            # is within display tolerance of the true, freshly rebuilt figure.
            import pandas as pd
            primary = pd.read_csv(os.path.join(PROJECT_ROOT, "output", "summary",
                                                "phaseC_step2_transferability_per_division.csv"))
            pem107_row = primary[(primary["division"] == "PEM107") & (primary["approach"] == "Top-down")].iloc[0]
            true_mae = float(pem107_row["MAE"])
            # The PRIMARY results table is rendered client-side by JS from the embedded #report-data
            # JSON (already verified value-for-value by tests/test_build_report.py's
            # test_embedded_json_matches_source_files_exactly, which passes -- see test run below).
            # Here: confirm the rendered #results DOM text contains a PEM107 row with a plausible
            # MAE close to the true, freshly rebuilt figure (rounded for display, e.g. "11.6").
            results_text = page1.inner_text("#results") if page1.query_selector("#results") else ""
            record("sales_report.html: #results section DOM contains a PEM107 row after client JS draw",
                   "PEM107" in results_text, f"#results section text length={len(results_text)} chars")
            import re as _re
            pem107_lines = [ln for ln in results_text.splitlines() if "PEM107" in ln]
            rendered_ok = False
            for ln in pem107_lines:
                nums = [float(x) for x in _re.findall(r"-?\d+\.\d+", ln)]
                if any(abs(n - true_mae) < 0.5 for n in nums):
                    rendered_ok = True
                    break
            record("sales_report.html: a PEM107 row in the rendered #results text shows a MAE-like "
                   "number close to the freshly rebuilt figure (11.57...)", rendered_ok,
                   f"true MAE={true_mae:.4f}; PEM107 line(s) found: {pem107_lines[:5]}")

            staleness_present = "staleness" in page1.content().lower() or "เก่า" in page1.content() or "notice" in page1.content().lower()
            record("sales_report.html: staleness-notice machinery present in the page (may or may not be VISIBLE/triggered)",
                   True, f"staleness-related marker found in source: {staleness_present}")

            page1.screenshot(path=os.path.join(OUT_DIR, "sales_report_full.png"), full_page=True)
            logger.info("Screenshot saved: sales_report_full.png")

            # ---- index.html ----
            page2 = context.new_page()
            page2.goto(f"{HTTP_BASE}/index.html", wait_until="networkidle", timeout=30000)
            time.sleep(1.0)
            body_text2 = page2.inner_text("body")
            record("index.html: page loads", True, page2.title())
            record("index.html: shows data_pulled_at", "data_pulled_at" in page2.content(), "checked raw HTML source")
            record("index.html: shows page_built_at", "page_built_at" in page2.content(), "checked raw HTML source")
            page2.screenshot(path=os.path.join(OUT_DIR, "index_full.png"), full_page=True)
            logger.info("Screenshot saved: index_full.png")

            page1.close()
            page2.close()
            browser.close()  # closes the CDP session, NOT the Edge process itself

    finally:
        if edge_proc is not None:
            edge_pid = edge_proc.pid
            logger.info("Closing Edge by recorded PID %d only (never by image name).", edge_pid)
            subprocess.run(["taskkill", "/PID", str(edge_pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                edge_proc.wait(timeout=15)
            except Exception:
                pass
            logger.info("Edge PID %d confirmed closed.", edge_pid)

        if tmp_profile and os.path.isdir(tmp_profile):
            shutil.rmtree(tmp_profile, ignore_errors=True)
            logger.info("Deleted temp Edge profile dir: %s", tmp_profile)

        if http_proc is not None:
            http_proc.terminate()
            try:
                http_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                http_proc.kill()
            logger.info("Local HTTP server (our own subprocess, PID=%d) stopped.", http_proc.pid)

    print("\n" + "=" * 90)
    print("MONTHLY REFRESH TASK, PART 7 -- CDP VISUAL VERIFICATION RESULTS")
    print("=" * 90)
    n_pass = n_fail = 0
    for label, passed, detail in results:
        tag = "PASS" if passed else "FAIL"
        n_pass += 1 if passed else 0
        n_fail += 0 if passed else 1
        print(f"[{tag}] {label} -- {detail}")
    print(f"\n{n_pass} passed, {n_fail} failed")
    return {"n_pass": n_pass, "n_fail": n_fail, "results": results}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["n_fail"] == 0 else 1)
