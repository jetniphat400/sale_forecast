"""Phase 23, Part 6: CDP visual verification of forecast/inventory.html's PEM101 selectable
not_late target -- each preset changes the per-item table/totals/band, the slider moves the
figures continuously, the note replaced the old robust/sensitive table, and every label renders.
Screenshots each preset into output/charts/inventory_verification/.

Same PROCESS SAFETY RULE as prior rounds: launch our own dedicated Edge instance
(--remote-debugging-port, --user-data-dir under the system temp folder), record its PID, close
only that PID (graceful CDP Browser.close first, then a PID-scoped taskkill fallback -- never by
image name), delete the temp profile afterward. No live database access.
"""
import base64
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("phase23_part6_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "inventory_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9224
HTTP_PORT = 8795
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
        logger.info("Local HTTP server started, PID=%d, port %d", http_proc.pid, HTTP_PORT)
        wait_for_http(f"{HTTP_BASE}/forecast/inventory.html")

        tmp_profile = tempfile.mkdtemp(prefix="edge_cdp_verify_")
        logger.info("Temp Edge profile dir: %s", tmp_profile)
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

        tab.eval_js("document.getElementById('division-select').value = 'PEM101'; onDivisionChange(); true;")
        time.sleep(0.8)

        # ---- note replaced the old table ----
        old_table_gone = tab.eval_js("document.getElementById('robust-item-table') === null")
        record("[PEM101] old robust-item-table is gone", old_table_gone, f"gone={old_table_gone}")

        section_visible = tab.eval_js(
            "getComputedStyle(document.getElementById('curve-target-section')).display !== 'none'")
        record("[PEM101] curve-target-section is visible", section_visible, f"visible={section_visible}")

        note_text = tab.eval_js(
            "Array.from(document.querySelectorAll('#curve-target-section p.hint')).map(p=>p.textContent).join(' | ')")
        note_ok = "reorder level" in note_text.lower() or "not_late" in note_text.lower()
        record("[PEM101] note explains data cannot identify reorder level", note_ok, note_text[:200])

        summary_text = tab.eval_js("document.getElementById('curve-target-summary').textContent")
        mentions_80 = "80" in summary_text and "distinct" in summary_text.lower()
        record("[PEM101] summary states 80 distinct ensemble members", mentions_80, summary_text[:250])

        # ---- 3 presets, each changes the table/totals/band ----
        preset_ids = ["preset-today-lowest", "preset-highest-at-today", "preset-stretch"]
        preset_names = ["today_lowest_stock", "highest_at_today_stock", "stretch_99pct"]
        prev_totals = None
        prev_first_row = None
        for pid, pname in zip(preset_ids, preset_names):
            tab.eval_js(f"document.getElementById('{pid}').click(); true;")
            time.sleep(0.4)
            totals = tab.eval_js("document.getElementById('curve-target-totals').textContent")
            first_row = tab.eval_js(
                "(() => { const tr = document.querySelector('#curve-item-table-body tr'); "
                "return tr ? tr.textContent : null; })()")
            n_rows = tab.eval_js("document.querySelectorAll('#curve-item-table-body tr').length")
            slider_val = tab.eval_js("document.getElementById('notlate-slider').value")
            record(f"[{pname}] table has rows", n_rows > 0, f"{n_rows} rows")
            record(f"[{pname}] totals box populated", bool(totals) and len(totals.strip()) > 0, totals[:200])
            if prev_totals is not None:
                record(f"[{pname}] totals differ from previous preset", totals != prev_totals,
                       f"prev={prev_totals[:100]!r} now={totals[:100]!r}")
            if prev_first_row is not None:
                record(f"[{pname}] item table differs from previous preset", first_row != prev_first_row,
                       f"prev={prev_first_row!r} now={first_row!r}")
            prev_totals = totals
            prev_first_row = first_row

            screenshot_path = os.path.join(OUT_DIR, f"phase23_pem101_preset_{pname}.png")
            tab.eval_js("document.getElementById('curve-target-section').scrollIntoView({block:'start'}); true;")
            time.sleep(0.4)
            tab.screenshot(screenshot_path)
            logger.info("Saved preset screenshot (%s): %s, slider=%s", pname, screenshot_path, slider_val)

        # ---- slider moves the figures continuously ----
        slider_min = float(tab.eval_js("parseFloat(document.getElementById('notlate-slider').min)"))
        slider_max = float(tab.eval_js("parseFloat(document.getElementById('notlate-slider').max)"))
        mid = (slider_min + slider_max) / 2
        stock_values = []
        for frac in [0.1, 0.3, 0.5, 0.7, 0.9]:
            target = slider_min + frac * (slider_max - slider_min)
            tab.eval_js(
                f"(() => {{ const el = document.getElementById('notlate-slider'); el.value = {target}; "
                f"applyCurveTarget({target}); return true; }})()")
            time.sleep(0.15)
            sv = tab.eval_js(
                "(() => { const t = document.getElementById('curve-target-totals').textContent; "
                "const m = t.match(/Stock value \\(median\\)([\\d,]+)/); return m ? m[1] : t; })()")
            stock_values.append(sv)
        distinct_values = len(set(stock_values))
        record("[PEM101] slider moves the figures continuously (5 distinct positions -> distinct stock values)",
               distinct_values >= 4, f"values at 5 slider fractions: {stock_values}")

        screenshot_path = os.path.join(OUT_DIR, "phase23_pem101_slider_position.png")
        tab.screenshot(screenshot_path)

        # ---- labels ----
        tier_a_header = tab.eval_js(
            "(() => { const hs = Array.from(document.querySelectorAll('h2')); "
            "const h = hs.find(h => h.textContent.toLowerCase().includes('tier a')); "
            "return h ? h.textContent : null; })()")
        tier_a_labeled = bool(tier_a_header) and (
            "scenario" in tier_a_header.lower() or "uncalibrated" in tier_a_header.lower())
        record("[PEM101] Tier A header labeled as scenario tool / uncalibrated", tier_a_labeled, f"{tier_a_header}")

        for division, expect_substr in [("PEM103", "g3"), ("PEM107", "uncalibrat")]:
            tab.eval_js(f"document.getElementById('division-select').value = {json.dumps(division)}; "
                        f"onDivisionChange(); true;")
            time.sleep(0.5)
            note = tab.eval_js("document.getElementById('scope-note').textContent")
            has_note = bool(note) and expect_substr.lower() in note.lower()
            record(f"[{division}] division note mentions '{expect_substr}'", has_note, f"{note}")

        pem104_opt = tab.eval_js(
            "(() => { const o = document.querySelector('#division-select option[value=\"PEM104\"]'); "
            "return o ? {title: o.title, text: o.textContent} : null; })()")
        pem104_ok = bool(pem104_opt) and "made to order" in (pem104_opt.get("text", "") + pem104_opt.get("title", "")).lower()
        record("[PEM104] option labeled 'made to order (excluded)'", pem104_ok, f"{pem104_opt}")

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
            logger.info("Local HTTP server stopped.")

    print("\n" + "=" * 90)
    print("PHASE 23 PART 6 -- CDP VISUAL VERIFICATION RESULTS (PEM101 selectable not_late target)")
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
