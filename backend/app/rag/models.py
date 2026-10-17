"""
models.py -- Data models for the legal knowledge system.

LegalSource: structured metadata for each official source.
LegalChunk: a section/passage from a legal document with full traceability.
RAGDocument: a chunk ready for embedding + Qdrant storage.
LegalEvidence: the bridge between RAG and the conversational agent.
"""

from enum import Enum
from typing import Optional
from datetime import date
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    LAW = "law"
    RULES = "rules"
    SCHEME = "scheme"
    PORTAL = "portal"
    BOARD = "board"
    NOTIFICATION = "notification"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    VERIFY = "verify"
    DISABLED = "disabled"
    SUPERSEDED = "superseded"
    PROPOSED = "proposed"


class Jurisdiction(str, Enum):
    CENTRAL = "central"
    STATE = "state"
    UT = "ut"


class EvidenceLevel(str, Enum):
    """Source hierarchy — higher = more authoritative for legal claims."""
    PRIMARY_LEGAL = "primary_legal"         # Acts, Rules, Gazette notifications
    OFFICIAL_GOVERNMENT = "official_government"  # Ministry, e-Shram, portals
    OFFICIAL_EXPLANATORY = "official_explanatory"  # FAQs, PIB, explainers
    SECONDARY = "secondary"                  # Commentary, analysis


class RetrievalCoverage(str, Enum):
    """How well the retrieval covered the query."""
    FULL = "full"           # Strong evidence found
    PARTIAL = "partial"     # Some evidence, but incomplete
    GAP = "gap"             # Known gap in knowledge
    CONFLICT = "conflict"   # Conflicting sources found
    NONE = "none"           # Nothing found


# ── Source type → Evidence level mapping ─────────────────────────────────────

SOURCE_TYPE_TO_EVIDENCE = {
    "act": EvidenceLevel.PRIMARY_LEGAL,
    "rule": EvidenceLevel.PRIMARY_LEGAL,
    "notification": EvidenceLevel.PRIMARY_LEGAL,
    "law": EvidenceLevel.PRIMARY_LEGAL,
    "rules": EvidenceLevel.PRIMARY_LEGAL,
    "scheme": EvidenceLevel.OFFICIAL_GOVERNMENT,
    "portal": EvidenceLevel.OFFICIAL_GOVERNMENT,
    "board": EvidenceLevel.OFFICIAL_GOVERNMENT,
    "government_guidance": EvidenceLevel.OFFICIAL_EXPLANATORY,
    "procedure": EvidenceLevel.OFFICIAL_EXPLANATORY,
    "faq": EvidenceLevel.OFFICIAL_EXPLANATORY,
    "statistics": EvidenceLevel.SECONDARY,
    "legal_aid": EvidenceLevel.OFFICIAL_GOVERNMENT,
    "other": EvidenceLevel.SECONDARY,
}


# ── LegalSource (from Phase 3 links.txt) ────────────────────────────────────

class LegalSource(BaseModel):
    """Structured metadata for an authoritative legal source."""
    source_id: str
    title: str
    source_type: SourceType
    authority: str
    jurisdiction: Jurisdiction
    state: Optional[str] = None
    worker_types: list[str] = Field(default_factory=lambda: ["all"])
    issue_categories: list[str] = Field(default_factory=lambda: ["all"])
    source_url: str
    status: SourceStatus = SourceStatus.ACTIVE
    effective_from: Optional[str] = None
    last_verified: str = ""
    notes: Optional[str] = None

    def matches_case(
        self,
        worker_type: str = None,
        state: str = None,
        issue: str = None,
    ) -> bool:
        if self.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED):
            return False
        if worker_type and "all" not in self.worker_types:
            if worker_type not in self.worker_types:
                return False
        if state:
            if self.jurisdiction == Jurisdiction.CENTRAL:
                pass
            elif self.state and self.state.lower() != state.lower():
                return False
        if issue and "all" not in self.issue_categories:
            if issue not in self.issue_categories:
                return False
        return True


