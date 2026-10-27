<#
Shared launcher of the two scheduled tasks (SaleForecast_PostingDelaySnapshot and SaleForecastMonthlyRefresh) -- Prompt 59.

Why: both tasks used to run `git pull --ff-only origin main` in the publishing clone and then Python. Two launches in the same second (a missed start after the machine woke) made the two pulls
collide on FETCH_HEAD ("Cannot fast-forward to multiple branches", exit 128), so neither merged and neither started Python (Prompt 58, STATUS.md). Task Scheduler does not restart a task whose
action returned an error code, so nothing repaired it.

What it does, in order:
  1. takes the shared lock (output\runs\git_pull.lock, written atomically, holding PID, task and start time), waiting up to lock_wait_seconds; a lock whose PID is dead or that is older than
     lock_stale_seconds is stale and is taken over (logged);
  2. git pull --ff-only origin main, retried git_retries times after a random wait of retry_wait_min_seconds to retry_wait_max_seconds;
  3. checks that HEAD equals origin/main and that no tracked file is modified or staged; on a failure it starts no Python;
  4. releases the lock (the lock covers ONLY the git steps, never the Python run: a monthly run of up to 3 hours must not make the daily task wait past its 1 hour limit; the monthly-runner lock
     already keeps the two jobs apart at Python level);
  5. starts Python with the script and its arguments and returns Python's exit code unchanged.
Every lock event and every git attempt (stdout, stderr, exit code, time) is appended to output\runs\task_launcher.log. Values come from config\config.yaml (block task_launcher); the parameters
of the same names override them (tests).

This file is a .ps1 on purpose: PowerShell reads the whole script before it runs it, so the pull in step 2 may rewrite this very file without changing the running copy (a .cmd file is read line by line
while it runs).

Exit codes: Python's own code when Python ran; 91 the lock was not obtained in time; 92 git pull failed after every retry; 93 HEAD is not origin/main or a tracked file is modified (Python not started);
94 the script to start does not exist or the launcher itself failed.

Usage (task action):  powershell.exe -NoProfile -ExecutionPolicy Bypass -File <clone>\src\task_launcher.ps1 -Task <task name> -Script src\snapshot_daily.py -Git <git.exe> -Python <python.exe>
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)][string]$Task,
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$Git = "git",
    [string]$Python = "python",
    [string]$CloneDir = (Split-Path -Parent $PSScriptRoot),
    [int]$LockWaitSeconds = -1,
    [int]$LockStaleSeconds = -1,
    [int]$GitRetries = -1,
    [int]$RetryWaitMinSeconds = -1,
    [int]$RetryWaitMaxSeconds = -1,
    [int]$GitTimeoutSeconds = -1,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"
$Defaults = @{ lock_file = "output/runs/git_pull.lock"; log_file = "output/runs/task_launcher.log"; lock_wait_seconds = 300; lock_stale_seconds = 900
               git_retries = 3; retry_wait_min_seconds = 20; retry_wait_max_seconds = 60; git_timeout_seconds = 300; lock_poll_seconds = 2 }

function Read-LauncherConfig([string]$root) {
    $cfg = @{}
    foreach ($k in $Defaults.Keys) { $cfg[$k] = $Defaults[$k] }
    $path = Join-Path $root "config\config.yaml"
    $found = $false
    if (Test-Path -LiteralPath $path) {
        $inBlock = $false
        foreach ($line in [System.IO.File]::ReadLines($path)) {
            if ($line -match '^task_launcher:\s*(#.*)?$') { $inBlock = $true; $found = $true; continue }
            if ($inBlock) {
                if ($line -match '^\S') { break }
                if ($line -match '^\s+([a-z_]+):\s*([^#\s][^#]*?)\s*(#.*)?$') {
                    $k = $Matches[1]; $v = $Matches[2].Trim('"')
                    if ($cfg.ContainsKey($k)) { if ($Defaults[$k] -is [int]) { $cfg[$k] = [int]$v } else { $cfg[$k] = $v } }
                }
            }
        }
    }
    $cfg["_block_found"] = $found
    return $cfg
}

