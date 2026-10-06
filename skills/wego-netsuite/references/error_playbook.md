# Error Playbook — NetSuite Champion

What the listener does when NetSuite MCP calls fail. The goal is **never** to fabricate a fallback answer — always surface the real error to the user with a clear next step.

---

## HTTP-status playbook

| Status | Meaning | User-facing reply | Internal action |
|---|---|---|---|
| 200/201 | Success | Normal grounded answer; for WRITE include sandbox URL + `_(sandbox)_` banner (auto via `governance.annotate_sandbox`) | Log call to `action_tracker.md` |
| 400 | Bad request — malformed body, missing field, invalid enum | "NetSuite rejected the request: `<error>`. Check the field names — the AP/AR doc lists the required ones." | Log full request body + response for debugging |
| 401 | Unauthorized — TBA token rejected | "Auth rejected by NetSuite. Token may have been revoked. Tag @Akansha in #netsuite_adminsupport to refresh the TBA token-pair." | TBA tokens don't auto-rotate — escalate manually |
| 403 | Forbidden — role lacks scope on this subsidiary/record/field | "Permission denied on that record/subsidiary for the Champion's role. Tag @Akansha in #netsuite_adminsupport to widen the role scope." | Log subsidiary + record type + role. Note: NetSuite **silently drops** restricted fields rather than 403'ing — reconcile via `metadata_catalog()` if values look missing. |
| 404 | Not found | "No record matches that criteria in NetSuite. Double-check the ID or the search filter." | Log query |
| 409 | Conflict — duplicate or workflow state mismatch | "NetSuite reports a conflict: `<error>`. Likely a duplicate or a workflow state issue. Check the existing record before retrying." | Log; surface NetSuite's conflict reason |
| 412 | Precondition failed — Champion-side preflight (e.g. period locked) | "Can't post into a locked/closed period. Open the period in #netsuite_adminsupport or use a different `trandate`." | This status is synthesised by `finance_tools` (see `is_gl_post_safe`), not returned by NetSuite |
| 429 | Rate-limited (concurrency cap shared across REST/SOAP/RESTlet — default 15) | "NetSuite is rate-limiting us — queued for retry in 30 s." | Exponential backoff: 30 s, 60 s, 120 s; max 3 retries. The `ConcurrencyLimiter` keeps us under the cap to avoid this. |
| 500 | Server error | "NetSuite returned a server error. Retrying once. If it fails again, post in #netsuite_adminsupport." | Retry once with jitter; on second fail, surface |
| 503 | Service unavailable | "NetSuite is temporarily unavailable. Retrying with backoff — try again in 1 minute." | Backoff retry; on third fail, alert |

---

## Domain-specific failure modes

### AP — vendor or bill create fails

- **400 "subsidiary required":** include `subsidiary.id` in the body. Cross-check against `knowledge_base/subsidiaries.md`.
- **400 "currency mismatch":** vendor currency must match subsidiary base. Use the subsidiary's currency from `subsidiaries.md`.
- **403 "approval workflow restricts":** vendor approval workflow is live since 2025-08-15 — Champion cannot bypass it. Reply: "Created in sandbox but pending approval — Nurul Ain or proxy needs to approve."

### AR — invoice or customer create fails

- **400 "tax code required":** subsidiary has multi-code tax setup. Look up the right code per `knowledge_base/tax_compliance.md`.
- **403 "customer approval required":** customer approval workflow live since 2025-10-16. Same treatment as AP.

### GL — journal create fails

- **400 "debits don't equal credits":** model produced unbalanced lines. Listener should re-prompt OpenClaw with the validation error.
- **403 "period locked":** target period is closed. Tell user which period is open.
- **400 "BU code missing":** BU code validation gap (see `gl_reporting.md`). Surface and suggest manual BU assignment.

### Tax — tax code or report fails

- **400 "tax code already exists":** the code is set up; Champion does not duplicate.
- **403 "Taxilla integration in progress":** UAE e-invoicing flow is not Champion-driven. Redirect to `#netsuite_tax` with @Akansha.

### OTA — pipeline status fails

- **404 "no recent OTA load":** pipeline did not run today. Check `#netsuite_ota` channel history; Akansha to investigate SFTP or BigQuery side.
- **400 "row count mismatch":** OTA validation tripped the >5% threshold. Surface the actual delta.

---

## Failure replies — exact phrasings to use

For consistency, the listener uses these templates verbatim:

```
🛑 Couldn't run that — NetSuite returned <status> (<short reason>).
<one-line cause if known>
Next step: <one of the recommended actions above>
```

Example:

```
🛑 Couldn't run that — NetSuite returned 403 (forbidden on subsidiary Wego India Pvt Ltd).
The Champion's role does not have full access to that subsidiary's vendors.
Next step: post in #netsuite_adminsupport with the subsidiary name and tag @Akansha to widen the role scope.
```

For WRITE failures, additionally:

```
No sandbox record was created.
```

This line is critical — without it, ambiguity creeps in about whether the write half-completed.

---

## What the listener never does on failure

- Never fabricates a record ID or URL.
- Never says "retrying silently" without telling the user.
- Never suppresses an error and answers from the KB doc alone — if MCP failed for a question that needed live data, the user must know.
- Never auto-promotes to production. There is no "fallback to prod" path.

---

## Logging on failure

Every failure is logged:

```
[YYYY-MM-DD HH:MM:SS UTC] [SCOPE: read-prod|write-sandbox] [CHANNEL: <id>] [USER: <slack_uid>] [STATUS: <http>] [PATH: <api-path>] [ERROR: <netsuite-msg>]
```

Logs go to:
- `memory/knowledge/action_tracker.md` (project-wide audit)
- (Legacy listener logs no longer exist — the Python listener was deleted on 2026-05-12. Errors now surface directly in the agent's Slack reply per `CLAUDE.md` Rule 5.)
- Surfaced summary to `#netsuite_adminsupport` if 3+ consecutive failures of the same type within 10 minutes.
