# MEMORY.md — Operational Memory (Core)

_Last reviewed: 2026-07-01. Owner: Nikhil Gupta / Data Automation's Claw-PRO._
_This is the lean, always-loaded core. Full dated history/changelog → **`memory/knowledge/memory_changelog.md`**._

---

## 1. User Context

- **Name**: Nikhil Gupta
- **Role**: AI & Automation Lead, Wego
- **Email**: nikhil@wego.com | **Slack**: U04H3EB2PTN | **DM channel**: D0AHK0616JW | **TZ**: Asia/Kolkata
- **Preferred time display**: Dubai (DXB, UTC+4) — ALWAYS show times in DXB, NEVER raw UTC. Hard rule.
- **Manager**: Duncan (VP Data, Marketing & Growth) | **Skip**: Ross (CEO)
- **OpenClaw instance**: s-c58f0c35.openclaw.wego.engineering | **Workspace**: /home/openclaw/.openclaw/workspace

---

## 2. Slack Channels (Key Reference)

| Channel | ID | Purpose |
|---|---|---|
| alphabot-masters | C08T81REV6Y | Automation failures, RPA alerts |
| netsuite_learning_hub | C0AR2B27A3U | NetSuite training, R&D |
| netsuite_ota | C08LZTG1YR5 | OTA flights + finance |
| netsuite_ap | C08N2T0CARE | Accounts payable (Nurul) |
| netsuite_ar | C08N2SY3HFS | Accounts receivable |
| netsuite_gl_and_reporting | C08MCK3NJTX | GL, reporting |
| netsuite_adminsupport | C08MCK8936Z | Admin config |
| netsuite-dev-agent | C0B9A8ZRM5X | Nikhil's dev/QA test channel (master access) |
| proj-alphabot-testing | C090HF85F2P | Supplier recon — internal testing |
| finance-automation-claw | C0AVB4VR708 | Supplier recon — production |

---

## 3. Key Relationships

| Person | Role | Notes |
|---|---|---|
| Duncan | COO / manager | duncan@wego.com |
| Ross | CEO | skip-level |
| Akansha Singh | NetSuite owner (replaced GC, Mar 2026) | token/role/access unblocker; FX & report standing instructions |
| Nurul | AP team | netsuite_ap |
| Madan Kumar | OpenClaw platform eng | madan@wego.com |
| Li Ping Low | Finance/NetSuite lead | liping@wego.com |
| Teng Bee Kim (Beekim) | Finance — owns several saved searches/reports | — |
| Sally / Sanal / others | Finance approvers | — |
| Madan, Richard, Mimi, Prateek, Ujjwal, Hansel, Marwa/Nada | eng/HR/data/GDS stakeholders | see changelog §2 |

---

## 4. Active Projects & Standing Decisions

Live project status → Jira (not stored here). Boards: IAX 721 (AI Automation), NDS 753 (NetSuite).

**Standing operating decisions:**
- Team is capacity-based, not siloed.
- Secrets in WegoClaw: `GITHUB_TOKEN_V4` (Nikhil-Wego org), `FIREFLIES_TOKEN`, `JIRA_API_TOKEN`, `NETSUITE_<SCOPE>_*`. Verify before ops. Never commit secrets.
- AlphaBot repo (`github.com/wego/alphabot`) is **read-only** unless Nikhil authorises a write (PR + ask).
- openclaw-nova is the canonical repo (`github.com/wego/openclaw-nova`); the workspace mirrors into it weekly (Sunday PR).
- All production automations need an IAX Jira ticket. Never disable a running automation without logging + notifying.
- **MEMORY.md edits**: never use the `edit` tool (truncation/redaction breaks exact-match) — use `sed`/`python3`/full-file write.
- **Self-improvement / rule changes via PR (STRICT):** Any change to MEMORY.md, SKILL.md, AGENTS.md, memory_changelog.md, or any workspace rule file MUST be committed to a feature branch and exposed as a GitHub PR for Nikhil to review. NEVER push rule/memory/skill changes directly to `main`. No exceptions.
- **Post-PR playbook**: every PR body + end-of-session summary includes: merge order · sync (or "automatic") · restart YES/NO + urgency · exact Slack test + expected reply · what breaks if wrong vs safe · rollback command. **Nikhil merges; the agent never merges.**
- **Restart heads-up**: any change to a long-running process (`scripts/netsuite_mcp_server.py`, `scripts/slack_upload_file.py`, etc.) needs an OpenClaw container restart to take effect — say so plainly at end of session. Doc/skill/`*.md` changes need no restart (read per session).

---

## 5. Active Automations & Systems

| Automation | Owner | Status |
|---|---|---|
| Commission automation | Prateek/Likith | Active |
| HR automations | Peter | Active |
| HCN/Hotels pipeline | Ayush | Active |
| Finance automations | Likith | Active |
| Supplier reconciliation | server listener | **Live** (bridge channels; agent is silent there) |

- Cron: 5 jobs in `cron/jobs.json` (mirror, hourly pull-sync, weekly Mon/Fri, daily_sync_status). Daemon resurrected by `scripts/cron/ensure_daemon.py`.
- **`daily_sync_status` posts ONLY to Nikhil's DM (D0AHK0616JW)** — never a channel.
- Systems: OpenClaw · Jira IAX/NDS · GitHub openclaw-nova (`wego/openclaw-nova`) · AlphaBot (read-only) · weekly mirror.

