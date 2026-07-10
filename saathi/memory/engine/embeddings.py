"""M9 embedding provider abstraction.

One interface, several adapters. The DEFAULT is a deterministic local embedder
(numpy, hashed char-n-gram bag → fixed-dim unit vector) that needs no external
service, so semantic retrieval is genuinely functional offline and tests are
reproducible. Cloud/ST/Ollama adapters share the contract and degrade
gracefully (available()==False) when their lib/keys are absent — never faked.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class EmbedResult:
    vectors: list[np.ndarray]
    version: str
    dim: int
    provider: str
    usage: dict = field(default_factory=dict)


class EmbeddingProvider:
    version = "base-0"
    dim = 0
    provider = "base"

    def available(self) -> bool:
        return False

    def embed(self, texts: list[str]) -> EmbedResult:  # pragma: no cover
        raise NotImplementedError


class LocalDeterministicEmbedder(EmbeddingProvider):
    """Hashed char-3-gram bag-of-features → L2-normalized vector.

    Deterministic, dependency-free, ~instant. Semantically meaningful for
    lexical/character overlap (shared words/roots cluster), which is a real,
    reproducible signal — not random. Default + test provider.
    """
    provider = "local-deterministic"

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.version = f"local-det-v1-d{dim}"

    def available(self) -> bool:
        return True

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        t = f"  {text.lower()}  "
        # word features + char trigrams
        feats = t.split()
        for i in range(len(t) - 2):
            feats.append(t[i:i + 3])
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        n = float(np.linalg.norm(vec))
        return vec / n if n > 0 else vec

    def embed(self, texts: list[str]) -> EmbedResult:
        vecs = [self._one(t) for t in texts]
        return EmbedResult(vectors=vecs, version=self.version, dim=self.dim,
                           provider=self.provider,
                           usage={"count": len(texts), "cost_usd": 0.0})


class SentenceTransformerEmbedder(EmbeddingProvider):
    """Local ST model adapter — available() only if the lib imports."""
    provider = "sentence-transformer"

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        self.model_name = model
        self.version = f"st-{model}"
        self._model = None
        self.dim = 384

    def available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
            return True
        except Exception:
            return False

    def embed(self, texts: list[str]) -> EmbedResult:  # pragma: no cover - no lib in env
        from sentence_transformers import SentenceTransformer
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        arr = self._model.encode(texts, normalize_embeddings=True)
        vecs = [np.asarray(v, dtype=np.float32) for v in arr]
        self.dim = len(vecs[0]) if vecs else self.dim
        return EmbedResult(vectors=vecs, version=self.version, dim=self.dim,
                           provider=self.provider, usage={"count": len(texts)})


class OllamaEmbedder(EmbeddingProvider):
    """Ollama /api/embeddings adapter — available() only if the daemon answers."""
    provider = "ollama"

    def __init__(self, model: str = "nomic-embed-text",
                 base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.version = f"ollama-{model}"
        self.dim = 768

    def available(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def embed(self, texts: list[str]) -> EmbedResult:  # pragma: no cover - no daemon in env
        import httpx
        vecs = []
        for t in texts:
            r = httpx.post(f"{self.base_url}/api/embeddings",
                           json={"model": self.model, "prompt": t}, timeout=30)
            v = np.asarray(r.json()["embedding"], dtype=np.float32)
            n = float(np.linalg.norm(v))
            vecs.append(v / n if n > 0 else v)
        self.dim = len(vecs[0]) if vecs else self.dim
        return EmbedResult(vectors=vecs, version=self.version, dim=self.dim,
                           provider=self.provider, usage={"count": len(texts)})


# Cloud adapters (OpenAI/Gemini) intentionally omitted from auto-selection —
# they route model calls and would need ExecutionGateway wiring + keys. The
# contract above is the extension point; add an adapter with available()/embed().

_PROVIDERS: dict[str, EmbeddingProvider] = {}


def register(name: str, provider: EmbeddingProvider) -> None:
    _PROVIDERS[name] = provider


def select_provider(prefer: str = "auto") -> EmbeddingProvider:
    """Local-first selection. `prefer` may name a registered provider; falls
    back to the deterministic local embedder, which is always available."""
    if prefer != "auto" and prefer in _PROVIDERS and _PROVIDERS[prefer].available():
        return _PROVIDERS[prefer]
    for name in ("sentence-transformer", "ollama"):
        p = _PROVIDERS.get(name)
        if p and p.available():
            return p
    return _PROVIDERS["local"]


def _bootstrap() -> None:
    if "local" not in _PROVIDERS:
        register("local", LocalDeterministicEmbedder())
        register("sentence-transformer", SentenceTransformerEmbedder())
        register("ollama", OllamaEmbedder())


_bootstrap()


def to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_bytes(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
