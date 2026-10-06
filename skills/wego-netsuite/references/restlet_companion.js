/**
 * NetSuite Champion — RESTlet companion (SuiteScript 2.1)
 *
 * Deploy this as a RESTlet in BOTH the production and sandbox accounts.
 * Records the script id + deployment id under the AWS secret keys:
 *   - ns_prod_restlet_script_id     ns_prod_restlet_deploy_id
 *   - ns_sandbox_restlet_script_id  ns_sandbox_restlet_deploy_id
 *
 * Exposes endpoints the standard REST API can't reach:
 *   1. action='saved_search'     — run a Saved Search by id, return rows
 *   2. action='file_get'         — fetch a File Cabinet file (b64 + meta)
 *   3. action='file_put'         — upload a file to the File Cabinet
 *   4. action='role_permissions' — fetch per-role permission grid
 *                                  (Role × record-type × Level) — blocked
 *                                  from SuiteQL + REST Record API for the
 *                                  integration role; record.load('role')
 *                                  CAN see the permissions sublist.
 *
 * Auth on the inbound RESTlet call uses the same TBA token-pair the
 * gateway uses for the standard REST API — no new credentials needed.
 *
 * Deployment instructions: see references/restlet_deployment.md
 *
 * @NApiVersion 2.1
 * @NScriptType Restlet
 */
