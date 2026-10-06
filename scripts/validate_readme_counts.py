#!/usr/bin/env python3
"""
README count validator.

README.md states counts that are easy to get wrong and easy to leave stale — the
number of skills, MCP tools, standard reports, and cron jobs. Every one of those
was wrong before 2026-08-11 (25 vs 24 skills, 17 vs 24 tools, 9 vs 10 reports,
"7 active" cron jobs when only 3 were enabled), because nothing checked them.

This re-derives each count from the tree and compares it to what README.md
claims. It also verifies that every skill directory is listed in
SKILL_REGISTRY.md, so a new skill cannot be added without registering it.

Usage:
    python3 scripts/validate_readme_counts.py

Exit 0 if the README matches the tree, 1 if not.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def count_skills() -> int:
    """Top-level directories under skills/ (each one is a loadable skill)."""
    return sum(
        1
        for p in (REPO / "skills").iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def count_mcp_tools() -> int:
    """Entries in the TOOLS list in the NetSuite MCP server."""
    src = (REPO / "scripts" / "netsuite_mcp_server.py").read_text()
    start = src.index("TOOLS = [")
    end = src.index("\n]", start)
    return len(re.findall(r'"name":\s*"([a-z0-9_]+)"', src[start:end]))


def count_standard_reports() -> int:
    """Keys in the STANDARD_REPORTS dict."""
    src = (REPO / "scripts" / "netsuite_mcp_server.py").read_text()
    start = src.index("STANDARD_REPORTS = {")
    end = src.index("\n}", start)
    return len(re.findall(r'^    "([a-z0-9_]+)":', src[start:end], re.M))


def count_cron_jobs() -> tuple:
    jobs = json.loads((REPO / "cron" / "jobs.json").read_text())["jobs"]
    return len(jobs), sum(1 for j in jobs if j.get("enabled"))


def find_claim(readme: str, pattern: str, label: str, errors: list):
    """Pull a single integer out of README.md, erroring if the phrasing moved."""
    m = re.search(pattern, readme)
    if not m:
        errors.append(
            f"{label}: could not find the claim in README.md — "
            f"the wording changed, update this validator (pattern: {pattern})"
        )
        return None
    return int(m.group(1))


def main() -> int:
    readme = (REPO / "README.md").read_text()
    registry = (REPO / "SKILL_REGISTRY.md").read_text()
    errors: list = []

    skills = count_skills()
    tools = count_mcp_tools()
    reports = count_standard_reports()
    jobs_total, jobs_enabled = count_cron_jobs()

    print("Derived from the tree:")
    print(f"  skills           = {skills}")
    print(f"  MCP tools        = {tools}")
    print(f"  standard reports = {reports}")
    print(f"  cron jobs        = {jobs_total} defined, {jobs_enabled} enabled")
    print()

    checks = [
        ("skills (section 5.2)", r"Agent skills \((\d+) active\)", skills),
        ("skills (SKILL_REGISTRY row)", r"Registry of all (\d+) skills", skills),
        ("MCP tools (section 3.3)", r"MCP tools exposed \(current count: (\d+)\)", tools),
        ("standard reports (section 3.6)", r"Standard financial reports \((\d+), server-side", reports),
        ("cron jobs defined (section 5.5)", r"Scheduled jobs \((\d+) defined", jobs_total),
        ("cron jobs enabled (section 5.5)", r"(\d+) enabled\)", jobs_enabled),
    ]

    for label, pattern, actual in checks:
        claimed = find_claim(readme, pattern, label, errors)
        if claimed is not None and claimed != actual:
            errors.append(f"{label}: README says {claimed}, tree has {actual}")

    # Every skill directory must appear in SKILL_REGISTRY.md.
    for p in sorted((REPO / "skills").iterdir()):
        if p.is_dir() and not p.name.startswith(".") and p.name not in registry:
            errors.append(f"SKILL_REGISTRY.md: skill '{p.name}' is not registered")

    if errors:
        print("❌ README OUT OF DATE")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("✅ README counts match the tree, all skills registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
