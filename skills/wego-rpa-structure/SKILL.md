---
name: wego-rpa-structure
description: Follow Nikhil's RPA repository conventions (Python + Robot Framework + BigQuery helpers + scheduler entrypoints). Use when creating, reviewing, or refactoring automations so new jobs match the established folder/file structure and naming patterns.
---

# Wego RPA Structure

Follow this structure when adding or editing automation jobs in the repository.

## 1) Repository shape

Assume a top-level `rpa/` folder with domain-based subfolders, for example:
- `Finance/`
- `Flights/`
- `Marketing/`
- `Flight_OPS/`
- `Hotels_Ops/`
- `SEO_Marketing/`
- `Recruitment/`
- `Subscription_Alert/`

Create new automations inside the relevant domain folder.

## 2) Standard job module pattern

For each automation module, keep related files together in one folder:

- Main Robot file: `*_main.robot` or domain-specific name (`<job>.robot`)
- Resource/helper Python file: `Resource_<Job>.py` (or `Resources_<Job>.py` in legacy modules)
- BigQuery/data helper: `BQ_<Job>.py`
- Optional notifier/helper scripts: e.g., `slack_bot.py`, scheduler helpers

Preferred trio for new work:
1. `<job>.robot`
2. `Resource_<Job>.py`
3. `BQ_<Job>.py`

## 3) Naming conventions

- Use PascalCase after prefixes for Python helper files:
  - `Resource_HotelTrader.py`
  - `BQ_HotelTrader.py`
- Keep Robot file names lowercase with underscores:
  - `hoteltrader_reco.robot`
  - `google_flights_main.robot`
- Match names across Robot + Resource + BQ files so ownership is obvious.

## 4) Separation of concerns

- Put browser/API/business workflow steps in Robot + `Resource_*.py`.
- Put warehouse/query/load logic in `BQ_*.py`.
- Keep module-specific logic local to the module directory.

## 5) Scheduler integration

Use `rpa/scheduler.py` as the central scheduler entrypoint pattern.
When adding a new job:
1. Add/import the job call in scheduler flow.
2. Keep module execution command/path explicit.
3. Preserve existing cadence and error-handling style.

## 6) Practical guardrails for new modules

Before finalizing a new module, verify:
- Folder is in the correct domain.
- Robot file runs end-to-end independently.
- `Resource_*.py` and `BQ_*.py` names align with the module.
- No hardcoded local machine paths or secrets.
- Logging/errors are clear enough for unattended runs.

## 7) Legacy tolerance

This repo contains legacy naming variations. Do not mass-rename working modules unless requested. For new modules, follow the preferred modern pattern above.
