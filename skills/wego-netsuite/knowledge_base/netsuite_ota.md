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
title: Tax Reporting — Wego NetSuite PRODUCTION
maintainer: Akansha Singh (akansha@wego.com)
owners: Akansha Singh, Peter Atef
last_updated: 2026-04-28
next_review: 2026-05-12
source_doc: prod/tax_reporting.md (first PROD-grounded draft)
project: NetSuite OpenClaw
environment: PRODUCTION (account 5564218)
---

# Tax Reporting — Wego NetSuite PROD

Authoritative reference for Wego's **production** tax accounts, withholding workflows, and statutory reporting structure. All accounts pulled live via `mcp__netsuite-prod__run_suiteql`.

> Sister docs: `references/sbx/tax_reporting.md`; `prod/ar_operations.md`, `prod/ap_operations.md`, `prod/gl_reporting.md`.

## 0. Agent operating rules

1. **Production only.** This doc reflects live PROD tax setup. For sandbox flows, use `references/sbx/tax_reporting.md`.
2. **Tax has filing consequences.** Wrong code on a posted transaction = wrong return. Never propose a tax-code change without explicit user approval and tax-team sign-off.
3. **Ask jurisdiction first.** Tax treatment varies by subsidiary — SG / UAE / KSA / EG / IN / ID / MY / PK each have their own input + output + WHT structure.
4. **Cite section + environment** — `[Tax §X / prod]`.
5. **Escalate, don't guess** — see §10 Do-Not-Answer List.
6. **Flag gaps** — §12 lists known unknowns.

> **PROD constraint:** the tax-code custom record (`customrecord_cus_entity_tax_map`) is owned by GC. Read access from this role is limited; for tax-map debugging escalate via `#netsuite_adminsupport`.

---

## 1. Output tax — sales side (per-jurisdiction, `OthCurrLiab`)

| Acct # | Name | Jurisdiction | Notes |
|---|---|---|---|
| 26016 | GST/VAT Output | Generic | Catch-all; verify if still in active use |
| 26020 | GST Output (Singapore) | SG | 9% standard rate (per current SG GST) |
| 26022 | VAT Output (Middle East) | UAE | 5% standard |
| 26024 | GST Output (India) | IN | 18% standard for services; export = 0 |
| 26026 | VAT Output (Egypt) | EG | Egypt VAT |
| 26028 | VAT Output (Indonesia) | ID | 11% PPN |
| 26030 | GST on Sales MY | MY | MY sales/service tax |
| 26032 | VAT Output (KSA) | SA | 15% standard |
| 26081 | VAT Liability SA | SA | **Likely Saudi — confirm scope vs 26032 / 26089** [Gap §12] |
| 26087 | VAT on Sales PK | PK | Pakistan |
| 26089 | VAT on Sales SA | SA | **Confirm scope vs 26032 / 26081** [Gap §12] |

### Special output VAT income lines (`accttype = Income`)

These post on revenue side rather than the standard liability account — used for B2C OTA where output tax is rolled into revenue presentation:

| Acct # | Name |
|---|---|
| 4501070 | OTA Flights (B2C) Output VAT |
| 4502050 | OTA Hotels (B2C) Output VAT |
| 48020 | Airport Tax Recovery (income recovery line) |

> **Pattern note:** for B2C OTA bookings, output VAT lands in 4501070 / 4502050 (Income) rather than 26022 / 26032 (Liability). This is unusual — confirm with Li Ping that the system reverses these to the correct liability at month-end via JE, otherwise statutory reports may understate VAT liability. [Gap §12]

---

## 2. Input tax — purchase side (per-jurisdiction, `OthCurrAsset`)

| Acct # | Name | Jurisdiction |
|---|---|---|
| 1401010 | GST Input (Singapore) | SG |
| 1401011 | VAT Input (Middle East) | UAE |
| 1401012 | GST Input (India) | IN |
| 1401013 | VAT Input (Egypt) | EG |
| 1401014 | GST on Purchases MY | MY |
| 1401015 | VAT Input (KSA) | SA |
| 1401016 | VAT Input (Indonesia) | ID |
| 1401090 | VAT on Purchases PK | PK |
| 1401091 | VAT on Purchases SA | SA — second SA-coded input acct, verify scope |

> Pairs with the AP-side bill posting (see `prod/ap_operations.md §8`).

> A generic `140 GST/VAT Input & Other Tax refund` (id=1896) also exists. Confirm whether it's a legacy catch-all to retire or still actively booked. [Gap §12]

---

## 3. India TDS — withholding (`OthCurrLiab`, all `_TO IA` branded)

Section-coded payable accounts. Vendor PAN + service type drive section selection on bill payment.

