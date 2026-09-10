"""
assemblyai.py -- AssemblyAI Voice Agent WebSocket integration.

This module handles:
  - WebSocket connection to wss://agents.assemblyai.com/v1/ws
  - session.update (system prompt, greeting, voice)
  - Sending input.audio (microphone PCM -> base64 -> WebSocket)
  - Receiving events (session.ready, transcript.*, reply.audio, reply.done)
  - Barge-in detection (reply.done with status=interrupted)

It does NOT handle:
  - Microphone / speaker hardware (that's audio.py)
  - Tools, RAG, case state (later phases)
"""

import asyncio
import base64
import json
import os

import websockets

from app.voice.audio import Microphone, Speaker

# ── Constants ────────────────────────────────────────────────────────────────

WS_URL = "wss://agents.assemblyai.com/v1/ws"

SYSTEM_PROMPT = """\
You are WorkerSaathi, a helpful voice assistant \
for informal and gig workers in India.

You are not a lawyer and do not provide legal advice.

Listen carefully to the worker's problem.
Ask one question at a time.
Keep spoken responses short and natural (1-3 sentences).
Speak in a warm, respectful tone.

You can speak Hindi, English, or Hinglish.
Match the language used by the worker.
If the worker mixes Hindi and English, respond in the same mixed style.

When the worker describes a problem, acknowledge it empathetically \
and ask a single clarifying question to understand their situation better.

Do not give specific legal advice or cite specific laws yet. \
Simply listen, understand, and clarify.\
"""

GREETING = (
    "Namaste. Main WorkerSaathi hoon. "
    "Aap mujhe apni problem bata sakte hain."
)

# AssemblyAI voice ID -- using a clear, natural-sounding voice
VOICE_ID = "Mark"


class AssemblyAIAgent:
    """
    Manages a single voice session with AssemblyAI's Voice Agent API.

    Lifecycle:
        agent = AssemblyAIAgent(api_key)
        await agent.run(mic, speaker)   # blocks until session ends
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY is required. "
                "Set it in your .env file."
            )
        self._api_key = api_key
        self._ws = None
        self._session_ready = asyncio.Event()
        self._running = False

    async def run(self, mic: Microphone, speaker: Speaker):
        """
        Main entry point. Opens WebSocket, configures session,
        then runs send/receive loops concurrently until stopped.
        """
        headers = {"Authorization": f"Bearer {self._api_key}"}

        print("[agent] Connecting to AssemblyAI Voice Agent API...")

        try:
            async with websockets.connect(
                WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                self._ws = ws
                self._running = True

                print("[agent] Connected. Sending session configuration...")

                # Step 1: Configure the session
                await self._send_session_update()

                # Step 2: Run send + receive concurrently
                # The mic loop waits for session.ready before streaming.
                await asyncio.gather(
                    self._receive_loop(speaker),
                    self._send_loop(mic),
                )

        except websockets.exceptions.ConnectionClosed as e:
            print(f"[agent] Connection closed: {e}")
        except Exception as e:
            print(f"[agent] Error: {e}")
        finally:
            self._running = False
            self._ws = None
            print("[agent] Session ended.")

    async def _send_session_update(self):
        """
        Send session.update as the first message.
        Configures: system prompt, greeting, voice.
        """
        config = {
            "type": "session.update",
            "session": {
                "system_prompt": SYSTEM_PROMPT,
                "greeting": GREETING,
                "input": {
                    "encoding": "pcm16",
                    "sample_rate": 24000,
                },
                "output": {
                    "encoding": "pcm16",
                    "sample_rate": 24000,
                    "voice": VOICE_ID,
                },
                "turn_detection": {
                    "silence_threshold": 500,
                },
            },
        }

        await self._ws.send(json.dumps(config))
        print("[agent] session.update sent.")

    async def _send_loop(self, mic: Microphone):
        """
        Continuously reads from the microphone and sends
        base64-encoded PCM to AssemblyAI as input.audio events.

        Waits for session.ready before starting.
        """
        # Don't send audio until the session is ready
        print("[agent] Waiting for session.ready...")
        await self._session_ready.wait()
        print("[agent] Microphone streaming started.")

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # PyAudio.read() blocks ~50ms, so run in a thread
                pcm_data = await loop.run_in_executor(None, mic.read)

                # Encode as base64 for JSON transport
                audio_b64 = base64.b64encode(pcm_data).decode("ascii")

                msg = json.dumps({
                    "type": "input.audio",
                    "audio": audio_b64,
                })

                await self._ws.send(msg)

            except Exception as e:
                if self._running:
                    print(f"[agent] Send error: {e}")
                break

    async def _receive_loop(self, speaker: Speaker):
        """
        Receives and dispatches all events from AssemblyAI.
        """
        try:
            async for raw_message in self._ws:
                if not self._running:
                    break

                event = json.loads(raw_message)
                event_type = event.get("type", "")

                # ── Session lifecycle ────────────────────────────────
                if event_type == "session.ready":
                    self._on_session_ready(event)

                # ── User speech ──────────────────────────────────────
                elif event_type == "input.speech.started":
                    pass  # user started talking

                elif event_type == "transcript.user":
                    self._on_user_transcript(event)

                # ── Agent response ───────────────────────────────────
                elif event_type == "reply.started":
                    pass  # agent is about to speak

                elif event_type == "reply.audio":
                    self._on_reply_audio(event, speaker)

                elif event_type == "transcript.agent":
                    self._on_agent_transcript(event)

                elif event_type == "reply.done":
                    self._on_reply_done(event, speaker)

                # ── Errors ───────────────────────────────────────────
                elif event_type == "session.error":
                    self._on_session_error(event)

                elif event_type == "session.end":
                    print("[agent] Session ended by server.")
                    self._running = False
                    break

                # ── Unknown ──────────────────────────────────────────
                else:
                    # Log unknown events during development
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("[agent] WebSocket closed.")
        except Exception as e:
            print(f"[agent] Receive error: {e}")
        finally:
            self._running = False

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_session_ready(self, event):
        """Session is configured and ready for audio."""
        print("[agent] Session ready!")
        print("=" * 50)
        print("  WorkerSaathi is listening.")
        print("  Speak into your microphone. Use headphones!")
        print("  Press Ctrl+C to stop.")
        print("=" * 50)
        self._session_ready.set()

    def _on_user_transcript(self, event):
        """Worker's speech has been transcribed."""
        text = event.get("text", "")
        if text.strip():
            print(f"\n  You: {text}")

    def _on_reply_audio(self, event, speaker: Speaker):
        """
        Agent audio chunk received.
        Decode from base64 and play through speaker.
        """
        audio_b64 = event.get("data", "") or event.get("audio", "")
        if audio_b64:
            try:
                pcm_data = base64.b64decode(audio_b64)
                speaker.play(pcm_data)
            except Exception as e:
                print(f"[agent] Audio playback error: {e}")

    def _on_agent_transcript(self, event):
        """Agent's spoken response transcribed."""
        text = event.get("text", "")
        if text.strip():
            print(f"\n  Agent: {text}")

    def _on_reply_done(self, event, speaker: Speaker):
        """
        Agent finished a reply.

        If status is 'interrupted', the worker barged in --
        flush any remaining speaker audio so it doesn't overlap.
        """
        status = event.get("status", "")
        if status == "interrupted":
            print("  [interrupted]")
            speaker.flush()

    def _on_session_error(self, event):
        """AssemblyAI reported an error."""
        error = event.get("error", {})
        msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        print(f"\n  [ERROR] {msg}")

    def stop(self):
        """Signal the agent to stop gracefully."""
        self._running = False
