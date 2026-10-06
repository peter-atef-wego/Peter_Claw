# references/dimension_aliases.md

Exact alias dictionaries and resolver algorithms for the NetSuite Champion's slowly-changing dimensions: subsidiaries, accounts, periods, currencies, locations, departments, classes.

When a user says "Wego SG" or "input tax KSA" or "May 2026", the bot must translate to a NetSuite internal id **before** building SuiteQL or write bodies. This file is the canonical mapping.

---

## 1. Subsidiaries

The 8 Wego entities and every alias the finance team uses.

```
Wego Pte Ltd            ← wego sg, wego singapore, sg, wegopte, wego pte, hq, parent, singapore
Wego FZ-LLC             ← wego uae, wego fz, fz, fz-llc, fzllc, uae, dubai
Wego Middle East        ← wego me, middle east, wegome
Wego Saudi and Tourism  ← wego ksa, ksa, saudi, wegosaudi, riyadh
Wego Travel and Tourism ← wego pakistan, pakistan, pk
Wego Travel S.A.E       ← wego egypt, egypt, eg, sae
ShopCash FZ-LLC         ← shopcash, sc, shopcash fz
Wego India Pvt Ltd      ← wego india, india, in, wego in
```

Lookups are case-insensitive. The bot does NOT have to hard-code internal IDs — always fetch from NetSuite via SuiteQL at the start of a session:

```sql
SELECT id, name, country, currency, isinactive
FROM   subsidiary
```

Cache the result for the thread. Map alias → `name` → `id`.

### Resolver algorithm (4 fallback levels)

```
resolve_subsidiary(input):
    needle = input.strip().lower()
    rows   = subsidiaries() from cache

    # 1. Internal-id match
    if needle.isdigit():
        for r in rows:
            if str(r.id) == needle: return r

    # 2. Exact name match
    for r in rows:
        if r.name.lower() == needle: return r

    # 3. Alias map (above)
    for canonical, aliases in SUBSIDIARY_ALIASES:
        if needle in aliases or needle == canonical.lower():
            for r in rows:
                if r.name.lower() == canonical.lower(): return r

    # 4. Substring fallback
    for r in rows:
        if needle in r.name.lower() or r.name.lower() in needle:
            return r

    return None
```

If the resolver returns `None` AND the request needs a subsidiary, ask the user. **Don't auto-pick.**

### Disambiguation: "Wego" alone

If the user says just "Wego", that matches 7 of 8 entities (every one except ShopCash). Always ask:

> Which subsidiary — Wego Pte Ltd, Wego FZ-LLC, Wego Middle East, Wego Saudi, Wego PK, Wego EG, ShopCash, or Wego India?

---

## 2. GL accounts

Per-account aliases for the most-asked accounts. Add new entries here when finance starts referring to an account by a nickname.

```
1401015 ← input tax ksa, ksa input tax, ksa input
26032   ← output tax ksa, ksa output tax, ksa output
26081   ← adjustment tax ksa, ksa adjustment
```

(More aliases will accrue here as we observe usage in `#netsuite_ap`, `#netsuite_ar`, `#netsuite_gl_and_reporting`, `#netsuite_tax`.)

Always confirm the real `acctnumber` and `id` by querying:

```sql
SELECT id, acctnumber,
       accountsearchdisplayname AS acctname,
       accttype, subsidiary, isinactive
FROM   account
WHERE  isinactive = 'F'
```

### Resolver algorithm

```
resolve_account(input):
    needle = input.strip().lower()
    rows   = accounts() from cache

    # 1. Digit input → match acctnumber or internal id
    if needle.isdigit():
        for r in rows:
            if r.acctnumber == needle or str(r.id) == needle:
                return r

    # 2. Exact acctname match
    for r in rows:
        if r.acctname.lower() == needle: return r

    # 3. Alias map
    for canonical_acctnumber, aliases in ACCOUNT_ALIASES:
        if needle in aliases:
            for r in rows:
                if r.acctnumber == canonical_acctnumber: return r

    # 4. Substring fallback on acctname
    for r in rows:
        if needle in r.acctname.lower(): return r

    return None
```

### Account-number ranges (Wego convention)

