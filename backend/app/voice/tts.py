"""
tts.py — Text-to-speech service.

High-level TTS service used by API routes. Manages the active
provider and handles language/speaker selection.
"""

from typing import Optional
import base64
import io
import re
import wave
from app.voice.providers.base import BaseTTSProvider, TTSResult, LanguageInfo
from app.voice.providers.sarvam import SarvamTTS


# Voice cut-off fix: chunk + stitch instead of truncating at 500 chars.
SARVAM_HARD_LIMIT = 2400
CHUNK_TARGET = 450
MAX_SPOKEN_CHARS = 2400


def clean_text_for_tts(text: str) -> str:
    """Strip markdown that sounds bad when spoken."""
    if not text:
        return ""
    t = text.replace("**", "").replace("__", "")
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"^\s*[-*\u2022]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def split_into_chunks(text: str, max_chars: int = CHUNK_TARGET) -> list[str]:
    """Split text into sentence-safe chunks of <= max_chars."""
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[\u0964.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        while len(sent) > max_chars:
            cut = max(
                sent.rfind(",", 0, max_chars),
                sent.rfind(";", 0, max_chars),
                sent.rfind(":", 0, max_chars),
                sent.rfind(" ", 0, max_chars),
            )
            if cut < max_chars // 2:
                cut = max_chars
            piece = sent[:cut].strip(" ,;:\u2014")
            if current and len(current) + 1 + len(piece) <= max_chars:
                current = f"{current} {piece}"
            else:
                if current:
                    chunks.append(current)
                current = piece
            sent = sent[cut:].strip(" ,;:\u2014")
        if not current:
            current = sent
        elif len(current) + 1 + len(sent) <= max_chars:
            current = f"{current} {sent}"
        else:
            chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def stitch_wav_bytes(wav_list: list[bytes]) -> bytes:
    """Concatenate WAV files (same format) into one WAV."""
    if not wav_list:
        return b""
    if len(wav_list) == 1:
        return wav_list[0]
    try:
        params = None
        all_frames = b""
        for w in wav_list:
            with wave.open(io.BytesIO(w), "rb") as wf:
                if params is None:
                    params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
                all_frames += wf.readframes(wf.getnframes())
        nchannels, sampwidth, framerate = params
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(nchannels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            wf.writeframes(all_frames)
        return out.getvalue()
    except Exception as e:
        print(f"  [tts] WAV stitch failed ({e}) - returning first chunk")
        return wav_list[0]


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

        cleaned = clean_text_for_tts(text)
        was_trimmed = False
        if len(cleaned) > MAX_SPOKEN_CHARS:
            head = cleaned[:MAX_SPOKEN_CHARS]
            cut = max(head.rfind("\u0964"), head.rfind("."), head.rfind("!"), head.rfind("?"))
            if cut > MAX_SPOKEN_CHARS // 2:
                head = head[: cut + 1]
            cleaned = head + " Poori jaankari screen par uplabdh hai."
            was_trimmed = True

        chunks = split_into_chunks(cleaned, CHUNK_TARGET)
        print(f"  [tts] Speaking {len(cleaned)} chars in {len(chunks)} chunk(s)"
              + (" (trimmed; full text on screen)" if was_trimmed else ""))

        wav_parts: list[bytes] = []
        last_error: Optional[str] = None
        for i, chunk in enumerate(chunks):
            result = await self._primary.synthesize(chunk, language_code, speaker, pace)
            if result.is_success and result.audio_bytes:
                wav_parts.append(result.audio_bytes)
            else:
                last_error = result.error
                print(f"  [tts] Chunk {i + 1}/{len(chunks)} failed: {result.error}")

        if not wav_parts:
            return TTSResult(
                error=last_error or "Sarvam TTS returned no audio.",
                provider="sarvam-bulbul-v3",
            )

        combined_wav = stitch_wav_bytes(wav_parts)
        combined_b64 = base64.b64encode(combined_wav).decode("ascii")
        size_kb = len(combined_wav) / 1024
        print(f"  [tts] Synthesized (sarvam-bulbul-v3): {size_kb:.1f}KB ({len(chunks)} chunks)")
        return TTSResult(
            audio_base64=combined_b64,
            audio_bytes=combined_wav,
            content_type="audio/wav",
            sample_rate=22050,
            provider="sarvam-bulbul-v3",
        )

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
