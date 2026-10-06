> ## ⚠️ ARCHITECTURE OVERRIDE — READ FIRST
>
> **You are operating via OpenClaw, calling Oracle's NetSuite MCP Standard Tools directly.**
>
> - **Reads** → MCP server `netsuite-mcp-standard-tools-production` (account `5564218`, GET-only).
> - **Writes** → MCP server `netsuite-mcp-standard-tools-sandbox` (account `5564218-sb1`, full CRUD).
> - **Auth** is OAuth 1.0a TBA, handled inside the MCP server using `NETSUITE_<SCOPE>_*` env vars. **You never see, log, or ask for tokens.**
> - **Slack I/O** uses `SLACK_BOT_TOKEN_NETSUITE_CHAMPION` in the OpenClaw runtime env.
>
> **There is NO Python listener in the live path.** Do **NOT**:
>
> - Import or instantiate a `netsuite_mcp` Python module.
> - Try to `pip install requests` or `requests-oauthlib`.
> - Reference "the listener" or tell the user to type `@bot run_suiteql <query>` — that was the legacy architecture.
> - Check `jobs.json`, look for `netsuite_listener` services, or grep for Python files.
> - Ask the user to paste credentials.
>
> **The operating contract is `skills/wego-netsuite/SKILL.md` + `CLAUDE.md` + `MEMORY.md`.** The 5 rules, the date-phrase table, the SuiteQL quirks, and the forbidden-phrase tripwire are in `CLAUDE.md`. The capability inventory is in `references/netsuite_capabilities.md`. The verb-by-verb SuiteQL recipes are in `references/finance_tools.md`. The dimension alias dicts are in `references/dimension_aliases.md`.
>
> If anything in the rest of this document mentions a "listener", "gateway", "Python module", or instructs the user to type `@bot run_suiteql` — **treat it as legacy prose**. Call Oracle's MCP tools directly. The legacy text remains for historical context but is NOT how you operate.
>
> **Execution method:** Run queries via `exec` tool:
> ```bash
> bash -c 'set -a; source /home/openclaw/.openclaw/cron/openclaw.env; set +a; python3 /home/openclaw/.openclaw/workspace/scripts/netsuite_query.py --scope prod --query "YOUR_SQL"'
> ```
> Parse the JSON, format it, reply. Never narrate.

---

---

## title: Accounts Receivable (AR) Operations — Agent Knowledge Base maintainer: Akansha Singh ([akansha@wego.com](mailto:akansha@wego.com)) owners: Akansha Singh, Nikhil Gupta last\_updated: 2026-04-27 next\_review: 2026-05-11 source\_doc: ar\_operations.md (process-by-process rewrite, refreshed against PRODUCTION NetSuite data) data\_source: NetSuite PRODUCTION (acct 5564218\) via netsuite-prod MCP, role "Claude Agent Read-Only" (read-only token) project: NetSuite OpenClaw

# Accounts Receivable (AR) — Wego NetSuite

NetSuite AR workflow, customer management, invoicing, revenue recognition, and cash application at Wego. Process-by-process reference for the OpenClaw AI agent. **All structural data in this doc was pulled from PROD on 2026-04-27** — see `data_source` above.

---

## Agent Operating Rules (read every time)

1. **Current-state only.** Sections flagged `Status: Future / In Dev` describe planned work — never describe them as how-to for today.  
2. **Ask about subsidiary first.** AR processing varies by subsidiary. Tax codes, bank accounts, approval chains, and GL postings differ.  
3. **Prefer exact NetSuite navigation paths** (e.g., `Customers > Sales > Invoices > [invoice] > Edit`).  
4. **Cite the section** — end responses with `[AR §<section title>]`.  
5. **Escalate, don't guess** — see §Do-Not-Answer List.  
6. **Use SuiteQL** when a live lookup beats prose. Templates in §SuiteQL Query Templates. The `netsuite-prod` MCP is read-only; use `netsuite-sbx` when testing destructive shapes.  
7. **Flag gaps** — say "I don't have that yet" rather than inventing.

---

## Team & Roles

**AR Lead / Approver:** Sally Aljary — customer approvals, invoice approval (KSA / ME / SG only), AR escalations, monthly close sign-off.

**Preparers / Analysts:**

- **Hana Ragaie** — WegoPro Egypt, Wego Travel S.A.E. (EGP), ME invoices  
- **Varsha / sartha** — India AR, GST (CGST/SGST/IGST), export invoices  
- **Sandeep Mopuru** — Cash application, payment reconciliation, BRR upload errors  
- **Shambhu Poddar** — AR postings across subsidiaries  
- **Moaz Faiad** — FX / PKR rate issues  
- **Kam** — ShopCash FZ-LLC branding / logo

**Finance & Oversight:**

- **Li Ping** (Finance Director) — period reopens, GL mapping, cross-subsidiary decisions  
- **Cecilia Tong** (CFO) — credit policy, new jurisdictions  
- **Supriya Kothari** — consolidation / leadership reporting

**Technical / Integrations:**

- **Akansha Singh** & **Nikhil Gupta** — NetSuite devs, AR/BRR script owners. As of 2026-03-30 handover, Akansha owns: invoice/payment unlocks, saved-search builds, SuiteScript, permission fixes, custom record maintenance (`customrecord_cus_entity_tax_map`), reclass journals, CSV import template changes, PDF template tweaks.

**Slack Channels:**

- `#netsuite_ar` (ID `C08N2SY3HFS`) — **now private, invite-only**. Tag `@Akansha` for script/error, `@Li Ping` for policy.  
- `#finance-automation-claw` (ID `C0AVB4VR708`) — OpenClaw automation scope (Akansha \+ Nikhil \+ Deepak Thapa).  
- `#netsuite_ota` — OTA-specific invoicing.  
- `#data-automations-bow-finance` — BOW finance automations (PG pipeline, RPA).  
- `#payments-b2b-credit-management` — B2B credit / collections.

**Escalation ladder:**

1. AR preparer → `#netsuite_ar` tagging Akansha (script/permission/unlock) or Sally (approval/policy).  
2. Akansha can't resolve in a day → tag Li Ping.  
3. Cross-sub or GL-impacting → Li Ping \+ Akansha \+ Nikhil.  
4. New tax jurisdiction or threshold → Cecilia Tong via Li Ping.

---

## Subsidiaries & Currencies (live from PRODUCTION, 2026-04-27)

**19 subsidiaries total** in NetSuite OneWorld: 16 operating/holding \+ 3 elimination. Do NOT confuse `Wego Pte Ltd (Singapore)` (ID 11, main SG OpCo) with `Wego` (ID 1, root holding) or `Wego Pte Ltd (SG Group)` (ID 3, intermediate holding).

