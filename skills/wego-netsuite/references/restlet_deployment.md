# RESTlet companion — deployment

NetSuite's standard REST API does **not** expose Saved Searches or the File Cabinet ([source: Tim Dietrich](https://timdietrich.me/blog/netsuite-saved-search-api/), [Coefficient](https://coefficient.io/use-cases/netsuite-rest-api-vs-saved-searches-transactions)). If Oracle's NetSuite MCP Standard Tools doesn't cover saved-searches / file-cabinet either (TBC at runtime — `list_record_types()` will tell us), the Champion falls back to a small SuiteScript 2.1 RESTlet that exposes both.

**Source (deploy this file as-is):** [`./restlet_companion.js`](./restlet_companion.js) — the canonical (and only) copy in the repo. Paste it into NetSuite's SuiteScript editor; no edits needed.

Auth on inbound RESTlet calls uses the **same TBA token-pair** Oracle's MCP already uses for the standard REST API — no new credentials needed.

---

## Endpoints exposed

| Action | What it does |
|---|---|
| `saved_search` | `search.load({id})` + paginated `runPaged` → returns rows (max 5 000) |
| `file_get` | `file.load({id})` → returns base64 contents + metadata |
| `file_put` | `file.create(...)` → uploads a file to a folder, returns the new id |
| `role_permissions` | `record.load('role')` → returns per-role permission grid (Role × record-type × Level). Cap = 50 roles per call. Used by the `get_role_permissions` MCP tool to answer permission-grid asks that SuiteQL + REST Record API both block. |

Caller payload (POST body, JSON):

```json
{"action": "saved_search", "search_id": "customsearch_finance_open_bills",
 "params": {"page_size": 1000, "row_cap": 5000}}
```

For `role_permissions`:

```json
{"action": "role_permissions", "role_ids": ["1042", "1043"], "include_inactive": false}
```

Omit `role_ids` to fetch all active roles (capped at 50).

Response shape:

```json
{"ok": true, "action": "saved_search", "search_id": "...",
 "row_count": 138, "rows": [...]}
```

Error shape:

```json
{"ok": false, "error_code": "missing_search_id", "error": "search_id is required"}
```

---

## Updating an already-deployed RESTlet (when adding a new action)

If you already have the companion deployed and the env vars set (the `NETSUITE_<SCOPE>_RESTLET_*` pair), adding a new `action` to the script is a one-step update — no new Script record, no new Deployment, no env-var change, no OpenClaw container restart:

1. In NetSuite UI: **Documents → Files → SuiteScripts**.
2. Open the deployed `restlet_companion.js`.
3. Click **Edit → Choose File** and upload the updated `skills/wego-netsuite/references/restlet_companion.js` from the repo.
4. Save.

NetSuite uses the new code on the next call. Validate via the smoke test below.

## First-time deployment (or after full removal)

1. **Upload the script.** In NetSuite UI: *Customisation → Scripting → Scripts → New*. Upload `skills/wego-netsuite/references/restlet_companion.js`. Set the script type to **RESTlet**.
2. **Configure the script.**
   - Name: `Champion RESTlet Companion`
   - ID: `customscript_champion_restlet`
   - API Version: 2.1
3. **Deploy it.** *Deploy Script* → New Deployment.
   - ID: `customdeploy_champion_restlet`
   - Status: Released
   - Audience → Roles: include the role used by the TBA token-pair (the staging-admin role on prod, the sandbox-admin on sandbox)
   - Log level: Debug while testing, Audit in steady state
4. **Note the IDs.** From the deployment page URL or external id field, capture:
   - script id (e.g. `customscript_champion_restlet` or numeric `1234`)
   - deployment id (e.g. `customdeploy_champion_restlet` or numeric `1`)
5. **Capture the IDs** from the deployment record (e.g. `customscript_openclaw_restlet_companion` + `customdeploy_openclaw_rt_companion`).

6. **Store on AlphaBot.** AWS Secrets Manager `alphabot-production` is the preferred location (matches the Finance Reco pattern):

   | AWS field name | Example value |
   |---|---|
   | `netsuite_production_restlet_script_id` | `customscript_openclaw_restlet_companion` |
   | `netsuite_production_restlet_deployment_id` | `customdeploy_openclaw_rt_companion` |

   Env-var equivalents (uppercase of the same names):

   | Env var | Example value |
   |---|---|
   | `NETSUITE_PRODUCTION_RESTLET_SCRIPT_ID` | `customscript_openclaw_restlet_companion` |
   | `NETSUITE_PRODUCTION_RESTLET_DEPLOYMENT_ID` | `customdeploy_openclaw_rt_companion` |

## Deploy in sandbox (5564218-sb1)

Repeat steps 1–5 in sandbox (status **Released**, audience = sandbox-admin TBA role only). Then:

| AWS field | Example value |
|---|---|
| `netsuite_sandbox_restlet_script_id` | `customscript_openclaw_restlet_companion` |
| `netsuite_sandbox_restlet_deployment_id` | `customdeploy_openclaw_rt_companion_sbx` |

Or env-var equivalents:

| Env var | Example value |
|---|---|
| `NETSUITE_SANDBOX_RESTLET_SCRIPT_ID` | `customscript_openclaw_restlet_companion` |
| `NETSUITE_SANDBOX_RESTLET_DEPLOYMENT_ID` | `customdeploy_openclaw_rt_companion_sbx` |

---

## Smoke-test

From the Champion in `#netsuite_champion` (or any of the five domain channels), ask:

> @Data Automation's Claw run saved search `customsearch_my_test_saved_search`

Expected: the bot calls `run_saved_search` via Oracle's MCP (which forwards to the RESTlet) and returns rows. If you get `RESTlet not deployed` or `script_id missing`, the script/deployment IDs aren't wired into the MCP server's config yet — Akansha needs to add them.

The legacy Python CLI smoke test (`test_netsuite_tba.py`) has been removed along with the rest of `test_py/netsuite-mcp/` on 2026-05-12. All verification now happens through the Slack/MCP path above.

---

## Permissions on the RESTlet role

Whichever role is used for the TBA token-pair must have:
- **Web Services** permission (Full)
- **REST Web Services** permission (Full)
- **Lists / Documents and Files** (View at minimum, Edit if you want `file_put`)
- View access on the records the Saved Searches read

The script does NOT bypass NetSuite's row-level permission model — Saved Searches still respect role visibility. If finance shares a Saved Search to the Admin role only, the Champion can't run it under a Read-Only role.

---

## File-size and pagination caps

- RESTlet response body cap: ~10 MB. The companion returns up to 5 000 rows by default; raise `params.row_cap` in the call if needed but watch the response size.
- File Cabinet `file.getContents()` returns the whole file in memory — anything > 10 MB will fail with `RCRD_DSNT_EXIST` or governance error. For larger files, retrieve the file URL and download out of band.

---

## Why a RESTlet (not pure REST)

Two things only RESTlets can do:

1. **Saved Searches** — finance teams build dozens of them in the UI; reproducing them in SuiteQL would be a full porting effort and lose drill-down links.
2. **File Cabinet** — the standard REST API has no `/file` resource. RESTlets can call `N/file`.

Once these are deployed once per account, they don't change. They are write-once infra, not part of the iterative Champion code.
