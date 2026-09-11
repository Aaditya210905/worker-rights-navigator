"""
embeddings.py -- Embedding generation using Qwen3-Embedding-8B
via HuggingFace Inference API (Scaleway provider).

Generates vectors for RAG documents and queries.
"""

import os
import time
from typing import Optional

from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

MODEL_ID = "Qwen/Qwen3-Embedding-8B"
PROVIDER = "scaleway"
BATCH_SIZE = 16  # API batch limit


class EmbeddingClient:
    """
    Generates embeddings using Qwen3-Embedding-8B
    via HuggingFace Inference API.
    """

    def __init__(self, api_key: Optional[str] = None):
        token = api_key or os.environ.get("HF_TOKEN", "")
        if not token or token == "hf_YOUR_TOKEN_HERE":
            raise ValueError(
                "HF_TOKEN is required. Set it in your .env file. "
                "Get one at https://huggingface.co/settings/tokens"
            )
        self._client = InferenceClient(
            provider=PROVIDER,
            api_key=token,
        )
        self._dimension = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts. Handles batching automatically.
        Returns list of embedding vectors.
        """
        all_embeddings = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            try:
                results = self._client.feature_extraction(
                    batch,
                    model=MODEL_ID,
                )
                # Results come as list of lists
                for vec in results:
                    if isinstance(vec[0], list):
                        # Nested — take first
                        all_embeddings.append(vec[0])
                    else:
                        all_embeddings.append(vec)
            except Exception as e:
                print(f"  [embed] Error on batch {i//BATCH_SIZE}: {e}")
                # Retry once after a short delay
                time.sleep(2)
                try:
                    results = self._client.feature_extraction(
                        batch,
                        model=MODEL_ID,
                    )
                    for vec in results:
                        if isinstance(vec[0], list):
                            all_embeddings.append(vec[0])
                        else:
                            all_embeddings.append(vec)
                except Exception as e2:
                    print(f"  [embed] Retry failed: {e2}")
                    # Return zero vectors as fallback
                    dim = self._dimension or 4096
                    for _ in batch:
                        all_embeddings.append([0.0] * dim)

            if not self._dimension and all_embeddings:
                self._dimension = len(all_embeddings[0])

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text."""
        results = self.embed_texts([query])
        return results[0] if results else []

    @property
    def dimension(self) -> int:
        """Return embedding dimension (discovered after first call)."""
        if self._dimension is None:
            # Do a test embed to discover dimension
            test = self.embed_texts(["test"])
            if test:
                self._dimension = len(test[0])
        return self._dimension or 4096
