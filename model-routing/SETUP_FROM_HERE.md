# Model Routing — Setup From Here (2026-04-09)

## What's Ready

✅ `model_router.py` — Task classification engine (works standalone)
✅ `nova_router_wrapper.py` — Wrapper for easy integration
✅ Cron scripts that route jobs through the tier system:
  - `cron/router_init.sh` — Initialize routing at startup
  - `cron/dispatch_with_routing.sh` — Route any job to correct tier
  - `cron/example_routed_job.sh` — Example job using routing

✅ OPENROUTER_API_KEY configured
✅ All 5-tier model IDs ready

## How to Activate (3 Steps)

### Step 1: Verify Router Works

```bash
cd /home/openclaw/.openclaw/workspace/model-routing
python3 -c "from model_router import route; r = route('analyze bigquery data'); print(f'Level: {r.level}, Model: {r.model_id}')"
```

Expected output: `Level: l3_standard, Model: anthropic/claude-sonnet-4-6`

### Step 2: Test Dispatcher

```bash
bash cron/dispatch_with_routing.sh fireflies_sync
```

Expected output:
```
Job: fireflies_sync
Tier: l1
Model: anthropic/claude-sonnet-4.6
✅ Routed to L1 tier (...)
Export Data Automation's Claw_MODEL_ID=anthropic/claude-sonnet-4.6 for downstream scripts
```

### Step 3: Update Cron Jobs in jobs.json

For each cron job, wrap with routing:

**Before:**
```json
{
  "name": "fireflies_sync",
  "schedule": "0 18 * * *",
  "command": "python3 scripts/fireflies_sync.py"
}
```

**After:**
```json
{
  "name": "fireflies_sync",
  "schedule": "0 18 * * *",
  "command": "bash cron/dispatch_with_routing.sh fireflies_sync && bash cron/example_routed_job.sh fireflies_sync"
}
```

Or simpler (one-liner):
```json
{
  "name": "fireflies_sync",
  "schedule": "0 18 * * *",
  "command": "export MODEL=$(cd model-routing && python3 -c \"from model_router import get_cron_model; print(get_cron_model('fireflies_sync'))\") && python3 scripts/fireflies_sync.py --model $MODEL"
}
```

### Step 4: For Interactive Sessions

For me (Data Automation's Claw-PRO in chat):

1. I classify tasks silently using `model_router.route()`
2. Request model override to the classified tier
3. OpenClaw assigns that model
4. Task runs with correct tier

**Example mapping (my internal logic):**
- "Check Jira tickets" → L2 tier → GPT-4o Mini
- "Analyze BigQuery data" → L3 tier → Claude Sonnet 4.6
- "General conversation" → L2 tier → GPT-4o Mini
- "CEO weekly report" → L4 tier → Claude Opus 4.8

## Environment Setup

Add to OpenClaw startup (e.g., `.bashrc` or systemd service):

```bash
export OPENROUTER_API_KEY="your_key_here"
export NOVA_CLAW_ROUTER_ENABLED=1

# Optional: Initialize router at startup
source /home/openclaw/.openclaw/workspace/cron/router_init.sh
```

## Files Changed

- `cron/router_init.sh` — Startup initialization
- `cron/dispatch_with_routing.sh` — Dispatcher script
- `cron/example_routed_job.sh` — Example usage
- `model-routing/nova_router_wrapper.py` — Integration wrapper
- `model-routing/router-integration.md` — Architecture guide
- `MEMORY.md` — Status update

## Next: Full Integration

Once above is working:

1. Update all cron jobs in `cron/jobs.json` to use dispatch_with_routing.sh
2. For interactive sessions: I use silent classification + request model override
3. Monitor costs via OpenRouter dashboard to verify tier usage is correct

## Troubleshooting

**Router won't initialize:**
- Check `OPENROUTER_API_KEY` is set: `echo $OPENROUTER_API_KEY`
- Verify model_router.py syntax: `python3 -m py_compile model-routing/model_router.py`

**Wrong model selected:**
- Check classification: `python3 model_router.py "your task description"`
- Adjust keywords in model_router.py if needed

**Costs not optimized:**
- Verify cron jobs are using dispatch_with_routing.sh
- Check Data Automation's Claw_MODEL_ID is being passed to scripts: `echo $Data Automation's Claw_MODEL_ID`