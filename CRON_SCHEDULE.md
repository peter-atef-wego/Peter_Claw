# OpenClaw Internal Cron Schedule

All jobs run via OpenClaw internal cron (`/home/openclaw/.openclaw/cron/jobs.json`).
Times below are **UTC**.

| Job | Schedule (UTC) | DXB Time | What it does |
|---|---|---|---|
| `openclaw_nova_mirror` | 03:30 Sun | 07:30 | Mirror workspace → wego/openclaw-nova via PR |
| `nova_claw_pull_sync` | 05 * * * * (hourly) | 09 * * * * | `git pull origin main` into the workspace (a merge, not a hard reset) |
| `weekly_team_monday` | 05:00 Mon | 09:00 | Create 4 Jira weekly-update tickets (IAX×3, NDS×1) + commit ticket keys |
| `weekly_team_friday` | 05:00 Fri | 09:00 | Post Slack reminder in #alphabot-masters with the week's ticket links |
| `daily_sync_status` | 19:05 daily | 23:05 | Post daily cron sync status to Nik (Slack DM) |

## Environment

Cron jobs source: `/home/openclaw/.openclaw/cron/openclaw.env` (chmod 600).
