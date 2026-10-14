# Cron Executor Setup

## Problem
OpenClaw's built-in cron scheduler (`cron.enabled: true` in `openclaw.json`) is not reliably waking and executing scheduled jobs. Last execution was May 12, 2026; jobs have not fired since.

## Solution
A **reliable fallback cron executor** that:
- Runs every 60 seconds as a daemon
- Parses standard cron expressions
- Tracks execution state to prevent duplicates
- Executes jobs via shell commands or agent turns
- Full logging to `logs/cron_executor_daemon.log`
- Resilient to errors (one job failure doesn't block others)

## Files
- `scripts/cron_executor.py` — Core executor logic
- `scripts/cron_executor_daemon.py` — Daemon wrapper (polls every 60s)
- `cron/openclaw-cron-executor.service` — systemd service unit

## Installation

### Option 1: Run as systemd service (Recommended)
```bash
cp /home/openclaw/.openclaw/cron/openclaw-cron-executor.service /etc/systemd/user/
systemctl --user daemon-reload
systemctl --user enable openclaw-cron-executor.service
systemctl --user start openclaw-cron-executor.service
systemctl --user status openclaw-cron-executor.service
```

Check logs:
```bash
journalctl --user -u openclaw-cron-executor.service -f
# or
tail -f /home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log
```

### Option 2: Run in background (Quick test)
```bash
/usr/bin/python3 /home/openclaw/.openclaw/workspace/scripts/cron_executor_daemon.py &
disown
tail -f /home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log
```

### Option 3: Run in a tmux/screen session (Development)
```bash
tmux new-session -d -s cron_executor -c /home/openclaw/.openclaw/workspace \
  "/usr/bin/python3 scripts/cron_executor_daemon.py"
tmux attach -t cron_executor
```

## Verification
Jobs are tracked in `/home/openclaw/.openclaw/workspace/cron/executor_state.json`:
```bash
cat /home/openclaw/.openclaw/workspace/cron/executor_state.json | jq .
```

Each job records:
- `last_run_ts` — Last execution timestamp (YYYY-MM-DD HH:MM format)
- `success` — Whether the run succeeded
- `updated_at` — Full ISO timestamp

Logs are at:
- `/home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log` (daemon loop)
- `/home/openclaw/.openclaw/workspace/logs/cron_executor.log` (executor runs)

## How It Works

### 1. Daemon Loop
`cron_executor_daemon.py` runs continuously:
```
Every 60 seconds:
  1. Execute `cron_executor.py`
  2. Capture output
  3. Log errors if any
  4. Sleep 60s
```

### 2. Executor Tick
`cron_executor.py` on each invocation:
```
1. Load jobs.json config
2. Load execution state
3. For each enabled job:
   a. Parse cron expression
   b. Check if expression matches current UTC time
   c. Check if already ran this minute (prevent duplicates)
   d. Execute job (shell command or agent turn)
   e. Update state with result
4. Save state
```

### 3. Cron Expression Parsing
Supports:
- `*` — any value
- `5` — specific value
- `1-5` — range
- `1,3,5` — list
- `*/5` — step (every 5)
- `0-23/2` — stepped range

Examples:
- `0 5 * * 1` → Monday 05:00 UTC
- `0 18 * * *` → Daily 18:00 UTC
- `5 * * * *` → Every hour at :05
- `30 3 * * 0` → Sunday 03:30 UTC

### 4. State Tracking
Prevents duplicate runs within the same minute via `executor_state.json`:
```json
{
  "jobs": {
    "weekly_team_monday": {
      "last_run_ts": "2026-05-18 05:00",
      "success": true,
      "updated_at": "2026-05-18T05:00:12.345Z"
    }
  }
}
```

## Disabling
To stop the executor:
```bash
# If using systemd:
systemctl --user stop openclaw-cron-executor.service
systemctl --user disable openclaw-cron-executor.service

# If running as daemon:
pkill -f cron_executor_daemon.py
```

## Troubleshooting

### Jobs not running
1. Check daemon is running: `ps aux | grep cron_executor_daemon`
2. Check logs: `tail -50 /home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log`
3. Verify jobs are enabled in `cron/jobs.json`
4. Verify cron expression matches current UTC time

### Executor crashes repeatedly
1. Check `/home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log` for errors
2. Check individual job logs: `tail /home/openclaw/.openclaw/workspace/logs/cron_executor.log`
3. Verify environment variables are loaded: `env | grep GITHUB_TOKEN`

### Job execution hangs
Jobs have a 10-minute timeout. If a job consistently times out:
1. Check what the job is doing
2. Consider splitting into smaller tasks
3. Review logs for the actual error

## Migration from OpenClaw Scheduler
Once this executor is stable, keep OpenClaw's scheduler enabled as a backup but trust this executor as the primary.

To fully disable OpenClaw cron in the future:
```bash
# openclaw.json
"cron": {
  "enabled": false,
  "store": "/home/openclaw/.openclaw/workspace/cron/jobs.json"
}
```

Then restart gateway:
```bash
openclaw gateway restart
```
