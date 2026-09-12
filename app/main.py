"""
FastAPI application entry point + voice agent runner.

Two modes of operation:
  1. `uvicorn app.main:app`           -- Run the FastAPI server (full REST API)
  2. `python app/main.py --voice`     -- Run the voice agent directly (microphone)

The FastAPI server provides:
  - REST API at /api/v1/
  - WebSocket voice proxy at /api/v1/voice/{session_id}
  - Swagger docs at /docs
  - Health check at /api/v1/health
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
from fastapi.middleware.cors import CORSMiddleware
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
    print(f"  Docs at     : http://{settings.app_host}:{settings.app_port}/docs")
    print("=" * 60)

    if not settings.assemblyai_api_key or settings.assemblyai_api_key == "your_key_here":
        print("  [!] ASSEMBLYAI_API_KEY not set -- voice features will not work.")
    else:
        print("  [ok] AssemblyAI API key loaded")

    yield  # App runs here

    # Shutdown — cleanup sessions
    from app.api.session import session_manager
    session_manager.cleanup_all()
    print("WorkerSaathi shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="WorkerSaathi",
    description=(
        "Voice-first Indian worker rights navigator. "
        "AssemblyAI handles real-time voice; FastAPI backend provides "
        "deterministic legal tools, RAG retrieval, case management, "
        "safety escalation, and evidence generation.\n\n"
        "## API Overview\n"
        "- **Sessions**: Create/manage conversation sessions\n"
        "- **Tools**: Execute backend tools (update_case_info, retrieve_rights, etc.)\n"
        "- **Case**: View case state, missing fields, next question\n"
        "- **Knowledge**: Browse indexed legal sources\n"
        "- **Voice**: WebSocket proxy for browser-based voice\n"
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ── CORS Middleware ───────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "*",  # Allow all for hackathon demo
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Mount API routers ────────────────────────────────────────────────────────

from app.api.routes import router as api_router
from app.api.knowledge import router as knowledge_router
from app.api.ws import router as ws_router

app.include_router(api_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


# ── Voice agent page ─────────────────────────────────────────────────────────

from fastapi.responses import FileResponse
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/voice", include_in_schema=False)
async def voice_page():
    """Serve the browser-based voice agent UI."""
    return FileResponse(STATIC_DIR / "voice.html")


# ── Root redirect to docs ────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API docs."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# ── Legacy health endpoint (backwards compatibility) ──────────────────────────

@app.get("/health", include_in_schema=False)
async def legacy_health():
    """Legacy health endpoint. Use /api/v1/health instead."""
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
    print("  Direct Microphone Mode")
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
    if "--voice" in sys.argv:
        # Voice agent mode (direct microphone)
        asyncio.run(run_voice_agent())
    else:
        # FastAPI server mode (default)
        import uvicorn
        uvicorn.run(
            "app.main:app",
            host=settings.app_host,
            port=settings.app_port,
            reload=True,
        )
