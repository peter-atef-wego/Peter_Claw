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
title: Accounts Payable (AP) Operations — Wego NetSuite PRODUCTION
maintainer: Akansha Singh (akansha@wego.com)
owners: Akansha Singh, Peter Atef
last_updated: 2026-04-28
next_review: 2026-05-12
source_doc: prod/ap_operations.md (rewrite blending Wego AP Process deck + live PROD pulls)
project: NetSuite OpenClaw
environment: PRODUCTION (account 5564218)
primary_sources:
  - "Wego AP Process.pptx.pdf" (uploaded 2026-04-28; 12 slides covering 11 AP processes)
  - mcp__netsuite-prod__run_suiteql (live PROD pulls 2026-04-24 → 2026-04-28)
  - EFT Process GDoc: https://docs.google.com/document/d/1kvJSrrR_9qH6cj1TZklvRB2wVeN4BSnuA3Uthqg7QHM/edit
---

# Accounts Payable (AP) — Wego NetSuite PROD

Authoritative reference for Wego's **production** NetSuite AP operations. The how-to flows in §6–§18 are taken from the AP team's own process deck (uploaded 2026-04-28). The infrastructure tables in §3–§5 are pulled live from `mcp__netsuite-prod__run_suiteql` against account **5564218**. Numbers will drift — see §24 revision log for the last refresh.

> **Sister doc:** `references/sbx/ap_operations.md` covers the sandbox environment. Do not quote sandbox numbers as production facts.

## 0. Agent operating rules

1. **Production only.** This doc reflects live PROD. For sandbox flows, switch to `references/sbx/ap_operations.md`.
2. **Real GL impact.** Anything described here posts to live books — never propose a write action without explicit user approval and Nurul Ain / Li Ping sign-off where applicable.
3. **Current-state only.** §22 "Future / Not Yet Live" is aspirational — don't describe it as how-to.
4. **Prefer exact NetSuite navigation paths** over prose. The deck and this doc both use the form `Lists > Relationships > Vendors > New`.
5. **Ask about subsidiary first.** Tax treatment, bank accounts, segments, and approvers all differ by sub.
6. **Escalate, don't guess** — see §21 Do-Not-Answer List.
7. **Cite the section + environment** — end with `[AP §X / prod]`.
8. **Use SuiteQL** when a live lookup beats prose. Templates in §19.
9. **Flag gaps** — §23 lists known unknowns; say "I don't have that yet."

> **PROD SuiteQL constraint:** the read-only role wired to `netsuite-prod` does **not** currently expose the `transaction`, `accountingperiod`, `customrecordtype`, or `customsegment` system tables (returns `Record was not found`). Transaction-level lookups must go through the REST record endpoints (`get_record` for `vendorBill`, `check`, `vendorPayment`, `journalEntry`, etc.) or via NetSuite UI saved searches. SBX does not have this restriction. Flag to GC / Akansha if a query needs broader access.

---

## 1. Team & escalation

### AP team

| Role | Name | Use for |
|---|---|---|
| AP Lead / Approver | Nurul Ain | Vendor approvals, bill approvals, JE approval, AP escalations, monthly close sign-off |
| Preparer | Natasya | Bill entry, vendor maintenance, AP aging |
| Preparer | Kam | UAE / SG vendor bills, ShopCash AP, branding ticket owner |
| Preparer | Rana | ME / UAE AP, SAR vendors |
| Preparer | Jamal | KSA vendors, AP postings |
| Preparer | Jinsha | India / IT vendor AP, TDS section mapping |
| Preparer | Mohamed Sherif | Egypt AP, EGP vendor bills |
| Preparer / AP ops | Shambhu Poddar | Cross-subsidiary AP entry |
| Finance analyst | Beekim | AP aging report requester; owner of "auto-extract" ask (2026-04-17) |
| Finance Director | Li Ping | Period reopens, GL mapping, cross-sub decisions |
| SuiteScript owner | GC (external, handover 2026-03-30) | Script errors, custom record changes, saved searches |

### Slack channels

- `#netsuite_ap` — main AP channel. Tag `@GC` for script/error fixes, `@Nurul Ain` for approvals.
- `#netsuite_adminsupport` — permission / script / integration cross-team.
- `#finance-automation-claw` — OpenClaw automation scope.

### Escalation ladder

1. AP preparer hits an issue → post in `#netsuite_ap` tagging GC (script/permission) or Nurul Ain (approval/policy).
2. If GC can't resolve within a day → tag Li Ping.
3. Cross-subsidiary or GL-impacting → Li Ping + Akansha + Peter.
4. New payment channel, bank H2H change, or FX rate source → Li Ping → Cecilia Tong (CFO).

---

## 2. Subsidiaries & currencies (live PROD)

PROD has **16 active operating subsidiaries + 3 elimination subsidiaries** in NetSuite (same shape as SBX). AP activity concentrates in the SG OpCo (sub 11), Wego Middle East (sub 14), Wego FZ-LLC (sub 33), India (sub 5), and Saudi (sub 26).

