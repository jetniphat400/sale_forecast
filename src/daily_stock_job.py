"""The daily stock job: pulls stock and reserved quantities, builds the two data files that change daily, checks them
against gates, and publishes them. Run once a day by src/snapshot_daily.py (the scheduled task
SaleForecast_PostingDelaySnapshot), inside the single database session that script already opens; it can also be run
on its own (python src/daily_stock_job.py --dry-run --from-pulls DIR) to rehearse everything except the database and git.

What it publishes (config `daily_stock.published_files`, nothing else):
  data/inventory.json    the index page's stock panel (built by src/build_inventory_dataset.py from the pull)
  data/stock_daily.json  the Min-Max page's stock figures and the three dates it shows (src/stock_daily.py)
Forecasts, Min and Max and every sales-derived figure stay monthly (src/monthly_refresh.py).

Order: pull (database) -> build both files in a temporary folder -> gates -> publish. Publish = git pull, stop if any
tracked file is modified or staged, copy the two files in, stage only them, commit with the pull time in the message,
push. While the monthly runner runs (its lock file exists and its process is alive) nothing is published and the log
says so. Any failure writes a log under output/runs/daily/ naming the failed gate or step and the error, makes no
commit or push, and exits non-zero. A dry run writes only to a temporary folder and its log and stages nothing.

DATABASE ACCESS RULE: the pull makes one connection attempt inside the caller's session; nothing here retries.
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import zlib
from datetime import datetime

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_daily  # noqa: E402

logger = logging.getLogger("daily_stock_job")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PULL_DIR_RELATIVE = os.path.join("output", "data", "daily_stock_pull")
SNAPSHOT_GLOB_DIR = os.path.join("output", "snapshots")


class DailyFailure(Exception):
    """A gate failed or a step could not be completed. `gate` / `step` name it for the log."""

    def __init__(self, message, gate=None, step=None):
        super().__init__(message)
        self.gate, self.step = gate, step


class DailyStop(DailyFailure):
    """The run stopped on purpose (for example a tracked file is modified): nothing was committed or pushed."""


def load_config(root: str = PROJECT_ROOT) -> dict:
    with open(os.path.join(root, "config", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


# ----------------------------------------------------------------------------------------------- the noon retry
def successful_run_today(root: str, config: dict, today=None) -> dict:
    """The log of the latest daily run that finished today (this machine's clock) with a status in config `daily_stock.success_statuses`,
    or None. A dry run, a failed run, a run held while the monthly runner ran and a skip never count."""
    today = str(today or datetime.now().date())
    log_dir = os.path.join(root, config["daily_stock"]["log_dir"])
    found = None
    for name in sorted(os.listdir(log_dir)) if os.path.isdir(log_dir) else []:
        if not (name.startswith("daily_stock_") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(log_dir, name), encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError):
            continue
        if (not log.get("dry_run") and log.get("status") in config["daily_stock"]["success_statuses"]
                and str(log.get("finished_at", ""))[:10] == today):
            found = log
    return found


def record_skip(root: str, config: dict, existing: dict) -> str:
    """Writes the log of a run that exited at once because a successful run of today exists; returns its path."""
    log = {"run_id": datetime.now().strftime("%Y%m%dT%H%M%S"), "dry_run": False, "status": config["daily_stock"]["skip_status"],
           "committed": False, "pushed": False, "gates": [], "steps": [],
           "note": f"a successful daily run of today exists (run {existing.get('run_id')}, status {existing.get('status')}, "
                   f"finished {existing.get('finished_at')}); this run did nothing and made no database connection",
           "finished_at": datetime.now().isoformat(timespec="seconds")}
    return _write_log(root, config, log)


# ----------------------------------------------------------------------------------------------- monthly runner lock
def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259    # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def monthly_runner_running(root: str, config: dict) -> bool:
    """True when the monthly runner's lock file exists and names a live process. A stale lock (dead process) is ignored."""
    path = os.path.join(root, config["daily_stock"]["monthly_lock_file"])
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            return pid_alive(int(json.load(f)["pid"]))
    except (ValueError, KeyError, OSError):
        return False


# ----------------------------------------------------------------------------------------------- the base for the gates
def load_base(root: str, config: dict) -> dict:
    """What today's pull is compared with: the last successful daily run's figures, or, before one exists, the latest
    daily stock snapshot (output/snapshots/inventory_daily_*.csv). None when neither exists."""
    last = os.path.join(root, config["daily_stock"]["last_success_file"])
    if os.path.exists(last):
        with open(last, encoding="utf-8") as f:
            base = json.load(f)
        base["source"] = "last successful daily run"
        return base
    snap_dir = os.path.join(root, SNAPSHOT_GLOB_DIR)
    files = sorted(f for f in os.listdir(snap_dir) if f.startswith("inventory_daily_") and f.endswith(".csv")) if os.path.isdir(snap_dir) else []
    if not files:
        return None
    df = pd.read_csv(os.path.join(snap_dir, files[-1]))
    return {"inventory_rows": int(len(df)), "on_hand_total": float(df["stock"].sum()), "pull_time": None,
            "source": f"latest daily stock snapshot ({files[-1]})"}


# ----------------------------------------------------------------------------------------------- gates
def _band(name: str, today: float, base_value: float, pct: float) -> dict:
    change = 100.0 * (today - base_value) / base_value if base_value else float("inf")
    ok = abs(change) <= pct
    return {"gate": name, "passed": bool(ok), "today": today, "base": base_value, "change_pct": round(change, 2) if change != float("inf") else None,
            "band_pct": pct, "detail": f"{today:,.0f} against {base_value:,.0f} ({change:+.1f}%), allowed +/-{pct}%"}


def check_gates(payload: dict, inventory: pd.DataFrame, backlog_ces: pd.DataFrame, base: dict, published: dict,
                config: dict, replay: bool = False) -> list:
    """Runs every gate and returns one result per gate (it never stops at the first failure, so the log shows all).
    `replay` is for a rehearsal on a saved pull, which by definition is the pull already published: the pull-time gate
    then only requires 'not older than' the published one."""
    cfg = config["daily_stock"]
    out = []
    if base is None:
        out.append({"gate": "row_count_band", "passed": True, "detail": "skipped: no earlier daily run or snapshot to compare with"})
        out.append({"gate": "on_hand_total_band", "passed": True, "detail": "skipped: no earlier daily run or snapshot to compare with"})
    else:
        out.append(_band("row_count_band", float(len(inventory)), float(base["inventory_rows"]), cfg["row_count_band_pct"]))
        out.append(_band("on_hand_total_band", float(inventory["stock"].sum()), float(base["on_hand_total"]), cfg["on_hand_total_band_pct"]))
        out[0]["base_source"] = out[1]["base_source"] = base.get("source")
    bad_inv = int(inventory["itemcode"].isna().sum() + (inventory["itemcode"].astype(str).str.strip() == "").sum())
    bad_ces = 0
    if backlog_ces is not None and len(backlog_ces):
        bad_ces = int(backlog_ces["ItemCode"].isna().sum() + (backlog_ces["ItemCode"].astype(str).str.strip() == "").sum())
    out.append({"gate": "no_null_item_codes", "passed": bad_inv == 0 and bad_ces == 0,
                "detail": f"{bad_inv} null or empty item codes in the stock pull, {bad_ces} in the reserved pull"})
    pt = pd.Timestamp(payload["pull_time"])
    if published is None:
        out.append({"gate": "pull_newer_than_published", "passed": True, "detail": "nothing published yet"})
    else:
        pub = pd.Timestamp(published["pull_time"])
        ok = pt >= pub if replay else pt > pub
        out.append({"gate": "pull_newer_than_published", "passed": bool(ok),
                    "detail": f"pull {payload['pull_time']} against published {published['pull_time']}"
                              + (" (replay of a saved pull: not older is enough)" if replay else "")})
    return out


def failed_gates(results: list) -> list:
    return [r for r in results if not r["passed"]]


# ----------------------------------------------------------------------------------------------- git
def git(root: str, *args, check: bool = True):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise DailyFailure(f"git {' '.join(args)} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[:1500]}",
                           step="git " + args[0])
    return proc


def tracked_changes(root: str) -> list:
    """Tracked files that are modified, staged, deleted or renamed (untracked files are not counted)."""
    out = git(root, "status", "--porcelain", "--untracked-files=no").stdout
    return [line for line in out.splitlines() if line.strip()]


def commit_size(root: str) -> dict:
    """Size of HEAD's change: the raw bytes of the files it changed and a zlib estimate of the new objects git stores."""
    names = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.split()
    raw = comp = 0
    per_file = {}
    for n in names:
        blob = subprocess.run(["git", "show", f"HEAD:{n}"], cwd=root, capture_output=True).stdout
        raw += len(blob)
        c = len(zlib.compress(blob, 6))
        comp += c
        per_file[n] = {"raw_bytes": len(blob), "compressed_bytes": c}
    return {"files": per_file, "raw_bytes": raw, "compressed_bytes_estimate": comp}


# ----------------------------------------------------------------------------------------------- stages
def pull_stage(root: str, pull_dir: str) -> dict:
    """The database part: the four pulls build_inventory_dataset needs, saved with their pull time. Uses the caller's
    open session (src/db.py session()) so it adds no connection."""
    import build_inventory_dataset as bid
    bconfig = bid.load_config()
    registry = bid.reconcile_against_335(bid.build_full_registry(bconfig))
    return bid.save_pulls(pull_dir, sorted(registry["code"].unique()))


def build_stage(root: str, pull_dir: str, out_dir: str) -> dict:
    """Builds both data files from the saved pull into out_dir, no database connection."""
    import build_inventory_dataset as bid
    frames, meta = bid.load_pulls(pull_dir)
    inv_out = os.path.join(out_dir, "inventory.json")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, os.path.join(root, "src", "build_inventory_dataset.py"), "--from-pulls", pull_dir, "--out", inv_out],
                          cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if proc.returncode != 0:
        raise DailyFailure(f"build_inventory_dataset.py exited {proc.returncode}: {proc.stderr[-1500:]}", step="build inventory.json")
    with open(inv_out, encoding="utf-8") as f:
        written = json.load(f)["snapshot"]["generated_at"]
    if written != meta["pulled_at_utc"]:
        raise DailyFailure(f"inventory.json says it was generated at {written}, the saved pull is from {meta['pulled_at_utc']}",
                           step="build inventory.json")
    payload = stock_daily.build_payload(frames["inventory"], frames["backlog_ces"], meta["pulled_at_local"])
    stock_out = os.path.join(out_dir, "stock_daily.json")
    stock_daily.write_payload(payload, stock_out)
    return {"inventory": frames["inventory"], "backlog_ces": frames["backlog_ces"], "payload": payload, "meta": meta,
            "inventory_json": inv_out, "stock_json": stock_out}


