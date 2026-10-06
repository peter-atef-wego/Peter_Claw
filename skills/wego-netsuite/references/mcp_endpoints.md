# NetSuite MCP Endpoints — Champion

> ## Status (2026-05-12 — Phase 1 in progress)
>
> Two MCP servers are referenced in `openclaw.json`:
>
> - `netsuite-mcp-standard-tools-production` — reads only (account `5564218`).
> - `netsuite-mcp-standard-tools-sandbox` — full CRUD (account `5564218-sb1`).
>
> **Phase 1**: wire `plugins.entries.mcp.servers` in `openclaw.json` to point at the existing `mcp_servers.json` definitions, then restart the agent and verify the MCP tools (`run_suiteql`, `read_record`, `create_record`, `update_record`, `metadata_catalog`, optionally `run_saved_search` and file-cabinet ops) appear in the tool list.
>
> **Until Phase 1 completes**, the agent uses `scripts/netsuite_query.py` via `bash -c` exec as the execution path — see `CLAUDE.md §0.2` for the exact wrappers. Both paths use the same TBA OAuth credentials from the `NETSUITE_<SCOPE>_*` env vars.
>
> When the MCP tools appear in the tool list, the agent automatically prefers them per `CLAUDE.md §0.2` priority order. The OAuth script remains as a fallback for anything MCP doesn't expose (likely saved searches and file cabinet, TBD).
>
> Phase 2 (after MCP tools appear): inventory exactly what tools Oracle exposes and update the §F mapping table in `finance_tools.md` so each Champion verb points at the real MCP tool name. Phase 3: tighten `CLAUDE.md §0.2` to prefer MCP explicitly.

---

Concrete READ and WRITE examples for each domain. Below is the reference for the underlying REST surface — both Oracle's MCP and `scripts/netsuite_query.py` ultimately hit these endpoints with the same TBA OAuth signature; the agent doesn't need to construct these URLs by hand but they're useful for debugging.

NetSuite REST URL bases:
- **READ (production):** `https://5564218.suitetalk.api.netsuite.com/services/rest/record/v1/`
- **WRITE (sandbox):** `https://5564218-sb1.suitetalk.api.netsuite.com/services/rest/record/v1/`

**Auth:** NetSuite TBA (Token-Based Authentication, OAuth 1.0a HMAC-SHA256). Each layer has its own consumer (`client_id` / `client_secret`) + token (`token_id` / `token_secret`) pair. The realm in the `Authorization` header uses the uppercase-underscore form of the account id (e.g. `5564218` for prod, `5564218_SB1` for sandbox); URL hosts use the lowercase-hyphen form (`5564218-sb1.suitetalk.api.netsuite.com`).

The MCP gateway picks the right URL host + TBA token-pair based on the request scope (READ vs WRITE).

## NetSuite REST API surface used by the gateway

Six endpoint families — the Champion is now a near-complete NetSuite client:

| Family | Path | Methods | Used for |
|---|---|---|---|
| **Record API** | `/services/rest/record/v1/<type>[/<id>]` | GET / POST / PATCH | CRUD on individual records (vendor, customer, vendorbill, invoice, journalentry, salestaxitem, …) |
| **SuiteQL** | `/services/rest/query/v1/suiteql` | POST | Ad-hoc analytical queries — joins, aggregates, multi-criteria filters. Body: `{"q": "<sql>"}`. Pagination via `?limit=&offset=`. |
| **Metadata catalog** | `/services/rest/record/v1/metadata-catalog[/<type>]` | GET | Schema introspection: list all standard + custom record types and their field/sublist shape. ([Oracle docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_1540810168.html)) |
| **Workbook / Dataset** | `/services/rest/query/v1/dataset/<id>/result` | GET | Execute a SuiteAnalytics dataset built in the UI. Cannot create/modify datasets via REST. ([Oracle docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_159414531069.html)) |
| **Async jobs** | `/services/rest/async/v1/query/suiteql` + `/job/<id>` | POST + GET | Fire-and-poll for SuiteQL queries that exceed sync timeout (~5 min) or 1 000-row sync cap. |
| **RESTlet companion** | `/app/site/hosting/restlet.nl?script=&deploy=` | POST | Saved Searches + File Cabinet. Standard REST API doesn't expose either. ([Tim Dietrich](https://timdietrich.me/blog/netsuite-saved-search-api/)) See `references/restlet_deployment.md`. |

