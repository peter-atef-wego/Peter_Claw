#!/usr/bin/env python3
"""
Reliable cron executor for jobs.json.
Designed to replace OpenClaw's built-in scheduler as a fallback.

Runs every minute from system crontab:
  * * * * * /usr/bin/python3 /home/openclaw/.openclaw/workspace/scripts/cron_executor.py

Features:
  - Parses standard cron expressions
  - Tracks execution state per job
  - Executes enabled jobs when scheduled time matches
  - Spawns subagent turns or shell commands
  - Full logging to file
  - Resilient to errors (one job failure doesn't block others)
"""

import argparse
import fcntl
import json
import logging
import os
import re
import sys
import subprocess
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

WORKSPACE_DIR = Path("/home/openclaw/.openclaw/workspace")
JOBS_CONFIG = WORKSPACE_DIR / "cron" / "jobs.json"
STATE_FILE = WORKSPACE_DIR / "cron" / "executor_state.json"
ENV_FILE = Path("/home/openclaw/.openclaw/cron/openclaw.env")
LOG_FILE = WORKSPACE_DIR / "logs" / "cron_executor.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cron_executor")


# ─────────────────────────────────────────────
# CRON EXPRESSION PARSING
# ─────────────────────────────────────────────

def parse_cron_expr(expr: str) -> dict:
    """
    Parse a cron expression into components.
    Format: minute hour day month day_of_week
    Returns: {minute, hour, day, month, day_of_week}
    """
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expr}")
    
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def matches_cron(cron_dict: dict, dt: datetime) -> bool:
    """
    Check if a given datetime matches a cron expression.
    Supports: *, numbers, ranges (1-5), and lists (1,3,5).
    """
    def field_matches(field_str: str, value: int) -> bool:
        if field_str == "*":
            return True
        
        # Handle comma-separated values
        if "," in field_str:
            return any(field_matches(part.strip(), value) for part in field_str.split(","))
        
        # Handle ranges
        if "-" in field_str and "*/" not in field_str:
            start, end = map(int, field_str.split("-"))
            return start <= value <= end
        
        # Handle step values (e.g., */5 or 0-23/2)
        if "/" in field_str:
            range_part, step = field_str.split("/")
            step = int(step)
            if range_part == "*":
                return value % step == 0
            else:
                start, end = map(int, range_part.split("-"))
                return start <= value <= end and (value - start) % step == 0
        
        # Handle plain number
        return int(field_str) == value
    
    # Monday=0, Sunday=6 in datetime; convert to cron format (Monday=1, Sunday=0)
    cron_dow = (dt.weekday() + 1) % 7

    # Vixie-cron semantics for day/day_of_week:
    # - If day=* and dow is specific  → match only on dow
    # - If dow=* and day is specific  → match only on day
    # - If both are *                 → always match
    # - If both are specific          → OR them (either can trigger)
    day_is_star = cron_dict["day"] == "*"
    dow_is_star = cron_dict["day_of_week"] == "*"

    if day_is_star and dow_is_star:
        day_match = True
    elif day_is_star:
        day_match = field_matches(cron_dict["day_of_week"], cron_dow)
    elif dow_is_star:
        day_match = field_matches(cron_dict["day"], dt.day)
    else:
        # Both restricted — OR (standard vixie-cron)
        day_match = (
            field_matches(cron_dict["day"], dt.day)
            or field_matches(cron_dict["day_of_week"], cron_dow)
        )

    return (
        field_matches(cron_dict["minute"], dt.minute)
        and field_matches(cron_dict["hour"], dt.hour)
        and day_match
        and field_matches(cron_dict["month"], dt.month)
    )


# ─────────────────────────────────────────────
# STATE TRACKING
# ─────────────────────────────────────────────

