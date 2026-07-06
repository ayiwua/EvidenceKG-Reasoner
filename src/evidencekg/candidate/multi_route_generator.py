from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evidencekg.candidate.attribute_similarity_recall import AttributeSimilarityRecall
from evidencekg.candidate.base import CandidateKey, RecallHit, RelationSpec
from evidencekg.candidate.common_neighbor_recall import CommonNeighborRecall
from evidencekg.candidate.evidence_cooccurrence_recall import EvidenceCooccurrenceRecall
from evidencekg.candidate.path_recall import PathRecall
from evidencekg.candidate.schema_recall import SchemaTypeRecall
from evidencekg.candidate.source_specific_recall import SourceSpecificRecall
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import write_jsonl


class MultiRouteCandidateGenerator:
    def __init__(self, relation_schema_path: str | Path) -> None:
        self.relations = self._load_relation_schema(relation_schema_path)
        self.schema_recall = SchemaTypeRecall()
        self.path_recall = PathRecall()
        self.common_neighbor_recall = CommonNeighborRecall()
        self.evidence_cooccurrence_recall = EvidenceCooccurrenceRecall()
        self.attribute_similarity_recall = AttributeSimilarityRecall()
        self.source_specific_recall = SourceSpecificRecall()

    def generate(self, graph: GraphStore) -> list[dict[str, Any]]:
        all_candidates: list[dict[str, Any]] = []
        for relation in self.relations:
            relation_candidates = self._generate_for_relation(graph, relation)
            all_candidates.extend(relation_candidates)
        for index, candidate in enumerate(all_candidates, start=1):
            candidate["candidate_id"] = f"cand_{index:06d}"
        return all_candidates

    def write(self, graph: GraphStore, out_path: str | Path) -> list[dict[str, Any]]:
        candidates = self.generate(graph)
        write_jsonl(out_path, candidates)
        return candidates

    def _generate_for_relation(self, graph: GraphStore, relation: RelationSpec) -> list[dict[str, Any]]:
        merged: dict[CandidateKey, dict[str, Any]] = {}
        heads = [entity_id for entity_type in relation.head_types for entity_id in graph.get_entities_by_type(entity_type)]
        tails = [entity_id for entity_type in relation.tail_types for entity_id in graph.get_entities_by_type(entity_type)]
        for head in heads:
            for tail in tails:
                if head == tail:
                    continue
                if not relation.allow_existing and graph.has_edge(head, relation.name, tail):
                    continue
                hits = self._route_hits(head, tail, relation, graph)
                if not hits:
                    continue
                key = (head, relation.name, tail)
                merged[key] = self._candidate_from_hits(key, hits)

        candidates = sorted(
            merged.values(),
            key=lambda item: (-item["candidate_score"], item["relation"], item["head"], item["tail"]),
        )
        return candidates[: relation.max_candidates]

    def _route_hits(self, head: str, tail: str, relation: RelationSpec, graph: GraphStore) -> list[RecallHit]:
        hits: list[RecallHit] = []
        routes = set(relation.recall_routes)
        if "schema_type" in routes:
            hits.append(self.schema_recall.score(head, tail, graph))
        if "path_rule" in routes:
            hit = self.path_recall.score(head, tail, relation, graph)
            if hit:
                hits.append(hit)
        if "common_neighbor" in routes:
            hit = self.common_neighbor_recall.score(head, tail, graph)
            if hit:
                hits.append(hit)
        if "evidence_cooccurrence" in routes:
            hit = self.evidence_cooccurrence_recall.score(head, tail, graph)
            if hit:
                hits.append(hit)
        if "attribute_similarity" in routes:
            hit = self.attribute_similarity_recall.score(head, tail, graph)
            if hit:
                hits.append(hit)
        if "source_specific_rule" in routes:
            hit = self.source_specific_recall.score(head, tail, relation, graph)
            if hit:
                hits.append(hit)
        return hits

    def _candidate_from_hits(self, key: CandidateKey, hits: list[RecallHit]) -> dict[str, Any]:
        head, relation, tail = key
        debug: dict[str, Any] = {}
        for hit in hits:
            debug.update(hit.debug)
        return {
            "candidate_id": "",
            "head": head,
            "relation": relation,
            "tail": tail,
            "candidate_score": round(sum(hit.score for hit in hits), 4),
            "recall_sources": [hit.source for hit in hits],
            "debug": debug,
        }

    def _load_relation_schema(self, path: str | Path) -> list[RelationSpec]:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        relations = payload.get("relations")
        if not isinstance(relations, list) or not relations:
            raise ValueError("relation schema must contain a non-empty relations list")
        return [RelationSpec.from_dict(item) for item in relations]
