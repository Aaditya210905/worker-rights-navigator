"""
ws.py -- WebSocket proxy for browser-based voice via AssemblyAI.

Browser connects to /api/v1/voice/{session_id}
Backend proxies audio to/from AssemblyAI, intercepting tool.call
events to execute them via the session's Orchestrator.

Flow:
  Browser  <-->  FastAPI WebSocket  <-->  AssemblyAI WebSocket
                       |
                  Orchestrator
                  (tool calls)
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import websockets

from app.api.session import session_manager
from app.agent.tool_registry import ALL_TOOLS, get_tools_for_status
from app.agent.prompts import build_system_prompt
from app.config import settings

router = APIRouter(tags=["Voice WebSocket"])

AAI_WS_URL = "wss://agents.assemblyai.com/v1/ws"

GREETING = (
    "Namaste. Main WorkerSaathi hoon. "
    "Aap mujhe apni problem bata sakte hain."
)

VOICE_ID = "arjun"


@router.websocket("/voice/{session_id}")
async def voice_proxy(ws: WebSocket, session_id: str):
    """
    WebSocket proxy between a browser client and AssemblyAI Voice Agent.

    Protocol (browser → backend):
      - { "type": "input.audio", "audio": "<base64 PCM>" }
      - { "type": "session.end" }

    Protocol (backend → browser):
      - All AssemblyAI events are forwarded as-is
      - Tool calls are intercepted and resolved server-side

    The backend keeps the AssemblyAI API key private and controls
    all tool execution through the Orchestrator.
    """
    # Validate session
    session = session_manager.get_session(session_id)
    if session is None:
        await ws.close(code=4004, reason="Session not found or expired")
        return

    await ws.accept()

    api_key = settings.assemblyai_api_key
    if not api_key or api_key == "your_key_here":
        await ws.send_json({"type": "error", "message": "AssemblyAI API key not configured"})
        await ws.close(code=4001)
        return

    orch = session.orchestrator
    pending_tool_calls: list[dict] = []

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with websockets.connect(
            AAI_WS_URL,
            additional_headers=headers,
            ping_interval=30,
            ping_timeout=60,
        ) as aai_ws:

            # Send initial session configuration
            initial_prompt = orch.get_initial_prompt()
            config = {
                "type": "session.update",
                "session": {
                    "system_prompt": initial_prompt,
                    "greeting": GREETING,
                    "input": {"language_codes": ["en", "hi"]},
                    "output": {"voice": VOICE_ID},
                    "tools": ALL_TOOLS,
                },
            }
            await aai_ws.send(json.dumps(config))

            async def browser_to_aai():
                """Forward browser audio/control messages to AssemblyAI."""
                try:
                    while True:
                        data = await ws.receive_text()
                        msg = json.loads(data)
                        msg_type = msg.get("type", "")

                        # Forward audio and session control directly
                        if msg_type in ("input.audio", "session.end"):
                            await aai_ws.send(data)
                        if msg_type == "session.end":
                            break
                except WebSocketDisconnect:
                    try:
                        await aai_ws.send(json.dumps({"type": "session.end"}))
                    except Exception:
                        pass

            async def aai_to_browser():
                """
                Forward AssemblyAI events to browser.
                Intercept tool.call events to run them server-side.
                """
                nonlocal pending_tool_calls
                try:
                    async for raw in aai_ws:
                        event = json.loads(raw)
                        event_type = event.get("type", "")

                        # Debug: log all non-audio events
                        if event_type != "reply.audio":
                            print(f"  [ws] Event: {event_type} -> {json.dumps(event, ensure_ascii=False)[:300]}")

                        # Track user transcripts
                        if event_type == "transcript.user":
                            text = event.get("text", "")
                            if text.strip():
                                orch.process_transcript(text)

                        # Track agent final transcripts
                        if event_type == "transcript.agent":
                            text = event.get("text", "")
                            if text.strip():
                                orch.process_agent_transcript(text)

                        # Accumulate tool calls
                        if event_type == "tool.call":
                            # AssemblyAI sends arguments as a JSON string
                            raw_args = event.get("arguments", {})
                            if isinstance(raw_args, str):
                                try:
                                    raw_args = json.loads(raw_args)
                                except json.JSONDecodeError:
                                    raw_args = {}

                            pending_tool_calls.append({
                                "call_id": event.get("call_id", ""),
                                "name": event.get("name", ""),
                                "arguments": raw_args,
                            })

                        # On reply.done, process tool calls server-side
                        if event_type == "reply.done":
                            status = event.get("status", "completed")

                            if status == "interrupted":
                                pending_tool_calls.clear()
                            elif pending_tool_calls:
                                for tc in pending_tool_calls:
                                    print(f"  [ws] Executing tool: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)[:100]})")

                                    # Run in executor to avoid blocking async loop (RAG can take seconds)
                                    import asyncio
                                    loop = asyncio.get_event_loop()
                                    result = await loop.run_in_executor(
                                        None,
                                        orch.handle_tool_call,
                                        tc["name"], tc["arguments"]
                                    )
                                    print(f"  [ws] Tool {tc['name']} completed")

                                    is_error = False
                                    try:
                                        parsed = json.loads(result["tool_result"])
                                        is_error = parsed.get("status") == "error"
                                    except (json.JSONDecodeError, KeyError):
                                        pass

                                    # Send tool.result to AssemblyAI
                                    tool_result_msg = {
                                        "type": "tool.result",
                                        "call_id": tc["call_id"],
                                        "result": result["tool_result"],
                                        "is_error": is_error,
                                    }
                                    await aai_ws.send(json.dumps(tool_result_msg))

                                    # Update session prompt if needed
                                    if result["needs_prompt_update"] and result["new_prompt"]:
                                        case_status = orch.case.status.value
                                        update_msg = {
                                            "type": "session.update",
                                            "session": {
                                                "system_prompt": result["new_prompt"],
                                                "tools": get_tools_for_status(case_status),
                                            },
                                        }
                                        await aai_ws.send(json.dumps(update_msg))

                                pending_tool_calls.clear()

                        # Forward everything to the browser
                        await ws.send_text(raw)

                        if event_type == "session.ended":
                            break

                except websockets.exceptions.ConnectionClosed:
                    pass

            # Run both directions concurrently
            await asyncio.gather(
                browser_to_aai(),
                aai_to_browser(),
            )

    except websockets.exceptions.InvalidStatusCode as e:
        await ws.send_json({
            "type": "error",
            "message": f"Failed to connect to AssemblyAI: {e}",
        })
    except Exception as e:
        try:
            await ws.send_json({
                "type": "error",
                "message": f"Voice proxy error: {str(e)}",
            })
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
