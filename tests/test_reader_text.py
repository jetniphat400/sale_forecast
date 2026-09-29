"""Guards for reader-facing text (CONVENTIONS.md "Reader-facing text", .claude/skills/reader-text/SKILL.md).

What a reader can see on forecast/sales_report.html and forecast/inventory.html must not carry
project internals: no file extension (.py .md .csv .yaml .json ...), no METRICS / DATA_MAP /
STATUS.md word, no section reference (§ or Sec. followed by a number), no config key, and no
line of more than 60 characters without any Thai.

Both pages are rebuilt into a pytest tmp_path by the same builders the monthly runner uses
(src/build_report.build_report(output_path=...) and src/build_inventory_page.build_page()); no
tracked file is written. build_inventory_page needs database pulls, so its data block is taken
from the tracked page's embedded JSON, with every reader-facing text field that the builder
produces without a database (disabled reasons, scope notes, curve note, PEM107 alert) regenerated
by the builder's own functions.

Two views are checked:
  * static  -- the HTML with scripts, styles and comments removed;
  * rendered -- the text Edge actually shows after the page's own JS ran (every inventory
    division), with Plotly stubbed and the CDN blocked so the run is offline. Skipped when Edge
    is not installed.

PENDING_REWRITE lists the few English lines that still need Thai wording from the user's
assistant (removing their references would leave them meaningless). They are the only lines the
guards let through; nothing else may match a rule.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from html.parser import HTMLParser

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
TRACKED_INVENTORY_HTML = os.path.join(PROJECT_ROOT, "forecast", "inventory.html")

THAI = re.compile(r"[\u0E00-\u0E7F]")
FILE_EXT = re.compile(r"\.(?:py|md|csv|yaml|yml|json|html|xlsx|js)\b", re.I)
INTERNAL_WORDS = re.compile(r"METRICS|DATA_MAP|PROJECT_GRAPH|STATUS\.md|CONVENTIONS")
SECTION_REF = re.compile(r"(?:§|\bSec\.|\bsection)\s*\d+", re.I)
INTERNAL_NAMES = re.compile(r"\b(?:stock_policy|confirmed_to_order|finished_goods_stock|component_stock_ato)\b")
MAX_NON_THAI_LINE = 60

# English lines awaiting Thai wording (see the module docstring). Each pattern is removed from a
# line before the rules run.
PENDING_REWRITE = [
    # sales_report.html: note about the earlier 9-origin chart, cites a file and a script
    re.compile(r"หมายเหตุเกี่ยวกับแกน X เดิม.*?แสดงทั้ง forecast และ actual"),
    # inventory.html, PEM103 only: the two older class names shown in the Policy column, no approved display name yet
    re.compile(r"^(?:finished_goods_stock|component_stock_ato)$"),
    # inventory.html: curve summary, item-set note, scope note, PEM107 limitations, relative-cost tail
    re.compile(r"\d+ distinct ensemble members \(deduplicated on reorder level.*?stock value THB [\d,]+\."),
    re.compile(r"Calibrated on the pre-Sec\.23 finished_goods_stock item set.*?PROJECT_GRAPH\.md node G2\)\."),
    re.compile(r"PEM101 128-item Fuse/Surge-Arrester pilot\. PARTIALLY CALIBRATED \(80 distinct ensemble members\)\."),
    re.compile(r"PEM10[37] -- E2 scoped pilot, sellable-warehouse list is a business assumption\. .*?(?:planning PEM103\.|not a calibrated policy\.)"),
    re.compile(r"•\s*\"Before May 2026\" is bounded.*?not like-for-like\."),
    re.compile(r"•\s*Post-May-2026 volume is small.*?a lot\."),
    re.compile(r"•\s*The cause of the decline is undetermined.*?concentrated in June\)\."),
    re.compile(r"•\s*What was actually separated in May 2026.*?not inferred here\."),
]


def _config_keys() -> set:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    keys = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and "_" in k and len(k) >= 6:
                    keys.add(k)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(cfg)
    return keys


def violations(lines, config_keys) -> list:
    """Every rule hit in `lines` (already stripped of scripts, styles and comments)."""
    key_re = re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, sorted(config_keys, key=len, reverse=True))) + r")(?![A-Za-z0-9_])")
    found = []
    for raw in lines:
        line = " ".join(raw.split())
        for pat in PENDING_REWRITE:
            line = pat.sub("", line)
        line = line.strip()
        if not line:
            continue
        for name, pat in [("file extension", FILE_EXT), ("internal word", INTERNAL_WORDS),
                          ("section reference", SECTION_REF), ("internal status name", INTERNAL_NAMES),
                          ("config key", key_re)]:
            m = pat.search(line)
            if m:
                found.append(f"{name} {m.group(0)!r} in: {line[:120]}")
        if len(line) > MAX_NON_THAI_LINE and not THAI.search(line):
            found.append(f"line over {MAX_NON_THAI_LINE} chars with no Thai: {line[:120]}")
    return found


class _VisibleText(HTMLParser):
    """Visible text lines: scripts, styles, comments and <head> dropped; inline tags do not break a line."""
    SKIP = {"script", "style", "head", "template"}
    INLINE = {"b", "i", "em", "strong", "code", "span", "a", "small", "sub", "sup", "u", "font"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self._cur, self._skip = [], [], 0

    def _flush(self):
        text = " ".join("".join(self._cur).split())
        if text:
            self.lines.append(text)
        self._cur = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag not in self.INLINE:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag not in self.INLINE:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._cur.append(data)

    def close(self):
        super().close()
        self._flush()


def visible_lines(html_text: str) -> list:
    p = _VisibleText()
    p.feed(html_text)
    p.close()
    return p.lines


# ------------------------------------------------------------------ building pages to tmp

def _fresh_inventory_data() -> dict:
    """The tracked page's embedded data, with every database-free reader text regenerated."""
    import build_inventory_page_data as bd
    with open(TRACKED_INVENTORY_HTML, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'<script type="application/json" id="inventory-data">(.*?)</script>', text, re.DOTALL)
    assert m, "embedded inventory-data block not found in the tracked inventory.html"
    data = json.loads(m.group(1))
    data["disabled_divisions"] = bd.disabled_division_reasons()
    data["disabled_division_labels"] = bd.DISABLED_DIVISION_LABELS
    data["model_calibrated_at"] = bd.MODEL_CALIBRATED_AT
    for division, dd in data["divisions"].items():
        dd["warehouse_scope_note"], dd["warehouse_scope_ref"] = bd.warehouse_scope_note_and_ref(division)
    data["divisions"]["PEM101"]["curve_target"] = bd._build_curve_target_pem101()
    data["pem107_alert"] = bd._load_pem107_alert()
    return data


