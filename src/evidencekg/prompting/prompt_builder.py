from __future__ import annotations

import json
from typing import Any


class PromptBuilder:
    def build(self, evidence_context: dict[str, Any]) -> dict[str, Any]:
        structured_context = dict(evidence_context)
        candidate = evidence_context["candidate"]
        compact_context = {
            "candidate": candidate,
            "head_profile": evidence_context.get("head_profile", {}),
            "tail_profile": evidence_context.get("tail_profile", {}),
            "graph_paths": evidence_context.get("graph_paths", []),
            "common_neighbors": evidence_context.get("common_neighbors", []),
            "related_triples": evidence_context.get("related_triples", []),
            "evidence_snippets": evidence_context.get("evidence_snippets", []),
        }
        prompt_text = (
            "You are judging whether a candidate enterprise asset KG relation is supported by graph evidence.\n"
            "Use only the provided context. Do not invent evidence ids.\n"
            f"Candidate: {candidate['head']} {candidate['relation']} {candidate['tail']}\n"
            "Return only valid JSON with this schema:\n"
            '{"decision":"accept|reject|uncertain","confidence":0.0,'
            '"reason":"short explanation","supporting_evidence_ids":[]}\n'
            "Context JSON:\n"
            f"{json.dumps(compact_context, ensure_ascii=False, sort_keys=True)}"
        )
        return {"structured_context": structured_context, "prompt_text": prompt_text}
