# LCC Suppliers — Action Keys & Trigger Phrases

Authoritative supplier list for the reconciliation skill. The `Action Key` column is what goes into the JSON `action` field — it must match exactly an entry in the server's `suppliers.json`.

If the user mentions a supplier not in this table, reply:
> Sorry, **[supplier]** isn't configured yet. Available suppliers: Jazeera, AJet, AL Madar, AirBlue, AirIndia Express, Air Arabia, AkasaAir, Atlas, Belair (Travel/INR/SGD), Bingtrip, Blue Horizon, Brightsun, CIT Malaysia, Chamwings (AE/INT/OM), Citizenplane, Dadabhai, Dnata (BH/Gold/OM), FitsAir, FlyDubai, Flyarystan, Flydeal, Flyin (EGP/EG/SAR), Flynas, Holiday Tours, Hong Ngoc, Indigo, Jordan Airlines, Kanoo (SAR/Egypt/AED/BHD), LetsFly, Monde (CAD/USD), Moonline, Nesma, NokAir, Quality Aviation, Regency, Salamair, Samad, SereneAir, SpiceJet, TSY, Tidesquare, TransNusa, Trans Arabian, Transavia, UR Airline, Wonder.

---

## Full table — 58 LCC suppliers

| # | Supplier | Action Key | Trigger Phrases |
|---|---|---|---|
| 1 | Jazeera | `jazeera` | jazeera, jaz, jaz reco |
| 2 | AJet | `ajet` | ajet |
| 3 | AL Madar Travel | `al_madar` | al madar, madar |
| 4 | AirBlue | `airblue` | airblue, air blue |
| 5 | AirIndia Express | `airindia_express` | airindia express, air india express |
| 6 | Air Arabia | `air_arabia` | air arabia, airarabia |
| 7 | AkasaAir | `akasaair` | akasa, akasaair |
| 8 | Atlas LowCost | `atlas_lc` | atlas, atlas lc |
| 9 | Belair Travel | `belair_travel` | belair travel |
| 10 | Belair INR | `belair_inr` | belair inr |
| 11 | Belair SGD | `belair_sgd` | belair sgd |
| 12 | Bingtrip | `bingtrip` | bingtrip |
| 13 | Blue Horizon | `blue_horizon` | blue horizon |
| 14 | Brightsun | `brightsun` | brightsun |
| 15 | CIT Malaysia | `cit_malaysia` | cit malaysia |
| 16 | Chamwings AE | `chamwings_ae` | chamwings ae |
| 17 | Chamwings INT | `chamwings_int` | chamwings int |
| 18 | Chamwings OM | `chamwings_om` | chamwings om |
| 19 | Citizenplane | `citizenplane` | citizenplane |
| 20 | Dadabhai KWD | `dadabhai_kwd` | dadabhai |
| 21 | Dnata BH | `dnata_bh` | dnata bh |
| 22 | Dnata Gold | `dnata_gold` | dnata gold |
| 23 | Dnata OM | `dnata_om` | dnata om |
| 24 | FitsAir | `fitsair` | fitsair |
| 25 | FlyDubai | `flydubai` | flydubai |
| 26 | Flyarystan | `flyarystan` | flyarystan |
| 27 | Flydeal LowCost | `flydeal_lc` | flydeal |
| 28 | Flyin EGP | `flyin_egp` | flyin egp |
| 29 | Flyin EG LowCost | `flyin_eg_lc` | flyin eg lc |
| 30 | Flyin SAR | `flyin_sar` | flyin sar |
| 31 | Flynas LowCost | `flynas_lc` | flynas |
| 32 | Holiday Tours | `holiday_tours` | holiday tours |
| 33 | Hong Ngoc | `hong_ngoc` | hong ngoc |
| 34 | Indigo | `indigo` | indigo |
| 35 | Jordan Airlines | `jordan_airlines` | jordan airlines |
| 36 | Kanoo SAR | `kanoo_sar` | kanoo sar |
| 37 | Kanoo Travel Egypt | `kanoo_egypt` | kanoo egypt |
| 38 | Kanoo AED | `kanoo_aed` | kanoo aed |
| 39 | Kanoo BHD | `kanoo_bhd` | kanoo bhd |
| 40 | LetsFly | `letsfly` | letsfly |
| 41 | Monde CAD | `monde_cad` | monde cad |
| 42 | Monde USD | `monde_usd` | monde usd |
| 43 | Moonline | `moonline` | moonline |
| 44 | Nesma | `nesma` | nesma |
| 45 | NokAir | `nokair` | nokair |
| 46 | Quality Aviation | `quality_aviation` | quality aviation |
| 47 | Regency Travels | `regency` | regency |
| 48 | Salamair | `salamair` | salamair |
| 49 | Samad Tours | `samad_tours` | samad tours |
| 50 | SereneAir | `sereneair` | sereneair |
| 51 | SpiceJet | `spicejet` | spicejet |
| 52 | TSY Travel | `tsy_travel` | tsy travel |
| 53 | Tidesquare | `tidesquare` | tidesquare |
| 54 | TransNusa | `transnusa` | transnusa |
| 55 | Trans Arabian | `trans_arabian` | trans arabian |
| 56 | Transavia | `transavia` | transavia |
| 57 | UR Airline | `ur_airline` | ur airline |
| 58 | Wonder EGP | `wonder_egp` | wonder egp |

---

## Disambiguation rules

When a user's wording is ambiguous (e.g., "Belair" without a currency), ask once:
> Belair has three configs: Travel, INR, SGD. Which one?

When a user names a multi-currency supplier without specifying:
- Belair → ask Travel / INR / SGD
- Chamwings → ask AE / INT / OM
- Dnata → ask BH / Gold / OM
- Kanoo → ask SAR / Egypt / AED / BHD
- Monde → ask CAD / USD
- Flyin → ask EGP / EG LowCost / SAR

Do not guess; ask once.

---

## Source of truth

The server's `suppliers.json` (in the AlphaBot repo at `rpa/openclaw/Finance/Supplier/LCC/suppliers.json`) is the authoritative config. If the two diverge, server wins. Update this file when `suppliers.json` changes.
