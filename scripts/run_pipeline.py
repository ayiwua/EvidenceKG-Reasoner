from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.candidate.base import RelationSpec
from evidencekg.candidate.multi_route_generator import MultiRouteCandidateGenerator
from evidencekg.eval.evaluator import V2Evaluator
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import write_json, write_jsonl
from evidencekg.llm.client_factory import ClientFactory
from evidencekg.llm.reasoner import LLMReasoner
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever
from evidencekg.verify.verifier import HardVerifier, SemanticVerifier
from evidencekg.writeback import PendingWriteback, ReviewApplier


def load_relation_specs(path: str | Path) -> dict[str, RelationSpec]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {item["name"]: RelationSpec.from_dict(item) for item in payload.get("relations", [])}


def run_pipeline(
    data_dir: str,
    relation_schema: str,
    llm_config: str,
    out_dir: str,
    enable_dense: bool = False,
) -> dict[str, object]:
    output_root = Path(out_dir)
    graph = GraphStore.from_dir(data_dir)
    relation_specs = load_relation_specs(relation_schema)

    candidate_path = output_root / "candidate_edges.jsonl"
    candidates = MultiRouteCandidateGenerator(relation_schema).write(graph, candidate_path)

    retriever = EvidenceRetriever(enable_dense=enable_dense)
    contexts = [
        retriever.retrieve(
            candidate,
            relation_specs[candidate["relation"]],
            graph,
            allow_keyword_only=not enable_dense,
        )
        for candidate in candidates
    ]
    contexts_path = output_root / "evidence_contexts.jsonl"
    write_jsonl(contexts_path, contexts)

    reasoner = LLMReasoner(ClientFactory.from_yaml(llm_config))
    hard = HardVerifier()
    semantic = SemanticVerifier()
    predictions = []
    verified = []
    for index, context in enumerate(contexts, start=1):
        relation = relation_specs[context["candidate"]["relation"]]
        prediction = reasoner.predict(context)
        prediction["prediction_id"] = f"pred_{index:06d}"
        predictions.append(prediction)
        hard_result = hard.verify(context, prediction, relation, graph)
        semantic_result = semantic.verify(context, prediction, relation) if hard_result["status"] == "passed" else {
            "support_status": "not_supported",
            "supported_evidence_ids": [],
            "weak_evidence_ids": [],
            "irrelevant_evidence_ids": prediction.get("supporting_evidence_ids", []),
            "conflict_evidence_ids": prediction.get("conflict_evidence_ids", []),
            "reason": "hard verifier failed",
        }
        record = dict(prediction)
        if hard_result["status"] != "passed" or semantic_result["support_status"] not in {"supported", "partially_supported"}:
            record["decision"] = "reject" if prediction["decision"] == "accept" else prediction["decision"]
        record["hard_verifier"] = hard_result
        record["semantic_verifier"] = semantic_result
        verified.append(record)

    llm_path = output_root / "llm_predictions.jsonl"
    verified_path = output_root / "verified_predictions.jsonl"
    write_jsonl(llm_path, predictions)
    write_jsonl(verified_path, verified)

    pending_path = output_root / "pending_edges.jsonl"
    pending = PendingWriteback().write(verified, graph, pending_path)
    review_path = output_root / "review_decisions.jsonl"
    review_decisions = [
        {"candidate_id": item["candidate_id"], "decision": "approved", "reviewer": "sample_smoke"}
        for item in pending
    ]
    write_jsonl(review_path, review_decisions)
    enriched_path = output_root / "triples.enriched.jsonl"
    review_report = ReviewApplier().apply(Path(data_dir) / "triples.jsonl", pending_path, review_path, enriched_path)

    report = V2Evaluator().evaluate(
        candidate_path,
        contexts_path,
        llm_path,
        verified_path,
        pending_path,
        Path(data_dir) / "gold_hidden_edges.jsonl",
    )
    report["writeback"] = {
        "pending_count": len(pending),
        "review_decision_count": len(review_decisions),
        "review_apply": review_report,
    }
    write_json(output_root / "evaluation_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EvidenceKG-Reasoner v2 sample pipeline.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--relation-schema", required=True)
    parser.add_argument("--llm-config", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--enable-dense", action="store_true")
    args = parser.parse_args()

    report = run_pipeline(args.data_dir, args.relation_schema, args.llm_config, args.out_dir, enable_dense=args.enable_dense)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
