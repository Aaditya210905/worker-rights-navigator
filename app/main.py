"""
FastAPI application entry point + voice agent runner.

Phase 1: Two modes of operation:
  1. `python app/main.py`        -- Run the voice agent directly (microphone)
  2. `uvicorn app.main:app`      -- Run the FastAPI server (health check only)

The voice agent connects directly from your PC to AssemblyAI.
No browser needed for Phase 1.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

# When running directly (python app/main.py), the project root
# isn't on sys.path. Add it so `from app.x import y` works.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings


# ── Lifespan (replaces deprecated on_event) ───────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("=" * 60)
    print("  WorkerSaathi starting up")
    print(f"  Environment : {settings.app_env}")
    print(f"  Listening on: {settings.app_host}:{settings.app_port}")
    print("=" * 60)

    if not settings.assemblyai_api_key or settings.assemblyai_api_key == "your_key_here":
        print("  [!] ASSEMBLYAI_API_KEY not set -- voice features will not work.")
    else:
        print("  [ok] AssemblyAI API key loaded")

    yield  # App runs here

    # Shutdown
    print("WorkerSaathi shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="WorkerSaathi",
    description=(
        "Voice-first Indian worker rights navigator. "
        "AssemblyAI handles real-time voice; FastAPI backend provides "
        "deterministic legal tools, RAG retrieval, case management, "
        "safety escalation, and evidence generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Basic liveness probe."""
    return JSONResponse(
        content={
            "status": "ok",
            "app": "WorkerSaathi",
            "version": "0.1.0",
            "environment": settings.app_env,
        }
    )


# ── Voice agent CLI runner ────────────────────────────────────────────────────

async def run_voice_agent():
    """
    Run the voice agent directly from your PC's microphone.

    This is the Phase 1 entry point:
      Microphone -> AssemblyAI Voice Agent API -> Speaker

    Use headphones to prevent acoustic echo!
    """
    from app.voice.audio import Microphone, Speaker
    from app.voice.assemblyai import AssemblyAIAgent

    api_key = settings.assemblyai_api_key
    if not api_key or api_key == "your_key_here":
        print("[error] ASSEMBLYAI_API_KEY not set in .env")
        print("        Copy .env.example to .env and add your key.")
        sys.exit(1)

    print()
    print("=" * 50)
    print("  WorkerSaathi Voice Agent")
    print("  Phase 1 -- Direct Microphone Mode")
    print()
    print("  USE HEADPHONES to prevent echo!")
    print("  Press Ctrl+C to stop.")
    print("=" * 50)
    print()

    agent = AssemblyAIAgent(api_key=api_key)
    mic = Microphone()
    speaker = Speaker()

    try:
        mic.open()
        speaker.open()
        print("[audio] Microphone and speaker opened.")

        await agent.run(mic, speaker)

    except KeyboardInterrupt:
        print("\n[agent] Stopping...")
        agent.stop()
    finally:
        mic.close()
        speaker.close()
        print("[audio] Audio devices closed.")


# ── Direct execution ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # When run directly, start the voice agent (not the web server)
    asyncio.run(run_voice_agent())
