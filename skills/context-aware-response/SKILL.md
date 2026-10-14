---
name: context-aware-response
description: Respond to user queries using existing memory, skills, and context. Use when asked to answer based on internal knowledge, past decisions, or stored docs, and verify gaps with authoritative references before replying.
version: 1.1
updated: 2026-04-14
---

# Context-Aware Response

## Core workflow

0) **Check channel ID first (before anything else)**
- If the query comes from a known Slack channel, load only that channel KB doc (see channel-kb-router/SKILL.md).
- Skip steps 1-2 for the channel-specific domain — those docs are authoritative.

1) **Check memory**
- Search MEMORY.md and relevant skill references for prior decisions, preferences, or known facts.
- Use the memory search tool before answering questions about history, preferences, or prior work.
- Check `memory/knowledge/decisions.md` for standing decisions that affect this query.

2) **Use existing skills and docs**
- If a relevant skill exists, load it and follow its guidance.
- Prefer internal references (skills/ or memory/) before external sources.
- Do not load a skill just because it might be tangentially relevant — load it only if it directly addresses the query.

3) **Classify query intent (if no channel context)**
- Use the intent classification table in MANIFEST.md Step 2 to identify which KB docs to load.
- Load the minimum set of docs that covers the intent — not everything.

4) **Validate gaps**
- If info is missing or uncertain, verify using authoritative sources (official docs, APIs, repos).
- State uncertainty explicitly if still unclear. Never fabricate.

5) **Respond with context**
- Answer based on confirmed info from memory/skills.
- If external references were used, cite them or describe the source.
- If the channel-specific doc was insufficient, note that escalation to the full KB was used.

## Guardrails

- Channel ID context always overrides keyword-based loading.
- Do not load the entire wego-netsuite folder to answer a single AP question.
- Do not invent facts or numbers.
- Do not store secrets in memory or skills.
- When a request falls outside known context, ask for clarification or check references.
- Always respond to Slack @mentions after reading thread context first.