$Cfg = Read-LauncherConfig $CloneDir
if ($LockWaitSeconds -ge 0) { $Cfg.lock_wait_seconds = $LockWaitSeconds }
if ($LockStaleSeconds -ge 0) { $Cfg.lock_stale_seconds = $LockStaleSeconds }
if ($GitRetries -ge 0) { $Cfg.git_retries = $GitRetries }
if ($RetryWaitMinSeconds -ge 0) { $Cfg.retry_wait_min_seconds = $RetryWaitMinSeconds }
if ($RetryWaitMaxSeconds -ge 0) { $Cfg.retry_wait_max_seconds = $RetryWaitMaxSeconds }
if ($GitTimeoutSeconds -ge 0) { $Cfg.git_timeout_seconds = $GitTimeoutSeconds }

$LockPath = Join-Path $CloneDir ($Cfg.lock_file -replace '/', '\')
$LogPath = Join-Path $CloneDir ($Cfg.log_file -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LockPath) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

function Write-Log([string]$event, [string]$detail = "") {
    $line = "{0} pid={1} task={2} {3} {4}" -f (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fff"), $PID, $Task, $event, $detail
    for ($i = 0; $i -lt 5; $i++) {
        try { [System.IO.File]::AppendAllText($LogPath, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))); return } catch { Start-Sleep -Milliseconds 100 }
    }
}

function Limit-Text([string]$s, [int]$n = 1500) {
    if ($null -eq $s) { return "" }
    $s = ($s -replace '\r?\n', ' | ').Trim()
    if ($s.Length -gt $n) { return $s.Substring(0, $n) + "..." }
    return $s
}

# ------------------------------------------------------------------------------------------------ the lock
$Mutex = $null
try { $Mutex = New-Object System.Threading.Mutex($false, "Global\SaleForecastGitPullLaunch") } catch { Write-Log "mutex_unavailable" $_.Exception.Message }

function Try-CreateLock {
    $tmp = "$LockPath.$PID.tmp"
    $body = @{ pid = $PID; task = $Task; started_at = (Get-Date).ToString("o") } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($tmp, $body, (New-Object System.Text.UTF8Encoding($false)))
    try { [System.IO.File]::Move($tmp, $LockPath); return $true }          # fails when the lock exists: the write of the whole content and the creation are one step
    catch [System.IO.IOException] { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue; return $false }
}

function Get-LockState {
    # returns @{ stale = bool; why = text } for an existing lock
    $item = Get-Item -LiteralPath $LockPath -ErrorAction SilentlyContinue
    if (-not $item) { return @{ stale = $true; why = "lock vanished" } }
    $holder = $null
    try { $holder = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json } catch { $holder = $null }
    $age = ((Get-Date) - $item.LastWriteTime).TotalSeconds
    if ($null -eq $holder -or $null -eq $holder.pid) {
        if ($age -gt $Cfg.lock_stale_seconds) { return @{ stale = $true; why = "unreadable lock older than $($Cfg.lock_stale_seconds) s" } }
        return @{ stale = $false; why = "unreadable lock, young" }
    }
    $started = $item.LastWriteTime
    try { $started = [datetime]::Parse($holder.started_at) } catch { }
    $holderAge = ((Get-Date) - $started).TotalSeconds
    if (-not (Get-Process -Id ([int]$holder.pid) -ErrorAction SilentlyContinue)) { return @{ stale = $true; why = "holder pid $($holder.pid) ($($holder.task)) is not running" } }
    if ($holderAge -gt $Cfg.lock_stale_seconds) { return @{ stale = $true; why = "holder pid $($holder.pid) ($($holder.task)) started $([int]$holderAge) s ago, over $($Cfg.lock_stale_seconds) s" } }
    return @{ stale = $false; why = "held by pid $($holder.pid) ($($holder.task)) since $($holder.started_at)" }
}

function Get-Lock {
    $deadline = (Get-Date).AddSeconds($Cfg.lock_wait_seconds)
    $waited = $false
    while ($true) {
        $got = $false
        $entered = $true
        if ($Mutex) { try { $entered = $Mutex.WaitOne(5000) } catch [System.Threading.AbandonedMutexException] { $entered = $true } }
        try {
            if ($entered) {
                if (Try-CreateLock) { $got = $true }
                else {
                    $state = Get-LockState
                    if ($state.stale) {
                        Write-Log "lock_takeover" $state.why
                        Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
                        if (Try-CreateLock) { $got = $true }
                    }
                    elseif (-not $waited) { Write-Log "lock_wait" $state.why; $waited = $true }
                }
            }
        }
        finally { if ($Mutex -and $entered) { try { $Mutex.ReleaseMutex() } catch { } } }
        if ($got) { Write-Log "lock_acquired" $LockPath; return $true }
        if ((Get-Date) -gt $deadline) { Write-Log "lock_timeout" "not obtained within $($Cfg.lock_wait_seconds) s"; return $false }
        Start-Sleep -Seconds $Cfg.lock_poll_seconds
    }
}

