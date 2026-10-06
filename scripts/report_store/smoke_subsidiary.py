#!/usr/bin/env python3
"""smoke_subsidiary.py — prove, end to end, that a per-subsidiary A/P Aging
request resolves to the right email and returns one .xlsx.

Answers the question "is it understanding the query and turning it into the
right subject?" with evidence rather than a guess. Every stage prints what it
produced, so a failure names itself instead of surfacing as the agent quietly
reading the wrong file.

  python3 scripts/report_store/smoke_subsidiary.py "Wego Pte Ltd (Singapore)" 30/07/2026
  python3 scripts/report_store/smoke_subsidiary.py singapore 30/07/2026   # -> should ASK

Stages:
  1. period      — the user's words -> ISO date
  2. scope       — the user's words -> an exact scope NetSuite emails (or ASK)
  3. subject     — the scope -> the subject line we search Gmail for
  4. inbox       — what IMAP actually returned for that subject
  5. store       — what landed in report memory
  6. tool        — the real get_stored_report result the agent would receive
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _SCRIPTS)

import filter_subsidiary as fs          # noqa: E402
import email_fetcher                    # noqa: E402
import report_store                     # noqa: E402
import netsuite_mcp_server as srv       # noqa: E402

KEY = "ap_aging_detail_bk_consolidated"


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    asked_sub, asked_period = argv[0], argv[1]

    entry, _subs = srv._report_registry_entry(KEY)
    if not entry:
        sys.exit(f"FAIL  registry has no entry for {KEY}")

    iso = srv._normalise_period(asked_period) or asked_period
    print(f"1. period   '{asked_period}' -> {iso}")

    variants = entry.get("subsidiary_variants") or []
    match, cands = fs.resolve_subsidiary(asked_sub, variants)
    if not match:
        print(f"2. scope    '{asked_sub}' -> ASK (candidates: {cands or variants})")
        print("\nThis is correct behaviour for an unclear scope: the agent must ask "
              "before sending a finance file. Re-run with an exact scope name.")
        return 0
    print(f"2. scope    '{asked_sub}' -> {match!r}")

    subject = entry["subsidiary_subject_template"].format(subsidiary=match)
    sub_key = entry["subsidiary_report_key_template"].format(
        slug=srv._subsidiary_slug(match))
    print(f"3. subject  searching Gmail for: {subject!r}")
    print(f"            report memory key   : {sub_key}")

    try:
        r = email_fetcher.fetch(subject, sub_key, period=None, since_days=180)
    except Exception as e:
        print(f"4. inbox    FAIL {type(e).__name__}: {e}")
        print("\nThe mailbox could not be read — this is NOT proof the report is "
              "missing. Fix auth/network first (python3 email_fetcher.py --preflight).")
        return 1
    print(f"4. inbox    scanned {r['candidates_seen']} mail from the sender in "
          f"{r['mailbox_used']}; {r['emails_matched']} matched this subject; "
          f"saved {len(r['saved'])} attachment(s); newest {r['newest_email_date']}")
    for e in r["saved"]:
        print(f"            saved -> {e['period']}/{e['filename']} ({e['size']} bytes)")
    if not r["emails_matched"]:
        print("            subjects actually seen (first few):")
        for s in r["subjects_seen"][:8]:
            print(f"              · {s}")

    periods = sorted({x["period"] for x in report_store.find_reports(sub_key)})
    print(f"5. store    periods held for this subsidiary: {periods or '(none)'}")

    out = srv.execute_get_stored_report(KEY, iso, subsidiary=match)
    print(f"6. tool     ok={out.get('ok')} "
          f"period={out.get('period')} source={out.get('source')} "
          f"substituted_from={out.get('substituted_from')}")
    if out.get("ok"):
        paths = out.get("file_paths") or []
        print(f"            file_paths ({len(paths)}): {paths}")
        ok = len(paths) == 1 and paths[0].lower().endswith(".xlsx")
        print(f"            {'PASS' if ok else 'FAIL'}  exactly one .xlsx to upload")
        if out.get("substituted_from"):
            print(f"            NOTE {out['substituted_from']} was not emailed; "
                  f"served {out['period']} — the agent must say so in one line.")
        return 0 if ok else 1
    print(f"            error={out.get('error')}")
    print(f"            {out.get('message')}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
