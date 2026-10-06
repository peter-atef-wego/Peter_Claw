---
name: automation-hub
triggers: [automation, n8n, bot, robot, workflow, airflow, python, alphabot]
load: always
version: 1.0
---

# Automation Hub Skill

## Purpose
This skill handles all automation-related tasks: designing, building, reviewing, and triaging automations across n8n/Any10, AlphaBot (Robot Framework + Python), and Airflow. It also manages the bridge between new automation requests and Jira ticket creation on the IAX board. Every automation starts with a ticket — no exceptions.

---

## Core Method

1. **Identify type** — Is this: new build, debug/fix, review, or status check?
2. **Identify tool** — n8n/Any10, Robot Framework (AlphaBot), Airflow, or pure Python script?
3. **Check patterns** — Load `references/n8n-patterns.md` for n8n; check `github.com/wego/alphabot` for Robot Framework conventions.
4. **Propose and confirm** — For new builds: propose structure before writing code. For fixes: state diagnosis before applying.
5. **Build** — Write clean, documented code. Follow naming conventions (see references).
6. **Create Jira ticket** — Create or reference an IAX ticket. No automation goes to production without one.
7. **Log in action_tracker** — Add to `memory/knowledge/action_tracker.md` with owner, due, and status.

---

## Decision Rules

1. If the automation involves finance data → confirm with Peter before wiring to production NetSuite.
2. If the automation writes to a shared Slack channel → test in DM first, not in the live channel.
3. If reusing AlphaBot → check `github.com/wego/alphabot` first. Do not reinvent existing libraries.
4. If the automation is scheduled (cron) → add a pattern entry to `memory/knowledge/cron_resilience.md` on first deploy.
5. If a running automation needs to be disabled → do NOT disable silently. Notify stakeholder and Peter first.
6. If the request is vague → clarify scope with one focused question before building anything.
7. n8n for event-driven integrations and simpler workflows; Robot Framework for complex multi-step bots with state.
8. Airflow for data pipeline orchestration only — not for ad-hoc automations.

---

## Reference Index

| Reference | Path | When to Load |
|---|---|---|
| n8n patterns | `skills/automation-hub/references/n8n-patterns.md` | Any n8n/Any10 work |
| AlphaBot repo | `github.com/wego/alphabot` | Robot Framework builds |
| Active scripts | `scripts/active/` | When debugging live scripts |
| Cron resilience | `memory/knowledge/cron_resilience.md` | When setting up or debugging scheduled jobs |

---

## Quick Commands

- `build n8n workflow for [X]` — propose workflow structure, then build.
- `debug [automation name]` — diagnose failure, propose fix.
- `review [script/workflow]` — code review with specific feedback.
- `create IAX ticket for [automation]` — create Jira ticket on IAX board.
- `list active automations` — pull from `memory/knowledge/projects.md` + action_tracker.
- `check alphabot for [pattern]` — search `github.com/wego/alphabot` for existing libraries.
