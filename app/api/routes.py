"""
routes.py -- Core REST API routes for WorkerSaathi.

All routes are mounted under /api/v1.
The Orchestrator handles all business logic — routes just
validate, dispatch, and format responses.
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.api.session import session_manager
from app.api.schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionSummary,
    SessionDetailResponse,
    SessionListResponse,
    ToolCallRequest,
    ToolCallResponse,
    CaseResponse,
    MissingFieldsResponse,
    CaseContextResponse,
    HealthResponse,
)
from app.agent.tool_registry import get_tools_for_status
from app.agent.prompts import build_system_prompt

router = APIRouter(tags=["WorkerSaathi API"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _case_to_response(case) -> CaseResponse:
    """Convert a CaseState to a CaseResponse."""
    return CaseResponse(
        case_id=case.case_id,
        status=case.status.value,
        worker_type=case.worker_type.value,
        issue_category=case.issue_category.value,
        state=case.state.value if case.state else "Unknown",
        safety_level=case.safety_level.value,
        created_at=case.created_at,
        platform_or_employer=case.platform_or_employer,
        incident_date=case.incident_date,
        payment_due_date=case.payment_due_date,
        amount=case.amount,
        deactivation_reason=case.deactivation_reason,
        injury_details=case.injury_details,
        payment_pending_duration=case.payment_pending_duration,
        raw_description=case.raw_description,
        turn_count=case.turn_count,
        filled_fields=case.get_filled_fields(),
    )


def _get_session_or_404(session_id: str):
    """Get a session or raise 404."""
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired."
        )
    return session


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    """Liveness probe with session count."""
    from app.config import settings
    return HealthResponse(
        environment=settings.app_env,
        active_sessions=session_manager.count(),
    )


# ── Session Management ───────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(req: SessionCreateRequest = SessionCreateRequest()):
    """Create a new conversation session."""
    session = session_manager.create_session()
    orch = session.orchestrator
    case = orch.case
    status = case.status.value

    return SessionCreateResponse(
        session_id=session.session_id,
        case_id=case.case_id,
        status=status,
        system_prompt=orch.get_initial_prompt(),
        available_tools=get_tools_for_status(status),
        created_at=datetime.fromtimestamp(session.created_at).isoformat(),
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    """List all active sessions."""
    sessions = session_manager.list_sessions()
    summaries = []
    for s in sessions:
        case = s.orchestrator.case
        summaries.append(SessionSummary(
            session_id=s.session_id,
            case_id=case.case_id,
            status=case.status.value,
            worker_type=case.worker_type.value,
            issue_category=case.issue_category.value,
            created_at=datetime.fromtimestamp(s.created_at).isoformat(),
            last_active=datetime.fromtimestamp(s.last_active).isoformat(),
        ))
    return SessionListResponse(sessions=summaries, total=len(summaries))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    """Get full session details including case state."""
    session = _get_session_or_404(session_id)
    orch = session.orchestrator
    case = orch.case
    status = case.status.value

    return SessionDetailResponse(
        session_id=session.session_id,
        case_id=case.case_id,
        status=status,
        case=_case_to_response(case),
        available_tools=get_tools_for_status(status),
        system_prompt=orch.get_initial_prompt(),
        created_at=datetime.fromtimestamp(session.created_at).isoformat(),
        last_active=datetime.fromtimestamp(session.last_active).isoformat(),
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """End a session."""
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")


# ── Tool Execution ────────────────────────────────────────────────────────────

@router.post(
    "/sessions/{session_id}/tools/{tool_name}",
    response_model=ToolCallResponse,
)
async def execute_tool(session_id: str, tool_name: str, req: ToolCallRequest):
    """
    Execute a tool call via the session's Orchestrator.

    This is the primary API — the same interface the AssemblyAI voice
    agent uses, now exposed as REST.
    """
    session = _get_session_or_404(session_id)
    orch = session.orchestrator

    # Execute the tool through the orchestrator
    result = orch.handle_tool_call(tool_name, req.arguments)

    # Parse the tool result JSON string back to dict
    try:
        parsed_result = json.loads(result["tool_result"])
    except (json.JSONDecodeError, KeyError):
        parsed_result = {"raw": result.get("tool_result", "")}

    # Get updated tools list
    status = orch.case.status.value
    available_tools = get_tools_for_status(status)

    return ToolCallResponse(
        tool_name=tool_name,
        tool_result=parsed_result,
        changed_fields=result.get("changed_fields", []),
        needs_prompt_update=result.get("needs_prompt_update", False),
        new_system_prompt=result.get("new_prompt"),
        available_tools=available_tools,
    )


# ── Case State ────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/case", response_model=CaseResponse)
async def get_case(session_id: str):
    """Get the current case state for a session."""
    session = _get_session_or_404(session_id)
    return _case_to_response(session.orchestrator.case)


@router.get(
    "/sessions/{session_id}/case/missing-fields",
    response_model=MissingFieldsResponse,
)
async def get_missing_fields(session_id: str):
    """Get missing fields and the next question to ask."""
    session = _get_session_or_404(session_id)
    cm = session.orchestrator.case_manager

    return MissingFieldsResponse(
        missing_fields=cm.get_missing_fields(),
        next_question=cm.get_next_question(),
        is_ready_for_retrieval=cm.is_ready_for_retrieval(),
    )


@router.get(
    "/sessions/{session_id}/case/context",
    response_model=CaseContextResponse,
)
async def get_case_context(session_id: str):
    """Get the current LLM system prompt context."""
    session = _get_session_or_404(session_id)
    orch = session.orchestrator
    context = orch.case_manager.get_case_context()
    return CaseContextResponse(
        context=context,
        system_prompt=build_system_prompt(context),
    )


# ── Transcript ────────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/transcript", status_code=200)
async def log_transcript(session_id: str, req: dict):
    """
    Log a user transcript line to the session.

    Body: { "text": "..." }
    """
    session = _get_session_or_404(session_id)
    text = req.get("text", "")
    if text.strip():
        session.orchestrator.process_transcript(text)
    return {"status": "ok", "turn_count": session.orchestrator.case.turn_count}