Gateway methods exposing each:

```python
gw.read(record_type, internal_id=None, query=None, limit=20,
        expand_sub_resources=False, scope="prod")          # GET → prod (or sandbox)
gw.create(record_type, body)                               # POST → sandbox
gw.update(record_type, internal_id, body)                  # PATCH → sandbox
gw.update_sublist(record_type, internal_id, sublist, lines) # PATCH sublist (lines)
gw.suiteql(q, limit=100, offset=0, scope="prod"|"sandbox") # POST /query/v1/suiteql
gw.metadata_catalog(record_type=None, scope="prod")        # GET /metadata-catalog
gw.dataset(dataset_id, limit=100, offset=0, scope="prod")  # GET /query/v1/dataset/<id>/result
gw.async_suiteql(q, scope="prod")                          # POST /async/v1/query/suiteql
gw.async_status(job_id, scope="prod")                      # GET  /async/v1/job/<id>
gw.saved_search(search_id=, params=None, scope="prod")     # → RESTlet companion
gw.file_cabinet_get(file_id=, scope="prod")                # → RESTlet companion
```

DELETE is intentionally not exposed.

### Sublists / subrecords

To get a transaction WITH its line items in one call, use `expand_sub_resources=True`:

```python
gw.read("vendorbill", internal_id="12345", expand_sub_resources=True)
# Response includes 'item.items' (line array), 'expense.items' (expense lines), etc.
```

Without that flag NetSuite returns hyperlinks to the sublists (`item: {links: [...]}`), forcing N+1 calls. ([Oracle – Sublists & Subrecords](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545141947.html))

To append line items to an existing bill:

```python
gw.update_sublist("vendorbill", "12345", "item", [
    {"item": {"id": "<itemId>"}, "quantity": 1, "rate": "500.00"},
    {"item": {"id": "<itemId>"}, "quantity": 2, "rate": "250.00"},
])
```

---

## SuiteQL — analytical query examples (use for any "show me / list / aggregate" question)

SuiteQL is the primary tool for analytical reads. Prefer it over the record API when the question:

- spans multiple record types (joins),
- needs aggregation (`SUM`, `COUNT`, `GROUP BY`),
- filters by computed criteria (date ranges, status combos, multi-subsidiary).

Endpoint: `POST /services/rest/query/v1/suiteql` (production for normal reads; sandbox for pre-flight verification).

### List vendors with open bills

```sql
SELECT v.id, v.companyname, COUNT(t.id) AS open_bills, SUM(t.foreigntotal) AS total_open
FROM vendor v
JOIN transaction t ON t.entity = v.id
WHERE t.type = 'VendBill' AND t.status = 'Open'
GROUP BY v.id, v.companyname
ORDER BY total_open DESC
```

### AP aging — no SuiteQL (2026-07-28)

Aging is report-engine output; the bucket SQL that was here produced numbers
that don't match the report and was being copied into hand-written queries.

`A/P Aging Detail BK` (consolidated or any subsidiary) ->
`get_stored_report(report_key="ap_aging_detail_bk_consolidated",
period="<ISO date>", subsidiary="<name>")`. A/R aging -> saved search
`ar_aging_details` (694). See CLAUDE.md §0.0.

### Trial balance for a period

```sql
SELECT a.acctnumber, a.acctname, SUM(tl.foreignamount) AS balance
FROM transactionline tl
JOIN account a ON a.id = tl.account
JOIN transaction t ON t.id = tl.transaction
WHERE t.postingperiod = <periodId> AND t.posting = 'T'
GROUP BY a.acctnumber, a.acctname
ORDER BY a.acctnumber
```

### Customers without recent activity (DSO support)

```sql
SELECT c.id, c.entityid, c.companyname, MAX(t.trandate) AS last_invoice
FROM customer c
LEFT JOIN transaction t ON t.entity = c.id AND t.type = 'CustInvc'
GROUP BY c.id, c.entityid, c.companyname
HAVING MAX(t.trandate) < (SYSDATE - 90) OR MAX(t.trandate) IS NULL
```

