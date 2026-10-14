# HEARTBEAT.md — Proactive Check Protocol

## Overview
Data Automation's Claw-PRO runs a heartbeat during active hours to surface issues before Peter has to ask.
Operating window: **09:00–23:00 Africa/Cairo**.
State is tracked in `memory/heartbeat-state.json`.

---

## Scheduled Cron Tasks

These run automatically via `cron/jobs.json`. Data Automation's Claw monitors their health.

| Job | Schedule (DXB) | What It Does |
|---|---|---|
| `openclaw_nova_mirror` | Sun 7:30 AM DXB | Mirror workspace → `wego/openclaw-nova` via PR |
| `nova_claw_pull_sync` | Hourly at :05 DXB | `git pull origin main` into the workspace (a merge, not a hard reset) |
| `weekly_team_monday` | Mon 9:00 AM DXB | Create IAX weekly Jira tickets for team |
| `weekly_team_friday` | Fri 9:00 AM DXB | Send Friday Slack reminder to team |
| `daily_sync_status` | Daily 11:05 PM DXB | Post daily cron sync status to Nik (Slack DM) |

**REMOVED (2026-04-13):** `netsuite_kb_sync` — disabled per Peter's request. No more NetSuite notifications.

If any of these fail, check `memory/knowledge/cron_resilience.md` for known failure patterns first.

---

## P1 — Every Heartbeat (Always Run)

These checks run on every heartbeat cycle without exception.

### 1. Stale Ticket Check (IAX + NDS)
- Query: all open tickets with no update in >24h during an active sprint.
- If found: surface ticket ID, assignee, last update, and recommended action.
- Never just list them — propose a next step for each.

**DISABLED (2026-04-29):**
- ~~Team Blocker Monitor~~ — Disabled per Peter's request
- ~~Automation Failure Check~~ — Disabled per Peter's request

---

## P2 — Rotating (2–4 per Heartbeat)

Run a rotating subset each cycle. Prioritise by recency of last check (see `heartbeat-state.json`).

### A. IAX Board Full Scan
Full triage of IAX board 721. Group by assignee. Flag blocked, stale, and unassigned tickets.

### B. NDS Board Scan
Full triage of NDS board 753. Focus on NetSuite transition items.
Flag anything waiting on team response.

### C. GitHub PR Review
Check `github.com/wego/openclaw-nova` for open PRs older than 2 days.
Check `github.com/wego/alphabot` for PRs from team members awaiting review.

### D. Cron Health Check
Review `cron_resilience.md` for repeated failure patterns.
Verify cron jobs in table above ran successfully at last scheduled time.

### E. Upcoming Meetings
Check calendar for meetings in the next 24h involving Peter or team members.
Flag any meeting with no agenda or pre-read material.



---

## P3 — Weekly (Run Once Per Week)

### Sprint Planning Prep
Before each sprint planning: generate a summary of what was completed, what's carrying over, and what new items should be pulled in. Reference `memory/knowledge/projects.md` and IAX board.

### MEMORY.md Pruning
Review MEMORY.md for outdated entries. Archive anything resolved >30 days ago.

### Cron Resilience Hygiene
Review all entries in `cron_resilience.md`. Close resolved incidents. Add patterns for any new failure types observed.

### Self-Upgrade Review
Check if any capability improvements identified in past sessions can now be implemented.

---

## Heartbeat State Management

After each heartbeat, update `memory/heartbeat-state.json`:
- Set `last_checks.<check_name>` to current ISO timestamp.
- If `crisis_mode` triggered (automation down, blocker unresolved >48h): set `crisis_mode: true` and notify Peter via Slack DM immediately.
- Log completed checks in `completed_today` array (reset daily at 00:00 Africa/Cairo).

## Output Format
Each heartbeat report:
1. P1 findings first — with a clear CLEAR / FLAG / ESCALATE status per item.
2. P2 rotating findings — summarised, not verbose.
3. Any actions Data Automation's Claw took autonomously (Slack message, Jira update).
4. Items requiring Peter's decision — surfaced as explicit questions, not buried.
