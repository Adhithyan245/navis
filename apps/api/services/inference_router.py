from apps.api.services.provider_manager import provider_manager
from apps.api.models.providers import ProviderResponse

class InferenceRouter:
    """Handles LLM routing with fallback logic."""
    
    async def get_inference(self, prompt: str) -> ProviderResponse:
        # The AIProvider already implements the Groq -> HuggingFace fallback
        # This router acts as a higher-level semantic interface if needed for complex flows
        response = await provider_manager.ai.execute(prompt=prompt)
        return response

inference_router = InferenceRouter()
