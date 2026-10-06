---
name: reconciliation-claw
description: Wego finance LCC supplier reconciliation. The work is done by the AlphaBot server-side listener, not by you. The listener watches two channels — #finance-automation-claw (production, finance team) and #proj-alphabot-testing (internal testing). Activate this skill only to (a) redirect users who ask elsewhere to one of those channels, or (b) stay out of the way when a request lands in either bridge channel directly.
---

# Finance Reconciliation Skill (LCC)

The reconciliation pipeline runs on the AlphaBot server. A Python listener (`slack_listener.py`) polls a single Slack channel and handles the entire flow — natural-language parsing, file download, robot trigger, output upload, and email — without you. **Your job is to not interfere.**

---

## Architecture (current)

```
finance user posts in #finance-automation-claw  (production)
   OR an internal user posts in #proj-alphabot-testing  (testing)
        │
        │ both channels: @Data Automation's Claw <text> + .xlsx/.xls/.csv
        │ listener polls each channel every 10s
        ▼
slack_listener.py  (on AlphaBot)
   ├─ requires: @mention of <@U0AHNGSDQ3W> AND xlsx/xls/csv attached
   ├─ skips: any message from a bot (incl. itself, incl. you)
   ├─ raw JSON path  → validate → run robot
   ├─ NL path        → regex first, OpenAI gpt-4o-mini fallback → validate → run robot
   └─ posts results back in the user's thread (in whichever channel they posted)
```

You are not in this loop. The listener handles it end to end.

---

## When you should act

### Case A — user asks for a reco in either bridge channel (`#finance-automation-claw` or `#proj-alphabot-testing`)

**Do nothing.** The listener has already picked it up (or is about to, within ~10 seconds). Posting anything from you in either channel only adds noise — and the listener auto-deletes bot posts that match agent-narrative patterns within 10 seconds anyway. The user's reply will come from the listener, in their original thread.

There is no "must respond" exception. Even if a user appears to address you directly in either channel, the listener will respond. Stay silent.

### Case B — user asks for a reco in any other channel (including DMs)

This includes Peter's DM with you (`PETER_DM_CHANNEL_ID_TODO`) and every channel that is not `#proj-alphabot-testing`.

