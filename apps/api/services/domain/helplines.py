"""
Emergency and helpline directory: national numbers per country plus
city-specific lines (non-emergency police, city services, utilities,
transit police, local health lines) for curated cities.

Curated by hand from official public sources; every entry carries a
category so the UI can group them. Emergency numbers ONLY ever come from
this file. For places without curated city lines, the caller may add
AI-compiled *non-emergency* city services, clearly flagged (see
local_city_services in care.py).

Numbers are stored as dialable strings; `display` keeps the local format.
"""
from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class Line(TypedDict, total=False):
    name: str
    number: str          # dialable (digits, + and # only)
    display: str         # how locals write it
    category: str        # emergency | police | medical | fire | mental_health | women_children | poison | city | utilities | transit | tourist | other
    note: str
    sms: bool
    url: str


def L(name: str, number: str, category: str, *, display: Optional[str] = None, note: str = "",
      sms: bool = False, url: str = "") -> Line:
    line: Line = {"name": name, "number": number, "display": display or number, "category": category}
    if note:
        line["note"] = note
    if sms:
        line["sms"] = True
    if url:
        line["url"] = url
    return line


# ── National directories ───────────────────────────────────────────────────

COUNTRY: Dict[str, List[Line]] = {
    "US": [
        L("Emergency (police, fire, ambulance)", "911", "emergency"),
        L("988 Suicide & Crisis Lifeline", "988", "mental_health", note="Call or text, 24/7", sms=True, url="https://988lifeline.org"),
        L("Poison Control", "18002221222", "poison", display="1-800-222-1222", url="https://poisonhelp.hrsa.gov"),
        L("Crisis Text Line", "741741", "mental_health", note="Text HOME", sms=True, url="https://www.crisistextline.org"),
        L("National Domestic Violence Hotline", "18007997233", "women_children", display="1-800-799-7233", url="https://www.thehotline.org"),
        L("RAINN Sexual Assault Hotline", "18006564673", "women_children", display="1-800-656-4673", url="https://www.rainn.org"),
        L("SAMHSA Helpline (substance use)", "18006624357", "mental_health", display="1-800-662-4357"),
        L("211 Community services", "211", "city", note="Housing, food, utilities help"),
    ],
    "CA": [
        L("Emergency (police, fire, ambulance)", "911", "emergency"),
        L("9-8-8 Suicide Crisis Helpline", "988", "mental_health", note="Call or text", sms=True),
        L("Health advice line (most provinces)", "811", "medical"),
        L("211 Community services", "211", "city"),
    ],
    "GB": [
        L("Emergency (police, fire, ambulance)", "999", "emergency", note="112 also works"),
        L("NHS 111 (urgent, non-emergency medical)", "111", "medical", url="https://111.nhs.uk"),
        L("Police non-emergency", "101", "police"),
        L("Samaritans", "116123", "mental_health", display="116 123", note="Free, 24/7"),
        L("Power cut", "105", "utilities"),
    ],
    "IE": [
        L("Emergency", "112", "emergency", note="999 also works"),
        L("Samaritans", "116123", "mental_health", display="116 123"),
    ],
    "AU": [
        L("Emergency (police, fire, ambulance)", "000", "emergency", note="112 works from mobiles"),
        L("Police Assistance Line (non-urgent)", "131444", "police", display="131 444"),
        L("Healthdirect (nurse advice)", "1800022222", "medical", display="1800 022 222"),
        L("Poisons Information", "131126", "poison", display="13 11 26"),
        L("Lifeline (crisis support)", "131114", "mental_health", display="13 11 14"),
        L("SES (floods, storms)", "132500", "other", display="132 500"),
    ],
    "NZ": [
        L("Emergency", "111", "emergency"),
        L("Police non-emergency", "105", "police"),
        L("Healthline", "0800611116", "medical", display="0800 611 116"),
        L("Need to talk? (mental health)", "1737", "mental_health", note="Call or text", sms=True),
    ],
    "IN": [
        L("National emergency", "112", "emergency"),
        L("Police", "100", "police"),
        L("Fire", "101", "fire"),
        L("Ambulance", "108", "medical", note="Emergency ambulance in most states"),
        L("Ambulance (national / maternity)", "102", "medical"),
        L("Women helpline (police)", "1091", "women_children"),
        L("Women helpline", "181", "women_children"),
        L("Childline", "1098", "women_children"),
        L("Senior citizens (Elderline)", "14567", "other"),
        L("Tele-MANAS mental health", "14416", "mental_health", note="Free, 24/7, many languages"),
        L("Cyber crime", "1930", "police", url="https://cybercrime.gov.in"),
        L("Tourist helpline", "1363", "tourist", note="Multilingual"),
        L("Highway emergency", "1033", "other"),
    ],
    "DE": [
        L("Police", "110", "police"),
        L("Fire & ambulance", "112", "emergency"),
        L("Medical on-call (non-emergency)", "116117", "medical", display="116 117"),
        L("TelefonSeelsorge (crisis)", "08001110111", "mental_health", display="0800 111 0 111"),
    ],
    "FR": [
        L("European emergency", "112", "emergency"),
        L("SAMU (medical)", "15", "medical"),
        L("Police", "17", "police"),
        L("Fire", "18", "fire"),
        L("Emergency by SMS (deaf / hard of hearing)", "114", "emergency", sms=True),
        L("Suicide prevention", "3114", "mental_health"),
    ],
    "ES": [
        L("Emergency", "112", "emergency"),
        L("National Police", "091", "police"),
        L("Suicide & crisis line", "024", "mental_health"),
    ],
    "IT": [
        L("Emergency", "112", "emergency"),
        L("Medical emergency", "118", "medical"),
        L("Police", "113", "police"),
        L("Fire", "115", "fire"),
    ],
    "IS": [
        L("Emergency", "112", "emergency"),
        L("Health advice (Heilsuvera)", "1700", "medical"),
        L("Red Cross helpline", "1717", "mental_health"),
    ],
    "FO": [L("Emergency", "112", "emergency")],
    "JP": [
        L("Police", "110", "police"),
        L("Fire & ambulance", "119", "emergency"),
        L("Japan Visitor Hotline (English, 24/7)", "+815038162787", "tourist", display="050-3816-2787"),
    ],
    "ID": [
        L("Emergency", "112", "emergency"),
        L("Police", "110", "police"),
        L("Ambulance", "119", "medical"),
        L("Fire", "113", "fire"),
    ],
    "KE": [
        L("Emergency", "999", "emergency", note="112 also works"),
        L("Gender-based violence helpline", "1195", "women_children"),
        L("Kenya Red Cross", "1199", "medical"),
    ],
    "SG": [
        L("Police", "999", "police"),
        L("Ambulance & fire", "995", "emergency"),
        L("Non-emergency ambulance", "1777", "medical"),
        L("Samaritans of Singapore", "1767", "mental_health", display="1-767"),
    ],
    "AE": [
        L("Police", "999", "police"),
        L("Ambulance", "998", "medical"),
        L("Fire", "997", "fire"),
    ],
}

