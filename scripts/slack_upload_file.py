#!/usr/bin/env python3
"""Upload a local file to Slack as an attachment.

Used after `export_suiteql_to_csv` / `run_standard_report` so users in
Slack actually get the CSV — instead of a useless `/tmp/...` path they
can't access. Slack's MCP doesn't expose file upload, so we call the
Web API directly via stdlib urllib (no extra deps).

Auth: reads SLACK_BOT_TOKEN_NETSUITE_CHAMPION env var (per the standard
openclaw.env). If that's missing, returns a clean error — never crashes.

Usage from bash (how the agent calls it):
    python3 scripts/slack_upload_file.py \\
        --file /tmp/netsuite_exports/foo.csv \\
        --channel C08LZTG1YR5 \\
        --thread-ts 1700000000.123 \\
        --comment "Here's the AR aging report"

Returns JSON to stdout:
    {"ok": true, "file_id": "F123", "permalink": "https://wegoinc.slack.com/files/..."}
or:
    {"ok": false, "error": "..."}

Exit code: 0 on success, 1 on any failure.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Optional


SLACK_API = "https://slack.com/api"

# Env-var names where the Slack bot token might be stored, in priority order.
# Different parts of the codebase use different names — try them all.
SLACK_TOKEN_ENV_NAMES = (
    "SLACK_BOT_TOKEN_NETSUITE_CHAMPION",
    "SLACK_BOT_TOKEN",
    "SLACK_TOKEN",
    "SLACK_API_TOKEN",
)

# Files we'll source as a fallback if the token isn't in os.environ.
# OpenClaw's cron env file is the most common place tokens live.
SLACK_ENV_FILE_CANDIDATES = (
    "/home/openclaw/.openclaw/cron/openclaw.env",
    "/home/openclaw/.openclaw/cron/.env",
)


def _resolve_token():
    """Find the Slack token via three paths, in order:
      1. os.environ (any of the known var names)
      2. Parsing /home/openclaw/.openclaw/cron/openclaw.env directly
      3. Same env file but the alt names
    Returns (token, source_description) or (None, list_of_paths_checked).
    """
    checked = []
    # 1. Already-exported env vars
    for name in SLACK_TOKEN_ENV_NAMES:
        checked.append(f"env:{name}")
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip(), f"os.environ[{name}]"

    # 2. Fallback: source the env file directly. The MCP server runs as its
    # own process; if it wasn't started with `source openclaw.env`, the cron
    # tokens are on disk but not in os.environ. Read them directly.
    for env_path in SLACK_ENV_FILE_CANDIDATES:
        checked.append(f"file:{env_path}")
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:]
                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key in SLACK_TOKEN_ENV_NAMES and val:
                        return val, f"{env_path}:{key}"
        except OSError:
            continue

    return None, checked


def _slack_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _slack_post_form(url: str, data: dict, token: str) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _ts_is_valid(ts: Optional[str]) -> bool:
    """A real Slack ts looks like '1751380930.426149' — epoch . microseconds."""
    if not ts or "." not in ts:
        return False
    whole, frac = ts.split(".", 1)
    return whole.isdigit() and frac.isdigit() and len(whole) >= 6


def _get_bot_user_id(token: str) -> Optional[str]:
    """The bot's own Slack user id, so we can skip its messages in history."""
    try:
        resp = _slack_get(f"{SLACK_API}/auth.test", token)
        return resp.get("user_id") if resp.get("ok") else None
    except Exception:
        return None


