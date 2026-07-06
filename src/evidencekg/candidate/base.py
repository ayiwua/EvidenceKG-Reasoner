from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CandidateKey = tuple[str, str, str]


@dataclass(frozen=True)
class RelationSpec:
    name: str
    description: str
    head_types: list[str]
    tail_types: list[str]
    preferred_sources: list[str]
    recall_routes: list[str]
    prompt_guidance: str
    semantic_verification_criteria: str
    max_candidates: int
    allow_existing: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelationSpec":
        required = [
            "name",
            "description",
            "head_types",
            "tail_types",
            "preferred_sources",
            "recall_routes",
            "prompt_guidance",
            "semantic_verification_criteria",
            "max_candidates",
        ]
        missing = [field_name for field_name in required if field_name not in payload]
        if missing:
            raise ValueError(f"relation schema missing fields {missing}: {payload}")
        return cls(
            name=str(payload["name"]),
            description=str(payload["description"]),
            head_types=list(payload["head_types"]),
            tail_types=list(payload["tail_types"]),
            preferred_sources=list(payload["preferred_sources"]),
            recall_routes=list(payload["recall_routes"]),
            prompt_guidance=str(payload["prompt_guidance"]),
            semantic_verification_criteria=str(payload["semantic_verification_criteria"]),
            max_candidates=int(payload["max_candidates"]),
            allow_existing=bool(payload.get("allow_existing", False)),
        )


@dataclass
class RecallHit:
    score: float
    source: str
    debug: dict[str, Any] = field(default_factory=dict)
