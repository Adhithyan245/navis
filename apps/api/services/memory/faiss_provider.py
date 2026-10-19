import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class FAISSMemoryProvider:
    def __init__(self):
        self.index = None # Bypassed by default
        
    async def retrieve_relevant_context(self, user_id: str, query: str, top_k: int = 5) -> List[Any]:
        return []
