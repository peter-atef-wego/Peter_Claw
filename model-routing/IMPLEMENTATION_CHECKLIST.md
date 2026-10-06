# Model Routing Implementation Checklist

**Goal:** Incoming DMs auto-route to L1-L4 based on query content.

---

## ❌ Current Problem

You ask: "What time is standup?"
- Classification says: L2 ✅
- Agent used: L2 ✅
- But you're seeing: L2 always

**Why:** Slack handler isn't intercepting DMs yet. They go to default agent (main) — was Haiku, now Sonnet (2026-06-16).

---

## ✅ Solution: Activate Slack Handler

### Step 1: Get Slack Tokens

```bash
# From https://api.slack.com/apps → Your App
# 1. Copy Bot User OAuth Token (xoxb-...)
# 2. Enable Socket Mode → Generate token (xapp-...)
```

### Step 2: Set Environment & Run Handler

```bash
export SLACK_BOT_TOKEN="xoxb-YOUR-TOKEN"
export SLACK_APP_TOKEN="xapp-YOUR-TOKEN"

# Install dependencies
pip install slack-bolt slack-sdk

# Start handler (runs forever, listening for DMs)
python3 /home/openclaw/.openclaw/workspace/scripts/slack_handler.py

# Output:
# [timestamp] INFO: Slack DM Router initialized
# [timestamp] INFO: Slack handler ready. Listening for DMs...
```

### Step 3: Test

Send DM to @Data Automation's Claw-PRO:
- "What time is standup?" → Should use L2
- "Debug this error" → Should use L3
- "Design architecture" → Should use L4

Handler logs will show:
```
[timestamp] INFO: Classified: 'What time is...' → Data Automation's Claw-l2
[timestamp] INFO: Spawning agent session: Data Automation's Claw-l2
```

---

## ✅ How It Works (Flow)

```
Your DM in Slack
    ↓
Slack App (Socket Mode)
    ↓
slack_handler.py listens & receives
    ↓
Calls model_router.py to classify query
    ↓
Gets tier: L1, L2, L3, or L4
    ↓
Maps to agent: Data Automation's Claw-l1/l2/l3/l4
    ↓
Spawns OpenClaw session with that agent
    ↓
Agent runs with ROUTED MODEL
    ↓
Response back to Slack
```

---

## ✅ What To Push to GitHub

Once working, update MEMORY.md:

```markdown
## Model Routing Live (2026-04-17)

- ✅ models.json — Single source of truth
- ✅ Agents Data Automation's Claw-l1/l2/l3/l4 registered
- ✅ Slack handler deployed and routing
- ✅ DMs auto-route to correct tier based on query

### How It Works
- Incoming DM → Slack handler intercepts
- Classifies to L1/L2/L3/L4
- Spawns correct agent
- Uses routed model for response

### Update Models
1. Edit model-routing/models.json
2. Run: python3 model-routing/generate_config.py
3. Push to GitHub
```

---

## ✅ Keep Memory in Sync

Add to MEMORY.md section after this is live:

```markdown
## 20. Model Routing Live — Auto-Routing Active (2026-04-17)

**Status:** Slack handler deployed. DMs auto-route to L1-L4 tiers.

**Files:**
- ✅ `model-routing/models.json` — Single source of truth (L1-L4 definitions)
- ✅ `model-routing/model_router.py` — Classification engine
- ✅ `scripts/slack_handler.py` — Slack listener (ACTIVE)
- ✅ `openclaw.json` — Agent profiles (Data Automation's Claw-l1/l2/l3/l4)

**How it works:**
1. DM arrives → Slack handler intercepts
2. Classifies query to tier using model_router.py
3. Spawns agent Data Automation's Claw-l1/l2/l3/l4
4. Response uses routed model

**To change models:**
1. Edit `model-routing/models.json`
2. Run `python3 model-routing/generate_config.py`
3. Commit + push
4. Restart slack_handler.py

**Cost savings:** ~30-50% vs always using L4
```

---

## Step-by-Step To Completion

- [ ] Get SLACK_BOT_TOKEN from workspace
- [ ] Get SLACK_APP_TOKEN from workspace  
- [ ] Set environment variables
- [ ] Run: `pip install slack-bolt slack-sdk`
- [ ] Start handler: `python3 scripts/slack_handler.py`
- [ ] Test: Send 4 DMs with different query types
- [ ] Verify logs show correct tier routing
- [ ] Update MEMORY.md with status
- [ ] Commit all changes
- [ ] Push to GitHub

---

## Important Notes

✅ Handler runs continuously in background  
✅ Listens only for YOUR DMs (Peter, PETER_SLACK_USER_ID_TODO)  
✅ Rejects DMs from anyone else  
✅ Falls back to L2 if classification fails  
✅ All logs show in handler output

---

## Next: You Tell Me

Ready to:
1. Get the Slack tokens?
2. Start the handler?
3. Test and confirm it's routing correctly?

Then I'll update MEMORY.md and push everything to GitHub.
