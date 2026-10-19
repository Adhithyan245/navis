import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from apps.api.models.providers import ProviderResponse
from apps.api.services.provider_manager import provider_manager
from apps.api.agents.orchestrator import run_orchestration

@pytest.mark.asyncio
async def test_orchestrator_cancellation_safety():
    """Simulates a frontend disconnect resulting in CancelledError during orchestration."""
    
    # We will mock the geo provider to sleep and then raise CancelledError
    async def mock_geo_fetch(*args, **kwargs):
        await asyncio.sleep(0.5)
        raise asyncio.CancelledError()
        
    with patch.object(provider_manager.geo, 'fetch', new=mock_geo_fetch):
        context = {}
        stream_chunks = []
        try:
            async for chunk in run_orchestration(query="Test", context=context):
                stream_chunks.append(chunk)
                if len(stream_chunks) > 1:
                    # Break the stream manually to simulate disconnect
                    break
        except Exception as e:
            pytest.fail(f"Orchestration raised exception instead of yielding safely: {e}")
            
        assert len(stream_chunks) > 0

@pytest.mark.asyncio
async def test_provider_timeout_fallback():
    """Simulates a provider timeout and ensures it falls back gracefully."""
    
    async def mock_fetch(*args, **kwargs):
        await asyncio.sleep(20) # Exceeds timeout
        return {"data": "should not reach"}
        
    with patch.object(provider_manager.wiki, 'fetch', new=mock_fetch):
        resp = await provider_manager.wiki.execute(topic="Paris")
        assert resp.source == "fallback"
        assert resp.confidence == 0.0
