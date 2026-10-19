"""
Knowledge retriever — public Retriever ABC + MarkdownRetriever implementation.

The `Retriever` ABC is the seam that lets future retrievers (vector,
hybrid, remote) slot in without changing the nodes that depend on it.
ContextRetrievalNode talks to the ABC; `MarkdownRetriever` (the in-tree
default) backs the singleton `context_retriever` used at startup.

`MarkdownRetriever` loads markdown-with-YAML-frontmatter from a directory
at process boot and serves O(N) facet-filtered + token-overlap retrieval.
It is NOT a vector store — it's structured, explainable retrieval ideal
for orchestration policy and city intel where determinism matters more
than recall.

Backwards-compat: `ContextRetriever` is preserved as an alias for
`MarkdownRetriever`; existing code that imported the concrete class
continues to work unchanged.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import yaml

from apps.api.core.logging import get_logger

logger = get_logger(__name__)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "for", "of", "in", "on", "at",
    "to", "from", "is", "are", "was", "were", "be", "been", "by", "with",
    "i", "me", "my", "you", "your", "we", "us", "our", "this", "that",
    "these", "those", "it", "its", "as", "near", "best", "good", "some",
    "any", "all",
})


@dataclass(frozen=True)
class KnowledgeChunk:
    path: str                          # relative to knowledge root, for tracing
    frontmatter: Dict[str, Any]
    body: str
    tokens: frozenset                  # cached token set for query overlap

    @property
    def city(self) -> Optional[str]:
        v = self.frontmatter.get("city")
        return str(v).lower() if v else None

    @property
    def workflow(self) -> Optional[str]:
        v = self.frontmatter.get("workflow")
        return str(v).lower() if v else None

    @property
    def tags(self) -> Set[str]:
        raw = self.frontmatter.get("tags") or []
        if isinstance(raw, str):
            raw = [raw]
        return {str(t).lower() for t in raw if t}

    @property
    def priority(self) -> int:
        p = self.frontmatter.get("priority")
        # accept "high"/"medium"/"low" or raw ints
        if isinstance(p, int):
            return p
        return {"high": 3, "medium": 2, "low": 1}.get(str(p).lower(), 0)

    def to_view(self) -> Dict[str, Any]:
        """Stable serialisable shape for downstream nodes / streams.

        Includes the full `frontmatter` dict so downstream workflows (e.g.
        checklist + plan) can read arbitrary metadata (`id`, `urgency`,
        `stage`, `household`, `deadline_days`, ...) without each new field
        needing a code change here.
        """
        return {
            "path": self.path,
            "city": self.city,
            "workflow": self.workflow,
            "tags": sorted(self.tags),
            "priority": self.priority,
            "body": self.body,
            "frontmatter": dict(self.frontmatter),
        }


def _tokenize(text: str) -> Set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w and w not in _STOPWORDS}


def _parse_file(path: Path, root: Path) -> Optional[KnowledgeChunk]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("knowledge.read_failed", path=str(path), error=str(e))
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        logger.warning("knowledge.missing_frontmatter", path=str(path))
        return None

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning("knowledge.bad_frontmatter", path=str(path), error=str(e))
        return None
    if not isinstance(frontmatter, dict):
        logger.warning("knowledge.frontmatter_not_dict", path=str(path))
        return None

    body = match.group(2).strip()
    rel = str(path.relative_to(root)).replace("\\", "/")
    tokens = _tokenize(body) | _tokenize(" ".join(str(v) for v in frontmatter.values()))

    return KnowledgeChunk(
        path=rel,
        frontmatter=frontmatter,
        body=body,
        tokens=frozenset(tokens),
    )


class Retriever(ABC):
    """
    Knowledge retriever interface.

    Implementations: `MarkdownRetriever` (in-tree, default). Future
    vector/hybrid retrievers should implement this same surface — the
    runtime nodes that consume retrieval (e.g. ContextRetrievalNode)
    depend on `Retriever`, not the concrete class, so swapping is a
    one-line monkeypatch in tests and a one-line registration in main.

    Implementations may be stateful (e.g. an in-memory corpus) but
    `retrieve()` MUST remain non-blocking from any async context. Heavy
    I/O belongs in `load()` or equivalent setup, called once.
    """
    @abstractmethod
    def retrieve(
        self,
        query: str,
        *,
        city: Optional[str] = None,
        workflow: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        limit: int = 5,
    ) -> List[KnowledgeChunk]:
        """Score chunks for the given query+facets and return top-N."""


class MarkdownRetriever(Retriever):
    def __init__(self) -> None:
        self._chunks: List[KnowledgeChunk] = []
        self._root: Optional[Path] = None

    def load(self, root: str | Path) -> int:
        root_path = Path(root)
        if not root_path.exists():
            logger.warning("knowledge.root_missing", path=str(root_path))
            self._chunks = []
            self._root = root_path
            return 0

        chunks: List[KnowledgeChunk] = []
        for path in sorted(root_path.rglob("*.md")):
            chunk = _parse_file(path, root_path)
            if chunk is not None:
                chunks.append(chunk)
        self._chunks = chunks
        self._root = root_path
        logger.info("knowledge.loaded", count=len(chunks), root=str(root_path))
        return len(chunks)

    def chunks(self) -> Iterable[KnowledgeChunk]:
        return iter(self._chunks)

    def retrieve(
        self,
        query: str,
        *,
        city: Optional[str] = None,
        workflow: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        limit: int = 5,
    ) -> List[KnowledgeChunk]:
        """
        Score chunks by (facet match, priority, query overlap) and return top-N.
        Pure CPU work; safe to call from any async context.
        """
        city_l = city.lower() if city else None
        workflow_l = workflow.lower() if workflow else None
        tag_set = {t.lower() for t in tags} if tags else set()
        query_tokens = _tokenize(query)

        scored: List[tuple[float, KnowledgeChunk]] = []
        for chunk in self._chunks:
            score = 0.0

            if city_l:
                # STRICT SCOPE (global correctness): when a city is requested,
                # never mix in chunks pinned to a DIFFERENT city. This is what
                # keeps destination-scoped relocation/essentials retrieval from
                # leaking irrelevant country-specific tasks (e.g. Aadhaar/TNEB
                # for a non-Chennai destination). City-less ("universal")
                # chunks always remain eligible.
                if chunk.city and chunk.city != city_l:
                    continue
                if chunk.city == city_l:
                    score += 5.0
            elif chunk.city:
                # No city requested: a chunk pinned to some city is never
                # the right answer (Boston's MBTA card for an unknown place).
                continue

            if workflow_l and chunk.workflow == workflow_l:
                score += 3.0

            if tag_set and chunk.tags & tag_set:
                score += 2.0 * len(chunk.tags & tag_set)

            score += chunk.priority * 0.5

            overlap = query_tokens & chunk.tokens
            score += len(overlap) * 0.75

            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]


# Backwards-compat alias: pre-refactor callers imported `ContextRetriever`.
ContextRetriever = MarkdownRetriever

# Singleton typed as the concrete class so startup can call `.load()`. Code
# that only retrieves (ContextRetrievalNode, future query-time consumers)
# should depend on `Retriever` instead — the ABC — to remain swappable.
context_retriever: MarkdownRetriever = MarkdownRetriever()
