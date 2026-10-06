#!/usr/bin/env python3
"""report_store.py — persistent memory for downloaded reports.

Concept borrowed from the flights-pricing memory-service (sources -> store ->
retrieval) implemented openclaw-style: stdlib only, flat files + a JSON index,
mirrored to S3 per-file at save time.

Layout:
  local:  ~/.openclaw/reports/<report_key>/<period>/<filename>
          ~/.openclaw/reports/index.json           (what we have + provenance)
  S3:     netsuite-agent/reports/<report_key>/<period>/<filename>

Durability is double: the local dir lives inside STATE_DIR (so the nightly
state backup includes it) AND every file is mirrored to S3 immediately at
save time — so a report saved at 10:00 survives a node loss at 10:05, and
retrieval by period works straight from S3 even on a fresh pod.

`period` is a plain string the caller controls — use "YYYY-MM" for monthly
reports ("2026-07"), "YYYY-MM-DD" for dailies. Retrieval matches exactly,
so store and query with the same convention.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "memory_backup"))
import s3lite  # noqa: E402

STATE_DIR = os.environ.get("STATE_DIR", "/home/openclaw/.openclaw")
REPORTS_DIR = os.environ.get("REPORTS_DIR", os.path.join(STATE_DIR, "reports"))
BUCKET = os.environ.get("BACKUP_BUCKET", "wego-enterprise-agent-logs-us-east-1-794531973703")
BASE_PREFIX = os.environ.get("BACKUP_BASE_PREFIX", "netsuite-agent")
INDEX = os.path.join(REPORTS_DIR, "index.json")


def _safe_name(s):
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in str(s)).strip()


def _load_index():
    try:
        return json.load(open(INDEX))
    except (OSError, json.JSONDecodeError):
        return {"reports": []}


def _save_index(idx):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    tmp = INDEX + ".tmp"
    json.dump(idx, open(tmp, "w"), indent=2)
    os.replace(tmp, INDEX)


def save_report(content_bytes, report_key, period, filename, source, meta=None,
                creds=None, mirror=True):
    """Store one report file locally + mirror to S3 + index it.
    Returns the index entry. Overwrites the same report_key/period/filename
    (a re-fetched report replaces the old copy — latest wins)."""
    report_key = _safe_name(report_key)
    period = _safe_name(period)
    filename = _safe_name(os.path.basename(filename)) or "report.bin"

    local_dir = os.path.join(REPORTS_DIR, report_key, period)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)
    with open(local_path, "wb") as fh:
        fh.write(content_bytes)

    s3_key = f"{BASE_PREFIX}/reports/{report_key}/{period}/{filename}"
    mirrored = False
    mirror_error = None
    if mirror:
        try:
            creds = creds or s3lite.resolve_creds()
            s3lite.put_object(creds, BUCKET, s3_key, content_bytes)
            mirrored = True
        except Exception as e:          # local copy still saved — report loudly
            mirror_error = str(e)[:200]

    entry = {
        "report_key": report_key, "period": period, "filename": filename,
        "source": source, "size": len(content_bytes),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "local_path": local_path, "s3_key": s3_key, "s3_mirrored": mirrored,
        "meta": meta or {},
    }
    if mirror_error:
        entry["s3_mirror_error"] = mirror_error
    idx = _load_index()
    idx["reports"] = [r for r in idx["reports"]
                      if not (r["report_key"] == report_key and r["period"] == period
                              and r["filename"] == filename)]
    idx["reports"].append(entry)
    _save_index(idx)
    return entry


def find_reports(report_key=None, period=None):
    """Index lookup. Both filters optional; exact match on each when given."""
    rows = _load_index()["reports"]
    if report_key:
        rows = [r for r in rows if r["report_key"] == _safe_name(report_key)]
    if period:
        rows = [r for r in rows if r["period"] == _safe_name(period)]
    return sorted(rows, key=lambda r: r["saved_at"])


def get_report(report_key, period, creds=None):
    """Return local file path(s) for report_key+period, pulling from the S3
    mirror when the local copy is gone (fresh pod after node loss)."""
    hits = find_reports(report_key, period)
    out = []
    if hits:
        for r in hits:
            if os.path.exists(r["local_path"]):
                out.append(r["local_path"])
                continue
            # index survived (git/state restore) but file didn't — refetch
            try:
                creds = creds or s3lite.resolve_creds()
                blob = s3lite.get_object(creds, BUCKET, r["s3_key"])
                os.makedirs(os.path.dirname(r["local_path"]), exist_ok=True)
                open(r["local_path"], "wb").write(blob)
                out.append(r["local_path"])
            except Exception:
                pass
        if out:
            return out

    # No index at all (fully fresh state) — fall back to listing S3 directly.
    try:
        creds = creds or s3lite.resolve_creds()
        prefix = f"{BASE_PREFIX}/reports/{_safe_name(report_key)}/{_safe_name(period)}/"
        for o in s3lite.list_objects(creds, BUCKET, prefix):
            fname = os.path.basename(o["key"])
            local_dir = os.path.join(REPORTS_DIR, _safe_name(report_key), _safe_name(period))
            os.makedirs(local_dir, exist_ok=True)
            p = os.path.join(local_dir, fname)
            open(p, "wb").write(s3lite.get_object(creds, BUCKET, o["key"]))
            out.append(p)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    # CLI: list what's stored
    rows = find_reports(*(sys.argv[1:3] if len(sys.argv) > 1 else ()))
    if not rows:
        print("no stored reports match")
    for r in rows:
        flag = "" if r.get("s3_mirrored") else "  (NOT mirrored to S3!)"
        print(f"{r['report_key']:32} {r['period']:12} {r['filename']:44} "
              f"{r['size']:>10}  {r['source']:8} {r['saved_at']}{flag}")
