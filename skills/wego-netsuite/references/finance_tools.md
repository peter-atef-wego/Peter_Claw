# references/finance_tools.md

Complete verb-by-verb SuiteQL recipe book for the NetSuite Champion. **Use these as templates**, parameterise via the resolvers in `dimension_aliases.md`, and run via the production MCP server (`netsuite-mcp-standard-tools-production`) for reads or the sandbox MCP server (`netsuite-mcp-standard-tools-sandbox`) for writes.

> Every recipe assumes the SuiteQL safety rules in [`suiteql_recipes.md`](./suiteql_recipes.md) — escape user-supplied literals, prefer `ROWNUM <=` over `LIMIT`, single quotes, `TO_DATE` for dates.

The Champion has **22 finance verbs**, grouped into four families:

- **Dimensions** (4) — list/lookup tools for the slowly-changing data.
- **Reads** (13) — analytic and detail queries.
- **Writes** (4) — sandbox-only mutations.
- **General** (1) — `run_suiteql` for anything not covered.

Every tool returns the gateway-shape envelope:

```json
{"ok": true|false, "data": <obj>, "url": <str|null>, "status": 200, "error": null|"…"}
```

---

## A. Dimensions (slowly-changing, cache 10 min in-thread)

### A.1 `get_subsidiaries`

**Purpose.** List all 8 Wego subsidiaries with id, name, country, currency, active/inactive flag. Always call this once per thread before any tool that needs a subsidiary id when the user is vague.

```sql
SELECT id, name, country, currency, isinactive
FROM   subsidiary
```

### A.2 `get_accounts`

**Purpose.** List active GL accounts. Optional `type_filter` to narrow.

```sql
SELECT id, acctnumber,
       accountsearchdisplayname AS acctname,
       accttype, subsidiary, isinactive
FROM   account
WHERE  isinactive = 'F'
  [AND accttype = :type_filter]
```

Common `accttype` values: `AcctRec`, `AcctPay`, `Bank`, `Income`, `Expense`, `OthCurrAsset`, `LongTermLiab`, `Equity`, `CostOfGoodsSold`, `OthIncome`, `OthExpense`.

### A.3 `get_currencies`

```sql
SELECT id, name, symbol, exchangerate, isinactive
FROM   currency
WHERE  isinactive = 'F'
```

### A.4 `get_period_status`

**Purpose.** Return open/closed/locked status of an accounting period. **Call this before any GL write** — closed/locked periods silently reject posts.

```sql
SELECT id, periodname, startdate, enddate,
       closed, alllocked AS locked,
       isadjust, isquarter, isyear
FROM   accountingperiod
WHERE  isyear = 'F' AND isquarter = 'F'
  AND  periodname = :period_name        -- e.g. 'May 2026'
```

If `period_alias` is null, resolve the **current** period:

```sql
SELECT id, periodname, startdate, enddate, closed, alllocked AS locked
FROM   accountingperiod
WHERE  isyear = 'F' AND isquarter = 'F' AND isadjust = 'F'
  AND  TO_DATE(:today,'YYYY-MM-DD') BETWEEN startdate AND enddate
```

`is_period_open()` returns `True` only if `closed != 'T'` AND `locked != 'T'`.

---

## B. Reads (production, GET-only)

### B.1 `get_account_balance`

**Purpose.** SUM of postings on a GL account, optionally scoped to subsidiary and/or accounting period. If both `period_alias` and `as_of_date` are omitted, returns the running balance.

```sql
SELECT SUM(tl.foreignamount) AS balance
FROM   transactionline tl
JOIN   transaction t ON t.id = tl.transaction
WHERE  tl.account = :account_id
  AND  t.posting = 'T'
  [AND t.subsidiary = :subsid]
  [AND t.postingperiod = :period_id]
  [AND t.trandate <= TO_DATE(:as_of_date,'YYYY-MM-DD')]
```

