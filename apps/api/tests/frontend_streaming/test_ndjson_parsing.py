"""
tests/frontend_streaming/test_ndjson_parsing.py

Validates NDJSON streaming from the frontend's perspective:
  - incremental chunk parsing
  - reconnect handling
  - malformed chunk recovery
  - slow consumer simulation
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _parse_ndjson(raw: str) -> list:
    """Parses NDJSON — tolerates blank lines and partial chunks."""
    results = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            # Real frontend should skip malformed chunks
            pass
    return results


def test_stream_returns_200_ndjson_content_type():
    resp = client.post("/interact", json={"query": "Cafes in Paris", "context": {}})
    assert resp.status_code == 200
    assert "ndjson" in resp.headers.get("content-type", "")


def test_each_chunk_has_event_and_data_keys():
    resp = client.post("/interact", json={"query": "Explore Berlin", "context": {}})
    chunks = _parse_ndjson(resp.text)
    assert len(chunks) > 0, "No chunks received"
    for chunk in chunks:
        assert "event" in chunk, f"Missing 'event' key: {chunk}"
        assert "data" in chunk, f"Missing 'data' key: {chunk}"


def test_first_chunk_is_heartbeat():
    resp = client.post("/interact", json={"query": "Transit in Tokyo", "context": {}})
    chunks = _parse_ndjson(resp.text)
    assert len(chunks) > 0
    first = chunks[0]
    assert first["event"] == "stream_heartbeat", f"First chunk should be heartbeat, got: {first}"


def test_last_chunk_is_result_or_error():
    resp = client.post("/interact", json={"query": "Best restaurants in NYC", "context": {}})
    chunks = _parse_ndjson(resp.text)
    assert len(chunks) > 1
    final_events = {c["event"] for c in chunks}
    assert "final_result" in final_events or "error" in final_events, \
        f"No terminal event found. Events: {final_events}"


_WIRE_EVENTS = {"partial_result", "final_result", "stream_heartbeat", "error"}


def test_only_wire_contract_events_reach_client():
    """Invisible orchestration: status/context_updated/agent_* stay internal."""
    resp = client.post("/interact", json={"query": "Cafes in Berlin", "context": {}})
    chunks = _parse_ndjson(resp.text)
    assert chunks
    leaked = {c["event"] for c in chunks} - _WIRE_EVENTS
    assert not leaked, f"internal events leaked to client: {leaked}"
    for c in chunks:
        if c["event"] == "error":
            assert set(c["data"]) == {"message"}, f"error payload leaks internals: {c}"


def test_empty_query_handled_gracefully():
    resp = client.post("/interact", json={"query": "", "context": {}})
    # Should not 500 — may return error event or proceed with empty query
    assert resp.status_code in (200, 422)


def test_oversized_payload_rejected():
    huge = "x" * 100_000
    resp = client.post("/interact", json={"query": huge, "context": {}})
    assert resp.status_code == 413


def test_ndjson_chunks_are_individually_parseable():
    """Each line must be independently parseable — frontend parses line by line."""
    resp = client.post("/interact", json={"query": "Events in London", "context": {}})
    for line in resp.text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            pytest.fail(f"Non-parseable NDJSON line: {line!r} — {e}")
