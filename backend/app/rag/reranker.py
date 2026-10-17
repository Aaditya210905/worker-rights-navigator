"""
reranker.py -- Evidence reranking with authority and status weighting.

Takes candidate retrieval results and reranks them based on:
  1. Retrieval score (semantic + BM25 fused)
  2. Evidence level authority (primary_legal > explanatory)
  3. Legal status validity (in_force > unknown)
  4. Worker type specificity (exact match > broad match)
  5. Issue match specificity
"""

from app.rag.models import EvidenceLevel


# Authority weights — higher = more authoritative
AUTHORITY_WEIGHTS = {
    EvidenceLevel.PRIMARY_LEGAL.value: 1.0,
    EvidenceLevel.OFFICIAL_GOVERNMENT.value: 0.7,
    EvidenceLevel.OFFICIAL_EXPLANATORY.value: 0.4,
    EvidenceLevel.SECONDARY.value: 0.1,
}

# Legal status weights — higher = more trustworthy
STATUS_WEIGHTS = {
    "in_force": 1.0,
    "in_force_with_exceptions": 0.9,
    "active": 0.8,
    "verify": 0.5,
    "insufficient_verified_central_information": 0.2,
    "": 0.3,  # unknown status
}


def rerank(
    candidates: list[dict],
    worker_type: str = None,
    issue: str = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Rerank retrieval candidates by composite score.

    Args:
        candidates: list of {score, payload} dicts from retriever
        worker_type: target worker type for specificity scoring
        issue: target issue for specificity scoring
        top_k: number of results to return

    Returns:
        Reranked list of candidates with composite_score added.
    """
    scored = []

    for candidate in candidates:
        payload = candidate.get("payload", {})
        retrieval_score = candidate.get("score", 0.0)

        # Authority score
        evidence_level = payload.get("evidence_level", "secondary")
        authority_score = AUTHORITY_WEIGHTS.get(evidence_level, 0.1)

        # Legal status score
        legal_status = payload.get("legal_status", "")
        status_score = STATUS_WEIGHTS.get(legal_status, 0.3)

        # Worker type specificity — exact match gets boost
        worker_score = 0.5  # default
        doc_workers = payload.get("worker_types", [])
        if worker_type:
            if worker_type in doc_workers:
                worker_score = 1.0  # exact match
            elif "all_workers" in doc_workers:
                worker_score = 0.6  # broadly applicable
            elif "unorganised_worker" in doc_workers:
                worker_score = 0.5  # partial match
            else:
                worker_score = 0.2  # poor match

        # Issue specificity
        issue_score = 0.5  # default
        doc_issues = payload.get("issue_categories", [])
        if issue:
            if issue in doc_issues:
                issue_score = 1.0
            elif "all" in doc_issues:
                issue_score = 0.5
            else:
                issue_score = 0.2

        # Composite score
        composite = (
            retrieval_score * 3.0      # retrieval relevance is primary
            + authority_score * 1.5     # authority matters significantly
            + status_score * 1.0        # legal status is important
            + worker_score * 0.8        # worker match helps
            + issue_score * 0.8         # issue match helps
        )

        scored.append({
            "score": retrieval_score,
            "composite_score": composite,
            "authority_score": authority_score,
            "status_score": status_score,
            "payload": payload,
        })

    # Sort by composite score (descending)
    scored.sort(key=lambda x: x["composite_score"], reverse=True)

    return scored[:top_k]