**Inputs.** `account_alias` (required) → resolve via `ACCOUNT_ALIASES` or `account` table; `subsidiary_alias` (optional); `period_alias` (optional); `as_of_date` (optional, ISO `YYYY-MM-DD`).

### B.2 / B.3 `get_ap_aging` / `get_ar_aging` — SQL REMOVED (2026-07-28)

**Aging must not be built in SuiteQL.** The bucket SQL that used to live here
was being copied into hand-written "aging" queries whose numbers do not match
NetSuite's report (open-item netting, consolidation and currency translation
happen inside the report engine). On 2026-07-28 that produced 25+ query
attempts shipped as an "A/P Aging Detail".

Route instead:
- **A/P Aging Detail BK** (consolidated or any subsidiary) ->
  `get_stored_report(report_key="ap_aging_detail_bk_consolidated",
  period="<ISO date>", subsidiary="<name>")` — NetSuite's own emailed export,
  filtered on its `Subsidiary: Name` column. See CLAUDE.md §0.0: SuiteQL,
  `run_standard_report` and `run_saved_search` are FORBIDDEN for this report.
- **A/R aging** -> maintained saved search `ar_aging_details` (694).

### B.4 `get_open_bills_for_vendor`

```sql
SELECT t.id, t.tranid, t.trandate, t.duedate, t.foreigntotal,
       t.status, v.companyname AS vendor
FROM   transaction t
JOIN   vendor v ON v.id = t.entity
WHERE  t.type = 'VendBill'
  AND  t.status != 'Paid In Full'
  AND  v.companyname LIKE :vendor_alias_like   -- e.g. '%Acme%'
ORDER  BY t.duedate
FETCH FIRST 200 ROWS ONLY
```

The `vendor` table header field is `companyname`; the transaction-header link to the vendor is `entity`, **not** `vendor`.

### B.5 `get_open_invoices_for_customer`

```sql
SELECT t.id, t.tranid, t.trandate, t.duedate, t.foreigntotal,
       t.status, c.companyname AS customer
FROM   transaction t
JOIN   customer c ON c.id = t.entity
WHERE  t.type = 'CustInvc'
  AND  t.status != 'Paid In Full'
  AND  c.companyname LIKE :customer_alias_like
ORDER  BY t.duedate
FETCH FIRST 200 ROWS ONLY
```

### B.6 `get_bill_detail`

Single-record GET via the Record API (Oracle MCP). Use when the user wants the line items of bill X.

```
GET /services/rest/record/v1/vendorbill/{id}?expandSubResources=true
```

Returns the bill header plus the `item` and `expense` sublists in one call.

### B.7 `get_invoice_detail`

```
GET /services/rest/record/v1/invoice/{id}?expandSubResources=true
```

### B.8 `get_trial_balance`

**Purpose.** Trial balance for a period — account-level balances. Optional subsidiary.

```sql
SELECT a.acctnumber,
       a.accountsearchdisplayname AS acctname,
       SUM(tl.foreignamount) AS balance
FROM   transactionline tl
JOIN   account a ON a.id = tl.account
JOIN   transaction t ON t.id = tl.transaction
WHERE  t.postingperiod = :period_id
  AND  t.posting = 'T'
  [AND t.subsidiary = :subsid]
GROUP  BY a.acctnumber, a.accountsearchdisplayname
ORDER  BY a.acctnumber
FETCH FIRST 1000 ROWS ONLY
```

### B.9 `get_fx_rate`

**Purpose.** Most recent consolidated exchange rate from a currency to a currency as of a given date.

```sql
SELECT rate, effectivedate
FROM   consolidatedexchangerate
WHERE  fromcurrency = (SELECT id FROM currency WHERE symbol = :from_ccy)
  AND  tocurrency   = (SELECT id FROM currency WHERE symbol = :to_ccy)
  AND  effectivedate <= TO_DATE(:on_date,'YYYY-MM-DD')
ORDER  BY effectivedate DESC
FETCH FIRST 1 ROWS ONLY
```

Default `:on_date` to today's ISO date.

### B.10 `get_vat_summary`

