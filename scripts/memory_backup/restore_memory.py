#!/usr/bin/env python3
"""restore_memory.py — restore a STATE or MEMORY backup from S3.

RUN QUIESCED. Pure stdlib. Mirrors backup_memory.py's two roots:
  state  -> restores openclaw runtime state into ~/.openclaw
            (never touches workspace or other preserved top-level dirs)
  memory -> restores MEMORY.md + memory/ into the workspace

Usage:
  python3 restore_memory.py                      # list both state/ and memory/ backups
  python3 restore_memory.py state  backup-<ts>.tar.gz
  python3 restore_memory.py memory backup-<ts>.tar.gz
Current on-disk state is preserved at <target>/.pre-restore-<epoch> first.
"""
import os
import shutil
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3lite  # noqa: E402

STATE_DIR = os.environ.get("STATE_DIR", "/home/openclaw/.openclaw")
WORKSPACE = os.environ.get("WORKSPACE_DIR", os.path.join(STATE_DIR, "workspace"))
BUCKET = os.environ.get("BACKUP_BUCKET", "wego-enterprise-agent-logs-us-east-1-794531973703")
BASE_PREFIX = os.environ.get("BACKUP_BASE_PREFIX", "netsuite-agent")

# For a STATE restore, never disturb these top-level entries (not in the backup).
STATE_PRESERVE = {"workspace", "tmp", "cache", ".cache", "logs",
                  "node_modules", "venv", ".venv"}


def _rel(name, key):
    """Key relative to the root prefix, e.g. 2026/07/23/082947Z.tar.gz."""
    return key[len(f"{BASE_PREFIX}/{name}/"):]


def _list(creds, name):
    # No filename filter: keys are now date-partitioned (YYYY/MM/DD/HHMMSSZ.tar.gz);
    # sort by LastModified so mixed old-flat + new-nested still orders correctly.
    objs = s3lite.list_objects(creds, BUCKET, f"{BASE_PREFIX}/{name}/")
    objs = [o for o in objs if o["key"].endswith(".tar.gz")]
    return sorted(objs, key=lambda o: o["modified"])


def cmd_list(creds):
    for name in ("state", "memory"):
        objs = _list(creds, name)
        print(f"\n{name}/  ({len(objs)} backups):")
        for o in objs[-10:]:
            print(f"  {o['modified']}  {o['size']:>12}  {_rel(name, o['key'])}")
    print("\nRestore: python3 restore_memory.py <state|memory> <YYYY/MM/DD/HHMMSSZ.tar.gz>")


def cmd_restore(creds, what, key_name):
    if what not in ("state", "memory"):
        sys.exit("first arg must be 'state' or 'memory'")
    target = STATE_DIR if what == "state" else WORKSPACE
    # Accept the relative subpath as listed (date-partitioned or legacy flat name).
    key = f"{BASE_PREFIX}/{what}/{key_name.lstrip('/')}"

    with tempfile.TemporaryDirectory() as work:
        blob = s3lite.get_object(creds, BUCKET, key)
        arc = os.path.join(work, "b.tar.gz"); open(arc, "wb").write(blob)
        unpack = os.path.join(work, "unpack"); os.makedirs(unpack)
        with tarfile.open(arc, "r:gz") as tar:
            tar.extractall(unpack)

        os.makedirs(target, exist_ok=True)
        stamp = str(int(time.time()))
        pre = os.path.join(target, f".pre-restore-{stamp}"); os.makedirs(pre)

        # Move aside only what the archive will replace; for state, keep the
        # preserved top-level dirs (workspace etc.) exactly where they are.
        preserve = STATE_PRESERVE if what == "state" else set()
        restored = set(os.listdir(unpack))
        for entry in os.listdir(target):
            if entry.startswith(".pre-restore-") or entry in preserve:
                continue
            if what == "memory" and entry not in restored:
                continue  # memory restore only overwrites MEMORY.md + memory/
            shutil.move(os.path.join(target, entry), os.path.join(pre, entry))

        moved = 0
        for entry in os.listdir(unpack):
            dst = os.path.join(target, entry)
            if os.path.exists(dst):
                shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
            shutil.move(os.path.join(unpack, entry), dst)
            moved += 1

    print(f"Restored {what} backup {os.path.basename(key_name)} into {target} "
          f"({moved} top-level entries).")
    print(f"Previous {what} state preserved at {pre} — delete after verifying.")
    print("Restart the agent and verify before deleting the .pre-restore dir.")


def main():
    creds = s3lite.resolve_creds()
    if len(sys.argv) < 2:
        cmd_list(creds)
    elif len(sys.argv) == 3:
        cmd_restore(creds, sys.argv[1], sys.argv[2])
    else:
        sys.exit("usage: restore_memory.py [ <state|memory> <backup-<ts>.tar.gz> ]")


if __name__ == "__main__":
    main()
