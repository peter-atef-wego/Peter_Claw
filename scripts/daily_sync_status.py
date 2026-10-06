#!/usr/bin/env python3
"""
daily_sync_status.py — Posts cron job run status to Peter's Slack DM.
Runs via cron at 19:05 UTC (11:05 PM DXB) daily.

Reads executor_state.json for last run times/statuses,
then sends a formatted Slack message to Peter's DM.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
WORKSPACE_DIR = Path("/home/openclaw/.openclaw/workspace")
STATE_FILE = WORKSPACE_DIR / "cron" / "executor_state.json"
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN_NETSUITE_CHAMPION")
NIK_USER_ID = "PETER_SLACK_USER_ID_TODO"

JOBS_TO_REPORT = [
    "openclaw_nova_mirror",
    "nova_claw_pull_sync",
    "weekly_team_monday",
    "weekly_team_friday",
]

SCHEDULES = {
    "openclaw_nova_mirror": "Sun 7:30 AM DXB",
    "nova_claw_pull_sync": "Hourly :05 DXB",
    "weekly_team_monday": "Mon 9:00 AM DXB",
    "weekly_team_friday": "Fri 9:00 AM DXB",
}

STATUS_EMOJI = {
    "ok": "✅",
    "success": "✅",
    "skipped_needs_llm": "⚠️",
    "failed": "❌",
    "error": "❌",
    "timeout": "⏱️",
    "reset": "🔄",
    "never": "⚪",
}


def load_state():
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def format_last_run(job_state: dict) -> str:
    iso = job_state.get("last_run_iso") or job_state.get("last_run_ts")
    if not iso or iso == "never":
        return "never"
    try:
        # Parse ISO string
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        # Convert to DXB (UTC+4)
        from datetime import timedelta
        dxb = dt.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=4))
        )
        return dxb.strftime("%b %d %H:%M DXB")
    except Exception:
        return str(iso)[:16]


def build_message(state: dict) -> dict:
    now_dxb = datetime.now(timezone.utc)
    from datetime import timedelta
    dxb_tz = timezone(timedelta(hours=4))
    now_str = datetime.now(dxb_tz).strftime("%b %d %H:%M DXB")

    rows = []
    has_failure = False

    # executor_state.json has two layers:
    # - top-level keys: old format with last_run epoch + last_status (stale "reset")
    # - state["jobs"]: new format with full ISO timestamps + real statuses
    # Always prefer state["jobs"] for accurate data.
    jobs_state = state.get("jobs", {})

    for job in JOBS_TO_REPORT:
        job_data = jobs_state.get(job, {})
        status = job_data.get("status", "never")
        last_run = format_last_run(job_data)
        detail = job_data.get("detail", "")
        emoji = STATUS_EMOJI.get(status, "❓")
        sched = SCHEDULES.get(job, "?")

        if status in ("failed", "error", "timeout", "skipped_needs_llm"):
            has_failure = True

        last_run_label = last_run if last_run != "never" else "never ran"
        row = f"{emoji} *{job}*  last: `{last_run_label}`  _{sched}_"
        if detail and status not in ("ok", "success", "reset", "never"):
            row += f"\n    ↳ {detail}"
        rows.append(row)

    header = f"*📊 Daily Cron Status — {now_str}*"
    body = "\n".join(rows)
    footer = "✅ All good" if not has_failure else "⚠️ Some jobs need attention"

    text = f"{header}\n\n{body}\n\n{footer}"
    return {"text": text}


def get_dm_channel(user_id: str) -> str:
    url = "https://slack.com/api/conversations.open"
    payload = json.dumps({"users": user_id}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"conversations.open failed: {data.get('error')}")
    return data["channel"]["id"]


def post_message(channel: str, text: str):
    url = "https://slack.com/api/chat.postMessage"
    payload = json.dumps({"channel": channel, "text": text, "mrkdwn": True}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"chat.postMessage failed: {data.get('error')}")
    return data


def main():
    if not SLACK_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    msg = build_message(state)

    # Open DM with Nik
    channel = get_dm_channel(NIK_USER_ID)
    result = post_message(channel, msg["text"])
    print(f"✅ Daily sync status posted to {channel} (ts={result.get('ts')})")


if __name__ == "__main__":
    main()
