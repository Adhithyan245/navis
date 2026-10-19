from typing import Dict, Any
from apps.api.services.provider_manager import provider_manager
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class ServicesAgent:
    async def run(self, query: str, context: Dict[str, Any]) -> dict:
        logger.info("ServicesAgent started")
        return {"agent": "services", "data": [], "error": "Not fully implemented for demo"}

services_agent = ServicesAgent()
