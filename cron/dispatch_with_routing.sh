#!/bin/bash
# dispatch_with_routing.sh — Route any cron job/task through NOVA tier system
# Usage: dispatch_with_routing.sh "job_name" ["task description"]

set -e

WORKSPACE_DIR="/home/openclaw/.openclaw/workspace"
ROUTER_DIR="$WORKSPACE_DIR/model-routing"
JOB_NAME="$1"
TASK_DESC="${2:-}"

# Initialize router
source "$WORKSPACE_DIR/cron/router_init.sh"

# Get the model for this job
if [ -n "$TASK_DESC" ]; then
    # Route by task description
    MODEL_JSON=$(cd "$ROUTER_DIR" && python3 nova_router_wrapper.py "$TASK_DESC" 2>/dev/null)
else
    # Route by cron job name
    MODEL_JSON=$(cd "$ROUTER_DIR" && python3 nova_router_wrapper.py "" --cron "$JOB_NAME" 2>/dev/null)
fi

# Extract model ID and tier
MODEL_ID=$(echo "$MODEL_JSON" | grep -o '"model_id": "[^"]*' | cut -d'"' -f4)
TIER=$(echo "$MODEL_JSON" | grep -o '"tier": "[^"]*' | cut -d'"' -f4)

echo "Job: $JOB_NAME"
echo "Tier: $TIER"
echo "Model: $MODEL_ID"
echo ""

# Export for use in called scripts
export NOVA_MODEL_ID="$MODEL_ID"
export NOVA_TIER="$TIER"
export NOVA_ROUTER_ENABLED=1

echo "✅ Routed to $TIER tier ($MODEL_ID)"
echo "Export NOVA_MODEL_ID=$MODEL_ID for downstream scripts"
