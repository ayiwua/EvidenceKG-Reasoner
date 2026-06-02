from __future__ import annotations

from pathlib import Path
from typing import Any

from evidencekg.candidate.generator import CandidateGenerator
from evidencekg.config.task_config import load_task_config
from evidencekg.eval.evaluator import Evaluator
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import write_json, write_jsonl
from evidencekg.llm.reasoner import MockReasoner, RealLLMReasoner
from evidencekg.prompting.prompt_builder import PromptBuilder
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever
from evidencekg.verify.verifier import Verifier


class PipelineRunner:
    def run(self, config_path: str, data_dir: str, output_dir: str, stage: str = "all") -> dict[str, Any]:
        config = load_task_config(config_path)
        graph = GraphStore.from_dir(data_dir)
        output_root = Path(output_dir)

        candidates = CandidateGenerator().generate(config, graph)
        write_jsonl(output_root / "candidate_pairs.jsonl", candidates)
        if stage == "candidates":
            return {"candidate_count": len(candidates)}

        retriever = EvidenceRetriever()
        contexts = [retriever.retrieve(candidate, config, graph) for candidate in candidates]
        write_jsonl(output_root / "evidence_contexts.jsonl", contexts)

        prompt_builder = PromptBuilder()
        reasoner = self._build_reasoner(config)
        verifier = Verifier()
        context_by_id = {context["candidate_id"]: context for context in contexts}
        verified_predictions = []
        for candidate in candidates:
            built = prompt_builder.build(context_by_id[candidate["candidate_id"]])
            prediction = reasoner.predict(built["structured_context"], built["prompt_text"])
            verified = verifier.verify(candidate, built["structured_context"], prediction, config, graph)
            verified["prediction_id"] = f"p_{len(verified_predictions) + 1:03d}"
            verified_predictions.append(verified)

        write_jsonl(output_root / "verified_predictions.jsonl", verified_predictions)
        predicted_edges = [
            item
            for item in verified_predictions
            if item["decision"] == "accept" and item["verifier_status"] == "passed"
        ]
        write_jsonl(output_root / "predicted_edges.jsonl", predicted_edges)

        report = Evaluator().evaluate(
            output_root / "predicted_edges.jsonl",
            Path(data_dir) / config.evaluation.gold_file,
            output_root / "verified_predictions.jsonl",
        )
        write_json(output_root / "evaluation_report.json", report)
        return report

    def _build_reasoner(self, config: Any) -> Any:
        if config.llm.mode == "mock":
            return MockReasoner()
        if config.llm.mode == "real":
            return RealLLMReasoner(config.llm)
        raise ValueError(f"unsupported llm.mode: {config.llm.mode}")
