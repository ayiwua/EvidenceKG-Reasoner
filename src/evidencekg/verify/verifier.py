from __future__ import annotations

from typing import Any

from evidencekg.config.task_config import TaskConfig
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
