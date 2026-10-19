import json
import logging
from typing import Dict, Any, List, Optional
from apps.api.services.inference_router import inference_router

logger = logging.getLogger(__name__)

def _result_items(data: Any) -> List[Any]:
    """Flatten the shapes humanization receives into a list of items."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "places", "events", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _item_name(item: Any) -> Optional[str]:
    """Display name for a provider item, including GeoJSON features whose
    name lives under `properties`."""
    if not isinstance(item, dict):
        return None
    for key in ("name", "title"):
        if item.get(key):
            return str(item[key])
    props = item.get("properties")
    if isinstance(props, dict):
        for key in ("name", "title", "address_line1"):
            if props.get(key):
                return str(props[key])
    return None


_PROMPT_ITEM_LIMIT = 15
_PROMPT_FIELDS = ("name", "title", "address", "address_line1", "address_line2",
                  "formatted", "categories", "rating", "distance", "description",
                  "summary", "text", "date", "venue", "url")


def _compact_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    flat = dict(item)
    props = item.get("properties")
    if isinstance(props, dict):
        flat = {**props, **{k: v for k, v in item.items() if k != "properties"}}
    return {k: flat[k] for k in _PROMPT_FIELDS if flat.get(k) not in (None, "", [])}


def _compact_for_prompt(data: Any) -> Any:
    """Trim provider payloads before they go into the LLM prompt: raw
    GeoJSON is huge and the useful signal is a handful of fields."""
    items = _result_items(data)
    if items:
        return [_compact_item(i) for i in items[:_PROMPT_ITEM_LIMIT]]
    return data


class HumanizationService:
    """Processes raw JSON outputs into natural language for final delivery."""
    
    async def format_response(self, query: str, context: dict, fused_data: Any) -> str:
        """
        LLM summary of `fused_data`, falling back to a deterministic summary
        when inference is unavailable. NEVER returns an error string.
        """
        prompt = f"""
        You are Navis, a helpful and intelligent city assistant.
        The user asked: "{query}"

        Here is the relevant data we found (JSON format):
        {json.dumps(_compact_for_prompt(fused_data), default=str)}

        Please provide a concise, natural language response incorporating this data.
        Be helpful and direct. Do not mention that you are an AI or using JSON.
        Write 2-4 sentences of plain prose: no tables, headings or bullet lists.
        You may bold place names with **double asterisks**. The individual
        places are already shown as cards, so highlight a few, don't list them all.
        """
        try:
            response = await inference_router.get_inference(prompt)
            if response and response.results:
                first = response.results[0]
                text = first.get("text", "") if isinstance(first, dict) else ""
                if text and text.strip():
                    return text.strip()
        except Exception as e:
            logger.warning(f"format_response inference failed: {e}")
        return self._summary_fallback(query, context, fused_data)

    def _summary_fallback(self, query: str, context: Any, fused_data: Any) -> str:
        """Deterministic, data-grounded summary used when the LLM is down."""
        try:
            items = _result_items(fused_data)
            city = None
            if isinstance(context, dict):
                city = context.get("city") or context.get("new_city")
            where = f" in {city}" if city else ""
            if not items:
                return f"I couldn't find matching results{where} right now. Try broadening your search."
            names = [n for n in (_item_name(i) for i in items) if n]
            # Keep first-seen order, drop duplicates.
            names = list(dict.fromkeys(names))[:3]
            count = len(items)
            noun = "result" if count == 1 else "results"
            if not names:
                return f"I found {count} {noun}{where} for you."
            if len(names) == 1:
                highlight = names[0]
            else:
                highlight = ", ".join(names[:-1]) + f" and {names[-1]}"
            return f"I found {count} {noun}{where}. Top picks include {highlight}."
        except Exception as e:
            logger.warning("Summary fallback failed: %s", e)
            return "Here is the information you requested."

    def _deterministic_fallback(self, data: Dict[str, Any], context: Dict[str, Any], agent: str) -> str:
        """
        Fallback to friendly deterministic rules if local LLM is down.
        NEVER raises — returns generic message on any internal error.
        """
        try:
            city = "your city"
            if isinstance(context, dict):
                city = context.get("city") or context.get("new_city") or "your city"
            
            if agent == "taste":
                places = data.get("places", []) or data.get("restaurants", []) if isinstance(data, dict) else []
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
            if agent in ("multi_agent", "voice", "general"):
                results = data.get("results", []) if isinstance(data, dict) else []
                if results:
                    return f"I found {len(results)} results for you in {city}."
                return f"I'm still gathering information for you in {city}."
                
            return "Here is the information you requested!"
        except Exception as e:
            logger.warning("Deterministic fallback failed: %s", e)
            return "Here is the information you requested."

    async def humanize(self, data: Dict[str, Any], context: Dict[str, Any], agent: str) -> str:
        """
        Generate a humanized response from raw data.
        NEVER raises — always returns a usable string.
        """
        try:
            safe_data = data if isinstance(data, dict) else {}
            safe_context = context if isinstance(context, dict) else {}
            
            system_prompt = "You are Navis, a friendly, warm, and helpful city-guide AI. Summarize the provided JSON data into a single, concise, conversational sentence or two. Don't mention the JSON structure, just talk to the user like a local guide."
            user_prompt = f"{system_prompt}\nAgent Context: {agent}\nUser Context: {json.dumps(safe_context, default=str)}\nData Payload: {json.dumps(safe_data, default=str)}"
            
            response = await inference_router.get_inference(user_prompt)
            if response and response.results:
                text = response.results[0].get("text", "")
                if text.strip():
                    return text.strip()
        except Exception as e:
            logger.warning(f"LLM humanization failed: {e}")
            
        return self._deterministic_fallback(data, context, agent)

humanization_service = HumanizationService()
