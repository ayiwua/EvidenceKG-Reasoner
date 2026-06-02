from __future__ import annotations

from typing import Any

from evidencekg.config.task_config import TaskConfig
from evidencekg.graph.graph_store import GraphStore


class EvidenceRetriever:
    def retrieve(self, candidate: dict[str, Any], config: TaskConfig, graph: GraphStore) -> dict[str, Any]:
        head = candidate["head"]
        tail = candidate["tail"]
        path_entities = sorted({entity for path in candidate.get("paths", []) for entity in path})
        query_entities = sorted({head, tail, *candidate.get("common_neighbors", []), *path_entities})
        related_triples = graph.get_triples_for_entities(query_entities)
        evidence = graph.get_evidence_for_entities(query_entities)

        for triple in related_triples:
            evidence.extend(graph.get_evidence_for_triple(triple["triple_id"]))

        deduped_evidence: dict[str, dict[str, Any]] = {}
        for item in evidence:
            deduped_evidence[item["evidence_id"]] = item

        return {
            "candidate_id": candidate["candidate_id"],
            "candidate": {
                "head": head,
                "relation": candidate["relation"],
                "tail": tail,
                "candidate_score": candidate.get("candidate_score", 0.0),
                "rule_scores": candidate.get("rule_scores", {}),
            },
            "head_profile": graph.get_entity(head) or {},
            "tail_profile": graph.get_entity(tail) or {},
            "graph_paths": candidate.get("paths", [])[: config.evidence_retrieval.max_paths],
            "common_neighbors": candidate.get("common_neighbors", []),
            "related_triples": related_triples if config.evidence_retrieval.include_related_triples else [],
            "evidence_snippets": list(deduped_evidence.values())[: config.evidence_retrieval.max_evidence_snippets],
        }
