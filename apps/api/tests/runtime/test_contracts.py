"""
NodeContract tests — opt-in compile-time validation.

The contract layer is "side-by-side" with the string resolver: nodes
without a contract still work; nodes WITH one get their config validated
before execution. This test suite exercises the validator + the
ContractValidatePass that runs it during composition.
"""
from __future__ import annotations

import pytest

from apps.api.runtime.contracts import (
    ConfigField,
    ContractViolation,
    NodeContract,
    validate_spec,
)
from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes import ContractValidatePass, PassContext, PassError
from apps.api.runtime.registry import NodeRegistry
from apps.api.runtime.nodes.base import Node


# ── direct validate_spec tests ──────────────────────────────────────────────

def test_required_field_present_passes():
    contract = NodeContract(
        name="x", config_fields=(ConfigField("provider", required=True),),
    )
    spec = NodeSpec(id="n", type="x", config={"provider": "geo"})
    validate_spec(spec, contract)  # no raise


def test_missing_required_field_raises():
    contract = NodeContract(
        name="x", config_fields=(ConfigField("provider", required=True),),
    )
    spec = NodeSpec(id="n", type="x", config={})
    with pytest.raises(ContractViolation, match="requires config field 'provider'"):
        validate_spec(spec, contract)


def test_missing_optional_field_passes():
    contract = NodeContract(
        name="x", config_fields=(ConfigField("method", required=False),),
    )
    spec = NodeSpec(id="n", type="x", config={})
    validate_spec(spec, contract)  # no raise


def test_non_dict_config_rejected():
    contract = NodeContract(name="x", config_fields=(ConfigField("k"),))
    # NodeSpec.config has a default_factory of dict, so we have to manually
    # construct one with non-dict config to test the validator's defence:
    class _FakeSpec:
        id = "n"
        config = "not a dict"
        depends_on = ()
    with pytest.raises(ContractViolation, match="expects dict config"):
        validate_spec(_FakeSpec(), contract)


def test_requires_dep_kinds_satisfied():
    contract = NodeContract(
        name="ranker",
        requires_dep_kinds=("provider_response",),
    )
    spec = NodeSpec(id="rank", type="x", depends_on=("places",))
    validate_spec(spec, contract, dep_kinds={"places": "provider_response"})


def test_requires_dep_kinds_unsatisfied_raises():
    contract = NodeContract(
        name="ranker",
        requires_dep_kinds=("provider_response",),
    )
    spec = NodeSpec(id="rank", type="x", depends_on=("places",))
    with pytest.raises(ContractViolation, match="provider_response"):
        validate_spec(spec, contract, dep_kinds={"places": "knowledge_chunks"})


# ── ContractValidatePass tests ──────────────────────────────────────────────

class _StrictNode(Node):
    contract = NodeContract(
        name="strict",
        config_fields=(ConfigField("required_key", required=True),),
        emits_kind="strict_output",
    )
    async def execute(self, ctx):
        return None


class _PermissiveNode(Node):
    """No contract — should be skipped by the validator."""
    async def execute(self, ctx):
        return None


@pytest.fixture
def strict_registry():
    reg = NodeRegistry()
    reg.register("strict", _StrictNode)
    reg.register("permissive", _PermissiveNode)
    return reg


def test_contract_validate_pass_fails_fast_on_missing_field(strict_registry):
    graph = WorkflowGraph.build(
        id="g", version="1",
        nodes=[NodeSpec(id="n", type="strict", config={})],
    )
    pass_ = ContractValidatePass(registry=strict_registry)
    with pytest.raises(PassError, match="required_key"):
        pass_.apply(graph, PassContext())


def test_contract_validate_pass_lets_valid_graphs_through(strict_registry):
    graph = WorkflowGraph.build(
        id="g", version="1",
        nodes=[NodeSpec(id="n", type="strict", config={"required_key": "ok"})],
    )
    pass_ = ContractValidatePass(registry=strict_registry)
    out = pass_.apply(graph, PassContext())
    assert out is graph or out.nodes.keys() == graph.nodes.keys()


def test_contract_validate_pass_skips_contractless_nodes(strict_registry):
    graph = WorkflowGraph.build(
        id="g", version="1",
        nodes=[NodeSpec(id="n", type="permissive", config={"anything": 1})],
    )
    pass_ = ContractValidatePass(registry=strict_registry)
    # no raise — permissive has no contract so validation is a no-op
    pass_.apply(graph, PassContext())


def test_provider_node_contract_catches_missing_provider_key():
    """The real ProviderNode declares a contract requiring `provider`.
    A workflow that forgets to specify it should fail at compose time,
    not at execution."""
    from apps.api.runtime.compose import compose_graphs
    bad = WorkflowGraph.build(
        id="bad", version="1", metadata={"section_kind": "x"},
        nodes=[
            NodeSpec(id="p", type="provider", config={"args": {}}),  # no 'provider'!
            NodeSpec(id="s", type="stream", depends_on=("p",), config={}),
        ],
    )
    other = WorkflowGraph.build(
        id="other", version="1", metadata={"section_kind": "y"},
        nodes=[NodeSpec(id="s", type="stream", config={})],
    )
    with pytest.raises(PassError, match="provider"):
        compose_graphs([bad, other])
