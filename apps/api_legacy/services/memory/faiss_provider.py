import os
import uuid
import time
import json
import logging
import asyncio
import math
from typing import List, Dict, Any, Optional
import numpy as np

from services.memory.base import MemoryProvider, MemoryItem, MemoryType

logger = logging.getLogger(__name__)

class FAISSMemoryProvider(MemoryProvider):
    def __init__(self, data_dir: str = "data/memory"):
        self.data_dir = data_dir
        self.index_path = os.path.join(self.data_dir, "faiss_index.bin")
        self.metadata_path = os.path.join(self.data_dir, "metadata.json")
        self.model = None
        self.index = None
        self.memories: Dict[str, MemoryItem] = {}
        self.id_to_index: Dict[str, int] = {}
        self.index_to_id: Dict[int, str] = {}
        self.lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize the sentence-transformer and FAISS index."""
        try:
            from sentence_transformers import SentenceTransformer
            import faiss
            
            # Use a fast, lightweight model for embeddings
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            
            os.makedirs(self.data_dir, exist_ok=True)
            
            # 384 is the dimension for all-MiniLM-L6-v2
            self.dimension = 384 
            
            if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("memories", []):
                        mem = MemoryItem(**item)
                        self.memories[mem.id] = mem
                    self.id_to_index = data.get("id_to_index", {})
                    # Ensure keys are integers for index_to_id
                    self.index_to_id = {int(k): v for k, v in data.get("index_to_id", {}).items()}
                logger.info(f"Loaded {len(self.memories)} memories from FAISS index.")
            else:
                self.index = faiss.IndexFlatL2(self.dimension)
                logger.info("Initialized new FAISS index.")
                
        except Exception as e:
            logger.error(f"Failed to initialize FAISS memory provider: {e}")
            raise

    async def _save_index(self):
        """Save index and metadata to disk."""
        import faiss
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump({
                "memories": [mem.model_dump() for mem in self.memories.values()],
                "id_to_index": self.id_to_index,
                "index_to_id": self.index_to_id
            }, f)

    async def add_memory(self, memory: MemoryItem):
        async with self.lock:
            # Generate embedding
            embedding = self.model.encode([memory.content])
            faiss_idx = self.index.ntotal
            
            self.index.add(np.array(embedding).astype("float32"))
            self.memories[memory.id] = memory
            self.id_to_index[memory.id] = faiss_idx
            self.index_to_id[faiss_idx] = memory.id
            
            await self._save_index()

    async def retrieve_relevant_context(
        self, 
        user_id: str, 
        query: str, 
        top_k: int = 5,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryItem]:
        
        if self.index.ntotal == 0:
            return []
            
        async with self.lock:
            await self._decay_memories_sync(user_id)
            
            embedding = self.model.encode([query])
            
            # Fetch more than top_k to allow filtering by user_id and memory_types
            search_k = min(self.index.ntotal, max(top_k * 5, 20))
            distances, indices = self.index.search(np.array(embedding).astype("float32"), search_k)
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx == -1:
                    continue
                    
                mem_id = self.index_to_id.get(int(idx))
                if not mem_id:
                    continue
                    
                mem = self.memories.get(mem_id)
                if not mem or mem.user_id != user_id:
                    continue
                    
                if memory_types and mem.memory_type not in memory_types:
                    continue
                    
                # Calculate final score incorporating similarity distance and recency score
                # FAISS L2 distance: lower is better. 
                # Convert distance to a similarity score between 0 and 1 (approximate)
                sim_score = max(0.0, 1.0 - (distances[0][i] / 2.0))
                
                # Boost score by recency and confidence
                final_score = sim_score * mem.recency_score * mem.confidence
                
                results.append((final_score, mem))
                
            # Sort by final score descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [mem for score, mem in results[:top_k]]

    async def _decay_memories_sync(self, user_id: str):
        """Internal sync version to use under lock."""
        now = time.time()
        to_delete = []
        dirty = False
        
        for mem_id, mem in self.memories.items():
            if mem.user_id != user_id:
                continue
                
            age = now - mem.timestamp
            
            # Check TTL
            if mem.ttl and age > mem.ttl:
                to_delete.append(mem_id)
                continue
                
            # Calculate recency score decay
            # Half-life of 30 days (2592000 seconds) for preferences, 7 days for interactions
            half_life = 2592000 if mem.memory_type == MemoryType.PREFERENCE else 604800
            
            new_recency = max(0.1, math.exp(-0.693 * age / half_life))
            
            if abs(mem.recency_score - new_recency) > 0.05:
                mem.recency_score = new_recency
                dirty = True
                
        # FAISS doesn't easily support deletion from FlatL2 without rebuilding.
        # So we just remove from memories dict and ignore them in retrieval.
        # Eventually we would rebuild the index.
        for mem_id in to_delete:
            del self.memories[mem_id]
            dirty = True
            
        if dirty:
            await self._save_index()

    async def decay_memories(self, user_id: str):
        import math
        async with self.lock:
            await self._decay_memories_sync(user_id)
