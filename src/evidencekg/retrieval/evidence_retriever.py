from __future__ import annotations

import math
import re
from typing import Any

from evidencekg.config.task_config import EvidenceRetrievalConfig, TaskConfig
from evidencekg.graph.graph_store import GraphStore


TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


class EvidenceRetriever:
    """Two-stage graph-aware evidence retrieval.

    The graph is used to build a rich candidate query and context. Evidence
    selection itself is dense retrieval followed by cross-encoder reranking.
    """

    def __init__(self) -> None:
        self._bi_encoders: dict[str, Any] = {}
        self._cross_encoders: dict[str, Any] = {}
        self._corpus_cache: dict[tuple[int, str], dict[str, Any]] = {}

    def retrieve(self, candidate: dict[str, Any], config: TaskConfig, graph: GraphStore) -> dict[str, Any]:
        head = candidate["head"]
        tail = candidate["tail"]
        path_entities = sorted({entity for path in candidate.get("paths", []) for entity in path})
        query_entities = sorted({head, tail, *candidate.get("common_neighbors", []), *path_entities})
        related_triples = graph.get_triples_for_entities(query_entities)
        retrieval_config = config.evidence_retrieval
        retrieval_query = self._build_candidate_query(candidate, related_triples, graph)
        evidence_snippets = self._retrieve_evidence_snippets(retrieval_query, retrieval_config, graph)

        return {
            "candidate_id": candidate["candidate_id"],
            "candidate": {
                "head": head,
                "relation": candidate["relation"],
                "tail": tail,
                "candidate_score": candidate.get("candidate_score", 0.0),
                "rule_scores": candidate.get("rule_scores", {}),
            },
            "head_profile": (graph.get_entity(head) or {}) if retrieval_config.include_entity_profiles else {},
            "tail_profile": (graph.get_entity(tail) or {}) if retrieval_config.include_entity_profiles else {},
            "graph_paths": candidate.get("paths", [])[: retrieval_config.max_paths]
            if retrieval_config.include_graph_paths
            else [],
            "common_neighbors": candidate.get("common_neighbors", [])
            if retrieval_config.include_common_neighbors
            else [],
            "related_triples": related_triples if retrieval_config.include_related_triples else [],
            "evidence_snippets": evidence_snippets,
        }

    def _retrieve_evidence_snippets(
        self, retrieval_query: str, config: EvidenceRetrievalConfig, graph: GraphStore
    ) -> list[dict[str, Any]]:
        corpus = self._get_or_build_corpus(config, graph)
        if not corpus["evidence_ids"]:
            return []

        bi_encoder = self._get_bi_encoder(config.bi_encoder_model)
        query_embedding = self._first_vector(bi_encoder.encode([retrieval_query]))
        embedding_scores = [
            self._cosine_similarity(query_embedding, evidence_embedding)
            for evidence_embedding in corpus["evidence_embeddings"]
        ]
        top_before = max(1, min(config.top_k_before_rerank, len(embedding_scores)))
        recalled = sorted(
            enumerate(embedding_scores),
            key=lambda item: (-item[1], corpus["evidence_ids"][item[0]]),
        )[:top_before]

        cross_encoder = self._get_cross_encoder(config.cross_encoder_model)
        pairs = [(retrieval_query, corpus["evidence_texts"][index]) for index, _ in recalled]
        rerank_scores = self._as_score_list(cross_encoder.predict(pairs))
        ranked = sorted(
            zip(recalled, rerank_scores),
            key=lambda item: (-float(item[1]), -float(item[0][1]), corpus["evidence_ids"][item[0][0]]),
        )

        top_after = max(1, min(config.top_k_after_rerank, config.max_evidence_snippets, len(ranked)))
        snippets: list[dict[str, Any]] = []
        for rank, ((index, embedding_score), rerank_score) in enumerate(ranked[:top_after], start=1):
            evidence_id = corpus["evidence_ids"][index]
            evidence = graph.get_evidence(evidence_id)
            if not evidence:
                continue
            snippet = dict(evidence)
            snippet["embedding_score"] = round(float(embedding_score), 6)
            snippet["rerank_score"] = round(float(rerank_score), 6)
            snippet["retrieval_query"] = retrieval_query
            snippet["retrieval_rank"] = rank
            snippets.append(snippet)
        return snippets

    def _get_or_build_corpus(self, config: EvidenceRetrievalConfig, graph: GraphStore) -> dict[str, Any]:
        cache_key = (id(graph), config.bi_encoder_model)
        cached = self._corpus_cache.get(cache_key)
        if cached:
            return cached

        evidence_ids: list[str] = []
        evidence_texts: list[str] = []
        for evidence in graph.evidence.values():
            evidence_ids.append(evidence["evidence_id"])
            evidence_texts.append(self._build_evidence_text(evidence, graph))

        bi_encoder = self._get_bi_encoder(config.bi_encoder_model)
        evidence_embeddings = self._as_vectors(bi_encoder.encode(evidence_texts)) if evidence_texts else []
        corpus = {
            "evidence_ids": evidence_ids,
            "evidence_texts": evidence_texts,
            "evidence_embeddings": evidence_embeddings,
        }
        self._corpus_cache[cache_key] = corpus
        return corpus

    def _get_bi_encoder(self, model_name: str) -> Any:
        cached = self._bi_encoders.get(model_name)
        if cached:
            return cached
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(model_name)
        self._bi_encoders[model_name] = encoder
        return encoder

    def _get_cross_encoder(self, model_name: str) -> Any:
        cached = self._cross_encoders.get(model_name)
        if cached:
            return cached
        from sentence_transformers import CrossEncoder

        encoder = CrossEncoder(model_name)
        self._cross_encoders[model_name] = encoder
        return encoder

    def _build_evidence_text(self, evidence: dict[str, Any], graph: GraphStore) -> str:
        related_entities = evidence.get("related_entities", [])
        related_text = " ".join(self._entity_text(entity_id, graph) for entity_id in related_entities)
        parts = [
            "evidence",
            evidence.get("text", ""),
            "source",
            evidence.get("source", ""),
            "related entities",
            " ".join(str(entity_id) for entity_id in related_entities),
            related_text,
            "timestamp",
            evidence.get("timestamp", ""),
            "reliability",
            evidence.get("reliability", ""),
        ]
        return " ".join(str(part) for part in parts if part not in (None, ""))

    def _build_candidate_query(
        self, candidate: dict[str, Any], related_triples: list[dict[str, Any]], graph: GraphStore
    ) -> str:
        path_summaries = [self._path_summary(path, graph) for path in candidate.get("paths", [])]
        common_neighbors = " ".join(
            self._entity_text(entity_id, graph) for entity_id in candidate.get("common_neighbors", [])
        )
        related_triple_text = " ".join(self._triple_text(triple, graph) for triple in related_triples)
        parts = [
            "Find evidence supporting this candidate relation.",
            "target relation",
            candidate["relation"],
            "head entity",
            self._entity_text(candidate["head"], graph),
            "tail entity",
            self._entity_text(candidate["tail"], graph),
            "common neighbors",
            common_neighbors,
            "graph paths",
            " ".join(path_summaries),
            "related triples",
            related_triple_text,
        ]
        return " ".join(str(part) for part in parts if part)

    def _path_summary(self, path: list[str], graph: GraphStore) -> str:
        pieces: list[str] = []
        for index, entity_id in enumerate(path):
            pieces.append(self._entity_text(entity_id, graph))
            if index < len(path) - 1:
                relations = sorted(
                    {
                        triple["relation"]
                        for triple in graph.get_triples_between(entity_id, path[index + 1])
                    }
                )
                if relations:
                    pieces.append("relations " + " ".join(relations))
        return " path ".join(pieces)

    def _triple_text(self, triple: dict[str, Any], graph: GraphStore) -> str:
        return " ".join(
            [
                self._entity_text(triple.get("head", ""), graph),
                str(triple.get("relation", "")),
                self._entity_text(triple.get("tail", ""), graph),
                "source",
                str(triple.get("source", "")),
            ]
        )

    def _entity_text(self, entity_id: str, graph: GraphStore) -> str:
        entity = graph.get_entity(entity_id) or {}
        attributes = entity.get("attributes", {})
        attribute_text = " ".join(f"{key} {value}" for key, value in sorted(attributes.items()))
        return " ".join(
            str(part)
            for part in [
                entity_id,
                entity.get("name", ""),
                entity.get("type", ""),
                entity.get("description", ""),
                attribute_text,
            ]
            if part
        )

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in TOKEN_RE.findall(text.lower()):
            tokens.append(token)
            for subtoken in re.split(r"[_./:-]+", token):
                if subtoken and subtoken != token:
                    tokens.append(subtoken)
        return tokens

    def _as_vectors(self, values: Any) -> list[list[float]]:
        if hasattr(values, "tolist"):
            values = values.tolist()
        return [[float(item) for item in vector] for vector in values]

    def _first_vector(self, values: Any) -> list[float]:
        return self._as_vectors(values)[0]

    def _as_score_list(self, values: Any) -> list[float]:
        if hasattr(values, "tolist"):
            values = values.tolist()
        return [float(value) for value in values]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

