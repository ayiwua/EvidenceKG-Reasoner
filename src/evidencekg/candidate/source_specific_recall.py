from __future__ import annotations

from evidencekg.candidate.base import RecallHit, RelationSpec
from evidencekg.graph.graph_store import GraphStore


class SourceSpecificRecall:
    source = "source_specific_rule"

    def score(self, head: str, tail: str, relation: RelationSpec, graph: GraphStore) -> RecallHit | None:
        hits: list[str] = []
        for evidence in graph.evidence_dict.values():
            related = set(evidence.get("related_entities", []))
            if head not in related or tail not in related:
                continue
            source = evidence.get("source", "")
            text = str(evidence.get("text", "")).lower()
            if relation.name == "owned_by" and source in {"ticket", "alert"}:
                hits.append(source)
            elif relation.name == "depends_on" and source == "service_dependency":
                hits.append(source)
            elif relation.name == "runs_on" and source in {"dns", "ticket", "alert"} and any(word in text for word in [" on ", "maps", "fired on"]):
                hits.append(source)
        if not hits:
            return None
        return RecallHit(min(0.75, 0.45 + 0.1 * len(hits)), self.source, {"source_hits": sorted(set(hits))})