| Range | Type | Examples |
|---|---|---|
| `1xxx` | Bank, AR, prepayments | `1000` cash, `1200` AR control, `1401015` Input Tax KSA |
| `2xxx` | AP, accruals, tax payables | `2010` AP control, `2200` VAT payable, `26032` Output Tax KSA, `26081` Adjustment Tax KSA |
| `3xxx` | Equity, retained earnings | `3000` share capital |
| `4xxx` | Revenue | `4100` Hotel commission, `4200` Flight commission |
| `5xxx` | Cost of revenue / direct cost | |
| `6xxx`–`7xxx` | OpEx | |
| `8xxx` | Other income, FX gain/loss | `8900` realised FX |
| `9xxx` | Tax expense, intercompany | |

These ranges are guidance, not authoritative. Always look up the real account in NetSuite before using it in a filter or write body.

---

## 3. Accounting periods

Periods are named `<Month> <Year>` in NetSuite (e.g. `May 2026`) — and **also** stored with `MMM-YYYY` short form via `periodname` patterns. Quarters: `Q1 2026`. Years: `2026`.

### Resolver algorithm

```
resolve_period(input):
    needle = input.strip()
    rows   = periods() from cache  -- SELECT … FROM accountingperiod ORDER BY startdate DESC

    # 1. Internal-id match
    if needle.isdigit():
        for r in rows:
            if str(r.id) == needle: return r

    # 2. Exact periodname match (case-insensitive)
    for r in rows:
        if r.periodname.lower() == needle.lower(): return r

    # 3. YYYY-MM form → match by startdate prefix
    if len(needle) == 7 and needle[4] == '-':
        for r in rows:
            if str(r.startdate).startswith(needle): return r

    # 4. Relative phrase → use date_phrase parser (see suiteql_recipes.md §7)
    #    e.g. 'this month' → (2026-05-01, 2026-05-31) → find period with startdate = 2026-05-01
    return None
```

### Period attributes to check

| Field | What it means |
|---|---|
| `id` | Internal id (use in `t.postingperiod = X`) |
| `periodname` | Display name (e.g. `May 2026`) |
| `startdate`, `enddate` | Inclusive date range |
| `closed` (`T`/`F`) | Soft close — adjustments still allowed when `closed=T` and `alllocked=F` |
| `alllocked` (`T`/`F`) | Hard close — no posting allowed |
| `isadjust` (`T`/`F`) | Adjustment period (between fiscal periods) |
| `isquarter` (`T`/`F`) | True if this row is a quarter aggregate |
| `isyear` (`T`/`F`) | True if this row is a year aggregate |

**For posting filters**, you want monthly periods only:

```sql
WHERE isyear='F' AND isquarter='F' AND isadjust='F'
```

**Before any GL write**, validate the target period is OPEN — see [`governance.md`](./governance.md) §3.

---

## 4. Currencies

```sql
SELECT id, name, symbol, exchangerate, isinactive
FROM   currency
WHERE  isinactive = 'F'
```

Resolve by ISO code (`symbol`), name, or internal id. Common at Wego: `SGD` (base), `USD`, `AED`, `SAR`, `PKR`, `EGP`, `INR`, `MYR`, `EUR`, `GBP`, `THB`, `IDR`.

### Per-currency display rules

| Currency | Decimals | Example |
|---|---|---|
| `JPY`, `KRW`, `VND` | 0 | `JPY 1,234,567` |
| Everything else | 2 | `SGD 1,234,567.89` |

---

## 5. Locations / departments / classes (segments)

NetSuite's three reporting segments. Cache the same way as the rest:

```sql
SELECT id, name, subsidiary, isinactive FROM location       WHERE isinactive='F'
SELECT id, name, subsidiary, isinactive FROM department     WHERE isinactive='F'
SELECT id, name, subsidiary, isinactive FROM classification WHERE isinactive='F'
```

Class is named `classification` in SuiteQL (not `class`, which is reserved).

When a query needs to be scoped to a segment ("show me OTA revenue by department"), join on the segment id at the transactionLine level:

```sql
JOIN transactionLine tl ON tl.transaction = t.id
WHERE  tl.department = :dept_id
```

---

## 6. Vendors / customers

No alias map — fuzzy-match by `companyname` at query time:

