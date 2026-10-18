"""
sarvam.py — Sarvam AI speech provider.

Integrates Sarvam Saaras v4 for STT (22 Indic languages + English)
and Bulbul v3 for TTS (10 Indic languages + English).

API docs: https://docs.sarvam.ai/
"""

import asyncio
import base64
import io
import os
from typing import Optional

from app.voice.providers.base import (
    BaseSTTProvider, BaseTTSProvider,
    STTResult, TTSResult, LanguageInfo,
)


# ── Language registry ────────────────────────────────────────────────────────

SARVAM_LANGUAGES = [
    LanguageInfo("hi-IN", "Hindi", "हिन्दी", True, True),
    LanguageInfo("en-IN", "English (India)", "English", True, True),
    LanguageInfo("bn-IN", "Bengali", "বাংলা", True, True),
    LanguageInfo("ta-IN", "Tamil", "தமிழ்", True, True),
    LanguageInfo("te-IN", "Telugu", "తెలుగు", True, True),
    LanguageInfo("mr-IN", "Marathi", "मराठी", True, True),
    LanguageInfo("gu-IN", "Gujarati", "ગુજરાતી", True, True),
    LanguageInfo("kn-IN", "Kannada", "ಕನ್ನಡ", True, True),
    LanguageInfo("ml-IN", "Malayalam", "മലയാളം", True, True),
    LanguageInfo("pa-IN", "Punjabi", "ਪੰਜਾਬੀ", True, True),
    LanguageInfo("od-IN", "Odia", "ଓଡ଼ିଆ", True, True),
    # STT-only languages (Saaras v4 supports 22 languages, Bulbul v3 has 11)
    LanguageInfo("as-IN", "Assamese", "অসমীয়া", True, False),
    LanguageInfo("ur-IN", "Urdu", "اردو", True, False),
    LanguageInfo("ne-IN", "Nepali", "नेपाली", True, False),
    LanguageInfo("sa-IN", "Sanskrit", "संस्कृतम्", True, False),
    LanguageInfo("sd-IN", "Sindhi", "سنڌي", True, False),
    LanguageInfo("kok-IN", "Konkani", "कोंकणी", True, False),
    LanguageInfo("doi-IN", "Dogri", "डोगरी", True, False),
    LanguageInfo("mni-IN", "Manipuri", "মৈতৈলোন্", True, False),
    LanguageInfo("brx-IN", "Bodo", "बर'", True, False),
    LanguageInfo("sat-IN", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", True, False),
    LanguageInfo("ks-IN", "Kashmiri", "كٲشُر", True, False),
    LanguageInfo("mai-IN", "Maithili", "मैथिली", True, False),
]

# Default speakers per language for TTS
DEFAULT_SPEAKERS = {
    "hi-IN": "ritu",
    "en-IN": "simran",
    "bn-IN": "roopa",
    "ta-IN": "gokul",
    "te-IN": "kavitha",
    "mr-IN": "mrunal",
    "gu-IN": "pooja",
    "kn-IN": "chaitra",
    "ml-IN": "ritu",
    "pa-IN": "anand",
    "od-IN": "ritu",
}

# Speakers available for Hindi/general use (Bulbul v3)
AVAILABLE_SPEAKERS = [
    "ritu", "shubh", "priya", "aditya", "rohan",
    "simran", "kavya", "neha", "rahul", "dev",
    "ishita", "amit", "pooja", "shreya", "advait",
]

# STT modes
STT_MODES = {
    "transcribe": "Standard transcription in source language",
    "translate": "Translate speech to English text",
    "codemix": "Handle Hindi-English code-mixed speech (Hinglish)",
    "verbatim": "Exact word-for-word transcription",
    "translit": "Romanized output (Devanagari → Latin script)",
}


class SarvamSTT(BaseSTTProvider):
    """
    Sarvam Saaras v4 speech-to-text.

    Supports 22 Indian languages + English with code-mixed output,
    keyterm prompting, and auto language detection.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key or os.environ.get("SARVAM_API_KEY", "")
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Sarvam client."""
        if self._client is None:
            from sarvamai import SarvamAI
            self._client = SarvamAI(api_subscription_key=self._api_key)
        return self._client

    async def transcribe(
        self,
        audio_data: bytes,
        language_code: str = "auto",
        mode: str = "transcribe",
    ) -> STTResult:
        """
        Transcribe audio using Sarvam Saaras v4.

        The SDK is synchronous, so we run it in a thread executor
        to avoid blocking the async event loop.
        """
        if not self._api_key:
            return STTResult(
                transcript="",
                error="SARVAM_API_KEY not configured. Set it in your .env file.",
                provider="sarvam",
            )

        # Validate mode
        if mode not in STT_MODES:
            mode = "transcribe"

        # Map "auto" to "unknown" for Sarvam
        lang = language_code if language_code != "auto" else "unknown"

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._do_transcribe,
                audio_data, lang, mode,
            )
            return result
        except Exception as e:
            return STTResult(
                transcript="",
                error=f"Sarvam STT error: {str(e)}",
                provider="sarvam",
            )

    def _do_transcribe(
        self, audio_data: bytes, language_code: str, mode: str
    ) -> STTResult:
        """Synchronous transcription call (runs in executor)."""
        client = self._get_client()

        # Wrap bytes in a file-like object
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "recording.wav"

        # WorkerSaathi-specific keyterms to improve recognition accuracy
        keyterms = [
            "WorkerSaathi", "Swiggy", "Zomato", "Uber", "Ola", "Rapido",
            "Urban Company", "Blinkit", "Zepto", "Dunzo",
            "e-Shram", "ESIC", "PF", "EPF",
            "Labour Commissioner", "DLSA",
            "gig worker", "delivery partner",
        ]

        response = client.speech_to_text.transcribe(
            file=audio_file,
            model="saaras:v4",
            mode=mode,
            language_code=language_code,
            keyterms=keyterms,
        )

        transcript = getattr(response, "transcript", "")
        detected_lang = getattr(response, "language_code", language_code)

        return STTResult(
            transcript=transcript or "",
            language_code=detected_lang or language_code,
            confidence=1.0,
            provider="sarvam-saaras-v4",
        )

    def get_supported_languages(self) -> list[LanguageInfo]:
        return [lang for lang in SARVAM_LANGUAGES if lang.stt_supported]


