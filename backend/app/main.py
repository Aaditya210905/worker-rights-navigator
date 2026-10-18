"""
FastAPI application entry point.

The FastAPI server provides:
  - REST API at /api/v1/
  - Sarvam voice endpoints at /api/v1/voice/*
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

from fastapi import FastAPI, HTTPException
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

    if not settings.sarvam_api_key:
        print("  [!] SARVAM_API_KEY not set -- voice features will not work.")
        print("       Get your key at https://dashboard.sarvam.ai/")
    else:
        print("  [ok] Sarvam AI API key loaded (Saaras v4 STT + Bulbul v3 TTS)")

    if not settings.llm_api_key:
        print("  [!] LLM_API_KEY not set -- agent reasoning will use rule-based fallback.")
    else:
        print(f"  [ok] LLM reasoning enabled: {settings.llm_model} ({settings.llm_base_url})")


    # Pre-warm the RAG retriever in a background thread so the first
    # voice session doesn't block for 30-60s while documents load.
    import threading

    def _prewarm_retriever():
        try:
            from app.agent.orchestrator import Orchestrator
            orch = Orchestrator()
            retriever = orch._get_retriever()
            if retriever:
                print("  [startup] RAG retriever pre-warmed successfully")
            else:
                print("  [startup] RAG retriever not available (data missing?)")
        except Exception as e:
            print(f"  [startup] RAG pre-warm failed (non-fatal): {e}")

    print("  [startup] Pre-warming RAG retriever in background...")
    threading.Thread(target=_prewarm_retriever, daemon=True).start()

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
        "Sarvam AI handles Indic speech (STT/TTS); FastAPI backend provides "
        "deterministic legal tools, RAG retrieval, case management, "
        "safety escalation, and evidence generation.\n\n"
        "## API Overview\n"
        "- **Sessions**: Create/manage conversation sessions\n"
        "- **Tools**: Execute backend tools (update_case_info, retrieve_rights, etc.)\n"
        "- **Case**: View case state, missing fields, next question\n"
        "- **Knowledge**: Browse indexed legal sources\n"
        "- **Voice**: Sarvam-powered STT/TTS/converse endpoints\n"
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
from app.api.voice_routes import router as voice_router
from app.api.action_plan import router as action_plan_router

app.include_router(api_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(action_plan_router, prefix="/api/v1")


# ── Frontend (voice web client) ──────────────────────────────────────────────

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# frontend/ resolution: works both in local dev (repo root) and in Docker (/app/frontend)
_candidates = [
    Path(__file__).resolve().parent.parent.parent / "frontend",  # Local repo root
    Path(__file__).resolve().parent.parent / "frontend",         # Docker container (/app/frontend)
    Path.cwd() / "frontend",
]
FRONTEND_DIR = next((p for p in _candidates if p.is_dir()), _candidates[0])
INDEX_HTML = FRONTEND_DIR / "index.html"

if FRONTEND_DIR.is_dir():
    # index.html loads `css/…` and `js/…` relatively, so those folders are
    # exposed at the site root (the page itself is served from /voice).
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
else:
    print(f"  [!] Frontend folder not found at {FRONTEND_DIR} -- /voice will return 404")


@app.get("/voice", include_in_schema=False)
async def voice_page():
    """Serve the browser-based voice agent UI."""
    if not INDEX_HTML.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(INDEX_HTML)


# ── Root redirect to voice UI ────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to voice agent UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/voice")


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


# ── Direct execution ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