| Sub ID | Subsidiary (PROD name) | Country | Currency | Type | Active customers (PROD) |
| ----: | :---- | :---- | :---- | :---- | ----: |
| 1 | Wego | SG | SGD | Root holding | 0 |
| 2 | ShopCash Pte Ltd | SG | SGD | Operating | 21 |
| 3 | Wego Pte Ltd (SG Group) | SG | SGD | Holding | 0 |
| 5 | Wego Search Technologies India | IN | INR | Operating (India) | 78 |
| 7 | Wego Egypt LLC | EG | EGP | Operating (legacy) | 15 |
| 8 | PT Wego Travel Indonesia | ID | IDR | Operating | 26 |
| 11 | Wego Pte Ltd (Singapore) | SG | SGD | Primary SG OpCo | **527** |
| 14 | Wego Middle East | AE | AED | Operating | **359** |
| 15 | Elimination – Wego Pte Ltd Group | SG | SGD | Elimination | n/a |
| 16 | Elimination – Wego Root | SG | SGD | Elimination | n/a |
| 24 | Wego Technology Malaysia | MY | MYR | Operating | 11 |
| 25 | Wego Travel & Tourism Pakistan | PK | PKR | Operating | 10 |
| 26 | WeGo Saudi | SA | SAR | Operating (KSA) | 53 |
| 27 | Wego Group Pte Ltd | SG | SGD | Holding | 0 |
| 28 | Wego ME Travel & Tourism LLC | AE | AED | Operating | 11 |
| 29 | Wego Travel S.A.E | EG | EGP | Operating (Egypt SAE) | 32 |
| 31 | Elimination – Wego Pte Ltd Singapore | SG | SGD | Elimination | n/a |
| 32 | Shopcash FZ-LLC | AE | AED | Operating | 5 |
| 33 | Wego FZ-LLC | AE | AED | Operating | 36 |

**Total active customers (PROD, 2026-04-27): 1,193.** Top by primary sub: SG OpCo (11) 527 · ME (14) 359 · India (5) 78 · KSA (26) 53 · Wego FZ-LLC (33) 36 · Travel SAE (29) 32 · Indonesia (8) 26 · ShopCash Pte (2) 21 · Egypt LLC (7) 15\. Holding subs (1, 3, 27\) and elimination subs (15, 16, 31\) hold no AR customers — by design.

**Currencies in use:** 160 currencies are defined in NetSuite (broad master list). For AR purposes the live ones are: **SGD** (1 \= base for SG subs), **USD** (id 17), **EUR** (4), **AED** (id 9), **EGP** (7), **INR** (5), **IDR** (8), **MYR** (16), **PKR** (PKR), **SAR**, **GBP** (10), **HKD** (14), **CNY** (12), **JPY** (77), **KRW** (15). Exchange rates are stored on the `currency` record and pulled per-transaction.

---

## GL Accounts At-A-Glance (AR-relevant, from PRODUCTION)

### AR control accounts (type `AcctRec`)

PROD has **18 active accounts** of type `AcctRec`, all multi-subsidiary (assigned to all 19 subs). The functional ones used by AR processes:

| Acct \# | Name | Used for |
| :---- | :---- | :---- |
| 12010 | Accounts Receivables (Excl OTA & Interco) | Non-OTA, non-IC customer invoices |
| 12020 | Accounts Receivables \- OTA | OTA (flights/hotels) customer invoices |
| 12022 | Accounts Receivable \- OTA Revenue Accrual | Unbilled OTA revenue awaiting BRR invoicing |
| 12030 | Accounts Receivables \- Interco | Intercompany AR (e.g., Wego SG → Wego ME) |
| 1201001 / 1202001 / 1203001 | Provision for DD (Excl / OTA / Interco) | Doubtful debts provisions |
| 120 | Accounts Receivable (parent) | Native NS rollup parent |
| 1000501–1000509 / 10005 (`_TO IA` suffix) | Trade Receivable — IA series | Specialty AR accounts (legacy / regional carve-outs) — confirm with Li Ping before use |

### Revenue accounts (type `Income`) — most common AR targets

- **OTA Flights:** 4501010 · Service Fee 4501020 · Insurance 4501050 · Discount 4501060 · **Output VAT 4501070**  
- **OTA Hotels:** 4502010 · Discount 4502020 · Commission 4502030 · Service Fee 4502040 · **Output VAT 4502050**  
- **WegoPro:** Flights 4504010 · WegoPro Hotels 4504110 · WegoBeds Hotels 4504210  
- **IC pairs (ending `011`):** 4501011 / 4502011 / 4501051 — use when billing another Wego entity

### Deferred revenue

- **22010** Deferred Revenue \- Adv Billing & Prepaid Rev  
- **2001102\_TO IA** Refundable Deposits · **2001103\_TO IA** Prepaid Revenue · **2001104\_TO IA** Contingent Revenue

### Revenue items commonly used on invoices (PROD-confirmed)

WegoPro family (item ids in parens):

- WegoPro Flights (GMV) (202) · WegoPro Flights Service Fee (203) · WegoPro Flights Insurance (220)  
- WegoPro Hotels (GMV) (204) · WegoPro Hotels Service Fee (205)  
- WegoPro Other Ancillaries (221) · WegoPro Subscription & Other Revenue (172)

Intercompany items (use when billing another Wego entity):

- Flight Metasearch Revenue \- Interco (186) · Hotels Metasearch Revenue \- Interco (187)  
- IT Support outsource income \- interco (189) · Customer support outsource income \- Interco (188)  
- Metasearch Licensing Fee \- Interco (223) · Other Income \- Interco (213)  
- GMV Sales OTA Flights \- interco (214) · OTA Flights Insurance \- interco (215) · OTA Hotels \- interco (216)

Withholding tax items (Discount-type, applied as negative lines on the invoice):

- Withholding Tax Liability (SG WHT) (68) · Withholding Tax expense (SG WHT) (69)  
- Withholding Tax Receivable (PPH 23\) (96) · Withholding tax PPh 23 Other (95)  
- Withholding Tax Receivable (PPH 4\) (98) · Withholding tax PPh 4 (2) Land & Building Rental (97)  
- Withholding Tax Receivable (PPH21) (101) · Withholding tax PPh 21 Employee Tax Payable (100)

Other AR-relevant items: Advance Billing & Prepaid Revenue (93, → GL 22010\) · Other Revenue \- Non Interco (66).

Standard OTA / Meta items (selected — full list available via `item` SuiteQL): OTA Flights – Sales GMV · OTA Hotels – Sales GMV · OTA Hotels Discount · Flights Bookables Discount · Flights Sponsored Rebate · FLIGHTS META / HOTELS META · FLIGHTS SPONSORED · FLIGHTS COMPARE UNITS / HOTELS COMPARE UNITS · Barter Deal Revenue · Co-Marketing Revenue · Data partnership · Direct · Programmatic · Media Spend (Rebate) · GDS Incentive.

---

## Process: Customer Onboarding

**Status:** Live — approval required before invoicing. **Owner:** Preparer creates; **Sally Aljary approves** for KSA / ME / SG. India and Indonesia go through their local preparer chain (Sally could not approve those as of 2025-07-29).

### Steps

