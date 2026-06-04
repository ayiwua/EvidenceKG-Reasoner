from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EvidenceRetrievalConfig:
    max_hops: int = 3
    max_paths: int = 5
    max_evidence_snippets: int = 8
    include_entity_profiles: bool = True
    include_graph_paths: bool = True
    include_common_neighbors: bool = True
    include_related_triples: bool = True


@dataclass(frozen=True)
class LLMConfig:
    mode: str = "mock"
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "LLM_API_KEY"
    base_url_env: str = "LLM_BASE_URL"
    model_env: str = "LLM_MODEL"
    temperature: float = 0.2
    best_of_n: int = 1
    timeout_seconds: float = 30.0
    max_retries: int = 2
    trust_env: bool = False


@dataclass(frozen=True)
class VerifierConfig:
    confidence_threshold: float = 0.7
    require_supporting_evidence: bool = True
    check_schema_consistency: bool = True
    check_evidence_grounding: bool = True
    check_conflict: bool = True


@dataclass(frozen=True)
class EvaluationConfig:
    gold_file: str = "gold_hidden_edges.jsonl"


@dataclass(frozen=True)
class TaskConfig:
    task_name: str
    target_relation: str
    allowed_head_types: list[str]
    allowed_tail_types: list[str]
    candidate_rules: list[str]
    schema_filter: dict[str, Any] = field(default_factory=lambda: {"enabled": True})
    evidence_retrieval: EvidenceRetrievalConfig = field(default_factory=EvidenceRetrievalConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    verifier: VerifierConfig = field(default_factory=VerifierConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)

    def is_allowed_pair(self, head_type: str, tail_type: str) -> bool:
        return head_type in self.allowed_head_types and tail_type in self.allowed_tail_types


def load_task_config(path: str | Path) -> TaskConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TaskConfig(
        task_name=raw["task_name"],
        target_relation=raw["target_relation"],
        allowed_head_types=list(raw["allowed_head_types"]),
        allowed_tail_types=list(raw["allowed_tail_types"]),
        candidate_rules=list(raw.get("candidate_rules", [])),
        schema_filter=dict(raw.get("schema_filter", {"enabled": True})),
        evidence_retrieval=EvidenceRetrievalConfig(**raw.get("evidence_retrieval", {})),
        llm=LLMConfig(**raw.get("llm", {})),
        verifier=VerifierConfig(**raw.get("verifier", {})),
        evaluation=EvaluationConfig(**raw.get("evaluation", {})),
    )
