"""
lemur.py -- Post-call analysis using AssemblyAI LeMUR.

Provides an endpoint to generate a structured legal action plan
based on the conversation transcript of a voice session.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import assemblyai as aai

from app.api.session import session_manager
from app.config import settings

router = APIRouter(tags=["LeMUR Analysis"])


class ActionPlanResponse(BaseModel):
    plan: str


@router.post("/sessions/{session_id}/action-plan", response_model=ActionPlanResponse)
async def generate_action_plan(session_id: str):
    """
    Generate a formal legal action plan using AssemblyAI LeMUR
    based on the full conversation transcript.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript = session.orchestrator.get_full_transcript()
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty")

    api_key = settings.assemblyai_api_key
    if not api_key or api_key == "your_key_here":
        raise HTTPException(status_code=500, detail="AssemblyAI API key not configured")

    aai.settings.api_key = api_key

    # Initialize LeMUR with the input text
    prompt = (
        "You are an expert Indian labor lawyer. "
        "Review the following conversation between a gig worker and the WorkerSaathi agent. "
        "Generate a structured, formal legal action plan that the worker can use to resolve their issue. "
        "The output should include:\n"
        "1. Case Summary\n"
        "2. Identified Legal Rights (from Indian law)\n"
        "3. Recommended Next Steps\n"
        "4. A drafted formal grievance message/letter to the employer or platform.\n\n"
        "CRITICAL INSTRUCTION: Redact any personally identifiable information (PII) such as "
        "phone numbers, email addresses, exact bank account numbers, or precise home addresses "
        "by replacing them with [REDACTED].\n\n"
        "Format your response in Markdown, using appropriate headers and bullet points. "
        "Ensure the language is professional but easy to understand."
    )

    try:
        # We use aai.LemurTask directly with input_text instead of a transcript ID
        # because the conversation was handled via Voice agent (which streams and doesn't 
        # produce a standard stored transcript ID in this workflow easily without a separate recording).
        result = aai.Lemur().task(
            prompt=prompt,
            input_text=transcript,
            final_model=aai.LemurModel.default
        )
        return ActionPlanResponse(plan=result.response)
    except Exception as e:
        print(f"[LeMUR] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate action plan: {str(e)}")
