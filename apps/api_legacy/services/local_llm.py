import time
import httpx
import json
import logging
from typing import Dict, Any, Optional
from services.metrics import metrics
from services.provider_base import BaseProvider, ProviderCapability, registry

logger = logging.getLogger(__name__)

class LocalLLMProvider(BaseProvider):
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model = "llama3" # Default model
        self._capability = ProviderCapability(
            id="ollama_llm",
            name="Ollama Local LLM API",
            is_primary=True,
            requires_key=False,
            domains=["voice", "humanization"]
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    async def generate_response(self, prompt: str, system: str = "") -> Optional[str]:
        from services.inference_router import InferenceRouter
        router = InferenceRouter()
        
        t0 = time.time()
        try:
            response = await router.generate_response(prompt, system=system)
            latency = (time.time() - t0) * 1000
            metrics.record_inference(latency)
            return response
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_inference(latency)
            logger.warning(f"Inference router failed: {e}")
            return None

# Register Local LLM Provider
registry.register(LocalLLMProvider())

class HumanizationService:
    """
    Converts raw data payloads into human-friendly responses.
    
    GUARANTEE: humanize() NEVER throws an exception.
    Falls back to deterministic rules when LLM is unavailable.
    """
    
    def __init__(self):
        self.provider = LocalLLMProvider()
        
    def _deterministic_fallback(self, data: Dict[str, Any], context: Dict[str, Any], agent: str) -> str:
        """
        Fallback to friendly deterministic rules if local LLM is down.
        NEVER raises — returns generic message on any internal error.
        """
        try:
            return self._deterministic_fallback_internal(data, context, agent)
        except Exception as e:
            logger.warning("Deterministic fallback failed: %s", e)
            return "Here is the information you requested."
    
    def _deterministic_fallback_internal(self, data: Dict[str, Any], context: Dict[str, Any], agent: str) -> str:
        """Internal deterministic logic — may raise; caller catches."""
        city = "your city"
        if isinstance(context, dict):
            city = context.get("city") or context.get("new_city") or "your city"
        
        if agent == "taste":
            places = data.get("places", []) if isinstance(data, dict) else []
            if places:
                first_name = places[0].get('name', 'a great spot') if isinstance(places[0], dict) else 'a great spot'
                return f"I found {len(places)} great spots in {city} for you to check out! '{first_name}' looks especially promising."
            return f"I couldn't find any exact matches in {city} right now, but feel free to broaden your search!"
            
        if agent == "explore":
            places = data.get("places", []) if isinstance(data, dict) else []
            if places:
                return f"Here are {len(places)} exciting places to explore in {city}. Have a great time!"
            return f"It's quiet in {city} right now. Try adjusting your preferences."
            
        if agent == "work":
            spaces = data.get("workspaces", []) if isinstance(data, dict) else []
            if spaces:
                return f"I found {len(spaces)} great coworking spaces and cafes in {city} where you can get some work done."
            return f"I couldn't find any specific workspaces in {city} right now."
            
        if agent == "settle":
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            return f"I've put together a list of {len(tasks)} important tasks to help you settle into {city}. Let's get started!"
            
        if agent == "services":
            services = data.get("services", []) if isinstance(data, dict) else []
            if services:
                return f"I located {len(services)} essential services nearby in {city}."
            return f"I couldn't find those services in {city} right now."
            
        if agent == "connect":
            events = data.get("events", []) if isinstance(data, dict) else []
            if events:
                return f"There are {len(events)} upcoming events in {city} that you might enjoy!"
            return f"I don't see any matching events in {city} at the moment."
        
        # Multi-agent / unknown agent type
        if agent == "multi_agent":
            results = data.get("results", []) if isinstance(data, dict) else []
            if results:
                return f"I found {len(results)} results for you in {city}."
            return f"I'm still gathering information for you in {city}."
            
        return "Here is the information you requested!"

    async def humanize(self, data: Dict[str, Any], context: Dict[str, Any], agent: str) -> str:
        """
        Generate a humanized response from raw data.
        NEVER raises — always returns a usable string.
        """
        try:
            # Safely serialize inputs
            safe_data = data if isinstance(data, dict) else {}
            safe_context = context if isinstance(context, dict) else {}
            
            system_prompt = "You are Navis, a friendly, warm, and helpful city-guide AI. Summarize the provided JSON data into a single, concise, conversational sentence or two. Don't mention the JSON structure, just talk to the user like a local guide."
            user_prompt = f"Agent Context: {agent}\nUser Context: {json.dumps(safe_context, default=str)}\nData Payload: {json.dumps(safe_data, default=str)}"
            
            response = await self.provider.generate_response(user_prompt, system=system_prompt)
            
            if response and isinstance(response, str) and response.strip():
                return response.strip()
        except Exception as e:
            logger.warning("LLM humanization failed: %s", e)
            
        # Fallback to deterministic rules if Ollama fails or is unavailable
        return self._deterministic_fallback(data, context, agent)
