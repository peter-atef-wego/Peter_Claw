# references/smoke_test_plan.md

End-to-end smoke test for the NetSuite Champion running on OpenClaw + Oracle's NetSuite MCP Standard Tools. Run these in order. Each test is a Slack message the user (Nikhil) posts in the listed channel; the **expected outcome** is what the bot should reply.

**Important caveat:** these tests must be executed **live** by the user against the deployed Champion — they can't run from inside this conversation, because they go through Slack → OpenClaw → Oracle MCP → NetSuite. Use this doc as the checklist; tick each item off as you run it.

---

## 0. Pre-flight (run once before the rest)

| # | Check | How | Pass criteria |
|---|---|---|---|
| 0.1 | OpenClaw env vars set | Inspect the OpenClaw secrets UI | All 15 vars in `MEMORY.md §A.11` present, write-only. |
| 0.2 | MCP servers reachable | DM the bot: `@Data Automation's Claw ping` (no NetSuite call needed) | Bot replies with a non-NetSuite acknowledgement. |
| 0.3 | Slack token works | The bot reads your mention | Mention triggers a reply (any reply). |

If any of 0.1–0.3 fail, stop and fix before running anything below.

---

## 1. Authentication + base connectivity

| # | Channel | Test message | Expected reply (shape) |
|---|---|---|---|
| 1.1 | DM (`D0AHK0616JW`) | `list our 8 subsidiaries` | Table of 8 rows with `id`, `name`, `country`, `currency`. Matches the alias table in `dimension_aliases.md`. |
| 1.2 | DM | `which period is open right now?` | One-line: "Current period is `MAY-2026` — open (closed=F, alllocked=F)." or the actual state. |
| 1.3 | DM | `what's the FX rate AED to SGD today?` | Headline `1 AED = X.XXXX SGD`, with effective date. |

**If any of 1.1–1.3 fail with `401 INVALID_LOGIN_ATTEMPT`** → token problem. Rotate TBA per `MEMORY.md §A.11` rotation guidance.

---

## 2. Per-channel read smoke (one read per domain channel)

| # | Channel | Test message | Expected reply (shape) |
|---|---|---|---|
| 2.1 | `#netsuite_ap` | `A/P Aging Detail BK for Wego FZ-LLC as of 30/06/2026` | ONE `get_stored_report` call (period=2026-06-30, subsidiary='Wego FZ-LLC') -> per-subsidiary xlsx from the emailed report, title row = subsidiary, totals foot. NO SuiteQL / saved search. |
| 2.2 | `#netsuite_ar` | `show me open invoices for any customer with "agoda" in the name` | Either a list of matches, OR a disambiguation prompt if >1 hits. |
| 2.3 | `#netsuite_gl_and_reporting` | `is May 2026 closed?` | Period status table, closed/alllocked flags, soft vs hard close note. |
| 2.4 | `#netsuite_tax` | `give me the VAT summary for May 2026 for Wego FZ-LLC` | Table grouped by `taxcode` with `tax_total` and `txn_count`. |
| 2.5 | `#netsuite_ota` | `show me the OTA loads from the last 7 days` | List of journals with `tranid`, `trandate`, `memo`, `amount`. |

Each reply MUST be **in-thread** (not in the channel main feed). If you see a main-feed post, the thread protocol is broken — check `CLAUDE.md §5`.

---

## 3. Master-channel routing

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 3.1 | `#netsuite_champion` | `[AP] show me open bills for Acme` | Treats as AP, loads `knowledge_base/netsuite_ap.md`, runs `get_open_bills_for_vendor`. |
| 3.2 | `#netsuite_champion` | `what's the trial balance for May 2026?` | Recognises GL nouns → loads `netsuite_gl_and_reporting.md`, runs `get_trial_balance`. |
| 3.3 | `#netsuite_champion` | `quick question` (no domain hint, no nouns) | Bot asks **one** clarifying question: "Which domain — AP, AR, GL, Tax, or OTA?" |

---

