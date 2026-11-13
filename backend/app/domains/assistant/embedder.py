"""Embedding 抽象：Fake（离线确定性哈希 1024 维）与 OpenAI 兼容 /embeddings。"""
import hashlib
import math
import re
from typing import Protocol

import httpx

from app.core.http import assert_safe_external_url

DIM = 1024
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """确定性哈希嵌入：token sha256 → 1024 桶累加 ±1（按哈希奇偶），L2 归一化。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vec = [0.0] * DIM
        for token in _TOKEN_RE.findall(text):
            hh = hashlib.sha256(token.encode("utf-8")).hexdigest()
            vec[int(hh[:8], 16) % DIM] += 1.0 if int(hh[-1], 16) % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec


class OpenAICompatEmbedder:
    def __init__(self, base_url: str, api_key: str, model: str,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        assert_safe_external_url(f"{self.base_url}/embeddings")
        with httpx.Client(transport=self._transport, timeout=60) as client:
            resp = client.post(f"{self.base_url}/embeddings",
                               headers={"Authorization": f"Bearer {self.api_key}"},
                               json={"model": self.model, "input": texts})
            resp.raise_for_status()
            data = resp.json()["data"]
        ordered = sorted(data, key=lambda item: item.get("index", 0))  # 保持输入顺序
        return [item["embedding"] for item in ordered]


def get_embedder() -> Embedder:
    from app.core.config import get_settings
    s = get_settings()
    if s.llm_base_url and s.llm_api_key:
        return OpenAICompatEmbedder(s.llm_base_url, s.llm_api_key, s.llm_model)
    return FakeEmbedder()
