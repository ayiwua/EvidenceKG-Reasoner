from __future__ import annotations

import json
import re
import sys
import time
from typing import Any, Protocol

from evidencekg.config.task_config import LLMConfig
from evidencekg.llm.base_client import BaseLLMClient, LLMRequest
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

    def __init__(
        self,
        config: LLMConfig,
        client: OpenAICompatibleClient | None = None,
        debug_timing: bool = False,
    ) -> None:
        self.config = config
        self.client = client or OpenAICompatibleClient(config)
        self.debug_timing = debug_timing
        self.last_metadata: dict[str, Any] = {}

    def predict(self, context: dict[str, Any], prompt_text: str | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        candidate_id = context.get("candidate_id")
        self.last_metadata = {
            "elapsed_seconds": 0.0,
            "attempts": 0,
            "degraded": False,
            "warning": "",
            "parse_elapsed_seconds": 0.0,
            "client_attempts": [],
            "error_type": "",
        }
        if not prompt_text:
            return self._fallback("real LLM mode requires prompt_text", start, attempts=0)

        last_error = ""
        last_error_type = ""
        client_attempts: list[dict[str, Any]] = []
        attempts = max(1, self.config.max_retries + 1)
        for attempt_index in range(1, attempts + 1):
            try:
                response = self.client.chat(
                    LLMRequest(
                        system_prompt="You return only valid JSON for evidence-grounded KG relation judgments.",
                        user_prompt=prompt_text,
                        metadata={
                            "candidate_id": str(candidate_id) if candidate_id else "",
                            "attempt_index": attempt_index,
                            "total_attempts": attempts,
                        },
                    )
                )
                parse_start = time.perf_counter()
                parsed = self._parse_json_output(response.content)
                parse_elapsed = round(time.perf_counter() - parse_start, 3)
                result = self._normalize(parsed)
                self.last_metadata = {
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "attempts": attempt_index,
                    "degraded": False,
                    "warning": "",
                    "parse_elapsed_seconds": parse_elapsed,
                    "client_attempts": client_attempts,
                    "error_type": "",
                }
                return result
            except Exception as exc:  # noqa: BLE001 - degrade external provider failures.
                last_error = str(exc)
                client_attempts.append(dict(getattr(self.client, "last_metadata", {})))
                last_error_type = self._classify_reasoner_error(last_error)
                print(
                    f"[llm-reasoner][warning] attempt={attempt_index}/{attempts} "
                    f"error_type={last_error_type} failed: {last_error}",
                    file=sys.stderr,
                    flush=True,
                )
        return self._fallback(
            f"real LLM unavailable or returned invalid JSON: {last_error}",
            start,
            attempts=attempts,
            client_attempts=client_attempts,
            error_type=last_error_type,
        )

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

    def _fallback(
        self,
        reason: str,
        start: float | None = None,
        attempts: int = 0,
        client_attempts: list[dict[str, Any]] | None = None,
        error_type: str = "",
    ) -> dict[str, Any]:
        elapsed = time.perf_counter() - start if start is not None else 0.0
        self.last_metadata = {
            "elapsed_seconds": round(elapsed, 3),
            "attempts": attempts,
            "degraded": True,
            "warning": reason,
            "parse_elapsed_seconds": 0.0,
            "client_attempts": client_attempts or [],
            "error_type": error_type or self._classify_reasoner_error(reason),
        }
        print(
            f"[llm-reasoner][warning] degraded_to_uncertain elapsed={elapsed:.2f}s reason={reason}",
            file=sys.stderr,
            flush=True,
        )
        return {
            "decision": "uncertain",
            "confidence": 0.0,
            "reason": reason,
            "supporting_evidence_ids": [],
        }

    def _classify_reasoner_error(self, text: str) -> str:
        lowered = text.lower()
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        if "no json object" in lowered or "jsondecodeerror" in lowered or "invalid json" in lowered:
            return "parse_failure"
        if "llm request failed" in lowered or "missing api key" in lowered:
            return "provider_error"
        return "reasoner_error" if text else ""


class LLMReasoner:
    """v2 structured reasoner using the unified LLMClient interface."""

    def __init__(self, client: BaseLLMClient) -> None:
        self.client = client

    def predict(self, context: dict[str, Any]) -> dict[str, Any]:
        request = self._request(context)
        try:
            response = self.client.chat(request, context=context)
            parsed = self._parse_json_output(response.content)
            result = self._normalize(parsed, context)
            result["provider_metadata"] = {
                "provider": response.provider,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "usage": response.usage,
                "raw": response.raw,
            }
            result["raw_response"] = response.content
            result["parse_error"] = ""
            return result
        except Exception as exc:  # noqa: BLE001 - explicit uncertain result for provider/parse failure.
            return self._uncertain(context, error_type=self._classify_reasoner_error(str(exc)), reason=str(exc))

    def _request(self, context: dict[str, Any]) -> LLMRequest:
        supporting_ids = [item["id"] for item in context.get("supporting_evidence_candidates", [])]
        conflict_ids = [item["id"] for item in context.get("conflict_evidence_candidates", [])]
        system_prompt = (
            "You are a strict JSON-only relation verification engine. "
            "Return exactly one JSON object and no markdown. "
            "Required fields: decision, confidence, relation, reason, "
            "supporting_evidence_ids, conflict_evidence_ids, evidence_analysis. "
            "decision must be accept, reject, or uncertain. confidence must be a number from 0 to 1. "
            "supporting_evidence_ids and conflict_evidence_ids must be arrays of strings selected only "
            "from the provided allowed evidence ids. If accepting, include at least one supporting evidence id."
        )
        user_prompt = json.dumps(
            {
                "required_output_schema": {
                    "decision": "accept | reject | uncertain",
                    "confidence": 0.0,
                    "relation": context.get("candidate", {}).get("relation", ""),
                    "reason": "short evidence-grounded explanation",
                    "supporting_evidence_ids": [],
                    "conflict_evidence_ids": [],
                    "evidence_analysis": [
                        {
                            "evidence_id": "one allowed evidence id",
                            "support_label": "strong_support | weak_support | irrelevant | conflict",
                            "explanation": "why this evidence does or does not support the relation",
                        }
                    ],
                },
                "allowed_supporting_evidence_ids": supporting_ids,
                "allowed_conflict_evidence_ids": conflict_ids,
                "candidate": context.get("candidate", {}),
                "packed_context": context.get("packed_context", {}),
                "supporting_evidence_candidates": context.get("supporting_evidence_candidates", []),
                "conflict_evidence_candidates": context.get("conflict_evidence_candidates", []),
            },
            ensure_ascii=False,
        )
        return LLMRequest(system_prompt=system_prompt, user_prompt=user_prompt, metadata={"candidate_id": context.get("candidate_id", "")})

    def _parse_json_output(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise ValueError("no JSON object found in LLM response")
            return json.loads(match.group(0))

    def _normalize(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        candidate = context.get("candidate", {})
        decision = str(payload.get("decision", "uncertain")).lower()
        if decision not in {"accept", "reject", "uncertain"}:
            decision = "uncertain"
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        supporting = payload.get("supporting_evidence_ids", [])
        conflict = payload.get("conflict_evidence_ids", [])
        analysis = payload.get("evidence_analysis", [])
        if not isinstance(supporting, list):
            supporting = []
        if not isinstance(conflict, list):
            conflict = []
        if not isinstance(analysis, list):
            analysis = []
        return {
            "prediction_id": "",
            "candidate_id": context.get("candidate_id", ""),
            "head": candidate.get("head", ""),
            "relation": str(payload.get("relation") or candidate.get("relation", "")),
            "tail": candidate.get("tail", ""),
            "decision": decision,
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "reason": str(payload.get("reason", "")),
            "supporting_evidence_ids": [str(item) for item in supporting],
            "conflict_evidence_ids": [str(item) for item in conflict],
            "evidence_analysis": analysis,
            "error_type": "",
            "fallback_reason": "",
        }

    def _uncertain(self, context: dict[str, Any], error_type: str, reason: str) -> dict[str, Any]:
        candidate = context.get("candidate", {})
        return {
            "prediction_id": "",
            "candidate_id": context.get("candidate_id", ""),
            "head": candidate.get("head", ""),
            "relation": candidate.get("relation", ""),
            "tail": candidate.get("tail", ""),
            "decision": "uncertain",
            "confidence": 0.0,
            "reason": reason,
            "supporting_evidence_ids": [],
            "conflict_evidence_ids": [],
            "evidence_analysis": [],
            "error_type": error_type,
            "fallback_reason": "llm_reasoner_failed",
            "provider_metadata": {},
            "raw_response": "",
            "parse_error": reason if error_type == "parse_failure" else "",
        }

    def _classify_reasoner_error(self, text: str) -> str:
        lowered = text.lower()
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        if "no json object" in lowered or "jsondecodeerror" in lowered or "invalid json" in lowered:
            return "parse_failure"
        if "missing api key" in lowered or "provider" in lowered or "response missing content" in lowered:
            return "provider_error"
        return "reasoner_error" if text else ""
