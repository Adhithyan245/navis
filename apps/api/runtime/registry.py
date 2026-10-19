"""
NodeRegistry — maps workflow-definition `type` strings to Node classes.

Nodes register themselves at import time. The runtime stays domain-agnostic;
this is the only seam where node implementations are looked up.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from apps.api.runtime.nodes.base import Node


class NodeRegistryError(Exception):
    pass


class NodeRegistry:
    def __init__(self) -> None:
        self._types: Dict[str, Type["Node"]] = {}

    def register(self, type_name: str, node_cls: Type["Node"]) -> None:
        if type_name in self._types:
            existing = self._types[type_name].__name__
            raise NodeRegistryError(
                f"node type {type_name!r} already registered to {existing}"
            )
        self._types[type_name] = node_cls

    def resolve(self, type_name: str) -> Type["Node"]:
        try:
            return self._types[type_name]
        except KeyError:
            known = ", ".join(sorted(self._types)) or "(none)"
            raise NodeRegistryError(
                f"unknown node type {type_name!r}. registered types: {known}"
            )

    def known_types(self) -> list[str]:
        return sorted(self._types)


node_registry = NodeRegistry()
