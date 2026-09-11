"""
retriever.py -- Hybrid retrieval + reranking + LegalEvidence.

Combines:
  1. Semantic search (Qdrant + Qwen3-Embedding-8B)
  2. BM25 keyword search (rank_bm25)
  3. Reciprocal Rank Fusion (RRF) for score merging
  4. Reranking by evidence_level priority
  5. Gap/conflict awareness
  6. LegalEvidence output for the agent

This is the core intelligence layer of Phase 4.
"""

import json
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from app.rag.models import (
    RAGDocument, LegalEvidence, EvidenceFinding,
    EvidenceLevel, RetrievalCoverage,
)
from app.rag.embeddings import EmbeddingClient
from app.rag.qdrant_store import QdrantStore


# Evidence level priority (lower = more authoritative)
EVIDENCE_PRIORITY = {
    EvidenceLevel.PRIMARY_LEGAL.value: 0,
    EvidenceLevel.OFFICIAL_GOVERNMENT.value: 1,
    EvidenceLevel.OFFICIAL_EXPLANATORY.value: 2,
    EvidenceLevel.SECONDARY.value: 3,
}

# RRF constant
RRF_K = 60


class HybridRetriever:
    """
    Hybrid retrieval with semantic + BM25 + reranking.

    Usage:
        retriever = HybridRetriever(qdrant, embedder, docs, gaps, conflicts)
        evidence = retriever.retrieve(
            query="salary not paid",
            worker_type="gig_worker",
            issue="unpaid_wages",
        )
    """

    def __init__(
        self,
        qdrant: QdrantStore,
        embedder: EmbeddingClient,
        documents: list[RAGDocument],
        gaps: list[dict] = None,
        conflicts: list[dict] = None,
    ):
        self._qdrant = qdrant
        self._embedder = embedder
        self._documents = documents
        self._gaps = gaps or []
        self._conflicts = conflicts or []

        # Build BM25 index
        tokenized_docs = [_tokenize(doc.text) for doc in documents]
        self._bm25 = BM25Okapi(tokenized_docs)

    def retrieve(
        self,
        query: str = None,
        worker_type: str = None,
        state: str = None,
        issue: str = None,
        raw_description: str = None,
        top_k: int = 5,
    ) -> LegalEvidence:
        """
        Retrieve relevant legal evidence for a worker's case.

        Args:
            query: search query (built from case if not provided)
            worker_type: e.g., "gig_worker"
            state: e.g., "Karnataka" (used for gap detection)
            issue: e.g., "unpaid_wages"
            raw_description: worker's own words
            top_k: number of results to return

        Returns:
            LegalEvidence with findings, gaps, and conflicts.
        """
        # Build query from case info if not provided
        if not query:
            parts = []
            if issue:
                parts.append(issue.replace("_", " "))
            if worker_type:
                parts.append(worker_type.replace("_", " "))
            if raw_description:
                parts.append(raw_description)
            query = " ".join(parts) if parts else "worker rights"

        # ── 1. Semantic search via Qdrant ────────────────────────
        query_vector = self._embedder.embed_query(query)
        semantic_results = self._qdrant.search(
            query_vector=query_vector,
            limit=top_k * 2,
            jurisdiction="central",
            worker_type=worker_type,
            issue_category=issue,
        )

        # ── 2. BM25 keyword search ──────────────────────────────
        query_tokens = _tokenize(query)
        bm25_scores = self._bm25.get_scores(query_tokens)

        # Filter BM25 results by worker_type and issue
        bm25_ranked = []
        for idx, score in enumerate(bm25_scores):
            if score <= 0:
                continue
            doc = self._documents[idx]
            # Apply same filters as Qdrant
            if worker_type and "all_workers" not in doc.worker_types:
                if worker_type not in doc.worker_types:
                    continue
            if issue and "all" not in doc.issue_categories:
                if issue not in doc.issue_categories:
                    continue
            bm25_ranked.append((idx, score))

        bm25_ranked.sort(key=lambda x: x[1], reverse=True)
        bm25_ranked = bm25_ranked[:top_k * 2]

        # ── 3. Reciprocal Rank Fusion ────────────────────────────
        fused_scores = {}

        # Score semantic results
        for rank, result in enumerate(semantic_results):
            doc_id = result["payload"].get("doc_id", "")
            rrf_score = 1.0 / (RRF_K + rank + 1)
            if doc_id not in fused_scores:
                fused_scores[doc_id] = {
                    "score": 0.0,
                    "payload": result["payload"],
                    "semantic_score": result["score"],
                }
            fused_scores[doc_id]["score"] += rrf_score

        # Score BM25 results
        for rank, (idx, bm25_score) in enumerate(bm25_ranked):
            doc = self._documents[idx]
            doc_id = doc.doc_id
            rrf_score = 1.0 / (RRF_K + rank + 1)
            if doc_id not in fused_scores:
                fused_scores[doc_id] = {
                    "score": 0.0,
                    "payload": doc.to_qdrant_payload(),
                    "semantic_score": 0.0,
                }
            fused_scores[doc_id]["score"] += rrf_score

        # ── 4. Rerank by evidence_level ──────────────────────────
        ranked = sorted(
            fused_scores.values(),
            key=lambda x: (
                -x["score"],  # Higher score first
                EVIDENCE_PRIORITY.get(
                    x["payload"].get("evidence_level", "secondary"), 9
                ),
            ),
        )

        # ── 5. Build findings ────────────────────────────────────
        findings = []
        for item in ranked[:top_k]:
            p = item["payload"]
            finding = EvidenceFinding(
                claim=p.get("title", ""),
                source_title=p.get("title", ""),
                source_id=p.get("source_id", ""),
                section=p.get("section", ""),
                evidence_text=p.get("text", ""),
                official_url=p.get("official_url", ""),
                evidence_level=p.get("evidence_level", "secondary"),
                legal_status=p.get("legal_status", ""),
                last_verified=p.get("last_verified", ""),
                retrieval_score=item["score"],
            )
            findings.append(finding)

        # ── 6. Check gaps ────────────────────────────────────────
        relevant_gaps = self._find_relevant_gaps(worker_type, issue)

        # ── 7. Check conflicts ───────────────────────────────────
        relevant_conflicts = self._find_relevant_conflicts(
            worker_type, issue, findings
        )

        # ── 8. Determine coverage ────────────────────────────────
        # Check if top findings are themselves gap-describing docs
        gap_keywords = ["not_found", "no verified", "gap", "unconfirmed",
                        "insufficient_verified"]
        findings_are_gaps = findings and all(
            any(kw in (f.evidence_text.lower() + f.legal_status.lower())
                for kw in gap_keywords)
            for f in findings[:2]  # check top 2
        )

        if relevant_conflicts:
            coverage = RetrievalCoverage.CONFLICT
        elif relevant_gaps and (not findings or findings_are_gaps):
            coverage = RetrievalCoverage.GAP
        elif findings and relevant_gaps:
            coverage = RetrievalCoverage.PARTIAL
        elif findings:
            coverage = RetrievalCoverage.FULL
        else:
            coverage = RetrievalCoverage.NONE

        # ── 9. Build limitations ─────────────────────────────────
        limitations = []
        if state and state.lower() != "central":
            limitations.append(
                f"This information is from Central Government sources only. "
                f"State-specific ({state}) laws may also apply."
            )
        limitations.append(
            "WorkerSaathi is not a lawyer. This information is for "
            "guidance only. Consult a legal professional for specific advice."
        )

        return LegalEvidence(
            issue=issue or "",
            jurisdiction="central",
            worker_type=worker_type or "",
            coverage=coverage,
            evidence=findings,
            gaps=[g["gap"] for g in relevant_gaps],
            conflicts=[c["description"] for c in relevant_conflicts],
            limitations=limitations,
        )

    def _find_relevant_gaps(
        self, worker_type: str = None, issue: str = None
    ) -> list[dict]:
        """Find gaps relevant to this case."""
        relevant = []
        # Build search words from worker_type and issue
        search_words = set()
        if worker_type:
            for word in worker_type.split("_"):
                if len(word) > 2:
                    search_words.add(word.lower())
        if issue:
            for word in issue.split("_"):
                if len(word) > 2:
                    search_words.add(word.lower())

        for gap in self._gaps:
            gap_text = gap.get("gap", "").lower()
            gap_id = gap.get("id", "").lower()
            combined = gap_text + " " + gap_id
            # Match if ANY two search words appear in the gap
            matches = sum(1 for w in search_words if w in combined)
            if matches >= 2 or (matches >= 1 and len(search_words) == 1):
                relevant.append(gap)

        return relevant

    def _find_relevant_conflicts(
        self,
        worker_type: str = None,
        issue: str = None,
        findings: list[EvidenceFinding] = None,
    ) -> list[dict]:
        """Find conflicts relevant to this case."""
        relevant = []
        search_words = set()
        if worker_type:
            for word in worker_type.split("_"):
                if len(word) > 2:
                    search_words.add(word.lower())
        if issue:
            for word in issue.split("_"):
                if len(word) > 2:
                    search_words.add(word.lower())

        for conflict in self._conflicts:
            desc = conflict.get("description", "").lower()
            cid = conflict.get("id", "").lower()
            combined = desc + " " + cid
            matches = sum(1 for w in search_words if w in combined)
            if matches >= 2 or (matches >= 1 and len(search_words) == 1):
                relevant.append(conflict)

        return relevant


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]