1. Preparer creates the customer — `Customers > Lists > Customers > New`.  
2. Required fields entered (see below).  
3. Record submitted for approval.  
4. Sally verifies: legal name accuracy · tax ID / GST validity · credit limit · duplicate check · currency matches sub base currency.  
5. Approved → customer activated, invoices can be issued.  
6. Rejected → preparer receives feedback, corrects, resubmits.

### Required fields (baseline)

Legal entity name · billing address (with postal code) · contact name/email/phone · primary currency · country · subsidiary (primary \+ any secondary) · payment terms · credit limit (if on account terms).

### Required extras per subsidiary

| Subsidiary | Extras |
| :---- | :---- |
| Wego Search Technologies (India) | **GSTIN**, state code, billing address must match state (drives CGST/SGST vs IGST) |
| Wego FZ-LLC / Wego ME / ShopCash FZ-LLC | **UAE TRN** |
| WeGo Saudi | Saudi VAT registration |
| Wego Egypt LLC / Wego Travel S.A.E | Egypt tax ID |
| PT Wego Travel Indonesia | **NPWP**, PPH codes (PPH 23 / 4(2) / 26\) |
| Wego Technology Malaysia | SST registration (if applicable) |

### Onboarding SLA

Submit Day 0 → review Day 1 → active Day 1–2 → first invoice Day 2+.

### Duplicate check

Akansha has scripted a **duplicate vendor** check. **No duplicate-customer script yet** — planned (OpenClaw scope). See §Known Gaps.

### Known issues

- India / Indonesia customers can't be approved by Sally — preparer chain handles locally (confirmed 2025-07-29).

### Escalation

Approval exceptions → Sally; policy changes → Li Ping → Cecilia.

---

## Process: Manual Invoice Creation

**Status:** Live. **Owner:** AR preparer (per sub). Sally approves for KSA / ME / SG.

### Steps

1. `Customers > Sales > Invoices > New`.  
2. Pick customer → subsidiary auto-populates.  
3. Add line items (see §GL Accounts for revenue items).  
4. Confirm tax code per line (driven by `customrecord_cus_entity_tax_map`).  
5. Save.  
   - SG / KSA / ME → status `Pending Approval`, Sally approves.  
   - India / Indonesia → local preparer chain approval.  
6. Post-approval: invoice is **locked from edit**. Only Akansha can unlock.

### GL impact

- **DR:** 12010 (non-OTA) · 12020 (OTA) · 12030 (Interco)  
- **CR:** 4501xxx / 4502xxx / 4504xxx revenue \+ tax on 4501070 / 4502050 (B2C output VAT)

### Known issues

| Issue | Cause | Fix | Date |
| :---- | :---- | :---- | :---- |
| "Billing Address required" on save | Customer has no default billing address | Customer → Address tab → add \+ mark default | recurring |
| AR preparer can't edit pending-approval invoice | Edit locked once submitted | Li Ping to allow pre-approval edit (under discussion) | 2026-04-15 |
| Period locked on AR for sub | Accounting period locked | Li Ping unlocks, or use next open period | 2026-02-10 (Jan 2026 Wego FZ-LLC) |
| PKR invoice amount ≠ JRL amount (same booking) | FX rates table updates intraday; invoice \+ JE captured different rates | **OPEN** — Moaz flagged; finance discussion | 2026-04-19 |
| ShopCash FZ-LLC invoices missing logo | Logo not uploaded | Kam to provide → Akansha to upload | 2026-03-10 |

### Escalation

Akansha for unlocks; Li Ping for period lock; Akansha \+ Nikhil for FX / PKR issue.

---

## Process: BRR-Generated Invoice (Automated)

**Status:** Live. **Owner:** Akansha \+ Nikhil (script owners since 2026-03-30 handover).

### What BRR is

Booking Revenue Recognition — Wego's custom scheduled-posting pipeline. Booking data arrives from **TPA (Travel Provider API)** → creates **Estimate** records → scheduled BRR script generates invoices and posts revenue to GL.

### BRR / Estimate scripts deployed in PROD (live, all active 2026-04-27)

| Script ID | Name | Type |
| :---- | :---- | :---- |
| `customscript_wf_ss_get_estbrr_files_sftp` | WG SS Get Estimate BRR Files From SFTP | Scheduled |
| `customscript_wg_mr_process_estimate_csv` | WG MR Process Estimate CSV | MapReduce |
| `customscript_wg_mr_process_brr_csv` | WG MR Process BRR CSV | MapReduce |
| `customscript_wg_mr_proc_unbilled_est_csv` | WG MR Process Unbilled Estimate CSV | MapReduce |
| `customscript_wg_mr_process_billed_brr_cs` | WG MR Process Billed BRR CSV | MapReduce |
| `customscript_wg_mr_open_closed_est_csv` | WG MR Open Closed Estimates From CSV | MapReduce |
| `customscript_wg_wa_upd_inv_on_ubbrr` | WG WA Update Invoice On Unbilled BRR | Action |
| `customscript_wg_wa_upd_inv_on_brr_est_fd` | WG WA Update Invoice on BRR EST FD | Action |
| `customscript_wg_wa_data_patch_est_apr_25` | WG WA Data Patch Estimate April 2025 Data | Action |
| `customscript_wg_mr_patch_est_apr_dup_lin` | WG MR Patch Estimate April Duplicate lines | MapReduce |
| `customscript_map_client` | Withholding Tax MAP client | Client |

### Flow

1. TPA feed lands → SFTP scheduled script (`customscript_wf_ss_get_estbrr_files_sftp`) pulls files.  
2. MR scripts process Estimate / BRR / Billed-BRR / Unbilled-Estimate CSVs into custom transaction records.  
3. Scheduled BRR run (daily \~01:00 SGT, before OTA Sales GMV load) — re-runs **T+1 and T+2** to catch late bookings.  
4. Workflow Actions (`customscript_wg_wa_upd_inv_on_ubbrr`, `customscript_wg_wa_upd_inv_on_brr_est_fd`) update invoices when matching Estimate / BRR rows arrive.  
5. **No manual approval needed** — posts directly.

### GL impact

- On booking → DR **12022** (AR \- OTA Revenue Accrual), CR 4501010 / 4502010 etc (revenue)  
- On invoice creation → DR **12020** (AR \- OTA), CR 12022 (swap-out) \+ tax to 4501070 / 4502050

### Custom transaction types

- `customtransactionwego_est_brr_fin_det` — header (Estimate / revenue amount)  
- `customtransactionwego_est_brr_fin_det_d` — detail rows (booking breakdown)  
- `customtransactionwego_est_brr_fin_det_o` — order detail (troubleshooting)

### Back-dating prevention (Live since Jan 2026\)

Estimate records **cannot be created or modified \>3 days in the past**. Deployed by Akansha to stop GL posting to prior (sometimes closed) months. Historical corrections require a new Estimate dated today \+ a separate manual JE via Akansha/Nikhil.

### Known issues

