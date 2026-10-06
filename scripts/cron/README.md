# OpenClaw cron — system-cron-driven executor (patches the broken built-in scheduler)

## The bug we're working around

OpenClaw's built-in cron scheduler has a bug where `job.name` comes through
as `undefined` when iterating `cron/jobs.json`. Symptoms:

- `cron/jobs-state.json` writes every job under the key `"undefined"`
- Every dispatch tick throws `TypeError: Cannot read properties of undefined (reading 'startsWith')`
- All scheduled jobs silently fail
- 36 consecutive errors observed before the issue was caught

Clearing `jobs-state.json` after a gateway restart **did not fix it** — the
`"undefined"` key comes back on the next tick, confirming the bug is in
the scheduler runtime itself, not in the state file.

The bug is inside the OpenClaw binary and **cannot be fixed from this
repo**. It needs an upstream fix from whoever maintains OpenClaw. This
patch routes around it by running a parallel scheduler from the
system crontab.

## The patch

`scripts/cron_executor.py` is a standalone Python scheduler that reads
the same `cron/jobs.json` and runs each enabled job at its scheduled time.
It has been live in the repo but was never working end-to-end because of
three internal bugs:

1. `execute_agent_turn` imported a non-existent module
   (`agents.Data_Automation_s_Claw.run`). Every job in `jobs.json` declares
   `payload.kind: "agentTurn"`, so every job crashed on ImportError.
2. The prefix stripper split on the first `: ` and didn't recognise that
   most agent-turn message bodies are actually bash commands with a prose
   prefix — leading to silent classification errors.
3. The trailing `". Do not ask for confirmation."` suffix was passed
   straight to bash, which treats it as a syntax error.

All three are fixed in this PR. Verified end-to-end against the 7 real
jobs in `cron/jobs.json` — 6 extract to clean bash, 1 (`daily_sync_status`)
is correctly identified as LLM-only and skipped without polluting the
failure counter.

## How it works now

The executor classifies each job's `payload.message` content rather than
trusting `payload.kind`:

| Message starts with… | Treatment |
|---|---|
| `source `, `python `, `git `, `curl `, `bash `, `sh `, `cd `, `export `, `echo `, `/usr/`, `/bin/` | bash command — execute |
| Anything else — but contains `: <shell-keyword>` later | strip prose prefix, execute the suffix |
| Prose with no shell content (`Build a Slack table…`) | skip cleanly with `skipped_needs_llm` status — these need the OpenClaw LLM runtime |

Trailers like `". Do not ask for confirmation."` are stripped before
handing to bash.

## Install — two paths

### Path A — host crontab (preferred, requires host access)

If you have access to the host running OpenClaw, this is the cleanest
install. One line in the host crontab:

```bash
crontab -e
```

Add:

```
* * * * * /usr/bin/python3 /home/openclaw/.openclaw/workspace/scripts/cron_executor.py tick >> /home/openclaw/.openclaw/workspace/logs/cron_executor_systemd.log 2>&1
```

Verify:

```bash
tail -f /home/openclaw/.openclaw/workspace/logs/cron_executor_systemd.log
# Should see one "Executor tick at <ts>" line per minute
```

### Path B — agent-startup self-heal (no host access needed)

If you don't have host access (typical inside an OpenClaw container,
where `crontab`, `/etc/systemd`, and `/etc/cron.d` are all read-only or
unavailable), use the `cron_executor_daemon.py` background process
combined with `ensure_daemon.py` running from the agent's startup protocol.

**How it works:**

1. `cron_executor_daemon.py` is a long-running process that calls
   `cron_executor.py tick` every 60 seconds. Same effect as cron, just
   driven by a loop instead of the host scheduler.
2. `scripts/cron/ensure_daemon.py` is an idempotent check-or-start:
   - Looks for an existing daemon (PID file → `pgrep` fallback)
   - If alive → does nothing, returns 0
   - If dead → spawns one detached (`start_new_session=True`, parent
     becomes PID 1), records the new PID
3. The project root `CLAUDE.md` step 8 runs `ensure_daemon.py` silently
   on every agent session start. Worst-case gap after a container
   restart: until the first Slack message wakes the bot — typically
   minutes, never hours during active hours.

