from __future__ import annotations

import json
import re
import sys
import time
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
                content = self.client.complete(
                    prompt_text,
                    attempt_index=attempt_index,
                    total_attempts=attempts,
                    candidate_id=str(candidate_id) if candidate_id else None,
                    debug_timing=self.debug_timing,
                )
                client_attempts.append(dict(getattr(self.client, "last_metadata", {})))
                parse_start = time.perf_counter()
                parsed = self._parse_json_output(content)
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
