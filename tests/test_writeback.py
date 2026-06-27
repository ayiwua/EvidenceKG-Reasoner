from pathlib import Path

from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import read_jsonl
from evidencekg.writeback import EdgeWriter, KGWritebackManager


def _prediction(
    candidate_id: str = "c_001",
    head: str = "ip_001",
    relation: str = "likely_owned_by",
    tail: str = "team_payment",
    decision: str = "accept",
    verifier_status: str = "passed",
) -> dict:
    return {
        "prediction_id": f"p_{candidate_id}",
        "candidate_id": candidate_id,
        "head": head,
        "relation": relation,
        "tail": tail,
        "decision": decision,
        "confidence": 0.91,
        "reason": "verified owner edge",
        "supporting_evidence_ids": ["ev_001"],
        "verifier_status": verifier_status,
        "verifier_details": {"evidence_grounding": True},
    }


def test_verifier_failed_prediction_is_not_written(tmp_path):
    graph = GraphStore.from_dir("data/sample")
    report = EdgeWriter().write_pending([_prediction(verifier_status="failed")], graph, tmp_path)

    assert read_jsonl(tmp_path / "pending_edges.jsonl") == []
    assert report["written_count"] == 0
    assert report["pending"] == 0


def test_accept_passed_prediction_writes_pending_edge(tmp_path):
    graph = GraphStore.from_dir("data/sample")
    report = EdgeWriter().write_pending([_prediction()], graph, tmp_path)
    edges = read_jsonl(tmp_path / "pending_edges.jsonl")

    assert report["pending"] == 1
    assert report["written_count"] == 1
    assert len(edges) == 1
    edge = edges[0]
    assert edge["head"] == "ip_001"
    assert edge["tail"] == "team_payment"
    assert edge["evidence_ids"] == ["ev_001"]
    assert edge["confidence"] == 0.91
    assert edge["reason"] == "verified owner edge"
    assert edge["candidate_id"] == "c_001"
    assert edge["verifier_details"] == {"evidence_grounding": True}


def test_duplicate_prediction_is_not_written_twice(tmp_path):
    graph = GraphStore.from_dir("data/sample")
    predictions = [_prediction(candidate_id="c_001"), _prediction(candidate_id="c_002")]
    report = EdgeWriter().write_pending(predictions, graph, tmp_path)
    edges = read_jsonl(tmp_path / "pending_edges.jsonl")

    assert len(edges) == 1
    assert report["skipped_duplicate"] == 1
    assert report["written_count"] == 1


def test_conflicting_prediction_is_skipped(tmp_path):
    graph = GraphStore.from_dir("data/sample")
    predictions = [
        _prediction(candidate_id="c_001", tail="team_payment"),
        _prediction(candidate_id="c_002", tail="team_auth"),
    ]
    report = EdgeWriter().write_pending(predictions, graph, tmp_path)
    edges = read_jsonl(tmp_path / "pending_edges.jsonl")

    assert len(edges) == 1
    assert report["skipped_conflict"] == 1


def test_enriched_triples_contains_original_triples_plus_approved_edges(tmp_path):
    graph = GraphStore.from_dir("data/sample")
    original_count = len(graph.iter_triples())
    report = KGWritebackManager().writeback([_prediction()], graph, tmp_path, mode="approved")
    enriched = read_jsonl(tmp_path / "triples.enriched.jsonl")

    assert report["approved"] == 1
    assert len(enriched) == original_count + 1
    assert enriched[-1]["candidate_id"] == "c_001"


def test_original_triples_file_is_not_overwritten(tmp_path):
    original_path = Path("data/sample/triples.jsonl")
    before = original_path.read_text(encoding="utf-8")
    graph = GraphStore.from_dir("data/sample")

    EdgeWriter().write_approved([_prediction()], graph, tmp_path)

    assert original_path.read_text(encoding="utf-8") == before
