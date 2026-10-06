# Persistent memory via S3 — two-root (state + memory), no EBS needed

Snapshots the agent to S3 so **S3 alone is a complete restore point** — you
can recover fully after node replacement without EBS and without GitHub.
Mirrors the flights-pricing agent's layout. Pure Python stdlib (the pod has
no aws CLI / boto3 / sqlite3 binary). Region `us-east-1`.

## Layout (date-partitioned, matches the flights-pricing agent)
```
s3://wego-enterprise-agent-logs-us-east-1-794531973703/netsuite-agent/
  state/YYYY/MM/DD/HHMMSSZ.tar.gz    # ~/.openclaw runtime state (sqlite/sessions/config)
  memory/YYYY/MM/DD/HHMMSSZ.tar.gz   # MEMORY.md + memory/ (also in GitHub; mirrored here)
```
The 14-day lifecycle rule (prefix `netsuite-agent/`) expires nested keys the
same as flat ones — no change needed there.
- **state** = openclaw's live runtime DB + internal state. Node-local, in git nowhere — this is the piece that genuinely needs S3.
- **memory** = the curated, human-meaningful memory. Already durable via GitHub; mirrored to S3 so a restore needs *only* S3.

## Files
| File | Purpose |
|---|---|
| `s3lite.py` | stdlib S3 client (SigV4 PUT/GET/LIST) + credential chain: env keys → `~/.aws/credentials` → IRSA → node IMDS |
| `preflight_s3.py` | one-run readiness check (creds source, state inventory, real S3 round-trip) |
| `backup_memory.py` | snapshots **both** roots → `state/` and `memory/`, uploads timestamped tar.gz. Loud failures |
| `restore_memory.py` | `no-arg` lists both; `state <key>` / `memory <key>` restores to the right target |

## Guarantees / review fixes baked in
- SQLite snapshotted via python `Connection.backup()` — never a raw copy of a live DB.
- **`.pre-restore-*` dirs excluded** — a restore leaves the old state at `<target>/.pre-restore-<epoch>`; it is not swept into the next backup.
- Ephemeral excludes (`workspace,tmp,cache,.cache,logs,node_modules,venv,.venv`) apply at the **state top level only** — a legitimately nested `cache/`/`logs/` deeper in the tree is preserved (not silently skipped). Excluded names are printed each run.
- Credential source printed; flags node-IMDS vs the scoped `EnterpriseAgentDevRole`.
- 4 GiB single-PUT cap with a clear error (add multipart if state ever approaches it).

## Run (in the agent)
```
python3 scripts/memory_backup/preflight_s3.py          # readiness
python3 scripts/memory_backup/backup_memory.py         # one manual backup (both roots)
python3 scripts/memory_backup/restore_memory.py        # list backups (shows relative keys)
python3 scripts/memory_backup/restore_memory.py state  YYYY/MM/DD/HHMMSSZ.tar.gz   # recover state
python3 scripts/memory_backup/restore_memory.py memory YYYY/MM/DD/HHMMSSZ.tar.gz   # recover memory
```
Scheduled every 8h via the `memory_s3_backup` cron job (kept alive by the
MCP-server watchdog). Retention: set a 14-day S3 lifecycle rule on
`netsuite-agent/` (console; the role has no delete permission by design).

## What this achieves vs EBS
Everything EBS would give for durability — **recoverable after node
replacement** — the one difference being the S3 restore is a **manual
`restore_memory.py` run**, whereas EBS is automatic/live. For "never lose
more than the backup interval," S3 alone is sufficient.
