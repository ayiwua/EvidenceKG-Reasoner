from evidencekg.candidate.generator import CandidateGenerator
from evidencekg.config.task_config import load_task_config
from evidencekg.graph.graph_store import GraphStore
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever


def test_evidence_context_is_traceable_and_limited():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(config, graph)[0]
    context = EvidenceRetriever().retrieve(candidate, config, graph)

    assert context["candidate_id"] == candidate["candidate_id"]
    assert context["head_profile"]["entity_id"] == candidate["head"]
    assert context["tail_profile"]["entity_id"] == candidate["tail"]
    assert len(context["graph_paths"]) <= config.evidence_retrieval.max_paths
    assert len(context["evidence_snippets"]) <= config.evidence_retrieval.max_evidence_snippets
    assert all("evidence_id" in item for item in context["evidence_snippets"])
    assert context["related_triples"]

