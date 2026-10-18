"""
voice_routes.py — REST API for the Sarvam-powered voice pipeline.

Endpoints:
  POST /api/v1/voice/stt          — Audio → Transcript
  POST /api/v1/voice/tts          — Text → Audio
  POST /api/v1/voice/converse     — Full turn: Audio in → response text + audio out
  GET  /api/v1/voice/languages    — List supported languages
  GET  /api/v1/voice/speakers     — List available TTS speakers

Agent architecture (converse endpoint):
  Sarvam STT → transcript
  → LLM (Groq/OpenAI-compatible) with tool schemas
  → LLM calls tools (update_case_info, retrieve_rights, escalate_safety …)
  → Orchestrator executes tools, returns results
  → LLM generates final spoken response
  → Sarvam TTS → audio

If LLM_API_KEY is not set, falls back to a minimal rule-based response
so the app still runs (STT + TTS always work).
"""

import json
import base64
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional

from app.api.session import session_manager
from app.voice.stt import get_stt_service
from app.voice.tts import get_tts_service
from app.agent.orchestrator import Orchestrator
from app.agent.tool_registry import get_tools_for_status
from app.agent.llm import run_agent_turn, get_llm_client


router = APIRouter(prefix="/voice", tags=["Voice (Sarvam)"])


# ── Request / Response models ────────────────────────────────────────────────

class TTSRequest(BaseModel):
    """Request body for text-to-speech."""
    text: str = Field(..., description="Text to convert to speech")
    language_code: str = Field(default="hi-IN", description="BCP-47 language code")
    speaker: str = Field(default="meera", description="Voice persona")
    pace: float = Field(default=1.0, ge=0.5, le=2.0, description="Speed multiplier")


class STTResponse(BaseModel):
    """Response from speech-to-text."""
    transcript: str
    language_code: str = ""
    provider: str = ""
    error: Optional[str] = None


class TTSResponse(BaseModel):
    """Response from text-to-speech."""
    audio_base64: str = ""
    content_type: str = "audio/wav"
    sample_rate: int = 24000
    provider: str = ""
    error: Optional[str] = None


class ConverseRequest(BaseModel):
    """Request for a full conversation turn via JSON (base64 audio)."""
    audio_base64: str = Field(..., description="Base64-encoded audio data")
    session_id: str = Field(..., description="Session ID from /sessions")
    language_code: str = Field(default="auto", description="Language code or 'auto'")
    stt_mode: str = Field(default="transcribe", description="STT mode")
    tts_speaker: str = Field(default="meera", description="TTS voice")
    tts_language: str = Field(default="hi-IN", description="TTS output language")


class ChatTurnRequest(BaseModel):
    """Request for a text conversation turn."""
    session_id: str = Field(..., description="Session ID from /sessions")
    message: str = Field(..., description="Worker's message text")
    tts_speaker: str = Field(default="ritu", description="TTS voice")
    tts_language: str = Field(default="hi-IN", description="TTS output language")
    synthesize_speech: bool = Field(default=False, description="Whether to also generate TTS audio")


class ChatTurnResponse(BaseModel):
    """Response from a text conversation turn."""
    agent_text: str = ""
    case_status: str = ""
    tool_calls_made: list[str] = Field(default_factory=list)
    audio_base64: str = ""
    error: Optional[str] = None


class ConverseResponse(BaseModel):
    """Response from a full conversation turn."""
    # STT result
    user_transcript: str = ""
    detected_language: str = ""

    # Agent response
    agent_text: str = ""
    case_status: str = ""
    tool_calls_made: list[str] = Field(default_factory=list)

    # TTS result
    audio_base64: str = ""
    audio_content_type: str = "audio/wav"

    # Errors
    stt_error: Optional[str] = None
    tts_error: Optional[str] = None
    agent_error: Optional[str] = None


class LanguageItem(BaseModel):
    code: str
    name: str
    native_name: str
    stt_supported: bool
    tts_supported: bool


class LanguagesResponse(BaseModel):
    languages: list[LanguageItem]
    total: int


class SpeakersResponse(BaseModel):
    speakers: list[str]
    language_code: str


# ── STT endpoint ─────────────────────────────────────────────────────────────

