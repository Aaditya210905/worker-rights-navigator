"""
tts.py — Text-to-speech service.

High-level TTS service used by API routes. Manages the active
provider and handles language/speaker selection.
"""

from typing import Optional
from app.voice.providers.base import BaseTTSProvider, TTSResult, LanguageInfo
from app.voice.providers.sarvam import SarvamTTS


class TTSService:
    """
    Text-to-speech service for WorkerSaathi.

    Uses Sarvam Bulbul v3 as the primary provider.
    """

    def __init__(self, api_key: str = None):
        self._primary: BaseTTSProvider = SarvamTTS(api_key=api_key)

    async def synthesize(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: str = "meera",
        pace: float = 1.0,
    ) -> TTSResult:
        """
        Convert text to speech audio.

        Args:
            text: Text to speak
            language_code: BCP-47 target language code
            speaker: Voice persona name
            pace: Speed multiplier (0.5 to 2.0)

        Returns:
            TTSResult with audio data and metadata
        """
        if not text or not text.strip():
            return TTSResult(
                error="Empty text provided.",
                provider="service",
            )

        # Truncate very long texts to avoid API limits
        # Sarvam TTS works best with shorter segments
        max_chars = 500
        if len(text) > max_chars:
            # Split at the last sentence boundary within limit
            truncated = text[:max_chars]
            last_period = max(
                truncated.rfind('.'),
                truncated.rfind('।'),  # Hindi full stop
                truncated.rfind('!'),
                truncated.rfind('?'),
            )
            if last_period > max_chars // 2:
                text = truncated[:last_period + 1]
            else:
                text = truncated + "..."

        result = await self._primary.synthesize(text, language_code, speaker, pace)

        if result.is_success:
            size_kb = len(result.audio_bytes) / 1024
            print(f"  [tts] Synthesized ({result.provider}): {size_kb:.1f}KB audio")
        else:
            print(f"  [tts] Error ({result.provider}): {result.error}")

        return result

    def get_supported_languages(self) -> list[LanguageInfo]:
        """Return all languages supported for TTS."""
        return self._primary.get_supported_languages()

    def get_available_speakers(self, language_code: str = "hi-IN") -> list[str]:
        """Return available speakers for a language."""
        return self._primary.get_available_speakers(language_code)


# Module-level singleton — lazy-initialized from config
_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton."""
    global _service
    if _service is None:
        from app.config import settings
        _service = TTSService(api_key=settings.sarvam_api_key)
    return _service
