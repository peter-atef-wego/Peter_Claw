#!/usr/bin/env python3
"""
weekly_team_runner.py — Wrapper that injects env vars from OpenClaw runtime, then runs weekly_team_setup.py

Called by cron_daemon, which doesn't have OpenClaw env vars loaded.
This script reads them from the gateway/runtime and passes them down.

Usage:
  python3 scripts/weekly_team_runner.py monday
  python3 scripts/weekly_team_runner.py friday
"""

import os
import subprocess
import sys

# Read current process env (gateway injects these on startup)
jira_token = os.environ.get("JIRA_API_TOKEN")
jira_email = os.environ.get("JIRA_EMAIL")
slack_bot = os.environ.get("SLACK_BOT_TOKEN_NETSUITE_CHAMPION") or os.environ.get("SLACK_BOT_TOKEN")
slack_webhook = os.environ.get("SLACK_WEBHOOK")

if not jira_token or not jira_email:
    print("ERROR: JIRA_API_TOKEN or JIRA_EMAIL not found in environment", file=sys.stderr)
    sys.exit(1)

# Prepare env for subprocess
env = os.environ.copy()
env["JIRA_API_TOKEN"] = jira_token
env["JIRA_EMAIL"] = jira_email
if slack_bot:
    env["SLACK_BOT_TOKEN_NETSUITE_CHAMPION"] = slack_bot
if slack_webhook:
    env["SLACK_WEBHOOK"] = slack_webhook

cmd = [
    "python3",
    "/home/openclaw/.openclaw/workspace/scripts/weekly_team_setup.py",
    sys.argv[1] if len(sys.argv) > 1 else "monday",
]

result = subprocess.run(cmd, env=env, cwd="/home/openclaw/.openclaw/workspace")
sys.exit(result.returncode)