| Sub ID | Subsidiary | Country | Currency (PROD `subsidiary.currency` id) | Type |
|---:|---|---|---|---|
| 1 | Wego | SG | id=1 | Root holding |
| 2 | ShopCash Pte Ltd | SG | SGD (id=1) | Operating |
| 3 | Wego Pte Ltd (SG Group) | SG | SGD (id=1) | Holding |
| 5 | Wego Search Technologies Private Limited | IN | INR (id=5) | Operating (India) |
| 7 | Wego Egypt LLC | EG | EGP (id=7) | Operating (legacy EG) |
| 8 | PT Wego Travel Indonesia | ID | IDR (id=8) | Operating |
| 11 | Wego Pte Ltd (Singapore) | SG | id=1 | Operating (primary SG OpCo) |
| 14 | Wego Middle East | AE | AED (id=10) | Operating |
| 15 | Elimination – Wego Pte Ltd (Group) | SG | id=1 | Elimination |
| 16 | Elimination – Wego Root | SG | id=1 | Elimination |
| 24 | Wego Technology Malaysia | MY | MYR (id=16) | Operating |
| 25 | Wego Travel & Tourism (Pakistan) | PK | PKR (id=115) | Operating |
| 26 | WeGo Saudi for Travel and Tourism | SA | SAR (id=9) | Operating (KSA) |
| 27 | Wego Group Pte Ltd | SG | id=1 | Holding |
| 28 | Wego ME Travel & Tourism LLC | AE | AED (id=10) | Operating |
| 29 | Wego Travel S.A.E | EG | EGP (id=7) | Operating |
| 31 | Elimination – Wego Pte Ltd (Singapore) | SG | id=1 | Elimination |
| 32 | Shopcash FZ-LLC | AE | AED (id=10) | Operating |
| 33 | Wego FZ-LLC | AE | AED (id=10) | Operating |

> **PROD anomaly to verify:** `subsidiary.currency` for SG-country subsidiaries (1, 3, 11, 15, 16, 27, 31) returns **id=1**, which the `currency` table maps to USD, not SGD (id=11). The SBX KB doc lists SG subs as SGD-base. Likely a functional vs. transaction currency nuance. **Confirm with Peter / Li Ping before quoting base currency for SG subs.** [Gap §23]

### Active vendor counts — PROD vs SBX

| Subsidiary | PROD vendors | SBX vendors | Δ |
|---|---:|---:|---:|
| Wego Pte Ltd (Singapore) | 804 | 750 | +54 |
| Wego Middle East | 322 | 322 | 0 |
| Wego Search Technologies (India) | 299 | 239 | +60 |
| WeGo Saudi | 182 | 119 | +63 |
| PT Wego Travel Indonesia | 109 | 93 | +16 |
| Wego Technology Malaysia | 83 | 59 | +24 |
| Wego Pakistan | 66 | 37 | +29 |
| Wego FZ-LLC | 62 | 5 | +57 |
| Wego Egypt LLC | 54 | 38 | +16 |
| Wego Travel S.A.E | 35 | 22 | +13 |
| Shopcash Pte Ltd | 31 | 30 | +1 |
| Shopcash FZ-LLC | 18 | 9 | +9 |
| Wego ME Travel & Tourism LLC | 16 | 14 | +2 |
| Wego (root) | 12 | 12 | 0 |

**Total active PROD vendors:** 2,093 across 14 active-AP subsidiaries.

> Wego FZ-LLC and Saudi vendor counts diverge sharply between PROD and SBX — sandbox data is significantly stale for those subs. **Don't size automation work on SBX numbers alone.**

### Currency id legend (live `currency` table)

`1=USD, 4=EUR, 5=INR, 7=EGP, 8=IDR, 9=SAR, 10=AED, 11=SGD, 16=MYR, 25=AUD, 59=GBP, 77=JPY, 83=KWD, 115=PKR.`

---

## 3. Transaction types used in AP

| NS type code | REST record | Record type | Section in this doc |
|---|---|---|---|
| `VendBill` | `vendorBill` | Vendor Bill | §7 Bill Creation |
| `VendCred` | `vendorCredit` | Vendor Credit | §9 Bill Credit |
| `PurchOrd` | `purchaseOrder` | Purchase Order | (see SBX doc §7.2) |
| `Check` | `check` | Check / Payment | §8 Bill Payment |
| `VPrep` | `vendorPayment` | Vendor Payment | §8 Bill Payment |
| `Journal` | `journalEntry` | Journal Entry | §10 Journal Entry |
| `IntercompanyJournal` | `interCompanyJournalEntry` (advanced) | Advanced Intercompany JE | §11 Advanced IC JE |
| `ItemRcpt` | `itemReceipt` | Item Receipt | (PO-matched bills) |

> **PROD lookup constraint:** the SuiteQL `transaction` table is not exposed to this role in PROD. To count or filter AP transactions, use `mcp__netsuite-prod__get_record` with the REST record names above, or run from a NetSuite UI saved search.

---

## 4. GL accounts for AP (live PROD)

### AP control accounts (`accttype = AcctPay`, all subsidiaries)

| Acct # | Internal ID | Name | Used for |
|---|---:|---|---|
| 21010 | 114 | Accounts Payable - (Excl OTA & Interco) | Non-OTA, non-intercompany vendor bills |
| 21020 | 1978 | Accounts Payables - OTA | OTA supplier payables |
| 21022 | 2202 | Accounts Payable - OTA Expense Accrual | Unbilled OTA supplier accrual (mirrors AR 12022) |
| 21030 | 1979 | Accounts Payables - Interco | Intercompany AP (mirror of 12030) |
| 2104010 | 1343 | Other Payables - Others | Catch-all other payables |
| 2104020 | 1571 | Employee Payable | Employee reimbursements / advances |
| 2000201_TO IA | 1047 | TO IA Commercial Payables_TO IA | "TO IA"-branded AP — verify scope with GC |

All 7 are scoped to **all 19 subsidiaries** (1, 2, 3, 5, 7, 8, 11, 14, 15, 16, 24, 25, 26, 27, 28, 29, 31, 32, 33).

### Tax-related liability accounts (`OthCurrLiab`)

These pair with AP bills' input/withholding tax postings. Output tax accounts (used on AR side) and withholding accounts (deducted on AP payment) live here.