| Issue | Cause | Fix |
| :---- | :---- | :---- |
| Revenue not posting to GL for a day | Estimate not created — TPA feed failure or script miss | Check Estimate query logs; manual trigger |
| Wrong GL account | GL mapping misconfigured for sub | Verify 4501xxx mapping per sub with Akansha |
| Deferred revenue not recognized | BRR schedule incorrect on Estimate | Review revenue recognition schedule on Estimate |
| Back-dated error | Trying to modify Estimate \>3 days old | Create new Estimate dated today; flag for manual correction |

### Escalation

BRR script logic changes → Akansha \+ Nikhil (do-not-answer).

---

## Process: Unbilled BRR (Revenue Accrual)

**Status:** Live — but blocked by recurring error since 2025-07-29. **Owner:** Sandeep Mopuru (reconciliation), Akansha (script).

### What it is

Accrual leg: revenue is recognized but the customer isn't invoiced yet. Posts DR 12022 / CR 4501xxx — reverses out when the actual invoice is generated. Driven by `customscript_wg_mr_proc_unbilled_est_csv` and `customscript_wg_wa_upd_inv_on_ubbrr`.

### Known error (unresolved as of 2026-04-24)

```
Invalid nextapprover reference key ERROR:
Field 'custbody_wego_jv_createdbyuser.supervisor.id' Not Found.
```

**Root cause:** The preparer's `supervisor` field on their Employee record is empty, so the approval-routing script can't look it up.

**Fix:** Admin (Akansha) sets `Employee.supervisor` for the affected user. Recurring — first seen 2025-07-29 (Sally ↔ prior consultant).

### Escalation

Admin to fix Employee record; Akansha for the lookup script.

---

## Process: Credit Notes

**Status:** Currently **no approval required** for manual or automated credit notes. **New approval flow in testing** — developed by Akansha in March 2026, testing assigned to Sally's team on 2026-03-25. **Verify current state before telling users "no approval" if date \> 2026-04-30.** **Owner:** Preparer; Sally approves (under new flow).

### Steps (current state)

1. `Customers > Sales > Credit Memos > New`.  
2. Pick customer → reference original invoice.  
3. Post credit → reduces customer AR.

### GL impact

- **DR:** Revenue account (4501xxx / 4502xxx / 4504xxx) — reverses the revenue  
- **CR:** 12010 / 12020 / 12030 — reduces AR

### Escalation

Large or unusual credit notes → Sally → Li Ping.

---

## Process: Customer Payment & Cash Application

**Status:** Live. **Owner:** Sandeep Mopuru (reconciliation), AR preparer (entry).

### Steps

1. Payment arrives in bank (transfer / card / PG settlement).  
2. `Customers > Sales > Customer Payment > New` → pick customer.  
3. Apply to one or more open invoice(s).  
4. Save → posts to **Undeposited Funds** by default (interim holding account).  
5. When bank deposit is reconciled, funds move Undeposited Funds → bank GL.

### GL impact

- Step 4: DR Undeposited Funds, CR 12010 / 12020 / 12030  
- Step 5: DR Bank (per sub), CR Undeposited Funds

### PG / settlement context (2026 active streams — `#data-automations-bow-finance`)

- **Tabby** settlements  
- **Worldpay** settlements  
- **Amex** settlements  
- **NBE** (National Bank of Egypt) settlements  
- These flow through the BOW finance automation pipeline → reconciled against Customer Payment / Undeposited Funds.

### Voiding a payment

- **Void button is missing on Customer Payment** (confirmed 2026-02-13 Akansha).  
- This is because *"Void Transactions Using Reversing Journals"* is **enabled** in NS config — in that mode, you void a payment by creating a **reversing journal**, not by clicking Void.  
- Not a bug. Permission to toggle the flag \= Admin only.

### Known issues

| Issue | Fix |
| :---- | :---- |
| Payment posted to Undeposited Funds in error (wanted to go to bank) | Akansha creates reclass journal |
| Can't void payment — no Void button | Expected (reversing-journals mode) — create reversing JE |

### Escalation

Akansha for reclass journals.

---

## Process: Undeposited Funds Management

**Status:** Live (constraint enforced). **Owner:** AR preparer (creates), Sandeep (reconciles), Admin (override only).

### Constraint

The **Account field on Customer Payment is read-only** except for Admin role. Only Akansha or Nikhil can override the Account to move a payment directly to a specific bank. Everyone else: it lands in Undeposited Funds.

### Workflow

1. Customer Payment auto-lands in Undeposited Funds.  
2. Finance reconciles bank deposit → moves in-transit items out of Undeposited Funds to the specific bank GL.  
3. If a payment sits \>60 days in Undeposited Funds, investigate:  
   - Match to missed bank deposit → reconcile.  
   - Duplicate / error → reversal via Akansha.

### Diagnostic

Run Customer Payment list filtered by `Status = "Not Deposited"`, filter dates \>60 days old. Escalate stale items.

### Escalation

Admin override (payment → bank) → Akansha / Nikhil. Reclass / reversal → Akansha.

---

## Process: Intercompany AR

**Status:** Live. **Owner:** AR preparer on selling sub; AP preparer on buying sub mirrors.

### Flow

1. Subsidiary A invoices Subsidiary B — use an **IC revenue item** (PROD ids: 186 Flight Metasearch \- Interco · 187 Hotels Metasearch \- Interco · 189 IT Support outsource income \- interco · 188 Customer support outsource income \- Interco · 223 Metasearch Licensing Fee \- Interco · 213 Other Income \- Interco · 214–216 GMV OTA \- interco family).  
2. On A's books: DR **12030** (AR \- Interco), CR 4501011 / 4502011 etc (IC revenue, accounts ending `011`).  
3. On B's books (AP side, mirror): DR IC expense, CR **21030** (AP \- Interco).  
4. On consolidation, elimination subs **15, 16, 31** net the IC balances to zero.

### When IC balances don't tie

Use the sibling skill `intercompany-balance-investigation` for structured debugging. Typical causes:

- **FX drift** — rate on AR side ≠ rate on AP side (different post dates).  
- **Elimination JE missed** — new IC account opened without updating elim mapping.  
- **Wrong-account post** — AR side went to 12010 instead of 12030\.  
- **Timing** — invoice in one period, bill in the next.

### Escalation

Akansha \+ Nikhil \+ Li Ping for unresolved IC breaks.

---

## Process: Advance Journal (Intercompany)

**Status:** Live. **Owner:** AR preparer, Akansha for journal-builder script issues.

### What it is

Per the AR Process deck (slide 6): when one Wego entity transfers funds to another in advance of a billing event, an **Advance Journal Entry** is posted on both books. This is distinct from the IC AR/AP invoice flow above — it's the cash-side leg.

### Steps (high level)

1. Selling/funding entity creates a journal: DR IC Receivable (12030), CR Bank.  
2. Receiving entity mirrors: DR Bank, CR IC Payable (21030).  
3. Eliminations (15 / 16 / 31\) net the position on consolidation.  
4. When the actual invoice/bill is later issued, the AR / AP leg is offset against the advance balance.

### Known issues

