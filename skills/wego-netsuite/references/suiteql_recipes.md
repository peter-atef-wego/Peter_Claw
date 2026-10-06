# references/suiteql_recipes.md

Master SuiteQL safety + recipe playbook for the NetSuite Champion. Read this **before** writing any free-form SuiteQL. The verb-specific templates live in [`finance_tools.md`](./finance_tools.md); this file is the cross-cutting query layer.

---

## 1. Why SuiteQL safety matters

NetSuite has **no parameterised SuiteQL** over REST — you concatenate strings and submit. That makes free-text user input dangerous. The risks:

1. **Multi-statement injection** (semicolons + UNION). Even though SuiteQL is read-only by design (no INSERT/UPDATE/DELETE), a `;` mid-query opens the door to data leak.
2. **Resource exhaustion.** An un-limited SELECT against `transactionLine` (multi-million rows) will time out.
3. **Cross-subsidiary information leak.** The integration role's permissions are the only real backstop — write queries that filter `subsidiary` and `posting` explicitly.

The Champion mitigates (1) by rejecting `;` mid-query, (2) by enforcing `ROWNUM`, (3) is the role's job — but the agent should still add the filter as defence in depth.

---

## 2. Literal escaping rules

| Python value | SuiteQL literal | Notes |
|---|---|---|
| `None` | `NULL` | Use `IS NULL` / `IS NOT NULL` to compare. |
| `True` / `False` | `'T'` / `'F'` | NetSuite SQL convention. |
| `int`, `float` | as-is (`123`, `1.5`) | No quotes. |
| `str` (with `'`) | single-quoted, doubled: `O'Reilly` → `'O''Reilly'` | Never use double quotes for strings. |
| `datetime.date` | `TO_DATE('YYYY-MM-DD','YYYY-MM-DD')` | |
| `datetime.datetime` | `TO_DATE('YYYY-MM-DD','YYYY-MM-DD')` | Time is dropped. |
| `list` | `IN (...)` body: `'A','B','C'` | Call as `WHERE id IN ({in_list(vals)})` |

**Escape function (canonical):**

```python
def escape_literal(value) -> str:
    if value is None:                    return "NULL"
    if isinstance(value, bool):          return "'T'" if value else "'F'"
    if isinstance(value, (int, float)):  return str(value)
    if isinstance(value, datetime):
        return f"TO_DATE('{value.strftime('%Y-%m-%d')}','YYYY-MM-DD')"
    if isinstance(value, date):
        return f"TO_DATE('{value.isoformat()}','YYYY-MM-DD')"
    s = str(value).replace("'", "''")
    return f"'{s}'"
```

**Rule:** if the value came from a user message, a NetSuite record field, a Slack thread, or any non-constant source, escape it. If it's a literal you typed into the recipe, fine.

---

## 3. Query-level sanitiser

Run `sanitise_query(q)` on any SuiteQL composed from free text before sending it to the MCP. The sanitiser:

1. **Strips comments** — `--single-line` and `/* block */`.
2. **Rejects multi-statement** — a `;` anywhere except trailing-whitespace raises `ValueError`.
3. **Rejects DDL/DML keywords** — `INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE` (case-insensitive, word-bounded).
4. **Enforces a row-count ceiling** — if the query lacks `ROWNUM` and is not a `GROUP BY` aggregate, the sanitiser inserts `ROWNUM <= 10000` into the `WHERE` clause (or appends one if there isn't one). Aggregate queries are bounded by group cardinality and left alone.

**Default ceiling:** `10000` rows. Override with `sanitise_query(q, rownum_cap=N)` if you need more (rare). The 50 KB result-size cap downstream will truncate before sending to the LLM regardless.

**Failure modes:**

- `ValueError: empty SuiteQL query` — sanitise was called on empty/whitespace.
- `ValueError: multi-statement SuiteQL not allowed` — `;` followed by more SQL.
- `ValueError: DDL/DML not allowed in SuiteQL — read-only queries only` — forbidden keyword.
- `ValueError: SuiteQL references non-whitelisted tables: [...]` — only if `enforce_whitelist=True`.

---

## 4. Table whitelist (optional, for user free-text queries)

When SuiteQL is composed from a user's free-text question (rather than a curated recipe), enable the whitelist:

```python
safe_suiteql(q, enforce_whitelist=True)
```

The default `FINANCE_TABLE_WHITELIST`:

```
transaction, transactionline, transactionaccountingline,
vendor, customer, vendorcategory, customercategory,
account, subsidiary, currency, currencyrate,
consolidatedexchangerate, accountingperiod, department,
location, classification, employee, item,
salestaxitem, purchasetaxitem, taxcontrolaccount,
approval, systemnote,
customtransaction_wego_est_brr_fin_det      # Wego custom transaction type
```

Trusted internal queries (built from `finance_tools.md` recipes) skip the whitelist — they only touch known-safe tables.

---

## 5. SuiteQL syntax cheat-sheet

Wrong on the left, right on the right. Each row has cost a real query at some point.

| Wrong | Right | Why |
|---|---|---|
| `LIMIT 50` | `WHERE ROWNUM <= 50` or `FETCH FIRST 50 ROWS ONLY` | No `LIMIT` keyword in SuiteQL / Oracle SQL. |
| `WHERE vendor = 123` (on `vendorBill`) | `WHERE entity = 123` | Transaction header field is `entity`. |
| `SELECT acctname FROM account` | `SELECT accountsearchdisplayname AS acctname` | `acctname` does not exist. |
| `SELECT locked FROM accountingperiod` | `SELECT alllocked AS locked` | `locked` does not exist. |
| `WHERE trandate > '2026-01-01'` | `WHERE trandate >= TO_DATE('2026-01-01','YYYY-MM-DD')` | Implicit string→date fails on certain locales. |
| `"some string"` | `'some string'` | Single quotes for string literals. |
| `NULL = something` | `something IS NULL` | Standard SQL. |
| Date math `trandate + 30` | `trandate + INTERVAL '30' DAY` or `TRUNC(SYSDATE) - 30` | Use Oracle date arithmetic. |
| Top-N w/o aggregation | `ORDER BY x DESC FETCH FIRST 10 ROWS ONLY` | `TOP` doesn't exist. |
| `SELECT TOP 10 ...` | same | as above |
| `SUBSTR` with 0-index | `SUBSTR(s, 1, n)` is 1-indexed | Oracle convention. |
| Boolean filter `closed = TRUE` | `closed = 'T'` | NetSuite uses `'T'` / `'F'` strings. |

---

## 6. The 8 most-useful idioms

### 6.1 Top-N

```sql
SELECT t.id, t.tranid, t.foreigntotal
FROM   transaction t
WHERE  t.type = 'VendBill'
ORDER  BY t.foreigntotal DESC
FETCH FIRST 10 ROWS ONLY
```

### 6.2 Group-by + having

```sql
SELECT v.companyname,
       COUNT(*) AS bill_count,
       SUM(t.foreigntotal) AS total
FROM   transaction t
JOIN   vendor v ON v.id = t.entity
WHERE  t.type = 'VendBill' AND t.posting = 'T'
GROUP  BY v.companyname
HAVING SUM(t.foreigntotal) > 100000
ORDER  BY total DESC
```

### 6.3 Aging buckets — REMOVED (2026-07-28)

**Do not build aging buckets in SuiteQL.** A/P and A/R aging come from
NetSuite's report engine; a query reproduces the shape but not the figures
(open-item netting, multi-book consolidation, currency translation).

- **A/P Aging Detail BK** — `get_stored_report(report_key=
  "ap_aging_detail_bk_consolidated", period="<ISO>", subsidiary="<name>")`.
  That serves NetSuite's own emailed export and filters the subsidiary out of
  it. See CLAUDE.md §0.0 — SuiteQL/saved-search for this report is forbidden.
- **A/R aging** — the maintained saved search `ar_aging_details` (694).

The old CASE/`SYSDATE` bucket snippet was deleted because it was being copied
into hand-written "aging" queries whose numbers do not match the report
(2026-07-28: 25+ query attempts shipped as an A/P Aging Detail).

### 6.4 Posting-period filter

```sql
WHERE t.postingperiod = (
    SELECT id FROM accountingperiod
    WHERE  periodname = 'May 2026'
      AND  isyear = 'F' AND isquarter = 'F' AND isadjust = 'F'
)
```

### 6.5 Date-range filter

```sql
WHERE t.trandate BETWEEN TO_DATE('2026-05-01','YYYY-MM-DD')
                    AND TO_DATE('2026-05-31','YYYY-MM-DD')
```

### 6.6 IN-list from a Python list

```python
ids = [101, 102, 103]
where = f"t.id IN ({','.join(escape_literal(x) for x in ids)})"
# → "t.id IN (101,102,103)"
```

### 6.7 Currency join

```sql
JOIN currency c ON c.id = t.currency
WHERE  c.symbol = 'AED'
```

### 6.8 Subsidiary-safe line-level filter

```sql
JOIN transactionLine tl ON tl.transaction = t.id
WHERE  tl.subsidiary = :subsid
  AND  tl.account = :account_id
```

### 6.9 FX rate from NetSuite (Rule 7 — never use external sources)

> **Use the locked tool, not these recipes by hand, and NOT saved search 705.** For any FX question call `run_standard_report` with `report_name: "fx_rate_list"` (params: `as_of_date` required; `base_symbol` / `source_symbol` optional). This reproduces the native **`Lists > Accounting > Currency Exchange Rates`** page (`currencyratelist.nl`) — `currencyrate` joined to `currency` for names. The SQL below is what the template runs server-side — reference/review only; do NOT paste it into `run_suiteql` yourself (the agent drifted three times — Peter 2026-06-30), and do NOT route FX to `run_saved_search`/search 705 (it returns raw internal ids).

Wego's books use NetSuite's `currencyrate` table as the source of truth for FX. **Never fall back to XE.com / Xignite / Bloomberg / Google Finance.** Per Akansha's standing instruction (2026-06-27), every currency-exchange-rate question routes here first.

The `fx_rate_list` template returns these fixed columns: `base_currency, effective_date (DD/MM/YYYY), exchange_rate, method (DIRECT), source_currency, base_currency_name, source_currency_name`. `exchange_rate` = units of `base_currency` per 1 `source_currency`.

**Latest rate, single pair, as of a date:**

```sql
SELECT TO_CHAR(cr.effectivedate, 'YYYY-MM-DD') AS effectivedate,
       cr.basecurrency, bc.symbol AS base_symbol,
       cr.transactioncurrency, tc.symbol AS tran_symbol,
       cr.exchangerate
FROM   currencyrate cr
JOIN   currency bc ON bc.id = cr.basecurrency
JOIN   currency tc ON tc.id = cr.transactioncurrency
WHERE  cr.basecurrency        = :base_id      -- resolve via currency table first
  AND  cr.transactioncurrency = :tran_id
  AND  cr.effectivedate <= TO_DATE(:asof_date, 'YYYY-MM-DD')
ORDER  BY cr.effectivedate DESC
FETCH FIRST 1 ROWS ONLY
```

**Resolve currency aliases first** (Rule 1):

```sql
SELECT id, symbol, name FROM currency WHERE symbol IN ('EGP', 'INR', 'SAR', 'AUD', ...)
```

Cache the symbol→id map per thread. Wego's commonly-needed ids stay stable but resolve fresh per session to avoid drift.

**Time series (last N days for a pair, useful for context):**

```sql
SELECT TO_CHAR(effectivedate, 'YYYY-MM-DD') AS effectivedate, exchangerate
FROM   currencyrate
WHERE  basecurrency        = :base_id
  AND  transactioncurrency = :tran_id
  AND  effectivedate BETWEEN TO_DATE(:from_date, 'YYYY-MM-DD')
                         AND TO_DATE(:to_date,   'YYYY-MM-DD')
ORDER  BY effectivedate DESC
```

**If no rate for the asked date** — say so honestly per Rule 5 / Rule 7. Example: *"NetSuite's most recent loaded rate is from 25 Jun 2026; today's (26 Jun) hasn't been loaded yet — Akansha owns the FX refresh schedule."* Do NOT substitute an external rate.

**Consolidated rate** (for B/S translation in a reporting currency): use `consolidatedexchangerate` not `currencyrate`. Different table, different semantics (period-end translation vs daily transactional). Confirm which the user wants before guessing.

**The reply must tag the source explicitly:** `Source: NetSuite Production (currencyrate table — same data as Lists > Accounting > Currency Exchange Rates in the NetSuite UI)` — so the user knows the lineage, the UI cross-check path, and can trust it for audit. The UI path is Akansha's named human-workflow (2026-06-27); SuiteQL hits the same backing table.

**UI cross-check / self-export path.** If the user wants to verify or export themselves, point them at:

> `Lists > Accounting > Currency Exchange Rates` → page-level *Export* button (CSV / XLS).

The Champion cannot drive this UI export directly — the OpenClaw-managed browser has no logged-in NetSuite session, and the bot must not handle NetSuite login credentials. If a user explicitly asks the bot to *navigate* there and click Export, deliver the SuiteQL result anyway (same data), name the UI path, and file an NDS ticket for the browser-credential gap rather than reporting "page not found" as if the data were unavailable.

**Full FX list as of a date (Akansha's required output format — 2026-06-27).** When the user asks *"pull currency exchange rate list as of today"* or any list variant, run this and render the result verbatim as a table with columns `base_currency | effective_date | exchange_rate | method | source_currency`:

```sql
WITH latest AS (
    SELECT cr.basecurrency, cr.transactioncurrency,
           MAX(cr.effectivedate) AS effectivedate
    FROM   currencyrate cr
    WHERE  cr.effectivedate <= TO_DATE(:asof_date, 'YYYY-MM-DD')
    GROUP BY cr.basecurrency, cr.transactioncurrency
)
SELECT bc.symbol                                  AS base_currency,
       TO_CHAR(cr.effectivedate, 'DD/MM/YYYY')    AS effective_date,
       cr.exchangerate                            AS exchange_rate,
       'DIRECT'                                   AS method,
       tc.symbol                                  AS source_currency
FROM   currencyrate cr
JOIN   latest l  ON l.basecurrency       = cr.basecurrency
                 AND l.transactioncurrency = cr.transactioncurrency
                 AND l.effectivedate       = cr.effectivedate
JOIN   currency bc ON bc.id = cr.basecurrency
JOIN   currency tc ON tc.id = cr.transactioncurrency
ORDER  BY bc.symbol, tc.symbol
```

Notes:
- Output column **order matters** — `base_currency, effective_date, exchange_rate, method, source_currency`. Don't reorder.
- `effective_date` is **DD/MM/YYYY** (Wego-finance reads in dd/mm/yyyy, not ISO).
- `method` is `'DIRECT'` as a literal — Wego loads direct rates into `currencyrate`. If the row is from `consolidatedexchangerate` instead, switch the table and label the method differently (period-end translation, not daily transactional).
- Symbols (`MYR`, `AED`, ...) come from `currency.symbol`, **not** the internal id — match Akansha's screenshot exactly.

Header-level `t.subsidiary` is fine for single-subsidiary postings; line-level catches intercompany legs.

---

## 7. Date-phrase resolver

Always resolve relative phrases to `(start, end)` ISO dates **before** building the SuiteQL. The bot's currentDate harness provides today; if missing, ask.

| Phrase (case-insensitive) | `start` | `end` |
|---|---|---|
| `today` | today | today |
| `yesterday` | today - 1 | today - 1 |
| ISO `YYYY-MM-DD` | parsed | parsed |
| `YYYY-MM` | 1st of month | last of month |
| `<Mon> <YYYY>` (`May 2026`, `Jan 2026`) | 1st | last |
| `YYYY` alone | Jan 1 | Dec 31 |
| `this week` / `current week` | Monday | Sunday (ISO week) |
| `last week` | prior Monday | prior Sunday |
| `this month` / `current month` | 1st | last of month |
| `mtd` | 1st of current month | today |
| `last month` | 1st of prior month | last of prior month |
| `this quarter` / `current quarter` | quarter start | quarter end |
| `qtd` | quarter start | today |
| `last quarter` | prior quarter start | prior quarter end |
| `Q<n> <YYYY>` (`Q1 2026`) | quarter start | quarter end |
| `this year` / `current year` | Jan 1 | Dec 31 |
| `ytd` | Jan 1 | today |
| `last year` | prior Jan 1 | prior Dec 31 |

**Wego fiscal year = calendar year** for every subsidiary. If that ever changes, override the resolver constant.

**Unsupported phrase?** Return `None` and ask the user. Don't guess.

---

## 8. Currency formatting

| Currency | Decimals | Example |
|---|---|---|
| `JPY`, `KRW`, `VND` | 0 | `JPY 1,234,567` |
| Everything else | 2 | `SGD 1,234,567.89`, `AED 3,420,000.00` |

Format: `<CCY> <thousands-separated number>`. Three-letter ISO codes, space, value. Empty/null amount → `<CCY> —`.

---

## 9. Concurrency

NetSuite caps concurrent REST + SOAP + RESTlet calls at **15** per account by default (+10 per SuiteCloud Plus license, max ~55). Bursty agent traffic produces `429` errors.

For the Champion:

- Cap concurrent calls to **10** to leave headroom.
- Cap per-minute rate to **60** (1/s sustained).
- On `429`, wait 5 s and retry once. If still failing, surface.

These limits live in the gateway under `ConcurrencyLimiter` for the legacy Python path; under the direct-MCP architecture Oracle's MCP enforces its own limits. If you see repeated 429s, slow down — don't fan out parallel queries from the same Slack message.

---

## 10. When to use SuiteQL vs Record API vs Saved Search

| Need | Best tool |
|---|---|
| Single record, header + lines | `read_record(type, id, expand_sub_resources=true)` |
| Analytic query (aggregate / multi-table) | SuiteQL recipe from `finance_tools.md` |
| Custom query the finance team already saved | `run_saved_search(search_id)` |
| Field-name discovery before a write | `metadata_catalog(record_type)` |
| **SuiteQL** table-name discovery (you don't know columns) | **`discover_table(table_name)`** — see §12 |
| Bulk export of >5000 rows | Saved Search via RESTlet (chunked); SuiteQL caps at 10000 |
| Anything that returns 1 number | SuiteQL with `SUM()` / `COUNT()` |

---

## 11. Failure modes

| Error | Cause | Action |
|---|---|---|
| `SuiteQL rejected: …` | Sanitiser caught DDL/DML/multi-statement | Rewrite, escape, or restrict to `SELECT`. |
| `400 INVALID_FIELD` on `account.acctname` | Field doesn't exist | Use `accountsearchdisplayname AS acctname`. |
| `400 INVALID_FIELD` on `accountingperiod.locked` | Field doesn't exist | Use `alllocked AS locked`. |
| `400 INVALID_FIELD` on `vendorBill.vendor` | Should be `entity` | `JOIN vendor v ON v.id = t.entity`. |
| `400` on a `LIMIT` keyword | SuiteQL doesn't support `LIMIT` | Use `ROWNUM` or `FETCH FIRST n ROWS ONLY`. |
| `429` | Concurrency / rate limit hit | Retry once after 5 s. |
| `5xx` / timeout | NetSuite slow | Retry once with a tighter `FETCH FIRST`. |
| Empty `items` | No rows match | Say so. Don't synthesise. |

---

## 12. Discover-then-query — `discover_table` for unknown schemas

When you're about to write a SuiteQL but don't remember the exact table or columns (e.g. is it `employeerolesforsearch` or `employeeroles`? does `customer` have `lastorderdate` or `lastsalesdate`?), **call `discover_table(name)` first**. Don't guess column names from training data — that's how `acctsearchdisplayname` typos get into production queries.

```json
discover_table({ "table_name": "employeerolesforsearch", "scope": "prod" })
// returns:
// { ok: true, table: "employeerolesforsearch",
//   row_count: 1183, columns: ["employee", "role", "selectedrole", "subsidiary", ...],
//   sample_row: {"employee": "5609", "role": "1058", ...},
//   message: "Table `employeerolesforsearch` is accessible. 7 columns, ~1183 rows. ..."
// }
```

When the table doesn't exist or the integration role can't read it, you get `ok=false` with `suggested_alternatives`:

```json
{ ok: false, table: "userrole", error: "TABLE_INACCESSIBLE",
  message: "Table `userrole` not found, or integration role lacks read permission. ...",
  suggested_alternatives: ["userroles", "employee", "employeerolesforsearch"] }
```

Recurse on the suggestions, cap at 3 attempts (§5.16). After 3 misses, surface the gap per Rule 5 — don't loop.

For known REST record types (vendor, customer, employee, vendorbill, journalentry, …) prefer `metadata_catalog(record_type)` over `discover_table` — it returns the canonical REST schema which is what `create_record` / `update_record` use.

---

## 13. Pre-built bundles

Don't hand-roll these — there are atomic tools that already do the job:

| Need | Tool | Notes |
|---|---|---|
| Active users + roles + user×role assignments | `export_access_audit` | Three CSVs in one call, per-query status, includes Akansha-handoff note for the permission grid (which isn't in SuiteQL). See [`access_audit.md`](./access_audit.md). |
| Aging / B/S / P&L / interco / GL listing | `run_standard_report` | Nine pre-validated templates. See [`standard_reports.md`](./standard_reports.md). |
