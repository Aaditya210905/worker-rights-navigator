"""
query_builder.py -- Converts CaseState into a structured retrieval query.

This is the bridge between the conversation layer (Phase 2) and
the retrieval layer (Phase 5). It understands what the worker's
problem is and constructs the best possible search query.

Key rules:
  - Unknown worker_type → broaden search, don't exclude
  - Multiple related issues → expand issue filter
  - Raw description → enrich the semantic query
"""

from typing import Optional

from app.case.models import (
    CaseState, WorkerType, IssueCategory, IndianState,
)


# Issue category → related search terms for semantic enrichment
ISSUE_SEARCH_TERMS = {
    "unpaid_wages": [
        "payment of wages", "salary not paid", "wage claim",
        "minimum wages", "deduction", "timely payment",
    ],
    "workplace_injury": [
        "workplace accident", "occupational safety", "injury",
        "compensation", "construction safety", "health",
    ],
    "platform_deactivation": [
        "platform account deactivated", "gig worker",
        "aggregator", "app deactivation", "reinstatement",
    ],
    "social_security": [
        "social security", "pension", "insurance",
        "welfare scheme", "e-Shram", "registration",
    ],
    "welfare": [
        "welfare scheme", "benefits", "social security",
        "worker registration", "e-Shram",
    ],
    "registration": [
        "worker registration", "e-Shram", "unorganised worker",
        "identity card", "social security registration",
    ],
    "legal_aid": [
        "free legal aid", "NALSA", "legal services",
        "legal assistance", "labour court",
    ],
    "labour_complaint": [
        "labour complaint", "grievance", "labour commissioner",
        "dispute resolution", "SAMADHAN",
    ],
    "employment_dispute": [
        "employment dispute", "termination", "industrial dispute",
        "unfair dismissal", "retrenchment",
    ],
    "workplace_safety": [
        "workplace safety", "occupational health",
        "safety duties", "construction safety", "hazardous work",
    ],
    "pension": [
        "pension scheme", "Atal Pension Yojana", "PM-SYM",
        "retirement", "old age pension",
    ],
    "insurance": [
        "insurance", "PMJJBY", "PMSBY", "PM-JAY",
        "health insurance", "life insurance",
    ],
    "healthcare": [
        "healthcare", "PM-JAY", "Ayushman Bharat",
        "hospital", "medical treatment",
    ],
}

# Issue → related issues to expand search
ISSUE_EXPANSIONS = {
    "unpaid_wages": ["employment_dispute"],
    "workplace_injury": ["workplace_safety", "social_security"],
    "platform_deactivation": ["social_security"],
    "welfare": ["social_security", "registration"],
    "registration": ["welfare", "social_security"],
    "pension": ["social_security"],
    "insurance": ["social_security"],
    "healthcare": ["social_security", "insurance"],
}

# Worker type → compatible broader types for search
WORKER_TYPE_EXPANSIONS = {
    "gig_worker": ["all_workers", "unorganised_worker"],
    "construction_worker": ["all_workers", "unorganised_worker"],
    "domestic_worker": ["all_workers", "unorganised_worker"],
    "factory_worker": ["all_workers"],
    "other_worker": ["all_workers", "unorganised_worker"],
    "unknown": ["all_workers"],
}


class RetrievalQuery:
    """Structured retrieval query built from CaseState."""

    def __init__(
        self,
        semantic_query: str,
        worker_types: list[str],
        issue_categories: list[str],
        jurisdiction: str = "central",
        preferred_evidence: list[str] = None,
        raw_description: str = "",
        original_worker_type: str = "",
    ):
        self.semantic_query = semantic_query
        self.worker_types = worker_types
        self.issue_categories = issue_categories
        self.jurisdiction = jurisdiction
        self.preferred_evidence = preferred_evidence or [
            "primary_legal", "official_government",
        ]
        self.raw_description = raw_description
        self.original_worker_type = original_worker_type

    def __repr__(self):
        return (
            f"RetrievalQuery(\n"
            f"  query='{self.semantic_query[:60]}...'\n"
            f"  workers={self.worker_types}\n"
            f"  issues={self.issue_categories}\n"
            f"  jurisdiction={self.jurisdiction}\n"
            f")"
        )


