import logging
import httpx
import time
from typing import Optional, Dict
from services.metrics import metrics

logger = logging.getLogger(__name__)


class InferenceRouter:
    """
    Routes local LLM inference requests with automatic fallback priority:
    llama3 -> mistral -> gemma -> deterministic summarizer

    Hardened against:
    - Ollama being offline
    - Individual model 404/500 errors
    - Connection timeouts
    - Excessive log spam from repeated failures

    GUARANTEE: generate_response() NEVER raises to callers.
    """

    # ── Class-level state (shared across instances) ──────────────────────
    _model_availability: Dict[str, bool] = {}
    _last_check_time: Dict[str, float] = {}
    _failure_count: Dict[str, int] = {}
    _all_failed_logged: bool = False
    _ollama_offline: bool = False
    _ollama_offline_since: float = 0.0

    _MODEL_RECHECK_INTERVAL = 60        # seconds before retrying a known-bad model
    _OLLAMA_RECHECK_INTERVAL = 30       # seconds before rechecking Ollama health
    _MAX_BACKOFF_SECONDS = 8.0          # max backoff per model attempt
    _BASE_TIMEOUT = 10.0                # base HTTP timeout

    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model_chain = ["llama3", "mistral", "gemma"]

    # ── Model availability tracking ──────────────────────────────────────

    def _should_skip_model(self, model: str) -> bool:
        """Skip models that recently failed, unless recheck interval elapsed."""
        if model not in self._model_availability:
            return False
        if self._model_availability[model]:
            return False
        last_check = self._last_check_time.get(model, 0)
        if (time.time() - last_check) > self._MODEL_RECHECK_INTERVAL:
            return False  # Retry after cooldown
        return True

    def _mark_model(self, model: str, available: bool):
        """Record model availability status with failure counting."""
        InferenceRouter._model_availability[model] = available
        InferenceRouter._last_check_time[model] = time.time()
        if available:
            InferenceRouter._failure_count[model] = 0
            InferenceRouter._all_failed_logged = False
            InferenceRouter._ollama_offline = False
        else:
            InferenceRouter._failure_count[model] = (
                InferenceRouter._failure_count.get(model, 0) + 1
            )

    def _get_backoff_seconds(self, model: str) -> float:
        """Exponential backoff based on consecutive failure count."""
        failures = InferenceRouter._failure_count.get(model, 0)
        if failures <= 1:
            return 0.0
        # 0.5s, 1s, 2s, 4s, 8s (capped)
        return min(0.5 * (2 ** (failures - 1)), self._MAX_BACKOFF_SECONDS)

    def _is_ollama_offline(self) -> bool:
        """Check cached Ollama offline status with recheck interval."""
        if not InferenceRouter._ollama_offline:
            return False
        elapsed = time.time() - InferenceRouter._ollama_offline_since
        if elapsed > self._OLLAMA_RECHECK_INTERVAL:
            # Allow a retry
            InferenceRouter._ollama_offline = False
            return False
        return True

    def _mark_ollama_offline(self):
        """Mark Ollama as globally offline."""
        InferenceRouter._ollama_offline = True
        InferenceRouter._ollama_offline_since = time.time()
        for m in self.model_chain:
            self._mark_model(m, False)

    # ── Public API ───────────────────────────────────────────────────────

    async def generate_response(
        self, prompt: str, system: str = "", stream: bool = False
    ) -> Optional[str]:
        """
        Attempts inference via models in priority order.
        NEVER crashes the orchestrator — always returns Optional[str].
        """
        try:
            return await self._generate_response_internal(prompt, system, stream)
        except Exception as e:
            logger.error("InferenceRouter unexpected top-level error: %s", e)
            return None

    async def _generate_response_internal(
        self, prompt: str, system: str, stream: bool
    ) -> Optional[str]:
        """Internal generation logic."""

        # Fast path: if Ollama is known offline, skip everything
        if self._is_ollama_offline():
            return None

        import asyncio

        for model in self.model_chain:
            if self._should_skip_model(model):
                continue

            # Exponential backoff wait
            backoff = self._get_backoff_seconds(model)
            if backoff > 0:
                await asyncio.sleep(backoff)

            try:
                headers = {"Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "system": system,
                    "stream": stream,
                }

                t0 = time.time()
                async with httpx.AsyncClient(timeout=self._BASE_TIMEOUT) as client:
                    res = await client.post(
                        self.ollama_url, json=payload, headers=headers
                    )
                    latency = (time.time() - t0) * 1000

                    if res.status_code == 200:
                        metrics.record_provider_call(
                            "ollama_" + model, latency, True
                        )
                        self._mark_model(model, True)

                        if stream:
                            pass  # stream handling reserved for future
                        else:
                            return res.json().get("response", "")
                    else:
                        metrics.record_provider_call(
                            "ollama_" + model, latency, False
                        )
                        self._mark_model(model, False)
                        logger.info(
                            "inference_router: model=%s status=%d — skipping",
                            model,
                            res.status_code,
                        )

            except httpx.TimeoutException:
                self._mark_model(model, False)
                logger.info(
                    "inference_router: model=%s timed out — skipping", model
                )
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Ollama is offline — mark globally
                self._mark_ollama_offline()
                if not InferenceRouter._all_failed_logged:
                    logger.warning(
                        "inference_router: Ollama is offline. "
                        "Falling back to deterministic mode."
                    )
                    InferenceRouter._all_failed_logged = True
                break
            except Exception as e:
                self._mark_model(model, False)
                logger.info(
                    "inference_router: model=%s error=%s — skipping", model, e
                )

        # All models failed — log once, then suppress
        if not InferenceRouter._all_failed_logged:
            logger.warning(
                "inference_router: All local AI models unavailable. "
                "Using deterministic fallback."
            )
            InferenceRouter._all_failed_logged = True

        return None
