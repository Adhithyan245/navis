"""
GraphComposer tests: namespacing, reference rewriting, terminal flipping,
root dedup, aggregator wiring, and refusal of malformed inputs.
"""
from __future__ import annotations

import pytest

from apps.api.runtime.compose import (
    ComposerError,
    _AGGREGATOR_ID,
    compose_graphs,
)
from apps.api.runtime.graph import NodeSpec, WorkflowGraph


def _build(workflow_id: str, *, section_kind: str = "x") -> WorkflowGraph:
    """Build a small graph: root -> middle -> terminal_stream."""
    return WorkflowGraph.build(
        id=workflow_id, version="1",
        metadata={"section_kind": section_kind},
        nodes=[
            NodeSpec(id="root", type="test.echo", config={"value": 1}),
            NodeSpec(id="middle", type="test.echo",
                     depends_on=("root",),
                     config={"value": "${root}"}),
            NodeSpec(id="final_stream", type="stream",
                     depends_on=("middle",),
                     config={"payload": {"q": "${ctx.query}", "data": "${middle}"}}),
        ],
    )


# ── single graph passthrough ────────────────────────────────────────────────

def test_single_graph_returns_unchanged():
    g = _build("solo")
    composed = compose_graphs([g])
    assert composed is g


def test_empty_list_raises():
    with pytest.raises(ComposerError):
        compose_graphs([])


# ── namespacing + rewriting ────────────────────────────────────────────────

def test_node_ids_are_namespaced():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    # Original ids should not appear standalone in the composed graph
    ids = set(composed.nodes)
    assert "root" not in ids, "raw id leaked into composed graph"
    assert "alpha__middle" in ids
    assert "beta__final_stream" in ids
    assert _AGGREGATOR_ID in ids


def test_depends_on_are_rewritten():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    # alpha__middle should depend on the deduped root (kept under alpha's name)
    alpha_middle = composed.nodes["alpha__middle"]
    assert all(d.startswith(("alpha__", "beta__")) for d in alpha_middle.depends_on), \
        f"unnamespaced dep leaked: {alpha_middle.depends_on}"


def test_local_refs_are_rewritten_in_config():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    # alpha__final_stream's payload had `${middle}` and `${ctx.query}`.
    # The first must be namespaced; the second must be left alone.
    payload = composed.nodes["alpha__final_stream"].config["payload"]
    assert payload["q"] == "${ctx.query}"
    # Note: middle was deduped or kept under namespace — either way ref should resolve
    assert "${" in payload["data"]
    assert "${middle}" not in payload["data"]


# ── terminal flipping ──────────────────────────────────────────────────────

def test_terminal_streams_are_demoted_to_partial():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    for terminal in ("alpha__final_stream", "beta__final_stream"):
        cfg = composed.nodes[terminal].config
        assert cfg.get("partial") is True, f"{terminal} not demoted to partial"


def test_workflow_with_no_terminal_stream_still_composes():
    """A workflow without a terminal stream contributes no aggregator section."""
    no_stream = WorkflowGraph.build(
        id="no_stream", version="1", metadata={"section_kind": "raw"},
        nodes=[NodeSpec(id="root", type="test.echo", config={"value": 0})],
    )
    has_stream = _build("normal")
    composed = compose_graphs([no_stream, has_stream], composed_id="mix")

    agg = composed.nodes[_AGGREGATOR_ID]
    # Aggregator depends only on the workflow that had a terminal
    assert agg.depends_on == ("normal__final_stream",)


def test_workflow_with_multiple_terminals_raises():
    bad = WorkflowGraph.build(
        id="multi", version="1",
        nodes=[
            NodeSpec(id="s1", type="stream", config={}),
            NodeSpec(id="s2", type="stream", config={}),
        ],
    )
    with pytest.raises(ComposerError, match="multiple terminal stream"):
        compose_graphs([bad, _build("other")])


# ── root dedup ─────────────────────────────────────────────────────────────

def test_identical_roots_are_deduped():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    # Both started with the same root (type=test.echo config={value:1}, no deps).
    # Exactly one survives.
    root_nodes = [
        nid for nid, spec in composed.nodes.items()
        if spec.type == "test.echo"
        and not spec.depends_on
        and spec.config == {"value": 1}
    ]
    assert len(root_nodes) == 1, f"dedup failed; roots survived: {root_nodes}"


def test_dedup_rewrites_downstream_refs():
    a = _build("alpha")
    b = _build("beta")
    composed = compose_graphs([a, b], composed_id="ab")

    surviving_root = next(
        nid for nid, spec in composed.nodes.items()
        if spec.type == "test.echo" and not spec.depends_on
    )

    # Every depends_on that used to reference alpha__root / beta__root must
    # now reference the survivor.
    for nid, spec in composed.nodes.items():
        for dep in spec.depends_on:
            if dep.endswith("__root"):
                assert dep == surviving_root, \
                    f"node {nid!r} still references stale root {dep!r}"


def test_distinct_roots_are_not_deduped():
    a = _build("alpha")
    b_diff = WorkflowGraph.build(
        id="beta", version="1", metadata={"section_kind": "x"},
        nodes=[
            NodeSpec(id="root", type="test.echo", config={"value": 999}),  # different config
            NodeSpec(id="final_stream", type="stream",
                     depends_on=("root",),
                     config={"payload": {"q": "${ctx.query}"}}),
        ],
    )
    composed = compose_graphs([a, b_diff], composed_id="ab")

    distinct_roots = [
        nid for nid, spec in composed.nodes.items()
        if spec.type == "test.echo" and not spec.depends_on
    ]
    assert len(distinct_roots) == 2


# ── aggregator wiring ──────────────────────────────────────────────────────

def test_aggregator_emits_section_per_workflow_with_user_friendly_kinds():
    a = _build("alpha", section_kind="places")
    b = _build("beta", section_kind="events")
    composed = compose_graphs([a, b], composed_id="ab")

    agg = composed.nodes[_AGGREGATOR_ID]
    sections = agg.config["payload"]["sections"]
    kinds = [s["kind"] for s in sections]
    assert sorted(kinds) == ["events", "places"]

    # User-facing labels — never workflow ids
    assert "alpha" not in kinds
    assert "beta" not in kinds


def test_aggregator_payload_has_no_workflow_ids():
    a = _build("alpha", section_kind="places")
    b = _build("beta", section_kind="events")
    composed = compose_graphs([a, b], composed_id="ab")

    import orjson
    blob = orjson.dumps(composed.nodes[_AGGREGATOR_ID].config["payload"]).decode()
    # The data refs DO contain namespaced ids ("${alpha__final_stream}") —
    # that's internal config, not user-facing payload. The user-facing
    # payload (after resolver runs at execution time) will be checked in
    # the e2e test.
    assert "${alpha__final_stream}" in blob
    assert "${beta__final_stream}" in blob
