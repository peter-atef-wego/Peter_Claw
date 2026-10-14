#!/usr/bin/env python3
"""
Cron job validator.

cron/jobs.json is the committed source of truth for schedules, but nothing
checked that the scripts it invokes actually exist. On 2026-08-11 the
`openclaw_nova_mirror` job was found pointing at `scripts/nova_mirror_pr.py`,
which is not in the repo — the job had been silently unable to run.

Checks, for every job:
  - the cron expression has 5 fields and plausible ranges
  - every `.py` / `.sh` path in the command exists in the repo
  - job ids are unique

Severity depends on whether the job is live. An **enabled** job whose script is
missing is an error — it fails every tick. A **disabled** job whose script is
missing is a warning: nothing is breaking, but it must not be enabled until the
script is restored. `openclaw_nova_mirror` is in exactly that state as of
2026-08-11.

Paths under /home/openclaw/.openclaw/workspace/ are resolved relative to the repo
root, since that is where the workspace is checked out at runtime.

Usage:
    python3 scripts/validate_cron_jobs.py

Exit 0 if every job is runnable, 1 if not.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKSPACE_PREFIX = "/home/openclaw/.openclaw/workspace/"

FIELD_RANGES = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 7),
]


def check_cron_expr(expr: str, job_id: str, errors: list):
    fields = expr.split()
    if len(fields) != 5:
        errors.append(f"{job_id}: cron expression has {len(fields)} fields, expected 5: {expr!r}")
        return
    for value, (name, lo, hi) in zip(fields, FIELD_RANGES):
        # Accept *, */n, a-b, a,b,c and combinations of those.
        for part in value.split(","):
            part = part.split("/")[0]
            if part == "*":
                continue
            bounds = part.split("-")
            if not all(b.isdigit() for b in bounds):
                errors.append(f"{job_id}: unparseable {name} field {part!r} in {expr!r}")
                continue
            for b in bounds:
                if not (lo <= int(b) <= hi):
                    errors.append(
                        f"{job_id}: {name} value {b} out of range {lo}-{hi} in {expr!r}"
                    )


def resolve(path_str: str) -> Path:
    if path_str.startswith(WORKSPACE_PREFIX):
        return REPO / path_str[len(WORKSPACE_PREFIX):]
    if path_str.startswith("/"):
        # An absolute path outside the workspace — cannot verify from the repo.
        return None
    return REPO / path_str


def main() -> int:
    jobs = json.loads((REPO / "cron" / "jobs.json").read_text())["jobs"]
    errors: list = []
    warnings: list = []
    seen = set()

    print(f"{len(jobs)} job(s) in cron/jobs.json:\n")

    for job in jobs:
        job_id = job.get("id", "<no id>")
        if job_id in seen:
            errors.append(f"{job_id}: duplicate job id")
        seen.add(job_id)

        if job.get("id") != job.get("name"):
            errors.append(f"{job_id}: id and name differ ({job.get('name')!r})")

        expr = job.get("schedule", {}).get("expr", "")
        check_cron_expr(expr, job_id, errors)

        cmd = job.get("command", "")
        scripts = re.findall(r"[\w./-]+\.(?:py|sh)", cmd)
        if not scripts and "git " not in cmd:
            errors.append(f"{job_id}: command references no script and is not a git command: {cmd!r}")

        missing = []
        for sc in scripts:
            target = resolve(sc)
            if target is None:
                continue
            if not target.exists():
                missing.append(sc)
        for sc in missing:
            msg = f"{job_id}: command references {sc}, which does not exist in the repo"
            if job.get("enabled"):
                errors.append(msg + " — job is ENABLED and fails every tick")
            else:
                warnings.append(msg + " — job is disabled, so nothing is failing; do not enable it until the script is restored")

        flag = "enabled " if job.get("enabled") else "disabled"
        note = f"  ⚠️  missing: {', '.join(missing)}" if missing else ""
        print(f"  [{flag}] {job_id:24} {expr:16}{note}")

    print()
    for w in warnings:
        print(f"⚠️  {w}")
    if warnings:
        print()

    if errors:
        print("❌ CRON CONFIG INVALID")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("✅ Every enabled cron job has a valid schedule and a script that exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
