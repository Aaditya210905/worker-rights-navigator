"""
embeddings.py -- Embedding generation via Ollama (local) or
HuggingFace Inference API (cloud).

Supports two backends:
  1. Ollama (default) — runs locally, no API key needed
  2. HuggingFace — cloud API, needs HF_TOKEN

Set EMBEDDING_BACKEND=ollama or EMBEDDING_BACKEND=huggingface in .env
"""

import os
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "ollama")

# Ollama settings
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-embedding")

# HuggingFace settings (fallback)
HF_MODEL_ID = "Qwen/Qwen3-Embedding-8B"
HF_PROVIDER = "scaleway"
BATCH_SIZE = 16


class EmbeddingClient:
    """
    Generates embeddings using Ollama (local) or HuggingFace (cloud).

    Default: Ollama with qwen3-embedding model.
    """

    def __init__(self, api_key: Optional[str] = None, backend: Optional[str] = None):
        self._backend = backend or EMBEDDING_BACKEND
        self._dimension = None

        if self._backend == "huggingface":
            self._init_huggingface(api_key)
        else:
            self._backend = "ollama"
            import ollama
            self._ollama = ollama
            print(f"  [embed] Using Ollama (model={OLLAMA_MODEL})")

    def _init_huggingface(self, api_key):
        """Initialize HuggingFace backend."""
        from huggingface_hub import InferenceClient
        token = api_key or os.environ.get("HF_TOKEN", "")
        if not token or token == "hf_YOUR_TOKEN_HERE":
            raise ValueError(
                "HF_TOKEN is required for HuggingFace backend. "
                "Set it in .env or use EMBEDDING_BACKEND=ollama"
            )
        self._client = InferenceClient(
            provider=HF_PROVIDER,
            api_key=token,
        )
        print(f"  [embed] Using HuggingFace ({HF_MODEL_ID})")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Handles batching automatically."""
        if self._backend == "ollama":
            return self._embed_ollama(texts)
        else:
            return self._embed_huggingface(texts)

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text."""
        results = self.embed_texts([query])
        return results[0] if results else []

    @property
    def dimension(self) -> int:
        """Return embedding dimension (discovered after first call)."""
        if self._dimension is None:
            test = self.embed_texts(["test"])
            if test:
                self._dimension = len(test[0])
        return self._dimension or 384

    # ── Ollama backend ───────────────────────────────────────────────────────

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Embed using local Ollama server with ollama Python package."""
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
                if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                    raise RuntimeError(
                        "Cannot connect to Ollama. Start it with: ollama serve\n"
                        "Then pull the model: ollama pull qwen3-embedding"
                    ) from e

                print(f"  [embed] Ollama error on batch {i//BATCH_SIZE}: {e}")
                # Retry once
                time.sleep(2)
                try:
                    response = self._ollama.embed(
                        model=OLLAMA_MODEL,
                        input=batch,
                    )
                    all_embeddings.extend(response.embeddings)
                except Exception as e2:
                    print(f"  [embed] Retry failed: {e2}")
                    raise RuntimeError(
                        f"Ollama embedding failed after retry: {e2}"
                    ) from e2

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
                print(f"  [embed] Error on batch {i//BATCH_SIZE}: {e}")
                time.sleep(2)
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
                except Exception as e2:
                    print(f"  [embed] Retry failed: {e2}")
                    raise RuntimeError(
                        f"Embedding API failed after retry: {e2}"
                    ) from e2

            if not self._dimension and all_embeddings:
                self._dimension = len(all_embeddings[0])

        return all_embeddings
