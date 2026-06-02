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
