---
name: Wego — Company & Business Overview
owner: Data Automation's Claw-PRO
source: Duncan Reid Blueprint v3.0 + Wego internal knowledge
last_reviewed: 2026-04-08
---

# Wego — Company & Business Overview

## What Is Wego?

Wego is a travel meta-search platform headquartered in Singapore, operating across the Middle East, South Asia, and Southeast Asia. It aggregates flight and hotel options from hundreds of airlines, OTAs (online travel agencies), and suppliers into a single search interface, allowing users to compare prices and book travel.

Wego does not sell tickets directly — it redirects users to the best available offer on the supplier's or OTA's platform.

---

## Core Products

| Product | Description |
|---|---|
| **Flights** | Meta-search for international and domestic flights. Aggregates GDS suppliers, airlines, and OTAs. |
| **Hotels** | Meta-search for hotel and accommodation listings. Integrates with major hotel chains and OTAs. |
| **Wego Metas** | Branded internal term for the core meta-search engine powering both flights and hotels. |
| **Wego.com** | Primary consumer web and mobile product (iOS + Android). |

---

## Business Model

- **Cost-Per-Click (CPC)**: Wego earns revenue when users click through to a supplier/OTA. Advertisers bid for placement.
- **Cost-Per-Acquisition (CPA)**: Some partner agreements pay on confirmed bookings.
- **B2B Partnerships**: White-label and API partnerships with regional banks, airlines, and portals.

Revenue depends on traffic quality, click-through rates, and advertiser bid competition — especially in MENA (Middle East & North Africa) and South Asia markets.

---

## Key Markets

| Region | Significance |
|---|---|
| Middle East (MENA) | Core market. Saudi Arabia, UAE, Kuwait are top revenue contributors. |
| South Asia | India, Pakistan, Bangladesh — high search volume, growing monetisation. |
| Southeast Asia | Singapore (HQ), Malaysia, Indonesia — maturing markets. |

---

## Technology Stack (High Level)

| Layer | Technology |
|---|---|
| Backend | Primarily Ruby on Rails, Go, Python microservices |
| Data | BigQuery (GCP), internal data pipelines via Airflow |
| Frontend | React (web), native iOS/Android |
| Infrastructure | GCP (Google Cloud Platform) |
| Search & Indexing | Custom meta-search engine — aggregates supplier feeds in real time |
| Finance/ERP | NetSuite (Oracle) — accounts payable, receivable, GL, reporting |
| CRM / Support | Internal tooling + Zendesk |

---

## Organisational Structure (High Level)

| Department | Scope |
|---|---|
| Engineering | Product development, platform, infrastructure, data |
| Finance | Accounting, reporting, AP/AR, commissions — heavy NetSuite usage |
| Marketing | Performance marketing, SEO, affiliate partnerships |
| Operations | Supplier partnerships, content operations, customer support |
| AI & Automation | Peter Atef's team — internal process automation, AI agents, data pipelines |

The AI & Automation team sits within Engineering/Operations and services multiple departments (Finance, HR, Payments).

---

## Finance & Operations Context

Finance is one of the heaviest consumers of automation at Wego. Key areas:

- **Commissions**: Calculating and reconciling supplier commission payouts (automated via n8n on Any10)
- **Balance Updates**: Real-time balance alerts flowing to `balance_update_alerts` Slack channel
- **NetSuite**: Oracle NetSuite is the ERP — AR, AP, GL, reporting all run here. Automation team builds integrations and data flows into/out of NetSuite.
- **Disputes**: Online and offline payment dispute workflows (AlphaBot + Robot Framework)

---

## Key Internal Systems for Data Automation's Claw to Know

| System | Used By | Data Automation's Claw Relevance |
|---|---|---|
| NetSuite | Finance | Automation team builds NS integrations (NDS Jira board) |
| AlphaBot | Engineering / Automation | Robot Framework bots — see `knowledge/company/systems-architecture.md` |
| Any10 (n8n) | Automation team | Visual workflow automations for finance + ops |
| Airflow | Data Engineering | DAG pipelines — Ayush's domain |
| BigQuery | Data / Analytics | Outputs from pipelines; referenced in reporting automations |
| OpenClaw | AI team | Agent platform — Data Automation's Claw-PRO runs here |

---

## Key Internal Teams Automation Interacts With

| Team | Primary Contact | What They Need |
|---|---|---|
| Finance / Accounting | Shantan (Finance), Li Ping Low (NetSuite) | NS integrations, commission reports, balance alerts |
| HR | Marwa Abosrea | HR process automations (contract renewal etc.) |
| Payments | Kero | Dispute bots, payment reconciliation |
| Hotels / HCN | Ujjwal Kaushik | Supplier data, Bel Air / GDS feeds |
| Engineering Ops | Madan Kumar | Infrastructure, Data Automation's Claw platform support |

---

## Wego's Automation Philosophy

Automation at Wego is **operational leverage** — reducing manual toil so teams can focus on higher-value work. The automation team is not a cost centre; every project should be framed in terms of:

- Hours saved per week
- Error rate reduction
- Dependency on a single person reduced (bus factor)

When proposing or scoping an automation, Data Automation's Claw should always ask: **"What's the manual process this replaces, and how often does it run?"**
