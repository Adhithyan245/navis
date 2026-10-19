"""
Node + graph contracts (side-by-side with the string resolver).

The runtime continues to support `${node.path}` resolver-based wiring for
existing nodes and workflows. New nodes can additionally declare a
`NodeContract` describing required config keys, emitted output shape, and
execution semantics (cancellation-safe, retry-safe, streamable).

The ContractValidatePass uses these declarations to fail-fast at compile
time when a workflow misconfigures a node. Nodes without a contract are
unaffected. This is an additive seam, not a replacement.
"""
from apps.api.runtime.contracts.node import (
    ConfigField,
    ContractViolation,
    NodeContract,
    validate_spec,
)

__all__ = [
    "ConfigField",
    "ContractViolation",
    "NodeContract",
    "validate_spec",
]
