from typing import Dict, Any
from apps.api.services.provider_manager import provider_manager
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class TasteAgent:
    async def run(self, query: str, context: Dict[str, Any]) -> dict:
        logger.info("TasteAgent started")
        loc = context.get("location")
        if not loc:
            return {"agent": "taste", "data": [], "error": "No location provided"}
        
        try:
            # Query places for dining/restaurants
            resp = await provider_manager.places.execute(lat=loc["lat"], lon=loc["lon"], category="dining")
            return {"agent": "taste", "data": resp.results, "error": resp.error}
        except Exception as e:
            logger.error(f"TasteAgent failed: {e}")
            return {"agent": "taste", "data": [], "error": str(e)}

taste_agent = TasteAgent()
