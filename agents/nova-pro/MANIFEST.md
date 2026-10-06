---
name: Data Automation's Claw-PRO Manifest
version: 1.5
last_updated: 2026-08-11
---

# MANIFEST.md - Skill Loading & Tool Index

## Always Loaded

These files are loaded on every session regardless of context:

- `agents/nova-pro/PERSONA.md`
- `agents/nova-pro/USER.md`
- `skills/automation-hub/SKILL.md`
- `skills/team-ops/SKILL.md` (also covers Jira IAX/NDS triage)
- `skills/wego-slack-channels/SKILL.md` (channel ID → skill routing)
- **DM context (Slack Direct)**: `skills/dm-model-signature/SKILL.md` (mandatory tier signature per OPERATING.md)

---

## Personal Use — Peter Direct (Override Priority)

When Peter is using OpenClaw UI directly (not from a Slack channel):
- **No channel-based routing restrictions apply**
- Load skills based on query intent (Step 2) with full access to all skill files
- Identity confirmed via OpenClaw UI session (peer.id = PETER_SLACK_USER_ID_TODO) — no Slack channel context present
- Default model: L1 (Sonnet 4.6) for DMs; L3 (Sonnet 4.6) for channel @mentions — same model, different chip; L4 (Opus 4.8) for strategy and highest-stakes work; L5 (GPT-5.5) manual only. Haiku removed 2026-06-16; Opus 4.7 retired 2026-08-11.

If no Slack channel ID is detected in the query context, treat as personal use and proceed to Step 2 directly.

---

## Step 1 - Channel-Aware KB Loading (Highest Priority)

When a query originates from a Slack channel, check the source channel ID BEFORE any keyword-based loading. Load only the KB doc(s) mapped to that channel.