| Acct # | Section | Description |
|---|---|---|
| 2000604_TO IA | Professional Tax Payable | Karnataka / Maharashtra etc. professional tax (state-level) |
| 2000802_TO IA | **194A** | Interest other than securities |
| 2000803_TO IA | **194J** Co | Professional fees — corporate |
| 2000804_TO IA | **194J** Non-Co | Professional fees — non-corporate |
| 2000805_TO IA | **194I** Co | Rent — corporate |
| 2000806_TO IA | **194I** Non-Co | Rent — non-corporate |
| 2000807_TO IA | **194C** Co | Contract — corporate |
| 2000808_TO IA | **194C** Non-Co | Contract — non-corporate |
| 2000809_TO IA | **195** | Non-resident payments |
| 2000810_TO IA | **192** | Salary TDS |
| 2000811_TO IA | **194H** | Commission |
| 2000901_TO IA | CIT Payable | Corporate Income Tax |

> Use SuiteScript to drive section selection from vendor PAN — owned by Jinsha + GC. Manual override only with tax-team sign-off.

---

## 4. Indonesia PPH — withholding (`OthCurrLiab`, **NOT** TO IA-branded)

| Acct # | Section | Description |
|---|---|---|
| 2000812 | **PPh 4(2)** | Land & Building Rental WHT (final) |
| 2000813 | **PPh 23** | Other (services, royalties, dividends) |
| 2000814 | **PPh 21** | Employee Tax Payable (payroll WHT) |

> Posted as `Discount`-style item on AP side; mirrors AR's WHT items.

> **Naming inconsistency:** 2000812-2000814 are **not** TO-IA-branded, while the India TDS accounts 2000802-2000811 **are** TO-IA-branded. Confirm with GC whether this is intentional (Indonesia PPH was added later under a different convention) or whether the Indonesia accounts should be retagged. [Gap §12]

---

## 5. Generic / cross-jurisdiction WHT accounts

| Acct # | Name | Type | Notes |
|---|---|---|---|
| 26018 | Withholding Tax Payable | OthCurrLiab | Generic / fallback |
| 14020 | Withholding Tax Receivable | OthCurrAsset | When Wego **is** the recipient (e.g., customer withholds on invoice) — pair with AR |
| 690 | Withholding Tax on Revenue | Expense | When customer's WHT effectively reduces realized revenue |
| 25012 | Employee Tax Payable | OthCurrLiab | Payroll WHT (cross-sub) |

---

## 6. Corporate income tax & deferred tax

### CIT provisioning

| Acct # | Name | Type |
|---|---|---|
| 27510 | Provision for Corporate Income Tax | OthCurrLiab |
| 2000901_TO IA | Corporate Income Tax Payable (TO IA) | OthCurrLiab |
| 5070001_TO IA | Income Tax expenses (TO IA) | Expense |
| 5070003_TO IA | Transfer of payment on behalf - Tax Expense | Expense |
| 5030228_TO IA | Tax allowance | Expense |
| 99010 | Income Tax expenses | OthExpense (separate from 5070001) |

> **Two income-tax expense accounts (5070001_TO IA vs 99010):** confirm posting rule — which subs use which. [Gap §12]

### Deferred tax

| Acct # | Name | Type |
|---|---|---|
| 17910 | Deferred Tax Assets - Acc Tax losses | OthAsset |
| 1801110 | (IIS) Wego India 99% | OthAsset |
| 1801210 | (IIS) Wego Pakistan 99% | OthAsset |
| 1801211 | (IIS) Impairment - Wego Pakistan | OthAsset |
| 2641110 | (DTS) Wego India 99% | OthCurrLiab — Due To Subsidiary, IN |
| 2641210 | (DTS) Wego Pakistan 99% | OthCurrLiab — DTS, PK |
| 2661110 | (DTR) Wego India 99% | OthCurrLiab — Due To Related, IN |
| 2661210 | (DTR) Wego Pakistan 99% | OthCurrLiab — DTR, PK |
| 2001201_TO IA | Deferred Tax Liability (TO IA) | LongTermLiab |

> The DTS/DTR sets above **only exist for IN and PK** in current PROD. Other subs presumably handle related-party balances via DFH/DFS/DFR (assets) — but no DTS/DTR exists for SG, UAE, EG, ID, MY, SA. Confirm whether this is by design or a gap. [Gap §12]

### Tax expense accruals & service fees

| Acct # | Name |
|---|---|
| 2401013 | Accrued Tax Service Fee (OthCurrLiab) |
| 8501013 | Tax service fees (Expense) |

---

## 7. Tax codes & subsidiary tax maps

Tax codes apply per subsidiary and are matched on transaction lines via the custom record `customrecord_cus_entity_tax_map`. Common errors:

### `INVALID_SUB_TAX_MAP`
- Customer / vendor's secondary subsidiary lacks a tax-map row.
- Surfaces on save of invoice / bill.
- Fix: GC adds row to `customrecord_cus_entity_tax_map`.
- **PROD impact:** P1 — blocks the AR/AP preparer's day. Treat as immediate escalation to GC via `#netsuite_adminsupport`.

### Tax-code application order (per line on invoice/bill)
1. NetSuite checks the entity's primary subsidiary → looks up tax code from tax-map.
2. If the line's posting subsidiary differs (multi-sub flow) → looks up secondary sub.
3. If no row exists → throws `INVALID_SUB_TAX_MAP`.

### Subsidiary-specific output tax codes (PROD)

| Sub ID | Subsidiary | Standard rate | Output Acct |
|---:|---|---|---|
| 11 | Wego Pte Ltd (Singapore) | 9% GST | 26020 |
| 14 | Wego Middle East (UAE) | 5% VAT | 26022 |
| 5 | Wego India | 18% GST (services) / 0% export | 26024 |
| 7 | Wego Egypt LLC | EG VAT | 26026 |
| 29 | Wego Travel SAE (Egypt) | EG VAT | 26026 |
| 8 | Wego Indonesia | 11% PPN | 26028 |
| 24 | Wego Malaysia | MY SST | 26030 |
| 26 | WeGo Saudi | 15% VAT | 26032 / 26081 / 26089 — **confirm split** |
| 25 | Wego Pakistan | PK VAT | 26087 |
| 33 | Wego FZ-LLC | 5% UAE VAT | 26022 |
| 28 | Wego ME T&T | 5% UAE VAT | 26022 |
| 32 | Shopcash FZ-LLC | 5% UAE VAT | 26022 |

> Rates are current-state per common knowledge; verify against the latest GC tax-map for any rate changes. [Gap §12]

---

## 8. AR-side WHT items (when customer withholds)

When a Wego customer withholds tax on an invoice (common in IN, SA, EG, ID), the WHT amount reduces realized revenue:

- AR side uses a `Discount` item that posts to `690 Withholding Tax on Revenue` (Expense).
- The withholding-receivable counterpart is `14020 Withholding Tax Receivable` if Wego will recover it, or it stays as a permanent expense if non-recoverable.

> Customer-WHT certificates need to be received and tracked outside NetSuite — see Sally Aljary's process.

---

## 9. Statutory & period reporting

### Per-subsidiary filing cadence

| Subsidiary | Filing | Cadence |
|---|---|---|
| Wego SG | GST return | Quarterly |
| Wego ME / FZ-LLC / ShopCash FZ / ME T&T | UAE VAT return | Quarterly |
| WeGo Saudi | KSA VAT (ZATCA) | Monthly |
| Wego India | GST + TDS | Monthly (GSTR-1, GSTR-3B, TDS) |
| WegoPro Egypt / Wego Travel SAE | EG VAT | Monthly |
| Wego Indonesia | PPN + PPh | Monthly |
| Wego Malaysia | SST | Bi-monthly |
| Wego Pakistan | PK VAT (FBR) | Monthly |

> Cadences above are typical-jurisdiction defaults. Confirm Wego-specific filing schedule with the tax team / Li Ping for any sub. [Gap §12]

### Tax filing reconciliation worksheet

Each month: tax preparer (or Li Ping team) exports per-jurisdiction transactions and reconciles:

1. Output VAT/GST per sub (26020 / 26022 / 26024 / 26026 / 26028 / 26030 / 26032 / 26087 / 26089) → matches sales report.
2. Input VAT/GST per sub (1401010-1401091) → matches purchase report.
3. Net = output − input → matches return line.
4. WHT (TDS / PPH) → matches statutory schedule before payment.

> Saved searches for these are owned by GC; need to be inventoried. [Gap §12]

### E-invoicing (current state)

- **KSA (ZATCA Phase 2):** integration likely required; confirm current state with Akansha / GC. Phase 1 was generally deployed; Phase 2 is the API-to-ZATCA real-time clearance phase. Status in Wego: TBD. [Gap §12]
- **India (e-invoicing IRP):** required for B2B above ₹5 cr aggregate turnover. Confirm Wego India's threshold and integration. [Gap §12]
- **Egypt (ETA):** real-time e-invoicing required; confirm WegoPro Egypt and Wego Travel SAE compliance. [Gap §12]
- **UAE:** e-invoicing mandate phased rollout (mid-2026 per FTA roadmap); confirm Wego ME / FZ readiness.
- **Singapore (InvoiceNow / Peppol):** voluntary today; mandate phasing in. Confirm Wego SG plans.

---

## 10. Do-Not-Answer List (escalate only)

In PROD these are extra-sensitive — never propose without sign-off:

- New tax code creation → tax team + GC
- Tax rate change for a jurisdiction → tax team + Li Ping
- Tax-map row additions / changes → GC only
- TDS section assignment for an unusual vendor type → tax team
- PPH section assignment dispute → tax team (Indonesia)
- KSA `26032` / `26081` / `26089` split decision → Li Ping + tax team
- Customer-WHT certificate handling → Sally + tax team
- E-invoicing integration changes (ZATCA, IRP, ETA) → Akansha + GC + tax team
- Period-close tax reconciliation deltas > materiality → Li Ping
- Treatment for B2B/B2C OTA output VAT presentation (income vs liability accounts 4501070 / 4502050 vs 26022/26032) → Li Ping
- Deferred tax recognition / impairment → external auditors + Li Ping
- Tax registration changes (new TRN, new VAT reg) → tax team
- Cross-border services (135 / 195 / Reverse-charge) → tax team

---

## 11. Useful SuiteQL (PROD)

### Find a tax-related account by keyword
```sql
SELECT id, acctnumber, accountsearchdisplayname, accttype
FROM account
WHERE (UPPER(accountsearchdisplayname) LIKE '%VAT%'
       OR UPPER(accountsearchdisplayname) LIKE '%GST%'
       OR UPPER(accountsearchdisplayname) LIKE '%WITHHOLD%'
       OR UPPER(accountsearchdisplayname) LIKE '%TAX%')
AND isinactive = 'F'
ORDER BY accttype, acctnumber;
```

### List all output VAT accounts
```sql
SELECT id, acctnumber, accountsearchdisplayname
FROM account
WHERE accttype = 'OthCurrLiab'
AND acctnumber LIKE '260%'
AND isinactive = 'F'
ORDER BY acctnumber;
```

### List all input VAT accounts
```sql
SELECT id, acctnumber, accountsearchdisplayname
FROM account
WHERE accttype = 'OthCurrAsset'
AND acctnumber LIKE '1401%'
AND isinactive = 'F'
ORDER BY acctnumber;
```

### List India TDS / WHT accounts
```sql
SELECT id, acctnumber, accountsearchdisplayname
FROM account
WHERE acctnumber LIKE '20008%'
AND isinactive = 'F'
ORDER BY acctnumber;
```

> `transaction` is not exposed in PROD, so for actual filing-period extracts (e.g., "all VAT-coded invoices in March 2026") use NetSuite UI saved searches or REST `get_record` per invoice. Long-term: request `transaction` access via GC.

---

## 12. Known gaps (TBD)

- [ ] Confirm KSA VAT account split: `26032` vs `26081` vs `26089` — when does each apply?
- [ ] Confirm Pakistan VAT model (`26087` / `1401090`) — provincial vs federal
- [ ] Confirm whether `26016 GST/VAT Output` (generic) is still in active use or legacy
- [ ] Confirm if `140 GST/VAT Input & Other Tax refund` (id=1896) is legacy alongside 1401010-1401091
- [ ] Why are Indonesia PPH accounts (2000812-2000814) not `_TO IA`-branded while India TDS (2000802-2000811) is?
- [ ] B2C OTA output VAT presented as income (4501070 / 4502050) — confirm month-end JE that moves these to liability accounts
- [ ] DTS/DTR accounts only exist for IN and PK — gap or by design for other subs?
- [ ] Two income tax expense accounts (5070001_TO IA vs 99010) — when each is used
- [ ] Saved-search IDs for monthly tax filing reconciliation per sub
- [ ] Filing cadence by subsidiary (currently estimated from jurisdiction defaults)
- [ ] E-invoicing status: KSA ZATCA Phase 2, India IRP, Egypt ETA, UAE FTA, SG InvoiceNow
- [ ] Tax-map custom record (`customrecord_cus_entity_tax_map`) read access — currently GC-only
- [ ] WHT rate matrix per Indonesia PPh section + per India TDS section
- [ ] Customer-WHT certificate inventory & tracking (currently outside NetSuite)
- [ ] Reverse-charge handling for cross-border services into UAE / KSA / SG

---

## 13. Revision log

| Date | Author | Change |
|---|---|---|
| 2026-04-28 | Akansha + Claude | First PROD-grounded draft. Sourced live from `mcp__netsuite-prod__run_suiteql` (62 tax-related accounts across `OthCurrLiab`, `OthCurrAsset`, `OthAsset`, `Expense`, `Income`, `LongTermLiab`, `OthExpense`). Flagged: KSA account split, naming inconsistency between India TDS and Indonesia PPH, OTA B2C VAT presented as income, two CIT expense accounts. |

---

## 14. Related

- `prod/ar_operations.md` — Output tax on AR, customer-WHT
- `prod/ap_operations.md` — Input tax on AP, vendor TDS / PPH
- `prod/gl_reporting.md` — Chart of accounts overview
- `sbx/tax_reporting.md` — Sandbox equivalent
- Skill: `intercompany-balance-investigation` — when DTS/DTR balances drift