function Remove-Lock {
    try {
        $holder = Get-Content -LiteralPath $LockPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if ([int]$holder.pid -eq $PID) { Remove-Item -LiteralPath $LockPath -Force; Write-Log "lock_released" }
        else { Write-Log "lock_not_ours_not_released" "now held by pid $($holder.pid)" }
    } catch { Write-Log "lock_release_failed" $_.Exception.Message }
}

# ------------------------------------------------------------------------------------------------ git
function Invoke-Git([string]$gitArgs) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Git
    $psi.Arguments = "-C `"$CloneDir`" $gitArgs"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEndAsync()
    $err = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($Cfg.git_timeout_seconds * 1000)) { try { $p.Kill() } catch { }; return @{ code = 124; out = ""; err = "git timed out after $($Cfg.git_timeout_seconds) s" } }
    $p.WaitForExit()
    return @{ code = $p.ExitCode; out = $out.Result; err = $err.Result }
}

function Update-Clone {
    $attempts = 1 + $Cfg.git_retries
    for ($i = 1; $i -le $attempts; $i++) {
        $r = Invoke-Git "pull --ff-only origin main"
        Write-Log "git_pull" ("attempt {0}/{1} exit={2} stdout=[{3}] stderr=[{4}]" -f $i, $attempts, $r.code, (Limit-Text $r.out), (Limit-Text $r.err))
        if ($r.code -eq 0) { return $true }
        if ($i -lt $attempts) {
            $wait = Get-Random -Minimum $Cfg.retry_wait_min_seconds -Maximum ($Cfg.retry_wait_max_seconds + 1)
            Write-Log "git_retry_wait" "$wait s"
            Start-Sleep -Seconds $wait
        }
    }
    return $false
}

function Test-CloneState {
    $head = Invoke-Git "rev-parse HEAD"
    $origin = Invoke-Git "rev-parse origin/main"
    $status = Invoke-Git "status --porcelain --untracked-files=no"
    Write-Log "git_check" ("HEAD={0} origin/main={1} tracked_changes=[{2}]" -f $head.out.Trim(), $origin.out.Trim(), (Limit-Text $status.out 400))
    if ($head.code -ne 0 -or $origin.code -ne 0 -or $status.code -ne 0) { return "a git check command failed (HEAD $($head.code), origin/main $($origin.code), status $($status.code))" }
    if ($head.out.Trim() -ne $origin.out.Trim()) { return "HEAD $($head.out.Trim()) is not origin/main $($origin.out.Trim())" }
    if ($status.out.Trim()) { return "tracked files are modified or staged: $(Limit-Text $status.out 400)" }
    return $null
}

# ------------------------------------------------------------------------------------------------ run
$ScriptPath = Join-Path $CloneDir $Script
try {
    Write-Log "launcher_start" ("script={0} clone={1} lock_wait={2}s stale={3}s retries={4} config_block={5}" -f $Script, $CloneDir, $Cfg.lock_wait_seconds, $Cfg.lock_stale_seconds, $Cfg.git_retries, $Cfg._block_found)
    if (-not (Get-Lock)) { exit 91 }
    $problem = $null
    $pulled = $false
    try {
        $pulled = Update-Clone
        if ($pulled) { $problem = Test-CloneState }
    }
    finally { Remove-Lock }
    if (-not $pulled) { Write-Log "launcher_stop" "git pull failed after every retry; Python not started"; exit 92 }
    if ($problem) { Write-Log "launcher_stop" "$problem; Python not started"; exit 93 }
    if (-not (Test-Path -LiteralPath $ScriptPath)) { Write-Log "launcher_stop" "script not found: $ScriptPath"; exit 94 }
    Write-Log "python_start" ("{0} {1} {2}" -f $Python, $ScriptPath, ($ScriptArgs -join " "))
    Set-Location -LiteralPath $CloneDir
    & $Python $ScriptPath @ScriptArgs
    $code = $LASTEXITCODE
    Write-Log "python_exit" "code=$code"
    exit $code
}
catch {
    Write-Log "launcher_error" (Limit-Text $_.Exception.Message)
    exit 94
}