def load_state() -> dict:
    """Load execution state from file.

    Migrates legacy format where job keys were stored at the top level
    This migration runs automatically and is idempotent.
    """
    raw: dict = {"jobs": {}}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                raw = json.load(f)
        except Exception as e:
            log.warning(f"Failed to load state: {e}. Starting fresh.")
            return {"jobs": {}}

    # --- Migration: lift top-level job keys into raw["jobs"] ---
    migrated = False
    jobs_bucket = raw.setdefault("jobs", {})
    for key in list(raw.keys()):
        if key == "jobs":
            continue
        val = raw[key]
        if isinstance(val, dict) and ("last_run" in val or "last_status" in val or "last_run_ts" in val):
            # Only migrate if NOT already in jobs bucket
            if key not in jobs_bucket:
                old_ts = val.get("last_run")  # old format was a float epoch
                new_entry = {
                    "last_run_ts": (
                        datetime.fromtimestamp(old_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                        if isinstance(old_ts, (int, float)) else old_ts
                    ),
                    "last_run_iso": (
                        datetime.fromtimestamp(old_ts, tz=timezone.utc).isoformat()
                        if isinstance(old_ts, (int, float)) else None
                    ),
                    "status": val.get("last_status", "unknown"),
                    "migrated_from_legacy": True,
                }
                jobs_bucket[key] = new_entry
                migrated = True
                log.debug(f"Migrated legacy state for job '{key}'")
            # Remove the top-level key regardless
            del raw[key]

    if migrated:
        log.info("Migrated legacy executor_state.json format → nested jobs bucket")
        # Persist the migrated state immediately
        try:
            STATE_FILE.write_text(json.dumps(raw, indent=2))
        except Exception as e:
            log.warning(f"Could not persist migrated state: {e}")

    raw.setdefault("jobs", {})
    return raw


def save_state(state: dict) -> None:
    """Save execution state to file."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.error(f"Failed to save state: {e}")


def job_should_run(job_name: str, now: datetime, state: dict) -> bool:
    """
    Check if a job should run.
    Prevent duplicate runs within the same minute.
    """
    job_state = state.get("jobs", {}).get(job_name, {})
    last_run = job_state.get("last_run_ts")
    
    # Format current time as YYYY-MM-DD HH:MM
    current_minute = now.strftime("%Y-%m-%d %H:%M")
    
    # If job ran this minute already, skip
    if last_run == current_minute:
        return False
    
    return True


# ─────────────────────────────────────────────
# JOB EXECUTION
# ─────────────────────────────────────────────

def load_env_file() -> dict:
    """Load environment variables from cron env file."""
    env = os.environ.copy()
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Handle export statements
                        if line.startswith("export "):
                            line = line[7:]
                        if "=" in line:
                            key, val = line.split("=", 1)
                            # Remove quotes if present
                            val = val.strip().strip('"\'')
                            # Expand env vars in value
                            val = val.replace("${GITHUB_TOKEN_V4}", env.get("GITHUB_TOKEN_V4", ""))
                            val = val.replace("${JIRA_API_TOKEN}", env.get("JIRA_API_TOKEN", ""))
                            val = val.replace("${SLACK_BOT_TOKEN_NETSUITE_CHAMPION}", env.get("SLACK_BOT_TOKEN_NETSUITE_CHAMPION", ""))
                            val = val.replace("${SLACK_WEBHOOK}", env.get("SLACK_WEBHOOK", ""))
                            if val:
                                env[key.strip()] = val
        except Exception as e:
            log.warning(f"Failed to load env file: {e}")
    return env


# Shell-keyword prefixes — if the message (or its post-colon suffix) starts
# with one of these, we treat it as a bash command. Otherwise we conclude
# the message genuinely needs an LLM (e.g. "Build a Slack table…") and skip
# it gracefully rather than crashing.
SHELL_KEYWORDS = (
    "source ", "python ", "python3 ", "git ", "curl ", "bash ", "sh ",
    "cd ", "export ", "echo ", "/usr/", "/bin/",
)

# Common english-prose trailers OpenClaw agent-turn jobs end with — must be
# stripped before handing off to bash. Bash treats them as garbage.
TRAILER_PATTERNS = (
    re.compile(r"\.\s*Do not ask for confirmation\.?\s*$", re.IGNORECASE),
    re.compile(r"\.\s*$"),  # any final period left over
)


def _looks_like_shell(s: str) -> bool:
    return any(s.lstrip().startswith(kw) for kw in SHELL_KEYWORDS)


def extract_shell_command(message: str) -> Optional[str]:
    """Find the bash command embedded in an agent-turn payload message.

    Walks every ': ' separator and returns the first suffix that starts
    with a shell keyword. Returns None if no shell-y content is found,
    which means the job genuinely needs an LLM and we should skip it.
    """
    # Case 1: already a bare shell command
    if _looks_like_shell(message):
        return message

    # Case 2: prose prefix → first ': ' followed by a shell keyword
    start = 0
    while True:
        idx = message.find(": ", start)
        if idx < 0:
            return None
        candidate = message[idx + 2:]
        if _looks_like_shell(candidate):
            return candidate
        start = idx + 2


def clean_shell_command(cmd: str) -> str:
    """Strip prose trailers that bash would treat as a syntax error."""
    cmd = cmd.strip()
    for pat in TRAILER_PATTERNS:
        cmd = pat.sub("", cmd).strip()
    return cmd


def execute_job_payload(message: str, job_name: str, env: dict,
                        timeout_s: int = 600, dry_run: bool = False) -> tuple:
    """Run one job's payload message. Returns (status, detail) where status
    is one of: 'ok', 'failed', 'timeout', 'skipped_needs_llm', 'error'.

    Replaces the old (execute_agent_turn, execute_shell_command) split.
    Every job in jobs.json declares payload.kind == "agentTurn", but in
    practice 6 of 7 message bodies are bash commands. We detect which is
    which from the message itself instead of trusting payload.kind.
    """
    shell_cmd = extract_shell_command(message)
    if shell_cmd is None:
        log.warning(
            f"⊘ Job {job_name} needs LLM, not shell — skipping cleanly. "
            f"This job has payload.kind=agentTurn AND no embedded bash; "
            f"it requires OpenClaw's runtime (currently broken) or a "
            f"Python rewrite. Won't try to run it from cron_executor."
        )
        return ("skipped_needs_llm", "no shell content found in message")

    shell_cmd = clean_shell_command(shell_cmd)

    if dry_run:
        log.info(f"  [dry-run] would execute: {shell_cmd[:200]}")
        return ("ok", "dry-run")

    try:
        result = subprocess.run(
            ["bash", "-c", shell_cmd],
            env=env,
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        if result.returncode == 0:
            log.info(f"✓ Job {job_name} completed (shell, {timeout_s}s budget)")
            if result.stdout:
                log.info(f"  Output: {result.stdout[:200]}")
            return ("ok", f"exit 0")

        log.error(f"✗ Job {job_name} failed with code {result.returncode}")
        if result.stderr:
            log.error(f"  STDERR: {result.stderr[:300]}")
        return ("failed", f"exit {result.returncode}: {(result.stderr or '')[:200]}")

    except subprocess.TimeoutExpired:
        log.error(f"✗ Job {job_name} timed out (>{timeout_s}s)")
        return ("timeout", f">{timeout_s}s")
    except Exception as e:
        log.error(f"✗ Job {job_name} exception: {e}")
        return ("error", str(e)[:200])


# ─── Backwards-compat shims ───────────────────────────────────────────────
# Kept so any other script that imports these names doesn't break. New
# code should call execute_job_payload directly.

def execute_agent_turn(message: str, job_name: str) -> bool:
    status, _ = execute_job_payload(message, job_name, os.environ.copy())
    return status == "ok"


def execute_shell_command(command: str, job_name: str, env: dict) -> bool:
    status, _ = execute_job_payload(command, job_name, env)
    return status == "ok"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def _job_lock_path(job_name: str) -> Path:
    lock_dir = WORKSPACE_DIR / "cron" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"{job_name}.lock"


def _acquire_job_lock(job_name: str):
    """Per-job advisory file lock. Returns (fd, True) on success or
    (None, False) if another instance is already running this job. The
    lock auto-releases when the fd is closed at process exit, so even a
    kill -9 unwedges it.
    """
    path = _job_lock_path(job_name)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, True
    except BlockingIOError:
        os.close(fd)
        return None, False


def _release_job_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _run_one_job(job: dict, now: datetime, state: dict, env: dict,
                 dry_run: bool = False, force: bool = False) -> str:
    """Run a single job after schedule/state gating. Returns one of:
    'ok', 'failed', 'skipped_not_scheduled', 'skipped_already_ran',
    'skipped_locked', 'skipped_needs_llm', 'invalid'.
    """
    job_name = job.get("name", "unnamed")
    schedule = job.get("schedule", {})

    if schedule.get("kind") != "cron":
        log.warning(f"Job {job_name}: non-cron schedule kind={schedule.get('kind')}; skipping")
        return "invalid"

    try:
        cron_dict = parse_cron_expr(schedule.get("expr", ""))
    except Exception as e:
        log.error(f"Invalid cron expr for {job_name}: {e}")
        return "invalid"

    if not force:
        if not matches_cron(cron_dict, now):
            return "skipped_not_scheduled"
        if not job_should_run(job_name, now, state):
            log.debug(f"Skipping {job_name} (already ran this minute)")
            return "skipped_already_ran"

    lock_fd, got_lock = _acquire_job_lock(job_name)
    if not got_lock:
        log.warning(f"⊘ Job {job_name} skipped — another instance is holding the lock")
        return "skipped_locked"

    try:
        log.info(f"→ Executing {job_name} (schedule: {schedule['expr']}{', FORCED' if force else ''})")

        payload = job.get("payload", {})
        message = payload.get("message", "")
        timeout_s = int(job.get("timeout_s") or 600)

        status, detail = execute_job_payload(
            message, job_name, env, timeout_s=timeout_s, dry_run=dry_run,
        )

        current_minute = now.strftime("%Y-%m-%d %H:%M")
        state.setdefault("jobs", {})[job_name] = {
            "last_run_ts": current_minute,
            "last_run_iso": now.isoformat(),
            "status": status,
            "detail": detail,
            "success": (status == "ok"),
            "updated_at": now.isoformat(),
        }
        return status if status == "ok" else ("failed" if status in ("failed", "timeout", "error") else status)
    finally:
        _release_job_lock(lock_fd)


def cmd_tick(args) -> int:
    """Run one tick — called every minute from system cron or the daemon."""
    now = datetime.now(timezone.utc)
    log.info(f"Executor tick at {now.isoformat()}")

    try:
        with open(JOBS_CONFIG) as f:
            config = json.load(f)
    except Exception as e:
        log.error(f"Failed to load jobs.json: {e}")
        return 1

    state = load_state()
    state.setdefault("jobs", {})
    env = load_env_file()

    executed = []
    failed = []
    skipped = []
    needs_llm = []

    for job in config.get("jobs", []):
        if not job.get("enabled", False):
            continue
        if args.only and job.get("name") != args.only:
            continue

        result = _run_one_job(job, now, state, env, dry_run=args.dry_run)

        name = job.get("name", "?")
        if result == "ok":
            executed.append(name)
        elif result == "failed":
            failed.append(name)
        elif result == "skipped_needs_llm":
            needs_llm.append(name)
        else:
            skipped.append(name)

    save_state(state)

    if executed or failed or needs_llm:
        log.info(
            f"Summary: {len(executed)} executed, {len(failed)} failed, "
            f"{len(skipped)} skipped, {len(needs_llm)} need LLM"
        )
        if failed:
            log.warning(f"Failed jobs: {', '.join(failed)}")
        if needs_llm:
            log.warning(f"Jobs needing LLM (skipped cleanly): {', '.join(needs_llm)}")

    return 0 if not failed else 1


def cmd_status(args) -> int:
    """Print one-line status per configured job."""
    try:
        with open(JOBS_CONFIG) as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to load jobs.json: {e}")
        return 1

    state = load_state()
    jobs_state = state.get("jobs", {})

    print(f"{'JOB':<28}  {'SCHEDULE':<14}  {'ENABLED':<8}  "
          f"{'LAST RUN (UTC)':<19}  {'STATUS':<22}")
    print("-" * 100)
    for job in config.get("jobs", []):
        name = job.get("name", "?")
        sched = job.get("schedule", {}).get("expr", "?")
        enabled = "yes" if job.get("enabled") else "no"
        js = jobs_state.get(name, {})
        last = (js.get("last_run_iso") or js.get("last_run_ts") or "never")[:19]
        status_str = js.get("status") or ("ok" if js.get("success") else "—")
        print(f"{name:<28}  {sched:<14}  {enabled:<8}  {last:<19}  {status_str:<22}")
    return 0


def cmd_run(args) -> int:
    """Force-run a single job NOW, ignoring its schedule."""
    now = datetime.now(timezone.utc)
    try:
        with open(JOBS_CONFIG) as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to load jobs.json: {e}")
        return 1

    target = None
    for job in config.get("jobs", []):
        if job.get("name") == args.name:
            target = job
            break
    if not target:
        print(f"Unknown job: {args.name}")
        return 2

    state = load_state()
    state.setdefault("jobs", {})
    env = load_env_file()

    result = _run_one_job(target, now, state, env, dry_run=args.dry_run, force=True)
    save_state(state)
    print(f"{args.name}: {result}")
    return 0 if result == "ok" else 1


def cmd_list(args) -> int:
    """List every job in jobs.json with its schedule and command preview."""
    try:
        with open(JOBS_CONFIG) as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to load jobs.json: {e}")
        return 1
    for job in config.get("jobs", []):
        name = job.get("name", "?")
        sched = job.get("schedule", {}).get("expr", "?")
        enabled = "✓" if job.get("enabled") else "✗"
        msg = (job.get("payload", {}).get("message", "") or "")
        cmd_preview = extract_shell_command(msg)
        if cmd_preview:
            preview = cmd_preview[:80] + ("…" if len(cmd_preview) > 80 else "")
        else:
            preview = "(needs LLM — no shell content)"
        print(f"{enabled} {name:<28} {sched:<14} {preview}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw cron-job executor (system-cron-driven, replaces broken built-in scheduler)."
    )
    sub = parser.add_subparsers(dest="cmd")

    p_tick = sub.add_parser("tick", help="Run one scheduler tick (default; cron calls this every minute).")
    p_tick.add_argument("--dry-run", action="store_true", help="Match schedules but don't actually exec.")
    p_tick.add_argument("--only", help="Limit this tick to one job name.")

    sub.add_parser("status", help="Print last-run status per job.")
    sub.add_parser("list", help="List jobs with their schedule + extracted shell command preview.")

    p_run = sub.add_parser("run", help="Force-run one job NOW, ignoring its schedule.")
    p_run.add_argument("name", help="Job name from jobs.json.")
    p_run.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    # Default to 'tick' when called without args (preserves cron compatibility)
    if not args.cmd:
        args.cmd = "tick"
        args.dry_run = False
        args.only = None

    if args.cmd == "tick":
        return cmd_tick(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
