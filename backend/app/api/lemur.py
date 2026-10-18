"""
lemur.py -- Post-call legal action plan generator.

Generates a structured legal action plan from the conversation
transcript using the orchestrator's built-in action planner.
No external LLM dependency required.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.session import session_manager

router = APIRouter(tags=["Action Plan"])


class ActionPlanResponse(BaseModel):
    plan: str


@router.post("/sessions/{session_id}/action-plan", response_model=ActionPlanResponse)
async def generate_action_plan(session_id: str):
    """
    Generate a formal legal action plan based on the full conversation transcript.

    Uses the orchestrator's built-in evidence/action planner to produce
    a structured plan with case summary, legal rights, and next steps.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    orch = session.orchestrator
    transcript = orch.get_full_transcript()
    case = orch.case

    # Build a structured plan from what we know about the case
    plan_parts = []

    plan_parts.append("# WorkerSaathi Legal Action Plan\n")

    # Case Summary
    plan_parts.append("## 1. Case Summary\n")
    filled = case.get_filled_fields()
    if filled:
        for k, v in filled.items():
            label = k.replace("_", " ").title()
            plan_parts.append(f"- **{label}**: {v}")
    else:
        plan_parts.append("- Case details are still being collected.")

    plan_parts.append("")

    # Legal Rights
    plan_parts.append("## 2. Your Legal Rights\n")

    issue = case.issue_category.value if case.issue_category else "unknown"
    worker = case.worker_type.value if case.worker_type else "unknown"

    if issue == "unpaid_wages":
        plan_parts.extend([
            "Under the **Payment of Wages Act, 1936** and **Code on Wages, 2019**:",
            "- Your employer must pay wages within 7 days of the end of each wage period",
            "- Delayed wages attract compensation up to 10x the withheld amount",
            "- You can file a complaint with the **Labour Commissioner** of your state",
            "- Online complaint portal: https://clc.gov.in",
        ])
    elif issue == "platform_deactivation":
        plan_parts.extend([
            "Under the **Code on Social Security, 2020** (in force Nov 2025):",
            "- Aggregators must register all gig workers on the government portal",
            "- You are entitled to a written explanation for deactivation",
            "- File a complaint with the **Gig Workers' Welfare Board** (if your state has one)",
            "- States with active gig worker laws: Rajasthan, Karnataka, Jharkhand, AP, Telangana",
        ])
    elif issue == "workplace_injury":
        plan_parts.extend([
            "Under the **Employees' Compensation Act, 1923** and **ESIC Act, 1948**:",
            "- You are entitled to compensation for injuries sustained during employment",
            "- Report the injury to your employer in writing immediately",
            "- File a claim with the **Employees' Compensation Commissioner**",
            "- If covered by ESIC, visit the nearest ESIC dispensary",
            "- Emergency: Call 112 if you are in immediate danger",
        ])
    else:
        plan_parts.extend([
            "- You have the right to fair wages under the **Code on Wages, 2019**",
            "- Gig workers are covered under the **Code on Social Security, 2020**",
            "- You may contact the **Labour Commissioner** for any workplace dispute",
        ])

    plan_parts.append("")

    # Recommended Next Steps
    plan_parts.append("## 3. Recommended Next Steps\n")
    plan_parts.extend([
        "1. **Document everything** — Save all payment receipts, chats, and screenshots",
        "2. **Send a written notice** — Email or WhatsApp your employer/platform with the issue",
        "3. **File a complaint** — Use the state Labour Commissioner portal or app",
        "4. **Contact a legal aid clinic** — District Legal Services Authority (DLSA) provides free help",
        "5. **Follow up** — Track your complaint number and follow up every 7 days",
    ])

    plan_parts.append("")

    # Grievance Template
    plan_parts.append("## 4. Grievance Message Template\n")

    platform = case.platform_or_employer or "[Platform/Employer Name]"
    amount = f"₹{case.amount}" if case.amount else "[Amount]"
    state = case.state.value if case.state and case.state.value != "Unknown" else "[State]"

    plan_parts.append(f"""```
To: Grievance Team, {platform}
Subject: Formal Grievance — {issue.replace('_', ' ').title()}

Dear Sir/Madam,

I am writing to formally raise a grievance regarding my employment with {platform}.

Issue: {issue.replace('_', ' ').title()}
Amount in dispute: {amount}
State: {state}

I request you to resolve this matter within 7 working days as required under
applicable Indian labour laws. Failure to do so will compel me to approach
the Labour Commissioner and relevant authorities.

Yours sincerely,
[Your Name]
[Your Worker/Driver ID]
[Date]
```""")

    plan_parts.append("")
    plan_parts.append("---")
    plan_parts.append("*Generated by WorkerSaathi — AI-powered worker rights navigator*")
    plan_parts.append("*This is not a substitute for professional legal advice.*")

    plan_text = "\n".join(plan_parts)

    # Also try the built-in ActionPlanner if available
    try:
        from app.evidence.action_planner import ActionPlanner
        planner = ActionPlanner()
        if transcript.strip():
            generated = planner.generate(case, transcript)
            if generated and len(generated) > 200:
                plan_text = generated
    except Exception as e:
        print(f"[action-plan] ActionPlanner not available, using template: {e}")

    return ActionPlanResponse(plan=plan_text)