def _resolve_thread_parent(channel: str, provided_ts: Optional[str],
                           token: str) -> Optional[str]:
    """Return the TRUE thread-parent ts for a channel upload.

    Hosts differ in what they hand the agent: OpenClaw passed the real Slack ts;
    Hermes may redact it ('[PHONE].426149') OR pass a ts that isn't the actual
    parent — either way the file lands in the channel root instead of the thread.
    We resolve it ourselves with a single conversations.history call:

      1. provided ts is valid AND present in recent history  -> trust it.
      2. provided ts is redacted but its '.NNNNNN' suffix matches a message
         -> use that message's real ts (recovers Hermes' [PHONE] masking).
      3. otherwise -> the most recent real (non-bot, top-level) message, which in
         a request->file-reply flow IS the triggering message the user asked in.

    Falls back to provided_ts if history is unavailable (e.g. missing
    channels:history / groups:history scope). Requires the bot to be in-channel.
    """
    try:
        url = (f"{SLACK_API}/conversations.history?channel="
               f"{urllib.parse.quote(channel)}&limit=100")
        resp = _slack_get(url, token)
    except Exception as e:
        print(f"[slack_upload] parent-resolve: history call failed: {e}", file=sys.stderr)
        return provided_ts
    if not resp.get("ok"):
        print(f"[slack_upload] parent-resolve: history not ok: {resp.get('error')!r} "
              f"— bot needs channels:history/groups:history scope + membership",
              file=sys.stderr)
        return provided_ts

    messages = resp.get("messages", [])
    ts_set = {m.get("ts", "") for m in messages}

    # 1. trust a valid ts that actually exists in the channel
    if _ts_is_valid(provided_ts) and provided_ts in ts_set:
        return provided_ts

    # 2. redaction case: recover via the surviving fractional suffix
    if provided_ts and "." in provided_ts:
        suffix = provided_ts.rsplit(".", 1)[1]
        if suffix.isdigit():
            for m in messages:
                if m.get("ts", "").endswith("." + suffix):
                    print(f"[slack_upload] parent-resolve: recovered {m['ts']} "
                          f"via suffix .{suffix}", file=sys.stderr)
                    return m["ts"]

    # 3. fall back to the most recent real human, top-level message
    bot_id = _get_bot_user_id(token)
    for m in messages:  # history is newest-first
        if m.get("subtype"):                      # skip joins / bot_message / etc.
            continue
        if bot_id and m.get("user") == bot_id:    # skip the bot's own messages
            continue
        parent = m.get("ts")
        print(f"[slack_upload] parent-resolve: using latest human message {parent}",
              file=sys.stderr)
        return parent or provided_ts

    return provided_ts