```sql
SELECT id, companyname, entityid, currency
FROM   vendor              -- or customer
WHERE  isinactive = 'F'
  AND  UPPER(companyname) LIKE UPPER('%alias%')
FETCH FIRST 10 ROWS ONLY
```

- 0 results → "I don't see a vendor matching '<alias>' in <scope>. Could you check the spelling?"
- 1 result → use it.
- >1 results → list them and ask which one. **Don't auto-pick.**

Use `entityid` (the human-friendly internal code) in display alongside `companyname` to help the user disambiguate.

---

## 7. Cache TTL and invalidation

| Dimension | Recommended cache TTL |
|---|---|
| Subsidiaries | 10 min |
| Accounts | 10 min |
| Periods | 10 min (or invalidate after a known close event) |
| Currencies | 10 min |
| Locations / Departments / Classes | 10 min |
| Vendors / Customers | **no cache** — fuzzy-match per query |

In direct-MCP usage, the cache lives inside the thread context. If you've already resolved a subsidiary in this thread, reuse the id; don't re-query.

If you suspect stale cache (user says "I just added Wego XYZ"), explicitly re-query — don't trust the cache.

---

## 8. Adding new aliases

When the finance team starts calling something by a new short name:

1. Verify the canonical name + id with a SuiteQL lookup.
2. Add the alias to the appropriate table in this file (under §1, §2, or open a new section).
3. Append a one-line entry to `MEMORY.md` Section B with the date, alias, and where you saw it used.

Aliases should be lowercase, no punctuation, and accept short forms ("FZ", "KSA", "SG") — the resolver does case-insensitive matching.

---

## 9. Tax codes

Tax codes in NetSuite live in two related tables depending on transaction side:

- **`salestaxitem`** — used on AR transactions (`invoice`, `creditmemo`, `customerpayment`).
- **`purchasetaxitem`** — used on AP transactions (`vendorbill`, `vendorcredit`, `vendorpayment`).

Both share `itemid` (the code), `description`, `rate`, `subsidiary`, `country`, `isinactive`. Some Wego setups expose them under the unified `taxitem` view — try that first, fall back to the specific tables.

### ⚠️ Compound naming — read this first

NetSuite tax-code `itemid` values are **compound**: `<TaxRegime>:<TaxCode>`. Finance users in the CSV write only the `<TaxCode>` part (after the colon). Examples from Wego sandbox:

| CSV column says | Actual NetSuite `itemid` | Subsidiary it belongs to |
|---|---|---|
| `ZR-SG 0%` | `GST_SG:ZR-SG 0%` | Wego Pte Ltd (Singapore) |
| `SR-SG 9%` | `GST_SG:SR-SG 9%` | Wego Pte Ltd |
| `OS-SG` | `GST_SG:OS-SG` | Wego Pte Ltd |
| `(any)` | `GST_SG:UNDEF-SG` | placeholder "undefined" code — **NEVER match this as a fallback** |
| `SR-AE 5%` | `VAT_AE:SR-AE 5%` | Wego FZ-LLC, Wego Middle East, ShopCash |
| `ZR-AE 0%` | `VAT_AE:ZR-AE 0%` | UAE subs |
| `OS-AE` | `VAT_AE:OS-AE` | UAE subs |
| `SR-SA 15%` | `VAT_SA:SR-SA 15%` | Wego Saudi |
| `IGST-IN 18%` | `GST_IN:IGST-IN 18%` | Wego India |
| `CGST-IN 9%` / `SGST-IN 9%` | `GST_IN:CGST-IN 9%` / `GST_IN:SGST-IN 9%` | Wego India |
| `EG-VAT 14%` | `VAT_EG:EG-VAT 14%` | Wego Travel S.A.E |
| `PK-GST 17%` | `GST_PK:PK-GST 17%` | Wego Travel and Tourism (Pakistan) |

### Subsidiary → Tax-regime prefix

The bot resolves the subsidiary first, then knows which regime prefix to search:

| Subsidiary | Tax-regime prefix |
|---|---|
| Wego Pte Ltd | `GST_SG` |
| Wego FZ-LLC | `VAT_AE` |
| Wego Middle East | `VAT_AE` |
| Wego Saudi and Tourism | `VAT_SA` |
| Wego Travel and Tourism (Pakistan) | `GST_PK` |
| Wego Travel S.A.E (Egypt) | `VAT_EG` |
| ShopCash FZ-LLC | `VAT_AE` |
| Wego India Pvt Ltd | `GST_IN` |

