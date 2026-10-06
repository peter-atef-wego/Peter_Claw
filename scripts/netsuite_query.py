#!/usr/bin/env python3
"""
netsuite_query.py — Direct NetSuite SuiteQL/REST execution via OAuth 1.0a TBA.

Used by the agent when Oracle MCP gateway tools are not available in the
tool list. Loads credentials from environment, generates OAuth 1.0a
HMAC-SHA256 header, executes via curl subprocess.

Read operations (against prod or sandbox):
    python3 netsuite_query.py --scope prod --query "SELECT id, name FROM subsidiary"
    python3 netsuite_query.py --scope sandbox --query "SELECT id FROM vendor WHERE rownum <= 5"
    python3 netsuite_query.py --scope prod --record customer --id 2252

Write operations (SANDBOX ONLY — prod writes are refused):
    python3 netsuite_query.py --scope sandbox --create vendor \\
        --body '{"companyname": "Acme Travel", "subsidiary": {"id": "2"}}'
    python3 netsuite_query.py --scope sandbox --update vendor --id 12345 \\
        --body '{"email": "ap@acme.example"}'

Write-mode output (success):
    {"ok": true, "status": 204, "internal_id": "12345",
     "location": "https://5564218-sb1.suitetalk.api.netsuite.com/.../12345",
     "body": null}

Write-mode output (failure):
    {"ok": false, "status": 400, "error": {...NetSuite error...}}

The internal_id and location are extracted from the Location response header.
Use them to construct the user-facing app URL per the URL templates in
skills/wego-netsuite/MEMORY.md §A.2.

PROD WRITE PROTECTION: any --create / --update with --scope prod is refused
client-side. Production role is read-only at NetSuite end (the role would
403 anyway); this script-level check is defense in depth so even a
confused agent cannot accidentally attempt a prod mutation.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets as secrets_mod
import subprocess
import sys
import time
import urllib.parse


def url_form(account_id: str) -> str:
    """For URL hosts: '5564218_SB1' → '5564218-sb1'"""
    return account_id.strip().lower().replace("_", "-")


def realm_form(account_id: str) -> str:
    """For OAuth realm: '5564218-sb1' → '5564218_SB1'"""
    return account_id.strip().upper().replace("-", "_")


def _pct(s: str) -> str:
    """RFC 3986 percent-encode (safe chars: -._~)"""
    return urllib.parse.quote(str(s), safe="-._~")


def oauth_header(method: str, url: str, client_id: str, client_secret: str,
                 token_id: str, token_secret: str, account_id: str) -> str:
    """Generate OAuth 1.0a HMAC-SHA256 Authorization header for NetSuite TBA."""
    oauth_params = {
        "oauth_consumer_key": client_id,
        "oauth_token": token_id,
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets_mod.token_hex(16),
        "oauth_version": "1.0",
    }

    parsed = urllib.parse.urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    all_params = list(oauth_params.items()) + query_params
    all_params.sort()
    param_string = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in all_params)

    base_string = "&".join([method.upper(), _pct(base_url), _pct(param_string)])
    signing_key = f"{_pct(client_secret)}&{_pct(token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature

    header_parts = [f'realm="{realm_form(account_id)}"']
    for k, v in sorted(oauth_params.items()):
        header_parts.append(f'{_pct(k)}="{_pct(v)}"')
    return "OAuth " + ", ".join(header_parts)


def get_credentials(scope: str) -> dict:
    """Load credentials from environment for given scope (prod/sandbox)."""
    if scope in ("prod", "production"):
        prefix = "NETSUITE_PRODUCTION"
    else:
        prefix = "NETSUITE_SANDBOX"

    return {
        "account_id": os.environ.get(f"{prefix}_ACCOUNT_ID", ""),
        "client_id": os.environ.get(f"{prefix}_CLIENT_ID", ""),
        "client_secret": os.environ.get(f"{prefix}_CLIENT_SECRET", ""),
        "token_id": os.environ.get(f"{prefix}_TOKEN_ID", ""),
        "token_secret": os.environ.get(f"{prefix}_TOKEN_SECRET", ""),
    }


def execute_suiteql(query: str, scope: str = "prod") -> dict:
    """Execute a SuiteQL query against NetSuite."""
    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/query/v1/suiteql"

    auth = oauth_header("POST", url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])

    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        "-d", json.dumps({"q": query}),
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout) if result.stdout else {"error": result.stderr}


def execute_get(record_type: str, record_id: str = None, scope: str = "prod") -> dict:
    """Execute a GET request against NetSuite Record API."""
    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/record/v1/{record_type}"
    if record_id:
        url += f"/{record_id}"

    auth = oauth_header("GET", url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])

    cmd = [
        "curl", "-s", "-X", "GET",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout) if result.stdout else {"error": result.stderr}


def execute_write(method: str, record_type: str, body: dict, scope: str,
                  record_id: str = None) -> dict:
    """POST (create) or PATCH (update) against NetSuite Record API.

    Refuses with WRITE_TO_PROD_FORBIDDEN if scope is prod — the production
    role is read-only at NetSuite end, this is defense in depth so a
    confused agent cannot accidentally attempt a mutation against prod.

    On success returns {"ok": true, "status": 2xx, "internal_id": "...",
    "location": "...", "body": ...}. The internal_id comes from the
    Location response header.

    On failure returns {"ok": false, "status": N, "error": "..."}.
    """
    if scope in ("prod", "production"):
        return {
            "ok": False,
            "status": 0,
            "error": "WRITE_TO_PROD_FORBIDDEN",
            "message": (
                f"Refusing {method} to production. Writes route to sandbox "
                f"only (use --scope sandbox). Production role is read-only "
                f"at NetSuite end; this client-side check is defense in depth."
            ),
        }

    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/record/v1/{record_type}"
    if record_id:
        url += f"/{record_id}"

    auth = oauth_header(method, url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])

    cmd = [
        "curl", "-s", "-i",
        "-X", method,
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        "-d", json.dumps(body),
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    raw = result.stdout or ""

    if "\r\n\r\n" in raw:
        headers_block, _, body_block = raw.partition("\r\n\r\n")
    else:
        headers_block, _, body_block = raw.partition("\n\n")

    status_code = 0
    if headers_block:
        first_line = headers_block.splitlines()[0]
        parts = first_line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])

    location = None
    for line in headers_block.splitlines():
        if line.lower().startswith("location:"):
            location = line.split(":", 1)[1].strip()
            break

    new_id = location.rstrip("/").split("/")[-1] if location else None

    body_json = None
    if body_block.strip():
        try:
            body_json = json.loads(body_block)
        except json.JSONDecodeError:
            pass

    if 200 <= status_code < 300:
        return {
            "ok": True,
            "status": status_code,
            "internal_id": new_id,
            "location": location,
            "body": body_json,
        }

    return {
        "ok": False,
        "status": status_code,
        "error": body_json if body_json else (body_block or result.stderr or "no response body"),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Execute NetSuite queries via TBA OAuth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  Reads:\n"
            "    --scope prod --query 'SELECT id, name FROM subsidiary'\n"
            "    --scope prod --record vendorbill --id 12345\n"
            "  Writes (sandbox only — prod is refused):\n"
            "    --scope sandbox --create vendor --body '{\"companyname\": \"X\", \"subsidiary\": {\"id\": \"2\"}}'\n"
            "    --scope sandbox --update vendor --id 12345 --body '{\"email\": \"x@y.com\"}'\n"
        ),
    )
    ap.add_argument("--scope", choices=["prod", "sandbox"], default="prod")
    ap.add_argument("--query", help="SuiteQL query to execute (READ).")
    ap.add_argument("--record", help="Record type for GET request (READ).")
    ap.add_argument("--id", help="Record internal ID (used with --record GET, or --update PATCH).")
    ap.add_argument("--create", help="Record type for POST (WRITE — sandbox only). Requires --body.")
    ap.add_argument("--update", help="Record type for PATCH (WRITE — sandbox only). Requires --id and --body.")
    ap.add_argument("--body", help="JSON body string for --create / --update.")
    args = ap.parse_args()

    if args.create or args.update:
        if not args.body:
            print(json.dumps({"ok": False, "error": "MISSING_BODY",
                              "message": "--create/--update require --body '<json>'"}, indent=2))
            sys.exit(2)
        try:
            body = json.loads(args.body)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": "INVALID_BODY_JSON",
                              "message": str(e)}, indent=2))
            sys.exit(2)

        if args.update and not args.id:
            print(json.dumps({"ok": False, "error": "MISSING_ID",
                              "message": "--update requires --id"}, indent=2))
            sys.exit(2)

        if args.create:
            result = execute_write("POST", args.create, body, args.scope)
        else:
            result = execute_write("PATCH", args.update, body, args.scope,
                                   record_id=args.id)
    elif args.query:
        result = execute_suiteql(args.query, args.scope)
    elif args.record:
        result = execute_get(args.record, args.id, args.scope)
    else:
        ap.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