def upload_file_to_slack(file_path: str, channel: str,
                        thread_ts: Optional[str] = None,
                        reply_to_id: Optional[str] = None,
                        message_id: Optional[str] = None,
                        comment: Optional[str] = None,
                        title: Optional[str] = None) -> dict:
    """Three-step upload using Slack's modern files.uploadV2 flow:
      1. files.getUploadURLExternal — get a one-time upload URL + file_id
      2. POST the file bytes to that URL
      3. files.completeUploadExternal — finalise + attach to channel/thread

    Returns {ok: True, file_id, permalink} on success, or
    {ok: False, error} on any failure. Never raises.

    THREAD RESOLUTION (2026-06-26 — fixes the persistent "file outside thread"
    bug that survived PR #77):
      OpenClaw exposes inbound Slack metadata as `message_id` / `reply_to_id`,
      but Slack's API expects `thread_ts`. These are the same underlying VALUE
      (a Slack message ts) under different field names — the agent's been
      passing nothing because no name matched. This function now accepts ALL
      three names and resolves internally, in this priority order:

         thread_ts  (highest — explicit override)
         reply_to_id  (the parent of an existing thread, or the message itself
                       if top-level — Slack treats these the same way for
                       posting a reply)
         message_id  (last fallback — the inbound message's own ts)

      Channel uploads (C/G prefix) still require ONE of these. DMs (D prefix)
      remain exempt — there's no thread concept in DMs.
    """
    # Resolve the thread parent ts from whichever field the caller provided.
    resolved_ts = thread_ts or reply_to_id or message_id

    # Pre-flight: enforce a parent ts for channel uploads BEFORE any Slack call.
    if channel and channel[0] in ("C", "G") and not resolved_ts:
        return {
            "ok": False,
            "error": "THREAD_TS_REQUIRED",
            "stage": "preflight",
            "message": (
                f"Channel uploads to {channel} need a thread parent ts so the "
                f"file lands inside the user's thread, not as a new top-level "
                f"channel message. Pass ONE of these from the inbound Slack "
                f"event (any of the three names works — the tool maps them): "
                f"`thread_ts`, `reply_to_id`, or `message_id`. OpenClaw normally "
                f"exposes these as `message_id` and `reply_to_id` in the inbound "
                f"metadata — pass whichever you have. DMs (channel id starts "
                f"with 'D') don't need this."
            ),
            "accepted_field_names": ["thread_ts", "reply_to_id", "message_id"],
        }

    # From here on, the rest of the function uses `resolved_ts` (may be None
    # for DMs, which is fine — Slack just posts to the DM channel root).
    thread_ts = resolved_ts

    token, source = _resolve_token()
    if not token:
        return {
            "ok": False,
            "error": (
                "Slack bot token not found. Checked: "
                + ", ".join(source)
                + ". Akansha to confirm one of these is set: "
                + ", ".join(SLACK_TOKEN_ENV_NAMES)
                + " (with files:write scope)."
            ),
            "stage": "auth",
            "checked": source,
        }

    # ── Resolve the TRUE thread parent (host-agnostic) ───────────────────────
    # The ts the agent passes can't be trusted across hosts: Hermes may redact it
    # ('[PHONE].426149') or hand over a ts that isn't the real parent, so the file
    # ends up in the channel root. Resolve the real parent from channel history.
    if channel and channel[0] in ("C", "G"):
        parent = _resolve_thread_parent(channel, thread_ts, token)
        if parent and parent != thread_ts:
            print(f"[slack_upload] thread parent {thread_ts!r} -> {parent}",
                  file=sys.stderr)
        if parent:
            thread_ts = parent

    if not os.path.exists(file_path):
        return {"ok": False,
                "error": f"file not found: {file_path}",
                "stage": "preflight"}

    size = os.path.getsize(file_path)
    if size == 0:
        return {"ok": False,
                "error": f"file is empty: {file_path}",
                "stage": "preflight"}
    fname = os.path.basename(file_path)

    # Step 1: Get external upload URL
    try:
        url = f"{SLACK_API}/files.getUploadURLExternal?" + urllib.parse.urlencode(
            {"filename": fname, "length": size}
        )
        r = _slack_get(url, token)
    except Exception as e:
        return {"ok": False, "error": f"getUploadURLExternal request failed: {e}",
                "stage": "get_upload_url"}
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "unknown"),
                "stage": "get_upload_url", "raw": r}

    upload_url = r["upload_url"]
    file_id = r["file_id"]

    # Step 2: PUT the file content
    try:
        with open(file_path, "rb") as f:
            body = f.read()
        req = urllib.request.Request(upload_url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status >= 300:
                return {"ok": False,
                        "error": f"file upload returned HTTP {resp.status}",
                        "stage": "upload"}
    except Exception as e:
        return {"ok": False, "error": f"file upload failed: {e}",
                "stage": "upload"}

    # Step 3: Complete the upload (attach to channel + optional thread)
    file_entry = {"id": file_id}
    if title:
        file_entry["title"] = title
    data = {
        "files": json.dumps([file_entry]),
        "channel_id": channel,
    }
    if thread_ts:
        data["thread_ts"] = thread_ts
    if comment:
        data["initial_comment"] = comment

    try:
        r = _slack_post_form(f"{SLACK_API}/files.completeUploadExternal", data, token)
    except Exception as e:
        return {"ok": False, "error": f"completeUploadExternal request failed: {e}",
                "stage": "complete"}
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "unknown"),
                "stage": "complete", "raw": r}

    files = r.get("files", [{}])
    first = files[0] if files else {}
    return {
        "ok": True,
        "file_id": first.get("id", file_id),
        "permalink": first.get("permalink"),
        "permalink_public": first.get("permalink_public"),
        "filename": fname,
        "size_bytes": size,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Upload a local file to Slack as an attachment."
    )
    parser.add_argument("--file", required=True, help="Absolute path to the file to upload.")
    parser.add_argument("--channel", required=True, help="Slack channel ID (e.g. C08LZTG1YR5).")
    parser.add_argument("--thread-ts",
                        help="Optional thread timestamp (post inside an existing thread).")
    parser.add_argument("--comment",
                        help="Optional message attached above the file in Slack.")
    parser.add_argument("--title",
                        help="Optional file title (defaults to the basename).")
    args = parser.parse_args()

    result = upload_file_to_slack(
        file_path=args.file,
        channel=args.channel,
        thread_ts=args.thread_ts,
        comment=args.comment,
        title=args.title,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
