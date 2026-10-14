---
name: Brain Sync — Advanced Rich Format
description: Complete system status in rich Slack blocks (interactive, multi-section)
owner: Peter Atef
created: 2026-04-14
trigger_phrase: "synced brain?"
---

# Brain Sync — Advanced Rich Format

When Peter asks "synced brain?", respond with this advanced rich Slack block format (not plain text).

---

## Rich Format Template

**Structure:**
1. Header: "🧠 Data Automation's Claw-PRO: Complete System Status"
2. Quick status line (Last Sync + Status)
3. Divider
4. GitHub Repository (section + 4-field grid)
5. Memory & Knowledge (section + 4-field grid)
6. Model Routing (section + 4-field grid + fallback/escalation)
7. Operational Rules (section + 4-field grid)
8. Divider + Footer context

**Each section includes:**
- Section header with emoji
- Fields in 2x2 or 4x1 grids
- Markdown formatting with bold, backticks, links
- Status indicators (✓, ✗, ⚠)

---

## Data to Display

**GitHub:**
- Current commit hash (short)
- Branch
- Upstream URL
- Workspace state (clean/dirty)

**Memory & Knowledge:**
- MEMORY.md size + sections + sync status
- Memory files count
- Contact database (people + meetings)
- Daily digest skill status

**Model Routing:**
- L1: Model ID + use case
- L2: Model ID + use case
- L3: Model ID + use case
- L4: Model ID + use case
- Fallback chain
- Auto-escalation status

**Operational Rules:**
- DM security (who, alerts)
- Slack response pattern (single message, rich format)
- Brain sync trigger
- Daily digest trigger

---

## Implementation

1. Query git, filesystem, model_router for current state
2. Build blocks array following template
3. Call `message.send()` with `blocks` parameter (rich format)
4. Never use plain text for "synced brain?" responses

---

## Key Rule

**ALWAYS rich Slack blocks.** Never plain text for brain sync status. Multi-section, interactive, professional.
