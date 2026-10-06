---
name: weekly-team-setup
description: >
  Nikhil's weekly team automation skill for the Intelligent Alpha Automation (IAX) team at Wego.
  Manages the full weekly update workflow: creates Jira tasks every Monday and sends Slack reminders
  every Friday. Load this skill whenever Nikhil asks to: set up the weekly tasks, create Jira weekly
  update tickets, send or schedule the Friday Slack reminder, deploy the weekly automation to OpenClaw
  or AlphaBot, make changes to team members, epics, boards, or the reminder message, or anything
  related to the recurring weekly team update process.
---

# Weekly Team Setup — Skill

## What This Does

Two automated jobs every week:

| When | What |
|------|------|
| Monday 09:00 Dubai (UTC+4) | Creates 4 Jira "Weekly Update" tasks, one per team member |
| Friday 09:00 Dubai (UTC+4) | Sends Slack reminder in #alphabot-masters with direct Jira links |

---

## Team Members

| Name | Jira Account ID | Slack ID | Jira Board | Issue Type | Epic |
|------|----------------|----------|------------|------------|------|
| Ayush Raj | `712020:4c7d6ace-7df0-46e7-bd53-60cb3cbd4b58` | `U01KSFH6WPK` | IAX | Weekly Update | IAX-454 |
| Likith | `712020:91ee1a0b-3411-46c7-a621-ca78ef29f4e1` | `U07GRT0PLSK` | IAX | Weekly Update | IAX-454 |
| Peter Atef | `712020:436280da-892e-44cf-ac47-0527ccae163d` | `U0A05CNQQ07` | IAX | Weekly Update | IAX-454 |
| Akansha Singh | `712020:5eace571-0f21-495f-a304-0511d95efb41` | `U0AGL8T9H5J` | NDS | Task | NDS-67 |

---

## Jira Config

```
JIRA_BASE_URL   = https://api.atlassian.com/ex/jira/a7e53b72-ded0-45e3-8d7c-fd3573f46f1d/rest/api/3
JIRA_AUTH_EMAIL = nikhil@wego.com
CLOUD_ID        = a7e53b72-ded0-45e3-8d7c-fd3573f46f1d
IAX_EPIC_KEY    = IAX-454   ← "Weekly Update Automation Team" epic on IAX board
NDS_EPIC_KEY    = NDS-67    ← "Weekly Update Automation Team" epic on NDS board
```

Secrets (stored in AWS Secrets Manager under `alphabot-production`):
- `JIRA_API_TOKEN`
- `SLACK_BOT_TOKEN`

---

## Slack Config

```
CHANNEL_ID   = C08T81REV6Y   ← #alphabot-masters (private channel)
REMINDER_TIME = 09:00 Dubai (06:00 UTC)
```

---

## Jira Ticket Format

**Summary:** `Weekly Team Update - Week of {D Month YYYY} — {Name}`
e.g. `Weekly Team Update - Week of 19 May 2026 — Ayush Raj`

**Parent (Epic):**
- IAX tickets → `IAX-454`
- NDS tickets → `NDS-67`

**Description (ADF format — pre-filled for team to fill as a comment):**
```
Team members: Add your weekly update as a COMMENT below using this format.

1. Completed This Week
2. In Progress
3. Blockers
4. Key Impact / Results
5. Next Week Focus (if you are not sure then lets discuss on Monday)

Please don't forget to add your task link for each task in this update.
```

---

## Slack Reminder Message Format

```
*Weekly Update Due — Week of {D Month YYYY}*

Team, please post your weekly updates in your respective tickets:

<https://wegomushi.atlassian.net/browse/{IAX-KEY-1}|{IAX-KEY-1} • Ayush Raj>
<https://wegomushi.atlassian.net/browse/{IAX-KEY-2}|{IAX-KEY-2} • Likith>
<https://wegomushi.atlassian.net/browse/{IAX-KEY-3}|{IAX-KEY-3} • Peter Atef>
<https://wegomushi.atlassian.net/browse/{NDS-KEY}|{NDS-KEY} • Akansha>

Please include:
• What you shipped this week
• Blockers & what you need
• What's next

Thanks!
```

Ticket keys created on Monday are saved to `/tmp/weekly_team_issues.json` and loaded on Friday to include direct links.

---

## Implementation — runs on OpenClaw (not AlphaBot)


