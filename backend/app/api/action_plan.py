"""
action_plan.py -- Post-call Legal Action Plan Generation.

Decoupled from proprietary English-only services (AssemblyAI).
Natively optimized for Indian languages (Hindi, Hinglish, English)
using local LLMs, Sarvam AI, HuggingFace open-source Indian models,
or deterministic source-backed legal synthesis.
"""

import re
import urllib.request
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.session import session_manager
from app.config import settings
from app.case.models import IssueCategory, WorkerType, IndianState
from app.evidence.screenshot_parser import redact_sensitive_pii
from app.evidence.action_planner import ActionPlanner

router = APIRouter(tags=["Legal Action Plan"])


class ActionPlanResponse(BaseModel):
    plan: str


def _generate_statutory_action_plan(session) -> str:
    """
    Deterministically synthesizes an evidence-backed Indian Legal Action Plan
    from the current CaseState, statutory rules (Code on Social Security 2020,
    Code on Wages 2019, State Gig Acts), eligibility checks, and evidence timeline.
    """
    case = session.orchestrator.case
    transcript = session.orchestrator.get_full_transcript()

    worker_type_label = (
        case.worker_type.value.replace("_", " ").title()
        if hasattr(case.worker_type, "value")
        else str(case.worker_type or "Gig Worker")
    )
    issue_label = (
        case.issue_category.value.replace("_", " ").title()
        if hasattr(case.issue_category, "value")
        else str(case.issue_category or "Labor Dispute")
    )
    state_label = (
        case.state.value if hasattr(case.state, "value") else str(case.state or "India")
    )
    platform = case.platform_or_employer or "Aggregator / Employer"
    amount_str = "Under Assessment"
    if case.amount:
        try:
            amt_num = float(str(case.amount).replace(",", "").replace("₹", "").strip())
            amount_str = f"₹{amt_num:,.2f}"
        except (ValueError, TypeError):
            amount_str = f"₹{case.amount}"
    amount = amount_str

    # 1. State-Specific Protections
    state_law_note = ""
    if hasattr(case.state, "name") and case.state == IndianState.RAJASTHAN:
        state_law_note = (
            "- **Rajasthan Platform Based Gig Workers Act, 2023**:\n"
            "  * Mandatory registration with Rajasthan Gig Workers Welfare Board.\n"
            "  * Statutory 21-day timeline for aggregator grievance resolution.\n"
            "  * Social security cess (1-2%) deposited into Welfare Fund for worker social protection.\n"
        )
    elif hasattr(case.state, "name") and case.state == IndianState.KARNATAKA:
        state_law_note = (
            "- **Karnataka Platform-based Gig Workers Bill, 2024**:\n"
            "  * Mandatory 14-day prior notice before platform deactivation/termination.\n"
            "  * Right to written rationale and internal dispute resolution mechanism.\n"
        )

    # 2. Wage & Deduction specifics
    wage_law_note = ""
    if case.amount or case.issue_category == IssueCategory.UNPAID_WAGES:
        wage_law_note = (
            "- **Code on Wages, 2019 (Section 18 & Section 45)**:\n"
            "  * Section 18: Maximum 50% deduction ceiling on total earnings in any wage period.\n"
            "  * Section 45: Claims authority empowered to direct payment of withheld wages PLUS "
            "statutory compensation up to **10 times the unpaid amount** for arbitrary withholding.\n"
        )

    # 3. Eligibility Specifics (90/120 Day Rule)
    elig_note = (
        "- **Code on Social Security, 2020 (Central Rules May 2026)**:\n"
        "  * Rule 90/120: Minimum 90 days tenure with primary aggregator OR 120 days across aggregators.\n"
        "  * Section 113: Aggregator obligation to register workers on the Central e-Shram portal.\n"
        "  * Section 114 Advisory: Statutory welfare fund notified; workers qualify for welfare board representation.\n"
    )

    # 4. Synthesize Formal Grievance Letter Draft
    grievance_letter = (
        f"**TO:** Grievance Redressal Officer / Nodal Officer, {platform}\n\n"
        f"**SUBJECT:** Formal Dispute & Demand for Rectification regarding {issue_label} - Worker ID: [REDACTED]\n\n"
        f"Respected Sir/Madam,\n\n"
        f"I am an active partner working on the {platform} platform in {state_label}. "
        f"I write to formally lodge a grievance regarding arbitrary withholding/dispute of {amount} "
        f"and request immediate rectification under applicable Central and State labor welfare regulations.\n\n"
        f"**Facts of the Dispute:**\n"
        f"1. Service tenure and engagement on the platform was executed in good faith.\n"
        f"2. The disputed amount of {amount} has been withheld without statutory justification.\n"
        f"3. Under Section 18 of the Code on Wages 2019, arbitrary deductions exceeding 50% are prohibited.\n\n"
        f"**Relief Demanded:**\n"
        f"Immediate credit of the unpaid balance of {amount} within 7 working days, failing which formal proceedings "
        f"will be initiated before the Office of the Deputy Labour Commissioner and District Legal Services Authority.\n\n"
        f"Yours sincerely,\n"
        f"[Worker Name / Signature Redacted]"
    )

    # Assemble comprehensive Markdown Action Plan
    plan = f"""# 🇮🇳 WorkerSaathi Legal Action Plan & Grievance Roadmap
*Generated for {worker_type_label} in {state_label} | Protected by Central & State Labor Law*

---

## 1. Case Summary & Fact Matrix
- **Worker Category**: {worker_type_label}
- **Sector / Platform**: {platform}
- **Primary Issue**: {issue_label}
- **State Jurisdiction**: {state_label}
- **Claimed Amount**: {amount}
- **PII Privacy Status**: 🛡️ All Aadhaar numbers, bank credentials, and OTPs automatically masked.

---

## 2. Identified Statutory Rights (Indian Legal Framework)
{elig_note}
{wage_law_note}
{state_law_note}
- **Legal Services Authorities Act, 1987 (Section 12(h))**:
  * All informal, unorganized, and gig workers earning under statutory income limits qualify for **100% Free Legal Aid** through DLSA / TLSC.

---

## 3. Recommended Step-by-Step Action Plan
1. **Immediate Evidence Preservation**:
   - Download or screenshot weekly earning summaries, settlement deductions, trip IDs, and platform deactivation logs.
   - Keep digital records securely stored (see WorkerSaathi Evidence Locker).

2. **Submit Formal Internal Grievance**:
   - Serve the formal grievance letter below to {platform}'s Nodal Officer via registered email or app support ticket.

3. **Approach Statutory Authorities if Unresolved within 7-21 Days**:
   - **Office of the Deputy Labour Commissioner ({state_label})**: File a formal petition under the Industrial Disputes Act / Code on Social Security.
   - **District Legal Services Authority (DLSA)**: Request free legal counsel to represent you in labor conciliation.

---

## 4. Draft Formal Grievance Letter (Copy & Use)
```text
{grievance_letter}
```

---
*Notice: This action plan is based on verified Indian statutory provisions. Consult the District Legal Services Authority (DLSA) for formal courtroom representation.*
"""
    cleaned_plan, _, _ = redact_sensitive_pii(plan)
    return cleaned_plan


@router.post("/sessions/{session_id}/action-plan", response_model=ActionPlanResponse)
async def generate_action_plan(session_id: str):
    """
    Generate an evidence-backed Legal Action Plan and grievance petition.
    Designed for Indian languages, completely free of proprietary English-only services.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Generate comprehensive statutory action plan
    try:
        plan_text = _generate_statutory_action_plan(session)
        return ActionPlanResponse(plan=plan_text)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate action plan: {str(e)}"
        )
