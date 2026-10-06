# references/netsuite_record_types.md

Canonical NetSuite REST record-type names and UI URL paths — **the source of truth** maintained by Akansha (Wego's NetSuite developer). Use this table when constructing `create_record` / `update_record` / `read_record` calls, and when the user describes a record in finance-team language.

> **Why this file exists.** On 2026-05-19 the bot tried to create a "Bill Payment" by calling `create_record(record_type="billpayment", ...)`, then `create_record(record_type="bill", ...)`. Both failed (`metadata_catalog` said "not found"). Instead of surfacing the gap, the bot improvised and created a vendor bill, labeled it "Bill Payment" in Slack, and constructed a URL using `vendbill.nl` while claiming a payment was created. NetSuite UI then rejected the URL with *"Transaction type specified is incorrect"*. The actual NetSuite REST type for Bill Payment is `vendorpayment`, with URL path `vendpymt.nl`. This file makes that mapping authoritative.

---

## 1. Transactions

| User-facing term | REST record type | UI URL path | Example |
|---|---|---|---|
| Invoice | `invoice` | `app/accounting/transactions/custinvc.nl` | `…/custinvc.nl?id=1436388&whence=` |
| Credit Memo | `creditmemo` | `app/accounting/transactions/custcred.nl` | `…/custcred.nl?id=1432047&whence=` |
| Customer Payment / Receipt | `customerpayment` | `app/accounting/transactions/custpymt.nl` | `…/custpymt.nl?id=1436188&whence=` |
| Estimate / Sales Order | `salesorder` | `app/accounting/transactions/salesord.nl` | `…/salesord.nl?id=1432355&whence=` |
| Vendor Bill / Bill | `vendorbill` | `app/accounting/transactions/vendbill.nl` | `…/vendbill.nl?id=1435787&whence=` |
| **Bill Payment / Vendor Payment** | **`vendorpayment`** | **`app/accounting/transactions/vendpymt.nl`** | `…/vendpymt.nl?id=1432649&whence=` |
| Journal Entry | `journalentry` | `app/accounting/transactions/journal.nl` | `…/journal.nl?id=1436295&whence=` |
| Vendor Credit | `vendorcredit` | `app/accounting/transactions/vendcred.nl` | |
| Check | `check` | `app/accounting/transactions/check.nl` | |

## 2. Entities

| User-facing term | REST record type | UI URL path | Example |
|---|---|---|---|
| Vendor | `vendor` | `app/common/entity/vendor.nl` | `…/vendor.nl?id=6055` |
| Customer | `customer` | `app/common/entity/custjob.nl` | `…/custjob.nl?id=5544` |
| Employee | `employee` | `app/common/entity/employee.nl` | `…/employee.nl?id=5547` |

## 3. Hosts per scope

| Scope | URL host |
|---|---|
| Sandbox (writes) | `5564218-sb1.app.netsuite.com` |
| Production (reads) | `5564218.app.netsuite.com` |

Both hosts share the **same** record-type → URL-path mapping above. Only the host changes.

---

## 4. Rules — non-negotiable

1. **Use the canonical REST record-type name from the tables above.** Not the finance-team term, not a guess. Bill Payment is `vendorpayment`, never `billpayment` or `bill` or `payment`. If you're not sure, call `metadata_catalog()` with no argument to list every type the MCP exposes, search the list, then call the create/update with the canonical name.

2. **Use the `ui_url` field returned by the tool result.** `execute_create` and `execute_update` in `scripts/netsuite_mcp_server.py` build and return the correct URL. **Never hand-construct URLs in your Slack reply** — the 2026-05-19 incident happened because the bot ignored the script's returned URL and wrote `vendbill.nl` itself.

3. **The script rejects known aliases.** If you call `create_record(record_type="billpayment", ...)`, the script returns `RECORD_TYPE_ALIAS_REJECTED` with `suggested_record_type="vendorpayment"`. **Re-issue the call with the canonical name.** Do NOT substitute a different record type to make the call "work".

4. **Post-write verification runs server-side.** After every successful POST, the script does a GET round-trip to confirm the record exists and is of the claimed type. If verification fails, the script returns `POST_WRITE_VERIFY_FAILED` with the read response — surface it verbatim to the user. Do NOT claim success when verification fails.

5. **Out of scope here:** custom record types (`customrecord_*`). For those, call `metadata_catalog("customrecord_xxx")` first to confirm the type exists, then use that name verbatim.

---

## 5. When the user describes a record in plain English

Translate before calling the tool. The bot is the natural-language layer — the script just executes.

### 5.1 Primary translation table (use this first)

| If the user says (or the CSV/file implies) | You call `record_type=` | URL contains |
|---|---|---|
| "create a vendor", "onboard supplier", "add new supplier", "set up vendor" | `vendor` | `vendor.nl` |
| "create a customer", "add customer", "set up new customer" | `customer` | `custjob.nl` |
| "onboard an employee", "create employee", "add new hire" | `employee` | `employee.nl` |
| "create a vendor bill", "post a bill", "enter a bill", "AP invoice", BIL-/BILL-/BIIL- prefix | `vendorbill` | `vendbill.nl` |
| "create a bill payment", "pay this bill", "BLP-..." prefix, "pay vendor", "issue payment" | `vendorpayment` | `vendpymt.nl` |
| "raise an invoice", "create invoice for customer", "bill the customer", INV- prefix | `invoice` | `custinvc.nl` |
| "credit memo", "refund the customer", "issue credit to customer", CM- prefix | `creditmemo` | `custcred.nl` |
| "customer payment", "log a receipt", "record payment from customer", "apply customer payment" | `customerpayment` | `custpymt.nl` |
| "vendor credit", "we got a credit from supplier", "supplier credit note" | `vendorcredit` | `vendcred.nl` |
| "post a journal", "create JE", "manual GL entry", "intercompany journal", JE-/JNL- prefix | `journalentry` | `journal.nl` |
| "raise an estimate", "create sales order", "issue quote", "EST-..." / "SO-..." | `salesorder` | `salesord.nl` |
| "cut a check", "write a check" | `check` | `check.nl` |

### 5.2 Resolution flow — what to actually do

Before any `create_record` / `update_record` / `read_record` call:

1. **Identify the noun the user actually used.** Is it "vendor" (entity) or "vendor bill" (transaction)? Is it "payment" (could be customer or vendor — disambiguate)? The two-word forms ("vendor bill", "vendor payment", "customer payment") are different records than the single nouns.

2. **Match against §5.1 table.** Get the canonical `record_type` and the expected URL fragment.

3. **State the resolved type out loud BEFORE calling the tool.** First line of your reply should be:
   > *Understood: creating a `vendorpayment` (NetSuite Bill Payment). URL will use `vendpymt.nl`. Resolving dimensions now…*
   
   This gives the user an early checkpoint to correct you if you misread. See `CLAUDE.md §5.8`.

4. **Call the tool with the canonical name from the table.** Not the user's phrasing. If the user says "create a bill payment", you do not pass `record_type="bill payment"` or `"billpayment"` — you pass `record_type="vendorpayment"`.

5. **Use the `ui_url` returned by the tool.** Never hand-construct (§5.6).

### 5.3 Disambiguation patterns — when there's genuine ambiguity

| User phrase | What to ask |
|---|---|
| "create a payment" (no qualifier) | *"Customer Payment (incoming receipt) or Vendor Payment / Bill Payment (outgoing)?"* |
| "create a bill" alone | Usually `vendorbill`, but ask: *"Vendor Bill (`vendorbill`) — i.e. an AP invoice from a supplier — or did you mean Bill Payment (`vendorpayment`)?"* |
| "invoice" used for AP | If the CSV/context is AP-side, the user may mean `vendorbill`. Ask: *"AR side (customer Invoice → `invoice`) or AP side (supplier Vendor Bill → `vendorbill`)?"* |
| "create a record for X" with no record type | Ask explicitly. List 3 likely candidates. |
| Wego tranid prefix you don't recognise | Look up an existing record with that prefix via SuiteQL: `SELECT id, type, tranid FROM transaction WHERE tranid LIKE 'XYZ-%' FETCH FIRST 1 ROWS ONLY`. The `type` column tells you the canonical name. |

### 5.4 CSV-driven creation — read the header

When the user uploads a CSV and asks "create the records from this CSV", do not guess the record type from the filename. Check:

1. **Column headers** — `Transaction Number` + `Apply Ref No` + `Posting Period` + `Account` (bank) → likely a Bill Payment (`vendorpayment`). `Bill Number` + `Vendor` + `Account` (expense) + `Amount` → likely a Vendor Bill (`vendorbill`).
2. **tranid prefix** in the data — `BLP-` (Bill Payment), `BIL-`/`BILL-` (Vendor Bill), `INV-` (Invoice), `JE-` (Journal Entry), `CM-` (Credit Memo).
3. **Confirm with the user** before any write: *"This CSV looks like Bill Payment records (BLP- prefix, Apply Ref No column). Each row will become a `vendorpayment` in sandbox. Confirm and I'll start with row 1, or correct me if it's actually [other type]."*

### 5.5 Entity vs Transaction — never confuse them

The user-facing word "vendor" is ambiguous:

- **Just "vendor"** → entity record (`vendor`, URL `vendor.nl`). Setting up a new supplier.
- **"Vendor bill"** → transaction record (`vendorbill`, URL `vendbill.nl`). Recording a bill we owe.
- **"Vendor payment" / "Bill Payment"** → transaction record (`vendorpayment`, URL `vendpymt.nl`). Paying a bill we owe.
- **"Vendor credit"** → transaction record (`vendorcredit`, URL `vendcred.nl`). A credit memo from a supplier.

Same disambiguation for "customer":

- **"Customer"** → entity (`customer`, URL `custjob.nl`).
- **"Customer payment" / "Receipt"** → transaction (`customerpayment`, URL `custpymt.nl`).
- **"Customer credit" / "Credit memo"** → transaction (`creditmemo`, URL `custcred.nl`).

**Heuristic**: an entity is a *thing that exists in your system* (a supplier, a buyer). A transaction is *something that happened* (a bill arrived, a payment went out). If the user is creating "a new vendor" — that's the entity. If they're recording "a vendor bill for $X dated Y" — that's a transaction against an existing vendor entity.

---

## 6. Maintenance

This file is co-authoritative with the `RECORD_URL_PATHS` and `RECORD_TYPE_ALIASES_TO_CANONICAL` dicts in `scripts/netsuite_mcp_server.py`. **When you add a record type to one, add it to the other in the same commit.** Drift between this doc and the script is a bug.

Last verified against Akansha's spec: 2026-05-19.
