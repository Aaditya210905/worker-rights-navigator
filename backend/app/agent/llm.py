"""
llm.py -- LLM client for WorkerSaathi agent reasoning.

Uses the OpenAI SDK with a configurable base_url so it works with any
OpenAI-compatible provider. Default: Groq (fast, free tier).

Configure via .env:
    LLM_API_KEY     = your provider key  (required)
    LLM_BASE_URL    = https://api.groq.com/openai/v1  (default)
    LLM_MODEL       = llama-3.1-8b-instant             (default)

Swap to OpenAI:
    LLM_BASE_URL    = https://api.openai.com/v1
    LLM_MODEL       = gpt-4o-mini

Swap to local Ollama:
    LLM_BASE_URL    = http://localhost:11434/v1
    LLM_API_KEY     = ollama
    LLM_MODEL       = llama3.2
"""

import json
import asyncio
from typing import Optional
from openai import AsyncOpenAI

from app.config import settings


# ── Singleton client ─────────────────────────────────────────────────────────

_client: Optional[AsyncOpenAI] = None


def get_llm_client() -> Optional[AsyncOpenAI]:
    """Return the shared LLM client, or None if no API key is configured."""
    global _client
    if _client is not None:
        return _client

    if not settings.llm_api_key:
        return None

    _client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    return _client


def _normalize_tools(tools: list[dict]) -> list[dict]:
    """
    Convert tool_registry format → OpenAI API format.

    tool_registry stores:
        {"type": "function", "name": "...", "description": "...", "parameters": {...}}

    OpenAI API expects:
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    normalized = []
    for t in tools:
        if "function" in t:
            # Already in OpenAI format
            normalized.append(t)
        else:
            normalized.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            })
    return normalized


# ── Agentic conversation loop ────────────────────────────────────────────────

async def run_agent_turn(
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    tool_executor,
    conversation_history: list[dict] = None,
    max_tool_rounds: int = 5,
) -> dict:
    """
    Run one full agentic turn:
      1. Send system prompt + user message to the LLM
      2. If LLM calls tools → execute via tool_executor, feed results back
      3. Repeat until LLM produces a final text response
      4. Return {text, tools_called}
    """
    client = get_llm_client()
    if client is None:
        return {"text": None, "tools_called": [], "error": "no_llm_key"}

    # Normalize tool schemas to OpenAI API format
    api_tools = _normalize_tools(tools) if tools else []

    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        messages.extend(conversation_history[-6:])

    messages.append({"role": "user", "content": user_message})

    tools_called = []

    for _round in range(max_tool_rounds):
        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=api_tools if api_tools else None,
                tool_choice="auto" if api_tools else None,
                temperature=0.3,
                max_tokens=600,
            )
        except Exception as e:
            print(f"  [llm] API error: {e}")
            return {"text": None, "tools_called": tools_called, "error": str(e)}

        msg = response.choices[0].message

        # No tool call → final text response
        if not msg.tool_calls:
            text = msg.content or ""
            return {"text": text.strip(), "tools_called": tools_called}

        # Tool calls → execute each, feed results back
        messages.append({"role": "assistant", "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]})

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

            print(f"  [llm] Tool call: {tool_name}({list(args.keys())})")
            tools_called.append(tool_name)

            result = tool_executor(tool_name, args)
            tool_result_str = result.get("tool_result", json.dumps({"status": "ok"}))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result_str,
            })

            # Update system prompt if case state changed
            if result.get("needs_prompt_update") and result.get("new_prompt"):
                messages[0]["content"] = result["new_prompt"]

    # Safety exit — force a plain response
    try:
        final = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages + [{"role": "user", "content": "Please respond now."}],
            temperature=0.3,
            max_tokens=400,
        )
        text = final.choices[0].message.content or ""
        return {"text": text.strip(), "tools_called": tools_called}
    except Exception as e:
        return {"text": None, "tools_called": tools_called, "error": str(e)}