- Mirror legs missing or posted in wrong period → IC break (see `intercompany-balance-investigation`).  
- Currency / FX rate mismatch between the two legs → IC break in functional currency.

### Escalation

Li Ping \+ Akansha for IC reconciliation; Akansha for any custom journal-builder script change.

---

## Process: Tax Code Handling & `INVALID_SUB_TAX_MAP`

**Status:** Live — recurring issue class. **Owner:** Akansha (custom record maintenance \+ script logic).

### Custom record (PROD-confirmed 2026-04-27)

`customrecord_cus_entity_tax_map` — maps each **Customer × Subsidiary** combination to a Tax Code \+ GL account. **1,481 active rows in PROD** (vs \~1,193 active customers, so most customers have at least one row, many have multiple).

**Schema (live PROD record id 1475):** | Field | Sample value | Meaning | |---|---|---| | `id` / `recordid` | 1475 | NS internal id | | `scriptid` | `VAL_95659_5564218_456` | Auto-generated NS script id | | `name` | 1475 | Display name (defaults to id) | | `custrecord_tax_customer` | 5915 | Customer internal id | | `custrecord_tax_sub` | 29 | Subsidiary internal id (here: Wego Travel S.A.E) | | `custrecord_tax_taxcode` | 176 | Tax code id (lookup against `taxitem`) | | `owner` | 5245 | Employee who created | | `created` / `lastmodified` | 02/12/2025 | Audit trail | | `isinactive` | F | Active flag |

One row is required per Customer × Subsidiary combination. Missing row \= `INVALID_SUB_TAX_MAP` error.

### Root cause of `INVALID_SUB_TAX_MAP`

Customer has a primary subsidiary with a tax map row, but a **secondary subsidiary without one**. When an invoice is raised from the secondary sub, NetSuite can't find the tax code → error.

### Fix

1. Open customer → Subsidiaries sub-tab → confirm secondary sub assignments.  
2. Ask Akansha (in `#netsuite_ar`) to add a row in `customrecord_cus_entity_tax_map` for the missing sub.  
3. If only **one** secondary sub, Akansha can script inheritance from the primary sub's tax code (Li Ping ↔ Akansha, 2025-10-06).

### Live lookup (SuiteQL — works in PROD today)

```sql
SELECT id, custrecord_tax_customer, custrecord_tax_sub, custrecord_tax_taxcode
FROM customrecord_cus_entity_tax_map
WHERE isinactive = 'F' AND custrecord_tax_customer = :customer_id;
```

### Common tax treatments by sub

| Subsidiary | Standard rate | Export treatment |
| :---- | :---- | :---- |
| Wego Pte Ltd (Singapore) \+ other SG | 9% SG GST | 0% for qualifying exports |
| Wego FZ-LLC / ME / ShopCash FZ-LLC | 5% UAE VAT | 0% qualifying. E-invoicing mandate Jan 1, 2027 (\>50M AED) / Jul 1, 2027 (\<15M AED) |
| WeGo Saudi | 15% KSA VAT | Zatka e-invoicing required |
| Wego Egypt / Travel S.A.E | 14% Egypt VAT | ETA portal |
| PT Wego Travel Indonesia | 11% PPN | PPH withholding items (PPH 23 / PPH 4\) |
| Wego Search Technologies (India) | 18% (CGST 9 \+ SGST 9 intra-state; 18% IGST inter-state) | 0% IGST for exports — see §India GST |
| Wego Pakistan | Sales tax (rate varies) |  |

### Escalation

`#netsuite_ar` → Akansha. New tax jurisdiction → Li Ping → Cecilia.

---

## Process: India GST & Export Edge Case

**Status:** Live — recurring open issue. **Owner:** Varsha / sartha (preparers); Akansha (unlocks); Li Ping (policy).

### Rule

- **Intra-state** (supplier and customer in same state): CGST 9% \+ SGST 9% \= 18%.  
- **Inter-state**: IGST 18%.  
- **Export** (foreign customer): IGST 0%, tagged as export.

### What drives the wrong result

- **Billing address** on the customer drives the tax code. If it lacks an "export-qualifying" attribute, system treats as domestic.  
- **GSTIN state ≠ billing address state** → posts IGST instead of CGST/SGST (or vice-versa).  
- **TP feed vs customer-provided GSTIN** mismatch — TP creates billing address, customer later updates with different GST number.

### Fix paths

- **Preferred:** correct customer record (billing address, GSTIN, export flag) BEFORE invoice creation.  
- **Reactive:** Akansha unlocks invoice → preparer corrects tax code → Sally re-approves.  
- **Open policy ask:** pre-approval edit flow for tax portion \+ billing \+ GST (sartha 2025-08, Li Ping 2026-04-15) — not yet live.

### Known issues

All from `#netsuite_ar`, 2025-08-13 onwards — recurring pattern:

- Export invoice auto-booked at 18%  
- State mismatch → wrong CGST/SGST vs IGST split  
- Billing address updated by customer post-creation (TP feed mismatch)

### Escalation

Akansha for unlock; Varsha for fix; Li Ping for policy.

---

## Process: Invoice PDF & Bank Details

**Status:** Live. **Owner:** Akansha (template management), Kam (ShopCash branding).

### Line-item grouping (expected, not a bug)

PDF template groups same-product lines by terms \+ month and sums quantity. Draft with two rows (Flights Qty 2 \+ Flights Qty 1\) prints as **one row, Qty 3** on the PDF. Internal record preserves the breakdown.

Hana ↔ Akansha flagged this 2026-03-10 — confirmed as-designed. If a customer wants lines shown separately, escalate to Akansha to adjust the PDF template (per customer or global).

### Bank details (auto-populated per subsidiary)

| Subsidiary | Bank on PDF |
| :---- | :---- |
| Wego Pte Ltd (Singapore) | DBS |
| Wego FZ-LLC / ME / ShopCash FZ-LLC | ADCB or Citibank AE |
| Wego Egypt / Travel S.A.E | CIB |
| Wego Search Technologies (India) | HDFC or Axis |
| WeGo Saudi | (confirm with Jamal) |
| Wego Pakistan | **TBD** (see §Known Gaps) |

### Template management

`Customize > Forms > Invoice`. Per-subsidiary custom template (header, footer, font, color). **Test in sandbox before prod.** Archive old templates for audit.

### Known issues

- **ShopCash FZ-LLC** invoices missing logo — Kam to provide, Akansha to upload (open since 2026-03-10).

### Escalation

Akansha for any PDF template change.

---

## Process: Invoice CSV Bulk Upload

**Status:** Live. **Owner:** AR preparer (uploads), Akansha (mapping fixes).

### Template

**`Wego | OTA SALE INVOICE Import`** — navigate `Setup > Imports > Saved CSV Imports`.

### Steps

1. Column headers in CSV must match the saved import template exactly.  
2. Run the import.  
3. Verify created invoices at `Customers > Sales > Invoices`.  
4. Review the import error log for failed rows.

### Known issues

