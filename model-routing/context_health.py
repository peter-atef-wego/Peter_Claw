"""
context_health.py — Knowledge File Health Scoring
Scores all knowledge/memory files by freshness, importance, and size efficiency.
Outputs a ranked report to memory/knowledge/context_health.md
Source: OpenClaw Architecture Guide v1.0 (Duncan Reid)

Run: python3 model-routing/context_health.py
"""

import os
import math
import datetime

# ── Configuration ──────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(REPO_ROOT, "memory", "knowledge", "context_health.md")
HALF_LIFE_DAYS = 14

# Importance weights per file (1.0 = critical, 0.5 = low)
IMPORTANCE = {
    "MEMORY.md":                            1.0,
    "memory/knowledge/decisions.md":        0.8,
    "memory/knowledge/cron_resilience.md":  0.8,
    "memory/knowledge/people.md":           0.7,
    "knowledge/company/wego-business.md":   0.6,
    "knowledge/company/systems-architecture.md": 0.6,
    "knowledge/company/org-structure.md":   0.6,
    "knowledge/company/glossary.md":        0.5,
    "memory/knowledge/projects.md":         0.6,
    "memory/knowledge/action_tracker.md":   0.6,
}

# Target line budgets per file
TARGET_LINES = {
    "MEMORY.md":                            100,
    "memory/knowledge/decisions.md":        80,
    "memory/knowledge/cron_resilience.md":  60,
    "memory/knowledge/people.md":           150,
    "knowledge/company/wego-business.md":   120,
    "knowledge/company/systems-architecture.md": 80,
    "knowledge/company/org-structure.md":   60,
    "knowledge/company/glossary.md":        80,
    "memory/knowledge/projects.md":         80,
    "memory/knowledge/action_tracker.md":   80,
}

# Files to scan (relative to repo root)
SCAN_FILES = list(IMPORTANCE.keys())
# Also scan all skills SKILL.md files
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")
if os.path.exists(SKILLS_DIR):
    for skill in os.listdir(SKILLS_DIR):
        skill_file = os.path.join("skills", skill, "SKILL.md")
        if os.path.exists(os.path.join(REPO_ROOT, skill_file)):
            SCAN_FILES.append(skill_file)
            IMPORTANCE.setdefault(skill_file, 0.6)
            TARGET_LINES.setdefault(skill_file, 100)


def freshness_score(filepath: str) -> float:
    """Score based on file modification time. Halves every HALF_LIFE_DAYS days."""
    try:
        mtime = os.path.getmtime(filepath)
        age_days = (datetime.datetime.now().timestamp() - mtime) / 86400
        return 0.5 ** (age_days / HALF_LIFE_DAYS)
    except FileNotFoundError:
        return 0.0


def size_efficiency_score(filepath: str, target_lines: int) -> float:
    """Score penalises bloated files. Capped at 1.0."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            actual_lines = sum(1 for _ in f)
        if actual_lines == 0:
            return 1.0
        return min(1.0, target_lines / actual_lines)
    except FileNotFoundError:
        return 0.0


def health_score(freshness: float, importance: float, size_eff: float) -> float:
    return round(0.5 * freshness + 0.3 * importance + 0.2 * size_eff, 3)


def status_label(score: float) -> str:
    if score >= 0.7:
        return "🟢 Fresh"
    elif score >= 0.5:
        return "🟡 Aging"
    elif score >= 0.3:
        return "🟠 Stale"
    else:
        return "🔴 Critical"


def run():
    results = []
    today = datetime.date.today().isoformat()

    for rel_path in SCAN_FILES:
        abs_path = os.path.join(REPO_ROOT, rel_path)
        imp = IMPORTANCE.get(rel_path, 0.5)
        target = TARGET_LINES.get(rel_path, 100)

        fresh = freshness_score(abs_path)
        size_eff = size_efficiency_score(abs_path, target)
        score = health_score(fresh, imp, size_eff)
        status = status_label(score)
        exists = os.path.exists(abs_path)

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                actual_lines = sum(1 for _ in f)
        except FileNotFoundError:
            actual_lines = 0

        results.append({
            "file": rel_path,
            "score": score,
            "status": status,
            "freshness": round(fresh, 3),
            "importance": imp,
            "size_eff": round(size_eff, 3),
            "actual_lines": actual_lines,
            "target_lines": target,
            "exists": exists,
        })

    # Sort by score ascending (worst first — needs most attention)
    results.sort(key=lambda x: x["score"])

    # Write report
    lines = [
        f"# Context Health Report",
        f"",
        f"_Generated: {today}. Formula: `health = 0.5×freshness + 0.3×importance + 0.2×size_efficiency`_",
        f"_Freshness half-life: {HALF_LIFE_DAYS} days. Files sorted by health score (worst first)._",
        f"",
        f"## Health Summary",
        f"",
        f"| File | Score | Status | Lines | Target | Action |",
        f"|---|---|---|---|---|---|",
    ]

    for r in results:
        action = "No action" if r["score"] >= 0.7 else (
            "Review soon" if r["score"] >= 0.5 else (
            "Update or archive" if r["score"] >= 0.3 else "Update immediately"))
        lines.append(
            f"| `{r['file']}` | {r['score']} | {r['status']} | {r['actual_lines']} | {r['target_lines']} | {action} |"
        )

    lines += [
        f"",
        f"## Files Needing Attention",
        f"",
    ]

    critical = [r for r in results if r["score"] < 0.5]
    if critical:
        for r in critical:
            lines.append(f"- **{r['file']}** — Score {r['score']} ({r['status']}). Lines: {r['actual_lines']}/{r['target_lines']}.")
    else:
        lines.append("All files are healthy. No immediate action needed.")

    lines += [
        f"",
        f"## MEMORY.md Budget Check",
        f"",
    ]

    memory_file = os.path.join(REPO_ROOT, "MEMORY.md")
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            memory_lines = sum(1 for _ in f)
        if memory_lines > 120:
            lines.append(f"⚠️ **MEMORY.md is {memory_lines} lines — over 120 line budget. Run `/memory-update` to prune.**")
        elif memory_lines > 100:
            lines.append(f"🟡 MEMORY.md is {memory_lines} lines — approaching budget. Monitor.")
        else:
            lines.append(f"✅ MEMORY.md is {memory_lines} lines — within budget.")
    except FileNotFoundError:
        lines.append("MEMORY.md not found.")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Health report written to: {OUTPUT_FILE}")
    print(f"Files scored: {len(results)}")
    critical_count = len([r for r in results if r['score'] < 0.3])
    if critical_count:
        print(f"⚠️  {critical_count} file(s) in CRITICAL state — update immediately.")


if __name__ == "__main__":
    run()
