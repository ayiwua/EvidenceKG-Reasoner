from evidencekg.prompting.prompt_builder import PromptBuilder


def test_prompt_builder_returns_structured_context_and_prompt_text():
    evidence_context = {
        "candidate_id": "c_001",
        "candidate": {"head": "ip_001", "relation": "rel", "tail": "team_a"},
        "head_profile": {},
        "tail_profile": {},
        "graph_paths": [],
        "common_neighbors": [],
        "related_triples": [],
        "evidence_snippets": [],
    }

    built = PromptBuilder().build(evidence_context)

    assert built["structured_context"]["candidate_id"] == "c_001"
    assert "Candidate:" in built["prompt_text"]
    assert "Context JSON:" in built["prompt_text"]
