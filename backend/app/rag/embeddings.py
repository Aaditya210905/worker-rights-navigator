"""
embeddings.py -- Embedding generation via OpenAI-compatible endpoints (OpenRouter,
OpenAI, Ollama) or HuggingFace Inference API.

Default backend:
  OpenAI / OpenRouter:
    EMBEDDING_BACKEND=openai
    EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
    EMBEDDING_API_KEY=<your_key>
    EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b:free
"""

import os
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "openai")

# OpenAI / OpenRouter settings
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b:free")

# Ollama settings (fallback)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-embedding")

# HuggingFace settings (legacy fallback)
HF_MODEL_ID = "Qwen/Qwen3-Embedding-8B"
HF_PROVIDER = "scaleway"

BATCH_SIZE = 16


class EmbeddingClient:
    """
    Generates embeddings using OpenAI-compatible API (OpenRouter/OpenAI),
    Ollama (local), or HuggingFace (cloud).

    Default: OpenRouter with nvidia/nemotron-3-embed-1b:free.
    """

    def __init__(self, api_key: Optional[str] = None, backend: Optional[str] = None):
        self._backend = (backend or EMBEDDING_BACKEND).lower()
        self._dimension = None

        if self._backend in ("openai", "openrouter"):
            self._init_openai(api_key)
        elif self._backend == "huggingface":
            self._init_huggingface(api_key)
        else:
            self._backend = "ollama"
            import ollama
            self._ollama = ollama
            print(f"  [embed] Using Ollama (model={OLLAMA_MODEL})")

    def _init_openai(self, api_key: Optional[str] = None):
        """Initialize OpenAI-compatible embedding client (OpenRouter, OpenAI, etc.)."""
        from openai import OpenAI

        token = api_key or os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
        self._openai_token = token
        self._openai_client = OpenAI(
            base_url=EMBEDDING_BASE_URL,
            api_key=token or "dummy-key",
        )
        self._extra_headers = {
            "HTTP-Referer": "https://workersaathi.in",
            "X-OpenRouter-Title": "WorkerSaathi",
        }
        status = "key loaded" if (token and not token.startswith("<")) else "NO API KEY (fallback enabled)"
        print(f"  [embed] Using OpenAI/OpenRouter model '{EMBEDDING_MODEL}' ({status})")

    def _init_huggingface(self, api_key: Optional[str] = None):
        """Initialize HuggingFace backend."""
        from huggingface_hub import InferenceClient
        token = api_key or os.environ.get("HF_TOKEN", "")
        if not token or token == "hf_YOUR_TOKEN_HERE":
            raise ValueError(
                "HF_TOKEN is required for HuggingFace backend. "
                "Set it in .env or use EMBEDDING_BACKEND=openai"
            )
        self._client = InferenceClient(
            provider=HF_PROVIDER,
            api_key=token,
        )
        print(f"  [embed] Using HuggingFace ({HF_MODEL_ID})")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Handles batching automatically."""
        if not texts:
            return []
        if self._backend in ("openai", "openrouter"):
            return self._embed_openai(texts)
        elif self._backend == "ollama":
            return self._embed_ollama(texts)
        else:
            return self._embed_huggingface(texts)

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text."""
        results = self.embed_texts([query])
        return results[0] if results else []

    @property
    def dimension(self) -> int:
        """Return embedding dimension (discovered after first call or default 2048)."""
        if self._dimension is None:
            token = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
            if token and not token.startswith("<") and self._backend in ("openai", "openrouter"):
                test = self.embed_texts(["test"])
                if test and test[0]:
                    self._dimension = len(test[0])
            if not self._dimension:
                # Default dimension for nemotron-3-embed-1b is 2048
                self._dimension = 2048 if self._backend in ("openai", "openrouter") else 4096
        return self._dimension

    @dimension.setter
    def dimension(self, val: int):
        self._dimension = val

    def _deterministic_fallback_embed(self, text: str, dim: int = 2048) -> list[float]:
        """Deterministic token-frequency vector fallback when embedding API is offline."""
        import math
        import hashlib

        vec = [0.0] * dim
        tokens = text.lower().split()
        if not tokens:
            return vec

        for token in tokens:
            h = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    # ── OpenAI / OpenRouter backend ──────────────────────────────────────────

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed using OpenAI / OpenRouter embeddings API."""
        all_embeddings = []

        token = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
        if not token or token.startswith("<"):
            fallback_dim = self._dimension or 2048
            print(f"  [embed] EMBEDDING_API_KEY not set. Using deterministic semantic fallback.")
            for text in texts:
                all_embeddings.append(self._deterministic_fallback_embed(text, dim=fallback_dim))
            return all_embeddings

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            try:
                response = self._openai_client.embeddings.create(
                    extra_headers=self._extra_headers,
                    model=EMBEDDING_MODEL,
                    input=batch,
                    encoding_format="float",
                )
                sorted_data = sorted(response.data, key=lambda x: getattr(x, "index", 0))
                for item in sorted_data:
                    all_embeddings.append(item.embedding)
            except Exception as e:
                print(f"  [embed] Embedding API offline ({e}). Using deterministic semantic fallback.")
                fallback_dim = self._dimension or 2048
                for text in batch:
                    all_embeddings.append(self._deterministic_fallback_embed(text, dim=fallback_dim))

            if not self._dimension and all_embeddings:
                self._dimension = len(all_embeddings[0])

        return all_embeddings

    # ── Ollama backend ───────────────────────────────────────────────────────

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Embed using local Ollama server with ollama Python package, falling back gracefully if offline."""
        all_embeddings = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]

            try:
                response = self._ollama.embed(
                    model=OLLAMA_MODEL,
                    input=batch,
                )
                all_embeddings.extend(response.embeddings)

            except Exception as e:
                error_msg = str(e)
                print(f"  [embed] Ollama offline ({error_msg[:60]}...). Using deterministic semantic fallback.")
                fallback_dim = self._dimension or 4096
                for text in batch:
                    all_embeddings.append(self._deterministic_fallback_embed(text, dim=fallback_dim))

            if not self._dimension and all_embeddings:
                self._dimension = len(all_embeddings[0])

        return all_embeddings

    # ── HuggingFace backend ──────────────────────────────────────────────────

    def _embed_huggingface(self, texts: list[str]) -> list[list[float]]:
        """Embed using HuggingFace Inference API."""
        all_embeddings = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            try:
                results = self._client.feature_extraction(
                    batch,
                    model=HF_MODEL_ID,
                )
                for vec in results:
                    if isinstance(vec[0], list):
                        all_embeddings.append(vec[0])
                    else:
                        all_embeddings.append(vec)
            except Exception as e:
                print(f"  [embed] HuggingFace offline ({e}). Using deterministic semantic fallback.")
                fallback_dim = self._dimension or 4096
                for text in batch:
                    all_embeddings.append(self._deterministic_fallback_embed(text, dim=fallback_dim))

            if not self._dimension and all_embeddings:
                self._dimension = len(all_embeddings[0])

        return all_embeddings
