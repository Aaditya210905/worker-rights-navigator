# ── WorkerSaathi — Production Dockerfile ─────────────────────────
# Compatible with Railway / Render / any Docker host
#
# The build context is the REPOSITORY ROOT (this file lives in backend/),
# because the image bundles both the backend code and the frontend assets.
#
# Build:   docker build -f backend/Dockerfile -t workersaathi .
# Run:     docker run -p 8000:8000 --env-file backend/.env workersaathi

FROM python:3.11-slim AS base

# Prevent .pyc + enable unbuffered logs (important for Render log drain)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System deps (only what the app actually needs at runtime) ────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        tesseract-ocr \
        tesseract-ocr-hin \
        tesseract-ocr-eng \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps (cached layer) ──────────────────────────────────
COPY backend/requirements-deploy.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Backend application code ────────────────────────────────────
COPY backend/app/ ./app/
COPY backend/knowledge/ ./knowledge/
COPY backend/scripts/ ./scripts/

# ── Frontend web client (served by FastAPI at /voice) ───────────
COPY frontend/ ./frontend/

# ── Pre-built vector store (Qdrant embeddings) ─────────────────
COPY backend/data/qdrant/ ./data/qdrant/

# ── Default environment (overridden by Render env vars) ─────────
ENV APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    EMBEDDING_BACKEND=huggingface

EXPOSE 8000

# ── Health check ────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os; import urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')" || exit 1

# ── Start (PORT env var is set by Railway/Render) ─────────────────
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 120"