EU_112 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "GR", "HU", "LV", "LT", "LU", "MT",
          "NL", "PL", "PT", "RO", "SK", "SI", "SE", "NO", "CH"}

# ── City overlays (lowercase city name → lines) ────────────────────────────

CITY: Dict[str, Dict[str, List[Line]]] = {
    "US": {
        "boston": [
            L("BOS:311 city services", "6176354500", "city", display="311 or 617-635-4500", url="https://www.boston.gov/311"),
            L("Boston Police (non-emergency)", "6173434911", "police", display="617-343-4911"),
            L("MBTA Transit Police", "6172221212", "transit", display="617-222-1212"),
            L("Massachusetts Behavioral Health Help Line", "8337732445", "mental_health", display="833-773-2445", note="24/7, free"),
            L("Massachusetts General Hospital", "6177262000", "medical", display="617-726-2000"),
            L("Mass 211 (state services)", "211", "city"),
        ],
        "new york": [
            L("NYC 311", "2126399675", "city", display="311 or 212-639-9675", url="https://portal.311.nyc.gov"),
            L("NYC 988 / NYC Well", "988", "mental_health", note="Call, text or chat"),
        ],
        "san francisco": [
            L("SF311 city services", "4157012311", "city", display="311 or 415-701-2311", url="https://sf311.org"),
            L("SFPD (non-emergency)", "4155530123", "police", display="415-553-0123"),
        ],
    },
    "IN": {
        "chennai": [
            L("Greater Chennai Corporation helpline", "1913", "city", url="https://chennaicorporation.gov.in"),
            L("Tamil Nadu health helpline", "104", "medical"),
            L("TANGEDCO electricity complaints (Minnagam)", "9498794987", "utilities", display="94987 94987"),
            L("Chennai Metro Water complaints", "04445674567", "utilities", display="044-4567 4567"),
        ],
        "bengaluru": [
            L("BBMP city helpline", "1533", "city"),
        ],
        "mumbai": [
            L("BMC disaster & civic helpline", "1916", "city"),
        ],
    },
}
CITY_ALIASES = {"bangalore": "bengaluru", "bombay": "mumbai", "madras": "chennai", "nyc": "new york",
                "new york city": "new york", "sf": "san francisco"}


def directory(country_code: Optional[str], city: Optional[str]) -> Dict[str, object]:
    """National + city lines for the place, emergency first. Never empty:
    unknown countries get 112 with a 'confirm locally' note."""
    cc = (country_code or "").upper()
    national = list(COUNTRY.get(cc, []))
    curated = bool(national)
    if not national:
        note = ("112 connects to emergency services across the EU." if cc in EU_112
                else "112 works on most mobile phones worldwide. Confirm the local number when you arrive.")
        national = [L("Emergency", "112", "emergency", note=note)]
    key = (city or "").strip().lower()
    key = CITY_ALIASES.get(key, key)
    city_lines = list(CITY.get(cc, {}).get(key, []))
    primary = next((l for l in national if l["category"] == "emergency"), national[0])
    return {
        "primary": primary,
        "national": national,
        "city": city_lines,
        "curated_country": curated,
        "curated_city": bool(city_lines),
    }
