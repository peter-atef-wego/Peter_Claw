# references/governance.md

Cross-cutting governance for the NetSuite Champion: PII redaction, period preflight, concurrency, sandbox banner, deduplication, action logging. These rules apply on **every** tool call regardless of which path the LLM chose.

Originally implemented in a Python module at `test_py/netsuite-mcp/governance.py`, which was **deleted from the repo on 2026-05-12** as part of the pivot to OpenClaw + Oracle MCP. Under the direct-MCP architecture, the bot is responsible for applying the equivalent rules in-context before posting tool output to Slack. The reference Python implementation is preserved in this doc (§1.5) for portability.

---

## 1. PII redaction

NetSuite stores personal/financial data that the bot must NEVER post to Slack or feed back into the LLM context. The redactor runs on every tool result before it goes to the model or to a reply.

### 1.1 Field-name allowlist (whole field redacted)

Any field whose lowercased key is in this set gets replaced with `"[REDACTED]"`:

```
bankaccountnumber, iban, swift, tin, ssn,
passportnumber, nationalid,
salary, compensation
```

Add new field names here when a new sensitive field is observed. Match by lowercased key only — `Iban`, `IBAN`, `iban` all hit.

### 1.2 Pattern-based scrubbing (anywhere in string values)

| Pattern | Regex | Replacement |
|---|---|---|
| IBAN | `\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b` | `[REDACTED-IBAN]` |
| Card-shaped number | `\b(?:\d[ -]*?){13,19}\b` | `[REDACTED-CARD]` |
| Generic long number (12+ digits, e.g. account numbers, national IDs) | `\b\d{12,}\b` | `[REDACTED-NUM]` |

Patterns are applied to every string in the response tree, recursively, after field-name redaction.

### 1.3 What's NOT redacted

- NetSuite internal IDs (≤9 digits typically).
- Vendor / customer / employee NAMES (these are not PII for finance ops).
- GL account numbers.
- Transaction ids (`tranid`), document numbers.
- Email addresses (kept because vendor onboarding needs them).

If you observe a leak (e.g. a 16-digit transaction-line memo got redacted by the long-number pattern), tune the pattern — don't add ad-hoc bypass logic.

### 1.4 Where redaction runs

In the legacy Python path: `tool_dispatcher.py` calls `redact(result)` before returning. In the direct-MCP path: the bot is responsible for applying the equivalent before it includes tool output in a Slack reply. **Treat anything that looks PII-shaped in tool output as redactable** — when in doubt, redact.

### 1.5 Reference implementation

```python
import re

PII_FIELDS = {
    "bankaccountnumber", "iban", "swift", "tin", "ssn",
    "passportnumber", "nationalid",
    "salary", "compensation",
}
_IBAN_RE     = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_CARD_RE     = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_LONG_NUM_RE = re.compile(r"\b\d{12,}\b")

def redact(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in PII_FIELDS else redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        s = _IBAN_RE.sub("[REDACTED-IBAN]", value)
        s = _CARD_RE.sub("[REDACTED-CARD]", s)
        s = _LONG_NUM_RE.sub("[REDACTED-NUM]", s)
        return s
    return value
```

---

## 2. Result-size cap

Tool results larger than **50 KB JSON** get truncated before going back to the LLM:

1. If `data.items` is a list of >50 rows, keep the first 50 and add:
   ```json
   {"truncated": true, "total_returned": N, "showing": 50}
   ```
2. Otherwise, stringify-truncate the whole payload to 50 KB with a preview marker.

50 KB ≈ 12 K tokens — enough for the model to answer, far less than the 5000-row cap the saved-search endpoint can return.

If the user actually wants the full list, run a tighter SuiteQL (filter first, then aggregate / page), or run a saved search and offer to email the CSV — don't try to bypass the cap.

---

## 3. Period preflight (mandatory before GL writes)

Every GL write (`create_journal_entry`, sometimes `create_bill` when `trandate` falls into a recent period) MUST first verify the target period is open. NetSuite **silently rejects** posts into closed/locked periods — the call returns 200 with no record id, and the journal disappears.

### 3.1 The check

```python
def is_gl_post_safe(period_row):
    if not period_row:                          return False, "no period resolved"
    if period_row['closed']    == 'T':          return False, f"period {period_row['periodname']} is CLOSED"
    if period_row['alllocked'] == 'T':          return False, f"period {period_row['periodname']} is LOCKED"
    return True, "ok"
```

### 3.2 Where to apply

