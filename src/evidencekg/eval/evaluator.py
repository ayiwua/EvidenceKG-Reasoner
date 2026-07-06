from __future__ import annotations

from pathlib import Path
from typing import Any

from evidencekg.io import read_jsonl


class Evaluator:
    def evaluate(
        self,
        predicted_edges_path: str | Path,
        gold_edges_path: str | Path,
        verified_predictions_path: str | Path | None = None,
    ) -> dict[str, Any]:
        predicted = read_jsonl(predicted_edges_path) if Path(predicted_edges_path).exists() else []
        gold = read_jsonl(gold_edges_path)
        verified = read_jsonl(verified_predictions_path) if verified_predictions_path and Path(verified_predictions_path).exists() else []

        predicted_keys = {(item["head"], item["relation"], item["tail"]) for item in predicted}
        gold_keys = {(item["head"], item["relation"], item["tail"]) for item in gold}
        hits = predicted_keys & gold_keys

        precision = len(hits) / len(predicted_keys) if predicted_keys else 0.0
        recall = len(hits) / len(gold_keys) if gold_keys else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

        accepted_count = sum(1 for item in verified if item.get("decision") == "accept")
        rejected_count = sum(1 for item in verified if item.get("decision") == "reject")
        uncertain_count = sum(1 for item in verified if item.get("decision") == "uncertain")
        pass_count = sum(1 for item in verified if item.get("verifier_status") == "passed")
        confidences = [float(item.get("confidence", 0.0)) for item in verified]

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "gold_count": len(gold_keys),
            "predicted_edge_count": len(predicted_keys),
            "hit_count": len(hits),
            "candidate_count": len(verified),
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "uncertain_count": uncertain_count,
            "verifier_pass_rate": round(pass_count / len(verified), 4) if verified else 0.0,
            "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        }


class V2Evaluator:
    def evaluate(
        self,
        candidate_edges_path: str | Path,
        evidence_contexts_path: str | Path,
        llm_predictions_path: str | Path,
        verified_predictions_path: str | Path,
        pending_edges_path: str | Path,
        gold_edges_path: str | Path,
    ) -> dict[str, Any]:
        candidates = read_jsonl(candidate_edges_path)
        contexts = read_jsonl(evidence_contexts_path)
        llm_predictions = read_jsonl(llm_predictions_path)
        verified = read_jsonl(verified_predictions_path)
        pending = read_jsonl(pending_edges_path)
        gold = read_jsonl(gold_edges_path)
        pending_keys = {(item["head"], item["relation"], item["tail"]) for item in pending}
        gold_keys = {(item["head"], item["relation"], item["tail"]) for item in gold}
        candidate_keys = {(item["head"], item["relation"], item["tail"]) for item in candidates}
        hits = pending_keys & gold_keys
        precision = len(hits) / len(pending_keys) if pending_keys else 0.0
        recall = len(hits) / len(gold_keys) if gold_keys else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        relation_counts: dict[str, int] = {}
        for candidate in candidates:
            relation_counts[candidate["relation"]] = relation_counts.get(candidate["relation"], 0) + 1
        evidence_counts = [len(item.get("supporting_evidence_candidates", [])) for item in contexts]
        return {
            "candidate": {
                "candidate_count": len(candidates),
                "candidate_count_by_relation": relation_counts,
                "candidate_recall_if_gold_available": round(len(candidate_keys & gold_keys) / len(gold_keys), 4)
                if gold_keys
                else None,
            },
            "retrieval": {
                "avg_evidence_count": round(sum(evidence_counts) / len(evidence_counts), 4) if evidence_counts else 0.0,
                "empty_context_rate": round(sum(1 for count in evidence_counts if count == 0) / len(evidence_counts), 4)
                if evidence_counts
                else 0.0,
                "evidence_recall_at_k_if_gold_available": None,
                "degraded_count": sum(1 for item in contexts if item.get("retrieval_metadata", {}).get("degraded")),
            },
            "llm": {
                "accept_count": sum(1 for item in llm_predictions if item.get("decision") == "accept"),
                "reject_count": sum(1 for item in llm_predictions if item.get("decision") == "reject"),
                "uncertain_count": sum(1 for item in llm_predictions if item.get("decision") == "uncertain"),
                "parse_error_count": sum(1 for item in llm_predictions if item.get("parse_error")),
                "fallback_count": sum(1 for item in llm_predictions if item.get("fallback_reason")),
            },
            "verifier": {
                "hard_pass_count": sum(1 for item in verified if item.get("hard_verifier", {}).get("status") == "passed"),
                "hard_fail_count": sum(1 for item in verified if item.get("hard_verifier", {}).get("status") == "failed"),
                "semantic_supported_count": sum(
                    1 for item in verified if item.get("semantic_verifier", {}).get("support_status") == "supported"
                ),
                "semantic_not_supported_count": sum(
                    1 for item in verified if item.get("semantic_verifier", {}).get("support_status") == "not_supported"
                ),
                "semantic_conflicted_count": sum(
                    1 for item in verified if item.get("semantic_verifier", {}).get("support_status") == "conflicted"
                ),
            },
            "final": {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "hit_count": len(hits),
                "pending_edge_count": len(pending_keys),
                "gold_count": len(gold_keys),
            },
        }
