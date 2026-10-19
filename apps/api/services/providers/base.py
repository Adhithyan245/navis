import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from apps.api.models.providers import ProviderResponse
from apps.api.core.logging import get_logger
from apps.api.observability.circuit_breaker import circuit_breaker

logger = get_logger(__name__)

class BaseProvider(ABC):
    def __init__(self):
        self.name = self.__class__.__name__
        self.session = None

    @abstractmethod
    async def fetch(self, *args, **kwargs) -> Any:
        pass

    async def execute(self, *args, **kwargs) -> ProviderResponse:
        from apps.api.services.provider_manager import provider_manager
        
        try:
            # We use an internal execute with a timeout
            # The circuit breaker is applied per-provider in their implementations
            # And concurrency is managed via global semaphore
            await provider_manager.semaphore.acquire()
            try:
                result = await asyncio.wait_for(self.fetch(*args, **kwargs), timeout=10.0)
            finally:
                provider_manager.semaphore.release()
                
            return ProviderResponse(
                provider=self.name,
                source="primary",
                results=result if isinstance(result, list) else [result],
                confidence=1.0,
                verified=True,
                retrieved_at=asyncio.get_event_loop().time()
            )
        except asyncio.CancelledError:
            logger.warning(f"{self.name} execution cancelled")
            raise  # Propagate cancellation
        except asyncio.TimeoutError:
            logger.error(f"{self.name} timed out")
            return self._fallback("Timeout Error")
        except Exception as e:
            logger.error(f"{self.name} failed: {e}")
            return self._fallback(str(e))

    def _fallback(self, reason: str) -> ProviderResponse:
        return ProviderResponse(
            provider=self.name,
            source="fallback",
            results=[],
            error=reason,
            confidence=0.0,
            verified=False,
            retrieved_at=asyncio.get_event_loop().time()
        )
