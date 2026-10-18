"""
voice_routes.py — REST API for the Sarvam-powered voice pipeline.

voice_routes.py — REST API for the Sarvam-powered voice pipeline.
that separate STT, TTS, and conversation into independent steps.

Endpoints:
  POST /api/v1/voice/stt          — Audio → Transcript
  POST /api/v1/voice/tts          — Text → Audio
  POST /api/v1/voice/converse     — Full turn: Audio in → response text + audio out
  GET  /api/v1/voice/languages    — List supported languages
  GET  /api/v1/voice/speakers     — List available TTS speakers
"""

import json
import base64
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.api.session import session_manager
from app.voice.stt import get_stt_service
from app.voice.tts import get_tts_service
from app.agent.orchestrator import Orchestrator


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
    """
    Transcribe audio to text using Sarvam Saaras v4.

    Supports 22 Indian languages + English. Use language_code='auto'
    for automatic detection, or 'hi-IN', 'en-IN', etc.
    """
    stt = get_stt_service()

    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    result = await stt.transcribe(audio_data, language_code, mode)

    if result.error:
        return STTResponse(
            transcript="",
            error=result.error,
            provider=result.provider,
        )

    return STTResponse(
        transcript=result.transcript,
        language_code=result.language_code,
        provider=result.provider,
    )


# ── TTS endpoint ─────────────────────────────────────────────────────────────

@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """
    Convert text to speech using Sarvam Bulbul v3.

    Supports 10 Indian languages + English. Returns base64-encoded audio.
    """
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


# ── Converse endpoint (full turn) ────────────────────────────────────────────