| Source Channel ID | Channel Name | Load These Files |
|---|---|---|
| C08N2T0CARE | netsuite_ap | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/knowledge_base/netsuite_ap.md |
| C08N2SY3HFS | netsuite_ar | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/knowledge_base/netsuite_ar.md |
| C08MCK3NJTX | netsuite_gl_and_reporting | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/knowledge_base/netsuite_gl_and_reporting.md |
| C08MHS9PMFC | netsuite_tax | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/knowledge_base/netsuite_tax.md |
| C08MCK8936Z | netsuite_adminsupport | (do not auto-respond — human triage channel) |
| C08LZTG1YR5 | netsuite_ota | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/knowledge_base/netsuite_ota.md |
| C0B1T3B4RMH | netsuite_champion (master — domain resolved from message prefix or classifier) | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/references/channel_routing.md + skills/wego-netsuite/references/prompt_templates.md |
| C0B9A8ZRM5X | netsuite-dev-agent (master — Peter's dev/QA channel for testing changes before they reach live finance channels; identical routing to netsuite_champion) | skills/wego-netsuite/SKILL.md + skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/TOOL_RESPONSE_MANDATE.md + skills/wego-netsuite/MEMORY.md + skills/wego-netsuite/references/channel_routing.md + skills/wego-netsuite/references/prompt_templates.md |
| C07EGK6JU8Y | data-marketing-reports | knowledge/company/wego-business.md |
| C08T81REV6Y | alphabot-masters | skills/automation-hub/SKILL.md + skills/wego-coding-automation-style/SKILL.md |
| C090HF85F2P | proj-alphabot-testing (testing bridge — internal team) | skills/Finance/reconciliation_claw/SKILL.md + references/suppliers.md + references/date-parsing.md |
| C0AVB4VR708 | finance-automation-claw (production bridge — finance team) | skills/Finance/reconciliation_claw/SKILL.md + references/suppliers.md + references/date-parsing.md |

Rules:
- For NetSuite channels: **always load SKILL.md + CLAUDE.md + MEMORY.md** first (architecture, 5-rule operating contract, the 15 OpenClaw env vars, hard guardrails). Then load the channel-specific `knowledge_base/netsuite_*.md` for domain detail.
- The architecture-override banner at the top of each `knowledge_base/netsuite_*.md` is authoritative: **OpenClaw calls Oracle's NetSuite MCP Standard Tools directly. There is no Python listener, no `netsuite_mcp` Python module to import, no `requests-oauthlib` to install.** If a section below the banner mentions a "listener", "gateway", or "Python tools", treat it as legacy prose — the operating contract is `SKILL.md` + `CLAUDE.md`.
- Load `references/finance_tools.md`, `suiteql_recipes.md`, `dimension_aliases.md`, `governance.md`, `netsuite_capabilities.md` on demand when the user's question needs deeper recipes.
- **Execute queries DIRECTLY in NetSuite channels.** When a user asks a NetSuite question in any of the six channels (or in an authorised DM), call the Oracle MCP tool that answers it and return the formatted result. Do **NOT** narrate internal steps ("Let me check…", "Let me try a different approach…", "Need to install requests…", "Let me check jobs.json…"). Do **NOT** describe edits you intend to make to skill files unless the user is explicitly asking for a code change. Do **NOT** invent files, commits, or pushes that you didn't actually make — that is hallucination and breaks finance trust.
- If no channel ID in context, proceed to Step 2.

---

## Step 2 - Query Intent Classification (No Channel Context)

When no channel ID is present, classify the query intent before loading skills. Pick the best-fit intent and load only what that intent requires.

| Intent | Trigger Signals | Load These Files |
|---|---|---|
| Finance Reconciliation | run reco, reconciliation, supplier reco, plus any of the 58 LCC supplier names (jazeera, flydubai, indigo, salamair, ajet, airblue, akasaair, …), xlsx attached + supplier name + dates | skills/Finance/reconciliation_claw/SKILL.md + references/suppliers.md + references/date-parsing.md |
| NetSuite | netsuite, subsidiary, AP, AR, GL, invoice, vendor, bill, tax, VAT, period close (note: "reconcile/reconciliation" alone is ambiguous — only route here if combined with NetSuite-specific terms) | skills/wego-netsuite/SKILL.md + relevant knowledge_base/*.md |
| Automation Build | n8n, workflow, webhook, robot, python, bot, airflow, script, build, automate | skills/automation-hub/SKILL.md + references/n8n-patterns.md |
| Jira / Sprint | jira, IAX, NDS, ticket, sprint, board, stale, blocked, triage | skills/team-ops/SKILL.md |
| Team / Capacity | team, assign, capacity, ayush, likith, peter, akansha, onboard, blocker | skills/team-ops/SKILL.md + knowledge/company/org-structure.md |
| Code Review | review, PR, code, refactor, style, naming, module, test | skills/wego-coding-automation-style/SKILL.md + skills/wego-github-coding-style/SKILL.md |
| Strategy / Architecture | strategy, architecture, design, plan, roadmap, infra, stack | Load Opus model + knowledge/company/systems-architecture.md |
| Company / Business | wego, company, product, markets, revenue, MENA, HCN, GDS | knowledge/company/wego-business.md + knowledge/company/glossary.md |

**Finance Reconciliation precedence:** if both "Finance Reconciliation" and "NetSuite" match, prefer Finance Reconciliation when (a) an xlsx is attached, OR (b) a supplier name from `references/suppliers.md` is present, OR (c) the source channel is one of the bridge channels: `#finance-automation-claw` (`C0AVB4VR708`, finance team production) or `#proj-alphabot-testing` (`C090HF85F2P`, internal team testing). Otherwise prefer NetSuite.

Multi-intent queries: Load docs for all matched intents. Cap at 3 intent categories. If more than 3 match, ask for clarification.

---

## Step 3 - Keyword Fallback (Last Resort)

Used when neither a channel ID nor clear intent classification matches.

| Keywords in Request | Load File |
|---|---|
| reco, reconciliation, run reco, supplier reco, jazeera, flydubai, salamair, indigo, ajet, airblue, akasaair, atlas, belair, bingtrip, brightsun, citizenplane, dadabhai, dnata, fitsair, flyarystan, flydeal, flyin, flynas, holiday tours, hong ngoc, jordan airlines, kanoo, letsfly, monde, moonline, nesma, nokair, quality aviation, regency, samad, sereneair, spicejet, tsy, tidesquare, transnusa, trans arabian, transavia, ur airline, wonder, al madar, air arabia, airindia express, blue horizon, cit malaysia, chamwings | skills/Finance/reconciliation_claw/SKILL.md + references/suppliers.md + references/date-parsing.md |
| n8n, workflow, webhook, node, trigger, credential | skills/automation-hub/references/n8n-patterns.md |
| jira, JQL, board, sprint, IAX, NDS, stale, ticket | skills/team-ops/SKILL.md |
| team, org, capacity, assign, report, onboard | knowledge/company/org-structure.md |
| stack, system, infra, architecture, platform, tool | knowledge/company/systems-architecture.md |
| wego, company, product, business, markets, revenue, mena, finance, netsuite | knowledge/company/wego-business.md |
| what is, define, glossary, acronym, term | knowledge/company/glossary.md |
| cron, failure, resilience, down, broken, error | memory/knowledge/cron_resilience.md |
| project, status, blocker, milestone | memory/knowledge/projects.md |
| decision, decided, rationale, why | memory/knowledge/decisions.md |

---

## On-Demand Only

Load only when explicitly requested or clearly required:

- memory/knowledge/people.md - when working style or contact info is needed
- memory/knowledge/action_tracker.md - when reviewing or updating task status
- scripts/ - when debugging or modifying live scripts

---

## External Tools (MCP)

| Tool | Connection | MCP ID | Purpose |
|---|---|---|---|
| Slack | MCP | d1f954aa-b930-4277-8bf8-862c5efde5cb | Send messages, read channels, search, DM Peter |
| Jira / Confluence | MCP | 01934f1e-d7f4-4cc5-8894-e5f48e7cbdfa | Query/update issues, read Confluence |
| GitHub | Env Var GITHUB_TOKEN_V4 | - | Read/write openclaw-nova; read alphabot (read-only) |
| Gmail | MCP | c2b3d5cb-2b67-4a15-a75b-3be2901d1847 | Read-only monitoring; never send unless instructed |
| Calendar | MCP | 014dfb76-a956-4cb6-ad64-aaa3b71d3d39 | Meeting lookup, scheduling support |
| Fireflies | Env Var FIREFLIES_TOKEN + MCP | 4e7e3e22-d7b2-4c03-9f5d-eb0a897d4bfa | Fetch transcripts and summaries |

Auth notes:
- GitHub uses GITHUB_TOKEN_V4 from WegoClaw environment variables (not MCP)
- All other tools connect via MCP ID listed above

---

## Jira Configuration

| Board | Project Key | Board ID | URL |
|---|---|---|---|
| AI Automation | IAX | 721 | https://wegomushi.atlassian.net/jira/software/projects/IAX/boards/721 |
| NetSuite | NDS | 753 | https://wegomushi.atlassian.net/jira/software/projects/NDS/boards/753 |

Auth: JIRA_EMAIL=peter.atef@wego.com + JIRA_API_TOKEN (from WegoClaw secrets)

---

## Tool Operating Rules

Jira:
- Always check current ticket status before updating
- Flag tickets with no update >24h during active sprint
- Use JQL for bulk queries

GitHub:
- Run auth preflight before any push or PR action
- PRs require Peter review before merge
- AlphaBot repo (wego/alphabot) is read-only - never push there

Slack:
- Never send to group or public channels without Peter review
- Use slack_search_public_and_private to find thread context before messaging
- Vendor/supplier messages must go through designated channels
- Never DM stakeholders on Peter behalf without explicit instruction
- Respond in-thread when source is a Slack thread - preserves context per thread ID

BigQuery:
- Do not attempt BQ queries unless explicitly given credentials and full context
- Delegate BQ work to Ayush unless Peter says otherwise

Memory:
- Daily log: memory/daily/YYYY-MM-DD.md - write here after each meaningful session
- Long-term: MEMORY.md - update when something is worth remembering across weeks

---

## Model Routing

| Task Type | Model | Rationale |
|---|---|---|
| Simple lookups, status checks, formatting | claude-sonnet-4.6 | Same model as L3; uniform quality floor. Haiku removed 2026-06-16. |
| General operations, planning, code review | claude-sonnet (DEFAULT) | Balanced capability |
| Strategy, architecture decisions, complex reasoning | claude-opus | When depth matters |

Routing is query-content-driven with channel floor enforcement:
- L1 Nano: mechanical/cron tasks only
- L2 Fast: generic queries with no technical signals (default for personal use, data-marketing channel)
- L3 Standard: technical queries (score >= 4) OR any query from a NetSuite/alphabot channel (channel floor)
- L4 Premium (Opus 4.8): architecture/strategy/exec signals detected, OR auto-escalated when confidence is low. Top Anthropic tier — never escalates further.
- L5 (GPT-5.5): manual only — cross-provider second opinion, never keyword-routed

Channel floor (netsuite_*, alphabot-masters) guarantees L3 minimum regardless of query length. Complexity scoring and L4 immediate keywords can still elevate above the floor. See model-routing/ROUTING.md and model_router.py for full logic.
