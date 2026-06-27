from __future__ import annotations

from pathlib import Path
from typing import Any

from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import write_json, write_jsonl


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