**Purpose.** Tax totals grouped by tax code for a period.

```sql
SELECT tl.taxcode,
       SUM(tl.taxamount)    AS tax_total,
       COUNT(DISTINCT t.id) AS txn_count
FROM   transactionline tl
JOIN   transaction t ON t.id = tl.transaction
WHERE  t.postingperiod = :period_id
  AND  tl.taxcode IS NOT NULL
  [AND t.subsidiary = :subsid]
GROUP  BY tl.taxcode
ORDER  BY tax_total DESC
FETCH FIRST 200 ROWS ONLY
```

### B.11 `get_recent_ota_loads`

**Purpose.** Recent OTA daily-load journals.

```sql
SELECT t.id, t.tranid, t.trandate, t.memo,
       SUM(tl.foreignamount) AS amount
FROM   transaction t
JOIN   transactionline tl ON tl.transaction = t.id
WHERE  t.memo LIKE 'OTA Daily Load%'
  AND  t.trandate >= TRUNC(SYSDATE) - :days
GROUP  BY t.id, t.tranid, t.trandate, t.memo
ORDER  BY t.trandate DESC
FETCH FIRST 100 ROWS ONLY
```

`:days` default = 7.

### B.12 `get_approval_status`

**Purpose.** Approval status + next approver for a single transaction.

```sql
SELECT t.id, t.tranid, t.approvalstatus, t.nextapprover,
       t.status, t.trandate
FROM   transaction t
WHERE  t.id = :internal_id
FETCH FIRST 1 ROWS ONLY
```

### B.13 `get_systemnotes`

**Purpose.** Recent system-note audit entries on a record.

```sql
SELECT date, name, type, field, oldvalue, newvalue
FROM   systemnote
WHERE  recordtype = :record_type
  AND  recordid   = :internal_id
ORDER  BY date DESC
FETCH FIRST :limit ROWS ONLY
```

`:limit` default = 10. `:record_type` examples: `'vendorbill'`, `'invoice'`, `'journalentry'`, `'vendor'`, `'customer'`.

### B.14 `export_suiteql_to_csv`

**Purpose.** Bulk-listing exports — paginates a SuiteQL server-side, writes all rows to a CSV on disk, and returns ONLY metadata + a 3-row preview to the agent. The full result set never enters the LLM context, so token cost is bounded regardless of row count.

```
arguments:
  query:          SuiteQL (WHERE / ORDER BY only — no LIMIT, OFFSET, FETCH FIRST/NEXT, ROWNUM)
  filename_hint:  slug for the output filename (timestamp appended automatically)
  scope:          'prod' (default) or 'sandbox'
  max_rows:       safety cap, default 50,000

returns on success:
  {ok, file_path, row_count, columns, preview (≤3 rows), scope, truncated, message}

returns on failure:
  {ok: False, error, message, [rows_exported_so_far, partial_file]}
```

**When to use.** Any listing where the result could exceed ~50 rows — vendor lists, customer lists, full open-bill listings, full GL exports, full transaction-line dumps. Follow `CLAUDE.md §5.11` — always `COUNT(*)` first, only offer this path if count > 50.

**Do NOT use for.** Small filtered queries (top-20, aging, single-account balance) — those go through `run_suiteql` and return inline.

**Token cost.** Constant — same as a normal chat read regardless of row count, because the rows live on disk and never enter context.

**File delivery.** The tool returns a local `file_path`. The agent surfaces the path + preview in its reply; if a Slack file-upload tool is wired, attach the file to the originating thread, otherwise quote the path so the user can fetch it directly.

---

## C. Writes (sandbox only — `5564218-sb1`)

**Rules for every write:**

1. Resolve every dimension first (subsidiary, currency, vendor, GL account, period).
2. Build the body using NetSuite's REST record-API shape (nested `{"id": "<id>"}` for record references).
3. Execute the write — see "Execution path" below for which transport to use.
4. Capture the returned `internal_id` **from the actual API response**. Never fabricate. Reply MUST include the sandbox URL constructed from the real id.
5. Append a one-line entry to `memory/knowledge/action_tracker.md`.

