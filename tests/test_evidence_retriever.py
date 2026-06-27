from dataclasses import replace

from evidencekg.candidate.generator import CandidateGenerator
from evidencekg.config.task_config import load_task_config
from evidencekg.graph.graph_store import GraphStore
from evidencekg.prompting.prompt_builder import PromptBuilder
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever
from evidencekg.verify.verifier import Verifier


def test_evidence_context_uses_two_stage_retrieval_and_is_limited():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(config, graph)[0]
    context = EvidenceRetriever().retrieve(candidate, config, graph)

    assert context["candidate_id"] == candidate["candidate_id"]
    assert context["head_profile"]["entity_id"] == candidate["head"]
    assert context["tail_profile"]["entity_id"] == candidate["tail"]
    assert len(context["graph_paths"]) <= config.evidence_retrieval.max_paths
    assert len(context["evidence_snippets"]) <= config.evidence_retrieval.top_k_after_rerank
    assert all("evidence_id" in item for item in context["evidence_snippets"])
    assert all("embedding_score" in item for item in context["evidence_snippets"])
    assert all("rerank_score" in item for item in context["evidence_snippets"])
    assert all("retrieval_query" in item for item in context["evidence_snippets"])
    assert [item["retrieval_rank"] for item in context["evidence_snippets"]] == list(
        range(1, len(context["evidence_snippets"]) + 1)
    )
    assert context["related_triples"]


def test_top_k_after_rerank_controls_snippet_count():
    base_config = load_task_config("configs/task_owned_by.yaml")
    config = replace(
        base_config,
        evidence_retrieval=replace(base_config.evidence_retrieval, top_k_before_rerank=5, top_k_after_rerank=2),
    )
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(base_config, graph)[0]

    context = EvidenceRetriever().retrieve(candidate, config, graph)

    assert len(context["evidence_snippets"]) == 2


def test_repeated_retrieve_reuses_models_and_encoded_corpus(fake_sentence_transformers):
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidates = CandidateGenerator().generate(config, graph)[:2]
    retriever = EvidenceRetriever()

    retriever.retrieve(candidates[0], config, graph)
    retriever.retrieve(candidates[1], config, graph)

    assert fake_sentence_transformers.FakeSentenceTransformer.init_count == 1
    assert fake_sentence_transformers.FakeCrossEncoder.init_count == 1
    assert fake_sentence_transformers.FakeSentenceTransformer.encode_count == 3


def test_prompt_builder_accepts_reranked_evidence_snippets():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(config, graph)[0]
    context = EvidenceRetriever().retrieve(candidate, config, graph)

    built = PromptBuilder().build(context)

    assert built["structured_context"]["evidence_snippets"][0]["embedding_score"] is not None
    assert "rerank_score" in built["prompt_text"]


def test_verifier_still_rejects_supporting_evidence_outside_context():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(config, graph)[0]
    context = EvidenceRetriever().retrieve(candidate, config, graph)
    prediction = {
        "decision": "accept",
        "confidence": 0.95,
        "reason": "claims unsupported evidence",
        "supporting_evidence_ids": ["not_in_context"],
    }

    verified = Verifier().verify(candidate, context, prediction, config, graph)

    assert verified["verifier_status"] == "failed"
    assert verified["verifier_details"]["evidence_grounding"] is False


def test_verifier_accepts_supporting_evidence_from_context_when_related():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidate = CandidateGenerator().generate(config, graph)[0]
    context = EvidenceRetriever().retrieve(candidate, config, graph)
    related_evidence = next(
        item
        for item in context["evidence_snippets"]
        if candidate["head"] in item.get("related_entities", [])
        or candidate["tail"] in item.get("related_entities", [])
    )
    prediction = {
        "decision": "accept",
        "confidence": 0.95,
        "reason": "uses context evidence",
        "supporting_evidence_ids": [related_evidence["evidence_id"]],
    }

    verified = Verifier().verify(candidate, context, prediction, config, graph)

    assert verified["verifier_details"]["evidence_grounding"] is True
