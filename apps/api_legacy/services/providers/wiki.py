"""
Wiki provider — reference and context data.

Provides background information, context, and knowledge base queries.
"""

import logging
from typing import Dict, Any
from .base import BaseProvider, ProviderCapability

logger = logging.getLogger(__name__)


class WikiProvider(BaseProvider):
    """
    Provides reference and context data.
    - Search Wikipedia
    - Get location context
    - Provide background information
    """

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            id="wiki",
            name="Wiki/Reference Provider",
            is_primary=False,
            requires_key=False,
            domains=["reference", "context", "knowledge"],
        )

    def is_configured(self) -> bool:
        """Wiki provider doesn't require keys — always available."""
        return True

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Search for reference information.

        Returns:
            {
                "results": [
                    {
                        "title": "Page Title",
                        "summary": "...",
                        "url": "...",
                        "source": "wikipedia|local",
                    },
                    ...
                ],
                "source": "wikipedia|fallback",
                "error": null,
            }
        """
        try:
            if not query or not isinstance(query, str):
                return self._safe_dict(error="Invalid query")

            # Placeholder: delegate to Wikipedia API
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"WikiProvider.search failed: {e}")
            return self._safe_dict(error=str(e))

    async def get_location_context(self, city: str) -> Dict[str, Any]:
        """
        Get background context about a location.

        Returns:
            {
                "city": "Boston",
                "country": "US",
                "description": "...",
                "population": 700000,
                "founded": 1630,
                "highlights": [...],
                "source": "wikipedia",
                "error": null,
            }
        """
        try:
            if not city or not isinstance(city, str):
                return self._safe_dict(error="Invalid city")

            # Placeholder
            return {
                "city": city,
                "description": "",
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"WikiProvider.get_location_context failed: {e}")
            return self._safe_dict(error=str(e))

    async def get_page(self, title: str) -> Dict[str, Any]:
        """
        Get a specific Wikipedia page.

        Returns:
            {
                "title": "...",
                "content": "...",
                "url": "...",
                "source": "wikipedia",
                "error": null,
            }
        """
        try:
            if not title or not isinstance(title, str):
                return self._safe_dict(error="Invalid title")

            # Placeholder
            return {
                "title": title,
                "content": "",
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"WikiProvider.get_page failed: {e}")
            return self._safe_dict(error=str(e))