# ── RAGDocument (chunk ready for Qdrant) ─────────────────────────────────────

class RAGDocument(BaseModel):
    """
    A chunk ready for embedding and Qdrant storage.
    Text + full metadata travel together.
    """
    doc_id: str
    text: str

    # Source traceability
    source_id: str
    title: str
    authority: str

    # Classification
    jurisdiction: str = "central"
    source_type: str = ""
    evidence_level: str = EvidenceLevel.SECONDARY.value

    # Filtering
    worker_types: list[str] = Field(default_factory=lambda: ["all_workers"])
    issue_categories: list[str] = Field(default_factory=lambda: ["all"])

    # Legal structure
    topic: str = ""
    chapter: str = ""
    section: str = ""
    subsection: str = ""

    # Status
    legal_status: str = ""
    effective_from: str = ""

    # URLs
    official_url: str = ""
    document_url: str = ""

    # Verification
    last_verified: str = ""
    notes: str = ""

    def to_qdrant_payload(self) -> dict:
        """Convert to Qdrant payload (everything except the vector)."""
        return self.model_dump(exclude={"doc_id"})


# ── LegalEvidence (RAG → Agent bridge) ───────────────────────────────────────

class EvidenceFinding(BaseModel):
    """A single piece of retrieved evidence."""
    claim: str
    source_title: str
    source_id: str
    section: str = ""
    evidence_text: str = ""
    official_url: str = ""
    evidence_level: str = EvidenceLevel.SECONDARY.value
    legal_status: str = ""
    last_verified: str = ""
    retrieval_score: float = 0.0


class LegalEvidence(BaseModel):
    """
    The structured output from the RAG system.
    This is what the LLM receives — not raw Qdrant records.
    """
    issue: str = ""
    jurisdiction: str = "central"
    worker_type: str = ""

    coverage: RetrievalCoverage = RetrievalCoverage.NONE
    evidence: list[EvidenceFinding] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Build context string for injection into the LLM system prompt."""
        lines = []
        lines.append(f"ISSUE: {self.issue}")
        lines.append(f"JURISDICTION: {self.jurisdiction}")
        lines.append(f"COVERAGE: {self.coverage.value}")

        if self.evidence:
            lines.append("\nEVIDENCE FOUND:")
            for i, e in enumerate(self.evidence, 1):
                lines.append(f"\n  [{i}] {e.source_title}")
                if e.section:
                    lines.append(f"      Section: {e.section}")
                lines.append(f"      Evidence: {e.evidence_text[:500]}")
                if e.official_url:
                    lines.append(f"      Source: {e.official_url}")
                lines.append(f"      Level: {e.evidence_level}")

        if self.gaps:
            lines.append("\nKNOWN GAPS (information not available):")
            for g in self.gaps:
                lines.append(f"  - {g}")

        if self.conflicts:
            lines.append("\nCONFLICTING INFORMATION FOUND:")
            for c in self.conflicts:
                lines.append(f"  - {c}")
            lines.append("  DO NOT choose one side. Tell the worker about the conflict.")

        if self.limitations:
            lines.append("\nLIMITATIONS:")
            for lim in self.limitations:
                lines.append(f"  - {lim}")

        return "\n".join(lines)


# ── LegalChunk (backwards compat with Phase 3) ──────────────────────────────

class LegalChunk(BaseModel):
    """A section/passage from a legal document, with full traceability."""
    chunk_id: str
    source_id: str
    title: str
    section: Optional[str] = None
    subsection: Optional[str] = None
    content: str
    authority: str
    source_url: str
    jurisdiction: Jurisdiction
    state: Optional[str] = None
    worker_types: list[str] = Field(default_factory=lambda: ["all"])
    issue_categories: list[str] = Field(default_factory=lambda: ["all"])
