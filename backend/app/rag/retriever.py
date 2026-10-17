"""
retriever.py -- Phase 5 Hybrid Retrieval Engine.

Combines all components into a single retrieval pipeline:

  CaseState / params
       |
  QueryBuilder   -> structured query with issue expansion
       |
  Qdrant         -> semantic search with metadata filters
  BM25           -> keyword search
       |
  RRF fusion     -> merge semantic + keyword results
       |
  Reranker       -> authority/status/specificity weighting
       |
  Validator      -> legal status + applicability checks
       |
  EvidenceAssembler -> LegalEvidence output
       |
  Agent / LLM
"""

import re
from typing import Optional

from rank_bm25 import BM25Okapi

from app.rag.models import (
    RAGDocument, LegalEvidence, EvidenceFinding,
    EvidenceLevel, RetrievalCoverage,
)
from app.rag.embeddings import EmbeddingClient
from app.rag.qdrant_store import QdrantStore
from app.rag.query_builder import QueryBuilder, RetrievalQuery
from app.rag.reranker import rerank
from app.rag.validator import EvidenceValidator
from app.rag.evidence import EvidenceAssembler


# RRF constant
RRF_K = 60


class HybridRetriever:
    """
    Phase 5 hybrid retrieval engine.

    Usage:
        retriever = HybridRetriever(qdrant, embedder, docs, gaps, conflicts)

        # From CaseState
        evidence = retriever.retrieve_for_case(case_state)

        # From explicit params
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

        # Index documents into Qdrant (required for in-memory mode)
        self._ensure_indexed()

    def _ensure_indexed(self):
        """Create Qdrant collection and index documents if not already done."""
        try:
            collections = [
                c.name for c in self._qdrant._client.get_collections().collections
            ]
            if self._qdrant._collection in collections:
                return  # Already indexed

            # Get embedding dimension
            dimension = self._embedder.dimension

            # Create collection
            self._qdrant.create_collection(dimension)

            # Embed all documents in batch
            texts = [doc.text for doc in self._documents]
            vectors = self._embedder.embed_texts(texts)

            # Index into Qdrant
            self._qdrant.upsert_documents(self._documents, vectors)
            print(f"  [retriever] Indexed {len(self._documents)} documents into Qdrant")

        except Exception as e:
            print(f"  [retriever] Indexing error: {e}")
            import traceback
            traceback.print_exc()

    def retrieve_for_case(self, case) -> LegalEvidence:
        """
        Retrieve evidence using a CaseState object.

        This is the primary entry point for the voice agent.
        """
        rq = QueryBuilder.from_case(case)
        return self._execute(rq)

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
        Retrieve evidence from explicit parameters.

        Used for testing and direct API calls.
        """
        rq = QueryBuilder.from_params(
            worker_type=worker_type,
            issue=issue,
            query=query,
            raw_description=raw_description,
        )
        return self._execute(rq, state=state, top_k=top_k)

    def _execute(
        self,
        rq: RetrievalQuery,
        state: str = None,
        top_k: int = 5,
    ) -> LegalEvidence:
        """Execute the full retrieval pipeline."""

        # ── 1. Semantic search via Qdrant ────────────────────────
        query_vector = self._embedder.embed_query(rq.semantic_query)

        # Use the primary worker type and issue for Qdrant filter
        primary_worker = rq.worker_types[0] if rq.worker_types else None
        primary_issue = rq.issue_categories[0] if rq.issue_categories else None

        semantic_results = self._qdrant.search(
            query_vector=query_vector,
            limit=top_k * 3,
            jurisdiction=rq.jurisdiction,
            worker_type=primary_worker,
            issue_category=primary_issue,
        )

        # ── 2. BM25 keyword search ──────────────────────────────
        query_tokens = _tokenize(rq.semantic_query)
        bm25_scores = self._bm25.get_scores(query_tokens)

        bm25_ranked = []
        for idx, score in enumerate(bm25_scores):
            if score <= 0:
                continue
            doc = self._documents[idx]
            # Filter by worker type (any match in expanded list)
            if rq.worker_types and "all_workers" not in rq.worker_types:
                doc_workers = set(doc.worker_types)
                query_workers = set(rq.worker_types) | {"all_workers"}
                if not doc_workers.intersection(query_workers):
                    continue
            # Filter by issue (any match in expanded list)
            if rq.issue_categories and "all" not in rq.issue_categories:
                doc_issues = set(doc.issue_categories)
                query_issues = set(rq.issue_categories) | {"all"}
                if not doc_issues.intersection(query_issues):
                    continue
            bm25_ranked.append((idx, score))

        bm25_ranked.sort(key=lambda x: x[1], reverse=True)
        bm25_ranked = bm25_ranked[:top_k * 3]

        # ── 3. Reciprocal Rank Fusion (RRF) ──────────────────────
        fused = {}

        for rank, result in enumerate(semantic_results):
            doc_id = result["payload"].get("doc_id", f"sem_{rank}")
            rrf_score = 1.0 / (RRF_K + rank + 1)
            if doc_id not in fused:
                fused[doc_id] = {"score": 0.0, "payload": result["payload"]}
            fused[doc_id]["score"] += rrf_score

        for rank, (idx, bm25_score) in enumerate(bm25_ranked):
            doc = self._documents[idx]
            doc_id = doc.doc_id
            rrf_score = 1.0 / (RRF_K + rank + 1)
            if doc_id not in fused:
                fused[doc_id] = {"score": 0.0, "payload": doc.to_qdrant_payload()}
            fused[doc_id]["score"] += rrf_score

        candidates = list(fused.values())

        # ── 4. Rerank ────────────────────────────────────────────
        reranked = rerank(
            candidates,
            worker_type=primary_worker,
            issue=primary_issue,
            top_k=top_k,
        )

        # ── 5. Build findings ────────────────────────────────────
        findings = []
        for item in reranked:
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
                retrieval_score=item.get("composite_score", item["score"]),
            )
            findings.append(finding)

        # ── 6. Validate ─────────────────────────────────────────
        # Pass original worker type so validator detects "unknown"
        original_wt = getattr(rq, 'original_worker_type', primary_worker)
        valid_findings, val_limitations = EvidenceValidator.validate(
            findings,
            worker_type=original_wt,
            issue=primary_issue,
            jurisdiction=rq.jurisdiction,
        )

        # ── 7. Find relevant gaps ────────────────────────────────
        relevant_gaps = self._find_relevant_gaps(primary_worker, primary_issue)

        # ── 8. Find relevant conflicts ───────────────────────────
        relevant_conflicts = self._find_relevant_conflicts(
            primary_worker, primary_issue
        )

        # ── 9. Assemble LegalEvidence ────────────────────────────
        return EvidenceAssembler.assemble(
            findings=valid_findings,
            gaps=relevant_gaps,
            conflicts=relevant_conflicts,
            limitations=val_limitations,
            worker_type=primary_worker or "",
            issue=primary_issue or "",
            state=state,
            jurisdiction=rq.jurisdiction,
        )

    def _find_relevant_gaps(
        self, worker_type: str = None, issue: str = None
    ) -> list[dict]:
        """Find gaps relevant to this case using word-level matching."""
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

        for gap in self._gaps:
            gap_text = gap.get("gap", "").lower()
            gap_id = gap.get("id", "").lower()
            combined = gap_text + " " + gap_id
            matches = sum(1 for w in search_words if w in combined)
            if matches >= 2 or (matches >= 1 and len(search_words) == 1):
                relevant.append(gap)

        return relevant

    def _find_relevant_conflicts(
        self, worker_type: str = None, issue: str = None
    ) -> list[dict]:
        """Find conflicts relevant to this case using word-level matching."""
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
    return [t for t in tokens if len(t) > 1]
