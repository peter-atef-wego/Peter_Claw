---
name: DM Model Signature — Mandatory Tier Display
description: Every response in Slack DMs must end with model tier indicator using dart emoji + tier + model name.
applies_to: Slack direct messages (chat_type=direct)
activated: 2026-05-20
updated: 2026-06-06
---

# DM Model Signature — Mandatory Tier Display

## Rule

**Every response in a Slack DM to Peter MUST end with a model tier signature.**

This is NOT optional. It applies to all interactive DM responses (not `NO_REPLY`).

**The signature shows the ACTUAL model that generated THIS message, not a pre-assigned tier.**

---

## Format

Signature appears as the last line of your message:

```
---
:dart: *L1 (Sonnet)*  [or *L2 (GPT-4o Mini)*/*L3 (Sonnet)*/*L4 (Opus)*]
```

**Exact structure:**
- Three dashes: `---`
- Space + dart emoji `:dart:`
- Space + asterisk-wrapped tier + model in parentheses
- Nothing after (no trailing text, no line break)

---

## Tier Mapping

| Tier | Model | Use Case |
|---|---|---|
| **L1** (DEFAULT — DMs) | `anthropic/claude-sonnet-4.6` | DMs, quick lookups, routine ops (was Haiku 4.5 until 2026-06-16 — removed) |
| **L2** | `openai/gpt-4o-mini` | Legacy batch jobs only |
| **L3** (channel @mentions) | `anthropic/claude-sonnet-4.6` | All Slack channel responses where bot is @mentioned |
| **L4** | `anthropic/claude-opus-4.8` | Architecture, strategy, critical decisions, crisis postmortems, prod-write reviews, HERMES validation |
| **L5** | `openai/gpt-5.5` | Cross-provider second opinion / Anthropic-down fallback. Manual only. |

**Routing rule:**
- DM → Default L1 (Sonnet — same model as L3; chip indicates DM surface)
- Slack channel @mention → Default L3 (Sonnet, minimum floor)
- Complex/strategy → Default L4 (Opus 4.8)
- L5 → NEVER auto-routed. Explicit invocation by Peter or documented escalation paths only (see `model-routing/ROUTING.md`).

---

## When to Use Each Tier

- **L1 (DEFAULT — DMs)**: Sonnet 4.6 (Haiku removed 2026-06-16 — same model as L3; chip indicates DM surface).
- **L2**: Legacy batch jobs only. Never for interactive use.
- **L3 (channel @mentions)**: Sonnet. Any time bot is @mentioned in a Slack channel — minimum floor.
- **L4**: Opus 4.8. Architecture, strategy, complex multi-domain analysis, and the highest-stakes reviews (prod writes, HERMES proposals, P0 postmortems). Rare. Signature chip: `🎯 L4 (Opus 4.8)`.
- **L5**: GPT-5.5. Different-provider cross-check; not a "bigger L4". Manual only. Signature chip: `🎯 L5 (GPT-5.5)`.

---

## Examples

**DM query (L1 — Sonnet, session model):**
```
Here's the status...

---
:dart: *L1 (Sonnet)*
```

**Slack channel @mention (L3 — Sonnet, session model):**
```
Here's the AP report for May 2026...

---
:dart: *L3 (Sonnet)*
```

**Escalation to L4 (Opus 4.8) for strategy/architecture:**
```
Here's the architecture analysis...

---
:dart: *L4 (Opus)*
```

---

## Special Case: `NO_REPLY`

When you have nothing to say, respond with ONLY `NO_REPLY` — no tier signature. This is the one exception.

---

## Implementation — DYNAMIC SIGNATURE (2026-06-06)

**The signature MUST reflect the ACTUAL model that generated this response.**

1. Detect `chat_type == "direct"` from inbound_meta.
2. Call `session_status(sessionKey="current")` to get the actual running model from the gateway.
3. Map the model to its tier:
   - `claude-sonnet*` (DM context) → L1 (Sonnet)
   - `claude-sonnet*` (channel @mention) → L3 (Sonnet)
   - `gpt-4o-mini*` → L2 (GPT-4o Mini)
   - `claude-sonnet*` → L3 (Sonnet)
   - `claude-opus*` → L4 (Opus)
4. Generate the response (using whatever model the session is running).
5. **Before sending:** append the signature showing the tier that ACTUALLY ran.
6. Send.

**IMPORTANT — External API calls don't change the signature:**

If you call an external API (e.g., OpenRouter for validation, or curl for Jira) in THIS response, that doesn't change the session model — the session model is what generated the reply text. Show the session model's tier.

**Example:** "I called Opus 4.8 via OpenRouter to validate the code" (external synchronous API call), but the session stayed on L1 the whole time → signature shows `:dart: *L1 (Sonnet)*` because L1 (Sonnet) generated this message.

---

## Rationale

This makes model routing transparent to Peter:
- He sees which tier each response used
- Helps track cost (L1 << L3 << L4)
- Teaches him when escalation happens
- Supports auditing model usage patterns
- **Dynamic signature shows the truth, not an assumption**

---

## Authority

- Set by Peter (2026-05-20 05:35 UTC)
- Updated 2026-06-06 for dynamic enforcement
- Applies in ALL Slack DMs
- Update this skill if tier mapping or format changes
