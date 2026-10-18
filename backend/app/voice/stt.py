"""
stt.py — Speech-to-text service.

High-level STT service used by API routes. Manages the active
provider and handles fallback logic.
"""

from typing import Optional
from app.voice.providers.base import BaseSTTProvider, STTResult, LanguageInfo
from app.voice.providers.sarvam import SarvamSTT


class STTService:
    """
    Speech-to-text service for WorkerSaathi.

    Uses Sarvam Saaras v4 as the primary provider.
    Designed for easy provider swapping if needed.
    """

    def __init__(self, api_key: str = None):
        self._primary: BaseSTTProvider = SarvamSTT(api_key=api_key)

    async def transcribe(
        self,
        audio_data: bytes,
        language_code: str = "auto",
        mode: str = "transcribe",
    ) -> STTResult:
        """
        Transcribe audio to text using the active provider.

        Args:
            audio_data: Raw audio bytes (WAV format preferred)
            language_code: BCP-47 code or "auto" for detection
            mode: transcribe | translate | codemix | verbatim

        Returns:
            STTResult with transcript and metadata
        """
        if not audio_data or len(audio_data) < 100:
            return STTResult(
                transcript="",
                error="Audio data too short or empty.",
                provider="service",
            )

        result = await self._primary.transcribe(audio_data, language_code, mode)

        if result.is_success:
            print(f"  [stt] Transcribed ({result.provider}): {result.transcript[:80]}")
        else:
            print(f"  [stt] Error ({result.provider}): {result.error}")

        return result

    def get_supported_languages(self) -> list[LanguageInfo]:
        """Return all languages supported for STT."""
        return self._primary.get_supported_languages()


# Module-level singleton — lazy-initialized from config
_service: Optional[STTService] = None


def get_stt_service() -> STTService:
    """Get or create the STT service singleton."""
    global _service
    if _service is None:
        from app.config import settings
        _service = STTService(api_key=settings.sarvam_api_key)
    return _service
