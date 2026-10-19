import asyncio
from typing import Dict, Any, AsyncGenerator
from apps.api.agents.taste_agent import taste_agent
from apps.api.agents.transit_agent import transit_agent
from apps.api.agents.explore_agent import explore_agent
from apps.api.agents.work_agent import work_agent
from apps.api.agents.services_agent import services_agent
from apps.api.agents.settle_agent import settle_agent
from apps.api.agents.home_agent import home_agent
from apps.api.core.logging import get_logger
from apps.api.models.responses import StreamChunk
from apps.api.services.provider_manager import provider_manager
from apps.api.services.humanization import humanization_service

logger = get_logger(__name__)

async def run_orchestration(query: str, context: Dict[str, Any] = None) -> AsyncGenerator[dict, None]:
    if context is None:
        context = {}
        
    logger.info("Orchestration started", query=query)
    yield StreamChunk(event="status", data="Analyzing context and intent").model_dump()
    
    # Ensure we have some location context, fetch if necessary
    if not context.get("location"):
        yield StreamChunk(event="status", data="Geocoding query context").model_dump()
        try:
            geo_res = await provider_manager.geo.execute(query=query)
            if geo_res.results:
                context["location"] = geo_res.results[0]
                yield StreamChunk(event="context_updated", data={"location": context["location"]}).model_dump()
        except Exception as e:
            logger.error(f"Geo resolution failed: {e}")
            yield StreamChunk(event="status", data="Could not resolve location accurately").model_dump()

    yield StreamChunk(event="status", data="Dispatching agents").model_dump()

    # Parallel agent execution with failure isolation
    tasks = [
        taste_agent.run(query, context),
        explore_agent.run(query, context),
        work_agent.run(query, context)
        # Add others as needed
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful_data = []
    
    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"Agent {idx} failed critically: {res}")
            yield StreamChunk(event="agent_failed", data={"agent_index": idx, "error": str(res)}).model_dump()
        else:
            agent_name = res.get("agent")
            if res.get("error"):
                yield StreamChunk(event="agent_failed", data={"agent": agent_name, "error": res["error"]}).model_dump()
            else:
                yield StreamChunk(event="agent_success", data={"agent": agent_name, "results_count": len(res.get("data", []))}).model_dump()
                successful_data.extend(res.get("data", []))

    yield StreamChunk(event="status", data="Fusing and analyzing results").model_dump()
    
    # Humanization
    final_text = await humanization_service.format_response(query, context, successful_data)
    
    yield StreamChunk(event="result", data={"response": final_text, "raw_data_count": len(successful_data)}, is_final=True).model_dump()
    logger.info("Orchestration complete")
