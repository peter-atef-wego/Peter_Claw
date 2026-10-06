#!/usr/bin/env python3
"""backup_memory.py — snapshot openclaw STATE + curated MEMORY to S3.

Mirrors the flights-pricing agent's S3 layout so S3 ALONE is a complete,
self-contained restore point — no EBS, no GitHub needed to recover:

  netsuite-agent/state/backup-<ts>.tar.gz    <- ~/.openclaw runtime state
                                                (sqlite / sessions / config),
                                                minus git-backed workspace + ephemerals
  netsuite-agent/memory/backup-<ts>.tar.gz   <- curated memory: MEMORY.md + memory/
                                                (also in GitHub; mirrored here so an
                                                 S3-only restore is fully sufficient)

Pure stdlib (pod has no aws CLI / boto3 / sqlite3 binary). LOUD on failure.

Review fixes applied:
  • .pre-restore-* dirs are excluded (were bloating every snapshot after a restore)
  • ephemeral excludes apply at the STATE-ROOT top level ONLY, so a legitimately
    nested dir named cache/logs/tmp deeper in the tree is NOT silently skipped
  • the excluded top-level dir names are printed (no silent truncation)
  • the resolved credential source is printed (flags node-IMDS vs scoped role)
"""
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3lite  # noqa: E402

STATE_DIR = os.environ.get("STATE_DIR", "/home/openclaw/.openclaw")
WORKSPACE = os.environ.get("WORKSPACE_DIR", os.path.join(STATE_DIR, "workspace"))
BUCKET = os.environ.get("BACKUP_BUCKET", "wego-enterprise-agent-logs-us-east-1-794531973703")
BASE_PREFIX = os.environ.get("BACKUP_BASE_PREFIX", "netsuite-agent")
MAX_UPLOAD_BYTES = int(os.environ.get("BACKUP_MAX_BYTES", str(4 * 1024 ** 3)))

# Top-level dirs in STATE_DIR that are ephemeral or durable elsewhere.
STATE_TOPLEVEL_EXCLUDE = set(filter(None, os.environ.get(
    "BACKUP_STATE_EXCLUDE",
    "workspace,tmp,cache,.cache,logs,node_modules,venv,.venv").split(",")))


def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


def _is_sqlite(path):
    if path.endswith((".sqlite", ".db")):
        return True
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _copy_file(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if _is_sqlite(src):
        try:
            sc = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            dc = sqlite3.connect(dest)
            sc.backup(dc)          # consistent snapshot of a live (WAL) DB
            dc.close(); sc.close()
            return True            # counted as sqlite
        except sqlite3.Error as e:
            fail(f"sqlite snapshot failed for {src}: {e}")
    with open(src, "rb") as a, open(dest, "wb") as b:
        b.write(a.read())
    return False


def snapshot_state(src_root, dest_root):
    """Walk STATE_DIR; exclude ephemeral dirs at the TOP LEVEL only and any
    .pre-restore-* dir. Returns (files, sqlite_count, excluded_toplevel)."""
    files = sqlite_n = 0
    excluded = []
    for dp, dn, fn in os.walk(src_root):
        if os.path.realpath(dp) == os.path.realpath(src_root):
            keep = []
            for d in list(dn):
                if d in STATE_TOPLEVEL_EXCLUDE or d.startswith(".pre-restore-"):
                    excluded.append(d)
                else:
                    keep.append(d)
            dn[:] = keep
        rel = os.path.relpath(dp, src_root)
        for name in fn:
            if name.endswith(("-wal", "-shm")):
                continue
            src = os.path.join(dp, name)
            if not os.path.isfile(src) or os.path.islink(src):
                continue
            dest = os.path.join(dest_root, name) if rel == "." \
                else os.path.join(dest_root, rel, name)
            if _copy_file(src, dest):
                sqlite_n += 1
            files += 1
    return files, sqlite_n, excluded


def snapshot_paths(paths, dest_root):
    """Copy an explicit list of files/dirs (the curated memory) into dest_root."""
    files = sqlite_n = 0
    for p in paths:
        if not os.path.exists(p):
            continue
        if os.path.isfile(p):
            if _copy_file(p, os.path.join(dest_root, os.path.basename(p))):
                sqlite_n += 1
            files += 1
        else:
            parent = os.path.dirname(os.path.abspath(p))
            for dp, _dn, fn in os.walk(p):
                rel = os.path.relpath(dp, parent)
                for name in fn:
                    src = os.path.join(dp, name)
                    if not os.path.isfile(src) or os.path.islink(src):
                        continue
                    if _copy_file(src, os.path.join(dest_root, rel, name)):
                        sqlite_n += 1
                    files += 1
    return files, sqlite_n, []


def pack_and_upload(name, snap_dir, ts, key_suffix, creds, work):
    archive = os.path.join(work, f"{name}-{ts}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(snap_dir, arcname=".")
    size = os.path.getsize(archive)
    if size > MAX_UPLOAD_BYTES:
        fail(f"[{name}] archive {size} bytes exceeds cap {MAX_UPLOAD_BYTES} "
             f"— widen excludes or add multipart upload")
    # Date-partitioned key (matches the flights-pricing agent):
    #   netsuite-agent/<root>/YYYY/MM/DD/HHMMSSZ.tar.gz
    key = f"{BASE_PREFIX}/{name}/{key_suffix}"
    try:
        s3lite.put_object(creds, BUCKET, key, open(archive, "rb").read())
    except RuntimeError as e:
        fail(f"[{name}] upload failed: {e}")
    return key, size


def main():
    if not os.path.isdir(STATE_DIR):
        fail(f"STATE_DIR {STATE_DIR} does not exist")

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")                 # local archive filename
    key_suffix = now.strftime("%Y/%m/%d/%H%M%SZ.tar.gz")  # S3 date-partitioned key
    t0 = time.time()
    try:
        creds = s3lite.resolve_creds()
    except RuntimeError as e:
        fail(str(e))

    with tempfile.TemporaryDirectory() as work:
        # ── state root ───────────────────────────────────────────────────
        state_snap = os.path.join(work, "state_snap"); os.makedirs(state_snap)
        sf, ss, excluded = snapshot_state(STATE_DIR, state_snap)
        skey, ssize = pack_and_upload("state", state_snap, ts, key_suffix, creds, work)

        # ── memory root (curated; also in git, mirrored for S3-only restore) ─
        mem_snap = os.path.join(work, "mem_snap"); os.makedirs(mem_snap)
        mpaths = [os.path.join(WORKSPACE, "MEMORY.md"),
                  os.path.join(WORKSPACE, "memory")]
        mf, ms, _ = snapshot_paths(mpaths, mem_snap)
        mkey, msize = pack_and_upload("memory", mem_snap, ts, key_suffix, creds, work)

    note = ""
    if getattr(creds, "source", "").startswith("imds"):
        note = ("  NOTE: creds via node IMDS role (not the scoped "
                "EnterpriseAgentDevRole) — works, but ask infra to scope it for "
                "least privilege.")
    print(f"OK state:  s3://{BUCKET}/{skey} ({ssize} bytes, {sf} files, {ss} sqlite; "
          f"excluded top-level: {sorted(excluded) or 'none'})")
    print(f"OK memory: s3://{BUCKET}/{mkey} ({msize} bytes, {mf} files)")
    print(f"creds={creds.source}  total={time.time() - t0:.0f}s{note}")


if __name__ == "__main__":
    main()
