"""
audio.py -- Microphone capture and speaker playback using PyAudio.

This module knows NOTHING about WorkerSaathi, AssemblyAI, or WebSockets.
It only deals with:
  - Reading PCM audio from the microphone
  - Writing PCM audio to the speakers

Audio format (AssemblyAI Voice Agent default):
  - Sample rate : 24,000 Hz
  - Channels    : 1 (mono)
  - Format      : PCM 16-bit signed little-endian
  - Chunk size  : ~50 ms  =  1,200 samples  =  2,400 bytes
"""

import pyaudio
import threading

# ── Audio constants ──────────────────────────────────────────────────────────

SAMPLE_RATE = 24_000          # 24 kHz
CHANNELS = 1                  # mono
FORMAT = pyaudio.paInt16      # 16-bit signed
BYTES_PER_SAMPLE = 2          # 16 bits = 2 bytes
CHUNK_SAMPLES = 1_200         # ~50 ms at 24 kHz
CHUNK_BYTES = CHUNK_SAMPLES * BYTES_PER_SAMPLE  # 2,400 bytes


class Microphone:
    """
    Captures PCM audio from the default input device.

    Usage:
        mic = Microphone()
        mic.open()
        chunk = mic.read()   # returns bytes (PCM16, 24kHz, mono)
        mic.close()
    """

    def __init__(self, rate=SAMPLE_RATE, channels=CHANNELS,
                 fmt=FORMAT, chunk_samples=CHUNK_SAMPLES):
        self._rate = rate
        self._channels = channels
        self._format = fmt
        self._chunk = chunk_samples
        self._pa = None
        self._stream = None

    def open(self):
        """Open the microphone stream."""
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=self._format,
            channels=self._channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
        )
        return self

    def read(self) -> bytes:
        """
        Read one chunk of PCM audio from the microphone.
        Returns raw bytes (PCM16, little-endian).
        Blocks until the chunk is ready (~50 ms).
        """
        if self._stream is None:
            raise RuntimeError("Microphone not opened. Call open() first.")
        return self._stream.read(self._chunk, exception_on_overflow=False)

    def close(self):
        """Release the microphone."""
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()


class Speaker:
    """
    Plays PCM audio through the default output device.

    Handles barge-in by flushing queued audio when flush() is called.

    Usage:
        spk = Speaker()
        spk.open()
        spk.play(pcm_bytes)   # non-blocking, queues for playback
        spk.flush()           # discard remaining audio (barge-in)
        spk.close()
    """

    def __init__(self, rate=SAMPLE_RATE, channels=CHANNELS,
                 fmt=FORMAT, chunk_samples=CHUNK_SAMPLES):
        self._rate = rate
        self._channels = channels
        self._format = fmt
        self._chunk = chunk_samples
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()

    def open(self):
        """Open the speaker stream."""
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=self._format,
            channels=self._channels,
            rate=self._rate,
            output=True,
            frames_per_buffer=self._chunk,
        )
        return self

    def play(self, pcm_data: bytes):
        """
        Write PCM audio to the speaker.
        Thread-safe: multiple callers won't corrupt the stream.
        """
        if self._stream is None:
            return
        with self._lock:
            try:
                self._stream.write(pcm_data)
            except Exception:
                pass  # stream may be closed during flush

    def flush(self):
        """
        Discard any buffered audio and reset the stream.
        Call this on barge-in (reply.done with status=interrupted).
        """
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.start_stream()
                except Exception:
                    pass

    def close(self):
        """Release the speaker."""
        with self._lock:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()
