# WorkerSaathi — Backend

FastAPI service that powers the WorkerSaathi voice agent: REST + WebSocket API,
deterministic case state machine, hybrid RAG legal retrieval, safety escalation,
evidence generation and SQLite persistence.

The static voice client lives in [`../frontend`](../frontend) and is served by
this service (`GET /voice`).

## Layout

| Path | Purpose |
|------|---------|
| `app/main.py` | FastAPI app: routers, CORS, frontend mount, `--voice` CLI runner |
| `app/config.py` | Settings loaded from `.env` (Pydantic Settings) |
| `app/api/` | HTTP/WS transport: `routes.py`, `ws.py`, `session.py`, `knowledge.py`, `lemur.py`, `schemas.py` |
| `app/agent/` | Orchestration: tool dispatch, prompts, classification, tool registry |
| `app/case/` | Case state machine: enums, fields, `CaseManager` |
| `app/rag/` | Legal knowledge engine: loaders, chunker, embeddings, Qdrant, retriever, reranker, validator |
| `app/voice/` | AssemblyAI client and PyAudio wrappers (CLI mode) |
| `app/evidence/` | Action planning from retrieved sources |
| `app/db/` | SQLite persistence (cases, events, plans, evidence) |
| `app/safety/` | Emergency escalation guardrails |
| `knowledge/` | Legal knowledge base (JSON research packages, source registry, coverage matrix) |
| `data/` | Runtime data: `worker_cases.db` + committed Qdrant vector store |
| `scripts/` | Utilities: `embed.py` |
| `tests/` | Test suite |

## Run

```bash
cd backend
python -m venv ../venv && ../venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env        # add ASSEMBLYAI_API_KEY
uvicorn app.main:app --reload
```

- Voice client: `http://127.0.0.1:8000/voice`
- Swagger docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`
- Direct microphone mode: `python app/main.py --voice`

> `data/`, `knowledge/` and `scripts/` are resolved relative to the repository
> root's `backend/` folder (via `Path(__file__)`), so the commands above work
> from any working directory as long as the package is importable.

## Knowledge base

```bash
ollama pull qwen3-embedding:8b
python -m app.rag.pipeline --index     # rebuild index
python -m app.rag.pipeline --test      # retrieval quality checks
python -m scripts.embed                # resume-friendly embedding runner
```

## Tests

```bash
python -m app.agent.test_orchestrator
python -m app.agent.test_scenarios
python -m app.rag.pipeline --test
```

## Deploy

`Dockerfile` here is built with the **repository root** as context (it also copies
`../frontend`):

```bash
docker build -f backend/Dockerfile -t workersaathi .
docker run -p 8000:8000 --env-file backend/.env workersaathi
```

`render.yaml` and `railway.toml` in the repository root point at
`backend/Dockerfile`.
