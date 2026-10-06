# TEACHING.md - How to Teach Data Automation's Claw New Things

_This file explains exactly how to add, update, or remove knowledge from openclaw-nova so that changes are picked up correctly. No code required — just edit the right file, commit, and push._

---

## 1. Add a New Slack Channel + KB Routing

When you want Data Automation's Claw to respond using a specific knowledge base doc when a query comes from a Slack channel:

**Step 1** — Add the channel to `skills/wego-slack-channels/references/channels.md`:
```
| new-channel-name | C0XXXXXXXXX | path/to/knowledge_base/doc.md |
```

**Step 2** — Add a row to the `agents/nova-pro/MANIFEST.md` Step 1 channel table:
```
| C0XXXXXXXXX | new-channel-name | path/to/knowledge_base/doc.md |
```

**Step 3** — Add the same row to `agents/nova-pro/MANIFEST.md` Step 1 table.

**Step 4** — Commit and push to GitHub. The `nova_claw_pull_sync` cron pulls every hour at :05 UTC.

That is it. No restart required — OpenClaw watches skill files automatically (`skills.load.watch: true`).

---

## 2. Add a New Knowledge Base Document

When you want to teach Data Automation's Claw new domain knowledge (e.g., a new NetSuite workflow, a new integration):

**Option A — Add to an existing KB doc:**
- Edit the relevant file in `skills/wego-netsuite/knowledge_base/` (e.g., `ap_operations.md`)
- Data Automation's Claw will pick it up on the next query that loads that doc

**Option B — Create a new KB doc:**
1. Create the file: `skills/wego-netsuite/knowledge_base/new_topic.md`
2. If it should be routed from a specific Slack channel, follow the "Add a New Channel" steps above
3. If it should be keyword-triggered, add the keywords + file path to MANIFEST.md Step 3 table

---

## 3. Add a New Skill

When you want Data Automation's Claw to have a new capability:

1. Create a folder: `skills/your-skill-name/`
2. Create `skills/your-skill-name/SKILL.md` with this frontmatter:
```yaml
---
name: your-skill-name
description: One sentence — what does this skill do and when is it loaded?
version: 1.0
triggers: [keyword1, keyword2, keyword3]
---
```
3. Write the skill content (purpose, method, rules, quick commands)
4. Add it to `SKILL_REGISTRY.md` in the appropriate section (always/auto/on-demand)
5. Add the load condition to `agents/nova-pro/MANIFEST.md` (Step 2 intent table or Step 3 keyword table)
6. If it should always load, add it to the Always Loaded list in MANIFEST.md
7. Commit and push

---

## 4. Update Team Capacity or Blockers

In `skills/team-ops/SKILL.md`:
- Update the **Team Quick Reference** table with current focus and blockers
- Update the **Active Blockers to Track** table when a blocker is resolved or new one appears
- Update the **Akansha Onboarding Tracker** when a milestone is reached

This is the only file Data Automation's Claw reads for team assignment decisions.

---

## 5. Update a Standing Decision

Standing decisions live in `MEMORY.md` Section 4 (Standing Operating Decisions).

- Edit the relevant bullet point
- Add the date when the decision changed
- Commit with message: `[memory] update standing decision: <topic>`

If the decision affects a specific skill (e.g., NetSuite API access rules), update that skill's frontmatter `usage:` field too.

---

## 6. Remove Something Data Automation's Claw Should Stop Knowing

**Remove a channel from KB routing:**
1. Delete the row from `agents/nova-pro/MANIFEST.md` Step 1 table
2. Delete the row from `skills/wego-slack-channels/references/channels.md`
3. Delete the row from the Channel-Specific KB table in `SKILL_REGISTRY.md`

**Remove a skill:**
1. Move the skill folder to `skills/archive/` (never delete)
2. Remove it from `SKILL_REGISTRY.md`
3. Remove its load condition from `MANIFEST.md`

**Remove a standing decision from memory:**
1. Delete or strikethrough the line in `MEMORY.md`
2. Add a dated note: `~~decision~~ (removed YYYY-MM-DD, reason: ...)`

---

## 7. Sync After Changes

After any edit to `agents/`, `skills/`, or `knowledge/`:
```
git add -p    # review specific changes
git commit -m "[scope] what changed and why"
git push
```

Data Automation's Claw auto-pulls every hour. Or trigger manually: ask Data Automation's Claw to "pull latest from GitHub".

---

## 8. Test That Data Automation's Claw Picked Up the Change

After pushing, ask Data Automation's Claw:
- "What KB doc do you load for #netsuite_ap?" — should return `netsuite_ap.md`
- "What skills are always loaded?" — should list `automation-hub`, `team-ops`, `wego-slack-channels` (plus `dm-model-signature` in DM context)
- "What is your routing logic?" — should describe the 3-step flow from MANIFEST.md

If Data Automation's Claw gives an outdated answer, ask it to "pull latest from GitHub" to force a sync.

---

## 9. Change Model Routing (Peter Only)

Model routing changes are LOCKED to Peter's verified identity. Only from OpenClaw UI or Slack DM from U0A05CNQQ07.

To adjust which queries go to which model tier:
1. Edit `model-routing/ROUTING.md` - update the Level Assignment Rules or complexity signals
2. Edit `model-routing/model_router.py` - update `COMPLEXITY_SIGNALS`, `L3_THRESHOLD`, or keyword lists
3. Test: `python3 model-routing/model_router.py "your test query here"`
4. Commit and push

To add a new immediate-Premium trigger (query that always goes to Opus):
- Add the keyword to `L4_IMMEDIATE_KEYWORDS` list in `model_router.py`
- Document the reason in `ROUTING.md` Level Assignment Rules

---

## 10. Add a New Contact Doc (Meeting Intelligence)

When you want Data Automation's Claw to track meetings with a new person:
1. Add the person to `memory/knowledge/people.md`
2. Fill in Profile and Communication Style sections manually (Data Automation's Claw will auto-populate Meeting History)
3. Add their trigger name to `skills/daily-digest-contacts/SKILL.md`
4. Commit and push

> **Open item (2026-08-11):** `skills/daily-digest-contacts/SKILL.md` describes
> per-person "contact files" but no contact-doc directory exists in this repo, and
> the `skills/meeting-prep/` skill this section used to point at was removed. Decide
> where contact docs live before relying on steps 2-3.

---

## 11. Get a Pre-Call Briefing

Say to Data Automation's Claw:
- "I have a call with Duncan in 30 minutes"
- "Prep me for my meeting with Li Ping"
- "Quick brief before I talk to Madan"


---

## 12. Query a Meeting by Subject Line

Say to Data Automation's Claw:
- "In the team standup on April 8, what did Ayush say about the pipeline?"
- "AI Weekly - what was decided about Akansha's first automation?"
- "The NetSuite sync meeting - what were the open items?"