### VAT-impacting transactions for a tax period

```sql
SELECT t.tranid, t.trandate, t.subsidiary, tl.taxcode, SUM(tl.taxamount) AS tax
FROM transactionline tl
JOIN transaction t ON t.id = tl.transaction
WHERE tl.taxcode IS NOT NULL
  AND t.trandate BETWEEN '2026-04-01' AND '2026-04-30'
  AND t.subsidiary = <subsidiaryId>
GROUP BY t.tranid, t.trandate, t.subsidiary, tl.taxcode
```

### OTA daily-load reconciliation

```sql
SELECT t.id, t.tranid, t.trandate, t.memo, SUM(tl.foreignamount) AS amount
FROM transaction t
JOIN transactionline tl ON tl.transaction = t.id
WHERE t.memo LIKE 'OTA Daily Load%'
  AND t.trandate >= TRUNC(SYSDATE) - 7
GROUP BY t.id, t.tranid, t.trandate, t.memo
ORDER BY t.trandate DESC
```

### Pagination

NetSuite returns at most `limit` rows per call (default 100, max 1000). Use `offset` to page. Response includes `hasMore` and `links` for the next page.

```python
offset, all_rows = 0, []
while True:
    resp = gw.suiteql("SELECT id FROM customer", limit=1000, offset=offset)
    items = resp["data"]["items"]
    all_rows.extend(items)
    if not resp["data"].get("hasMore"):
        break
    offset += len(items)
```

### Important SuiteQL gotchas

- Use **`rownum`** (Oracle-style), not `LIMIT` inside the query — pagination is via the URL params.
- Date literals use single quotes: `'2026-04-30'`. Use `TO_DATE('2026-04-30', 'YYYY-MM-DD')` if comparing to a typed date column.
- Status values are short codes for some types (e.g. transaction status uses `'Open'`, `'Paid In Full'`) — mismatch produces 0 rows, not an error. Verify with the record API first if results look wrong.
- Joins on transaction-line require both `transactionline` and `transaction` tables.

---

## AP — vendor & bill operations

### READ — list vendors

```
GET /vendor?fields=entityid,companyname,subsidiary,email&q=companyname START_WITH "Acme"
```

### READ — bill status

```
GET /vendorbill/<internalId>?expandSubResources=true
```

### READ — open bills for a vendor

```
GET /vendorbill?q=entity IS <vendorId> AND status IS_NOT "Paid In Full"
```

### WRITE — create vendor (sandbox)

```
POST /vendor
Body:
{
  "companyname": "Acme Travel",
  "subsidiary": { "id": "<subsidiaryId>" },
  "email": "ap@acmetravel.com",
  "currency": { "id": "<currencyId>" }
}
```

Reply must include: `https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=<returnedId>`

### WRITE — create vendor bill (sandbox)

```
POST /vendorbill
Body:
{
  "entity": { "id": "<vendorId>" },
  "subsidiary": { "id": "<subsidiaryId>" },
  "trandate": "2026-05-06",
  "duedate": "2026-06-05",
  "item": [
    {
      "item": { "id": "<itemId>" },
      "quantity": 1,
      "rate": "1500.00"
    }
  ]
}
```

---

## AR — customer & invoice operations

### READ — customer lookup

```
GET /customer?q=entityid IS "CUST-001"
```

### READ — invoice status

```
GET /invoice/<internalId>
```

### READ — AR aging by subsidiary

```
GET /invoice?q=subsidiary IS <subsidiaryId> AND status IS_NOT "Paid In Full"
```

### WRITE — create customer (sandbox)

```
POST /customer
Body:
{
  "companyname": "Globex Ltd",
  "subsidiary": { "id": "<subsidiaryId>" },
  "email": "ar@globex.com",
  "currency": { "id": "<currencyId>" }
}
```

### WRITE — create invoice (sandbox)

```
POST /invoice
Body:
{
  "entity": { "id": "<customerId>" },
  "subsidiary": { "id": "<subsidiaryId>" },
  "trandate": "2026-05-06",
  "item": [ { "item": { "id": "<itemId>" }, "quantity": 1, "rate": "2500.00" } ]
}
```