| Acct # | Name | Notes |
|---|---|---|
| 26016 | GST/VAT Output | Generic |
| 26020 | GST Output (Singapore) | SG |
| 26022 | VAT Output (Middle East) | UAE |
| 26024 | GST Output (India) | IN |
| 26026 | VAT Output (Egypt) | EG |
| 26028 | VAT Output (Indonesia) | ID |
| 26030 | GST on Sales MY | MY |
| 26032 | VAT Output (KSA) | SA |
| 26081 | VAT Liability SA | SA — separate from 26032; verify usage |
| 26087 | VAT on Sales PK | PK |
| 26089 | VAT on Sales SA | SA |
| 26018 | Withholding Tax Payable | Generic WHT |
| 25012 | Employee Tax Payable | Payroll WHT |
| 27510 | Provision for Corporate Income Tax | CIT provision |
| 2401013 | Accrued Tax Service Fee | Tax service accrual |
| 2000812 | Withholding tax PPh 4(2) Land & Building Rental | ID PPH 4(2) |
| 2000813 | Withholding tax PPh 23 Other | ID PPH 23 |
| 2000814 | Withholding tax PPh 21 Employee Tax Payable | ID PPH 21 |
| 2000604_TO IA | TO IA Professional Tax Payable | India professional tax (TO IA branded) |
| 2000802_TO IA | TO IA Withhold tax 194A | India 194A WHT |
| 2000803_TO IA | TO IA Withhold tax Professional Co | India 194J Co |
| 2000804_TO IA | TO IA Withhold tax Professional Non Co | India 194J Non-Co |
| 2000805_TO IA | TO IA Withhold tax Rent Co | India 194I Co |
| 2000806_TO IA | TO IA Withhold tax Rent Non Co | India 194I Non-Co |
| 2000807_TO IA | TO IA Withhold tax Contract Co | India 194C Co |
| 2000808_TO IA | TO IA Withhold tax Contract Non Co | India 194C Non-Co |
| 2000809_TO IA | TO IA Withhold tax Non Resident | India 195 NR |
| 2000810_TO IA | TO IA Withhold tax Salary | India 192 |
| 2000811_TO IA | TO IA Withhold tax Commission | India 194H |
| 2000901_TO IA | TO IA Corporate Income Tax Payable | India CIT |
| 2641110 / 2641210 | (DTS) deferred tax — IN / PK | India / Pakistan deferred tax |
| 2661110 / 2661210 | (DTR) deferred tax recoverable — IN / PK | India / Pakistan |

> **Input VAT (recoverable, AP side):** PROD has **per-jurisdiction Input VAT accounts** under `accttype = OthCurrAsset`:
> - `1401010` GST Input (Singapore)
> - `1401011` VAT Input (Middle East)
> - `1401012` GST Input (India)
> - `1401013` VAT Input (Egypt)
> - `1401014` GST on Purchases MY
> - `1401015` VAT Input (KSA)
> - `1401016` VAT Input (Indonesia)
> - `1401090` VAT on Purchases PK
> - `1401091` VAT on Purchases SA
> Plus a generic `140 GST/VAT Input & Other Tax refund` (id=1896) — likely a catch-all or legacy. Use the per-jurisdiction accounts for new postings; verify with Peter if 140 should be retired.

### SuiteQL: find an AP account in PROD

```sql
SELECT id, acctnumber, accountsearchdisplayname, accttype, subsidiary
FROM account
WHERE accttype = 'AcctPay' AND isinactive = 'F'
ORDER BY acctnumber;
```

---

## 5. Bank accounts (live PROD)

PROD has **87 active bank/cash accounts**. Highlights below.

### Per-subsidiary primary banks

| Subsidiary / region | Primary banks (PROD) |
|---|---|
| Wego SG (sub 11) | DBS (SGD/USD/INR/EUR/GBP/AUD/CAD/JPY); Citibank (SGD/USD/EUR/MYR/GBP); HSBC SG (EUR/GBP/SGD/USD); Transfermate SG; SingX SG |
| Wego ME / FZ (UAE) | ADCB AED (FZ); Citibank ME (AED/USD/SAR/KWD); HSBC FZ (AED/USD); Transfermate ME-FZ; SingX ME-FZ; Citibank SC (AED/SAR/USD) |
| WeGo Saudi | ANB (USD/BHD/SAR x2); SABB KSA; SABB USD |
| Wego India | Axis Bank (Capital + Saving); Citibank India INR; DBS India FD; HSBC INR |
| Wego Egypt | Attijariwafa EGP/USD; CIB EGP (multiple) / USD; NBE EGP |
| Wego Indonesia | BCA Menara Palma IDR/USD |
| Wego Malaysia | Cash on hand MY only — bank account TBD (see §23) |
| Wego Pakistan | Meezan (PKR/USD); MCB (PKR) |
| Cross-FX gateways | MONFX (GBP/USD/EUR/AUD); Western Union (USD/EUR); Transfermate (multi-sub); SingX (multi-sub) |

Cash-on-hand accounts exist for: ID, IN, SG, EG (multiple), MY, PK, ME-FZ.

### Fixed deposits

`1000201–1000205` ("TO IA" prefixed) cover Axis IN, Citibank SG, Samba USD, Samba AED, ADCB AED. `1121020` is a non-TO-IA Fixed Deposit - DBS Bank India.

### SuiteQL: list active banks

```sql
SELECT id, acctnumber, accountsearchdisplayname
FROM account
WHERE accttype = 'Bank' AND isinactive = 'F'
ORDER BY acctnumber;
```

---

# AP Process Flows (from the AP team's process deck — uploaded 2026-04-28)

> **Source:** "Wego AP Process.pptx.pdf", 12 slides authored by the AP team. Slides 10 (CSV Import) and 12 (AP Aging Report) were left blank in the deck — **flagged as documentation gaps in §23**. The 11 process headings below mirror the deck's table of contents on slide 1.

The 11 AP processes are: **Vendor Creation, Bill Creation, Bill Payment, Bill Credit, Journal Entry, Advanced Journal, Amortization Journal, Account Reconciliation, CSV Import, EFT Process, AP Aging Report.**

---

## 6. Vendor Creation

**Navigation:** `Lists > Relationships > Vendors > New`

### Required fields (from the deck)

