#!/usr/bin/env python3
"""
ensure_daemon.py — Make sure cron_daemon.py is running. Idempotent.

Called from AGENTS.md step 8 on every session start.
Survives container restarts: if daemon died, this resurrects it.

Usage:
  python3 scripts/cron/ensure_daemon.py            # ensure running (default)
  python3 scripts/cron/ensure_daemon.py --status   # report only, don't start
  python3 scripts/cron/ensure_daemon.py --restart  # kill + restart
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR  = Path(__file__).resolve().parent
WORKSPACE   = SCRIPT_DIR.parent.parent
DAEMON      = WORKSPACE / "scripts" / "cron_daemon.py"
PID_FILE    = WORKSPACE / "cron" / "daemon.pid"
LOG_FILE    = WORKSPACE / "logs" / "cron.log"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True  # exists, just can't signal


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def _find_daemon() -> int | None:
    # 1. Check PID file
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return pid

    # 2. Fallback: pgrep
    try:
        r = subprocess.run(
            ["pgrep", "-f", r"python[0-9.]* .*cron_daemon\.py"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            pid = int(r.stdout.strip().split("\n")[0])
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(str(pid))
            return pid
    except Exception:
        pass

    return None


def _start() -> int | None:
    if not DAEMON.exists():
        print(f"ERROR: {DAEMON} not found", file=sys.stderr)
        return None

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a") as log:
        log.write(f"\n--- ensure_daemon: start at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ---\n")
        proc = subprocess.Popen(
            ["python3", str(DAEMON)],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(WORKSPACE),
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))
    time.sleep(0.5)

    if _pid_alive(proc.pid):
        return proc.pid
    return None


def _stop() -> None:
    pid = _find_daemon()
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not _pid_alive(pid):
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def cmd_ensure() -> int:
    pid = _find_daemon()
    if pid:
        print(f"cron_daemon running (PID {pid})")
        return 0
    pid = _start()
    if pid:
        print(f"cron_daemon started (PID {pid})")
        return 0
    print("ERROR: failed to start cron_daemon", file=sys.stderr)
    return 1


def cmd_status() -> int:
    pid = _find_daemon()
    if pid:
        print(f"running: PID {pid}")
        return 0
    print("not running")
    return 1


def cmd_restart() -> int:
    _stop()
    return cmd_ensure()


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--status",  action="store_true")
    g.add_argument("--restart", action="store_true")
    args = p.parse_args()

    if args.status:
        return cmd_status()
    if args.restart:
        return cmd_restart()
    return cmd_ensure()


if __name__ == "__main__":
    sys.exit(main())
