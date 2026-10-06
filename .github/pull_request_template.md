## What changed

<!-- One or two sentences. Lead with the answer. -->

## Why

<!-- The trigger: a Jira ticket, an incident, a Nikhil decision, a stale doc. Link it. -->

- Jira:
- Related PR / incident:

## Scope

Tick what this touches — anything under `agents/`, `skills/`, or `knowledge/` is a
structural change and needs a PR rather than a direct push (see `CLAUDE.md` §
Git Discipline).

- [ ] `agents/` — persona, manifest, operating rules
- [ ] `skills/` — new skill, or a change to an existing SKILL.md
- [ ] `knowledge/` — company knowledge docs
- [ ] `model-routing/` — tier definitions or router logic
- [ ] `cron/` — job schedules (`cron/jobs.json` only; runtime state is gitignored)
- [ ] `scripts/` — executable scripts
- [ ] `memory/` — memory files or protocols
- [ ] Docs only

## Checks

- [ ] `OPENCLAW_WORKSPACE="$PWD" python3 scripts/bootstrap-validate.py` passes
- [ ] Touched `*.py` compile (`python3 -m py_compile <files>`)
- [ ] Touched `*.json` parse
- [ ] No secrets added — real values stay in WegoClaw / `openclaw.env`; only
      `.env.example` carries placeholders
- [ ] `SKILL_REGISTRY.md` updated if a skill was added, removed, or renamed
- [ ] `README.md` counts still match the tree if files were added or removed

## Restart needed?

Does this change a long-running process (e.g. `scripts/netsuite_mcp_server.py`)?
If so the container needs a restart before the new code takes effect — say so
here and tell Nikhil (MEMORY.md § 4).

- [ ] No restart needed
- [ ] Restart needed — flagged to Nikhil

## Memory

- [ ] Logged in `memory/knowledge/action_tracker.md` if this changes state
- [ ] Decision recorded in `memory/knowledge/decisions.md` if this is a decision
