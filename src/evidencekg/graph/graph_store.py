from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

from evidencekg.io import read_jsonl


TOKEN_RE = re.compile(r"[^a-z0-9]+")


class GraphStore:
    """v2 JSONL-backed KG store with a NetworkX MultiDiGraph index."""

    def __init__(self) -> None:
        self.entity_dict: dict[str, dict[str, Any]] = {}
        self.triple_list: list[dict[str, Any]] = []
        self.triple_dict: dict[str, dict[str, Any]] = {}
        self.graph = nx.MultiDiGraph()
        self.evidence_dict: dict[str, dict[str, Any]] = {}
        self.entity_to_evidence: dict[str, list[str]] = defaultdict(list)
        self.entity_by_type: dict[str, list[str]] = defaultdict(list)
        self.relation_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.name_index: dict[str, list[str]] = defaultdict(list)
        self.alias_index: dict[str, list[str]] = defaultdict(list)
        self._triples_by_entity: dict[str, list[str]] = defaultdict(list)
        self._triples_by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.entities = self.entity_dict
        self.triples = self.triple_dict
        self.evidence = self.evidence_dict

    @classmethod
    def from_dir(cls, data_dir: str | Path) -> "GraphStore":
        root = Path(data_dir)
        store = cls()
        store.load_entities(root / "entities.jsonl")
        store.load_evidence(root / "evidence.jsonl")
        store.load_triples(root / "triples.jsonl")
        return store

    def load_entities(self, path: str | Path) -> None:
        for entity in read_jsonl(path):
            self._require_fields(entity, ["id", "type", "name", "aliases", "properties"], path)
            entity_id = entity["id"]
            if entity_id in self.entity_dict:
                raise ValueError(f"duplicate entity id: {entity_id}")
            self.entity_dict[entity_id] = entity
            self.entity_by_type[entity["type"]].append(entity_id)
            self.graph.add_node(entity_id, **entity)
            self._index_text(self.name_index, entity.get("name", ""), entity_id)
            for alias in entity.get("aliases", []):
                self._index_text(self.alias_index, str(alias), entity_id)

    def load_triples(self, path: str | Path) -> None:
        for triple in read_jsonl(path):
            self._require_fields(
                triple,
                ["id", "head", "relation", "tail", "source", "source_row_id", "confidence", "properties"],
                path,
            )
            triple_id = triple["id"]
            if triple_id in self.triple_dict:
                raise ValueError(f"duplicate triple id: {triple_id}")
            head = triple["head"]
            tail = triple["tail"]
            if head not in self.entity_dict:
                raise ValueError(f"triple {triple_id} references unknown head: {head}")
            if tail not in self.entity_dict:
                raise ValueError(f"triple {triple_id} references unknown tail: {tail}")
            self.triple_dict[triple_id] = triple
            self.triple_list.append(triple)
            self.relation_index[triple["relation"]].append((head, tail))
            self._triples_by_entity[head].append(triple_id)
            self._triples_by_entity[tail].append(triple_id)
            self._triples_by_pair[(head, tail)].append(triple_id)
            self.graph.add_edge(
                head,
                tail,
                key=triple_id,
                id=triple_id,
                relation=triple["relation"],
                source=triple["source"],
                confidence=triple["confidence"],
                properties=triple.get("properties", {}),
            )

    def load_evidence(self, path: str | Path) -> None:
        for evidence in read_jsonl(path):
            self._require_fields(
                evidence,
                ["id", "source", "source_file", "source_row_id", "text", "related_entities", "timestamp", "reliability", "metadata"],
                path,
            )
            evidence_id = evidence["id"]
            if evidence_id in self.evidence_dict:
                raise ValueError(f"duplicate evidence id: {evidence_id}")
            unknown = [entity_id for entity_id in evidence.get("related_entities", []) if entity_id not in self.entity_dict]
            if unknown:
                raise ValueError(f"evidence {evidence_id} references unknown entities: {unknown}")
            self.evidence_dict[evidence_id] = evidence
            for entity_id in evidence.get("related_entities", []):
                self.entity_to_evidence[entity_id].append(evidence_id)

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.entity_dict.get(entity_id)

    def get_entities_by_type(self, type_name: str) -> list[str]:
        return list(self.entity_by_type.get(type_name, []))

    def iter_entities_by_type(self, entity_types: list[str]) -> list[dict[str, Any]]:
        ids: list[str] = []
        for entity_type in entity_types:
            ids.extend(self.entity_by_type.get(entity_type, []))
        return [self.entity_dict[entity_id] for entity_id in ids]

    def iter_triples(self) -> list[dict[str, Any]]:
        return list(self.triple_list)

    def get_triple(self, triple_id: str) -> dict[str, Any] | None:
        return self.triple_dict.get(triple_id)

    def get_neighbors(self, entity_id: str, relation: str | None = None, direction: str = "both") -> list[str]:
        if entity_id not in self.graph:
            return []
        if direction not in {"both", "in", "out"}:
            raise ValueError(f"unsupported direction: {direction}")
        neighbors: set[str] = set()
        if direction in {"both", "out"}:
            for _, target, data in self.graph.out_edges(entity_id, data=True):
                if relation is None or data.get("relation") == relation:
                    neighbors.add(target)
        if direction in {"both", "in"}:
            for source, _, data in self.graph.in_edges(entity_id, data=True):
                if relation is None or data.get("relation") == relation:
                    neighbors.add(source)
        return sorted(neighbors)

    def get_shortest_path(self, head: str, tail: str, max_depth: int = 3) -> list[str]:
        if head not in self.graph or tail not in self.graph:
            return []
        undirected = nx.Graph()
        undirected.add_nodes_from(self.graph.nodes)
        undirected.add_edges_from((source, target) for source, target in self.graph.edges())
        try:
            path = nx.shortest_path(undirected, head, tail)
        except nx.NetworkXNoPath:
            return []
        return path if len(path) - 1 <= max_depth else []

    def find_paths(self, head: str, tail: str, max_hops: int, max_paths: int) -> list[list[str]]:
        if head not in self.graph or tail not in self.graph:
            return []
        undirected = nx.Graph()
        undirected.add_nodes_from(self.graph.nodes)
        undirected.add_edges_from((source, target) for source, target in self.graph.edges())
        paths: list[list[str]] = []
        try:
            for path in nx.all_simple_paths(undirected, head, tail, cutoff=max_hops):
                paths.append(path)
                if len(paths) >= max_paths:
                    break
        except nx.NetworkXNoPath:
            return []
        return paths

    def get_common_neighbors(self, head: str, tail: str) -> list[str]:
        return sorted(set(self.get_neighbors(head)) & set(self.get_neighbors(tail)))

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        return self.evidence_dict.get(evidence_id)

    def get_evidence_by_entity(self, entity_id: str) -> list[dict[str, Any]]:
        return [self.evidence_dict[eid] for eid in self.entity_to_evidence.get(entity_id, [])]

    def get_triples_between(self, head: str, tail: str, direction: str = "both") -> list[dict[str, Any]]:
        if direction not in {"both", "forward"}:
            raise ValueError(f"unsupported direction: {direction}")
        ids = list(self._triples_by_pair.get((head, tail), []))
        if direction == "both":
            ids.extend(self._triples_by_pair.get((tail, head), []))
        return [self.triple_dict[triple_id] for triple_id in ids]

    def get_triples_for_entities(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        for entity_id in entity_ids:
            seen.update(self._triples_by_entity.get(entity_id, []))
        return [self.triple_dict[triple_id] for triple_id in sorted(seen)]

    def get_related_triples(self, entity_id: str) -> list[dict[str, Any]]:
        return [self.triple_dict[triple_id] for triple_id in self._triples_by_entity.get(entity_id, [])]

    def has_edge(self, head: str, relation: str, tail: str) -> bool:
        return any(
            triple["head"] == head and triple["relation"] == relation and triple["tail"] == tail
            for triple in self.get_triples_between(head, tail, direction="forward")
        )

    def has_relation(self, head: str, relation: str, tail: str) -> bool:
        return self.has_edge(head, relation, tail)

    def search_entities(self, text: str) -> list[str]:
        token = self._normalize_text(text)
        return sorted(set(self.name_index.get(token, [])) | set(self.alias_index.get(token, [])))

    def _require_fields(self, record: dict[str, Any], fields: list[str], path: str | Path) -> None:
        missing = [field for field in fields if field not in record]
        if missing:
            raise ValueError(f"{path} record missing required fields {missing}: {record}")

    def _index_text(self, target: dict[str, list[str]], value: str, entity_id: str) -> None:
        if value:
            target[self._normalize_text(value)].append(entity_id)

    def _normalize_text(self, value: str) -> str:
        return TOKEN_RE.sub("_", str(value or "").strip().lower()).strip("_")
