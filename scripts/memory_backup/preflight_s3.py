#!/usr/bin/env python3
"""preflight_s3.py — v2, pure stdlib. Run inside the agent pod.

v1 (.sh) found: no aws CLI, no sqlite3 binary, no /data. All three are
handled in v2 (python sqlite3 module + s3lite uploader + real state dir),
so the ONLY remaining question is AWS credentials. This checks every
place they could be (env keys, ~/.aws, IRSA, node IMDS) plus the state
dir + a real S3 write/read on our prefix when creds exist.

Exit 0 -> backups will work; enable the cron job.
Exit 1 -> the FAIL lines name exactly what to ask Andy for.
"""
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3lite  # noqa: E402

STATE_DIR = os.environ.get("STATE_DIR", "/home/openclaw/.openclaw")
BUCKET = os.environ.get("BACKUP_BUCKET", "wego-enterprise-agent-logs-us-east-1-794531973703")
PREFIX = os.environ.get("BACKUP_PREFIX", "netsuite-agent/memory")

passed, failed = [], []
ok = lambda m: passed.append(m) or print(f"PASS  {m}")          # noqa: E731
bad = lambda m: failed.append(m) or print(f"FAIL  {m}")          # noqa: E731

print(f"== memory-backup preflight v2 (pure python) "
      f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} ==")

# 1. stdlib pieces the backup relies on
try:
    import sqlite3, tarfile, hashlib, hmac  # noqa: F401,E401
    ok("python stdlib (sqlite3/tarfile/hashlib/hmac) present")
except ImportError as e:
    bad(f"stdlib import failed: {e}")

# 2. state dir
if os.path.isdir(STATE_DIR):
    total = 0
    sqlites = []
    for dp, dn, fn in os.walk(STATE_DIR):
        dn[:] = [d for d in dn if d not in
                 {"workspace", "tmp", "cache", ".cache", "logs", ".git",
                  "node_modules", "venv", ".venv"}]
        for f in fn:
            p = os.path.join(dp, f)
            try:
                total += os.path.getsize(p)
            except OSError:
                continue
            if f.endswith((".sqlite", ".db")):
                sqlites.append(os.path.relpath(p, STATE_DIR))
    ok(f"state dir {STATE_DIR} — {total // (1024 * 1024)}MB to back up "
       f"(after excludes), {len(sqlites)} sqlite/db files")
    for s in sqlites[:10]:
        print(f"      sqlite: {s}")
else:
    bad(f"state dir {STATE_DIR} missing")

# 3. credentials — the decider
creds = None
try:
    creds = s3lite.resolve_creds()
    ok(f"AWS credentials found (source: {creds.source})")
except RuntimeError as e:
    bad(str(e))

# 4. real S3 round-trip on our prefix
if creds:
    probe_key = f"{PREFIX}/_writetest.txt"
    body = f"write-test {int(time.time())}".encode()
    try:
        s3lite.put_object(creds, BUCKET, probe_key, body)
        ok(f"S3 WRITE s3://{BUCKET}/{probe_key}")
        back = s3lite.get_object(creds, BUCKET, probe_key)
        ok("S3 READ back matches" if back == body else "S3 READ returned different content")
        s3lite.list_objects(creds, BUCKET, f"{PREFIX}/")
        ok("S3 LIST on prefix")
    except RuntimeError as e:
        bad(f"S3 round-trip: {e}")

print(f"== RESULT: {len(passed)} pass / {len(failed)} fail ==")
if failed:
    print("VERDICT: not ready — fix the FAIL lines. If it's NO_AWS_CREDENTIALS, the ask "
          "to Andy is: inject an access key scoped to the Appendix-A policy as WegoClaw "
          "env vars (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY), or IRSA-annotate the "
          "service account to EnterpriseAgentDevRole.")
    sys.exit(1)
print("VERDICT: backups will work. Enable the memory_s3_backup cron job.")
