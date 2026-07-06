from __future__ import annotations

from typing import Any

from evidencekg.config.task_config import TaskConfig
from evidencekg.candidate.base import RelationSpec
from evidencekg.graph.graph_store import GraphStore


class Verifier:
    def __init__(self) -> None:
        self._accepted_keys: set[tuple[str, str, str]] = set()

    def verify(
        self,
        candidate: dict[str, Any],
        context: dict[str, Any],
        prediction: dict[str, Any],
        config: TaskConfig,
        graph: GraphStore,
    ) -> dict[str, Any]:
        head = candidate["head"]
        tail = candidate["tail"]
        head_entity = graph.get_entity(head) or {}
        tail_entity = graph.get_entity(tail) or {}

        schema_ok = config.is_allowed_pair(head_entity.get("type", ""), tail_entity.get("type", ""))
        evidence_ok = self._check_evidence_grounding(context, prediction, graph)
        confidence_ok = not (
            prediction["decision"] == "accept" and prediction["confidence"] < config.verifier.confidence_threshold
        )
        conflict_ok = (head, candidate["relation"], tail) not in self._accepted_keys

        final_decision = prediction["decision"]
        verifier_status = "passed"
        if config.verifier.check_schema_consistency and not schema_ok:
            final_decision = "reject"
            verifier_status = "failed"
        elif config.verifier.check_evidence_grounding and not evidence_ok:
            final_decision = "reject" if config.verifier.require_supporting_evidence else "uncertain"
            verifier_status = "failed"
        elif config.verifier.check_conflict and not conflict_ok:
            final_decision = "reject"
            verifier_status = "failed"
        elif config.verifier.confidence_threshold and not confidence_ok:
            final_decision = "uncertain"
            verifier_status = "failed"

        if final_decision == "accept" and verifier_status == "passed":
            self._accepted_keys.add((head, candidate["relation"], tail))

        return {
            "prediction_id": "",
            "candidate_id": candidate["candidate_id"],
            "head": head,
            "relation": candidate["relation"],
            "tail": tail,
            "decision": final_decision,
            "confidence": prediction["confidence"],
            "reason": prediction["reason"],
            "supporting_evidence_ids": prediction.get("supporting_evidence_ids", []),
            "verifier_status": verifier_status,
            "verifier_details": {
                "schema_consistency": schema_ok,
                "evidence_grounding": evidence_ok,
                "confidence_threshold": confidence_ok,
                "conflict_check": conflict_ok,
            },
            "source": "mock_llm_inference",
        }

    def _check_evidence_grounding(
        self, context: dict[str, Any], prediction: dict[str, Any], graph: GraphStore
    ) -> bool:
        if prediction["decision"] != "accept":
            return True
        supporting = prediction.get("supporting_evidence_ids", [])
        if not supporting:
            return False
        context_evidence_ids = {item["evidence_id"] for item in context.get("evidence_snippets", [])}
        candidate = context["candidate"]
        head = candidate["head"]
        tail = candidate["tail"]
        for evidence_id in supporting:
            if evidence_id not in context_evidence_ids:
                return False
            evidence = graph.get_evidence(evidence_id)
            if not evidence:
                return False
            related = set(evidence.get("related_entities", []))
            if head not in related and tail not in related:
                return False
        return True


