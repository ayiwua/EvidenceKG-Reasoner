from evidencekg.config.task_config import LLMConfig, load_task_config
from evidencekg.llm.base_client import LLMResponse
from evidencekg.llm.reasoner import RealLLMReasoner


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_metadata = {
            "request_start": 1.0,
            "response_received": 2.0,
            "elapsed_seconds": 1.0,
            "error_type": "",
        }

    def chat(self, request, **kwargs):
        assert "Candidate:" in request.user_prompt
        return LLMResponse("fake", "fake-model", self.content, 0)


class FailingClient:
    last_metadata = {
        "request_start": 1.0,
        "response_received": 2.0,
        "elapsed_seconds": 1.0,
        "error_type": "provider_error",
    }

    def chat(self, request, **kwargs):
        raise RuntimeError("network unavailable")


def test_real_config_loads_openai_compatible_fields():
    config = load_task_config("configs/task_owned_by_real.yaml")

    assert config.llm.mode == "real"
    assert config.llm.provider == "openai_compatible"
    assert config.llm.best_of_n == 1
    assert config.llm.api_key_env == "LLM_API_KEY"
    assert config.llm.base_url_env == "LLM_BASE_URL"
    assert config.llm.model_env == "LLM_MODEL"
    assert config.llm.trust_env is False
    assert config.llm.timeout_seconds == 15
    assert config.llm.max_retries == 1


def test_real_reasoner_parses_json_output():
    client = FakeClient(
        '{"decision":"accept","confidence":0.82,"reason":"supported",'
        '"supporting_evidence_ids":["ev_001"]}'
    )
    reasoner = RealLLMReasoner(LLMConfig(mode="real", max_retries=0), client=client)

    prediction = reasoner.predict({}, "Candidate: ip_001 likely_owned_by team_payment")

    assert prediction == {
        "decision": "accept",
        "confidence": 0.82,
        "reason": "supported",
        "supporting_evidence_ids": ["ev_001"],
    }


def test_real_reasoner_degrades_on_provider_failure():
    reasoner = RealLLMReasoner(LLMConfig(mode="real", max_retries=0), client=FailingClient())

    prediction = reasoner.predict({}, "Candidate: ip_001 likely_owned_by team_payment")

    assert prediction["decision"] == "uncertain"
    assert prediction["confidence"] == 0.0
    assert "network unavailable" in prediction["reason"]
