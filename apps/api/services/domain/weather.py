"""Weather & climate for a place: now, 7 days, daylight, what to pack (Open-Meteo)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, get_json, result

URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
# Fallback forecast (MET Norway, free, worldwide). Open-Meteo rate-limits by IP,
# and shared cloud IPs (e.g. free hosting) often hit that limit.
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_HEADERS = {"User-Agent": "Navis/1.0 github.com/Adhithyan245/navis"}

# MET Norway symbol (without _day/_night) → nearest WMO code, so describe() works.
_MET_SYMBOLS = {
    "clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45,
    "lightrain": 61, "rain": 63, "heavyrain": 65, "lightrainshowers": 80, "rainshowers": 81, "heavyrainshowers": 82,
    "lightsleet": 66, "sleet": 66, "heavysleet": 67, "lightsleetshowers": 66, "sleetshowers": 66,
    "lightsnow": 71, "snow": 73, "heavysnow": 75, "lightsnowshowers": 85, "snowshowers": 85, "heavysnowshowers": 86,
}


def met_symbol_to_wmo(symbol: str | None) -> int | None:
    if not symbol:
        return None
    base = symbol.split("_")[0]
    if "thunder" in base:
        return 95
    return _MET_SYMBOLS.get(base)


def met_to_open_meteo(data: Dict[str, Any], lon: float) -> Dict[str, Any] | None:
    """Reshape a MET Norway compact forecast like an Open-Meteo response.
    Local dates use the longitude's approximate UTC offset (no timezone in
    the feed); sunrise/sunset aren't provided."""
    from datetime import datetime, timedelta

    series = ((data or {}).get("properties") or {}).get("timeseries") or []
    if not series:
        return None
    first = series[0]
    inst = (first.get("data") or {}).get("instant", {}).get("details", {})
    nxt = (first.get("data") or {}).get("next_1_hours") or (first.get("data") or {}).get("next_6_hours") or {}
    offset = timedelta(hours=round(lon / 15))
    days: Dict[str, Dict[str, Any]] = {}
    for row in series:
        try:
            t = datetime.fromisoformat(row["time"].replace("Z", "+00:00")) + offset
        except (KeyError, ValueError):
            continue
        temp = ((row.get("data") or {}).get("instant") or {}).get("details", {}).get("air_temperature")
        d = days.setdefault(t.date().isoformat(), {"temps": [], "rain": 0.0, "symbols": []})
        if isinstance(temp, (int, float)):
            d["temps"].append(temp)
        for key in ("next_1_hours", "next_6_hours"):
            block = (row.get("data") or {}).get(key)
            if block:
                amount = (block.get("details") or {}).get("precipitation_amount")
                if key == "next_1_hours" and isinstance(amount, (int, float)):
                    d["rain"] += amount
                code = met_symbol_to_wmo((block.get("summary") or {}).get("symbol_code"))
                if code is not None and 9 <= t.hour <= 18:
                    d["symbols"].append(code)
                break
    dates = sorted(days)[:7]
    if not dates:
        return None

    def worst(codes):
        return max(codes) if codes else None

    return {
        "timezone": None,
        "current": {
            "temperature_2m": inst.get("air_temperature"),
            "apparent_temperature": None,
            "weather_code": met_symbol_to_wmo((nxt.get("summary") or {}).get("symbol_code")),
            "wind_speed_10m": round(inst["wind_speed"] * 3.6, 1) if isinstance(inst.get("wind_speed"), (int, float)) else None,
            "relative_humidity_2m": inst.get("relative_humidity"),
            "precipitation": None,
            "time": first.get("time"),
        },
        "daily": {
            "time": dates,
            "weather_code": [worst(days[d]["symbols"]) for d in dates],
            "temperature_2m_max": [max(days[d]["temps"]) if days[d]["temps"] else None for d in dates],
            "temperature_2m_min": [min(days[d]["temps"]) if days[d]["temps"] else None for d in dates],
            # No probabilities in the compact feed: estimate from the day's total.
            "precipitation_probability_max": [70 if days[d]["rain"] >= 1 else 40 if days[d]["rain"] >= 0.2 else 10 for d in dates],
            "sunrise": [None for _ in dates],
            "sunset": [None for _ in dates],
        },
    }

# US AQI bands (EPA)
_AQI = ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"), (200, "Unhealthy"),
        (300, "Very unhealthy"), (10_000, "Hazardous"))


def aqi_label(aqi: Any) -> str | None:
    try:
        v = float(aqi)
    except (TypeError, ValueError):
        return None
    return next(label for limit, label in _AQI if v <= limit)


