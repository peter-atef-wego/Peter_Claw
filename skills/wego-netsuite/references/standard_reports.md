# Standard NetSuite Reports — agent reference

This skill exposes seven pre-validated NetSuite financial reports via the
`run_standard_report` MCP tool. The SuiteQL for each report lives **inside the
MCP server** (`scripts/netsuite_mcp_server.py → STANDARD_REPORTS`). The agent
only supplies parameters — never the raw SQL — which keeps every run cheap
(bounded-token export), safe (validated params, no SQL injection surface), and
consistent (same SQL every time).

---

## How to use this from the agent's side

When the user asks for one of the seven reports, call:

```json
{
  "tool": "run_standard_report",
  "arguments": {
    "report_name": "<one of the 7>",
    "params": { ... see per-report list below ... },
    "scope": "prod",                // default; "sandbox" for testing
    "filename_hint": "optional_override"  // tool builds one if you skip this
  }
}
```

The tool returns the same shape as `export_suiteql_to_csv` — a `file_path`,
`row_count`, `columns`, and a 3-row `preview`. The full data stays on disk;
only the preview enters the LLM context. **Token cost is bounded regardless
of row count** (≈38k tokens, the same as a normal chat read).

Reply pattern to user: post the CSV file path + the preview table + the row
count + a one-line summary. Don't paste the full data into Slack.

---

## The seven reports

### ~~1. `aging_detailed`~~ — REMOVED 2026-07-28

**Deleted.** This was an **A/R** template (`type='CustInvc'`, `customer`,
`aging_bucket`) and the agent used it to answer an **A/P Aging Detail BK**
request — serving receivables data as payables. Aging figures come from
NetSuite's report engine and cannot be reproduced by any query.

For A/P Aging Detail BK use `get_stored_report(report_key=
"ap_aging_detail_bk_consolidated", period=<ISO>, subsidiary=<optional>)` —
NetSuite's own emailed export, with auto-fetch from the inbox on a miss.

### 2. `customer_statement` — Customer Statement of Account (data)

All invoices, payments, credit memos and refunds for **one customer**
between two dates. Returns the same raw data the NetSuite Statement PDF is
built from.

| Param | Required? | Type | Example |
|---|---|---|---|
| `customer` | ✅ | string (entityid) | `Agoda Pte Ltd` |
| `from_date` | ✅ | YYYY-MM-DD | `2026-01-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-05-21` |

**Sample asks:**
- *"Statement of account for Agoda Jan–May this year"* → resolve customer name first via `run_suiteql`, then call with `{customer: "Agoda Pte Ltd", from_date: "2026-01-01", to_date: "2026-05-21"}`.

**Columns:** customer, transaction_date, reference, transaction_type, due_date, memo, amount, open_balance, currency, subsidiary.

> ⚠️ **PDF format note:** If the user explicitly asks for the *printable PDF* version (the one Wego sends to clients on letterhead), tell them that requires a separate ~2hr build to wire up NetSuite's `customer-statement` print endpoint. This tool gives you the **data**, not the formatted PDF. Don't claim otherwise.

---

### 3. `revenue_periodic` — Revenue report (periodic)

Revenue posted to Income / Other-Income accounts between two dates, grouped
by period × account × customer × subsidiary.

| Param | Required? | Type | Example |
|---|---|---|---|
| `from_date` | ✅ | YYYY-MM-DD | `2026-04-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-04-30` |
| `subsidiary_id` | optional | int | `2` |

**Date matching:** uses `accountingperiod.startdate / enddate` — pass the first
and last day of the period(s) you want.

**Columns:** period, gl_code, account, customer, subsidiary, revenue.

---

### 4. `gl_report` — GL postings for one account (periodic)

Every posting line hitting a single GL account between two dates, with
debit / credit / entity / memo / subsidiary.

| Param | Required? | Type | Example |
|---|---|---|---|
| `gl_code` | ✅ | string (digits/letters/dots/dashes) | `1221010` |
| `from_date` | ✅ | YYYY-MM-DD | `2026-04-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-04-30` |
| `subsidiary_id` | optional | int | `2` |

