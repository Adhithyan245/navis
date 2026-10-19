"""
WorkflowRegistry — load + cache compiled WorkflowGraphs by name.

At process startup, the app calls `workflow_registry.load_dir(path)` to
scan a directory of YAML/JSON workflow files. Each file's `workflow` (or
`id`) field becomes its lookup key. Routes then resolve workflows by
name in O(1) without re-parsing.

Re-loading is supported (and required when running tests that mutate the
workflows directory), but is not hot-reloaded automatically — the runtime
trusts that workflow definitions are stable during a process lifetime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

from apps.api.core.logging import get_logger
from apps.api.runtime.compiler.compile import CompilerError, compile_workflow
from apps.api.runtime.compiler.loader import load_definition
from apps.api.runtime.graph import WorkflowGraph

logger = get_logger(__name__)


class WorkflowNotFound(Exception):
    pass


class WorkflowRegistry:
    def __init__(self) -> None:
        self._graphs: Dict[str, WorkflowGraph] = {}

    def register(self, graph: WorkflowGraph) -> None:
        self._graphs[graph.id] = graph

    def get(self, name: str) -> WorkflowGraph:
        try:
            return self._graphs[name]
        except KeyError:
            known = ", ".join(sorted(self._graphs)) or "(none)"
            raise WorkflowNotFound(f"workflow {name!r} not registered. Known: {known}")

    def names(self) -> Iterable[str]:
        return sorted(self._graphs)

    def load_dir(self, path: str | Path) -> int:
        """Load every *.yaml / *.yml / *.json file in `path`. Returns the count."""
        root = Path(path)
        if not root.exists():
            logger.warning("workflow dir does not exist", path=str(root))
            return 0
        count = 0
        for f in sorted(root.iterdir()):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".yaml", ".yml", ".json"):
                continue
            try:
                data = load_definition(f)
                graph = compile_workflow(data)
            except CompilerError as e:
                logger.error("workflow compile failed", file=str(f), error=str(e))
                raise
            self.register(graph)
            count += 1
            logger.info("workflow registered", id=graph.id, version=graph.version, nodes=len(graph.nodes))
        return count

    def clear(self) -> None:
        self._graphs.clear()


workflow_registry = WorkflowRegistry()
