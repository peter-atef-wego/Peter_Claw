# Observability — direct-MCP architecture

> ## Architecture context
>
> The NetSuite Champion runs as OpenClaw calling Oracle's MCP servers directly. The legacy Python listener (`test_py/netsuite-mcp/`) and its dedicated logging/alerts stack were **deleted from the repo on 2026-05-12**. This doc describes the much-simpler observability model under the new architecture.

---

## 1. Where signals come from now

| Signal | Where it lives | Who sees it |
|---|---|---|
| **Tool errors** (NetSuite 4xx/5xx, timeouts, MCP plugin errors) | Surfaced verbatim in the agent's Slack reply per `CLAUDE.md` Rule 5 (errors surface verbatim) | Whoever is in the thread |
| **State-changing actions** (every sandbox create/update/delete) | One line per action in `memory/knowledge/action_tracker.md` | Whoever inspects the audit log |
| **Slack-side delivery failures** (auth, rate limits) | Surfaced as an agent post if possible; otherwise the OpenClaw harness logs | Nikhil (via OpenClaw runtime logs) |
| **OpenClaw harness logs** (skill loading, MCP-server calls, exceptions) | OpenClaw runtime log files / dashboards | Nikhil |

There is **no** Python daemon, no separate listener log, no per-mention JSONL trace, no daily rollup script. If you need traceability, the audit log + Slack thread history together tell the full story.

---

## 2. Audit log — the one file you actually maintain

`memory/knowledge/action_tracker.md` — append-only, one line per state-changing action. The bot writes this **before** posting the reply for every sandbox create/update/delete.

**Line format:**

```
<ISO timestamp> | <channel> | <user> | <verb> | <record_type> | <internal_id> | <sandbox_url>
```

**Examples:**

```
2026-05-12T14:32:11+00 | #netsuite_ap                | U07XYZ | create_vendor        | vendor       | 12345 | https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=12345
2026-05-12T14:35:02+00 | #netsuite_champion          | U07XYZ | create_bill          | vendorbill   | 67890 | https://5564218-sb1.app.netsuite.com/app/accounting/transactions/vendbill.nl?id=67890
2026-05-12T15:11:48+00 | #netsuite_gl_and_reporting  | U02ABC | create_journal_entry | journalentry | 99001 | https://5564218-sb1.app.netsuite.com/app/accounting/transactions/journal.nl?id=99001
```

**Reads are NOT logged here.** Only state changes — that's the audit trail Akansha and Nikhil need.

---

## 3. Surfacing failures

When a tool call fails:

1. **Detect.** Oracle MCP returns a non-2xx status or an error envelope.
2. **Reply verbatim.** Post the actual error code + NetSuite's message + one short human sentence of context. See `CLAUDE.md §13 Failure-mode lookup` for the lookup table.
3. **Don't retry on a different server.** If a write to sandbox fails, don't retry against prod (it would 403 anyway; the policy is sandbox-only writes).
4. **Don't paper over.** No "let me try a different approach" narration. No fabricated success.

Specific signals worth surfacing immediately:

| Signal | Likely cause | Suggested reply |
|---|---|---|
| `401 INVALID_LOGIN_ATTEMPT` (prod or sandbox) | TBA token expired or integration role revoked | "NetSuite returned 401. The TBA token may have expired. Nikhil — heads up." |
| `403` on a SuiteQL field | Integration role lacks permission | "NetSuite returned 403 on `<table>`. Akansha may need to extend the integration role." |
| `429` | Concurrency / rate limit hit | Wait 5 s, retry once. Surface if still failing. |
| `5xx` / network timeout | NetSuite slow or transient outage | Retry once with a tighter query. Surface if still failing. |
| Slack `not_authed` / `invalid_auth` | `SLACK_BOT_TOKEN_NETSUITE_CHAMPION` issue | Cannot reply via Slack — log via OpenClaw harness; Nikhil must rotate. |

---

## 4. Trends and patterns

Under the legacy listener architecture there was a daily rollup script that wrote a markdown file per day. Under the direct-MCP architecture this is not implemented — and may not be needed. If trend analytics become valuable (e.g. "how many vendor creates per week?", "which channels see the most reads?"), options are:

- Parse `memory/knowledge/action_tracker.md` directly (one grep + count).
- Query Slack channel history via the Slack MCP tools.
- Add a periodic OpenClaw task (e.g. a cron or scheduled skill invocation) to summarise — would need to be designed.

For now, the audit log + on-demand inspection is sufficient.

---

## 5. Where to look when something breaks

1. **The user's Slack thread** — the bot's reply should contain the actual error message, surfaced verbatim per Rule 5. Start here.
2. **`memory/knowledge/action_tracker.md`** — confirm whether a state change actually happened or not.
3. **OpenClaw runtime logs** — for skill-loading issues, MCP-server connectivity issues, or harness-level errors. Access via the OpenClaw admin UI.
4. **NetSuite audit trail (in NetSuite UI)** — for "did the record actually post?" questions on writes. Search by `tranid` or by the user's name as the script executor.

If none of these surface the issue, escalate to Akansha (NetSuite-side) or Nikhil (OpenClaw / MCP server config).
