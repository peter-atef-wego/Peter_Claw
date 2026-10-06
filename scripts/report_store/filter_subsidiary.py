#!/usr/bin/env python3
"""filter_subsidiary.py — carve a per-subsidiary report out of the stored
Consolidated 'A/P Aging Detail BK' export (and any report with the same shape).

Input layout (NetSuite export):
  row 1  Wego Group
  row 2  Wego (Consolidated)          <- replaced with the subsidiary name
  row 3  A/P Aging Detail BK
  row 4  As of 30 June 2026
  row 7  column headers (incl. 'Subsidiary: Name')
  row 8+ data

What it does: keep the title block (rewriting row 2), keep the header row,
keep ONLY the data rows whose 'Subsidiary: Name' equals the requested
subsidiary. Vendor group-header / subtotal rows from the consolidated
grouping are dropped (their totals describe the consolidated view, not the
subsidiary — recomputing them here would be fabrication). Output is .xlsx.

Format sniffing: NetSuite mails '.xls' that can be real BIFF, actual XLSX,
or an HTML table wearing a .xls name — all three are handled.
Dependencies (pod): openpyxl for output (+xlsx input); xlrd for BIFF input.
Missing libs produce a LOUD, named error — never a wrong file.
"""
import os
import re
import sys

SUBSIDIARY_COL = "Subsidiary: Name"


def _read_grid(path):
    """Return the sheet as list[list[values]] regardless of real format."""
    with open(path, "rb") as fh:
        magic = fh.read(8)
    if magic[:4] == b"PK\x03\x04":                      # real xlsx (whatever the extension says)
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("MISSING_LIB: openpyxl needed to read this xlsx "
                               "(pip install --user openpyxl)")
        load_path = path
        tmp = None
        if not path.lower().endswith(".xlsx"):
            # openpyxl validates by EXTENSION — NetSuite ships xlsx content
            # under a .xls name, so load via a temp .xlsx copy.
            import shutil
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".xlsx")
            os.close(fd)
            shutil.copyfile(path, tmp)
            load_path = tmp
        try:
            wb = openpyxl.load_workbook(load_path, data_only=True, read_only=True)
            ws = wb[wb.sheetnames[0]]
            return [[c if c is not None else "" for c in row]
                    for row in ws.iter_rows(values_only=True)]
        finally:
            if tmp:
                os.unlink(tmp)
    if magic[:4] == b"\xd0\xcf\x11\xe0":                 # BIFF .xls
        try:
            import xlrd
        except ImportError:
            raise RuntimeError("MISSING_LIB: xlrd needed to read this .xls "
                               "(pip install --user xlrd)")
        book = xlrd.open_workbook(path)
        sh = book.sheet_by_index(0)
        return [[sh.cell_value(r, c) for c in range(sh.ncols)]
                for r in range(sh.nrows)]
    text = open(path, "rb").read().decode("utf-8", "replace")
    low_head = text[:2000].lower()
    # CSV / TSV — NetSuite's scheduled export now arrives as report.csv (2026-07-29).
    if path.lower().endswith((".csv", ".tsv", ".txt")) or (
            "<" not in low_head[:200] and ("," in low_head or "\t" in low_head)):
        import csv as _csv
        import io as _io
        try:
            dialect = _csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except _csv.Error:
            dialect = _csv.excel
        return [row for row in _csv.reader(_io.StringIO(text), dialect)]
    # SpreadsheetML (Excel 2003 XML) — what NetSuite's emailed report.xls
    # actually is. Cells are SPARSE: ss:Index jumps over empty columns, so
    # positional parsing misaligns data — indexes must be honored.
    if "<?xml" in low_head and "urn:schemas-microsoft-com:office:spreadsheet" in low_head:
        return _read_spreadsheetml(path)
    # HTML table pretending to be .xls (older NetSuite export style)
    if "<table" in text.lower() or "<html" in low_head:
        return _read_html_table(text)
    raise RuntimeError(f"UNRECOGNISED_FORMAT: first bytes {magic!r} — not xlsx/xls/xml/html")


