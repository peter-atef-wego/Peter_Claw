# SKILL_REGISTRY.md - Master Skill Index

_Single reference for all skills in openclaw-nova. Updated when skills are added, removed, or versioned._
_Last updated: 2026-08-11_

> Every directory under `skills/` must appear in this file. `scripts/validate_readme_counts.py`
> fails CI if one is missing, so a new skill cannot ship unregistered.
>
> **2026-08-11 cleanup:** removed 8 rows pointing at skill directories that do not
> exist (`jira-tracker`, `channel-kb-router`, `meeting-prep`, `wego-jira`,
> `llm-agents-rag`, `prompt-engineering`, `looker`, `frontend-web` — the P1.6
> "ghost skills" finding in `audits/2026-06-ARCHITECTURE_AUDIT.md`), added 5 rows
> for skills that existed but were never registered, and corrected the NetSuite
> KB filenames, which named files that were never on disk.

---

## Always-Loaded Skills (Every Session)

| Skill | Version | File | Purpose |
|---|---|---|---|
| automation-hub | 1.0 | skills/automation-hub/SKILL.md | Build, debug, review automations (n8n, Robot, Airflow) |
| team-ops | 1.0 | skills/team-ops/SKILL.md | Team capacity, assignment logic, Jira IAX/NDS triage, onboarding |
| wego-slack-channels | 1.0 | skills/wego-slack-channels/SKILL.md | Channel ID → skill routing map |
| dm-model-signature | 1.0 | skills/dm-model-signature/SKILL.md | DM context only — mandatory tier signature chip per OPERATING.md |

---

## Auto-Loaded Skills (By Intent or Keyword)

| Skill | Version | File | Trigger |
|---|---|---|---|
| reconciliation-claw | 1.0 | skills/Finance/reconciliation_claw/SKILL.md | reco, reconciliation, run reco, supplier reco, OR any of the 58 LCC supplier names (jazeera, flydubai, indigo, salamair, ajet, …) |
| suppliers (LCC) | - | skills/Finance/reconciliation_claw/references/suppliers.md | loaded with reconciliation-claw |
| date-parsing | - | skills/Finance/reconciliation_claw/references/date-parsing.md | loaded with reconciliation-claw |
| n8n-patterns | - | skills/automation-hub/references/n8n-patterns.md | n8n, workflow, webhook, credential |
| channels | - | skills/wego-slack-channels/references/channels.md | channel name → ID resolution |
| org-structure | - | knowledge/company/org-structure.md | team, org, capacity, onboard |
| systems-architecture | - | knowledge/company/systems-architecture.md | stack, infra, platform, architecture |
| wego-business | - | knowledge/company/wego-business.md | wego, product, markets, revenue |
| glossary | - | knowledge/company/glossary.md | what is, define, acronym |

---

## Channel-Specific KB Docs (Loaded by Channel ID)

Filenames below are the ones actually on disk. `agents/nova-pro/MANIFEST.md` Step 1
is the authoritative routing table — this is a summary of it.

| Channel | Channel ID | KB Doc |
|---|---|---|
| netsuite_ap | C08N2T0CARE | skills/wego-netsuite/knowledge_base/netsuite_ap.md |
| netsuite_ar | C08N2SY3HFS | skills/wego-netsuite/knowledge_base/netsuite_ar.md |
| netsuite_gl_and_reporting | C08MCK3NJTX | skills/wego-netsuite/knowledge_base/netsuite_gl_and_reporting.md |
| netsuite_tax | C08MHS9PMFC | skills/wego-netsuite/knowledge_base/netsuite_tax.md |
| netsuite_ota | C08LZTG1YR5 | skills/wego-netsuite/knowledge_base/netsuite_ota.md |
| netsuite_adminsupport | C08MCK8936Z | — (human triage channel, do not auto-respond) |
| netsuite_champion | C0B1T3B4RMH | skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/references/channel_routing.md (master channel — domain resolved at runtime) |
| netsuite-dev-agent | C0B9A8ZRM5X | skills/wego-netsuite/CLAUDE.md + skills/wego-netsuite/references/channel_routing.md (master access — Nikhil's dev/QA channel for testing changes before they reach live finance channels) |
| data-marketing-reports | C07EGK6JU8Y | knowledge/company/wego-business.md |
| alphabot-masters | C08T81REV6Y | skills/automation-hub/SKILL.md + skills/wego-coding-automation-style/SKILL.md |
| proj-alphabot-testing | C090HF85F2P | skills/Finance/reconciliation_claw/SKILL.md (internal team testing bridge) |
| finance-automation-claw | C0AVB4VR708 | skills/Finance/reconciliation_claw/SKILL.md (finance team production bridge) |

---

## On-Demand Skills (Load Only When Explicitly Needed)

| Skill | File | When to Load |
|---|---|---|
| brain-sync-advanced-format | skills/brain-sync-advanced-format/SKILL.md | Building a rich Slack Block status report |
| context-aware-response | skills/context-aware-response/SKILL.md | When answering from memory or prior context; channel-vs-DM tone shifts |
| daily-digest-contacts | skills/daily-digest-contacts/SKILL.md | Resolving who receives the daily digest |
| dm-working-indicator | skills/dm-working-indicator/SKILL.md | Showing a working indicator while a DM turn is in flight |
| itops | skills/itops/SKILL.md | IT operations, monitoring, incident workflows |
| model-providers | skills/model-providers/SKILL.md | OpenAI vs Claude selection, API patterns |
| nik-memory-sync | skills/nik-memory-sync/SKILL.md | When syncing memory/skills to GitHub |
| nik-profile | skills/nik-profile/SKILL.md | When collaboration style or Nikhil context is needed |
| openclaw-nova-mirror | skills/openclaw-nova-mirror/SKILL.md | When validating or running the weekly mirror sync |
| ops-sync | skills/ops-sync/SKILL.md | When updating cron schedule docs or OpenClaw job config |
| robot-python-automation | skills/robot-python-automation/SKILL.md | Robot Framework + Python design patterns |
| session-analytics | skills/session-analytics/SKILL.md | When tracking model usage or cost reporting |
| sql-plsql-bigquery | skills/sql-plsql-bigquery/SKILL.md | SQL correctness, BQ optimization, cost control |
| weekly-team-setup | skills/weekly-team-setup/SKILL.md | Monday IAX ticket creation + Friday wrap-up |
| wego-automation-ops | skills/wego-automation-ops/SKILL.md | Strategic automation delivery, CI/CD, KPIs |
| wego-coding-automation-style | skills/wego-coding-automation-style/SKILL.md | Code review, style checks |
| wego-github-coding-style | skills/wego-github-coding-style/SKILL.md | GitHub repo structure, naming conventions |
| wego-netsuite | skills/wego-netsuite/SKILL.md | When no channel context - full NetSuite reference |
| wego-rpa-structure | skills/wego-rpa-structure/SKILL.md | Robot Framework repo structure |

---

## How to Read This File

- **Always-Loaded** = in memory on every session, no trigger needed
- **Auto-Loaded** = triggered by intent classification or keywords in query
- **Channel-Specific KB** = loaded when source Slack channel ID matches (highest priority)
- **On-Demand** = only load when the query clearly requires this skill

For routing logic, see `agents/nova-pro/MANIFEST.md`.
For adding new skills/channels, see `TEACHING.md`.