def publish_stage(root: str, config: dict, built: dict, replay: bool = False) -> dict:
    cfg = config["daily_stock"]
    git(root, "pull", "--ff-only", "origin", "main")
    changes = tracked_changes(root)
    if changes:
        raise DailyStop("a tracked file is modified or staged, so nothing is published: " + "; ".join(changes[:10]),
                        step="tracked files clean")
    pub_path = os.path.join(root, stock_daily.STOCK_JSON_RELATIVE)
    published = stock_daily.read_payload(pub_path) if os.path.exists(pub_path) else None
    recheck = [r for r in check_gates(built["payload"], built["inventory"], built["backlog_ces"], None, published, config, replay)
               if r["gate"] == "pull_newer_than_published"]
    if failed_gates(recheck):
        raise DailyFailure(recheck[0]["detail"], gate="pull_newer_than_published")
    targets = {"data/inventory.json": built["inventory_json"], "data/stock_daily.json": built["stock_json"]}
    if sorted(targets) != sorted(cfg["published_files"]):
        raise DailyFailure("config daily_stock.published_files does not match the two files this job builds", step="staging list")
    for rel, src in targets.items():
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    changed = [p for p in cfg["published_files"] if git(root, "status", "--porcelain", "--", p).stdout.strip()]
    if not changed:
        return {"committed": False, "pushed": False, "reason": "neither file changed"}
    git(root, "add", "--", *changed)
    staged = git(root, "diff", "--cached", "--name-only").stdout.split()
    if sorted(staged) != sorted(changed):
        git(root, "reset", "-q", check=False)
        raise DailyFailure(f"staged files {staged} differ from the daily job's own files {changed}", step="staging list")
    pull_time = built["payload"]["pull_time"]
    git(root, "commit", "-q", "-m", f"{cfg['commit_message_prefix']} {pull_time}")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    result = {"committed": True, "commit": head, "files": changed, "commit_size": commit_size(root), "pushed": False}
    push = git(root, "push", "origin", "main", check=False)
    result["push_output"] = (push.stdout + push.stderr).strip()[-1500:]
    result["pushed"] = push.returncode == 0
    if not result["pushed"]:
        result["error"] = "git push failed; the commit exists locally and the next run pushes it"
    return result


