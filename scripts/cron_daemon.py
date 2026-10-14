#!/usr/bin/env python3
"""
cron_daemon.py — Peter's cron daemon. Clean rewrite 2026-06-05.

Single file. No dependencies beyond stdlib.
Runs 7 scheduled jobs using shell commands.
Self-healing: recovers on container restart via ensure_daemon.py.

Usage:
  python3 scripts/cron_daemon.py             # run as daemon (loops forever)
  python3 scripts/cron_daemon.py --status    # show last run times
  python3 scripts/cron_daemon.py --tick      # run one check cycle and exit
  python3 scripts/cron_daemon.py --dry-run   # tick but don't actually execute
  python3 scripts/cron_daemon.py --run <job> # force-run one job now
"""

import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
WORKSPACE    = Path(__file__).resolve().parent.parent
JOBS_FILE    = WORKSPACE / "cron" / "jobs.json"
STATE_FILE   = WORKSPACE / "cron" / "state.json"
ENV_FILE     = Path("/home/openclaw/.openclaw/cron/openclaw.env")
LOG_FILE     = WORKSPACE / "logs" / "cron.log"
LOCK_DIR     = WORKSPACE / "cron" / "locks"

# ── Logging ────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cron_daemon")

# ── Cron expression matching ───────────────────────────────────────────────

def _field(expr: str, val: int) -> bool:
    if expr == "*":
        return True
    if "," in expr:
        return any(_field(p, val) for p in expr.split(","))
    if "/" in expr:
        rng, step = expr.split("/", 1)
        step = int(step)
        if rng == "*":
            return val % step == 0
        a, b = map(int, rng.split("-"))
        return a <= val <= b and (val - a) % step == 0
    if "-" in expr:
        a, b = map(int, expr.split("-"))
        return a <= val <= b
    return int(expr) == val


def cron_matches(expr: str, dt: datetime) -> bool:
    """Return True if dt matches the 5-field cron expression."""
    parts = expr.split()
    if len(parts) != 5:
        return False
    m, h, dom, mon, dow_expr = parts
    # Convert Python weekday (Mon=0) to cron dow (Sun=0)
    cron_dow = (dt.weekday() + 1) % 7
    dom_star = dom == "*"
    dow_star = dow_expr == "*"
    if dom_star and dow_star:
        day_ok = True
    elif dom_star:
        day_ok = _field(dow_expr, cron_dow)
    elif dow_star:
        day_ok = _field(dom, dt.day)
    else:
        # Vixie: OR when both restricted
        day_ok = _field(dom, dt.day) or _field(dow_expr, cron_dow)
    return (
        _field(m, dt.minute)
        and _field(h, dt.hour)
        and day_ok
        and _field(mon, dt.month)
    )

# ── State ──────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            # Schema check
            if data.get("schema") == "v1" and "jobs" in data:
                return data
        except Exception as e:
            log.warning(f"Corrupt state file, resetting: {e}")
    return {"schema": "v1", "jobs": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)

# ── Environment ────────────────────────────────────────────────────────────

