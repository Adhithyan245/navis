from typing import Any, Dict, List
from pydantic import ValidationError

def enforce_provider_fallback_schema(provider_name: str, reason: str) -> Dict[str, Any]:
    """Returns a safe fallback structure for any provider that fails."""
    return {
        "results": [],
        "source": "fallback",
        "provider": provider_name,
        "error": reason,
        "confidence": 0.0,
        "verified": False
    }

def validate_response_builder(model: Any, data: Dict[str, Any]) -> Any:
    """Layer 1: Validates raw data before sending it down the stream."""
    try:
        return model(**data)
    except ValidationError as e:
        return model(**enforce_provider_fallback_schema("builder", str(e)))

def validate_stream_chunk(chunk_data: Dict[str, Any]) -> bool:
    """Layer 2: Ensure stream chunks are valid JSON strings representing partial data."""
    # Basic structural check before yielding
    if "event" not in chunk_data or "data" not in chunk_data:
        return False
    return True