| Section | Fields |
|---|---|
| **General** | Vendor Name, Email, Phone, Subsidiary |
| **Address** | Billing Address (mandatory; secondary address optional) |
| **Financial** | Currency, Payment Terms, Tax ID (TRN/GSTIN/NPWP/PAN/SST as applicable) |
| **Bank Information** | Bank name, account number, IBAN/SWIFT, beneficiary name |
| **Save** | Save → triggers manager-approval email |

### Approval workflow

1. Preparer fills the form → **Save**.
2. NetSuite emails the AP manager (Nurul Ain) for approval.
3. **Approved** → vendor becomes usable for bill entry.
4. **Rejected** → preparer corrects → resubmits → manager re-reviews. Loop continues until approved.

### Subsidiary-specific extras

| Subsidiary | Required extras |
|---|---|
| Wego Search Technologies (India, sub 5) | GSTIN, PAN (for TDS section mapping), state code |
| Wego FZ-LLC / Wego ME / ShopCash FZ-LLC (subs 33, 14, 32, 28) | UAE TRN, IBAN |
| WeGo Saudi (sub 26) | Saudi VAT reg, IBAN |
| Wego Egypt LLC / Wego Travel S.A.E (subs 7, 29) | Egypt tax ID, bank |
| PT Wego Travel Indonesia (sub 8) | NPWP, PPH code (23 / 4(2) / 21 / 26) |
| Wego Technology Malaysia (sub 24) | SST reg (if applicable) |
| Wego Pakistan (sub 25) | Vendor bank (per Moaz) |

### Duplicate prevention

GC's duplicate-vendor SuiteScript is **live in PROD**. Triggers on create; blocks if name or tax ID matches an existing vendor in the same subsidiary. Preparer should reuse the existing vendor or request a Nurul Ain exception.

---

## 7. Bill Creation

**Navigation:** `Transactions > Payables > Enter Bills`

### Step-by-step (from the deck)

1. **Vendor** — select from approved vendors only.
2. **Reference Number** — vendor's invoice number. Fails if duplicate for the same vendor (see §20 errors).
3. **Invoice Date** — tax-relevant; must fall in an open period.
4. **Subsidiary** — auto-populates from vendor; verify before save.
5. **Terms** — pull from vendor default; override when needed.
6. **Add expenses** — one or more lines, each requiring:
   - **Account** (the GL expense / asset account)
   - **Amount**
   - **Department**
   - **BU code**
   - **Product Segment**
   - **Market Segment**
   - **Tax Code** + **Tax Amount** (per jurisdiction; see §13)
7. **Attach Invoice** (optional but expected) — PDF of the supplier invoice.
8. **Save** — posts bill (or sends to Pending Approval if approval workflow is on).

> **Five-segment requirement:** every expense line **must** carry Department + BU code + Product Segment + Market Segment in addition to the account and tax code. This is the same 5-segment booking convention enforced in GL (`gl_reporting.md` §6). Bills missing segments will fail validation or land in a default bucket that breaks downstream reporting.

### Three entry paths

| Path | When used | Owner |
|---|---|---|
| **Manual entry** (deck flow above) | Default; AP team prefers this. | Per-sub preparer |
| **Bill from PO + Item Receipt** | Goods/services with a PO. | Procurement-driven; rare in AP-only books |
| **Bulk CSV upload** | Large batches. | Known fragility — see §15 |

### GL impact

- **Dr.** Expense / Asset (per line, with segments)
- **Cr.** AP control account: `21010` (default), `21020` (OTA), `21022` (OTA accrual), `21030` (intercompany), or `2104010 / 2104020` for non-vendor employee/other payables.
- **Dr.** Input VAT (1401010–1401091 per jurisdiction) when tax code marks the line recoverable.
- **Cr.** Withholding tax payable (`2000802–2000811_TO IA` for India, `2000812–2000814` for Indonesia, `26018` generic) on net-of-WHT bills.

---

## 8. Bill Payment

**Navigation:** `Transactions > Payables > Pay Bills`

### Step-by-step (from the deck)

1. **Bank Account** — choose the paying bank (e.g., `1100411 ADCB (AED) - FZ`, DBS SGD, Citibank ME, etc.).
2. **Filter** by Vendor and/or Date Range to surface eligible bills.
3. **Select Bills** — tick the bills to pay. Open vendor credits applied here (see §9).
4. **Payment Date** — must fall in an open period.
5. **Payment Method** — Check / EFT / Wire / H2H file.
6. **Submit** — generates the payment record (`Check` or `VendorPayment`).

### Approval

- **Nurul Ain approves** SG/ME payment runs.
- Other subs: per-sub preparer chain.

### Channels in production

1. **ADCB H2H (Host-to-Host)** — UAE payment integration (Wego FZ-LLC sub 33 / Wego ME sub 14). PROD bank account `1100411 ADCB (AED) - FZ`. NetSuite → file → upload to ADCB.
2. **Citibank ME / SC** — multi-currency for ME entities (AED, USD, SAR, KWD).
3. **HSBC FZ / SG** — additional ME and SG payments.
4. **DBS (SG)** — primary SG OpCo (SGD/USD/INR/EUR/GBP/AUD/CAD/JPY).
5. **ANB / SABB (KSA)** — KSA vendor payments.
6. **Attijariwafa / CIB / NBE (Egypt)** — EGP and USD.
7. **Axis / Citibank / DBS / HSBC (India)** — INR.
8. **BCA (Indonesia)** — IDR / USD.
9. **Meezan / MCB (Pakistan)** — PKR / USD.
10. **Cross-FX gateways:** MONFX, Western Union, Transfermate, SingX — non-base-ccy payouts and treasury transfers.

### GL impact

- **Dr.** AP control account (whichever the bill posted to).
- **Cr.** Bank or Interim/Clearing account.
- After file upload + bank confirmation, reconcile (§17).

### Common error: bill posted to wrong subsidiary

- Cause: preparer picked wrong sub at bill create (auto-default off for shared vendors).
- Fix in PROD: void the bill (if in open period) **or** GC reclass JE (if period closed). **Never** edit posting subsidiary directly on a posted bill in PROD.

