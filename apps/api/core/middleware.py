import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
import structlog
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        
        return response

class SchemaEnforcementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Skip validation for streaming responses
        if isinstance(response, StreamingResponse):
            return response
            
        # Additional layer 3 validation for non-streaming responses could be added here
        # E.g., intercepting JSONResponse and validating against a strict OpenAPI schema definition.
        # But for performance and standard FastAPI behavior, Pydantic handles most of this.
        
        return response
