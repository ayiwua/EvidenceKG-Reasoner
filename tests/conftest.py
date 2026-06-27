from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _tokens(text: str) -> list[str]:
    return text.lower().replace("/", " ").replace("-", " ").replace("_", " ").split()


class FakeSentenceTransformer:
    init_count = 0
    encode_count = 0

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        type(self).init_count += 1

    def encode(self, texts: list[str]) -> list[list[float]]:
        type(self).encode_count += 1
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        vector = [0.0] * 64
        for token in _tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            vector[int(digest[:8], 16) % len(vector)] += 1.0
        return vector


class FakeCrossEncoder:
    init_count = 0
    predict_count = 0

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        type(self).init_count += 1

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        type(self).predict_count += 1
        scores: list[float] = []
        for query, evidence_text in pairs:
            query_tokens = set(_tokens(query))
            evidence_tokens = set(_tokens(evidence_text))
            if not query_tokens or not evidence_tokens:
                scores.append(0.0)
            else:
                scores.append(len(query_tokens & evidence_tokens) / len(query_tokens | evidence_tokens))
        return scores


@pytest.fixture(autouse=True)
def fake_sentence_transformers(monkeypatch):
    FakeSentenceTransformer.init_count = 0
    FakeSentenceTransformer.encode_count = 0
    FakeCrossEncoder.init_count = 0
    FakeCrossEncoder.predict_count = 0
    module = types.SimpleNamespace(
        SentenceTransformer=FakeSentenceTransformer,
        CrossEncoder=FakeCrossEncoder,
        FakeSentenceTransformer=FakeSentenceTransformer,
        FakeCrossEncoder=FakeCrossEncoder,
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return module
