#!/usr/bin/env python3
"""
weekly_team_wrapper.py — Wrapper to source env and execute weekly team setup.

This wrapper ensures:
1. Environment variables from openclaw.env are loaded
2. The weekly_team_setup.py script executes properly
3. Errors are logged to a dedicated log file

Usage:
  python3 scripts/weekly_team_wrapper.py monday
  python3 scripts/weekly_team_wrapper.py friday
"""

import os
import sys
import logging
from pathlib import Path
import subprocess

# Setup logging
LOG_DIR = Path("/home/openclaw/.openclaw/workspace/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "weekly_team_wrapper.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("weekly_team_wrapper")

# Load env file
ENV_FILE = Path("/home/openclaw/.openclaw/cron/openclock.env")
if ENV_FILE.exists():
    log.info(f"Loading env from {ENV_FILE}")
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip("'\"")
                os.environ[key.strip()] = value
                log.debug(f"Set {key.strip()}={value[:20]}...")
else:
    log.warning(f"Env file not found at {ENV_FILE}")

# Execute the weekly team setup
if len(sys.argv) != 2 or sys.argv[1] not in ("monday", "friday"):
    log.error("Usage: weekly_team_wrapper.py monday|friday")
    sys.exit(2)

mode = sys.argv[1]
script = Path("/home/openclaw/.openclaw/workspace/scripts/weekly_team_setup.py")

log.info(f"Executing weekly_team_setup.py {mode}")
try:
    result = subprocess.run(
        ["python3", str(script), mode],
        cwd="/home/openclaw/.openclaw/workspace",
        timeout=300,
        check=False,
    )
    if result.returncode == 0:
        log.info(f"weekly_team_setup.py {mode} completed successfully")
        sys.exit(0)
    else:
        log.error(f"weekly_team_setup.py {mode} failed with exit code {result.returncode}")
        sys.exit(1)
except subprocess.TimeoutExpired:
    log.error(f"weekly_team_setup.py {mode} timed out")
    sys.exit(1)
except Exception as e:
    log.error(f"Error executing weekly_team_setup.py: {e}")
    sys.exit(1)
