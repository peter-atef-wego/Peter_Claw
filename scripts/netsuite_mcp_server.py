#!/usr/bin/env python3
"""
netsuite_mcp_server.py — MCP stdio server wrapping NetSuite OAuth queries.

Speaks the MCP protocol (JSON-RPC over stdin/stdout) and exposes:
  - run_suiteql: Execute SuiteQL queries
  - read_record: GET a record by type + ID
  - create_record: POST a new record (sandbox only)
  - update_record: PATCH an existing record (sandbox only)
  - metadata_catalog: GET metadata for a record type

Registered via: openclaw mcp set netsuite-prod '{"command":"python3","args":["scripts/netsuite_mcp_server.py"],"env":{"NETSUITE_SCOPE":"prod"}}'
"""

import json
import sys
import os
import logging
import csv
import re
from datetime import datetime

# Setup logging to file + stderr for debugging
log_dir = os.path.expanduser("~/.openclaw/logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "netsuite_mcp.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Add workspace to path for netsuite_query imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from netsuite_query import execute_suiteql, execute_get, get_credentials, oauth_header, url_form, realm_form, _pct

import subprocess
import base64
import hashlib
import hmac
import secrets as secrets_mod
import time
import urllib.parse


SCOPE = os.environ.get("NETSUITE_SCOPE", "prod")

# Canonical NetSuite UI URL paths — source of truth per Akansha (NetSuite developer).
# DO NOT CHANGE without re-confirming with Akansha. The bot MUST use the
# `ui_url` field returned by execute_create/update/get — it MUST NOT hand-construct
# URLs in its Slack reply. The 2026-05-19 BLP-OC12345 incident happened because the
# bot called create_record("vendorpayment", ...) correctly but then wrote a Slack
# URL with the vendbill.nl path. Trust the script's URL field.
RECORD_URL_PATHS = {
    # Transactions
    "invoice": "app/accounting/transactions/custinvc.nl",
    "creditmemo": "app/accounting/transactions/custcred.nl",
    "customerpayment": "app/accounting/transactions/custpymt.nl",
    "salesorder": "app/accounting/transactions/salesord.nl",
    "vendorbill": "app/accounting/transactions/vendbill.nl",
    "vendorpayment": "app/accounting/transactions/vendpymt.nl",
    "journalentry": "app/accounting/transactions/journal.nl",
    "vendorcredit": "app/accounting/transactions/vendcred.nl",
    "check": "app/accounting/transactions/check.nl",
    # Entities
    "vendor": "app/common/entity/vendor.nl",
    "customer": "app/common/entity/custjob.nl",
    "employee": "app/common/entity/employee.nl",
}

# Map common user-facing finance terms to the canonical NetSuite REST record type.
# If the agent passes one of these as record_type, the script rejects with a
# helpful "did you mean" error rather than POSTing a bogus type and either
# 404-ing or creating something else. The bot MUST learn the canonical names
# (see references/netsuite_record_types.md §5.1 translation table); this map is
# the safety net, not the primary teacher.
#
# Keys are normalized: lowercased, spaces and hyphens collapsed to nothing,
# then matched against the user input the same way. So "Bill Payment",
# "bill_payment", "bill-payment", "billpayment" all resolve to the same key.
RECORD_TYPE_ALIASES_TO_CANONICAL = {
    # Bill Payment / Vendor Payment family
    "billpayment": "vendorpayment",
    "billpay": "vendorpayment",
    "bp": "vendorpayment",
    "vendorpay": "vendorpayment",
    "vendpay": "vendorpayment",
    "vendpymt": "vendorpayment",
    "vendpybl": "vendorpayment",
    "paybill": "vendorpayment",
    "paybills": "vendorpayment",
    "payvendor": "vendorpayment",
    # Customer Payment / Receipt family
    "customerpay": "customerpayment",
    "custpymt": "customerpayment",
    "custpay": "customerpayment",
    "receipt": "customerpayment",
    "customerreceipt": "customerpayment",
    "receivepayment": "customerpayment",
    # Vendor Bill / AP Bill family
    "bill": "vendorbill",
    "vendbill": "vendorbill",
    "vendorinvoice": "vendorbill",
    "apinvoice": "vendorbill",
    "apbill": "vendorbill",
    "supplierbill": "vendorbill",
    "supplierinvoice": "vendorbill",
    # Customer Invoice / AR Invoice family
    "arinvoice": "invoice",
    "customerinvoice": "invoice",
    "custinvoice": "invoice",
    "custinvc": "invoice",
    # Credit Memo (customer side)
    "creditmemos": "creditmemo",
    "custcredit": "creditmemo",
    "customercredit": "creditmemo",
    "custcred": "creditmemo",
    "credit": "creditmemo",  # ambiguous but most common usage at Wego is AR
    # Vendor Credit (AP side)
    "vendcred": "vendorcredit",
    "suppliercredit": "vendorcredit",
    # Entities — common misspellings
    "custjob": "customer",
    "supplier": "vendor",
    "buyer": "customer",
    "worker": "employee",
    "staff": "employee",
    # Journal Entry
    "journal": "journalentry",
    "je": "journalentry",
    "jnl": "journalentry",
    "manualje": "journalentry",
    "gljournal": "journalentry",
    # Sales Order / Estimate
    "salesord": "salesorder",
    "so": "salesorder",
    "estimate": "salesorder",  # per Akansha's mapping
    "quote": "salesorder",
    "quotation": "salesorder",
    # Check
    "cheque": "check",
}


def _normalize_record_type_input(s):
    """Normalize a user-supplied record-type string for alias lookup.
    Lowercases, strips, removes spaces / underscores / hyphens.
    'Bill Payment' / 'bill_payment' / 'bill-payment' all → 'billpayment'.
    """
    if not s:
        return ""
    return (s or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

# Hosts per scope. URL host uses the lowercase-hyphen form (e.g. 5564218-sb1).
_HOSTS_UI = {
    "prod":        "5564218.app.netsuite.com",
    "production":  "5564218.app.netsuite.com",
    "sandbox":     "5564218-sb1.app.netsuite.com",
    "sb":          "5564218-sb1.app.netsuite.com",
}


def _canonical_record_type(record_type):
    """Map a passed record_type to the canonical NetSuite REST name.

    Lookup order:
      1. Exact lowercase match against RECORD_URL_PATHS (already canonical).
      2. Normalized (spaces/underscores/hyphens stripped) match against the
         alias map — catches 'Bill Payment', 'bill_payment', 'bill-payment',
         'billpayment' equivalently.
      3. Normalized match against RECORD_URL_PATHS (catches 'bill payment'
         style natural-language input even without an alias entry).
      4. Unknown — return the input as-is and let downstream handle.

    Returns (canonical_name, was_aliased) tuple.
    """
    raw = (record_type or "").strip().lower()
    if raw in RECORD_URL_PATHS:
        return raw, False

    normalized = _normalize_record_type_input(record_type)
    if normalized in RECORD_TYPE_ALIASES_TO_CANONICAL:
        return RECORD_TYPE_ALIASES_TO_CANONICAL[normalized], True
    if normalized in RECORD_URL_PATHS:
        # User passed "vendor bill" → normalizes to "vendorbill" which IS canonical;
        # accept and don't flag as aliased.
        return normalized, False

    return raw, False  # unknown — let NetSuite error out


def _build_ns_url(record_type, internal_id, scope="sandbox"):
    """Build the correct NetSuite UI URL for a record, scope-aware.

    scope ∈ {prod, production, sandbox, sb}. Defaults to sandbox.
    Falls back to a generic entity path if record_type is unknown (the bot
    should rarely hit this — RECORD_URL_PATHS covers the standard set).
    """
    host = _HOSTS_UI.get((scope or "sandbox").lower(), _HOSTS_UI["sandbox"])
    path = RECORD_URL_PATHS.get(record_type.lower(), f"app/common/entity/{record_type}.nl")
    return f"https://{host}/{path}?id={internal_id}&whence="


# ──────────────────────────────────────────────────────────────────────────────
# CSV-row → fully-resolved-dimensions resolver.
#
# Purpose: the bot was systematically dropping line-level dimensions
# (Department, Tax Code, BU Code, Location, Market Segment) when building
# vendorbill / journalentry create bodies — claiming "MCP doesn't expose
# direct IDs via SuiteQL in a straightforward way". That claim was a
# hallucination; the IDs are all queryable. This resolver takes the CSV
# row directly and looks up EVERY id server-side, returning either a
# complete resolved dict the caller can post, or a structured list of
# resolution errors. The bot can't silently skip fields it doesn't
# assemble.
# ──────────────────────────────────────────────────────────────────────────────

# Subsidiary name → tax-regime prefix. Determines the GST_SG: / VAT_AE: /
# VAT_SA: / GST_IN: / etc. prefix when composing the full purchasetaxitem /
# salestaxitem itemid. Source: dimension_aliases.md §9.
SUBSIDIARY_NAME_TO_REGIME_PREFIX = {
    "wego pte ltd": "GST_SG",
    "wego pte ltd (singapore)": "GST_SG",
    "wego fz-llc": "VAT_AE",
    "wego middle east": "VAT_AE",
    "wego saudi and tourism": "VAT_SA",
    "wego travel and tourism": "GST_PK",
    "wego travel s.a.e": "VAT_EG",
    "shopcash fz-llc": "VAT_AE",
    "wego india pvt ltd": "GST_IN",
}


def _sql_escape(value):
    """Single-quote-safe SuiteQL literal — doubles single quotes per Oracle SQL."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _ql(value):
    """Lower-case a string for case-insensitive matching."""
    return (value or "").strip().lower()


def _suiteql_first_row(query, scope):
    """Run a SuiteQL and return the first item dict, or None.
    Hides the network noise from the resolver functions below.
    """
    rs = execute_suiteql(query, scope=scope)
    if isinstance(rs, dict):
        items = rs.get("items") or (rs.get("data") or {}).get("items") or []
        if items:
            return items[0]
    return None


def _suiteql_all_rows(query, scope):
    rs = execute_suiteql(query, scope=scope)
    if isinstance(rs, dict):
        return rs.get("items") or (rs.get("data") or {}).get("items") or []
    return []


def _resolve_subsidiary(name, scope):
    """name → {id, name} or None. Tries exact match, then case-insensitive."""
    if not name:
        return None
    name = name.strip()
    row = _suiteql_first_row(
        f"SELECT id, name FROM subsidiary WHERE name = {_sql_escape(name)} AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "name": row.get("name")}
    # Case-insensitive fallback
    rows = _suiteql_all_rows(
        f"SELECT id, name FROM subsidiary WHERE UPPER(name) = UPPER({_sql_escape(name)}) AND isinactive = 'F'",
        scope,
    )
    if rows:
        return {"id": str(rows[0]["id"]), "name": rows[0].get("name")}
    return None


def _resolve_vendor(identifier, scope):
    """entityid (preferred) or companyname → vendor row. Returns None if no
    unique match. The bot should NEVER substitute another vendor."""
    if not identifier:
        return None
    identifier = identifier.strip()
    # Try entityid exact first
    row = _suiteql_first_row(
        f"SELECT id, entityid, companyname FROM vendor WHERE entityid = {_sql_escape(identifier)} AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "entityid": row.get("entityid"), "companyname": row.get("companyname")}
    # Try companyname exact
    row = _suiteql_first_row(
        f"SELECT id, entityid, companyname FROM vendor WHERE companyname = {_sql_escape(identifier)} AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "entityid": row.get("entityid"), "companyname": row.get("companyname")}
    # Substring fallback — but only return if exactly one match
    rows = _suiteql_all_rows(
        f"SELECT id, entityid, companyname FROM vendor WHERE UPPER(companyname) LIKE UPPER('%' || {_sql_escape(identifier)} || '%') AND isinactive = 'F' AND ROWNUM <= 5",
        scope,
    )
    if len(rows) == 1:
        r = rows[0]
        return {"id": str(r["id"]), "entityid": r.get("entityid"), "companyname": r.get("companyname")}
    if len(rows) > 1:
        return {"_ambiguous": True, "candidates": [{"id": str(r["id"]), "entityid": r.get("entityid"), "companyname": r.get("companyname")} for r in rows]}
    return None


def _resolve_currency(symbol, scope):
    if not symbol:
        return None
    row = _suiteql_first_row(
        f"SELECT id, symbol, name FROM currency WHERE symbol = {_sql_escape(symbol.strip())} AND isinactive = 'F'",
        scope,
    )
    return {"id": str(row["id"]), "symbol": row["symbol"]} if row else None


def _resolve_account(acctnumber, scope):
    """Lookup by acctnumber (most common) — bot can also pass internal id."""
    if not acctnumber:
        return None
    val = str(acctnumber).strip()
    row = _suiteql_first_row(
        f"SELECT id, acctnumber, accountsearchdisplayname AS acctname FROM account WHERE acctnumber = {_sql_escape(val)} AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "acctnumber": row.get("acctnumber"), "acctname": row.get("acctname")}
    return None


def _resolve_department(name, scope):
    if not name:
        return None
    row = _suiteql_first_row(
        f"SELECT id, name FROM department WHERE name = {_sql_escape(name.strip())} AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "name": row.get("name")}
    # Case-insensitive
    row = _suiteql_first_row(
        f"SELECT id, name FROM department WHERE UPPER(name) = UPPER({_sql_escape(name.strip())}) AND isinactive = 'F'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "name": row.get("name")}
    return None


def _resolve_location(name, scope):
    if not name:
        return None
    row = _suiteql_first_row(
        f"SELECT id, name FROM location WHERE UPPER(name) = UPPER({_sql_escape(name.strip())}) AND isinactive = 'F'",
        scope,
    )
    return {"id": str(row["id"]), "name": row["name"]} if row else None


def _resolve_class(name, scope):
    """NetSuite class lives in `classification` table (not `class`, reserved word)."""
    if not name:
        return None
    row = _suiteql_first_row(
        f"SELECT id, name FROM classification WHERE UPPER(name) = UPPER({_sql_escape(name.strip())}) AND isinactive = 'F'",
        scope,
    )
    return {"id": str(row["id"]), "name": row["name"]} if row else None


def _resolve_tax_code(csv_value, subsidiary_name, scope, table="purchasetaxitem"):
    """Compound itemid resolver. CSV says 'ZR-SG 0%'; the actual NetSuite
    itemid is 'GST_SG:ZR-SG 0%'. We compose the prefix from the subsidiary
    and search by full compound itemid first, then LIKE-with-UNDEF-excluded.
    Never matches *UNDEF* codes (placeholders).
    """
    if not csv_value or not subsidiary_name:
        return None
    prefix = SUBSIDIARY_NAME_TO_REGIME_PREFIX.get(_ql(subsidiary_name))
    if not prefix:
        return {"_error": f"No tax-regime prefix mapped for subsidiary '{subsidiary_name}'."}

    full_itemid = f"{prefix}:{csv_value.strip()}"

    # 1. Exact compound match
    row = _suiteql_first_row(
        f"SELECT id, itemid FROM {table} WHERE itemid = {_sql_escape(full_itemid)} AND isinactive = 'F' AND itemid NOT LIKE '%UNDEF%'",
        scope,
    )
    if row:
        return {"id": str(row["id"]), "itemid": row.get("itemid")}

    # 2. LIKE fallback (whitespace / formatting variants), still excluding UNDEF
    like_pattern = f"{prefix}:%{csv_value.strip()}%"
    rows = _suiteql_all_rows(
        f"SELECT id, itemid FROM {table} WHERE itemid LIKE {_sql_escape(like_pattern)} AND itemid NOT LIKE '%UNDEF%' AND isinactive = 'F' AND ROWNUM <= 5",
        scope,
    )
    if len(rows) == 1:
        return {"id": str(rows[0]["id"]), "itemid": rows[0].get("itemid")}
    if len(rows) > 1:
        return {"_ambiguous": True, "candidates": [{"id": str(r["id"]), "itemid": r["itemid"]} for r in rows]}

    return None


def _bu_normalize(s):
    """Normalize BU-code strings for lookup: lowercase, strip whitespace,
    collapse internal whitespace, drop hyphens. Keeps parens because some
    values intentionally include them ('Shared (to be allocated)')."""
    if not s:
        return ""
    out = str(s).strip().lower().replace("-", "").replace("_", "")
    # Collapse whitespace
    out = "".join(out.split())
    return out


def _resolve_bu_code(csv_value, scope):
    """BU Code custom segment lookup — pure dynamic SuiteQL on
    customrecord_cseg_msa_bu_code. No hardcoded ID fallback.

    Rationale (2026-05-20): a hardcoded map silently went stale (mapped
    'OH Shared' to id 13 when NetSuite had reassigned it to 11) and the
    bill posted with the wrong BU and no error. A hard failure is always
    better than silent wrong data in finance records.

    Format-tolerant matching: case-insensitive, whitespace/hyphen/underscore
    collapsed (parens preserved). Returns the matched id and live NetSuite
    name. Returns an ambiguous-candidate list if substring matches >1 row.
    Returns a structured _error if SuiteQL itself fails (role permission,
    network) — caller must surface verbatim, never substitute.
    """
    if not csv_value:
        return None
    needle = _bu_normalize(csv_value)

    try:
        rows = _suiteql_all_rows(
            "SELECT id, name FROM customrecord_cseg_msa_bu_code "
            "WHERE isinactive = 'F' AND ROWNUM <= 200",
            scope,
        )
    except Exception as e:
        return {"_error": (
            f"BU Code SuiteQL lookup failed against "
            f"customrecord_cseg_msa_bu_code: {e}. The integration role "
            f"may lack read access to this custom-record table — "
            f"Akansha needs to grant it. No hardcoded fallback by design "
            f"(stale IDs caused silent wrong-BU posts on 2026-05-20)."
        )}

    if not rows:
        return {"_error": (
            "BU Code SuiteQL returned no rows from "
            "customrecord_cseg_msa_bu_code. Either the table is empty "
            "or the integration role can't read it. Akansha to verify."
        )}

    # Exact normalized match
    for r in rows:
        if _bu_normalize(r.get("name", "")) == needle:
            return {"id": str(r["id"]), "name": r.get("name"),
                    "matched_via": "suiteql_exact"}
    # Substring fallback
    partials = [r for r in rows
                if needle and needle in _bu_normalize(r.get("name", ""))]
    if len(partials) == 1:
        r = partials[0]
        return {"id": str(r["id"]), "name": r.get("name"),
                "matched_via": "suiteql_substring"}
    if len(partials) > 1:
        return {"_ambiguous": True, "matched_via": "suiteql",
                "candidates": [{"id": str(r["id"]), "name": r.get("name")}
                                for r in partials]}

    return None


def resolve_csv_dimensions(record_type, csv_row, scope="sandbox"):
    """Resolve every dimension a CSV row needs for a vendorbill or journalentry
    create. Returns {ok, resolved, errors, body_hint}.

    csv_row is a flat dict. Recognised keys (all optional — only resolve what's
    present):
      subsidiary, vendor_entity_id, vendor, customer, customer_entity_id,
      currency, account, expense_account, department, location, class,
      tax_code, taxcode, bu_code, market_segment, memo, tran_date, due_date,
      bill_number, bill_ref, amount, line_memo

    On success, `body_hint` contains a partial NetSuite REST body skeleton the
    caller can finalise and POST. The caller is responsible for line-item
    structure (item.items vs expense.items) and any record-specific header
    fields not in this resolver.
    """
    resolved = {}
    errors = []

    # ── header dimensions ──────────────────────────────────────────────────
    sub_name = csv_row.get("subsidiary") or csv_row.get("Subsidiary")
    if sub_name:
        sub = _resolve_subsidiary(sub_name, scope)
        if sub:
            resolved["subsidiary"] = sub
        else:
            errors.append({"field": "subsidiary", "input": sub_name,
                           "error": f"Subsidiary '{sub_name}' not found in NetSuite (or inactive)."})

    if record_type in ("vendorbill", "vendorpayment", "vendorcredit"):
        ven_input = csv_row.get("vendor_entity_id") or csv_row.get("vendor") or csv_row.get("Vendor")
        if ven_input:
            ven = _resolve_vendor(ven_input, scope)
            if ven and ven.get("_ambiguous"):
                errors.append({"field": "vendor", "input": ven_input,
                               "error": "Vendor name matches multiple records — re-call with the exact entityid.",
                               "candidates": ven["candidates"]})
            elif ven:
                resolved["vendor"] = ven
            else:
                errors.append({"field": "vendor", "input": ven_input,
                               "error": f"Vendor '{ven_input}' not found in {scope}. Resolve via entityid or companyname exact match before calling, or have the user point at an existing vendor id."})

    cur = csv_row.get("currency") or csv_row.get("Currency")
    if cur:
        c = _resolve_currency(cur, scope)
        if c:
            resolved["currency"] = c
        else:
            errors.append({"field": "currency", "input": cur,
                           "error": f"Currency symbol '{cur}' not found in NetSuite (or inactive)."})

    # ── line-level dimensions ──────────────────────────────────────────────
    acct = csv_row.get("expense_account") or csv_row.get("account") or csv_row.get("Account")
    if acct:
        a = _resolve_account(acct, scope)
        if a:
            resolved["account"] = a
        else:
            errors.append({"field": "account", "input": acct,
                           "error": f"GL account '{acct}' not found in NetSuite (or inactive). Pass the acctnumber from the chart of accounts."})

    dept = csv_row.get("department") or csv_row.get("Department")
    if dept:
        d = _resolve_department(dept, scope)
        if d:
            resolved["department"] = d
        else:
            errors.append({"field": "department", "input": dept,
                           "error": f"Department '{dept}' not found in NetSuite (or inactive)."})

    loc = csv_row.get("location") or csv_row.get("Location")
    if loc:
        l = _resolve_location(loc, scope)
        if l:
            resolved["location"] = l
        else:
            errors.append({"field": "location", "input": loc,
                           "error": f"Location '{loc}' not found in NetSuite."})

    cls = csv_row.get("class") or csv_row.get("Class") or csv_row.get("market_segment") or csv_row.get("Market Segment")
    if cls:
        c = _resolve_class(cls, scope)
        if c:
            resolved["class"] = c
        else:
            errors.append({"field": "class", "input": cls,
                           "error": f"Class '{cls}' not found in `classification` table (NetSuite SuiteQL uses `classification`, not `class`)."})

    tax = csv_row.get("tax_code") or csv_row.get("taxcode") or csv_row.get("Tax Code") or csv_row.get("TaxCode")
    if tax:
        table_name = "purchasetaxitem" if record_type in ("vendorbill", "vendorpayment", "vendorcredit") else "salestaxitem"
        sub_name_for_tax = resolved.get("subsidiary", {}).get("name") or sub_name
        t = _resolve_tax_code(tax, sub_name_for_tax, scope, table=table_name)
        if t and t.get("_error"):
            errors.append({"field": "tax_code", "input": tax, "error": t["_error"]})
        elif t and t.get("_ambiguous"):
            errors.append({"field": "tax_code", "input": tax,
                           "error": "Tax-code suffix matches multiple non-UNDEF codes in this regime — re-call with the exact full itemid.",
                           "candidates": t["candidates"]})
        elif t:
            resolved["tax_code"] = t
        else:
            errors.append({"field": "tax_code", "input": tax,
                           "error": f"No non-UNDEF tax code matching '{tax}' for subsidiary '{sub_name_for_tax}' in {table_name}. UNDEF placeholders are excluded by design — surface this gap to Akansha rather than substituting one."})

    bu = csv_row.get("bu_code") or csv_row.get("BU Code") or csv_row.get("BU") or csv_row.get("bu code")
    if bu:
        b = _resolve_bu_code(bu, scope)
        if b and b.get("_error"):
            errors.append({"field": "bu_code", "input": bu, "error": b["_error"]})
        elif b and b.get("_ambiguous"):
            errors.append({"field": "bu_code", "input": bu,
                           "error": "BU Code matches multiple rows in customrecord_cseg_msa_bu_code — re-call with the exact value.",
                           "candidates": b["candidates"]})
        elif b:
            resolved["bu_code"] = b
        else:
            errors.append({"field": "bu_code", "input": bu,
                           "error": f"BU Code '{bu}' not found in customrecord_cseg_msa_bu_code (live SuiteQL). Either the BU doesn't exist in NetSuite, or Akansha needs to add it. No hardcoded fallback by design — silent stale IDs caused the 2026-05-20 wrong-BU incident."})

    # Spurious-segment safety: the bot's hand-rolled bodies historically
    # leaked the BU Code value into Product Segment (cseg_msa_product_segment).
    # The high-level *_from_csv tools never write cseg_msa_product_segment
    # — only fields explicitly in the CSV get populated. So we don't need
    # to error on the column; just rely on the resolver not knowing it.
    # If finance later adds a real Product Segment column, add a resolver
    # for it alongside the BU one.

    return {
        "ok": len(errors) == 0,
        "resolved": resolved,
        "errors": errors,
    }


def execute_create_vendor_bill_from_csv(csv_row, scope="sandbox"):
    """End-to-end Vendor Bill create from a CSV-style row dict. Resolves every
    dimension server-side via resolve_csv_dimensions, builds the complete
    expense.items body, POSTs it, runs post-write verify. Bot cannot drop
    fields because it doesn't assemble the body.

    csv_row recognised keys: bill_ref / bill_number (→ tranid), subsidiary,
    vendor_entity_id / vendor, currency, tran_date / trandate, due_date /
    duedate, memo, expense_account / account, amount, line_memo / description,
    department, location, class / market_segment, tax_code, bu_code.
    """
    res = resolve_csv_dimensions("vendorbill", csv_row, scope=scope)
    if not res["ok"]:
        return {
            "ok": False,
            "error": "DIMENSION_RESOLUTION_FAILED",
            "errors": res["errors"],
            "resolved_so_far": res["resolved"],
            "message": (
                "Cannot create vendor bill — one or more CSV fields could not be "
                "resolved to NetSuite internal IDs. Surface each error verbatim to "
                "the user; do NOT create the bill with missing fields."
            ),
        }

    r = res["resolved"]
    line = {
        "account":    {"id": r["account"]["id"]},
        "amount":     float(csv_row.get("amount") or csv_row.get("Amount") or 0),
        "memo":       csv_row.get("line_memo") or csv_row.get("description") or "",
    }
    if r.get("department"): line["department"] = {"id": r["department"]["id"]}
    if r.get("location"):   line["location"]   = {"id": r["location"]["id"]}
    if r.get("class"):      line["class"]      = {"id": r["class"]["id"]}
    if r.get("tax_code"):   line["taxcode"]    = {"id": r["tax_code"]["id"]}
    if r.get("bu_code"):    line["cseg_msa_bu_code"] = {"id": r["bu_code"]["id"]}

    body = {
        "entity":     {"id": r["vendor"]["id"]} if r.get("vendor") else None,
        "subsidiary": {"id": r["subsidiary"]["id"]} if r.get("subsidiary") else None,
        "trandate":   csv_row.get("tran_date") or csv_row.get("trandate"),
        "duedate":    csv_row.get("due_date") or csv_row.get("duedate"),
        "tranid":     csv_row.get("bill_number") or csv_row.get("bill_ref"),
        "memo":       csv_row.get("memo") or "",
        "currency":   {"id": r["currency"]["id"]} if r.get("currency") else None,
        "expense":    {"items": [line]},
    }
    # Drop None-valued header fields
    body = {k: v for k, v in body.items() if v is not None}

    create_result = execute_create("vendorbill", body, scope=scope)
    if create_result.get("ok"):
        create_result["resolved_fields"] = r
    return create_result


def execute_create_journal_entry_from_csv(csv_row, scope="sandbox"):
    """End-to-end Journal Entry create from a CSV-style row dict.

    csv_row recognised keys (line-level, per row in the CSV):
      subsidiary, tran_date / trandate, memo (header), and for each line:
      account, debit, credit, line_memo, department, location, class /
      market_segment, bu_code. If the CSV is multi-line, pass csv_row.lines
      as a list of dicts with the line-level fields.
    """
    # Resolve header dimensions
    header_res = resolve_csv_dimensions("journalentry", csv_row, scope=scope)
    header_errors = list(header_res["errors"])
    header_resolved = header_res["resolved"]

    # Build lines — either from csv_row.lines (multi-line) or from csv_row itself (single-line CSV)
    raw_lines = csv_row.get("lines") or [csv_row]
    resolved_lines = []
    all_errors = list(header_errors)

    for idx, raw in enumerate(raw_lines):
        line_res = resolve_csv_dimensions("journalentry", raw, scope=scope)
        for e in line_res["errors"]:
            e["line"] = idx + 1
            all_errors.append(e)

        rl = line_res["resolved"]
        line_obj = {
            "account": {"id": rl["account"]["id"]} if rl.get("account") else None,
            "debit":   float(raw.get("debit") or 0) or None,
            "credit":  float(raw.get("credit") or 0) or None,
            "memo":    raw.get("line_memo") or raw.get("description") or raw.get("memo") or "",
        }
        if rl.get("department"): line_obj["department"] = {"id": rl["department"]["id"]}
        if rl.get("location"):   line_obj["location"]   = {"id": rl["location"]["id"]}
        if rl.get("class"):      line_obj["class"]      = {"id": rl["class"]["id"]}
        if rl.get("bu_code"):    line_obj["cseg_msa_bu_code"] = {"id": rl["bu_code"]["id"]}
        line_obj = {k: v for k, v in line_obj.items() if v is not None}
        resolved_lines.append(line_obj)

    if all_errors:
        return {
            "ok": False,
            "error": "DIMENSION_RESOLUTION_FAILED",
            "errors": all_errors,
            "header_resolved": header_resolved,
            "message": (
                "Cannot create journal entry — one or more CSV fields could not be "
                "resolved. Surface each error verbatim to the user; do NOT create "
                "the JE with missing fields."
            ),
        }

    # Debit/credit balance check
    total_debit = sum((l.get("debit") or 0) for l in resolved_lines)
    total_credit = sum((l.get("credit") or 0) for l in resolved_lines)
    if abs(total_debit - total_credit) > 0.01:
        return {
            "ok": False,
            "error": "UNBALANCED_JOURNAL",
            "message": f"Unbalanced journal: debits={total_debit}, credits={total_credit}. Must net to zero.",
        }

    body = {
        "subsidiary": {"id": header_resolved["subsidiary"]["id"]} if header_resolved.get("subsidiary") else None,
        "trandate":   csv_row.get("tran_date") or csv_row.get("trandate"),
        "memo":       csv_row.get("memo") or "",
        "line":       {"items": resolved_lines},
    }
    body = {k: v for k, v in body.items() if v is not None}

    create_result = execute_create("journalentry", body, scope=scope)
    if create_result.get("ok"):
        create_result["resolved_header"] = header_resolved
        create_result["resolved_lines"] = resolved_lines
    return create_result


def execute_update_vendor_bill_from_csv(record_id, csv_row, scope="sandbox", line_index=0):
    """Partial-update an existing vendorbill from a CSV-style row dict.
    Used for amendments — when the user says "the tax code is wrong" or
    "BU Code is missing" in the same thread, the bot calls this with just
    the changed fields. Only the fields present in csv_row are touched;
    everything else on the bill is left alone.

    Returns the same {ok, internal_id, ui_url, resolved_fields} shape as
    create_vendor_bill_from_csv. On any resolution failure, returns
    DIMENSION_RESOLUTION_FAILED with per-field errors — bot must surface
    verbatim, never patch with incomplete data.
    """
    # Resolve only the fields the user supplied for the amendment
    res = resolve_csv_dimensions("vendorbill", csv_row, scope=scope)
    if not res["ok"]:
        return {
            "ok": False,
            "error": "DIMENSION_RESOLUTION_FAILED",
            "errors": res["errors"],
            "resolved_so_far": res["resolved"],
            "message": "Cannot amend vendor bill — one or more amendment fields could not be resolved.",
        }

    r = res["resolved"]

    # Build a partial PATCH body. Only include fields actually resolved.
    body = {}

    # Header-level fields
    if "vendor" in r:     body["entity"]     = {"id": r["vendor"]["id"]}
    if "subsidiary" in r: body["subsidiary"] = {"id": r["subsidiary"]["id"]}
    if "currency" in r:   body["currency"]   = {"id": r["currency"]["id"]}
    if csv_row.get("tran_date") or csv_row.get("trandate"):
        body["trandate"] = csv_row.get("tran_date") or csv_row.get("trandate")
    if csv_row.get("due_date") or csv_row.get("duedate"):
        body["duedate"] = csv_row.get("due_date") or csv_row.get("duedate")
    if csv_row.get("memo"):
        body["memo"] = csv_row.get("memo")
    if csv_row.get("bill_number") or csv_row.get("bill_ref"):
        body["tranid"] = csv_row.get("bill_number") or csv_row.get("bill_ref")

    # Line-level fields — patch a specific line by index (default: line 0).
    # NetSuite REST line-level patches typically replace the line; we provide
    # only the fields the user asked to change.
    line_patch = {}
    if "account" in r:    line_patch["account"]    = {"id": r["account"]["id"]}
    if "department" in r: line_patch["department"] = {"id": r["department"]["id"]}
    if "location" in r:   line_patch["location"]   = {"id": r["location"]["id"]}
    if "class" in r:      line_patch["class"]      = {"id": r["class"]["id"]}
    if "tax_code" in r:   line_patch["taxcode"]    = {"id": r["tax_code"]["id"]}
    if "bu_code" in r:    line_patch["cseg_msa_bu_code"] = {"id": r["bu_code"]["id"]}
    if csv_row.get("amount") is not None:    line_patch["amount"] = float(csv_row["amount"])
    if csv_row.get("line_memo"):             line_patch["memo"]   = csv_row["line_memo"]

    if line_patch:
        body["expense"] = {"items": [{**line_patch, "line": line_index + 1}]}

    if not body:
        return {
            "ok": False,
            "error": "NO_FIELDS_TO_UPDATE",
            "message": "Amendment csv_row contained no recognised fields to update.",
        }

    update_result = execute_update("vendorbill", record_id, body, scope=scope)
    if update_result.get("ok"):
        update_result["resolved_fields"] = r
        update_result["patched_body"] = body
    return update_result


def execute_update_journal_entry_from_csv(record_id, csv_row, scope="sandbox"):
    """Partial-update an existing journalentry from a CSV-style row dict.
    Same amendment flow as execute_update_vendor_bill_from_csv. For multi-line
    JEs, pass csv_row.lines as a list of line dicts; each line must include
    its `line` index (1-based) to identify which line to patch.
    """
    res = resolve_csv_dimensions("journalentry", csv_row, scope=scope)
    header_errors = list(res["errors"])

    raw_lines = csv_row.get("lines") or []
    resolved_lines = []
    all_errors = list(header_errors)

    for raw in raw_lines:
        line_res = resolve_csv_dimensions("journalentry", raw, scope=scope)
        for e in line_res["errors"]:
            e["line"] = raw.get("line") or "?"
            all_errors.append(e)

        rl = line_res["resolved"]
        line_obj = {"line": raw.get("line")}
        if rl.get("account"):    line_obj["account"]    = {"id": rl["account"]["id"]}
        if rl.get("department"): line_obj["department"] = {"id": rl["department"]["id"]}
        if rl.get("location"):   line_obj["location"]   = {"id": rl["location"]["id"]}
        if rl.get("class"):      line_obj["class"]      = {"id": rl["class"]["id"]}
        if rl.get("bu_code"):    line_obj["cseg_msa_bu_code"] = {"id": rl["bu_code"]["id"]}
        if raw.get("debit") is not None:  line_obj["debit"]  = float(raw["debit"])
        if raw.get("credit") is not None: line_obj["credit"] = float(raw["credit"])
        if raw.get("memo"):               line_obj["memo"]   = raw["memo"]
        resolved_lines.append(line_obj)

    if all_errors:
        return {
            "ok": False,
            "error": "DIMENSION_RESOLUTION_FAILED",
            "errors": all_errors,
            "message": "Cannot amend journal entry — one or more amendment fields could not be resolved.",
        }

    body = {}
    if res["resolved"].get("subsidiary"):
        body["subsidiary"] = {"id": res["resolved"]["subsidiary"]["id"]}
    if csv_row.get("tran_date") or csv_row.get("trandate"):
        body["trandate"] = csv_row.get("tran_date") or csv_row.get("trandate")
    if csv_row.get("memo"):
        body["memo"] = csv_row.get("memo")
    if resolved_lines:
        body["line"] = {"items": resolved_lines}

    if not body:
        return {"ok": False, "error": "NO_FIELDS_TO_UPDATE",
                "message": "Amendment csv_row contained no recognised fields to update."}

    update_result = execute_update("journalentry", record_id, body, scope=scope)
    if update_result.get("ok"):
        update_result["resolved_header"] = res["resolved"]
        update_result["resolved_lines"] = resolved_lines
        update_result["patched_body"] = body
    return update_result


# Where exported CSVs land. Override with NETSUITE_EXPORT_DIR env var.
EXPORT_DIR = os.environ.get("NETSUITE_EXPORT_DIR", "/tmp/netsuite_exports")
EXPORT_PAGE_SIZE = 1000
EXPORT_DEFAULT_MAX_ROWS = 50000


def _slug(s, default="export"):
    """File-safe slug from a hint string."""
    out = re.sub(r"[^A-Za-z0-9_-]+", "_", (s or default)).strip("_")
    return (out or default)[:80]


def _suiteql_one_page(query, scope, limit, offset):
    """Single-page SuiteQL with limit+offset URL params.
    NetSuite's SuiteQL REST endpoint supports ?limit=N&offset=M for paging.
    """
    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/query/v1/suiteql?limit={limit}&offset={offset}"
    auth = oauth_header("POST", url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])
    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        "-d", json.dumps({"q": query}),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if not result.stdout:
        return {"error": result.stderr or "empty response"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"non-JSON response: {e}", "raw": result.stdout[:500]}


def execute_export_suiteql_to_csv(query, filename_hint=None, scope="prod",
                                  max_rows=EXPORT_DEFAULT_MAX_ROWS):
    """Run a SuiteQL with server-side pagination, write all rows to a CSV
    file, and return only metadata + a 3-row preview. The full result set
    NEVER enters the LLM context — token cost is bounded regardless of
    row count.

    Use this for bulk-listing requests (>50 rows). For small filtered
    queries, prefer run_suiteql which returns rows inline.

    Returns:
      ok=True:  {file_path, row_count, columns, preview (≤3 rows), scope, message}
      ok=False: {error, message, [rows_exported_so_far, partial_file]}
    """
    if not query or not isinstance(query, str):
        return {"ok": False, "error": "BAD_QUERY",
                "message": "export_suiteql_to_csv requires a non-empty SuiteQL string."}

    # Reject queries that pre-bake their own pagination — we paginate via
    # URL params, so the caller's query must not also paginate (would
    # produce inconsistent/duplicate rows across pages).
    lowered = query.lower()
    if " limit " in lowered or "fetch first" in lowered or "fetch next" in lowered \
       or " offset " in lowered or "rownum" in lowered:
        return {"ok": False, "error": "QUERY_HAS_PAGINATION",
                "message": ("Remove LIMIT / OFFSET / FETCH FIRST / FETCH NEXT / "
                            "ROWNUM from the query — the export tool paginates "
                            "server-side. Filter with WHERE / ORDER BY only.")}

    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": "EXPORT_DIR_UNWRITABLE",
                "message": f"Could not create export dir {EXPORT_DIR}: {e}"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug(filename_hint, default=f"netsuite_export_{scope}")
    file_path = os.path.join(EXPORT_DIR, f"{slug}_{timestamp}.csv")

    offset = 0
    total_rows = 0
    preview = []
    columns = None
    writer = None
    fh = None

    try:
        fh = open(file_path, "w", newline="", encoding="utf-8")
        while total_rows < max_rows:
            page = _suiteql_one_page(query, scope, limit=EXPORT_PAGE_SIZE, offset=offset)

            if page.get("error") or page.get("type") == "error" or page.get("status") in (400, 401, 403, 500):
                err_msg = (page.get("error") or page.get("title")
                           or page.get("detail") or json.dumps(page)[:300])
                return {"ok": False, "error": "SUITEQL_ERROR",
                        "message": f"NetSuite SuiteQL error at offset {offset}: {err_msg}",
                        "rows_exported_so_far": total_rows,
                        "partial_file": file_path if total_rows else None}

            items = page.get("items") or []
            if not items:
                break

            if writer is None:
                # Discover columns from the first row; drop NetSuite metadata keys
                first = items[0]
                columns = [c for c in first.keys() if c != "links"]
                writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()

            for row in items:
                clean = {k: ("" if row.get(k) is None else row.get(k)) for k in columns}
                writer.writerow(clean)
                if len(preview) < 3:
                    preview.append(clean)
                total_rows += 1
                if total_rows >= max_rows:
                    break

            # Stop if NetSuite says no more, or we got a short page
            if not page.get("hasMore", False) or len(items) < EXPORT_PAGE_SIZE:
                break
            offset += EXPORT_PAGE_SIZE
    except Exception as e:
        return {"ok": False, "error": "EXPORT_FAILED",
                "message": f"Export failed at offset {offset} (rows so far: {total_rows}): {e}",
                "rows_exported_so_far": total_rows,
                "partial_file": file_path if total_rows else None}
    finally:
        if fh is not None:
            fh.close()

    if total_rows == 0:
        # No rows — clean up the empty file
        try: os.remove(file_path)
        except OSError: pass
        return {"ok": True, "row_count": 0, "columns": [], "preview": [],
                "file_path": None, "scope": scope,
                "message": "Query returned 0 rows — no file written."}

    truncated = total_rows >= max_rows
    return {
        "ok": True,
        "file_path": file_path,
        "row_count": total_rows,
        "columns": columns,
        "preview": preview,
        "scope": scope,
        "truncated": truncated,
        "message": (
            f"✅ Exported {total_rows} rows to {file_path}. "
            f"Columns: {', '.join(columns)}. "
            f"Preview shows first {len(preview)} row(s)."
            + (f" ⚠️ Truncated at max_rows={max_rows} — refine the query if you need more." if truncated else "")
        ),
    }


def execute_refresh_mcp_logs(days_back=1):
    """Render the MCP activity JSONL into committed markdown for today and
    optionally the last (days_back - 1) days. Returns the list of rendered
    file paths + per-day summary; the AGENT is responsible for the actual
    `git add / commit / push` step (it has bash access; the MCP server
    deliberately does not handle git credentials).

    Used to satisfy on-demand "give me the latest NetSuite logs" DMs —
    keeps the rendered markdown on GitHub fresh without waiting for the
    daily cron.
    """
    from datetime import date as _date, timedelta as _td
    try:
        days_back = max(1, min(int(days_back), 30))
    except (TypeError, ValueError):
        days_back = 1

    renderer = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "render_netsuite_mcp_logs.py")
    md_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "memory", "logs", "netsuite-mcp"))

    if not os.path.exists(renderer):
        return {"ok": False, "error": "RENDERER_MISSING",
                "message": f"Renderer script not found at {renderer}."}

    rendered_files = []
    per_day = []
    today = _date.today()

    for d in range(days_back):
        day = today - _td(days=d)
        date_str = day.strftime("%Y-%m-%d")
        try:
            r = subprocess.run(
                ["python3", renderer, date_str],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            per_day.append({"date": date_str, "rendered": False,
                            "error": "renderer timeout (>30s)"})
            continue
        except Exception as e:
            per_day.append({"date": date_str, "rendered": False,
                            "error": f"renderer failed: {e}"})
            continue

        md_path = os.path.join(md_root, f"{date_str}.md")
        if os.path.exists(md_path):
            rendered_files.append(md_path)
            per_day.append({"date": date_str, "rendered": True,
                            "file": md_path,
                            "stdout": (r.stdout or "").strip()[:200]})
        else:
            per_day.append({"date": date_str, "rendered": False,
                            "stdout": (r.stdout or "").strip()[:200]})

    return {
        "ok": True,
        "days_back": days_back,
        "rendered_files": rendered_files,
        "per_day": per_day,
        "next_step": (
            "Agent — run `git add memory/logs/netsuite-mcp/*.md && "
            "git commit -m \"chore: MCP activity log refresh\" && "
            "git push origin main`, then reply to the user with the GitHub URL "
            "https://github.com/wego/openclaw-nova/blob/main/memory/logs/netsuite-mcp/<TODAY>.md"
        ),
        "message": (
            f"Rendered {len(rendered_files)} day(s) of MCP activity logs. "
            f"Agent must git commit/push the markdown to make them visible on GitHub."
        ),
    }


# ─── Standard reports — pre-validated SuiteQL templates ────────────────────
# Seven named reports the agent can run on demand. The SuiteQL lives HERE
# (server-side, version-controlled, tested) instead of being re-drafted by
# the agent each time. Per-report params are validated against type-specific
# rules to keep them safe to substitute into the SQL string.
#
# All reports return their results via execute_export_suiteql_to_csv — the
# full result set never enters the LLM context. Bounded token cost.

import re as _re


def _v_date(s):
    """YYYY-MM-DD only. Rejects everything else."""
    if not isinstance(s, str) or not _re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError(f"Invalid date (expected YYYY-MM-DD): {s!r}")
    return s


def _v_identifier(s, max_len=100):
    """Customer / vendor / entity-id. Escape single quotes for SQL."""
    if not isinstance(s, str) or not s.strip():
        raise ValueError(f"Expected non-empty string identifier: {s!r}")
    if len(s) > max_len:
        raise ValueError(f"Identifier too long (max {max_len}): {s[:40]}…")
    return s.replace("'", "''")


def _v_gl_code(s):
    """GL account code. Digits, letters, dots, dashes, underscores only."""
    if not isinstance(s, str) or not _re.match(r"^[\w\.\-]{1,30}$", s):
        raise ValueError(f"Invalid GL code: {s!r}")
    return s


def _v_int(v):
    """Subsidiary / period / account internal-id."""
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError(f"Expected integer, got {v!r}")


def _v_currency_symbol(s):
    """ISO-style currency symbol/code (e.g. AED, EGP, MYR, USD). Used to
    filter the FX rate list. Letters only, 2-5 chars, upper-cased. Safe to
    substitute into SQL after this validation (no quotes/spaces survive)."""
    if not isinstance(s, str) or not _re.match(r"^[A-Za-z]{2,5}$", s.strip()):
        raise ValueError(
            f"Invalid currency symbol (expected 2-5 letters like 'AED'): {s!r}"
        )
    return s.strip().upper()


def _v_gl_code_list(v):
    """List of GL codes. Accepts either a Python list or a
    comma-separated string. Validates each code with _v_gl_code, caps
    at 50 codes, returns a SQL-list-ready string like
    `'150', '155', '160'` for direct substitution inside `IN (…)`.
    """
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",") if x.strip()]
    if not isinstance(v, list) or not v:
        raise ValueError(f"Expected list of GL codes (or comma string), got {v!r}")
    if len(v) > 50:
        raise ValueError(f"Too many GL codes (max 50): got {len(v)}")
    cleaned = [_v_gl_code(c) for c in v]
    return ", ".join(f"'{c}'" for c in cleaned)


# Each entry: {description, required_params, optional_params, sql_template,
#              filename_template}. Placeholders in SQL use {name} formatting;
# optional filters use {{optional_block}} markers that are stripped if the
# param is absent.
STANDARD_REPORTS = {


    # ─── 2. Customer Statement of Account (data — not the PDF) ────────────
    "customer_statement": {
        "description": (
            "Customer statement DATA — invoices, payments, credit memos and "
            "refunds for one customer between two dates. Returns the same "
            "raw data the NetSuite Statement PDF is built from. The actual "
            "PDF format requires a separate build (NetSuite report/print "
            "endpoint, ~2hr effort) — out of scope for SuiteQL."
        ),
        "required": {
            "customer": _v_identifier,
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {},
        "sql": """
SELECT
  c.entityid                                                     AS customer,
  t.trandate                                                     AS transaction_date,
  t.tranid                                                       AS reference,
  CASE t.type
    WHEN 'CustInvc' THEN 'Invoice'
    WHEN 'CustPymt' THEN 'Payment'
    WHEN 'CustCred' THEN 'Credit Memo'
    WHEN 'CustRfnd' THEN 'Refund'
    ELSE t.type
  END                                                            AS transaction_type,
  t.duedate                                                      AS due_date,
  t.memo,
  t.foreigntotal                                                 AS amount,
  t.foreignamountunpaid                                          AS open_balance,
  t.currency,
  s.name                                                         AS subsidiary
FROM transaction t
JOIN customer c   ON t.entity     = c.id
JOIN subsidiary s ON t.subsidiary = s.id
WHERE c.entityid = '{customer}'
  AND t.posting  = 'T'
  AND t.voided   = 'F'
  AND t.trandate BETWEEN TO_DATE('{from_date}', 'YYYY-MM-DD')
                     AND TO_DATE('{to_date}',   'YYYY-MM-DD')
  AND t.type IN ('CustInvc', 'CustPymt', 'CustCred', 'CustRfnd')
ORDER BY t.trandate, t.tranid
""",
        "filename": "customer_statement_{customer}_{from_date}_to_{to_date}",
    },

    # ─── 3. Revenue report (periodic) ─────────────────────────────────────
    "revenue_periodic": {
        "description": (
            "Revenue posted to Income / Other-Income accounts, grouped by "
            "period × account × customer × subsidiary. Date range is "
            "matched against the accounting period start/end."
        ),
        "required": {
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {"subsidiary_id": _v_int},
        "sql": """
SELECT
  ap.periodname                                                  AS period,
  a.acctnumber                                                   AS gl_code,
  a.fullname                                                     AS account,
  c.entityid                                                     AS customer,
  s.name                                                         AS subsidiary,
  SUM(tal.amount)                                                AS revenue
FROM transactionaccountingline tal
JOIN transaction t       ON tal.transaction = t.id
JOIN account a           ON tal.account     = a.id
JOIN subsidiary s        ON t.subsidiary    = s.id
JOIN accountingperiod ap ON t.postingperiod = ap.id
LEFT JOIN customer c     ON t.entity        = c.id
WHERE a.accttype IN ('Income', 'OthIncome')
  AND t.posting  = 'T'
  AND t.voided   = 'F'
  AND ap.startdate >= TO_DATE('{from_date}', 'YYYY-MM-DD')
  AND ap.enddate   <= TO_DATE('{to_date}',   'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
GROUP BY ap.periodname, a.acctnumber, a.fullname, c.entityid, s.name
ORDER BY ap.periodname, a.acctnumber
""",
        "filename": "revenue_{from_date}_to_{to_date}",
    },

    # ─── 4. GL report (specific account, periodic) ────────────────────────
    "gl_report": {
        "description": (
            "Every posting line hitting a single GL account between two "
            "dates, with debit / credit / entity / memo / subsidiary. "
            "Example GL code: '1221010' (Revenue Accrual - Market place)."
        ),
        "required": {
            "gl_code":   _v_gl_code,
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {"subsidiary_id": _v_int},
        "sql": """
SELECT
  t.trandate                                                     AS transaction_date,
  ap.periodname                                                  AS period,
  t.tranid                                                       AS reference,
  t.type                                                         AS transaction_type,
  COALESCE(c.entityid, v.entityid)                               AS entity,
  t.memo,
  CASE WHEN tal.amount >= 0 THEN tal.amount ELSE 0 END           AS debit,
  CASE WHEN tal.amount <  0 THEN -tal.amount ELSE 0 END          AS credit,
  tal.amount                                                     AS net,
  t.currency,
  s.name                                                         AS subsidiary
FROM transactionaccountingline tal
JOIN transaction t       ON tal.transaction = t.id
JOIN account a           ON tal.account     = a.id
JOIN subsidiary s        ON t.subsidiary    = s.id
JOIN accountingperiod ap ON t.postingperiod = ap.id
LEFT JOIN customer c     ON t.entity        = c.id
LEFT JOIN vendor v       ON t.entity        = v.id
WHERE a.acctnumber = '{gl_code}'
  AND t.posting    = 'T'
  AND t.voided     = 'F'
  AND t.trandate BETWEEN TO_DATE('{from_date}', 'YYYY-MM-DD')
                     AND TO_DATE('{to_date}',   'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
ORDER BY t.trandate, t.tranid
""",
        "filename": "gl_{gl_code}_{from_date}_to_{to_date}",
    },

    # ─── 5. Payment by customers ──────────────────────────────────────────
    "customer_payments": {
        "description": (
            "All customer payments received between two dates. Optionally "
            "filter to one customer or one subsidiary."
        ),
        "required": {
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {
            "customer":      _v_identifier,
            "subsidiary_id": _v_int,
        },
        "sql": """
SELECT
  t.trandate                                                     AS payment_date,
  t.tranid                                                       AS payment_ref,
  c.entityid                                                     AS customer,
  t.foreigntotal                                                 AS amount,
  t.currency,
  t.memo,
  s.name                                                         AS subsidiary
FROM transaction t
JOIN customer c   ON t.entity     = c.id
JOIN subsidiary s ON t.subsidiary = s.id
WHERE t.type    = 'CustPymt'
  AND t.posting = 'T'
  AND t.voided  = 'F'
  AND t.trandate BETWEEN TO_DATE('{from_date}', 'YYYY-MM-DD')
                     AND TO_DATE('{to_date}',   'YYYY-MM-DD')
  {{customer: AND c.entityid = '{customer}' }}
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
ORDER BY t.trandate, c.entityid
""",
        "filename": "customer_payments_{from_date}_to_{to_date}",
    },

    # ─── 6. Balance sheet (as of date) ────────────────────────────────────
    "balance_sheet": {
        "description": (
            "Balance-sheet line items as of <as_of_date> — Assets, "
            "Liabilities and Equity grouped by account type and account. "
            "Drops zero-balance rows. Note: this is the raw line-level "
            "data; consolidated multi-currency rollup is NOT applied — "
            "balances are in transaction currency. Apply consolidation "
            "in the consuming tool if needed."
        ),
        "required": {"as_of_date": _v_date},
        "optional": {"subsidiary_id": _v_int},
        "sql": """
SELECT
  a.accttype                                                     AS account_type,
  a.acctnumber                                                   AS gl_code,
  a.fullname                                                     AS account,
  s.name                                                         AS subsidiary,
  SUM(tal.amount)                                                AS balance,
  '{as_of_date}'                                                 AS as_of_date
FROM transactionaccountingline tal
JOIN transaction t  ON tal.transaction = t.id
JOIN account a      ON tal.account     = a.id
JOIN subsidiary s   ON t.subsidiary    = s.id
WHERE a.accttype IN ('Bank', 'AcctRec', 'OthCurrAsset', 'FixedAsset',
                     'OthAsset', 'AcctPay', 'CredCard', 'OthCurrLiab',
                     'LongTermLiab', 'Equity')
  AND t.posting = 'T'
  AND t.voided  = 'F'
  AND t.trandate <= TO_DATE('{as_of_date}', 'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
GROUP BY a.accttype, a.acctnumber, a.fullname, s.name
HAVING ABS(SUM(tal.amount)) > 0.005
ORDER BY a.accttype, a.acctnumber
""",
        "filename": "balance_sheet_{as_of_date}",
    },

    # ─── 7. Income statement (periodic) ───────────────────────────────────
    "income_statement": {
        "description": (
            "P&L lines between two dates — Income, Other-Income, COGS, "
            "Expense, Other-Expense grouped by account × period × "
            "subsidiary. Drops zero-amount rows."
        ),
        "required": {
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {"subsidiary_id": _v_int},
        "sql": """
SELECT
  a.accttype                                                     AS account_type,
  a.acctnumber                                                   AS gl_code,
  a.fullname                                                     AS account,
  s.name                                                         AS subsidiary,
  ap.periodname                                                  AS period,
  SUM(tal.amount)                                                AS amount
FROM transactionaccountingline tal
JOIN transaction t       ON tal.transaction = t.id
JOIN account a           ON tal.account     = a.id
JOIN subsidiary s        ON t.subsidiary    = s.id
JOIN accountingperiod ap ON t.postingperiod = ap.id
WHERE a.accttype IN ('Income', 'OthIncome', 'COGS', 'Expense', 'OthExpense')
  AND t.posting = 'T'
  AND t.voided  = 'F'
  AND ap.startdate >= TO_DATE('{from_date}', 'YYYY-MM-DD')
  AND ap.enddate   <= TO_DATE('{to_date}',   'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
GROUP BY a.accttype, a.acctnumber, a.fullname, s.name, ap.periodname
HAVING ABS(SUM(tal.amount)) > 0.005
ORDER BY a.accttype, a.acctnumber, ap.periodname
""",
        "filename": "income_statement_{from_date}_to_{to_date}",
    },

    # ─── 8. Intercompany Balance Sheet — AR + AP, single subsidiary ───────
    "interco_balance_sheet": {
        "description": (
            "Intercompany AR + AP balances as-of <as_of_date>. Filters by "
            "account code list (defaults to Wego's standard interco "
            "accounts: 12030 AR-Interco and 21030 AP-Interco). "
            "subsidiary_id is OPTIONAL — omit it to get the CONSOLIDATED "
            "view (one row per subsidiary × account × currency); pass it "
            "to scope to a single subsidiary. Always groups by "
            "subsidiary + account + currency so the agent has full "
            "breakdown to format from. Drops zero-balance rows. "
            "Different subs may use different interco account codes — "
            "override the default list via account_codes if needed."
        ),
        "required": {
            "as_of_date": _v_date,
        },
        "optional": {
            "subsidiary_id": _v_int,
            "account_codes": _v_gl_code_list,
        },
        "defaults": {
            "account_codes": "'12030', '21030'",  # pre-formatted for IN()
        },
        "sql": """
SELECT
  a.acctnumber                                                   AS gl_code,
  a.fullname                                                     AS account,
  s.name                                                         AS subsidiary,
  t.currency,
  SUM(tal.amount)                                                AS balance,
  '{as_of_date}'                                                 AS as_of_date
FROM transactionaccountingline tal
JOIN transaction t  ON tal.transaction = t.id
JOIN account a      ON tal.account     = a.id
JOIN subsidiary s   ON t.subsidiary    = s.id
WHERE a.acctnumber IN ({account_codes})
  AND t.posting = 'T'
  AND t.voided  = 'F'
  AND t.trandate <= TO_DATE('{as_of_date}', 'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
GROUP BY a.acctnumber, a.fullname, s.name, t.currency
HAVING ABS(SUM(tal.amount)) > 0.005
ORDER BY a.acctnumber, s.name, t.currency
""",
        "filename": "interco_bs_{as_of_date}",
    },

    # ─── 9. GL listing — multiple GL accounts in one report ───────────────
    "gl_listing_multi": {
        "description": (
            "Same shape as gl_report but accepts a LIST of GL codes and "
            "returns a single consolidated CSV with a gl_code column so "
            "you can filter or group downstream. Use this when the user "
            "asks for a multi-account listing like 'GL 150, 155, 160, "
            "262, 2624, 266'. Cap is 50 codes per call."
        ),
        "required": {
            "gl_codes":  _v_gl_code_list,
            "from_date": _v_date,
            "to_date":   _v_date,
        },
        "optional": {"subsidiary_id": _v_int},
        "sql": """
SELECT
  t.trandate                                                     AS transaction_date,
  ap.periodname                                                  AS period,
  a.acctnumber                                                   AS gl_code,
  a.fullname                                                     AS account,
  t.tranid                                                       AS reference,
  t.type                                                         AS transaction_type,
  COALESCE(c.entityid, v.entityid)                               AS entity,
  t.memo,
  CASE WHEN tal.amount >= 0 THEN tal.amount ELSE 0 END           AS debit,
  CASE WHEN tal.amount <  0 THEN -tal.amount ELSE 0 END          AS credit,
  tal.amount                                                     AS net,
  t.currency,
  s.name                                                         AS subsidiary
FROM transactionaccountingline tal
JOIN transaction t       ON tal.transaction = t.id
JOIN account a           ON tal.account     = a.id
JOIN subsidiary s        ON t.subsidiary    = s.id
JOIN accountingperiod ap ON t.postingperiod = ap.id
LEFT JOIN customer c     ON t.entity        = c.id
LEFT JOIN vendor v       ON t.entity        = v.id
WHERE a.acctnumber IN ({gl_codes})
  AND t.posting    = 'T'
  AND t.voided     = 'F'
  AND t.trandate BETWEEN TO_DATE('{from_date}', 'YYYY-MM-DD')
                     AND TO_DATE('{to_date}',   'YYYY-MM-DD')
  {{subsidiary_id: AND t.subsidiary = {subsidiary_id} }}
ORDER BY a.acctnumber, t.trandate, t.tranid
""",
        "filename": "gl_listing_multi_{from_date}_to_{to_date}",
    },

    # ─── 10. FX rate list (Rule 7 — currencyrate, NEVER the currency table) ─
    # Locked because the agent kept drifting: sometimes it queried the
    # `currency` table's per-record `exchangerate` field (wrong — that's a
    # display rate, not a pairwise rate), sometimes it flipped the base, and
    # the values/columns came out different every time it was asked (see
    # Nikhil's 3-snapshot report 2026-06-30). This template pins:
    #   • SOURCE  : `currencyrate` (the pairwise rate table) — the SAME data
    #               behind `Lists > Accounting > Currency Exchange Rates`.
    #   • DIRECTION: exchange_rate = units of base_currency per 1 source_currency
    #               (NetSuite native: basecurrency / transactioncurrency / exchangerate).
    #   • LATEST  : one row per (base, source) pair — the most recent
    #               effectivedate on or before as_of_date (CTE).
    #   • COLUMNS : Akansha's required 5-col order first
    #               (base_currency | effective_date | exchange_rate | method |
    #               source_currency), then full names as trailing context.
    #   • DATE    : DD/MM/YYYY (Wego-finance reads dd/mm/yyyy, not ISO).
    #   • METHOD  : literal 'DIRECT' — every rate Wego loads is a direct rate;
    #               all observed data shows DIRECT. If NetSuite ever stores a
    #               method column, switch the literal to that column here.
    "fx_rate_list": {
        "description": (
            "Currency exchange rate list AS OF a single date — the exact "
            "data + columns of the native NetSuite page Lists > Accounting > "
            "Currency Exchange Rates (currencyratelist.nl) with the AS OF "
            "filter. Latest rate per currency pair on or before as_of_date. "
            "Columns: base_currency (FULL NAME, e.g. 'Egyptian Pound'), "
            "source_currency (FULL NAME), exchange_rate, effective_date "
            "(DD/MM/YYYY). NO internal ids, NO symbols. Optional base_symbol "
            "/ source_symbol filters by SYMBOL (e.g. base_symbol='EGP'). "
            "USE THIS for 'currency exchange rate list as of <date>' / "
            "'FX rates today'. For a DATE RANGE use fx_rate_range instead. "
            "Only currencies marked Base Currency = Yes appear as base "
            "(matches the native page — excludes non-base currencies like "
            "Turkish Lira). Never hand-write SuiteQL or use saved search 705."
        ),
        "required": {"as_of_date": _v_date},
        "optional": {
            "base_symbol":   _v_currency_symbol,
            "source_symbol": _v_currency_symbol,
        },
        "sql": """
WITH latest AS (
  SELECT cr.basecurrency,
         cr.transactioncurrency,
         MAX(cr.effectivedate) AS effectivedate
  FROM   currencyrate cr
  WHERE  cr.effectivedate <= TO_DATE('{as_of_date}', 'YYYY-MM-DD')
  GROUP BY cr.basecurrency, cr.transactioncurrency
)
SELECT
  bc.name                                     AS base_currency,
  tc.name                                     AS source_currency,
  cr.exchangerate                             AS exchange_rate,
  TO_CHAR(cr.effectivedate, 'DD/MM/YYYY')     AS effective_date
FROM currencyrate cr
JOIN latest l   ON l.basecurrency        = cr.basecurrency
               AND l.transactioncurrency = cr.transactioncurrency
               AND l.effectivedate       = cr.effectivedate
JOIN currency bc ON bc.id = cr.basecurrency
JOIN currency tc ON tc.id = cr.transactioncurrency
WHERE bc.isbasecurrency = 'T'   -- only true base currencies (matches the native page; excludes e.g. Turkish Lira which has rate rows but is Base Currency = No)
  {{base_symbol: AND bc.symbol = '{base_symbol}' }}
  {{source_symbol: AND tc.symbol = '{source_symbol}' }}
ORDER BY bc.name, tc.name
""",
        "filename": "fx_rate_list_{as_of_date}",
    },

    # ─── 11. FX rate list over a DATE RANGE (every effective date in range) ─
    # Akansha 2026-06-30: "currency exchange rate list from 1st June to 30th
    # June for all base and source currency." Same full-name columns as
    # fx_rate_list, but returns EVERY effective-dated row in the range (not
    # just the latest per pair). Backed by currencyrate; NO internal ids.
    "fx_rate_range": {
        "description": (
            "Currency exchange rates over a DATE RANGE (from_date..to_date) — "
            "every effective-dated rate for every base x source pair in the "
            "window. Same full-name columns as fx_rate_list: base_currency "
            "(FULL NAME), source_currency (FULL NAME), exchange_rate, "
            "effective_date (DD/MM/YYYY). NO internal ids, NO symbols. Optional "
            "base_symbol / source_symbol filters. USE THIS when the user asks "
            "for FX rates 'from <date> to <date>' / 'for June' / a month or "
            "period. For a single as-of snapshot use fx_rate_list. Only "
            "currencies marked Base Currency = Yes appear as base (matches the "
            "native page; excludes non-base like Turkish Lira)."
        ),
        "required": {"from_date": _v_date, "to_date": _v_date},
        "optional": {
            "base_symbol":   _v_currency_symbol,
            "source_symbol": _v_currency_symbol,
        },
        "sql": """
SELECT
  bc.name                                     AS base_currency,
  tc.name                                     AS source_currency,
  cr.exchangerate                             AS exchange_rate,
  TO_CHAR(cr.effectivedate, 'DD/MM/YYYY')     AS effective_date
FROM currencyrate cr
JOIN currency bc ON bc.id = cr.basecurrency
JOIN currency tc ON tc.id = cr.transactioncurrency
WHERE cr.effectivedate BETWEEN TO_DATE('{from_date}', 'YYYY-MM-DD')
                           AND TO_DATE('{to_date}',   'YYYY-MM-DD')
  AND bc.isbasecurrency = 'T'   -- only true base currencies (matches the native page; excludes non-base like Turkish Lira)
  {{base_symbol: AND bc.symbol = '{base_symbol}' }}
  {{source_symbol: AND tc.symbol = '{source_symbol}' }}
ORDER BY bc.name, tc.name, cr.effectivedate
""",
        "filename": "fx_rate_range_{from_date}_to_{to_date}",
    },
}


def _strip_optional_blocks(sql, params):
    """Process {{name: ... }} markers — keep the block if `name` is in
    params (and substitute), drop it otherwise.
    """
    out = sql
    pattern = _re.compile(r"\{\{\s*(\w+)\s*:(.*?)\}\}", _re.DOTALL)
    while True:
        m = pattern.search(out)
        if not m:
            break
        name, body = m.group(1), m.group(2)
        if name in params and params[name] not in (None, ""):
            replacement = body.format(**params)
        else:
            replacement = ""
        out = out[:m.start()] + replacement + out[m.end():]
    return out


def execute_run_standard_report(report_name, params=None, scope="prod",
                                 filename_hint=None,
                                 max_rows=None):
    """Look up a named report template, validate + substitute params,
    then run via execute_export_suiteql_to_csv. The full result set
    stays on disk — only a 3-row preview reaches the LLM context.

    Returns the same shape as execute_export_suiteql_to_csv, plus a
    `report_name` field for tracing.
    """
    if report_name not in STANDARD_REPORTS:
        return {
            "ok": False,
            "error": "UNKNOWN_REPORT",
            "message": (
                f"Unknown report '{report_name}'. Available: "
                f"{', '.join(sorted(STANDARD_REPORTS.keys()))}."
            ),
            "available": sorted(STANDARD_REPORTS.keys()),
        }

    report = STANDARD_REPORTS[report_name]
    params = dict(params or {})

    # 1. Validate required params
    missing = [k for k in report["required"] if k not in params or params[k] in (None, "")]
    if missing:
        return {
            "ok": False,
            "error": "MISSING_PARAMS",
            "message": f"Report '{report_name}' requires: {missing}.",
            "required_params": list(report["required"].keys()),
            "optional_params": list(report["optional"].keys()),
        }

    # 2. Run validators (raises → return error)
    validated = {}
    try:
        for k, validator in report["required"].items():
            validated[k] = validator(params[k])
        for k, validator in report["optional"].items():
            if k in params and params[k] not in (None, ""):
                validated[k] = validator(params[k])
    except ValueError as e:
        return {"ok": False, "error": "INVALID_PARAM", "message": str(e)}

    # 2b. Apply per-template defaults for optional params the user didn't
    # supply. Defaults are stored pre-validated (e.g. an account_codes
    # default of "'12030', '21030'" is already SQL-list-formatted) so they
    # substitute directly into the SQL placeholder.
    for k, default in report.get("defaults", {}).items():
        if k not in validated:
            validated[k] = default

    # 3. Substitute placeholders. Process optional blocks first so missing
    #    params don't break the subsequent .format().
    try:
        sql = _strip_optional_blocks(report["sql"], validated)
        sql = sql.format(**validated)
    except KeyError as e:
        return {"ok": False, "error": "TEMPLATE_PARAM_MISSING",
                "message": f"Template references {e} but it was not supplied."}

    # 4. Build filename hint
    if not filename_hint:
        try:
            filename_hint = report["filename"].format(**validated)
        except KeyError:
            filename_hint = f"{report_name}_{datetime.utcnow().strftime('%Y%m%d')}"

    # 5. Hand off to the export tool
    export_kwargs = {"filename_hint": filename_hint, "scope": scope}
    if max_rows:
        export_kwargs["max_rows"] = max_rows
    result = execute_export_suiteql_to_csv(sql, **export_kwargs)

    if isinstance(result, dict):
        result["report_name"] = report_name
        result["params"] = validated
    return result


# ─────────────────────────────────────────────────────────────────────────
# Schema-discovery + atomic multi-export tools
# ─────────────────────────────────────────────────────────────────────────
# Two tools that together let the agent answer "I don't know the schema for
# this — figure it out" without falling back to silence:
#
#   discover_table(name)         — schema probe; returns columns + sample row
#   export_access_audit(scope)   — atomic 3-CSV bundle (users/roles/mapping)
#                                  with per-query status (one 403 doesn't
#                                  swallow the other two).
#
# Both are read-only against prod. Both return ok=False with a verbatim
# NetSuite error on failure — they never silently drop work.

# Whitelist for discover_table's table-name argument. SuiteQL identifiers
# are alpha-num-underscore only; we reject everything else to prevent
# someone from sneaking SQL fragments in via the table name.
_DISCOVER_TABLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _suiteql_error_summary(rs):
    """Best-effort extraction of a human-readable error from a SuiteQL
    response that didn't succeed. Returns "" if the response looks fine.
    """
    if not isinstance(rs, dict):
        return ""
    if rs.get("error"):
        return _safe_str(rs.get("error"), cap=200)
    status = rs.get("status")
    if status in (400, 401, 403, 404, 500):
        msg = (rs.get("title") or rs.get("detail")
               or (rs.get("o:errorDetails") or [{}])[0].get("detail", "")
               or rs.get("message") or "")
        return _safe_str(f"HTTP {status}: {msg}" if msg else f"HTTP {status}", cap=200)
    if rs.get("type") == "error":
        return _safe_str(rs.get("title") or rs.get("detail") or "error", cap=200)
    return ""


def execute_discover_table(table_name, scope="prod"):
    """Schema-discovery helper. Returns columns + one sample row + row
    count, OR an explicit error with suggested alternatives.

    Use this when you need to write a SuiteQL query but don't know the
    table's columns — cheaper than guessing column names from training
    data, and the result is grounded in the live schema.

    Returns:
      ok=True:   {table, columns, sample_row, row_count, scope}
      ok=False:  {table, error, message, suggested_alternatives, scope}
    """
    if not table_name or not isinstance(table_name, str):
        return {"ok": False, "error": "BAD_INPUT",
                "message": "discover_table requires a non-empty table_name string."}

    clean = table_name.strip()
    if not _DISCOVER_TABLE_RE.match(clean):
        return {"ok": False, "error": "INVALID_TABLE_NAME",
                "message": ("Table name must start with a letter and contain "
                            "only letters, digits, underscore (max 64 chars).")}

    # Step 1 — row count. Cheapest possible query; tells us whether the
    # integration role can see the table at all.
    count_rs = execute_suiteql(f"SELECT COUNT(*) AS rowcount FROM {clean}",
                               scope=scope)
    err = _suiteql_error_summary(count_rs)
    if err:
        # Generate near-neighbour suggestions. Cheap heuristic — strip
        # plural, swap user↔employee, swap permission↔role, etc.
        lc = clean.lower()
        suggestions = []
        for alt in (
            lc + "s" if not lc.endswith("s") else lc[:-1],
            "employee" if "user" in lc else None,
            "role" if "permission" in lc else None,
            "employeerolesforsearch" if "userrole" in lc or "roleassign" in lc else None,
            "subsidiary" if "company" in lc or "entity" in lc else None,
        ):
            if alt and alt != lc and alt not in suggestions:
                suggestions.append(alt)
        return {
            "ok": False, "table": clean, "scope": scope,
            "error": "TABLE_INACCESSIBLE",
            "message": (f"Table `{clean}` not found, or integration role "
                        f"lacks read permission. NetSuite said: {err}. "
                        "If you wanted a record type rather than a SuiteQL "
                        "table, try metadata_catalog instead."),
            "suggested_alternatives": suggestions[:5],
        }

    items = count_rs.get("items") or []
    row_count = items[0].get("rowcount") if items else None

    # Step 2 — fetch a single sample row to learn column names + types.
    sample_rs = execute_suiteql(
        f"SELECT * FROM {clean} FETCH FIRST 1 ROWS ONLY", scope=scope)
    err = _suiteql_error_summary(sample_rs)
    columns = []
    sample_row = None
    if err:
        # COUNT(*) worked but SELECT * didn't — odd, but report it. Some
        # tables have row-level perms that allow count but not select.
        return {
            "ok": True, "table": clean, "scope": scope,
            "row_count": row_count, "columns": [], "sample_row": None,
            "partial": True,
            "message": (f"Table `{clean}` exists ({row_count} rows) but "
                        f"sample SELECT failed: {err}. Try naming explicit "
                        "columns rather than SELECT *."),
        }
    rows = sample_rs.get("items") or []
    if rows:
        first = rows[0]
        columns = [c for c in first.keys() if c != "links"]
        sample_row = {c: _safe_str(first.get(c), cap=120) for c in columns}

    return {
        "ok": True, "table": clean, "scope": scope,
        "row_count": row_count,
        "columns": columns,
        "sample_row": sample_row,
        "message": (f"Table `{clean}` is accessible. {len(columns)} columns, "
                    f"~{row_count} rows. Build the real query from these "
                    "columns — don't guess."),
    }


# ── export_access_audit — atomic 3-CSV bundle ────────────────────────────
#
# Three queries are tried in fixed order. Each is independent: one failure
# does NOT abort the others. Per-query status is reported in the response
# so the agent can surface failures verbatim per Rule 5 / §5.15.
#
# IMPORTANT: NetSuite does NOT expose the per-role permission grid via
# SuiteQL. The role table has metadata only (name, centertype, restrict
# settings) — not the View/Edit/Full matrix per record type. That export
# is admin-only (Akansha) via Setup → Users/Roles → Manage Roles → Export
# or a SuiteScript dump. The audit tool is honest about this gap.

_ACCESS_AUDIT_QUERIES = [
    {
        "key": "users",
        "label": "Active users with login enabled",
        "filename": "ns_access_users",
        # Use BUILTIN.DF where available; fall back to subselect for subsidiary.
        # giveaccess='T' is the canonical "login enabled" flag.
        "sql": (
            "SELECT "
            "  e.id, "
            "  e.entityid, "
            "  e.firstname, "
            "  e.lastname, "
            "  e.email, "
            "  e.title, "
            "  e.giveaccess, "
            "  e.isinactive, "
            "  (SELECT s.name FROM subsidiary s WHERE s.id = e.subsidiary) AS subsidiary "
            "FROM employee e "
            "WHERE e.giveaccess = 'T' "
            "  AND e.isinactive = 'F' "
            "ORDER BY e.entityid"
        ),
    },
    {
        "key": "roles",
        "label": "Active roles (metadata only — NOT the permission grid)",
        "filename": "ns_access_roles",
        "sql": (
            "SELECT "
            "  r.id, "
            "  r.name, "
            "  r.centertype, "
            "  r.issalesrole, "
            "  r.isinactive, "
            "  r.restrictbydevice "
            "FROM role r "
            "WHERE r.isinactive = 'F' "
            "ORDER BY r.name"
        ),
    },
    {
        "key": "user_role_map",
        "label": "User × role assignment map",
        "filename": "ns_access_user_role_map",
        # At Wego, the working table is `employeeroles` (verified live via the
        # bot's 2026-05-22 reply pulling role names from this exact join).
        # `employeerolesforsearch` is the canonical NS view name in some
        # editions but is NOT exposed in Wego's integration role — calling it
        # returns "Record 'employeerolesforsearch' was not found". If this
        # leg fails in a future edition / role change, the per-query status
        # in `execute_export_access_audit` surfaces it cleanly and the other
        # two CSVs still deliver. Agent should then `discover_table` for the
        # local equivalent (`employee_role`, `usertoroles`, etc.).
        "sql": (
            "SELECT "
            "  er.employee AS user_id, "
            "  e.entityid  AS user_name, "
            "  e.email     AS user_email, "
            "  er.role     AS role_id, "
            "  r.name      AS role_name, "
            "  r.centertype "
            "FROM employeeroles er "
            "JOIN employee e ON er.employee = e.id "
            "JOIN role r     ON er.role     = r.id "
            "WHERE e.giveaccess = 'T' "
            "  AND e.isinactive = 'F' "
            "  AND r.isinactive = 'F' "
            "ORDER BY e.entityid, r.name"
        ),
    },
]


def execute_export_access_audit(scope="prod"):
    """Atomic 3-CSV access-audit export.

    Runs three independent SuiteQL queries — users, roles, user×role
    assignments — and writes one CSV per query. Per-query status is
    reported so the agent can never silently partial-deliver.

    The permission grid (Role × record-type × View/Edit/Full) is NOT
    queryable via SuiteQL — that's an admin export and is named in the
    response so the agent surfaces the gap verbatim.

    Returns:
      {
        ok: True if at least one query succeeded; False if all three failed,
        scope: "prod" | "sandbox",
        results: { users: {ok, file_path, row_count, preview, ...},
                   roles: {...},
                   user_role_map: {...} },
        permission_grid_note: "<honest message about Akansha-only export>",
        summary: "<one-line human readable>",
      }
    """
    out = {"scope": scope, "results": {}}
    any_ok = False
    failures = []

    for q in _ACCESS_AUDIT_QUERIES:
        # execute_export_suiteql_to_csv already returns a typed dict and
        # never raises — perfect building block for "run all, report each".
        res = execute_export_suiteql_to_csv(
            query=q["sql"],
            filename_hint=q["filename"],
            scope=scope,
        )
        # Tag each result with the query label so the agent can build a
        # one-line-per-csv summary.
        if isinstance(res, dict):
            res["label"] = q["label"]
        out["results"][q["key"]] = res
        if isinstance(res, dict) and res.get("ok") and res.get("row_count", 0) > 0:
            any_ok = True
        else:
            err = (res.get("error") if isinstance(res, dict) else "UNKNOWN") or "EMPTY"
            failures.append(f"{q['key']}: {err}")

    out["ok"] = any_ok
    out["permission_grid_note"] = (
        "Per-role permission grid (Role × record-type × View/Edit/Full) is "
        "NOT exportable via SuiteQL — NetSuite doesn't expose the role-permission "
        "line table. For the full matrix, Akansha needs to export from "
        "Setup → Users/Roles → Manage Roles → Export List, or run a Saved Search "
        "of type 'Role' with permission columns added."
    )

    if any_ok and not failures:
        out["summary"] = (
            f"✅ Access audit exported — 3/3 CSVs written. "
            f"Users: {out['results']['users'].get('row_count')}, "
            f"Roles: {out['results']['roles'].get('row_count')}, "
            f"User×Role: {out['results']['user_role_map'].get('row_count')}."
        )
    elif any_ok:
        out["summary"] = (
            f"⚠️ Access audit partial — {len(_ACCESS_AUDIT_QUERIES) - len(failures)}/"
            f"{len(_ACCESS_AUDIT_QUERIES)} CSVs written. "
            f"Failed: {'; '.join(failures)}. "
            "Surface these to the user verbatim per Rule 5 — do not hide."
        )
    else:
        out["summary"] = (
            f"❌ Access audit failed — 0/{len(_ACCESS_AUDIT_QUERIES)} CSVs written. "
            f"Errors: {'; '.join(failures)}. "
            "Likely cause: integration role lacks read permission on these "
            "tables. Tag Akansha to widen the role."
        )
    return out


# ─────────────────────────────────────────────────────────────────────────
# Role-permissions — calls the existing restlet_companion (no new deploy)
# ─────────────────────────────────────────────────────────────────────────
# The role-permission grid (Role × record-type × Level) is blocked from
# SuiteQL and the REST Record API for the integration role. We piggyback
# on the EXISTING restlet_companion.js (already deployed; handles
# saved_search / file_get / file_put) by adding a 4th action,
# 'role_permissions'. That handler uses N/record.load('role') which CAN
# see the permissions sublist.
#
# No new env vars. Reuses the same pair the saved_search path uses:
#   NETSUITE_PRODUCTION_RESTLET_SCRIPT_ID + NETSUITE_PRODUCTION_RESTLET_DEPLOYMENT_ID
#   (or sandbox equivalents)
#
# To enable: upload the latest references/restlet_companion.js to the
# File Cabinet, replacing the old version. NetSuite uses the new code on
# the next call — no new Script record, no new Deployment, no env-var
# change, no OpenClaw container restart needed.

def execute_get_role_permissions(role_ids=None, include_inactive=False, scope="prod"):
    """Fetch the per-role permission grid via the EXISTING restlet companion.

    POSTs to the deployed restlet_companion with action='role_permissions'.
    Reuses NETSUITE_<SCOPE>_RESTLET_SCRIPT_ID / _DEPLOYMENT_ID — the same
    env vars saved_search / file_get / file_put already use. No new env
    vars to set.

    Args:
        role_ids: Optional list[str] or comma-string of role internal IDs.
                  If omitted, the RESTlet returns ALL active roles (capped
                  at 50 by the RESTlet — page if you have more).
        include_inactive: Optional bool; include inactive roles (default False).
        scope: "prod" or "sandbox".

    Returns:
        {"ok": True, "action": "role_permissions", "count": N,
         "roles": [{role_id, role_name, permissions:[...]}, ...]}
        OR
        {"ok": False, "error": "<CODE>", "message": "<verbatim>"}

    Error codes:
        RESTLET_NOT_DEPLOYED — companion env vars missing (rare —
                              saved_search uses the same vars)
        RESTLET_HANDLER_STALE — RESTlet is reachable but the deployed JS
                              predates the role_permissions action;
                              uploader replaces File Cabinet copy with
                              references/restlet_companion.js (no other
                              changes needed)
        RESTLET_HTTP_<status> — non-200 response from NetSuite
        INVALID_RESTLET_RESPONSE — response wasn't JSON
        INVALID_ROLE_IDS — caller passed non-integer role id
    """
    scope_up = (scope or "prod").upper()
    if scope_up == "PROD":
        scope_up = "PRODUCTION"
    script_var = f"NETSUITE_{scope_up}_RESTLET_SCRIPT_ID"
    deploy_var = f"NETSUITE_{scope_up}_RESTLET_DEPLOYMENT_ID"

    script_id = os.environ.get(script_var, "").strip()
    deploy_id = os.environ.get(deploy_var, "").strip()

    if not script_id or not deploy_id:
        return {
            "ok": False,
            "error": "RESTLET_NOT_DEPLOYED",
            "message": (
                f"restlet_companion env vars missing for scope={scope}: "
                f"need {script_var} and {deploy_var}. These are the SAME "
                f"vars saved_search / file_get / file_put already use — if "
                f"those work in this environment and this doesn't, the env "
                f"vars got dropped. If they're not set at all, deploy "
                f"restlet_companion.js per "
                f"skills/wego-netsuite/references/restlet_deployment.md "
                f"first."
            ),
        }

    # Validate role_ids — only digits allowed per entry.
    role_ids_payload = None
    if role_ids is not None:
        if isinstance(role_ids, list):
            cleaned = [str(r).strip() for r in role_ids if str(r).strip()]
        else:
            cleaned = [s.strip() for s in str(role_ids).split(",") if s.strip()]
        for rid in cleaned:
            if not rid.isdigit():
                return {
                    "ok": False,
                    "error": "INVALID_ROLE_IDS",
                    "message": f"role_ids must be integers. Got: {rid!r}",
                }
        role_ids_payload = cleaned or None

    try:
        creds = get_credentials(scope)
    except Exception as e:
        return {"ok": False, "error": "CRED_LOOKUP_FAILED",
                "message": f"Could not load NetSuite credentials for scope={scope}: {e}"}

    host = f"{url_form(creds['account_id'])}.restlets.api.netsuite.com"
    url = (f"https://{host}/app/site/hosting/restlet.nl"
           f"?script={urllib.parse.quote(script_id)}"
           f"&deploy={urllib.parse.quote(deploy_id)}")

    payload = {"action": "role_permissions"}
    if role_ids_payload:
        payload["role_ids"] = role_ids_payload
    if include_inactive:
        payload["include_inactive"] = True
    body_to_send = json.dumps(payload)

    try:
        auth = oauth_header(
            "POST", url,
            creds["client_id"], creds["client_secret"],
            creds["token_id"], creds["token_secret"],
            creds["account_id"],
        )
    except Exception as e:
        return {"ok": False, "error": "OAUTH_SIGN_FAILED",
                "message": f"Could not sign RESTlet request: {e}"}

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-d", body_to_send,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "RESTLET_TIMEOUT",
                "message": "RESTlet call timed out after 60s."}

    raw = (result.stdout or "").rstrip()
    if not raw:
        return {"ok": False, "error": "EMPTY_RESPONSE",
                "message": f"RESTlet returned no body. stderr: {result.stderr[:300]}"}

    # Last line is HTTP code (from -w '\n%{http_code}'); everything before is body.
    body, _, http_code = raw.rpartition("\n")
    if not body:
        body = http_code
        http_code = ""

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "INVALID_RESTLET_RESPONSE",
            "message": f"HTTP {http_code or '?'} — response wasn't JSON: {body[:300]}",
        }

    if http_code and not http_code.startswith("2"):
        return {
            "ok": False,
            "error": f"RESTLET_HTTP_{http_code}",
            "message": f"NetSuite RESTlet returned HTTP {http_code}: {body[:300]}",
            "raw": data,
        }

    # If the deployed restlet_companion.js predates the role_permissions
    # action, it returns ok=false, error_code='unknown_action'. Translate
    # to a clearer code so the agent surfaces the right unblocker (replace
    # the File Cabinet copy of the script — no env change, no redeploy).
    if isinstance(data, dict) and data.get("ok") is False:
        if data.get("error_code") == "unknown_action":
            return {
                "ok": False,
                "error": "RESTLET_HANDLER_STALE",
                "message": (
                    "The deployed restlet_companion.js predates the "
                    "role_permissions action. Replace the File Cabinet copy "
                    "of the script with the latest "
                    "skills/wego-netsuite/references/restlet_companion.js — "
                    "NetSuite auto-uses the new code on the next call. No "
                    "new Script record, no new Deployment, no env-var "
                    "change, no OpenClaw restart needed."
                ),
                "raw": data,
            }

    # The RESTlet itself sets ok=True/False — pass through.
    return data


# ─────────────────────────────────────────────────────────────────────────
# Saved-search runner — paste a NetSuite saved-search URL (or its id) and
# the bot loads + runs it by id over OAuth TBA (no browser session needed).
# Reuses the EXISTING restlet_companion `saved_search` action — the finance
# team maintains the search in the NetSuite UI; the bot just executes it.
# ─────────────────────────────────────────────────────────────────────────

# Registry of known saved searches (intent -> id). Source of truth is the
# JSON file; finance users never paste URLs/ids — the agent matches their
# question to an entry here and runs it by id. Override path with
# NETSUITE_SAVED_SEARCHES_FILE.
SAVED_SEARCHES_FILE = os.environ.get(
    "NETSUITE_SAVED_SEARCHES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "skills", "wego-netsuite", "references",
                 "saved_searches.json"),
)


def load_saved_search_registry():
    """Read the saved-search registry JSON. Returns a dict:
        {"ok": True, "searches": [...], "by_key": {key: entry}}
    or {"ok": False, "error": ..., "searches": [], "by_key": {}} if the
    file is missing/unreadable (graceful — the URL/id path still works)."""
    path = SAVED_SEARCHES_FILE
    if not os.path.exists(path):
        return {"ok": False, "error": "REGISTRY_NOT_FOUND",
                "message": f"saved_searches.json not found at {path}",
                "searches": [], "by_key": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": "REGISTRY_UNREADABLE",
                "message": f"Could not read {path}: {e}",
                "searches": [], "by_key": {}}
    searches = data.get("searches") or []
    by_key = {s["key"]: s for s in searches if s.get("key")}
    return {"ok": True, "searches": searches, "by_key": by_key,
            "matching_rules": data.get("matching_rules", {})}


def _collapse_text_columns(rows):
    """The RESTlet returns BOTH the raw value (key `X`) and, when it differs,
    the display label (key `X_text`) for select/list columns. NetSuite's UI
    shows the label, and finance doesn't want the duplicate `_text` columns
    (Akansha 2026-06-30: the export was "adding two additional columns:
    Name_text, Type_text"). For each base key `X` that has a sibling `X_text`,
    keep the human-readable label in `X` and drop `X_text`. `_text` keys with
    no matching base key are left untouched (nothing to merge into)."""
    out = []
    for r in rows:
        if not isinstance(r, dict):
            out.append(r)
            continue
        drop = {k for k in r if k.endswith("_text") and k[:-5] in r}
        merged = {}
        for k, val in r.items():
            if k in drop:
                continue
            tkey = k + "_text"
            if tkey in r and r.get(tkey) not in (None, ""):
                merged[k] = r[tkey]      # prefer the label NetSuite displays
            else:
                merged[k] = val
        out.append(merged)
    return out


def _write_rows_to_csv(rows, filename_hint, scope="prod"):
    """Write a list of dict rows (from a saved search) to a CSV in
    EXPORT_DIR. Header is the union of keys across rows, in first-seen
    order. Returns (file_path, columns, preview3) or raises OSError."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    columns = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug(filename_hint, default=f"saved_search_{scope}")
    file_path = os.path.join(EXPORT_DIR, f"{slug}_{timestamp}.csv")
    with open(file_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return file_path, columns, rows[:3]


def _parse_saved_search_id(value):
    """Accept any of these and return the saved-search identifier as a str,
    or None if nothing usable is found:

      • a full NetSuite UI URL:
          https://5564218.app.netsuite.com/app/common/search/searchresults.nl?searchid=705&whence=
          …/search/search.nl?id=705
      • a bare internal id:        "705"
      • a script-id style id:      "customsearch_ar_aging" / "customsearch123"

    NetSuite's search.load({id}) accepts BOTH the numeric internal id and the
    string scriptId, so we pass whichever the user gave through unchanged.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # URL form — pull searchid / id out of the query string.
    if "://" in s or "searchresults.nl" in s or "search.nl" in s or "?" in s:
        try:
            parsed = urllib.parse.urlparse(s)
            qs = urllib.parse.parse_qs(parsed.query)
            for key in ("searchid", "id", "searchId", "ID"):
                if key in qs and qs[key]:
                    cand = qs[key][0].strip()
                    if cand:
                        s = cand
                        break
        except Exception:
            pass  # fall through to the raw-value checks below

    # Bare numeric internal id.
    if s.isdigit():
        return s
    # Script-id style (customsearch...) — letters, digits, underscores.
    if _re.match(r"^[A-Za-z][\w]{2,80}$", s):
        return s
    return None


def execute_run_saved_search(search_ref=None, scope="prod", filters=None,
                             row_cap=50000, page_size=1000,
                             key=None, export_csv=False, filename_hint=None):
    """Run a NetSuite saved search BY ID via the existing restlet_companion
    `saved_search` action. Reuses the same RESTlet env vars / OAuth that
    get_role_permissions uses — no new deploy, no browser.

    Resolution order for WHICH search to run:
        1. key      — a registry key from saved_searches.json (preferred;
                      this is how the agent self-serves by intent — finance
                      users never pass a URL/id).
        2. search_ref — a saved-search id ("705"), script id
                      ("customsearch_x"), or a pasted UI URL (we extract id).

    Args:
        search_ref: id / script id / UI URL (used if `key` is not given).
        key: registry key (e.g. "ar_aging"). Looks up the id
             in saved_searches.json.
        scope: "prod" or "sandbox".
        filters: optional NetSuite filter-expression override (advanced).
        row_cap: max rows to return (RESTlet hard cap; default 50000).
        page_size: page size for runPaged (<=1000).
        export_csv: if True, write the rows to a CSV in EXPORT_DIR and return
                    file_path + a 3-row preview instead of all rows inline
                    (use for list/report asks, then upload_file_to_slack).
        filename_hint: optional CSV filename slug (defaults to the registry
                    title or the search id).

    Returns:
        {"ok": True, "action": "saved_search", "search_id": "705",
         "row_count": N, "rows": [...]}                      (export_csv=False)
        {"ok": True, "action": "saved_search", "search_id": "705",
         "row_count": N, "file_path": "...", "columns": [...],
         "preview": [...3 rows...]}                          (export_csv=True)
      OR {"ok": False, "error": "<CODE>", "message": "<verbatim>"}

    Error codes mirror execute_get_role_permissions, plus:
        INVALID_SEARCH_REF — neither key nor a usable search_ref was given
        UNKNOWN_REGISTRY_KEY — key not found in saved_searches.json
        RESTLET_HANDLER_STALE — deployed restlet predates saved_search action
    """
    registry_title = None
    # 1. Registry key wins.
    if key:
        reg = load_saved_search_registry()
        entry = reg["by_key"].get(key)
        if not entry:
            return {
                "ok": False,
                "error": "UNKNOWN_REGISTRY_KEY",
                "message": (
                    f"No saved search registered under key {key!r}. Known "
                    f"keys: {sorted(reg['by_key'].keys()) or '(registry empty)'}. "
                    f"Add it to saved_searches.json or pass search_ref."
                ),
                "known_keys": sorted(reg["by_key"].keys()),
            }
        search_id = _parse_saved_search_id(entry.get("search_id"))
        registry_title = entry.get("title")
        if scope == "prod" and entry.get("scope"):
            scope = entry["scope"]
        if export_csv is False and entry.get("default_export_csv"):
            export_csv = True
        if not filename_hint and registry_title:
            filename_hint = registry_title
    else:
        search_id = _parse_saved_search_id(search_ref)

    if not search_id:
        return {
            "ok": False,
            "error": "INVALID_SEARCH_REF",
            "message": (
                f"No usable saved search given. Pass `key` (a registry key "
                f"from saved_searches.json) OR `search_ref` (id like 705, "
                f"script id, or a UI URL with searchid=). Got "
                f"key={key!r}, search_ref={search_ref!r}."
            ),
        }

    scope_up = (scope or "prod").upper()
    if scope_up == "PROD":
        scope_up = "PRODUCTION"
    script_var = f"NETSUITE_{scope_up}_RESTLET_SCRIPT_ID"
    deploy_var = f"NETSUITE_{scope_up}_RESTLET_DEPLOYMENT_ID"
    script_id = os.environ.get(script_var, "").strip()
    deploy_id = os.environ.get(deploy_var, "").strip()
    if not script_id or not deploy_id:
        return {
            "ok": False,
            "error": "RESTLET_NOT_DEPLOYED",
            "message": (
                f"restlet_companion env vars missing for scope={scope}: "
                f"need {script_var} and {deploy_var}. Same vars role_permissions "
                f"/ file_get use. If unset, deploy restlet_companion.js per "
                f"skills/wego-netsuite/references/restlet_deployment.md first."
            ),
        }

    try:
        page_size = min(int(page_size or 1000), 1000)
        row_cap = max(1, int(row_cap or 5000))
    except (TypeError, ValueError):
        return {"ok": False, "error": "INVALID_PARAM",
                "message": "row_cap and page_size must be integers."}

    try:
        creds = get_credentials(scope)
    except Exception as e:
        return {"ok": False, "error": "CRED_LOOKUP_FAILED",
                "message": f"Could not load NetSuite credentials for scope={scope}: {e}"}

    host = f"{url_form(creds['account_id'])}.restlets.api.netsuite.com"
    url = (f"https://{host}/app/site/hosting/restlet.nl"
           f"?script={urllib.parse.quote(script_id)}"
           f"&deploy={urllib.parse.quote(deploy_id)}")

    params = {"page_size": page_size, "row_cap": row_cap}
    if filters:
        params["filters"] = filters
    payload = {"action": "saved_search", "search_id": search_id, "params": params}
    body_to_send = json.dumps(payload)

    try:
        auth = oauth_header(
            "POST", url,
            creds["client_id"], creds["client_secret"],
            creds["token_id"], creds["token_secret"],
            creds["account_id"],
        )
    except Exception as e:
        return {"ok": False, "error": "OAUTH_SIGN_FAILED",
                "message": f"Could not sign RESTlet request: {e}"}

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-d", body_to_send,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "RESTLET_TIMEOUT",
                "message": "Saved-search RESTlet call timed out after 120s."}

    raw = (result.stdout or "").rstrip()
    if not raw:
        return {"ok": False, "error": "EMPTY_RESPONSE",
                "message": f"RESTlet returned no body. stderr: {result.stderr[:300]}"}

    body, _, http_code = raw.rpartition("\n")
    if not body:
        body = http_code
        http_code = ""

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"ok": False, "error": "INVALID_RESTLET_RESPONSE",
                "message": f"HTTP {http_code or '?'} — response wasn't JSON: {body[:300]}"}

    if http_code and not http_code.startswith("2"):
        return {"ok": False, "error": f"RESTLET_HTTP_{http_code}",
                "message": f"NetSuite RESTlet returned HTTP {http_code}: {body[:300]}",
                "raw": data}

    if isinstance(data, dict) and data.get("ok") is False:
        if data.get("error_code") == "unknown_action":
            return {
                "ok": False,
                "error": "RESTLET_HANDLER_STALE",
                "message": (
                    "The deployed restlet_companion.js predates the "
                    "saved_search action. Replace the File Cabinet copy with "
                    "the latest skills/wego-netsuite/references/restlet_companion.js "
                    "— NetSuite auto-uses the new code on the next call. No new "
                    "Script record, Deployment, env-var, or OpenClaw restart "
                    "needed."
                ),
                "raw": data,
            }

    # Annotate with registry title for clean source-tagging by the agent.
    if isinstance(data, dict) and registry_title:
        data["title"] = registry_title

    # Drop the duplicate `_text` columns the RESTlet emits (Akansha 2026-06-30).
    if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
        data["rows"] = _collapse_text_columns(data["rows"])

    # Optional CSV export — for list/report asks, hand back a file_path the
    # agent uploads via upload_file_to_slack, plus a 3-row preview, instead of
    # dumping up to row_cap rows into the LLM context.
    if export_csv and isinstance(data, dict) and data.get("ok") and data.get("rows"):
        rows = data.get("rows") or []
        try:
            file_path, columns, preview = _write_rows_to_csv(
                rows, filename_hint or f"saved_search_{search_id}", scope)
        except OSError as e:
            data["export_error"] = f"could not write CSV: {e}"
            return data
        return {
            "ok": True,
            "action": "saved_search",
            "search_id": data.get("search_id", search_id),
            "title": registry_title,
            "row_count": data.get("row_count", len(rows)),
            "file_path": file_path,
            "columns": columns,
            "preview": preview,
        }

    return data


# ─────────────────────────────────────────────────────────────────────────
# File Cabinet — fetch a file's content via the RESTlet `file_get` action.
# Metadata/lookup goes through the SuiteQL `file` table; content comes back
# base64 from the RESTlet and is written to EXPORT_DIR, ready for
# upload_file_to_slack. Built for the "Reports via Schedule Script" folder
# pattern (scheduled NetSuite reports dropped as .xlsx into the cabinet).
# ─────────────────────────────────────────────────────────────────────────

_RESTLET_FILE_CAP_BYTES = 9 * 1024 * 1024  # RESTlet response cap is 10MB; keep margin


def _report_store_modules():
    """Import report_store/email_fetcher from scripts/report_store lazily —
    keeps server startup independent of them and picks up workspace updates."""
    import importlib.util
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_store")
    mods = {}
    for name in ("report_store", "email_fetcher"):
        spec = importlib.util.spec_from_file_location(name, os.path.join(base, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods


def execute_fetch_email_report(subject_contains, report_key, period=None, since_days=7):
    try:
        mods = _report_store_modules()
    except Exception as e:
        return {"ok": False, "error": "REPORT_STORE_IMPORT_FAILED", "message": str(e)[:300]}
    try:
        r = mods["email_fetcher"].fetch(subject_contains, report_key,
                                        period=period, since_days=int(since_days or 7))
    except Exception as e:
        return {"ok": False, "error": "EMAIL_FETCH_FAILED",
                "message": f"{type(e).__name__}: {e}"}
    slim = [{k: s.get(k) for k in ("report_key", "period", "filename", "size",
                                   "local_path", "s3_mirrored", "saved_at")}
            for s in r.get("saved", [])]
    out = {"ok": True, "emails_matched": r.get("emails_matched", 0),
           "files_saved": len(slim), "saved": slim,
           "auth_source": r.get("auth_source"),
           "mailbox_used": r.get("mailbox_used"),
           "candidates_seen": r.get("candidates_seen", 0)}
    if slim:
        out["message"] = (f"{len(slim)} attachment(s) stored under {report_key} "
                          f"(from {r.get('mailbox_used')}). Deliver via "
                          f"upload_file_to_slack.")
        return out
    # Zero matches: hand back WHY, so the reply can be specific instead of
    # "not in email" (which sent the agent hunting File Cabinet/saved searches).
    out["mailboxes_tried"] = r.get("mailboxes_tried")
    out["subjects_seen"] = r.get("subjects_seen")
    cand = r.get("candidates_seen", 0)
    if cand == 0:
        out["message"] = (
            f"No mail from {mods['email_fetcher'].FROM_ADDR} at all in the last {since_days} days "
            f"(mailboxes tried: {r.get('mailboxes_tried')}). Either this "
            f"mailbox ({os.environ.get('GMAIL_USER', 'rpa@wego.com')}) doesn't "
            f"receive the report — check it's a To/Cc recipient, not just "
            f"Akansha — or the window is too short. Do NOT substitute a saved "
            f"search or SuiteQL.")
    else:
        out["message"] = (
            f"{cand} email(s) from {mods['email_fetcher'].FROM_ADDR} found in {r.get('mailbox_used')}, "
            f"but none whose subject contains '{subject_contains}'. Subjects "
            f"actually present: {r.get('subjects_seen')}. Fix the "
            f"subject_contains string (or report_sources.json) to match one of "
            f"those — do NOT substitute a saved search or SuiteQL.")
    return out


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _normalise_period(text):
    """Turn whatever the user said into the ISO date the store is keyed by —
    the report's 'as of' date is dynamic, so accept every shape finance uses:
      '30/06/2026', '30-06-2026'        -> 2026-06-30  (DD/MM/YYYY, NetSuite order)
      '2026-06-30'                      -> 2026-06-30
      '30 June 2026', 'June 30 2026'    -> 2026-06-30
      'June 2026', 'Jun-2026', '06/2026'-> month END (2026-06-30)
      'June end' (no year)              -> month end, current year
    Returns None when the text carries no date (caller serves the latest)."""
    import calendar
    t = " ".join(str(text or "").lower().replace(",", " ").split())
    if not t:
        return None
    m = _re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = _re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", t)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if mo > 12 and d <= 12:
            d, mo = mo, d
        return f"{y:04d}-{mo:02d}-{d:02d}"
    mon = None
    for name, num in _MONTHS.items():
        if _re.search(rf"\b{name}\b", t) or _re.search(rf"\b{name[:3]}\b", t):
            mon = num
            break
    if mon:
        ym = _re.search(r"\b(20\d{2})\b", t)
        year = int(ym.group(1)) if ym else datetime.now().year
        rest = t.replace(str(year), " ") if ym else t
        dm = _re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", rest)
        day = int(dm.group(1)) if dm and 1 <= int(dm.group(1)) <= 31 else \
            calendar.monthrange(year, mon)[1]
        return f"{year:04d}-{mon:02d}-{day:02d}"
    m = _re.search(r"\b(\d{1,2})[/\-](20\d{2})\b", t)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"
    return None


def _report_registry_entry(report_key):
    try:
        reg = json.load(open(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "skills",
            "wego-netsuite", "references", "report_sources.json")))
    except Exception:
        return {}, []
    # Exact match first; then prefix match so 'ap_aging_detail_bk' finds
    # 'ap_aging_detail_bk_consolidated' (PR #127: the agent called the short key,
    # the registry stores the long one — both must work). A miss is also LEARNED:
    # it silently skips registry flags (deliver_as / refresh), which is exactly
    # how a raw .xls got served, so the alias gets fixed rather than papered over.
    reports = reg.get("reports", [])
    entry = next((r for r in reports if r.get("report_key") == report_key), None)
    if entry is None:
        entry = next((r for r in reports
                      if r.get("report_key", "").startswith(report_key)), None)
        _lessons().record("registry_miss", report_key=report_key,
                          resolved_to=(entry or {}).get("report_key"))
    entry = entry or {}
    return entry, (entry.get("subsidiaries") or reg.get("subsidiaries") or [])


def _lessons():
    """Load the self-learning capture module; returns a no-op stub on failure so
    a broken learning path can never break report serving."""
    try:
        import importlib.util as _ilu
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "report_store", "lessons.py")
        spec = _ilu.spec_from_file_location("lessons", fp)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        class _Stub:
            @staticmethod
            def record(*a, **k):
                pass
        return _Stub()


def _norm(s):
    return _re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _subsidiary_slug(name):
    return _re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _deliver_as_xlsx(paths, report_key, served_period):
    """Return ([single_xlsx_path], converted_bool) or an error dict.
    Priority: existing .xlsx -> any non-.xls raw (csv first) -> .xls last."""
    xlsx_paths = [p for p in paths if p.lower().endswith((".xlsx", ".xlsm"))]
    xls_paths = [p for p in paths if p.lower().endswith((".xls", ".xlsb"))]
    csv_paths = [p for p in paths if p.lower().endswith(".csv")]
    other_raw = [p for p in paths
                 if p not in xlsx_paths and p not in xls_paths and p not in csv_paths]
    if xlsx_paths:
        return [xlsx_paths[0]], False
    fs_mod = _load_filter_module()
    if isinstance(fs_mod, dict):
        return fs_mod, None
    src_file = (csv_paths or other_raw or xls_paths or paths)[0]
    try:
        conv = fs_mod.convert_to_xlsx(src_file)
    except RuntimeError as e:
        _lessons().record("report_error", report_key=report_key,
                          error="CONVERSION_FAILED", period=served_period, message=str(e))
        return {"ok": False, "error": "CONVERSION_FAILED", "message": str(e)[:400]}, None
    return [conv["out_path"]], True


def _load_filter_module():
    """Load scripts/report_store/filter_subsidiary.py; returns the module, or an
    error dict ready to hand straight back to the caller."""
    import importlib.util as _ilu
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "report_store", "filter_subsidiary.py")
    spec = _ilu.spec_from_file_location("filter_subsidiary", fpath)
    mod = _ilu.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return {"ok": False, "error": "FILTER_IMPORT_FAILED", "message": str(e)[:300]}
    return mod


def execute_get_stored_report(report_key, period, subsidiary=None):
    try:
        mods = _report_store_modules()
    except Exception as e:
        return {"ok": False, "error": "REPORT_STORE_IMPORT_FAILED", "message": str(e)[:300]}
    entry, subs_list = _report_registry_entry(report_key)

    # The 'as of' date is dynamic — accept any phrasing the user typed.
    iso = _normalise_period(period)
    if iso:
        period = iso

    # ── Resolve the SCOPE before touching the inbox ────────────────────────
    # The ONLY vocabulary is the scope names NetSuite actually emails (the text
    # between 'BK ' and ' as of'). No invented keyword lists — match the user's
    # words to a real subject, or ask them to confirm. Nothing is assumed.
    variants = entry.get("subsidiary_variants") or subs_list
    if subsidiary and variants:
        _fsp = _load_filter_module()
        if isinstance(_fsp, dict):
            return _fsp
        _m, _c = _fsp.resolve_subsidiary(subsidiary, variants)
        if not _m:
            listed = _c if len(_c) > 1 else variants
            return {"ok": False,
                    "error": "SCOPE_NEEDS_CONFIRMATION",
                    "candidates": listed,
                    "message": (f"'{subsidiary}' matches {len(_c)} of the report scopes "
                                f"NetSuite emails. Ask the user which one they mean — "
                                f"'is this what you want?' — listing: {listed}. WAIT for "
                                f"the answer before sending any file."
                                if len(_c) > 1 else
                                f"'{subsidiary}' doesn't match any scope NetSuite emails. "
                                f"Ask the user to pick one: {variants}. WAIT for the answer "
                                f"before sending any file.")}
        subsidiary = _m
        # An exact scope named 'Wego (Consolidated)' IS the group report; serve
        # it from the group key rather than looking for a separate email.
        if _norm(subsidiary) == "wego (consolidated)":
            subsidiary = None

    # ── NATIVE per-subsidiary report (preferred since 2026-07-30) ──────────
    # Akansha schedules one email per subsidiary: 'AP: A/P Aging Detail BK
    # <Subsidiary> as of DD/MM/YYYY'. NetSuite segregates the rows itself, so
    # the '- No Vendor -' block is attributed correctly and NOTHING is inferred.
    # Only fall through to filtering the consolidated file if that email is
    # missing. Pure stdlib + openpyxl throughout — no AI tokens.
    tmpl = entry.get("subsidiary_subject_template")
    if subsidiary and tmpl:          # only when a scope was actually requested
        fs_probe = _load_filter_module()
        if isinstance(fs_probe, dict):
            return fs_probe
        sub_name = subsidiary       # already resolved to an exact scope above
        sub_key = (entry.get("subsidiary_report_key_template", "{slug}")
                   .format(slug=_subsidiary_slug(sub_name)))
        # 'BK <subsidiary> as of' anchoring stops 'Wego' matching 'Wego Middle East'
        sub_subject = tmpl.format(subsidiary=sub_name)
        # ONE inbox pass (180d) covers both jobs: pick up a newer copy of a
        # period we already hold, and find one we don't. A second call after a
        # failed first was pure waste and hid the first failure.
        sub_fresh = False
        sub_fetch_error = None
        sub_requested = period
        sub_substituted = None
        try:
            fr = mods["email_fetcher"].fetch(sub_subject, sub_key,
                                             period=None, since_days=180)
            sub_fresh = bool(fr.get("saved"))
        except Exception as e:
            sub_fetch_error = f"{type(e).__name__}: {e}"
        sub_paths = mods["report_store"].get_report(sub_key, period)
        if not sub_paths:
            have = sorted({r["period"] for r in
                           mods["report_store"].find_reports(sub_key)})
            _lessons().record("report_error", report_key=sub_key,
                              error="PERIOD_NOT_AVAILABLE", period=period,
                              subsidiary=sub_name, message=f"available={have}")
            if sub_fetch_error:
                # The inbox could not be read, so we CANNOT claim the period
                # wasn't emailed — say the search failed instead of guessing.
                return {"ok": False, "error": "INBOX_UNREACHABLE",
                        "subsidiary": sub_name, "requested_period": period,
                        "available_periods": have,
                        "message": (f"Could not search the mailbox for '{sub_name}' "
                                    f"{period}: {sub_fetch_error}. This is NOT proof the "
                                    f"report is missing — the inbox was unreachable. Report "
                                    f"the failure and stop; do NOT send another period or "
                                    f"the consolidated file."
                                    + (f" On file: {have}." if have else ""))}
            if not have:
                return {"ok": False, "error": "PERIOD_NOT_AVAILABLE",
                        "subsidiary": sub_name, "requested_period": period,
                        "available_periods": have,
                        "message": (f"No '{sub_name}' report for {period}, and no other "
                                    f"period either. The inbox was searched just now for "
                                    f"'{sub_subject}' (180 days). Say exactly this. Do NOT "
                                    f"fall back to the consolidated file, do NOT use SuiteQL.")}
            # Nikhil 2026-08-10: "always upload whatever latest is available
            # instead of asking". Done HERE, in the tool, not by the agent —
            # the agent improvising this is what produced a hand-filtered file
            # and a three-message interrogation. It can only fire when the
            # inbox WAS searched successfully (sub_fetch_error is None above),
            # so "not emailed yet" is a fact, never an unread mailbox.
            sub_substituted, period = period, have[-1]
            sub_paths = mods["report_store"].get_report(sub_key, period)
        if sub_paths:
            out, conv = (sub_paths, False)
            if entry.get("deliver_as") == "xlsx":
                out, conv = _deliver_as_xlsx(sub_paths, sub_key, period)
                if isinstance(out, dict):
                    return out
            _lessons().record("report_served", report_key=sub_key, period=period,
                              subsidiary=sub_name,
                              filename=os.path.basename(out[0]) if out else None,
                              converted=conv, fetched_fresh=sub_fresh)
            stale_warn = (f"WARNING: could not re-check the inbox for a newer copy "
                          f"({sub_fetch_error}) — this may not be the latest. "
                          if sub_fetch_error else "")
            sub_note = (f"NOTE: {sub_substituted} has not been emailed for this "
                        f"subsidiary (inbox searched just now); this is the LATEST "
                        f"available, {period}. Send the file and say that in one "
                        f"line — do not ask the user whether to send it. "
                        if sub_substituted else "")
            return {"ok": True, "report_key": sub_key, "period": period,
                    "refresh_error": sub_fetch_error,
                    "requested_period": sub_requested,
                    "substituted_from": sub_substituted, "subsidiary": sub_name,
                    "file_paths": out, "converted_to_xlsx": conv,
                    "fetched_fresh": sub_fresh, "source": "per_subsidiary_email",
                    "message": (f"{stale_warn}{sub_note}{sub_name} — NetSuite's own per-subsidiary report "
                                f"for {period} (not derived from the consolidated "
                                f"file, so the '- No Vendor -' block is included). "
                                f"Deliver via upload_file_to_slack (in-thread).")}
    # ALWAYS re-check the inbox for this report first, even when the period is
    # already stored: Akansha re-sends/reschedules, so the newest email for a
    # period supersedes what we hold (Nikhil 2026-07-29). Newest-wins because
    # save_report overwrites the same report_key/period/filename.
    fetched_fresh = False
    refresh_error = None
    if entry.get("refresh") == "always" and entry.get("subject_contains"):
        try:
            fr = mods["email_fetcher"].fetch(entry["subject_contains"], report_key,
                                            period=None, since_days=90)
            fetched_fresh = bool(fr.get("saved"))
        except Exception as e:
            # Never let a refresh failure block serving what we already have.
            refresh_error = f"{type(e).__name__}: {e}"

    try:
        paths = mods["report_store"].get_report(report_key, period)
    except Exception as e:
        return {"ok": False, "error": "REPORT_LOOKUP_FAILED",
                "message": f"{type(e).__name__}: {e}"}

    if not paths and entry.get("source") == "email" and entry.get("subject_contains"):
        # FALLBACK (Nikhil 2026-07-28): not in memory -> pull fresh from the
        # inbox, which saves to memory as a side effect, then serve it now.
        # period=None: each email is stored under ITS OWN parsed period, so a
        # different month's email is never mis-filed under the asked period.
        try:
            fr = mods["email_fetcher"].fetch(entry["subject_contains"], report_key,
                                             period=None, since_days=90)
            fetched_fresh = fetched_fresh or fr.get("emails_matched", 0) > 0
            paths = mods["report_store"].get_report(report_key, period)
        except Exception as e:
            return {"ok": False, "error": "INBOX_UNREACHABLE",
                    "requested_period": period,
                    "message": (f"{period} isn't in memory and the mailbox could not be "
                                f"searched: {type(e).__name__}: {e}. This is NOT proof the "
                                f"report is missing — report the failure and stop; do NOT "
                                f"send another period.")}

    served_period = period
    substituted_from = None
    if not paths:
        # The asked-for period isn't in memory and the inbox has already been
        # re-fetched above. Serving the latest is allowed ONLY from here — i.e.
        # only once a real search has proved the period was never emailed — and
        # it must be LABELLED. Handing Akansha the June file presented as July
        # (2026-08-03) was the unlabelled version of this, which is the bug.
        known = mods["report_store"].find_reports(report_key)
        periods = sorted({r["period"] for r in known})
        _lessons().record("report_error", report_key=report_key,
                          error="PERIOD_NOT_AVAILABLE", period=period,
                          message=f"available={periods}")
        if not periods:
            return {"ok": False, "error": "PERIOD_NOT_AVAILABLE",
                    "requested_period": period, "available_periods": periods,
                    "message": (f"No report for {period}, and no other period either. "
                                f"The inbox was re-checked just now and NetSuite has "
                                f"not emailed it. Tell the user exactly this; do NOT "
                                f"rebuild it via SuiteQL.")}
        # Same deliberate rule as the per-subsidiary path: only reachable after a
        # SUCCESSFUL inbox search (an unreadable mailbox returns INBOX_UNREACHABLE
        # above), so serving the latest states a fact rather than covering a gap.
        substituted_from, served_period = period, periods[-1]
        paths = mods["report_store"].get_report(report_key, served_period)
    fresh_note = ("Fetched FRESH from the rpa@wego.com inbox just now and saved to "
                  "memory (it wasn't stored). " if fetched_fresh else "")
    if refresh_error:
        fresh_note += (f"WARNING: could not re-check the inbox for a newer copy "
                       f"({refresh_error}) — this may not be the latest. ")
    if substituted_from:
        fresh_note += (f"NOTE: nothing exists for {substituted_from} (not in memory, "
                       f"not in the inbox) — this is the LATEST available: "
                       f"{served_period}. Send the file and say that in one line. Do "
                       f"NOT present it as {substituted_from}, and do NOT ask the user "
                       f"whether to send it. ")
    # "consolidated" is NOT a subsidiary — it means serve the file untouched.
    # Filtering on it would drop the '- No Vendor -' / '- No Subsidiary -'
    # blocks that belong to the consolidated view (Akansha 2026-07-29:
    # "for consolidated one the whole No vendor thing is not there").
    if not subsidiary:
        # Deliver Excel even when NetSuite mails CSV (it does now) — rows are
        # preserved verbatim; only cell types/formats change.
        #
        # When deliver_as=xlsx, pick ONE source file and convert it:
        #   1. Prefer .csv (cleanest source for conversion, avoids BIFF quirks)
        #   2. Fall back to .xls if no CSV exists
        #   3. If already .xlsx / .xlsm, serve as-is
        # Serving BOTH the raw .xls AND .csv would upload two files and confuse
        # callers — always produce exactly one xlsx output.
        # (Nikhil 2026-07-29: bug fix — previously both files were returned,
        # causing the raw .xls to be uploaded as the first attachment.)
        out_paths, converted = list(paths), False
        if entry.get("deliver_as") == "xlsx":
            fs_mod = _load_filter_module()
            if isinstance(fs_mod, dict):
                return fs_mod
            # Pick ONE source, in this order (Nikhil 2026-07-29: "the raw can be
            # anything apart from xls, mostly it'll be csv — convert that"):
            #   1. an existing .xlsx/.xlsm  -> serve as-is, nothing to convert
            #   2. ANY non-.xls raw         -> convert (csv first, then tsv/txt/
            #                                  whatever NetSuite switches to next)
            #   3. .xls                     -> LAST resort only
            # NetSuite mails BOTH report.xls and report.csv, and the .xls is the
            # one that opens wrong in Excel — it must never win (PR #127/#129).
            xlsx_paths = [p for p in paths if p.lower().endswith((".xlsx", ".xlsm"))]
            xls_paths = [p for p in paths if p.lower().endswith((".xls", ".xlsb"))]
            csv_paths = [p for p in paths if p.lower().endswith(".csv")]
            other_raw = [p for p in paths
                         if p not in xlsx_paths and p not in xls_paths
                         and p not in csv_paths]
            if xlsx_paths:
                out_paths, converted = [xlsx_paths[0]], False
            else:
                src_file = (csv_paths or other_raw or xls_paths or paths)[0]
                try:
                    conv = fs_mod.convert_to_xlsx(src_file)
                    out_paths, converted = [conv["out_path"]], True
                except RuntimeError as e:
                    _lessons().record("report_error", report_key=report_key,
                                      error="CONVERSION_FAILED", period=served_period,
                                      message=str(e))
                    return {"ok": False, "error": "CONVERSION_FAILED",
                            "message": str(e)[:400]}
        _lessons().record("report_served", report_key=report_key, period=served_period,
                          filename=os.path.basename(out_paths[0]) if out_paths else None,
                          converted=converted, fetched_fresh=fetched_fresh)
        if substituted_from:
            _lessons().record("latest_substituted", report_key=report_key,
                              requested_period=substituted_from, served=served_period)
        return {"ok": True, "report_key": report_key, "period": served_period,
                "requested_period": period, "is_latest_substitute": bool(substituted_from),
                "file_paths": out_paths, "fetched_fresh": fetched_fresh,
                "converted_to_xlsx": converted,
                "message": (f"{fresh_note}{len(out_paths)} file(s) for "
                            f"{report_key}/{served_period}"
                            + (" (converted from CSV to xlsx — rows unchanged)"
                               if converted else "")
                            + ". Deliver via upload_file_to_slack (in-thread).")}

    # ── FALLBACK: carve the subsidiary out of the consolidated file ────────
    fs = _load_filter_module()
    if isinstance(fs, dict):
        return fs
    target = subsidiary
    if subs_list:
        match, candidates = fs.resolve_subsidiary(subsidiary, subs_list)
        if match:
            target = match
        elif len(candidates) > 1:
            _lessons().record("report_error", report_key=report_key,
                              error="SUBSIDIARY_AMBIGUOUS", subsidiary=subsidiary,
                              message=f"candidates={candidates}")
            return {"ok": False, "error": "SUBSIDIARY_AMBIGUOUS",
                    "message": (f"'{subsidiary}' matches several subsidiaries: "
                                f"{candidates}. Ask the user which one.")}
        # no candidates -> try the literal text; filter will name what exists
    try:
        r = fs.filter_report(paths[0], target)
    except RuntimeError as e:
        _lessons().record("report_error", report_key=report_key,
                          error="SUBSIDIARY_FILTER_FAILED", subsidiary=target,
                          period=served_period, message=str(e))
        return {"ok": False, "error": "SUBSIDIARY_FILTER_FAILED",
                "message": str(e)[:500]}
    _lessons().record("report_served", report_key=report_key, period=served_period,
                      subsidiary=target, filename=os.path.basename(r["out_path"]),
                      rows=r["data_rows"], fetched_fresh=fetched_fresh)
    return {"ok": True, "report_key": report_key, "period": served_period,
            "requested_period": period, "is_latest_substitute": bool(substituted_from),
            "subsidiary": target, "file_paths": [r["out_path"]],
            "data_rows": r["data_rows"], "fetched_fresh": fetched_fresh,
            "source": "derived_from_consolidated",
            "message": (f"{fresh_note}Filtered {report_key}/{served_period} to "
                        f"'{target}' — {r['data_rows']} rows. {r['note']} Deliver via "
                        f"upload_file_to_slack (in-thread).")}


def execute_list_stored_reports(report_key=None, period=None):
    try:
        mods = _report_store_modules()
    except Exception as e:
        return {"ok": False, "error": "REPORT_STORE_IMPORT_FAILED", "message": str(e)[:300]}
    rows = mods["report_store"].find_reports(report_key, period)
    slim = [{k: r.get(k) for k in ("report_key", "period", "filename", "size",
                                   "source", "saved_at", "s3_mirrored")} for r in rows]
    return {"ok": True, "count": len(slim), "reports": slim}


def execute_get_cabinet_file(file_id=None, filename=None, folder_name=None,
                             scope="prod"):
    """Fetch a File Cabinet file. Resolve by numeric `file_id`, or search by
    `filename` (substring, latest-modified wins) optionally scoped to
    `folder_name`. Writes the decoded file to EXPORT_DIR and returns
    {ok, file_path, name, size_bytes, matches?}. If the name search hits
    multiple files, returns the match list instead of guessing."""
    import base64

    # 1. Resolve the file id via the SuiteQL `file` table if not given.
    if not file_id:
        if not filename:
            return {"ok": False, "error": "MISSING_REF",
                    "message": "Pass file_id (numeric) or filename (substring to search)."}
        safe_name = str(filename).replace("'", "''")
        q = (
            "SELECT f.id, f.name, f.filesize, f.folder, mf.name AS folder_name, "
            "TO_CHAR(f.lastmodifieddate, 'YYYY-MM-DD HH24:MI') AS last_modified "
            "FROM file f LEFT JOIN mediaitemfolder mf ON mf.id = f.folder "
            f"WHERE UPPER(f.name) LIKE UPPER('%{safe_name}%')"
        )
        if folder_name:
            safe_folder = str(folder_name).replace("'", "''")
            q += f" AND UPPER(mf.name) LIKE UPPER('%{safe_folder}%')"
        q += " ORDER BY f.lastmodifieddate DESC"
        page = _suiteql_one_page(q, scope, limit=25, offset=0)
        if page.get("error") or page.get("type") == "error":
            return {"ok": False, "error": "FILE_LOOKUP_FAILED",
                    "message": f"SuiteQL file lookup failed: {json.dumps(page)[:300]}"}
        items = page.get("items") or []
        if not items:
            return {"ok": False, "error": "FILE_NOT_FOUND",
                    "message": f"No File Cabinet file matching {filename!r}"
                               + (f" in folder ~'{folder_name}'" if folder_name else "")
                               + f" (scope={scope})."}
        if len(items) > 1:
            return {"ok": False, "error": "MULTIPLE_MATCHES",
                    "message": (f"{len(items)} files match {filename!r} — pick one and "
                                f"re-call with its file_id."),
                    "matches": [{k: it.get(k) for k in
                                 ("id", "name", "filesize", "folder_name", "last_modified")}
                                for it in items]}
        file_id = items[0]["id"]
        if items[0].get("filesize") and int(items[0]["filesize"]) > _RESTLET_FILE_CAP_BYTES:
            return {"ok": False, "error": "FILE_TOO_LARGE",
                    "message": (f"{items[0]['name']} is {items[0]['filesize']} bytes — over the "
                                f"RESTlet 10MB response cap. Download it from the NetSuite UI.")}

    # 2. Fetch content via the RESTlet file_get action (same env vars as saved_search).
    scope_up = (scope or "prod").upper()
    if scope_up == "PROD":
        scope_up = "PRODUCTION"
    script_id = os.environ.get(f"NETSUITE_{scope_up}_RESTLET_SCRIPT_ID", "").strip()
    deploy_id = os.environ.get(f"NETSUITE_{scope_up}_RESTLET_DEPLOYMENT_ID", "").strip()
    if not script_id or not deploy_id:
        return {"ok": False, "error": "RESTLET_NOT_DEPLOYED",
                "message": (f"restlet_companion env vars missing for scope={scope}: need "
                            f"NETSUITE_{scope_up}_RESTLET_SCRIPT_ID and _DEPLOYMENT_ID. Deploy "
                            f"restlet_companion.js per references/restlet_deployment.md.")}

    try:
        creds = get_credentials(scope)
    except Exception as e:
        return {"ok": False, "error": "CRED_LOOKUP_FAILED",
                "message": f"Could not load NetSuite credentials for scope={scope}: {e}"}

    host = f"{url_form(creds['account_id'])}.restlets.api.netsuite.com"
    url = (f"https://{host}/app/site/hosting/restlet.nl"
           f"?script={urllib.parse.quote(script_id)}"
           f"&deploy={urllib.parse.quote(deploy_id)}")
    payload = {"action": "file_get", "file_id": str(file_id)}
    try:
        auth = oauth_header("POST", url, creds["client_id"], creds["client_secret"],
                            creds["token_id"], creds["token_secret"], creds["account_id"])
    except Exception as e:
        return {"ok": False, "error": "OAUTH_SIGN_FAILED",
                "message": f"Could not sign RESTlet request: {e}"}

    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
           "-H", f"Authorization: {auth}", "-H", "Content-Type: application/json",
           "-d", json.dumps(payload), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "RESTLET_TIMEOUT",
                "message": "file_get RESTlet call timed out after 180s."}

    raw = (result.stdout or "").rstrip()
    if not raw:
        return {"ok": False, "error": "EMPTY_RESPONSE",
                "message": f"RESTlet returned no body. stderr: {result.stderr[:300]}"}
    body, _, http_code = raw.rpartition("\n")
    if not body:
        body, http_code = http_code, ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"ok": False, "error": "INVALID_RESTLET_RESPONSE",
                "message": f"HTTP {http_code or '?'} — response wasn't JSON: {body[:300]}"}
    if http_code and not http_code.startswith("2"):
        return {"ok": False, "error": f"RESTLET_HTTP_{http_code}",
                "message": f"NetSuite RESTlet returned HTTP {http_code}: {body[:300]}",
                "raw": data}
    if isinstance(data, dict) and data.get("ok") is False:
        if data.get("error_code") == "unknown_action":
            return {"ok": False, "error": "RESTLET_HANDLER_STALE",
                    "message": ("Deployed restlet_companion.js predates the file_get action — "
                                "replace the File Cabinet copy with the latest "
                                "references/restlet_companion.js."),
                    "raw": data}
        return data

    # 3. Decode and write to EXPORT_DIR.
    content_b64 = data.get("content_b64")
    if not content_b64:
        return {"ok": False, "error": "NO_CONTENT",
                "message": f"RESTlet returned no content for file {file_id}.", "raw": {
                    k: data.get(k) for k in ("id", "name", "size", "file_type")}}
    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)
        out_name = data.get("name") or f"cabinet_file_{file_id}"
        out_path = os.path.join(EXPORT_DIR, out_name)
        try:
            content = base64.b64decode(content_b64)
        except Exception:
            # Text files come back as plain text, not base64.
            content = str(content_b64).encode("utf-8")
        with open(out_path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        return {"ok": False, "error": "WRITE_FAILED",
                "message": f"Could not write file locally: {e}"}

    return {"ok": True, "action": "file_get", "file_id": data.get("id", file_id),
            "name": out_name, "file_path": out_path,
            "size_bytes": os.path.getsize(out_path),
            "folder": data.get("folder"),
            "message": (f"Fetched '{out_name}' ({os.path.getsize(out_path)} bytes) to {out_path}. "
                        f"Deliver via upload_file_to_slack — never paste the /tmp path.")}


# ─────────────────────────────────────────────────────────────────────────
# Deletion audit — query the `deletedrecord` SuiteQL table
# ─────────────────────────────────────────────────────────────────────────
# Born 2026-06-16 from Akansha's "list of all deleted records/transactions
# from production" ask in #netsuite_champion. The bot refused without
# actually trying — this tool ensures the query is attempted against prod
# every time, and surfaces the verbatim NetSuite response on failure
# (so we know whether it's a permission gap to widen vs an edition gap
# requiring a different path).
#
# Rule 2 alignment: defaults to scope="prod" — sandbox ONLY if explicitly
# requested by the caller.

def execute_get_deleted_records(record_type=None, since_date=None, until_date=None,
                                 deleted_by=None, scope="prod"):
    """Query the deletion audit log from NetSuite.

    Runs SuiteQL against the `deletedrecord` table (defaults to production).
    Returns CSV path + 3-row preview for bounded token cost; full result
    stays on disk. If NetSuite refuses, the verbatim error and the
    Akansha-actionable next step come back in `message`.

    Args:
        record_type: optional NetSuite record type filter (e.g. "vendorbill",
                     "journalentry", "vendor", "customer").
        since_date:  optional YYYY-MM-DD lower bound on deleted_date.
        until_date:  optional YYYY-MM-DD upper bound on deleted_date.
        deleted_by:  optional internal user id who performed the delete.
        scope:       "prod" (default per Rule 2) or "sandbox" (only if
                     explicitly named by the user).

    Returns:
      ok=True:  {file_path, row_count, columns, preview, scope, query_method}
      ok=False: {error, message, attempted_query, scope}
    """
    where_parts = []
    if since_date:
        # Light validation — _v_date raises on bad format
        try:
            _v_date(since_date)
            where_parts.append(
                f"deleteddate >= TO_DATE('{since_date}', 'YYYY-MM-DD')")
        except Exception as e:
            return {"ok": False, "error": "INVALID_SINCE_DATE",
                    "message": f"since_date must be YYYY-MM-DD: {e}"}
    if until_date:
        try:
            _v_date(until_date)
            where_parts.append(
                f"deleteddate <= TO_DATE('{until_date}', 'YYYY-MM-DD')")
        except Exception as e:
            return {"ok": False, "error": "INVALID_UNTIL_DATE",
                    "message": f"until_date must be YYYY-MM-DD: {e}"}
    if record_type:
        # SuiteQL string-literal safety
        rt = _sql_escape(str(record_type).strip())
        where_parts.append(f"recordtypeid = {rt}")
    if deleted_by:
        # Must be a positive integer (NetSuite user internal id)
        try:
            uid = int(str(deleted_by).strip())
            assert uid > 0
            where_parts.append(f"deletedby = {uid}")
        except Exception:
            return {"ok": False, "error": "INVALID_DELETED_BY",
                    "message": "deleted_by must be a positive integer "
                               "(NetSuite user internal id)."}

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    suiteql = (
        "SELECT id, recordtypeid, name, deletedby, deleteddate "
        f"FROM deletedrecord {where_clause} ORDER BY deleteddate DESC"
    ).strip()

    filename_hint = "deleted_records"
    if since_date:
        filename_hint += f"_{since_date.replace('-', '')}"
    if record_type:
        filename_hint += f"_{record_type}"

    result = execute_export_suiteql_to_csv(
        query=suiteql, filename_hint=filename_hint, scope=scope,
    )

    if isinstance(result, dict) and result.get("ok"):
        result["query_method"] = "suiteql:deletedrecord"
        result["scope"] = scope
        return result

    # Failure — surface the verbatim NetSuite response so the next step is obvious.
    err = (result.get("error") if isinstance(result, dict) else "UNKNOWN") or "UNKNOWN"
    raw_msg = (result.get("message") if isinstance(result, dict) else str(result)) or ""

    next_step = ""
    raw_lower = raw_msg.lower()
    if "403" in raw_msg or "permission" in raw_lower or "insufficient" in raw_lower:
        next_step = (
            " Looks like a permission gap — integration role likely needs "
            "`Lists → Deleted Records: View`. Tag Akansha to widen the role."
        )
    elif "404" in raw_msg or "not found" in raw_lower or "invalid_record" in raw_lower:
        next_step = (
            " This NetSuite edition may not expose deletedrecord via SuiteQL. "
            "Fallback path: Setup → Audit Trail (UI) for a one-off, or open an "
            "NDS ticket to wire up the REST `/deletedrecord` endpoint as an "
            "MCP tool."
        )

    return {
        "ok": False,
        "error": "DELETED_RECORDS_QUERY_FAILED",
        "underlying_error": err,
        "message": (
            f"NetSuite refused the deletion-audit query (scope={scope}). "
            f"Verbatim: {raw_msg[:300]}.{next_step}"
        ),
        "attempted_query": suiteql[:300],
        "scope": scope,
    }


_BU_CODE_KEY_NORMS = {
    # Normalized form (lowercase, no whitespace/_/-) of every alias that
    # should route to the canonical cseg_msa_bu_code REST field.
    "bu", "bucode", "bu_code", "bucode", "businessunit",
    "businessunitcode", "business_unit", "business_unit_code",
    "csegmsabucode",  # in case someone typed cseg_msa_bu_code already — keep it canonical too
}


def _norm_field_key(s):
    """Normalize a field key for case/whitespace/_/-insensitive matching."""
    if not s:
        return ""
    out = str(s).strip().lower()
    for ch in (" ", "\t", "_", "-"):
        out = out.replace(ch, "")
    return out


def _live_bu_id_set(scope):
    """Live SuiteQL: every active BU id from customrecord_cseg_msa_bu_code.
    Used to detect when a BU id has been misplaced on the `class` field
    (the 2026-05-20 Gift Cards collision). Returns a set of string ids,
    or None if SuiteQL fails (in which case we fall back to leaving the
    body alone — better than blocking a write).
    """
    try:
        rows = _suiteql_all_rows(
            "SELECT id FROM customrecord_cseg_msa_bu_code "
            "WHERE isinactive = 'F' AND ROWNUM <= 500",
            scope,
        )
        return {str(r["id"]) for r in rows if r.get("id") is not None}
    except Exception as e:
        logger.warning(f"Could not fetch live BU id set for body guard: {e}")
        return None


def _enforce_bu_field_on_line(line, bu_id_set):
    """In-place rewrite of one expense/item/line dict:

    1. Any key that normalizes to a BU-code alias (BU Code, bu_code,
       BU CODE, BU, business_unit, business_unit_code, etc.) gets its
       value moved to canonical `cseg_msa_bu_code` and the original key
       removed.
    2. If `class` carries an id that exists in the live BU id set AND
       there is no `cseg_msa_bu_code` already set, treat it as misplaced
       BU: move to `cseg_msa_bu_code` and drop `class`. This is the
       Gift-Cards collision guard (2026-05-20 BILL-010).

    Returns the list of mutations applied, for logging / surfacing.
    """
    if not isinstance(line, dict):
        return []
    mutations = []

    # 1. Field-name aliases → cseg_msa_bu_code
    for key in list(line.keys()):
        if key == "cseg_msa_bu_code":
            continue
        if _norm_field_key(key) in _BU_CODE_KEY_NORMS:
            val = line.pop(key)
            if "cseg_msa_bu_code" not in line and val not in (None, ""):
                line["cseg_msa_bu_code"] = val
                mutations.append(f"renamed line field '{key}' → 'cseg_msa_bu_code'")
            else:
                mutations.append(f"dropped duplicate line field '{key}' (cseg_msa_bu_code already set)")

    # 2. class field carrying a BU id → move to cseg_msa_bu_code
    if bu_id_set:
        cls = line.get("class")
        cls_id = None
        if isinstance(cls, dict):
            cls_id = cls.get("id")
        elif isinstance(cls, (str, int)):
            cls_id = str(cls)
        if cls_id is not None and str(cls_id) in bu_id_set and "cseg_msa_bu_code" not in line:
            line["cseg_msa_bu_code"] = {"id": str(cls_id)}
            line.pop("class", None)
            mutations.append(
                f"moved class.id={cls_id} → cseg_msa_bu_code (id matches "
                f"customrecord_cseg_msa_bu_code; class would have posted "
                f"as Product Segment — 2026-05-20 Gift-Cards collision guard)"
            )

    return mutations


def _enforce_bu_field_in_body(record_type, body, scope):
    """Walk a NetSuite REST body and rewrite any BU-code field-name
    variants to the canonical `cseg_msa_bu_code` on every line. Also
    detects and corrects the misplaced-BU-on-class collision.

    Only applies to record types that carry BU code on their line items:
    vendorbill, vendorcredit, vendorpayment, journalentry.

    Returns the list of mutations applied — the bot's reply can surface
    them so the user sees what was auto-corrected.
    """
    if not isinstance(body, dict):
        return []
    if record_type not in {"vendorbill", "vendorcredit", "vendorpayment", "journalentry"}:
        return []

    mutations = []
    bu_id_set = _live_bu_id_set(scope)

    # Walk standard line-item containers
    for container_key in ("expense", "item", "line"):
        container = body.get(container_key)
        if isinstance(container, dict):
            items = container.get("items")
            if isinstance(items, list):
                for idx, line in enumerate(items):
                    line_mutations = _enforce_bu_field_on_line(line, bu_id_set)
                    for m in line_mutations:
                        mutations.append(f"{container_key}.items[{idx}]: {m}")

    # Also guard header-level fields (some record types put BU on header)
    header_mutations = _enforce_bu_field_on_line(body, bu_id_set)
    for m in header_mutations:
        mutations.append(f"header: {m}")

    if mutations:
        logger.warning(
            f"BU-field placement guard rewrote {len(mutations)} field(s) "
            f"on {record_type} body before POST: {mutations}"
        )
    return mutations


def execute_create(record_type, body, scope="sandbox"):
    """Create a record via POST.

    Rejects unknown record-type aliases with a helpful "did you mean" error
    BEFORE hitting NetSuite — saves a round-trip and avoids the 2026-05-19
    bill-payment failure pattern (bot tried `billpayment` / `bill`, both 404,
    then improvised).
    """
    canonical, was_aliased = _canonical_record_type(record_type)
    if was_aliased:
        logger.warning(
            f"⚠️  record_type alias: '{record_type}' → '{canonical}'. "
            f"Bot should use canonical name. See references/netsuite_record_types.md."
        )
        return {
            "ok": False,
            "error": "RECORD_TYPE_ALIAS_REJECTED",
            "message": (
                f"'{record_type}' is not a canonical NetSuite REST record type. "
                f"Did you mean '{canonical}'? Re-issue the create_record call with "
                f"record_type='{canonical}'. See references/netsuite_record_types.md "
                f"for the full mapping. Do NOT substitute a different record type."
            ),
            "suggested_record_type": canonical,
        }
    if canonical not in RECORD_URL_PATHS:
        logger.warning(f"⚠️  record_type '{canonical}' not in RECORD_URL_PATHS — proceeding but URL may be generic.")

    record_type = canonical

    # Hard guard: enforce BU code field placement on the body before POST.
    # Any field-name variant of "BU Code" gets routed to cseg_msa_bu_code;
    # a BU id sitting on `class` (the 2026-05-20 Gift-Cards collision) gets
    # moved to cseg_msa_bu_code and the class field dropped.
    bu_field_mutations = _enforce_bu_field_in_body(record_type, body, scope)

    logger.info(f"CREATE {record_type} (scope={scope}) - body: {json.dumps(body, default=str)[:200]}...")
    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/record/v1/{record_type}"

    auth = oauth_header("POST", url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])

    cmd = [
        "curl", "-s", "-i", "-X", "POST",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        "-d", json.dumps(body) if isinstance(body, dict) else body,
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout
    # Parse response - handle both HTTP/1.1 and HTTP/2 line endings
    # Try \r\n\r\n first, then \n\n
    if "\r\n\r\n" in output:
        headers, _, resp_body = output.partition("\r\n\r\n")
    elif "\n\n" in output:
        headers, _, resp_body = output.partition("\n\n")
    else:
        headers = output
        resp_body = ""

    location = ""
    for line in headers.replace("\r\n", "\n").split("\n"):
        if line.lower().startswith("location:"):
            location = line.split(":", 1)[1].strip()

    internal_id = location.rsplit("/", 1)[-1] if location else None
    is_success = "204" in headers or "201" in headers

    if internal_id and is_success:
        # Build correct UI URL — scope-aware, sandbox by default for writes.
        ui_url = _build_ns_url(record_type, internal_id, scope=scope)

        # Post-write verification: read back the record we just created and
        # confirm it exists and is the type we intended. Catches the 2026-05-19
        # incident pattern (bot creates one type and labels it another) at the
        # transport layer rather than relying solely on prompt rules.
        verify = execute_get(record_type, internal_id, scope=scope)
        verify_ok = isinstance(verify, dict) and not verify.get("error") and (
            verify.get("id") == internal_id or str(verify.get("id", "")) == str(internal_id)
        )
        if not verify_ok:
            logger.error(
                f"❌ POST_WRITE_VERIFY_FAILED: created {record_type} id={internal_id} "
                f"but read-back failed: {str(verify)[:300]}"
            )
            return {
                "ok": False,
                "error": "POST_WRITE_VERIFY_FAILED",
                "internal_id": internal_id,
                "ui_url": ui_url,
                "verify_response": verify,
                "message": (
                    f"⚠️ Created {record_type} returned id={internal_id} but read-back failed. "
                    f"The record may not actually exist at that id, OR it exists but is a "
                    f"different record type. Surface this to the user verbatim — DO NOT claim success."
                ),
            }

        result = {
            "ok": True,
            "record_type": record_type,
            "internal_id": internal_id,
            "location": location,
            "ui_url": ui_url,
            "sandbox_url": ui_url,  # back-compat alias
            "message": (
                f"✅ {record_type} created (ID: {internal_id}). "
                f"Open in NetSuite: {ui_url}"
            ),
        }
        if bu_field_mutations:
            result["bu_field_guard_mutations"] = bu_field_mutations
        logger.info(f"✅ CREATE SUCCESS (verified): {record_type} id={internal_id} url={ui_url}")
        return result
    elif is_success and not internal_id:
        # 204 but no location header - check stderr for location
        result = {"ok": True, "internal_id": "unknown", "note": "Created but no Location header returned"}
        logger.warning(f"⚠️  CREATE SUCCESS (no ID): {record_type} - {result['note']}")
        return result
    else:
        try:
            error_obj = json.loads(resp_body) if resp_body.strip() else {"error": f"HTTP response: {headers[:200]}"}
        except:
            error_obj = {"error": resp_body[:500] if resp_body else f"Headers: {headers[:300]}"}
        # Extract user-friendly error message
        error_msg = error_obj
        if isinstance(error_obj, dict) and "o:errorDetails" in error_obj and error_obj["o:errorDetails"]:
            error_msg = error_obj["o:errorDetails"][0].get("detail", str(error_obj))
        logger.error(f"❌ CREATE FAILED: {record_type} - {error_msg}")
        return {"ok": False, "error": error_obj, "message": f"❌ Failed to create {record_type}: {error_msg}"}


def execute_update(record_type, record_id, body, scope="sandbox"):
    """Update a record via PATCH.

    Rejects unknown record-type aliases with a helpful "did you mean" error
    BEFORE hitting NetSuite — same protection as execute_create.
    """
    canonical, was_aliased = _canonical_record_type(record_type)
    if was_aliased:
        logger.warning(
            f"⚠️  record_type alias: '{record_type}' → '{canonical}'. "
            f"Bot should use canonical name."
        )
        return {
            "ok": False,
            "error": "RECORD_TYPE_ALIAS_REJECTED",
            "message": (
                f"'{record_type}' is not a canonical NetSuite REST record type. "
                f"Did you mean '{canonical}'? Re-issue the update_record call with "
                f"record_type='{canonical}'."
            ),
            "suggested_record_type": canonical,
        }
    record_type = canonical

    # Same BU-field placement guard as execute_create — see _enforce_bu_field_in_body.
    bu_field_mutations = _enforce_bu_field_in_body(record_type, body, scope)

    logger.info(f"UPDATE {record_type} id={record_id} (scope={scope}) - body: {json.dumps(body, default=str)[:200]}...")
    creds = get_credentials(scope)
    host = f"{url_form(creds['account_id'])}.suitetalk.api.netsuite.com"
    url = f"https://{host}/services/rest/record/v1/{record_type}/{record_id}"

    auth = oauth_header("PATCH", url, creds["client_id"], creds["client_secret"],
                        creds["token_id"], creds["token_secret"], creds["account_id"])

    cmd = [
        "curl", "-s", "-i", "-X", "PATCH",
        "-H", f"Authorization: {auth}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: transient",
        "-d", json.dumps(body) if isinstance(body, dict) else body,
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    headers, _, resp_body = result.stdout.partition("\r\n\r\n")
    if "204" in headers:
        ui_url = _build_ns_url(record_type, record_id, scope=scope)
        logger.info(f"✅ UPDATE SUCCESS: {record_type} id={record_id} url={ui_url}")
        result = {
            "ok": True,
            "record_type": record_type,
            "internal_id": record_id,
            "ui_url": ui_url,
            "sandbox_url": ui_url,  # back-compat alias
            "message": f"✅ {record_type} updated (ID: {record_id}). Open in NetSuite: {ui_url}",
        }
        if bu_field_mutations:
            result["bu_field_guard_mutations"] = bu_field_mutations
        return result
    else:
        try:
            error = json.loads(resp_body) if resp_body else {"error": "No response"}
        except:
            error = {"error": resp_body[:500]}
        logger.error(f"❌ UPDATE FAILED: {record_type} id={record_id} - {error}")
        return {"ok": False, "error": error}


# MCP Protocol Implementation
TOOLS = [
    {
        "name": "run_suiteql",
        "description": "Execute a SuiteQL query against NetSuite. Returns JSON result with items array.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The SuiteQL query to execute"},
                "scope": {"type": "string", "enum": ["prod", "sandbox"], "default": "prod", "description": "Which environment to query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_record",
        "description": "GET a NetSuite record by type and internal ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "Record type (e.g. vendor, customer, employee)"},
                "record_id": {"type": "string", "description": "Internal ID of the record"},
                "scope": {"type": "string", "enum": ["prod", "sandbox"], "default": "prod"}
            },
            "required": ["record_type", "record_id"]
        }
    },
    {
        "name": "create_record",
        "description": "Create a new record in NetSuite sandbox. Returns internal_id and sandbox URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "Record type (e.g. vendor, customer)"},
                "body": {"type": "object", "description": "Record fields as JSON object"}
            },
            "required": ["record_type", "body"]
        }
    },
    {
        "name": "update_record",
        "description": "Update an existing record in NetSuite sandbox via PATCH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "Record type"},
                "record_id": {"type": "string", "description": "Internal ID to update"},
                "body": {"type": "object", "description": "Fields to update"}
            },
            "required": ["record_type", "record_id", "body"]
        }
    },
    {
        "name": "metadata_catalog",
        "description": "Get metadata/schema for a NetSuite record type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "Record type to get metadata for"}
            },
            "required": ["record_type"]
        }
    },
    {
        "name": "refresh_mcp_logs",
        "description": (
            "Render the MCP activity JSONL into committed markdown at "
            "memory/logs/netsuite-mcp/<DATE>.md for today (and optionally "
            "the last days_back-1 days). The agent must then git add / "
            "commit / push the rendered files — this tool does NOT touch "
            "git. Use this when the user (in DM with Nikhil) asks for "
            "'logs', 'activity', 'what did you do today', or 'give me the "
            "NetSuite logs', so they can see fresh activity on GitHub "
            "without waiting for the daily cron. Returns the list of "
            "rendered file paths + per-day status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer", "default": 1,
                    "description": "How many days of logs to render (1 = today only, 7 = last week). Max 30."
                }
            }
        }
    },
    {
        "name": "upload_file_to_slack",
        "description": (
            "Upload a local file (typically a CSV from export_suiteql_to_csv "
            "or run_standard_report) to Slack as a native file attachment. "
            "Call this RIGHT AFTER any export tool when serving a Slack "
            "user — the bare `/tmp/...csv` path the export returns is "
            "useless inside Slack. Posts the file into the channel + the "
            "user's thread, with an optional comment. "
            "\n\n"
            "THREAD HANDLING (2026-06-26 fix): channel uploads (C/G prefix) "
            "MUST land inside the user's thread, not as a new top-level "
            "channel message. You MUST pass ONE of these three fields from "
            "the inbound Slack event metadata — the tool maps them all to "
            "Slack's thread_ts internally: "
            "  • `thread_ts` (canonical Slack field name) "
            "  • `reply_to_id` (the name OpenClaw uses in inbound metadata) "
            "  • `message_id` (the name OpenClaw uses for the inbound message ts) "
            "Pass whichever the inbound event gives you — any works. DMs (D "
            "prefix) don't need any of these. If you omit all three on a "
            "channel upload, the tool refuses with THREAD_TS_REQUIRED. "
            "\n\n"
            "Returns file_id + permalink on success. Requires "
            "SLACK_BOT_TOKEN_NETSUITE_CHAMPION env var; if absent, returns "
            "ok=false cleanly without raising."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["file_path", "channel"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path of the file to upload (e.g. /tmp/netsuite_exports/foo.csv)."
                },
                "channel": {
                    "type": "string",
                    "description": "Slack channel ID where the file should appear (e.g. C08LZTG1YR5 for #netsuite_ota, or a DM channel ID)."
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Slack thread parent ts. Pass this OR reply_to_id OR message_id — the tool maps all three to the same target. Pass whichever name the inbound Slack metadata gave you."
                },
                "reply_to_id": {
                    "type": "string",
                    "description": "Alias for thread_ts — the name OpenClaw uses in inbound metadata for the parent message id. Pass directly from inbound event; tool resolves it to thread_ts."
                },
                "message_id": {
                    "type": "string",
                    "description": "Alias for thread_ts — the name OpenClaw uses for the inbound message's own ts. For top-level @mentions where there's no separate parent, this IS the thread parent ts."
                },
                "comment": {
                    "type": "string",
                    "description": "Optional text message attached above the file in Slack. Use this to summarise what the file contains."
                },
                "title": {
                    "type": "string",
                    "description": "Optional file title shown in Slack. Defaults to the basename of file_path."
                }
            }
        }
    },
    {
        "name": "run_standard_report",
        "description": (
            "Run one of ten pre-validated NetSuite financial reports — "
            "customer_statement, revenue_periodic, "
            "gl_report, customer_payments, balance_sheet, income_statement, "
            "interco_balance_sheet, gl_listing_multi, fx_rate_list, "
            "fx_rate_range. Templates live server-side; agent only supplies "
            "params (dates, customer, GL code(s), optional subsidiary_id / "
            "currency symbols). Result is written to CSV and a 3-row preview "
            "returned — full data stays on disk so token cost is bounded "
            "regardless of row count. Use this whenever the user asks for one "
            "of those named reports. For ANY currency-exchange-rate / FX "
            "question, ALWAYS use fx_rate_list (as-of a date) or fx_rate_range "
            "(date range) — never hand-write SuiteQL, never saved search 705 "
            "(Rule 7)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["report_name", "params"],
            "properties": {
                "report_name": {
                    "type": "string",
                    "enum": [
                        "customer_statement",
                        "revenue_periodic",
                        "gl_report",
                        "customer_payments",
                        "balance_sheet",
                        "income_statement",
                        "interco_balance_sheet",
                        "gl_listing_multi",
                        "fx_rate_list",
                        "fx_rate_range",
                    ],
                    "description": "Which standard report to run."
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Required + optional params per report. See "
                        "skills/wego-netsuite/references/standard_reports.md "
                        "for the exact param list per report. All dates "
                        "are YYYY-MM-DD."
                    )
                },
                "scope": {
                    "type": "string", "enum": ["prod", "sandbox"],
                    "default": "prod",
                    "description": "Which NetSuite environment. Reads default to prod."
                },
                "filename_hint": {
                    "type": "string",
                    "description": (
                        "Optional override for the CSV filename. If omitted, "
                        "the tool builds one from the report name + params "
                        "(e.g. gl_report_2026-05-21.csv)."
                    )
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Optional cap on rows exported (defaults to system limit)."
                }
            }
        }
    },
    {
        "name": "export_suiteql_to_csv",
        "description": (
            "Run a SuiteQL with server-side pagination, write all rows to a "
            "CSV file, and return ONLY a 3-row preview + metadata to the "
            "caller. Use this for bulk-listing requests (>50 rows) — keeps "
            "token cost bounded regardless of row count. For small filtered "
            "queries, prefer run_suiteql which returns rows inline. The query "
            "must NOT include LIMIT / OFFSET / FETCH FIRST / FETCH NEXT / "
            "ROWNUM — filter with WHERE / ORDER BY only; the tool paginates "
            "server-side. Returns {ok, file_path, row_count, columns, "
            "preview, truncated}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":          {"type": "string",
                                   "description": "SuiteQL. WHERE/ORDER BY only — no LIMIT/OFFSET/FETCH/ROWNUM."},
                "filename_hint":  {"type": "string",
                                   "description": "Slug for the output filename (e.g. 'wego_sg_active_vendors'). Timestamp is appended automatically."},
                "scope":          {"type": "string", "enum": ["prod", "sandbox"], "default": "prod"},
                "max_rows":       {"type": "integer", "default": 50000,
                                   "description": "Safety cap. Default 50,000."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "resolve_csv_dimensions",
        "description": (
            "Resolve every CSV-row dimension (subsidiary, vendor, currency, "
            "account, department, location, class, tax code, BU code) to "
            "NetSuite internal IDs in one call. Returns either a fully "
            "resolved dict or a structured list of resolution errors per "
            "field. USE THIS before any create_record call when the user "
            "uploaded a CSV — it prevents silently-dropped fields. Compound "
            "tax codes (regime:code) and UNDEF-placeholder filtering are "
            "handled server-side."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string",
                                "description": "Target record type (vendorbill, journalentry, vendorpayment, etc.)"},
                "csv_row":     {"type": "object",
                                "description": "Flat dict of CSV column → value (subsidiary, vendor, currency, account, department, location, class/market_segment, tax_code, bu_code, etc.)"},
                "scope":       {"type": "string", "enum": ["prod", "sandbox"], "default": "sandbox"}
            },
            "required": ["record_type", "csv_row"]
        }
    },
    {
        "name": "create_vendor_bill_from_csv",
        "description": (
            "End-to-end Vendor Bill create from a CSV-style row. Resolves "
            "every dimension server-side (subsidiary, vendor, currency, "
            "account, department, location, class, tax code, BU code), "
            "builds the complete expense.items body, POSTs to sandbox, runs "
            "post-write verification, and returns the result with every "
            "resolved field surfaced. USE THIS for any CSV-driven vendor "
            "bill creation — the bot cannot drop dimensions because it "
            "doesn't assemble the body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv_row": {"type": "object",
                            "description": "Flat dict from one CSV row: bill_ref/bill_number, subsidiary, vendor_entity_id/vendor, currency, tran_date, due_date, memo, expense_account/account, amount, line_memo, department, location, class, tax_code, bu_code"},
                "scope":   {"type": "string", "enum": ["sandbox"], "default": "sandbox"}
            },
            "required": ["csv_row"]
        }
    },
    {
        "name": "create_journal_entry_from_csv",
        "description": (
            "End-to-end Journal Entry create from a CSV-style row. For a "
            "multi-line JE pass csv_row.lines as a list of line dicts. "
            "Resolves header (subsidiary, trandate) and every line's "
            "dimensions (account, debit/credit, department, location, "
            "class, BU code), validates debits=credits, POSTs to sandbox. "
            "Bot cannot drop line-level fields. USE THIS for any CSV-driven "
            "journal creation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv_row": {"type": "object",
                            "description": "Either a single-line CSV row (account/debit/credit at top level) or a multi-line dict with .lines = [...]"},
                "scope":   {"type": "string", "enum": ["sandbox"], "default": "sandbox"}
            },
            "required": ["csv_row"]
        }
    },
    {
        "name": "update_vendor_bill_from_csv",
        "description": (
            "Partial-update an existing Vendor Bill (amendment). USE THIS "
            "when the user says 'this is wrong, fix it' or 'X is missing, "
            "add it' in the thread for a bill you just created. Pass only "
            "the changed fields in csv_row — everything else on the bill "
            "is left alone. Server-side dimension resolution (so the bot "
            "cannot accidentally drop or substitute fields). Returns the "
            "same {ok, internal_id, ui_url, resolved_fields} shape as "
            "create_vendor_bill_from_csv plus the patched_body for audit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_id":  {"type": "string",
                               "description": "Internal id of the vendor bill to amend (from the create response or NetSuite UI)."},
                "csv_row":    {"type": "object",
                               "description": "Flat dict of ONLY the fields to change. E.g. {\"tax_code\": \"SR-SG 9%\"} to fix just the tax code on line 1."},
                "line_index": {"type": "integer", "default": 0,
                               "description": "0-based index of the line to patch when amending a line-level field. Default 0 (first line)."},
                "scope":      {"type": "string", "enum": ["sandbox"], "default": "sandbox"}
            },
            "required": ["record_id", "csv_row"]
        }
    },
    {
        "name": "discover_table",
        "description": (
            "Schema-discovery helper. Given a SuiteQL table name, returns "
            "(a) row count, (b) the column list, and (c) one sample row "
            "with values truncated for safety. Use this whenever you need "
            "to write a SuiteQL query but don't know the exact column "
            "names — it grounds your next query in the live schema "
            "instead of guessed-from-training-data column names. "
            "If the table doesn't exist or the integration role can't "
            "read it, the tool returns ok=false with the verbatim "
            "NetSuite error PLUS a list of suggested alternative table "
            "names — so the agent can iterate without falling silent. "
            "This is the cornerstone of §5.16 self-building queries: "
            "discover the schema first, then write the real query."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["table_name"],
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": ("SuiteQL table name to probe — e.g. "
                                    "'employee', 'role', "
                                    "'employeerolesforsearch'. Only letters, "
                                    "digits and underscores allowed.")
                },
                "scope": {"type": "string", "enum": ["prod", "sandbox"],
                          "default": "prod"},
            }
        }
    },
    {
        "name": "get_role_permissions",
        "description": (
            "Fetch the per-role permission grid (Role × record-type × Level) "
            "via the openclaw-nova SuiteScript RESTlet. This data is BLOCKED "
            "from SuiteQL and the REST Record API for the integration role — "
            "the RESTlet wraps NetSuite's native record.load('role') which "
            "DOES have access to the permissions sublist. Returns the full "
            "permission list per role: permission_key, permission_name "
            "(e.g. 'Vendor Bills'), level ('View'/'Create'/'Edit'/'Full'/"
            "'Customize'/'None'), and restriction. Use this for any ask "
            "about role permissions, edit/customize filtering, can-approve "
            "queries, or permission audits. If the RESTlet isn't deployed "
            "yet (env vars missing), returns ok=false with "
            "RESTLET_NOT_DEPLOYED + a clean Akansha-handoff message — surface "
            "verbatim per Rule 5; do not substitute a role-metadata dump "
            "per §5.18."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "role_ids": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string",
                         "description": "Comma-separated role IDs."}
                    ],
                    "description": ("Optional list of role internal IDs to "
                                    "fetch. If omitted, returns all active "
                                    "roles (capped at 50 by the RESTlet — "
                                    "page if you have more).")
                },
                "include_inactive": {
                    "type": "boolean", "default": False,
                    "description": "Include inactive roles. Default False."
                },
                "scope": {"type": "string", "enum": ["prod", "sandbox"],
                          "default": "prod"}
            }
        }
    },
    {
        "name": "run_saved_search",
        "description": (
            "Run an EXISTING NetSuite saved search and return its rows (or a "
            "CSV). PREFERRED USAGE: pass `key` — a registry key from "
            "saved_searches.json — so the agent self-serves by INTENT. The "
            "finance user asks a normal question (e.g. 'show me AR aging'); "
            "you match it to a registry entry "
            "(see list_saved_searches) and call this with that key. NOTE: FX / "
            "currency-exchange-rate questions are NOT a saved search — use "
            "run_standard_report report_name=fx_rate_list for those. Finance "
            "users NEVER paste a URL or id — that mapping lives in the "
            "registry. (You may also pass `search_ref` = id / script id / a "
            "pasted UI URL when there's no registry entry yet.) Runs via the "
            "SuiteScript RESTlet over OAuth — no browser/login. For "
            "list/report asks set export_csv=true, then upload the returned "
            "file_path via upload_file_to_slack into the user's thread. If the "
            "RESTlet isn't deployed returns RESTLET_NOT_DEPLOYED; if the "
            "deployed script predates the saved_search action returns "
            "RESTLET_HANDLER_STALE — surface verbatim per Rule 5. If the "
            "question matches MORE THAN ONE registry entry or NONE well, ask "
            "the user to confirm which report before running — do not guess."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "Registry key from saved_searches.json (PREFERRED) — "
                        "e.g. 'ar_aging'. Resolves to the saved "
                        "search id + title; applies the entry's default "
                        "export_csv. Use this for intent-driven self-serve."
                    )
                },
                "search_ref": {
                    "type": "string",
                    "description": (
                        "Fallback when there's no registry entry: a saved-"
                        "search id, script id, or a pasted NetSuite UI URL "
                        "containing searchid=/id= (the tool parses the id)."
                    )
                },
                "export_csv": {
                    "type": "boolean", "default": False,
                    "description": (
                        "If true, write rows to a CSV and return file_path + "
                        "a 3-row preview (then upload_file_to_slack). Use for "
                        "any 'list / report / export / download' ask. Registry "
                        "entries with default_export_csv=true turn this on "
                        "automatically."
                    )
                },
                "filename_hint": {
                    "type": "string",
                    "description": "Optional CSV filename slug. Defaults to the registry title or the search id."
                },
                "scope": {"type": "string", "enum": ["prod", "sandbox"],
                          "default": "prod",
                          "description": "NetSuite environment. Reads default to prod."},
                "filters": {
                    "type": "string",
                    "description": "Optional NetSuite filter-expression override (advanced). Omit to use the search's own filters."
                },
                "row_cap": {
                    "type": "integer", "default": 50000,
                    "description": "Max rows (RESTlet hard cap). Default 50000. Raise per-call if a search exceeds it; very large pulls may hit RESTlet governance — fall back to a SuiteQL export if so."
                },
                "page_size": {
                    "type": "integer", "default": 1000,
                    "description": "Page size for paged fetch (<=1000). Default 1000."
                }
            }
        }
    },
    {
        "name": "list_saved_searches",
        "description": (
            "List the saved searches registered in saved_searches.json — the "
            "intent -> saved-search routing table. Returns each entry's key, "
            "title, intent, and example_questions. Call this to find which "
            "saved search answers the user's question, then run it with "
            "run_saved_search(key=...). Use it whenever a finance user asks "
            "for a report/list that might be backed by a maintained saved "
            "search and you're not sure of the key."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_cabinet_file",
        "description": (
            "Fetch a file from the NetSuite File Cabinet EXACTLY as stored — "
            "byte-identical, no re-computation. USE THIS when a report already "
            "exists as a file in the cabinet (e.g. the 'Reports via Schedule "
            "Script' folder where scheduled GL/report .xlsx exports land): the "
            "user gets the SAME file NetSuite generated. Resolve by numeric "
            "file_id, or by filename substring (latest-modified wins; optional "
            "folder_name filter). If several files match, returns the match "
            "list — pick one and re-call with its file_id; don't guess. Then "
            "ALWAYS deliver via upload_file_to_slack (in-thread), never the "
            "/tmp path. To browse a folder first, run_suiteql on the `file` "
            "table (join mediaitemfolder for folder names). Files >10MB exceed "
            "the RESTlet cap — direct the user to the NetSuite UI. Errors "
            "(RESTLET_NOT_DEPLOYED / RESTLET_HANDLER_STALE / FILE_NOT_FOUND) "
            "are surfaced verbatim per Rule 5."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "Numeric File Cabinet internal id (e.g. 465072). Preferred when known."
                },
                "filename": {
                    "type": "string",
                    "description": "Filename substring to search (case-insensitive), e.g. 'GL_8402030_WegoMiddleEast_Sep-2025'. Latest-modified match wins."
                },
                "folder_name": {
                    "type": "string",
                    "description": "Optional folder-name substring filter, e.g. 'Reports via Schedule Script'."
                },
                "scope": {"type": "string", "enum": ["prod", "sandbox"],
                          "default": "prod",
                          "description": "NetSuite environment the file lives in."}
            }
        }
    },
    {
        "name": "fetch_email_report",
        "description": (
            "Pull a NetSuite scheduled-report EMAIL from the rpa@wego.com Gmail "
            "inbox and file its attachment(s) into persistent report memory "
            "(local store + S3 mirror, indexed by report_key + period). "
            "NetSuite report emails always come from system@sent-via.netsuite.com; "
            "pass subject_contains to pick the report (e.g. 'NetSuite "
            "Classification Lists'). period defaults to the YYYY-MM found in "
            "the subject (NetSuite convention) or the email date — override "
            "only if the user names a different period. Known reports live in "
            "references/report_sources.json — use its report_key/subject so "
            "storage stays consistent. Searches [Gmail]/All Mail (report mail is "
            "often filtered out of INBOX), so a zero-match returns diagnostics: "
            "mailboxes tried, how many mails from the sender, and the actual "
            "subjects present — relay those and fix the subject, NEVER fall back "
            "to a saved search or SuiteQL. Auth: EMAIL_FROM_PWD from the env / "
            "openclaw.env / OpenClaw config (AWS Secrets Manager is NOT used — "
            "cross-account). Errors surfaced verbatim."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject_contains": {"type": "string",
                                     "description": "Substring the email subject must contain."},
                "report_key": {"type": "string",
                               "description": "Slug to store under, e.g. classification_lists."},
                "period": {"type": "string",
                           "description": "Optional period override (YYYY-MM or YYYY-MM-DD)."},
                "since_days": {"type": "integer", "default": 7,
                               "description": "How many days back to search the inbox."}
            },
            "required": ["subject_contains", "report_key"]
        }
    },
    {
        "name": "get_stored_report",
        "description": (
            "Retrieve a report from persistent report memory by report_key + "
            "period (e.g. classification_lists / 2026-07). Serves the EXACT "
            "file that was ingested (from email or File Cabinet) — no "
            "re-computation. Pulls from the S3 mirror automatically if the "
            "local copy is gone (fresh pod). Returns file_path(s) — deliver "
            "via upload_file_to_slack in-thread, never the /tmp path. This tool "
            "is the WHOLE job: it searches the inbox, picks the right email, "
            "picks the right source file and converts it. Upload the path it "
            "returns and stop. NEVER open, read, filter, re-convert or "
            "size-check the file, never list the report store, and never call "
            "fetch_email_report yourself — doing any of that by hand rebuilds "
            "what this call already did, and gets it wrong. Do NOT rebuild the "
            "report with SuiteQL. ALWAYS-LATEST: for reports flagged "
            "refresh=always (A/P Aging Detail BK) the inbox is re-checked on "
            "EVERY call even when the period is already stored, because Akansha "
            "re-sends/reschedules — newest email wins. DELIVERY FORMAT: the "
            "scheduled export is CSV; consolidated delivery converts it to .xlsx "
            "(rows verbatim, only cell types/date formats change) so finance gets "
            "Excel. PERIOD: pass what the user SAID — '30/06/2026', '30 June "
            "2026', 'June 2026', 'June end', ISO — it is normalised to the ISO "
            "date internally (month-only = month end). PERIOD FALLBACK is "
            "handled HERE, not by you: the inbox is searched for the period the "
            "user asked for, and ONLY if that search succeeds and proves the "
            "period was never emailed is the latest available returned instead "
            "— with substituted_from / is_latest_substitute set and the note to "
            "relay in `message`. Send that file and state its date in one line; "
            "never offer the user a menu of periods. The one error that means "
            "send NOTHING is INBOX_UNREACHABLE: the mailbox could not be read, "
            "so nothing is known — report it and stop. "
            "SUBSIDIARY: when the user names one (exact scopes listed in "
            "report_sources.json), pass `subsidiary`. Each subsidiary has its "
            "OWN NetSuite email ('AP: A/P Aging Detail BK <Subsidiary> as of "
            "DD/MM/YYYY') and THAT is what gets served — the consolidated file "
            "is a different report and is never the source, so what it does or "
            "does not contain says nothing about a subsidiary's availability. "
            "If the scope is unclear the call returns SCOPE_NEEDS_CONFIRMATION "
            "with candidates: ask which one and WAIT. 'consolidated' or no "
            "subsidiary mentioned -> omit the param and serve the stored file "
            "as-is."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_key": {"type": "string"},
                "period": {"type": "string",
                           "description": "Period as stored (YYYY-MM or YYYY-MM-DD)."},
                "subsidiary": {"type": "string",
                               "description": "Official subsidiary name (or close variant) to filter to. Omit for consolidated."}
            },
            "required": ["report_key", "period"]
        }
    },
    {
        "name": "list_stored_reports",
        "description": (
            "List persistent report memory (report_key, period, filename, "
            "source, saved_at). Optional report_key/period filters. Use to "
            "answer 'what reports do we have' and to find the right key/period "
            "before get_stored_report."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_key": {"type": "string"},
                "period": {"type": "string"}
            }
        }
    },
    {
        "name": "get_deleted_records",
        "description": (
            "Query NetSuite's deletion audit log (the `deletedrecord` "
            "SuiteQL table). Use this for any 'list deleted records', "
            "'deletion audit', 'what was deleted since X', or 'who "
            "deleted Y' ask. Defaults to PRODUCTION per Rule 2 — sandbox "
            "is used only when the user explicitly names sandbox. "
            "Returns a CSV path + 3-row preview (bounded token cost). "
            "On NetSuite refusal, surfaces the verbatim error plus an "
            "Akansha-actionable next step (most commonly: integration "
            "role needs `Lists → Deleted Records: View`). This tool "
            "ALWAYS attempts the query — never refuse the user without "
            "calling this first per Rule 6."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_type": {
                    "type": "string",
                    "description": ("Optional NetSuite record type to filter "
                                    "(e.g. 'vendorbill', 'journalentry', "
                                    "'vendor', 'customer'). Omit for all "
                                    "record types.")
                },
                "since_date": {
                    "type": "string",
                    "description": ("Optional YYYY-MM-DD lower bound on "
                                    "deleted_date. Resolve relative phrases "
                                    "(yesterday/last month) per §3 before "
                                    "passing.")
                },
                "until_date": {
                    "type": "string",
                    "description": "Optional YYYY-MM-DD upper bound on deleted_date."
                },
                "deleted_by": {
                    "type": "integer",
                    "description": ("Optional NetSuite user internal id "
                                    "(positive integer) to filter by who "
                                    "performed the delete.")
                },
                "scope": {
                    "type": "string", "enum": ["prod", "sandbox"],
                    "default": "prod",
                    "description": ("Default 'prod'. Per Rule 2, only switch "
                                    "to 'sandbox' if the user explicitly names "
                                    "sandbox in their request.")
                }
            }
        }
    },
    {
        "name": "export_access_audit",
        "description": (
            "Atomic 3-CSV NetSuite access audit — runs three SuiteQL "
            "exports in one call and reports per-query status: "
            "(a) active users with login enabled, (b) all active roles "
            "(metadata only — NOT the permission grid), (c) user × role "
            "assignment map. Each query is independent — one 403 does "
            "NOT swallow the other two. The response includes "
            "`permission_grid_note` explicitly stating that the "
            "per-role View/Edit/Full grid is NOT exportable via SuiteQL "
            "and must come from Akansha's admin export. Use this when "
            "the user asks for a user/role/access export — it satisfies "
            "§5.15 (multi-part atomic delivery) by design. "
            "Always follow up with upload_file_to_slack for each "
            "successful file_path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["prod", "sandbox"],
                          "default": "prod",
                          "description": ("Which environment to read from. "
                                          "Reads default to prod.")}
            }
        }
    },
    {
        "name": "update_journal_entry_from_csv",
        "description": (
            "Partial-update an existing Journal Entry (amendment). For "
            "multi-line JE amendments, pass csv_row.lines = [...] with "
            "each line's `line` field (1-based) identifying which line to "
            "patch. Same DIMENSION_RESOLUTION_FAILED semantics as the "
            "create flow."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string"},
                "csv_row":   {"type": "object"},
                "scope":     {"type": "string", "enum": ["sandbox"], "default": "sandbox"}
            },
            "required": ["record_id", "csv_row"]
        }
    }
]


def handle_request(request):
    """Handle a single JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": f"netsuite-mcp-{SCOPE}",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True
                }
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


# ── Per-tool-call activity log (JSONL, append-only) ──────────────────────
# One line per MCP tool call. Args and result are SUMMARISED, not dumped in
# full — no bodies, no PII, no SuiteQL row contents. Daily file rotation.
# A separate render script (scripts/render_netsuite_mcp_logs.py) turns the
# JSONL into a markdown table committed to memory/logs/netsuite-mcp/.
MCP_LOG_DIR = os.environ.get(
    "NETSUITE_MCP_LOG_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "netsuite-mcp"),
)


def _safe_str(v, cap=80):
    """String-coerce a value, cap length, replace newlines."""
    try:
        s = str(v).replace("\n", " ").replace("\r", " ")
    except Exception:
        return "?"
    return s if len(s) <= cap else s[:cap] + "…"


def _summarise_tool_args(tool_name, args):
    """Per-tool list of safe-to-log argument keys. Never logs full bodies,
    csv_row values, vendor names, dollar amounts, or full SuiteQL results.
    """
    if not isinstance(args, dict):
        return {}
    safe = {}
    if tool_name == "run_suiteql":
        safe["query"] = _safe_str(args.get("query", ""), cap=200)
    elif tool_name == "read_record":
        safe["record_type"] = args.get("record_type")
        safe["record_id"] = args.get("record_id")
    elif tool_name in ("create_record", "update_record"):
        safe["record_type"] = args.get("record_type")
        body = args.get("body") or {}
        if isinstance(body, dict):
            safe["body_fields"] = list(body.keys())[:10]
        if tool_name == "update_record":
            safe["record_id"] = args.get("record_id")
    elif tool_name == "metadata_catalog":
        safe["record_type"] = args.get("record_type")
    elif tool_name == "export_suiteql_to_csv":
        safe["filename_hint"] = args.get("filename_hint")
        safe["query"] = _safe_str(args.get("query", ""), cap=200)
        if args.get("max_rows"):
            safe["max_rows"] = args.get("max_rows")
    elif tool_name == "resolve_csv_dimensions":
        safe["record_type"] = args.get("record_type")
        csv = args.get("csv_row") or {}
        if isinstance(csv, dict):
            safe["csv_fields"] = list(csv.keys())[:15]
    elif tool_name in ("create_vendor_bill_from_csv", "create_journal_entry_from_csv"):
        csv = args.get("csv_row") or {}
        if isinstance(csv, dict):
            safe["csv_fields"] = list(csv.keys())[:15]
            for k in ("bill_ref", "bill_number"):
                if k in csv:
                    safe[k] = _safe_str(csv[k], cap=50)
    elif tool_name in ("update_vendor_bill_from_csv", "update_journal_entry_from_csv"):
        safe["record_id"] = args.get("record_id")
        csv = args.get("csv_row") or {}
        if isinstance(csv, dict):
            safe["csv_fields"] = list(csv.keys())[:15]
    elif tool_name == "discover_table":
        safe["table_name"] = args.get("table_name")
    elif tool_name == "export_access_audit":
        pass  # only scope, captured below
    elif tool_name == "get_role_permissions":
        rids = args.get("role_ids")
        if isinstance(rids, list):
            safe["role_id_count"] = len(rids)
        elif isinstance(rids, str):
            safe["role_id_count"] = len([x for x in rids.split(",") if x.strip()])
        else:
            safe["role_id_count"] = 0  # all active
        safe["include_inactive"] = bool(args.get("include_inactive"))
    elif tool_name == "get_deleted_records":
        for k in ("record_type", "since_date", "until_date", "deleted_by"):
            if args.get(k) is not None:
                safe[k] = _safe_str(args.get(k), cap=40)
    elif tool_name == "run_saved_search":
        if args.get("search_ref") is not None:
            safe["search_ref"] = _safe_str(args.get("search_ref"), cap=120)
        for k in ("row_cap", "page_size"):
            if args.get(k) is not None:
                safe[k] = args.get(k)
    elif tool_name == "get_cabinet_file":
        for k in ("file_id", "filename", "folder_name"):
            if args.get(k) is not None:
                safe[k] = _safe_str(args.get(k), cap=80)
    elif tool_name in ("fetch_email_report", "get_stored_report", "list_stored_reports"):
        for k in ("subject_contains", "report_key", "period", "since_days"):
            if args.get(k) is not None:
                safe[k] = _safe_str(args.get(k), cap=80)
    if "scope" in args:
        safe["scope"] = args.get("scope")
    return safe


def _row_count_from_result(result):
    """Best-effort row-count extraction from a tool response."""
    if not isinstance(result, dict):
        return None
    for key in ("row_count", "count"):
        v = result.get(key)
        if isinstance(v, int):
            return v
    items = result.get("items")
    if isinstance(items, list):
        return len(items)
    data = result.get("data")
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return len(items)
    return None


def _log_tool_call(tool_name, scope, args, result, duration_ms):
    """Append one JSONL line per tool call. Swallows all errors — logging
    must never break the tool path.
    """
    try:
        os.makedirs(MCP_LOG_DIR, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_path = os.path.join(MCP_LOG_DIR, f"{date_str}.jsonl")

        try:
            result_json = json.dumps(result, default=str) if result is not None else ""
        except Exception:
            result_json = ""
        result_bytes = len(result_json.encode("utf-8")) if result_json else 0

        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        # For tools that don't set ok=True explicitly (e.g. run_suiteql returns
        # raw NetSuite response), infer success from absence of an error field.
        if isinstance(result, dict) and "ok" not in result:
            ok = not (result.get("error") or result.get("type") == "error")

        entry = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "tool": tool_name,
            "scope": scope or "n/a",
            "args": _summarise_tool_args(tool_name, args),
            "ok": ok,
            "result_bytes": result_bytes,
            "duration_ms": int(duration_ms),
        }
        rows = _row_count_from_result(result)
        if rows is not None:
            entry["row_count"] = rows
        if not ok and isinstance(result, dict):
            entry["error"] = _safe_str(result.get("error") or result.get("message") or "", cap=120)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Best-effort — never break the tool path
        try:
            logger.debug(f"MCP activity log write failed: {e}")
        except Exception:
            pass


def call_tool(name, arguments):
    """Execute a tool, log timing + summary metrics to the daily JSONL,
    and return the result. The actual dispatch logic lives in
    _call_tool_dispatch (below) — this wrapper exists so EVERY tool call
    gets logged once, in one place, regardless of which branch handles it.
    """
    start = time.time()
    scope = (arguments.get("scope") if isinstance(arguments, dict) else None) or SCOPE
    result = None
    try:
        result = _call_tool_dispatch(name, arguments)
        return result
    finally:
        duration_ms = (time.time() - start) * 1000
        _log_tool_call(name, scope, arguments, result, duration_ms)


def _call_tool_dispatch(name, arguments):
    """Execute a tool and return the result."""
    logger.debug(f"📞 TOOL CALL: {name} with args: {json.dumps(arguments, default=str)[:300]}")
    scope = arguments.get("scope", SCOPE)

    if name == "run_suiteql":
        return execute_suiteql(arguments["query"], scope=scope)

    elif name == "read_record":
        return execute_get(arguments["record_type"], arguments.get("record_id"), scope=scope)

    elif name == "create_record":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_create(arguments["record_type"], arguments["body"], scope="sandbox")

    elif name == "update_record":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_update(arguments["record_type"], arguments["record_id"], arguments["body"], scope="sandbox")

    elif name == "metadata_catalog":
        return execute_get(f"metadata-catalog/{arguments['record_type']}", scope=scope)

    elif name == "refresh_mcp_logs":
        return execute_refresh_mcp_logs(
            days_back=arguments.get("days_back", 1),
        )

    elif name == "upload_file_to_slack":
        # Lazy import — script-level helper, no need to load until used
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from slack_upload_file import upload_file_to_slack
        return upload_file_to_slack(
            file_path=arguments["file_path"],
            channel=arguments["channel"],
            thread_ts=arguments.get("thread_ts"),
            reply_to_id=arguments.get("reply_to_id"),
            message_id=arguments.get("message_id"),
            comment=arguments.get("comment"),
            title=arguments.get("title"),
        )

    elif name == "run_standard_report":
        return execute_run_standard_report(
            arguments["report_name"],
            params=arguments.get("params", {}),
            scope=arguments.get("scope", "prod"),
            filename_hint=arguments.get("filename_hint"),
            max_rows=arguments.get("max_rows"),
        )

    elif name == "export_suiteql_to_csv":
        return execute_export_suiteql_to_csv(
            arguments["query"],
            filename_hint=arguments.get("filename_hint"),
            scope=arguments.get("scope", "prod"),
            max_rows=arguments.get("max_rows", EXPORT_DEFAULT_MAX_ROWS),
        )

    elif name == "discover_table":
        return execute_discover_table(
            arguments["table_name"],
            scope=arguments.get("scope", "prod"),
        )

    elif name == "export_access_audit":
        return execute_export_access_audit(
            scope=arguments.get("scope", "prod"),
        )

    elif name == "get_role_permissions":
        return execute_get_role_permissions(
            role_ids=arguments.get("role_ids"),
            include_inactive=bool(arguments.get("include_inactive", False)),
            scope=arguments.get("scope", "prod"),
        )

    elif name == "run_saved_search":
        return execute_run_saved_search(
            search_ref=arguments.get("search_ref"),
            key=arguments.get("key"),
            scope=arguments.get("scope", "prod"),
            filters=arguments.get("filters"),
            row_cap=arguments.get("row_cap", 50000),
            page_size=arguments.get("page_size", 1000),
            export_csv=bool(arguments.get("export_csv", False)),
            filename_hint=arguments.get("filename_hint"),
        )

    elif name == "list_saved_searches":
        reg = load_saved_search_registry()
        if not reg.get("ok"):
            return reg
        slim = [
            {k: s.get(k) for k in
             ("key", "title", "intent", "example_questions", "search_id", "scope")}
            for s in reg["searches"]
        ]
        return {"ok": True, "count": len(slim), "searches": slim,
                "matching_rules": reg.get("matching_rules", {})}

    elif name == "fetch_email_report":
        return execute_fetch_email_report(
            subject_contains=arguments.get("subject_contains"),
            report_key=arguments.get("report_key"),
            period=arguments.get("period"),
            since_days=arguments.get("since_days", 7),
        )

    elif name == "get_stored_report":
        return execute_get_stored_report(
            report_key=arguments.get("report_key"),
            period=arguments.get("period"),
            subsidiary=arguments.get("subsidiary"),
        )

    elif name == "list_stored_reports":
        return execute_list_stored_reports(
            report_key=arguments.get("report_key"),
            period=arguments.get("period"),
        )

    elif name == "get_cabinet_file":
        return execute_get_cabinet_file(
            file_id=arguments.get("file_id"),
            filename=arguments.get("filename"),
            folder_name=arguments.get("folder_name"),
            scope=arguments.get("scope", "prod"),
        )

    elif name == "get_deleted_records":
        return execute_get_deleted_records(
            record_type=arguments.get("record_type"),
            since_date=arguments.get("since_date"),
            until_date=arguments.get("until_date"),
            deleted_by=arguments.get("deleted_by"),
            scope=arguments.get("scope", "prod"),
        )

    elif name == "resolve_csv_dimensions":
        return resolve_csv_dimensions(
            arguments["record_type"],
            arguments["csv_row"],
            scope=arguments.get("scope") or scope,
        )

    elif name == "create_vendor_bill_from_csv":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_create_vendor_bill_from_csv(arguments["csv_row"], scope="sandbox")

    elif name == "create_journal_entry_from_csv":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_create_journal_entry_from_csv(arguments["csv_row"], scope="sandbox")

    elif name == "update_vendor_bill_from_csv":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_update_vendor_bill_from_csv(
            arguments["record_id"],
            arguments["csv_row"],
            scope="sandbox",
            line_index=arguments.get("line_index", 0),
        )

    elif name == "update_journal_entry_from_csv":
        if (scope or "").lower() in ("prod", "production"):
            return {"ok": False, "error": "WRITE_TO_PROD_FORBIDDEN",
                    "message": "Production writes are forbidden. Use scope='sandbox'."}
        return execute_update_journal_entry_from_csv(
            arguments["record_id"],
            arguments["csv_row"],
            scope="sandbox",
        )

    else:
        return {"error": f"Unknown tool: {name}"}


def _start_cron_watchdog(interval_s=300):
    """Keep the cron daemon alive by anchoring it to THIS long-running,
    gateway-supervised process.

    Why: cron_daemon.py was otherwise only (re)started at session start
    (AGENTS.md step 8). A container restart or a daemon crash with no session
    left EVERY cron job dead — silently. It happened: the daemon died
    2026-07-14 and stayed dead 9 days (no backups, no mirror, no daily DM)
    before anyone noticed. ensure_daemon.py is idempotent (no-ops if the
    daemon is already up), so calling it on MCP startup + every 5 min costs
    nothing when healthy and self-heals within 5 min when not. Fully isolated:
    a daemon thread wrapped so it can never disturb the stdio loop.
    """
    import threading

    ensure = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "cron", "ensure_daemon.py")

    def _loop():
        while True:
            try:
                subprocess.run(["python3", ensure], capture_output=True,
                               text=True, timeout=30)
            except Exception:
                pass  # never let watchdog failure touch the server
            time.sleep(interval_s)

    try:
        threading.Thread(target=_loop, name="cron-watchdog", daemon=True).start()
    except Exception:
        pass


def main():
    """MCP stdio server main loop — reads JSON-RPC from stdin, writes to stdout."""
    # Load env from openclaw.env
    env_file = "/home/openclaw/.openclaw/cron/openclaw.env"
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    # Handle export prefix
                    if line.startswith("export "):
                        line = line[7:]
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip('"').strip("'")
                    # Resolve ${VAR} references from existing env
                    if value.startswith("${") and value.endswith("}"):
                        ref_var = value[2:-1]
                        value = os.environ.get(ref_var, "")
                    # Only set if we have a real value
                    if value and key:
                        os.environ[key] = value

    # Keep the cron daemon alive for as long as this server runs (see docstring).
    _start_cron_watchdog()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
