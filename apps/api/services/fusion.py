from typing import List, Dict, Any, Optional
from apps.api.models.providers import ProviderResponse
from apps.api.core.exceptions import FusionError
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

def item_identity(item: Dict[str, Any]) -> Optional[str]:
    """Stable dedup key for a provider item.

    Flat items use name/title/id. GeoJSON features (Geoapify) carry nothing
    at the top level, so look in `properties` — place_id first, then name —
    and finally fall back to rounded coordinates. Returns None when the item
    has no usable identity at all (callers keep such items rather than
    collapsing them onto one key)."""
    for key in ("name", "title", "id", "place_id", "fsq_id"):
        value = item.get(key)
        if value not in (None, ""):
            return f"{key}:{str(value).lower().strip()}"

    props = item.get("properties")
    if isinstance(props, dict):
        for key in ("place_id", "id", "name", "title"):
            value = props.get(key)
            if value not in (None, ""):
                return f"{key}:{str(value).lower().strip()}"
        lat, lon = props.get("lat"), props.get("lon")
        if lat is not None and lon is not None:
            try:
                return f"geo:{float(lat):.5f},{float(lon):.5f}"
            except (TypeError, ValueError):
                pass

    geometry = item.get("geometry")
    if isinstance(geometry, dict):
        coords = geometry.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                return f"geo:{float(coords[1]):.5f},{float(coords[0]):.5f}"
            except (TypeError, ValueError):
                pass

    lat = item.get("lat") or item.get("latitude")
    lon = item.get("lon") or item.get("lng") or item.get("longitude")
    if lat is not None and lon is not None:
        try:
            return f"geo:{float(lat):.5f},{float(lon):.5f}"
        except (TypeError, ValueError):
            pass
    return None


class FusionEngine:
    """Robust engine for merging, deduplicating, and scoring provider outputs."""
    
    def merge(self, responses: List[ProviderResponse]) -> Dict[str, Any]:
        """Merges multiple provider responses into a unified structure."""
        merged_results = []
        seen_identifiers = set()
        
        for response in responses:
            if not response:
                continue
            
            for item in response.results:
                if not isinstance(item, dict):
                    continue
                
                # Deterministic deduplication; items with no identity are kept.
                identifier = item_identity(item)

                if identifier is None or identifier not in seen_identifiers:
                    if identifier is not None:
                        seen_identifiers.add(identifier)
                    # Provenance tracking
                    item["_provenance"] = {
                        "provider": response.provider,
                        "confidence": response.confidence,
                        "verified": response.verified,
                        "retrieved_at": response.retrieved_at
                    }
                    merged_results.append(item)
                    
        # Deterministic sorting (e.g., by confidence or name)
        merged_results.sort(key=lambda x: x["_provenance"]["confidence"], reverse=True)
        
        return {
            "total_results": len(merged_results),
            "data": merged_results,
            "providers_used": [r.provider for r in responses if r.results],
            "fallback_used": any(r.source == "fallback" for r in responses)
        }

    def fuse_results(self, agent_results: Any) -> Dict[str, Any]:
        """
        Merge results safely from multiple agents.
        NEVER raises — returns empty result on any internal error.
        """
        try:
            return self._fuse_results_internal(agent_results)
        except Exception as e:
            logger.error("FusionEngine.fuse_results crashed: %s", e)
            return {
                "results": [],
                "sources": [],
                "confidence": 0.0,
                "verified": False,
                "inferred_fields": [],
                "message": f"Fusion failed: {e}",
            }

    def _fuse_results_internal(self, agent_results: Any) -> Dict[str, Any]:
        """Internal fusion logic — may raise; caller catches."""
        fused_items = []
        seen_identifiers = set()
        sources = set()

        if not agent_results:
            return {
                "results": [],
                "sources": [],
                "confidence": 0.0,
                "verified": False,
                "inferred_fields": [],
                "message": "No agent results available.",
            }

        if not isinstance(agent_results, list):
            agent_results = [agent_results]
        
        agent_results = [r for r in agent_results if r is not None]

        for res in agent_results:
            if isinstance(res, BaseException):
                logger.warning("Skipping exception in agent results: %s", res)
                continue

            if not isinstance(res, dict):
                logger.warning("Skipping invalid agent result: %s", type(res))
                continue

            agent_data = res.get("data") or {}
            if isinstance(agent_data, list):
                agent_data = {"results": agent_data}

            if not isinstance(agent_data, dict):
                logger.warning("Agent data is malformed, skipping.")
                continue

            for key, items in agent_data.items():
                if items is None:
                    continue

                if isinstance(items, dict):
                    items = [items]

                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    identifier = item_identity(item)
                    if identifier is None:
                        continue

                    if identifier in seen_identifiers:
                        continue

                    item.setdefault("provenance", "provider-derived")
                    item.setdefault("confidence", 1.0)

                    fused_items.append(item)
                    seen_identifiers.add(identifier)

            res_sources = res.get("sources") or []
            if isinstance(res_sources, str):
                res_sources = [res_sources]

            if isinstance(res_sources, list):
                for s in res_sources:
                    if s:
                        sources.add(str(s))

        fused_items.sort(
            key=lambda x: (
                float(x.get("confidence", 1.0)),
                str(x.get("name", ""))
            ),
            reverse=True
        )

        avg_confidence = 0.0
        if fused_items:
            try:
                avg_confidence = (
                    sum(float(x.get("confidence", 1.0)) for x in fused_items)
                    / len(fused_items)
                )
            except (TypeError, ValueError, ZeroDivisionError):
                avg_confidence = 0.0

        return {
            "results": fused_items,
            "sources": list(sources),
            "confidence": round(avg_confidence, 2),
            "verified": avg_confidence >= 0.8,
            "inferred_fields": [],
            "message": (
                "Successfully fused multi-agent results."
                if fused_items
                else "No verified results available."
            )
        }

fusion_engine = FusionEngine()
