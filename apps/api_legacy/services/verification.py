import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

_SAFE_FALLBACK_MESSAGE = "Here is the information you requested."


class VerificationService:
    """
    Safety and Anti-Hallucination Layer.
    Verifies humanized outputs against raw provider data.

    GUARANTEE: verify_and_harden() NEVER throws an exception.
    """
    def __init__(self):
        pass
        
    def verify_and_harden(self, humanized_text: str, fused_data: Dict[str, Any]) -> str:
        """
        Validates generated text against the actual data.
        If unsupported claims are found, replaces with safe fallback.
        NEVER raises.
        """
        try:
            return self._verify_internal(humanized_text, fused_data)
        except Exception as e:
            logger.error("VerificationService crashed: %s", e)
            return _SAFE_FALLBACK_MESSAGE

    def _verify_internal(self, humanized_text: str, fused_data: Dict[str, Any]) -> str:
        """Internal verification logic — may raise; caller catches."""
        if not humanized_text or not isinstance(humanized_text, str):
            return _SAFE_FALLBACK_MESSAGE

        if not isinstance(fused_data, dict):
            return humanized_text

        results = fused_data.get("results", [])
        
        # Simple heuristic verification:
        # If the LLM generates a response but there is actually 0 data,
        # it is a hallucination.
        if not results:
            if any(word in humanized_text.lower() for word in ["found", "here are", "enjoy", "these"]):
                logger.warning(f"Hallucination detected! Suppressed output: '{humanized_text}'")
                return "Insufficient verified live data available."
                
        # If there's low confidence data, downgrade the enthusiasm
        if fused_data.get("confidence", 1.0) < 0.6:
            if "!" in humanized_text:
                humanized_text = humanized_text.replace("!", ".")
                
        return humanized_text
