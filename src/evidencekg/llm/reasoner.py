from __future__ import annotations

import json
import re
from typing import Any, Protocol

from evidencekg.config.task_config import LLMConfig
from evidencekg.llm.openai_compatible_client import OpenAICompatibleClient


class BaseReasoner(Protocol):
    def predict(self, context: dict[str, Any], prompt_text: str | None = None) -> dict[str, Any]:
        ...


class MockReasoner:
    """Rule-based stand-in for an LLM. It consumes structured context only."""

    def predict(self, context: dict[str, Any], prompt_text: str | None = None) -> dict[str, Any]:
        candidate = context["candidate"]
        evidence = context.get("evidence_snippets", [])
        paths = context.get("graph_paths", [])
        common_neighbors = context.get("common_neighbors", [])
        score = float(candidate.get("candidate_score", 0.0))
        evidence_ids = [item["evidence_id"] for item in evidence]

        confidence = min(0.95, score + (0.1 if evidence else 0.0))
        if evidence and paths and (common_neighbors or score >= 0.6) and confidence >= 0.7:
            decision = "accept"
            reason = "Structured graph paths and traceable evidence support the candidate relation."
            if context.get("tail_profile", {}).get("type") in {"department", "person"}:
                reason = "Mock reasoner overreached on an indirect owner candidate and cited a bad evidence id."
                evidence_ids = ["ev_missing_mock"]
        elif evidence or paths:
            decision = "uncertain"
            confidence = max(0.45, min(confidence, 0.69))
            reason = "Some structured evidence exists, but support is not strong enough for acceptance."
        else:
            decision = "reject"
            confidence = min(confidence, 0.4)
            reason = "No sufficient structured evidence was found for the candidate relation."

        return {
            "decision": decision,
            "confidence": round(confidence, 3),
            "reason": reason,
            "supporting_evidence_ids": evidence_ids[:3] if decision in {"accept", "uncertain"} else [],
        }


class RealLLMReasoner:
    """OpenAI-compatible reasoner using prompt text, with JSON parsing and fallback."""

    def __init__(self, config: LLMConfig, client: OpenAICompatibleClient | None = None) -> None:
        self.config = config
        self.client = client or OpenAICompatibleClient(config)

    def predict(self, context: dict[str, Any], prompt_text: str | None = None) -> dict[str, Any]:
        if not prompt_text:
            return self._fallback("real LLM mode requires prompt_text")

        last_error = ""
        attempts = max(1, self.config.max_retries + 1)
        for _ in range(attempts):
            try:
                content = self.client.complete(prompt_text)
                parsed = self._parse_json_output(content)
                return self._normalize(parsed)
            except Exception as exc:  # noqa: BLE001 - degrade external provider failures.
                last_error = str(exc)
        return self._fallback(f"real LLM unavailable or returned invalid JSON: {last_error}")

    def _parse_json_output(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise ValueError("no JSON object found in LLM response")
            return json.loads(match.group(0))

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        decision = str(payload.get("decision", "uncertain")).lower()
        if decision not in {"accept", "reject", "uncertain"}:
            decision = "uncertain"
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        evidence_ids = payload.get("supporting_evidence_ids", [])
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        return {
            "decision": decision,
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "reason": str(payload.get("reason", "No reason provided.")),
            "supporting_evidence_ids": [str(item) for item in evidence_ids],
        }

    def _fallback(self, reason: str) -> dict[str, Any]:
        return {
            "decision": "uncertain",
            "confidence": 0.0,
            "reason": reason,
            "supporting_evidence_ids": [],
        }
