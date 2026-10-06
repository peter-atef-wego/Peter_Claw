---
name: nik-memory-sync
description: Keep Nikhil’s memory and skills aligned between OpenClaw runtime files and the openclaw-nova GitHub repo. Use when updating memory/skills, syncing changes, or reconciling edits made directly on GitHub so both sources stay consistent.
---

# Nikhil Memory + Skills Sync

Maintain a single, aligned “brain” between local memory/skills and the GitHub repo.

## Core rules

- Treat the GitHub repo as the source of record for memory + skills.
- Auto‑commit and push memory/skills updates without waiting for approval.
- Never commit secrets or credentials.

## When to sync

- After every memory/skills update, commit + push.
- If Nikhil says he edited GitHub, pull immediately and reconcile.
- On session start: pull latest before making changes (if GitHub auth is available).

## Sync procedure (default)

1) `git pull` to ensure local is current.
2) Update relevant memory/skills files.
3) `git add` only the relevant files.
4) `git commit` with a clear message.
5) `git push` to main.

## Conflict handling

- If a merge conflict appears, pause and ask Nikhil how to resolve.
- Never overwrite GitHub changes silently.

## Sensitive data guardrail

- Do not store tokens, passwords, or secrets in memory or skills.
- If a user shares secrets, ask to rotate and do not commit them.
