import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AgentTask(BaseModel):
    agent_name: str
    priority: int
    dependencies: List[str] = []
    is_parallelizable: bool = True
    cancellation_safe: bool = True

class ExecutionPlan(BaseModel):
    tasks: List[AgentTask]
    requires_cross_agent: bool
    
class AgentPlanner:
    """
    Decomposes a user query into a Directed Acyclic Graph (DAG) of agent executions.
    """
    def __init__(self):
        self.supported_agents = {
            "taste", "connect", "transit", "work", "services", "settle", "explore"
        }
        
    def _detect_intents(self, query: str) -> List[str]:
        """Simple heuristic intent parser to extract multiple intents."""
        lower = query.lower()
        intents = []
        
        # Heuristics based on keywords
        if any(w in lower for w in ["food", "restaurant", "cafe", "coffee", "eat"]):
            intents.append("taste")
        if any(w in lower for w in ["transit", "subway", "bus", "commute"]):
            intents.append("transit")
        if any(w in lower for w in ["work", "coworking", "job", "office"]):
            intents.append("work")
        if any(w in lower for w in ["apartment", "housing", "rent", "settle", "move in"]):
            intents.append("settle")
        if any(w in lower for w in ["event", "concert", "meetup", "party"]):
            intents.append("connect")
        if any(w in lower for w in ["hospital", "pharmacy", "doctor", "gym"]):
            intents.append("services")
            
        if not intents or any(w in lower for w in ["explore", "discover", "places", "park"]):
            if "explore" not in intents:
                intents.append("explore")
                
        return intents
        
    def generate_plan(self, query: str) -> ExecutionPlan:
        """
        Generates a DAG of agent tasks.
        Enforces guardrails to prevent infinite chaining and circular dependencies.
        """
        intents = self._detect_intents(query)
        
        # Guardrail: Prevent infinite fanout
        if len(intents) > 4:
            logger.warning("Query triggered too many intents. Capping at 4.")
            intents = intents[:4]
            
        tasks = []
        added = set()
        
        for intent in intents:
            if intent in added:
                continue
            
            task = AgentTask(
                agent_name=intent,
                priority=1,
                is_parallelizable=True,
                cancellation_safe=True
            )
            
            # Setup dependencies
            if intent == "settle":
                task.priority = 0
                # Settle plan might need transit info, but to prevent circular deps, 
                # we don't strictly require it unless explicitly asked.
            elif intent == "transit":
                task.priority = 0 # High priority, run first
                
            tasks.append(task)
            added.add(intent)
            
        # Add transit if cross-agent (e.g. apartment + work + transit)
        if len(tasks) > 1 and "transit" not in added:
            if "settle" in added or "work" in added:
                tasks.append(AgentTask(
                    agent_name="transit",
                    priority=0,
                    is_parallelizable=True,
                    cancellation_safe=True
                ))
                added.add("transit")
                
        # Resolve dependencies (prevent circular)
        for task in tasks:
            if task.agent_name in ["work", "taste", "explore", "connect"]:
                if "transit" in added:
                    task.dependencies.append("transit")
                    
        return ExecutionPlan(
            tasks=tasks,
            requires_cross_agent=len(tasks) > 1
        )
