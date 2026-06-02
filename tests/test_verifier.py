from evidencekg.config.task_config import load_task_config
from evidencekg.graph.graph_store import GraphStore
from evidencekg.verify.verifier import Verifier


def test_verifier_rejects_bad_evidence_grounding_for_accept():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = {"candidate_id": "c_x", "head": "ip_001", "relation": config.target_relation, "tail": "team_payment"}
    context = {"candidate": candidate, "evidence_snippets": [{"evidence_id": "ev_001"}]}
    prediction = {
        "decision": "accept",
        "confidence": 0.9,
        "reason": "bad evidence id",
        "supporting_evidence_ids": ["ev_missing"],
    }

    verified = Verifier().verify(candidate, context, prediction, config, graph)

    assert verified["decision"] == "reject"
    assert verified["verifier_status"] == "failed"
    assert not verified["verifier_details"]["evidence_grounding"]


def test_verifier_allows_grounded_accept():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = {"candidate_id": "c_x", "head": "ip_001", "relation": config.target_relation, "tail": "team_payment"}
    context = {"candidate": candidate, "evidence_snippets": [{"evidence_id": "ev_001"}]}
    prediction = {
        "decision": "accept",
        "confidence": 0.9,
        "reason": "grounded",
        "supporting_evidence_ids": ["ev_001"],
    }

    verified = Verifier().verify(candidate, context, prediction, config, graph)

    assert verified["decision"] == "accept"
    assert verified["verifier_status"] == "passed"


def test_verifier_rejects_schema_illegal_candidate():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = {"candidate_id": "c_bad", "head": "ticket_001", "relation": config.target_relation, "tail": "team_payment"}
    context = {"candidate": candidate, "evidence_snippets": [{"evidence_id": "ev_001"}]}
    prediction = {
        "decision": "accept",
        "confidence": 0.9,
        "reason": "schema should fail",
        "supporting_evidence_ids": ["ev_001"],
    }

    verified = Verifier().verify(candidate, context, prediction, config, graph)

    assert verified["decision"] == "reject"
    assert verified["verifier_status"] == "failed"
    assert not verified["verifier_details"]["schema_consistency"]
