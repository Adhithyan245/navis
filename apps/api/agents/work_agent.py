from typing import Dict, Any
from apps.api.services.provider_manager import provider_manager
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class WorkAgent:
    async def run(self, query: str, context: Dict[str, Any]) -> dict:
        logger.info("WorkAgent started")
        loc = context.get("location")
        if not loc:
            return {"agent": "work", "data": [], "error": "No location provided"}
            
        try:
            # Query places for cafes
            resp = await provider_manager.places.execute(lat=loc["lat"], lon=loc["lon"], category="cafe")
            return {"agent": "work", "data": resp.results, "error": resp.error}
        except Exception as e:
            logger.error(f"WorkAgent failed: {e}")
            return {"agent": "work", "data": [], "error": str(e)}

work_agent = WorkAgent()