### Resolver algorithm — non-negotiable

When the CSV says `ZR-SG 0%` and the bill's subsidiary is `Wego Pte Ltd`:

```
1. Resolve subsidiary → get the regime prefix:
     Wego Pte Ltd → GST_SG

2. Search `purchasetaxitem` (or `salestaxitem` for AR) for an exact compound match:
     SELECT id, itemid, rate
     FROM   purchasetaxitem
     WHERE  itemid = 'GST_SG:ZR-SG 0%'      -- compose: <prefix>:<csv_value>
       AND  subsidiary = :subsid_id
       AND  isinactive = 'F'

3. If exactly one row → USE IT. Done.

4. If zero rows → try `itemid LIKE :prefix || ':%' || :csv_value || '%'`
   to allow whitespace / formatting variants:
     SELECT id, itemid, rate
     FROM   purchasetaxitem
     WHERE  itemid LIKE 'GST_SG:%ZR-SG%'
       AND  subsidiary = :subsid_id
       AND  isinactive = 'F'

5. If multiple rows from step 4 → list candidates and ask once (per §5.9, then stop).

6. NEVER fall back to `UNDEF-`. Any `itemid` containing `UNDEF` is a placeholder
   meaning "undefined / not yet mapped". If the only match is an UNDEF code,
   surface that as a real blocker:
     "No usable tax code matching 'ZR-SG 0%' for subsidiary Wego Pte Ltd.
      The only candidate (`GST_SG:UNDEF-SG`) is a placeholder. Akansha needs to
      configure the real ZR-SG 0% code, or you need to point me at a different
      code id. Stopping."
```

### Why the 2026-05-19 incident happened

The bot searched `purchasetaxitem` for something containing `ZR-SG 0%`, didn't constrain by the `GST_SG:` prefix, didn't filter `UNDEF` out, and picked `GST_SG:UNDEF-SG` as a fallback when the real `GST_SG:ZR-SG 0%` was in the same list. **The two compound rules above (subsidiary → regime prefix, never-match-UNDEF) fix this class of mistake.**

### REST field on the line

For `vendorbill` and `vendorcredit` expense lines, use `taxcode` (not `tax_code`, not `taxitem`):

```json
{
  "expense": {"items": [
    {
      "account":    {"id": "<account_id>"},
      "amount":     100.00,
      "memo":       "…",
      "department": {"id": "<dept_id>"},
      "taxcode":    {"id": "<purchasetaxitem_id>"},
      "cseg_msa_bu_code": {"id": "<bu_code_id>"}
    }
  ]}
}
```

For `invoice` and `creditmemo` item lines, use `taxcode` with `salestaxitem_id`.

**Tax codes are subsidiary-scoped.** A tax code id valid for Wego Pte Ltd is NOT valid for Wego FZ-LLC. Always include the `subsidiary = :subsid_id` filter when resolving. If a finance user gives you a tax-code name like `ZR-SG 0%` but the target subsidiary isn't Singapore, **stop and ask** — there's a mismatch.

### Common tax-code aliases at Wego (the suffix the user types)

```
ZR-SG 0%   ← zero rated sg, zr sg, sg zero rated, zr-sg
SR-SG 9%   ← standard rated sg, sr sg, gst, sg gst, sg 9, gst sg
OS-SG      ← out of scope sg, os sg
OS-AE      ← out of scope ae, out of scope uae, os ae
ZR-AE 0%   ← zero rated ae, zr ae, uae zero
SR-AE 5%   ← uae vat, ae vat, sr ae, 5%
SR-SA 15%  ← ksa vat, sr sa, 15% sa, saudi vat
IGST-IN 18% ← igst, india igst, 18 india
CGST-IN 9% ← cgst, india cgst
SGST-IN 9% ← sgst, india sgst
EG-VAT 14% ← egypt vat, eg vat
PK-GST 17% ← pakistan gst, pk gst
```

Bot composes the full `itemid` to search: `<regime_prefix>:<resolved_suffix>`. E.g. user says "GST SG" → resolver picks `SR-SG 9%` suffix → full search target `GST_SG:SR-SG 9%`.

