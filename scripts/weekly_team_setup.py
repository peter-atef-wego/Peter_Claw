#!/usr/bin/env python3
"""
weekly_team_setup.py — OpenClaw cron job for the IAX team weekly update flow.

Two modes (selected by CLI arg):
  python3 scripts/weekly_team_setup.py monday   → create 4 Jira weekly-update tickets
  python3 scripts/weekly_team_setup.py friday   → post Slack reminder with ticket links

Tokens are read from env (sourced from /home/openclaw/.openclaw/cron/openclaw.env):
  JIRA_API_TOKEN, JIRA_EMAIL, SLACK_BOT_TOKEN

Ticket keys created on Monday are persisted to memory/state/weekly_team_issues.json
inside this repo (NOT /tmp/) so they survive container restarts and the Friday
job can find them.
"""

import json
import logging
import os
import sys
import base64
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

JIRA_BASE_URL = "https://api.atlassian.com/ex/jira/a7e53b72-ded0-45e3-8d7c-fd3573f46f1d/rest/api/3"
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "nikhil@wego.com")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN_NETSUITE_CHAMPION")
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK") or os.environ.get("SLACK_WEBHOOK_ALPHABOT_MASTERS")
# Hardcoded: this script ONLY posts to #alphabot-masters. The env var name
# contains "NETSUITE" for legacy reasons — it's the team's shared Slack bot,
# not a NetSuite-only bot. Never broaden this constant without explicit ask.
SLACK_CHANNEL = "C08T81REV6Y"  # #alphabot-masters

DUBAI_TZ = ZoneInfo("Asia/Dubai")

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "memory" / "state"
STATE_FILE = STATE_DIR / "weekly_team_issues.json"

# ─────────────────────────────────────────────
# TEAM
# ─────────────────────────────────────────────

IAX_EPIC_KEY = "IAX-454"
NDS_EPIC_KEY = "NDS-67"

MEMBERS = [
    {
        "name": "Ayush Raj",
        "jira_id": "712020:4c7d6ace-7df0-46e7-bd53-60cb3cbd4b58",
        "slack_id": "U01KSFH6WPK",
        "project": "IAX",
        "issue_type": "Weekly Update",
    },
    {
        "name": "Likith",
        "jira_id": "712020:91ee1a0b-3411-46c7-a621-ca78ef29f4e1",
        "slack_id": "U07GRT0PLSK",
        "project": "IAX",
        "issue_type": "Weekly Update",
    },
    {
        "name": "Peter Atef",
        "jira_id": "712020:436280da-892e-44cf-ac47-0527ccae163d",
        "slack_id": "U0A05CNQQ07",
        "project": "IAX",
        "issue_type": "Weekly Update",
    },
    {
        "name": "Akansha",
        "jira_id": "712020:5eace571-0f21-495f-a304-0511d95efb41",
        "slack_id": "U0AGL8T9H5J",
        "project": "NDS",
        "issue_type": "Task",
    },
]

JIRA_DESCRIPTION_ADF = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "Team members: Add your weekly update as a COMMENT below using this format.",
                }
            ],
        },
        {
            "type": "orderedList",
            "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Completed This Week"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "In Progress"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Blockers"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Key Impact / Results"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Next Week Focus (if you are not sure then lets discuss on Monday)"}]}]},
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "Please don't forget to add your task link for each task in this update.",
                }
            ],
        },
    ],
}

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("weekly_team_setup")


def _require_env() -> None:
    missing = [k for k, v in {"JIRA_API_TOKEN": JIRA_API_TOKEN, "SLACK_BOT_TOKEN_NETSUITE_CHAMPION": SLACK_BOT_TOKEN}.items() if not v]
    if missing:
        log.error(f"Missing env vars: {missing}. Source /home/openclaw/.openclaw/cron/openclaw.env first.")
        sys.exit(2)


def get_week_label() -> str:
    today = datetime.now(DUBAI_TZ)
    monday = today - timedelta(days=today.weekday())
    # strftime %-d doesn't work on all systems; use %d and strip leading 0
    date_str = monday.strftime("%d %B %Y").lstrip('0')
    return date_str


# ─────────────────────────────────────────────
# JIRA (stdlib urllib)
# ─────────────────────────────────────────────

def _jira_auth_header() -> str:
    """Return Basic auth header for Jira."""
    creds = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    encoded = base64.b64encode(creds.encode()).decode()
    return f"Basic {encoded}"


