#!/usr/bin/env python3
"""lessons.py — the self-learning loop: capture -> distill -> durable memory.

Modelled on the flights-pricing memory-service curator/distiller (capture raw
observations, distil durable facts, write under governance) but built for this
runtime: Python stdlib only, no sidecar, no inference key in the pod.

Split of duties — deliberately the same as theirs:
  CAPTURE   (deterministic, here)  every report tool outcome is appended to
            lessons.jsonl. Cheap, always on, never blocks the tool.
  DISTIL    (deterministic, here)  aggregate the log into RECURRING patterns
            (same failure 3+ times, unknown report_key, subsidiary misses,
            format changes) and render them to a markdown file the agent
            loads every session. No LLM needed for this tier.
  ACT       (agent + human)        the agent reads the markdown at session
            start and must not repeat a known mistake; anything that changes
            BEHAVIOUR (registry keys, subjects, rules) goes through a PR.
            The loop proposes; a human merges — the agent can't silently
            rewrite its own rules.

Storage lives inside STATE_DIR so the nightly S3 backup carries it:
  ~/.openclaw/reports/lessons.jsonl          raw observations (capped)
  <workspace>/memory/knowledge/learned_lessons.md   distilled, session-loaded
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

STATE_DIR = os.environ.get("STATE_DIR", "/home/openclaw/.openclaw")
WORKSPACE = os.environ.get("WORKSPACE_DIR", os.path.join(STATE_DIR, "workspace"))
LOG_PATH = os.environ.get("LESSONS_LOG", os.path.join(STATE_DIR, "reports", "lessons.jsonl"))
OUT_MD = os.environ.get("LESSONS_MD",
                        os.path.join(WORKSPACE, "memory", "knowledge", "learned_lessons.md"))
MAX_LOG_LINES = int(os.environ.get("LESSONS_MAX_LINES", "5000"))
RECUR_THRESHOLD = int(os.environ.get("LESSONS_RECUR_THRESHOLD", "3"))


def record(event, **fields):
    """Append one observation. Never raises — learning must not break serving."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "event": event}
        for k, v in fields.items():
            if v is None:
                continue
            row[k] = v if isinstance(v, (int, float, bool)) else str(v)[:300]
        with open(LOG_PATH, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        _trim()
    except Exception:
        pass


def _trim():
    try:
        with open(LOG_PATH) as fh:
            lines = fh.readlines()
        if len(lines) > MAX_LOG_LINES:
            with open(LOG_PATH, "w") as fh:
                fh.writelines(lines[-MAX_LOG_LINES:])
    except Exception:
        pass


def _load():
    out = []
    try:
        with open(LOG_PATH) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return out


def distil():
    """Aggregate the raw log into recurring, actionable patterns."""
    rows = _load()
    lessons = []
    if not rows:
        return {"rows": 0, "lessons": lessons}

    fails = [r for r in rows if r.get("event") == "report_error"]

    # 1. the same error code recurring
    for (err, key), n in Counter((r.get("error", "?"), r.get("report_key", "?"))
                                 for r in fails).items():
        if n >= RECUR_THRESHOLD:
            sample = next((r.get("message", "") for r in fails
                           if r.get("error") == err and r.get("report_key") == key), "")
            lessons.append({
                "kind": "recurring_error", "count": n,
                "text": f"`{err}` on report `{key}` has happened {n}x. "
                        f"Latest: {sample[:180]}",
                "action": "Fix the root cause (registry entry / subject / period "
                          "handling) and open a PR — do not keep retrying at runtime."})

    # 2. report_key values callers use that the registry doesn't know
    unknown = Counter(r.get("report_key") for r in rows
                      if r.get("event") == "registry_miss" and r.get("report_key"))
    for key, n in unknown.items():
        if n >= 1:
            lessons.append({
                "kind": "unknown_report_key", "count": n,
                "text": f"Callers used report_key `{key}` {n}x but the registry has no "
                        f"exact entry for it.",
                "action": f"Add `{key}` as an alias (or fix the tool description) in "
                          f"report_sources.json — a miss means registry flags like "
                          f"deliver_as/refresh are silently skipped."})

    # 3. subsidiary names that never match
    subs = Counter(r.get("subsidiary") for r in fails
                   if r.get("error") in ("SUBSIDIARY_FILTER_FAILED", "SUBSIDIARY_AMBIGUOUS")
                   and r.get("subsidiary"))
    for name, n in subs.items():
        if n >= 2:
            lessons.append({
                "kind": "subsidiary_mismatch", "count": n,
                "text": f"Subsidiary `{name}` failed to resolve/filter {n}x.",
                "action": "Check it against the official list in report_sources.json "
                          "(spelling/variant) and add the variant if finance uses it."})

    # 4. attachment format drift (NetSuite changing export type under us)
    fmts = defaultdict(set)
    for r in rows:
        if r.get("event") == "report_served" and r.get("filename"):
            ext = os.path.splitext(r["filename"])[1].lower()
            if ext:
                fmts[r.get("report_key", "?")].add(ext)
    for key, exts in fmts.items():
        if len(exts) > 1:
            lessons.append({
                "kind": "format_drift", "count": len(exts),
                "text": f"Report `{key}` has arrived as {sorted(exts)} — the source "
                        f"export format changed.",
                "action": "Confirm delivery still converts correctly and note the "
                          "current format in report_sources.json."})

    # 5. periods asked for that were never available (scheduling gap, not a bug)
    subs_periods = Counter(r.get("requested_period") for r in rows
                          if r.get("event") == "latest_substituted" and r.get("requested_period"))
    for per, n in subs_periods.items():
        if n >= 2:
            lessons.append({
                "kind": "missing_period", "count": n,
                "text": f"Period `{per}` was asked for {n}x but never exists — the "
                        f"latest was served instead.",
                "action": "Ask Akansha whether that period's report is scheduled; this "
                          "is a NetSuite scheduling gap, not a code bug."})

    lessons.sort(key=lambda x: -x["count"])
    return {"rows": len(rows), "lessons": lessons}


def render(result=None):
    """Write the distilled lessons to the session-loaded markdown file."""
    result = result or distil()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Learned lessons (auto-distilled — do not hand-edit)",
        "",
        f"_Generated {ts} from {result['rows']} observations "
        f"(`~/.openclaw/reports/lessons.jsonl`) by "
        f"`scripts/report_store/lessons.py`._",
        "",
        "Loaded every session. **Read this before answering a report request** — if a "
        "pattern below matches what you're about to do, don't repeat the mistake. "
        "Anything that changes BEHAVIOUR (registry keys, subjects, rules) must go "
        "through a PR: this loop proposes, a human merges.",
        "",
    ]
    if not result["lessons"]:
        lines += ["_No recurring patterns yet._", ""]
    else:
        for L in result["lessons"]:
            lines += [f"### {L['kind']} (x{L['count']})", "", L["text"], "",
                      f"**Action:** {L['action']}", ""]
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines))
    return {"path": OUT_MD, "lessons": len(result["lessons"]), "rows": result["rows"]}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        print(json.dumps(distil(), indent=2))
    else:
        r = render()
        print(f"OK wrote {r['path']} — {r['lessons']} lesson(s) from {r['rows']} observations")
