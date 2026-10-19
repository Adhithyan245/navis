class NavisBaseException(Exception):
    """Base exception for all Navis custom errors."""
    pass

class ProviderError(NavisBaseException):
    """Raised when a provider fails to return expected data."""
    def __init__(self, provider_name: str, reason: str):
        self.provider_name = provider_name
        self.reason = reason
        super().__init__(f"Provider '{provider_name}' failed: {reason}")

class AgentError(NavisBaseException):
    """Raised when an agent execution encounters a fatal error."""
    pass

class FusionError(NavisBaseException):
    """Raised during merging of provider outputs."""
    pass

class SchemaValidationError(NavisBaseException):
    """Raised when data structure is malformed."""
    pass
