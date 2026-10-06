#!/bin/bash
# router_init.sh — Initialize model routing for NOVA-PRO
# Call this at OpenClaw startup or before any LLM session

set -e

WORKSPACE_DIR="/home/openclaw/.openclaw/workspace"
ROUTER_DIR="$WORKSPACE_DIR/model-routing"

# Verify OPENROUTER_API_KEY is set
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ OPENROUTER_API_KEY not set. Model routing cannot initialize."
    exit 1
fi

# Verify model_router.py exists
if [ ! -f "$ROUTER_DIR/model_router.py" ]; then
    echo "❌ model_router.py not found at $ROUTER_DIR"
    exit 1
fi

# Test router with simple classification
TEST_RESULT=$(cd "$ROUTER_DIR" && python3 -c "from model_router import route; r = route('test'); print(r.model_id)")

if [ -z "$TEST_RESULT" ]; then
    echo "❌ Router failed to initialize"
    exit 1
fi

echo "✅ Model routing initialized"
echo "✅ OPENROUTER_API_KEY present"
echo "✅ model_router.py working"
echo "Default model: $TEST_RESULT"
echo ""
echo "Router ready. Export NOVA_ROUTER_ENABLED=1 to activate per-request routing."
