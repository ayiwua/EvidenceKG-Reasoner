from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evidencekg.llm.anthropic_client import AnthropicClient
from evidencekg.llm.local_client import LocalClient
from evidencekg.llm.mock_client import MockLLMClient
from evidencekg.llm.openai_compatible_client import OpenAICompatibleClient


class ClientFactory:
    @classmethod
    def from_yaml(cls, path: str | Path) -> Any:
        return cls.from_config(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Any:
        provider_name = str(config.get("provider", "mock"))
        provider_config = dict(config.get("providers", {}).get(provider_name, {}))
        merged = dict(config)
        merged.update(provider_config)
        merged["provider"] = provider_name
        if provider_name == "mock":
            return MockLLMClient(merged)
        if provider_name == "openai_compatible":
            return OpenAICompatibleClient(merged)
        if provider_name == "anthropic":
            return AnthropicClient(merged)
        if provider_name == "local":
            return LocalClient(merged)
        raise ValueError(f"unsupported llm provider: {provider_name}")
