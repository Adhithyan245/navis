"""
PHASE 2: Response Schema Enforcement Layer

Validates and normalizes all responses to the unified APIResponse schema.
Ensures deterministic, safe, and predictable response structure across all endpoints.
"""

import logging
from typing import Dict, Any, List, Optional, Literal
from pydantic import ValidationError

from apps.api.models.responses import APIResponse, KNOWN_SOURCES

logger = logging.getLogger(__name__)


class ResponseValidationError(Exception):
    """Raised when response fails validation."""
    pass


class ResponseValidator:
    """Validates and normalizes responses to APIResponse schema."""

    # ─── VALIDATION ───

    @staticmethod
    def validate(response: Any, context: str = "unknown") -> APIResponse:
        """
        Validate and normalize a response to APIResponse schema.
        """
        # Already valid APIResponse
        if isinstance(response, APIResponse):
            try:
                # Re-validate to catch edge cases
                return APIResponse(**response.model_dump())
            except ValidationError as e:
                logger.error(f"APIResponse re-validation failed in {context}: {e}")
                raise ResponseValidationError(f"Invalid APIResponse in {context}: {e}")

        # Convert dict to APIResponse
        if isinstance(response, dict):
            try:
                return APIResponse(**response)
            except ValidationError as e:
                logger.error(f"Response validation failed in {context}: {e}")
                logger.debug(f"Failed response data: {response}")
                raise ResponseValidationError(f"Invalid response structure in {context}: {e}")

        # Invalid type
        raise ResponseValidationError(
            f"Response must be APIResponse or dict, got {type(response).__name__} in {context}"
        )

    @staticmethod
    def ensure_consistency(response: APIResponse) -> APIResponse:
        """
        Ensure response consistency rules.
        """
        # Fix data: ensure dict or list
        if response.data is None:
            response.data = {}

        # Fix sources: ensure list
        if response.sources is None:
            response.sources = []

        # Consistency: fallback status requires fallback source_mode
        if response.status == "fallback":
            if response.source_mode not in (None, "fallback"):
                logger.warning(f"Correcting source_mode to 'fallback' (was '{response.source_mode}')")
                response.source_mode = "fallback"
        
        # Consistency: success status should have sources
        elif response.status == "success":
            if not response.sources:
                logger.warning(f"Success status with empty sources; changing to fallback")
                response.status = "fallback"
                response.source_mode = "fallback"
            elif response.source_mode not in ("live", "cache", "hybrid"):
                logger.warning(f"Correcting source_mode to 'live' (was '{response.source_mode}')")
                response.source_mode = "live"

        return response

    # ─── BUILDERS ───

    @staticmethod
    def success(
        data: Dict[str, Any] = None,
        sources: List[str] = None,
        source_mode: str = "live",
        explanation: str = "",
        agent: str = "unknown",
        source: str = "provider",
    ) -> APIResponse:
        """Build a successful response."""
        return APIResponse(
            status="success",
            data=data or {},
            sources=sources or [],
            source_mode=source_mode,
            explanation=explanation,
            agent=agent,
            source=source,
        )

    @staticmethod
    def fallback(
        data: Dict[str, Any] = None,
        reason: str = "No data available",
        db_sources: List[str] = None,
        suggestions: List[str] = None,
        agent: str = "unknown",
    ) -> APIResponse:
        """Build a fallback response."""
        return APIResponse(
            status="fallback",
            data=data or {},
            sources=db_sources or [],
            source_mode="fallback",
            explanation=reason,
            message=reason,
            suggestions=suggestions,
            agent=agent,
            source="fallback",
            reason="provider_fallback",
        )

    @staticmethod
    def error(
        reason: str = "Internal error",
        agent: str = "unknown",
        suggestions: List[str] = None,
    ) -> APIResponse:
        """Build an error response."""
        return APIResponse(
            status="error",
            data={},
            sources=[],
            source_mode="fallback",
            explanation=reason,
            message=reason,
            suggestions=suggestions or ["Try again later"],
            agent=agent,
            source="error",
            reason="internal_error",
        )

    @staticmethod
    def apply_to_stream_response(
        response: APIResponse,
        domain: str = "unknown",
        context: str = "unknown",
        fail_on_error: bool = False,
    ) -> APIResponse:
        """
        Apply complete validation + consistency checks to stream response.
        """
        try:
            # Validate
            response = ResponseValidator.validate(response, context=context)
            
            # Ensure consistency
            response = ResponseValidator.ensure_consistency(response)
            
            return response
        except ResponseValidationError as e:
            logger.error(f"Failed to validate response in {context}: {e}")
            if fail_on_error:
                raise
            # Fallback to safe response
            return ResponseValidator.fallback(
                reason=f"Response validation failed: {str(e)[:50]}",
                agent=domain,
            )


# Singleton instance
response_validator = ResponseValidator()
