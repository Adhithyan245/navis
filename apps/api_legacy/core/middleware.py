import json
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from models.response import APIResponse

VALID_SOURCE_MODES = {"live", "fallback", "mixed"}
VALID_STATUSES = {"success", "fallback", "error"}

class GlobalResponseValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only validate non-streaming JSON responses.
        # Streaming endpoints are validated via Pydantic at event construction time.
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body_parts = [section async for section in response.body_iterator]
            raw = b"".join(body_parts) if isinstance(body_parts[0], bytes) else "".join(body_parts).encode()

            if raw:
                try:
                    data = json.loads(raw)
                    # Only validate payloads that look like APIResponse shapes
                    if isinstance(data, dict) and ("status" in data or "source_mode" in data):
                        APIResponse(**data)  # Pydantic validators run here
                except Exception as e:
                    return Response(
                        content=json.dumps({
                            "status": "error",
                            "data": {},
                            "explanation": f"Response schema validation failed: {str(e)}",
                            "context_used": {},
                            "sources": [],
                            "source_mode": "fallback",
                            "suggestions": None
                        }),
                        status_code=500,
                        media_type="application/json"
                    )

            # Reconstruct the body iterator
            async def body_iter():
                yield raw
            response.body_iterator = body_iter()

        return response
