#!/usr/bin/env python3
"""email_fetcher.py — pull NetSuite report emails from Gmail into the report store.

Auth: Gmail IMAP (imap.gmail.com:993, stdlib imaplib) as GMAIL_USER
(default rpa@wego.com).
Password source (first hit wins, all matched CASE-INSENSITIVELY):
  1. this process's environment      (EMAIL_FROM_PWD / GMAIL_APP_PASSWORD / ...)
  2. gateway env files               (/home/openclaw/.openclaw/cron/openclaw.env)
  3. OpenClaw JSON config            (MCP env blocks / portal secrets, any depth)
AWS Secrets Manager is deliberately NOT used: the secret lives in account
058264138250 while the pod runs in 794531973703, and its default
aws/secretsmanager KMS key cannot be shared cross-account — that call could
only ever return AccessDenied and made real failures look like an IAM
problem. Other env overrides: GMAIL_USER, REPORT_FROM_ADDR.

NetSuite scheduled emails always come from system@sent-via.netsuite.com;
the SUBJECT distinguishes the report. Attachments are saved to the report
store (local + S3 mirror) under <report_key>/<period>/.

CLI:
  python3 email_fetcher.py --preflight                      # password + IMAP login only
  python3 email_fetcher.py --subject "NetSuite Classification Lists" \
        --report-key classification_lists [--period 2026-07] [--since-days 7]
"""
import argparse
import email
import email.header
import imaplib
import os
import re
import sys
import email.utils
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "memory_backup"))
import report_store  # noqa: E402
import s3lite        # noqa: E402

GMAIL_USER = os.environ.get("GMAIL_USER", "rpa@wego.com")
FROM_ADDR = os.environ.get("REPORT_FROM_ADDR", "system@sent-via.netsuite.com")
IMAP_HOST = os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com")


# Env vars checked first, in this order. EMAIL_FROM_PWD is what Nikhil set in
# OpenClaw secrets (2026-07-28) and mirrors the old Secrets Manager key name.
# Matched CASE-INSENSITIVELY (Linux env vars are case-sensitive, so
# EMAIL_FROM_PWD / email_from_pwd / Email_From_Pwd would otherwise be three
# different misses). Order = preference.
PWD_ENV_VARS = ("EMAIL_FROM_PWD", "GMAIL_APP_PASSWORD", "EMAIL_APP_PASSWORD")
_PWD_VAR_SET = {v.upper() for v in PWD_ENV_VARS}


# Files the gateway/cron write secrets into. Needed because the gateway spawns
# the MCP server with ONLY the env vars in its config block — the host
# environment (where EMAIL_FROM_PWD lives) is NOT inherited. So the same code
# sees the var from bash but not from inside the MCP server; reading these
# files makes both paths work.
PWD_ENV_FILES = (
    os.environ.get("OPENCLAW_ENV_FILE", "/home/openclaw/.openclaw/cron/openclaw.env"),
    "/home/openclaw/.openclaw/openclaw.env",
    os.path.expanduser("~/.openclaw/cron/openclaw.env"),
)

# OpenClaw's JSON config holds MCP server env blocks / portal secrets.
OPENCLAW_CONFIG_FILES = (
    os.environ.get("OPENCLAW_CONFIG_FILE", "/home/openclaw/.openclaw/openclaw.json"),
    os.path.expanduser("~/.openclaw/openclaw.json"),
)


def _pwd_from_env_files():
    for path in PWD_ENV_FILES:
        try:
            with open(path) as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            key, _, val = line.partition("=")
            if key.strip().upper() in _PWD_VAR_SET:
                val = val.strip().strip('"').strip("'")
                if val and not (val.startswith("${") and val.endswith("}")):
                    return val, f"file:{os.path.basename(path)}:{key.strip()}"
    return None, None


