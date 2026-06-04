from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI, OpenAIError

from evidencekg.config.task_config import LLMConfig


class OpenAICompatibleClient:
    """OpenAI SDK client for OpenAI-compatible chat completions APIs."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.last_metadata: dict[str, Any] = {}
        self._load_dotenv()

    def complete(
        self,
        prompt_text: str,
        attempt_index: int = 1,
        total_attempts: int = 1,
        candidate_id: str | None = None,
        debug_timing: bool = False,
    ) -> str:
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var: {self.config.api_key_env}")

        base_url = os.environ.get(self.config.base_url_env, self.config.base_url)
        model = os.environ.get(self.config.model_env, self.config.model)
        trust_env = os.environ.get("LLM_TRUST_ENV", str(self.config.trust_env)).lower() in {"1", "true", "yes"}
        request_timeout = None if self.config.timeout_seconds <= 0 else self.config.timeout_seconds
        timeout_label = "none" if request_timeout is None else f"{request_timeout}s"
        start = time.perf_counter()
        wall_start = time.time()
        candidate_label = candidate_id or "unknown"
        self.last_metadata = {
            "candidate_id": candidate_id,
            "attempt_index": attempt_index,
            "total_attempts": total_attempts,
            "model": model,
            "base_url": base_url,
            "timeout_seconds": request_timeout,
            "request_start": wall_start,
            "response_received": None,
            "elapsed_seconds": 0.0,
            "error_type": "",
            "error": "",
        }
        print(
            "[llm-client] "
            f"attempt={attempt_index}/{total_attempts} "
            f"model={model} timeout={timeout_label} "
            f"retries={self.config.max_retries} base_url={base_url}",
            file=sys.stderr,
            flush=True,
        )
        client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/",
            http_client=httpx.Client(timeout=request_timeout, trust_env=trust_env),
        )

        stop_heartbeat = threading.Event()
        heartbeat = None
        if debug_timing:
            heartbeat = threading.Thread(
                target=self._heartbeat,
                args=(candidate_label, start, stop_heartbeat),
                daemon=True,
            )
            heartbeat.start()
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=self.config.temperature,
                messages=[
                    {
                        "role": "system",
                        "content": "You return only valid JSON for evidence-grounded KG relation judgments.",
                    },
                    {"role": "user", "content": prompt_text},
                ],
            )
        except OpenAIError as exc:
            stop_heartbeat.set()
            if heartbeat is not None:
                heartbeat.join(timeout=0.2)
            elapsed = time.perf_counter() - start
            error_type = self._classify_error(exc)
            self.last_metadata.update(
                {
                    "response_received": time.time(),
                    "elapsed_seconds": round(elapsed, 3),
                    "error_type": error_type,
                    "error": str(exc),
                }
            )
            print(
                f"[llm-client][warning] attempt={attempt_index}/{total_attempts} "
                f"elapsed={elapsed:.2f}s error_type={error_type} error={exc}",
                file=sys.stderr,
                flush=True,
            )
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        finally:
            stop_heartbeat.set()
            if heartbeat is not None:
                heartbeat.join(timeout=0.2)

        content = completion.choices[0].message.content
        if not content:
            elapsed = time.perf_counter() - start
            self.last_metadata.update(
                {
                    "response_received": time.time(),
                    "elapsed_seconds": round(elapsed, 3),
                    "error_type": "provider_error",
                    "error": "LLM response did not contain message content",
                }
            )
            raise ValueError("LLM response did not contain message content")
        elapsed = time.perf_counter() - start
        self.last_metadata.update(
            {
                "response_received": time.time(),
                "elapsed_seconds": round(elapsed, 3),
                "error_type": "",
                "error": "",
            }
        )
        print(
            f"[llm-client] attempt={attempt_index}/{total_attempts} elapsed={elapsed:.2f}s received_content=true",
            file=sys.stderr,
            flush=True,
        )
        return content

    def _heartbeat(self, candidate_id: str, start: float, stop_event: threading.Event) -> None:
        while not stop_event.wait(10):
            elapsed = int(time.perf_counter() - start)
            print(
                f"[llm] candidate={candidate_id} still waiting... elapsed={elapsed}s",
                file=sys.stderr,
                flush=True,
            )

    def _classify_error(self, exc: OpenAIError) -> str:
        text = str(exc).lower()
        if "timed out" in text or "timeout" in text:
            return "timeout"
        return "provider_error"

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
