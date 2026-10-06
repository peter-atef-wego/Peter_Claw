#!/usr/bin/env python3
"""
Bootstrap Validation Agent — Runs on every restart to ensure consistency.

Purpose:
- Verify tier mappings are correct (Sonnet floor, Haiku removed 2026-06-16)
- Check all critical files are NOT stale
- Validate MEMORY.md section counts
- Exit 0 if all checks pass, exit 1 if any fail

This prevents stale memory from leaking into responses after gateway restart.
"""

import os
import sys
import json
import hashlib
from pathlib import Path

# Defaults to the live OpenClaw workspace. Override with OPENCLAW_WORKSPACE so the
# same checks can run against a plain checkout (e.g. in CI).
WORKSPACE = Path(
    os.environ.get("OPENCLAW_WORKSPACE")
    or Path.home() / ".openclaw" / "workspace"
)

def check_memory_consistency():
    """Verify MEMORY.md has all sections + correct tier mapping."""
    memory_file = WORKSPACE / "MEMORY.md"
    
    if not memory_file.exists():
        print("❌ MEMORY.md missing")
        return False
    
    content = memory_file.read_text()
    
    # Core sections that must remain in the lean MEMORY.md core
    # (2026-07-01: MEMORY.md was split into a lean always-loaded core + a
    #  full changelog archive so it fits the session context window. The
    #  dated §8/§30/§33 history now lives in memory/knowledge/memory_changelog.md.)
    required_sections = [
        "## 1. User Context",
        "## 6. Model Routing",
        "## 7. Active Behavioral Rules",
    ]
    for section in required_sections:
        if section not in content:
            print(f"❌ MEMORY.md missing core section: {section}")
            return False

    # Tier routing: Sonnet floor, Opus 4.8 as L4 ceiling, Haiku removed
    if "claude-sonnet-4.6" not in content:
        print("❌ MEMORY.md missing Sonnet as L1/L3 tier")
        return False
    stale_opus = [v for v in ("claude-opus-4.6", "claude-opus-4.7") if v in content]
    if stale_opus:
        print(f"❌ MEMORY.md contains stale {', '.join(stale_opus)} (should be claude-opus-4.8)")
        return False
    low = content.lower()
    if "claude-haiku" in low and "removed" not in low:
        print("❌ MEMORY.md has an active Haiku reference (should be removed)")
        return False
    # DM tier signature rule must survive in the core
    if "L1 (Sonnet)" not in content:
        print("❌ MEMORY.md missing DM tier signature rule")
        return False

    # Core is intentionally lean now — just guard against corruption/empty.
    core_lines = len(content.split('\n'))
    if core_lines < 80:
        print(f"❌ MEMORY.md core too small ({core_lines} lines) — possibly corrupted")
        return False

    # Nothing-lost guarantee: the full dated history must exist in the archive.
    changelog = WORKSPACE / "memory" / "knowledge" / "memory_changelog.md"
    if not changelog.exists():
        print("❌ memory/knowledge/memory_changelog.md missing (full history archive)")
        return False
    cl_lines = len(changelog.read_text().split('\n'))
    if cl_lines < 700:
        print(f"❌ memory_changelog.md truncated ({cl_lines} lines, expect >700)")
        return False

    print(f"✅ MEMORY.md valid (core {core_lines} lines + changelog {cl_lines} lines, Sonnet floor confirmed)")
    return True

def check_skill_consistency():
    """Verify dm-model-signature skill has correct L1=Sonnet, L3=Sonnet, L4=Opus 4.8 mapping (Opus 4.7 retired 2026-08-11)."""
    skill_file = WORKSPACE / "skills" / "dm-model-signature" / "SKILL.md"
    
    if not skill_file.exists():
        print("❌ dm-model-signature skill missing")
        return False
    
    content = skill_file.read_text()
    
    # L1 = Sonnet for DMs (Haiku removed 2026-06-16)
    if "claude-sonnet-4.6" not in content:
        print("❌ dm-model-signature skill missing Sonnet as L1/L3 tier")
        return False
    
    # L3 = Sonnet for channel @mentions
    if "claude-sonnet-4.6" not in content:
        print("❌ dm-model-signature skill missing Sonnet as L3 channel tier")
        return False
    
    # L4 = Opus 4.8 — 4.6 and 4.7 are both retired
    stale = [v for v in ("opus-4.6", "opus-4.7") if v in content]
    if stale:
        print(f"❌ dm-model-signature skill has stale {', '.join(stale)} (should be opus-4.8)")
        return False

    if "claude-opus-4.8" not in content:
        print("❌ dm-model-signature skill missing Opus 4.8 as L4 tier")
        return False

    print("✅ dm-model-signature skill consistent (L1=Sonnet, L3=Sonnet, L4=Opus 4.8)")
    return True

def check_operating_md():
    """Verify OPERATING.md has DM signature mandate."""
    op_file = WORKSPACE / "agents" / "nova-pro" / "OPERATING.md"
    
    if not op_file.exists():
        print("❌ OPERATING.md missing")
        return False
    
    content = op_file.read_text()
    
    if "Slack DM Model Signature" not in content:
        print("❌ OPERATING.md missing DM signature mandate")
        return False
    
    print("✅ OPERATING.md has DM signature mandate")
    return True

def check_manifest_md():
    """Verify MANIFEST.md loads dm-model-signature in Always Loaded section."""
    manifest_file = WORKSPACE / "agents" / "nova-pro" / "MANIFEST.md"
    
    if not manifest_file.exists():
        print("❌ MANIFEST.md missing")
        return False
    
    content = manifest_file.read_text()
    
    if "dm-model-signature" not in content:
        print("❌ MANIFEST.md does not load dm-model-signature skill")
        return False
    
    if "Always Loaded" not in content:
        print("❌ MANIFEST.md missing Always Loaded section")
        return False
    
    print("✅ MANIFEST.md loads dm-model-signature in Always Loaded")
    return True


def check_bu_code_rule():
    """Verify CLAUDE.md has the BU Code field rule (cseg_msa_bu_code only)."""
    claude_file = WORKSPACE / "skills" / "wego-netsuite" / "CLAUDE.md"

    if not claude_file.exists():
        print("❌ CLAUDE.md missing")
        return False

    content = claude_file.read_text()

    if "cseg_msa_bu_code" not in content:
        print("❌ CLAUDE.md missing BU Code field rule (cseg_msa_bu_code)")
        return False

    if "5.10" not in content:
        print("❌ CLAUDE.md missing §5.10 BU Code hard rule")
        return False

    print("✅ CLAUDE.md has BU Code field rule (§5.10 cseg_msa_bu_code)")
    return True

def main():
    """Run all checks. Exit 0 if all pass, 1 if any fail."""
    print("\n🔍 Bootstrap Validation Agent (2026-05-20)")
    print("=" * 60)
    
    checks = [
        ("MEMORY.md Consistency", check_memory_consistency),
        ("DM Signature Skill", check_skill_consistency),
        ("OPERATING.md Mandate", check_operating_md),
        ("MANIFEST.md Loading", check_manifest_md),
        ("BU Code Field Rule", check_bu_code_rule),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append(result)
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            results.append(False)
    
    print("=" * 60)
    
    if all(results):
        print("✅ ALL CHECKS PASSED — Ready for deployment")
        print("   Tier mapping is consistent (Sonnet floor)")
        print("   DM signature will display correctly")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"❌ {failed}/{len(results)} checks FAILED — Fix before proceeding")
        sys.exit(1)

if __name__ == "__main__":
    main()
