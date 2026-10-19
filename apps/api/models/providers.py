from pydantic import BaseModel, Field
from typing import Any, List, Optional

class ProviderResponse(BaseModel):
    provider: str
    source: str = "primary" # primary, fallback
    results: List[Any] = Field(default_factory=list)
    error: Optional[str] = None
    confidence: float = 0.0
    verified: bool = False
    retrieved_at: float
