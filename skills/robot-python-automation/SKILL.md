---
name: robot-python-automation
description: Robot Framework + Python automation design, coding patterns, execution, testing, and debugging. Use when building or reviewing automations in this stack.
---

# Robot Framework + Python Automation

This skill captures the engineering patterns Nikhil’s team uses for reliable, unattended automations with Robot Framework and Python.

## 1) Architecture split

- **Robot files**: orchestration, business flow, high‑level steps.
- **Python modules**: keyword implementations, integrations, parsing, reusable utilities.

Why: this separation keeps Robot files readable and makes Python logic testable.

## 2) Project structure

Recommended module trio (for Wego work):
1. `<job>.robot` (or `<job>_main.robot`)
2. `Resource_<Job>.py`
3. `BQ_<Job>.py` (for data/warehouse logic)

Keep names aligned so ownership and purpose are obvious.

## 3) Keyword design (Python)

- Use small, single‑purpose keywords.
- Validate inputs early and fail with clear errors.
- Avoid side effects in helper functions unless required.

## 4) Logging standards

For unattended runs, logs must answer:
- What input was used?
- What filters were applied?
- How many records were processed?
- What external side effects occurred?

Log these explicitly. Do not rely on implicit logs.

## 5) Error handling

- Catch predictable failures: auth, network, parsing.
- Retry where safe; avoid infinite loops.
- Fail with actionable messages (include endpoint, file, job name).

## 6) Testing strategy

- Unit test Python helpers where possible.
- Component test APIs and parsing logic.
- Run a smoke test of Robot workflows in staging before scheduling.

## 7) Stability & maintainability

- Prefer deterministic flows over fragile UI interactions.
- Use stable selectors and avoid hardcoded sleeps.
- Avoid local‑path dependencies; use env variables.

## 8) Scheduling & operations

- Jobs should run end‑to‑end without manual intervention.
- Include clear exit status and log summary.
- If scheduling via `scheduler.py`, keep new job execution explicit.

## 9) Security & secrets

- Never commit secrets.
- Use secret managers or environment variables.
- Mask secrets in logs.

## 10) Common pitfalls

- Overloading Robot files with logic (move to Python).
- Silent failures (always log why a step failed).
- Inconsistent naming across files.

## Official references

- Robot Framework User Guide: https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html
- Robot Framework Libraries: https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#libraries
- Python Docs: https://docs.python.org/3/