**Sample ask:** *"GL report for 1221010 - Revenue Accrual - Market place for April"* → `{gl_code: "1221010", from_date: "2026-04-01", to_date: "2026-04-30"}`. The user typically gives you the full `<code> - <name>` string; **only pass the code** before the dash.

**Columns:** transaction_date, period, reference, transaction_type, entity, memo, debit, credit, net, currency, subsidiary.

---

### 5. `customer_payments` — Payments received from customers

All `CustPymt` transactions between two dates, optionally filtered to one
customer or one subsidiary.

| Param | Required? | Type | Example |
|---|---|---|---|
| `from_date` | ✅ | YYYY-MM-DD | `2026-04-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-04-30` |
| `customer` | optional | string | `Agoda Pte Ltd` |
| `subsidiary_id` | optional | int | `2` |

**Columns:** payment_date, payment_ref, customer, amount, currency, memo, subsidiary.

---

### 6. `balance_sheet` — Balance sheet (as of date)

Asset / Liability / Equity balances as of a date, grouped by account type
and account. Drops zero-balance rows.

| Param | Required? | Type | Example |
|---|---|---|---|
| `as_of_date` | ✅ | YYYY-MM-DD | `2026-05-21` |
| `subsidiary_id` | optional | int | `2` |

**Account types included:** Bank, AcctRec, OthCurrAsset, FixedAsset, OthAsset, AcctPay, CredCard, OthCurrLiab, LongTermLiab, Equity.

**Caveat:** balances are in **transaction currency** — multi-currency consolidation rollup is NOT applied. If the user needs a consolidated B/S in a single reporting currency, mention this caveat and offer to add a `run_suiteql` step that joins to `consolidatedexchangerate`. Out of scope for this template.

**Columns:** account_type, gl_code, account, subsidiary, balance, as_of_date.

---

### 7. `income_statement` — Income statement (periodic)

P&L lines between two dates — Income, Other-Income, COGS, Expense,
Other-Expense — grouped by account × period × subsidiary. Drops zero-amount
rows.

| Param | Required? | Type | Example |
|---|---|---|---|
| `from_date` | ✅ | YYYY-MM-DD | `2026-04-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-04-30` |
| `subsidiary_id` | optional | int | `2` |

**Columns:** account_type, gl_code, account, subsidiary, period, amount.

---

### 8. `interco_balance_sheet` — Intercompany AR + AP balances (as of date)

Intercompany AR + AP balances as-of a date. Filters by **account code list** (not by NetSuite's `tointersubsidiary` flag, which Wego doesn't populate consistently). Defaults to Wego's standard interco accounts — `12030 AR-Interco` and `21030 AP-Interco` — but accepts an override if a subsidiary uses different codes.

| Param | Required? | Type | Default | Example |
|---|---|---|---|---|
| `as_of_date` | ✅ | YYYY-MM-DD | — | `2026-01-31` |
| `subsidiary_id` | optional | int | none → CONSOLIDATED | `7` (one sub only) |
| `account_codes` | optional | list / comma-string | `['12030', '21030']` | `['12010','12020','21010','21020']` (e.g. FZ-LLC) |

**Sample asks:**
- *"BS - AR AP Interco for Wego Consolidated as of Jan 31"* → `{as_of_date: "2026-01-31"}` (omit subsidiary_id → consolidated; defaults to 12030/21030)
- *"BS - AR AP Interco for Beekim as of yesterday"* → resolve Beekim → `subsidiary_id`, call with `{as_of_date: "2026-05-20", subsidiary_id: <id>}`
- *"BS - AR AP Interco for FZ-LLC, but they use 12010/12020/21010/21020"* → `{as_of_date: "2026-01-31", subsidiary_id: <fz-llc-id>, account_codes: ["12010","12020","21010","21020"]}`

**Grouping:** always `(subsidiary, account, currency)` — so even single-subsidiary calls return per-currency detail. No aggregate-only mode (you can always SUM downstream; you can't recover detail you didn't query for).

**Columns:** gl_code, account, subsidiary, currency, balance, as_of_date.

