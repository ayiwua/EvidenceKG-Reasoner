from evidencekg.llm.reasoner import MockReasoner


def test_mock_reasoner_uses_structured_context():
    context = {
        "candidate": {"head": "ip_001", "relation": "likely_owned_by", "tail": "team_payment", "candidate_score": 0.7},
        "graph_paths": [["ip_001", "service_payment_api", "team_payment"]],
        "common_neighbors": ["service_payment_api"],
        "evidence_snippets": [{"evidence_id": "ev_001"}],
    }

    prediction = MockReasoner().predict(context)

    assert prediction["decision"] == "accept"
    assert 0.0 <= prediction["confidence"] <= 1.0
    assert prediction["supporting_evidence_ids"] == ["ev_001"]

