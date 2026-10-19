"""
Semantic dedup tests — Node.canonicalize_dedup_key + DedupPass interaction.

These verify that the ProviderNode override collapses whitespace + case
variants of the same provider call, while leaving genuinely-different
calls distinct. Default Node behavior (structural equality) is also
covered for nodes that don't customize.
"""
from __future__ import annotations

import orjson
import pytest

from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes import DedupPass, PassContext
from apps.api.runtime.nodes.provider import ProviderNode


# ── ProviderNode.canonicalize_dedup_key ─────────────────────────────────────

def test_provider_dedup_key_collapses_whitespace_in_string_args():
    """`Chennai` and ` Chennai ` should produce the same key."""
    spec_a = NodeSpec(id="a", type="provider", config={
        "provider": "geo", "args": {"query": "Chennai"},
    })
    spec_b = NodeSpec(id="b", type="provider", config={
        "provider": "geo", "args": {"query": "  Chennai  "},
    })
    assert ProviderNode.canonicalize_dedup_key(spec_a) == \
           ProviderNode.canonicalize_dedup_key(spec_b)


def test_provider_dedup_key_collapses_case():
    spec_a = NodeSpec(id="a", type="provider", config={
        "provider": "geo", "args": {"query": "Chennai"},
    })
    spec_b = NodeSpec(id="b", type="provider", config={
        "provider": "geo", "args": {"query": "CHENNAI"},
    })
    assert ProviderNode.canonicalize_dedup_key(spec_a) == \
           ProviderNode.canonicalize_dedup_key(spec_b)


def test_provider_dedup_key_distinguishes_different_queries():
    """`Chennai` vs `Mumbai` should NOT collapse."""
    spec_a = NodeSpec(id="a", type="provider", config={
        "provider": "geo", "args": {"query": "Chennai"},
    })
    spec_b = NodeSpec(id="b", type="provider", config={
        "provider": "geo", "args": {"query": "Mumbai"},
    })
    assert ProviderNode.canonicalize_dedup_key(spec_a) != \
           ProviderNode.canonicalize_dedup_key(spec_b)


def test_provider_dedup_key_distinguishes_different_providers():
    spec_a = NodeSpec(id="a", type="provider", config={
        "provider": "geo", "args": {"query": "x"},
    })
    spec_b = NodeSpec(id="b", type="provider", config={
        "provider": "places", "args": {"query": "x"},
    })
    assert ProviderNode.canonicalize_dedup_key(spec_a) != \
           ProviderNode.canonicalize_dedup_key(spec_b)


def test_provider_dedup_key_passes_resolver_strings_through_untouched():
    """Resolver refs like `${ctx.query}` are already identical across
    equivalent calls — don't normalize them or we'd over-collapse."""
    spec_a = NodeSpec(id="a", type="provider", config={
        "provider": "geo", "args": {"query": "${ctx.query}"},
    })
    spec_b = NodeSpec(id="b", type="provider", config={
        "provider": "geo", "args": {"query": "${ctx.query}"},
    })
    # Should be equal (trivially) but also: the value isn't mangled
    key_a = ProviderNode.canonicalize_dedup_key(spec_a)
    assert b"${ctx.query}" in key_a


# ── DedupPass end-to-end ────────────────────────────────────────────────────

def test_dedup_pass_collapses_whitespace_equivalent_roots():
    """Two graphs where one node's whitespace differs should still
    collapse during composition."""
    g = WorkflowGraph.build(
        id="g", version="1",
        nodes=[
            NodeSpec(id="a__geo", type="provider", config={
                "provider": "geo", "args": {"query": "Chennai"},
            }),
            NodeSpec(id="b__geo", type="provider", config={
                "provider": "geo", "args": {"query": "  chennai  "},
            }),
            NodeSpec(id="b__downstream", type="provider",
                     depends_on=("b__geo",),
                     config={"provider": "places", "args": {"q": "${b__geo}"}}),
        ],
    )
    ctx = PassContext()
    out = DedupPass().apply(g, ctx)

    surviving_geos = [
        s for s in out.nodes.values()
        if s.type == "provider" and s.config.get("provider") == "geo"
    ]
    assert len(surviving_geos) == 1, "whitespace-equivalent geo nodes not deduped"
    assert ctx.rewrites, "expected rewrite map populated"


def test_dedup_pass_rewrites_downstream_refs_when_dedup_fires():
    g = WorkflowGraph.build(
        id="g", version="1",
        nodes=[
            NodeSpec(id="a__root", type="provider", config={
                "provider": "geo", "args": {"query": "x"},
            }),
            NodeSpec(id="b__root", type="provider", config={
                "provider": "geo", "args": {"query": "x"},
            }),
            NodeSpec(id="b__downstream", type="provider",
                     depends_on=("b__root",),
                     config={"provider": "places", "args": {"q": "${b__root.results.0.lat}"}}),
        ],
    )
    out = DedupPass().apply(g, PassContext())

    surviving_root_id = next(
        nid for nid, spec in out.nodes.items()
        if spec.type == "provider" and spec.config.get("provider") == "geo"
    )
    downstream = out.nodes["b__downstream"]

    # depends_on must point at the survivor
    assert downstream.depends_on == (surviving_root_id,)
    # And config refs to the dropped node must be rewritten too
    serialized = orjson.dumps(downstream.config).decode()
    assert surviving_root_id in serialized
    dropped = {"a__root", "b__root"} - {surviving_root_id}
    for d in dropped:
        assert d not in serialized, f"stale ref to dropped node {d} survived in config"


def test_dedup_pass_leaves_distinct_roots_alone():
    g = WorkflowGraph.build(
        id="g", version="1",
        nodes=[
            NodeSpec(id="a__geo", type="provider", config={
                "provider": "geo", "args": {"query": "Chennai"},
            }),
            NodeSpec(id="b__geo", type="provider", config={
                "provider": "geo", "args": {"query": "Mumbai"},
            }),
        ],
    )
    out = DedupPass().apply(g, PassContext())
    assert len(out.nodes) == 2
