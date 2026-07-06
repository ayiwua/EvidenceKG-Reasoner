from __future__ import annotations

import json
import os
import time
from typing import Any

from evidencekg.llm.base_client import LLMResponse


class MockLLMClient:
    provider = "mock"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        model_env = str(config.get("model_env", ""))
        self.model = os.environ.get(model_env, str(config.get("model", "mock-evidencekg-v2"))) if model_env else str(config.get("model", "mock-evidencekg-v2"))

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        start = time.perf_counter()
        context = kwargs.get("context") or {}
        support = context.get("supporting_evidence_candidates", [])
        conflict = context.get("conflict_evidence_candidates", [])
        candidate = context.get("candidate", {})
        decision = "accept" if support and not conflict else "uncertain"
        confidence = 0.86 if decision == "accept" else 0.45
        payload = {
            "decision": decision,
            "confidence": confidence,
            "relation": candidate.get("relation", ""),
            "reason": "MockLLM uses supplied structured evidence context for local smoke execution.",
            "supporting_evidence_ids": [item["id"] for item in support[:3]],
            "conflict_evidence_ids": [item["id"] for item in conflict[:3]],
            "evidence_analysis": [
                {
                    "evidence_id": item["id"],
                    "support_label": "strong_support",
                    "explanation": "Evidence was selected as a supporting candidate by relation-aware retrieval.",
                }
                for item in support[:3]
            ],
        }
        latency_ms = int((time.perf_counter() - start) * 1000)
        content = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            latency_ms=latency_ms,
            usage={"input_tokens": sum(len(item.get("content", "")) for item in messages), "output_tokens": len(content)},
            raw={"mock": True},
        )
