"""The daily extra pulls and the rebuild stage of the daily job (Prompt 57; METRICS.md Sec.28, "Daily cycle").

The stock publish of src/daily_stock_job.py stays first and unchanged. After it, inside the same database session, `run_extras` pulls the other sources that can be pulled every
day (Trend sales, PEM107 deliveries, raw-material stock and open purchase orders), each in its own try/except; after the session has closed, `run_rebuild` recomputes every page that
depends on them (Trend tab, the PEM107 part of the Min-Max page, Production Plan, material plan, executive tab) with the existing builders and publishes the pages in a second commit.
Everything stays in one transaction in this sense: a backup of every file that may change is taken before the first pull; a failed pull puts back its own files; a failed rebuild puts back
all of them. The model (forecast, vintages, logs, Min and Max calibration, the sales report, the executive sales and accuracy figures) is never touched: gates compare it before and after.

Nothing here makes a connection except the pull functions it calls, which use the caller's open session (src/db.py) and their existing SQL.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger("daily_rebuild")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINMAX_FREE_KEYS = ("page_built_at", "freshness", "disabled_divisions", "pem107_alert")      # what a daily rebuild of the Min-Max page may change; every other embedded key must stay equal


class RebuildFailure(Exception):
    """A pull band, a step or a gate of the daily extras or rebuild failed; `step` names it."""

    def __init__(self, message, step=None):
        super().__init__(message)
        self.step = step


# ----------------------------------------------------------------------------------------------- small helpers
def _sha(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _json_eq(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def skip_reason(root: str, config: dict, today=None):
    """Why the extras and the rebuild must not run now, or None: the monthly runner is alive (lock with a live process), or a monthly attempt or success is recorded for today."""
    import daily_stock_job as djob
    cfg = config["daily_rebuild"]
    today = str(today or date.today())
    if djob.monthly_runner_running(root, config):
        return "the monthly runner is running"
    attempt = _read_json(os.path.join(root, cfg["monthly_attempt_file"]))
    if str(attempt.get("date")) == today:
        return f"a monthly attempt is recorded for today (run {attempt.get('run_id')})"
    if str(_read_json(os.path.join(root, cfg["monthly_state_file"])).get("recorded_at", ""))[:10] == today:
        return "a monthly success is recorded for today"
    return None


# ----------------------------------------------------------------------------------------------- backup
def source_files(config: dict) -> dict:
    """{source: [relative files its pull writes]}."""
    cfg, t = config["daily_rebuild"], config["trend_tab"]["pull_dir"]
    return {"trend": [f"{t}/{n}" for n in ("daily.csv", "names.csv", "completeness.json")],
            "pem107": list(cfg["pem107_files"]),
            "material": [config["operation_plan"]["week3_inputs_file"]]}


def backup_paths(config: dict) -> list:
    """Every file the extras or the rebuild may change: the three sources' files, the plan records and the integrity file, the material records, the allowed pages."""
    op, mp = config["operation_plan"], config["material_plan"]
    rels = [f for files in source_files(config).values() for f in files]
    rels += [op[k] for k in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file")]
    rels += [mp["output_material_month_file"], mp["output_material_summary_file"]]
    rels += list(config["daily_rebuild"]["allowed_files"])
    return list(dict.fromkeys(rels))


class Backup:
    """A copy of `rels` (relative to `root`) taken now; `restore` puts them back (a file that did not exist is removed); `verify` lists the ones whose hash differs from the copy."""

    def __init__(self, root: str, rels: list):
        self.root, self.rels = root, list(rels)
        self.dir = tempfile.mkdtemp(prefix="daily_backup_")
        self.hashes = {}
        for rel in self.rels:
            src = os.path.join(root, *rel.split("/"))
            self.hashes[rel] = _sha(src)
            if self.hashes[rel] is not None:
                dst = os.path.join(self.dir, *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

    def restore(self, rels: list = None) -> None:
        for rel in (rels or self.rels):
            dst = os.path.join(self.root, *rel.split("/"))
            if self.hashes[rel] is None:
                if os.path.exists(dst):
                    os.remove(dst)
            else:
                shutil.copy2(os.path.join(self.dir, *rel.split("/")), dst)

    def verify(self, rels: list = None) -> list:
        return [rel for rel in (rels or self.rels) if _sha(os.path.join(self.root, *rel.split("/"))) != self.hashes[rel]]

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- the extra pulls (inside the open session)
def pull_trend(root: str) -> dict:
    import build_trend_tab
    return {"rows": int(build_trend_tab.pull(root, in_open_session=True)["completeness"]["n_rows"])}


def pull_pem107(root: str) -> dict:
    import cube_ces_pull
    return {"rows": int(cube_ces_pull.pull_pem107_alert(root, in_open_session=True)["rows"]["cube_ces_omni"])}


def pull_material(root: str) -> dict:
    import material_plan
    return material_plan.pull_rm_stock_and_open_orders(root, in_open_session=True)["rows"]


PULLS = {"trend": pull_trend, "pem107": pull_pem107, "material": pull_material}


def previous_counts(root: str, config: dict) -> dict:
    """{source: {metric: rows}} of the files now on disk (what the new pull is compared with); a missing file gives no entry."""
    out = {}
    try:
        out["trend"] = {"rows": int(_read_json(os.path.join(root, source_files(config)["trend"][2]))["n_rows"])}
    except (KeyError, TypeError):
        pass
    raw = os.path.join(root, config["daily_rebuild"]["pem107_files"][2])
    bundle = os.path.join(root, config["operation_plan"]["week3_inputs_file"])
    try:
        out["pem107"] = {"rows": int(len(pd.read_csv(raw)))}
    except Exception:  # noqa: BLE001 -- no readable earlier file: no band for this source
        pass
    try:
        b = pd.read_pickle(bundle)
        out["material"] = {"rm_inventory": int(len(b["rm_inventory"])), "open_orders": int(len(b["open_orders"]))}
    except Exception:  # noqa: BLE001
        pass
    return out


def check_band(source: str, counts: dict, before: dict, bands: dict) -> None:
    """Raises when a source's row count is further from the last one than its band (config daily_rebuild.bands_pct, per metric)."""
    for metric, n in counts.items():
        old, pct = (before or {}).get(metric), bands.get(f"{source}_{metric}")
        if old and pct is not None and abs(100.0 * (n - old) / old) > pct:
            raise RebuildFailure(f"{source} {metric}: {n} rows against {old} ({100.0 * (n - old) / old:+.1f}%), allowed +/-{pct}%", step=f"pull {source}")


def begin(root: str, config: dict, git: bool = True):
    """Brings the clone up to date and backs up every file that may change; returns the Backup. Call it before the first pull (inside the session is fine: no query)."""
    if git:
        import daily_stock_job as djob
        djob.git(root, "pull", "--ff-only", "origin", "main")
        changes = djob.tracked_changes(root, djob.shared_output_prefixes(config))
        if changes:
            raise djob.DailyStop("a tracked file is modified or staged, so no extra pull or rebuild runs: " + "; ".join(changes[:10]), step="tracked files clean")
    return Backup(root, backup_paths(config))


def run_extras(root: str, config: dict, backup: Backup, done=(), pulls: dict = None) -> list:
    """Each source in its own try/except; a failed pull (error or band) puts back its own files and is logged as {source, status, error}; `done` = sources already ok today (the noon retry)."""
    before, bands, files, results = previous_counts(root, config), config["daily_rebuild"]["bands_pct"], source_files(config), []
    for name, fn in (pulls or PULLS).items():
        if name in done:
            results.append({"source": name, "status": "done_earlier_today"})
            continue
        started = time.time()
        try:
            counts = fn(root)
            check_band(name, counts, before.get(name), bands)
            results.append({"source": name, "status": "ok", "rows": counts, "seconds": round(time.time() - started, 1)})
        except Exception as e:  # noqa: BLE001 -- every failure must reach the log, and the earlier files stay
            backup.restore(files[name])
            results.append({"source": name, "status": "failed", "error": f"{type(e).__name__}: {e}"[:400], "seconds": round(time.time() - started, 1)})
            logger.error("extra pull %s failed: %s", name, e)
    return results


# ----------------------------------------------------------------------------------------------- the rebuild steps (existing builders, saved data only)
def step_trend(root: str):
    import build_trend_tab
    return build_trend_tab.run_build(root)


def step_minmax(root: str):
    """The Min-Max page from the same inputs as the monthly step 7 (the pilot pull label is the page's own), so only what depends on the daily pulls moves: its embedded data must equal the
    old page's except MINMAX_FREE_KEYS."""
    import build_inventory_page
    import inventory_page_sources
    import operation_plan as op
    path = os.path.join(root, "forecast", "inventory.html")
    old = op.read_page_data(path)
    page = build_inventory_page.build_page(**inventory_page_sources.daily_snapshot_sources(old["divisions"]["PEM103"]["snapshot_pull_date"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    new = op.read_page_data(path)
    changed = sorted(k for k in set(old) | set(new) if k not in MINMAX_FREE_KEYS and not _json_eq(old.get(k), new.get(k)))
    if changed:
        raise RebuildFailure(f"the Min-Max page's embedded data changed outside {MINMAX_FREE_KEYS}: {changed}", step="minmax data unchanged")


def step_operation_plan(root: str):
    import build_operation_plan_page
    import operation_plan
    operation_plan.run(root, today=pd.Timestamp(date.today()))
    build_operation_plan_page.build_page(root)


def step_material_plan(root: str):
    import build_material_plan_page
    import material_plan
    material_plan.run(root, today=pd.Timestamp(date.today()))
    build_material_plan_page.build_page(root)


def step_executive(root: str):
    import build_exec_summary
    build_exec_summary.run_exec_build(root)


STEPS = [("trend", step_trend), ("minmax", step_minmax), ("operation plan", step_operation_plan), ("material plan", step_material_plan), ("executive", step_executive)]


# ----------------------------------------------------------------------------------------------- gates
def _index_parts(text: str) -> tuple:
    """(index.html with the Trend data block and the executive block cut out, the executive block's model part: cards 1 to 3, the charts, the table, the lists below it: no header, no card 4, no watch list)."""
    import build_exec_summary as bes
    import build_trend_tab as btt
    a, b = text.index(bes.EXEC_BEGIN) + len(bes.EXEC_BEGIN), text.index(bes.EXEC_END)
    block = text[a:b]
    rest = text[:a] + text[b:]
    if btt.BEGIN_MARK in rest:
        rest = rest[:rest.index(btt.BEGIN_MARK)] + rest[rest.index(btt.END_MARK):]
    block = block[block.index('<div class="kpis"'):]
    block = re.sub(r'<div class="kpi" id="execCard4">.*?</div></div>', "", block, flags=re.S)
    return rest, re.sub(r'<ul id="execWatch">.*?</ul>', "", block, flags=re.S)


def snapshot(root: str, config: dict) -> dict:
    """What the gates compare with, taken before the first rebuild step."""
    import operation_plan as op
    rd = config["daily_rebuild"]
    with open(os.path.join(root, "index.html"), encoding="utf-8") as f:
        rest, model = _index_parts(f.read())
    try:
        meta = _read_json(op.path_of(root, config["operation_plan"]["output_meta_file"]))
    except Exception:  # noqa: BLE001
        meta = {}
    return {"index_rest": rest, "exec_model": model, "model_hashes": {rel: _sha(os.path.join(root, *rel.split("/"))) for rel in rd["model_files"]},
            "months": meta.get("months"), "items": (meta.get("counts") or {}).get("items")}


def _vintage_gate(root: str) -> None:
    import monthly_refresh
    monthly_refresh.step7d_vintage_gate(False, "")


def check_gates(root: str, config: dict, snap: dict, git: bool = True) -> list:
    """Runs every gate after the rebuild steps; raises RebuildFailure on the first that fails; returns the names that passed."""
    import material_plan as mp
    import operation_plan as op
    rd, passed = config["daily_rebuild"], []

    def gate(name, ok, detail=""):
        if not ok:
            raise RebuildFailure(f"{name}: {detail}", step=name)
        passed.append(name)
    op_cfg, mp_cfg = config["operation_plan"], mp.load_config(root)
    op.verify_outputs(root, op_cfg)
    mp.verify_outputs(root, mp_cfg)
    passed.append("verify_outputs (operation plan, material plan)")
    _, _, om = op.read_outputs(root, op_cfg)
    _, _, mm = mp.read_outputs(root, mp_cfg)
    gate("pair check", str(om["built_at"]) == str(mm["operation_plan_built_at"]), f"operation plan built {om['built_at']}, material plan used {mm['operation_plan_built_at']}")
    _vintage_gate(root)
    passed.append("vintage gate")
    stock_time = str(_read_json(os.path.join(root, "data", "stock_daily.json")).get("pull_time", ""))
    gate("plan stock time", str(om["stock_pull"]["pulled_at_local"])[:19] == stock_time[:19], f"plan {om['stock_pull']['pulled_at_local']}, published stock {stock_time}")
    gate("months and items unchanged", om["months"] == snap["months"] and om["counts"]["items"] == snap["items"], f"months {om['months']} items {om['counts']['items']} against {snap['months']} {snap['items']}")
    gate("material count band", abs(100.0 * (mm["n_materials"] - snap["n_materials"]) / snap["n_materials"]) <= rd["bands_pct"]["materials"] if snap.get("n_materials") else True, f"{mm['n_materials']} materials against {snap.get('n_materials')}")
    with open(os.path.join(root, "index.html"), encoding="utf-8") as f:
        rest, model = _index_parts(f.read())
    gate("index.html outside the Trend and executive blocks identical", rest == snap["index_rest"])
    gate("executive model figures identical", model == snap["exec_model"])
    gate("model files and the sales report untouched", {rel: _sha(os.path.join(root, *rel.split("/"))) for rel in rd["model_files"]} == snap["model_hashes"],
         "a model-input file or the sales report changed")
    if git:
        import daily_stock_job as djob
        stray = [line for line in djob.tracked_changes(root, djob.shared_output_prefixes(config)) if line[3:].strip().strip('"') not in rd["allowed_files"]]
        gate("only allowed files changed", not stray, "; ".join(stray[:10]))
    return passed


# ----------------------------------------------------------------------------------------------- archive, commit, the stage
def archive_monthly_records(root: str, config: dict, today=None) -> str:
    """Once per month, before the first daily overwrite of the plan records: copies the records the monthly run built into output/summary/<archive_dir>/<YYYY-MM>/ (only when the monthly success of this month is recorded)."""
    rd, today = config["daily_rebuild"], today or date.today()
    month = f"{today.year}-{today.month:02d}"
    if _read_json(os.path.join(root, rd["monthly_state_file"])).get("last_success_month") != month:
        return None
    dst = os.path.join(root, *rd["archive_dir"].split("/"), month)
    if os.path.exists(dst):
        return None
    op, mp = config["operation_plan"], config["material_plan"]
    os.makedirs(dst)
    for rel in [op[k] for k in ("output_item_month_file", "output_division_month_file", "output_meta_file", "output_integrity_file")] + [mp["output_material_month_file"], mp["output_material_summary_file"]]:
        src = os.path.join(root, *rel.split("/"))
        if os.path.exists(src):
            shutil.copy2(src, dst)
    return dst


def commit_and_push(root: str, config: dict, pull_time: str) -> dict:
    import daily_stock_job as djob
    rd = config["daily_rebuild"]
    changed = [p for p in rd["allowed_files"] if djob.git(root, "status", "--porcelain", "--", p).stdout.strip()]
    if not changed:
        return {"committed": False, "pushed": False, "reason": "no allowed file changed"}
    djob.git(root, "add", "--", *changed)
    staged = djob.git(root, "diff", "--cached", "--name-only").stdout.split()
    if sorted(staged) != sorted(changed):
        djob.git(root, "reset", "-q", check=False)
        raise RebuildFailure(f"staged files {staged} differ from the rebuild's own files {changed}", step="staging list")
    djob.git(root, "commit", "-q", "-m", f"{rd['commit_message_prefix']} {pull_time}")
    result = {"committed": True, "commit": djob.git(root, "rev-parse", "HEAD").stdout.strip(), "files": changed, "pushed": False}
    push = djob.git(root, "push", "origin", "main", check=False)
    result["pushed"] = push.returncode == 0
    if not result["pushed"]:
        result["error"] = "git push failed; the commit exists locally and the next run pushes it"
    return result


def run_rebuild(root: str, config: dict, backup: Backup, git: bool = True, steps: list = None, gates=None, today=None) -> dict:
    """The rebuild stage (after the session has closed and the stock files are published). Returns {status, steps, gates, committed, pushed, failed_step, error, restored}; never raises for a failed step or gate:
    everything is put back (hash-checked) and the failure is in the result."""
    result = {"status": "ok", "steps": [], "gates": []}
    reason = skip_reason(root, config, today)
    if reason:
        return {"status": "skipped", "reason": reason}
    try:
        snap = snapshot(root, config)
        import material_plan as mp
        try:
            snap["n_materials"] = int(mp.read_outputs(root, mp.load_config(root))[2]["n_materials"])
        except Exception:  # noqa: BLE001
            snap["n_materials"] = None
        archived = archive_monthly_records(root, config, today)
        if archived:
            result["archived_to"] = os.path.relpath(archived, root)
        for name, fn in (steps or STEPS):
            started = time.time()
            try:
                fn(root)
            except RebuildFailure:
                raise
            except Exception as e:  # noqa: BLE001
                raise RebuildFailure(f"{type(e).__name__}: {e}", step=name) from e
            result["steps"].append({"step": name, "seconds": round(time.time() - started, 1)})
        result["gates"] = (gates or check_gates)(root, config, snap, git)
        reason = skip_reason(root, config, today)
        if reason:
            raise RebuildFailure(f"{reason} (checked again before the commit)", step="lock before commit")
        if git:
            pull_time = str(_read_json(os.path.join(root, "data", "stock_daily.json")).get("pull_time", ""))
            result.update(commit_and_push(root, config, pull_time))
    except Exception as e:  # noqa: BLE001
        result.update({"status": "failed", "failed_step": getattr(e, "step", None) or "rebuild", "error": f"{type(e).__name__}: {e}"[:600]})
        import daily_stock_job as djob
        if djob.monthly_runner_running(root, config):
            result["restored"] = False
            result["note"] = "the monthly runner is running: nothing was put back (it rewrites these files)"
        else:
            backup.restore()
            if git:
                djob.git(root, "checkout", "--", *config["daily_rebuild"]["allowed_files"], check=False)
            result["restored"] = not backup.verify()
        logger.error("daily rebuild failed at %s: %s", result["failed_step"], e)
    return result


# ----------------------------------------------------------------------------------------------- the daily log
def finalize(stock_status: str, extras: list, rebuild: dict, config: dict) -> tuple:
    """(status, exit code) of the whole day: the stock status stays when every pull and the rebuild are ok or skipped on purpose; otherwise published_partial and exit 2."""
    failed = any(e["status"] == "failed" for e in extras or []) or (rebuild or {}).get("status") == "failed" or ((rebuild or {}).get("pushed") is False and (rebuild or {}).get("committed"))
    if failed and stock_status in config["daily_stock"]["success_statuses"]:
        return config["daily_rebuild"]["partial_status"], config["daily_rebuild"]["partial_exit_code"]
    return stock_status, 0


def partial_run_today(root: str, config: dict, today=None):
    """The latest log of today with the partial status (the noon retry), or None."""
    log_dir = os.path.join(root, config["daily_stock"]["log_dir"])
    found = None
    for name in sorted(os.listdir(log_dir)) if os.path.isdir(log_dir) else []:
        if name.startswith("daily_stock_") and name.endswith(".json"):
            log = _read_json(os.path.join(log_dir, name))
            if not log.get("dry_run") and log.get("status") == config["daily_rebuild"]["partial_status"] and str(log.get("finished_at", ""))[:10] == str(today or date.today()):
                found = log
    return found


def done_sources(log: dict) -> set:
    return {e["source"] for e in (log or {}).get("extras", []) if e.get("status") in ("ok", "done_earlier_today")}
