from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class ProviderCapability(BaseModel):
    id: str
    name: str
    is_primary: bool = False
    requires_key: bool = True
    domains: List[str] = [] # e.g., ["places", "routing", "geocoding"]

class BaseProvider:
    """Base class for all data providers."""
    
    @property
    def capability(self) -> ProviderCapability:
        raise NotImplementedError
        
    def is_configured(self) -> bool:
        """Check if the provider has all required configuration (e.g., API keys)."""
        if not self.capability.requires_key:
            return True
        return False
        
    async def health_check(self) -> str:
        """Returns 'ACTIVE', 'LIMITED', or 'DISABLED'"""
        if not self.is_configured():
            return "DISABLED"
        return "ACTIVE"


class ProviderRegistry:
    """Dynamically registers and manages all available providers."""
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        
    def register(self, provider: BaseProvider):
        self._providers[provider.capability.id] = provider
        logger.info(f"Registered provider: {provider.capability.name} ({provider.capability.id})")
        
    def get_provider(self, provider_id: str) -> Optional[BaseProvider]:
        return self._providers.get(provider_id)
        
    def get_providers_by_domain(self, domain: str) -> List[BaseProvider]:
        return [p for p in self._providers.values() if domain in p.capability.domains]
        
    def get_primary_provider(self, domain: str) -> Optional[BaseProvider]:
        """Gets the primary open-infrastructure provider for a domain."""
        for p in self.get_providers_by_domain(domain):
            if p.capability.is_primary and p.is_configured():
                return p
        return None
        
    def get_enrichment_providers(self, domain: str) -> List[BaseProvider]:
        """Gets optional/secondary providers for a domain."""
        return [p for p in self.get_providers_by_domain(domain) if not p.capability.is_primary and p.is_configured()]

# Global registry instance
registry = ProviderRegistry()
