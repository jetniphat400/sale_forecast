"""Shared launcher of the two scheduled tasks (SaleForecast_PostingDelaySnapshot and SaleForecastMonthlyRefresh), Prompt 59, rewritten in Python in Prompt 60b.

Why it exists: both tasks used to run `git pull --ff-only origin main` in the publishing clone and then Python. Two launches in the same second (a missed start after the machine woke) made the two
pulls collide on FETCH_HEAD ("Cannot fast-forward to multiple branches", exit 128), so neither merged and neither started Python (Prompt 58, STATUS.md). Task Scheduler does not restart a task whose
action returned an error code, so nothing repaired it.

Why Python and not the PowerShell launcher of Prompt 59: started by Task Scheduler on this machine, powershell.exe -File failed before its first line in most starts (Prompt 60b: $PSScriptRoot empty in a
param default, then "The argument ... to the -File parameter does not exist" for a file that exists, exit 0xFFFD0000), while `cmd /c python ...` never failed in the same conditions.

What it does, in order:
  1. takes the shared lock (output/runs/git_pull.lock, written atomically, holding PID, task and start time), waiting up to lock_wait_seconds; a lock whose PID is dead or that is older than
     lock_stale_seconds is stale and is taken over (logged);
  2. git pull --ff-only origin main, retried git_retries times after a random wait of retry_wait_min_seconds to retry_wait_max_seconds;
  3. checks that HEAD equals origin/main and that no tracked file is modified or staged; on a failure it starts no Python;
  4. releases the lock (the lock covers ONLY the git steps, never the Python run: a monthly run of up to 3 hours must not make the daily task wait past its 1 hour limit; the monthly-runner lock
     already keeps the two jobs apart at Python level);
  5. starts Python with the script and its arguments and returns Python's exit code unchanged.
Every lock event and every git attempt (stdout, stderr, exit code, time) is appended to output/runs/task_launcher.log. Values come from config/config.yaml (block task_launcher); the options of the
same names override them (tests).

The bootstrap log (D:\\sale_forecast\\output\\runs\\task_launcher_bootstrap.log, a fixed path that depends on no config) gets a line before anything else happens (user, Python, argv, cwd, TEMP) and a line
when the launcher ends, with any error that escaped, so a start that dies early still leaves a trace.

Exit codes: Python's own code when Python ran; 91 the lock was not obtained in time; 92 git pull failed after every retry; 93 HEAD is not origin/main or a tracked file is modified (Python not started);
94 the script to start does not exist or the launcher itself failed.

Usage (task action):  cmd.exe /c <python.exe> <clone>\\src\\task_launcher.py --task <task name> --script src\\snapshot_daily.py --git <git.exe> --python <python.exe> [script arguments]
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import traceback

BOOTSTRAP_LOG = r"D:\sale_forecast\output\runs\task_launcher_bootstrap.log"
DEFAULTS = {"lock_file": "output/runs/git_pull.lock", "log_file": "output/runs/task_launcher.log", "lock_wait_seconds": 300, "lock_stale_seconds": 900, "git_retries": 3,
            "retry_wait_min_seconds": 20, "retry_wait_max_seconds": 60, "git_timeout_seconds": 300, "lock_poll_seconds": 2}
MUTEX_NAME = "Global\\SaleForecastGitPullLaunch"


def now():
    return datetime.datetime.now()


def append_line(paths, line):
    for path in paths:
        try:
            with open(path, "a", encoding="utf-8", newline="") as f:
                f.write(line + "\r\n")
            return
        except OSError:
            continue


def write_boot(text):
    line = "%s pid=%d %s" % (now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], os.getpid(), text)
    append_line([os.environ.get("TASK_LAUNCHER_BOOTSTRAP_LOG") or BOOTSTRAP_LOG, os.path.join(tempfile.gettempdir(), "task_launcher_bootstrap.log")], line)


def read_config(root):
    cfg = dict(DEFAULTS)
    path = os.path.join(root, "config", "config.yaml")
    found = False
    if os.path.isfile(path):
        in_block = False
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if line.startswith("task_launcher:"):
                    in_block, found = True, True
                    continue
                if in_block:
                    if line[:1] and not line[:1].isspace():
                        break
                    body = line.split("#", 1)[0].strip()
                    if ":" in body:
                        key, value = (p.strip().strip('"') for p in body.split(":", 1))
                        if key in cfg and value:
                            cfg[key] = int(value) if isinstance(DEFAULTS[key], int) else value
    cfg["_block_found"] = found
    return cfg


def pid_alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)                    # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.GetLastError() == 5                                # access denied: the process exists
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259     # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


class NamedMutex:
    """Serialises the check-and-create of the lock file between launches (Windows named mutex); a no-op elsewhere or when it cannot be created."""
    def __init__(self):
        self.handle = None
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
                self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
            except Exception:
                self.handle = None

    def enter(self, millis=5000):
        if not self.handle:
            return True
        import ctypes
        ctypes.windll.kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        return ctypes.windll.kernel32.WaitForSingleObject(self.handle, millis) in (0, 0x80)      # WAIT_OBJECT_0 or WAIT_ABANDONED

    def leave(self):
        if self.handle:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
            ctypes.windll.kernel32.ReleaseMutex(self.handle)


def limit_text(text, n=1500):
    text = (text or "").replace("\r\n", " | ").replace("\n", " | ").strip()
    return text[:n] + "..." if len(text) > n else text


class Launcher:
    def __init__(self, args, clone_dir):
        self.args, self.clone = args, clone_dir
        self.cfg = read_config(clone_dir)
        for key in ("lock_wait_seconds", "lock_stale_seconds", "git_retries", "retry_wait_min_seconds", "retry_wait_max_seconds", "git_timeout_seconds"):
            value = getattr(args, key)
            if value is not None and value >= 0:
                self.cfg[key] = value
        self.lock_path = os.path.join(clone_dir, *self.cfg["lock_file"].split("/"))
        self.log_path = os.path.join(clone_dir, *self.cfg["log_file"].split("/"))
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.mutex = NamedMutex()

    def log(self, event, detail=""):
        append_line([self.log_path], "%s pid=%d task=%s %s %s" % (now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], os.getpid(), self.args.task, event, detail))

    # ---------------------------------------------------------------------------------------------- the lock
    def try_create_lock(self):
        tmp = "%s.%d.tmp" % (self.lock_path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "task": self.args.task, "started_at": now().isoformat()}, f)
        try:
            os.rename(tmp, self.lock_path)                    # fails when the lock exists: the content and the creation are one step
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    def lock_state(self):
        """(stale, why) of an existing lock."""
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return True, "lock vanished"
        holder = None
        try:
            with open(self.lock_path, encoding="utf-8") as f:
                holder = json.load(f)
            pid = int(holder["pid"])
        except Exception:
            if age > self.cfg["lock_stale_seconds"]:
                return True, "unreadable lock older than %d s" % self.cfg["lock_stale_seconds"]
            return False, "unreadable lock, young"
        try:
            holder_age = (now() - datetime.datetime.fromisoformat(holder["started_at"])).total_seconds()
        except Exception:
            holder_age = age
        who = "holder pid %d (%s)" % (pid, holder.get("task"))
        if not pid_alive(pid):
            return True, "%s is not running" % who
        if holder_age > self.cfg["lock_stale_seconds"]:
            return True, "%s started %d s ago, over %d s" % (who, int(holder_age), self.cfg["lock_stale_seconds"])
        return False, "held by pid %d (%s) since %s" % (pid, holder.get("task"), holder.get("started_at"))

    def get_lock(self):
        deadline = time.time() + self.cfg["lock_wait_seconds"]
        waited = False
        while True:
            got = False
            entered = self.mutex.enter()
            try:
                if entered:
                    if self.try_create_lock():
                        got = True
                    else:
                        stale, why = self.lock_state()
                        if stale:
                            self.log("lock_takeover", why)
                            try:
                                os.remove(self.lock_path)
                            except OSError:
                                pass
                            got = self.try_create_lock()
                        elif not waited:
                            self.log("lock_wait", why)
                            waited = True
            finally:
                if entered:
                    self.mutex.leave()
            if got:
                self.log("lock_acquired", self.lock_path)
                return True
            if time.time() > deadline:
                self.log("lock_timeout", "not obtained within %d s" % self.cfg["lock_wait_seconds"])
                return False
            time.sleep(self.cfg["lock_poll_seconds"])

    def remove_lock(self):
        try:
            with open(self.lock_path, encoding="utf-8") as f:
                pid = int(json.load(f)["pid"])
            if pid == os.getpid():
                os.remove(self.lock_path)
                self.log("lock_released")
            else:
                self.log("lock_not_ours_not_released", "now held by pid %d" % pid)
        except Exception as e:
            self.log("lock_release_failed", str(e))

    # ---------------------------------------------------------------------------------------------- git
    def git(self, *git_args):
        try:
            p = subprocess.run([self.args.git, "-C", self.clone, *git_args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.cfg["git_timeout_seconds"])
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "git timed out after %d s" % self.cfg["git_timeout_seconds"]
        except OSError as e:
            return 125, "", "git could not be started: %s" % e

    def update_clone(self):
        attempts = 1 + self.cfg["git_retries"]
        for i in range(1, attempts + 1):
            code, out, err = self.git("pull", "--ff-only", "origin", "main")
            self.log("git_pull", "attempt %d/%d exit=%d stdout=[%s] stderr=[%s]" % (i, attempts, code, limit_text(out), limit_text(err)))
            if code == 0:
                return True
            if i < attempts:
                wait = random.randint(self.cfg["retry_wait_min_seconds"], self.cfg["retry_wait_max_seconds"])
                self.log("git_retry_wait", "%d s" % wait)
                time.sleep(wait)
        return False

    def check_clone(self):
        """None when HEAD is origin/main and no tracked file is modified or staged, else the reason."""
        hc, head, _ = self.git("rev-parse", "HEAD")
        oc, origin, _ = self.git("rev-parse", "origin/main")
        sc, status, _ = self.git("status", "--porcelain", "--untracked-files=no")
        self.log("git_check", "HEAD=%s origin/main=%s tracked_changes=[%s]" % (head.strip(), origin.strip(), limit_text(status, 400)))
        if hc or oc or sc:
            return "a git check command failed (HEAD %d, origin/main %d, status %d)" % (hc, oc, sc)
        if head.strip() != origin.strip():
            return "HEAD %s is not origin/main %s" % (head.strip(), origin.strip())
        if status.strip():
            return "tracked files are modified or staged: %s" % limit_text(status, 400)
        return None

    # ---------------------------------------------------------------------------------------------- run
    def run(self):
        script_path = os.path.join(self.clone, self.args.script)
        self.log("launcher_start", "script=%s clone=%s lock_wait=%ds stale=%ds retries=%d config_block=%s" % (self.args.script, self.clone, self.cfg["lock_wait_seconds"],
                 self.cfg["lock_stale_seconds"], self.cfg["git_retries"], self.cfg["_block_found"]))
        if not self.get_lock():
            return 91
        pulled, problem = False, None
        try:
            pulled = self.update_clone()
            if pulled:
                problem = self.check_clone()
        finally:
            self.remove_lock()
        if not pulled:
            self.log("launcher_stop", "git pull failed after every retry; Python not started")
            return 92
        if problem:
            self.log("launcher_stop", "%s; Python not started" % problem)
            return 93
        if not os.path.isfile(script_path):
            self.log("launcher_stop", "script not found: %s" % script_path)
            return 94
        self.log("python_start", "%s %s %s" % (self.args.python, script_path, " ".join(self.args.script_args)))
        code = subprocess.call([self.args.python, script_path, *self.args.script_args], cwd=self.clone)
        self.log("python_exit", "code=%d" % code)
        return code


def parse(argv):
    p = argparse.ArgumentParser(description="Shared launcher of the scheduled tasks")
    p.add_argument("--task", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--git", default="git")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--clone-dir", default="")
    for key in ("lock_wait_seconds", "lock_stale_seconds", "git_retries", "retry_wait_min_seconds", "retry_wait_max_seconds", "git_timeout_seconds"):
        p.add_argument("--" + key.replace("_", "-"), dest=key, type=int, default=None)
    args, rest = p.parse_known_args(argv)
    args.script_args = rest
    return args


def main(argv):
    write_boot("boot user=%s python=%s exe=%s cwd=%s userprofile=%s temp=%s argv=[%s]" % (os.environ.get("USERNAME", "?"), sys.version.split()[0], sys.executable, os.getcwd(),
               os.environ.get("USERPROFILE", "?"), os.environ.get("TEMP", "?"), " ".join(argv)))
    code = 94
    try:
        args = parse(argv)
        clone = os.path.abspath(args.clone_dir) if args.clone_dir else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = Launcher(args, clone).run()
    except SystemExit as e:                                      # argparse: a missing or unknown option
        code = 94
        write_boot("launcher_args_error code=%s" % e.code)
    except Exception:
        tb = traceback.extract_tb(sys.exc_info()[2])
        write_boot("launcher_fatal %s at line %d: %s" % (traceback.format_exc().strip().splitlines()[-1], tb[-1].lineno, tb[-1].line))
        code = 94
    finally:
        write_boot("end exitcode=%s" % code)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
