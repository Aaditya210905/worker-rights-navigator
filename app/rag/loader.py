"""
loader.py -- Loads the research package into RAGDocument objects.

Reads knowledge_items.json, source_registry.json, gaps.json, conflicts.json
from the workersaathi research package and normalizes them into
RAGDocument objects ready for chunking and embedding.
"""

import json
from pathlib import Path
from typing import Optional

from app.rag.models import (
    RAGDocument, EvidenceLevel, SOURCE_TYPE_TO_EVIDENCE,
)


class ResearchLoader:
    """
    Loads the WorkerSaathi research package.

    Input:  knowledge/workersaathi/json/
    Output: list[RAGDocument], gaps, conflicts
    """

    def __init__(self, data_dir: str):
        self._dir = Path(data_dir)
        self._knowledge_items = []
        self._source_registry = {}
        self._gaps = []
        self._conflicts = []

    def load(self):
        """Load all JSON files from the research package."""
        # Knowledge items
        ki_path = self._dir / "knowledge_items.json"
        if ki_path.exists():
            with open(ki_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._knowledge_items = data.get("items", [])

        # Source registry
        sr_path = self._dir / "source_registry.json"
        if sr_path.exists():
            with open(sr_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for src in data.get("sources", []):
                self._source_registry[src["source_id"]] = src

        # Gaps
        gaps_path = self._dir / "gaps.json"
        if gaps_path.exists():
            with open(gaps_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._gaps = data.get("gaps", [])

        # Conflicts
        conflicts_path = self._dir / "conflicts.json"
        if conflicts_path.exists():
            with open(conflicts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._conflicts = data.get("conflicts", [])

        print(f"  Loaded: {len(self._knowledge_items)} knowledge items, "
              f"{len(self._source_registry)} sources, "
              f"{len(self._gaps)} gaps, {len(self._conflicts)} conflicts")

    def to_rag_documents(self) -> list[RAGDocument]:
        """Convert knowledge items to RAGDocument objects."""
        docs = []

        for item in self._knowledge_items:
            content = item.get("content", "").strip()
            if not content:
                continue

            # Determine evidence level from source_type
            source_type = item.get("source_type", "other")
            evidence_level = SOURCE_TYPE_TO_EVIDENCE.get(
                source_type, EvidenceLevel.SECONDARY
            ).value

            doc = RAGDocument(
                doc_id=item.get("source_id", ""),
                text=content,
                source_id=item.get("source_id", ""),
                title=item.get("title", ""),
                authority=item.get("authority", ""),
                jurisdiction=item.get("jurisdiction", "central"),
                source_type=source_type,
                evidence_level=evidence_level,
                worker_types=item.get("worker_types", ["all_workers"]),
                issue_categories=item.get("issue_categories", ["all"]),
                topic=item.get("topic", ""),
                chapter=item.get("chapter", ""),
                section=item.get("section", ""),
                subsection=item.get("subsection", ""),
                legal_status=item.get("legal_status", ""),
                effective_from=item.get("effective_from", ""),
                official_url=item.get("official_url", ""),
                document_url=item.get("document_url", ""),
                last_verified=item.get("last_verified", ""),
                notes=item.get("notes", ""),
            )
            docs.append(doc)

        print(f"  Created {len(docs)} RAG documents")
        return docs

    @property
    def gaps(self) -> list[dict]:
        return self._gaps

    @property
    def conflicts(self) -> list[dict]:
        return self._conflicts

    @property
    def source_registry(self) -> dict:
        return self._source_registry