define(['N/record', 'N/search', 'N/file', 'N/log'], function (record, search, file, log) {

    var ROLE_PERMISSIONS_MAX_ROLES = 50;

    function post(payload) {
        try {
            var action = payload && payload.action;
            switch (action) {
                case 'saved_search':
                    return runSavedSearch(payload);
                case 'file_get':
                    return getFile(payload);
                case 'file_put':
                    return putFile(payload);
                case 'role_permissions':
                    return getRolePermissions(payload);
                default:
                    return error('unknown_action', 'unknown action: ' + action);
            }
        } catch (e) {
            log.error('restlet_companion', e);
            return error('exception', String(e));
        }
    }

    function runSavedSearch(payload) {
        var id = payload.search_id;
        if (!id) return error('missing_search_id', 'search_id is required');

        var ss = search.load({ id: id });

        // Optional runtime filter overrides.
        if (payload.params && payload.params.filters) {
            try {
                ss.filterExpression = payload.params.filters;
            } catch (e) {
                // older NS versions: append filters via .filters
                log.audit('saved_search_filter_override_failed', String(e));
            }
        }

        var pageSize = Math.min(payload.params && payload.params.page_size || 1000, 1000);
        var pages = ss.runPaged({ pageSize: pageSize });
        var rows = [];
        var cap = payload.params && payload.params.row_cap || 5000;

        pages.pageRanges.forEach(function (pr) {
            if (rows.length >= cap) return;
            var page = pages.fetch({ index: pr.index });
            page.data.forEach(function (r) {
                if (rows.length >= cap) return;
                var obj = { id: r.id };
                r.columns.forEach(function (col) {
                    var key = col.label || (col.summary ?
                        (col.summary + '_' + col.name) : col.name);
                    obj[key] = r.getValue(col);
                    var txt = r.getText(col);
                    if (txt && txt !== obj[key]) obj[key + '_text'] = txt;
                });
                rows.push(obj);
            });
        });

        return { ok: true, action: 'saved_search', search_id: id,
                 row_count: rows.length, rows: rows };
    }

    function getFile(payload) {
        var id = payload.file_id;
        if (!id) return error('missing_file_id', 'file_id is required');
        var f = file.load({ id: id });
        return {
            ok: true, action: 'file_get',
            id: f.id,
            name: f.name,
            folder: f.folder,
            file_type: f.fileType,
            size: f.size,
            url: f.url,
            mime: f.fileType,
            // Files >10MB will overflow RESTlet response cap (10MB).
            // Caller should check `size` before requesting if uncertain.
            content_b64: f.getContents()  // already base64 for binary types
        };
    }

    function putFile(payload) {
        var name = payload.name;
        var folder = payload.folder;
        var contentB64 = payload.content_b64;
        var fileType = payload.file_type || file.Type.PLAINTEXT;
        if (!name || !folder || !contentB64) {
            return error('missing_fields', 'name, folder, content_b64 required');
        }
        var f = file.create({
            name: name,
            fileType: fileType,
            contents: contentB64,
            folder: folder,
            isOnline: false
        });
        var id = f.save();
        return { ok: true, action: 'file_put', id: id, name: name, folder: folder };
    }

    function error(code, msg) {
        return { ok: false, error_code: code, error: msg };
    }

    // ── role_permissions ────────────────────────────────────────────────
    // Returns the per-role permission grid. N/record.load('role') is the
    // only API surface that can see the permissions sublist for the
    // integration role — SuiteQL and the REST Record API both block it.
    //
    // Payload (POST body):
    //   {
    //     "action": "role_permissions",
    //     "role_ids": ["1042", "1043"],          // optional; default = all active
    //     "include_inactive": false              // optional; default false
    //   }
    //
    // Response:
    //   { "ok": true, "action": "role_permissions", "count": N,
    //     "roles": [{role_id, role_name, centertype, isinactive,
    //                permissions: [{permission_key, permission_name,
    //                               level, restriction}, ...]}, ...] }
    function getRolePermissions(payload) {
        var includeInactive = !!(payload && payload.include_inactive);
        var roleIds = null;

        if (payload && payload.role_ids) {
            if (Object.prototype.toString.call(payload.role_ids) === '[object Array]') {
                roleIds = payload.role_ids;
            } else {
                roleIds = String(payload.role_ids).split(',');
            }
            roleIds = roleIds.map(function (s) { return String(s).trim(); })
                             .filter(function (s) { return s.length > 0; });
            if (roleIds.length > ROLE_PERMISSIONS_MAX_ROLES) {
                return error('too_many_roles',
                    'Cap is ' + ROLE_PERMISSIONS_MAX_ROLES +
                    ' role_ids per call. Got ' + roleIds.length + '. Page the call.');
            }
        } else {
            roleIds = rpListActiveRoles(includeInactive);
            if (roleIds.length > ROLE_PERMISSIONS_MAX_ROLES) {
                return error('too_many_active_roles',
                    'Active role count (' + roleIds.length +
                    ') exceeds cap of ' + ROLE_PERMISSIONS_MAX_ROLES +
                    '. Pass role_ids explicitly to page.');
            }
        }

        var roles = [];
        for (var i = 0; i < roleIds.length; i++) {
            roles.push(rpLoadRole(roleIds[i]));
        }
        return {
            ok: true,
            action: 'role_permissions',
            count: roles.length,
            roles: roles
        };
    }

    function rpListActiveRoles(includeInactive) {
        var ids = [];
        var filters = [];
        if (!includeInactive) {
            filters.push(['isinactive', 'is', 'F']);
        }
        var sr = search.create({
            type: search.Type.ROLE,
            filters: filters,
            columns: [{ name: 'internalid', sort: search.Sort.ASC }]
        });
        sr.run().each(function (result) {
            ids.push(result.id);
            return true;
        });
        return ids;
    }

    function rpLoadRole(roleId) {
        try {
            var rec = record.load({ type: record.Type.ROLE, id: roleId });
            return {
                role_id: String(roleId),
                role_name: rec.getValue({ fieldId: 'name' }) || '',
                centertype: rec.getValue({ fieldId: 'centertype' }) || '',
                issalesrole: rec.getValue({ fieldId: 'issalesrole' }) || 'F',
                isinactive: rec.getValue({ fieldId: 'isinactive' }) || 'F',
                restrictbydevice: rec.getValue({ fieldId: 'restrictbydevice' }) || 'F',
                permission_count: rpCountPermissions(rec),
                permissions: rpExtractPermissions(rec)
            };
        } catch (e) {
            return {
                role_id: String(roleId),
                error: 'role_load_failed',
                message: String(e && e.message ? e.message : e)
            };
        }
    }

    function rpCountPermissions(rec) {
        try {
            return rec.getLineCount({ sublistId: 'permissions' });
        } catch (e) { return 0; }
    }

    function rpExtractPermissions(rec) {
        var perms = [];
        var count = rpCountPermissions(rec);
        for (var i = 0; i < count; i++) {
            try {
                perms.push({
                    permission_key: rec.getSublistValue({
                        sublistId: 'permissions', fieldId: 'permkey', line: i
                    }) || '',
                    permission_name: rec.getSublistText({
                        sublistId: 'permissions', fieldId: 'permkey', line: i
                    }) || '',
                    level: rec.getSublistText({
                        sublistId: 'permissions', fieldId: 'permlevel', line: i
                    }) || '',
                    restriction: rec.getSublistText({
                        sublistId: 'permissions', fieldId: 'restriction', line: i
                    }) || ''
                });
            } catch (e) {
                // skip a bad row, continue
            }
        }
        return perms;
    }

    return { post: post };
});
