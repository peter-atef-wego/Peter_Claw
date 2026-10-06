# references/netsuite_capabilities.md

Complete inventory of what NetSuite (and Oracle's NetSuite MCP Standard Tools) can do, mapped to Wego use cases. Use this as the "master of NetSuite" reference — when a finance user asks "can you also…?", look here first.

**Status legend:**

- ✅ **Wired** — recipe / write protocol exists in `finance_tools.md`.
- 🔶 **Doable, undocumented** — Oracle's MCP supports it via `read_record` / `create_record` / `run_suiteql`; no Wego-specific recipe yet.
- ➕ **Add when needed** — a known finance workflow we haven't yet had to support; document on first ask.
- ⛔ **Out of scope** — not relevant for Wego (e.g. physical inventory) or actively forbidden (e.g. prod writes).

---

## 1. Entity records

| Record type | NetSuite ref | Status | Wego use case | Notes |
|---|---|---|---|---|
| Vendor | `vendor` | ✅ create, read, list-open-bills | Onboard new vendors (OTA partners, suppliers). | `companyname`, `subsidiary`, `currency`, `email`, `entityid`. |
| Customer | `customer` | ✅ create, read, list-open-invoices | B2B customers, partners. | Same shape as vendor. |
| Contact | `contact` | 🔶 | Multi-contact onboarding for a vendor/customer. | Linked via `company` field. |
| Employee | `employee` | 🔶 read | Approver lookups for IC journals, expense reports. | Keep PII redaction strict. |
| Subsidiary | `subsidiary` | ✅ list | 8 Wego entities. | Cached per-thread. |
| Partner | `partner` | ➕ | Marketing partners, OTA partners as non-vendor entities. | Used in some Wego revenue flows. |

## 2. Transaction records (the core of finance ops)

### 2.1 AP side

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Vendor Bill | `vendorbill` (`VendBill`) | ✅ create, read, list-open, approval-status, aging | OTA invoices, supplier bills. |
| Vendor Bill Approval | (status field on `vendorbill`) | 🔶 | Approve / reject pending bills. Currently read-only; transition via `approvalstatus` field. |
| Vendor Credit | `vendorcredit` (`VendCred`) | 🔶 | Returns, adjustments from vendors. |
| Vendor Payment | `vendorpayment` (`VendPymt`) | ➕ | H2H banking, manual payment runs. |
| Purchase Order | `purchaseorder` (`PurchOrd`) | 🔶 | Bill→PO matching for the OTA pipeline. |
| Item Receipt | `itemreceipt` | 🔶 | Receive against a PO before billing. |
| Expense Report | `expensereport` (`ExpRept`) | ➕ | Employee expense submission flow. |

### 2.2 AR side

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Invoice | `invoice` (`CustInvc`) | ✅ create-via-suiteql, read, list-open, aging | B2B billing, Meta Revenue. |
| Customer Payment | `customerpayment` (`CustPymt`) | ➕ | Apply received payment to open invoices. |
| Credit Memo | `creditmemo` (`CustCred`) | 🔶 | Customer refunds, returns. |
| Cash Sale | `cashsale` (`CashSale`) | 🔶 | Direct sale without an invoice. |
| Cash Refund | `cashrefund` (`CashRfnd`) | ➕ | Refund without a credit memo. |
| Customer Deposit | `customerdeposit` (`CustDep`) | ➕ | Prepayments before invoice. |
| Sales Order | `salesorder` (`SalesOrd`) | 🔶 | Quote → order → invoice flow (used selectively). |
| Item Fulfillment | `itemfulfillment` (`ItemShip`) | ⛔ | Travel — no physical fulfillment. |

### 2.3 GL side

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Journal Entry | `journalentry` (`Journal`) | ✅ create (preflight + balance check) | Manual adjustments, OTA loads, FX reval. |
| Intercompany Journal | `intercompanyjournalentry` | ➕ | Cross-subsidiary postings. Higher governance bar. |
| Statistical Journal | `statisticaljournalentry` | ⛔ | Stat-only postings — rare for Wego. |
| Bank Transfer | `transfer` (`Transfer`) | ➕ | Move cash between bank accounts. |
| Deposit | `deposit` (`Deposit`) | ➕ | Record bank deposits. |
| Memorized Transaction | `memorizedtransaction` | ➕ | Recurring journals (rent, depreciation). |

### 2.4 Custom transaction types (Wego-specific)

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Estimated/Booked Revenue Finance Detail | `customtransaction_wego_est_brr_fin_det` | 🔶 (in SuiteQL whitelist) | Wego's revenue recognition workflow. Source: `references/suiteql_recipes.md` whitelist. |

If finance has other custom transaction types, they'll appear in `metadata_catalog()` — discover at runtime.

---

## 3. Items / products

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Service Item | `serviceitem` | 🔶 | Billing line items (commission, fee). |
| Non-Inventory Item | `noninventoryitem` | 🔶 | OTA products, marketing services. |
| Inventory Item | `inventoryitem` | ⛔ | N/A — travel. |
| Item Group | `itemgroup` | ➕ | Bundled offerings. |
| Sales Tax Item | `salestaxitem` | 🔶 | Tax code on AR. |
| Purchase Tax Item | `purchasetaxitem` | 🔶 | Tax code on AP. |

---

## 4. Lists / segments (slowly-changing dimensions)

| Record | NetSuite type | Status | Wego use case |
|---|---|---|---|
| Account (GL) | `account` | ✅ list + resolver | Chart of accounts. |
| Currency | `currency` | ✅ list + resolver | 12+ currencies. |
| Exchange Rate | `currencyrate`, `consolidatedexchangerate` | ✅ get_fx_rate | FX point-in-time. |
| Accounting Period | `accountingperiod` | ✅ resolver + open/closed check | Period close, preflight. |
| Department | `department` | ✅ list | Reporting segment. |
| Location | `location` | ✅ list | Reporting segment. |
| Classification (Class) | `classification` | ✅ list | Reporting segment. (Called `class` in SuiteQL → `classification`.) |
| Subsidiary | `subsidiary` | ✅ list + 8-entity aliases | The 8 Wego entities. |

---

## 5. Approval / workflow operations

NetSuite's approval engine runs as workflow scripts. The Champion can:

| Operation | Status | How |
|---|---|---|
| Read approval status | ✅ `get_approval_status` | `SELECT approvalstatus, nextapprover FROM transaction WHERE id=…` |
| Read approval history | ✅ `get_systemnotes` | Filter `systemnote.field` for status changes. |
| Transition a bill to "Approved" | 🔶 sandbox only | `update_record('vendorbill', id, {"approvalstatus": {"id": "2"}})` — `2` = Approved in NetSuite's default vendor-bill workflow. **Validate the workflow allows REST transitions** before relying on this. |
| Reject a bill | 🔶 sandbox only | Same; `id=3` typically = Rejected. |
| Trigger workflow re-evaluation | ⛔ | Not exposed via REST. Requires SuiteScript on save. |

**Caution:** workflows often have client-side scripts that don't fire on REST writes. Test in sandbox before promising a workflow transition.

---

## 6. File Cabinet operations

Requires the RESTlet companion (`references/restlet_companion.js`) if Oracle's MCP doesn't expose this natively.

| Operation | Status | RESTlet action |
|---|---|---|
| Upload a file | 🔶 | `file_put` — base64 content + folder + name |
| Download a file | 🔶 | `file_get` — returns base64 + metadata |
| Attach file to record | ➕ | NetSuite has an `attachfile` REST endpoint; or set `attachment` field on the record. |
| List folder contents | ➕ | `SELECT * FROM file WHERE folder = :id` via SuiteQL. |

Use cases at Wego:

- Attach a vendor invoice PDF to a `vendorbill`.
- Pull the OTA CSV from File Cabinet to inspect a failed load.
- Upload supporting docs for journal entries.

---

## 7. Saved Searches

The finance team has a library of Saved Searches built in the NetSuite UI. The Champion runs them **by id** over OAuth via the RESTlet companion (`saved_search` action) — no browser, no UI login. **This is the "don't make Claw write SuiteQL for everything" path:** finance maintains the search (columns + filters) in the UI; the Champion just executes it and returns/formats the rows.

| Operation | Status | How |
|---|---|---|
| Execute a Saved Search | ✅ `run_saved_search` | Pass the id (`705`), the script id (`customsearch_x`), **or paste the NetSuite UI URL** (e.g. `.../searchresults.nl?searchid=705&whence=`) — the tool extracts the id. RESTlet companion, ≤5 000 rows. |
| List Saved Searches | ➕ | `SELECT id, title, scriptid FROM customsearch …` (limited visibility). Or ask finance for the id. |
| Filter override at run time | 🔶 | `run_saved_search(filters=...)` → RESTlet `params.filters` (filterExpression). Test cautiously. |

**How to use it:** when a user pastes a saved-search URL or names an id and wants "what this search shows," call `run_saved_search` with `search_ref=<url or id>`. The output shape is whatever the saved search defines (UI labels). For canonical/audited numbers (FX, aging, GL) prefer the locked `run_standard_report` templates — saved searches are user-maintained and can change shape without notice.

**Deploy dependency:** the `saved_search` action lives in `references/restlet_companion.js`. It works only if that script is deployed in NetSuite and the integration role can access the target search. If not, the tool returns `RESTLET_NOT_DEPLOYED` / `RESTLET_HANDLER_STALE` — surface verbatim and hand off to Akansha (admin) per Rule 5.

**Wego Saved Search inventory:** capture observed search IDs in `knowledge_base/netsuite_<domain>.md` as finance teams reference them.

---

## 8. SuiteQL — analytic surface

The workhorse for any aggregate / multi-table query. Full safety rules and 8 idiom recipes in `references/suiteql_recipes.md`. The 24-table whitelist covers the standard finance reporting surface plus the Wego custom transaction.

**When to prefer SuiteQL over Record API:**

- Aggregate (`SUM`, `COUNT`, `GROUP BY`) → SuiteQL.
- Filter across multiple records → SuiteQL.
- Single-record fetch with line items → Record API with `expandSubResources=true`.
- Period status / dimension list → SuiteQL.

---

## 9. Metadata catalog / schema introspection

Oracle's MCP exposes `metadata_catalog(record_type?)`:

- No argument → list of all record types the MCP exposes.
- With `record_type` → fields + sublists for that record.

**Use it:**

- Before any write — confirm field names exist.
- When a SuiteQL `INVALID_FIELD` fires — find the real field name.
- When finance asks "what fields are on the bill?" — return the metadata.
- At session start in `#netsuite_champion`, optionally call once and cache.

---

## 10. Bulk / async operations

| Operation | Status | How |
|---|---|---|
| CSV Import | ➕ | NetSuite's CSV import API or upload to File Cabinet + trigger via Saved Import. Mostly used for OTA daily loads — see `knowledge_base/netsuite_ota.md`. |
| Async jobs | ➕ | NetSuite exposes async REST jobs for long-running operations (re-evaluations, bulk re-saves). |
| Bulk update via SuiteQL | ⛔ | SuiteQL is read-only by design. For bulk writes, use the Record API in a loop with concurrency limits. |

---

## 11. NetSuite features not (yet) wired

These are real NetSuite capabilities that Wego uses but the Champion does not currently document patterns for. Add a recipe when finance first asks:

| Feature | NetSuite term | When to add |
|---|---|---|
| Revenue recognition | Advanced Revenue Management, schedules, accounting rules | When AR Champion users ask about deferred revenue. |
| Fixed Asset Management | `assetdepreciation`, `fixedasset` records | When GL users ask about depreciation. |
| Multi-Book Accounting | Different posting books per subsidiary | If/when Wego adopts secondary book. |
| Bank Reconciliation | `accountreconciliation` | When AP/AR users ask about reconciling H2H statements. |
| Email a record | NetSuite's `email` endpoint per record type | "Send invoice X to customer Y". |
| PDF generation | NetSuite's print endpoint per record type | "Send me the invoice PDF". |
| Workflow re-evaluation trigger | Custom REST hook | Only if Akansha exposes one. |
| Memorized transactions | `memorizedtransaction` | Recurring monthly journals (depreciation, rent). |

---

## 12. Hard rules (what we never do)

| Operation | Why never |
|---|---|
| Production write of any kind | Read-only policy; MCP plugin blocks it. |
| Inventory adjustment | N/A for travel + would violate read-only on prod anyway. |
| Token paste / re-paste prompts | Tokens live in MCP server + OpenClaw env; bot never handles them. |
| Bulk delete | Sandbox cleanup at most; one delete at a time with explicit user confirmation. |
| Cross-subsidiary write without explicit subsidiary alias | Always require subsidiary scope to avoid silent posting under the wrong entity. |
| GL post into a closed/locked period | Preflight rejects; surface error. |
| Workflow transition without sandbox test | Workflows often have client-side scripts that don't fire on REST — test first. |

---

## 13. NetSuite best-practice checklist (apply on every call)

1. **Resolve dimensions first.** Subsidiary, currency, GL account, vendor, customer, period — all by alias → id before composing SuiteQL or a write body.
2. **Use line-level subsidiary filter** (`tl.subsidiary`) for multi-leg or intercompany analytic queries.
3. **`expandSubResources=true`** on `read_record` for line items in one call (avoid N+1).
4. **Period preflight** (`is_gl_post_safe`) before every GL write.
5. **Validate write bodies** against `metadata_catalog(record_type)` if you've never written this record type before.
6. **Cap row counts** (`FETCH FIRST n ROWS ONLY` or `ROWNUM <= n`) on every SELECT.
7. **Single quotes for literals**, `TO_DATE()` for dates, `'T'`/`'F'` for booleans.
8. **Posting filter** (`t.posting = 'T'`) on every GL-impacting query.
9. **`entity` not `vendor`** on transaction-header joins; **`accountsearchdisplayname AS acctname`** on `account`; **`alllocked AS locked`** on `accountingperiod`.
10. **Concurrency ≤ 10** in-flight per agent message; `429` → wait 5 s, retry once.
11. **PII redaction** (`references/governance.md` §1) on every tool result.
12. **Sandbox banner** on every successful sandbox write.
13. **Audit log line** to `memory/knowledge/action_tracker.md` on every state change.
14. **Surface errors verbatim** — never paper over.

---

## 14. The Champion's "centralized space" promise

What the bot delivers, end-to-end, in any of the six channels and authorised DMs:

1. **Ask about Wego data** → reads from production via `run_suiteql` / `read_record` against `5564218`.
2. **Create vendor by description** → resolves subsidiary, currency, email; writes to sandbox via `create_record('vendor', body)`; replies with the sandbox URL.
3. **Create bill by description** → resolves vendor (fuzzy), subsidiary, item lines; preflights period if `trandate` is past; writes to sandbox; replies with sandbox URL.
4. **Create journal by description** → resolves accounts, subsidiary; period preflight; validates `debits=credits`; writes to sandbox; replies with sandbox URL.
5. **Run a Saved Search** → forwards to RESTlet companion (or Oracle's native call if available); returns rows.
6. **Discover schema** → calls `metadata_catalog` to list fields / sublists.
7. **Surface period status / aging / balance / FX / VAT / OTA loads** → SuiteQL recipes A–B in `finance_tools.md`.
8. **Audit a change** → `get_systemnotes` for "who changed what when".
9. **Approval status** → `get_approval_status`.
10. **Master-channel routing** → auto-classifies by domain or asks once.

Anything outside this list is **either** a 🔶 add-when-needed (write a recipe and update `finance_tools.md`) **or** out of scope (defer to Akansha).

---

## 15. When you reach a capability gap

If a user asks for something not listed above, **don't guess**. The right response sequence:

1. Call `metadata_catalog(record_type)` to confirm the record exists.
2. If it does, draft a SuiteQL or write-body **and test in sandbox first**.
3. Reply with the sandbox result + URL, plus one line: "If this looks right, I can repeat against prod" (for reads) / "logged in `action_tracker.md`" (for writes).
4. After the user confirms it worked, append the new recipe to `finance_tools.md` and update the status flag in this doc from 🔶 → ✅.

This is how the Champion grows over time — recipe-by-recipe, validated against real finance questions.
