---
name: Wego AI & Automation — Systems Architecture
owner: Nikhil Gupta
last_reviewed: 2026-04-06
---

# Systems Architecture

## Core Platforms

| Tool | URL / Access | Purpose |
|---|---|---|
| OpenClaw | s-c58f0c35.openclaw.wego.engineering | AI agent platform — Data Automation's Claw-PRO runs here |
| Jira | wegomushi.atlassian.net | Project tracking (IAX + NDS boards) |
| Confluence | wegomushi.atlassian.net | Documentation |
| GitHub | github.com/Nikhil-Wego / github.com/wego | Code repos |
| Slack | wego workspace | Team communication |
| NetSuite | Internal ERP | Finance/accounting operations |
| BigQuery | GCP project | Data warehouse for pipeline outputs |
| Airflow | Internal | Pipeline orchestration (Ayush's domain) |
| Fireflies | fireflies.ai | Meeting recording and transcription |

---

## Key Repositories

| Repo | Access | Purpose |
|---|---|---|
| github.com/wego/openclaw-nova | Read/Write | This Data Automation's Claw-PRO agent repo |
| github.com/wego/alphabot | Read-only | Wego's automation bot framework (Robot Framework + Python) |

---

## Automation Tools

### n8n / Any10
- **What**: Visual workflow automation platform. Used for event-driven automations, integrations, and scheduled jobs.
- **Who**: Likith (primary), Akansha (learning). Finance automations, supplier recos, commission workflows.
- **Patterns**: See `skills/automation-hub/references/n8n-patterns.md`.
- **Deployed via**: Any10 (Wego's hosted n8n environment).

### Robot Framework + Python (AlphaBot)
- **What**: Keyword-driven test/automation framework. All bot logic in `github.com/wego/alphabot`.
- **Who**: Ayush (Hotels/HCN), Peter (HR, disputes). Nikhil oversees architecture.
- **Structure**: Each automation is a Robot Framework suite; shared Python libraries in `alphabot/libs/`.
- **Run**: Triggered via schedule or Slack command via AlphaBot dispatcher.

### Apache Airflow
- **What**: DAG-based pipeline orchestrator. Used for data pipeline scheduling at Wego.
- **Who**: Ayush (HCN/Hotels pipelines).
- **Backend**: Writes to BigQuery.

### BigQuery
- **What**: Google Cloud data warehouse. Downstream target for Airflow pipelines.
- **Access**: Via service account (`BQ_SERVICE_ACCOUNT_PATH` in `.env`).
- **Project**: `GOOGLE_CLOUD_PROJECT` env variable.

---

## Integration Patterns

- **Slack → trigger**: Alphabot and n8n automations can be triggered by Slack messages in specific channels.
- **Jira ↔ automations**: IAX tickets created for every automation before production deploy. Status updated by bots on completion.
- **Airflow → BQ**: Pipeline outputs land in BigQuery; downstream reports pull from BQ.
- **NetSuite ↔ n8n**: Finance automations read/write NetSuite via API. Akansha will own this.
- **Fireflies → Data Automation's Claw-PRO**: Transcripts stored in `fireflies/summaries/`; indexed in `fireflies/index.json`.

---

## OpenClaw Setup

- **Instance**: s-c58f0c35.openclaw.wego.engineering
- **Workspace path**: `/home/openclaw/.openclaw/workspace`
- **Secrets (WegoClaw)**: GITHUB_TOKEN_V4 (fine-grained, Nikhil-Wego org), JIRA_EMAIL, JIRA_API_TOKEN (pending)
- **Known issue**: Data Automation's Claw OAuth token refresh failure for openai-codex — monitor `alphabot-masters` channel.
- **Cron**: `daily-push-Data Automation's Claw-claw` — setup in progress.
- **Contact for platform issues**: Madan Kumar (madan@wego.com).
