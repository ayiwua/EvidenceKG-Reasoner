from __future__ import annotations

import re
import math
from typing import Any

from evidencekg.candidate.base import RelationSpec
from evidencekg.graph.graph_store import GraphStore


TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
CONFLICT_WORDS = {"not", "no", "without", "unknown", "unassigned", "unowned"}


class EvidenceRetriever:
    """Relation-aware graph evidence retrieval for v2 candidates."""

    def __init__(
        self,
        enable_dense: bool = False,
        bi_encoder_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        self.enable_dense = enable_dense
        self.bi_encoder_model = bi_encoder_model
        self.cross_encoder_model = cross_encoder_model
        self._bi_encoder: Any | None = None
        self._cross_encoder: Any | None = None
        self._corpus_cache: dict[int, dict[str, Any]] = {}

    def retrieve(
        self,
        candidate: dict[str, Any],
        relation: RelationSpec,
        graph: GraphStore,
        top_k: int = 5,
        allow_keyword_only: bool = False,
    ) -> dict[str, Any]:
        if not self.enable_dense and not allow_keyword_only:
            raise RuntimeError(
                "dense retrieval is not configured in this local build; pass allow_keyword_only=True "
                "to run explicit degraded keyword-only retrieval"
            )
        query = self._build_relation_query(candidate, relation, graph)
        ranked = (
            self._hybrid_dense_rank(candidate, relation, query, graph, top_k=max(top_k * 4, 20))
            if self.enable_dense
            else self._keyword_rank(candidate, relation, query, graph)
        )
        initial = ranked[:top_k]
        expanded = self._expand_evidence(initial, graph, top_k=top_k)
        support, conflict = self._split_support_conflict(candidate, relation, expanded)

        return {
            "candidate_id": candidate["candidate_id"],
            "candidate": {
                "head": candidate["head"],
                "relation": candidate["relation"],
                "tail": candidate["tail"],
                "candidate_score": candidate.get("candidate_score", 0.0),
                "recall_sources": candidate.get("recall_sources", []),
                "debug": candidate.get("debug", {}),
            },
            "relation_query": query,
            "retrieval_metadata": {
                "mode": "hybrid_dense_cross_encoder" if self.enable_dense else "keyword_only",
                "degraded": False if self.enable_dense else True,
                "fallback_reason": "" if self.enable_dense else "keyword_only_explicitly_enabled_for_smoke",
                "bi_encoder_model": self.bi_encoder_model if self.enable_dense else "",
                "cross_encoder_model": self.cross_encoder_model if self.enable_dense else "",
                "preferred_sources": relation.preferred_sources,
                "top_k": top_k,
                "initial_evidence_count": len(initial),
                "expanded_evidence_count": len(expanded),
            },
            "head_profile": graph.get_entity(candidate["head"]) or {},
            "tail_profile": graph.get_entity(candidate["tail"]) or {},
            "graph_path": graph.get_shortest_path(candidate["head"], candidate["tail"], max_depth=3),
            "supporting_evidence_candidates": support,
            "conflict_evidence_candidates": conflict,
            "packed_context": self._pack_context(candidate, relation, graph, support, conflict),
        }

    def _hybrid_dense_rank(
        self,
        candidate: dict[str, Any],
        relation: RelationSpec,
        query: str,
        graph: GraphStore,
        top_k: int,
    ) -> list[dict[str, Any]]:
        keyword_rows = self._keyword_rank(candidate, relation, query, graph)
        keyword_by_id = {item["id"]: item for item in keyword_rows}
        corpus = self._get_or_build_dense_corpus(graph)
        if not corpus["evidence_ids"]:
            return []
        query_embedding = self._first_vector(self._get_bi_encoder().encode([query]))
        dense_scores = [
            self._cosine_similarity(query_embedding, evidence_embedding)
            for evidence_embedding in corpus["evidence_embeddings"]
        ]
        recalled = sorted(
            enumerate(dense_scores),
            key=lambda item: (-item[1], corpus["evidence_ids"][item[0]]),
        )[:top_k]
        pairs = [(query, corpus["evidence_texts"][index]) for index, _ in recalled]
        rerank_scores = self._as_score_list(self._get_cross_encoder().predict(pairs))
        ranked: list[dict[str, Any]] = []
        for (index, dense_score), rerank_score in zip(recalled, rerank_scores):
            evidence_id = corpus["evidence_ids"][index]
            evidence = dict(graph.evidence_dict[evidence_id])
            keyword_score = float(keyword_by_id.get(evidence_id, {}).get("retrieval_score", 0.0))
            evidence["retrieval_score"] = round(float(rerank_score) + dense_score + keyword_score, 4)
            evidence["dense_score"] = round(float(dense_score), 6)
            evidence["rerank_score"] = round(float(rerank_score), 6)
            evidence["retrieval_reasons"] = keyword_by_id.get(evidence_id, {}).get("retrieval_reasons", []) + [
                "dense_recall",
                "cross_encoder_rerank",
            ]
            ranked.append(evidence)
        return sorted(ranked, key=lambda item: (-float(item["retrieval_score"]), item["id"]))

    def _keyword_rank(
        self,
        candidate: dict[str, Any],
        relation: RelationSpec,
        query: str,
        graph: GraphStore,
    ) -> list[dict[str, Any]]:
        query_tokens = set(self._tokenize(query))
        ranked: list[dict[str, Any]] = []
        for evidence in graph.evidence_dict.values():
            text = self._evidence_text(evidence, graph)
            text_tokens = set(self._tokenize(text))
            related = set(evidence.get("related_entities", []))
            overlap = len(query_tokens & text_tokens)
            score = float(overlap) * 0.08
            if candidate["head"] in related:
                score += 1.0
            if candidate["tail"] in related:
                score += 1.0
            if evidence.get("source") in relation.preferred_sources:
                score += 0.35
            score += float(evidence.get("reliability", 0.0)) * 0.2
            if score <= 0:
                continue
            item = dict(evidence)
            item["retrieval_score"] = round(score, 4)
            item["retrieval_reasons"] = self._retrieval_reasons(candidate, relation, evidence)
            ranked.append(item)
        return sorted(ranked, key=lambda item: (-item["retrieval_score"], item["id"]))

    def _expand_evidence(self, initial: list[dict[str, Any]], graph: GraphStore, top_k: int) -> list[dict[str, Any]]:
        by_id = {item["id"]: dict(item) for item in initial}
        for evidence in initial:
            for entity_id in evidence.get("related_entities", []):
                for expanded in graph.get_evidence_by_entity(entity_id):
                    if expanded["id"] in by_id:
                        continue
                    item = dict(expanded)
                    item["retrieval_score"] = round(float(evidence.get("retrieval_score", 0.0)) * 0.6, 4)
                    item["retrieval_reasons"] = ["expanded_from_related_entity", entity_id]
                    by_id[item["id"]] = item
                    if len(by_id) >= top_k * 2:
                        break
                if len(by_id) >= top_k * 2:
                    break
            if len(by_id) >= top_k * 2:
                break
        return sorted(by_id.values(), key=lambda item: (-float(item.get("retrieval_score", 0.0)), item["id"]))

    def _split_support_conflict(
        self,
        candidate: dict[str, Any],
        relation: RelationSpec,
        evidence_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        support: list[dict[str, Any]] = []
        conflict: list[dict[str, Any]] = []
        for evidence in evidence_rows:
            text_tokens = set(self._tokenize(evidence.get("text", "")))
            related = set(evidence.get("related_entities", []))
            item = self._context_evidence(evidence)
            if CONFLICT_WORDS & text_tokens:
                conflict.append(item)
            elif candidate["head"] in related or candidate["tail"] in related:
                item["support_hint"] = self._support_hint(candidate, relation, evidence)
                support.append(item)
        return support, conflict

    def _build_relation_query(self, candidate: dict[str, Any], relation: RelationSpec, graph: GraphStore) -> str:
        head_text = self._entity_text(candidate["head"], graph)
        tail_text = self._entity_text(candidate["tail"], graph)
        return " ".join(
            [
                relation.name,
                relation.description,
                relation.prompt_guidance,
                relation.semantic_verification_criteria,
                "head",
                head_text,
                "tail",
                tail_text,
                "preferred sources",
                " ".join(relation.preferred_sources),
            ]
        )

    def _pack_context(
        self,
        candidate: dict[str, Any],
        relation: RelationSpec,
        graph: GraphStore,
        support: list[dict[str, Any]],
        conflict: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "task": "verify_candidate_relation",
            "relation": relation.name,
            "semantic_criteria": relation.semantic_verification_criteria,
            "candidate_statement": (
                f"{self._entity_text(candidate['head'], graph)} "
                f"{relation.name} {self._entity_text(candidate['tail'], graph)}"
            ),
            "supporting_evidence_ids": [item["id"] for item in support],
            "conflict_evidence_ids": [item["id"] for item in conflict],
        }

    def _context_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": evidence["id"],
            "source": evidence.get("source", ""),
            "source_file": evidence.get("source_file", ""),
            "source_row_id": evidence.get("source_row_id", ""),
            "text": evidence.get("text", ""),
            "related_entities": evidence.get("related_entities", []),
            "timestamp": evidence.get("timestamp", ""),
            "reliability": evidence.get("reliability", 0.0),
            "retrieval_score": evidence.get("retrieval_score", 0.0),
            "retrieval_reasons": evidence.get("retrieval_reasons", []),
        }

    def _retrieval_reasons(self, candidate: dict[str, Any], relation: RelationSpec, evidence: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        related = set(evidence.get("related_entities", []))
        if candidate["head"] in related:
            reasons.append("contains_head")
        if candidate["tail"] in related:
            reasons.append("contains_tail")
        if evidence.get("source") in relation.preferred_sources:
            reasons.append("preferred_source")
        if evidence.get("reliability", 0) >= 0.85:
            reasons.append("high_reliability")
        return reasons

    def _support_hint(self, candidate: dict[str, Any], relation: RelationSpec, evidence: dict[str, Any]) -> str:
        related = set(evidence.get("related_entities", []))
        if candidate["head"] in related and candidate["tail"] in related:
            return "mentions_head_and_tail"
        if candidate["head"] in related:
            return "mentions_head"
        if candidate["tail"] in related:
            return "mentions_tail"
        return f"relation_context_{relation.name}"

    def _evidence_text(self, evidence: dict[str, Any], graph: GraphStore) -> str:
        entity_text = " ".join(self._entity_text(entity_id, graph) for entity_id in evidence.get("related_entities", []))
        return " ".join(
            [
                evidence.get("text", ""),
                evidence.get("source", ""),
                entity_text,
                str(evidence.get("timestamp", "")),
            ]
        )

    def _get_or_build_dense_corpus(self, graph: GraphStore) -> dict[str, Any]:
        cache_key = id(graph)
        if cache_key in self._corpus_cache:
            return self._corpus_cache[cache_key]
        evidence_ids: list[str] = []
        evidence_texts: list[str] = []
        for evidence in graph.evidence_dict.values():
            evidence_ids.append(evidence["id"])
            evidence_texts.append(self._evidence_text(evidence, graph))
        embeddings = self._as_vectors(self._get_bi_encoder().encode(evidence_texts)) if evidence_texts else []
        corpus = {"evidence_ids": evidence_ids, "evidence_texts": evidence_texts, "evidence_embeddings": embeddings}
        self._corpus_cache[cache_key] = corpus
        return corpus

    def _get_bi_encoder(self) -> Any:
        if self._bi_encoder is None:
            from sentence_transformers import SentenceTransformer

            self._bi_encoder = SentenceTransformer(self.bi_encoder_model)
        return self._bi_encoder

    def _get_cross_encoder(self) -> Any:
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder

            self._cross_encoder = CrossEncoder(self.cross_encoder_model)
        return self._cross_encoder

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

    def _entity_text(self, entity_id: str, graph: GraphStore) -> str:
        entity = graph.get_entity(entity_id) or {}
        properties = entity.get("properties", {})
        property_text = ""
        if isinstance(properties, dict):
            property_text = " ".join(f"{key} {value}" for key, value in sorted(properties.items()))
        return " ".join(
            str(part)
            for part in [entity_id, entity.get("name", ""), entity.get("type", ""), property_text]
            if part
        )

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in TOKEN_RE.findall(str(text).lower()):
            tokens.append(token)
            for subtoken in re.split(r"[_./:-]+", token):
                if subtoken and subtoken != token:
                    tokens.append(subtoken)
        return tokens
