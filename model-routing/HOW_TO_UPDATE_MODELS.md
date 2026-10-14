# How to Update Models (Single Source of Truth)

**TL;DR:** Change `models.json`, run `generate_config.py`, push.

---

## The Problem We Solved

Before:
- Change L2 model → Update openclaw.json
- Change L2 model → Update model_router.py keywords
- Change L2 model → Update ROUTING.md
- Change L2 model → Update Slack handler config
- Change L2 model → Update MEMORY.md

**5 places to change. Easy to miss one. Causes inconsistencies.**

---

## The Solution: Single Source of Truth

Now:
- **Only** change `model-routing/models.json`
- Run `python3 generate_config.py`
- Everything else auto-updates

---

## Example: Change L2 Model

### Step 1: Edit models.json

```json
{
  "tiers": [
    {
      "id": "l2",
      "name": "L2 — Daily Operations",
      "model": "openai/gpt-4-turbo",  // ← CHANGE THIS
      "provider": "openrouter",
      "keywords": [...]
    }
  ]
}
```

### Step 2: Generate Configs

```bash
cd /home/openclaw/.openclaw/workspace/model-routing
python3 generate_config.py
```

Output:
```
✅ Generated configs:
  - 5 agent profiles
  - 4 tier keyword mappings
  - OpenClaw models section
  - ROUTING.md documentation

✅ Updated ../../openclaw.json
✅ Updated model_router.py
✅ Generated ROUTING.md
```

### Step 3: Push to GitHub

```bash
cd /home/openclaw/.openclaw/workspace
git add model-routing/ openclaw.json
git commit -m "model-routing: update L2 model to gpt-4-turbo"
git push
```

**Done.** All configs are now consistent.

---

## What Gets Updated

| File | What Changes | Why |
|---|---|---|
| `openclaw.json` | Agent list + models section | Agents use new model IDs |
| `model_router.py` | Keyword mappings | Router uses new tier keywords |
| `ROUTING.md` | Documentation | Docs stay current |

---

## Example: Add a New Tier (L5)

### Step 1: Add to models.json

```json
{
  "tiers": [
    { ... existing L1-L4 ... },
    {
      "id": "l5",
      "name": "L5 — Ultra-Premium",
      "model": "anthropic/claude-opus-4.5",
      "provider": "openrouter",
      "cost_tier": "ultra",
      "keywords": ["priority", "urgent", "critical", "vip"],
      "agent_id": "Data Automation's Claw-l5"
    }
  ]
}
```

### Step 2: Generate

```bash
python3 generate_config.py
```

Now you have:
- ✅ Data Automation's Claw-l5 agent in openclaw.json
- ✅ L5 keywords in model_router.py
- ✅ L5 documented in ROUTING.md

### Step 3: Push

```bash
git add model-routing/ openclaw.json
git commit -m "feat: add L5 ultra-premium tier"
git push
```

---

## Files

| File | Purpose |
|---|---|
| `models.json` | **Single source of truth** (edit this) |
| `generate_config.py` | Reads models.json, updates everything else |
| `model_router.py` | Uses keywords from generated config |
| `openclaw.json` | Agent list & models (auto-updated) |
| `ROUTING.md` | Auto-generated documentation |

---

## Workflow

```
You edit models.json
      ↓
Run generate_config.py
      ↓
Generate agents (openclaw.json)
Generate keywords (model_router.py)
Generate docs (ROUTING.md)
      ↓
git add + commit + push
      ↓
Everything stays in sync
```

---

## Why This Matters

✅ **No manual duplication** — Change once, everywhere updates  
✅ **Consistency guaranteed** — Same models in all configs  
✅ **Easy audits** — Look at models.json to see all tiers  
✅ **Safe updates** — Script won't break anything  
✅ **Documentation automatic** — Docs always match reality

---

## Next Change: Just Follow This Pattern

1. Edit `model-routing/models.json`
2. Run `python3 generate_config.py`
3. Push to GitHub

That's it. No more hunting for places to change.
