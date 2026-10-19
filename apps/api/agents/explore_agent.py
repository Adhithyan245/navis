from typing import Dict, Any
from apps.api.services.provider_manager import provider_manager
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class ExploreAgent:
    async def run(self, query: str, context: Dict[str, Any]) -> dict:
        logger.info("ExploreAgent started")
        loc = context.get("location")
        if not loc:
            return {"agent": "explore", "data": [], "error": "No location provided"}
            
        try:
            # Query events around location
            resp = await provider_manager.events.execute(lat=loc["lat"], lon=loc["lon"], radius=20)
            return {"agent": "explore", "data": resp.results, "error": resp.error}
        except Exception as e:
            logger.error(f"ExploreAgent failed: {e}")
            return {"agent": "explore", "data": [], "error": str(e)}

explore_agent = ExploreAgent()
