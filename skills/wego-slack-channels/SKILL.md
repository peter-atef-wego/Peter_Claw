---
name: wego-slack-channels
description: Slack channel ID map for Wego. Use when a user refers to a Slack channel by name, OR when a query arrives from a Slack channel and you need to load the correct knowledge base doc for that channel.
---

# Wego Slack Channels

## Overview

Two responsibilities:
1. **Name → ID resolution** — Resolve Wego Slack channel names to IDs for Slack read/send/reaction actions.
2. **Channel → KB routing** — When a query originates from a known channel, load the specific knowledge base doc for that channel instead of loading all docs broadly.

## Usage

### Sending / Reading Slack Messages
1. When a user mentions a channel name (e.g., "netsuite_gl_and_reporting"), look up the channel ID.
2. Use the channel ID in all Slack tool calls.

### Channel-Aware KB Loading (Primary Use Case)
When a query arrives from a Slack channel:
1. Extract the source channel ID from context.
2. Look it up in `references/channels.md` (Channel → KB Doc table).
3. Load ONLY the KB doc(s) listed for that channel.
4. Do NOT load the entire `wego-netsuite/SKILL.md` — load only what the channel needs.
5. If the channel-specific doc doesn't answer the query, then load `wego-netsuite/SKILL.md` as a fallback reference.

**Example:** Query from `C08N2T0CARE` (netsuite_ap) → load `knowledge_base/ap_operations.md` only, not all 10 KB files.

**Example:** Query from `C08T81REV6Y` (alphabot-masters) → load `automation-hub/SKILL.md` + `wego-coding-automation-style/SKILL.md`, not any netsuite docs.

## References

- `references/channels.md` — canonical channel name → ID → KB doc mapping.

## When NOT to Use This Skill

- If query has no channel context and is purely keyword-driven, use MANIFEST.md keyword routing instead.
- If channel is not in the map, fall back to standard keyword-based skill loading.
