# Model Routing Integration Guide

## Goal
Enable full 5-tier model routing for Data Automation's Claw-PRO across interactive sessions and cron jobs.

## Current State
- `model_router.py` exists and works standalone ✓
- `ROUTING.md` spec complete ✓
- OPENROUTER_API_KEY configured ✓
- **Gap:** OpenClaw runtime doesn't auto-classify and route tasks

## Solution: Gateway Middleware Integration

### Step 1: Create Router Wrapper (Compatibility Layer)

File: `model-routing/nova_router_wrapper.py`

This wrapper sits between OpenClaw and the LLM provider, intercepts prompts, and routes to the correct model.

```python
#!/usr/bin/env python3
"""
Data Automation's Claw Router Wrapper — Integrates model_router.py with OpenClaw LLM calls.
Intercepts prompts, classifies to tier, routes to OPENROUTER_API_KEY with correct model.
"""

import os
import sys
import json
from model_router import route, get_cron_model, MODELS

def route_prompt(prompt_text: str, is_cron: str = None) -> dict:
    """
    Route a prompt to the correct model tier.
    Returns: {"model_id": "...", "tier": "...", "provider": "openrouter"}
    """
    if is_cron:
        model_id = get_cron_model(is_cron)
        # Find tier from MODELS keys
        tier = next((k for k, v in MODELS.items() if v == model_id and k != "fallback"), "l3")
    else:
        result = route(prompt_text)
        model_id = result.model_id
        # Extract tier from result level (l1_nano → l1, l2_fast → l2, etc)
        tier = result.level.split("_")[0] if "_" in result.level else result.level

    return {
        "model_id": model_id,
        "tier": tier,
        "provider": "openrouter",
        "api_key_env": "OPENROUTER_API_KEY",
        "fallback": "openai/gpt-4o"
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 nova_router_wrapper.py '<prompt>' [--cron job_name]")
        sys.exit(1)
    
    prompt = sys.argv[1]
    is_cron = sys.argv[3] if len(sys.argv) > 2 and sys.argv[2] == "--cron" else None
    
    result = route_prompt(prompt, is_cron)
    print(json.dumps(result, indent=2))
```

### Step 2: OpenClaw Configuration

Add to `openclaw.json` (or equivalent config):

```json
{
  "lm": {
    "routing": {
      "enabled": true,
      "router_script": "./model-routing/nova_router_wrapper.py",
      "auto_classify": true,
      "provider": "openrouter",
      "api_key": "OPENROUTER_API_KEY"
    },
    "models": {
      "l1": "anthropic/claude-sonnet-4.6",
      "l2": "openai/gpt-4o-mini",
      "l3": "anthropic/claude-sonnet-4-6",
      "l4": "anthropic/claude-opus-4-8"
    },
    "fallback": "openai/gpt-4o"
  }
}
```

### Step 3: For Immediate Use (Manual Routing)

Until OpenClaw gateway supports auto-routing, I can:

1. **Read the prompt internally**
2. **Run silent classification** (user never sees it)
3. **Request model override** to the classified tier
4. **Proceed with that model**

This requires OpenClaw to support per-request model overrides.

## Implementation Timeline

| Phase | Action | Blocker |
|---|---|---|
| **Phase 1** | Create wrapper scripts (nova_router_wrapper.py) | None — can do now |
| **Phase 2** | Update openclaw.json with tier config | None — can do now |
| **Phase 3** | Integrate into gateway request pipeline | **Requires OpenClaw code access** |
| **Phase 4** | Test end-to-end with all 5 tiers | Depends on Phase 3 |

## Manual Routing (Works Today)

For this session and ongoing:

1. **Classify this task:** "General conversation about model routing" → **Standard tier**
2. **Request override:** To `anthropic/claude-sonnet-4-6`
3. **I'll handle the rest:** Silent classification of future tasks, smart model selection

Once OpenClaw has the wrapper + config, auto-routing kicks in automatically.

## Questions for Peter

1. Do you have access to OpenClaw gateway code to add the middleware?
2. Can OpenClaw support per-request model overrides in the API?
3. Should I create wrapper scripts now for testing, or wait for gateway integration?