> ⚠️ **If your subsidiary uses different interco account codes**, pass them via `account_codes`. The default `[12030, 21030]` is Wego's standard but not universal — e.g. Wego FZ-LLC has 0 postings on those accounts; they may use `12010 AR (Excl OTA & Interco)` / `12020 AR - OTA` / `21010 AP (Excl OTA & Interco)` / `21020 AP - OTA` instead. When in doubt, run a quick `run_suiteql` like `SELECT acctnumber, fullname FROM account WHERE fullname LIKE '%Interco%' AND <subsidiary in subsidiary_list>` to confirm.

---

### 9. `gl_listing_multi` — GL postings across multiple accounts (periodic)

Same shape as `gl_report` (#4) but accepts a **list** of GL codes and
returns one consolidated CSV with a `gl_code` column for downstream
filtering / grouping. Cap is 50 codes per call.

| Param | Required? | Type | Example |
|---|---|---|---|
| `gl_codes` | ✅ | list of strings OR comma-string | `["150","155","160","262","2624","266"]` or `"150,155,160,262,2624,266"` |
| `from_date` | ✅ | YYYY-MM-DD | `2026-04-01` |
| `to_date` | ✅ | YYYY-MM-DD | `2026-04-30` |
| `subsidiary_id` | optional | int | `7` |

**Sample ask:** *"GL listing 150, 155, 160, 262, 2624, 266 for Beekim April"* →
resolve Beekim → `subsidiary_id`, then call with the 6 codes as a list.

**Columns:** transaction_date, period, gl_code, account, reference, transaction_type, entity, memo, debit, credit, net, currency, subsidiary.

---

## Subsidiary id reference (Wego)

When the user names a Wego subsidiary, resolve to the `subsidiary_id` int:

| Subsidiary | id |
|---|---|
| Wego Pte Ltd (SG) | 2 |
| Wego Travel Saudi Limited | 7 |
| Wego DMCC (Dubai) | 4 |
| Wego Egypt | 9 |
| ... | (full list in SKILL.md §subsidiaries) |

If unsure of the id, run a quick `run_suiteql` lookup:
`SELECT id, name FROM subsidiary` before calling the report.

---

## Cost & safety guarantees

- **Per-call token cost:** ~38k tokens, regardless of row count. Same shape as a normal chat read. The full CSV stays on disk; only a 3-row preview reaches the LLM context.
- **SQL injection:** every param is validated against a type rule (date format, GL code charset, integer cast, single-quote escape for identifiers) before substitution. The agent cannot craft a malicious param that reaches NetSuite raw — validators raise `INVALID_PARAM` first.
- **Versioning:** the SQL lives in `STANDARD_REPORTS` in the MCP server. If a report needs tuning (e.g. a different aging bucket boundary), change the template in one place; every future call picks up the new version. No agent prompt edits required.
- **Discoverability:** if the agent calls `run_standard_report` with `report_name="foo"` (unknown), the response lists all 7 available names — the agent can re-route automatically.

---

## When NOT to use this tool

- **Custom slicing the user describes that isn't one of the 7.** Fall back to `run_suiteql` (small result) or `export_suiteql_to_csv` (bulk).
- **The user wants the formatted PDF**, not the data. Tell them PDF needs a separate build.
- **Cross-subsidiary consolidated B/S in one reporting currency.** Template returns transaction-currency balances; ask before consolidating.
- **User/role/access audit** — use the dedicated `export_access_audit` tool (atomic 3-CSV delivery). See [`access_audit.md`](./access_audit.md).
- **Unknown SuiteQL schema** — use `discover_table(table_name)` to learn columns before writing the query. See [`suiteql_recipes.md §12`](./suiteql_recipes.md).

---

## Adding an 8th report later

1. Add an entry to `STANDARD_REPORTS` in `scripts/netsuite_mcp_server.py`:
   ```python
   "my_new_report": {
       "description": "...",
       "required": {"from_date": _v_date},
       "optional": {"subsidiary_id": _v_int},
       "sql": "SELECT ... WHERE x = '{from_date}' {{subsidiary_id: AND t.sub = {subsidiary_id} }}",
       "filename": "my_new_report_{from_date}",
   },
   ```
2. Add the name to the `enum` in the tool's `inputSchema` (same file, TOOLS list).
3. Add a section to this doc.

That's it — no agent prompt change needed.
