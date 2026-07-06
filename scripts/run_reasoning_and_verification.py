from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.candidate.base import RelationSpec
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import read_jsonl, write_jsonl
from evidencekg.llm.client_factory import ClientFactory
from evidencekg.llm.reasoner import LLMReasoner
from evidencekg.verify.verifier import HardVerifier, SemanticVerifier


def load_relation_specs(path: str | Path) -> dict[str, RelationSpec]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {item["name"]: RelationSpec.from_dict(item) for item in payload.get("relations", [])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v2 LLM reasoning and verification.")
    parser.add_argument("--contexts", required=True)
    parser.add_argument("--relation-schema", required=True)
    parser.add_argument("--llm-config", required=True)
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    relation_specs = load_relation_specs(args.relation_schema)
    llm_config = yaml.safe_load(Path(args.llm_config).read_text(encoding="utf-8")) or {}
    graph = GraphStore.from_dir(args.data_dir)
    reasoner = LLMReasoner(ClientFactory.from_config(llm_config))
    hard = HardVerifier()
    semantic = SemanticVerifier()
    predictions = []
    verified = []
    for index, context in enumerate(read_jsonl(args.contexts), start=1):
        relation_name = context["candidate"]["relation"]
        relation = relation_specs[relation_name]
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
        final_decision = prediction["decision"]
        if hard_result["status"] != "passed" or semantic_result["support_status"] not in {"supported", "partially_supported"}:
            final_decision = "reject" if prediction["decision"] == "accept" else prediction["decision"]
        record = dict(prediction)
        record["decision"] = final_decision
        record["hard_verifier"] = hard_result
        record["semantic_verifier"] = semantic_result
        verified.append(record)

    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "llm_predictions.jsonl", predictions)
    write_jsonl(out_dir / "verified_predictions.jsonl", verified)
    summary = {
        "prediction_count": len(predictions),
        "accept_count": sum(1 for item in verified if item["decision"] == "accept"),
        "reject_count": sum(1 for item in verified if item["decision"] == "reject"),
        "uncertain_count": sum(1 for item in verified if item["decision"] == "uncertain"),
        "hard_pass_count": sum(1 for item in verified if item["hard_verifier"]["status"] == "passed"),
        "semantic_supported_count": sum(
            1 for item in verified if item["semantic_verifier"]["support_status"] == "supported"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
