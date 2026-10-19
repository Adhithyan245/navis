"""
Base provider interface and registry.

Every provider MUST:
- Return a valid dictionary ALWAYS
- NEVER return None
- NEVER throw unhandled exceptions
- Use empty fallback structures on failure
"""

import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ProviderCapability(BaseModel):
    """Metadata about a provider's capabilities."""
    id: str
    name: str
    is_primary: bool = False
    requires_key: bool = True
    domains: List[str] = []  # e.g., ["places", "routing", "geocoding"]


class BaseProvider:
    """Base class for all data providers."""

    @property
    def capability(self) -> ProviderCapability:
        """Return provider metadata."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Check if the provider has all required configuration."""
        if not self.capability.requires_key:
            return True
        return False

    async def health_check(self) -> str:
        """Returns 'ACTIVE', 'LIMITED', or 'DISABLED'."""
        if not self.is_configured():
            return "DISABLED"
        return "ACTIVE"

    def _safe_dict(self, data: Optional[Dict] = None, error: str = "") -> Dict[str, Any]:
        """
        Returns a guaranteed valid response dictionary.
        Used as fallback when provider fails.
        """
        return {
            "results": [],
            "source": "fallback",
            "error": error if error else None,
            **(data or {}),
        }


class ProviderRegistry:
    """Centralized registry of all available providers."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider):
        """Register a provider."""
        self._providers[provider.capability.id] = provider
        logger.debug(
            f"Registered provider: {provider.capability.name} ({provider.capability.id})"
        )

    def get_provider(self, provider_id: str) -> Optional[BaseProvider]:
        """Retrieve a provider by ID."""
        return self._providers.get(provider_id)

    def get_providers_by_domain(self, domain: str) -> List[BaseProvider]:
        """Get all providers that serve a domain."""
        return [p for p in self._providers.values() if domain in p.capability.domains]

    def get_primary_provider(self, domain: str) -> Optional[BaseProvider]:
        """Get the primary provider for a domain."""
        providers = self.get_providers_by_domain(domain)
        primary = [p for p in providers if p.capability.is_primary]
        if primary:
            return primary[0]
        return providers[0] if providers else None

    def list_providers(self) -> Dict[str, str]:
        """List all registered providers."""
        return {
            provider_id: provider.capability.name
            for provider_id, provider in self._providers.items()
        }


# Global registry instance
_global_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    return _global_registry