@pytest.fixture(scope="module")
def built_pages(tmp_path_factory):
    import build_inventory_page as bp
    import build_report
    out = tmp_path_factory.mktemp("reader_text")
    sales = build_report.build_report(output_path=str(out / "sales_report.html"))
    mp = pytest.MonkeyPatch()
    data = _fresh_inventory_data()
    mp.setattr(bp, "build_data", lambda: data)
    try:
        page = bp.build_page()
    finally:
        mp.undo()
    inv = str(out / "inventory.html")
    with open(inv, "w", encoding="utf-8") as f:
        f.write(page)
    return {"sales_report": sales, "inventory": inv}


# ------------------------------------------------------------------ static view

@pytest.mark.parametrize("page", ["sales_report", "inventory"])
def test_static_visible_text_is_reader_text(page, built_pages):
    with open(built_pages[page], encoding="utf-8") as f:
        lines = visible_lines(f.read())
    assert len(lines) > 20, f"{page}: visible text extraction looks empty"
    found = violations(lines, _config_keys())
    assert not found, f"{page}: reader-facing text carries project internals:\n" + "\n".join(found)


def test_guard_catches_each_rule():
    """The guard itself: one sample per rule must be caught, and Thai text must pass."""
    keys = {"segment_policy"}
    assert violations(["ดูที่ build_report.py"], keys)
    assert violations(["ตามเอกสาร METRICS"], keys)
    assert violations(["ตาม Sec.23 ของโครงการ"], keys)
    assert violations(["ตาม § 40"], keys)
    assert violations(["แก้ segment_policy ก่อน"], keys)
    assert violations(["x" * 30 + " " + "y" * 40], keys)
    assert not violations(["ตัวควบคุมด้านล่างเปลี่ยนแค่ตัวเลขบนหน้านี้ ไม่ได้เปลี่ยนการทายยอดขาย"], keys)
    assert not violations(["Min/Max ไม่เปลี่ยน เพราะคำนวณจากยอดขาย ไม่ได้ใช้ stock ปัจจุบัน " + "a" * 70], keys)