def get_app_password():
    """Resolution order: process env -> gateway env file(s) -> OpenClaw JSON
    config. Returns (password, source). Raises NO_PASSWORD with the exact
    remedy if none of the three has it. Secrets Manager is not consulted."""
    # Case-insensitive scan of the real environment, honoring PWD_ENV_VARS order.
    env_upper = {k.upper(): (k, v) for k, v in os.environ.items()}
    for var in PWD_ENV_VARS:
        hit = env_upper.get(var.upper())
        if hit and hit[1]:
            return hit[1], f"env:{hit[0]}"
    pwd, src = _pwd_from_env_files()
    if pwd:
        return pwd, src
    pwd, src = _pwd_from_openclaw_config()
    if pwd:
        return pwd, src
    raise RuntimeError(
        "NO_PASSWORD: EMAIL_FROM_PWD not found in this process env, in "
        f"{', '.join(PWD_ENV_FILES)}, or in the OpenClaw config "
        f"({', '.join(OPENCLAW_CONFIG_FILES)}). It IS set in the pod shell, but "
        "the gateway spawns the MCP server with only its own env block, so the "
        "server never inherits it. Fix (either): add "
        "EMAIL_FROM_PWD=<value> to /home/openclaw/.openclaw/cron/openclaw.env "
        "(sourced at server startup), or put it in the MCP server's env block "
        "(`openclaw mcp set ... '{\"env\":{\"EMAIL_FROM_PWD\":\"...\"}}'`), then "
        "restart. AWS Secrets Manager is deliberately NOT used — the secret is "
        "cross-account (058264138250 vs 794531973703) and its default KMS key "
        "cannot be shared.")


def _pwd_from_openclaw_config():
    """Last resort: OpenClaw keeps MCP server env blocks / secrets in its JSON
    config. Scan it for any key matching PWD_ENV_VARS (case-insensitive) at any
    depth, so a password stored via `openclaw mcp set`/portal secrets is found
    even when it wasn't exported into this process."""
    import json as _json

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and str(k).upper() in _PWD_VAR_SET and v.strip() \
                        and not (v.startswith("${") and v.endswith("}")):
                    return v, k
                found = walk(v)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    for path in OPENCLAW_CONFIG_FILES:
        try:
            with open(path) as fh:
                cfg = _json.load(fh)
        except (OSError, ValueError):
            continue
        hit = walk(cfg)
        if hit:
            return hit[0], f"config:{os.path.basename(path)}:{hit[1]}"
    return None, None


def _imap_login():
    """Log in, and classify a failure precisely.

    Three different things get reported as "Gmail is broken" and they have
    three different fixes — guessing between them sends the wrong person to do
    the wrong job (2026-08-10: the agent told Nikhil the rpa@wego.com password
    was "invalid/expired" and to get Akansha to re-auth, without knowing
    whether a password had even been found).
    """
    pwd, src = get_app_password()          # raises NO_PASSWORD with its own remedy
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST)
    except Exception as e:
        raise RuntimeError(
            f"IMAP_UNREACHABLE: cannot open {IMAP_HOST}:993 ({type(e).__name__}: {e}). "
            f"Network/egress problem, NOT a credential problem — the password was "
            f"found ({src}). Nothing about the mailbox contents is known.") from e
    try:
        conn.login(GMAIL_USER, pwd)
    except imaplib.IMAP4.error as e:
        detail = str(e)
        try:
            conn.logout()
        except Exception:
            pass
        raise RuntimeError(
            f"IMAP_AUTH_REJECTED: Gmail refused the login for {GMAIL_USER} "
            f"({detail}). A password WAS found ({src}, {len(pwd)} chars), so this "
            f"is the password being wrong/revoked — not a missing secret. Fix: "
            f"generate a fresh app password for {GMAIL_USER} and update "
            f"EMAIL_FROM_PWD, then restart the MCP server. Note Gmail also "
            f"rejects logins when IMAP is disabled on the account or the app "
            f"password was created for a different account.") from e
    return conn, src


def _decode(s):
    if not s:
        return ""
    parts = email.header.decode_header(s)
    return "".join(p.decode(enc or "utf-8", "replace") if isinstance(p, bytes) else p
                   for p, enc in parts)


def _subject_key(s):
    """Normalise a subject for matching: casefold + collapse ALL whitespace
    runs (incl. NBSP and header-folding newlines) to single spaces.

    NetSuite's real subject has a DOUBLE space —
    'AP: A/P Aging Detail BK  Wego (Consolidated) as of 30/06/2026' — so a
    registry entry written with single spacing never substring-matched
    (2026-07-28). Normalising both sides means the registry can keep the FULL,
    specific subject (which is what stops a per-subsidiary variant being filed
    under the consolidated key) without being hostage to invisible spacing.
    """
    return re.sub(r"\s+", " ", str(s or "").replace("\xa0", " ")).strip().lower()


