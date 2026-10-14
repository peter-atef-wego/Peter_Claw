---
name: openclaw-nova-mirror
description: Validate and maintain exact mirror sync between the OpenClaw workspace and openclaw-nova (wego/openclaw-nova). Ensures no file/directory mismatches.
---

# openclaw-nova Mirror Sync Validation

Maintains 1:1 parity between the OpenClaw workspace and the openclaw-nova public mirror. Prevents drift, file loss, or structural mismatches.

## Validation Rules

When syncing the workspace → openclaw-nova:

1. **Pre-sync check**: Compare file counts and directory trees
2. **Sync operation**: Copy all files/dirs from the workspace
3. **Exclude list** (do not copy to mirror):
   - BOOTSTRAP.md
   - CLAUDE.md
   - ENVIRONMENT.md
   - IDENTITY.md
   - SOUL.md
   - TOOLS.md
   - USER.md
   - .env.example (optional)
   - tmp_*.json files
   - *.pyc files

4. **Post-sync validation** (must pass before push):
   - File count match (workspace == mirror)
   - Directory tree match (workspace == mirror)
   - No extra files in mirror
   - No missing files from mirror
   - All subdirectories present (jira/AI_Automation_Team, jira/NetSuite, etc.)

## Validation Script

```bash
# Pre-sync
find /home/openclaw/.openclaw/workspace -type f -not -path '*/.git*' -not -path '*/.venv/*' ! -name '.gitkeep' ! -name 'BOOTSTRAP.md' ! -name 'CLAUDE.md' ! -name 'ENVIRONMENT.md' ! -name 'IDENTITY.md' ! -name 'SOUL.md' ! -name 'TOOLS.md' ! -name 'USER.md' ! -name '.env.example' ! -name 'tmp_*.json' ! -name '*.pyc' | sed 's|/home/openclaw/.openclaw/workspace/||' | sort > /tmp/nova_files.txt

cd /tmp/openclaw-nova && find . -type f -not -path '*/.git*' -not -path '*/.venv/*' ! -name '.gitkeep' | sed 's|^\./||' | sort > /tmp/mirror_files.txt

# Validate
if diff /tmp/nova_files.txt /tmp/mirror_files.txt > /dev/null 2>&1; then
  echo "✅ FILES MATCH"
else
  echo "❌ FILE MISMATCH"
  diff /tmp/nova_files.txt /tmp/mirror_files.txt
  exit 1
fi

# Directory validation
cd /home/openclaw/.openclaw/workspace && find . -type d -not -path '*/.git*' -not -path '*/.venv/*' | sort > /tmp/nova_dirs.txt
cd /tmp/openclaw-nova && find . -type d -not -path '*/.git*' -not -path '*/.venv/*' | sort > /tmp/mirror_dirs.txt

if diff /tmp/nova_dirs.txt /tmp/mirror_dirs.txt > /dev/null 2>&1; then
  echo "✅ DIRECTORIES MATCH"
else
  echo "❌ DIRECTORY MISMATCH"
  diff /tmp/nova_dirs.txt /tmp/mirror_dirs.txt
  exit 1
fi

echo "✅ SYNC VALIDATION PASSED"
```

## When to Use

1. **Before pushing to openclaw-nova**: Run full validation
2. **After each sync**: Confirm no drift
3. **Scheduled sync job**: Include in cron (weekly/monthly)

## Known Safe Excludes

These files/folders are internal-only and should never appear in mirror:
- Personal identity files (BOOTSTRAP, CLAUDE, IDENTITY, SOUL, TOOLS, USER, ENVIRONMENT)
- Temp test files (tmp_*.json)
- Python cache (*.pyc)
- Development envs (.env.example)

## Troubleshooting

**"FILE MISMATCH"**: Run diff command to see what's missing/extra. Copy missing files or delete extras before pushing.

**"DIRECTORY MISMATCH"**: Ensure subdirectories like jira/AI_Automation_Team are created (even if empty with .gitkeep).

**Large file count difference**: Check if .git or .venv got included in comparison. Use `-not -path '*/.git*'` and `-not -path '*/.venv/*'` filters.
