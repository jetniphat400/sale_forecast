"""Phase E1-fix-2, Part 5: mandatory visual verification of forecast/inventory.html and
forecast/sales_report.html via raw CDP over WebSocket, per the task's own PROCESS SAFETY RULE:
never terminate any browser by name; launch our own Edge instance, record its PID, close only
that PID (and its own child processes, via a PID-scoped, not image-name-scoped, kill as a
fallback after a graceful CDP Browser.close).

Serves the project root over plain HTTP (Python's own http.server, our own subprocess, tracked
and torn down the same way) so relative links between index.html and forecast/*.html resolve
exactly as they do for a real user, and so the dashboard-link check is meaningful.

Writes screenshots to output/charts/inventory_verification/ and prints a pass/fail line per
check. Never left running: browser and server processes are torn down in a `finally` block even
on error, and the temp Edge profile directory is deleted afterward.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phaseE1fix2_part5_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "inventory_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9222
HTTP_PORT = 8791
CDP_BASE = f"http://127.0.0.1:{CDP_PORT}"
HTTP_BASE = f"http://127.0.0.1:{HTTP_PORT}"

results = []  # (label, passed: bool, detail: str)


def record(label, passed, detail=""):
    results.append((label, passed, detail))
    logger.info("[%s] %s -- %s", "PASS" if passed else "FAIL", label, detail)


class CdpTab:
    """One CDP target (browser tab), talked to over its own raw WebSocket connection."""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self._id = 0

    def send(self, method, params=None, timeout=20):
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} error: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(f"CDP {method} timed out")

    def navigate_and_wait(self, url, timeout=30):
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("method") == "Page.loadEventFired":
                return
        raise TimeoutError(f"Page.loadEventFired not seen for {url} within {timeout}s")

    def eval_js(self, expression):
        result = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(f"JS error evaluating {expression!r}: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def screenshot(self, path):
        result = self.send("Page.captureScreenshot", {"format": "png"}, timeout=30)
        import base64
        with open(path, "wb") as f:
            f.write(base64.b64decode(result["data"]))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


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
    tabs = []

    try:
        # ---- 1. Serve the project root over plain HTTP (our own subprocess) ----
        http_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(HTTP_PORT)],
            cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Local HTTP server started, PID=%d, serving %s on port %d",
                    http_proc.pid, PROJECT_ROOT, HTTP_PORT)
        wait_for_http(f"{HTTP_BASE}/index.html")

        # ---- 2. Launch our OWN Edge instance: remote-debugging-port + a user-data-dir under the
        # system temp folder (never the drive root). PID recorded immediately. ----
        tmp_profile = tempfile.mkdtemp(prefix="edge_cdp_verify_")
        logger.info("Temp Edge profile dir: %s (under %s, not a drive root)",
                    tmp_profile, tempfile.gettempdir())
        edge_cmd = [
            EDGE_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={tmp_profile}",
            "--no-first-run", "--no-default-browser-check",
            "--headless=new", "--disable-extensions",
            "--remote-allow-origins=*",  # Chromium >=111 rejects our WebSocket's Origin header otherwise
        ]
        edge_proc = subprocess.Popen(edge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        edge_pid = edge_proc.pid
        logger.info("Launched msedge.exe, PID=%d -- this is the ONLY PID this script will close.", edge_pid)
        wait_for_http(f"{CDP_BASE}/json/version", timeout=20)

        # ---- 3. Dashboard link check (index.html -> forecast/inventory.html, forecast/sales_report.html) ----
        idx = requests.get(f"{HTTP_BASE}/index.html", timeout=10)
        has_inv_link = 'href="forecast/inventory.html"' in idx.text
        has_sales_link = 'href="forecast/sales_report.html"' in idx.text
        inv_resolves = requests.get(f"{HTTP_BASE}/forecast/inventory.html", timeout=10).status_code == 200
        sales_resolves = requests.get(f"{HTTP_BASE}/forecast/sales_report.html", timeout=10).status_code == 200
        record("dashboard Inventory link present + resolves", has_inv_link and inv_resolves,
               f"href present={has_inv_link}, GET forecast/inventory.html status ok={inv_resolves}")
        record("dashboard Sales link present + resolves", has_sales_link and sales_resolves,
               f"href present={has_sales_link}, GET forecast/sales_report.html status ok={sales_resolves}")

        # ---- 4. Open a tab, verify inventory.html ----
        new_target = requests.put(f"{CDP_BASE}/json/new?{HTTP_BASE}/forecast/inventory.html", timeout=10).json()
        tab = CdpTab(new_target["webSocketDebuggerUrl"])
        tabs.append((new_target["id"], tab))
        tab.send("Runtime.enable")
        # loadEventFired may already have fired before we attached Page.enable via /json/new; force
        # a fresh navigation so navigate_and_wait can observe it deterministically.
        tab.navigate_and_wait(f"{HTTP_BASE}/forecast/inventory.html")
        time.sleep(1.0)  # let Plotly.newPlot's initial render + onControlChange() settle

        n_charts_rendered = tab.eval_js(
            "document.querySelectorAll('.plotly-chart svg.main-svg').length")
        record("inventory.html: both Plotly chart containers have rendered content",
               n_charts_rendered >= 2, f"{n_charts_rendered} chart <svg class=main-svg> elements found (expect >=2)")

        disclaimer_visible = tab.eval_js(
            "(() => { const el = document.querySelector('.note-box'); "
            "if (!el) return false; const r = el.getBoundingClientRect(); "
            "return r.height > 0 && r.width > 0 && getComputedStyle(el).visibility !== 'hidden'; })()")
        record("inventory.html: scenario disclaimer (.note-box) visible", bool(disclaimer_visible))

        stock_value_before = tab.eval_js("document.getElementById('tot-stock-value').textContent")
        tradeoff_data_before = tab.eval_js(
            "JSON.stringify(document.getElementById('chart-tradeoff').data.map(t => t.y))")

        screenshot_default = os.path.join(OUT_DIR, "inventory_default.png")
        tab.screenshot(screenshot_default)
        logger.info("Saved default-scenario screenshot: %s", screenshot_default)

        # Change a Tier A control (procurement lead time slider) and dispatch a real 'input' event
        # -- the page's own event handler, not a hand-written recompute.
        tab.eval_js(
            "(() => { const el = document.getElementById('ctrl-procurement_lead_time_days'); "
            "el.value = 90; el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
        time.sleep(0.8)

        stock_value_after = tab.eval_js("document.getElementById('tot-stock-value').textContent")
        record("inventory.html: control change updates displayed stock_value",
               stock_value_before != stock_value_after,
               f"before={stock_value_before!r} after={stock_value_after!r}")

        tradeoff_data_after = tab.eval_js(
            "JSON.stringify(document.getElementById('chart-tradeoff').data.map(t => t.y))")
        record("inventory.html: trade-off chart redraws on control change",
               tradeoff_data_before != tradeoff_data_after,
               "chart-tradeoff series y-values changed" if tradeoff_data_before != tradeoff_data_after
               else "chart-tradeoff series y-values UNCHANGED")

        screenshot_changed = os.path.join(OUT_DIR, "inventory_changed_scenario.png")
        tab.screenshot(screenshot_changed)
        logger.info("Saved changed-scenario screenshot: %s", screenshot_changed)

        # Table sort check
        first_col_before = tab.eval_js(
            "Array.from(document.querySelectorAll('#item-table-body tr')).slice(0,5)"
            ".map(tr => tr.children[0].textContent)")
        tab.eval_js("document.querySelectorAll('#item-table thead th')[2].click()")  # sort by Min
        time.sleep(0.3)
        first_col_after = tab.eval_js(
            "Array.from(document.querySelectorAll('#item-table-body tr')).slice(0,5)"
            ".map(tr => tr.children[0].textContent)")
        record("inventory.html: table sorts on header click", first_col_before != first_col_after,
               f"before={first_col_before} after={first_col_after}")

        # ---- 5. Open a tab, verify sales_report.html ----
        new_target2 = requests.put(f"{CDP_BASE}/json/new?{HTTP_BASE}/forecast/sales_report.html", timeout=10).json()
        tab2 = CdpTab(new_target2["webSocketDebuggerUrl"])
        tabs.append((new_target2["id"], tab2))
        tab2.send("Runtime.enable")
        tab2.navigate_and_wait(f"{HTTP_BASE}/forecast/sales_report.html")
        time.sleep(1.2)

        n_charts2 = tab2.eval_js("document.querySelectorAll('.plotly-chart svg.main-svg').length")
        record("sales_report.html: Plotly chart containers have rendered content",
               n_charts2 >= 4, f"{n_charts2} chart <svg class=main-svg> elements found (expect >=4 of 5)")

        disclaimer_visible2 = tab2.eval_js(
            "(() => { const el = document.querySelector('.note-box'); "
            "if (!el) return false; const r = el.getBoundingClientRect(); "
            "return r.height > 0 && r.width > 0 && getComputedStyle(el).visibility !== 'hidden'; })()")
        record("sales_report.html: scenario disclaimer (.note-box) visible", bool(disclaimer_visible2))

        fva_before = tab2.eval_js(
            "JSON.stringify((document.getElementById('chart-fva')||{}).data ? "
            "document.getElementById('chart-fva').data.map(t=>t.y) : null)")
        tab2.eval_js(
            "(() => { const sel = document.getElementById('filterOrigin'); "
            "sel.value = sel.options[sel.options.length-1].value; "
            "sel.dispatchEvent(new Event('change', {bubbles: true})); return true; })()")
        time.sleep(0.8)
        fva_after = tab2.eval_js(
            "JSON.stringify((document.getElementById('chart-fva')||{}).data ? "
            "document.getElementById('chart-fva').data.map(t=>t.y) : null)")
        record("sales_report.html: control (Rolling origin) changes displayed chart data",
               fva_before != fva_after, f"chart-fva data changed={fva_before != fva_after}")

        record("sales_report.html: sortable table check", None,
               "N/A -- this page has no click-to-sort table (src/build_report.py has no sortTable "
               "handler); not fabricated as pass or fail.")

        screenshot_sales = os.path.join(OUT_DIR, "sales_report_default.png")
        tab2.screenshot(screenshot_sales)
        logger.info("Saved sales_report.html screenshot: %s", screenshot_sales)

    finally:
        # ---- Teardown: close tabs, close the browser via CDP, then verify/enforce by PID only ----
        for target_id, tab in tabs:
            try:
                tab.close()
            except Exception:
                pass
            try:
                requests.get(f"{CDP_BASE}/json/close/{target_id}", timeout=5)
            except Exception:
                pass

        if edge_proc is not None:
            edge_pid = edge_proc.pid
            try:
                requests.get(f"{CDP_BASE}/json/close", timeout=3)
            except Exception:
                pass
            try:
                ver = requests.get(f"{CDP_BASE}/json/version", timeout=2)
                still_up = ver.status_code == 200
            except Exception:
                still_up = False
            if still_up or edge_proc.poll() is None:
                logger.info("Closing Edge by PID %d only (never by image name).", edge_pid)
                subprocess.run(["taskkill", "/PID", str(edge_pid), "/T", "/F"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            edge_proc.wait(timeout=15)
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
    print("PART 5 -- CDP VISUAL VERIFICATION RESULTS")
    print("=" * 90)
    n_pass = n_fail = n_na = 0
    for label, passed, detail in results:
        tag = "N/A " if passed is None else ("PASS" if passed else "FAIL")
        if passed is None:
            n_na += 1
        elif passed:
            n_pass += 1
        else:
            n_fail += 1
        print(f"[{tag}] {label} -- {detail}")
    print(f"\n{n_pass} passed, {n_fail} failed, {n_na} N/A")
    return {"n_pass": n_pass, "n_fail": n_fail, "n_na": n_na, "results": results}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["n_fail"] == 0 else 1)