---

## 9. Bill Credit

**Navigation:** `Transactions > Payables > Enter Vendor Credits`

### Step-by-step (from the deck)

1. **Vendor** — pick the vendor issuing the credit note.
2. **Link to Original Bill** (optional) — choose the bill being credited. NetSuite auto-fills lines; preparer can override.
3. **Items / Expenses** — enter credited amounts with the same Account / Department / BU / Product / Market / Tax Code as the original bill.
4. **Save**.
5. **Apply Credit** — go to `Pay Bills` (§8) and apply the open credit against an open bill from the same vendor + currency + subsidiary.

### GL impact

- **Dr.** AP control account (reduces vendor liability)
- **Cr.** Original expense / asset account (reverses the Dr. on the original bill, with same segments)
- Tax lines reverse the bill's tax postings.

### Common errors

- **Won't apply** — credit's currency or subsidiary doesn't match the bill. Verify before save.
- **Applied against wrong bill** — preparer reverses the application via `Vendors > Payables > Pay Bills` and re-applies.

---

## 10. Journal Entry (vendor / AP-side)

**Navigation:** `Transactions > Financial > Make Journal Entries`

> Used for AP corrections, accruals, expense reclasses, and vendor balance adjustments inside a single subsidiary.

### Step-by-step (from the deck)

1. **Header** — Subsidiary, Date, Memo, Posting Period.
2. **Line 1 (Debit side)** — Expense or Asset account; Amount; **Department + BU + Product + Market** segments; Tax Code (if applicable).
3. **Line 2 (Credit side)** — A/P control account (typically `21010` or as required); attach **Name = Vendor** so the JE moves the vendor sub-ledger; same segments.
4. **Save.**

### When to use

- Reclassing an expense between accounts (e.g., GL recoded after Li Ping mapping change)
- Posting a manual accrual against a vendor at month-end (AP team and Li Ping coordinate)
- Reversing a posting that can't be voided because period closed

### Closed-period note

If the target period is closed, request Li Ping to reopen, **or** post the JE to the next open period and reference the original transaction in the memo. Never bypass period locks in PROD.

### GL impact

Whatever Dr / Cr lines you write — the vendor sub-ledger only moves if the AP-control line carries a `Name` (vendor).

---

## 11. Advanced Journal Entry (Intercompany)

**Navigation:** `Transactions > Financial > Make Advanced Intercompany Journal Entries`

> Used for cross-subsidiary postings — e.g., SG OpCo charging FZ-LLC for shared services. NetSuite auto-creates the matching elimination side via the IC scheme.

### Step-by-step (from the deck)