def load_env() -> dict:
    env = os.environ.copy()
    if not ENV_FILE.exists():
        log.warning(f"Env file not found: {ENV_FILE}")
        return env
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                # Expand ${VAR} references from the actual environment
                import re
                v = re.sub(r'\$\{([^}]+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), v)
                env[k.strip()] = v
    except Exception as e:
        log.warning(f"Failed to read env file: {e}")
    return env

# ── Job locking ────────────────────────────────────────────────────────────

def job_lock(name: str):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{name}.lock"
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def job_unlock(fd) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except Exception:
        pass

# ── Job execution ──────────────────────────────────────────────────────────

def run_job(job: dict, env: dict, dry_run: bool = False) -> str:
    """Execute one job. Returns 'ok', 'failed', 'timeout', or 'locked'."""
    name = job["name"]
    cmd  = job.get("command", "")
    timeout = int(job.get("timeout_s", 300))

    if not cmd:
        log.error(f"[{name}] No command defined — skipping")
        return "failed"

    fd = job_lock(name)
    if fd is None:
        log.warning(f"[{name}] Already running — skipping (locked)")
        return "locked"

    try:
        if dry_run:
            log.info(f"[{name}] DRY-RUN: {cmd[:120]}")
            return "ok"

        log.info(f"[{name}] Starting")
        result = subprocess.run(
            ["bash", "-c", cmd],
            env=env,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            log.info(f"[{name}] OK (exit 0)")
            if result.stdout.strip():
                log.info(f"[{name}] stdout: {result.stdout.strip()[:300]}")
            return "ok"
        else:
            log.error(f"[{name}] FAILED (exit {result.returncode})")
            if result.stderr.strip():
                log.error(f"[{name}] stderr: {result.stderr.strip()[:400]}")
            return "failed"

    except subprocess.TimeoutExpired:
        log.error(f"[{name}] TIMEOUT (>{timeout}s)")
        return "timeout"
    except Exception as e:
        log.error(f"[{name}] EXCEPTION: {e}")
        return "failed"
    finally:
        job_unlock(fd)

# ── Tick ───────────────────────────────────────────────────────────────────

def tick(dry_run: bool = False) -> None:
    """Check all jobs and run any that are due."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    try:
        with open(JOBS_FILE) as f:
            config = json.load(f)
    except Exception as e:
        log.error(f"Cannot load jobs.json: {e}")
        return

    state = load_state()
    env   = load_env()
    dirty = False

    for job in config.get("jobs", []):
        if not job.get("enabled", True):
            continue
        name  = job["name"]
        schedule = job.get("schedule", {})
        # Handle both old string format and new dict format
        if isinstance(schedule, dict):
            expr = schedule.get("expr", "")
        else:
            expr = schedule

        if not cron_matches(expr, now):
            continue

        # Deduplicate: skip if already ran this exact minute
        last_run = state["jobs"].get(name, {}).get("last_run_minute")
        this_minute = now.strftime("%Y-%m-%d %H:%M")
        if last_run == this_minute:
            log.debug(f"[{name}] Already ran this minute — skip")
            continue

        status = run_job(job, env, dry_run=dry_run)

        state["jobs"][name] = {
            "last_run_minute": this_minute,
            "last_run_iso": now.isoformat(),
            "last_status": status,
        }
        dirty = True

    if dirty:
        save_state(state)


# ── CLI commands ───────────────────────────────────────────────────────────

def cmd_status() -> None:
    state = load_state()
    try:
        with open(JOBS_FILE) as f:
            config = json.load(f)
        jobs = [j["name"] for j in config.get("jobs", [])]
    except Exception:
        jobs = list(state["jobs"].keys())

    print(f"\n{'Job':<30} {'Last Run':>19}  {'Status':>8}")
    print("-" * 62)
    for name in jobs:
        js = state["jobs"].get(name, {})
        last = js.get("last_run_iso", "never")[:19]
        status = js.get("last_status", "-")
        print(f"{name:<30} {last:>19}  {status:>8}")
    print()


def cmd_run_one(name: str) -> None:
    try:
        with open(JOBS_FILE) as f:
            config = json.load(f)
    except Exception as e:
        print(f"ERROR: cannot load jobs.json: {e}")
        sys.exit(1)

    job = next((j for j in config.get("jobs", []) if j["name"] == name), None)
    if not job:
        print(f"ERROR: job '{name}' not found")
        sys.exit(1)

    env    = load_env()
    state  = load_state()
    status = run_job(job, env)
    now    = datetime.now(timezone.utc)
    state["jobs"][name] = {
        "last_run_minute": now.strftime("%Y-%m-%d %H:%M"),
        "last_run_iso": now.isoformat(),
        "last_status": status,
    }
    save_state(state)
    print(f"Result: {status}")


def cmd_daemon() -> None:
    log.info("=" * 60)
    log.info("cron_daemon started")
    log.info(f"Jobs:  {JOBS_FILE}")
    log.info(f"State: {STATE_FILE}")
    log.info(f"Log:   {LOG_FILE}")
    log.info("=" * 60)

    while True:
        try:
            tick()
        except Exception as e:
            log.error(f"Tick exception: {e}", exc_info=True)
        # Sleep until the next minute boundary + 2s buffer
        now = time.time()
        sleep_s = 60 - (now % 60) + 2
        time.sleep(sleep_s)


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="OpenClaw cron daemon")
    p.add_argument("--status",   action="store_true", help="Show last run status")
    p.add_argument("--tick",     action="store_true", help="Run one check cycle and exit")
    p.add_argument("--dry-run",  action="store_true", help="Tick without executing")
    p.add_argument("--run",      metavar="JOB",       help="Force-run one job now")
    args = p.parse_args()

    if args.status:
        cmd_status()
    elif args.tick or args.dry_run:
        tick(dry_run=args.dry_run)
    elif args.run:
        cmd_run_one(args.run)
    else:
        cmd_daemon()


if __name__ == "__main__":
    main()