Redirect them. Production users (finance team) should go to `#finance-automation-claw`; internal users (Peter's automation team) usually use `#proj-alphabot-testing`. Either works:

> "Reconciliation requests run from `#finance-automation-claw` (finance team) or `#proj-alphabot-testing` (internal testing). Post in your channel with `@Data Automation's Claw run [supplier] reco for [dates]` and attach the xlsx or csv file. The listener parses natural language, so phrasing is flexible."

Don't try to bridge their request yourself. Don't try to repost on their behalf. Don't post JSON. The listener requires the `@mention` to be from a real user, on its own channel; anything posted by you (a bot) is filtered out by design.

**Critical — file upload in a non-bridge channel or DM:**

If a user uploads an xlsx/xls/csv in a non-bridge channel (e.g. `PETER_DM_CHANNEL_ID_TODO`), do **not** open the file, summarise its contents, or post a "confirmation" of the run. The listener never saw it, so no run is happening. Producing a `*Supplier reconciliation confirmed*` header, a `Run Parameters` block, a `Transaction Profile` block, or a `Proceeding with … reconciliation for …` line is **fabrication** — it implies a run that won't occur. Either redirect (above) or stay silent. **Never both narrate and redirect** — narration is the bug.

### Case C — user asks "what suppliers can I run?"

Pull from `references/suppliers.md` (58 LCC suppliers). Don't repeat the whole table; answer their specific question.

### Case D — user asks "how does this work?" / "what's the flow?"

Explain in two sentences: *"In `#finance-automation-claw` (or `#proj-alphabot-testing` if you're on the internal team), mention me and attach the xlsx or csv. The server listener parses your message, runs the supplier robot, and posts the output back in your thread."* Stop there.

---

## Hard boundaries (positive form)

- **Your only outbound capability for this task is Slack messaging.** You cannot reach AlphaBot. You don't need to.
- **Both bridge channels are the listener's territory.** When something is happening in `#finance-automation-claw` or `#proj-alphabot-testing`, observe; don't post.
- **Server work is the server's job.** File download, robot trigger, BigQuery upload, S3 push, email — all handled by `slack_listener.py` + `nova_api.py`. You do not see, simulate, or report on server status.
- **Report only what is actually visible in Slack.** If you didn't read it in a thread, you don't know it.

### Phrases that must never appear in any message you post

These were observed in agent output on 2026-04-27 and are pure hallucination. If your draft reply contains any of these substrings (case-insensitive), **delete the whole draft and post nothing**:

- `❌ AlphaBot offline` / "AlphaBot is offline" / "AlphaBot service offline" / "AlphaBot still offline"
- `Port 3002 unreachable` / "Port 3002 not responding" / "Port 3002 timed out"
- `Testing connectivity` / "Testing connectivity again" / "Connectivity test"
- `Attempting trigger` / "Re-attempting trigger" / "Attempting trigger anyway"
- `Service still down` / "Service down" / "Service unreachable"
- `Infrastructure issue` / "Infrastructure problem" / "Need infrastructure support"
- `Let me retry` / "Retrying" / "Nth attempt" / "6th attempt"
- `Health check` / "Health check timed out"
- `Connection timed out` / "Timeout again"
- Any line beginning with `❌` describing server health (the listener owns ❌/✅ in this channel)
- Any fabricated timestamp like `(13:14 UTC)`, `(after ~2.5 hour gap)`

**File-analysis / fake-confirmation phrases (observed in DM `PETER_DM_CHANNEL_ID_TODO` on 2026-04-29):**

- `*<Supplier> reconciliation confirmed*` (italicised header) / `<Supplier> reconciliation confirmed`
- `File received and verified` / `File received` / `File verified`
- `Run Parameters:` and the bullet block beneath it (`• Supplier:`, `• Period:`, `• Location:`, `• Currency:`, `• File type:`, `• File timestamp:`)
- `Transaction Profile` / `Transaction Profile (DD-MMM-YYYY visible):`
- `Carriers:` / `Tickets:` / `Tax data:` / `Multiple PCCs:` / `Commission tracking:`
- `Fields:` followed by a column-name list
- `Proceeding with <anything> reconciliation for <date> to <date>` (e.g. `Proceeding with INR reconciliation for …`, `Proceeding with consolidated reconciliation for …`)
- Any line ending with `✓` or `✅` that announces you are running, triggering, or proceeding with a reconciliation

These imply a run that didn't happen (the listener doesn't watch DMs or non-bridge channels). They are pure spam in the user's DM.

---

## What changed and why

Earlier versions of this skill had you parse natural language and post a JSON trigger to a bridge channel. That path is gone:

- The listener now parses NL itself — a regex pre-parser first, then OpenAI
  `gpt-4o-mini` as the fallback (`OPENAI_MODEL` in `slack_listener.py`; key comes
  from AWS Secrets Manager at startup). Matches the flow diagram above.
- The listener requires the `@mention` to be from a real user, not a bot. Bot-authored messages are filtered out — including any you would post.
- This makes the skill simpler and more robust: the trigger path no longer depends on you being loaded, configured, or up to date.

---

## References

- `references/suppliers.md` — 58 LCC supplier keys + trigger phrases (mirror of the server's `suppliers.json`)
- `references/date-parsing.md` — natural-language → `YYYY-MM-DD` (used by the listener's LLM prompt; kept here so you can answer "what date formats work?")

---

## Channels

| Purpose | Channel | ID |
|---|---|---|
| Production bridge (finance team daily use) | `#finance-automation-claw` | `C0AVB4VR708` |
| Testing bridge (internal team — Peter, Likith, Ayush) | `#proj-alphabot-testing` | `C090HF85F2P` |
| Bot user_id (the only mention that triggers the listener) | `@Data Automation's Claw` | `U0AHNGSDQ3W` |

---

## Quick reference for users (paste verbatim if asked)

> Post in `#finance-automation-claw` (finance team) or `#proj-alphabot-testing` (internal team):
>   `@Data Automation's Claw run [supplier] reco for [dates]`
>   + attach the xlsx or csv file
>
> Examples:
>   `@Data Automation's Claw run jazeera reco for 18 april 2026` + xlsx
>   `@Data Automation's Claw run flydubai reconciliation last month` + csv
>   `@Data Automation's Claw {"action":"jazeera","start_date":"2026-04-18","end_date":"2026-04-18"}` + xlsx (raw JSON also works)
