"""
NodeContract — lightweight, declarative description of a node's config
shape + execution semantics.

Deliberately NOT a full type system. We don't try to statically validate
the resolver strings (e.g. that `${geo.results.0.lat}` will actually
yield a float at runtime) — that would require static analysis of the
upstream node's output, which side-by-side migration with the resolver
explicitly avoids.

What we DO catch at compile time:
  * required config fields are present
  * required deps (by node type) are declared
  * the contract itself is well-formed

Anything else (resolver string evaluation, runtime type compatibility)
remains a runtime concern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


class ContractViolation(Exception):
    """Raised when a NodeSpec fails its declared NodeContract."""


@dataclass(frozen=True)
class ConfigField:
    """One key in a node's config block."""
    name: str
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class NodeContract:
    """
    A node implementation's published contract. Compiler passes use it
    to validate WorkflowGraphs before execution.

    Fields:
      name              — human label for the contract (logging/errors only)
      config_fields     — required + optional keys in spec.config
      emits_kind        — semantic label for the node's output. Free-form
                          string ("provider_response", "ranked_list",
                          "stream_payload", "knowledge_chunks", ...). The
                          runtime does not interpret it today; it's surfaced
                          in traces and reserved for future contract-to-
                          contract compatibility checks.
      requires_dep_kinds — list of `emits_kind` values this node must have
                          at least one of among its declared deps. Empty
                          list means "no kind requirement" (any deps OK).
      streamable        — node emits PARTIAL_RESULT / FINAL_RESULT itself
      cancellation_safe — node tolerates asyncio.CancelledError without
                          leaving external state in a bad shape
      retry_safe        — node is idempotent enough to be retried on
                          failure without side-effects
    """
    name: str
    config_fields: Sequence[ConfigField] = ()
    emits_kind: str = "any"
    requires_dep_kinds: Sequence[str] = ()
    streamable: bool = False
    cancellation_safe: bool = True
    retry_safe: bool = True


def validate_spec(spec: Any, contract: NodeContract, dep_kinds: dict[str, str] | None = None) -> None:
    """
    Check a NodeSpec against a NodeContract. Raises ContractViolation on
    the first failure. `dep_kinds` maps dep_id -> emits_kind from upstream
    contracts; pass an empty dict if no upstream kind information is
    available (kind checks are skipped in that case).

    `spec` is a runtime.graph.NodeSpec but we accept Any here to avoid an
    import cycle; we only touch `.id`, `.config`, `.depends_on`.
    """
    cfg = getattr(spec, "config", None) or {}
    if not isinstance(cfg, dict):
        raise ContractViolation(
            f"node {spec.id!r}: contract {contract.name!r} expects dict config, "
            f"got {type(cfg).__name__}"
        )

    for field_ in contract.config_fields:
        if field_.required and field_.name not in cfg:
            raise ContractViolation(
                f"node {spec.id!r}: contract {contract.name!r} requires "
                f"config field {field_.name!r} (missing)"
            )

    if contract.requires_dep_kinds and dep_kinds:
        present_kinds = {
            dep_kinds[d] for d in getattr(spec, "depends_on", ()) if d in dep_kinds
        }
        missing = [k for k in contract.requires_dep_kinds if k not in present_kinds]
        if missing:
            raise ContractViolation(
                f"node {spec.id!r}: contract {contract.name!r} requires at least "
                f"one dependency of kind(s) {missing!r}; declared deps have kinds "
                f"{sorted(present_kinds)!r}"
            )
