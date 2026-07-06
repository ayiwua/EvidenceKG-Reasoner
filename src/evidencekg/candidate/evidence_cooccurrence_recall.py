from __future__ import annotations

from evidencekg.candidate.base import RecallHit
from evidencekg.graph.graph_store import GraphStore


class EvidenceCooccurrenceRecall:
    source = "evidence_cooccurrence"

    def score(self, head: str, tail: str, graph: GraphStore) -> RecallHit | None:
        evidence_ids: list[str] = []
        for evidence in graph.evidence_dict.values():
            related = set(evidence.get("related_entities", []))
            if head in related and tail in related:
                evidence_ids.append(evidence["id"])
        if not evidence_ids:
            return None
        return RecallHit(
            min(0.5, 0.18 + 0.08 * len(evidence_ids)),
            self.source,
            {"shared_evidence_count": len(evidence_ids), "shared_evidence_ids": evidence_ids[:8]},
        )
