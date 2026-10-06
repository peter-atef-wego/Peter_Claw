# Slack Handler Setup — Auto-Route DMs to Tier Agents

**Status:** Ready to deploy (2026-04-17)

---

## What It Does

The custom Slack handler:
1. Listens for incoming DMs from Nikhil (U04H3EB2PTN)
2. Classifies message to tier (L1-L4)
3. Spawns OpenClaw session with routed agent (Data Automation's Claw-l1/l2/l3/l4)
4. Sends response back to Slack

---

## Prerequisites

### 1. Slack App Tokens

You need two tokens from your Slack workspace:

**SLACK_BOT_TOKEN** (xoxb-...):
- Go to: https://api.slack.com/apps
- Select your app
- OAuth & Permissions → Bot Token Scopes
- Add: `chat:write`, `channels:read`, `users:read`
- Copy the Bot User OAuth Token

**SLACK_APP_TOKEN** (xapp-...):
- Same app → Socket Mode → Enable
- Generate App-Level Token with scope `connections:write`
- Copy the token

### 2. Python Dependencies

```bash
pip install slack-bolt slack-sdk
```

### 3. Set Environment Variables

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"
```

Or create `.env`:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

---

## How to Run

### Option A: Direct (Development)

```bash
cd /home/openclaw/.openclaw/workspace

# Set tokens
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."

# Run
python3 scripts/slack_handler.py

# Output:
# [timestamp] INFO: Slack DM Router initialized
# [timestamp] INFO: Slack handler ready. Listening for DMs...
```

### Option B: Systemd Service (Production)

Create `/etc/systemd/user/slack-router.service`:

```ini
[Unit]
Description=Data Automation's Claw Slack DM Router
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/openclaw/.openclaw/workspace/scripts/slack_handler.py
Environment="SLACK_BOT_TOKEN=xoxb-..."
Environment="SLACK_APP_TOKEN=xapp-..."
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Then:
```bash
systemctl --user daemon-reload
systemctl --user enable slack-router
systemctl --user start slack-router
```

### Option C: Cron (Check Every 5 Minutes)

Add to crontab:

```bash
*/5 * * * * pgrep -f slack_handler.py > /dev/null || cd /home/openclaw/.openclaw/workspace && SLACK_BOT_TOKEN="xoxb-..." SLACK_APP_TOKEN="xapp-..." python3 scripts/slack_handler.py &
```

---

## Testing

### 1. Manual Test (Without Handler)

```bash
# Send a test DM to Data Automation's Claw-PRO bot
# In Slack: @Data Automation's Claw "Can you review my code?"

# Then manually route:
python3 /home/openclaw/.openclaw/workspace/scripts/slack_dm_router.py "Can you review my code?"
# Output: Data Automation's Claw-l3
```

### 2. Live Test (With Handler Running)

1. **Start handler:**
   ```bash
   python3 scripts/slack_handler.py
   ```

2. **Send Slack DM:**
   - Open Slack
   - Message @Data Automation's Claw-PRO
   - Type: "What time is the standup?"

3. **Expect:**
   - Handler logs: `Classified: 'What time is standup...' → Data Automation's Claw-l2`
   - Slack response: `✅ Processing with Data Automation's Claw-L2 — Session: ...`
   - Session runs with GPT-4o-mini (L2 model)

### 3. Tier Verification

Send different DMs and check routing:

| Message | Expected Tier | Check |
|---|---|---|
| "What time is standup?" | L2 | Daily ops (generic query) |
| "Debug this Python error" | L3 | Code issue (technical) |
| "Push changes to GitHub" | L1 | Git ops (script) |
| "Design our architecture" | L4 | Strategy (executive) |

---

## Monitoring

### Check Handler Status

```bash
# If running as service:
systemctl --user status slack-router

# If running directly:
ps aux | grep slack_handler

# Log output:
tail -f /tmp/slack_handler.log  # (if redirected)
```

### View Recent Sessions

```bash
openclaw sessions list
# Look for "Data Automation's Claw-l1", "Data Automation's Claw-l2", "Data Automation's Claw-l3", "Data Automation's Claw-l4" sessions
```

### Check Message Classification

```bash
# Test router independently
python3 scripts/slack_dm_router.py "your test message here"
```

---

## Troubleshooting

### Error: "Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN"

**Fix:** Set environment variables before running

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
python3 scripts/slack_handler.py
```

### Error: "slack_bolt not installed"

**Fix:** Install dependencies

```bash
pip install slack-bolt slack-sdk
```

### Handler Runs But No Response in Slack

1. **Check permissions:**
   - Ensure bot has `chat:write` scope
   - Ensure Socket Mode is enabled on the Slack app

2. **Check logs:**
   ```bash
   python3 scripts/slack_handler.py 2>&1 | tee /tmp/slack_handler.log
   ```

3. **Verify tokens are correct:**
   - xoxb- (Bot Token)
   - xapp- (App Token)

### Sessions Not Spawning

1. **Check OpenClaw status:**
   ```bash
   openclaw status
   ```

2. **Check agent IDs exist:**
   ```bash
   openclaw agents list
   # Should show: Data Automation's Claw-l1, Data Automation's Claw-l2, Data Automation's Claw-l3, Data Automation's Claw-l4
   ```

3. **Test spawn manually:**
   ```bash
   openclaw sessions spawn --agent-id Data Automation's Claw-l2 --message "test" --timeout-seconds 30
   ```

---

## Architecture

```
DM from Nikhil
    ↓
Slack App (Socket Mode)
    ↓
slack_handler.py receives event
    ↓
Verify: is Nikhil? (U04H3EB2PTN)
    ↓
Classify: model_router.py → tier
    ↓
Spawn: openclaw sessions spawn --agent-id Data Automation's Claw-{tier}
    ↓
Execute: Agent runs with routed model
    ↓
Response: Send back to Slack
```

---

## Files

| File | Purpose |
|---|---|
| `scripts/slack_handler.py` | Main handler (this script) |
| `scripts/slack_dm_router.py` | Standalone classifier |
| `model-routing/SLACK_INTEGRATION.md` | Integration guide |
| `openclaw.json` | Agent profiles (Data Automation's Claw-l1/l2/l3/l4) |

---

## Next Steps

1. ✅ Get SLACK_BOT_TOKEN and SLACK_APP_TOKEN from your workspace
2. ✅ Set environment variables
3. ✅ Run `python3 scripts/slack_handler.py`
4. ✅ Send test DMs to @Data Automation's Claw-PRO
5. ✅ Monitor sessions and routing

---

## Support

- **Questions about tokens?** → https://api.slack.com/apps
- **Socket Mode docs?** → https://slack.com/help/articles/360033383054
- **OpenClaw issues?** → Check `openclaw status` and logs

---

## Cost Impact

By routing to tiers automatically:
- **L1 tasks** use Sonnet (Haiku removed 2026-06-16)
- **L2 tasks** use GPT-4o-mini (2-3x cheaper than L3)
- **L3 tasks** use Sonnet (baseline)
- **L4 tasks** use Opus (premium, only when needed)

**Savings:** ~30-50% on average compared to always using L4.
