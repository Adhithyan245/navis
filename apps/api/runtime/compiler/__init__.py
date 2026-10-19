"""
Workflow compiler — turn YAML/JSON workflow definitions into WorkflowGraphs.

Typical usage:

    from apps.api.runtime.compiler import workflow_registry

    workflow_registry.load_dir("apps/api/workflows")
    graph = workflow_registry.get("explore_city")
"""
from apps.api.runtime.compiler.compile import compile_workflow, CompilerError
from apps.api.runtime.compiler.loader import load_definition
from apps.api.runtime.compiler.registry import WorkflowRegistry, workflow_registry

__all__ = [
    "compile_workflow",
    "CompilerError",
    "load_definition",
    "WorkflowRegistry",
    "workflow_registry",
]
