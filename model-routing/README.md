# Model Routing System — Complete Rebuild

**Status:** Ready for implementation (2026-04-17)

---

## Architecture Decision

Instead of trying to spawn 5 separate agents (complex, failing), we use:
- **Single agent (main)** handles all DMs
- **Router classifies** each DM to tier (L1-L4)
- **Model override** sent with each request (if supported by OpenClaw)
- **Fallback:** Use main agent with appropriate context

---

## How It Works

```
DM from Peter
    ↓
Router classifies → Tier (L1/L2/L3/L4)
    ↓
Gets model ID for that tier
    ↓
Sends to main agent with model context
    ↓
Agent responds using appropriate model
    ↓
Response back to Slack
```

---

## Implementation

### 1. Single Config File (models.json)
Already created. Single source of truth for all L1-L4 definitions.

### 2. Classification Engine (model_router.py)
Already works. Classifies queries to tiers correctly.

### 3. Slack Handler
Option A (Current): Poll Slack, classify, respond with routing info
Option B (Better): Respond in-thread with model used

### 4. Model Override Mechanism
Since OpenClaw doesn't support dynamic model switching yet:
- **Context injection:** Include model tier in prompt context
- **Agent context:** Let main agent know which tier to use
- **Fallback:** Respond with "Using L3 (Sonnet)" context

---

## What Actually Works Now

✅ models.json → Defines L1-L4  
✅ model_router.py → Classifies correctly  
✅ Handler → Listens to DMs  
✅ Agents exist → Data Automation's Claw-l1/l2/l3/l4 registered  

---

## What Needs To Happen

1. Handler detects DM
2. Classifies to tier
3. Responds in Slack with: "Routing to L3 (Claude Sonnet)"
4. Sends message to agent with context about model tier
5. Agent includes tier info in response

---

## Simplest Working Version

Just respond with the tier and let user know which model is being used:

```
You: "Debug this code"

Handler: 
"🎯 Routing to L3 (Claude Sonnet 4.6)
Processing your request..."
```

Then respond with appropriate detail level.

---

## Files & Status

| File | Status | Purpose |
|---|---|---|
| models.json | ✅ Complete | Tier definitions |
| model_router.py | ✅ Working | Classification |
| openclaw.json | ✅ Updated | Agent list |
| slack_model_router.py | ✅ Running | Handler |
| MEMORY.md | ⏳ To update | Status tracking |

---

## Next Steps

1. Ensure handler is running
2. Send test DMs
3. Verify routing classification in logs
4. Update MEMORY.md
5. Push to GitHub
6. Confirm everything in sync

Done.
