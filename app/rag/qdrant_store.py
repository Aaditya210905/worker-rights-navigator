"""
qdrant_store.py -- Qdrant vector database for legal knowledge.

Uses qdrant-client in local/in-memory mode — no external server needed.
Stores RAG document chunks with vectors + metadata payload.
Supports filtered search by jurisdiction, worker_types, issue_categories.
"""

from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.rag.models import RAGDocument


COLLECTION_NAME = "workersaathi_central"


class QdrantStore:
    """
    Qdrant vector store for WorkerSaathi legal knowledge.

    Runs locally — no external server needed.
    Stores vectors + metadata payloads for filtered retrieval.
    """

    def __init__(self, path: Optional[str] = None):
        """
        Args:
            path: Directory for persistent storage. None = in-memory.
        """
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=path)
        else:
            self._client = QdrantClient(":memory:")
        self._collection = COLLECTION_NAME

    def create_collection(self, dimension: int):
        """Create the vector collection with payload indexes."""
        # Delete if exists
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection in collections:
            self._client.delete_collection(self._collection)

        # Create collection
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=dimension,
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes for fast filtering
        for field in ["jurisdiction", "evidence_level", "topic", "legal_status"]:
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        print(f"  Created Qdrant collection '{self._collection}' "
              f"(dim={dimension}, distance=cosine)")

    def upsert_documents(
        self,
        docs: list[RAGDocument],
        vectors: list[list[float]],
    ):
        """Insert documents with their vectors into Qdrant."""
        points = []
        for i, (doc, vec) in enumerate(zip(docs, vectors)):
            point = PointStruct(
                id=i,
                vector=vec,
                payload=doc.to_qdrant_payload(),
            )
            points.append(point)

        # Upsert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self._client.upsert(
                collection_name=self._collection,
                points=batch,
            )

        print(f"  Upserted {len(points)} documents into Qdrant")

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        jurisdiction: str = None,
        worker_type: str = None,
        issue_category: str = None,
    ) -> list[dict]:
        """
        Search for similar documents with metadata filtering.

        Returns list of {score, payload} dicts.
        """
        # Build filter conditions
        conditions = []

        if jurisdiction:
            conditions.append(
                FieldCondition(
                    key="jurisdiction",
                    match=MatchValue(value=jurisdiction),
                )
            )

        if worker_type:
            conditions.append(
                FieldCondition(
                    key="worker_types",
                    match=MatchAny(any=[worker_type, "all_workers"]),
                )
            )

        if issue_category:
            conditions.append(
                FieldCondition(
                    key="issue_categories",
                    match=MatchAny(any=[issue_category, "all"]),
                )
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        ).points

        return [
            {
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    def count(self) -> int:
        """Return the number of documents in the collection."""
        try:
            info = self._client.get_collection(self._collection)
            return info.points_count
        except Exception:
            return 0
