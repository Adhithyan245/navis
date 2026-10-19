"""
PHASE 2: Response Schema Enforcement Layer

Validates and normalizes all responses to the unified APIResponse schema.
Ensures deterministic, safe, and predictable response structure across all endpoints.

Key Responsibilities:
1. Validate APIResponse fields (status, data, sources, source_mode)
2. Normalize responses from various sources
3. Enforce consistency between status/sources/source_mode
4. Provide helper builders for common response patterns
5. Detect and prevent schema violations
"""

import logging
from typing import Dict, Any, List, Optional, Literal
from pydantic import ValidationError

from models.response import APIResponse, KNOWN_SOURCES

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
        
        Args:
            response: Raw response (dict, APIResponse, or invalid)
            context: Calling context for error logging (e.g., 'stream_explore')
            
        Returns:
            Validated APIResponse instance
            
        Raises:
            ResponseValidationError: If response cannot be normalized
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
        Ensure response consistency rules:
        - If status=fallback, source_mode must be fallback
        - If status=success, sources must not be empty
        - data must be dict or list (never None)
        
        Fixes minor inconsistencies and raises on critical violations.
        """
        # Fix data: ensure dict or list
        if response.data is None:
            response.data = {} if response.status == "success" else {}

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

    # ─── NORMALIZATION ───

    @staticmethod
    def from_provider_response(
        provider_response: Dict[str, Any],
        domain: str = "places",
        context: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Normalize provider response to APIResponse-compatible dict.
        
        Args:
            provider_response: Raw response from ProviderManager
            domain: Data domain (places, services, events, transit)
            context: Calling context for logging
            
        Returns:
            Dict ready for APIResponse construction
        """
        if not isinstance(provider_response, dict):
            logger.error(f"Invalid provider response type in {context}: {type(provider_response)}")
            return {"status": "fallback", "data": {}, "sources": [], "source_mode": "fallback"}

        # Extract source and error
        source = provider_response.get("source", "fallback")
        error = provider_response.get("error")
        results = provider_response.get("results", [])

        # Build response
        is_live = source != "fallback" and not error

        return {
            "status": "success" if (is_live and results) else "fallback",
            "data": {domain: results} if results else {},
            "sources": [source] if is_live else [],
            "source_mode": "live" if is_live else "fallback",
            "explanation": error or f"No {domain} available",
            "source": source,
        }

    @staticmethod
    def merge_responses(
        responses: List[APIResponse],
        merge_strategy: Literal["all", "first", "best"] = "best",
        context: str = "unknown",
    ) -> APIResponse:
        """
        Merge multiple APIResponse objects.
        
        Args:
            responses: List of APIResponse objects to merge
            merge_strategy:
                - "all": Combine all data and sources
                - "first": Use first non-fallback response
                - "best": Use best quality response (success > cache > fallback)
            context: Calling context for logging
            
        Returns:
            Merged APIResponse
        """
        if not responses:
            return ResponseValidator.fallback(reason="No responses to merge")

        # Filter out errors and None
        valid = [r for r in responses if isinstance(r, APIResponse) and r.status != "error"]
        if not valid:
            return ResponseValidator.error(reason="All responses failed")

        if merge_strategy == "first":
            for r in valid:
                if r.status == "success":
                    return r
            return valid[0]

        elif merge_strategy == "best":
            # Prefer success > cache > fallback
            for r in valid:
                if r.status == "success" and r.source_mode == "live":
                    return r
            for r in valid:
                if r.status == "success" and r.source_mode == "cache":
                    return r
            return valid[0]

        # "all" strategy: combine data and sources
        merged_data = {}
        merged_sources = set()
        merged_status = "fallback"
        any_success = False

        for r in valid:
            if r.status == "success":
                any_success = True
            if isinstance(r.data, dict):
                merged_data.update(r.data)
            if r.sources:
                merged_sources.update(r.sources)

        return APIResponse(
            status="success" if any_success else "fallback",
            data=merged_data,
            sources=list(merged_sources),
            source_mode="hybrid" if len(merged_sources) > 1 else ("live" if any_success else "fallback"),
            explanation=f"Combined {len(valid)} responses",
            source="merged",
        )

    # ─── INSPECTION ───

    @staticmethod
    def is_valid(response: Any) -> bool:
        """Check if response is valid APIResponse."""
        if not isinstance(response, APIResponse):
            return False
        try:
            ResponseValidator.validate(response, context="is_valid_check")
            return True
        except ResponseValidationError:
            return False

    @staticmethod
    def get_issues(response: APIResponse) -> List[str]:
        """Get list of schema issues with response."""
        issues = []

        # Check status
        if response.status not in ("success", "fallback", "error"):
            issues.append(f"Invalid status: {response.status}")

        # Check data
        if not isinstance(response.data, (dict, list)):
            issues.append(f"data must be dict or list, got {type(response.data)}")
        if isinstance(response.data, dict) and len(response.data) == 0 and response.status == "success":
            issues.append("Empty data dict with success status")

        # Check sources
        if response.sources is not None:
            if not isinstance(response.sources, list):
                issues.append(f"sources must be list, got {type(response.sources)}")
            else:
                for s in response.sources:
                    if s not in KNOWN_SOURCES:
                        issues.append(f"Unknown source: {s}")

        # Check consistency
        if response.status == "fallback" and response.source_mode and response.source_mode != "fallback":
            issues.append(f"Fallback status requires fallback source_mode, got {response.source_mode}")

        if response.status == "success" and not response.sources:
            issues.append("Success status requires at least one source")

        return issues

    @staticmethod
    def log_issues(response: APIResponse, context: str = "unknown") -> None:
        """Log any schema issues found in response."""
        issues = ResponseValidator.get_issues(response)
        if issues:
            logger.warning(f"Schema issues in {context}:")
            for issue in issues:
                logger.warning(f"  - {issue}")

    # ─── MIDDLEWARE ───

    @staticmethod
    def apply_to_stream_response(
        response: APIResponse,
        domain: str = "unknown",
        context: str = "unknown",
        fail_on_error: bool = False,
    ) -> APIResponse:
        """
        Apply complete validation + consistency checks to stream response.
        
        Use this before yielding from stream methods.
        """
        try:
            # Validate
            response = ResponseValidator.validate(response, context=context)
            
            # Ensure consistency
            response = ResponseValidator.ensure_consistency(response)
            
            # Log any issues (non-fatal)
            ResponseValidator.log_issues(response, context=context)
            
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