@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    language_code: str = Form(default="auto", description="BCP-47 language code or 'auto'"),
    mode: str = Form(default="transcribe", description="transcribe|translate|codemix|verbatim"),
):
    """Transcribe audio to text using Sarvam Saaras v4."""
    stt = get_stt_service()
    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    result = await stt.transcribe(audio_data, language_code, mode)

    if result.error:
        return STTResponse(transcript="", error=result.error, provider=result.provider)

    return STTResponse(
        transcript=result.transcript,
        language_code=result.language_code,
        provider=result.provider,
    )


# ── TTS endpoint ─────────────────────────────────────────────────────────────

@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """Convert text to speech using Sarvam Bulbul v3."""
    tts = get_tts_service()
    result = await tts.synthesize(
        text=req.text,
        language_code=req.language_code,
        speaker=req.speaker,
        pace=req.pace,
    )

    if result.error:
        return TTSResponse(error=result.error, provider=result.provider)

    return TTSResponse(
        audio_base64=result.audio_base64,
        content_type=result.content_type,
        sample_rate=result.sample_rate,
        provider=result.provider,
    )


# ── Converse endpoint (full agentic turn) ────────────────────────────────────

@router.post("/converse", response_model=ConverseResponse)
async def converse(req: ConverseRequest):
    """
    Full conversation turn: audio in → agent response + audio out.

    Flow:
      1. Decode base64 audio
      2. Sarvam STT → transcript
      3. LLM agentic loop (tool calls via orchestrator)
      4. Sarvam TTS → spoken response
      5. Return everything
    """
    # 1. Validate session
    session = session_manager.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    orch = session.orchestrator
    response = ConverseResponse()

    # 2. Decode audio
    try:
        audio_data = base64.b64decode(req.audio_base64)
    except Exception as e:
        response.stt_error = f"Invalid base64 audio: {str(e)}"
        return response

    # 3. STT
    stt = get_stt_service()
    stt_result = await stt.transcribe(audio_data, req.language_code, req.stt_mode)

    if not stt_result.is_success:
        response.stt_error = stt_result.error
        return response

    response.user_transcript = stt_result.transcript
    response.detected_language = stt_result.language_code
    print(f"\n  [stt] Transcribed: {stt_result.transcript}")

    # 4. Record transcript in orchestrator
    orch.process_transcript(stt_result.transcript)

    # 5. Run LLM agent turn
    agent_result = await _run_llm_turn(orch, stt_result.transcript)
    response.agent_text = agent_result["text"]
    response.case_status = orch.case.status.value
    response.tool_calls_made = agent_result.get("tools_called", [])

    if agent_result.get("error"):
        response.agent_error = agent_result["error"]

    # Record agent response in transcript history
    if response.agent_text:
        orch.process_agent_transcript(response.agent_text)

    # 6. TTS
    if response.agent_text:
        tts = get_tts_service()
        tts_lang = req.tts_language

        # Mirror the worker's detected language for the response
        if stt_result.language_code in ("hi-IN", "hi"):
            tts_lang = "hi-IN"
        elif stt_result.language_code in ("en-IN", "en"):
            tts_lang = "en-IN"

        tts_result = await tts.synthesize(
            text=response.agent_text,
            language_code=tts_lang,
            speaker=req.tts_speaker,
        )

        if tts_result.is_success:
            response.audio_base64 = tts_result.audio_base64
            response.audio_content_type = tts_result.content_type
        else:
            response.tts_error = tts_result.error

    return response


# ── Text chat endpoint (agentic turn from typed input) ───────────────────────

@router.post("/chat", response_model=ChatTurnResponse)
async def chat(req: ChatTurnRequest):
    """
    Run an agentic conversation turn for text input.
    Executes tools (update_case_info, check_eligibility, retrieve_rights, Tavily search, etc.)
    and returns structured agent response + case state + optional TTS audio.
    """
    session = session_manager.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    orch = session.orchestrator
    response = ChatTurnResponse()

    # 1. Record user transcript
    orch.process_transcript(req.message)

    # 2. Run LLM agent turn with tools
    agent_result = await _run_llm_turn(orch, req.message)
    response.agent_text = agent_result.get("text", "")
    response.case_status = orch.case.status.value
    response.tool_calls_made = agent_result.get("tools_called", [])

    if agent_result.get("error"):
        response.error = agent_result["error"]

    # 3. Record agent response
    if response.agent_text:
        orch.process_agent_transcript(response.agent_text)

        # 4. Optional TTS synthesis
        if req.synthesize_speech:
            tts = get_tts_service()
            tts_result = await tts.synthesize(
                text=response.agent_text,
                language_code=req.tts_language,
                speaker=req.tts_speaker,
            )
            if tts_result.is_success and tts_result.audio_base64:
                response.audio_base64 = tts_result.audio_base64

    return response


