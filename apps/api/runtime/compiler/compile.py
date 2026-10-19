"""
Workflow dict -> WorkflowGraph compiler.

Validates structure, builds NodeSpecs, and runs the graph's own
GraphValidationError checks (missing deps, cycles, duplicate ids).
"""
from __future__ import annotations

from typing import Any, Dict, List

from apps.api.runtime.graph import NodeSpec, WorkflowGraph


class CompilerError(Exception):
    pass


_REQUIRED_NODE_FIELDS = {"id", "type"}


def compile_workflow(data: Dict[str, Any]) -> WorkflowGraph:
    workflow_id = data.get("workflow") or data.get("id")
    if not workflow_id or not isinstance(workflow_id, str):
        raise CompilerError("workflow definition must set a string 'workflow' or 'id'")

    version = str(data.get("version", "0"))
    metadata = data.get("metadata", {}) or {}
    if not isinstance(metadata, dict):
        raise CompilerError(f"workflow {workflow_id!r}: 'metadata' must be a mapping")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise CompilerError(f"workflow {workflow_id!r}: 'nodes' must be a non-empty list")

    specs: List[NodeSpec] = []
    for idx, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise CompilerError(
                f"workflow {workflow_id!r}: node #{idx} must be a mapping, got {type(raw).__name__}"
            )
        missing = _REQUIRED_NODE_FIELDS - raw.keys()
        if missing:
            raise CompilerError(
                f"workflow {workflow_id!r}: node #{idx} missing required fields: {sorted(missing)}"
            )

        node_id = raw["id"]
        if not isinstance(node_id, str) or not node_id:
            raise CompilerError(f"workflow {workflow_id!r}: node #{idx} 'id' must be a non-empty string")

        type_name = raw["type"]
        if not isinstance(type_name, str) or not type_name:
            raise CompilerError(f"workflow {workflow_id!r}: node {node_id!r} 'type' must be a non-empty string")

        depends_on = raw.get("depends_on", []) or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
            raise CompilerError(
                f"workflow {workflow_id!r}: node {node_id!r} 'depends_on' must be a list of strings"
            )

        config = raw.get("config", {}) or {}
        if not isinstance(config, dict):
            raise CompilerError(f"workflow {workflow_id!r}: node {node_id!r} 'config' must be a mapping")

        retries = int(raw.get("retries", 0))
        retry_backoff_s = float(raw.get("retry_backoff_s", 0.5))
        timeout_s_raw = raw.get("timeout_s")
        timeout_s = float(timeout_s_raw) if timeout_s_raw is not None else None
        optional = bool(raw.get("optional", False))
        emits = raw.get("emits")
        if emits is not None and not isinstance(emits, str):
            raise CompilerError(f"workflow {workflow_id!r}: node {node_id!r} 'emits' must be a string")

        specs.append(NodeSpec(
            id=node_id,
            type=type_name,
            config=config,
            depends_on=tuple(depends_on),
            emits=emits,
            retries=retries,
            retry_backoff_s=retry_backoff_s,
            timeout_s=timeout_s,
            optional=optional,
        ))

    return WorkflowGraph.build(
        id=workflow_id,
        version=version,
        nodes=specs,
        metadata=metadata,
    )
