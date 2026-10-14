#!/usr/bin/env python3
"""
netsuite_slack_bridge.py — Wrapper for NetSuite operations that sends Slack confirmations.

Usage:
  python netsuite_slack_bridge.py create employee '{"firstname":"Nova","lastname":"Test"}' [slack_channel_id] [slack_thread_id]
  python netsuite_slack_bridge.py update vendor 12345 '{"entityid":"NEW-ID"}' [slack_channel_id]

This script:
1. Calls the MCP tool via the netsuite_mcp_server
2. Logs the result
3. Posts a confirmation/error message to Slack (if channel provided)
"""

import sys
import json
import os
import subprocess
from datetime import datetime

def get_slack_token():
    """Get Slack bot token from env."""
    return os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_TOKEN")

def send_slack_message(channel, message, thread_ts=None, blocks=None):
    """Send a message to Slack."""
    token = get_slack_token()
    if not token:
        print("[WARN] SLACK_BOT_TOKEN not set; skipping Slack notification")
        return None
    
    payload = {
        "channel": channel,
        "text": message,
    }
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    
    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "https://slack.com/api/chat.postMessage"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    try:
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            return resp.get("ts")
        else:
            print(f"[WARN] Slack error: {resp.get('error')}")
            return None
    except:
        print(f"[WARN] Failed to parse Slack response: {result.stdout[:200]}")
        return None

def call_netsuite_tool(operation, record_type, record_id_or_body, second_body=None):
    """Call the MCP tool directly."""
    # Build the tool call
    if operation == "create":
        tool_name = "create_record"
        arguments = {"record_type": record_type, "body": json.loads(record_id_or_body)}
    elif operation == "update":
        tool_name = "update_record"
        arguments = {
            "record_type": record_type,
            "record_id": record_id_or_body,
            "body": json.loads(second_body)
        }
    elif operation == "read":
        tool_name = "read_record"
        arguments = {"record_type": record_type, "record_id": record_id_or_body}
    else:
        raise ValueError(f"Unknown operation: {operation}")
    
    # Call the script directly (since MCP is async via stdio)
    # For now, we'll return the arguments so the caller can invoke the tool
    return tool_name, arguments

def format_slack_blocks(operation, record_type, result):
    """Format a Slack block message for the result."""
    if result.get("ok"):
        if operation == "create":
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"\u2705 **{record_type.title()} Created Successfully**\n\n*Internal ID:* `{result['internal_id']}`"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{result.get('sandbox_url', '#')}|Open in NetSuite>"
                    }
                }
            ]
        elif operation == "update":
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"\u2705 **{record_type.title()} Updated Successfully**\n\n*ID:* `{result['internal_id']}`"
                    }
                }
            ]
    else:
        error_detail = result.get("error", {})
        if isinstance(error_detail, dict):
            if "o:errorDetails" in error_detail:
                msg = error_detail["o:errorDetails"][0].get("detail", str(error_detail))
            else:
                msg = error_detail.get("detail", str(error_detail))
        else:
            msg = str(error_detail)
        
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"\u274c **{record_type.title()} Creation Failed**\n\n\`\`\`{msg}\`\`\`"
                }
            }
        ]

def main():
    if len(sys.argv) < 3:
        print("Usage: netsuite_slack_bridge.py <create|update|read> <record_type> <record_id_or_body> [second_body] [slack_channel] [thread_ts]")
        sys.exit(1)
    
    operation = sys.argv[1]
    record_type = sys.argv[2]
    record_id_or_body = sys.argv[3]
    second_body = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("C") else None
    slack_channel = sys.argv[5] if len(sys.argv) > 5 else (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4].startswith("C") else None)
    thread_ts = sys.argv[6] if len(sys.argv) > 6 else None
    
    # Log the operation
    timestamp = datetime.utcnow().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "operation": operation,
        "record_type": record_type,
        "record_id": record_id_or_body if operation != "create" else "TBD"
    }
    
    # Call the tool
    tool_name, arguments = call_netsuite_tool(operation, record_type, record_id_or_body, second_body)
    
    # For now, print the log entry
    print(json.dumps(log_entry))
    print(f"Tool: {tool_name}, Args: {json.dumps(arguments)}")

if __name__ == "__main__":
    main()
