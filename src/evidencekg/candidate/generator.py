from __future__ import annotations

from typing import Any

from evidencekg.config.task_config import TaskConfig
from evidencekg.graph.graph_store import GraphStore


class CandidateGenerator:
    def generate(self, config: TaskConfig, graph: GraphStore) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        heads = graph.iter_entities_by_type(config.allowed_head_types)
        tails = graph.iter_entities_by_type(config.allowed_tail_types)
        seen: set[tuple[str, str, str]] = set()

        for head in heads:
            for tail in tails:
                head_id = head["entity_id"]
                tail_id = tail["entity_id"]
                if head_id == tail_id:
                    continue
                if not config.is_allowed_pair(head["type"], tail["type"]):
                    continue
                if graph.has_relation(head_id, config.target_relation, tail_id):
                    continue

                rule_scores, paths, common_neighbors = self._score_pair(head_id, tail_id, config, graph)
                generation_rules = [name for name, score in rule_scores.items() if score > 0]
                if not generation_rules:
                    continue

                key = (head_id, config.target_relation, tail_id)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "candidate_id": f"c_{len(candidates) + 1:03d}",
                        "head": head_id,
                        "relation": config.target_relation,
                        "tail": tail_id,
                        "generation_rules": generation_rules,
                        "rule_scores": rule_scores,
                        "candidate_score": round(sum(rule_scores.values()), 3),
                        "paths": paths,
                        "common_neighbors": common_neighbors,
                    }
                )

        candidates.sort(key=lambda item: (-item["candidate_score"], item["candidate_id"]))
        for index, candidate in enumerate(candidates, start=1):
            candidate["candidate_id"] = f"c_{index:03d}"
        return candidates

    def _score_pair(
        self, head_id: str, tail_id: str, config: TaskConfig, graph: GraphStore
    ) -> tuple[dict[str, float], list[list[str]], list[str]]:
        rule_scores = {rule: 0.0 for rule in config.candidate_rules}
        max_hops = config.evidence_retrieval.max_hops
        max_paths = config.evidence_retrieval.max_paths
        paths = graph.find_paths(head_id, tail_id, max_hops=max_hops, max_paths=max_paths)

        if "two_hop_path" in rule_scores and paths:
            shortest = min(len(path) - 1 for path in paths)
            rule_scores["two_hop_path"] = 0.4 if shortest <= 2 else 0.25

        head_neighbors = set(graph.get_neighbors(head_id))
        tail_neighbors = set(graph.get_neighbors(tail_id))
        common_neighbors = sorted(head_neighbors & tail_neighbors)
        if "common_neighbor" in rule_scores and common_neighbors:
            rule_scores["common_neighbor"] = min(0.3, 0.15 + 0.05 * len(common_neighbors))

        if "evidence_overlap" in rule_scores:
            for evidence in graph.evidence.values():
                related = set(evidence.get("related_entities", []))
                if head_id in related and tail_id in related:
                    rule_scores["evidence_overlap"] = 0.2
                    break

        return ({key: round(value, 3) for key, value in rule_scores.items()}, paths, common_neighbors)
