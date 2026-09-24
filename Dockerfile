# ── WorkerSaathi — Production Dockerfile ─────────────────────────
# Optimised for Render.com free tier (512MB RAM)
#
# Build:   docker build -t workersaathi .
# Run:     docker run -p 8000:8000 --env-file .env workersaathi

FROM python:3.11-slim AS base

# Prevent .pyc + enable unbuffered logs (important for Render log drain)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System deps (only what the app actually needs at runtime) ────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps (cached layer) ──────────────────────────────────
COPY requirements-deploy.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Application code ────────────────────────────────────────────
COPY app/ ./app/
COPY knowledge/ ./knowledge/
COPY scripts/ ./scripts/
COPY data/ ./data/ 2>/dev/null || true

# ── Ensure data directory exists for SQLite ─────────────────────
RUN mkdir -p /app/data

# ── Default environment (overridden by Render env vars) ─────────
ENV APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    EMBEDDING_BACKEND=huggingface

EXPOSE 8000

# ── Health check ────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── Start ────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "120"]