---

## 6. Model Routing — CURRENT STATE (source of truth: `model-routing/models.json`)

- **L1 (default — DMs, quick ops)**: `anthropic/claude-sonnet-4.6`
- **L2 (legacy batch only)**: `openai/gpt-4o-mini`
- **L3 (channel @mentions)**: `anthropic/claude-sonnet-4.6` (same model as L1; chip shows surface, not model)
- **L4 (strategy/architecture + highest-stakes)**: `anthropic/claude-opus-4.8` — Opus 4.7 retired 2026-08-11
- **L5 (manual only, cross-provider)**: `openai/gpt-5.5` — was L6 until 2026-08-11. There is no L6.
- **Haiku removed entirely (2026-06-16)** — Sonnet is the floor everywhere below L4. Cost trade-off accepted.
- Fallback chain: each tier → `openai/gpt-4o`.
- **DM signature**: end every DM reply to Nikhil with `---` then `:dart: *L1 (Sonnet)*` (actual tier that ran). L4 only on explicit escalation (spawn subagent — no silent escalation).
- **GitHub push**: always show commit hash + URL.

---

## 7. Active Behavioral Rules (index — detail in changelog / skills)

- **BREVITY (rule #1, applies to EVERY reply).** Before sending, check the draft:
  1. **One message.** Not a stream. Do the work silently, post the result once.
  2. **≤120 words** unless a table/file/steps genuinely need more. A one-line
     question gets a 1–3 line answer.
  3. **Zero process narration.** Delete any sentence starting "Let me…",
     "I'll check…", "Found it…", "Running…", "Respawning…", "Now let me…",
     plus anything about which model/tool/table you tried or why it was slow.
  4. **No unsolicited extras** — no alternatives, no "a few things to check on
     your end", no closing offers, no restating the question.
  If the draft fails any of the four, rewrite it before sending. Wordiness is a
  defect, not a style. (Full version: root CLAUDE.md Output Standards.)
- **Autonomy (golden rule):** "check X" → report findings only; don't fix/restore/push unless told "fix/restore/sync". (changelog §9)
- **One message, zero redundancy:** no opening + output + closing; post ONE Slack message per action. No play-by-play / "Let me check…" narration. (changelog §15/§28; skill CLAUDE.md §6.0)
- **No diagnostic leak:** never send raw script/exec/print output to Slack — summarise. (changelog §17)
- **A/P Aging BK delivery format (STRICT):** NEVER upload the raw `.xls`. The conversion is the TOOL's job — `get_stored_report` already picks the `.csv` (NetSuite mails both), converts it to `.xlsx` and returns exactly ONE file path. Upload that path. Do NOT hand-convert with pandas: a hand-rolled version drops the NetSuite title block and produces a different file from the tool's. If you ever receive more than one path or a `.xls`, the pod is running stale code — say so and stop, don't paper over it. **Never hand-inspect the store** (no `ls ~/.openclaw/reports`, no size comparisons, no reading the *consolidated* file to answer a *subsidiary* question — each subsidiary has its own email). **When the requested period was never emailed, the TOOL already serves the latest available and sets `substituted_from`** — relay its note in one line and send the file; never offer the user a choice of periods. (changelog §37, 2026-08-10)
- **Threading:** channel/group replies go in-thread (`replyToMode=all`); DMs flat. Files must land in the SAME thread as the answer. (changelog §29)
- **DM security:** only Nikhil (U04H3EB2PTN) may use the bot via DM; others → deny + email alert + stop. Channels are open. (changelog §17b)
- **Bridge-channel silence:** in `#finance-automation-claw` / `#proj-alphabot-testing` the agent stays silent (listener owns those). Never emit the forbidden supplier-recon phrases. (changelog §20)
- **NetSuite tool-response mandate:** every NetSuite tool call in a channel posts exactly one result (status + id + URL for writes). No fake success. (changelog §32; skill)
- **NetSuite default:** reads default to **production**; sandbox only if explicitly asked. Finance data ALWAYS from NetSuite, never external (Rule 7 in skill).
- **Standard financial reports (`reportrunner.nl?cr=`)** — A/P & A/R Aging, P&L, IS, BS — are the report engine's proprietary logic; **not reproducible via SuiteQL**. Don't rebuild; export from NetSuite. (2026-07-01)
- **Saved searches**: run via `run_saved_search`; when the ask names a filter (approver, vendor, status, date), APPLY it — never dump the full set. Registry: `skills/wego-netsuite/references/saved_searches.json`.
- **Triggers:** "synced brain?" → rich status blocks · "consumed memory info" → analytics · "daily digest with <name>" → contact digest. (changelog §13/§14/§18)
- **Bootstrap validation** runs each session (`scripts/bootstrap-validate.py`) — blocks on stale memory / Haiku references. (changelog §34)

---

## 8. Pending Items

Live pending → Jira (IAX/NDS) + `memory/knowledge/action_tracker.md`. Items without a ticket yet:
- JIRA_API_TOKEN / cron self-upgrade items (see changelog §7).
- _(add here when they arise before a ticket exists)_

---

_Detailed, dated operational history (§7–§35: mirror sync, Jira setup, session analytics, brain-sync, all Slack/model/NetSuite incident logs, supplier-recon spec, etc.) → **`memory/knowledge/memory_changelog.md`**._
