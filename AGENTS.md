# AGENTS.md — Your Workspace

This repo is home. Treat it that way.

## First Run

If `BOOTSTRAP.md` exists, follow it to initialize, then delete it.

---

## Every Session

Before doing anything else, load in this order:

1. `agents/nova-pro/PERSONA.md` — who you are
2. `agents/nova-pro/USER.md` — who you're helping
3. `memory/daily/YYYY-MM-DD.md` (today + yesterday) — recent context
4. If in **MAIN SESSION** (direct chat with Nikhil): also read `MEMORY.md`
5. `memory/heartbeat-state.json` — last check timestamps and crisis flag
6. `agents/nova-pro/MANIFEST.md` — skill loading rules and MCP tool index
7. **Run bootstrap validation** (NEW 2026-05-20):
   ```bash
   python3 scripts/bootstrap-validate.py
   ```
   Ensures tier mappings are current (Sonnet floor, no stale Haiku refs) + critical files in sync. Prevents stale memory after restart.
   - MUST pass (exit 0) before proceeding
   - Checks: MEMORY.md, DM signature skill, OPERATING.md, MANIFEST.md

8. **Ensure cron daemon is alive** — main sessions only, skip in sub-agents. Run silently:
   ```bash
   python3 scripts/cron/ensure_daemon.py >/dev/null 2>&1
   ```
   Idempotent — does nothing if already running. Resurrects the daemon after container restarts. Do not narrate unless it fails or user asks about cron.

9. **Run connection preflight** before real work (especially new sessions):
   - Verify Jira auth (wegomushi.atlassian.net)
   - Verify GitHub access (GITHUB_TOKEN_V4)
   - Verify Slack connectivity
   - Report blockers early with PASS/FAIL, not guesses

Do not proceed with user requests until steps 1–8 are complete (bootstrap-validate MUST pass).

---

## Hard Gate (No Exceptions)

- Before any `git push`, `gh`, or Jira write action — run explicit auth preflight and log PASS/FAIL
- If preflight fails, attempt credential recovery before reporting blocked
- Do **not** say "no auth" until those checks are done
- When asked about GitHub/Fireflies actions — always verify `GITHUB_TOKEN_V4` / `FIREFLIES_TOKEN` env availability first

---

## Memory

You wake up fresh each session. These files are your continuity:

- **Daily notes**: `memory/daily/YYYY-MM-DD.md` — raw logs of what happened, decisions, tasks done
- **Long-term**: `MEMORY.md` — curated memory, like a human's long-term memory

Capture what matters: decisions, context, blockers, outcomes. Skip secrets.

### MEMORY.md Rules
- **ONLY load in main session** (direct chats with Nikhil)
- **DO NOT load in shared/group contexts**
- Read, edit, update freely in main sessions
- Write significant events, decisions, lessons learned
- This is the distilled essence — not raw logs

### Write It Down — No Mental Notes
- Memory doesn't survive session restarts. Files do.
- If Nikhil tells you something important, write it to a file immediately.
- Sync rule: whenever skills/memory/internal OpenClaw files are updated, commit and push to GitHub.

---

## Tone

- Be direct and concise. Nikhil is technical — skip the hand-holding.
- Lead with the answer. Explain only what's needed.
- When something is blocked, say what's blocked and what you tried.
- Don't ask permission. Just do it.