| Error | Cause | Fix | Date |
| :---- | :---- | :---- | :---- |
| "Please add email if you wanna send invoice details email or uncheck Email" | "Send transactions Via Email" is on in the saved import, but the customer record has no email | Uncheck Email on the saved import OR populate customer emails | 2026-01-05 Hana |
| CSV bulk fails silently for some rows | Tax code not recognized for sub, or missing required field | Review import log → fix row → re-upload failed subset | recurring |

### Escalation

Akansha for mapping changes.

**Note (2026-04-27):** A full registry of CSV Import templates used by AR (with column lists and sub-by-sub variant mapping) is **not yet captured** in this doc — saved CSV Imports are not exposed via the SuiteQL surface area. Tracked in §Known Gaps.

---

## Process: File Attachments on Invoices

**Status:** Live.

### Steps

Navigation: `Customers > Sales > Invoices > [invoice] > Files tab > Attach Files`.

Select file → upload → add a description (e.g., "Supporting PO", "Proof of delivery"). Customers can view attachments via the customer portal (if enabled).

**Supported:** PDF, PNG/JPG/GIF, Excel/CSV.

---

## Process: Invoice Edit & Post-Approval Unlock

**Status:** Restricted — edit locks after approval. Akansha performs unlocks. **Owner:** Akansha (unlock), Sally (re-approval), Li Ping (policy).

### Current state

| Editable after save, pre-approval | Payment Terms, Due Date, Memo, custom fields (e.g., BU Code) | | Not editable after approval | Amount, line items, tax code, billing address — void \+ recreate, or request Akansha unlock |

### Unlock process

1. Preparer posts in `#netsuite_ar` tagging `@Akansha` with invoice ID \+ reason.  
2. Akansha unlocks → preparer edits → Sally re-approves.

### Open policy ask (Li Ping, 2026-04-15)

Allow pre-approval edit of **tax portion \+ billing address \+ GST** without full unlock. Originally requested 2025-08 by sartha. Not yet implemented.

### Escalation

Akansha for unlock; Li Ping for policy change.

---

## Process: Period Lock & Unlock

**Status:** Live. **Owner:** Li Ping.

### What locks

Accounting period can be locked separately on AR / AP / GL sides per sub. After close, new postings are blocked for that sub \+ period.

### Known lock incident

- Jan 2026 Wego FZ-LLC AR was locked when preparer tried to post JRL-WAE5413671D. Akansha ↔ Sally resolved on 2026-02-10 — either Li Ping unlocked, or preparer used a different period.

### Unlock

Only Li Ping. Preparer posts in `#netsuite_ar` with period, sub, and reason → Li Ping unlocks temporarily → preparer posts → period re-locked.

### Escalation

Li Ping only.

---

## Process: Monthly AR Close

**Status:** Live monthly cadence. **Owner:** Sally Aljary (sign-off) \+ Sandeep Mopuru (cash recon).

### Checklist

- [ ] All invoices for the period reconciled to booking system (count \+ amount match)  
- [ ] Customer payments received and receipts posted (match bank deposits)  
- [ ] **Undeposited Funds** reconciled — no stale in-transit items  
- [ ] Credit memos approved and posted  
- [ ] BRR postings verified for the period (revenue \+ accrual swap-out on invoice)  
- [ ] **AR Aging** reviewed — collections flagged for \>60 days past due  
- [ ] Customer subsidiary assignments updated (any customer moved entity)  
- [ ] Invoice template changes (if any) documented and tested  
- [ ] IC AR (12030) ties to IC AP (21030) — see §Intercompany AR  
- [ ] Period locked on AR side (Li Ping)  
- [ ] **DSO** calculated and reported to Finance

### Close calendar (reference)

| Day | Step |
| :---- | :---- |
| WD-2 | Cut-off: last trandate allowed for AR |
| WD-1 | BRR catch-up runs complete (T+2) |
| WD+1 | AR accruals posted |
| WD+3 | IC reconciliation run |
| WD+4 | Period locked on AR |

See `gl_reporting.md` for the full consolidated close sequence.

---

## Reference: SuiteQL Query Templates

Use via the NetSuite MCP (`mcp__netsuite-prod__run_suiteql` for live PROD reads, `mcp__netsuite-sbx__run_suiteql` for safe testing).

**PROD permission gap (2026-04-27):** the `transaction` table is currently NOT queryable via the prod read-only role — returns `Record 'transaction' was not found`. The role's Transactions tab needs `Find Transaction` (or equivalent) added before the SuiteQL templates below can run against PROD. They DO work today against `netsuite-sbx`. Tracked in §Known Gaps.

### Open invoices for a subsidiary (sandbox-only today)

```sql
SELECT id, tranid, trandate, entity, amount, status
FROM transaction
WHERE type = 'CustInvc' AND subsidiary = :sub_id AND status = 'Open'
ORDER BY trandate DESC;
```

### AR aging bucket (sandbox-only today)

```sql
SELECT subsidiary,
  CASE WHEN (SYSDATE - trandate) <= 30 THEN '0-30'
       WHEN (SYSDATE - trandate) <= 60 THEN '31-60'
       WHEN (SYSDATE - trandate) <= 90 THEN '61-90'
       ELSE '90+' END AS bucket,
  COUNT(*) AS invoice_count
FROM transaction
WHERE type = 'CustInvc' AND status = 'Open'
GROUP BY subsidiary,
  CASE WHEN (SYSDATE - trandate) <= 30 THEN '0-30'
       WHEN (SYSDATE - trandate) <= 60 THEN '31-60'
       WHEN (SYSDATE - trandate) <= 90 THEN '61-90'
       ELSE '90+' END;
```

### Find a customer by name fragment (works in PROD)

```sql
SELECT id, entityid, companyname, subsidiary
FROM customer
WHERE UPPER(companyname) LIKE UPPER('%:fragment%')
  AND isinactive = 'F';
```

### Active customers for a single subsidiary (works in PROD)

```sql
SELECT id, entityid, companyname
FROM customer
WHERE isinactive = 'F' AND subsidiary = :sub_id;
```

### Tax map row for a customer (works in PROD)

```sql
SELECT id, custrecord_tax_customer, custrecord_tax_sub, custrecord_tax_taxcode
FROM customrecord_cus_entity_tax_map
WHERE isinactive = 'F' AND custrecord_tax_customer = :customer_id;
```

### BRR / Estimate scripts (works in PROD)

```sql
SELECT scriptid, name, scripttype, isinactive
FROM script
WHERE LOWER(name) LIKE '%brr%' OR LOWER(name) LIKE '%estimate%' OR LOWER(name) LIKE '%tax map%';
```

### BRR journals in a period (sandbox-only today)

```sql
SELECT id, tranid, trandate, memo, amount, subsidiary
FROM transaction
WHERE type = 'Journal' AND memo LIKE '%BRR%'
  AND trandate BETWEEN TO_DATE(':start','YYYY-MM-DD') AND TO_DATE(':end','YYYY-MM-DD');
```