async def air_quality(place: PlaceRef) -> Dict[str, Any] | None:
    """Current air quality (US AQI, PM2.5, ozone) and pollen where modelled (Europe)."""
    data = await get_json(AIR_URL, params={
        "latitude": place.lat, "longitude": place.lon, "timezone": "auto",
        "current": "us_aqi,pm2_5,pm10,ozone,uv_index,grass_pollen,birch_pollen,ragweed_pollen",
    })
    cur = (data or {}).get("current")
    if not cur or cur.get("us_aqi") is None:
        return None
    pollen = {k.replace("_pollen", ""): cur.get(k) for k in ("grass_pollen", "birch_pollen", "ragweed_pollen")
              if isinstance(cur.get(k), (int, float))}
    return {"us_aqi": cur.get("us_aqi"), "label": aqi_label(cur.get("us_aqi")), "pm2_5": cur.get("pm2_5"),
            "pm10": cur.get("pm10"), "ozone": cur.get("ozone"), "uv_index": cur.get("uv_index"),
            "pollen": pollen or None}

# WMO weather codes → short words
_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorms",
    96: "Thunderstorms with hail", 99: "Thunderstorms with hail",
}


def describe(code: Any) -> str:
    try:
        return _CODES.get(int(code), "Mixed")
    except (TypeError, ValueError):
        return "Mixed"


def packing_hints(days: List[Dict[str, Any]], wind_kmh: float | None) -> List[str]:
    if not days:
        return []
    lows = [d["min_c"] for d in days if d.get("min_c") is not None]
    highs = [d["max_c"] for d in days if d.get("max_c") is not None]
    rainy = sum(1 for d in days if (d.get("rain_chance") or 0) >= 50)
    hints = []
    if lows and min(lows) <= 0:
        hints.append("Freezing nights: pack a warm coat, hat and gloves.")
    elif lows and min(lows) <= 8:
        hints.append("Chilly mornings and evenings: bring warm layers.")
    if highs and max(highs) >= 30:
        hints.append("Hot days ahead: light clothes, sunscreen and water.")
    if rainy >= 2:
        hints.append(f"Rain is likely on {rainy} of the next {len(days)} days: a rain jacket or umbrella helps.")
    if wind_kmh and wind_kmh >= 35:
        hints.append("It's windy right now: a windproof layer is worth it.")
    return hints or ["Mild, settled weather: everyday clothes are fine."]


async def weather(place: PlaceRef) -> Dict[str, Any]:
    key = f"domain.weather:{place.lat:.2f}:{place.lon:.2f}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    air_task = asyncio.create_task(air_quality(place))
    data = await get_json(URL, params={
        "latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 7,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
    })
    source = "open-meteo"
    if not data or "current" not in data:
        met = await get_json(MET_URL, params={"lat": round(place.lat, 4), "lon": round(place.lon, 4)}, headers=MET_HEADERS)
        data = met_to_open_meteo(met, place.lon) if met else None
        source = "met-norway"
    if not data or "current" not in data or data["current"].get("temperature_2m") is None:
        return result("unavailable",
                      message=f"The forecast for {place.label} isn't loading right now. Check back in a few minutes.",
                      alternatives=["Your phone's weather app will have the latest forecast."])
    cur = data["current"]
    daily = data.get("daily") or {}
    days = []
    for i, day in enumerate(daily.get("time") or []):
        def at(k):
            v = daily.get(k) or []
            return v[i] if i < len(v) else None
        days.append({"date": day, "summary": describe(at("weather_code")), "max_c": at("temperature_2m_max"),
                     "min_c": at("temperature_2m_min"), "rain_chance": at("precipitation_probability_max"),
                     "sunrise": at("sunrise"), "sunset": at("sunset")})
    now = {
        "temp_c": cur.get("temperature_2m"), "feels_like_c": cur.get("apparent_temperature"),
        "summary": describe(cur.get("weather_code")), "wind_kmh": cur.get("wind_speed_10m"),
        "humidity": cur.get("relative_humidity_2m"), "local_time": cur.get("time"),
    }
    air = await air_task
    hints = packing_hints(days, cur.get("wind_speed_10m"))
    if air and air.get("us_aqi") is not None and air["us_aqi"] > 100:
        hints.insert(0, f"Air quality is {air['label'].lower()} (AQI {round(air['us_aqi'])}): limit long outdoor exercise.")
    if air and isinstance(air.get("uv_index"), (int, float)) and air["uv_index"] >= 6:
        hints.append(f"High UV (index {round(air['uv_index'])}): sunscreen and a hat around midday.")
    out = result("ok", {"now": now, "days": days, "timezone": data.get("timezone"), "air": air,
                        "packing": hints},
                 message=f"{now['summary']}, {round(now['temp_c'])}°C in {place.label} right now"
                         + (f" (feels like {round(now['feels_like_c'])}°C)." if now.get("feels_like_c") is not None else "."),
                 sources=[source])
    await cache.set(key, out, ttl=20 * 60 if source == "open-meteo" else 30 * 60)
    return out
