from __future__ import annotations

import os
import time
from typing import Any

from evidencekg.llm.base_client import LLMRequest, LLMResponse


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, config: dict[str, Any]) -> None:
        model_env = str(config.get("model_env", "ANTHROPIC_MODEL"))
        self.model = os.environ.get(model_env, str(config.get("model", "claude-3-5-sonnet-latest")))
        self.api_key_env = str(config.get("api_key_env", "ANTHROPIC_API_KEY"))
        self.max_tokens = int(config.get("max_tokens", 800))
        self.temperature = float(config.get("temperature", 0.0))

    def chat(self, request: LLMRequest, **kwargs: Any) -> LLMResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var for anthropic provider: {self.api_key_env}")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic package is required for anthropic provider") from exc

        start = time.perf_counter()
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=request.system_prompt,
            messages=[{"role": "user", "content": request.user_prompt}],
        )
        content = "".join(getattr(block, "text", "") for block in response.content)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            latency_ms=int((time.perf_counter() - start) * 1000),
            usage={
                "input_tokens": int(getattr(response.usage, "input_tokens", 0)),
                "output_tokens": int(getattr(response.usage, "output_tokens", 0)),
            },
            raw={"id": getattr(response, "id", "")},
        )