### AR sub-ledger for a sub × period (sandbox-only today)

```sql
SELECT t.tranid, t.trandate, t.entity, a.acctnumber, tal.debitamount, tal.creditamount
FROM transaction t
JOIN transactionaccountingline tal ON tal.transaction = t.id
JOIN account a ON a.id = tal.account
WHERE t.subsidiary = :sub_id AND a.acctnumber = '12020'
  AND t.trandate BETWEEN TO_DATE(':start','YYYY-MM-DD') AND TO_DATE(':end','YYYY-MM-DD')
ORDER BY t.trandate;
```

### Volumes quick check

**SANDBOX values (last refreshed 2026-04-24, kept here as historical reference until PROD transaction permission is granted):** Journal 153,937 · VendBill 43,351 · SalesOrd 18,114 · CustInvc 17,185 · Check 975 · CustCred 819\. PROD numbers TBD pending §Known Gaps fix.

---

## Process: AR Reporting & Dashboards

**Status:** Live for core reports; automation \+ central saved-search registry under OpenClaw scope. **Owner:** Sally Aljary (review, monthly distribution). Akansha \+ Nikhil (saved-search builds, customizations, automation). Supriya Kothari (leadership roll-up). Li Ping (consolidated / DSO).

### Navigation

- `Reports > Financial > A/R Aging Summary` or `A/R Aging Detail` — native NS reports.  
- `Reports > Saved Searches > All Saved Searches` — Wego custom searches, typically named `Wego | AR – <purpose>`.  
- `Reports > Financial > Income Statement` — revenue by GL (4501xxx / 4502xxx / 4504xxx).  
- `Reports > Financial > Balance Sheet` — AR control balances (12010 / 12020 / 12022 / 12030).

### Core AR reports

| Report | Purpose | Frequency | Owner | Built on |
| :---- | :---- | :---- | :---- | :---- |
| **Invoice Register** | Every invoice issued in date range — audit \+ revenue recon | Daily / weekly | AR preparer, Sally | Saved search: `transaction` where type \= `CustInvc` |
| **AR Aging Summary (by sub)** | Open invoices bucketed 0–30 / 31–60 / 61–90 / 90+ | Monthly close | Sally | Native NS A/R Aging Summary \+ subsidiary filter |
| **AR Aging Detail** | Per-invoice drill-down for collections follow-ups | Weekly | Sally \+ preparer | Native NS A/R Aging Detail |
| **DSO (Days Sales Outstanding)** | Avg collection cycle per sub | Monthly | Li Ping | Custom: (AR balance ÷ credit sales) × period days |
| **Revenue by Customer** | Top customers by booking / invoice value — exclude IC rev (4501011 / 4502011\) | Monthly | Finance | Saved search grouped by entity, filtered by revenue account |
| **Revenue by GL Account** | Revenue mix — OTA Flights (4501xxx) vs OTA Hotels (4502xxx) vs WegoPro (4504010 / 4504110\) vs WegoBeds (4504210 \+ 4555010\) | Monthly | Finance / Supriya | Income Statement filtered to 45xxxxx |
| **Customer Payment Status** | Open invoices \+ last-receipt date — collections queue | Daily | AR team | Saved search: unpaid `CustInvc` \+ last payment date |
| **Undeposited Funds Aging** | In-transit payments not yet deposited; items \>60 days flagged stale | Weekly | Sandeep | Saved search: Customer Payment, Status \= Not Deposited |
| **Credit Memo Register** | Credit notes issued — review for abuse / error patterns | Monthly | Sally | Saved search: `CustCred` |
| **BRR Posting Audit** | All BRR-generated invoices \+ revenue postings per period | Monthly | Akansha | Saved search joining `customtransactionwego_est_brr_fin_det*` \+ `CustInvc` |
| **IC AR vs IC AP Reconciliation** | 12030 (IC AR) tied to counter-sub's 21030 (IC AP) | Monthly | Akansha \+ Li Ping | SuiteQL join across subs — see sibling skill `intercompany-balance-investigation` |
| **Tax / Output VAT Summary** | Output VAT/GST posted to 4501070 \+ 4502050 etc. by sub \+ period | Monthly | Surbhi (tax) | See `tax_reporting.md` for full filing calendar |
| **New Customer Activity** | Customers created / activated in the period | Weekly | Sally | Saved search: `customer` filtered by date created |
| **Period AR Sub-Ledger** | Full AR postings for one sub × one period (reconciliation) | Monthly | Preparer | SuiteQL template in §SuiteQL (AR sub-ledger) |

### Leadership / consolidated reports

- **Monthly revenue mix deck** (segments: OTA / WegoPro / WegoBeds / Meta / Sponsored / Programmatic) — Supriya → Cecilia.  
- **Cross-sub AR balance** — consolidation view; eliminations via subs 15 / 16 / 31\.  
- **AR health** — aging trend \+ DSO trend \+ write-off rate \+ collections \>60 days count.

### Distribution

- Sally emails **AR Aging Summary** to Li Ping \+ Cecilia on WD+4.  
- Akansha emails **BRR Posting Audit** to Li Ping on WD+3.  
- Supriya pulls **Revenue by GL Account** \+ **Revenue by Customer** for the monthly leadership deck.  
- Collections preparers use **Customer Payment Status** daily to drive follow-up emails.

### Known issues

| Issue | Fix |
| :---- | :---- |
| Saved searches not formally catalogued — hard to know which one to run | Registry is an OpenClaw gap (see §Known Gaps); for now ask Akansha or check `#netsuite_ar` |
| AR Aging Detail slow on full history | Run per-sub, or limit filter to Open status \+ \>0 days past due |
| Revenue by Customer double-counts IC invoices | Exclude revenue accounts ending `011` (IC pairs: 4501011, 4502011, 4501051\) |
| DSO formula differs by preparer | Document canonical formula in `gl_reporting.md`; Li Ping to sign off |
| No automated AR Aging extract (beekim ask) | 2026-04-17 — pending OpenClaw build; use `netsuite-report-ticket` skill to log |

### Automation scope (OpenClaw / under development)

- **Auto-emailed AR aging extract** (beekim 2026-04-17, AR \+ AP) — not yet built.  
- **Daily AR digest to `#netsuite_ar`** — proposed in OpenClaw sync 2026-04-22 (Akansha \+ Nikhil).  
- **Consolidated AR dashboard** — planned in `#finance-automation-claw`.  
- **BRR post-run summary to Slack** — Akansha scope.

### Saved-search IDs

**TBD** — formal registry is an OpenClaw gap. **Saved searches are NOT exposed via SuiteQL** (verified PROD 2026-04-27: `savedsearch` table returns `Record not found`). Catalog must be compiled via the UI (`Reports > Saved Searches > All Saved Searches`) and exported manually. Populate this list as each report is catalogued:

| Report | Saved-search ID | Owner |
| :---- | :---- | :---- |
| Invoice Register | TBD | Akansha |
| AR Aging Summary (Wego custom) | TBD | Akansha |
| Customer Payment Status | TBD | Akansha |
| BRR Posting Audit | TBD | Akansha |
| IC AR reconciliation query | TBD | Akansha |

