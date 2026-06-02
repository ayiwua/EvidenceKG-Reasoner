from __future__ import annotations

from typing import Any, Protocol


class BaseReasoner(Protocol):
    def predict(self, context: dict[str, Any]) -> dict[str, Any]:
        ...


class MockReasoner:
    """Rule-based stand-in for an LLM. It consumes structured context only."""

    def predict(self, context: dict[str, Any]) -> dict[str, Any]:
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
