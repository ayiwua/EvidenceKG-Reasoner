from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import networkx as nx

from evidencekg.io import read_jsonl


class GraphStore:
    """JSONL-backed KG store with a MultiDiGraph structural index."""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()
        self.entities: dict[str, dict[str, Any]] = {}
        self.triples: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}
        self._triples_by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._triples_by_entity: dict[str, list[str]] = defaultdict(list)
        self._evidence_by_entity: dict[str, list[str]] = defaultdict(list)

    @classmethod
    def from_dir(cls, data_dir: str | Path) -> "GraphStore":
        store = cls()
        root = Path(data_dir)
        store.load_entities(root / "entities.jsonl")
        store.load_evidence(root / "evidence.jsonl")
        store.load_triples(root / "triples.jsonl")
        return store

    def load_entities(self, path: str | Path) -> None:
        for entity in read_jsonl(path):
            entity_id = entity["entity_id"]
            self.entities[entity_id] = entity
            self.graph.add_node(entity_id)

    def load_triples(self, path: str | Path) -> None:
        for triple in read_jsonl(path):
            triple_id = triple["triple_id"]
            head = triple["head"]
            tail = triple["tail"]
            self.triples[triple_id] = triple
            self.graph.add_edge(head, tail, key=triple_id, triple_id=triple_id, relation=triple["relation"])
            self._triples_by_pair[(head, tail)].append(triple_id)
            self._triples_by_entity[head].append(triple_id)
            self._triples_by_entity[tail].append(triple_id)

    def load_evidence(self, path: str | Path) -> None:
        for evidence in read_jsonl(path):
            evidence_id = evidence["evidence_id"]
            self.evidence[evidence_id] = evidence
            for entity_id in evidence.get("related_entities", []):
                self._evidence_by_entity[entity_id].append(evidence_id)

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.entities.get(entity_id)

    def iter_entities_by_type(self, entity_types: list[str]) -> list[dict[str, Any]]:
        wanted = set(entity_types)
        return [entity for entity in self.entities.values() if entity.get("type") in wanted]

    def iter_triples(self) -> list[dict[str, Any]]:
        return list(self.triples.values())

    def get_triple(self, triple_id: str) -> dict[str, Any] | None:
        return self.triples.get(triple_id)

    def get_triples_between(self, head: str, tail: str) -> list[dict[str, Any]]:
        ids = self._triples_by_pair.get((head, tail), []) + self._triples_by_pair.get((tail, head), [])
        return [self.triples[triple_id] for triple_id in ids]

    def get_triples_for_entities(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        for entity_id in entity_ids:
            seen.update(self._triples_by_entity.get(entity_id, []))
        return [self.triples[triple_id] for triple_id in sorted(seen)]

    def get_related_triples(self, entity_id: str) -> list[dict[str, Any]]:
        return [self.triples[triple_id] for triple_id in self._triples_by_entity.get(entity_id, [])]

    def has_relation(self, head: str, relation: str, tail: str) -> bool:
        return any(triple["relation"] == relation for triple in self.get_triples_between(head, tail))

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        return self.evidence.get(evidence_id)

    def get_evidence_for_triple(self, triple_id: str) -> list[dict[str, Any]]:
        triple = self.get_triple(triple_id)
        if not triple:
            return []
        return [self.evidence[eid] for eid in triple.get("evidence_ids", []) if eid in self.evidence]

    def get_evidence_for_entities(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(entity_ids)
        scored: dict[str, tuple[int, dict[str, Any]]] = {}
        for evidence in self.evidence.values():
            related = set(evidence.get("related_entities", []))
            overlap = len(wanted & related)
            if overlap:
                scored[evidence["evidence_id"]] = (overlap, evidence)
        return [item for _, item in sorted(scored.values(), key=lambda pair: (-pair[0], pair[1]["evidence_id"]))]

    def get_neighbors(self, entity_id: str) -> list[str]:
        if entity_id not in self.graph:
            return []
        neighbors = set(self.graph.successors(entity_id)) | set(self.graph.predecessors(entity_id))
        return sorted(neighbors)

    def find_paths(self, head: str, tail: str, max_hops: int, max_paths: int) -> list[list[str]]:
        if head not in self.graph or tail not in self.graph:
            return []
        undirected = nx.Graph()
        undirected.add_nodes_from(self.graph.nodes)
        undirected.add_edges_from((u, v) for u, v in self.graph.edges())
        results: list[list[str]] = []
        queue: deque[list[str]] = deque([[head]])
        while queue and len(results) < max_paths:
            path = queue.popleft()
            if len(path) - 1 >= max_hops:
                continue
            for neighbor in sorted(undirected.neighbors(path[-1])):
                if neighbor in path:
                    continue
                next_path = path + [neighbor]
                if neighbor == tail:
                    results.append(next_path)
                    if len(results) >= max_paths:
                        break
                else:
                    queue.append(next_path)
        return results
