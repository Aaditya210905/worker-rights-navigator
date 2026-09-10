"""
assemblyai.py -- AssemblyAI Voice Agent WebSocket integration.

This module handles:
  - WebSocket connection to wss://agents.assemblyai.com/v1/ws
  - session.update with correct inline field structure
  - Sending input.audio (microphone PCM -> base64 -> WebSocket)
  - Receiving all events per the official events reference
  - session.end on clean shutdown
  - Barge-in detection (reply.done with status=interrupted)

Field reference (from official events-reference.md):
  session.update.session.system_prompt  -> string
  session.update.session.greeting       -> string
  session.update.session.output.voice   -> string  (NOT top-level voice)
  reply.audio.data                      -> base64 PCM16
  reply.done.status                     -> "completed" | "interrupted"
  transcript.agent.interrupted          -> bool
"""

import asyncio
import base64
import json

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

IMPORTANT LANGUAGE RULES:
- You ONLY speak Hindi, English, or Hinglish.
- Match the language used by the worker.
- If the worker mixes Hindi and English, respond in the same mixed style.
- If someone speaks in any other language, politely say: \
  "Main sirf Hindi aur English mein baat kar sakta hoon."
- NEVER respond in any language other than Hindi, English, or Hinglish.

When the worker describes a problem, acknowledge it empathetically \
and ask a single clarifying question to understand their situation better.

Do not give specific legal advice or cite specific laws yet. \
Simply listen, understand, and clarify.\
"""

GREETING = (
    "Namaste. Main WorkerSaathi hoon. "
    "Aap mujhe apni problem bata sakte hain."
)

# Valid voices: alba, anna, charles, estelle, eve, george, giovanni,
#               iris, jane, jean, juergen, lola, mary, michael, paul,
#               rafael, reid, vera
VOICE_ID = "arjun"


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
        self._session_id = None          # saved from session.ready for reconnection
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
                await self._send_session_update()

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

        Correct field structure per events-reference.md:
          - system_prompt : top-level in session
          - greeting      : top-level in session
          - output.voice  : nested under output (NOT top-level voice)
        """
        config = {
            "type": "session.update",
            "session": {
                "system_prompt": SYSTEM_PROMPT,
                "greeting": GREETING,
                "input": {
                    "language_codes": ["en", "hi"],
                },
                "output": {
                    "voice": VOICE_ID,
                },
            },
        }
        await self._ws.send(json.dumps(config))
        print("[agent] session.update sent.")

    async def _send_session_end(self):
        """
        Send session.end for clean teardown.
        Stops billing immediately instead of 30s grace window.
        """
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(json.dumps({"type": "session.end"}))
            except Exception:
                pass

    async def _send_loop(self, mic: Microphone):
        """
        Continuously reads from microphone and sends base64 PCM
        as input.audio events. Waits for session.ready first.
        """
        print("[agent] Waiting for session.ready...")
        await self._session_ready.wait()
        print("[agent] Microphone streaming started.")

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                pcm_data = await loop.run_in_executor(None, mic.read)
                audio_b64 = base64.b64encode(pcm_data).decode("ascii")
                await self._ws.send(json.dumps({
                    "type": "input.audio",
                    "audio": audio_b64,
                }))
            except Exception as e:
                if self._running:
                    print(f"[agent] Send error: {e}")
                break

    async def _receive_loop(self, speaker: Speaker):
        """Receives and dispatches all events from AssemblyAI."""
        try:
            async for raw_message in self._ws:
                if not self._running:
                    break

                event = json.loads(raw_message)
                event_type = event.get("type", "")

                # ── Session lifecycle ─────────────────────────────
                if event_type == "session.ready":
                    self._on_session_ready(event)

                elif event_type == "session.updated":
                    pass  # session.update accepted — no action needed

                elif event_type == "session.ended":
                    secs = event.get("session_duration_seconds", "?")
                    print(f"[agent] session.ended (duration: {secs}s)")
                    self._running = False
                    break

                # ── User speech ───────────────────────────────────
                elif event_type == "input.speech.started":
                    pass

                elif event_type == "input.speech.stopped":
                    pass

                elif event_type == "transcript.user.delta":
                    pass  # partial — wait for final transcript.user

                elif event_type == "transcript.user":
                    self._on_user_transcript(event)

                # ── Agent response ────────────────────────────────
                elif event_type == "reply.started":
                    pass

                elif event_type == "reply.audio":
                    self._on_reply_audio(event, speaker)

                elif event_type == "transcript.agent.delta":
                    pass  # partial — wait for final transcript.agent

                elif event_type == "transcript.agent":
                    self._on_agent_transcript(event, speaker)

                elif event_type == "reply.done":
                    self._on_reply_done(event, speaker)

                # ── Errors ────────────────────────────────────────
                elif event_type == "session.error":
                    self._on_session_error(event)

                # ── Unknown ───────────────────────────────────────
                else:
                    pass  # silently ignore unknown event types

        except websockets.exceptions.ConnectionClosed:
            print("[agent] WebSocket closed.")
        except Exception as e:
            print(f"[agent] Receive error: {e}")
        finally:
            self._running = False

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_session_ready(self, event):
        """Session established — save session_id and unblock mic loop."""
        self._session_id = event.get("session_id")
        print(f"[agent] Session ready! (id: {self._session_id})")
        print("=" * 50)
        print("  WorkerSaathi is listening.")
        print("  Speak into your microphone. Use headphones!")
        print("  Press Ctrl+C to stop.")
        print("=" * 50)
        self._session_ready.set()

    def _on_user_transcript(self, event):
        """Final transcript of the worker's utterance."""
        text = event.get("text", "")
        if text.strip():
            print(f"\n  You: {text}")

    def _on_reply_audio(self, event, speaker: Speaker):
        """Decode base64 PCM16 and play through speaker."""
        audio_b64 = event.get("data", "")
        if audio_b64:
            try:
                pcm_data = base64.b64decode(audio_b64)
                speaker.play(pcm_data)
            except Exception as e:
                print(f"[agent] Audio playback error: {e}")

    def _on_agent_transcript(self, event, speaker: Speaker):
        """
        Final transcript of the agent's reply.
        If interrupted=True, the worker cut in — flush speaker.
        """
        text = event.get("text", "")
        interrupted = event.get("interrupted", False)

        if text.strip():
            marker = " [interrupted]" if interrupted else ""
            print(f"\n  Agent: {text}{marker}")

        if interrupted:
            speaker.flush()

    def _on_reply_done(self, event, speaker: Speaker):
        """
        Reply finished. status = "completed" | "interrupted".
        Belt-and-suspenders flush alongside transcript.agent handler.
        """
        if event.get("status") == "interrupted":
            speaker.flush()

    def _on_session_error(self, event):
        """Log session errors with full context."""
        code = event.get("code", "unknown")
        message = event.get("message", "")
        param = event.get("param", "")
        detail = f"code={code}"
        if message:
            detail += f", message={message!r}"
        if param:
            detail += f", param={param!r}"
        print(f"\n  [session.error] {detail}")

    def stop(self):
        """Signal the agent to stop and send a clean session.end."""
        self._running = False
        if self._ws:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._send_session_end())
            except RuntimeError:
                pass