**Execution path (per `CLAUDE.md §0.2`):**

| Path | When | How |
|---|---|---|
| Oracle MCP `create_record` / `update_record` | If the tool appears in your tool list | `create_record(record_type="vendor", body={...})` |
| Direct OAuth via `scripts/netsuite_query.py` | If MCP write tools are NOT in your tool list | `--scope sandbox --create vendor --body '{...}'` — see §0.2 for the exact `bash -c` wrapper. Returns `{"ok": true, "internal_id": "...", "location": "..."}` |

**Critical:** if **neither** path is available for the requested write (e.g. MCP is missing AND the script doesn't support this action), **do not fabricate**. Per `CLAUDE.md §5.2`, name the blocker and stop. The 2026-05-12 vendor-fake-create incident (logged in `MEMORY.md §B.1`) is the worked example of what not to do.

### C.1 `create_vendor`

**Body:**

```json
{
  "companyname": "Acme Travel",
  "subsidiary": {"id": "<subsid_id>"},
  "currency":   {"id": "<ccy_id>"},
  "email":      "ap@acme.example",
  ...extra fields passed through
}
```

`currency` is optional; defaults to the subsidiary's base currency. `email` is optional. `extra` is a free-form dict of additional NetSuite vendor fields passed through verbatim.

**URL on reply:** `https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=<id>`

### C.2 `create_customer`

**Body:** same shape as `create_vendor` (`companyname`, `subsidiary`, `currency`, `email`).

**URL:** `https://5564218-sb1.app.netsuite.com/app/common/entity/custjob.nl?id=<id>`

### C.3 `create_bill` (`vendorbill`) — for CSV-driven creates use `create_vendor_bill_from_csv` instead

**TL;DR:** if the user uploaded a CSV, **call the high-level MCP tool `create_vendor_bill_from_csv`** with the row as a flat dict. The tool resolves every dimension (subsidiary, vendor, currency, account, department, location, class, tax code, BU code) server-side, builds the body, POSTs, and returns the result with every resolved field surfaced. Bot cannot drop fields because it doesn't assemble the body. Same applies for journals — see `create_journal_entry_from_csv`.

The hand-rolled `create_record("vendorbill", body)` path still works and is documented below for non-CSV creates (single ad-hoc bills, partial updates, etc.), but **on CSV imports the high-level tool is the canonical path** as of 2026-05-19.

#### `create_vendor_bill_from_csv` — preferred for CSV imports

Call shape:

```json
{
  "tool": "create_vendor_bill_from_csv",
  "arguments": {
    "csv_row": {
      "bill_ref":         "BILL-010",
      "bill_number":      "TEST-CLAW-BILL-010",
      "subsidiary":       "Wego Pte Ltd (Singapore)",
      "vendor_entity_id": "TestClaw Vendor 04",
      "currency":         "USD",
      "tran_date":        "2026-05-13",
      "due_date":         "2026-05-13",
      "memo":             "OC Testing for Bill creation",
      "expense_account":  "8302010",
      "amount":           100,
      "line_memo":        "Test line printing and stationery",
      "department":       "OH : Finance",
      "tax_code":         "ZR-SG 0%",
      "bu_code":          "Shared (to be allocated)"
    },
    "scope": "sandbox"
  }
}
```

The tool internally:

1. Resolves the subsidiary → looks up its tax-regime prefix (e.g. `Wego Pte Ltd → GST_SG`).
2. Resolves the vendor by `entityid` exact match (single, definitive — no fuzzy guessing).
3. Resolves currency by ISO symbol, account by `acctnumber`, department by name, location/class by name.
4. Composes the full tax-code itemid (`GST_SG:ZR-SG 0%`) and looks it up in `purchasetaxitem` excluding UNDEF placeholders.
5. Looks up the BU code in the hardcoded custom-segment map.
6. **If any resolution fails**, returns `{"ok": false, "error": "DIMENSION_RESOLUTION_FAILED", "errors": [...]}` — bot must surface each field error verbatim. No partial creation.
7. **If all resolve**, builds the body with EVERY field present in the line item, POSTs, runs post-write verification, returns `{"ok": true, "internal_id": "...", "ui_url": "...", "resolved_fields": {...}}`.

The `resolved_fields` block surfaces every resolved id — bot uses this in the §5.8 opener and the final summary. No "Note: Department wasn't applied" excuse — if the field was in the CSV, it's in the body, or the call failed loudly.

#### `create_journal_entry_from_csv` — preferred for CSV-driven JE imports

Same shape. For multi-line JEs, pass `csv_row.lines` as a list:

```json
{
  "csv_row": {
    "subsidiary": "Wego Pte Ltd (Singapore)",
    "tran_date":  "2026-05-13",
    "memo":       "Manual reclass",
    "lines": [
      {"account": "8302010", "debit": 100, "department": "OH : Finance", "bu_code": "Shared (to be allocated)"},
      {"account": "6101000", "credit": 100, "department": "OH : Finance", "bu_code": "Shared (to be allocated)"}
    ]
  }
}
```

Tool validates debits = credits before POST. Same dimension-resolution guarantees apply per line — no missing Department/Location/Class/BU on any line.

---

#### Hand-rolled `create_record("vendorbill", body)` — for non-CSV creates only

**Pre-flight:**

1. Resolve the vendor: SuiteQL on `vendor` table — try `entityid` exact match first, then `companyname` exact match, then `companyname LIKE '%alias%'`. **If exactly one result → use it confidently without asking.** If >1 results → list candidates and ask once (per §5.9, then stop and wait). If 0 results → ask whether to create the vendor first, then **wait for the answer** before proceeding.
2. Resolve subsidiary, expense account(s), department, currency, location, tax code (per side), and any custom segments (`cseg_msa_bu_code` etc.) from the CSV. **Every column in the CSV must map to a real id before you build the body.** If you can't resolve any field, ask and stop — do not omit fields silently.
3. For tax codes specifically, see `references/dimension_aliases.md §9` — tax codes are subsidiary-scoped and live in `purchasetaxitem` for AP-side records.

**Body — complete example with every common CSV field mapped:**

```json
{
  "entity":     {"id": "<vendor_id>"},
  "subsidiary": {"id": "<subsid_id>"},
  "trandate":   "2026-05-13",
  "duedate":    "2026-06-12",
  "tranid":     "TEST-CLAW-BILL-010",
  "memo":       "OC Testing for Bill creation",
  "currency":   {"id": "<currency_id>"},
  "exchangerate": 1,

  "expense": {"items": [
    {
      "account":    {"id": "<expense_account_id>"},
      "amount":     100.00,
      "memo":       "Test line printing and stationery",
      "department": {"id": "<department_id>"},
      "location":   {"id": "<location_id>"},           // include if CSV has it
      "class":      {"id": "<class_id>"},              // include if CSV has it
      "taxcode":    {"id": "<purchasetaxitem_id>"},    // ALWAYS include if subsidiary uses tax codes
      "cseg_msa_bu_code": {"id": "<bu_code_id>"}       // include if CSV has BU Code column
    }
  ]}
}
```

**Field-by-field mapping from CSV columns** (per `references/dimension_aliases.md §"CSV Column Name → NetSuite REST Field Mapping"`):

| CSV column | NetSuite REST field | Lives on | Resolver |
|---|---|---|---|
| `bill_ref` / `bill_number` | `tranid` (header) | header | as-is from CSV |
| `subsidiary` | `subsidiary` (header) | header | `subsidiary` table |
| `vendor_entity_id` / `entity` / `vendor` | `entity` (header) | header | `vendor` table (entityid first, companyname second) |
| `tran_date` / `transaction_date` | `trandate` (header) | header | ISO `YYYY-MM-DD` |
| `due_date` | `duedate` (header) | header | ISO `YYYY-MM-DD` |
| `currency` | `currency` (header) | header | `currency` table by symbol |
| `memo` (header) | `memo` (header) | header | as-is |
| `expense_account` / `account` | `account` (line) | expense.items[i] | `account` table by acctnumber |
| `amount` | `amount` (line) | expense.items[i] | number |
| `line_memo` / `description` | `memo` (line) | expense.items[i] | as-is |
| `department` / `dept` | `department` (line) | expense.items[i] | `department` table |
| `location` | `location` (line) | expense.items[i] | `location` table |
| `class` | `class` (line) | expense.items[i] | `classification` table (SuiteQL name; REST field is `class`) |
| `tax_code` / `taxcode` | `taxcode` (line) | expense.items[i] | `purchasetaxitem` table, subsidiary-scoped |
| `BU Code` / `bu_code` / `BU` | `cseg_msa_bu_code` (line) | expense.items[i] | hardcoded value map in `dimension_aliases.md §"BU Code"` |

**Do NOT silently drop any field that has a value in the CSV.** If `tax_code` column is present and non-empty, `taxcode` field MUST be in the line body with a real id. If `BU Code` column is present, `cseg_msa_bu_code` MUST be there. The 2026-05-19 Vendor Bill incident posted a "success" reply with no tax-code, no department, no BU — meaning either the body was incomplete or the bill was created with missing fields. Either way, the user can't verify and the audit trail is broken. **Surface every resolved field in the §5.8 opener AND in the final post-create summary.**

**Reply format after a successful create:**

> *Understood: creating a `vendorbill` (NetSuite Vendor Bill). URL will use `vendbill.nl`. Resolving dimensions now…*
>
> ✅ Vendor Bill `TEST-CLAW-BILL-010` created in sandbox (internal_id `1436589`).
>
> Resolved fields:
> - Vendor: TestClaw Vendor 04 (id 5855)
> - Subsidiary: Wego Pte Ltd (id 11)
> - Currency: USD (id 1)
> - Tran Date: 2026-05-13 / Due: 2026-06-12
> - Line 1: $100.00 → Account 8302010 Printing & Stationery (id 710), Dept Finance (id 26), Tax Code ZR-SG 0% (id 7), BU Shared-to-allocate (id 5)
>
> URL: https://5564218-sb1.app.netsuite.com/app/accounting/transactions/vendbill.nl?id=1436589

If any of those resolved-field bullets are missing because the CSV column was empty, say so explicitly: *"Line 1 had no `BU Code` in the CSV — left empty in NetSuite."* Don't omit silently.

**URL:** `https://5564218-sb1.app.netsuite.com/app/accounting/transactions/vendbill.nl?id=<id>` — use the `ui_url` field returned by the tool (§5.6), don't hand-construct.

### C.4 `create_journal_entry`

**Pre-flight (mandatory):**

1. Resolve `subsidiary_alias`. If not found → error.
2. Call `get_period_status()` for the current period. If `closed='T'` OR `alllocked='T'` → reject with "current accounting period is closed or locked — GL post would be silently rejected by NetSuite".
3. Sum `lines[*].debit` and `lines[*].credit`. If `|debits - credits| > 0.01` → reject with "unbalanced journal: debits=X credits=Y".

**Body:**

```json
{
  "subsidiary": {"id": "<subsid_id>"},
  "trandate":   "2026-05-12",
  "memo":       "Free text",
  "line": {"items": [
      {"account": {"id": "<acctId>"}, "debit":  1000.00, "memo": "…"},
      {"account": {"id": "<acctId>"}, "credit": 1000.00, "memo": "…"}
  ]}
}
```

**URL:** `https://5564218-sb1.app.netsuite.com/app/accounting/transactions/journal.nl?id=<id>`

---

## D. General

### D.1 `run_suiteql`

**Use only when no decomposed verb above fits.** The auto-sanitiser rejects DDL/DML, rejects multi-statements, and enforces `ROWNUM <= 10000` if neither `ROWNUM` nor `GROUP BY` is present. See [`suiteql_recipes.md`](./suiteql_recipes.md) for the rules.

`scope` parameter: `'prod'` (default, read-only) or `'sandbox'`.

### D.2 `run_saved_search`

Execute a NetSuite Saved Search by id (e.g. `customsearch_my_id`). Up to 5000 rows. Required when finance teams reference a Saved Search by id rather than describing the query. `params` (optional): `page_size`, `row_cap`, filter overrides.

### D.3 `get_metadata_catalog`

Schema introspection. Returns the list of record types (if `record_type` null) or the field/sublist schema of one record type. **Use this before constructing writes** when you're unsure of a field name.

### D.4 `read_record`

Generic GET by record type + internal id (production). Set `expand_lines=true` to include sublist line items in one call.

---

## E. Common joins and idioms

### Header vs line subsidiary filtering

For analytic queries across multi-leg postings (intercompany), prefer the **line-level** subsidiary filter:

```sql
JOIN transactionLine tl ON tl.transaction = t.id
WHERE tl.subsidiary = :subsid
```

For single-subsidiary lookups, the header-level filter (`t.subsidiary = :subsid`) is fine and faster.

### Status filters

| `transaction.type` | "Open" status filter |
|---|---|
| `VendBill` | `t.status != 'Paid In Full'` |
| `CustInvc` | `t.status != 'Paid In Full'` |
| `VendCred` (vendor credit) | `t.status != 'Fully Applied'` |
| `CustCred` (customer credit) | `t.status != 'Fully Applied'` |
| `Journal` | postings always; no "open" concept |

### Posting filter

For any GL-impacting query, always include `t.posting = 'T'` to exclude non-posting transactions (estimates, opportunities, etc.).

---

## F. Verb → MCP tool mapping (current)

Under the legacy Python listener, these verbs lived in `finance_tools.py`. Under the direct-MCP architecture they map to Oracle's MCP tool surface:

| Champion verb | Oracle MCP call |
|---|---|
| `get_subsidiaries` | `run_suiteql("SELECT id, name, … FROM subsidiary")` |
| `get_accounts` | `run_suiteql("SELECT … FROM account WHERE isinactive='F'")` |
| `get_currencies` | `run_suiteql("SELECT … FROM currency WHERE isinactive='F'")` |
| `get_period_status` | `run_suiteql` (recipe A.4) |
| `get_account_balance` | `run_suiteql` (recipe B.1) |
| `get_ap_aging` | **`get_stored_report`** (emailed report; SuiteQL forbidden) |
| `get_ar_aging` | `run_saved_search` key=`ar_aging_details` |
| `get_open_bills_for_vendor` | `run_suiteql` (recipe B.4) |
| `get_open_invoices_for_customer` | `run_suiteql` (recipe B.5) |
| `get_bill_detail` / `get_invoice_detail` | `read_record('vendorbill'|'invoice', id, expand_sub_resources=true)` |
| `get_trial_balance` | `run_suiteql` (recipe B.8) |
| `get_fx_rate` | `run_suiteql` (recipe B.9) |
| `get_vat_summary` | `run_suiteql` (recipe B.10) |
| `get_recent_ota_loads` | `run_suiteql` (recipe B.11) |
| `get_approval_status` | `run_suiteql` (recipe B.12) |
| `get_systemnotes` | `run_suiteql` (recipe B.13) |
| `create_vendor` / `create_customer` / `create_bill` / `create_journal_entry` | `create_record(record_type, body)` on sandbox |
| `run_saved_search` | `run_saved_search(search_id, params)` |
| `get_metadata_catalog` | `metadata_catalog(record_type?)` |
| `read_record` | `read_record(record_type, internal_id, expand_sub_resources?)` |

If Oracle's MCP exposes a higher-level verb (e.g. a built-in "AP aging" tool), prefer it over hand-rolled SuiteQL — call `list_record_types()` / inspect the tool list at session start to discover.
