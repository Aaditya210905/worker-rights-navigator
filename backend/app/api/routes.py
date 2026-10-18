"""
routes.py -- Core REST API routes for WorkerSaathi.

All routes are mounted under /api/v1.
The Orchestrator handles all business logic — routes just
validate, dispatch, and format responses.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse

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
    EligibilityCheckRequest,
    WageCalculationRequest,
    ComplaintGenerateRequest,
)
from app.agent.tool_registry import get_tools_for_status
from app.agent.prompts import build_system_prompt
from app.evidence.eligibility import EligibilityChecker
from app.evidence.wage_calculator import WageCalculator, WageCalculationResult
from app.evidence.screenshot_parser import EvidenceManager, EvidenceItem, EvidenceTimeline
from app.evidence.complaint_generator import (
    ComplaintGenerator, ComplaintAuthority, ComplaintLanguage
)

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
        days_worked=case.days_worked,
        has_eshram=case.has_eshram,
        eligibility_report=case.eligibility_report,
        wage_calculation=case.wage_calculation,
        evidence_items=case.evidence_items,
        complaint_drafts=case.complaint_drafts,
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

    This is the primary API — the same interface the voice
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


# ── Legal Help & Evidence Endpoints (Gireesh) ─────────────────────────────────

@router.post("/sessions/{session_id}/eligibility")
async def evaluate_eligibility(session_id: str, req: EligibilityCheckRequest):
    """
    Evaluate worker eligibility against the 90/120-Day Rule, e-Shram,
    Section 114 status, and State Gig Worker Acts.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    days_primary = req.days_with_primary_aggregator if req.days_with_primary_aggregator is not None else case.days_worked
    has_eshram = req.has_eshram if req.has_eshram is not None else case.has_eshram
    worker_type = req.worker_type or case.worker_type
    state = req.state or case.state
    platform = req.platform_name or case.platform_or_employer

    report = EligibilityChecker.evaluate(
        worker_type=worker_type,
        state=state,
        days_with_primary_aggregator=days_primary,
        total_days_across_aggregators=req.total_days_across_aggregators,
        number_of_aggregators=req.number_of_aggregators,
        has_eshram=has_eshram,
        age=req.age or case.age,
        platform_name=platform,
    )

    case.eligibility_report = report.model_dump()
    if days_primary is not None:
        session.orchestrator.case_manager.update_field("days_worked", days_primary)
    if has_eshram is not None:
        session.orchestrator.case_manager.update_field("has_eshram", has_eshram)

    return report.model_dump()


@router.post("/sessions/{session_id}/wages")
async def calculate_wages(session_id: str, req: WageCalculationRequest):
    """
    Calculate itemized unpaid wages, unlawful deductions (Sec 18 cap),
    and 10x statutory compensation claim under Section 45 Code on Wages.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    calc_result = WageCalculator.calculate(
        base_unpaid=req.base_unpaid,
        withheld_incentives=req.withheld_incentives,
        unauthorized_deductions=req.unauthorized_deductions,
        fuel_or_expenses_withheld=req.fuel_or_expenses_withheld,
        worker_type=case.worker_type,
        state=case.state,
        period_description=req.period_description or case.payment_pending_duration,
    )

    case.wage_calculation = calc_result.model_dump()
    if calc_result.net_unpaid_balance > 0:
        session.orchestrator.case_manager.update_field("amount", str(int(calc_result.net_unpaid_balance)))

    return calc_result.model_dump()


@router.post("/sessions/{session_id}/evidence/upload")
async def upload_evidence(
    session_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
):
    """
    Upload payment screenshot, deactivation alert, or chat record.
    Automatically applies PII redaction (masks Aadhaar, bank numbers, OTPs)
    and extracts amounts, dates, and order IDs.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt", ".csv"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    filename = file.filename or "uploaded_proof.png"
    import os
    ext = os.path.splitext(filename)[1].lower()

    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB."
        )

    item = EvidenceManager.save_and_parse_upload(
        file_bytes=file_bytes,
        filename=filename,
        case_id=case.case_id,
        user_caption=caption,
    )


    # Append to case evidence items
    case.evidence_items.append(item.model_dump())

    # If amount was detected and case.amount is empty, update it
    if item.parsed_data.primary_amount and not case.amount:
        session.orchestrator.case_manager.update_field("amount", str(int(item.parsed_data.primary_amount)))
    if item.parsed_data.detected_platform and not case.platform_or_employer:
        session.orchestrator.case_manager.update_field("platform_or_employer", item.parsed_data.detected_platform)

    return {
        "status": "success",
        "evidence_id": item.evidence_id,
        "filename": item.filename,
        "annexure_label": item.annexure_label,
        "evidence_type": item.evidence_type.value,
        "parsed_data": item.parsed_data.model_dump(),
        "total_items": len(case.evidence_items),
    }


