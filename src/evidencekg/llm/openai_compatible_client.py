from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from evidencekg.config.task_config import LLMConfig
from evidencekg.llm.base_client import LLMRequest, LLMResponse


class OpenAICompatibleClient:
    """OpenAI SDK client for OpenAI-compatible chat completions APIs."""

    def __init__(self, config: LLMConfig | dict[str, Any]) -> None:
        self.config = config
        self.provider = "openai_compatible"
        self._load_dotenv()
        self.model = self._env_config_value("model_env", "model", "gpt-4o-mini")

    def chat(self, request: LLMRequest, **kwargs: Any) -> LLMResponse:
        api_key_env = str(self._config_value("api_key_env", "LLM_API_KEY"))
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var for openai_compatible provider: {api_key_env}")
        base_url = self._env_config_value("base_url_env", "base_url", "")
        if not base_url:
            raise RuntimeError("missing base URL for openai_compatible provider; set LLM_BASE_URL or base_url")
        model = self._env_config_value("model_env", "model", self.model)
        timeout_value = float(self._config_value("timeout", self._config_value("timeout_seconds", 30.0)))
        request_timeout = None if timeout_value <= 0 else timeout_value
        start = time.perf_counter()
        client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/",
            http_client=httpx.Client(timeout=request_timeout, trust_env=False),
        )
        completion = client.chat.completions.create(
            model=model,
            temperature=float(self._config_value("temperature", 0.0)),
            max_tokens=int(self._config_value("max_tokens", 800)),
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        )
        content = completion.choices[0].message.content or ""
        if not content:
            raise RuntimeError("openai_compatible provider response missing content")
        usage = getattr(completion, "usage", None)
        return LLMResponse(
            provider=self.provider,
            model=model,
            content=content,
            latency_ms=int((time.perf_counter() - start) * 1000),
            usage={
                "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            },
            raw={"id": getattr(completion, "id", "")},
        )

    def _load_dotenv(self) -> None:
        env_path = Path(".env")
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    def _config_value(self, key: str, default: Any = None) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    def _env_config_value(self, env_key_name: str, config_key: str, default: str) -> str:
        env_name = str(self._config_value(env_key_name, ""))
        if env_name and os.environ.get(env_name):
            return str(os.environ[env_name])
        return str(self._config_value(config_key, default))
