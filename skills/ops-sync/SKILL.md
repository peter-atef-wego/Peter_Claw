---
name: ops-sync
---

# Ops Sync

## Overview

Standardize how we update OpenClaw’s internal scheduler and keep GitHub documentation aligned.

## Workflow

### 1) Update scheduler configuration

- **Internal cron (OpenClaw):** `/home/openclaw/.openclaw/cron/jobs.json`
- **HEARTBEAT backup:** `HEARTBEAT.md` in repo
- Ensure commands source `/home/openclaw/.openclaw/cron/openclaw.env` (no secrets in git).
- **Duplicate check**: before adding new schedule/docs, search repo for existing schedule files (`CRON_SCHEDULE.md`, `HEARTBEAT.md`, `cron/jobs.json`) and reuse instead of creating new ones. If a file already exists, update it—do not create a duplicate.

### 2) Update documentation in GitHub

- Update `CRON_SCHEDULE.md` with the current schedule (UTC + DXB time).

### 3) Commit + push

- Commit repo changes to **openclaw-nova** (GitHub is source of truth for schedules).
- If only scheduler config changed, also copy `cron/jobs.json` into repo mirror at `cron/jobs.json`.

## Current scheduled jobs (baseline)

- `netsuite_kb_sync` — Mon/Thu 04:00 UTC (8 AM DXB)
- `openclaw_nova_mirror` — Sun 03:30 UTC (7:30 AM DXB) — mirror workspace → wego/openclaw-nova via PR
- `nova_claw_pull_sync` — hourly at :05 UTC — `git pull origin main` into the workspace (a merge, not a hard reset — see cron/jobs.json)
- `daily_sync_status` — daily 19:05 UTC (11:05 PM DXB) — post daily cron sync status to Nik (Slack DM)

## Guardrails

- Do **not** store secrets in memory/skills/docs.
- Use least‑privilege tokens and `openclaw.env` for runtime secrets.
- Keep HEARTBEAT as backup even when internal cron is enabled.
