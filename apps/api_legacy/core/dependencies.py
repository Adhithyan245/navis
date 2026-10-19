"""
Dependency verification layer.
(Refactored for Zero-API-Key Open Infrastructure)
"""

import logging
from core.config import settings

logger = logging.getLogger(__name__)

class APINotConfiguredError(Exception):
    """Deprecated: Kept for backward compatibility, but no longer raised during normal operation."""
    pass

def assert_api_available(api_name: str) -> None:
    """
    Deprecated: The system now uses dynamic provider registries and gracefully falls back to open infrastructure.
    This function no longer raises exceptions.
    """
    pass
