"""
PHASE 2: Schema Enforcement Middleware

Middleware layer that intercepts all API responses and enforces APIResponse schema compliance.
Ensures that no response leaves the system without proper validation.
"""

import logging
from typing import Callable, Any
from functools import wraps
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

from models.response import APIResponse
from services.response_validator import ResponseValidator, ResponseValidationError

logger = logging.getLogger(__name__)


class SchemaEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces APIResponse schema on all responses.
    
    - Intercepts successful responses (200, 201, etc.)
    - Validates response is proper APIResponse structure
    - Normalizes if needed, fallback if invalid
    - Never allows malformed responses through
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        # Skip middleware for health checks and static files
        if request.url.path in ("/health", "/docs", "/openapi.json") or request.url.path.startswith("/static"):
            return await call_next(request)

        response = await call_next(request)

        # Only validate successful responses
        if response.status_code not in (200, 201):
            return response

        # Try to extract body and validate
        try:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Parse JSON
            import json
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON response from {request.url.path}")
                return response

            # Validate as APIResponse
            try:
                api_response = ResponseValidator.validate(
                    data,
                    context=f"middleware_{request.url.path}",
                )
                # Re-serialize validated response
                validated_body = api_response.model_dump_json().encode()
                response.body_iterator = self._aiter_bytes([validated_body])
                response.headers["content-length"] = str(len(validated_body))
            except ResponseValidationError as e:
                logger.error(f"Schema validation failed for {request.url.path}: {e}")
                # Return safe fallback
                fallback = ResponseValidator.fallback(
                    reason="Response schema validation failed",
                    agent=data.get("agent", "unknown"),
                )
                fallback_body = fallback.model_dump_json().encode()
                return JSONResponse(fallback.model_dump(), status_code=200)

        except Exception as e:
            logger.error(f"Middleware error processing response: {e}")
            # Don't crash; return original response
            return response

        return response

    @staticmethod
    async def _aiter_bytes(byte_strings):
        """Utility to iterate over byte strings."""
        for chunk in byte_strings:
            yield chunk


def enforce_schema(endpoint_name: str = "unknown") -> Callable:
    """
    Decorator to enforce schema on individual endpoint handlers.
    
    Usage:
        @router.get("/explore")
        @enforce_schema("explore")
        async def get_explore(context: UserContext) -> APIResponse:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                result = await func(*args, **kwargs)
                
                # If result is APIResponse, validate it
                if isinstance(result, APIResponse):
                    try:
                        result = ResponseValidator.validate(
                            result,
                            context=f"endpoint_{endpoint_name}",
                        )
                        result = ResponseValidator.ensure_consistency(result)
                        ResponseValidator.log_issues(result, context=endpoint_name)
                    except ResponseValidationError as e:
                        logger.error(f"Schema validation failed in {endpoint_name}: {e}")
                        # Return safe fallback
                        result = ResponseValidator.fallback(
                            reason=f"Schema validation error in {endpoint_name}",
                            agent=endpoint_name,
                        )
                
                return result
            except Exception as e:
                logger.error(f"Error in {endpoint_name} endpoint: {e}")
                # Return safe error response
                return ResponseValidator.error(
                    reason=f"Endpoint error: {str(e)[:50]}",
                    agent=endpoint_name,
                )

        return wrapper
    return decorator


def validate_response_schema(response: Any, context: str = "unknown") -> APIResponse:
    """
    Standalone validation function for use in routes.
    
    Usage:
        @router.post("/search")
        async def search(...) -> APIResponse:
            ...
            final_response = build_response(...)
            return validate_response_schema(final_response, context="search")
    """
    try:
        response = ResponseValidator.validate(response, context=context)
        response = ResponseValidator.ensure_consistency(response)
        ResponseValidator.log_issues(response, context=context)
        return response
    except ResponseValidationError as e:
        logger.error(f"Failed to validate response in {context}: {e}")
        return ResponseValidator.fallback(
            reason=f"Response validation failed in {context}",
            agent=context,
        )
