# 2026-06 Architecture Sync — Audit & Stale Cleanup

**Audit window:** post PR #57 (2026-05-22, last README sync) → 2026-06-09 (today).
**Scope:** Whole repo except `skills/Finance/reconciliation_claw/` (untouched per request).
**Status:** Phase 1 of the 3-phase architecture refresh.

Findings ranked **P1** (fix now, in this PR), **P2** (recommend, separate PR), **P3** (note only, no rush).

---

## Summary

| Severity | Count | This PR fixes |
|---|---|---|
| P1 — must fix now | 6 | 5 (one deferred — see #5) |
| P2 — recommend follow-up | 5 | 0 |
| P3 — note only | 4 | 0 |

**This PR's net effect:** docs/cleanup only. No runtime behavior change. Verified by `git diff --stat` — no edits to `netsuite_mcp_server.py`, MCP tool registrations, dispatch branches, cron job definitions, or skill files referenced at runtime by MANIFEST routing.

---

## P1 — Fixed in this PR

### P1.1 — README `§3.3 MCP tools exposed` says "current count: 15" — actually 17

**Evidence:** `scripts/netsuite_mcp_server.py` TOOLS list contains 17 unique tool registrations (verified by `grep -oE '"name": "[a-z_]+"'`):
```
create_journal_entry_from_csv  create_record  create_vendor_bill_from_csv
discover_table                 export_access_audit  export_suiteql_to_csv
get_role_permissions           metadata_catalog  read_record
refresh_mcp_logs               resolve_csv_dimensions  run_standard_report
run_suiteql                    update_journal_entry_from_csv  update_record
update_vendor_bill_from_csv    upload_file_to_slack
```

README §3.3 also lists phantom entries `execute_create` / `execute_update` as separate tools — they're internal helper functions, not MCP tools.

**Missing from README:**
- `discover_table` (PR #59 — schema discovery)
- `export_access_audit` (PR #59 — atomic 3-CSV bundle)
- `get_role_permissions` (PR #61 + #62 — via existing restlet_companion)
- `resolve_csv_dimensions` (predates README rewrite)
- `update_vendor_bill_from_csv` (predates README rewrite)
- `update_journal_entry_from_csv` (predates README rewrite)

**Fix:** README §3.3 rewritten to 17 tools, grouped by purpose. Phantom `execute_*` removed.

### P1.2 — README `§7 Key decisions log` stops at 2026-05-22 (PR #57)

**Missing decisions (PR #59 → PR #62, plus 4 standing rules added in this session):**
- PR #59 — Atomic access-audit + self-building queries + always-respond rules (§5.15, §5.16, §5.17)
- PR #60 — §5.18 No substitute deliverables + employeerolesforsearch→employeeroles SQL fix
- PR #61 — Initial role-permissions RESTlet (superseded by #62)
- PR #62 — `get_role_permissions` via existing `restlet_companion.js` — no new env vars
- 2026-06-09 — Standing rule: container-restart heads-up on every code-touching change (MEMORY.md §4)
- 2026-06-09 — `#netsuite-dev-agent` (`C0B9A8ZRM5X`) registered as Peter's dev/QA channel

**Fix:** §7 extended with 6 new rows, footer updated to 2026-06-09.

### P1.3 — `CRON_SCHEDULE.md` lists `netsuite_kb_sync` which doesn't exist in `cron/jobs.json`

**Evidence:**
- `cron/jobs.json` job names: `daily_sync_status, fireflies_daily_digest, fireflies_sync, nova_claw_pull_sync, openclaw_nova_mirror, weekly_team_friday, weekly_team_monday` (7 jobs)
- `CRON_SCHEDULE.md` lists 8 jobs — includes phantom `netsuite_kb_sync` (Mon/Thu 04:00) that doesn't exist
- KB sync was explicitly disabled per `MEMORY.md §4`: *"NetSuite KB sync: DISABLED 2026-04-13 per Peter. Script retained at `scripts/netsuite_kb_sync.py` but cron job removed."*

**Fix:** Drop the row from `CRON_SCHEDULE.md`. Source of truth = `cron/jobs.json`.

### P1.4 — `BOOTSTRAP.md` still present despite explicit "delete after first run" instruction

**Evidence:** `BOOTSTRAP.md` line 33: *"Delete this file (BOOTSTRAP.md). You won't need it again."* — file still in repo, 1399 bytes. The agent has been running for months; BOOTSTRAP.md's first-run setup has long since completed (IDENTITY.md, USER.md, SOUL.md, MEMORY.md all exist with substantial content).

**Fix:** Delete the file.

### P1.5 — README internal inconsistency: dots vs dashes for model IDs

**Evidence:** Same §3.1 table mixes formats:
```
| L1 | openrouter/anthropic/claude-haiku-4-5  | …  (dash)
| L3 | openrouter/anthropic/claude-sonnet-4.6 | …  (dot)
| L4 | openrouter/anthropic/claude-opus-4-7   | …  (dash)
```

OpenRouter's actual ID format is **dashes** (confirmed by `memory/knowledge/session_analytics_tracker.py` lines 17-18 using `claude-sonnet-4-6` and `claude-opus-4-7`). Anthropic SDK accepts dots; OpenRouter requires dashes. The L3 dot was the bug that caused channel routing silent failures on 2026-06-09 (see `memory/daily/2026-06-09.md`).

**Fix:** README §3.1 normalised to dashes throughout (matches OpenRouter format actually used at runtime).

### P1.6 — MANIFEST references 4 skill directories that don't exist

**Evidence:**
```
GHOST: skills/channel-kb-router   (referenced in MANIFEST)
GHOST: skills/jira-tracker         (referenced in MANIFEST)
GHOST: skills/looker               (referenced in MANIFEST)
GHOST: skills/meeting-prep         (referenced in MANIFEST)
```

**Risk of auto-fix:** MEDIUM. If MANIFEST is parsed by anything at runtime (`load skills/X` calls fail when X doesn't exist), removing the references could break the loader; if MANIFEST is documentation-only, fix is safe.

**Decision for this PR:** ⚠️ NOT auto-fixed. Flagged here for explicit decision. Recommended action depends on the loader — most likely the loader silently skips missing dirs, in which case removing the references is safe doc cleanup. **Ask before next PR.**

---

## P2 — Recommend separate PR

### P2.1 — `bootstrap-validate.py` model-ID checks use dots (`claude-haiku-4.5`), not OpenRouter dashes

**Evidence:** `scripts/bootstrap-validate.py` lines 46, 49, 53, 77, 82 all use dot format. This is checking MEMORY.md content, which also uses dots (lines 172, 805 etc.) — so the validator passes today. But MEMORY.md uses dots while the live OpenRouter calls use dashes. **The validator checks an inconsistent target.**

**Recommendation:** Decide a single source-of-truth format. If runtime uses dashes (which it does), validator + MEMORY.md should both use dashes. If both formats are acceptable to OpenRouter, document that and stop checking either one.

### P2.2 — 17 skills exist in `skills/` but are NOT referenced in `MANIFEST.md` routing

```
brain-sync-advanced-format, context-aware-response, daily-digest-contacts,
dm-working-indicator, itops, model-providers, peter-memory-sync, peter-profile,
openclaw-nova-mirror, ops-sync, robot-python-automation, session-analytics,
sql-plsql-bigquery, weekly-team-setup, wego-automation-ops, wego-rpa-structure,
wego-slack-channels
```

Some are likely loaded by other mechanisms (e.g. `dm-model-signature` is always-loaded per its own SKILL.md, `peter-memory-sync` runs on schedule, `session-analytics` is a logger). Others may genuinely be orphans.

**Recommendation:** Audit each — for every skill, document one of: (a) channel/keyword routes that load it, (b) script that imports it, (c) "always-loaded baseline" marker, or (d) orphan → delete. Should take ~1 hour. PR title: `[audit] skill loading inventory + orphan removal`.

### P2.3 — 6 dormant Slack-handler scripts (~33 KB total)

```
scripts/slack_dm_router.py        (1.6 KB)
scripts/slack_handler.py          (6.3 KB)
scripts/slack_handler_builtin.py  (7.2 KB)
scripts/slack_handler_simple.py   (7.0 KB)
scripts/slack_model_router.py     (5.3 KB)
scripts/slack_router_direct.py    (6.0 KB)
```

`scripts/slack_dm_router.py` line 1 docstring: *"This script is called by the Slack plugin when a DM arrives"* — `model-routing/SLACK_INTEGRATION.md` marks the integration as `⏳ requires platform team or code update`. So none of these are wired in.

**Recommendation:** Move all 6 to `attic/slack-routing-2026-04/` with a one-line README explaining what they were. Git history preserves the originals; current repo gets cleaner.

### P2.4 — `MEMORY.md` contains contradictory model-routing entries

Three entries in MEMORY.md describe different L1 defaults:
- Line 172: *"L1 (DEFAULT — DMs, general): anthropic/claude-haiku-4.5"*
- Line 495: *"L1: anthropic/claude-sonnet-4.6 (default for DMs)"*
- Line 805: *"L1 (DEFAULT, THE FLOOR): claude-sonnet-4.6 — ALL DMs"*

The history is real (Haiku → Sonnet → Haiku flip-flop), but having three contradictory "current state" claims in the always-loaded MEMORY.md will confuse future sessions about which is the live policy.

**Recommendation:** Keep ONE canonical "current routing policy" block in §A (reference state). Move the historical entries to §B (change log) explicitly dated, so the "current" answer is unambiguous.

### P2.5 — `ENVIRONMENT.md` scope confusion

`ENVIRONMENT.md` is about Kubernetes pod runtime constraints (writable paths, package installs, network policy). It is **not** the env-var inventory. The env-var inventory lives in `skills/wego-netsuite/MEMORY.md §A.7` (NetSuite + Slack secrets).

The user's mental model is "ENVIRONMENT.md = env vars" — file name suggests that. Worth renaming to `RUNTIME.md` or adding a one-line preamble: *"This file documents the Kubernetes runtime. For env-var inventory see `skills/wego-netsuite/MEMORY.md §A.7`."*

**Recommendation:** Add the disambiguating preamble. Low priority.

---

## P3 — Note only

### P3.1 — `MEMORY.md` token size approaching the soft ceiling

883 lines, 43,241 bytes. Roughly 10–13k tokens at GPT/Claude tokenisation rates. Threshold mentioned in Phase 1 plan: 15k. **Not over yet.** Worth monitoring; the rotating-window split (§A always loaded + 30-day decisions + `memory/archive/MEMORY-2026-Hx.md` for older) becomes worthwhile around 15–20k.

### P3.2 — Tool-list + cron-schedule drift will recur

Both have already drifted in 2 weeks. Long-term fix: generator script that reads `netsuite_mcp_server.py::TOOLS` and `cron/jobs.json`, regenerates the corresponding markdown sections. Add to weekly cron. ~50 lines of Python.

### P3.3 — Hardcoded model IDs scattered across files

27 lines across `MEMORY.md`, `scripts/`, `agents/`, `skills/`, `README.md`. Each one is a potential drift point. Centralising in `model-routing/models.json` would prevent the next `4-6 vs 4.6` outage class.

### P3.4 — `scripts/cron_executor.py` has known race patterns

Per `MEMORY.md §B` (PRs #53, #54): repeated ghost-state and stale-`nextRunAtMs` incidents. Recommend a `cron doctor` self-check in `cron_executor_daemon.py` startup that flags inconsistent state. Out of scope for Phase 1; should be in Phase 2 alongside the "per-job last-success age" feature for `daily_sync_status`.

---

## What this PR changes

| File | Change | Lines |
|---|---|---|
| `README.md` | §3.1 model IDs normalised to dashes; §3.3 tool list (15 → 17, phantom entries removed); §7 decisions log (+6 rows); footer updated to 2026-06-09 | doc-only |
| `CRON_SCHEDULE.md` | Removed `netsuite_kb_sync` row | doc-only |
| `BOOTSTRAP.md` | **Deleted** per the file's own instruction | -1 file |
| `audits/2026-06-ARCHITECTURE_AUDIT.md` | NEW — this document | +1 file |

**Runtime files NOT touched:**
- `scripts/netsuite_mcp_server.py` — unchanged
- `scripts/cron_executor*.py` — unchanged
- `cron/jobs.json` — unchanged
- `agents/nova-pro/MANIFEST.md` — unchanged (ghost-skill cleanup deferred to next PR per P1.6)
- `skills/*/SKILL.md` — unchanged
- Any file referenced by a live skill at runtime — unchanged

**Restart needed?** No. This is doc-only; the agent reads skill files fresh per session, and none of the runtime files (MCP server, cron executor, scripts) were touched. The hourly `nova_claw_pull_sync` cron will pull the README/CRON_SCHEDULE updates within an hour of merge.

---

## Open questions for Peter before Phase 2

1. **P1.6 ghost skills in MANIFEST** — safe to remove the 4 references, or are they wired up via something I don't see? (Most likely safe doc cleanup.)
2. **P2.2 unreferenced skills** — happy to do the loading-inventory PR; want me to scope it?
3. **P2.3 dormant Slack scripts** — move to `attic/` or delete entirely?
4. **P2.4 MEMORY.md model-routing dedup** — which version is current today? (My read: L1=Haiku per `dm-model-signature` SKILL.md and `bootstrap-validate.py`, but MEMORY.md line 805 contradicts.)

Phase 2 (NetSuite centralization design) doesn't depend on any of these — happy to start that whenever you say go.