class QueryBuilder:
    """
    Converts CaseState into a structured RetrievalQuery.

    Handles:
      - Unknown worker_type → broaden search
      - Issue expansion → include related issues
      - Semantic enrichment → add legal terms to query
      - Jurisdiction determination
    """

    @staticmethod
    def from_case(case: CaseState) -> RetrievalQuery:
        """Build a RetrievalQuery from the current CaseState."""

        # ── Worker types ─────────────────────────────────────────
        worker_types = []
        wt = case.worker_type
        if wt and wt != WorkerType.UNKNOWN:
            wt_str = wt.value
            worker_types.append(wt_str)
            # Add broader types
            for expanded in WORKER_TYPE_EXPANSIONS.get(wt_str, []):
                if expanded not in worker_types:
                    worker_types.append(expanded)
        else:
            # Unknown → search broadly
            worker_types = ["all_workers", "unorganised_worker", "gig_worker"]

        # ── Issue categories ─────────────────────────────────────
        issues = []
        issue = case.issue_category
        if issue and issue != IssueCategory.UNKNOWN:
            issue_str = issue.value
            issues.append(issue_str)
            # Add related issues
            for expanded in ISSUE_EXPANSIONS.get(issue_str, []):
                if expanded not in issues:
                    issues.append(expanded)
        else:
            issues = ["all"]

        # ── Semantic query ───────────────────────────────────────
        query_parts = []

        # Add issue-specific legal terms
        if issue and issue != IssueCategory.UNKNOWN:
            terms = ISSUE_SEARCH_TERMS.get(issue.value, [])
            query_parts.extend(terms[:3])  # Top 3 terms

        # Add worker type context
        if wt and wt != WorkerType.UNKNOWN:
            query_parts.append(wt.value.replace("_", " "))

        # Add raw description if available
        if case.raw_description:
            query_parts.append(case.raw_description)

        semantic_query = " ".join(query_parts) if query_parts else "worker rights and entitlements"

        # ── Jurisdiction ─────────────────────────────────────────
        jurisdiction = "central"  # Phase 5 is central-only

        return RetrievalQuery(
            semantic_query=semantic_query,
            worker_types=worker_types,
            issue_categories=issues,
            jurisdiction=jurisdiction,
            raw_description=case.raw_description or "",
            original_worker_type=wt.value if wt else "unknown",
        )

    @staticmethod
    def from_params(
        worker_type: str = None,
        issue: str = None,
        query: str = None,
        raw_description: str = None,
    ) -> RetrievalQuery:
        """Build a query from explicit parameters (for testing)."""

        # Worker types
        worker_types = []
        if worker_type and worker_type != "unknown":
            worker_types.append(worker_type)
            for expanded in WORKER_TYPE_EXPANSIONS.get(worker_type, []):
                if expanded not in worker_types:
                    worker_types.append(expanded)
        else:
            worker_types = ["all_workers"]

        # Issues
        issues = []
        if issue:
            issues.append(issue)
            for expanded in ISSUE_EXPANSIONS.get(issue, []):
                if expanded not in issues:
                    issues.append(expanded)
        else:
            issues = ["all"]

        # Semantic query
        query_parts = []
        if query:
            query_parts.append(query)
        if issue:
            terms = ISSUE_SEARCH_TERMS.get(issue, [])
            query_parts.extend(terms[:2])
        if worker_type:
            query_parts.append(worker_type.replace("_", " "))

        semantic_query = " ".join(query_parts) if query_parts else "worker rights"

        return RetrievalQuery(
            semantic_query=semantic_query,
            worker_types=worker_types,
            issue_categories=issues,
            jurisdiction="central",
            raw_description=raw_description or "",
            original_worker_type=worker_type or "unknown",
        )