**Bootstrapping manually** (first time, or after the container is
freshly started and you don't want to wait for a Slack ping):

```bash
python3 /home/openclaw/.openclaw/workspace/scripts/cron/ensure_daemon.py
# → "cron_executor_daemon started (PID xxxx)"
```

**Verify daemon health:**

```bash
python3 scripts/cron/ensure_daemon.py --status
# → "running: PID xxxx"

tail -f logs/cron_executor_daemon.log
# Should see "[INFO] Executor tick at <ts>" every minute
```

**Force-restart** (e.g. after deploying a code change to
`cron_executor.py`):

```bash
python3 scripts/cron/ensure_daemon.py --restart
```

### What the executor does (regardless of which path)

- Runs every minute
- Reads `cron/jobs.json` (same file OpenClaw reads — single source of truth)
- Writes state to `cron/executor_state.json` (separate from OpenClaw's
  broken `cron/jobs-state.json` — no conflict)
- Maintains per-job file locks in `cron/locks/<job>.lock` so two ticks
  can't overlap on the same job
- Logs to `logs/cron_executor.log`

## CLI commands

```bash
# Run one scheduler tick (what cron calls every minute)
python3 scripts/cron_executor.py tick
python3 scripts/cron_executor.py tick --dry-run        # match schedules but don't exec

# Print last-run status of every job
python3 scripts/cron_executor.py status

# List jobs with their schedule + extracted command preview
python3 scripts/cron_executor.py list

# Force-run one job NOW, ignoring its schedule (manual recovery)
```

`status` output looks like:

```
JOB                           SCHEDULE        ENABLED   LAST RUN (UTC)       STATUS
----------------------------------------------------------------------------------------
openclaw_nova_mirror          30 3 * * 0      yes       2026-05-18T03:30:01  ok
nova_claw_pull_sync           5 * * * *       yes       2026-05-22T06:05:01  ok
weekly_team_monday            0 5 * * 1       yes       2026-05-19T05:00:02  ok
weekly_team_friday            0 5 * * 5       yes       2026-05-16T05:00:02  ok
daily_sync_status             5 19 * * *      yes       2026-05-21T19:05:00  skipped_needs_llm
```

## Coexistence with OpenClaw's broken scheduler

Both schedulers can read `jobs.json` simultaneously without breaking each
other, because:

- They write to **different state files**
  (`jobs-state.json` vs `executor_state.json`).
- Per-job file locks (`cron/locks/<job>.lock`) prevent two
  cron_executor instances from running the same job at once. They do
  NOT protect against OpenClaw's binary running the same job — but in
  practice OpenClaw's scheduler isn't running anything successfully right
  now, so there's nothing to collide with.

**Once OpenClaw's bug is fixed upstream**, decide one of:

1. **Disable OpenClaw's built-in scheduler** in its config and rely
   permanently on system cron. Simpler. Recommended.
2. **Re-enable OpenClaw's scheduler** and disable the system cron entry
   (`crontab -e`, comment out the line). Reverts to the original
   architecture.

Don't run both indefinitely — eventually one job will run twice in the
same minute and you'll fight a git push race.

## What about `daily_sync_status`?

That one job genuinely needs the LLM (it composes a Slack Block table
from state and posts it). The current executor skips it with status
`skipped_needs_llm` — not a failure, just an honest "I can't run this
from cron".

Two ways to bring it back without OpenClaw:

1. **Rewrite it as a pure Python script** (~50 lines) that reads
   `cron/executor_state.json` + `cron/jobs.json`, formats a Slack Block
   message, and posts via the Slack webhook (`$SLACK_WEBHOOK` env var).
   Then update its `payload.message` in `jobs.json` to invoke the new
   script. Bash-shaped, runs from cron_executor automatically.
2. **Leave it broken** and rely on Nikhil's own `status` CLI check when
   he wants the digest. Cheap.

Pick option 1 if the daily Slack message is genuinely valuable; option 2
otherwise. Not in scope for this PR — flag and decide separately.

## Recovery checklist if jobs go silent again

1. **Is the daemon alive?**
   ```bash
   python3 scripts/cron/ensure_daemon.py --status
   ```
   If not running, the agent's next session-start will resurrect it
   automatically — or do it manually now:
   ```bash
   python3 scripts/cron/ensure_daemon.py
   ```
2. **Are jobs running?**
   ```bash
   python3 scripts/cron_executor.py status
   ```
   Look for recent `last_run_iso` on each job. If all show `never`, the
   daemon may be alive but the executor is failing — check the next step.
3. **What does the log say?**
   ```bash
   tail -50 logs/cron_executor.log
   tail -50 logs/cron_executor_daemon.log
   ```
   Look for `[ERROR]` lines.
4. **Does the command extract cleanly for the broken job?**
   ```bash
   python3 scripts/cron_executor.py run <job_name> --dry-run
   ```
   If not, the `payload.message` may have an unusual prefix the extractor
   doesn't recognise — file an issue.
5. **Force-run for a live error:**
   ```bash
   python3 scripts/cron_executor.py run <job_name>
   ```
6. **Stale lock?** If `cron/locks/<job>.lock` exists and the holding PID
   is dead, the lock is harmless — `fcntl` advisory locks are released
   when the process exits. Delete the file only if you're certain no
   process holds it; safer to just leave it.
7. **Daemon stuck?** `python3 scripts/cron/ensure_daemon.py --restart`
   kills any running daemon and spawns a fresh one. Useful after a
   code change to `cron_executor.py`.

## Files in this directory

- `README.md` — this file
- (locks/ — per-job file locks, auto-created)

The executor script itself is at `scripts/cron_executor.py`; the daemon
wrapper (alternative to system cron, runs forever in foreground) is at
`scripts/cron_executor_daemon.py`. Either works — system cron is simpler
and survives process crashes for free.