| Piece | Location |
|---|---|
| Script | `scripts/weekly_team_setup.py` |
| Cron entries | `cron/jobs.json` → `weekly_team_monday`, `weekly_team_friday` |
| Env file | `/home/openclaw/.openclaw/cron/openclaw.env` — provides `JIRA_API_TOKEN`, `JIRA_EMAIL`, and the shared Slack bot token (env var name is `SLACK_BOT_TOKEN_NETSUITE_CHAMPION` for legacy reasons — it's the team's single Slack bot, not NetSuite-specific). |
| State (Mon→Fri) | `memory/state/weekly_team_issues.json` — committed to git so it survives container restarts |
| Schedule index | `CRON_SCHEDULE.md` |

### Schedule

| Job | Cron (UTC) | DXB |
|---|---|---|
| `weekly_team_monday` | `0 5 * * 1` | Mon 09:00 |
| `weekly_team_friday` | `0 5 * * 5` | Fri 09:00 |

### CLI

```bash
source /home/openclaw/.openclaw/cron/openclaw.env
python3 /home/openclaw/.openclaw/workspace/scripts/weekly_team_setup.py monday
python3 /home/openclaw/.openclaw/workspace/scripts/weekly_team_setup.py friday
```

`monday` creates the 4 tickets and writes `memory/state/weekly_team_issues.json`. The cron job commits + pushes that file so Friday's run can read it. `friday` reads the state file and posts the Slack reminder; if the file is missing it still sends a graceful reminder without ticket links.

### Functions

| Function | Called When | Does |
|---|---|---|
| `run_monday()` | Monday cron | Creates 4 Jira tickets, writes state file |
| `run_friday()` | Friday cron | Loads state, sends Slack reminder with links |
| `create_jira_issue(member, week_label)` | by Monday | One ticket with epic + ADF description |
| `send_slack_reminder(issues)` | by Friday | Posts formatted message to #alphabot-masters |
| `get_week_label()` | both | Returns Monday of current week as `"19 May 2026"` |

### Manual triggering

No `nova_api` HTTP endpoint, no Slack `slack_listener` trigger phrase. Manual runs:
1. Ask Claude on OpenClaw to run the CLI command above
2. For one-off corrections (re-assigning a ticket, fixing a reminder, editing the description) use Atlassian/Slack MCPs directly — `mcp__01934f1e-…__editJiraIssue`, `…__addCommentToJiraIssue`, Slack MCP `send_message`

---

## Common Changes Nikhil May Ask For

| Change | What to update |
|--------|---------------|
| Add a team member | Append a row to `MEMBERS` in `scripts/weekly_team_setup.py` (name, jira_id, slack_id, project, issue_type). Get Jira account ID via Atlassian MCP `lookupJiraAccountId`. |
| Remove a team member | Remove their row from `MEMBERS` |
| Change reminder time | Update the cron `expr` in `cron/jobs.json` (UTC) and the DXB column in `CRON_SCHEDULE.md` |
| Change the Slack channel | Update `SLACK_CHANNEL` constant |
| Change the description template | Update `JIRA_DESCRIPTION_ADF` dict |
| Change the epic | Update `IAX_EPIC_KEY` or `NDS_EPIC_KEY` constants |
| Add a new board (not IAX/NDS) | Add another `elif member["project"] == "XYZ"` branch in `create_jira_issue()` |

---

## Jira API Reference

Create issue: `POST {JIRA_BASE_URL}/issue`
Auth: Basic auth with `JIRA_EMAIL:JIRA_API_TOKEN`
Epic link: set `fields.parent.key` to the epic key (next-gen projects)
Description: ADF (Atlassian Document Format) JSON, not markdown

Jira base URL:
`https://api.atlassian.com/ex/jira/a7e53b72-ded0-45e3-8d7c-fd3573f46f1d/rest/api/3`

---

## Notes

- **Slack target is hardcoded to `C08T81REV6Y` (#alphabot-masters).** The bot token (`SLACK_BOT_TOKEN_NETSUITE_CHAMPION`) is the team's shared Slack bot — the env var name is legacy, the bot itself is not NetSuite-specific. This script never reads channel from input and never posts to any NetSuite channel.
- The "Sent using Claude" attribution in Slack is controlled by Slack's OAuth app display settings — cannot be removed from code side.
- `memory/state/weekly_team_issues.json` persists ticket keys between Monday and Friday jobs. Stored in git (not `/tmp/`) so container restarts can't lose it. If the file is somehow missing on Friday, the reminder still sends — just without the per-person ticket links.
- NDS board uses issue type `"Task"` (not `"Weekly Update"`) as that's what's available on that project.
- Akansha's timezone is Asia/Kuala_Lumpur but she's included in the Dubai-timed reminder since she's part of the team.
