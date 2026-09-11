"""
assemblyai.py -- AssemblyAI Voice Agent WebSocket integration.

Phase 2: Uses LLM tool calling for case classification.
The LLM calls update_case_info whenever it identifies information
from the worker's speech. We process the tool call, update case
state, and send tool.result back.

Event flow for tool calls (from events-reference.md):
  1. LLM decides to call a tool
  2. Server sends tool.call with arguments
  3. Server sends reply.done (tool call reply)
  4. We send tool.result with the result
  5. LLM generates a response using the result
  6. Server sends reply.started, reply.audio, reply.done

Field reference:
  session.update.session.tools           -> array   (tool definitions)
  session.update.session.system_prompt   -> string  (MUTABLE mid-session)
  session.update.session.greeting        -> string  (IMMUTABLE after first)
  session.update.session.output.voice    -> string  (IMMUTABLE after first)
"""

import asyncio
import base64
import json

import websockets

from app.voice.audio import Microphone, Speaker
from app.agent.conversation import ConversationController
from app.agent.classifier import CASE_TOOLS

# ── Constants ────────────────────────────────────────────────────────────────

WS_URL = "wss://agents.assemblyai.com/v1/ws"

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

    Phase 2: Uses LLM tool calling for intelligent case classification.
    The LLM calls update_case_info to extract structured case data,
    and we guide its next question via tool results and prompt updates.
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY is required. "
                "Set it in your .env file."
            )
        self._api_key = api_key
        self._ws = None
        self._session_id = None
        self._session_ready = asyncio.Event()
        self._running = False
        self._controller = ConversationController()
        self._pending_tool_calls = []  # accumulate tool.call events

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

    async def _send_session_update(self, system_prompt: str = None):
        """
        Send session.update.

        On first call: sends full config (prompt, greeting, voice, language, tools).
        On subsequent calls: sends only the updated system_prompt (mutable).
        """
        if system_prompt is None:
            # First call — full configuration including tools
            initial_prompt = self._controller.get_initial_prompt()
            config = {
                "type": "session.update",
                "session": {
                    "system_prompt": initial_prompt,
                    "greeting": GREETING,
                    "input": {
                        "language_codes": ["en", "hi"],
                    },
                    "output": {
                        "voice": VOICE_ID,
                    },
                    "tools": CASE_TOOLS,
                },
            }
            await self._ws.send(json.dumps(config))
            print("[agent] session.update sent (initial with tools).")
        else:
            # Subsequent call — only update system_prompt (mutable)
            config = {
                "type": "session.update",
                "session": {
                    "system_prompt": system_prompt,
                },
            }
            await self._ws.send(json.dumps(config))

    async def _send_tool_result(self, call_id: str, result: str, is_error: bool = False):
        """Send tool.result back to the LLM."""
        msg = {
            "type": "tool.result",
            "call_id": call_id,
            "result": result,
            "is_error": is_error,
        }
        await self._ws.send(json.dumps(msg))

    async def _send_session_end(self):
        """Send session.end for clean teardown."""
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
                    pass  # accepted

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
                    pass

                elif event_type == "transcript.user":
                    self._on_user_transcript(event)

                # ── Agent response ────────────────────────────────
                elif event_type == "reply.started":
                    pass

                elif event_type == "reply.audio":
                    self._on_reply_audio(event, speaker)

                elif event_type == "transcript.agent.delta":
                    pass

                elif event_type == "transcript.agent":
                    self._on_agent_transcript(event, speaker)

                elif event_type == "reply.done":
                    await self._on_reply_done(event, speaker)

                # ── Tool calls ────────────────────────────────────
                elif event_type == "tool.call":
                    self._on_tool_call(event)

                # ── Errors ────────────────────────────────────────
                elif event_type == "session.error":
                    self._on_session_error(event)

                else:
                    pass

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
        """Final transcript — log it and track in controller."""
        text = event.get("text", "")
        if text.strip():
            print(f"\n  You: {text}")
            self._controller.process_transcript(text)

    def _on_tool_call(self, event):
        """
        LLM wants to call a tool. Accumulate it — we process
        all pending tool calls when reply.done arrives.
        """
        call_id = event.get("call_id", "")
        name = event.get("name", "")
        arguments = event.get("arguments", {})

        print(f"\n  [tool.call] {name}({json.dumps(arguments, ensure_ascii=False)})")
        self._pending_tool_calls.append({
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        })

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
        """Final transcript of the agent's reply."""
        text = event.get("text", "")
        interrupted = event.get("interrupted", False)

        if text.strip():
            marker = " [interrupted]" if interrupted else ""
            print(f"\n  Agent: {text}{marker}")

        if interrupted:
            speaker.flush()

    async def _on_reply_done(self, event, speaker: Speaker):
        """
        Reply finished.

        If there are pending tool calls, process them and send results.
        On interruption, flush audio and discard pending tool calls.
        """
        status = event.get("status", "completed")

        if status == "interrupted":
            speaker.flush()
            self._pending_tool_calls.clear()
            return

        # Process any pending tool calls
        if self._pending_tool_calls:
            for tc in self._pending_tool_calls:
                result = self._controller.process_tool_call(
                    tc["name"], tc["arguments"]
                )

                # Send tool.result back to the LLM
                await self._send_tool_result(tc["call_id"], result["tool_result"])

                # Update system prompt if case state changed
                if result["needs_prompt_update"] and result["new_prompt"]:
                    await self._send_session_update(result["new_prompt"])

            self._pending_tool_calls.clear()

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
