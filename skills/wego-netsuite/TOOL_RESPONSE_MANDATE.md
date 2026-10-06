# TOOL_RESPONSE_MANDATE.md — Mandatory Response Protocol for NetSuite Tools

**EFFECTIVE IMMEDIATELY. This overrides default OpenClaw tool behavior in all NetSuite channels.**

## The Problem (Fixed 2026-05-19)

When Claude called NetSuite tools in Slack channels (`#netsuite_champion`, `#netsuite_ap`, etc.), the tool results were visible in Claude's internal context but **were not being relayed back to the user**. This caused:

- Employee NOVA-EMP-001 created successfully in NetSuite, but user received no confirmation
- Vendor bills created but users saw silence
- Records created without audit trail or notification

**Root cause:** OpenClaw's standard tool-calling system treats tool results as private context. NetSuite writes are state-changing and must be visible to users.

## The Fix

**Every time Claude calls a NetSuite tool in a Slack channel context, Claude MUST post exactly ONE message with:**

1. **Status** (✅ Success / ❌ Failed / ⚠️ Warning)
2. **What happened** (e.g., "Employee NOVA-EMP-001 created")
3. **Record ID** (if successful and a write)
4. **Sandbox URL** (if successful and a write — use RECORD_URL_PATHS from netsuite_mcp_server.py)
5. **Error detail** (if failed — from tool result verbatim, not paraphrased)

## Examples

### ✅ Successful Create

```
✅ Employee created: NOVA-EMP-001 (ID: 6256)
Sandbox: https://5564218-sb1.app.netsuite.com/app/common/entity/employee.nl?id=6256&whence=
```

### ✅ Successful Query

```
Found 3 open vendor bills for Wego MENA:
- BILL-004 (AED 45,000 | due 2026-06-15)
- BILL-005 (AED 32,000 | due 2026-06-20)
- BILL-006 (AED 18,500 | due 2026-06-25)
```

### ❌ Failed Write (with error)

```
❌ Failed to create employee:
Error while accessing a resource. There is already an employee with external access to this account using that entity name.

Fix: Use a different entity ID (e.g., NOVA-EMP-002) and try again.
```

## When This Applies

- **All Slack channels:** `#netsuite_ap`, `#netsuite_ar`, `#netsuite_gl_and_reporting`, `#netsuite_tax`, `#netsuite_ota`, `#netsuite_champion`
- **All tool calls:** `create_record`, `update_record`, `read_record`, `run_suiteql`, `metadata_catalog`
- **Exception:** If Claude is running a silent background query (not triggered by a user message), don't post—just log the result internally

## Integration with CLAUDE.md Rules

This mandate is **consistent with, not an override of**, `CLAUDE.md`:

- **§0.1 (One message):** This IS that one message. No separate narration.
- **§0.2 (Execution discipline):** After you call the tool, you surface it. No silent retries.
- **§5.2 (No fake execution):** Real API response → real URL and ID. This ensures you never fake a success.
- **§9 (Logging):** Same message that goes to Slack ALSO gets logged to `memory/knowledge/action_tracker.md`.

## Implementation Checklist for Claude

When you call a NetSuite tool in Slack:

- [ ] Tool call completes (success or error)
- [ ] Extract status, ID, URL from tool result
- [ ] Format one-line summary (see Examples above)
- [ ] Post to Slack in the originating channel/thread
- [ ] Log to `memory/knowledge/action_tracker.md`
- [ ] Do NOT post a second message, do NOT ask "shall I proceed", do NOT narrate your thinking

## Automated Enforcement (Future)

Once this is in place, OpenClaw's Slack gateway will validate:
- If Claude calls a NetSuite MCP tool in a Slack channel, it expects a public-channel reply within 30 seconds
- If no reply is posted, the gateway logs it as "tool result surfaced: FALSE" in the audit log
- If this happens repeatedly, Nikhil is notified

## Troubleshooting

**If you (Claude) find yourself posting a success message but no tool was actually called:**
- Stop immediately
- Re-read `CLAUDE.md §5.2` and §5.3
- Post a correction in the same thread: "I need to correct my previous message — I will now make the actual API call."
- Call the tool
- Post the real result

**If a user reports that a record was "created but I got no confirmation":**
- Query NetSuite to verify the record exists
- If it does: post a confirmation with the real ID and URL from NetSuite
- If it doesn't: post "Not found in NetSuite; may have been rolled back or created under a different ID."
- Log the incident as a "Silent Tool Response" failure in `memory/knowledge/cron_resilience.md`

---

End of mandate. Effective immediately. Load this file in all NetSuite-context sessions before responding.
