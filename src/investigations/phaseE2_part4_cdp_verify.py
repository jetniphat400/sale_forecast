"""Phase E2 Part 4: visual verification of the multi-division inventory.html via raw CDP over
WebSocket. Verifies: switching division changes every figure and the warehouse checklist, the
disabled entries (CI101/PEM102/PEM104) show their exclusion note, controls still work for each
enabled division, and the trade-off chart redraws per division. Screenshots each enabled division
at the default scenario.

Same PROCESS SAFETY RULE as prior rounds: launch our own Edge instance, record its PID, close
only that PID (graceful CDP Browser.close first, then a PID-scoped taskkill fallback -- never by
image name), temp profile under the system temp folder, deleted afterward.
"""
import base64
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
logger = logging.getLogger("phaseE2_part4_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "inventory_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9222
HTTP_PORT = 8793
CDP_BASE = f"http://127.0.0.1:{CDP_PORT}"
HTTP_BASE = f"http://127.0.0.1:{HTTP_PORT}"
DIVISIONS = ["PEM101", "PEM103", "PEM107"]
DISABLED_DIVISIONS = ["CI101", "PEM102", "PEM104"]

results = []


def record(label, passed, detail=""):
    results.append((label, passed, detail))
    logger.info("[%s] %s -- %s", "PASS" if passed else "FAIL", label, detail)


class CdpTab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self._id = 0

    def send(self, method, params=None, timeout=20):
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
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
            msg = json.loads(self.ws.recv())
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
        http_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(HTTP_PORT)],
            cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Local HTTP server started, PID=%d, serving %s on port %d",
                    http_proc.pid, PROJECT_ROOT, HTTP_PORT)
        wait_for_http(f"{HTTP_BASE}/index.html")

        tmp_profile = tempfile.mkdtemp(prefix="edge_cdp_verify_")
        logger.info("Temp Edge profile dir: %s (under %s, not a drive root)",
                    tmp_profile, tempfile.gettempdir())
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

        new_target = requests.put(f"{CDP_BASE}/json/new?{HTTP_BASE}/forecast/inventory.html", timeout=10).json()
        tab = CdpTab(new_target["webSocketDebuggerUrl"])
        tabs.append((new_target["id"], tab))
        tab.send("Runtime.enable")
        tab.navigate_and_wait(f"{HTTP_BASE}/forecast/inventory.html")
        time.sleep(1.0)

        # ---- Disabled entries show their note ----
        disabled_opts = tab.eval_js(
            "Array.from(document.querySelectorAll('#division-select option[disabled]'))"
            ".map(o => ({value: o.value, title: o.title, text: o.textContent}))")
        all_have_title = all(o["title"] for o in disabled_opts) if disabled_opts else False
        record("disabled <option> entries carry a non-empty exclusion note (title attribute)",
               len(disabled_opts) == 3 and all_have_title, f"{disabled_opts}")

        note_list_text = tab.eval_js("document.getElementById('disabled-note-list').textContent")
        all_named = all(d in note_list_text for d in DISABLED_DIVISIONS)
        record("visible disabled-note-list names all 3 excluded divisions with a reason",
               all_named, f"contains all of {DISABLED_DIVISIONS}: {all_named}")

        # ---- Per-division checks: switching changes figures + checklist; controls work; chart redraws ----
        prev_stock_value = None
        prev_checklist = None
        for division in DIVISIONS:
            tab.eval_js(f"document.getElementById('division-select').value = {json.dumps(division)}; "
                        f"onDivisionChange(); true;")
            time.sleep(0.6)

            title = tab.eval_js("document.getElementById('page-title').textContent")
            record(f"[{division}] page title updated to mention the division", division in title, title)

            stock_value = tab.eval_js("document.getElementById('tot-stock-value').textContent")
            record(f"[{division}] totals show a real stock_value", bool(stock_value) and stock_value != "-", stock_value)
            if prev_stock_value is not None:
                record(f"[{division}] stock_value differs from the previous division",
                       stock_value != prev_stock_value, f"prev={prev_stock_value!r} now={stock_value!r}")
            prev_stock_value = stock_value

            checklist = tab.eval_js(
                "Array.from(document.querySelectorAll('#warehouse-checklist .item-check')).map(l => l.textContent.trim())")
            record(f"[{division}] warehouse checklist is non-empty", len(checklist) > 0, f"{checklist}")
            if prev_checklist is not None:
                record(f"[{division}] warehouse checklist differs from the previous division",
                       checklist != prev_checklist, f"prev={prev_checklist} now={checklist}")
            prev_checklist = checklist

            n_charts = tab.eval_js("document.querySelectorAll('.plotly-chart svg.main-svg').length")
            record(f"[{division}] both Plotly charts rendered", n_charts >= 2, f"{n_charts} chart svg elements")

            tradeoff_before = tab.eval_js(
                "JSON.stringify(document.getElementById('chart-tradeoff').data.map(t => t.y))")
            tab.eval_js(
                "(() => { const el = document.getElementById('ctrl-procurement_lead_time_days'); "
                "el.value = 90; el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
            time.sleep(0.6)
            stock_value_after_control = tab.eval_js("document.getElementById('tot-stock-value').textContent")
            record(f"[{division}] control change updates the displayed stock_value",
                   stock_value_after_control != stock_value,
                   f"before={stock_value!r} after={stock_value_after_control!r}")
            tradeoff_after = tab.eval_js(
                "JSON.stringify(document.getElementById('chart-tradeoff').data.map(t => t.y))")
            record(f"[{division}] trade-off chart redraws on control change",
                   tradeoff_before != tradeoff_after, "chart-tradeoff series changed")

            screenshot_path = os.path.join(OUT_DIR, f"e2_{division.lower()}_default.png")
            # reset the control back to default before screenshotting "at the default scenario"
            tab.eval_js(
                "(() => { const el = document.getElementById('ctrl-procurement_lead_time_days'); "
                "el.value = 60; el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
            time.sleep(0.5)
            tab.screenshot(screenshot_path)
            logger.info("Saved %s screenshot: %s", division, screenshot_path)

    finally:
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
                still_up = requests.get(f"{CDP_BASE}/json/version", timeout=2).status_code == 200
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
    print("PHASE E2 PART 4 -- CDP VISUAL VERIFICATION RESULTS (multi-division inventory.html)")
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
