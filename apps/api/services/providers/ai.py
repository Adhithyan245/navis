import aiohttp
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.core.config import settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# HuggingFace's serverless `api-inference.huggingface.co` host was retired;
# the OpenAI-compatible router is its replacement.
HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"


def extract_chat_text(data: dict) -> str:
    """Pull the assistant text out of an OpenAI-style chat completion.
    Returns "" when the payload has no usable content."""
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


class AIProvider(BaseProvider):
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, prompt: str, model: str | None = None) -> dict:
        model = model or settings.GROQ_MODEL
        messages = [{"role": "user", "content": prompt}]
        errors = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            # Groq Primary
            if settings.GROQ_API_KEY:
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {"model": model, "messages": messages, "temperature": 0.3}
                try:
                    async with session.post(GROQ_CHAT_URL, json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            text = extract_chat_text(await resp.json())
                            if text:
                                return {"text": text, "model": model}
                            errors.append("groq: empty completion")
                        else:
                            errors.append(f"groq: HTTP {resp.status}")
                except aiohttp.ClientError as e:
                    errors.append(f"groq: {type(e).__name__}")

            # HuggingFace Fallback
            if settings.HUGGINGFACE_API_KEY:
                fb_model = settings.HUGGINGFACE_MODEL
                headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}"}
                payload = {"model": fb_model, "messages": messages, "temperature": 0.3}
                try:
                    async with session.post(HF_CHAT_URL, json=payload, headers=headers) as fb_resp:
                        if fb_resp.status == 200:
                            text = extract_chat_text(await fb_resp.json())
                            if text:
                                return {"text": text, "model": f"hf:{fb_model}"}
                            errors.append("huggingface: empty completion")
                        else:
                            errors.append(f"huggingface: HTTP {fb_resp.status}")
                except aiohttp.ClientError as e:
                    errors.append(f"huggingface: {type(e).__name__}")

        detail = "; ".join(errors) if errors else "keys are missing"
        raise ValueError(f"AI Inference APIs failed ({detail}).")
