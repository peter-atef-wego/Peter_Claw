#!/usr/bin/env python3
"""Render the NetSuite MCP activity JSONL into a daily markdown table.

Reads:  logs/netsuite-mcp/YYYY-MM-DD.jsonl   (gitignored, written by netsuite_mcp_server.py)
Writes: memory/logs/netsuite-mcp/YYYY-MM-DD.md   (committed to git, viewable on GitHub)

Usage:
    python3 scripts/render_netsuite_mcp_logs.py             # render today (UTC)
    python3 scripts/render_netsuite_mcp_logs.py 2026-05-21  # render a specific day
    python3 scripts/render_netsuite_mcp_logs.py --all       # render every JSONL on disk

Cheap by design: only reads/writes files, never calls the agent or any
LLM. Intended to run from cron once a day.
"""

import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSONL_DIR = os.path.join(REPO_ROOT, "logs", "netsuite-mcp")
MD_DIR = os.path.join(REPO_ROOT, "memory", "logs", "netsuite-mcp")


def _human_bytes(n):
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n}B"


def _human_duration(ms):
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{int(ms)}ms"


def _args_cell(args):
    if not isinstance(args, dict) or not args:
        return "—"
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 40:
            s = s[:40] + "…"
        parts.append(f"`{k}`={s}")
    cell = ", ".join(parts)
    return cell if len(cell) <= 120 else cell[:120] + "…"


def render_day(day_str):
    src = os.path.join(JSONL_DIR, f"{day_str}.jsonl")
    if not os.path.exists(src):
        return None, 0

    entries = []
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        return None, 0

    md = [f"# {day_str} — NetSuite MCP activity", ""]
    md.append(f"_{len(entries)} tool calls_")
    md.append("")
    md.append("| Time (UTC) | Tool | Scope | Args | Status | Rows | Bytes | Duration |")
    md.append("|---|---|---|---|---|---|---|---|")

    total_bytes = 0
    total_duration_ms = 0
    ok_count = 0
    err_count = 0
    per_tool = {}

    for e in entries:
        ts = e.get("ts", "")
        time_part = ts[11:16] if len(ts) >= 16 else ts
        tool = e.get("tool", "?")
        scope = e.get("scope", "")
        args_cell = _args_cell(e.get("args", {}))
        ok = e.get("ok", False)
        status = "✅" if ok else "❌"
        if ok:
            ok_count += 1
        else:
            err_count += 1
        rows = e.get("row_count")
        rows_cell = str(rows) if rows is not None else "—"
        rb = e.get("result_bytes", 0)
        total_bytes += rb
        dur = e.get("duration_ms", 0)
        total_duration_ms += dur

        per_tool.setdefault(tool, {"n": 0, "ok": 0, "err": 0, "bytes": 0, "ms": 0})
        per_tool[tool]["n"] += 1
        per_tool[tool]["ok" if ok else "err"] += 1
        per_tool[tool]["bytes"] += rb
        per_tool[tool]["ms"] += dur

        md.append(
            f"| {time_part} | `{tool}` | {scope} | {args_cell} | {status} | {rows_cell} | "
            f"{_human_bytes(rb)} | {_human_duration(dur)} |"
        )
        if not ok and e.get("error"):
            md.append(
                f"|  |  |  | ↳ error: _{e['error']}_ |  |  |  |  |"
            )

    md.append("")
    md.append(f"**Totals:** {len(entries)} calls · {ok_count} OK · {err_count} errors · "
              f"{_human_bytes(total_bytes)} returned · {_human_duration(total_duration_ms)} total")
    md.append("")
    md.append("## Per-tool breakdown")
    md.append("")
    md.append("| Tool | Calls | OK | Err | Bytes returned | Total time |")
    md.append("|---|---|---|---|---|---|")
    for tool in sorted(per_tool, key=lambda t: -per_tool[t]["n"]):
        s = per_tool[tool]
        md.append(f"| `{tool}` | {s['n']} | {s['ok']} | {s['err']} | "
                  f"{_human_bytes(s['bytes'])} | {_human_duration(s['ms'])} |")
    md.append("")

    os.makedirs(MD_DIR, exist_ok=True)
    dst = os.path.join(MD_DIR, f"{day_str}.md")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return dst, len(entries)


def render_all():
    if not os.path.isdir(JSONL_DIR):
        print(f"No JSONL dir at {JSONL_DIR}")
        return
    days = sorted(
        f[:-6] for f in os.listdir(JSONL_DIR)
        if f.endswith(".jsonl") and len(f) >= 16
    )
    for d in days:
        out, n = render_day(d)
        print(f"{d}: {n} entries → {out}" if out else f"{d}: empty")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        render_all()
        return
    day_str = (sys.argv[1] if len(sys.argv) > 1
               else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    out, n = render_day(day_str)
    if out:
        print(f"Rendered {n} entries → {out}")
    else:
        print(f"No log entries for {day_str}")


if __name__ == "__main__":
    main()