class SarvamTTS(BaseTTSProvider):
    """
    Sarvam Bulbul v3 text-to-speech.

    Supports 10 Indian languages + English with multiple
    voice personas, adjustable pace, and expression control.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key or os.environ.get("SARVAM_API_KEY", "")
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Sarvam client."""
        if self._client is None:
            from sarvamai import SarvamAI
            self._client = SarvamAI(api_subscription_key=self._api_key)
        return self._client

    async def synthesize(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: str = "meera",
        pace: float = 1.0,
    ) -> TTSResult:
        """
        Convert text to speech using Sarvam Bulbul v3.

        Runs synchronous SDK in a thread executor.
        """
        if not self._api_key:
            return TTSResult(
                error="SARVAM_API_KEY not configured. Set it in your .env file.",
                provider="sarvam",
            )

        if not text or not text.strip():
            return TTSResult(
                error="Empty text provided for TTS.",
                provider="sarvam",
            )

        # Validate language — fall back to Hindi if TTS doesn't support it
        tts_langs = {l.code for l in SARVAM_LANGUAGES if l.tts_supported}
        if language_code not in tts_langs:
            language_code = "hi-IN"

        # Use default speaker for the language if not specified
        if speaker not in AVAILABLE_SPEAKERS:
            speaker = DEFAULT_SPEAKERS.get(language_code, "meera")

        # Clamp pace
        pace = max(0.5, min(2.0, pace))

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._do_synthesize,
                text, language_code, speaker, pace,
            )
            return result
        except Exception as e:
            return TTSResult(
                error=f"Sarvam TTS error: {str(e)}",
                provider="sarvam",
            )

    def _do_synthesize(
        self, text: str, language_code: str, speaker: str, pace: float
    ) -> TTSResult:
        """Synchronous TTS call (runs in executor)."""
        client = self._get_client()

        response = client.text_to_speech.convert(
            text=text,
            language_code=language_code,
            model="bulbul:v3",
            speaker=speaker,
            pace=pace,
            speech_sample_rate=22050,
        )

        # Response contains base64-encoded audio chunks
        audios = getattr(response, "audios", [])
        if not audios:
            return TTSResult(
                error="Sarvam TTS returned no audio.",
                provider="sarvam-bulbul-v3",
            )

        # Decode first audio chunk
        audio_b64 = audios[0]
        audio_bytes = base64.b64decode(audio_b64)

        return TTSResult(
            audio_base64=audio_b64,
            audio_bytes=audio_bytes,
            content_type="audio/wav",
            sample_rate=24000,
            provider="sarvam-bulbul-v3",
        )

    def get_supported_languages(self) -> list[LanguageInfo]:
        return [lang for lang in SARVAM_LANGUAGES if lang.tts_supported]

    def get_available_speakers(self, language_code: str = "hi-IN") -> list[str]:
        return AVAILABLE_SPEAKERS