---

## GL & Reporting — balances, journals, period

### READ — GL account balance

```
GET /account?q=number IS "10001"
```

### READ — trial balance saved search (custom)

```
POST /search
Body:
{
  "type": "transaction",
  "filters": [...],
  "columns": ["account","amount","subsidiary"]
}
```

### READ — period status

```
GET /accountingperiod?q=startdate ON_OR_BEFORE "2026-05-06" AND enddate ON_OR_AFTER "2026-05-06"
```

### WRITE — create journal entry (sandbox)

```
POST /journalentry
Body:
{
  "subsidiary": { "id": "<subsidiaryId>" },
  "trandate": "2026-05-06",
  "memo": "Champion-created: <user request>",
  "line": [
    { "account": { "id": "<debitAcctId>" }, "debit": 1000 },
    { "account": { "id": "<creditAcctId>" }, "credit": 1000 }
  ]
}
```

---

## Tax — codes, returns, e-invoicing

### READ — list tax codes for a subsidiary

```
GET /salestaxitem?q=subsidiary IS <subsidiaryId>
GET /purchasetaxitem?q=subsidiary IS <subsidiaryId>
```

### READ — VAT report for a period (custom saved search)

```
POST /search
Body: { "type": "transaction", "filters": [["taxcode","anyof",[…]], ["postingperiod","abs",<periodId>]] }
```

### WRITE — create custom tax code (sandbox)

```
POST /salestaxitem
Body: { "name": "GST 18% IND", "subsidiary": { "id": "<subsidiaryId>" }, "rate": "18" }
```

---

## OTA — pipeline status, CSV import logs

### READ — last OTA journal upload

```
GET /journalentry?q=memo START_WITH "OTA Daily Load" ORDER BY trandate DESC LIMIT 5
```

### READ — CSV import job status

```
GET /scriptdeployment?q=scriptid CONTAINS "ota_csv_import"
```

OTA writes are typically driven by the SFTP+CSV pipeline, not by the Champion. If a user explicitly asks the Champion to post an OTA journal in sandbox, the journal-entry POST above applies.

---

## Updates — PATCH existing records (sandbox only)

For editing fields on an existing record (vendor email change, bill due-date update, etc.) use PATCH. Body contains only the fields to change.

```
PATCH /services/rest/record/v1/vendor/<internalId>
Body: {"email": "new-ap@acmetravel.com"}
```

```
PATCH /services/rest/record/v1/vendorbill/<internalId>
Body: {"duedate": "2026-07-15"}
```

The gateway routes PATCH to the **sandbox** layer only. Production records are never modified by the Champion.

---

## Error-shape contract

Every MCP call returns one of:

```json
{ "ok": true, "data": <object>, "url": "<sandbox-or-prod-url>" }
{ "ok": false, "status": 401|400|403|429|500, "error": "<surface-able message>", "raw": <netsuite-payload> }
```

The listener forwards the surface-able message to Slack on failure. See `error_playbook.md` for what user-facing replies look like.

---

## Constraints the gateway enforces

1. **Record-API reads hit production only.** `gw.read()` always uses the production host + read TBA token-pair.
2. **Record-API writes (POST + PATCH) hit sandbox only.** `gw.create()` and `gw.update()` always use the sandbox host + write TBA token-pair. Production records are never modified by the Champion.
3. **SuiteQL respects the explicit `scope` arg.** `gw.suiteql(q, scope='prod')` (default) reads production. `gw.suiteql(q, scope='sandbox')` reads sandbox — useful for verifying a query against sandbox data before running on prod. SuiteQL is read-only by definition (no DML).
4. **No DELETE.** The Champion never deletes records, even in sandbox. If the user wants to delete, they do it manually.
5. **Idempotency key.** Every WRITE (POST + PATCH) includes a generated `X-NetSuite-Idempotency` header (UUID4); duplicate within 60 s is a no-op returning the original response.
6. **Rate limit budget.** Default 60 calls/min per scope. Exceeding triggers a queued retry with exponential backoff.
