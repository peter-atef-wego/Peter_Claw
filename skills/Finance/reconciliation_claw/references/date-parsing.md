# Date Parsing — Natural Language → `YYYY-MM-DD`

The JSON trigger requires `start_date` and `end_date` in `YYYY-MM-DD`. This file is the conversion table.

**General rules:**
- If year is missing, assume current year.
- If month is missing on the end date, use the start date's month.
- Separators between dates: `to`, `-`, `&`, `→`, `till`, `until`, `through`, `and`. First number = start, second = end.
- "Same date" inputs (one date only, or "same" for end) → set both `start_date` and `end_date` to that date.
- Always emit `start_date <= end_date`. If user gave them reversed, swap and confirm with user.

---

## Single date (start = end)

| User says | start_date | end_date |
|---|---|---|
| "april 27, 2026" | `2026-04-27` | `2026-04-27` |
| "for april 27, 2026" | `2026-04-27` | `2026-04-27` |
| "27 april" | `2026-04-27` | `2026-04-27` |
| "start and end april 27, 2026" | `2026-04-27` | `2026-04-27` |
| "start april 27 end same" | `2026-04-27` | `2026-04-27` |

---

## Range

| User says | start_date | end_date |
|---|---|---|
| "april 27 to april 28 2026" | `2026-04-27` | `2026-04-28` |
| "27 to 28 april 2026" | `2026-04-27` | `2026-04-28` |
| "april 27 - april 28" | `2026-04-27` | `2026-04-28` |
| "27-4-2026 to 28 april 2026" | `2026-04-27` | `2026-04-28` |
| "27/04/2026 to 28/04/2026" | `2026-04-27` | `2026-04-28` |
| "start april 27 end april 28" | `2026-04-27` | `2026-04-28` |
| "from 27 apr to 28 apr 2026" | `2026-04-27` | `2026-04-28` |
| "18th April to 19th April 2026" | `2026-04-18` | `2026-04-19` |
| "27 april to 28-04-2026" | `2026-04-27` | `2026-04-28` |
| "27/04 to 28/04/2026" | `2026-04-27` | `2026-04-28` |

---

## Relative (resolve against today's date)

| User says | start_date | end_date |
|---|---|---|
| "today" | today | today |
| "yesterday" | yesterday | yesterday |
| "this week" | Monday of current week | today |
| "last week" | Monday of last week | Sunday of last week |
| "this month" | 1st of current month | today |
| "last month" | 1st of previous month | last day of previous month |

---

## When to ask the user

Ask once if any of these are true:
- No date(s) at all → "Could you confirm the start and end dates?"
- Only start, no end (and not phrased as single-date) → "What's the end date?"
- Year truly ambiguous (e.g., "27 january" when current month is December — could mean past or future) → "Do you mean 27 January [current_year] or [next_year]?"
- Words you don't recognise (e.g., "Q1", "fiscal week 14") → ask for explicit dates.

Do not invent. One question, one answer, then proceed.

---

## Validation regex

Before posting JSON, both dates must match:

```
^\d{4}-\d{2}-\d{2}$
```

And `start_date <= end_date` (string comparison works for ISO dates).
