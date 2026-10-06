# openclaw-nova — Data Automation's Claw-PRO

**AI & Automation Lead Agent for Peter Atef, Wego — Data Automation team.**

| | |
|---|---|
| OpenClaw instance | `s-c58f0c35.openclaw.wego.engineering` |
| Repository | https://github.com/wego/openclaw-nova |
| Workspace | `/home/openclaw/.openclaw/workspace` |
| Mirror job | `openclaw_nova_mirror` — weekly PR from the OpenClaw workspace into this repo |
| Owner | Peter Atef (`peter.atef@wego.com`) |

---

## 1. What this is

An always-on AI operations agent built on **OpenClaw**. It runs as one persistent identity (`@Data Automation's Claw`, Slack user `U0AHNGSDQ3W`) and handles four product surfaces:

1. **NetSuite Champion** — live SuiteQL queries, record creation, and 10 pre-built standard financial reports across 6 finance Slack channels. Reads against production (`5564218`), writes against sandbox (`5564218-sb1`).
2. **Cron automation** — GitHub mirror, hourly workspace sync, weekly team setup, daily status DM. Resurrected via a self-healing daemon after container restarts.
3. **Proactive monitoring** — heartbeat checks during business hours (09:00–23:00 GST). P1: stale tickets. P2 rotating: board scans, GitHub PRs, cron health. P3 weekly: sprint prep, memory pruning.
4. **Finance reconciliation (advisory)** — 58 LCC suppliers across two bridge channels. The pipeline is owned by a server-side listener on the AlphaBot host; the agent only answers questions and redirects, and is contractually silent in the bridge channels. See §5.3 *Finance reconciliation agent*.

The container is ephemeral, so all four depend on the persistent-memory layer in
**§4 *Persistent memory*** — this repo *is* the agent's long-term memory, mirrored
nightly to S3.

---

## 2. Root-level files — what each one does

| File | Purpose |
|---|---|
| `README.md` | This file. Project overview, structure, and operational index. |
| `CLAUDE.md` | **Operating contract.** Startup protocol, core rules (no silent failures, no hallucination, no stale Jira), skill loading strategy, MCP tool index, Jira boards, Slack channels, output standards, git discipline. |
| `MEMORY.md` | **Operational memory** — every decision, fix, config change, and incident. Loaded on every main session. Source of truth for *how we got here*. Read/write rules: §4 *Persistent memory*. |
| `AGENTS.md` | **Session bootstrap.** Load order: PERSONA → USER → daily memory → MEMORY.md → heartbeat state → MANIFEST. Hard gate: auth preflight before any git/Jira/GitHub action. |
| `HEARTBEAT.md` | Proactive monitoring protocol (window, P1/P2/P3 checks, crisis-mode triggers). |
| `SOUL.md` | Personality and tone — direct, resourceful, no filler. |
| `IDENTITY.md` | Agent identity metadata (name, creature, vibe, emoji, avatar). |
| `USER.md` | About Peter — channels, preferences, escalation routes. |
| `TOOLS.md` | Local tool notes — environment-specific config. |
| `SKILL_REGISTRY.md` | Registry of all 24 skills with descriptions and load conditions. |
| `TEACHING.md` | Teaching patterns and knowledge-transfer templates. |
| `CRON_SCHEDULE.md` | Quick reference for cron job schedules (cross-reference for `cron/jobs.json`). |
| `ENVIRONMENT.md` | Environment variables and where secrets live. |
| `BOOTSTRAP.md` | First-run initialization (delete after first run). |

---

## 3. Architecture (current as of 2026-05-22)

### 3.1 Model routing — 5 tiers

All sessions go through `model-routing/model_router.py`, which classifies the incoming task and picks the cheapest model that can answer it. L5 is manual-only — never keyword-routed.

| Tier | Model | Used for |
|---|---|---|
| **L1** | `openrouter/anthropic/claude-sonnet-4-6` | DMs, KB lookups, routine ops — **same model as L3**; chip indicates surface (DM vs channel) |
| **L2** | `openai/gpt-4o-mini` | Light routing, tag/classification, summarisation |
| **L3** | `openrouter/anthropic/claude-sonnet-4-6` | **Default** for channel @mentions, NetSuite queries, code edits, tool-use loops |
| **L4** | `openrouter/anthropic/claude-opus-4-8` | Top Anthropic tier — multi-step finance reasoning, architecture decisions, ambiguous writes, crisis postmortems, prod-write reviews, HERMES proposal validation |
| **L5** | `openrouter/openai/gpt-5.5` | Cross-provider second opinion — independent check of Anthropic answers (HERMES validator diversity), final fallback if Anthropic is down. Manual only. |

**2026-08-11 — Opus 4.7 retired.** The old L5 (Opus 4.8) moved up to L4 and the old L6 (GPT-5.5) moved up to L5. There is no L6. L4 inherited the retired tier's keyword routing and is the auto-escalation target from L3, so it is no longer manual-only; L5 still is. Full spec: `model-routing/ROUTING.md`.

**Hard floor for NetSuite Champion:** Sonnet 4.6. Haiku is **forbidden** in any NetSuite channel — too weak for SuiteQL synthesis and multi-step tool reasoning (decided 2026-05-19).

### 3.2 NetSuite integration

Two execution paths — MCP primary, OAuth script as fallback.

| Path | How | When |
|---|---|---|
| **MCP** | `scripts/netsuite_mcp_server.py` — stdio JSON-RPC server, spawned by OpenClaw gateway, two scopes (`netsuite-prod`, `netsuite-sandbox`) | MCP tools present in the tool list (default for live agent sessions) |
| **OAuth script** | `scripts/netsuite_query.py` — direct OAuth 1.0a TBA via `bash` | MCP tool unavailable in the harness; documented in `wego-netsuite/CLAUDE.md §0.2` |

