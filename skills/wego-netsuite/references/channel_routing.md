# Channel Routing — NetSuite Champion

> ## ⚠️ ARCHITECTURE OVERRIDE
>
> You are operating via **OpenClaw**, calling **Oracle's NetSuite MCP Standard Tools** directly. There is **no Python listener** in the live path. References to "the listener" anywhere in this doc are legacy prose — the runtime path is: Slack mention → OpenClaw (you) → Oracle MCP server → NetSuite. See `SKILL.md §1` for the live architecture diagram.

Authoritative table mapping each Slack channel to (a) its KB doc, (b) the MCP scope used for queries originating in that channel, and (c) the typical intents to expect.

This table is the source of truth. `agents/nova-pro/MANIFEST.md` mirrors it for channel-aware KB loading. If you change this table, update the MANIFEST in the same commit.

---

## Channel → KB doc → MCP scope

| Channel | Channel ID | KB doc auto-loaded | MCP READ (prod `5564218`) | MCP WRITE (sandbox `5564218-sb1`) | Common intents |
|---|---|---|---|---|---|
| `#netsuite_ap` | `C08N2T0CARE` | `knowledge_base/netsuite_ap.md` | ✅ | ✅ | bill status, vendor lookup, vendor create, bill create, approval queue check |
| `#netsuite_ar` | `C08N2SY3HFS` | `knowledge_base/netsuite_ar.md` | ✅ | ✅ | invoice status, customer lookup, customer create, invoice create, AR aging |
| `#netsuite_gl_and_reporting` | `C08MCK3NJTX` | `knowledge_base/netsuite_gl_and_reporting.md` | ✅ | ✅ | GL balance, journal create, trial balance, period status, BU drill-down |
| `#netsuite_tax` | `C08MHS9PMFC` | `knowledge_base/netsuite_tax.md` | ✅ | ✅ | VAT code lookup, tax code create, e-invoicing status, tax report retrieval |
| `#netsuite_ota` | `C08LZTG1YR5` | `knowledge_base/netsuite_ota.md` | ✅ | ✅ | OTA pipeline status, CSV import log, journal upload status, validation errors |
| `#netsuite_champion` | `C0B1T3B4RMH` | resolved at runtime — see "Master channel routing" below | ✅ | ✅ | anything from any of the five domains; centralized master channel |
| `#netsuite-dev-agent` | `C0B9A8ZRM5X` | resolved at runtime — uses the same master-channel routing as `#netsuite_champion` | ✅ | ✅ | **Nikhil's dev / QA channel for testing changes before they touch live finance channels.** Treat exactly like `#netsuite_champion` — real MCP calls, real SuiteQL, real sandbox writes when asked. Do NOT degrade behaviour because "it's a test channel" — Nikhil is validating production code paths. |

**For every channel above**, the MANIFEST also force-loads `SKILL.md` + `CLAUDE.md` + `MEMORY.md` (architecture + 5-rule operating contract + env var inventory). The per-channel KB doc is **additional** domain detail, not a substitute for the core skill files.

**Bot user-id that triggers the agent:** `@Data Automation's Claw` — `U0AHNGSDQ3W`.

---

## Channels intentionally NOT in the Champion's set

| Channel | Channel ID | Why excluded |
|---|---|---|
| `#netsuite_adminsupport` | `C08MCK8936Z` | Human-driven channel for auth, role, sandbox-refresh, and config escalation. Akansha and Nikhil triage manually. The Champion should not auto-respond. |
| `#wego-netsuite-automated-tests` | (TBD) | Test-run output channel; no human queries expected. |
| `#netsuite-integrations` | (TBD) | Integration-design discussion; cross-functional, not a query channel. |

---

## Master channel routing — `#netsuite_champion` and `#netsuite-dev-agent`

`#netsuite_champion` (`C0B1T3B4RMH`) is the centralized live master channel. `#netsuite-dev-agent` (`C0B9A8ZRM5X`) is Nikhil's dev / QA channel — **identical routing**, used for validating any new behaviour before it lands in live finance channels. Both follow the same domain-resolution flow below.

Anyone can use either for any domain. Resolve the domain from the user's message in this order:

