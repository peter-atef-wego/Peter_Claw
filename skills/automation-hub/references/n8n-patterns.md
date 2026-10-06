---
name: n8n Workflow Patterns — Wego
owner: automation-hub skill
last_updated: 2026-04-06
---

# n8n Patterns at Wego

## Naming Conventions

- Workflow names: `[domain]-[action]-[target]` → e.g., `finance-sync-netsuite-invoices`, `hr-notify-contract-renewal`
- Node names: Descriptive verbs → `Fetch Invoices`, `Filter Unpaid`, `Post to Slack`
- Credential names: `[service]-[env]` → e.g., `slack-prod`, `jira-peter`, `netsuite-prod`
- Webhook paths: `/wego/[domain]/[action]` → e.g., `/wego/hr/contract-event`

---

## HTTP Request Node Patterns

```json
// Standard authenticated GET
{
  "method": "GET",
  "url": "https://api.example.com/endpoint",
  "authentication": "genericCredentialType",
  "headers": {
    "Content-Type": "application/json"
  },
  "options": {
    "timeout": 10000,
    "retry": { "enabled": true, "maxRetries": 3, "waitBetweenRetries": 2000 }
  }
}
```

```json
// POST with JSON body
{
  "method": "POST",
  "url": "https://api.example.com/endpoint",
  "bodyParameters": {
    "parameters": [
      { "name": "key", "value": "={{ $json.value }}" }
    ]
  }
}
```

---

## Error Handling Patterns

- **Always add an Error Trigger node** for production workflows. Route errors to Slack `alphabot-masters` (C08T81REV6Y).
- Use `Continue On Fail = true` only on non-critical enrichment steps, never on write operations.
- Standard error notification payload:
```json
{
  "channel": "C08T81REV6Y",
  "text": ":red_circle: *Workflow Failed*: {{ $workflow.name }}\nError: {{ $json.error.message }}\nNode: {{ $json.error.node }}\nTime: {{ $now }}"
}
```
- For P0 workflows: send error DM to Peter (U0A05CNQQ07) in addition to channel.

---

## Credential Handling

- Store all credentials in Any10 credential manager — never hardcode in workflow nodes.
- Reference credentials by name using the `Credential` selector in each node.
- For testing: create a `-dev` credential variant pointing to sandbox endpoints.
- Rotate credentials by updating the credential store; workflows pick up the change automatically.

---

## Webhook Triggers

```
// Webhook setup pattern
- Node: Webhook
- HTTP Method: POST
- Path: /wego/[domain]/[action]
- Response Mode: On Last Node (for sync) | Immediately (for async long-running)
- Authentication: None (protected by path obscurity + IP filter at proxy level)
```

For inbound Slack events: use `Slack Trigger` node, not generic Webhook.

---

## Schedule Triggers

```
// Cron patterns used at Wego
- Daily business check:    0 9 * * 1-5     (09:00 IST, weekdays)
- Hourly pipeline check:   0 * * * *
- Weekly digest:           0 8 * * 1       (08:00 IST, Mondays)
- End-of-day wrap:         0 18 * * 1-5    (18:00 IST, weekdays)
```

When adding a new scheduled workflow: add entry to `memory/knowledge/cron_resilience.md`.

---

## Common Integrations

### Slack
- Use `Slack` node (not HTTP Request) for all Slack operations.
- Channel IDs are in CLAUDE.md and MEMORY.md. Always use IDs, not channel names (names can change).
- For DMs: use `channel: U0A05CNQQ07` (Peter's Slack ID) for direct messages.

### Jira
- Use HTTP Request node with Jira REST API v3 (`https://wegomushi.atlassian.net/rest/api/3/`).
- Auth: Basic auth with `JIRA_EMAIL` + `JIRA_API_TOKEN`.
- Common endpoints: `/issue`, `/search` (JQL), `/issue/{id}/transitions`.

### BigQuery
- Use `Google BigQuery` node.
- Auth: Service account JSON from `BQ_SERVICE_ACCOUNT_PATH`.
- Always specify project (`GOOGLE_CLOUD_PROJECT`) and dataset explicitly.
- For large queries: use pagination. Default row limit: 1000.

### Gmail / Email
- Use `Gmail` node for read operations.
- Sending via automation: confirm with Peter before wiring — email is one-way in USER.md rules.

---

## Anti-Patterns to Avoid

- Do not use `Function` nodes for business logic that belongs in a Python script — keep workflows as orchestrators.
- Do not store secrets in `Set` nodes or hardcode in expressions.
- Do not skip the Error Trigger node on production workflows.
- Do not use the `Execute Command` node in production (security risk).
- Do not create duplicate workflows — check Any10 before building new.