def create_jira_issue(member: dict, week_label: str) -> dict | None:
    summary = f"Weekly Team Update - Week of {week_label} — {member['name']}"
    payload = {
        "fields": {
            "project": {"key": member["project"]},
            "issuetype": {"name": member["issue_type"]},
            "summary": summary,
            "description": JIRA_DESCRIPTION_ADF,
            "assignee": {"accountId": member["jira_id"]},
        }
    }
    if member["project"] == "IAX":
        payload["fields"]["parent"] = {"key": IAX_EPIC_KEY}
    elif member["project"] == "NDS":
        payload["fields"]["parent"] = {"key": NDS_EPIC_KEY}

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{JIRA_BASE_URL}/issue",
        data=body,
        headers={
            "Authorization": _jira_auth_header(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 201:
                issue = json.loads(resp.read().decode())
                log.info(f"Created {issue['key']} for {member['name']}")
                return issue
            else:
                log.error(f"Failed to create ticket for {member['name']}: {resp.status}")
                return None
    except urllib.error.HTTPError as e:
        log.error(f"Jira HTTP error for {member['name']}: {e.code} {e.read().decode()}")
        return None
    except Exception as e:
        log.error(f"Error creating ticket for {member['name']}: {e}")
        return None


# ─────────────────────────────────────────────
# SLACK (using Webhook)
# ─────────────────────────────────────────────

def send_slack_reminder(created_issues: list[dict]) -> None:
    week_label = get_week_label()

    if created_issues:
        lines = []
        for issue in created_issues:
            m = issue["member"]
            url = f"https://wegomushi.atlassian.net/browse/{issue['key']}"
            lines.append(f"<{url}|{issue['key']} • {m['name']}>")
        ticket_block = "\n".join(lines)
    else:
        ticket_block = "_(no ticket links found — Monday job may have failed; please add update on your latest weekly ticket)_"

    message = (
        f"*Weekly Update Due — Week of {week_label}*\n\n"
        f"Team, please post your weekly updates in your respective tickets:\n\n"
        f"{ticket_block}\n\n"
        "Please include:\n"
        "• What you shipped this week\n"
        "• Blockers & what you need\n"
        "• What's next\n\n"
        "Thanks!"
    )

    # Try webhook first, fall back to token-based API
    if SLACK_WEBHOOK:
        _send_via_webhook(message)
    else:
        log.warning("SLACK_WEBHOOK not set; cannot send message")
        sys.exit(1)


def _send_via_webhook(message: str) -> None:
    """Send message via Slack webhook."""
    payload = json.dumps({"text": message}).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                log.info("Slack reminder sent to #alphabot-masters")
            else:
                log.error(f"Slack webhook returned {resp.status}")
                sys.exit(1)
    except Exception as e:
        log.error(f"Slack webhook error: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

def save_issues(issues: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w") as f:
        json.dump({"week_label": get_week_label(), "issues": issues}, f, indent=2)
    log.info(f"Saved {len(issues)} issue keys to {STATE_FILE}")


def load_issues() -> list[dict]:
    if not STATE_FILE.exists():
        log.warning(f"No state file at {STATE_FILE} — Friday reminder will send without ticket links.")
        return []
    with STATE_FILE.open() as f:
        return json.load(f).get("issues", [])


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def run_monday() -> None:
    _require_env()
    week_label = get_week_label()
    log.info(f"Monday job — week of {week_label}")
    created = []
    for member in MEMBERS:
        issue = create_jira_issue(member, week_label)
        if issue:
            created.append({
                "member": member,
                "key": issue["key"],
                "project": member["project"],
                "url": f"https://wegomushi.atlassian.net/browse/{issue['key']}",
            })
    save_issues(created)
    log.info(f"Monday done — {len(created)}/{len(MEMBERS)} tickets created")
    if len(created) != len(MEMBERS):
        sys.exit(1)


def run_friday() -> None:
    _require_env()
    log.info("Friday job — sending Slack reminder")
    issues = load_issues()
    send_slack_reminder(issues)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("monday", "friday"):
        print("Usage: python3 scripts/weekly_team_setup.py monday|friday", file=sys.stderr)
        sys.exit(2)
    {"monday": run_monday, "friday": run_friday}[sys.argv[1]]()


if __name__ == "__main__":
    main()
