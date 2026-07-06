from __future__ import annotations

import re

from evidencekg.candidate.base import RecallHit
from evidencekg.graph.graph_store import GraphStore


TOKEN_RE = re.compile(r"[a-z0-9]+")


class AttributeSimilarityRecall:
    source = "attribute_similarity"

    def score(self, head: str, tail: str, graph: GraphStore) -> RecallHit | None:
        head_tokens = self._tokens(graph.get_entity(head) or {})
        tail_tokens = self._tokens(graph.get_entity(tail) or {})
        if not head_tokens or not tail_tokens:
            return None
        overlap = sorted(head_tokens & tail_tokens)
        if not overlap:
            return None
        union = head_tokens | tail_tokens
        similarity = len(overlap) / len(union)
        return RecallHit(min(0.35, 0.1 + similarity), self.source, {"attribute_similarity": round(similarity, 4), "shared_tokens": overlap})

    def _tokens(self, entity: dict[str, object]) -> set[str]:
        parts: list[str] = [str(entity.get("id", "")), str(entity.get("name", ""))]
        parts.extend(str(item) for item in entity.get("aliases", []) if item)
        properties = entity.get("properties", {})
        if isinstance(properties, dict):
            parts.extend(str(value) for value in properties.values() if value)
        return set(TOKEN_RE.findall(" ".join(parts).lower())) - {"svc", "team", "app", "ip", "host", "prod"}
