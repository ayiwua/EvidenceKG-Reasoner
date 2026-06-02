from evidencekg.candidate.generator import CandidateGenerator
from evidencekg.config.task_config import load_task_config
from evidencekg.graph.graph_store import GraphStore


def test_candidates_use_schema_filter_and_structural_rules():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidates = CandidateGenerator().generate(config, graph)

    assert 50 <= len(candidates) <= 150
    for candidate in candidates:
        assert candidate["relation"] == config.target_relation
        assert "type_rule" not in candidate["generation_rules"]
        assert set(candidate["generation_rules"]) & {"two_hop_path", "common_neighbor", "evidence_overlap"}
        assert candidate["candidate_score"] > 0
        assert "rule_scores" in candidate
        head = graph.get_entity(candidate["head"])
        tail = graph.get_entity(candidate["tail"])
        assert config.is_allowed_pair(head["type"], tail["type"])


def test_type_only_pair_is_not_generated():
    config = load_task_config("configs/task_owned_by.yaml")
    graph = GraphStore.from_dir("data/sample")
    candidates = CandidateGenerator().generate(config, graph)
    keys = {(item["head"], item["tail"]) for item in candidates}

    assert ("db_inventory", "person_alice") not in keys

