"""
schemas.py -- Pydantic request/response models for the WorkerSaathi API.

All API contracts are defined here. FastAPI uses these for
automatic validation, serialization, and Swagger documentation.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "WorkerSaathi"
    version: str = "0.1.0"
    environment: str = "development"
    active_sessions: int = 0


# ── Session ───────────────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    """Optional metadata when creating a session."""
    language: str = Field(default="hi", description="Preferred language: hi, en, or hinglish")


class SessionCreateResponse(BaseModel):
    session_id: str
    case_id: str
    status: str
    system_prompt: str
    available_tools: list[dict]
    created_at: str


class SessionSummary(BaseModel):
    session_id: str
    case_id: str
    status: str
    worker_type: str
    issue_category: str
    created_at: str
    last_active: str


class SessionDetailResponse(BaseModel):
    session_id: str
    case_id: str
    status: str
    case: CaseResponse
    available_tools: list[dict]
    system_prompt: str
    created_at: str
    last_active: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int


# ── Tool Execution ────────────────────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    """Arguments to pass to a tool."""
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific arguments (same schema as AssemblyAI tool.call)"
    )


class ToolCallResponse(BaseModel):
    tool_name: str
    tool_result: dict[str, Any]
    changed_fields: list[str]
    needs_prompt_update: bool
    new_system_prompt: Optional[str] = None
    available_tools: list[dict] = Field(default_factory=list)


# ── Case ──────────────────────────────────────────────────────────────────────

class CaseResponse(BaseModel):
    case_id: str
    status: str
    worker_type: str
    issue_category: str
    state: str
    safety_level: str
    created_at: str

    # Filled fields
    platform_or_employer: Optional[str] = None
    incident_date: Optional[str] = None
    payment_due_date: Optional[str] = None
    amount: Optional[str] = None
    deactivation_reason: Optional[str] = None
    injury_details: Optional[str] = None
    payment_pending_duration: Optional[str] = None
    raw_description: Optional[str] = None
    turn_count: int = 0

    # Computed
    filled_fields: dict[str, str] = Field(default_factory=dict)


class MissingFieldsResponse(BaseModel):
    missing_fields: list[dict[str, Any]]
    next_question: Optional[str] = None
    is_ready_for_retrieval: bool = False


class CaseContextResponse(BaseModel):
    context: str
    system_prompt: str


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidencePackageResponse(BaseModel):
    case_id: str
    purpose: str
    evidence_package: dict[str, Any]
    action_plan: list[dict[str, Any]]


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KnowledgeStatsResponse(BaseModel):
    total_sources: int = 0
    total_documents: int = 0
    total_gaps: int = 0
    total_conflicts: int = 0
    jurisdiction: str = "central"


class SourceItem(BaseModel):
    id: str = ""
    title: str = ""
    source_type: str = ""
    url: str = ""
    jurisdiction: str = ""


class KnowledgeSourcesResponse(BaseModel):
    sources: list[SourceItem]
    total: int


# ── Chat (text mode) ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="Worker's text message")


class ChatResponse(BaseModel):
    session_id: str
    message: str
    case_status: str
    tool_calls_made: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
