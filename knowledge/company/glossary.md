---
name: Wego AI & Automation — Glossary
owner: Nikhil Gupta
last_reviewed: 2026-04-06
---

# Glossary

| Term | Definition |
|---|---|
| **HCN** | Hotel Content Network — Wego's hotel content aggregation system. Ayush owns the Airflow/BQ pipelines that feed it. |
| **HotelBeds** | A major hotel distribution platform and content supplier used by Wego. Part of the Hotels ops domain. |
| **GDS** | Global Distribution System — legacy flight/hotel booking infrastructure (e.g., Amadeus, Sabre, Galileo). Likith works on GDS-related automations and supplier recos. |
| **LCC** | Low-Cost Carrier — budget airlines. Relevant to flight content pipelines. |
| **Bel Air** | A supplier development initiative Likith is actively working on. Related to GDS/supplier deals. Context: premium content or supplier channel. |
| **ADM** | Agent Debit Memo — a charge issued by an airline to a travel agent for ticketing errors or policy violations. Relevant to disputes and Finance automation. |
| **IATA** | International Air Transport Association — governs airline standards, ticketing rules, and ADMs. |
| **RHC** | Revenue Health Check — internal finance process. Context: automated reconciliation checks. |
| **AlphaBot** | Wego's internal automation bot framework built on Robot Framework + Python. Repo: `github.com/wego/alphabot` (read-only for Nikhil's team). |
| **OpenClaw** | AI agent platform used by Wego. Nikhil's instance: s-c58f0c35.openclaw.wego.engineering. |
| **IAX** | Jira project key for the AI Automation board (board 721). Used for all automation-related tickets. |
| **NDS** | Jira project key for the NetSuite board (board 753). Used for all NetSuite-related tickets. |
| **Any10** | Wego's hosted n8n environment. Used for deploying and running n8n workflows in production. |
| **n8n** | Open-source visual workflow automation tool. Used extensively by Likith and being taught to Akansha. |
| **Robot Framework** | Open-source keyword-driven test/automation framework (Python-based). Foundation of AlphaBot. |
| **NetSuite** | Oracle NetSuite — ERP system used for finance, accounting, and HR operations at Wego. Akansha is taking ownership from GC (who exited Mar 2026). |
| **Fireflies** | AI meeting note-taker. Transcripts stored in `fireflies/summaries/`. Data Automation's Claw-PRO extracts action items via the `fireflies-intel` skill. |
| **WegoClaw** | Wego's secrets/credentials store for OpenClaw. Holds GITHUB_TOKEN_V4, JIRA_EMAIL, and other secrets used by Data Automation's Claw-PRO. |
| **Supplier Reco** | Supplier Reconciliation — automated matching of supplier invoices/statements to internal records. Part of Likith's Finance automation work. |
| **Ticket Express** | Internal Wego ticketing or issuance flow. Context: relevant to GDS or airline ticketing automations. |
| **BOWF** | Bills of Work / Finance — context for the `data-automations-bow-finance` and `bowf_commissions_automation` Slack channels. Commission automation lives here. |
| **Offline Disputes** | Disputes not handled through the online/automated flow — require manual credential access. Peter is blocked on this (waiting on Kero, Payments team). |
| **Online Disputes** | Automated dispute handling flow. Peter's domain in Cairo. |
| **Phase 1** | Refers to the first deployment phase of Peter's HR Contract Renewal automation. Ready to deploy to Marwa's system. |
