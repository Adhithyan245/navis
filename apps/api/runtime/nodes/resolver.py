"""
Reference resolver for node configs.

Workflow YAML can reference upstream outputs and execution context via the
`${...}` syntax. The resolver walks a config tree and replaces any string
value matching `${path}` with the looked-up value.

Supported path roots
--------------------
  ${nodeid}                  - the full output of node `nodeid`
  ${nodeid.path.to.field}    - dotted path into the output (ints become list indices)
  ${ctx.query}               - execution query string
  ${ctx.user.<key>}          - execution.user_context[key]
  ${ctx.meta.<key>}          - execution.metadata[key]

Anything not matching `${...}` (or `${...}` mixed inside a larger string)
is returned as-is. Mixed interpolation (e.g. "near ${geo.name}") is NOT
supported in this iteration — references must be the entire string.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Sequence

from apps.api.runtime.context import NodeContext

_REF = re.compile(r"^\$\{([^}]+)\}$")


class ResolverError(Exception):
    pass


def resolve(value: Any, ctx: NodeContext) -> Any:
    """Recursively resolve `${...}` references inside dicts/lists/strings."""
    if isinstance(value, str):
        m = _REF.match(value)
        if not m:
            return value
        return _lookup(m.group(1), ctx)
    if isinstance(value, Mapping):
        return {k: resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
        out = [resolve(v, ctx) for v in value]
        return out if isinstance(value, list) else tuple(out)
    return value


def _lookup(path: str, ctx: NodeContext) -> Any:
    parts = path.split(".")
    head, *rest = parts

    if head == "ctx":
        if not rest:
            raise ResolverError("'${ctx}' requires a sub-path")
        section, *sub = rest
        if section == "query":
            base: Any = ctx.query
            sub_parts = sub
        elif section == "user":
            base = ctx.user_context
            sub_parts = sub
        elif section == "meta":
            base = ctx.execution.metadata
            sub_parts = sub
        else:
            raise ResolverError(f"unknown ctx section {section!r}")
        return _walk(base, sub_parts, original=path)

    # otherwise: upstream node reference
    dep_result = ctx.inputs.get(head)
    if dep_result is None:
        raise ResolverError(
            f"reference {path!r}: node {head!r} is not a declared dependency of {ctx.spec.id!r}"
        )
    if not dep_result.ok:
        # Don't raise — let nodes treat None as "upstream had no data"
        return None
    return _walk(dep_result.output, rest, original=path)


def _walk(obj: Any, parts: Sequence[str], *, original: str) -> Any:
    cur = obj
    for p in parts:
        if cur is None:
            return None
        if isinstance(cur, Mapping):
            cur = cur.get(p)
            continue
        if isinstance(cur, (list, tuple)):
            try:
                idx = int(p)
            except ValueError:
                raise ResolverError(
                    f"reference {original!r}: cannot index sequence with non-integer {p!r}"
                )
            cur = cur[idx] if -len(cur) <= idx < len(cur) else None
            continue
        # object attribute fallback (e.g. ProviderResponse)
        cur = getattr(cur, p, None)
    return cur
