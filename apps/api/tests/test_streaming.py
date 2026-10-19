import pytest
import json
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)

def test_interaction_streaming():
    response = client.post(
        "/interact",
        json={"query": "Find me a cafe in SF", "context": {}},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    
    # Check that it returns NDJSON properly
    chunks = response.text.strip().split("\n")
    assert len(chunks) > 0
    
    # First chunk should be a status or heartbeat
    first_chunk = json.loads(chunks[0])
    assert "event" in first_chunk
    assert "data" in first_chunk
    
    # Last chunk should be the final result or at least an event
    last_chunk = json.loads(chunks[-1])
    assert "event" in last_chunk
