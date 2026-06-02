from evidencekg.config.task_config import load_task_config


def test_task_config_loads_target_relation_and_mock_mode():
    config = load_task_config("configs/task_owned_by.yaml")

    assert config.target_relation == "likely_owned_by"
    assert "type_rule" not in config.candidate_rules
    assert config.llm.mode == "mock"
    assert config.llm.best_of_n == 1
    assert config.is_allowed_pair("ip", "team")

