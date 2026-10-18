"""
base.py — Abstract base classes for speech providers.

All STT/TTS providers implement these interfaces so the
rest of the app stays provider-agnostic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class STTResult:
    """Result from a speech-to-text transcription."""
    transcript: str
    language_code: str = ""
    confidence: float = 0.0
    provider: str = ""
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None and bool(self.transcript.strip())


@dataclass
class TTSResult:
    """Result from a text-to-speech synthesis."""
    audio_base64: str = ""
    audio_bytes: bytes = b""
    content_type: str = "audio/wav"
    sample_rate: int = 24000
    provider: str = ""
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None and (bool(self.audio_base64) or bool(self.audio_bytes))


@dataclass
class LanguageInfo:
    """Metadata about a supported language."""
    code: str           # e.g. "hi-IN"
    name: str           # e.g. "Hindi"
    native_name: str    # e.g. "हिन्दी"
    stt_supported: bool = True
    tts_supported: bool = True


# ── Abstract providers ───────────────────────────────────────────────────────

class BaseSTTProvider(ABC):
    """Abstract speech-to-text provider."""

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language_code: str = "auto",
        mode: str = "transcribe",
    ) -> STTResult:
        """
        Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio bytes (WAV, MP3, etc.)
            language_code: BCP-47 language code or "auto" for detection
            mode: transcribe | translate | codemix | verbatim

        Returns:
            STTResult with transcript and metadata
        """
        ...

    @abstractmethod
    def get_supported_languages(self) -> list[LanguageInfo]:
        """Return list of supported languages for STT."""
        ...


class BaseTTSProvider(ABC):
    """Abstract text-to-speech provider."""

    @abstractmethod
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
            TTSResult with audio data
        """
        ...

    @abstractmethod
    def get_supported_languages(self) -> list[LanguageInfo]:
        """Return list of supported languages for TTS."""
        ...

    @abstractmethod
    def get_available_speakers(self, language_code: str = "hi-IN") -> list[str]:
        """Return list of speaker names for a language."""
        ...
