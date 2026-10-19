import abc
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class MemoryType(str, Enum):
    EPISODIC = "episodic"
    PREFERENCE = "preference"
    INTERACTION = "interaction"
    SYSTEM = "system"

class MemoryItem(BaseModel):
    id: str
    user_id: str
    memory_type: MemoryType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float
    ttl: Optional[float] = None  # Time to live in seconds
    
    # Provenance data
    confidence: float = 1.0
    source: str = "user_input"
    recency_score: float = 1.0

class MemoryProvider(abc.ABC):
    """Abstract interface for Vector Memory Stores."""
    
    @abc.abstractmethod
    async def initialize(self):
        """Initialize the connection to the memory store."""
        pass

    @abc.abstractmethod
    async def add_memory(self, memory: MemoryItem):
        """Add a memory to the store."""
        pass

    @abc.abstractmethod
    async def retrieve_relevant_context(
        self, 
        user_id: str, 
        query: str, 
        top_k: int = 5,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryItem]:
        """Retrieve relevant memories based on semantic similarity and recency decay."""
        pass
        
    @abc.abstractmethod
    async def decay_memories(self, user_id: str):
        """Apply TTL and recency decay to existing memories."""
        pass
