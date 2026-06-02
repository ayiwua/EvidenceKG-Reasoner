from __future__ import annotations

from typing import Any


class PromptBuilder:
    def build(self, evidence_context: dict[str, Any]) -> dict[str, Any]:
        structured_context = dict(evidence_context)
        candidate = evidence_context["candidate"]
        prompt_text = (
            "Decide whether the candidate relation is supported by the provided graph evidence.\n"
            f"Candidate: {candidate['head']} {candidate['relation']} {candidate['tail']}\n"
            "Return JSON with decision, confidence, reason, and supporting_evidence_ids."
        )
        return {"structured_context": structured_context, "prompt_text": prompt_text}
