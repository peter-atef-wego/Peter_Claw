#!/usr/bin/env python3
"""
NOVA Router Wrapper — Integrates model_router.py with OpenClaw LLM calls.
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
    
    NOTE: RouteResult.level values are l1_nano, l2_fast, l3_standard, l4_premium but
    MODELS dict keys are l1, l2, l3, l4. This split() extracts the tier prefix.
    Future improvement: align RouteResult.level to match MODELS keys exactly.
    """
    if is_cron:
        model_id = get_cron_model(is_cron)
        # Find tier from MODELS keys
        tier = next((k for k, v in MODELS.items() if v == model_id and k != "fallback"), "l3")
    else:
        result = route(prompt_text)
        model_id = result.model_id
        # Extract tier from result level (l1_nano → l1, l2_fast → l2, etc)
        # TODO: Remove this split once RouteResult.level uses l1/l2/l3/l4 directly
        tier = result.level.split("_")[0] if "_" in result.level else result.level

    return {
        "model_id": model_id,
        "tier": tier,
        "provider": "openrouter",
        "api_key_env": "OPENROUTER_API_KEY",
        "fallback": "openai/gpt-4o",
        "cost_optimized": True
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 nova_router_wrapper.py '<prompt>' [--cron job_name]")
        sys.exit(1)
    
    prompt = sys.argv[1]
    is_cron = sys.argv[3] if len(sys.argv) > 2 and sys.argv[2] == "--cron" else None
    
    result = route_prompt(prompt, is_cron)
    print(json.dumps(result, indent=2))
