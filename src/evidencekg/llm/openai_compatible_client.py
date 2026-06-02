from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from evidencekg.config.task_config import LLMConfig


class OpenAICompatibleClient:
    """Small stdlib client for OpenAI-compatible chat completions APIs."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._load_dotenv()

    def complete(self, prompt_text: str) -> str:
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var: {self.config.api_key_env}")

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": os.environ.get("OPENAI_MODEL", self.config.model),
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "You return only valid JSON for evidence-grounded KG relation judgments.",
                },
                {"role": "user", "content": prompt_text},
            ],
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM response did not contain choices[0].message.content") from exc

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
