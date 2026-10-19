"""Money: local currency, exchange rate from the user's home currency, tipping norms."""
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, get_json, result
from apps.api.services.domain.country_facts import currency_for

RATES_URL = "https://api.frankfurter.dev/v1/latest"
# Currencies the free reference-rate feed publishes (European Central Bank set).
FX_COVERED = {"AUD", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD", "HUF", "IDR", "ILS",
              "INR", "ISK", "JPY", "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD",
              "THB", "TRY", "USD", "ZAR"}


async def _rate(base: str, quote: str) -> Optional[Dict[str, Any]]:
    key = f"domain.fx:{base}:{quote}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    data = await get_json(RATES_URL, params={"from": base, "to": quote})
    rate = ((data or {}).get("rates") or {}).get(quote)
    if not rate:
        return None
    out = {"rate": rate, "date": data.get("date")}
    await cache.set(key, out, ttl=6 * 3600)
    return out


async def money(place: PlaceRef, *, home_country_code: Optional[str] = None,
                tipping: Optional[str] = None) -> Dict[str, Any]:
    local = currency_for(place.country_code)
    home = currency_for(home_country_code) if home_country_code else None
    if not local:
        return result("empty", {"tipping": tipping},
                      message=f"We don't have currency details for {place.label} yet.",
                      alternatives=["Card payments and ATMs are the easiest way to get local money on arrival."])
    data: Dict[str, Any] = {"currency": local, "home_currency": home, "tipping": tipping}
    if not home or home == local:
        return result("ok", data, message=f"The local currency in {place.label} is {local}.")
    if local not in FX_COVERED or home not in FX_COVERED:
        return result("partial", data,
                      message=f"The local currency is {local}. A live {home}→{local} rate isn't in our feed, "
                              "so check your bank app or a currency converter before exchanging.",
                      alternatives=["Withdrawing from a local ATM usually beats airport exchange counters."])
    fx = await _rate(home, local)
    if not fx:
        return result("partial", data,
                      message=f"The local currency is {local}. Live exchange rates are refreshing; try again shortly.")
    data.update({"rate": fx["rate"], "rate_date": fx["date"]})
    # Quote whichever direction reads naturally (1 USD ≈ 88.50 INR, not 1 INR ≈ 0.01 USD).
    if fx["rate"] >= 1:
        quote = f"1 {home} ≈ {fx['rate']:,.2f} {local}"
    else:
        quote = f"1 {local} ≈ {1 / fx['rate']:,.2f} {home}"
    return result("ok", data,
                  message=f"{quote} (reference rate, {fx['date']}).",
                  alternatives=["Card payments abroad: pick paying in the local currency for a better rate."],
                  sources=["frankfurter"])
