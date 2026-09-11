"""
models.py -- Data models for the legal knowledge system.

LegalSource: structured metadata for each official source.
LegalChunk: a section/passage from a legal document with full traceability.
"""

from enum import Enum
from typing import Optional
from datetime import date
from pydantic import BaseModel, Field


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


class LegalSource(BaseModel):
    """
    Structured metadata for an authoritative legal source.

    Each source maps to one entry in links.txt.
    The LLM never invents sources — it can only reference these.
    """
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
        """
        Check if this source is relevant to a given case.
        Returns True if the source matches on all provided dimensions.
        """
        if self.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED):
            return False

        # Check worker type
        if worker_type and "all" not in self.worker_types:
            if worker_type not in self.worker_types:
                return False

        # Check state/jurisdiction
        if state:
            if self.jurisdiction == Jurisdiction.CENTRAL:
                pass  # central sources apply everywhere
            elif self.state and self.state.lower() != state.lower():
                return False

        # Check issue
        if issue and "all" not in self.issue_categories:
            if issue not in self.issue_categories:
                return False

        return True


class LegalChunk(BaseModel):
    """
    A section/passage from a legal document, with full traceability.

    Every chunk retains its source, section, and authority so
    WorkerSaathi can say: "According to Section X of the Y Act..."
    """
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