## 4. Dimension resolution

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 4.1 | DM | `what's the AP aging for FZ?` | Resolves "FZ" → `Wego FZ-LLC` via `SUBSIDIARY_ALIASES`. |
| 4.2 | DM | `what's the AP aging for Wego?` | Asks: "Which subsidiary — Wego Pte Ltd, Wego FZ-LLC, Wego ME, …?" (8 options). |
| 4.3 | DM | `show me the input tax KSA balance for this month` | Resolves "input tax KSA" → account `1401015` (per `ACCOUNT_ALIASES`); resolves "this month" → current period. |
| 4.4 | DM | `what was the AP aging last quarter for KSA?` | Resolves "last quarter" → `(start, end)`; resolves "KSA" → `Wego Saudi and Tourism`. |

---

## 5. Sandbox writes (the centralized-creation promise)

> ⚠️ These run against sandbox `5564218-sb1`. Records are real but will be wiped on the next quarterly refresh. Each test ends with a sandbox URL — open it in NetSuite to verify the record looks right.

| # | Channel | Test message | Expected reply |
|---|---|---|---|
| 5.1 | `#netsuite_ap` | `create vendor "Smoke Test Vendor — DELETEME" in Wego FZ-LLC with currency AED and email vendor@example.com` | `✅ Created vendor **Smoke Test Vendor — DELETEME** in sandbox. Link: https://5564218-sb1.app.netsuite.com/app/common/entity/vendor.nl?id=<id>` + sandbox banner. |
| 5.2 | `#netsuite_ar` | `create customer "Smoke Test Customer — DELETEME" in Wego SG with currency SGD` | Same shape, `custjob.nl?id=…`. |
| 5.3 | `#netsuite_ap` | `create a bill for "Smoke Test Vendor — DELETEME" dated today, due in 30 days, single line of SGD 100 for hotel commission` | Resolves vendor, resolves subsidiary from vendor record, posts the bill, replies with `vendbill.nl?id=…`. |
| 5.4 | `#netsuite_gl_and_reporting` | `post a journal in Wego SG today: debit 1000 SGD to 4100, credit 1000 SGD to 1200, memo "smoke test — DELETEME"` | Preflight checks period open + debits=credits, posts, replies with `journal.nl?id=…`. |
| 5.5 | `#netsuite_gl_and_reporting` | `post a journal in Wego SG dated 2025-12-31: debit 100 to 4100, credit 100 to 1200` (deliberately closed period) | ⚠️ Rejection: "Can't post — December 2025 period is closed". No sandbox record created. |
| 5.6 | `#netsuite_champion` | `[AP] create vendor "Champion Test Vendor — DELETEME" in Wego India` | Routes to AP, creates in sandbox, replies with URL. |

**For every successful write:**

- The reply contains the sandbox URL.
- The sandbox banner appears at the end of the reply.
- A new line appears in `memory/knowledge/action_tracker.md` with the same fields.

---

## 6. SuiteQL free-form (run_suiteql)

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 6.1 | DM | `run this SuiteQL: SELECT COUNT(*) FROM vendor WHERE isinactive='F'` | Returns the count. Auto-sanitised; no warning needed. |
| 6.2 | DM | `run this: SELECT * FROM transaction LIMIT 10` | Bot rewrites `LIMIT 10` → `WHERE ROWNUM <= 10` OR explains the syntax fix and re-runs. |
| 6.3 | DM | `run this: DELETE FROM vendor WHERE id=1` | Rejected with "DDL/DML not allowed in SuiteQL — read-only queries only". No write attempted. |
| 6.4 | DM | `run this: SELECT 1; SELECT 2` | Rejected with "multi-statement SuiteQL not allowed". |

---

## 7. Schema introspection

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 7.1 | DM | `what fields are on a vendor record?` | Calls `metadata_catalog('vendor')`, returns the field list + sublists. |
| 7.2 | DM | `what record types does NetSuite expose?` | Calls `metadata_catalog()` (no arg), returns the list. |

---

## 8. Saved Search (RESTlet companion)

> Only run if a saved search exists. Ask Akansha for a low-risk test search id first.

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 8.1 | DM | `run saved search customsearch_<id>` | Forwards to the RESTlet (`run_saved_search`); returns rows. |
| 8.2 | DM | `run saved search customsearch_doesnotexist` | Error message: "RESTlet returned `unknown_search_id` …" or NetSuite's actual error. |

