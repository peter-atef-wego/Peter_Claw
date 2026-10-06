#!/usr/bin/env python3
"""
Slack DM Router — Auto-routes incoming DMs to correct tier agent (nova-l1/l2/l3/l4).

This script is called by the Slack plugin when a DM arrives:
1. Receives the message text
2. Classifies to tier using model_router.py
3. Returns agent ID for OpenClaw to spawn

Usage (from Slack plugin):
    python3 slack_dm_router.py "message text from user"
    # Output: nova-l2 (or nova-l1/l3/l4)
"""

import sys
import os

# Add model-routing to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model-routing'))

from model_router import route

def classify_dm(message_text: str) -> str:
    """
    Classify a Slack DM and return the agent ID to use.
    
    Returns: "nova-l1", "nova-l2", "nova-l3", or "nova-l4"
    """
    try:
        result = route(message_text)
        
        # Extract tier from result.level (e.g., "l2_fast" → "l2")
        if "_" in result.level:
            tier = result.level.split("_")[0]
        else:
            tier = result.level
        
        agent_id = f"nova-{tier}"
        
        # Log for debugging
        print(f"[DM Router] Message: '{message_text[:50]}...' → Tier: {tier} → Agent: {agent_id}", 
              file=sys.stderr)
        
        return agent_id
    except Exception as e:
        # Fallback to L2 (daily ops) on any error
        print(f"[DM Router] Classification error: {e}. Defaulting to nova-l2", file=sys.stderr)
        return "nova-l2"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("nova-l2")  # Default fallback
        sys.exit(0)
    
    message = " ".join(sys.argv[1:])
    agent_id = classify_dm(message)
    print(agent_id)
