from __future__ import annotations

import os
import time
from typing import Any

import httpx

from evidencekg.llm.base_client import LLMRequest, LLMResponse


class LocalClient:
    provider = "local"

    def __init__(self, config: dict[str, Any]) -> None:
        model_env = str(config.get("model_env", "LOCAL_LLM_MODEL"))
        base_url_env = str(config.get("base_url_env", "LOCAL_LLM_BASE_URL"))
        self.model = os.environ.get(model_env, str(config.get("model", "local-model")))
        self.base_url = os.environ.get(base_url_env, str(config.get("base_url", "http://localhost:8000/chat")))
        self.timeout = float(config.get("timeout", 30))

    def chat(self, request: LLMRequest, **kwargs: Any) -> LLMResponse:
        start = time.perf_counter()
        payload = {
            "model": self.model,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            **kwargs,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.base_url, json=payload)
            response.raise_for_status()
            raw = response.json()
        content = str(raw.get("content") or raw.get("message") or "")
        if not content:
            raise RuntimeError("local provider response missing content")
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            latency_ms=int((time.perf_counter() - start) * 1000),
            usage=dict(raw.get("usage", {})),
            raw=raw,
        )
