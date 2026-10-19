"""
Small, stable per-country facts: currency and emergency numbers.

Emergency numbers are the commonly published primary numbers. They're shown
with a "verify locally" note; 112 works on mobile phones across the EU and
in many other countries, so it's the fallback.
"""
from __future__ import annotations

from typing import Dict, Optional

CURRENCY: Dict[str, str] = {
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL", "AR": "ARS", "CL": "CLP", "CO": "COP", "PE": "PEN",
    "GB": "GBP", "IE": "EUR", "FR": "EUR", "DE": "EUR", "ES": "EUR", "PT": "EUR", "IT": "EUR", "NL": "EUR",
    "BE": "EUR", "AT": "EUR", "FI": "EUR", "GR": "EUR", "LU": "EUR", "MT": "EUR", "CY": "EUR", "SK": "EUR",
    "SI": "EUR", "EE": "EUR", "LV": "EUR", "LT": "EUR", "HR": "EUR", "CH": "CHF", "NO": "NOK", "SE": "SEK",
    "DK": "DKK", "FO": "DKK", "GL": "DKK", "IS": "ISK", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "RO": "RON",
    "BG": "BGN", "TR": "TRY", "IL": "ILS", "AE": "AED", "SA": "SAR", "QA": "QAR", "EG": "EGP", "MA": "MAD",
    "ZA": "ZAR", "KE": "KES", "NG": "NGN", "GH": "GHS", "TZ": "TZS", "UG": "UGX", "ET": "ETB", "RW": "RWF",
    "IN": "INR", "PK": "PKR", "BD": "BDT", "LK": "LKR", "NP": "NPR", "MV": "MVR", "CN": "CNY", "HK": "HKD",
    "TW": "TWD", "JP": "JPY", "KR": "KRW", "SG": "SGD", "MY": "MYR", "TH": "THB", "VN": "VND", "PH": "PHP",
    "ID": "IDR", "AU": "AUD", "NZ": "NZD", "FJ": "FJD", "PG": "PGK", "UA": "UAH", "RS": "RSD", "GE": "GEL",
    "AM": "AMD", "KZ": "KZT", "JM": "JMD", "DO": "DOP", "CR": "CRC", "PA": "USD", "EC": "USD", "SV": "USD",
    "PR": "USD", "GU": "USD", "BS": "BSD", "BB": "BBD", "TT": "TTD", "MU": "MUR", "SC": "SCR",
}

# (police, ambulance, fire) — or a single shared number.
EMERGENCY: Dict[str, Dict[str, str]] = {
    "US": {"all": "911"}, "CA": {"all": "911"}, "MX": {"all": "911"}, "PR": {"all": "911"},
    "GB": {"all": "999", "alt": "112"}, "IE": {"all": "112", "alt": "999"},
    "AU": {"all": "000", "mobile": "112"}, "NZ": {"all": "111"},
    "IN": {"all": "112", "police": "100", "ambulance": "102", "fire": "101"},
    "JP": {"police": "110", "ambulance": "119", "fire": "119"},
    "KR": {"police": "112", "ambulance": "119", "fire": "119"},
    "CN": {"police": "110", "ambulance": "120", "fire": "119"},
    "HK": {"all": "999"}, "SG": {"police": "999", "ambulance": "995", "fire": "995"},
    "MY": {"all": "999"}, "TH": {"police": "191", "ambulance": "1669", "fire": "199"},
    "ID": {"all": "112", "police": "110", "ambulance": "118"}, "PH": {"all": "911"},
    "VN": {"police": "113", "ambulance": "115", "fire": "114"},
    "BR": {"police": "190", "ambulance": "192", "fire": "193"},
    "AR": {"police": "911", "ambulance": "107", "fire": "100"},
    "ZA": {"police": "10111", "ambulance": "10177", "mobile": "112"},
    "KE": {"all": "999", "alt": "112"}, "NG": {"all": "112"}, "EG": {"police": "122", "ambulance": "123"},
    "AE": {"police": "999", "ambulance": "998", "fire": "997"}, "IL": {"police": "100", "ambulance": "101", "fire": "102"},
    "TR": {"all": "112"}, "CH": {"all": "112", "police": "117", "ambulance": "144", "fire": "118"},
    "IS": {"all": "112"}, "FO": {"all": "112"}, "NO": {"all": "112", "police": "112", "ambulance": "113", "fire": "110"},
}

EU_LIKE = {"FR", "DE", "ES", "PT", "IT", "NL", "BE", "AT", "FI", "GR", "LU", "MT", "CY", "SK", "SI", "EE",
           "LV", "LT", "HR", "SE", "DK", "PL", "CZ", "HU", "RO", "BG"}


def currency_for(country_code: Optional[str]) -> Optional[str]:
    return CURRENCY.get((country_code or "").upper())


def emergency_for(country_code: Optional[str]) -> Dict[str, str]:
    cc = (country_code or "").upper()
    if cc in EMERGENCY:
        return dict(EMERGENCY[cc])
    if cc in EU_LIKE:
        return {"all": "112"}
    return {"all": "112", "unverified": "true"}
