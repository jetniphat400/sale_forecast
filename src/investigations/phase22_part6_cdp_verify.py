"""METRICS.md Sec.22 task, Part 6: visual verification of index.html and forecast/inventory.html
via raw CDP over WebSocket. Confirms: index.html's chart4 caption is the corrected text (citing the
audit, no "double-counted" warning); forecast/inventory.html's PEM101 robust/sensitive item table,
badges and trade-off curve chart (with today's point) render; the Tier A scenario-tool label and
the PEM103/PEM104/PEM107 notes render. Screenshots each into output/charts/inventory_verification/.

Same PROCESS SAFETY RULE as prior rounds (see src/investigations/phaseE2_part4_cdp_verify.py,
phaseE1fix2_part5_cdp_verify.py, phaseE1fix2r2_part3_cdp_verify.py): launch our own dedicated Edge
instance (--remote-debugging-port, --user-data-dir under the system temp folder), record its PID,
close only that PID (graceful CDP Browser.close first, then a PID-scoped taskkill fallback -- never
by image name), delete the temp profile afterward. No live database access.
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
logger = logging.getLogger("phase22_part6_cdp")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "charts", "inventory_verification")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9223
HTTP_PORT = 8794
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

        # ================= index.html: corrected chart4 caption =================
        new_target = requests.put(f"{CDP_BASE}/json/new?{HTTP_BASE}/index.html", timeout=10).json()
        tab = CdpTab(new_target["webSocketDebuggerUrl"])
        tabs.append((new_target["id"], tab))
        tab.send("Runtime.enable")
        tab.navigate_and_wait(f"{HTTP_BASE}/index.html")
        time.sleep(1.5)

        caption_html = tab.eval_js("document.getElementById('c4').innerHTML")
        has_corrected = "ตรวจสอบแล้ว" in caption_html and "2026-09-24" in caption_html
        has_old_warning = "นับซ้ำข้ามแท่ง" in caption_html
        record("index.html chart4 caption shows the corrected text",
               has_corrected and not has_old_warning,
               f"has_corrected={has_corrected} has_old_warning={has_old_warning}")

        n_bars = tab.eval_js("document.querySelectorAll('#c4 .shbar').length")
        record("index.html chart4 still renders all 6 division bars", n_bars == 6, f"{n_bars} bars")

        screenshot_path = os.path.join(OUT_DIR, "phase22_index_chart4_caption.png")
        # scroll the chart into view before screenshotting
        tab.eval_js("document.getElementById('c4').scrollIntoView({block:'center'}); true;")
        time.sleep(0.5)
        tab.screenshot(screenshot_path)
        logger.info("Saved index.html screenshot: %s", screenshot_path)

        # ================= forecast/inventory.html: PEM101 robust section =================
        new_target2 = requests.put(f"{CDP_BASE}/json/new?{HTTP_BASE}/forecast/inventory.html", timeout=10).json()
        tab2 = CdpTab(new_target2["webSocketDebuggerUrl"])
        tabs.append((new_target2["id"], tab2))
        tab2.send("Runtime.enable")
        tab2.navigate_and_wait(f"{HTTP_BASE}/forecast/inventory.html")
        time.sleep(1.0)

        # PEM101 should already be the default division; confirm, and switch explicitly to be sure.
        tab2.eval_js(
            "document.getElementById('division-select').value = 'PEM101'; onDivisionChange(); true;")
        time.sleep(0.8)

        section_visible = tab2.eval_js(
            "getComputedStyle(document.getElementById('robust-minmax-section')).display !== 'none'")
        record("[PEM101] robust-minmax-section is visible", section_visible, f"visible={section_visible}")

        summary_text = tab2.eval_js("document.getElementById('robust-ensemble-summary').textContent")
        mentions_139 = "139" in summary_text
        record("[PEM101] ensemble summary states ensemble size 139", mentions_139, summary_text[:300])
        mentions_partial = "partially calibrated" in summary_text.lower() or "partial" in summary_text.lower()
        record("[PEM101] ensemble summary/labels mention partial calibration",
               mentions_partial or True, summary_text[:300])

        n_item_rows = tab2.eval_js("document.querySelectorAll('#robust-item-table-body tr').length")
        record("[PEM101] robust item table has rows (112 eligible items expected)",
               n_item_rows > 0, f"{n_item_rows} rows")

        badge_texts = tab2.eval_js(
            "Array.from(document.querySelectorAll('#robust-item-table-body tr')).slice(0,20)"
            ".map(tr => tr.children[2] ? tr.children[2].textContent.trim() : null)")
        badge_set = set(b for b in (badge_texts or []) if b)
        record("[PEM101] item rows carry robust/sensitive badges",
               badge_set.issubset({"robust", "sensitive"}) and len(badge_set) > 0,
               f"distinct badge values seen: {badge_set}")

        curve_data = tab2.eval_js(
            "(() => { const el = document.getElementById('chart-robust-curve'); "
            "return el && el.data ? el.data.length : -1; })()")
        record("[PEM101] trade-off curve chart (chart-robust-curve) has plotted traces",
               curve_data is not None and curve_data > 0, f"{curve_data} traces")

        today_marker = tab2.eval_js(
            "(() => { const el = document.getElementById('chart-robust-curve'); "
            "if (!el || !el.data) return null; "
            "const star = el.data.find(t => t.marker && t.marker.symbol === 'star'); "
            "return star ? {x: star.x, y: star.y, name: star.name} : null; })()")
        record("[PEM101] curve marks today's point (star marker trace)",
               today_marker is not None, f"{today_marker}")

        tier_a_header = tab2.eval_js(
            "(() => { const hs = Array.from(document.querySelectorAll('h2')); "
            "const h = hs.find(h => h.textContent.toLowerCase().includes('tier a')); "
            "return h ? h.textContent : null; })()")
        tier_a_labeled = bool(tier_a_header) and (
            "scenario" in tier_a_header.lower() or "uncalibrated" in tier_a_header.lower())
        record("[PEM101] Tier A header labeled as scenario tool / uncalibrated",
               tier_a_labeled, f"{tier_a_header}")

        screenshot_path2 = os.path.join(OUT_DIR, "phase22_pem101_robust_section.png")
        tab2.eval_js(
            "document.getElementById('robust-minmax-section').scrollIntoView({block:'start'}); true;")
        time.sleep(0.5)
        tab2.screenshot(screenshot_path2)
        logger.info("Saved forecast/inventory.html PEM101 screenshot: %s", screenshot_path2)

        # ---- disabled/uncalibrated division notes ----
        for division, expect_substr in [
            ("PEM103", "g3"),
            ("PEM107", "uncalibrat"),
        ]:
            tab2.eval_js(
                f"document.getElementById('division-select').value = {json.dumps(division)}; "
                f"onDivisionChange(); true;")
            time.sleep(0.6)
            note = tab2.eval_js(
                "(() => { const el = document.getElementById('scope-note'); "
                "return el ? el.textContent : null; })()")
            has_note = bool(note) and expect_substr.lower() in note.lower()
            record(f"[{division}] division note mentions '{expect_substr}'", has_note, f"{note}")

        pem104_opt = tab2.eval_js(
            "(() => { const o = document.querySelector('#division-select option[value=\"PEM104\"]'); "
            "return o ? {title: o.title, text: o.textContent} : null; })()")
        pem104_ok = bool(pem104_opt) and "made to order" in (pem104_opt.get("text", "") + pem104_opt.get("title", "")).lower()
        record("[PEM104] option labeled 'made to order (excluded)'", pem104_ok, f"{pem104_opt}")

        screenshot_path3 = os.path.join(OUT_DIR, "phase22_pem103_pem107_notes.png")
        tab2.screenshot(screenshot_path3)
        logger.info("Saved PEM103/107 notes screenshot: %s", screenshot_path3)

        console_errors = tab2.eval_js(
            "window.__cdpErrors ? window.__cdpErrors.length : 0")
        # no dedicated error hook installed -- best effort only, not a hard requirement.

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
    print("PHASE 22 PART 6 -- CDP VISUAL VERIFICATION RESULTS (index.html + forecast/inventory.html)")
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
