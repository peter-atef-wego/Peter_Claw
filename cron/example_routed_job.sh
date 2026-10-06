#!/bin/bash
# example_routed_job.sh — Example cron job that uses NOVA model routing
# This runs a task through the router, gets the model tier, and executes with that model

set -e

WORKSPACE_DIR="/home/openclaw/.openclaw/workspace"
JOB_NAME="fireflies_sync"

# Step 1: Route the job through NOVA tier system
echo "=== Routing $JOB_NAME ==="
source "$WORKSPACE_DIR/cron/dispatch_with_routing.sh" "$JOB_NAME"

# Step 2: Now $NOVA_MODEL_ID is set to the correct model for this job
echo ""
echo "=== Executing $JOB_NAME with model: $NOVA_MODEL_ID ==="

# Example: Call the actual job script with the routed model
# In your actual scripts, pass NOVA_MODEL_ID to the Python/shell commands

case "$JOB_NAME" in
    fireflies_sync)
        echo "Running: python3 $WORKSPACE_DIR/scripts/fireflies_sync.py"
        # python3 "$WORKSPACE_DIR/scripts/fireflies_sync.py" --model "$NOVA_MODEL_ID"
        ;;
    nova_claw_pull_sync)
        echo "Running: git pull"
        # git -C "$WORKSPACE_DIR" pull --rebase
        ;;
    *)
        echo "Unknown job: $JOB_NAME"
        exit 1
        ;;
esac

echo "✅ $JOB_NAME completed (routed via $NOVA_TIER/$NOVA_MODEL_ID)"
