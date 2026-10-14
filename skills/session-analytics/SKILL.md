---
name: session-analytics
description: Track and report on session consumption — queries, models used, tiers, costs. Summarize in 5-tier breakdown on request.
---

# Session Analytics — Memory & Model Consumption

Tracks every prompt, classifies to tier, logs model used, and provides consumption reports.

## Tracking

Every prompt is logged with:
- Timestamp
- Query text (first 100 chars)
- Classified tier (nano/fast/analyst/standard/premium)
- Model ID used
- Estimated tokens (rough)
- Cost estimate

## Log File

`memory/knowledge/session_analytics.jsonl` — one entry per line (JSON Lines format)

Example entry:
```json
{"ts": "2026-04-10T04:10:00Z", "query": "Check Jira tickets...", "tier": "fast", "model": "google/gemini-3-flash-preview", "tokens_est": 250, "cost_est": 0.000125}
```

## Report Format (5-Tier Breakdown)

Request: "consumed memory info"

Response (Slack rich format):

```
📊 SESSION ANALYTICS

🟢 Nano (12 queries) — $0.003
  • git pull openclaw-nova
  • python script runner
  • extract json output

🔵 Fast (8 queries) — $0.012
  • slack channel scan
  • jira triage check
  • meeting prep

🟣 Analyst (2 queries) — $0.048
  • bigquery analysis
  • netsuite data reconciliation

🟠 Standard (15 queries) — $0.675
  • general conversation
  • code review
  • analysis request

🔴 Premium (0 queries) — $0.000
  • (none this session)

━━━━━━━━━━━━━━━━━
Total: 37 queries | $0.738 | Tier Distribution: 32% Nano, 22% Fast, 5% Analyst, 41% Standard
```

## Implementation

See `memory/knowledge/session_analytics_tracker.py` for logging logic.

Call before sending response:
```python
from session_analytics_tracker import log_query
log_query(prompt_text, tier, model_id)
```

On request "consumed memory info":
```python
from session_analytics_tracker import generate_report
report = generate_report()
send_slack_rich_format(report)
```
