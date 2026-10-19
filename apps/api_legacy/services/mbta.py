import os
import httpx
from typing import Dict, Any

class MBTAService:
    def __init__(self):
        self.api_key = os.getenv("MBTA_API_KEY", "")
        self.base_url = "https://api-v3.mbta.com"

    async def get_transit_options(self, location: Dict[str, float]) -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_mbta_api_key":
            return {
                "status": "error",
                "options": [],
                "explanation": "MBTA API key missing. Unable to fetch transit options."
            }
            
        if not location or "lat" not in location or "lng" not in location:
             return {
                "status": "error",
                "options": [],
                "explanation": "Valid location coordinates are required for MBTA integration."
            }

        try:
            async with httpx.AsyncClient() as client:
                headers = {"x-api-key": self.api_key}
                response = await client.get(
                    f"{self.base_url}/stops",
                    headers=headers,
                    params={
                        "filter[latitude]": location["lat"],
                        "filter[longitude]": location["lng"],
                        "filter[radius]": 0.01, # roughly 1km
                        "sort": "distance"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                stops = data.get("data", [])
                normalized_options = []
                for stop in stops[:3]: # top 3 closest stops
                    attrs = stop.get("attributes", {})
                    normalized_options.append({
                        "mode": "Transit",
                        "station_name": attrs.get("name"),
                        "distance": attrs.get("distance", 0.0), # in degrees, roughly
                        "description": attrs.get("description", "MBTA Station")
                    })
                
                return {
                    "status": "success" if normalized_options else "fallback",
                    "options": normalized_options,
                    "explanation": f"Found {len(normalized_options)} nearby MBTA stops." if normalized_options else "No nearby MBTA stops found."
                }
        except httpx.TimeoutException:
            return {
                "status": "error",
                "options": [],
                "explanation": "MBTA API timeout."
            }
        except httpx.HTTPStatusError as e:
             return {
                "status": "error",
                "options": [],
                "explanation": f"MBTA API HTTP error: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "status": "error",
                "options": [],
                "explanation": f"MBTA API error: {str(e)}"
            }
