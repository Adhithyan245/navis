import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Canonical empty result — used as fallback when fusion fails
_EMPTY_FUSION_RESULT: Dict[str, Any] = {
    "results": [],
    "sources": [],
    "confidence": 0.0,
    "verified": False,
    "inferred_fields": [],
    "message": "No agent results available.",
}


class FusionEngine:
    """
    Response Fusion Engine.

    Merges outputs from different parallel agents,
    deduplicates POIs, preserves provenance,
    and safely handles partial / failed agent payloads.

    GUARANTEE: fuse_results() NEVER throws an exception.
    """

    def __init__(self):
        pass

    def fuse_results(self, agent_results: Any) -> Dict[str, Any]:
        """
        Merge results safely from multiple agents.
        NEVER raises — returns empty result on any internal error.
        """
        try:
            return self._fuse_results_internal(agent_results)
        except Exception as e:
            logger.error("FusionEngine.fuse_results crashed: %s", e)
            return dict(_EMPTY_FUSION_RESULT, message=f"Fusion failed: {e}")

    def _fuse_results_internal(self, agent_results: Any) -> Dict[str, Any]:
        """Internal fusion logic — may raise; caller catches."""

        fused_items = []
        seen_identifiers = set()
        sources = set()

        # Safety guard: normalize input
        if not agent_results:
            return dict(_EMPTY_FUSION_RESULT)

        # If someone passes a non-list, wrap it
        if not isinstance(agent_results, list):
            agent_results = [agent_results]
        
        # Additional guard: filter out None elements
        agent_results = [r for r in agent_results if r is not None]

        for res in agent_results:

            # Skip exceptions that leaked from asyncio.gather
            if isinstance(res, BaseException):
                logger.warning("Skipping exception in agent results: %s", res)
                continue

            # Skip completely invalid agent payloads
            if not isinstance(res, dict):
                logger.warning("Skipping invalid agent result: %s", type(res))
                continue

            # -------------------------
            # SAFE DATA EXTRACTION
            # -------------------------

            agent_data = res.get("data") or {}

            # Some agents may directly return a list
            if isinstance(agent_data, list):
                agent_data = {"results": agent_data}

            # Skip malformed data
            if not isinstance(agent_data, dict):
                logger.warning("Agent data is malformed, skipping.")
                continue

            # -------------------------
            # MERGE ITEMS
            # -------------------------

            for key, items in agent_data.items():

                if items is None:
                    continue

                # Convert single dict item into list
                if isinstance(items, dict):
                    items = [items]

                if not isinstance(items, list):
                    continue

                for item in items:

                    if not isinstance(item, dict):
                        continue

                    # Standardized naming
                    name = (
                        item.get("name")
                        or item.get("title")
                        or item.get("id")
                        or ""
                    )

                    if not name:
                        continue

                    identifier = str(name).lower().strip()

                    if identifier in seen_identifiers:
                        continue

                    # -------------------------
                    # DEFAULT PROVENANCE
                    # -------------------------

                    item.setdefault("provenance", "provider-derived")
                    item.setdefault("confidence", 1.0)

                    fused_items.append(item)
                    seen_identifiers.add(identifier)

            # -------------------------
            # SAFE SOURCE MERGING
            # -------------------------

            res_sources = res.get("sources") or []

            # Normalize single source string
            if isinstance(res_sources, str):
                res_sources = [res_sources]

            if isinstance(res_sources, list):
                for s in res_sources:
                    if s:
                        sources.add(str(s))

        # -------------------------
        # SORT RESULTS
        # -------------------------

        fused_items.sort(
            key=lambda x: (
                float(x.get("confidence", 1.0)),
                str(x.get("name", ""))
            ),
            reverse=True
        )

        # -------------------------
        # OVERALL CONFIDENCE
        # -------------------------

        avg_confidence = 0.0

        if fused_items:
            try:
                avg_confidence = (
                    sum(float(x.get("confidence", 1.0)) for x in fused_items)
                    / len(fused_items)
                )
            except (TypeError, ValueError, ZeroDivisionError):
                avg_confidence = 0.0

        # -------------------------
        # FINAL RESPONSE
        # -------------------------

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