1. **Header** — Subsidiary (initiating), Currency, Date, Memo, Posting Period.
2. **Lines** — for each line:
   - **Subsidiary** (the line's posting sub; can be different across lines)
   - **Account** (typically a `DFH/DFS/DFR/DTH/DTS/DTR` IC account — see §12)
   - **Debit** or **Credit**
   - **Memo**
   - **Name** (counterparty subsidiary representation, when required)
3. **Save** — NetSuite generates the IC pair and the elimination posting at consolidation.

### Use cases at Wego

- Recharging shared SG infrastructure cost to FZ-LLC.
- Settling intercompany loans (DFH/DTH families).
- Investment in subsidiary postings (IIS accounts; see `gl_reporting.md`).
- Period-end balance squaring across the elimination subs (15, 16, 31).

> Most cross-subsidiary corrections at Wego go through Advanced IC JE rather than two parallel single-sub JEs — the Advanced form is the supported tool for IC bookings.

---

## 12. Intercompany AP

### Standard IC AP flow

1. Subsidiary B receives an IC invoice from Subsidiary A.
2. Posts to AP account **21030** (Interco AP, id=1979) on B's books.
3. Mirrors A's **12030** (Interco AR).
4. Elimination subs (15, 16, 31) net IC AR/AP to zero on consolidation.

### IC account families (high-level — see `gl_reporting.md` for full chart)

| Family | Side | Meaning |
|---|---|---|
| **DFH** Due From - Holdings | Asset | A holding entity is owed from a sub |
| **DFS** Due From - Subsidiaries | Asset | A sub is owed from another sub |
| **DFR** Due From - Related | Asset | Related-party receivable |
| **DTH** Due To - Holdings | Liability | A sub owes a holding entity |
| **DTS** Due To - Subsidiaries | Liability | A sub owes another sub |
| **DTR** Due To - Related | Liability | Related-party payable |

### When IC balances don't tie in PROD

- Use the **`intercompany-balance-investigation`** skill.
- Typical causes: FX drift, elimination journal missing, AP side posted to wrong account (21010 instead of 21030), bill/invoice date mismatch spanning a period boundary, **`_TO IA`-branded accounts not aligned across subs**.

> The "TO IA"-prefixed accounts (`1047`, `2000201_TO IA`, etc.) are a parallel set tied to a specific consolidation/integration scheme. **Confirm with Li Ping / GC** before using them in IC analysis. [Gap §23]

---

## 13. Tax handling on AP bills

### Input VAT (recoverable)

- UAE / KSA / SG / Egypt / India / MY / ID — recoverable where the bill is for taxable supplies to a VAT-registered entity.
- **Posting accounts in PROD:** per-jurisdiction `1401010–1401091` (see §4). Use these on tax-coded lines.

### India TDS (withholding)

Section-coded payable accounts (PROD numbers from §4): 194A → `2000802_TO IA`, 194J Co → `2000803_TO IA`, 194J Non-Co → `2000804_TO IA`, 194I Co/Non-Co → `2000805/2000806_TO IA`, 194C Co/Non-Co → `2000807/2000808_TO IA`, 195 (NR) → `2000809_TO IA`, 192 (Salary) → `2000810_TO IA`, 194H (Commission) → `2000811_TO IA`. Vendor PAN drives section selection.

### Indonesia PPH (withholding)

- PPh 4(2) Land/Building → `2000812`
- PPh 23 Other → `2000813`
- PPh 21 Employee → `2000814`
- Posted as `Discount`-style item on the AP side (mirrors AR's WHT items).

### `INVALID_SUB_TAX_MAP` on vendor bill (PROD)

- Same root cause as AR: vendor's subsidiary assignment missing a tax map row.
- Fix: GC adds row to `customrecord_cus_entity_tax_map` (vendor side uses the same custom record).
- **In PROD this is more sensitive** than SBX — broken bill blocks the preparer's day; treat as P1.

For full tax detail (e-invoicing, FTA portal, VAT returns), see `prod/tax_reporting.md`.

---

## 14. Amortization Journal Entries

**Navigation:** `Transactions > Financial > Create Amortization Journal Entries`

> Used to recognise prepaid expenses (e.g., annual SaaS, insurance) over the months of benefit. Amortization schedules are attached at bill entry; this screen runs the periodic recognition.

### Step-by-step (from the deck)

1. **Filter** by Date / Period and Subsidiary.
2. **Submit** — NetSuite scans for amortization schedules with recognition due in the chosen period.
3. **NetSuite auto-generates** the JE: Dr. Expense (with segments), Cr. Prepaid asset.

### Supporting setup

- Each prepaid bill must have an **Amortization Template** assigned at line level (`Lists > Accounting > Amortization Templates`).
- Amortization runs typically happen as part of **monthly close** (Li Ping owns scheduling).
- Schedules carry the original line's segments forward to the recognition JE — verify via REST `get_record` on `journalEntry` if a recognition looks misposted.

### When schedules are missing

- Bill posted directly to expense (no schedule) — preparer / AP lead reverses with a JE and re-enters with schedule.
- Schedule end-date inconsistent with contract — Li Ping approves correction.

---

## 15. CSV Import (bulk bill upload)

**Navigation:** `Setup > Import / Export > Import CSV Records` (NetSuite standard)

> The deck slide 10 was **left blank** — we do not have a sanctioned process diagram for CSV import. The notes below are reconstructed from PROD usage and §20 error patterns. Treat this section as **partial; confirm with Nurul Ain / GC before relying on it.** [Gap §23]

### What we know

- Saved CSV import jobs exist for bulk vendor bill upload.
- AP team **prefers manual entry** (Nurul Ain) over CSV bulk upload because of fragility (tax codes, segment fields, period dates).
- Import job log in NetSuite shows row-level failures.

### Common CSV failure patterns

- Tax code not recognized for the bill's subsidiary → fix tax code or vendor sub.
- Required custom segment missing on a line → add Department / BU / Product / Market column.
- Period date outside open periods → adjust dates.
- Reference number duplicated within import file or against existing vendor bill → de-duplicate.

### Workflow when CSV is needed

1. Pull the saved import template (request from GC — exact template column list is a §23 gap).
2. Fill rows; validate every line has the 5 segments + tax code.
3. Run import.
4. Check the import job log; export failed rows; correct; re-import only the failed subset.
5. Spot-check a few imported bills via REST `get_record` to confirm segments + tax landed correctly.

---

## 16. EFT Process

**Navigation:** Refer to the AP team's process doc.

> The deck slide 11 points to a separate Google Doc rather than embedding the steps. The doc is the canonical EFT reference; this section summarises only what we know from PROD context.

**EFT process doc:** https://docs.google.com/document/d/1kvJSrrR_9qH6cj1TZklvRB2wVeN4BSnuA3Uthqg7QHM/edit

### Channels classified as EFT in PROD

- **ADCB H2H** (UAE) — automated file upload from NetSuite to ADCB.
- **DBS / Citibank / HSBC** SG/ME corporate banking portals — manual upload of NetSuite-generated payment files.
- **Cross-FX gateways** (MONFX, Western Union, Transfermate, SingX) — used when the payable currency doesn't match the paying bank's base currency.

### What's in the GDoc (per AP team)

- Payment file format per bank (field names, lengths, IBAN rules).
- Signatory and approval workflow per channel.
- Reconciliation steps once the bank confirms (mirrors §17 Account Reconciliation).
- Exceptions playbook for rejected files.

> **Action for the agent:** when the user asks an EFT question, read the GDoc directly via the Google Drive MCP (`read_file_content`) before answering. Don't paraphrase from this section.

---

## 17. Account Reconciliation

**Navigation:**
- Step 1 (import statement): `Transactions > Bank > Banking Import`
- Step 2 (match): `Transactions > Bank > Match Bank Data`
- Step 3 (reconcile): `Transactions > Bank > Reconcile Bank Statement`

### Step 1 — Banking Import (from the deck)

1. Open `Banking Import`.
2. **Choose Format** — supported: **CSV, OFX, QFX, BAI2, CAMT.053**.
3. **Upload** the bank statement file.
4. Submit. NetSuite parses and stages the lines.

### Step 2 — Match Bank Data (from the deck)

1. Open `Match Bank Data`.
2. NetSuite **Intelligent Matching** auto-pairs imported lines with NetSuite payments / deposits / charges.
3. **Manual matching** is required where intelligent matching can't resolve. The line **must show Difference = 0** before it can be marked matched.
4. Available actions: **Clear** (mark as matched), **Exclude** (omit the line from reconciliation, e.g., bank fees pending approval), **Undo Match** (revert).
5. Submit when all lines are resolved.

### Step 3 — Reconcile Bank Statement (from the deck)

1. Open `Reconcile Bank Statement`.
2. Enter **Statement End Date**.
3. Enter **Ending Balance** from the statement.
4. NetSuite shows reconciled vs. unreconciled lines and computes the diff.
5. When diff = 0, **Save** to lock the reconciliation for that period.

### Common issues

- **Bank statement import fails** — file format change at the bank or mapping outdated. Fix: GC updates the import mapping. Recurring across PROD's 87 bank accounts.
- **Match score wrong** — Intelligent Matching paired the wrong NetSuite transaction. Use Undo Match → manual match.
- **Unidentified bank line** — typically a bank fee, FX revaluation, or a payment that hasn't been booked. Either book the missing payment / fee, or Exclude with a memo.
- **Difference ≠ 0** — almost always a missing or duplicated NetSuite transaction; investigate before forcing reconciliation.

---

## 18. AP Aging Report

**Navigation:** `Reports > Receivables > A/P Aging Summary` (or `A/P Aging Detail`)

> The deck slide 12 was **left blank** — we do not have a sanctioned AP Aging diagram from the AP team. The notes below combine PROD usage and beekim's open ask. **Confirm cadence and exact saved-search IDs with Nurul Ain / Beekim.** [Gap §23]

### Standard reports

- **A/P Aging Summary** — by vendor, in the buckets `Current / 1-30 / 31-60 / 61-90 / 91+ days past due`.
- **A/P Aging Detail** — bill-level expansion.
- Custom **saved searches** exist per subsidiary; exact IDs are a §23 gap.

### Run cadence

- **Weekly** — beekim's ask (2026-04-17): auto-extract weekly AP aging across all subs. Currently manual.
- **Month-end** — Nurul Ain runs the global aging as part of close.

### Performance note

Global aging on PROD is slow because of the open-bill volume + saved-search complexity. Run **per-subsidiary** when possible. Request a summary saved search from GC for ad-hoc queries.

### OpenClaw automation scope

Beekim's auto-extract is in the OpenClaw backlog (see §22). Expected output: weekly summary + detail push (Slack or email), per subsidiary, with FX-translated totals to USD/SGD for the consolidated view.

---

## 19. Useful SuiteQL queries (PROD-compatible)

> SuiteQL `transaction` not exposed in PROD role. Queries below stay within what the role allows. For transaction-level analysis, use `get_record` or the NetSuite UI.

### Active vendors per subsidiary

```sql
SELECT subsidiary, COUNT(id) AS vendor_count
FROM vendor
WHERE isinactive = 'F'
GROUP BY subsidiary
ORDER BY COUNT(id) DESC;
```

### Find vendor by name

```sql
SELECT id, entityid, companyname, subsidiary, currency
FROM vendor
WHERE UPPER(companyname) LIKE UPPER('%:name_fragment%')
AND isinactive = 'F';
```

### List active AP control accounts

```sql
SELECT id, acctnumber, accountsearchdisplayname, subsidiary
FROM account
WHERE accttype = 'AcctPay' AND isinactive = 'F'
ORDER BY acctnumber;
```

### List bank accounts

```sql
SELECT id, acctnumber, accountsearchdisplayname
FROM account
WHERE accttype = 'Bank' AND isinactive = 'F'
ORDER BY acctnumber;
```

### Vendor mix by subsidiary + currency

```sql
SELECT subsidiary, currency, COUNT(id) AS cnt
FROM vendor
WHERE isinactive = 'F'
GROUP BY subsidiary, currency
ORDER BY subsidiary, COUNT(id) DESC;
```

### Pull a single vendor bill / payment (transaction lookup)

Use `mcp__netsuite-prod__get_record` with `record_type=vendorBill` (or `vendorPayment`, `journalEntry`, `vendorCredit`) and `record_id=<id>`.

---

## 20. Error catalog (PROD-relevant)

| Error / symptom | Cause | Fix in PROD | Notes |
|---|---|---|---|
| Bill posted to wrong subsidiary | Preparer picked wrong sub on bill create | Void + re-enter (open period) OR GC reclass JE (closed period). Never edit the sub on a posted bill. | Recurring; treat as P2 |
| `INVALID_SUB_TAX_MAP` on vendor bill save | Vendor's secondary sub missing tax map row | GC adds row to `customrecord_cus_entity_tax_map` | Recurring; P1 in PROD because it blocks the preparer |
| ADCB H2H payment file rejected | Field mismatch (IBAN length, beneficiary name) | Fix vendor record → regenerate file → re-upload to ADCB | Intermittent |
| Bulk bill CSV upload fails silently | Tax code not recognized for sub or missing required custom field / segment | Review import log → fix row → re-upload failed subset | Recurring |
| Bank statement import failure | File format change by bank OR mapping outdated | GC updates import mapping | Recurring across PROD's 87 accounts |
| Duplicate vendor blocked on create | GC's duplicate-vendor script matched existing vendor by name or tax ID | Use existing vendor OR Nurul Ain exception | Working as intended |
| Vendor credit won't apply against bill | Currency or subsidiary mismatch | Check credit's sub + currency must match the bill | Recurring |
| Payment run skipping bills | Bills in `Pending Approval`, not `Open` | Nurul Ain approves → rerun payment run | Recurring |
| Period locked for AP post | Accounting period locked on AP side | Li Ping unlocks, or move bill to next open period | PROD-only sensitivity (closed-period reclasses) |
| "Bill reference number already exists" | Vendor's bill number already used for this vendor | Increment / append suffix, or confirm not duplicate | Recurring |
| TDS deducted on wrong section / rate | Vendor's PAN-based section mapping outdated | Jinsha updates vendor record → rerun WHT calc on payment | India-specific |
| Amortization JE lines posted to default segment | Schedule template missing segment carry-forward | Reverse JE → fix template → re-run | Rare; verify with REST |
| Match Bank Data difference ≠ 0 | Missing or duplicated NetSuite transaction | Investigate; never force reconciliation with non-zero diff | Recurring |
| AP aging report slow | Large open-bill set + saved-search complexity | Run per-subsidiary instead of global; request a summary saved search from GC | Recurring |
| Beekim's auto-extract weekly AP aging request | Currently manual extract | **OpenClaw scope** — 2026-04-17 ask, not yet built | Future |
| SuiteQL on `transaction` blocked in PROD | Read-only role permissions | Workaround: REST `get_record` per transaction. Long-term: ask GC to grant `transaction` access. | Confirmed 2026-04-28 |

---

## 21. Do-Not-Answer List (escalate only)

In PROD these are extra-sensitive — never propose changes without sign-off:

- New vendor approval exceptions → Nurul Ain / Li Ping
- Payment term exceptions beyond policy → Nurul Ain / Li Ping
- Period re-open requests → Li Ping only
- GL account mapping changes → Li Ping + Akansha + Peter
- Tax treatment for a new jurisdiction or new vendor type → tax team
- TDS section / rate decisions on unusual vendor types → tax team
- Customer write-off analogs on AP side → Nurul Ain + Li Ping
- Cross-subsidiary manual JEs to move AP — use Advanced IC JE (§11), not parallel JEs
- FX rate source / timing changes
- Bank H2H integration changes → GC + Akansha + Treasury
- Any bill reversal in a closed period

---

## 22. Future / Not Yet Live (PROD)

- **Vendor creation automation** — OpenClaw scope; bulk upload + duplicate prevention + checkbox validation
- **Bill processing automation** — OCR → draft bill (with the 5 segments pre-populated) → preparer review flow (Peter; later phase)
- **Payment workflow automation** — Pay Bills → approval → file gen → bank integration end-to-end
- **AP aging auto-extract** — beekim's 2026-04-17 request; weekly summary + detail push (Slack or email)
- **Full bank data import auto-heal** — when bank changes format, agent flags and suggests mapping update instead of silent failure
- **Unified duplicate prevention** — across vendor / customer / bill (extends GC's vendor dedupe)
- **PROD `transaction` SuiteQL access** — request to GC; would unlock the same query templates the SBX doc has

---

## 23. Known gaps (TBD)

- [ ] **Slide 10 (CSV Import)** in the AP deck is blank — request the canonical CSV import process from Nurul Ain / GC and replace §15.
- [ ] **Slide 12 (AP Aging Report)** in the AP deck is blank — request the canonical AP Aging report procedure (saved-search IDs, cadence, recipients) and replace §18.
- [ ] Confirm SG-subsidiary base currency (`subsidiary.currency=1`) — is this USD-functional or SGD-functional? §2
- [ ] Confirm if `140 GST/VAT Input & Other Tax refund` (id=1896) is a legacy catch-all to retire, or still in active use alongside the 1401010–1401091 per-jurisdiction inputs. §4
- [ ] Scope of `_TO IA`-branded accounts (`1047`, `2000201_TO IA`, `2000604_TO IA`, etc.) — what consolidation/integration scheme? §12
- [ ] PROD bill volumes & AP aging snapshot — blocked by lack of `transaction` SuiteQL access
- [ ] Full AP expense GL map (5xxxxx / 6xxxxx) — covered in `gl_reporting.md`; cross-link when that doc lands
- [ ] ADCB H2H field spec (IBAN/beneficiary/reference rules)
- [ ] CSV bulk import template column list (AP, PROD)
- [ ] Saved-search IDs for AP aging in PROD (per subsidiary, per team)
- [ ] Role permission matrix in PROD (AP Clerk vs AP Approver vs AP Admin)
- [ ] Vendor bank details custom record + validation rules (PROD)
- [ ] Payment file specs for each non-ADCB bank (DBS, Citibank ME, HSBC, Axis, CIB, NBE, Meezan, MCB)
- [ ] MY primary bank for sub 24 (only cash-on-hand account observed; bank account used for MYR payments — through which GL?)
- [ ] Pakistan primary bank — observed Meezan + MCB; which is primary?
- [ ] Who owns ShopCash FZ-LLC AP (no named preparer)
- [ ] Confirm 26081 vs 26032 (both VAT KSA) — when does each apply?
- [ ] Confirm 26087 (VAT on Sales PK) coverage — Pakistan VAT model
- [ ] Pull the EFT GDoc into a structured PROD reference once Drive permissions allow

---

## 24. Revision log

| Date | Author | Change |
|---|---|---|
| 2026-04-28 | Akansha + Claude | **Rewrite.** Folded the 11 process flows from "Wego AP Process.pptx.pdf" (uploaded 2026-04-28) into the doc as §6–§18. Slides 10 (CSV Import) and 12 (AP Aging) were blank in the source deck — flagged as gaps. Added the 5-segment booking convention (Department + BU + Product + Market + Tax Code) consistently across Bill Creation / Vendor Credit / JE / Advanced IC JE / Amortization. Added Advanced Intercompany JE (§11) and Amortization JE (§14) sections that the previous draft was missing. Linked EFT GDoc. |
| 2026-04-28 | Akansha + Claude | (Earlier draft) First PROD-grounded skeleton. Sourced live from `mcp__netsuite-prod__run_suiteql` (subsidiaries, vendor counts, AP control accounts, tax accounts, 87 bank accounts, currency map). Flagged: PROD `transaction` SuiteQL not exposed; SG `subsidiary.currency=1` anomaly; consolidated Input VAT 140; `_TO IA` branded accounts. |

---

## 25. Related

- `prod/ar_operations.md` — Sister doc for Accounts Receivable (PROD)
- `prod/gl_reporting.md` — Chart of accounts, JE workflows, segments, elimination subs (PROD)
- `prod/tax_reporting.md` — Input VAT / TDS / PPH / e-invoicing (PROD)
- `sbx/ap_operations.md` — Sandbox equivalent of this doc
- Skill: `intercompany-balance-investigation` — IC reconciliation
- Skill: `openclaw-meeting-actions` — sync action items
- AP team's process deck: "Wego AP Process.pptx.pdf" (12 slides, uploaded 2026-04-28)
- EFT process GDoc: https://docs.google.com/document/d/1kvJSrrR_9qH6cj1TZklvRB2wVeN4BSnuA3Uthqg7QHM/edit