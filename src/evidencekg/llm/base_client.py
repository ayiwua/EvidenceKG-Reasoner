from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    provider: str
    model: str
    content: str
    latency_ms: int
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class BaseLLMClient(Protocol):
    provider: str
    model: str

    def chat(self, request: LLMRequest, **kwargs: Any) -> LLMResponse:
        ...