def _period_from(msg, subject):
    """Best-effort period from the subject, normalised to ISO so storage and
    retrieval always use one convention:
      'NetSuite Classification Lists : 2026-07'            -> 2026-07
      'AP: A/P Aging Detail BK Wego ... as of 30/06/2026'  -> 2026-06-30
    Falls back to the email Date (YYYY-MM)."""
    m = re.search(r"(20\d{2}-\d{2}(?:-\d{2})?)", subject)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2})/(\d{2})/(20\d{2})", subject)   # DD/MM/YYYY (NetSuite 'as of')
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date"))
        return dt.strftime("%Y-%m")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def _period_from_header(subject, sent):
    """Same rules as _period_from, but from the (subject, Date) pair we already
    hold after the header pass — no message body required."""
    m = re.search(r"(20\d{2}-\d{2}(?:-\d{2})?)", subject)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2})/(\d{2})/(20\d{2})", subject)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        return sent.strftime("%Y-%m")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m")


# Search All Mail FIRST: NetSuite report mail is often filtered/archived or
# only CC'd to rpa@wego.com, so it may never sit in INBOX. All Mail covers
# inbox + archived + labelled. Names differ by Gmail locale, hence the list.
SEARCH_MAILBOXES = ('"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "INBOX")


def _search_mailboxes(conn, from_addr, since, mailbox=None):
    """Try each mailbox until one selects AND returns hits. Returns
    (ids, mailbox_used, tried) — ids empty if nothing matched anywhere."""
    boxes = [mailbox] if mailbox else list(SEARCH_MAILBOXES)
    tried = []
    for box in boxes:
        typ, _ = conn.select(box, readonly=True)
        if typ != "OK":
            tried.append(f"{box}(no-such-mailbox)")
            continue
        typ, data = conn.search(None, "FROM", f'"{from_addr}"', "SINCE", since)
        if typ != "OK":
            tried.append(f"{box}(search-failed)")
            continue
        ids = data[0].split()
        tried.append(f"{box}({len(ids)} from-sender)")
        if ids:
            return ids, box, tried
    return [], None, tried


def _fetch_headers(conn, ids, batch=200):
    """Return [(mid, subject, sent_datetime)] for every candidate id, pulling
    ONLY the Subject/Date headers.

    Why this exists (Nikhil 2026-08-10): the old code ran
    `conn.fetch(mid, "(RFC822)")` for EVERY email the FROM+SINCE search
    returned, just to read its Subject. Over a 180-day window All Mail holds
    thousands of NetSuite emails carrying 1-2 MB attachments each — several GB
    of download before a single subject was compared, so the per-subsidiary
    fetch stalled and the July 'Wego Pte Ltd (Singapore)' email was never seen
    even though it was sitting in Gmail. Headers are ~200 bytes and fetch in
    batches, so the same window now costs a few hundred KB.
    """
    out = []
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        want_ids = {c.decode() if isinstance(c, bytes) else str(c) for c in chunk}
        idset = ",".join(sorted(want_ids, key=int))
        try:
            typ, data = conn.fetch(idset, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
        except Exception:
            typ, data = "NO", []
        got = set()
        if typ == "OK":
            for item in data or []:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                m = re.match(rb"\s*(\d+)\s", item[0] or b"")
                if not m:
                    continue
                mid = m.group(1).decode()
                got.add(mid)
                out.append((mid.encode(),) + _head_of(item[1]))
        # Anything the batch response didn't cover, fetch one by one (still
        # header-only, so a fallback is cheap rather than catastrophic).
        for mid in sorted(want_ids - got, key=int):
            try:
                typ, data = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
            except Exception:
                continue
            if typ != "OK":
                continue
            for item in data or []:
                if isinstance(item, tuple) and len(item) >= 2:
                    out.append((mid.encode(),) + _head_of(item[1]))
                    break
    return out


def _head_of(raw):
    """(subject, sent) from a raw header blob. Undated -> oldest, so a mail we
    cannot date can never outrank a properly dated one."""
    hdr = email.message_from_bytes(raw or b"")
    subject = _decode(hdr.get("Subject", ""))
    try:
        sent = email.utils.parsedate_to_datetime(hdr.get("Date"))
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
    except Exception:
        sent = datetime.min.replace(tzinfo=timezone.utc)
    return subject, sent


def fetch(subject_contains, report_key, period=None, since_days=7,
          from_addr=FROM_ADDR, mailbox=None):
    """Find matching emails, save every attachment to the report store.
    Returns {ok, saved, emails_matched, candidates_seen, mailboxes_tried,
    subjects_seen, auth_source} — the diagnostics matter when 0 match, so the
    agent can say WHY (wrong mailbox / sender / window / subject) instead of
    just 'not in email'."""
    conn, auth_src = _imap_login()
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        ids, box_used, tried = _search_mailboxes(conn, from_addr, since, mailbox)
        saved, matched = [], 0
        subjects_seen = []
        want = _subject_key(subject_contains)
        creds = None
        # Collect matches FIRST, then process NEWEST-FIRST by the Date header.
        # Why: IMAP SEARCH order is not guaranteed by spec, and save_report
        # overwrites the same key/period/filename — so "latest wins" was only
        # true by accident (ascending UIDs). Sorting on Date makes it explicit,
        # and the seen-set means an older duplicate can never overwrite a newer
        # file for the same period (Nikhil 2026-07-29).
        # PASS 1 — headers only, so subject matching costs bytes not gigabytes.
        cands = []
        for mid, subject, sent in _fetch_headers(conn, ids):
            if len(subjects_seen) < 25:
                subjects_seen.append(subject)
            if want and want not in _subject_key(subject):
                continue
            cands.append((sent, mid, subject))

        cands.sort(key=lambda c: c[0], reverse=True)      # newest first
        matched = len(cands)
        seen_targets = set()
        seen_periods = set()
        skipped_older = 0
        # PASS 2 — download the FULL message only for mails we will actually
        # save. Newest-first + seen_periods means an older duplicate for a
        # period is skipped before its attachment is ever transferred.
        for sent, mid, subject in cands:
            per = period or _period_from_header(subject, sent)
            if per in seen_periods:
                skipped_older += 1
                continue
            try:
                typ, msgdata = conn.fetch(mid, "(RFC822)")
            except Exception:
                continue
            if typ != "OK" or not msgdata or not isinstance(msgdata[0], tuple):
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            seen_periods.add(per)
            for part in msg.walk():
                fname = part.get_filename()
                if not fname:
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                target = (per, _decode(fname))
                if target in seen_targets:
                    skipped_older += 1      # a newer email already supplied this
                    continue
                seen_targets.add(target)
                if creds is None:
                    try:
                        creds = s3lite.resolve_creds()
                    except Exception:
                        creds = False   # save locally; mirror flagged in entry
                entry = report_store.save_report(
                    payload, report_key, per, _decode(fname), source="email",
                    meta={"subject": subject, "from": from_addr,
                          "email_date": msg.get("Date", ""), "mailbox": box_used},
                    creds=creds or None, mirror=bool(creds))
                saved.append(entry)
        newest_used = cands[0][0].isoformat() if cands else None
        return {"ok": True, "emails_matched": matched, "saved": saved,
                "candidates_seen": len(ids), "mailbox_used": box_used,
                "mailboxes_tried": tried, "subjects_seen": subjects_seen,
                "newest_email_date": newest_used, "older_duplicates_skipped": skipped_older,
                "auth_source": auth_src}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def preflight():
    print("== email-report preflight ==")
    try:
        pwd, src = get_app_password()
        print(f"PASS  app password obtained ({src}, {len(pwd)} chars)")
    except Exception as e:
        print(f"FAIL  password/secret: {e}")
        print("      NOTE: this preflight runs as a bash subprocess and inherits "
              "the shell env; the MCP server is spawned by the gateway with ONLY "
              "its configured env block. If preflight PASSES here but the "
              "fetch_email_report TOOL says NO_PASSWORD, put the value where the "
              "server can see it: add EMAIL_FROM_PWD=<value> to "
              "/home/openclaw/.openclaw/cron/openclaw.env (sourced at startup), "
              "or into the MCP server's env block via `openclaw mcp set`, then "
              "restart.")
        return 1
    try:
        conn, _ = _imap_login()
        typ, _d = conn.select("INBOX", readonly=True)
        conn.logout()
        print(f"PASS  IMAP login as {GMAIL_USER} + INBOX select ({typ})")
    except Exception as e:
        print(f"FAIL  {e}")
        return 1
    print("VERDICT: email report fetching will work.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--subject", help="substring the subject must contain")
    ap.add_argument("--report-key", help="store under this report key")
    ap.add_argument("--period", help="override period (default: parsed from subject/date)")
    ap.add_argument("--since-days", type=int, default=7)
    a = ap.parse_args()
    if a.preflight:
        sys.exit(preflight())
    if not (a.subject and a.report_key):
        sys.exit("need --subject and --report-key (or --preflight)")
    r = fetch(a.subject, a.report_key, a.period, a.since_days)
    print(f"emails matched: {r['emails_matched']} | files saved: {len(r['saved'])} "
          f"| auth: {r['auth_source']}")
    for e in r["saved"]:
        print(f"  {e['report_key']}/{e['period']}/{e['filename']} "
              f"({e['size']} bytes, mirrored={e['s3_mirrored']})")
