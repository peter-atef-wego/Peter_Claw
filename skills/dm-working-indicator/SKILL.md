---
name: DM Working Indicator
description: "Status: OpenClaw Slack integration does not yet support bot activity status. Feature disabled pending platform support."
applies_to: Slack direct messages (chat_type=direct)
activated: 2026-06-09
status: PENDING PLATFORM SUPPORT
---

# DM Working Indicator — Status

## Current Status

**NOT YET WORKING.** OpenClaw's Slack `message` tool does not yet expose bot activity status API.

The `activityType` and `activityState` parameters are accepted but not applied by the Slack integration. This is a platform limitation, not a bug in the skill.

**Waiting on:** OpenClaw gateway enhancement to support setting bot presence/status via the message tool.

---

## What We Wanted

When you send a complex query in DM:
1. Set my bot status to `"Finding answers…"`
2. Do the work
3. Send response
4. Clear status

This would appear on your profile while I'm thinking, giving you visual confirmation I'm actively processing.

---

## Workaround Until Then

For now:
- You send a query
- I process it (no visual indicator yet)
- You get a response with tier signature (`:dart: *L1 (Sonnet)*`)
- The tier signature proves I actually ran

Not ideal, but honest.

---

## When This Is Enabled

The skill will be updated to include implementation details and examples once OpenClaw's Slack plugin supports bot activity status.

Track this as a platform feature request: "Slack bot activity status via message tool parameters"
