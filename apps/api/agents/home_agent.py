from typing import Dict, Any
from apps.api.services.provider_manager import provider_manager
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class HomeAgent:
    async def run(self, query: str, context: Dict[str, Any]) -> dict:
        logger.info("HomeAgent started")
        return {"agent": "home", "data": [], "error": "Not fully implemented for demo"}

home_agent = HomeAgent()