### Escalation

- New saved search or customization → Akansha, or use `netsuite-report-ticket` skill to log in NDS Jira.  
- Report timing / content change → Sally → Li Ping.  
- Leadership-deck change → Supriya → Cecilia.

---

## Reference: Error Catalog (by symptom)

Full Slack-sourced list — cross-reference to the process section for context.

| Error / symptom | Process | Fix |
| :---- | :---- | :---- |
| `INVALID_SUB_TAX_MAP` on save | Tax Code Handling | Akansha adds tax map row |
| `Invalid nextapprover reference key ...supervisor.id not found` | Unbilled BRR | Admin sets Employee.supervisor |
| "Billing Address required" | Manual Invoice | Customer → Address → mark Billing |
| India export invoice at 18% IGST | India GST | Update customer address / export flag; Akansha unlock if posted |
| India CGST/SGST vs IGST misclass | India GST | GSTIN state \= billing address state; or Akansha unlock |
| Void button missing on Customer Payment | Customer Payment | Expected — use reversing journal |
| Payment in Undeposited Funds, needs to move | Undep Funds | Akansha reclass journal |
| Invoice PDF grouped lines | Invoice PDF | Expected; Akansha to adjust template if needed |
| Can't edit pending-approval invoice | Invoice Edit | Open policy ask — Li Ping |
| Period locked for post | Period Lock | Li Ping unlocks |
| PKR invoice ≠ JRL amount | Manual Invoice (FX) | **OPEN** — Moaz / finance |
| ShopCash FZ-LLC missing logo | Invoice PDF | Kam \+ Akansha |
| CSV "Please add email" error | CSV Bulk | Uncheck Email or populate emails |
| India TP-feed vs updated GST | India GST | Update customer, regenerate / unlock |

---

## Do-Not-Answer List (escalate, don't guess)

- Credit limit increases → Sally → Cecilia  
- Period re-open requests → Li Ping only  
- GL account mapping changes → Li Ping \+ Akansha \+ Nikhil  
- Tax treatment for a new jurisdiction or product line → Li Ping \+ external advisor  
- BRR / Estimate script logic changes → Akansha \+ Nikhil  
- Customer write-offs → Sally → Li Ping → Cecilia (per amount)  
- Cross-subsidiary manual journals → Li Ping  
- FX rate source changes → Cecilia \+ Akansha  
- Any invoice reversal in a closed period → Akansha \+ Li Ping  
- Post-approval tax/billing edit → Akansha unlock only; policy change \= Li Ping

---

## Future / Not Yet Live

- Automated credit-note approval flow (in testing 2026-03-25)  
- Automated AR aging extract (beekim ask 2026-04-17, applies to AR \+ AP)  
- Automated receipt posting from bank feed (Li Ping ↔ Sally 2026-03-25)  
- **Customer-side duplicate prevention** (extends Akansha's vendor dedupe) — OpenClaw scope  
- **Agent-driven customer creation** with checkbox validation \+ Excel upload — OpenClaw scope  
- ShopCash FZ-LLC branded invoice template (pending Kam's logo)  
- UAE e-invoicing integration (Edicom / Cygnet / Taxilla eval — see `tax_reporting.md`)  
- India pre-approval edit of tax portion \+ billing \+ GST (sartha 2025-08, Li Ping 2026-04-15)

---

## Known Gaps (TBD)

- [ ] **PROD `transaction` table SuiteQL access** — current read-only role can't query Transactions; needs Transactions tab perm added. Without this, all live AR aging / invoice / BRR queries run against sandbox only.  
- [ ] FX rate source — NetSuite feed vs manual; PKR variance Apr 19 issue  
- [ ] Full subsidiary × tax code matrix — `taxitem` ID per sub per scenario  
- [ ] Saved-search IDs for AR reporting (UI-only; not SuiteQL-queryable)  
- [ ] CSV import template registry (full column list \+ exact required fields per scenario per sub) (UI-only; not SuiteQL-queryable)  
- [ ] Custom segments used on AR forms (UI-only; not SuiteQL-queryable)  
- [ ] ShopCash FZ-LLC invoice branding (logo \+ footer)  
- [ ] Role permission matrix (AR Clerk vs Approver vs Admin)  
- [ ] OTA booking-system → Estimate integration details (payload, frequency, retry behavior)  
- [ ] BRR reconciliation worked example with real numbers  
- [ ] Duplicate-invoice-number validation rule  
- [ ] Who owns ShopCash Pte Ltd AR (no named preparer)  
- [ ] Customer email defaults for CSV upload path  
- [ ] Pakistan primary bank  
- [ ] WeGo Saudi bank on invoice PDF

---

## Revision Log

| Date | Author | Change |
| :---- | :---- | :---- |
| 2026-04-14 | Akansha | Initial draft |
| 2026-04-23 | Akansha \+ Claude | Full rewrite for AI-agent use (§0 rules, glossary, FAQ, DNA, Gaps) |
| 2026-04-24 | Akansha \+ Claude | Enriched with sandbox (16 subs, real GL accounts, real items, volumes) \+ Slack error catalog |
| 2026-04-24 (v2) | Akansha \+ Claude | Process-by-process restructure — matches Akansha's preferred layout. |
| 2026-04-24 (v3) | Akansha \+ Claude | Expanded Reports into full Process section (14 core reports, automation scope, saved-search ID registry). |
| **2026-04-27** | **Akansha \+ Claude** | **PROD refresh.** All structural data now sourced from NetSuite PRODUCTION (acct 5564218\) via `netsuite-prod` MCP, role "Claude Agent Read-Only". 19 subs (16 op \+ 3 elim) confirmed with PROD names. Per-sub active customer counts refreshed (1,193 total active; SG OpCo 527, ME 359 lead). 18 PROD AcctRec accounts catalogued. 11 BRR / Estimate / WHT-MAP scripts confirmed live with their PROD scriptids. `customrecord_cus_entity_tax_map` confirmed in PROD with 1,481 active rows; live row schema captured. WegoPro item ids (170, 171, 172, 202–205, 220, 221\) and IC item ids (186–189, 213–216, 223\) confirmed in PROD. PG / settlement context added (Tabby / Worldpay / Amex / NBE). Advance JE process added as own section (per AR Process deck slide 6). Flagged PROD `transaction` permission gap as a Known Gap blocking AR aging / sub-ledger SuiteQL today. Saved searches / CSV import templates / custom segments confirmed NOT queryable via SuiteQL — must be sourced from UI. |

---

## Related

- `ap_operations.md` — Accounts Payable  
- `gl_reporting.md` — Chart of accounts, JE workflows, elimination  
- `tax_reporting.md` — VAT / GST / WHT / e-invoicing  
- Skill: `intercompany-balance-investigation` — IC reconciliation  
- Skill: `openclaw-meeting-actions` — sync action items from daily Nikhil / Akansha sync