# ── Languages endpoint ───────────────────────────────────────────────────────

@router.get("/languages", response_model=LanguagesResponse)
async def get_languages():
    """List all languages supported by WorkerSaathi."""
    stt = get_stt_service()
    tts = get_tts_service()
    tts_langs = {l.code for l in tts.get_supported_languages()}

    all_langs = {}
    for lang in stt.get_supported_languages():
        all_langs[lang.code] = LanguageItem(
            code=lang.code,
            name=lang.name,
            native_name=lang.native_name,
            stt_supported=True,
            tts_supported=lang.code in tts_langs,
        )

    languages = list(all_langs.values())
    return LanguagesResponse(languages=languages, total=len(languages))


# ── Speakers endpoint ────────────────────────────────────────────────────────

@router.get("/speakers", response_model=SpeakersResponse)
async def get_speakers(language_code: str = "hi-IN"):
    """List available TTS voice speakers for a language."""
    tts = get_tts_service()
    speakers = tts.get_available_speakers(language_code)
    return SpeakersResponse(speakers=speakers, language_code=language_code)


# ── LLM agentic turn ─────────────────────────────────────────────────────────

async def _run_llm_turn(orch: Orchestrator, user_text: str) -> dict:
    """
    Run one full agent turn through the LLM.

    If LLM_API_KEY is set → full LLM reasoning with tool calls.
    If not set            → minimal rule-based fallback (STT/TTS still work).

    Returns: {"text": "...", "tools_called": [...], "error": "..." (optional)}
    """
    client = get_llm_client()

    if client is None:
        # No LLM key — use minimal fallback so the app still runs
        print("  [llm] No LLM key set — using rule-based fallback")
        return _rule_based_fallback(orch, user_text)

    # Get the system prompt with live case context
    system_prompt = orch.get_initial_prompt()

    # Get tools available for the current case status
    tools = get_tools_for_status(orch.case.status.value)

    # Build conversation history from transcript
    history = _build_history(orch)

    # Define the tool executor (wraps orchestrator)
    def execute_tool(tool_name: str, args: dict) -> dict:
        return orch.handle_tool_call(tool_name, args)

    result = await run_agent_turn(
        system_prompt=system_prompt,
        user_message=user_text,
        tools=tools,
        tool_executor=execute_tool,
        conversation_history=history,
    )

    # If LLM returned nothing, fall back
    if not result.get("text"):
        fallback = _rule_based_fallback(orch, user_text)
        fallback["tools_called"] = result.get("tools_called", []) + fallback.get("tools_called", [])
        return fallback

    return result


def _build_history(orch: Orchestrator) -> list[dict]:
    """
    Convert the orchestrator's transcript history into OpenAI message format.
    Keeps only the last 6 turns to limit context window usage.
    """
    messages = []
    for line in orch._transcript_history[-12:]:
        if line.startswith("Worker: "):
            messages.append({"role": "user", "content": line[8:]})
        elif line.startswith("WorkerSaathi: "):
            messages.append({"role": "assistant", "content": line[14:]})
    # Remove the last user message — it will be sent as the current turn
    if messages and messages[-1]["role"] == "user":
        messages = messages[:-1]
    return messages


# ── Rule-based fallback (used when LLM key is missing) ──────────────────────

def _rule_based_fallback(orch: Orchestrator, user_text: str) -> dict:
    """
    Minimal fallback that keeps the app functional without an LLM key.
    Uses the case state machine to decide what to say.
    Does NOT do keyword classification — just asks the next question.
    """
    case = orch.case
    cm = orch.case_manager
    next_q = cm.get_next_question()

    if next_q:
        return {"text": next_q, "tools_called": []}

    if not case.get_filled_fields():
        return {
            "text": (
                "Namaste! Main WorkerSaathi hoon. "
                "Aap mujhe apni kaam se judi problem bata sakte hain — "
                "jaise payment nahi mili, account block ho gaya, ya koi aur issue."
            ),
            "tools_called": [],
        }

    return {
        "text": (
            "Main aapki baat sun raha hoon. "
            "Kripya apni problem detail mein batayein — "
            "kya hua, kab hua, aur kitna amount involved hai."
        ),
        "tools_called": [],
        "error": "llm_key_not_configured",
    }
