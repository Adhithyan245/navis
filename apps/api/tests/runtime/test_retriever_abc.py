"""
Retriever ABC tests — verify the seam works.

The ABC is the contract that lets future retrievers (vector, hybrid,
remote) slot in without touching nodes. These tests prove:
  * `MarkdownRetriever` satisfies the ABC.
  * A trivial alternative retriever can be plugged into ContextRetrievalNode
    without changes to the node itself.
"""
from __future__ import annotations

from typing import Iterable, List, Optional
from pathlib import Path

import pytest

from apps.api.services.context_retriever import (
    ContextRetriever,
    KnowledgeChunk,
    MarkdownRetriever,
    Retriever,
)


def test_markdown_retriever_implements_abc():
    assert isinstance(MarkdownRetriever(), Retriever)


def test_context_retriever_alias_still_works():
    """Backwards-compat: pre-refactor code imported ContextRetriever."""
    assert ContextRetriever is MarkdownRetriever


def test_can_instantiate_custom_retriever():
    """A minimal alternative retriever class satisfies the seam."""

    class FixedRetriever(Retriever):
        def __init__(self, payload: List[KnowledgeChunk]) -> None:
            self._payload = payload

        def retrieve(self, query, *, city=None, workflow=None, tags=None, limit=5):
            return self._payload[:limit]

    chunk = KnowledgeChunk(
        path="fixed.md",
        frontmatter={"city": "x", "workflow": "y"},
        body="fixed",
        tokens=frozenset(),
    )
    r = FixedRetriever([chunk, chunk, chunk])
    assert isinstance(r, Retriever)

    out = r.retrieve("anything", limit=2)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_context_retrieval_node_works_with_alternative_retriever(monkeypatch):
    """Swap the singleton with a fake Retriever and verify the node still works."""
    from apps.api.runtime.context import ExecutionContext, NodeContext
    from apps.api.runtime.events import EventBus
    from apps.api.runtime.graph import NodeSpec
    from apps.api.runtime.nodes.context import ContextRetrievalNode
    from apps.api.services import context_retriever as ctx_mod

    class StubRetriever(Retriever):
        def __init__(self) -> None:
            self.calls = []
        def retrieve(self, query, *, city=None, workflow=None, tags=None, limit=5):
            self.calls.append({"query": query, "city": city, "workflow": workflow,
                               "tags": list(tags) if tags else None, "limit": limit})
            return [KnowledgeChunk(
                path="stub.md",
                frontmatter={"workflow": "x"},
                body="stub body",
                tokens=frozenset(),
            )]

    stub = StubRetriever()
    monkeypatch.setattr(ctx_mod, "context_retriever", stub)
    # The node imports `context_retriever` at module load. Patch the
    # reference in the node module too so we exercise the seam.
    from apps.api.runtime.nodes import context as ctx_node_mod
    monkeypatch.setattr(ctx_node_mod, "context_retriever", stub)

    spec = NodeSpec(id="ctx", type="context_retrieval", config={
        "workflow": "explore_city", "tags": ["cafes"], "limit": 3,
    })
    bus = EventBus(run_id="t", heartbeat_interval_s=60.0)
    execution = ExecutionContext(
        workflow_id="t", run_id="t", query="best cafes",
        events=bus,
    )
    node_ctx = NodeContext(execution=execution, spec=spec, inputs={})

    result = await ContextRetrievalNode(spec).execute(node_ctx)
    assert len(stub.calls) == 1
    assert stub.calls[0]["query"] == "best cafes"
    assert stub.calls[0]["limit"] == 3
    assert len(result["chunks"]) == 1


def test_markdown_retriever_load_returns_chunk_count(tmp_path):
    """Sanity check that the default retriever still loads markdown files."""
    (tmp_path / "test.md").write_text(
        "---\ncity: x\nworkflow: y\ntags: [a]\n---\nbody text",
        encoding="utf-8",
    )
    r = MarkdownRetriever()
    count = r.load(tmp_path)
    assert count == 1

    chunks = r.retrieve("body text", city="x")
    assert len(chunks) == 1
    assert chunks[0].body == "body text"
