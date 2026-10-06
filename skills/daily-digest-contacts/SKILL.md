---
name: Daily Digest — Contact Lookup & Meeting Context
description: Pull consolidated contact files by person name(s) or meeting name
owner: Nikhil Gupta
created: 2026-04-14
trigger_phrases: 
  - "daily digest with [name]"
  - "daily digest with [name] and [name]"
  - "checkpoint [name]"
  - "summary [name] from [meeting_title]"
---

# Daily Digest — Contact Lookup Skill

When Nikhil uses trigger phrases, respond with consolidated contact information in rich Slack format.

---

## Query Patterns

### Pattern 1: Single Person
```
"daily digest with likith"
"checkpoint with Duncan"
"summary Duncan"
```


### Pattern 2: Multiple People
```
"daily digest with likith and ayush"
"checkpoint likith, ayush, peter"
"summary Duncan and Nikhil"
```

**Response:** Pull both files, merge into single rich Slack report.

### Pattern 3: Specific Meeting
```
"daily digest with likith from Commission automation"
"checkpoint Duncan from Nikhil x Duncan catchup"
"summary ayush from HCN/Hotels pipeline"
```

**Response:** Find the meeting in person's contact file, pull that specific meeting's context + action items.

### Pattern 4: Meeting Search
```
"search 'Commission automation'"
"find meeting 'Roadmap Follow ups'"
```

**Response:** Search across all contacts, return all people who attended + context.

---

## Response Format (Slack Blocks)

**Single person example:**

```
📋 LIKITH

Last Meeting: 2026-04-12 — Commission automation checkpoint
Context: Discussed n8n flow, commission calculation logic

Recent Meetings:
• 2026-04-12 — Commission automation checkpoint
• 2026-04-10 — AIA Weekly Meeting - Data
• 2026-04-05 — Roadmap Follow ups - Data

Action Items from These Meetings:
- Code review on n8n flow (from 2026-04-12)
- Clarify commission rounding logic (from 2026-04-10)
```

**Multiple people example:**

```
👥 Daily Digest: LIKITH + AYUSH

📌 LIKITH
Last: 2026-04-12 — Commission automation checkpoint
Meetings: 80 total | Recent: 3

📌 AYUSH  
Last: 2026-04-12 — AIA Weekly Meeting - Data
Meetings: 66 total | Recent: 2
```

---

## Contact File Location


Format:
- Name
- Last meeting date & title
- All meetings (most recent first, last 10 shown)
- Context for each meeting
- Action items

---

## Implementation

1. Parse query for names/meeting titles
3. Extract relevant sections (last meeting, recent meetings, action items)
4. Format in Slack blocks (rich format, no designation/role)
5. Send to Nikhil

---

## Key Rules

- **No designation shown** — just name + content
- **Always show last meeting first**
- **Extract action items** from each meeting context
- **Support fuzzy matching** — "likith", "Likith", "LIKITH" all work
- **Multiple people** — merge into single view, show cross-dependencies if any
- **Meeting search** — return all attendees + dates
