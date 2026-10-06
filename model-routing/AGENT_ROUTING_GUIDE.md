# Model Routing — Option 3: Per-Agent Configuration

**Status:** ✅ IMPLEMENTED (2026-04-17)

---

## Architecture

Instead of intercepting at the gateway level (which OpenRouter doesn't support), we use separate agent profiles for each tier. The Slack integration classifies incoming messages and spawns the correct agent.

### Agent IDs (openclaw.json)

```json
{
  "agents": {
    "list": [
      {"id": "Data Automation's Claw-l1", "model": "openrouter/anthropic/claude-sonnet-4.6"},
      {"id": "Data Automation's Claw-l2", "model": "openrouter/openai/gpt-4o-mini"},
      {"id": "Data Automation's Claw-l3", "model": "openrouter/anthropic/claude-sonnet-4.6"},
      {"id": "Data Automation's Claw-l4", "model": "openrouter/anthropic/claude-opus-4.8"}
    ]
  }
}
```

### Routing Flow

1. **Message arrives** → Slack DM from Nikhil
2. **Classify** → `agent_router.py` analyzes message
3. **Spawn agent** → OpenClaw spawns `Data Automation's Claw-l1/l2/l3/l4` based on classification
4. **Execute** → Agent handles request with routed model

---

## Files

| File | Purpose |
|---|---|
| `model-routing/model_router.py` | Task classification engine (unchanged) |
| `model-routing/agent_router.py` | Maps task → agent ID |
| `openclaw.json` | Agents list with Data Automation's Claw-l1 through Data Automation's Claw-l4 |

---

## Usage

### Manual Routing (Test)

```bash
# Classify a message and get agent ID
python3 /home/openclaw/.openclaw/workspace/model-routing/agent_router.py "Can you review this Python code?"
# Output: Data Automation's Claw-l3

# Or for a generic query
python3 /home/openclaw/.openclaw/workspace/model-routing/agent_router.py "What's the weather?"
# Output: Data Automation's Claw-l2
```

### Automated (Slack Plugin)

The Slack integration should:

1. Receive incoming DM
2. Call `agent_router.py` to classify
3. Spawn session with routed agent:

```bash
# Example:
AGENT_ID=$(python3 agent_router.py "$MESSAGE_TEXT")
openclaw sessions spawn --agent-id "$AGENT_ID" --message "$MESSAGE_TEXT"
```

---

## Classification Rules

| Query Type | Tier | Example |
|---|---|---|
| Generic queries, daily ops | L2 | "What time is the standup?" |
| Code review, debugging | L3 | "Debug this Python error" |
| Strategy, architecture | L4 | "Design the system architecture" |
| Git ops, scripts | L1 | "Push changes to GitHub" |

---

## Model IDs

**L1 (Scripts):**
- Model: `anthropic/claude-sonnet-4.6`
- Cost: Lowest
- Speed: Fastest
- Use: File ops, git, cron jobs

**L2 (Daily Ops):** ← DEFAULT
- Model: `openai/gpt-4o-mini`
- Cost: Low
- Speed: Fast
- Use: Slack queries, Jira triage, generic questions

**L3 (Technical):**
- Model: `anthropic/claude-sonnet-4.6`
- Cost: Medium
- Speed: Balanced
- Use: Automation, code, debugging

**L4 (Strategy):**
- Model: `anthropic/claude-opus-4.8`
- Cost: Highest
- Speed: Slowest
- Use: Architecture, exec reports, complex strategy

---

## Testing

```bash
# Test classifier
python3 model-routing/agent_router.py "Deploy this to production"
# Should return: Data Automation's Claw-l3 or Data Automation's Claw-l4 (strategy)

python3 model-routing/agent_router.py "Add this file to git"
# Should return: Data Automation's Claw-l1 (scripts)

python3 model-routing/agent_router.py "What's my calendar?"
# Should return: Data Automation's Claw-l2 (daily ops, default)
```

---

## Fallback Behavior

If classification fails, defaults to **Data Automation's Claw-l2** (GPT-4o-mini, daily ops tier).

---

## Implementation Checklist

- [x] Separate agent profiles created in openclaw.json
- [x] `agent_router.py` script written
- [x] Model IDs match ROUTING.md spec
- [ ] Slack integration updated to call `agent_router.py` (Slack plugin work)
- [ ] Test with live DMs from Nikhil
- [ ] Monitor token usage by tier

---

## Notes

- **No gateway changes needed** — works with current OpenClaw architecture
- **Backwards compatible** — main agent still works as fallback
- **Observability** — Each session tracks which tier was used
- **Cost control** — Expensive tasks automatically escalate; cheap tasks don't waste L4 tokens

---

## Contact

Questions about routing? Check `model-routing/ROUTING.md` for full spec.