@router.post("/converse", response_model=ConverseResponse)
async def converse(req: ConverseRequest):
    """
    Full conversation turn: audio in → agent response + audio out.

    Flow:
      1. Decode base64 audio
      2. Sarvam STT → transcript
      3. Feed transcript to the session's Orchestrator
      4. Run a simple LLM-free response based on the orchestrator's state
      5. Sarvam TTS → spoken response
      6. Return everything

    The orchestrator handles tool dispatch, case state, and legal retrieval.
    The LLM reasoning happens through the tool calls, not in this endpoint.
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

    # 4. Feed transcript to orchestrator
    orch.process_transcript(stt_result.transcript)

    # 5. Generate agent response using the orchestrator's case context
    agent_response = _generate_agent_response(orch, stt_result.transcript)
    response.agent_text = agent_response["text"]
    response.case_status = orch.case.status.value
    response.tool_calls_made = agent_response.get("tools_called", [])

    # 6. TTS on the agent response
    if response.agent_text:
        tts = get_tts_service()
        tts_lang = req.tts_language

        # Auto-detect: if user spoke Hindi, respond in Hindi
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


# ── Languages endpoint ───────────────────────────────────────────────────────

@router.get("/languages", response_model=LanguagesResponse)
async def get_languages():
    """
    List all languages supported by WorkerSaathi.

    Shows both STT and TTS support per language.
    """
    stt = get_stt_service()
    tts = get_tts_service()

    stt_langs = {l.code for l in stt.get_supported_languages()}
    tts_langs = {l.code for l in tts.get_supported_languages()}

    # Merge unique languages
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


# ── Agent response generation ────────────────────────────────────────────────

def _generate_agent_response(orch: Orchestrator, user_text: str) -> dict:
    """
    Generate a conversational response based on the current case state.

    This uses the orchestrator's deterministic case state machine to
    decide what to say next. It automatically calls tools when the case
    state requires it (e.g., retrieve_rights when enough info is gathered).

    Returns:
        {"text": "...", "tools_called": [...]}
    """
    case = orch.case
    cm = orch.case_manager
    tools_called = []

    # Step 1: Try to auto-classify from the transcript
    # (The LLM normally does this, but for text mode we do it heuristically)
    _auto_classify(orch, user_text)

    # Step 2: Check if safety escalation is needed
    safety_keywords = [
        "injury", "hurt", "accident", "chot", "dard", "mar", "pit",
        "zakhmi", "hospital", "blood", "khoon", "trapped", "banda",
        "child", "bachcha", "trafficking", "threat", "dhamki",
    ]
    lower_text = user_text.lower()
    for kw in safety_keywords:
        if kw in lower_text:
            result = orch.handle_tool_call("escalate_safety", {
                "danger_type": "ongoing_injury" if kw in ("injury", "hurt", "chot", "zakhmi", "hospital") else "other_emergency",
                "description": user_text,
            })
            tools_called.append("escalate_safety")
            safety_resp = json.loads(result["tool_result"])
            return {
                "text": (
                    "🚨 Aapki suraksha sabse pehle hai. "
                    "Agar aap kisi khatre mein hain, toh turant 112 par call karein. "
                    + safety_resp.get("safety_response", "")
                ),
                "tools_called": tools_called,
            }

    # Step 3: Check case state and determine response
    filled = case.get_filled_fields()
    next_q = cm.get_next_question()

    # If we have enough info, auto-trigger rights retrieval
    if cm.is_ready_for_retrieval() and case.status.value in (
        "classified", "collecting_information", "retrieving_rights"
    ):
        # Build query from case info
        wt = case.worker_type.value if case.worker_type.value != "unknown" else "worker"
        ic = case.issue_category.value if case.issue_category.value != "unknown" else "rights"
        query = f"{wt} {ic} rights India"
        if case.state and case.state.value != "Unknown":
            query += f" {case.state.value}"

        result = orch.handle_tool_call("retrieve_rights", {"query": query})
        tools_called.append("retrieve_rights")

        parsed = json.loads(result["tool_result"])
        evidence = parsed.get("legal_evidence", "")

        if evidence:
            # Summarize the evidence for spoken response
            response_text = _build_rights_response(case, evidence)
            return {"text": response_text, "tools_called": tools_called}

    # If we need more info, ask the next question
    if next_q:
        # Acknowledge what we know + ask next question
        ack = _build_acknowledgment(case, filled)
        return {
            "text": f"{ack} {next_q}",
            "tools_called": tools_called,
        }

    # Default: acknowledge and offer help
    if not filled:
        return {
            "text": (
                "Namaste! Main WorkerSaathi hoon. "
                "Aap mujhe apni kaam se judi problem bata sakte hain — "
                "jaise payment nahi mili, account block ho gaya, ya koi aur issue."
            ),
            "tools_called": tools_called,
        }

    return {
        "text": (
            "Main aapki problem samajh gaya hoon. "
            "Kya aap aur koi jaankari dena chahte hain, "
            "ya main aapke rights check karun?"
        ),
        "tools_called": tools_called,
    }


def _auto_classify(orch: Orchestrator, text: str):
    """
    Heuristic auto-classification from transcript text.

    Uses STATE_NAME_MAP, WorkerType, IssueCategory from case/models.py —
    the single authoritative source. No duplicate maps here.
    """
    from app.case.models import STATE_NAME_MAP, WorkerType, IssueCategory

    lower = text.lower()
    updates = {}

    # ── Issue classification ─────────────────────────────────────────────────
    wage_keywords = [
        "payment", "salary", "paise", "paisa", "rupees", "pending",
        "nahi mili", "nahi diya", "wages", "pay", "tankhwah", "vetan",
        "तनख्वाह", "वेतन", "पैसे", "भुगतान",
    ]
    injury_keywords = [
        "injury", "hurt", "accident", "chot", "hadsa", "hospital",
        "zakhmi", "gir gaya", "fell", "चोट", "दुर्घटना", "घायल",
    ]
    deact_keywords = [
        "deactivat", "block", "suspend", "banned", "id band",
        "account band", "login nahi", "app se nikal",
        "खाता बंद", "अकाउंट बंद",
    ]

    def _match(keywords, txt, orig):
        for kw in keywords:
            search = orig if any(ord(c) > 0x0900 for c in kw) else txt
            if kw in search:
                return True
        return False

    if _match(wage_keywords, lower, text):
        updates["issue_category"] = IssueCategory.UNPAID_WAGES.value
    elif _match(injury_keywords, lower, text):
        updates["issue_category"] = IssueCategory.WORKPLACE_INJURY.value
    elif _match(deact_keywords, lower, text):
        updates["issue_category"] = IssueCategory.PLATFORM_DEACTIVATION.value

    # ── Worker type & platform name ──────────────────────────────────────────
    # Check platforms (longest first to avoid "ola" matching "hola" etc.)
    gig_platforms = {
        "urban company": "Urban Company",
        "shadowfax": "Shadowfax",
        "blinkit": "Blinkit",
        "rapido": "Rapido",
        "swiggy": "Swiggy",
        "zomato": "Zomato",
        "porter": "Porter",
        "zepto": "Zepto",
        "dunzo": "Dunzo",
        "borzo": "Borzo",
        "uber": "Uber",
        "ola": "Ola",
        "delivery": None,
        "driver": None,
        "platform": None,
    }
    for kw, platform_name in gig_platforms.items():
        if kw in lower:
            updates["worker_type"] = WorkerType.GIG_WORKER.value
            if platform_name:
                updates["platform_or_employer"] = platform_name
            break

    if "worker_type" not in updates:
        construction_kw = ["construction", "building", "mazdoor", "nirmaan",
                           "labour", "site", "thekedar", "निर्माण", "मजदूर"]
        if _match(construction_kw, lower, text):
            updates["worker_type"] = WorkerType.CONSTRUCTION_WORKER.value

    if "worker_type" not in updates:
        domestic_kw = ["domestic", "maid", "ghar ka kaam", "helper",
                       "cook", "nanny", "bai", "घरेलू", "घर का काम"]
        if _match(domestic_kw, lower, text):
            updates["worker_type"] = WorkerType.DOMESTIC_WORKER.value

    # ── State — uses STATE_NAME_MAP from case/models.py ─────────────────────
    # Longest match first to avoid "up" matching inside "cup" / "setup"
    for name in sorted(STATE_NAME_MAP, key=len, reverse=True):
        state_enum = STATE_NAME_MAP[name]
        search = text if any(ord(c) > 0x0900 for c in name) else lower
        if name in search:
            updates["state"] = state_enum.value
            break

    # ── Amount extraction ────────────────────────────────────────────────────
    import re
    amount_patterns = [
        r'(?:rs\.?|₹|rupees?|rupaiye?)\s*(\d[\d,]*)',
        r'(\d[\d,]*)\s*(?:rs\.?|₹|rupees?|rupaiye?)',
        r'(\d+)\s*(?:hazaar|hazar|thousand|हज़ार|हजार)',
    ]
    for pattern in amount_patterns:
        m = re.search(pattern, lower)
        if m:
            amount = m.group(1).replace(",", "")
            if any(w in lower for w in ("hazaar", "hazar", "thousand")):
                amount = str(int(amount) * 1000)
            updates["amount"] = amount
            break

    # ── Apply updates through the orchestrator ───────────────────────────────
    if updates:
        orch.handle_tool_call("update_case_info", {"confidence": "medium", **updates})




def _build_acknowledgment(case, filled: dict) -> str:
    """Build a brief spoken acknowledgment of what we know so far."""
    parts = []

    if case.worker_type.value != "unknown":
        wt_map = {
            "gig_worker": "delivery/platform worker",
            "construction_worker": "construction worker",
            "domestic_worker": "domestic worker",
        }
        parts.append(f"Aap ek {wt_map.get(case.worker_type.value, 'worker')} hain")

    if case.platform_or_employer:
        parts.append(f"{case.platform_or_employer} ke liye kaam karte hain")

    if case.issue_category.value != "unknown":
        ic_map = {
            "unpaid_wages": "payment pending hai",
            "workplace_injury": "kaam ke dauraan chot lagi",
            "platform_deactivation": "account deactivate ho gaya",
        }
        parts.append(ic_map.get(case.issue_category.value, ""))

    if case.amount:
        parts.append(f"₹{case.amount} ka maamla hai")

    if not parts:
        return "Theek hai."

    return "Main samajh raha hoon — " + ", ".join(p for p in parts if p) + "."


def _build_rights_response(case, evidence: str) -> str:
    """Build a spoken summary of legal rights from the evidence."""
    # Keep it concise for voice — max 3-4 key points
    lines = evidence.split("\n")
    key_points = []
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 20 and not stripped.startswith("---"):
            key_points.append(stripped)
        if len(key_points) >= 5:
            break

    summary = " ".join(key_points[:5])

    # Truncate for voice-friendly length
    if len(summary) > 400:
        summary = summary[:400] + "..."

    response = (
        f"Aapke case ke baare mein maine verified legal sources se jaankari nikali hai. "
        f"{summary} "
        f"Yeh information verified government sources se hai. "
        f"Kya aap complaint draft karna chahte hain ya aur jaankari chahiye?"
    )

    return response
