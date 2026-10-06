---
name: wego-coding-automation-style
description: Apply Nikhil's coding and automation delivery style for Wego projects. Use when writing, refactoring, reviewing, or planning Python + Robot Framework automations so implementation choices, naming, modularity, error handling, and delivery practices stay consistent with his team standards.
---

# Wego Coding + Automation Style

## 1) Core engineering approach

- Build for unattended execution first.
- Prefer stable, explicit logic over clever shortcuts.
- Keep automations easy to debug by another engineer in minutes.
- Optimize for maintainability and operational reliability, not one-off speed.

## 2) Tech split

- Robot files orchestrate workflow steps and business process sequence.
- Python helper files implement keyword logic, integrations, parsing, and reusable utilities.
- Data warehouse/reporting logic stays separated in dedicated modules (e.g., `BQ_*.py`).

Do not mix heavy SQL/data-loading logic directly into Robot steps when a Python helper module is more maintainable.

## 3) Reuse-first implementation

Before adding new code:

1. Look for an existing module with similar supplier/process behavior.
2. Reuse proven helper patterns.
3. Extract shared behavior into reusable functions only when it is used by multiple modules.

Avoid premature abstraction. Create shared utilities when reuse is real.

## 4) Naming and readability

- Use descriptive, domain-relevant names that match finance/ops terminology.
- Keep file names and module names aligned so ownership is obvious.
- Keep functions short and single-purpose where possible.
- Prefer explicit variables over ambiguous abbreviations (unless business-standard abbreviations are already established).

## 5) Error handling and observability

- Fail with clear, actionable error messages.
- Log critical decision points: input source, filters applied, output counts, final action.
- Catch expected integration failures (network/auth/data format) and surface context.
- Avoid swallowing exceptions silently.

## 6) Data and integration hygiene

- Validate incoming data shape before transformation/load.
- Keep credentials/secrets out of source code.
- Avoid hardcoded local paths and environment-specific assumptions.
- Keep side effects (uploads, status updates, API writes) explicit and traceable.

## 7) PR/review quality bar

- The job follows the established module structure.
- New logic is testable (at least component-level when possible).
- Logging is sufficient for Jenkins/server runtime diagnosis.
- Backward compatibility is maintained unless explicitly requested.

## 8) Delivery mindset

- Think in terms of business outcomes: hours saved, failure reduction, operational consistency.
- Prefer incremental improvements over risky big-bang rewrites.
- When proposing enhancements, include impact and rollout risk.
