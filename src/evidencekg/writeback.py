from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import read_jsonl, write_json, write_jsonl


class EdgeWriter:
    """Writes verified prediction edges without mutating the source KG files."""

    def build_edges(
        self, predictions: list[dict[str, Any]], graph: GraphStore
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        existing_edges = {(item["head"], item["relation"], item["tail"]) for item in graph.iter_triples()}
        existing_by_head_relation: dict[tuple[str, str], set[str]] = {}
        for head, relation, tail in existing_edges:
            existing_by_head_relation.setdefault((head, relation), set()).add(tail)

        written_edges: set[tuple[str, str, str]] = set()
        written_by_head_relation: dict[tuple[str, str], set[str]] = {}
        edges: list[dict[str, Any]] = []
        report = {
            "pending": 0,
            "skipped_duplicate": 0,
            "skipped_conflict": 0,
            "approved": 0,
            "written_count": 0,
        }

        for prediction in predictions:
            if prediction.get("decision") != "accept" or prediction.get("verifier_status") != "passed":
                continue

            key = (prediction["head"], prediction["relation"], prediction["tail"])
            head_relation = (prediction["head"], prediction["relation"])
            if key in existing_edges or key in written_edges:
                report["skipped_duplicate"] += 1
                continue
            existing_tails = existing_by_head_relation.get(head_relation, set())
            written_tails = written_by_head_relation.get(head_relation, set())
            conflicting_tails = (existing_tails | written_tails) - {prediction["tail"]}
            if conflicting_tails:
                report["skipped_conflict"] += 1
                continue

            edge = self._edge_from_prediction(prediction, len(edges) + 1)
            edges.append(edge)
            written_edges.add(key)
            written_by_head_relation.setdefault(head_relation, set()).add(prediction["tail"])

        report["written_count"] = len(edges)
        return edges, report

    def write_pending(self, predictions: list[dict[str, Any]], graph: GraphStore, output_dir: str | Path) -> dict[str, int]:
        edges, report = self.build_edges(predictions, graph)
        report["pending"] = len(edges)
        write_jsonl(Path(output_dir) / "pending_edges.jsonl", edges)
        write_json(Path(output_dir) / "writeback_report.json", report)
        return report

    def write_approved(
        self, predictions: list[dict[str, Any]], graph: GraphStore, output_dir: str | Path
    ) -> dict[str, int]:
        edges, report = self.build_edges(predictions, graph)
        report["approved"] = len(edges)
        enriched_triples = [dict(item) for item in graph.iter_triples()] + edges
        write_jsonl(Path(output_dir) / "triples.enriched.jsonl", enriched_triples)
        write_json(Path(output_dir) / "writeback_report.json", report)
        return report

    def _edge_from_prediction(self, prediction: dict[str, Any], index: int) -> dict[str, Any]:
        return {
            "triple_id": f"pred_{index:03d}_{prediction['candidate_id']}",
            "head": prediction["head"],
            "relation": prediction["relation"],
            "tail": prediction["tail"],
            "evidence_ids": list(prediction.get("supporting_evidence_ids", [])),
            "confidence": prediction.get("confidence", 0.0),
            "reason": prediction.get("reason", ""),
            "candidate_id": prediction["candidate_id"],
            "prediction_id": prediction.get("prediction_id", ""),
            "verifier_details": prediction.get("verifier_details", {}),
            "source": "verified_prediction_writeback",
        }


class KGWritebackManager:
    def __init__(self, writer: EdgeWriter | None = None) -> None:
        self.writer = writer or EdgeWriter()

    def writeback(
        self,
        predictions: list[dict[str, Any]],
        graph: GraphStore,
        output_dir: str | Path,
        mode: str = "pending",
    ) -> dict[str, int]:
        if mode == "pending":
            return self.writer.write_pending(predictions, graph, output_dir)
        if mode == "approved":
            return self.writer.write_approved(predictions, graph, output_dir)
        raise ValueError(f"unsupported writeback mode: {mode}")


class PendingWriteback:
    """v2 pending edge writer. It never mutates source triples."""

    def build_pending_edges(self, verified_predictions: list[dict[str, Any]], graph: GraphStore) -> list[dict[str, Any]]:
        existing = {(item["head"], item["relation"], item["tail"]) for item in graph.iter_triples()}
        pending: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        created_at = datetime.now(timezone.utc).isoformat()
        for item in verified_predictions:
            key = (item["head"], item["relation"], item["tail"])
            if key in existing or key in seen:
                continue
            if item.get("decision") != "accept":
                continue
            if item.get("hard_verifier", {}).get("status") != "passed":
                continue
            semantic = item.get("semantic_verifier", {})
            if semantic.get("support_status") not in {"supported", "partially_supported"}:
                continue
            pending.append(
                {
                    "candidate_id": item["candidate_id"],
                    "head": item["head"],
                    "relation": item["relation"],
                    "tail": item["tail"],
                    "confidence": item.get("confidence", 0.0),
                    "supporting_evidence_ids": semantic.get("supported_evidence_ids")
                    or item.get("supporting_evidence_ids", []),
                    "semantic_status": semantic.get("support_status", ""),
                    "reason": item.get("reason", ""),
                    "recall_sources": item.get("recall_sources", []),
                    "created_at": created_at,
                }
            )
            seen.add(key)
        return pending

    def write(self, verified_predictions: list[dict[str, Any]], graph: GraphStore, out_path: str | Path) -> list[dict[str, Any]]:
        pending = self.build_pending_edges(verified_predictions, graph)
        write_jsonl(out_path, pending)
        return pending


class ReviewApplier:
    def apply(
        self,
        triples_path: str | Path,
        pending_path: str | Path,
        review_path: str | Path,
        out_path: str | Path,
    ) -> dict[str, int]:
        triples = read_jsonl(triples_path)
        pending = read_jsonl(pending_path)
        reviews = {item["candidate_id"]: item for item in read_jsonl(review_path)}
        enriched = list(triples)
        approved = 0
        rejected = 0
        skipped = 0
        existing = {(item["head"], item["relation"], item["tail"]) for item in triples}
        for index, edge in enumerate(pending, start=1):
            review = reviews.get(edge["candidate_id"])
            if not review:
                skipped += 1
                continue
            if review.get("decision") != "approved":
                rejected += 1
                continue
            key = (edge["head"], edge["relation"], edge["tail"])
            if key in existing:
                skipped += 1
                continue
            enriched.append(
                {
                    "id": f"enriched_{index:06d}_{edge['candidate_id']}",
                    "head": edge["head"],
                    "relation": edge["relation"],
                    "tail": edge["tail"],
                    "source": "reviewed_pending_edge",
                    "source_row_id": edge["candidate_id"],
                    "confidence": edge.get("confidence", 0.0),
                    "properties": {
                        "supporting_evidence_ids": edge.get("supporting_evidence_ids", []),
                        "review_decision": "approved",
                    },
                }
            )
            existing.add(key)
            approved += 1
        write_jsonl(out_path, enriched)
        return {"approved": approved, "rejected": rejected, "skipped": skipped, "output_count": len(enriched)}