def _read_spreadsheetml(path):
    import xml.etree.ElementTree as ET
    NS = "{urn:schemas-microsoft-com:office:spreadsheet}"
    rows = []
    row = None
    col = 0
    for event, el in ET.iterparse(path, events=("start", "end")):
        tag = el.tag
        if event == "start":
            if tag == f"{NS}Row":
                row, col = [], 0
            elif tag == f"{NS}Cell" and row is not None:
                idx = el.get(f"{NS}Index")
                col = int(idx) if idx else col + 1     # ss:Index is 1-based
        elif event == "end":
            if tag == f"{NS}Cell" and row is not None:
                data = el.find(f"{NS}Data")
                val = (data.text or "").strip() if data is not None else ""
                while len(row) < col:
                    row.append("")
                row[col - 1] = val
                el.clear()
            elif tag == f"{NS}Row" and row is not None:
                rows.append(row)
                row = None
                el.clear()
    if not rows:
        raise RuntimeError("UNRECOGNISED_FORMAT: SpreadsheetML but no rows parsed")
    return rows


def _read_html_table(text):
    from html.parser import HTMLParser

    class T(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell, self.in_cell = [], None, [], False

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th"):
                self.in_cell, self.cell = True, []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.in_cell:
                self.in_cell = False
                self.row.append("".join(self.cell).strip())
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.in_cell:
                self.cell.append(data)

    p = T()
    p.feed(text)
    if not p.rows:
        raise RuntimeError("UNRECOGNISED_FORMAT: HTML file but no <table> rows found")
    return p.rows


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


_SUBJECT_SCOPE = re.compile(r"\bbk\s+(.+?)\s+as\s+of\b", re.I)


def scope_from_subject(text):
    """Pull the scope out of a NetSuite subject line.

    The subject IS the mapping: everything between 'BK ' and ' as of' is the
    scope, verbatim. Finance users paste the whole subject —
    'AP: A/P Aging Detail BK Wego Pte Ltd (Singapore) as of 30/07/2026' — and
    the agent forwards it as the subsidiary, which matched nothing and made the
    agent ask which subsidiary was meant when the user had already said it in
    full (Nikhil 2026-08-11). Returns None when the text isn't subject-shaped.
    """
    m = _SUBJECT_SCOPE.search(re.sub(r"\s+", " ", str(text or "")))
    return m.group(1).strip() if m else None


def resolve_subsidiary(user_text, names):
    """Match what the user said to the official subsidiary list.
    Returns (match, candidates) — match set only when exactly one fits."""
    # A pasted subject line already names the scope exactly — use it and skip
    # the fuzzy matching entirely.
    from_subject = scope_from_subject(user_text)
    if from_subject:
        user_text = from_subject
    want = _norm(user_text)
    exact = [n for n in names if _norm(n) == want]
    if len(exact) == 1:
        return exact[0], exact
    # Forward containment only (user text inside the official name) — reverse
    # containment lets short names like 'Wego' swallow every query.
    subs = [n for n in names if want in _norm(n)]
    if len(subs) == 1:
        return subs[0], subs
    if subs:
        return None, subs
    # Token-subset fallback: every word the user typed appears in the name, in
    # any order/punctuation. Lets 'SG Group (Consolidated)' find
    # 'Wego Pte Ltd (SG Group) (Consolidated)' while 'singapore' still stays
    # ambiguous across the two Singapore reports.
    qt = set(re.findall(r"[a-z0-9.]+", want))
    if qt:
        toks = {n: set(re.findall(r"[a-z0-9.]+", _norm(n))) for n in names}
        # Identical word-set first: 'Wego Pte Ltd Singapore' (brackets dropped)
        # is the SAME scope as 'Wego Pte Ltd (Singapore)', and must not be
        # reported as ambiguous just because '... (Singapore) (Consolidated)'
        # is a superset of it.
        same = [n for n in names if toks[n] == qt]
        if len(same) == 1:
            return same[0], same
        hits = [n for n in names if qt <= toks[n]]
        if len(hits) == 1:
            return hits[0], hits
        if hits:
            return None, hits
    return None, []


_ISO_DT = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T[\d:.]+Z?$")


def _as_date(v):
    """NetSuite writes date cells as ss:Type="DateTime" with ISO values
    ('2026-07-15T00:00:00.000'). Excel renders them as dates, but copying the
    raw text into a new sheet shows the ISO string — Akansha 2026-07-29:
    "Date column needs to be fixed". Return a real date object so the output
    can carry NetSuite's DD/MM/YYYY display format; None if not a date."""
    import datetime as _dt
    m = _ISO_DT.match(str(v or "").strip())
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def convert_to_xlsx(src_path, out_path=None):
    """Convert ANY supported report file (CSV / SpreadsheetML / BIFF / xlsx) to
    a clean .xlsx: every row preserved verbatim (order, grouping, NetSuite's own
    totals) but cells made to behave — date columns become real dates rendered
    DD/MM/YYYY instead of ISO text, money columns become 2dp numbers.

    Needed because the scheduled export is now CSV while finance wants Excel
    (Nikhil 2026-07-29). Format change only — no rows added, dropped or
    recomputed."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("MISSING_LIB: openpyxl needed to convert to xlsx "
                           "(pip install --user openpyxl)")
    grid = _read_grid(src_path)
    if not grid:
        raise RuntimeError("EMPTY_FILE: nothing to convert")

    hdr_i = next((i for i, row in enumerate(grid)
                  if any(_norm(c) == _norm(SUBSIDIARY_COL) for c in row)), None)
    header = grid[hdr_i] if hdr_i is not None else []
    date_cols = [j for j, c in enumerate(header) if "date" in _norm(c)]
    money_cols = [j for j, c in enumerate(header)
                  if _norm(c) in (_norm("Amount (Foreign Currency)"),
                                  _norm("Open Balance"))]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    for i, row in enumerate(grid):
        out = list(row)
        if hdr_i is not None and i > hdr_i:
            for j in date_cols:
                if j < len(out):
                    dv = _as_date(out[j])
                    if dv is not None:
                        out[j] = dv
            for j in money_cols:
                if j < len(out):
                    mv = _amount(out[j])
                    if mv is not None:
                        out[j] = round(mv, 2)
        ws.append(out)

    if date_cols:
        from openpyxl.utils import get_column_letter
        for j in date_cols:
            for cell in ws[get_column_letter(j + 1)]:
                if hasattr(cell.value, "year"):
                    cell.number_format = "DD/MM/YYYY"

    if not out_path:
        out_path = os.path.splitext(src_path)[0] + ".xlsx"
    wb.save(out_path)
    return {"out_path": out_path, "rows": len(grid),
            "converted_from": os.path.splitext(src_path)[1] or "?"}


def _amount(v):
    """Coerce a NetSuite cell to a number: 1646.64, '$1,646.64', '($376.31)',
    '-$8,939.55'. Returns None for non-numeric."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    if not s:
        return None
    neg = ("(" in s and ")" in s) or s.startswith("-")
    s = re.sub(r"[^0-9.]", "", s.replace(",", ""))
    if not s or s == ".":
        return None
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return None


def _parse_groups(data, vendor_col):
    """Parse NetSuite's grouped layout into [(vendor, [detail rows])].
    Group header = vendor name alone in the Vendor column; 'Total - X' rows
    close a group (their consolidated totals are discarded — we recompute)."""
    groups, current = [], None
    for r in data:
        v = str(r[vendor_col]).strip() if len(r) > vendor_col else ""
        others = any(str(c).strip() for j, c in enumerate(r) if j != vendor_col)
        if v and _norm(v).startswith("total"):
            current = None                      # consolidated subtotal — drop
            continue
        if v and not others:
            current = (v, [])                   # vendor group header
            groups.append(current)
            continue
        if not v and not others:
            continue                            # blank spacer row
        if current is None:
            current = ("", [])                  # detail before any header
            groups.append(current)
        current[1].append(r)
    return groups


def filter_report(src_path, subsidiary, out_path=None):
    """Per-subsidiary xlsx PRESERVING NetSuite's vendor grouping:
    vendor header -> matching detail rows -> 'Total - <vendor>' recomputed
    from the kept rows only (consolidated totals are wrong for a slice).
    Vendors with no matching rows are omitted. A grand 'Total' row closes
    the report. Built-in validation: grand total must equal the sum of the
    recomputed group totals. Returns stats + validation."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("MISSING_LIB: openpyxl needed to write the filtered "
                           "xlsx (pip install --user openpyxl)")
    grid = _read_grid(src_path)

    hdr_i = next((i for i, row in enumerate(grid)
                  if any(_norm(c) == _norm(SUBSIDIARY_COL) for c in row)), None)
    if hdr_i is None:
        raise RuntimeError(f"HEADER_NOT_FOUND: no row contains '{SUBSIDIARY_COL}' — "
                           f"is this the right report file?")
    header = list(grid[hdr_i])
    ncols = len(header)

    def col(name, default=None):
        return next((j for j, c in enumerate(header) if _norm(c) == _norm(name)), default)

    sub_col = col(SUBSIDIARY_COL)
    vendor_col = col("Vendor", 0)
    open_col = col("Open Balance")
    amt_col = col("Amount (Foreign Currency)")
    cur_col = next((j for j, c in enumerate(header)
                    if _norm(c).startswith("currency")), None)
    # Any column whose header mentions 'date' holds NetSuite DateTime cells.
    date_cols = [j for j, c in enumerate(header) if "date" in _norm(c)]

    data = grid[hdr_i + 1:]
    want = _norm(subsidiary)
    groups = _parse_groups(data, vendor_col)

    def _display_row(r):
        """Money cells -> rounded NUMBERS (NetSuite XML carries full precision
        like 291.26714952 while the UI shows 2dp) so the sheet foots exactly.
        Date cells -> real date objects (raw XML holds ISO DateTime strings;
        written as text they'd display as 2026-07-15T00:00:00.000)."""
        r = list(r)[:ncols] + [""] * max(0, ncols - len(r))
        for j in (amt_col, open_col):
            if j is not None and j < len(r):
                v = _amount(r[j])
                if v is not None:
                    r[j] = round(v, 2)
        for j in date_cols:
            if j < len(r):
                dv = _as_date(r[j])
                if dv is not None:
                    r[j] = dv
        return r

    kept_groups, kept_count = [], 0
    for vendor, rows in groups:
        match = [_display_row(r) for r in rows
                 if len(r) > sub_col and _norm(r[sub_col]) == want]
        if match:
            kept_groups.append((vendor, match))
            kept_count += len(match)
    if not kept_count:
        seen = sorted({str(r[sub_col]).strip() for _v, rows in groups for r in rows
                       if len(r) > sub_col and str(r[sub_col]).strip()})
        raise RuntimeError(f"NO_ROWS: 0 rows for subsidiary '{subsidiary}'. "
                           f"Subsidiaries present in this file: {seen[:25]}")

    def total_row(label, rows):
        """Recompute a totals row from the kept rows: Open Balance always;
        foreign Amount only when the group is single-currency (mixed
        currencies don't sum meaningfully — left blank, like honesty)."""
        t = [""] * ncols
        t[vendor_col] = label
        if open_col is not None:
            vals = [_amount(r[open_col]) for r in rows if len(r) > open_col]
            vals = [v for v in vals if v is not None]
            if vals:
                t[open_col] = round(sum(vals), 2)
        if amt_col is not None and cur_col is not None:
            curs = {str(r[cur_col]).strip() for r in rows
                    if len(r) > cur_col and str(r[cur_col]).strip()}
            if len(curs) == 1:
                vals = [_amount(r[amt_col]) for r in rows if len(r) > amt_col]
                vals = [v for v in vals if v is not None]
                if vals:
                    t[amt_col] = round(sum(vals), 2)
                    t[cur_col] = curs.pop()
        return t

    # Title block with the scope line rewritten to the subsidiary.
    title = [list(r) for r in grid[:hdr_i]]
    rewritten = False
    for r in title:
        for j, c in enumerate(r):
            if "consolidated" in _norm(c):
                r[j] = subsidiary
                rewritten = True
    if not rewritten and len(title) >= 2 and title[1]:
        j = next((j for j, c in enumerate(title[1]) if str(c).strip()), 0)
        title[1][j] = subsidiary
        rewritten = True

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    for r in title:
        ws.append(list(r))
    ws.append(header)
    group_totals = []
    all_rows = []
    for vendor, rows in kept_groups:
        if vendor:
            hdr_row = [""] * ncols
            hdr_row[vendor_col] = vendor
            ws.append(hdr_row)
        for r in rows:
            ws.append(r)
        # NetSuite writes 'Total - No Vendor' for the '- No Vendor -' group.
        clean_vendor = vendor.strip().strip("-").strip() if vendor else ""
        label = f"Total - {clean_vendor}" if clean_vendor else "Total - (no vendor)"
        trow = total_row(label, rows)
        ws.append(trow)
        if open_col is not None and trow[open_col] != "":
            group_totals.append(trow[open_col])
        all_rows.extend(rows)
    grand = total_row("Total", all_rows)
    # The grand total must FOOT against the displayed group totals (finance
    # will sum the column in Excel), so it is defined as their sum — not an
    # independent raw-row sum, which can drift by cents through per-group
    # rounding (seen live: 7089570.44 vs .42 on Wego Travel S.A.E).
    raw_grand = grand[open_col] if open_col is not None else ""
    if open_col is not None and group_totals:
        grand[open_col] = round(sum(group_totals), 2)
    ws.append(grand)

    validation = {"vendors_kept": len(kept_groups), "detail_rows": kept_count}
    if open_col is not None and grand[open_col] != "":
        validation["open_balance_total"] = grand[open_col]
        # Sanity: displayed grand vs independent raw-row sum, allowing the
        # accumulated per-group rounding (half a cent per group).
        tol = 0.005 * max(1, len(group_totals)) + 0.01
        drift = abs((raw_grand or 0) - grand[open_col])
        validation["totals_reconcile"] = drift <= tol
        validation["rounding_drift"] = round(drift, 4)
        if not validation["totals_reconcile"]:
            raise RuntimeError(f"VALIDATION_FAILED: raw-row sum {raw_grand} vs "
                               f"grand {grand[open_col]} drift {drift} exceeds "
                               f"tolerance {tol} — refusing to emit a bad file")

    # Display dates the way NetSuite does (DD/MM/YYYY) instead of ISO text.
    from openpyxl.utils import get_column_letter
    for j in date_cols:
        col_letter = get_column_letter(j + 1)
        for cell in ws[col_letter]:
            if hasattr(cell.value, "year"):
                cell.number_format = "DD/MM/YYYY"

    # Second sheet where Excel's Vendor/Total filters actually work: the grouped
    # layout leaves Vendor blank on detail rows, so filtering the Vendor column
    # shows "(Blanks)" and hides every transaction (Akansha 2026-07-30).
    flat_rows = 0
    try:
        flat = wb.create_sheet("Filterable")
        flat.append(header)
        for vendor, rows in kept_groups:
            for r in rows:
                out = list(r)[:ncols] + [""] * max(0, ncols - len(r))
                out[vendor_col] = vendor or out[vendor_col]
                flat.append(out)
                flat_rows += 1
        if flat.max_row > 1:
            flat.auto_filter.ref = flat.dimensions
            flat.freeze_panes = "A2"
        for j in date_cols:
            for cell in flat[get_column_letter(j + 1)]:
                if hasattr(cell.value, "year"):
                    cell.number_format = "DD/MM/YYYY"
    except Exception:
        flat_rows = 0

    if not out_path:
        base = os.path.splitext(src_path)[0]
        slug = re.sub(r"[^A-Za-z0-9]+", "_", subsidiary).strip("_")
        out_path = f"{base}__{slug}.xlsx"
    wb.save(out_path)
    return {"out_path": out_path, "data_rows": kept_count,
            "source_rows": len(data), "title_rewritten": rewritten,
            "validation": validation, "filterable_rows": flat_rows,
            "note": ("Vendor grouping preserved; per-vendor and grand totals "
                     "recomputed from the included rows only (Open Balance "
                     "always; foreign Amount only for single-currency groups). "
                     "Vendors with no rows for this subsidiary are omitted.")}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: filter_subsidiary.py <report.xls[x]> <Subsidiary Name> [out.xlsx]")
    r = filter_report(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(f"OK {r['out_path']} — {r['data_rows']}/{r['source_rows']} rows, "
          f"title rewritten: {r['title_rewritten']}")
