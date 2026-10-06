# Slack Plugin Integration — Auto-Route DMs to Tiers

**Status:** Script ready (2026-04-17). Requires Slack plugin modification.

---

## How It Works

When a DM arrives from Peter:

1. **Slack plugin receives DM** → Message text available
2. **Router classifies** → `slack_dm_router.py` → returns agent ID
3. **Spawn agent** → OpenClaw spawns `Data Automation's Claw-l1/l2/l3/l4` session
4. **Execute** → Agent processes with routed model

---

## Files

| File | Purpose |
|---|---|
| `scripts/slack_dm_router.py` | DM classifier → agent ID |
| `model-routing/agent_router.py` | Standalone classification (for testing) |
| `model-routing/AGENT_ROUTING_GUIDE.md` | Full architecture docs |

---

## Classification Rules

**L1 (Scripts, Git Ops)**
- "Push changes to GitHub"
- "Run cron job now"
- "Create a file"
- Keywords: git, push, script, bash, cron

**L2 (Daily Ops)** ← DEFAULT
- "What's my calendar?"
- "When is the standup?"
- "Jira status"
- Keywords: schedule, meeting, status, query, when, what

**L3 (Technical, Code)**
- "Debug this Python error"
- "Review my code"
- "Optimize this query"
- Keywords: code, debug, error, review, optimize, technical

**L4 (Strategy, Architecture)**
- "Design the system"
- "What's our roadmap?"
- "Executive summary"
- Keywords: design, architecture, strategy, roadmap, plan

---

## Integration Steps (For Slack Plugin)

### Step 1: Capture DM Text

In the Slack plugin message handler:

```python
# When a DM arrives
message_text = event["text"]  # Raw message from user
user_id = event["user"]
```

### Step 2: Route via Script

```python
import subprocess

# Call router script
result = subprocess.run(
    ["python3", "/home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py", message_text],
    capture_output=True,
    text=True
)

agent_id = result.stdout.strip()  # "Data Automation's Claw-l1", "Data Automation's Claw-l2", etc.
```

### Step 3: Spawn Agent Session

```python
# Use agent_id when spawning the session
# Instead of:
#   openclaw sessions spawn --message "..."
#
# Use:
#   openclaw sessions spawn --agent-id Data Automation's Claw-l2 --message "..."

# This ensures the session uses the routed model
```

### Step 4: Execute

```python
# Send message to the spawned session
# Session will use Data Automation's Claw-l2's model: openai/gpt-4o-mini
```

---

## Example: Testing the Router

```bash
# Test script directly
python3 /home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py "Can you review my code?"
# Output: Data Automation's Claw-l3

python3 /home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py "What time is standup?"
# Output: Data Automation's Claw-l2

python3 /home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py "Deploy to production"
# Output: Data Automation's Claw-l4 (strategy tier)

python3 /home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py "Push to GitHub"
# Output: Data Automation's Claw-l1 (scripts tier)
```

---

## Agent Models

| Agent | Model | Use Case |
|---|---|---|
| `Data Automation's Claw-l1` | `anthropic/claude-sonnet-4.6` | Scripts, git, operations (Haiku removed 2026-06-16) |
| `Data Automation's Claw-l2` | `openai/gpt-4o-mini` | Daily queries, Slack, Jira (DEFAULT) |
| `Data Automation's Claw-l3` | `anthropic/claude-sonnet-4.6` | Code, technical, debugging |
| `Data Automation's Claw-l4` | `anthropic/claude-opus-4.8` | Strategy, architecture, reports |

---

## What Happens if Router Fails?

Defaults to **Data Automation's Claw-l2** (daily ops tier). Always safe fallback.

---

## Testing in Production

1. Send DM: "What's my calendar?"
   - Expected: Uses Data Automation's Claw-l2 (GPT-4o-mini)
   - Look for: Fast response, good summary

2. Send DM: "Debug this error: ..."
   - Expected: Uses Data Automation's Claw-l3 (Sonnet 4.6)
   - Look for: Deeper analysis, code-aware

3. Send DM: "Push my changes"
   - Expected: Uses Data Automation's Claw-l1 (Sonnet 4.6 — Haiku removed 2026-06-16)
   - Look for: Quick, efficient execution

---

## Monitoring

To see which tier was used:

```bash
# Check session history
openclaw sessions list
# Look at "Model" column for each session

# Example:
# Data Automation's Claw-l2 session → openrouter/openai/gpt-4o-mini
# Data Automation's Claw-l3 session → openrouter/anthropic/claude-sonnet-4.6
```

---

## Next Steps

1. ✅ Router script created
2. ✅ Agent profiles configured (Data Automation's Claw-l1/l2/l3/l4)
3. ✅ Classification rules documented
4. ⏳ **Slack plugin integration** (requires platform team or code update)
5. ⏳ Test live DMs
6. ⏳ Monitor token usage by tier

---

## Questions?

- **How does it decide which tier?** → `model_router.py` classifies based on task keywords and context
- **Can I override the tier?** → User can say "use L4 for this" (requires prompt rule)
- **What if it gets it wrong?** → Falls back to Data Automation's Claw-l2; can manually request different tier
- **How much cheaper is L1 than L4?** → L1 is now Sonnet 4.6 (was Haiku until 2026-06-16); ~3-5x cheaper than Opus.

---

## Files

- `model-routing/ROUTING.md` — Full 4-tier spec
- `model-routing/AGENT_ROUTING_GUIDE.md` — Architecture
- `model-routing/agent_router.py` — Standalone classifier
- `scripts/slack_dm_router.py` — Slack plugin integration script
- `openclaw.json` — Agent profiles (Data Automation's Claw-l1 through Data Automation's Claw-l4)