- **Production** (`5564218`) — reads only. Writes are refused client-side.
- **Sandbox** (`5564218-sb1`) — full CRUD. Vendor / vendor bill / journal entry / customer / invoice / bill payment.
- **Auth** — OAuth 1.0a TBA (HMAC-SHA256). Credentials in MCP server env config (`openclaw.json`) for the live path; sourced from `/home/openclaw/.openclaw/cron/openclaw.env` for the script path. The agent never sees tokens.

### 3.3 MCP tools exposed (current count: 24)

| Tool | Scope | Purpose |
|---|---|---|
| `run_suiteql` | prod / sandbox | Free-form SuiteQL with type-safe param substitution |
| `read_record` | prod / sandbox | GET a record by type + internal id |
| `create_record` | sandbox only | POST a record; alias-checked, post-write-verified |
| `update_record` | sandbox only | PATCH a record |
| `metadata_catalog` | prod / sandbox | List record types, field schemas |
| `discover_table` | prod / sandbox | Schema-discovery probe — row count + columns + sample row, OR suggested alternatives. Powers §5.16 self-building queries (PR #59). |
| `export_suiteql_to_csv` | prod | Bulk-safe — paginates server-side, writes CSV, returns 3-row preview only (bounded ~38k tokens regardless of row count) |
| `run_standard_report` | prod | 10 pre-built financial reports (see `wego-netsuite/references/standard_reports.md`) |
| `export_access_audit` | prod | Atomic 3-CSV bundle — users / roles / user×role assignments. Per-query status, never partial-delivers silently (PR #59). |
| `get_role_permissions` | prod / sandbox | Per-role permission grid via the existing `restlet_companion.js` (action `role_permissions`). Reuses existing `NETSUITE_<SCOPE>_RESTLET_*` env vars (PR #62). |
| `upload_file_to_slack` | n/a | Three-step Slack `files.uploadV2` flow — turns a `/tmp/...` CSV into a real Slack file attachment |
| `refresh_mcp_logs` | n/a | Render JSONL tool-call log to daily markdown for committing |
| `resolve_csv_dimensions` | sandbox | Resolve every CSV-row dimension (subsidiary, vendor, currency, account, dept, location, class, tax, BU) to NetSuite internal IDs in one call. |
| `create_vendor_bill_from_csv` | sandbox | CSV → vendor bill with server-side field mapping (BU code, currency, dimensions) |
| `update_vendor_bill_from_csv` | sandbox | Partial-update an existing Vendor Bill (amendment) — only changed fields |
| `create_journal_entry_from_csv` | sandbox | CSV → journal entry, same field mapping |
| `update_journal_entry_from_csv` | sandbox | Partial-update an existing Journal Entry (multi-line aware) |
| `run_saved_search` | prod / sandbox | Execute an existing NetSuite saved search by id |
| `list_saved_searches` | prod / sandbox | Enumerate saved searches available to the integration role |
| `get_cabinet_file` | prod | Fetch a File Cabinet document by path or internal id |
| `fetch_email_report` | n/a | Pull a report delivered by email (IMAP via `scripts/report_store/email_fetcher.py`) |
| `get_stored_report` | n/a | Read a previously stored report out of the local report store |
| `list_stored_reports` | n/a | Enumerate what the report store currently holds |
| `get_deleted_records` | prod / sandbox | Query the deleted-records log for an audit trail |

### 3.4 Slack configuration

| Setting | Value | Why |
|---|---|---|
| `streaming.mode` | `off` | No verbose intermediate messages. ONE answer per question. |
| `replyToModeByChatType` | `channel: all, group: all, direct: off` | Channel replies stay in-thread |
| `thread.initialHistoryLimit` | `15` | Enough thread context for follow-ups |
| `thread.requireExplicitMention` | `true` | Bot only responds when @mentioned |

**Slack bot token** — `SLACK_BOT_TOKEN_NETSUITE_CHAMPION`. Source of truth: `/home/openclaw/.openclaw/cron/openclaw.env`. Also injected into the live OpenClaw process env so MCP tools can read it directly. `scripts/slack_upload_file.py` checks 4 env var names then falls back to parsing the env file (PR #57, 2026-05-22).

### 3.5 NetSuite Champion channels

| Channel | ID | Domain | KB doc |
|---|---|---|---|
| `#netsuite_champion` | `C0B1T3B4RMH` | Master (needs domain hint) | resolved per-message |
| `#netsuite-dev-agent` | `C0B9A8ZRM5X` | **Dev / QA — Peter's testing channel.** Master access. Use for testing any change before promoting to live finance channels. | resolved per-message |
| `#netsuite_ap` | `C08N2T0CARE` | Accounts Payable | `wego-netsuite/knowledge_base/netsuite_ap.md` |
| `#netsuite_ar` | `C08N2SY3HFS` | Accounts Receivable | `netsuite_ar.md` |
| `#netsuite_gl_and_reporting` | `C08MCK3NJTX` | General Ledger & Reporting | `netsuite_gl_and_reporting.md` |
| `#netsuite_tax` | `C08MHS9PMFC` | Tax | `netsuite_tax.md` |
| `#netsuite_ota` | `C08LZTG1YR5` | OTA Integrations | `netsuite_ota.md` |
| `#netsuite_adminsupport` | `C08MCK8936Z` | Admin/escalation (do not auto-respond) | — |

DMs: `PETER_DM_CHANNEL_ID_TODO` (Peter) — trusted; full access. DMs from any other user are redirected to the relevant channel.

### 3.6 Standard financial reports (10, server-side templates)

The agent does **not** re-draft SuiteQL for these — it calls `run_standard_report(report_name, params)`. SQL templates live in `scripts/netsuite_mcp_server.py::STANDARD_REPORTS`. Token cost is bounded at ~38k regardless of row count.

| `report_name` | Question it answers | Required params |
|---|---|---|
| `customer_statement` | Per-customer statement | `customer`, `from_date`, `to_date` |
| `revenue_periodic` | Revenue between dates | `from_date`, `to_date` |
| `gl_report` | Postings to one GL account | `gl_code`, `from_date`, `to_date` |
| `customer_payments` | Payments received | `from_date`, `to_date` |
| `balance_sheet` | B/S as of a date | `as_of_date` |
| `income_statement` | P&L between dates | `from_date`, `to_date` |
| `interco_balance_sheet` | Intercompany AR + AP balances (Beekim's monthly) | `as_of_date` |
| `gl_listing_multi` | Multi-GL listing in one CSV (Beekim's monthly) | `gl_codes`, `from_date`, `to_date` |
| `fx_rate_list` | Currency exchange rates as of one date (latest per pair) | `as_of_date` (optional `base_symbol`, `source_symbol`) |
| `fx_rate_range` | Every effective-dated FX rate across a window | `from_date`, `to_date` (optional `base_symbol`, `source_symbol`) |

Full param reference: `skills/wego-netsuite/references/standard_reports.md`.

---

## 4. Persistent memory — how the agent remembers

The container is ephemeral: it is replaced on restart and nothing on local disk
survives. Everything the agent knows across sessions is therefore written down in
this repo and mirrored to S3. Three layers, with different durability and cost:

| Layer | Where | Written by | Durability |
|---|---|---|---|
| **Curated memory** | `MEMORY.md`, `memory/knowledge/*.md`, `memory/daily/*.md` | The agent, during a session | Git — this repo is the source of truth |
| **Runtime state** | `~/.openclaw/` (sqlite, sessions, config) | OpenClaw itself | S3 only — in git nowhere |
| **Short-term recall** | `memory/.dreams/` | The runtime, per session | Disposable — gitignored, rebuilt each session |

### 4.1 Read path — what loads at session start

`CLAUDE.md` § Startup Protocol defines the order, and it is a hard gate: the agent
does not answer anything until steps 1-3 complete.

1. `agents/nova-pro/PERSONA.md` — identity and operating rules
2. `agents/nova-pro/USER.md` — who Peter is, authorised channels, team
3. `memory/daily/YYYY-MM-DD.md` — today's log, if it exists
4. `MEMORY.md` — full operational memory (main sessions only; skipped in sub-agents to save context)
4b. `memory/knowledge/learned_lessons.md` — distilled recurring failures; read before any report request
5. `memory/heartbeat-state.json` — last check timestamps, crisis-mode flag
6. `agents/nova-pro/MANIFEST.md` — skill routing table and MCP tool index

### 4.2 Write path — what the agent records, and where

Per `CLAUDE.md` § Core Rules: *no orphaned actions*, and *always write it down*.

| File | Holds | Rule |
|---|---|---|
| `memory/daily/YYYY-MM-DD.md` | One file per day, append-only | Written after each meaningful session |
| `memory/knowledge/decisions.md` | Dated decision log with rationale and decider | A decision is not made until it is in here |
| `memory/knowledge/action_tracker.md` | Methodology for capturing actions; live items live in Jira IAX | Every state-changing action gets logged |
| `memory/knowledge/people.md` | Team and stakeholder map, working styles | — |
| `memory/knowledge/projects.md` | Active project tracking | — |
| `memory/knowledge/cron_resilience.md` | Cron failure patterns and resurrection notes | — |
| `memory/knowledge/context_health.md` | Token usage and context-cost notes | — |
| `memory/knowledge/memory_changelog.md` | Changelog of memory and protocol changes | — |
| `memory/logs/netsuite-mcp/*.md` | Daily NetSuite MCP tool-call summaries | Rendered from raw JSONL, which is gitignored |
| `memory/state/weekly_team_issues.json` | State for the weekly-team-setup cron | — |
| `MEMORY.md` | Long-term operational memory | Update when something matters across weeks. **Never edit with a line-based edit tool** — truncation breaks exact-match; use `sed`/`python3`/full-file write |

### 4.3 Self-learning loop — capture, distil, propose

`scripts/report_store/lessons.py` implements a three-stage loop so the same
failure does not recur:

- **CAPTURE** (deterministic, always on) — every report tool outcome is appended
  to `~/.openclaw/reports/lessons.jsonl`. Cheap, never blocks the tool.
- **DISTIL** (deterministic, nightly via the `lessons_distil` cron at 23:30 UTC) —
  aggregates the log into *recurring* patterns only: the same failure 3+ times,
  unknown report keys, subsidiary misses, format changes. Rendered to
  `memory/knowledge/learned_lessons.md`, which loads every session. No LLM needed.
- **ACT** (agent proposes, human merges) — the agent reads that markdown at startup
  and must not repeat a known mistake. Anything that changes *behaviour* — registry
  keys, subjects, rules — goes through a PR. **The loop proposes; a human merges.**
  The agent cannot silently rewrite its own rules.

### 4.4 Durability — S3 snapshots and the git round-trip

`scripts/memory_backup/` snapshots two roots nightly (`memory_s3_backup` cron,
23:00 UTC) so that **S3 alone is a complete restore point** — full recovery after
node replacement, without EBS and without GitHub:

```
s3://…/netsuite-agent/state/YYYY/MM/DD/HHMMSSZ.tar.gz   # ~/.openclaw runtime state
s3://…/netsuite-agent/memory/YYYY/MM/DD/HHMMSSZ.tar.gz  # MEMORY.md + memory/
```

- `state` is node-local and in git nowhere — this is the root that genuinely needs S3.
  SQLite is snapshotted via `Connection.backup()`, never a raw copy of a live DB.
- `memory` is already durable in git; it is mirrored so a restore needs *only* S3.
- Pure Python stdlib — the pod has no `aws` CLI, `boto3`, or `sqlite3` binary.
  `preflight_s3.py` is a one-run readiness check; `restore_memory.py` with no
  arguments lists what is available.
- 14-day lifecycle on the `netsuite-agent/` prefix.

Git closes the loop in the other direction: the `nova_claw_pull_sync` cron runs
`git pull origin main` in the live workspace every hour at :05. So the repo is not
a backup of the agent — **it is the agent's memory**, and a merged PR is how a
change reaches the running system.

> **Two caveats, both verified against `cron/jobs.json` on 2026-08-11:**
>
> 1. The pull is a **merge, not a hard reset**, despite what several docs used to
>    claim. A local edit in the workspace is not silently discarded — but it *can*
>    make the pull fail and leave the workspace stranded on old code. Commit and
>    push workspace edits promptly.
> 2. The reverse direction is **broken**. `openclaw_nova_mirror` runs
>    `scripts/nova_mirror_pr.py`, which is not in this repo. The job is disabled so
>    nothing is failing, but there is currently no automated workspace → repo push;
>    changes have to be committed by hand until the script is restored.

---

## 5. Directory structure

### 5.1 `/scripts/` — Executable scripts

| File | Status | Purpose |
|---|---|---|
| `netsuite_mcp_server.py` | ✅ Active | MCP stdio server — exposes 24 NetSuite tools, hosts all 10 standard report SQL templates |
| `netsuite_query.py` | ✅ Active | Direct OAuth fallback (read, `--create`, `--update`) |
| `netsuite_slack_bridge.py` | ✅ Active | Slack ↔ NetSuite event glue |
| `slack_upload_file.py` | ✅ Active | Slack `files.uploadV2` — 6-source token resolution (PR #57) |
| `render_netsuite_mcp_logs.py` | ✅ Active | JSONL → daily markdown for `memory/logs/netsuite-mcp/*.md` |
| `cron_executor.py` | ✅ Active | Cron job executor — patches OpenClaw's broken built-in scheduler (`job.name === undefined`, PR #53) |
| `cron_executor_daemon.py` | ✅ Active | Persistent daemon — resurrected by session-start hook after container restarts (PR #54) |
| `cron_daemon.py` | ✅ Active | Thin daemon entrypoint wrapper |
| `cron/ensure_daemon.py` | ✅ Active | Idempotent watchdog — keeps the daemon alive |
| `universal_cron_runner.py` | ✅ Active | Lower-level runner — parses `cron/jobs.json` and dispatches |
| `weekly_team_setup.py` | ✅ Active | Weekly IAX team setup (Monday tickets, Friday wrap-up) |
| `weekly_team_runner.py` | ✅ Active | Cron entrypoint — `monday` / `friday` mode dispatch |
| `weekly_team_wrapper.py` | ✅ Active | Wrapper that adds logging + failure reporting around the runner |
| `daily_sync_status.py` | ✅ Active | Builds the daily cron sync status DM to Peter |
| `memory_backup/backup_memory.py` | ✅ Active | Nightly `memory/` → S3 backup (`memory_s3_backup` cron) |
| `memory_backup/restore_memory.py` | ✅ Active | Restore `memory/` from an S3 snapshot |
| `memory_backup/preflight_s3.py` | ✅ Active | Credential + bucket reachability check before a backup run |
| `memory_backup/s3lite.py` | ✅ Active | Dependency-free S3 signer/client used by the backup scripts |
| `report_store/report_store.py` | ✅ Active | Local report store behind `get_stored_report` / `list_stored_reports` |
| `report_store/email_fetcher.py` | ✅ Active | IMAP fetch for emailed NetSuite reports (`fetch_email_report`) |
| `report_store/filter_subsidiary.py` | ✅ Active | Subsidiary slicing for stored reports |
| `report_store/lessons.py` | ✅ Active | Nightly lesson distillation (`lessons_distil` cron) |
| `smoke_test.py` | ✅ Active | End-to-end smoke check (Slack DM send path) |
| `bootstrap-validate.py` | ✅ Active | Environment validator — tier mapping, memory integrity. Honours `OPENCLAW_WORKSPACE` so it also runs against a plain checkout in CI |
| `validate_routing_consistency.py` | ✅ Active | Asserts `models.json`, both routers, and the tier tables in `ROUTING.md` / `SKILL.md` / `README.md` all agree, and that no retired model ID lingers |
| `validate_readme_counts.py` | ✅ Active | Re-derives the skill / MCP-tool / report / cron counts from the tree and fails if this README disagrees, or if a skill is unregistered |
| `validate_cron_jobs.py` | ✅ Active | Validates every `cron/jobs.json` schedule and checks the script it invokes exists. An enabled job with a missing script fails; a disabled one warns |
| `slack_dm_router.py` | 💤 Dormant | Model routing for Slack DMs (earlier 4-tier design) |
| `slack_handler.py`, `slack_handler_builtin.py`, `slack_handler_simple.py` | 💤 Dormant | Slack event handler variants (earlier 4-tier design) |
| `slack_model_router.py` | 💤 Dormant | Model selection router |
| `slack_router_direct.py` | 💤 Dormant | Direct-routing experiment |
| `report_store/smoke_subsidiary.py`, `report_store/test_end_to_end.py` | 🧪 Tests | Report-store checks, run by hand |

Docs living alongside the scripts: `scripts/SLACK_HANDLER_SETUP.md`, `scripts/cron/README.md`, `scripts/memory_backup/README.md`.

### 5.2 `/skills/` — Agent skills (24 active)

Always-loaded baseline: `automation-hub`, `team-ops`, `wego-slack-channels` (channel-ID routing).

**Skills by domain:**

| Skill | Purpose |
|---|---|
| `wego-netsuite/` | **NetSuite Champion** — SKILL.md + CLAUDE.md + MEMORY.md + `references/` + `knowledge_base/` docs. The largest skill in the repo. |
| `Finance/reconciliation_claw/` | Finance reconciliation — 58 LCC suppliers, listener-first. The agent's role is advisory only; see §5.3 *Finance reconciliation agent* |
| `wego-slack-channels/` | Channel ID → skill routing map (always loaded) |
| `automation-hub/` | Top-level automation strategy (always loaded) |
| `team-ops/` | Jira / team status / standup (always loaded) |
| `wego-automation-ops/` | Cross-functional automation strategy |
| `brain-sync-advanced-format/` | Rich Slack block status reports |
| `weekly-team-setup/` | Monday tickets + Friday wrap, IAX board automation |
| `peter-memory-sync/` | Memory file pruning + consolidation |
| `peter-profile/` | Peter profile reload |
| `dm-model-signature/` | Stamps `🎯 L1/L2/L3/L4` chip on every DM reply |
| `context-aware-response/` | Channel-vs-DM tone shifts |
| `model-providers/` | Provider notes (OpenRouter, OpenAI, direct) |
| `openclaw-nova-mirror/` | Weekly mirror PR builder |
| `ops-sync/` | Heartbeat + sync state |
| `session-analytics/` | JSONL session telemetry |
| `sql-plsql-bigquery/` | BQ / PL/SQL reference for Wego BI work |
| `robot-python-automation/` | RPA / Python automation reference |
| `wego-coding-automation-style/` | Wego Python style guide |
| `wego-github-coding-style/` | Wego GitHub PR conventions |
| `daily-digest-contacts/` | Recipient map for the daily digest |
| `dm-working-indicator/` | Shows a working indicator while a DM turn is in flight |
| `wego-rpa-structure/` | RPA project layout reference |
| `itops/` | IT ops escalation paths |

### 5.3 `/skills/Finance/` — Finance reconciliation agent (LCC)

The one skill whose job is mostly **to stay out of the way**. Reconciliation is run
end to end by a server-side listener on the AlphaBot host, not by this agent.

| File | Purpose |
|---|---|
| `reconciliation_claw/SKILL.md` | Trigger conditions, the four cases the agent may act on, and the flow diagram |
| `reconciliation_claw/CLAUDE.md` | Behavioural contract — what the agent can and cannot do, and the phrase blocklist |
| `reconciliation_claw/references/suppliers.md` | 58 LCC supplier keys + trigger phrases. Mirror of the server's `suppliers.json` |
| `reconciliation_claw/references/date-parsing.md` | Natural-language → `YYYY-MM-DD` rules used by the listener's LLM prompt |

**How a run actually happens** — the agent is not in this loop:

```
finance user posts in #finance-automation-claw   (C0AVB4VR708, production)
  OR internal user posts in #proj-alphabot-testing (C090HF85F2P, testing)
      │  @Data Automation's Claw <text> + .xlsx/.xls/.csv
      │  listener polls each channel every ~10s
      ▼
slack_listener.py  (on the AlphaBot server)
  ├─ requires an @mention of U0AHNGSDQ3W from a REAL user + a file attached
  ├─ ignores every bot-authored message — including this agent's
  ├─ raw JSON path → validate → run robot
  ├─ NL path       → regex pre-parser, then OpenAI gpt-4o-mini fallback → validate → run robot
  └─ replies in the user's own thread, uploads output, sends email
```

**The agent's role is read-only advisory.** Four cases, from `SKILL.md`:

| Case | Where | Correct behaviour |
|---|---|---|
| A | Either bridge channel | **Silence.** The listener has it. It also auto-deletes bot posts matching narrative patterns within ~10s, so anything posted is deleted noise. No "must respond" exception. |
| B | Any other channel or DM | Redirect to a bridge channel. Do not repost on the user's behalf — a bot @mention does not trigger the listener. |
| C | "What suppliers can I run?" | Answer from `references/suppliers.md`; don't dump the table. |
| D | "How does this work?" | Two sentences, then stop. |

**Why the contract is this blunt.** Both files carry an explicit phrase blocklist,
added after two logged incidents: on 2026-04-27 the agent posted fabricated server
health (`AlphaBot offline`, `Port 3002 unreachable`, retry counts) into a bridge
thread where the listener had in fact succeeded; on 2026-04-29 it posted a
`*<Supplier> reconciliation confirmed*` block with `Run Parameters` and a
`Transaction Profile` into Peter's DM, for a file the listener never saw and a run
that never happened. Neither state is observable from Slack. The rule is that if a
draft contains a blocklisted phrase, the whole draft is discarded and nothing is
posted — **narration is the bug**, and silence is the correct output.

The listener's own source is vendored in `test_py/` for review — see §5.9 *Remaining top-level directories*.

### 5.4 `/agents/nova-pro/` — Agent configuration

| File | Purpose |
|---|---|
| `MANIFEST.md` | **Skill loading rules** — channel ID → skill mapping, keyword routing, execution rules. Master routing table. |
| `PERSONA.md` | Agent identity and operating rules |
| `USER.md` | Peter profile, authorized channels, team contacts |

### 5.5 `/cron/` — Scheduled jobs (7 defined, 3 enabled)

`jobs.json` defines all jobs. Schedules in **UTC** (DXB = UTC+4). `enabled: false` jobs stay defined but are not dispatched.

| Job | Schedule | Enabled | Action |
|---|---|---|---|
| `memory_s3_backup` | `0 23 * * *` (daily 23:00 UTC) | ✅ | Back up `memory/` to S3 |
| `lessons_distil` | `30 23 * * *` (daily 23:30 UTC) | ✅ | Distil the day's sessions into `memory/knowledge/learned_lessons.md` |
| `nova_claw_pull_sync` | `5 * * * *` (hourly :05) | ✅ | `git pull origin main` into the workspace |
| `openclaw_nova_mirror` | `30 3 * * 0` (Sun 03:30 UTC) | ⛔ | Open mirror PR to `wego/openclaw-nova`. **Broken:** its command runs `scripts/nova_mirror_pr.py`, which is not in the repo. Disabled, so it is not failing — but it cannot work until the script is restored. |
| `weekly_team_monday` | `0 5 * * 1` (Mon 05:00 UTC) | ⛔ | Create IAX weekly tickets |
| `weekly_team_friday` | `0 5 * * 5` (Fri 05:00 UTC) | ⛔ | Friday wrap-up post |
| `daily_sync_status` | `5 19 * * *` (daily 19:05 UTC) | ⛔ | Post sync status to Peter's DM |

Supporting files in `cron/`: `dispatch_with_routing.sh`, `router_init.sh`, `example_routed_job.sh`.

**Only `cron/jobs.json` is committed.** The daemon's runtime state — `state.json`,
`jobs-state.json`, `executor_state.json`, `daemon.pid`, `locks/*.lock`, `runs/*.jsonl` —
is gitignored: it is rewritten on every tick, and committing it produced a merge
conflict on every mirror sync. Inspect it in the live workspace, not here.

### 5.6 `/memory/` — Session and knowledge memory

| Path | Purpose |
|---|---|
| `daily/YYYY-MM-DD.md` | Daily session logs (dated, append-only) |
| `knowledge/action_tracker.md` | **Audit log** — every state-changing action (one row per write) |
| `knowledge/decisions.md` | Architectural decisions, dated |
| `knowledge/cron_resilience.md` | Cron failure patterns + resurrection notes |
| `knowledge/context_health.md` | Token usage / context cost notes |
| `knowledge/projects.md` | Active project tracking |
| `knowledge/people.md` | Team contact map |
| `knowledge/learned_lessons.md` | Nightly distilled lessons (`lessons_distil` cron output) |
| `knowledge/memory_changelog.md` | Dated changelog of memory/protocol changes |
| `knowledge/session_analytics_tracker.py` | Writes the per-session telemetry rows |
| `knowledge/session_analytics.jsonl` | Per-session telemetry |
| `logs/netsuite-mcp/*.md` | Daily NetSuite MCP tool-call summaries (rendered from JSONL) |
| `state/weekly_team_issues.json` | State for weekly team setup cron |
| `heartbeat-state.json` | Last check timestamps, crisis mode flag |
| `YYYY-MM-DD.md` (root of `memory/`) | Older dated session logs, pre-`daily/` layout |
| `.dreams/` | Short-term recall cache + event stream — **gitignored**, rebuilt each session |

### 5.7 `/model-routing/` — 5-tier routing system

| File | Purpose |
|---|---|
| `ROUTING.md` | Full 5-tier spec (L1+L3=Sonnet 4.6, L2=GPT-4o-mini, L4=Opus 4.8, L5=GPT-5.5) — Haiku removed 2026-06-16, Opus 4.7 retired 2026-08-11 |
| `AGENT_ROUTING_GUIDE.md` | How the router chooses tiers |
| `HOW_TO_UPDATE_MODELS.md` | Model-version bump procedure |
| `IMPLEMENTATION_CHECKLIST.md` | Routing rollout checklist |
| `SETUP_FROM_HERE.md` | First-run setup |
| `SLACK_INTEGRATION.md` | Slack handler integration notes |
| `TEAM_SETUP_GUIDE.md` | Team onboarding |
| `model_router.py` | Task classification engine |
| `agent_router.py` | Agent-side wrapper |
| `nova_router_wrapper.py` | OpenClaw integration wrapper |
| `context_health.py` | Token / cost monitor |
| `generate_config.py` | Config codegen |
| `models.json` | Per-tier model registry |
| `README.md` | Directory overview |
| `router-integration.md` | How the router hooks into OpenClaw |

### 5.8 `/knowledge/` — Company knowledge

| Path | Purpose |
|---|---|
| `company/glossary.md` | Wego internal glossary (loaded on-demand on "what is X?" keywords) |
| `company/org-structure.md` | Org chart and reporting lines |
| `company/systems-architecture.md` | How Wego's systems fit together |
| `company/wego-business.md` | Business model and commercial context |

### 5.9 Remaining top-level directories

| Path | Purpose |
|---|---|
| `agents/nova-pro/` | Agent config — `MANIFEST.md`, `PERSONA.md`, `USER.md`, `OPERATING.md` |
| `audits/` | Point-in-time architecture audits (`2026-06-ARCHITECTURE_AUDIT.md`) |
| `docs/` | Setup runbooks — `CRON_EXECUTOR_SETUP.md` |
| `jira/` | Jira board notes and per-project folders (`README.md`) |
| `logs/` | Runtime log destination. **Log files are gitignored**; only `.gitkeep` is committed, because `universal_cron_runner.py` opens a `FileHandler` here without creating the directory first. |
| `test_py/` | **Finance listener source**, vendored here for review before deployment to the AlphaBot host — not run from this repo. `slack_listener.py` (the reconciliation listener — §5.3 *Finance reconciliation agent*), `nova_api.py` (Flask trigger API inside the AlphaBot container, deployed at `/config/rpa/openclaw/Finance/Supplier/LCC/`), `skip_keywords.py` (Robot pre-run modifier), `suppliers.json` (58 LCC suppliers — the source `references/suppliers.md` mirrors) |
| `.openclaw/` | Local OpenClaw instance config carried with the repo |

---

## 6. Key configuration files

| File | Location | Purpose |
|---|---|---|
| `openclaw.json` | `/home/openclaw/.openclaw/openclaw.json` | Platform config — models, channels, streaming, threading, MCP servers, env injection |
| `openclaw.env` | `/home/openclaw/.openclaw/cron/openclaw.env` | Secrets — `GITHUB_TOKEN_V4`, `JIRA_API_TOKEN`, `JIRA_EMAIL`, `SLACK_BOT_TOKEN_NETSUITE_CHAMPION`, NetSuite TBA |
| `.env.example` | repo root | Template for local dev — placeholders only, never real values |
| `.gitignore` | repo root | Excludes secrets, `__pycache__`, cron runtime state, log files, agent caches, archives |
| `.gitattributes` | repo root | Forces LF endings; marks binaries and append-only JSONL |
| `.github/workflows/validate.yml` | `.github/` | CI — compiles all Python, parses all JSON/JSONL, runs the four validators, scans for committed credentials, and rejects runtime artifacts |
| `.github/pull_request_template.md` | `.github/` | PR checklist — scope, validators, restart-needed flag, memory logging |
| `.github/CODEOWNERS` | `.github/` | Review routing; `model-routing/`, `agents/`, `cron/jobs.json` called out explicitly |

### MCP servers registered via `openclaw mcp set`

| Server | Script | Scope |
|---|---|---|
| `netsuite-mcp-standard-tools-production` | Oracle's SuiteApp | Production reads |
| `netsuite-mcp-standard-tools-sandbox` | Oracle's SuiteApp | Sandbox writes |
| `nova-claw-tools` | `scripts/netsuite_mcp_server.py` | Our 24 custom tools (reports, CSV export, saved searches, Slack upload, logging) |

---

## 7. NetSuite operating rules (excerpt)

Full contract: `skills/wego-netsuite/CLAUDE.md`. Highlights below — **the `§` numbers
in this section refer to sections of that file, not of this README.**

- **§0.1 Response discipline** — ONE message per question. No streaming, no "let me check…", no intermediate posts.
- **Rule 2** — Reads to prod, writes to sandbox. No exceptions.
- **§5.2 No fake execution** — never claim a write succeeded without a real `internal_id` from a 2xx response in this turn. Two real fabrication incidents on 2026-05-12 drove this rule.
- **§5.8 State the resolved record type first** — every write reply opens with *"Understood: creating a `<canonical_type>` (NetSuite <Friendly Name>). URL will use `<filename>.nl`."* before any tool call.
- **§5.10 BU Code field** — always `cseg_msa_bu_code`. Never `custcol_wego_bu_code`, never `class`. Resolved live via `customrecord_cseg_msa_bu_code`.
- **§5.11 Bulk listings** — `SELECT COUNT(*)` first. Explicit export verbs (`download`, `export`, `csv`, `attach`) go straight to `export_suiteql_to_csv`. Ambiguous "show me" with >50 rows → offer 3 options (filter / top-N / export).
- **§5.13 Standard reports** — use `run_standard_report`, never re-draft SuiteQL for the 10 named reports.
- **§5.14 CSV delivery** — always upload to Slack via `upload_file_to_slack`. Never leave at `/tmp/...`. Failure path = one short message with path + error, **never** inline-dump rows as fallback.
- **Sandbox URL paths are exact** — `vendbill.nl` (not `vendorbill.nl` / `bill.nl`). Hand-constructed URLs are forbidden — always use the tool's returned `ui_url`.

---

## 8. Key decisions log

| Date | Decision | Details |
|---|---|---|
| 2026-06-09 | `#netsuite-dev-agent` registered (`C0B9A8ZRM5X`) | Master access — same routing as `#netsuite_champion`. Peter's dev/QA channel for validating changes before they touch live finance channels. |
| 2026-06-09 | Standing rule: restart heads-up on code changes | When a change touches a long-running OpenClaw process (e.g. `netsuite_mcp_server.py`), proactively tell Peter the container needs a restart for the new code to take effect (MEMORY.md §4). |
| 2026-06-09 | `get_role_permissions` via existing `restlet_companion` (PR #62) | Extends the deployed `restlet_companion.js` with a 4th action `role_permissions`. Reuses existing `NETSUITE_<SCOPE>_RESTLET_*` env vars — no new env vars, no parallel deployment. Replaces the standalone RESTlet from PR #61. |
| 2026-06-09 | §5.18a — Try `get_role_permissions` first | For permission-grid asks, call the new tool; on `RESTLET_HANDLER_STALE` reply with the one-step File Cabinet update path; on `role_load_failed` Akansha widens the integration role's `Setup → Set Up Company → Role` permission. |
| 2026-06-09 | §5.18 — No substitute deliverables (PR #60) | When a filtered ask can't be satisfied exactly, name the blocker + unblocker + stop. Never dump an unfiltered substitute. 5 forbidden lead-in phrases added to §7 tripwire. |
| 2026-06-09 | Atomic access-audit + self-building queries (PR #59) | `export_access_audit` ships 3 CSVs atomically; `discover_table` grounds queries in live schema instead of guessing. §5.15 (multi-part atomic), §5.16 (self-building queries), §5.17 (always respond) rules added. |
| 2026-05-22 | Slack token resolution hardened (PR #57) | `slack_upload_file.py` now checks 4 env var names + parses `openclaw.env` directly. §5.14 forbids inline-fallback on upload failure. |
| 2026-05-21 | Interco BS + CSV-to-Slack (PR #56) | `interco_balance_sheet` filters by GL code (not `tointersubsidiary`). `slack_upload_file.py` ships. |
| 2026-05-21 | +2 standard reports (PR #55) | `interco_balance_sheet`, `gl_listing_multi` — Beekim's monthly use case. Total = 9. |
| 2026-05-21 | Self-healing cron daemon (PR #54) | Session-start hook resurrects `cron_executor_daemon.py` after container restart. |
| 2026-05-21 | Cron executor fix (PR #53) | Patches OpenClaw's `job.name === undefined` scheduler bug. |
| 2026-05-20 | Standard reports tool (PR #52) | 7 server-side SuiteQL templates with bounded-token export. |
| 2026-05-20 | MCP activity logging (PR #51) | JSONL per tool call + daily markdown renderer. DM "give me logs" refreshes. |
| 2026-05-20 | BU Code rule | `cseg_msa_bu_code` enforced as the only correct field. |
| 2026-05-19 | Haiku removed from NetSuite | Permanently banned in NetSuite channels — too weak. Sonnet 4.6 is the floor. |
| 2026-05-19 | Bulk-listing protocol (PR #50) | §5.11 — 1-turn flow on explicit export intent. |
| 2026-05-13 | MCP fully wired | `openclaw mcp set` (not `plugins.entries.mcp`). Credentials baked into env config. |
| 2026-05-12 | Sonnet 4.6 default | All channel sessions on Sonnet via OpenRouter. |
| 2026-05-12 | Streaming off | No verbose intermediate messages. ONE answer per question. |
| 2026-05-12 | Thread replies | `replyToModeByChatType: channel=all`. Follow-ups inherit thread context. |
| 2026-05-12 | Channel containment (§5.1) | Never cross-post between channels. Driven by a real cross-post incident. |
| 2026-05-12 | Direct OAuth fallback | `netsuite_query.py` works when MCP gateway is unavailable. |
| 2026-05-11 | Cron payload format | `payload.kind=systemEvent` (not `agentTurn`). Config path in workspace. |

---

## 9. Jira boards

| Board | Project | URL |
|---|---|---|
| IAX | AI Automation | https://wegomushi.atlassian.net/jira/software/projects/IAX/boards/721 |
| NDS | NetSuite | https://wegomushi.atlassian.net/jira/software/projects/NDS/boards/753 |

---

## 10. Support

| Contact | Role |
|---|---|
| Peter Atef (`peter.atef@wego.com`) | Owner / Operator |
| Madan Kumar (`madan@wego.com`) | OpenClaw Platform |
| Akansha (`akansha@wego.com`) | NetSuite Developer — sandbox→prod promotion, role/permission grants, schema changes |
| Beekim (`beekim@wego.com`) | Sr Finance Manager — owner of monthly interco BS + GL listing |
| Cecilia / Li Ping | Period close approvers |

**Repository:** https://github.com/wego/openclaw-nova — the canonical repo. The `openclaw_nova_mirror` cron opens the weekly PR that syncs the live OpenClaw workspace into it.

---

## 11. Quick start (for a new operator)

1. Read `CLAUDE.md` (operating contract) and `AGENTS.md` (session bootstrap).
2. Skim `MEMORY.md` § "Section A — Reference state" for current architecture facts.
3. Check `cron/jobs.json` for the schedule (runtime state is gitignored — read it in the live workspace).
4. Validate the checkout:
   ```bash
   OPENCLAW_WORKSPACE="$PWD" python3 scripts/bootstrap-validate.py
   python3 scripts/validate_routing_consistency.py
   python3 scripts/validate_cron_jobs.py
   python3 scripts/validate_readme_counts.py
   ```
   CI runs all four on every push and PR (`.github/workflows/validate.yml`).
5. Use `SKILL_REGISTRY.md` to find the right skill, and `agents/nova-pro/MANIFEST.md` for the channel → skill routing table.
6. For NetSuite work, read `skills/wego-netsuite/CLAUDE.md` end-to-end before touching any channel.

---

*Last updated: 2026-08-11 — three changes. (1) Repo contents replaced with the current
OpenClaw workspace snapshot; every `NOVA_CLAW` folder/repo reference renamed to
`openclaw-nova`. (2) Opus 4.7 retired — L5→L4, L6→L5, now a 5-tier ladder. (3) Hygiene
pass: runtime state and a leaked Slack token removed, `agents/nova-pro/` paths repaired,
8 ghost skill references purged (closes audit P1.6), CI + two new validators added.
Added §4 documenting the persistent-memory
architecture actually in use (read path, write path, self-learning loop, S3 + git
durability) — promoted above the directory listing since everything else depends on
it — and §5.3 documenting the Finance reconciliation agent and why its contract is
as blunt as it is. Corrected three claims that did not match the code: the hourly
pull is a merge rather than a hard reset, `openclaw_nova_mirror` is broken because
its script is absent, and the reconciliation listener parses NL with OpenAI
`gpt-4o-mini` — not Claude Haiku 4.5, which two Finance docs claimed and which is
forbidden by policy elsewhere in this repo. All README counts are now machine-checked
against the tree by `scripts/validate_readme_counts.py` (24 skills, 24 MCP tools,
10 standard reports, 7 cron jobs / 3 enabled). Full detail:
`memory/daily/2026-08-11.md`.*

*Prior update: 2026-06-09 — Phase 1 architecture sync (PR title `[audit] 2026-06 architecture sync + stale cleanup`). Synced through PRs #59–#62 plus 2026-06-09 standing rules. See `audits/2026-06-ARCHITECTURE_AUDIT.md` for the full P1/P2/P3 findings.*
