---
name: wego-github-coding-style
description: Apply Nikhil’s GitHub coding style for Wego automations (Python + Robot Framework), including repo/module structure, naming, code quality, and PR standards. Use when creating, refactoring, reviewing, or preparing commits/PRs so code matches established team conventions.
---

# Wego GitHub Coding Style

Follow these standards when producing code changes for Nikhil’s automation repos.

## 1) Repo and module structure

Use domain-based folders under `rpa/` (Finance, Flights, Marketing, Ops, etc.).
For each automation module, keep this standard trio together:

1. Robot orchestration file (`<job>.robot` or `<job>_main.robot`)
2. Python workflow/helper file (`Resource_<Job>.py`)
3. Data/BQ helper file (`BQ_<Job>.py`)

Keep module names aligned across Robot + Python files.

## 2) Responsibilities split

- Robot files: process flow and step orchestration.
- `Resource_*.py`: integrations, parsing, keyword logic, reusable helpers.
- `BQ_*.py`: warehouse/load/query behavior.

Avoid burying complex data/business logic directly inside Robot files when Python modules are clearer.

## 3) Naming and readability

- Python helper files: prefixed naming (`Resource_`, `BQ_`) with clear domain suffix.
- Robot files: lowercase with underscores.
- Function names should be explicit and business-meaningful.
- Prefer small, single-purpose functions where practical.

## 4) Reliability and logging

- Design for unattended scheduled execution.
- Fail with actionable errors.
- Log: input source, key filters, record counts, and final output action.
- Handle expected failures (auth/network/format) with context.

## 5) Data and config hygiene

- Validate upstream data before transformation/load.
- Keep secrets out of source control.
- Avoid machine-specific hardcoded paths.
- Make external side effects (uploads/status writes/API updates) explicit in logs.

## 6) GitHub commit and PR standards

- Keep commits scoped to one logical change.
- Use clear commit messages (what changed + intent).
- Preserve backward compatibility unless breaking change is requested.
- Add/adjust tests or validation steps when possible.
- Include brief PR notes: problem, solution, risk, rollout/verification steps.

## 7) Legacy-aware development

This codebase includes legacy variations (`Resources_` vs `Resource_`, custom Robot names).
Do not mass-rename stable modules without explicit request.
For new modules, follow the preferred modern pattern above.
