"""
voice/ — Speech provider integration.

Responsibilities:
  - STT via Sarvam Saaras v4 (22 Indic languages + English)
  - TTS via Sarvam Bulbul v3 (11 Indic languages + English)
  - Provider abstraction for easy swapping
  - Audio format handling

Modules:
  - providers/base.py    — Abstract STT/TTS interfaces
  - providers/sarvam.py  — Sarvam AI integration
  - stt.py               — High-level STT service
  - tts.py               — High-level TTS service
"""
