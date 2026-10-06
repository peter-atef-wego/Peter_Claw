#!/usr/bin/env python3
"""
Agent Router — Routes incoming DMs to the correct tier agent (nova-l1, nova-l2, nova-l3, nova-l4).
Classifies the incoming message and returns the agent ID to use.

Usage:
    python3 agent_router.py "incoming message text"
    # Output: nova-l2 (or nova-l1/l3/l4)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from model_router import route

def route_to_agent(message_text: str) -> str:
    """
    Classify a message and return the agent ID to use.
    
    Returns: "nova-l1", "nova-l2", "nova-l3", or "nova-l4"
    """
    try:
        result = route(message_text)
        
        # Extract tier from result.level (e.g., "l2_fast" → "l2")
        if "_" in result.level:
            tier = result.level.split("_")[0]  # "l2_fast" → "l2"
        else:
            tier = result.level  # Already "l2"
        
        agent_id = f"nova-{tier}"
        return agent_id
    except Exception as e:
        # Fallback to L2 (default daily ops)
        print(f"Router error: {e}, defaulting to nova-l2", file=sys.stderr)
        return "nova-l2"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agent_router.py 'message text'")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    agent_id = route_to_agent(message)
    print(agent_id)
