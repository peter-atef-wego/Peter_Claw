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
title: General Ledger & Reporting — Wego NetSuite PRODUCTION
maintainer: Akansha Singh (akansha@wego.com)
owners: Akansha Singh, Peter Atef
last_updated: 2026-04-28
next_review: 2026-05-12
source_doc: prod/gl_reporting.md (rewrite blending #proj-finance-segment-allocation Slack + live PROD pulls)
project: NetSuite OpenClaw
environment: PRODUCTION (account 5564218)
primary_sources:
  - Slack: #proj-finance-segment-allocation, #payments-reconciliation, #finance-fx-cashflow-treasury, #finance-leadership, #finance-tech, #payments-finance
  - mcp__netsuite-prod__run_suiteql (live PROD pulls 2026-04-24 → 2026-04-28)
  - Sang Le (Data Engineering) — monthly NetSuite files for Flights/Hotels GMV
  - Li Ping (Finance Director) — segment owner
  - Mimi (HR/Payroll) — payroll segment allocation in Payroll2u
---

# General Ledger & Reporting — Wego NetSuite PROD

Authoritative reference for Wego's **production** General Ledger, chart of accounts, segment booking conventions, JE workflows, and reporting cadence. All numeric data was pulled live via `mcp__netsuite-prod__run_suiteql` against account **5564218** on 2026-04-28. Process context is sourced from `#proj-finance-segment-allocation` and adjacent Slack channels.

> **Sister doc:** `references/sbx/gl_reporting.md` covers the sandbox environment. Do not quote sandbox numbers as production facts.

## 0. Agent operating rules

1. **Production only.** This doc reflects live PROD. For sandbox, switch to `references/sbx/gl_reporting.md`.
2. **5-segment booking is enforced.** Every P&L posting carries Account + Department + BU code (Classification) + Product Segment + Market Segment. See §3 — this is the authoritative convention for AP, AR, JE, Advanced IC JE, and amortization JEs.
3. **Real GL impact.** Posting actions touch live books — never propose write actions without Li Ping sign-off.
4. **Cite the section + environment** — end with `[GL §X / prod]`.
5. **Use SuiteQL** for live lookups (templates in §19); use REST `get_record` for transaction-level lookups since `transaction` table is not exposed.
6. **Flag gaps** — §22 lists known unknowns; say "I don't have that yet."

> **PROD SuiteQL constraint:** the read-only role wired to `netsuite-prod` does **not** expose the `transaction`, `accountingperiod`, `customrecordtype`, or `customsegment` system tables (returns `Record was not found`). Period-close, segment-record metadata, and transaction-level queries must go through REST `get_record` or NetSuite UI saved searches. Long-term action: ask GC to grant `transaction` + `accountingperiod` access to this role.

---

## 1. Team & escalation

### Owners by area

| Area | Name | Use for |
|---|---|---|
| Finance Director | Li Ping | Segment design, GL mapping changes, period reopens, consolidated reporting |
| AR Lead | Sally Aljary | AR-side GL postings, customer write-offs |
| AP Lead | Nurul Ain | AP-side GL postings, vendor JE approval |
| Treasury / FX | Cecilia Tong (CFO) | FX rate source, treasury allocation files |
| Payroll segments | Mimi | Payroll2u — entity + Department/BU code allocation per employee |
| Manpower allocation | Svetlana | Manpower budget allocation file (entity × Department × BU) |
| Data Engineering — NetSuite files | Sang Le | Monthly GMV NetSuite files (Flights/Hotels), GDS Incentive, segment aggregations |
| Data Engineering — automation | Sheng Xiong Quek | Segment list automation, aggregation scripts |
| BU/segment data feeds | Hansel Baro | Cross-team coordination on segment work |
| Reconciliation automation | Peter Dalmia, Harshal Patankar | Payment gateway recon → NetSuite |
| SuiteScript / mappings | GC (external, handover 2026-03-30) | CoA changes, custom record updates, saved searches |
| Project lead | Akansha Singh | OpenClaw automation; chart-of-account questions; this doc |
| Project co-lead | Peter Atef | OpenClaw automation; integration work |

### Slack channels (GL-relevant)

| Channel | Purpose |
|---|---|
| `#proj-finance-segment-allocation` | **Primary GL/segment work.** Li Ping ↔ Sang Le ↔ Sheng Xiong on the 5-segment list; monthly NetSuite GMV files (Flights / Hotels / Cancellation / COGS); GDS Incentive aggregation; Mimi's payroll segment fields. |
| `#finance-leadership` | Li Ping, Cecilia Tong — close-period decisions |
| `#finance-tech` | Finance automation tools / RPA / NetSuite tech |
| `#finance-fx-cashflow-treasury` | FX rate sourcing, cashflow, treasury allocation |
| `#payments-finance` | Payments ↔ finance interface (gateway settlements, recon files) |
| `#payments-reconciliation` | Active recon-automation work — Alexandre Morin (Payments) ↔ Peter Dalmia ↔ Harshal Patankar; gateway file formats; crypto payments rollout (Feb 2026) |
| `#netsuite_ar`, `#netsuite_ap`, `#netsuite_adminsupport` | Sub-ledger questions that may roll up to GL |
| `#finance-automation-claw`, `#data-automations-bow-finance` | OpenClaw automation scope |

### Escalation ladder

1. Single-sub posting issue → relevant sub-ledger lead (Sally for AR, Nurul Ain for AP).
2. Cross-sub or segment booking issue → Li Ping (`#proj-finance-segment-allocation`).
3. CoA / custom segment / saved-search change → GC + Akansha + Peter.
4. FX rate, period reopen, consolidation diff → Li Ping → Cecilia Tong (CFO).

---

## 2. Subsidiaries & currencies (live PROD)

PROD has **16 active operating subsidiaries + 3 elimination subsidiaries**. Same shape as SBX.

| Sub ID | Subsidiary | Country | Currency (`subsidiary.currency` id) | Type |
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

**Currency id legend (live `currency` table):** `1=USD, 4=EUR, 5=INR, 7=EGP, 8=IDR, 9=SAR, 10=AED, 11=SGD, 16=MYR, 25=AUD, 59=GBP, 77=JPY, 83=KWD, 115=PKR.`

> **PROD anomaly to verify:** `subsidiary.currency` for SG-country subsidiaries (1, 3, 11, 15, 16, 27, 31) returns **id=1** (USD), not id=11 (SGD). Likely a functional vs. transaction currency nuance. **Confirm with Li Ping / Peter.** [Gap §22]

---

## 3. The 5-segment booking convention (authoritative)

From `#proj-finance-segment-allocation` (Li Ping, 2025-01-22 → 2026-01-23 Jan26 segment list):

> "We have opened the segments fields in NetSuite and would need to book **3 segments in all P/L transactions i.e. account code, department, BU code** for a start in Jan 2025 until we are able to automate the allocation files to show **all 5 segments**."

**Current PROD state (2026-04):** the 5 segments below are all live in PROD and required on every P&L line.

| # | Segment | NetSuite field | Source table | What it captures |
|---|---|---|---|---|
| 1 | **Account code** | `Account` | `account` (516 active) | The GL bucket (e.g., `4501010 OTA Flights`, `6101010 COS-Staff Salaries`) |
| 2 | **Department** | `Department` | `department` (20 active) | Functional team (e.g., Software Engineering, Finance, Marketing-Performance) |
| 3 | **BU code** | `Classification` | `classification` (15 active) | Business unit / product line (e.g., Flights Marketplace, Hotel Bookings) |
| 4 | **Product Segment** | (custom segment) | `customsegment` — **not exposed via SuiteQL** | Product-level dimension on top of BU |
| 5 | **Market Segment** | (custom segment) | `customsegment` — **not exposed via SuiteQL** | Geographic / market-level dimension |

> Product Segment + Market Segment are custom segments. Their internal IDs and value lists are **not retrievable via SuiteQL** in this PROD role (`Record 'customsegment' was not found`). Reach into the NetSuite UI (`Customization > Lists, Records, & Fields > Custom Segments`) or ask GC for the value list. [Gap §22]

### Where the 5 segments are required

- AP — Vendor Bill, Vendor Credit, Bill Payment posting (see `prod/ap_operations.md` §7)
- AR — Customer Invoice, Customer Payment, Credit Memo
- GL — every P&L line on Make Journal Entries
- IC — every line on Make Advanced Intercompany Journal Entries
- Amortization — schedule template carries segments forward

### Where the 5 segments are **not** required

- Balance-sheet-only postings (e.g., reclass between two cash accounts in the same sub).
- Investment-in-subsidiary (IIS) postings — equity-only.

---

## 4. Departments (live PROD — 20 active)

| ID | Department |
|---:|---|
| 27 | Admin & IT Support (Office Infra/General) |
| 20 | COD (Cost of Delivery) |
| 17 | COS (Cost of Sales) |
| 28 | Common |
| 25 | Corporate Services |
| 9 | Customer Service |
| 11 | Data Engineering & Analytics |
| 22 | Design Marketing |
| 23 | Design UX |
| 26 | Finance |
| 2 | Human Resource |
| 4 | Management (CEO Office) |
| 18 | Marketing-Brand |
| 21 | Marketing-Performance |
| 8 | Media Solutions |
| 19 | OH (Overhead) |
| 10 | Product Management |
| 6 | Sales/Commercial/Customer Success |
| 5 | Software Engineering |
| 24 | System Operations |

> The Department dimension cleanly maps to the major P&L families:
> - `61xxxxx COS-Staff` → Department = COS / Software Engineering / Data Engineering / Customer Service
> - `71xxxxx COD-Staff` → Department = COD
> - `81xxxxx OH-Staff` / `8101010 Director` → Department = OH / Management
> - Marketing → Marketing-Brand / Marketing-Performance
> - Admin → Admin & IT Support / Corporate Services

---

## 5. BU codes / Classifications (live PROD — 15 active)

| ID | BU code (Classification) |
|---:|---|
| 1 | Flights Marketplace |
| 2 | Flights Ad Units |
| 3 | Hotels Marketplace |
| 4 | Hotels Ad Units |
| 5 | Ads Onsite |
| 6 | Ads Offsite |
| 7 | Audience Data |
| 8 | Flight Bookings (Full Fees) |
| 9 | Hotel Bookings |
| 10 | Subscription-Expense Management |
| 12 | Coupons |
| 14 | Affiliate Commission |
| 15 | Travel Insurance |
| 20 | Shared (to be allocated) |
| 101 | Anciliaries |

> **`20 Shared (to be allocated)`** is the holding bucket for costs that aren't yet split — e.g., shared SG infra before Cecilia's manpower allocation file runs. Postings to this BU should resolve to a real BU after the allocation cycle.
>
> **Note:** the Slack thread (Li Ping → Svetlana, 2025-01-22) calls out that **Cecilia Tong's manpower budget allocation file** is the input that splits Shared cost across BUs based on budgeted revenue per BU.

---

## 6. Locations (live PROD — 2 active)

| ID | Location |
|---:|---|
| 1 | Bangalore |
| 2 | Mumbai |

> **Anomaly:** the `location` dimension is currently populated for **India only**. All other subsidiaries do not use the Location field (PROD return is empty for SG/ME/EG/SA/etc.). Likely an India-only payroll/office requirement that didn't get extended to other subs. **Confirm with Li Ping whether Location should be opened up across all subs or whether it's intentionally India-scoped.** [Gap §22]

---

## 7. Chart of accounts at a glance (live PROD)

PROD has **716 active accounts** across 19 NetSuite account types:

| accttype | Active count | Used for |
|---|---:|---|
| `AcctPay` | 7 | AP control accounts (see `prod/ap_operations.md` §4) |
| `AcctRec` | 7 | AR control accounts (see `prod/ar_operations.md`) |
| `Bank` | 87 | All bank/cash accounts across 14 active-AP subs (see §13) |
| `COGS` | 84 | Cost of revenue / cost of sales lines (§9) |
| `DeferExpense` | 3 | Prepaid expense holding accounts (`_TO IA`-branded) |
| `DeferRevenue` | 4 | Prepaid revenue / contingent revenue / refundable deposits |
| `Equity` | 14 | Share capital, retained earnings, reserves (§12) |
| `Expense` | 133 | All operating expense lines (§10) — overwhelmingly `_TO IA`-branded |
| `FixedAsset` | 16 | PP&E + intangibles + ROU + accumulated depn (§14) |
| `Income` | 89 | Revenue lines — Metasearch, OTA, WegoPro, WegoBeds, Ads, Cashback, Coupons (§8) |
| `LongTermLiab` | 5 | LT loans, deferred tax liability, employee benefit liability |
| `NonPosting` | 8 | Statistical / non-posting lines |
| `OthAsset` | 30 | IIS investments, intercompany Due From, "TO IA"-branded other assets |
| `OthCurrAsset` | 93 | Payment-gateway clearing, AR central clearance, prepayments, intercompany DFx, Input VAT (§13) |
| `OthCurrLiab` | 97 | AP central clearance, accruals, employee, output VAT, intercompany DTx (§13) |
| `OthExpense` | 20 | FX losses, interest expense, IT (§11) |
| `OthIncome` | 11 | Interest income, FX gains, government grants (§11) |
| `Stat` | 2 | Statistical accounts |
| `UnbilledRec` | 7 | Revenue accruals (Marketplace, Advertising, GDS Incentive, IATA/PLB, VCC Rebate) |

### SuiteQL: list any account type

```sql
SELECT id, acctnumber, accountsearchdisplayname, accttype, subsidiary
FROM account
WHERE accttype = '<AcctType>' AND isinactive = 'F'
ORDER BY acctnumber;
```

---

## 8. Income / revenue accounts (live PROD — 89 active)

The 4xxxxxx range is the revenue chart. Wego revenue splits into seven product families:

### 8.1 Metasearch revenue (`41xxxxx`)

The original/core Wego marketplace product. Each product line has `Revenue / Revenue - Interco / Revenue - Inter BU` triplet.

| Acct # | Name |
|---|---|
| 4101010 | Flights Metasearch Revenue |
| 4101011 | Flights Metasearch Revenue - Interco |
| 4101012 | Flights Metasearch Revenue - Inter BU |
| 4101020 | Hotels Metasearch Revenue |
| 4101021 | Hotels Metasearch Revenue - Interco |
| 4101022 | Hotels Metasearch Revenue - Inter BU |
| 4101030 | Other Metasearch Revenue |
| 4101031 | Other Metasearch Revenue - Interco |
| 4101032 | Other Metasearch Revenue - Inter BU |
| 4102010 | Flights Compare Units |
| 4102020 | Hotels Compare Units |
| 4102030 | Flights Sponsored |
| 4102040 | Hotels Sponsored |
| 4103010 | Flights Meta Rebate |
| 4103020 | Hotels Meta Rebate |
| 4103030 | Flights Compare Units Rebate |
| 4103040 | Hotels Compare Units Rebate |
| 4103050 | Flights Sponsored Rebate |
| 4103060 | Hotels Sponsored Rebate |

### 8.2 Display / advertising (`42xxxxx`)

| Acct # | Name |
|---|---|
| 4201010 | Direct |
| 4201020 | Data partnership |
| 4201050 | Programmatic |
| 4202010 | Co-Marketing Revenue |

### 8.3 WegoPro Subscription (`43xxx`)

| Acct # | Name |
|---|---|
| 43010 | WegoPro Expense Management Subscription & Other Revenue |

### 8.4 ShopCash / Cashback (`44xxxxx`)

| Acct # | Name |
|---|---|
| 4401010 | Cashback |
| 4401020 | Coupons |
| 4401030 | Bonus |
| 4401040 | Gift Cards |

### 8.5 OTA Agency Model — primary booking revenue (`45xxxxx`)

These are the GMV-driven revenue lines that Sang Le's monthly NetSuite files populate.

| Acct # | Name |
|---|---|
| 4501010 | OTA Flights |
| 4501011 | OTA Flights - interco |
| 4501020 | OTA Flights Service Fee |
| 4501050 | OTA Flights Insurance |
| 4501051 | OTA Flights Insurance - interco |
| 4501060 | OTA Flights Discount |
| 4501070 | OTA Flights (B2C) Output VAT |
| 4502010 | OTA Hotels |
| 4502011 | OTA Hotels - interco |
| 4502020 | OTA Hotels Discount |
| 4502030 | OTA Hotels Commission |
| 4502040 | OTA Hotels Service Fee |
| 4502050 | OTA Hotels (B2C) Output VAT |
| 4504010 | WegoPro Flights |
| 4504020 | WegoPro Flights Service Fee |
| 4504030 | WegoPro Flights Insurance |
| 4504050 | WegoPro Other Ancillaries |
| 4504110 | WegoPro Hotels |
| 4504120 | WegoPro Hotels Service Fee |
| 4504210 | WegoBeds Hotels |
| 45090 | Sales GMV Realised Exchange Gain/loss |

### 8.6 OTA Agency Model — supplier costs (`455xxxx`)

These are paired with the revenue lines above (Sang Le's GMV COGS files).

| Acct # | Name |
|---|---|
| 4551010 | OTA Flights Supplier Costs |
| 4551011 | OTA Flights Supplier Costs - interco |
| 4551020 | OTA Insurance Costs |
| 4551021 | OTA Insurance Costs - interco |
| 4552010 | OTA Hotels Supplier Costs |
| 4552011 | OTA Hotels Supplier Costs - interco |
| 4554010 | WegoPro Flights Supplier Costs |
| 4554020 | WegoPro Insurance Costs |
| 4554050 | WegoPro Other Ancillaries Supplier Cost |
| 4554110 | WegoPro Hotels Supplier Costs |
| 4555010 | WegoBeds Hotels Supplier Costs |
| 45590 | COGS GMV Realised Exchange Gain/loss |

### 8.7 OTA Merchant Model (`46xxxxx`)

| Acct # | Name |
|---|---|
| 4601010 | 3rd Party OTA Flight Revenue |
| 4601020 | Interco OTA Flight Revenue |
| 4602010 | 3rd Party OTA Hotels Revenue |
| 4602020 | Interco OTA Hotels Revenue |

### 8.8 Other revenue (`48xxx`)

| Acct # | Name |
|---|---|
| 48010 | Other Revenue - Non interco |
| 48020 | Airport Tax Recovery |
| 48030 | **GDS Incentive** — see Sang Le's `GDS_SEGMENT_INCENTIVE` file (Slack 2024-11-25) |
| 48040 | Performance Linked Bonus (PLB) |
| 48050 | UATP Rebate |
| 48060 | Other Incentive |
| 48070 | Vendor Commission |
| 48080 | Customer support outsource income - Interco |
| 48082 | IT Support outsource income - interco |
| 48083 | Licensing Fee - Interco |

### 8.9 `_TO IA`-branded transfer revenue (`40xxxxx_TO IA`)

These are "transfer of collection on behalf" accounts — the cross-entity collection scheme. **Verify with Li Ping / GC** before using; they're a parallel set tied to a specific consolidation/integration scheme. [Gap §22]

| Acct # | Name |
|---|---|
| 4000103_TO IA | Transfer of collection on behalf - Metasearch |
| 4000205_TO IA | Transfer of collection on behalf - Compare Units |
| 4000307_TO IA | Transfer of collection on behalf - Agency Revenue Disc |
| 4010005_TO IA | Other Incentive |
| 4010006_TO IA | BOW Insurance |
| 4010007_TO IA | Transfer of collection on behalf - Merchant Revenue |
| 4010008_TO_IA | WegoBeds Hotels Revenue |
| 4010009 | WegoPro Flights Revenue (note: stored without `_TO IA` suffix) |
| 4010010_TO_IA | WegoPro Hotels Revenue |
| 4010104_TO IA | Transfer of collection on behalf - Merchant Rev Disc |
| 4020105_TO IA | Transfer of collection on behalf - Display |
| 4030001_TO IA | Services & Licensing Fees |
| 4030003_TO IA | Barter Deal Revenue |
| 4030006_TO IA | Transfer of collection on behalf - Other Revenue |

---

## 9. COGS / cost of revenue (live PROD — 84 active)

### 9.1 Direct media spend (`51xxx`)

| Acct # | Name |
|---|---|
| 51010 | COGS-Media Spend (Direct Clients) |
| 51020 | COGS-Media Spend (Co-Marketing) |
| 51030 | COGS-Media Spend (Rebate) |
| 51040 | COGS-Media Production |
| 51050 | COGS-Barter Deal Expenses |

### 9.2 Inventory pass-through (`52xxxxx, 53xxx, 59xxx`)

| Acct # | Name |
|---|---|
| 5201010 | COGS-Flight inventory-3rd party |
| 5201020 | COGS-Flight inventory-Interco |
| 5202010 | COGS-Hotel inventory-3rd party |
| 5202020 | COGS-Hotel inventory-Interco |
| 53010 | COGS-Licensing Fee - Interco |
| 59090 | COGS-Others-Interco |

### 9.3 COS-Staff (`6101xxx, 61020`)

The "Cost of Sales" people-cost block. Pairs with Department=COS.

| Acct # | Name |
|---|---|
| 6101010 | COS-Staff - Salaries |
| 6101011 | COS-Staff - Bonus |
| 6101012 | COS-Staff -  CPF, SDL & other Provident Fund |
| 6101020 | COS-Staff - Mobile Allowance |
| 6101021 | COS-Staff - Transport allowance |
| 6101022 | COS-Staff - Other benefit |
| 6101030 | COS-Staff - Training & Development |
| 6101032 | COS-Staff - Welfare |
| 6101040 | COS-Employee Insurance |
| 6101050 | COS-Staff - Gratuity Provsion |
| 6101051 | COS-Staff - Unutilised leave provison |
| 6101060 | COS-Agency contract staff |
| 61020 | COS-Staff Commission |

### 9.4 OTA Agency Model — fees (`62xxxxx`)

| Acct # | Name |
|---|---|
| 620 | OTA Agency Model - COS |
| 6201010 | Agency Model-Flight Search Fees-3rd Party |
| 6201020 | Agency Model-Flight Metasearch Fee - Interco |
| 6201021 | Agency Model-Flight Metasearch Fee - Inter BU |
| 6202010 | Agency Model-Hotels Metasearch Fee - 3rd Party |
| 6202020 | Agency Model-Hotels Metasearch Fee - Interco |
| 6202021 | Agency Model-Hotels Metasearch Fee - Inter BU |
| 62030 | Agency Model-Transaction Fees |
| 6203010 | Payment Gateway Fees |
| 6203020 | UATP Fee |
| 6203050 | Others (include Fraud Mgt Fee) |

### 9.5 OTA Merchant Model — fees (`63xxxxx`)

| Acct # | Name |
|---|---|
| 6301010 | Merchant Model -Flight Search Fees_TO IA |
| 6301020 | Merchant Model -Flight Metasearch Fee - Interco |
| 6301030 | Merchant Model -Hotels Metasearch Fee - Interco |

### 9.6 Marketing (`64xxxxx`)

The Performance Marketing chart. Pairs with Department=Marketing-Performance / Marketing-Brand.

| Acct # | Name |
|---|---|
| 6401010 | SEM |
| 6401020 | SEO |
| 6401030 | Display |
| 6402010 | Online |
| 6402020 | Offline |
| 6402030 | Social Media & Experimental |
| 6402040 | Brand Promotion |
| 6402050 | Revenue Sharing |
| 6403010 | Affiliate Marketing commissions |
| 6403020 | Loyalty Expense |
| 6404010 | Apps Marketing (UA/RT) |
| 6404020 | Apps Marketings (Pre-load) |
| 6405010 | Event/Conference Cost |
| 6405020 | Advertisting (sic) |
| 6405030 | Sponsorships |
| 6405040 | PR |
| 6408010 | Marketing Tools and Services |

### 9.7 COD-Staff + COD-Tech (`71xxxxx, 72xxx, 73xxx, 74xxxxx`)

The "Cost of Delivery" block — engineering / hosting / content / customer support.

| Acct # | Name |
|---|---|
| 7101010 | COD-Staff - Salaries |
| 7101011 | COD-Staff - Bonus |
| 7101012 | COD-Staff -  CPF, SDL & other Provident Fund |
| 7101020 | COD-Staff - Mobile Allowance |
| 7101021 | COD-Staff - Transport allowance |
| 7101022 | COD-Staff - Other benefit |
| 7101030 | COD-Staff - Training & Development |
| 7101032 | COD-Staff - Welfare |
| 7101040 | COD-Employee Insurance |
| 7101050 | COD-Staff - Gratuity Provsion |
| 7101051 | COD-Staff - Unutilised leave provison |
| 7101060 | COD-Agency contract staff |
| 72010 | Content Delivery Network |
| 72020 | Hosting & Storage |
| 72030 | Domain Registration |
| 73010 | Content and licensing |
| 7401010 | Customer support outsource expense - Interco |
| 7401020 | Customer support outsource expense - 3rd Party |
| 7402010 | IT support - Interco |
| 7402020 | IT support - 3rd Party |
| 7403010 | COD-Software Subscription |

---

## 10. Operating expense (live PROD — 133 active)

The 5xxxxxx_TO IA / 8xxxxxx / 9xxxxxx ranges. Highlights below — full list is queryable via §19.

### 10.1 OH-Staff & Director (`81xxxxx, 8103xxx`)

| Acct # | Name |
|---|---|
| 8101010 | Director - Salaries |
| 8101011 | Director - Bonus |
| 8101012 | Director - CPF, SDL & Other Provident Fund |
| 8101013 | Director - Other Benefit (housing) |
| 8102010 | OH-Staff - Salaries |
| 8102011 | OH-Staff - Bonus |
| 8102012 | OH-Staff -  CPF, SDL & other Provident Fund |
| 8102020 | OH-Staff - Mobile Allowance |
| 8102021 | OH-Staff - Transport allowance |
| 8102022 | OH-Staff - Other benefit |
| 8102030 | OH-Staff - Training & Development |
| 8102032 | OH-Staff - Welfare |
| 8102040 | OH-Employee Insurance |
| 8102050 | OH-Staff - Gratuity Provsion |
| 8102051 | OH-Staff - Unutilised leave provison |
| 8102060 | OH-Agency contract staff |
| 8103010 | Employee Share Scheme |
| 8103020 | Employee work visa/permit fees |
| 8103030 | Recruitment expenses |
| 8103040 | Retrenchment cost |

### 10.2 Bank, office, professional, travel (`82xxxxxx, 83xxxxx, 84xxxxxx, 85xxxxxx, 86xxxxxx`)

| Acct # | Name |
|---|---|
| 8201010 | Bank Charges |
| 8201025 | Donations |
| 8201026 | Dues & subscriptions |
| 8201050 | Penalty / Late Payment Fees |
| 8201090 | Other Admin Expenses |
| 8301010 | Brokerage & Commissions |
| 8301020 | Office - Cleaning and Maintenance |
| 8301021 | Office - Insurance |
| 8301022 | Office - Rental |
| 8301023 | Office - Other Building Charges |
| 8301030 | Utilities |
| 8301040 | Reinstatement cost |
| 8302010 | Printing and Stationery |
| 8302020 | Other office Supplies |
| 8401010 | Internet Access |
| 8401020 | Leaseline Expenses |
| 8401030 | Telephone |
| 8402010 | Low Value Assets Purchase |
| 8402020 | Short-term Hardware rental |
| 8402030 | Software Subscription |
| 8501010 | Audit fees |
| 8501011 | Accounting fees |
| 8501012 | Corporate Secretary service fees |
| 8501013 | Tax service fees |
| 8502010 | Legal advisory fees |
| 8502020 | Consultancy service fees |
| 8502030 | Professional Employer Organisation Service Fees |
| 8502040 | Other professional service |
| 8601010 | Travel - Entertainment & Gifts |
| 8601020 | Travel - Flights related cost |
| 8601030 | Travel - Hotels related cost |
| 8601040 | Travel - Land transport cost |
| 8601050 | Travel - Roaming and IDD cost |
| 8601060 | Travel - Others |
| 8602010 | Bad Debt Written Off |
| 8602011 | Bad Debt Provision |
| 8602110 | AR Insurance |
| 8603010 | License fees |

### 10.3 Depreciation & Amortisation (`87xxxxx`)

| Acct # | Name |
|---|---|
| 8701010 | Depreciation of Computer Software & Hardware |
| 8701020 | Depreciation of Furniture & Fixtures |
| 8701030 | Depreciation of Leasehold Improvements |
| 8701040 | Depreciation of Office Equipment |
| 8701090 | Depreciation of Right-of-use asset |
| 8702010 | Amortisation - Internet Domain |
| 8702020 | Amortisation - Trademarks |
| 8702030 | Amortisation - Technology Development |

### 10.4 `_TO IA`-branded operating expense (`50xxxxx_TO IA`)

PROD has 50+ `_TO IA`-branded expense accounts mirroring the marketing / content / G&A / employee / travel / tax chart. They represent the "Transfer of payment on behalf" scheme for cross-entity expense. Examples:

| Acct # | Name |
|---|---|
| 5010101_TO IA | SEM |
| 5010201_TO IA | Online (marketing) |
| 5020201_TO IA | Hotel Review and Rating Data |
| 5030102_TO IA | Board Meeting Charges |
| 5030204_TO IA | Director - SDL |
| 5030205_TO IA | Employee Benefits - Key Management |
| 5030604_TO IA | Travel - Meals |
| 5030701_TO IA | Bad Debt |
| 5070001_TO IA | Income Tax expenses |

The pattern `_TO IA` = **Transfer of payment On behalf — InterAccount**. Postings on these accounts are part of the cross-entity settlement scheme where one sub pays on behalf of another. **Pair every TO IA expense post with a counterparty TO IA payable** (`2000201_TO IA Commercial Payables` and similar).

### 10.5 Withholding Tax on Revenue (`690`)

| Acct # | Name |
|---|---|
| 690 | Withholding Tax on Revenue |

---

## 11. Other Income / Other Expense (live PROD)

### 11.1 Other Income (`OthIncome` — 11 active)

| Acct # | Name |
|---|---|
| 49010 | Bad Debts Recovered |
| 49020 | Government Grant/Subsidy |
| 49030 | Interest Income |
| 49080 | Miscellaneous Income |
| 49090 | Other Income - Interco |
| 4040001_TO IA | Fixed Deposit Interest |
| 4040003_TO IA | Transfer of Payment on behalf - Finance related income |
| 4050004_TO IA | Transfer of payment on behalf - Other income |
| 4060001_TO IA | Gain from Sales of Fixed Assets |
| 4060002_TO IA | Unrealized Foreign Exchange Gain |
| 4060003_TO IA | Exchange Gain |

### 11.2 Other Expense (`OthExpense` — 20 active)

| Acct # | Name |
|---|---|
| 91010 | (Gain)/Loss on Disposal of Fixed Assets |
| 91020 | (Gain)/Loss on Foreign Exchange - Realized |
| 91021 | (Gain)/Loss on Foreign Exchange - Unrealized |
| 91080 | Rounding Gain/Loss (sys) |
| 91081 | Unrealized Matching Gain/Loss (sys) |
| 92010 | Miscellaneous Expense |
| 92090 | Other Expense - Interco |
| 93010 | Interest Expense |
| 93020 | Interest expense - Lease Liability |
| 9401010 | Legal and professional fee |
| 9401020 | Valuation and PPA fee |
| 9401030 | Due Diligence fees |
| 95010 | Provision for Impairment on Investment |
| 95020 | (Gain)/Loss on Disposal of Investment |
| 99010 | Income Tax expenses |
| 5040002_TO IA | Unrealized Foreign Exchange Loss |
| 5040003_TO IA | Exchange Loss |
| 5040008_TO IA | Transfer of payment on behalf - Other Losses |
| 5050001_TO IA | Fixed Assets Write Off |
| 5050004_TO IA | Transfer of payment on behalf - Other Non-Oper. Exp |

> **FX accounts pairing:** `91020 / 91021` are the Realized / Unrealized FX P&L accounts produced by NetSuite's revaluation engine. `4060002_TO IA / 4060003_TO IA / 5040002_TO IA / 5040003_TO IA` are the matching `_TO IA`-scheme entries for cross-entity FX. **Confirm which set is authoritative for consolidated reporting** — this is a `#finance-fx-cashflow-treasury` topic. [Gap §22]

---

## 12. Equity (live PROD — 14 active)

| Acct # | Name |
|---|---|
| 31010 | Ordinary Share Capital |
| 31020 | Preference Share Capital |
| 31030 | Treasury Shares |
| 31040 | Convertible Preference Share |
| 32010 | Retained Earnings |
| 32020 | Net profit/(loss) for the year |
| 33010 | Capital Reserve |
| 33020 | Share Plan Reserve |
| 33030 | Translation Reserve |
| 33040 | Revaluation Reserve |
| 33090 | Opening Balance (Sys) |
| 33092 | Cumulative Translation Adjustment (Sys) |
| 33093 | Cumulative Translation Adjustment-Elimination (Sys) |
| 3000302_TO IA | Defined Benefit Plans |

> `33092` and `33093` are NetSuite-system-generated CTA accounts produced by consolidation. Don't post to them directly. `33090` is system-generated opening balance; only the historical conversion JE touches it.

---

## 13. Intercompany scheme & payment-gateway clearing

### 13.1 Intercompany account families

| Family | Side | accttype | Examples (PROD) |
|---|---|---|---|
| **DFH** Due From - Holdings | Asset | OthAsset | (per-counterparty 1410xxx) |
| **DFS** Due From - Subsidiaries | Asset | OthAsset / OthCurrAsset | (per-counterparty) |
| **DFR** Due From - Related | Asset | OthCurrAsset | (per-counterparty) |
| **DTH** Due To - Holdings | Liability | LongTermLiab / OthCurrLiab | (per-counterparty) |
| **DTS** Due To - Subsidiaries | Liability | OthCurrLiab | (per-counterparty) |
| **DTR** Due To - Related | Liability | OthCurrLiab | (per-counterparty) |
| **IIS** Investment In Subsidiaries | Asset | OthAsset | Per-sub investment cost + impairment pair |

The 6-family DFx / DTx scheme is the live IC accounting model. Every IC posting goes through Advanced Intercompany JE (see `prod/ap_operations.md` §11) which posts the sub-A side to `DFx` and the sub-B side to `DTx`. **Elimination subs (15, 16, 31)** net the pair to zero on consolidation.

> **`_TO IA`-branded IC scheme runs in parallel** — `2000201_TO IA Commercial Payables_TO IA` (id=1047), `4000103_TO IA Transfer of collection`, `5000103_TO IA Transfer of payment`, etc. **This is a separate scheme.** Confirm with Li Ping / GC the boundary between DFx/DTx and `_TO IA` postings before doing IC analysis. [Gap §22]

### 13.2 Payment-gateway clearing (`OthCurrAsset` — partial list)

PROD has 93 OthCurrAsset accounts. The payment gateway clearing accounts split per gateway × currency:

| Gateway | Currencies in PROD |
|---|---|
| **APISO** | 8 currencies (cross-currency clearing) |
| **NIUM** | Multi-currency |
| **Revolut** | Multi-currency |
| **PayPal** | Multi-currency |
| **Checkout** | Multi-currency |
| **UATP** | USD-based |

Pair with: AR Central Clearance per currency (AED, EGP, INR, PKR, SAR, USD) on `OthCurrAsset`; AP Central Clearance per currency on `OthCurrLiab` — see `prod/ap_operations.md` §4.

> Active recon-automation work in `#payments-reconciliation`: Alexandre Morin (Payments) is sharing settlement file samples → Peter Dalmia / Harshal Patankar map them to NetSuite. **Crypto Payments rollout (Feb 2026)** added a new gateway-side recon stream.

### 13.3 Bank accounts (87 active)

See `prod/ap_operations.md` §5 for the per-subsidiary primary bank table. Key facts:
- 14 active-AP subs span DBS, Citibank (SG/ME/IN), HSBC (SG/FZ/IN), ADCB (FZ — H2H), ANB/SABB (KSA), Attijariwafa/CIB/NBE (EG), BCA (ID), Meezan/MCB (PK).
- Cross-FX gateways: MONFX, Western Union, Transfermate, SingX.
- Fixed deposits `1000201–1000205` ("TO IA" prefixed) for Axis IN, Citibank SG, Samba USD, Samba AED, ADCB AED. Plus `1121020 Fixed Deposit - DBS Bank India`.

---

## 14. Fixed Assets (live PROD — 16 active)

Cost-and-accumulated-depreciation pairs:

| Cost acct | Accum depn / amort acct | Asset class |
|---|---|---|
| 1901010 Computer Software & Hardwares at Cost | 1901011 Accumulated Depreciation | IT hardware/software |
| 1902010 Furniture & Fixtures at Cost | 1902011 Accumulated Depreciation | F&F |
| 1903010 Leasehold Improvements at Cost | 1903011 Accumulated Depreciation | Leasehold |
| 1904010 Office Equipment at Cost | 1904011 Accumulated Depreciation | Office |
| 1909010 Right-of-use asset at PV | 1909011 Accumulated Depreciation - ROU | IFRS 16 ROU |
| 1951010 Internet Domain at Cost | 1951011 Accumulated Amortisation | Domain (intangible) |
| 1952010 Trademarks & Licenses at Cost | 1952011 Accumulated Amortisation | Trademarks (intangible) |
| 1953010 Website Development at Cost | 1953011 Accumulated Amortisation | Website dev (intangible) |

Depreciation/amortisation P&L accounts: see §10.3.

---

## 15. Unbilled Receivables — revenue accruals (live PROD — 7 active)

| Acct # | Name |
|---|---|
| 1221010 | Revenue Accrual - Marketplace |
| 1221011 | Revenue Accrual - Advertising & Co-marketing |
| 1221030 | Revenue Accrual - Affliates (sic) |
| 1222010 | GDS Incentive Accrual |
| 1222020 | Supplier Commission (IATA/PLB) |
| 1222030 | Marketing Fee (Rev share) |
| 1222040 | VCC Rebate |

> These pair with `48030 GDS Incentive`, `48040 PLB`, `48070 Vendor Commission`, etc. on the income side. Sang Le's monthly NetSuite files (Slack, 2024-11-25 → 2025-04-21) drive the GDS Incentive recognition. VCC Rebate flow has a known timing issue: insurance commissions arrive ~3 days after flight booking due to Wenrix optimization (Sang Le, 2024-12-30) — this drives a separate schedule rather than a single accrual.

---

## 16. JE workflows in PROD

### 16.1 Single-subsidiary Journal Entry

**Navigation:** `Transactions > Financial > Make Journal Entries`

- See `prod/ap_operations.md` §10 for the AP-side template.
- Same shape applies for revenue corrections, accruals, FX revaluation manual posts, and equity moves.
- 5 segments required on every P&L line.

### 16.2 Advanced Intercompany Journal Entry

**Navigation:** `Transactions > Financial > Make Advanced Intercompany Journal Entries`

- See `prod/ap_operations.md` §11 for the full template.
- Used for cross-subsidiary postings (DFx/DTx scheme; IIS impairments; recharges).

### 16.3 Amortization Journal

**Navigation:** `Transactions > Financial > Create Amortization Journal Entries`

- See `prod/ap_operations.md` §14.
- Recognises prepaid expenses; schedules attached at original bill / item-level.
- Schedules carry the original line's segments forward — verify via REST `get_record` if a recognition lands without segments.

### 16.4 Monthly close inputs (`#proj-finance-segment-allocation` cadence)

The recurring inputs Li Ping consumes for close:

| Input | Owner | Cadence | Source / GDrive |
|---|---|---|---|
| Flights GMV NS files (Sales Booking / Cancellation / COGS / Exchange) | Sang Le | Monthly | Drive folder per month, e.g., `2024-11-25_Flights_NS_Files` |
| Hotels GMV NS files (Sales Booking / Cancellation / COGS / Marketing Fee) | Sang Le | Monthly | Drive folder per month |
| GDS Incentive (segment) | Sang Le | Monthly | `GDS_SEGMENT_INCENTIVE` sheet |
| Aggregated by payment currency code | Sang Le | Monthly | "files aggregated by payment currency code" (Slack 2025-04-21) |
| Payroll segment allocation (entity × Department × BU per employee) | Mimi (Payroll2u, custom field "Department/BU Code") | Monthly (run ~24th of month) | Payroll2u export |
| Manpower budget allocation file | Cecilia Tong (CFO) | Annual + ad-hoc | CFO sheet |
| Segment list reference (Jan26 worksheet, etc.) | Li Ping | Quarterly refresh | Master segment Google Sheet |
| Payment gateway settlement files | Alexandre Morin (Payments) → Peter Dalmia / Harshal Patankar | Per-gateway daily/weekly | Per-gateway dashboards / email |

### 16.5 Period close

- `accountingperiod` system table is **not exposed** to this PROD role via SuiteQL.
- Period status checks must go through NetSuite UI (`Setup > Accounting > Manage Accounting Periods`) or REST `get_record`.
- **Period reopen requests → Li Ping only.**
- Closed-period AP/AR corrections go via JE (single-sub) or Advanced IC JE (cross-sub).

---

## 17. Reporting cadence

### Standard NetSuite financial reports

- **Income Statement / P&L** by subsidiary, BU, Department, period
- **Balance Sheet** by subsidiary, period
- **Trial Balance** by subsidiary
- **Consolidated Income Statement / Consolidated Balance Sheet** — runs through elimination subs (15, 16, 31)
- **AR Aging / AP Aging** — see `prod/ar_operations.md` and `prod/ap_operations.md` §18

### Key recurring outputs

- **Monthly close pack** — Li Ping (post Sang Le's GMV file ingestion + Mimi's payroll segment file)
- **Weekly AP aging** — currently manual; OpenClaw automation scope (Beekim, 2026-04-17 ask)
- **Payment gateway recon** — automation in `#payments-reconciliation` (Alexandre / Peter Dalmia / Harshal)
- **GDS Incentive** — monthly accrual + true-up, Sang Le file → Li Ping
- **VAT / GST / TDS / PPH returns** — see `prod/tax_reporting.md`

### Dashboards & extracts going to Cecilia / leadership

- Manpower allocation file (entity × Department × BU × employee × cost) — flows from Mimi's payroll → Cecilia's allocation engine → Li Ping's GL splits.
- Sang Le's "files aggregated by payment currency code" — for FX exposure tracking.

---

## 18. Useful SuiteQL queries (PROD-compatible)

> SuiteQL `transaction`, `accountingperiod`, `customrecordtype`, `customsegment` not exposed in PROD role. Queries below stay within what the role allows.

### Chart of accounts breakdown

```sql
SELECT accttype, COUNT(id) AS cnt
FROM account
WHERE isinactive = 'F'
GROUP BY accttype
ORDER BY accttype;
```

### Find an account by number or name

```sql
SELECT id, acctnumber, accountsearchdisplayname, accttype, subsidiary
FROM account
WHERE (acctnumber LIKE :pattern OR UPPER(accountsearchdisplayname) LIKE UPPER(:name))
AND isinactive = 'F'
ORDER BY acctnumber;
```

### List all departments

```sql
SELECT id, name FROM department WHERE isinactive = 'F' ORDER BY name;
```

### List all BU codes (Classifications)

```sql
SELECT id, name FROM classification WHERE isinactive = 'F' ORDER BY name;
```

### List all locations

```sql
SELECT id, name, fullname FROM location WHERE isinactive = 'F' ORDER BY name;
```

### List subsidiaries with currency

```sql
SELECT s.id, s.name, s.country, s.currency, c.name AS currency_name
FROM subsidiary s
LEFT JOIN currency c ON c.id = s.currency
WHERE s.isinactive = 'F'
ORDER BY s.id;
```

### Find every revenue account

```sql
SELECT acctnumber, accountsearchdisplayname
FROM account
WHERE accttype = 'Income' AND isinactive = 'F'
ORDER BY acctnumber;
```

### Find every COGS / expense account

```sql
SELECT acctnumber, accountsearchdisplayname, accttype
FROM account
WHERE accttype IN ('COGS','Expense') AND isinactive = 'F'
ORDER BY accttype, acctnumber;
```

### Pull a JE / Advanced IC JE / Amortization JE

Use REST: `mcp__netsuite-prod__get_record` with `record_type=journalEntry` (single-sub) or `interCompanyJournalEntry` (advanced) and `record_id=<id>`.

---

## 19. Error catalog (GL / reporting — PROD-relevant)

| Error / symptom | Cause | Fix in PROD | Notes |
|---|---|---|---|
| P&L line missing Department / BU / Product / Market segment | Preparer skipped a required segment | Reverse the JE → re-post with all 5 segments | High-frequency; segments enforced from Jan 2025 onward |
| `_TO IA` posting on non-`_TO IA` counterparty | Wrong account family used | Reverse + re-post; confirm the IC scheme with Li Ping/GC | Recurring; `_TO IA` parallel scheme is sub-set-specific |
| FX revaluation posting unexpected | Period revaluation engine ran before all transactions cleared | Wait for revaluation completion before final close steps; re-open period if needed | Period-end |
| Consolidated Trial Balance not zeroing | IC pair (DFx/DTx) not matched on counterparty currency / sub | Use `intercompany-balance-investigation` skill | See sister skill |
| Net profit (32020) doesn't tie to P&L sum | NetSuite auto-rollup hasn't run / period not yet closed | Refresh; check period state | Cosmetic if periods open |
| Period locked for posting | Period closed | Li Ping reopens, or post to next open period with memo | PROD-only sensitivity |
| `Record 'transaction' was not found` (SuiteQL) | Read-only role doesn't expose `transaction` | Use REST `get_record` per record type | Confirmed 2026-04-28 |
| `Record 'accountingperiod' was not found` (SuiteQL) | Same role limit | Use NetSuite UI / REST | Confirmed 2026-04-28 |
| `Record 'customsegment' was not found` (SuiteQL) | Same role limit | Use NetSuite UI / GC for value lists | Confirmed 2026-04-28 |
| Sang Le NS file row missing CoA number | Account number not present in ChartofAccount tab | Sang Le adds row to source file (Slack 2024-12-02) | Recurring |
| VCC Rebate booked under wrong tab | Rebate timing — flight booking → 3-day delay → insurance commission posts later | Split insurance commission into separate schedule (Sang Le 2024-12-30) | Recurring |
| Payroll segment file empty for new joiners | Bamboo not yet updated; Mimi using Payroll2u "Finance Grouping" + custom Department/BU code field | Mimi adds new field to Payroll2u; pull pre-payroll-run | Per Slack 2025-01-22 |

---

## 20. Do-Not-Answer List (escalate only)

In PROD these are extra-sensitive — never propose changes without sign-off:

- New CoA addition / retirement → Li Ping + Akansha + Peter + GC
- New custom segment value (Product Segment / Market Segment) → Li Ping + GC
- Period reopen → Li Ping only
- Cross-sub manual JE → use Advanced IC JE; not parallel single-sub JEs
- FX rate source / timing change → Li Ping → Cecilia Tong
- Consolidation methodology change → Li Ping + Cecilia Tong
- Elimination sub mapping change (15, 16, 31) → Li Ping + GC
- Treasury / IIS impairment posting → Li Ping + Cecilia Tong + auditor
- Tax / WHT account mapping → tax team + Li Ping
- Manpower allocation methodology change → Cecilia Tong → Li Ping → Mimi/Svetlana
- `_TO IA` scheme changes → Li Ping + GC

---

## 21. Future / OpenClaw scope (GL)

- **Automated 5-segment validation on every posting** — agent-driven check before save
- **GDS Incentive auto-accrual** — replace Sang Le's monthly file with NetSuite-resident calc
- **VAT/output-tax automation per booking-type / market** (cross-cuts with `tax_reporting.md`)
- **Auto-extract of P&L by BU** — Cecilia / Li Ping consume; currently manual
- **Payment gateway recon → JE auto-post** — currently manual; in `#payments-reconciliation` scope
- **Crypto Payments recon (Feb 2026 launch)** — gateway sample → NetSuite JE
- **Manpower allocation auto-split of Shared (BU 20) cost** — replace Cecilia's manual file
- **PROD `transaction` + `accountingperiod` SuiteQL access** — request to GC; would unlock close-period analytics
- **Custom segment metadata via SuiteQL** — request to GC
- **Single source of truth for `_TO IA` vs DFx/DTx scheme** — documentation effort with Li Ping + GC

---

## 22. Known gaps (TBD)

- [ ] Confirm SG-subsidiary base currency (`subsidiary.currency=1`) — USD-functional or SGD-functional?
- [ ] Boundary between **DFx/DTx scheme** and **`_TO IA` scheme** — when to use which on cross-entity postings; which is authoritative for consolidation
- [ ] **Product Segment** custom segment value list — internal IDs and meanings (blocked: SuiteQL `customsegment` not exposed)
- [ ] **Market Segment** custom segment value list — same blocker
- [ ] Whether **Location** dimension should be opened beyond India (only Bangalore + Mumbai populated)
- [ ] Authoritative FX P&L set — `91020/91021` (system) vs `4060002/4060003/5040002/5040003 _TO IA` (cross-entity)
- [ ] `33092 / 33093 CTA` — exact consolidation rules and whether agent should ever read these directly
- [ ] **Revenue accrual** flow doc — how `1221xxx / 1222xxx` accruals tie to Sang Le's monthly NS files
- [ ] **VCC Rebate** schedule split — separate accrual vs. main flight schedule; final state post-Wenrix-optimization fix
- [ ] **GDS Incentive** — current calc methodology vs. accrual policy
- [ ] Cecilia's manpower allocation file structure (entity × Department × BU × employee × budgeted cost)
- [ ] List of saved searches in `Reports / SuiteAnalytics` used by Li Ping for monthly close
- [ ] Period close checklist — order of operations, AP cutoff, AR cutoff, FX revaluation, segment validation, consolidation
- [ ] Crypto Payments gateway field spec (file format, dashboard download path)
- [ ] Whether `4010009 WegoPro Flights Revenue_TO IA` is intentionally stored without `_TO IA` suffix in `acctnumber` (only sister account in this position; data quality flag)
- [ ] Inventory of `NonPosting` (8) accounts and their use cases
- [ ] Inventory of `Stat` (2) accounts (statistical accounts)

---

## 23. Revision log

| Date | Author | Change |
|---|---|---|
| 2026-04-28 | Akansha + Claude | **Rewrite.** Re-grounded the doc with `#proj-finance-segment-allocation` Slack thread context (Li Ping, Sang Le, Sheng Xiong, Mimi, Svetlana, Cecilia) and live PROD pulls. Rewrote §3 around the 5-segment booking convention. Added §4 (20 Departments), §5 (15 BU codes), §6 (Locations — India anomaly). Reorganised §8 by revenue family (Metasearch / Display / WegoPro / ShopCash / OTA Agency / OTA Merchant / Other / `_TO IA`). Reorganised §9 / §10 by cost block (51-Media / 52-Inventory / 61-COS / 62-Agency / 63-Merchant / 64-Marketing / 71-COD / 81-OH / 82-86 G&A / 87 Depn). Documented `_TO IA` scheme at §10.4. Added §13 (IC + payment gateway clearing), §14 (Fixed Assets pairs), §15 (Unbilled Receivables / revenue accruals). Documented monthly close inputs (§16.4 cadence table) — Sang Le's GMV files, Mimi's payroll segments, Cecilia's manpower allocation, GDS Incentive. Added error catalog (§19) with Slack-sourced recurring issues (CoA gaps in NS file, VCC rebate timing, payroll-segment-for-new-joiners). |
| 2026-04-28 | Akansha + Claude | (Earlier draft) First PROD-grounded skeleton with chart of accounts, AR/AP control accounts, intercompany scheme, JE workflows, partial expense map. |

---

## 24. Related

- `prod/ap_operations.md` — AP processes (vendor, bill, payment, IC JE, amortization, recon)
- `prod/ar_operations.md` — AR processes
- `prod/tax_reporting.md` — Input/Output VAT, TDS, PPH, e-invoicing
- `sbx/gl_reporting.md` — Sandbox equivalent of this doc
- Skill: `intercompany-balance-investigation` — IC reconciliation playbook
- Skill: `openclaw-meeting-actions` — Akansha/Peter sync action items
- Skill: `netsuite-report-ticket` — convert finance ask → NDS Jira ticket
- Slack: `#proj-finance-segment-allocation` — primary GL/segment work
- GDrive: Sang Le's monthly Flights/Hotels NS files; segment master sheet (Jan26)