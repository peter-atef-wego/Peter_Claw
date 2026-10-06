#!/usr/bin/env python3
"""test_end_to_end.py — run the REAL A/P Aging request path against a fake mailbox.

Nothing is stubbed except the IMAP socket: real registry, real subject matching,
real period parsing, real report store on disk (REPORTS_DIR), real CSV->xlsx
conversion, real execute_get_stored_report. The mailbox is loaded with the same
subjects Akansha's NetSuite schedule actually sends, including the two traps
that have burned us:

  · 'BK  Wego Pte Ltd (Singapore) as of ...'  <- DOUBLE space, as NetSuite sends it
  · three distinct Singapore-ish scopes that must never be confused
  · an older duplicate of the SAME period that must not overwrite the newer one

Run it anywhere, including the pod:

    python3 scripts/report_store/test_end_to_end.py

Exit code 0 = every case passed.
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
os.environ["REPORTS_DIR"] = tempfile.mkdtemp(prefix="ap_aging_test_")
sys.path.insert(0, _HERE)
sys.path.insert(0, _SCRIPTS)

import imaplib                       # noqa: E402
import email_fetcher                 # noqa: E402
import report_store                  # noqa: E402
import netsuite_mcp_server as srv    # noqa: E402
import openpyxl                      # noqa: E402

KEY = "ap_aging_detail_bk_consolidated"
SG = "Wego Pte Ltd (Singapore)"


def csv_for(scope, as_of, vendors):
    """A NetSuite A/P Aging Detail export: 4 title rows, a blank, then data."""
    rows = ["Wego Group", scope, "A/P Aging Detail BK", f"As of {as_of}", "",
            "Vendor,Transaction Name,Category,Subsidiary,BU Code,Date,Amount,Open Balance"]
    for v in vendors:
        rows.append(v)
        rows.append(f"Bill,{v},Trade,{scope},BL-WGC,30/07/2026,3455.04,3455.04")
        rows.append(f"Total - {v},,,,,,3455.04,3455.04")
    return ("\n".join(rows) + "\n").encode()


# (subject, Date header, attachment bytes) — the mailbox under test.
MAIL = [
    ("AP: A/P Aging Detail BK  Wego (Consolidated) as of 30/07/2026",
     "Thu, 30 Jul 2026 04:00:00 +0000",
     csv_for("Wego (Consolidated)", "30 July 2026", ["Wego Egypt LLC", "Wego Travel S.A.E"])),
    ("AP: A/P Aging Detail BK  Wego Pte Ltd (Singapore) as of 30/06/2026",
     "Tue, 30 Jun 2026 04:00:00 +0000",
     csv_for(SG, "30 June 2026", ["JUNE VENDOR"])),
    ("AP: A/P Aging Detail BK  Wego Pte Ltd (Singapore) as of 30/07/2026",
     "Thu, 30 Jul 2026 03:00:00 +0000",
     csv_for(SG, "30 July 2026", ["STALE DUPLICATE"])),
    ("AP: A/P Aging Detail BK  Wego Pte Ltd (Singapore) as of 30/07/2026",
     "Thu, 30 Jul 2026 05:00:00 +0000",
     csv_for(SG, "30 July 2026", ["1PASSWORD", "A.F.T SG PTE LTD"])),
    ("AP: A/P Aging Detail BK  Wego Pte Ltd (Singapore) (Consolidated) as of 30/07/2026",
     "Thu, 30 Jul 2026 04:00:00 +0000",
     csv_for("Wego Pte Ltd (Singapore) (Consolidated)", "30 July 2026", ["SG CONSOL"])),
    ("AP: A/P Aging Detail BK  Wego Pte Ltd (SG Group) (Consolidated) as of 30/07/2026",
     "Thu, 30 Jul 2026 04:00:00 +0000",
     csv_for("Wego Pte Ltd (SG Group) (Consolidated)", "30 July 2026", ["SG GROUP"])),
]


class FakeIMAP:
    """Only the socket is fake. Subject matching, dating, dedup are the real code."""

    def __init__(self, mail, auth_error=None):
        self.mail, self.auth_error = mail, auth_error
        self.bodies_pulled = 0

    def login(self, user, pwd):
        if self.auth_error:
            raise imaplib.IMAP4.error(self.auth_error)
        return ("OK", [b"logged in"])

    def select(self, box, readonly=True):
        return ("OK", None) if "All Mail" in box or box == "INBOX" else ("NO", None)

    def search(self, *a):
        return ("OK", [b" ".join(str(i + 1).encode() for i in range(len(self.mail)))])

    def _raw(self, i, headers_only):
        subj, date, payload = self.mail[i]
        head = f"Subject: {subj}\r\nDate: {date}\r\n".encode()
        if headers_only:
            return head + b"\r\n"
        self.bodies_pulled += 1
        return (head + b"MIME-Version: 1.0\r\n"
                b"Content-Type: application/octet-stream\r\n"
                b'Content-Disposition: attachment; filename="report.csv"\r\n\r\n' + payload)

    def fetch(self, idset, what):
        hdr = "HEADER.FIELDS" in what
        out = []
        for tok in str(idset).replace("b'", "").strip("'").split(","):
            i = int(tok) - 1
            out.append((f"{i + 1} (X ".encode(), self._raw(i, hdr)))
            out.append(b")")
        return ("OK", out)

    def logout(self):
        return ("BYE", None)


_REAL_LOADER = srv._report_store_modules


def install_mailbox(mail, auth_error=None):
    """Swap the IMAP socket in EVERY live copy of the fetcher.

    execute_get_stored_report re-executes report_store/email_fetcher.py through
    importlib on EVERY call, so it holds a different module object than the one
    this file imported by name AND rebuilds it constantly. Patching the local
    copy alone left the server talking to real Gmail; patching without pinning
    let the next call overwrite the patch. Both are the class of mistake this
    suite exists to catch, so: pin one instance, patch every copy.
    """
    box = FakeIMAP(mail, auth_error)
    mods = _REAL_LOADER()
    srv._report_store_modules = lambda: mods      # pin, or the patch is re-executed away
    for mod in {id(m): m for m in (email_fetcher, mods["email_fetcher"])}.values():
        mod.get_app_password = lambda: ("app-password-16ch", "test:EMAIL_FROM_PWD")
        mod.imaplib.IMAP4_SSL = lambda host: box
    return box


def sheet_of(path):
    ws = openpyxl.load_workbook(path).active
    return ["|".join("" if c is None else str(c) for c in row)
            for row in ws.iter_rows(values_only=True)]


PASS, FAIL = [], []


def check(case, cond, detail):
    (PASS if cond else FAIL).append(case)
    print(f"  {'PASS' if cond else 'FAIL'}  {case}: {detail}")


def case_1_happy_path():
    print("\n[1] July IS in the mailbox — the exact request Akansha makes")
    box = install_mailbox(MAIL)
    out = srv.execute_get_stored_report(KEY, "30/07/2026", subsidiary=SG)
    check("returns ok", out.get("ok"), f"ok={out.get('ok')} error={out.get('error')}")
    if not out.get("ok"):
        print(f"        {out.get('message')}")
        return
    paths = out.get("file_paths") or []
    check("exactly one xlsx", len(paths) == 1 and paths[0].endswith(".xlsx"), str(paths))
    check("served the asked period", out.get("period") == "2026-07-30",
          f"period={out.get('period')}")
    check("no period substitution", not out.get("substituted_from"),
          f"substituted_from={out.get('substituted_from')}")
    check("came from the subsidiary's own email",
          out.get("source") == "per_subsidiary_email", str(out.get("source")))
    rows = sheet_of(paths[0])
    body = "\n".join(rows)
    check("title block says Singapore", SG in body, rows[1][:60])
    check("title block says July", "30 July 2026" in body, rows[3][:60])
    check("holds the NEWER July email's rows", "1PASSWORD" in body,
          "1PASSWORD present" if "1PASSWORD" in body else "MISSING")
    check("older same-period duplicate ignored", "STALE DUPLICATE" not in body,
          "absent" if "STALE DUPLICATE" not in body else "LEAKED IN")
    check("no other subsidiary bleeds in",
          not any(x in body for x in ("Wego Egypt", "SG GROUP", "SG CONSOL")), "clean")
    check("downloaded only needed bodies", box.bodies_pulled <= 2,
          f"{box.bodies_pulled} of {len(MAIL)} full messages")


def case_2_scope_traps():
    print("\n[2] The three Singapore scopes must stay distinct")
    for scope, marker in ((SG, "1PASSWORD"),
                          ("Wego Pte Ltd (Singapore) (Consolidated)", "SG CONSOL"),
                          ("Wego Pte Ltd (SG Group) (Consolidated)", "SG GROUP")):
        install_mailbox(MAIL)
        out = srv.execute_get_stored_report(KEY, "30/07/2026", subsidiary=scope)
        body = "\n".join(sheet_of(out["file_paths"][0])) if out.get("ok") else ""
        check(f"{scope!r} -> its own file", marker in body,
              f"marker {marker} {'found' if marker in body else 'MISSING'}")
    install_mailbox(MAIL)
    out = srv.execute_get_stored_report(KEY, "30/07/2026", subsidiary="singapore")
    check("bare 'singapore' asks instead of guessing",
          out.get("error") == "SCOPE_NEEDS_CONFIRMATION",
          f"{out.get('error')} candidates={out.get('candidates')}")


def case_3_auth_broken():
    print("\n[3] Gmail login rejected — must send NOTHING, not last month's file")
    install_mailbox(MAIL)                      # seed June + July into the store
    srv.execute_get_stored_report(KEY, "30/06/2026", subsidiary=SG)
    install_mailbox(MAIL, auth_error="b'[AUTHENTICATIONFAILED] Invalid credentials'")
    out = srv.execute_get_stored_report(KEY, "31/08/2026", subsidiary=SG)
    check("refuses to serve", not out.get("ok"), f"ok={out.get('ok')}")
    check("says the inbox was unreadable", out.get("error") == "INBOX_UNREACHABLE",
          str(out.get("error")))
    check("names the real cause", "IMAP_AUTH_REJECTED" in (out.get("message") or ""),
          (out.get("message") or "")[:88])
    check("does NOT substitute another period", not out.get("file_paths"),
          f"file_paths={out.get('file_paths')}")


def case_4_period_never_emailed():
    print("\n[4] Period genuinely never emailed — serve latest, LABELLED")
    install_mailbox(MAIL)
    out = srv.execute_get_stored_report(KEY, "31/08/2026", subsidiary=SG)
    check("still delivers a file", out.get("ok") and out.get("file_paths"),
          f"ok={out.get('ok')}")
    check("flags the substitution", out.get("substituted_from") == "2026-08-31",
          f"substituted_from={out.get('substituted_from')} served={out.get('period')}")
    check("tells the agent to say so", "LATEST" in (out.get("message") or "").upper(),
          (out.get("message") or "")[:88])


def case_5_how_people_actually_ask():
    """The args an agent plausibly forwards from a real Slack message.

    Nikhil pastes the whole subject line. Akansha drops the brackets. Neither
    should produce "which subsidiary did you mean?" when the message already
    said it in full — but genuinely ambiguous wording still must ask.
    """
    print("\n[5] Real query shapes -> the right scope, or an honest ask")
    subj = "AP: A/P Aging Detail BK  Wego Pte Ltd (Singapore) as of 30/07/2026"
    for label, arg in (("pasted subject (double space)", subj),
                       ("subject without the AP: tag", subj.replace("AP: ", "")),
                       ("brackets dropped", "Wego Pte Ltd Singapore"),
                       ("lowercase", "wego pte ltd (singapore)")):
        install_mailbox(MAIL)
        out = srv.execute_get_stored_report(KEY, subj, subsidiary=arg)
        body = "\n".join(sheet_of(out["file_paths"][0])) if out.get("ok") else ""
        check(f"{label} -> July Singapore",
              out.get("period") == "2026-07-30" and "1PASSWORD" in body,
              f"period={out.get('period')} error={out.get('error')}")
    for label, arg in (("bare 'Singapore'", "Singapore"),
                       ("bare 'consolidated'", "consolidated")):
        install_mailbox(MAIL)
        out = srv.execute_get_stored_report(KEY, "30/07/2026", subsidiary=arg)
        check(f"{label} still asks", out.get("error") == "SCOPE_NEEDS_CONFIRMATION",
              f"{out.get('error')} candidates={out.get('candidates')}")


def main():
    print(f"report store: {os.environ['REPORTS_DIR']}")
    for fn in (case_1_happy_path, case_2_scope_traps,
               case_3_auth_broken, case_4_period_never_emailed,
               case_5_how_people_actually_ask):
        fn()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + "; ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