| Verb | Pre-check |
|---|---|
| `create_journal_entry` | **Always** — fetch the current (or `trandate`'s) period, verify open, abort with `412 PRECONDITION_FAILED` if not. |
| `create_bill` | Optional — bills usually post into the current period via `trandate`. If `trandate` is in the past, run the check. |
| `create_vendor` / `create_customer` | Not applicable — these don't post to GL. |

### 3.3 User-facing message on rejection

> ⚠️ Can't post — the **May 2026** period is closed. Either change `trandate` to the current open period (`Jun 2026`) or have Akansha re-open May 2026 for adjustments.

Never silently retry on a different period.

---

## 4. Sandbox banner

Every successful sandbox write reply gets an explicit "this is sandbox" footer so the user understands the change is not in production. Apply idempotently — if "sandbox" already appears in the reply text, skip.

**Banner text:**

```
_(sandbox 5564218-sb1 — change is in sandbox only, not production)_
```

**Apply when:**

- `mcp_resp.ok == True`, AND
- the response URL contains `5564218-sb1` or `_sb1`, AND
- the reply text doesn't already contain the word "sandbox" (case-insensitive).

Place at the end of the reply, after the URL.

---

## 5. Concurrency limits

NetSuite caps concurrent calls per account at **15** (default) + 10 per SuiteCloud Plus license, max ~55. Shared across REST, SOAP, and RESTlets.

For the Champion:

- **Concurrent in-flight calls: ≤ 10** (leave headroom for other automations).
- **Per-minute rate: ≤ 60** (1/s sustained, bursts allowed up to the concurrent cap).

On `429`: wait 5 s, retry once. If it fails again, surface verbatim — don't loop.

These limits live in `ConcurrencyLimiter` for the Python path. Under direct MCP, Oracle's MCP server enforces its own limits — if you see repeated 429s, slow down rather than parallel-fanning from one Slack message.

---

## 6. Action audit log

Every state-changing tool call (create / update / delete on sandbox) must append a single line to `memory/knowledge/action_tracker.md`:

```
<ISO timestamp> | <channel> | <user> | <verb> | <record_type> | <internal_id> | <sandbox_url>
```

Examples:

```
2026-05-12T14:32:11+00 | #netsuite_ap                | U07XYZ | create_vendor        | vendor       | 12345 | https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=12345
2026-05-12T14:35:02+00 | #netsuite_champion          | U07XYZ | create_bill          | vendorbill   | 67890 | https://5564218-sb1.app.netsuite.com/app/accounting/transactions/vendbill.nl?id=67890
2026-05-12T15:11:48+00 | #netsuite_gl_and_reporting  | U02ABC | create_journal_entry | journalentry | 99001 | …
```

This is non-negotiable — every successful sandbox write produces exactly one log line. The bot must call the tracker (or have its harness call it) before posting the reply.

Reads are NOT logged here. The audit trail is for state changes.

---

## 7. Deduplication / idempotency

### 7.1 Slack message deduplication

Slack delivers each message with a stable `ts` (timestamp). The bot must process each `ts` exactly once. The legacy listener used a `BoundedSet(capacity=5000)` to remember the most recent 5000 message timestamps and skip duplicates. Under direct MCP, the harness handles this — but if you find yourself answering the same message twice (e.g. on a retry), check whether the `ts` is in the recent-seen set.

### 7.2 Write idempotency

The Oracle MCP `create_record` is NOT idempotent — calling it twice creates two records. If a network blip retries a `create_bill` mid-call:

- Check the response. If the first call succeeded (`200` with an `id`), don't retry.
- If the call failed with a timeout but the record may have been created, run a SuiteQL lookup by the unique fields (vendor + trandate + total) before retrying.

This is rare under healthy networks; but be aware.

---

## 8. Bounded LRU pattern (for any in-memory dedup set)

When you maintain a set of "seen things" in memory (processed timestamps, recently DMed alert types, etc.), use a bounded LRU:

```python
class BoundedSet:
    def __init__(self, capacity=5000):
        self._items = {}   # ordered dict via insertion order
        self._capacity = capacity

    def add(self, item):
        if item in self._items: return
        if len(self._items) >= self._capacity:
            del self._items[next(iter(self._items))]
        self._items[item] = None

    def __contains__(self, item):
        return item in self._items
```

This avoids the "set grows forever" leak in long-running processes.

---

## 9. Hard-rule recap

These rules are non-negotiable. If a tool call or reply violates any of them, abort and rewrite:

1. **Production is read-only.** Writes to `5564218` are blocked at the MCP server — never even attempt them.
2. **Every sandbox write reply contains the sandbox URL** of the new/updated record.
3. **GL writes preflight the period** via `is_gl_post_safe()` — closed/locked → abort with a clear message.
4. **PII redaction runs on every tool result** before it reaches the LLM or Slack.
5. **Concurrency stays under 10** in-flight; `429` triggers a single retry, not a loop.
6. **Every state-changing call logs to `action_tracker.md`** with one line.
7. **Tokens never appear in replies, logs, or LLM context** — they live in the MCP server and the OpenClaw env, full stop.