def test_visible_text_extraction_drops_scripts_styles_and_comments():
    lines = visible_lines("<html><head><title>x.py</title></head><body><!-- a.py --><p>สวัสดี <b>ครับ</b></p>"
                          "<script>var f='b.csv'</script><style>.c{}</style><div>ต่อ</div></body></html>")
    assert lines == ["สวัสดี ครับ", "ต่อ"]


# ------------------------------------------------------------------ rendered view (Edge)

def _find_edge():
    for c in (os.environ.get("EDGE_PATH"),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if c and os.path.exists(c):
            return c
    return None


class _Edge:
    """Own headless Edge on a temp profile; only its own PID is ever closed."""

    def __init__(self, exe):
        import websocket
        self._ws_mod = websocket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.profile = tempfile.mkdtemp(prefix="reader_text_edge_")
        self.proc = subprocess.Popen(
            [exe, f"--remote-debugging-port={self.port}", f"--user-data-dir={self.profile}", "--headless=new",
             "--no-first-run", "--no-default-browser-check", "--allow-file-access-from-files", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws, self._id = None, 0
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1).read()
                return
            except Exception:
                time.sleep(0.5)
        self.close()
        raise RuntimeError("Edge did not start")

    def call(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                return m

    def open(self, url):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?{url}", method="PUT")
        tab = json.load(urllib.request.urlopen(req))
        self.ws = self._ws_mod.create_connection(tab["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.call("Network.enable")
        self.call("Network.setBlockedURLs", urls=["*cdnjs.cloudflare.com*"])
        self.call("Page.enable")
        self.call("Page.addScriptToEvaluateOnNewDocument",
                  source="window.Plotly={newPlot:function(){},react:function(){}};")
        self.call("Page.navigate", url=url)
        for _ in range(60):
            if self.ev("document.readyState") == "complete":
                break
            time.sleep(0.5)
        time.sleep(0.5)

    def ev(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)["result"]
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:400])
        return r["result"].get("value")

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        shutil.rmtree(self.profile, ignore_errors=True)


def _file_url(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")


@pytest.fixture(scope="module")
def rendered_texts(built_pages):
    exe = _find_edge()
    try:
        import websocket  # noqa: F401
    except ImportError:
        pytest.skip("websocket-client not installed")
    if not exe:
        pytest.skip("Edge not installed")
    texts = {}
    edge = _Edge(exe)
    try:
        edge.open(_file_url(built_pages["sales_report"]))
        texts["sales_report"] = edge.ev("document.body.innerText")
        edge.open(_file_url(built_pages["inventory"]))
        for division in ("PEM101", "PEM103", "PEM107"):
            edge.ev(f"document.getElementById('division-select').value='{division}'; onDivisionChange(); 1")
            time.sleep(0.5)
            texts[f"inventory {division}"] = edge.ev("document.body.innerText")
    finally:
        edge.close()
    return texts


@pytest.mark.parametrize("view", ["sales_report", "inventory PEM101", "inventory PEM103", "inventory PEM107"])
def test_rendered_text_is_reader_text(view, rendered_texts):
    lines = re.split(r"[\n\t]", rendered_texts[view])  # innerText joins table cells with tabs
    assert len(lines) > 20, f"{view}: rendered text looks empty"
    found = violations(lines, _config_keys())
    assert not found, f"{view}: rendered reader-facing text carries project internals:\n" + "\n".join(found)
