import time
import asyncio
import random
from typing import Callable, Any
from functools import wraps
from apps.api.core.logging import get_logger
from apps.api.core.exceptions import ProviderError

logger = get_logger(__name__)

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, max_backoff: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_backoff = max_backoff
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_fallbacks = 0
        self.consecutive_successes = 0

    def _get_backoff(self) -> float:
        """Exponential backoff with jitter"""
        base_backoff = min(self.max_backoff, self.recovery_timeout * (2 ** max(0, self.failures - self.failure_threshold)))
        jitter = random.uniform(0.8, 1.2)
        return base_backoff * jitter

    def record_failure(self):
        self.failures += 1
        self.total_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("Circuit breaker OPEN", failures=self.failures, next_retry_in=self._get_backoff())

    def record_success(self):
        self.consecutive_successes += 1
        if self.state == "HALF_OPEN" and self.consecutive_successes >= 3:
            self.failures = 0
            self.state = "CLOSED"
            logger.info("Circuit breaker CLOSED (recovered)")
        elif self.state == "CLOSED":
            self.failures = max(0, self.failures - 1)

    def can_execute(self) -> bool:
        self.total_calls += 1
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            backoff = self._get_backoff()
            if time.time() - self.last_failure_time > backoff:
                self.state = "HALF_OPEN"
                self.consecutive_successes = 0
                return True
            return False
        # HALF_OPEN
        return True

def circuit_breaker(threshold: int = 5, timeout: int = 60):
    breaker = CircuitBreaker(failure_threshold=threshold, recovery_timeout=timeout)
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not breaker.can_execute():
                logger.error(f"Circuit breaker prevents call to {func.__name__}")
                breaker.total_fallbacks += 1
                raise ProviderError(func.__name__, "Circuit breaker is OPEN")
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise e
        
        # Attach breaker to function for metrics access
        wrapper.__breaker__ = breaker
        return wrapper
    return decorator