### What the bot must always do for tax codes on writes

1. **Resolve the subsidiary first** — it determines the regime prefix.
2. **Look up the regime prefix** from the table above (`Wego Pte Ltd → GST_SG`, etc.).
3. **Compose the full compound `itemid`** as `<prefix>:<csv_value>` and search by exact `itemid =` first.
4. **If no exact match**, fall back to `itemid LIKE '<prefix>:%<csv_value>%'`.
5. **Filter out any UNDEF placeholder** — never match `*UNDEF*` as a real tax code.
6. **Pick the right table by transaction side** — `purchasetaxitem` for AP, `salestaxitem` for AR.
7. **Include `taxcode: {"id": "<id>"}` in every expense/item line in the body** — even for zero-rated codes. NetSuite needs the id.
8. **Surface the resolved tax code in the §5.8 opener and in the final summary** so the user can verify before / after.

If the only candidates are UNDEF placeholders or there's no match, **stop and surface** per §5.9 — don't create the bill with a wrong tax code. UNDEF codes typically don't post correctly and can trigger downstream tax-report errors finance has to clean up.

---

## BU Code (Custom Segment)

**This is NOT the department or classification table.** BU Code is a custom segment in NetSuite.

**SuiteQL table:** `customrecord_cseg_msa_bu_code`. Resolution is **pure dynamic** — `_resolve_bu_code` queries this table on every call and returns the live id. **No hardcoded ID fallback by design** — on 2026-05-20 a hardcoded map silently returned id 13 when NetSuite had reassigned the BU to id 11, posting the bill with wrong data and no error. A hard `DIMENSION_RESOLUTION_FAILED` is always preferable to silent wrong IDs in finance records.

**REST field name on expense / line bodies:** `cseg_msa_bu_code` — the only correct name. Verified 2026-05-20 on bill `1436791`. Not `custcol_wego_bu_code`, not `class`, not `classification`, not `bu_code` (CSV alias only). See CLAUDE.md §5.10 for the hard rule.

**ID-collision warning:** internal ids are scoped per table, not globally unique. On 2026-05-20 the bot reused BU id `13` on the `class` field — NetSuite read it as classification id 13 ("Gift Cards") and posted the bill with the wrong Product Segment. A resolved id must only be written to the field tied to the table it was read from.

**If `_resolve_bu_code` fails:**
- SuiteQL error (e.g. role can't read `customrecord_cseg_msa_bu_code`) → returns `_error` with a message naming Akansha as the unblocker.
- No match found → returns None; caller surfaces `DIMENSION_RESOLUTION_FAILED` with the BU value and the live-table source.
- Multiple matches → returns `_ambiguous` with candidate list; caller asks the user to pick.

**Never:** substitute a hardcoded id, guess, or post the bill with a missing BU.

**DO NOT confuse with:**
- Department (separate table, separate field)
- Classification/Class (separate table, separate field)
- Product Segment (separate custom list)

---

## CSV Column Name → NetSuite REST Field Mapping

When reading CSV files for bill/vendor creation, map these column headers to their correct REST API field names:

| CSV Column Header (case-insensitive) | NetSuite REST Field Name |
|---|---|
| `BU Code` / `bu_code` / `BU` / `bu code` | `cseg_msa_bu_code` |
| `Department` / `department` / `dept` | `department` |
| `Subsidiary` / `subsidiary` / `sub` | `subsidiary` |
| `Currency` / `currency` / `ccy` | `currency` |
| `Expense Account` / `expense_account` / `account` | `account` |
| `Tax Code` / `tax_code` / `taxcode` | `taxcode` |
| `Vendor` / `vendor_entity_id` / `entity` | `entity` |

**CRITICAL:** When CSV has `BU Code` or `bu_code` as column header, the agent MUST use field `cseg_msa_bu_code` on expense lines. Do NOT:
- Look up "BU Code" in the department table
- Create a new classification
- Use `classification` field
- Use `class` field
- Use `custcol_wego_bu_code` (verified non-existent 2026-05-20)
- Use the resolved BU id on any other field (id-collision risk — see ID-collision warning above)

Just map the value to `cseg_msa_bu_code` with `{"id": "<resolved_id>"}`. **And** when hand-rolling a body, only assign that id to that field and nowhere else.
