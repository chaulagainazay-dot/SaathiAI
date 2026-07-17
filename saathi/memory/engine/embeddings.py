"""M9 embedding provider abstraction.

One interface, several adapters. The DEFAULT is a deterministic local embedder
(numpy, hashed char-n-gram bag → fixed-dim unit vector) that needs no external
service, so semantic retrieval is genuinely functional offline and tests are
reproducible. Cloud/ST/Ollama adapters share the contract and degrade
gracefully (available()==False) when their lib/keys/models are absent — never faked.

Auto-selection must not pick a provider whose runtime is present but whose
embedding model is missing (silent None embeddings are forbidden).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class EmbedResult:
    vectors: list[np.ndarray]
    version: str
    dim: int
    provider: str
    usage: dict = field(default_factory=dict)


@dataclass
class ProviderReadiness:
    """Precise readiness for an embedding provider (no downloads)."""

    name: str
    ready: bool
    reason: str = "ok"
    detail: str = ""
    model: str = ""
    runtime_reachable: bool = False
    model_available: bool = False
    dimension_valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ready": self.ready,
            "reason": self.reason,
            "detail": self.detail,
            "model": self.model,
            "runtime_reachable": self.runtime_reachable,
            "model_available": self.model_available,
            "dimension_valid": self.dimension_valid,
        }


class EmbeddingProvider:
    version = "base-0"
    dim = 0
    provider = "base"

    def available(self) -> bool:
        return False

    def readiness(self) -> ProviderReadiness:
        """Structured readiness. Default maps available()."""
        ok = self.available()
        return ProviderReadiness(
            name=self.provider,
            ready=ok,
            reason="ok" if ok else "unavailable",
            dimension_valid=bool(self.dim and self.dim > 0),
        )

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

    def readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            name=self.provider,
            ready=True,
            reason="ok",
            runtime_reachable=True,
            model_available=True,
            dimension_valid=self.dim > 0,
        )

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

    def readiness(self) -> ProviderReadiness:
        ok = self.available()
        return ProviderReadiness(
            name=self.provider,
            ready=ok,
            reason="ok" if ok else "sentence_transformers_not_installed",
            model=self.model_name,
            runtime_reachable=ok,
            model_available=ok,
            dimension_valid=self.dim > 0,
        )

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
    """Ollama /api/embeddings adapter.

    ``available()`` / ``readiness()`` require runtime reachable **and** the
    configured embedding model present in ``/api/tags``. Daemon up alone is not
    enough (prevents silent empty embeddings when nomic-embed-text is missing).
    """
    provider = "ollama"

    def __init__(self, model: str = "nomic-embed-text",
                 base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.version = f"ollama-{model}"
        self.dim = 768
        self._last_readiness: Optional[ProviderReadiness] = None

    def _list_model_names(self) -> tuple[bool, list[str], str]:
        """Return (reachable, names, error). Bounded, no downloads."""
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            if r.status_code != 200:
                return False, [], f"http_{r.status_code}"
            data = r.json() if r.content else {}
            names: list[str] = []
            for m in (data.get("models") or []):
                if isinstance(m, dict) and m.get("name"):
                    names.append(str(m["name"]))
                elif isinstance(m, str):
                    names.append(m)
            return True, names, ""
        except Exception as e:
            return False, [], type(e).__name__

    def _model_present(self, names: list[str]) -> bool:
        target = (self.model or "").lower()
        if not target:
            return False
        for n in names:
            nl = n.lower()
            # exact or tag prefix (nomic-embed-text:latest)
            if nl == target or nl.startswith(target + ":") or target in nl:
                return True
        return False

    def readiness(self) -> ProviderReadiness:
        reachable, names, err = self._list_model_names()
        if not reachable:
            pr = ProviderReadiness(
                name=self.provider,
                ready=False,
                reason="runtime_unreachable",
                detail=err,
                model=self.model,
                runtime_reachable=False,
                model_available=False,
                dimension_valid=self.dim > 0,
            )
            self._last_readiness = pr
            return pr
        present = self._model_present(names)
        if not present:
            pr = ProviderReadiness(
                name=self.provider,
                ready=False,
                reason="embedding_model_missing",
                detail=f"model {self.model!r} not in ollama tags",
                model=self.model,
                runtime_reachable=True,
                model_available=False,
                dimension_valid=self.dim > 0,
            )
            self._last_readiness = pr
            return pr
        pr = ProviderReadiness(
            name=self.provider,
            ready=True,
            reason="ok",
            model=self.model,
            runtime_reachable=True,
            model_available=True,
            dimension_valid=self.dim > 0,
        )
        self._last_readiness = pr
        return pr

    def available(self) -> bool:
        return self.readiness().ready

    def embed(self, texts: list[str]) -> EmbedResult:
        ready = self.readiness()
        if not ready.ready:
            raise RuntimeError(
                f"ollama embedder not ready: {ready.reason} ({ready.detail})"
            )
        import httpx
        vecs = []
        for t in texts:
            r = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": t},
                timeout=30,
            )
            if r.status_code != 200:
                raise RuntimeError(f"ollama embeddings HTTP {r.status_code}")
            body = r.json() if r.content else {}
            emb = body.get("embedding")
            if not emb:
                raise RuntimeError("ollama embeddings returned empty embedding")
            v = np.asarray(emb, dtype=np.float32)
            if v.size == 0:
                raise RuntimeError("ollama embeddings returned zero-size vector")
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


def get_registered(name: str) -> Optional[EmbeddingProvider]:
    return _PROVIDERS.get(name)


def select_provider(prefer: str = "auto") -> EmbeddingProvider:
    """Local-first selection with readiness gating.

    * ``prefer="auto"``: first *ready* optional provider (ST, then Ollama with
      embedding model present), else deterministic local.
    * ``prefer="local"`` / ``"local-deterministic"``: always deterministic.
    * ``prefer="ollama"``: Ollama only if ready; otherwise raises so callers
      see a precise failure (does not silently pick local).
    * other names: registered provider if ready, else local for unknown names
      that are not explicit external providers.
    """
    _bootstrap()
    key = (prefer or "auto").strip().lower()

    if key in {"local", "local-deterministic", "deterministic"}:
        return _PROVIDERS["local"]

    if key == "auto":
        for name in ("sentence-transformer", "ollama"):
            p = _PROVIDERS.get(name)
            if p is None:
                continue
            if p.readiness().ready:
                return p
        return _PROVIDERS["local"]

    # Explicit named provider
    p = _PROVIDERS.get(key)
    if p is None:
        # Unknown name → local (safe default for legacy call sites)
        return _PROVIDERS["local"]
    ready = p.readiness()
    if ready.ready:
        return p
    # Explicit ollama/st must not silently fall back — fail closed
    if key in {"ollama", "sentence-transformer"}:
        raise RuntimeError(
            f"embedding provider {key!r} not ready: {ready.reason} "
            f"({ready.detail})"
        )
    return _PROVIDERS["local"]


def _bootstrap() -> None:
    if "local" not in _PROVIDERS:
        register("local", LocalDeterministicEmbedder())
        register("local-deterministic", LocalDeterministicEmbedder())
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