1. **Explicit prefix** at the start of the message — any of:
   - `[AP] …` / `[AR] …` / `[GL] …` / `[Tax] …` / `[OTA] …`
   - `AP: …` / `AR: …` / `GL: …` / `Tax: …` / `OTA: …`
   - `for AP, …` / `for AR, …` / `for GL, …` / `for Tax, …` / `for OTA, …`
   - `AP operation: …` / `AR operation: …` / `GL operation: …` / `Tax operation: …` / `OTA operation: …`
2. **Implicit nouns** — apply the keyword routing table from `prompt_templates.md §2` ("bill"/"vendor"/"AP aging" → AP, "invoice"/"customer" → AR, "trial balance"/"period close" → GL, "VAT"/"e-invoice" → Tax, "OTA"/"BigQuery feed" → OTA).
3. **Ask the user** — if both steps return ambiguous, reply in-thread with **one** short clarifier:
   > Which area is this about — *AP*, *AR*, *GL*, *Tax*, or *OTA*? Prefix your message (e.g. `[AP] …` or `AP: …`) and I'll route it.

Once a domain is resolved, load the same KB doc as the per-domain channel (e.g. `[AP] …` in `#netsuite_champion` is treated identically to a message in `#netsuite_ap`) and proceed with the Oracle MCP call.

---

## Routing precedence (when multiple skills could match)

The `agents/nova-pro/MANIFEST.md` documents the global precedence. NetSuite-specific addendum:

1. **Channel ID match wins.** If the source channel is one of the six NetSuite channels, load `SKILL.md + CLAUDE.md + MEMORY.md + the channel KB`. Do not fall back to other skills until you've checked Oracle's MCP first.
2. **Finance Reconciliation does NOT collide here.** The Finance Reco bridge channels are `#finance-automation-claw` and `#proj-alphabot-testing` — disjoint from the NetSuite six.
3. **Multi-intent queries** (e.g. "what's the AP aging and also can you create a vendor X") — treat the read sub-question and the write sub-question as a single thread but two MCP calls: one against the production server, one against sandbox. Reply is one message with both outcomes and the sandbox URL for the write.

---

## Read vs write classification rules

**READ if the message asks for state:**
- "what is …", "show me …", "list …", "is X paid", "balance of …", "status of …", "any open …", "aging for …", "find …", "check …".
- Route the Oracle MCP call to `netsuite-mcp-standard-tools-production`.

**WRITE if the message requests a change:**
- "create …", "add …", "post …", "new vendor …", "new bill …", "new customer …", "new journal …", "set up …".
- Route the Oracle MCP call to `netsuite-mcp-standard-tools-sandbox`. Reply MUST contain the sandbox URL.

**Ambiguous → classify as READ and ask in-thread.** Never assume a write intent. Asking is cheap; a wrong write is not.

---

## URL templates (used in write-success replies)

Construct these from the `id` returned by Oracle's MCP `create_record` call. Always sandbox.

| Record type | URL template |
|---|---|
| Vendor | `https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=<internalId>` |
| Customer | `https://5564218-sb1.app.netsuite.com/app/common/entity/custjob.nl?id=<internalId>` |
| Vendor Bill | `https://5564218-sb1.app.netsuite.com/app/accounting/transactions/vendbill.nl?id=<internalId>` |
| Invoice | `https://5564218-sb1.app.netsuite.com/app/accounting/transactions/custinvc.nl?id=<internalId>` |
| Journal Entry | `https://5564218-sb1.app.netsuite.com/app/accounting/transactions/journal.nl?id=<internalId>` |
| Item | `https://5564218-sb1.app.netsuite.com/app/common/item/item.nl?id=<internalId>` |

If you create a record type not in this table, fall back to:
`https://5564218-sb1.app.netsuite.com/app/common/search/searchresults.nl?searchid=<internalId>` and include the internal ID and record type in the reply text.

---

## How to know you're on the right path

If you find yourself thinking any of the following — **stop**, re-read `SKILL.md §1`, and use Oracle's MCP tools instead:

- "Let me import `netsuite_mcp`…"
- "Let me check if `requests` / `requests-oauthlib` is installed…"
- "Let me look for the `netsuite_listener` service…"
- "Let me check `jobs.json`…"
- "I'll tell the user to type `@bot run_suiteql <query>` in `#netsuite_ap`…"
- "Let me load credentials from `/home/openclaw/.openclaw/cron/openclaw.env`…"

You have Oracle MCP tools. Use them. Token / env-var loading is the MCP server's job, not yours.