---

## 9. Failure-mode coverage

| # | Channel | Test message | Expected behaviour |
|---|---|---|---|
| 9.1 | DM | `create vendor "Foo" in Atlantis` (unknown subsidiary) | Error: "I don't recognise 'Atlantis' as a subsidiary. Which subsidiary — Wego Pte Ltd, Wego FZ-LLC, …?" |
| 9.2 | DM | `create bill for vendor "Acme" in Wego SG today for 100` (multiple vendors match) | Error: "Vendor 'Acme' matches multiple records — be more specific. Candidates: Acme Travel (id=…), Acme Hotels (id=…)." |
| 9.3 | DM | `post a journal in Wego SG today: debit 100 to 4100, credit 50 to 1200` (unbalanced) | Error: "Unbalanced journal: debits=100 credits=50 — must net to zero." |
| 9.4 | (after rotating away the prod TBA token) | DM `list our subsidiaries` | Error reply: "NetSuite returned 401 — token may need rotation. Nikhil — heads up." (Then rotate back.) |

---

## 10. Slack-thread protocol

| # | Channel | Test | Pass criteria |
|---|---|---|---|
| 10.1 | `#netsuite_ap` | Send `@Data Automation's Claw what's the AP aging?` as a TOP-LEVEL message | Bot replies with `thread_ts = <your message ts>`, creating a new thread (visible as 1 reply on your message). |
| 10.2 | (same channel) | In the thread from 10.1, send `… and now for Wego India?` | Bot replies in the SAME thread; uses "Wego India" from your text, doesn't re-ask for subsidiary. |
| 10.3 | (same channel) | Edit your original message after the bot replied | Bot ignores the edit. No new reply, no echo. |
| 10.4 | (same channel) | Another user mentions the bot in the same channel from a different message | Bot handles them independently — no cross-thread state leak. |

---

## 11. Master-of-NetSuite breadth check

Pick **one from each section** of `netsuite_capabilities.md` to confirm the bot handles the breadth:

| Section | One question to ask |
|---|---|
| Entity records | `look up vendor with id 12345` |
| Transactions (AP) | `show me bill 67890` (uses `read_record('vendorbill', 67890, expand_lines=true)`) |
| Transactions (AR) | `show me invoice 67891` |
| Transactions (GL) | `show me journal 67892` |
| Items | `list our service items` (`SELECT … FROM serviceitem`) |
| Lists / segments | `list our locations` |
| Approval | `is bill 67890 approved yet?` |
| Saved Search | (see §8) |
| SuiteQL | (see §6) |
| Schema | (see §7) |
| Custom transaction | `count rows in customtransaction_wego_est_brr_fin_det` |

Each should return a real answer or a clean "I'd need NetSuite to expose X, raising with Akansha" message — never silence, never fabrication.

---

## 12. Post-test cleanup

After the smoke tests, in sandbox:

1. Mark the smoke-test vendors / customers / bills / journals **inactive** (don't delete — keeps the audit trail).
2. Note the test count in `MEMORY.md §B.3` under "Pending follow-ups".

For records in prod: none should have been created. Verify by searching the Champion audit trail (`memory/knowledge/action_tracker.md`) for the test timestamp — every line MUST point to a `5564218-sb1` URL, none to `5564218`.

---

## 13. Pass criteria for "Champion is live"

- ✅ Sections 0–4 pass with no surfaced errors that aren't expected.
- ✅ At least 3 of 6 writes in §5 succeed and return a working sandbox URL.
- ✅ Section 9 failure-modes return the expected error messages (not silent failures or fabricated success).
- ✅ Section 10 thread protocol is correct (no main-feed posts, threads inherit).
- ✅ Section 11 breadth check covers ≥8 of 11 rows.

If all pass: declare go-live in `MEMORY.md §B.3`. If any §9 failure mode shows a silent-success (i.e. bot fabricates an answer instead of surfacing the error), **stop** and fix the prompt-side rule before going live — that's the most dangerous failure mode for a finance bot.
