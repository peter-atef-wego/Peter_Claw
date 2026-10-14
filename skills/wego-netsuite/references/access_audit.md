# Access audit — exporting users, roles, and assignments

How the NetSuite Champion handles "give me a list of users / roles / who has access" requests. The canonical entry point is the `export_access_audit` tool — it bundles three SuiteQL exports into one atomic call with per-query status.

This document covers:

1. What `export_access_audit` produces (and what it doesn't)
2. The exact SuiteQL queries it runs
3. Why the permission grid isn't here — and how to get it
4. How to extend the audit to additional tables

---

## 1. What you get from one call

`export_access_audit(scope="prod")` runs three SuiteQL exports in parallel-ish (sequential, but independent — one failure does NOT abort the others) and returns:

```json
{
  "ok": true,
  "scope": "prod",
  "results": {
    "users":         { "ok": true, "file_path": "...ns_access_users_<ts>.csv",
                       "row_count": 403, "preview": [...], "label": "..." },
    "roles":         { "ok": true, "file_path": "...ns_access_roles_<ts>.csv",
                       "row_count": 62,  "preview": [...], "label": "..." },
    "user_role_map": { "ok": true, "file_path": "...ns_access_user_role_map_<ts>.csv",
                       "row_count": 1183,"preview": [...], "label": "..." }
  },
  "permission_grid_note": "Per-role permission grid (Role × record-type × View/Edit/Full) is NOT exportable via SuiteQL — …",
  "summary": "✅ Access audit exported — 3/3 CSVs written. Users: 403, Roles: 62, User×Role: 1183."
}
```

If one query fails (most commonly the user-role map under a restrictive integration role), `ok` stays `true` as long as at least one CSV was written, and the failed query is named in `summary` with its verbatim NetSuite error.

### Three CSVs, what's in each

| CSV | Columns | Row count (typical) | Purpose |
|---|---|---|---|
| `ns_access_users_<ts>.csv` | id, entityid, firstname, lastname, email, title, giveaccess, isinactive, subsidiary | ~400 | One row per employee with login enabled |
| `ns_access_roles_<ts>.csv` | id, name, centertype, issalesrole, isinactive, restrictbydevice | ~60 | One row per active role definition (metadata only) |
| `ns_access_user_role_map_<ts>.csv` | user_id, user_name, user_email, role_id, role_name, centertype | ~1000+ | One row per (user × role) — a user with 3 roles appears 3 times |

---

## 2. The SuiteQL queries

Source of truth: `_ACCESS_AUDIT_QUERIES` in `scripts/netsuite_mcp_server.py`. Reproduced here for review and debug.

### Users (login-enabled, active)

```sql
SELECT
  e.id,
  e.entityid,
  e.firstname,
  e.lastname,
  e.email,
  e.title,
  e.giveaccess,
  e.isinactive,
  (SELECT s.name FROM subsidiary s WHERE s.id = e.subsidiary) AS subsidiary
FROM employee e
WHERE e.giveaccess = 'T'
  AND e.isinactive = 'F'
ORDER BY e.entityid
```

`giveaccess = 'T'` is the canonical "login enabled" flag. An employee can exist with `giveaccess = 'F'` (terminated, contractor without login, etc.) — those are filtered out.

### Roles (active, metadata only)

```sql
SELECT
  r.id,
  r.name,
  r.centertype,
  r.issalesrole,
  r.isinactive,
  r.restrictbydevice
FROM role r
WHERE r.isinactive = 'F'
ORDER BY r.name
```

This is the metadata table only — name, center, sales-flag, device-restriction. **Permission lines are NOT here.** See §3.

### User × role assignment map

```sql
SELECT
  er.employee AS user_id,
  e.entityid  AS user_name,
  e.email     AS user_email,
  er.role     AS role_id,
  r.name      AS role_name,
  r.centertype
FROM employeeroles er
JOIN employee e ON er.employee = e.id
JOIN role r     ON er.role     = r.id
WHERE e.giveaccess = 'T'
  AND e.isinactive = 'F'
  AND r.isinactive = 'F'
ORDER BY e.entityid, r.name
```

`employeeroles` is the working table at Wego (verified live 2026-05-22 — the bot resolved 33 custom role names against this exact join). The plural-suffixed `employeerolesforsearch` is the canonical SuiteQL view name in other NetSuite editions but is NOT exposed in Wego's integration role — calling it returns `Record 'employeerolesforsearch' was not found`. If a future role/edition change breaks this leg, the per-query status in the response surfaces it cleanly while the other two CSVs still deliver; the agent should then use `discover_table` to probe for the local equivalent (`employee_role`, `usertoroles`, etc.).

---

## 3. The permission grid — what's NOT in this export, and how to get it

**Hard limit.** NetSuite does NOT expose the per-role permission grid (Role × record-type × View/Create/Edit/Full/None) via SuiteQL. The `role` record's permission lines are not queryable.

The `export_access_audit` response includes a `permission_grid_note` that says exactly this — so the agent always surfaces the gap rather than fabricating an answer.

### How to get the permission grid (admin paths only)

| Path | Who | Time | What you get |
|---|---|---|---|
| Setup → Users/Roles → Manage Roles → Export List | Akansha | 1 min | Basic role list (mostly same as our `roles` CSV — limited value over what we already have) |
| Saved Search of type "Role" with permission columns added | Akansha | 5–10 min | The full Role × Permission × Level matrix |
| SuiteScript dump: `nlapiLoadRecord('role', id)` → iterate `permissions` sublist → CSV | Akansha | 30 min one-time build | Full matrix, scriptable, can be re-run |

The agent's job here is to **name the gap clearly** in the Slack reply, with the unblocker explicit:

> *"Permission grid (Role × record-type × View/Edit/Full) is not in SuiteQL — Akansha needs to export it from NetSuite admin. Tagged her in #netsuite_adminsupport."*

---

## 4. Extending the audit — adding a fourth or fifth table

If you find yourself wanting to add, say, "active integrations with their role bindings" or "login history for the last 30 days," edit `_ACCESS_AUDIT_QUERIES` in `scripts/netsuite_mcp_server.py`. The pattern is:

```python
{
    "key": "integrations",                       # short stable identifier
    "label": "Active integrations + their assigned role",
    "filename": "ns_access_integrations",        # _<timestamp>.csv appended
    "sql": "SELECT i.id, i.name, i.state, ..."
            " FROM integration i WHERE i.state = 'enabled' ORDER BY i.name",
},
```

The executor (`execute_export_access_audit`) loops the list. Adding a query doesn't require any changes to the dispatch logic, the tool schema, or the operating rules — the rule says "atomic delivery of N CSVs," and N is just the length of this list.

---

## 5. The agent flow for an access-audit request

When a user in `#netsuite_champion` (or any of the NetSuite channels) asks for users / roles / access:

1. **Recognise the intent.** Phrases that route to `export_access_audit`:
   - *"export all users / all roles / who has access"*
   - *"user listing", "role listing", "access audit"*
   - *"who's in NetSuite production"*
   - *"give me users and roles and assignments"*
2. **Call `export_access_audit(scope="prod")`.** ONE tool call, three CSVs.
3. **For each `ok=true` result, call `upload_file_to_slack`** with the channel/thread of the user's message. Three uploads, one reply.
4. **Build ONE Slack reply** per §0.1 with this structure:

   ```
   ✅ Access audit — 3/3 CSVs uploaded above.
   • users.csv — 403 active users with login enabled
   • roles.csv — 62 active roles (metadata only)
   • user_role_map.csv — 1,183 user × role assignments

   📝 Permission grid (Role × record-type × View/Edit/Full) is not in SuiteQL —
      Akansha exports it via Setup → Users/Roles → Manage Roles or a Role
      Saved Search. Tag her if you need the full matrix.
   ```

5. **If any of the three failed**, list the failure with the verbatim NS error and the unblocker — never omit it.

This pattern is enforced by §5.15 (multi-part atomic delivery) and §5.17 (always respond).

## 6. Follow-up asks: permission-level filters — use `get_role_permissions`

After the initial audit delivers, users often follow up with permission-level filters:

- *"Give me roles with Edit functionality, not Customize."*
- *"Which roles can approve bills?"*
- *"Show me everyone who can post journals."*

**These are answerable** — via the `get_role_permissions` MCP tool, which POSTs to the existing `restlet_companion.js` (action `role_permissions`). SuiteQL and the REST Record API can't reach this data, but `N/record.load('role')` inside SuiteScript can.

**The agent flow:**

1. Call `get_role_permissions(role_ids=None)` to fetch all active roles + their permission lines.
2. Filter / aggregate locally to answer the specific question (e.g. "roles with `level='Edit'` on `permission_key='TRAN_VENDBILL'`").
3. Write the result to CSV via `export_suiteql_to_csv` if >20 rows; upload via `upload_file_to_slack`.
4. Reply with ONE message, filtered answer + file attachment.

**Stale-handler fallback (§5.18):** If `get_role_permissions` returns `RESTLET_HANDLER_STALE`, the deployed `restlet_companion.js` predates the `role_permissions` action. The correct reply is short:

> *"The role_permissions handler isn't in the deployed RESTlet yet — replace the File Cabinet copy of `restlet_companion.js` with the latest from `skills/wego-netsuite/references/restlet_companion.js`. ~1 min, no env change, no redeploy, no restart. NetSuite uses the new code on the next call."*

What you DO NOT do: dump the unfiltered 33-role list from CSV (b) "in case it's useful." The user already has it. Re-dumping it buries the real answer (the unblocker) under irrelevant data — that's the §5.18 substitute-dump anti-pattern.