def _write_log(root: str, config: dict, log: dict) -> str:
    out_dir = os.path.join(root, config["daily_stock"]["log_dir"])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"daily_stock_{log['run_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, default=str, ensure_ascii=False)
    return path


def record_failure(root: str, config: dict, step: str, exc: Exception) -> str:
    """Log for a failure that happened before the job itself ran (login refused, the measurement failed)."""
    log = {"run_id": datetime.now().strftime("%Y%m%dT%H%M%S"), "dry_run": False, "status": "failed", "failed_gate": None,
           "failed_step": step, "committed": False, "pushed": False, "gates": [], "steps": [],
           "error": {"type": type(exc).__name__, "message": str(exc)[:3000], "traceback_tail": traceback.format_exc()[-2500:]},
           "finished_at": datetime.now().isoformat(timespec="seconds")}
    return _write_log(root, config, log)


# ----------------------------------------------------------------------------------------------- the run
def run(root: str = PROJECT_ROOT, dry_run: bool = False, pull_dir: str = None, base: dict = None, config: dict = None,
        run_id: str = None, pull_fn=None) -> dict:
    """One daily run. `pull_dir` given = use that saved pull and make no database connection (dry run, tests);
    otherwise `pull_fn(root, pull_dir)` (default pull_stage) pulls inside the caller's open session. `base` is what
    the gates compare with; load it BEFORE the caller writes today's snapshot. Returns the run log; raises DailyFailure
    (after writing the log) on a failed gate or step."""
    config = config or load_config(root)
    run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%S")
    log = {"run_id": run_id, "dry_run": dry_run, "started_at": datetime.now().isoformat(timespec="seconds"), "steps": [], "gates": [],
           "committed": False, "pushed": False}
    tmp = tempfile.mkdtemp(prefix="daily_stock_")
    step = "start"
    try:
        if base is None:
            base = load_base(root, config)
        log["base"] = base
        step = "pull"
        if pull_dir is None:
            pull_dir = os.path.join(root, PULL_DIR_RELATIVE)
            meta = (pull_fn or pull_stage)(root, pull_dir)
            log["steps"].append({"step": "pull", "rows": meta.get("rows"), "pulled_at_local": meta.get("pulled_at_local")})
        else:
            log["steps"].append({"step": "pull", "note": "saved pull reused, no database connection", "pull_dir": pull_dir})
        step = "build"
        built = build_stage(root, pull_dir, tmp)
        log["pull_time"] = built["payload"]["pull_time"]
        log["stock_source_load_time"] = built["payload"]["stock_source_load_time"]
        log["reserved_source_load_time"] = built["payload"]["reserved_source_load_time"]
        log["steps"].append({"step": "build", "stock_rows": int(len(built["inventory"])), "items_with_stock": len(built["payload"]["items"])})
        step = "gates"
        pub_path = os.path.join(root, stock_daily.STOCK_JSON_RELATIVE)
        published = stock_daily.read_payload(pub_path) if os.path.exists(pub_path) else None
        log["gates"] = check_gates(built["payload"], built["inventory"], built["backlog_ces"], base, published, config, replay=dry_run)
        bad = failed_gates(log["gates"])
        if bad:
            raise DailyFailure("; ".join(f"{b['gate']}: {b['detail']}" for b in bad), gate=bad[0]["gate"])
        step = "publish"
        if dry_run:
            log["status"] = "dry_run_passed"
            log["steps"].append({"step": "publish", "note": "dry run: nothing staged, committed or pushed"})
        elif monthly_runner_running(root, config):
            log["status"] = "skipped_monthly_runner_running"
            log["steps"].append({"step": "publish", "note": "the monthly runner is running; nothing published today"})
        else:
            result = publish_stage(root, config, built)
            log["steps"].append({"step": "publish", **{k: v for k, v in result.items() if k != "commit_size"}})
            log["committed"], log["pushed"] = result["committed"], result["pushed"]
            log["commit_size"] = result.get("commit_size")
            if result["committed"] and not result["pushed"]:
                raise DailyFailure(result.get("error", "push failed"), step="git push")
            log["status"] = "published" if result["pushed"] else "nothing_to_publish"
            if result["pushed"]:
                last_path = os.path.join(root, config["daily_stock"]["last_success_file"])
                os.makedirs(os.path.dirname(last_path), exist_ok=True)
                with open(last_path, "w", encoding="utf-8") as f:
                    json.dump({"pull_time": log["pull_time"], "inventory_rows": int(len(built["inventory"])),
                               "on_hand_total": float(built["inventory"]["stock"].sum()), "run_id": run_id}, f, indent=2)
        log["finished_at"] = datetime.now().isoformat(timespec="seconds")
        log["log_path"] = _write_log(root, config, log)
        return log
    except Exception as e:  # noqa: BLE001 -- every failure must reach the log
        log["status"] = "failed"
        log["failed_gate"] = getattr(e, "gate", None)
        log["failed_step"] = getattr(e, "step", None) or step
        log["error"] = {"type": type(e).__name__, "message": str(e)[:3000], "traceback_tail": traceback.format_exc()[-2500:]}
        log["finished_at"] = datetime.now().isoformat(timespec="seconds")
        log["log_path"] = _write_log(root, config, log)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="rehearse on a saved pull: no database, no git, only a log is written")
    ap.add_argument("--from-pulls", metavar="DIR", help="saved pull directory (written by build_inventory_dataset.py --save-pulls)")
    args = ap.parse_args(argv)
    if not args.from_pulls:
        print("run on its own only as a rehearsal: --dry-run --from-pulls DIR (the real run is src/snapshot_daily.py)", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        log = run(dry_run=args.dry_run, pull_dir=os.path.abspath(args.from_pulls))
    except DailyFailure as e:
        logger.error("DAILY STOCK JOB FAILED (%s): %s", e.gate or e.step, e)
        return 1
    print(json.dumps({k: log[k] for k in ("run_id", "status", "gates", "log_path")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
