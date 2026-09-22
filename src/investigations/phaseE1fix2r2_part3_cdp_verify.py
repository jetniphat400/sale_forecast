"""Phase E1-fix-2 (round 2), Part 3: visual re-verification of forecast/inventory.html via raw
CDP over WebSocket, after (a) adding the visible monthly-proration-vs-daily-window note and
(b) regenerating the embedded JSON from the Part 2 recompute.

Note on scope: the task's "confirm ... the four recomputed figures display" is read here as the
page's own displayed totals (stock_value, holding_cost, n_items -- the figures this page has
ALWAYS displayed and that respond to the Tier A controls), since forecast/inventory.html has never
displayed confirmed_total/open_demand_total/fill_rate/cycle_service_level -- those four are
produced by src/phaseE1fix_recompute.py, src/phaseE1fix_simulation.py and
src/investigations/phaseE1fix_validator.py directly (console + CSV, already verified in Part 2),
not by this interactive page. Flagged explicitly rather than silently assumed.

Same PROCESS SAFETY RULE as before: launch our own Edge, record its PID, close only that PID.
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
logger = logging.getLogger("phaseE1fix2r2_part3_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "inventory_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9222
HTTP_PORT = 8792
CDP_BASE = f"http://127.0.0.1:{CDP_PORT}"
HTTP_BASE = f"http://127.0.0.1:{HTTP_PORT}"

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

        # ---- Proration note visible, and contains "3.3" ----
        note_check = tab.eval_js(
            "(() => { const el = document.getElementById('proration-note'); "
            "if (!el) return {found: false}; const r = el.getBoundingClientRect(); "
            "return {found: true, visible: r.height > 0 && r.width > 0 && "
            "getComputedStyle(el).visibility !== 'hidden', text: el.textContent}; })()")
        has_pct = bool(note_check and note_check.get("text") and "3.3" in note_check["text"])
        record("inventory.html: monthly-proration note (#proration-note) present and visible",
               bool(note_check and note_check.get("found") and note_check.get("visible")),
               f"found={note_check.get('found') if note_check else None}, "
               f"visible={note_check.get('visible') if note_check else None}")
        record("inventory.html: proration note states the observed 3.3% figure", has_pct,
               "contains '3.3'" if has_pct else "does NOT contain '3.3'")

        disclaimer_visible = tab.eval_js(
            "(() => { const el = document.querySelector('.note-box'); "
            "if (!el) return false; const r = el.getBoundingClientRect(); "
            "return r.height > 0 && r.width > 0; })()")
        record("inventory.html: scenario disclaimer (.note-box) still visible", bool(disclaimer_visible))

        n_charts_rendered = tab.eval_js("document.querySelectorAll('.plotly-chart svg.main-svg').length")
        record("inventory.html: both Plotly chart containers have rendered content",
               n_charts_rendered >= 2, f"{n_charts_rendered} chart <svg class=main-svg> elements found")

        # ---- "the four recomputed figures display" -- read as this page's own displayed
        # totals (stock_value, holding_cost, n_items), which DO come from the same Part 2
        # recompute pipeline and DO respond live to the Tier A controls; the page has never
        # displayed confirmed_total/open_demand_total/fill_rate/cycle_service_level (produced
        # by separate scripts, verified in Part 2's console+CSV output, not on this page). ----
        totals_before = tab.eval_js(
            "({stockValue: document.getElementById('tot-stock-value').textContent, "
            "holdingCost: document.getElementById('tot-holding-cost').textContent, "
            "nItems: document.getElementById('tot-n-items').textContent})")
        all_nonblank = all(v and v.strip() not in ("", "-") for v in totals_before.values())
        record("inventory.html: displayed totals (stock_value/holding_cost/n_items) show real values",
               all_nonblank, f"{totals_before}")

        screenshot_default = os.path.join(OUT_DIR, "r2_inventory_default.png")
        tab.screenshot(screenshot_default)
        logger.info("Saved default-scenario screenshot: %s", screenshot_default)

        tab.eval_js(
            "(() => { const el = document.getElementById('ctrl-procurement_lead_time_days'); "
            "el.value = 90; el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
        time.sleep(0.8)
        totals_after = tab.eval_js(
            "({stockValue: document.getElementById('tot-stock-value').textContent, "
            "holdingCost: document.getElementById('tot-holding-cost').textContent, "
            "nItems: document.getElementById('tot-n-items').textContent})")
        record("inventory.html: control change updates the displayed totals",
               totals_before["stockValue"] != totals_after["stockValue"],
               f"before={totals_before['stockValue']!r} after={totals_after['stockValue']!r}")

        screenshot_changed = os.path.join(OUT_DIR, "r2_inventory_changed_scenario.png")
        tab.screenshot(screenshot_changed)
        logger.info("Saved changed-scenario screenshot: %s", screenshot_changed)

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
    print("PHASE E1-FIX-2 (ROUND 2), PART 3 -- CDP RE-VERIFICATION RESULTS")
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