class HardVerifier:
    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self.confidence_threshold = confidence_threshold
        self._accepted_keys: set[tuple[str, str, str]] = set()

    def verify(self, context: dict[str, Any], prediction: dict[str, Any], relation: RelationSpec, graph: GraphStore) -> dict[str, Any]:
        candidate = context["candidate"]
        head = candidate["head"]
        tail = candidate["tail"]
        head_type = (graph.get_entity(head) or {}).get("type", "")
        tail_type = (graph.get_entity(tail) or {}).get("type", "")
        context_evidence_ids = {
            item["id"]
            for item in context.get("supporting_evidence_candidates", []) + context.get("conflict_evidence_candidates", [])
        }
        supporting_ids = prediction.get("supporting_evidence_ids", [])
        conflict_ids = prediction.get("conflict_evidence_ids", [])
        schema_ok = (
            prediction.get("relation") == relation.name
            and head_type in relation.head_types
            and tail_type in relation.tail_types
        )
        decision_ok = prediction.get("decision") in {"accept", "reject", "uncertain"}
        confidence = float(prediction.get("confidence", 0.0))
        confidence_ok = 0.0 <= confidence <= 1.0 and not (
            prediction.get("decision") == "accept" and confidence < self.confidence_threshold
        )
        evidence_ids_ok = isinstance(supporting_ids, list) and isinstance(conflict_ids, list) and all(
            evidence_id in context_evidence_ids for evidence_id in supporting_ids + conflict_ids
        )
        accept_has_evidence = prediction.get("decision") != "accept" or bool(supporting_ids)
        conflict_ok = (head, relation.name, tail) not in self._accepted_keys
        passed = all([schema_ok, decision_ok, confidence_ok, evidence_ids_ok, accept_has_evidence, conflict_ok])
        if passed and prediction.get("decision") == "accept":
            self._accepted_keys.add((head, relation.name, tail))
        return {
            "status": "passed" if passed else "failed",
            "schema": schema_ok,
            "decision": decision_ok,
            "confidence": confidence_ok,
            "evidence_ids": evidence_ids_ok,
            "accept_has_evidence": accept_has_evidence,
            "conflict": conflict_ok,
        }


class SemanticVerifier:
    SUPPORT_WORDS = {
        "owned_by": {"team", "handled", "investigated", "reviewed", "routed", "responsible"},
        "depends_on": {"depends", "upstream", "calls", "validation", "storage", "trace"},
        "runs_on": {"on", "maps", "host", "fired", "prod"},
    }

    def verify(self, context: dict[str, Any], prediction: dict[str, Any], relation: RelationSpec) -> dict[str, Any]:
        if prediction.get("decision") != "accept":
            return {
                "support_status": "not_supported",
                "supported_evidence_ids": [],
                "weak_evidence_ids": [],
                "irrelevant_evidence_ids": [],
                "conflict_evidence_ids": prediction.get("conflict_evidence_ids", []),
                "reason": "semantic verification only promotes accepted predictions",
            }
        candidate = context["candidate"]
        evidence_by_id = {item["id"]: item for item in context.get("supporting_evidence_candidates", [])}
        supported: list[str] = []
        weak: list[str] = []
        irrelevant: list[str] = []
        for evidence_id in prediction.get("supporting_evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                irrelevant.append(evidence_id)
                continue
            status = self._judge_evidence(candidate, relation, evidence)
            if status == "supported":
                supported.append(evidence_id)
            elif status == "weak":
                weak.append(evidence_id)
            else:
                irrelevant.append(evidence_id)
        conflict_ids = list(prediction.get("conflict_evidence_ids", []))
        if conflict_ids:
            support_status = "conflicted"
        elif supported:
            support_status = "supported"
        elif weak:
            support_status = "partially_supported"
        else:
            support_status = "not_supported"
        return {
            "support_status": support_status,
            "supported_evidence_ids": supported,
            "weak_evidence_ids": weak,
            "irrelevant_evidence_ids": irrelevant,
            "conflict_evidence_ids": conflict_ids,
            "reason": self._reason(support_status, relation.name),
        }

    def _judge_evidence(self, candidate: dict[str, Any], relation: RelationSpec, evidence: dict[str, Any]) -> str:
        related = set(evidence.get("related_entities", []))
        text = str(evidence.get("text", "")).lower()
        has_head = candidate["head"] in related
        has_tail = candidate["tail"] in related
        words = self.SUPPORT_WORDS.get(relation.name, set())
        has_relation_language = any(word in text for word in words)
        if has_head and has_tail and has_relation_language:
            return "supported"
        if has_head and has_tail:
            return "weak"
        return "irrelevant"

    def _reason(self, support_status: str, relation_name: str) -> str:
        if support_status == "supported":
            return f"supporting evidence text and related entities support {relation_name}"
        if support_status == "partially_supported":
            return f"evidence mentions both endpoints but relation language is weak for {relation_name}"
        if support_status == "conflicted":
            return "conflict evidence was cited"
        return "supporting evidence does not semantically support the candidate relation"
