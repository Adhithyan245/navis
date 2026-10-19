"""
ContractValidatePass — opt-in compile-time validation of NodeContract.

Walks every spec in the graph. For nodes whose registered class declares
a `contract`, runs validate_spec against the spec. Nodes without a
contract are silently skipped — this is the "side-by-side" migration
path: contracts add safety where declared, without forcing every node
to migrate at once.

Failures raise PassError so the composer fails fast at compile time
rather than at execution.
"""
from __future__ import annotations

from typing import Dict

from apps.api.core.logging import get_logger
from apps.api.runtime.contracts import ContractViolation, validate_spec
from apps.api.runtime.graph import WorkflowGraph
from apps.api.runtime.passes.base import GraphPass, PassContext, PassError
from apps.api.runtime.registry import NodeRegistry, node_registry

logger = get_logger(__name__)


class ContractValidatePass(GraphPass):
    name = "contract_validate"

    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self._registry = registry or node_registry

    def apply(self, graph: WorkflowGraph, ctx: PassContext) -> WorkflowGraph:
        # Collect emits_kind per node id so contracts that declare
        # requires_dep_kinds can be checked.
        kinds: Dict[str, str] = {}
        for spec in graph.nodes.values():
            try:
                node_cls = self._registry.resolve(spec.type)
            except Exception:
                continue
            if node_cls.contract is not None:
                kinds[spec.id] = node_cls.contract.emits_kind

        validated = 0
        for spec in graph.nodes.values():
            try:
                node_cls = self._registry.resolve(spec.type)
            except Exception:
                # Unregistered type — let the runtime fail at execution
                # with its own clearer error rather than here.
                continue

            contract = node_cls.contract
            if contract is None:
                continue

            try:
                validate_spec(spec, contract, dep_kinds=kinds)
            except ContractViolation as exc:
                raise PassError(str(exc)) from exc
            validated += 1

        if validated:
            logger.info("passes.contract_validate", validated=validated, total=len(graph.nodes))

        # Pass is pure-check; graph passes through unchanged.
        return graph