@router.get("/sessions/{session_id}/evidence")
async def get_evidence_and_timeline(session_id: str):
    """
    Get all uploaded evidence items and the compiled chronological Evidence Timeline.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    evidence_objs = []
    for itm in case.evidence_items:
        try:
            evidence_objs.append(EvidenceItem(**itm))
        except Exception:
            pass

    timeline = EvidenceManager.build_timeline(
        case_id=case.case_id,
        case_state_fields=case.get_filled_fields(),
        uploaded_items=evidence_objs,
    )

    return {
        "case_id": case.case_id,
        "evidence_items": [e.model_dump() for e in evidence_objs],
        "timeline": timeline.model_dump(),
        "timeline_markdown": timeline.to_markdown_table(),
    }


@router.post("/sessions/{session_id}/complaint")
async def generate_complaint(session_id: str, req: ComplaintGenerateRequest):
    """
    Generate formal dispute complaint draft (Aggregator Nodal Officer, Labour Commissioner, DLSA, Welfare Board)
    in English or Hindi.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    try:
        auth_type = ComplaintAuthority(req.authority_type)
    except ValueError:
        auth_type = ComplaintAuthority.AGGREGATOR_GRIEVANCE_OFFICER

    lang = ComplaintLanguage.HINDI if req.language == "hi" else ComplaintLanguage.ENGLISH

    wage_calc = None
    if case.wage_calculation:
        try:
            wage_calc = WageCalculationResult(**case.wage_calculation)
        except Exception:
            pass

    eligibility = None
    if case.eligibility_report:
        try:
            eligibility = EligibilityReport(**case.eligibility_report)
        except Exception:
            pass

    evidence_objs = []
    for itm in case.evidence_items:
        try:
            evidence_objs.append(EvidenceItem(**itm))
        except Exception:
            pass

    timeline = EvidenceManager.build_timeline(
        case_id=case.case_id,
        case_state_fields=case.get_filled_fields(),
        uploaded_items=evidence_objs,
    )

    doc = ComplaintGenerator.generate(
        case=case,
        authority=auth_type,
        language=lang,
        wage_calc=wage_calc,
        eligibility=eligibility,
        timeline=timeline,
        evidence_items=evidence_objs,
    )

    case.complaint_drafts.append(doc.model_dump())
    return doc.model_dump()


@router.get("/sessions/{session_id}/complaint/{doc_id}/html", response_class=HTMLResponse)
async def view_complaint_html(session_id: str, doc_id: str):
    """
    Returns clean, official printable HTML view for the generated complaint petition.
    """
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    for draft in case.complaint_drafts:
        if draft.get("document_id") == doc_id:
            return draft.get("body_html", "<p>No content</p>")

    raise HTTPException(status_code=404, detail="Complaint document not found")


@router.get("/sessions/{session_id}/complaint/{doc_id}/pdf")
async def download_complaint_pdf(session_id: str, doc_id: str):
    """
    Returns the generated complaint as a downloadable PDF.
    """
    from fastapi.responses import Response
    session = _get_session_or_404(session_id)
    case = session.orchestrator.case

    for draft in case.complaint_drafts:
        if draft.get("document_id") == doc_id:
            pdf_base64 = draft.get("body_pdf_base64")
            if not pdf_base64:
                raise HTTPException(
                    status_code=501,
                    detail="PDF generation not available (weasyprint not installed or failed)."
                )
            import base64
            pdf_bytes = base64.b64decode(pdf_base64)
            filename = f"{doc_id}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )

    raise HTTPException(status_code=404, detail="Complaint document not found")
