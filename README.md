<p align="center">
  <h1 align="center">⚖️ WorkerSaathi</h1>
  <p align="center">
    <strong>AI-Powered Voice Agent for Indian Worker Rights Navigation</strong>
  </p>
  <p align="center">
    Empowering informal and gig workers to understand and exercise their legal rights — through voice, in their own language.
  </p>
</p>

---

## 🎯 Problem Statement

India has **450+ million informal workers** — gig delivery riders, construction labourers, domestic workers — most of whom have no idea what legal protections exist for them. When a Swiggy rider doesn't get paid for 3 weeks, or a construction worker is injured on-site with no compensation, they don't know:

- What laws protect them
- Where to file complaints
- What evidence to collect
- Who to contact for help

**WorkerSaathi** solves this by providing a **voice-first, multilingual AI assistant** that listens to a worker describe their problem in natural Hindi/Hinglish/English, identifies the legal issues, retrieves verified government-sourced rights, and guides them through next steps — all through a simple voice conversation.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🎤 **Voice-First Interface** | Workers speak naturally in Hindi, Hinglish, or English — no typing needed |
| 🧠 **Smart Case Understanding** | Automatically classifies worker type, issue category, and extracts key details |
| 📚 **RAG-Powered Legal Knowledge** | Retrieves verified rights from a curated Central Government knowledge base |
| 🛡️ **Safety-First Design** | Immediately escalates if a worker reports danger, injury, trafficking, or child labour |
| 📋 **Evidence Package Generation** | Creates structured legal evidence packages workers can use to file complaints |
| ✉️ **Message Drafting** | Drafts formal messages to employers/platforms in appropriate tone |
| 🔄 **Stateful Conversations** | Maintains conversation context and case progress across the entire session |
| 🌐 **REST + WebSocket API** | Full FastAPI backend with Swagger docs for easy integration |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser / Client                         │
│  ┌──────────────────┐  ┌─────────────────────────────────────┐  │
│  │   Voice UI       │  │   REST API (Swagger)                │  │
│  │  (voice.html)    │  │   /api/v1/...                       │  │
│  └────────┬─────────┘  └──────────────┬──────────────────────┘  │
└───────────┼────────────────────────────┼────────────────────────┘
            │ WebSocket                  │ HTTP
            ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  WS Proxy    │  │  REST Routes │  │  Session Manager       │ │
│  │  (ws.py)     │  │ (routes.py)  │  │  (session.py)          │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────┘ │
│         │                 │                                      │
│         ▼                 ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Orchestrator                              │ │
│  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────────────┐  │ │
│  │  │ Case Manager│ │ Tool Router  │ │ Prompt Builder       │  │ │
│  │  │ (state.py)  │ │ (registry)   │ │ (prompts.py)         │  │ │
│  │  └──────┬──────┘ └──────┬───────┘ └──────────────────────┘  │ │
│  └─────────┼───────────────┼───────────────────────────────────┘ │
│            │               │                                     │
│            ▼               ▼                                     │
│  ┌─────────────┐  ┌──────────────────────────────────────────┐  │
│  │ CaseState   │  │           Tool Handlers                   │  │
│  │ (Pydantic)  │  │                                           │  │
│  └─────────────┘  │  update_case_info  → Field Extraction     │  │
│                   │  retrieve_rights   → RAG Pipeline          │  │
│                   │  generate_evidence → Evidence Assembler    │  │
│                   │  draft_message     → Message Generator     │  │
│                   │  escalate_safety   → Emergency Response    │  │
│                   └──────────┬───────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                    RAG Pipeline                               ││
│  │                                                               ││
│  │  Knowledge JSON → Loader → Chunker → Embeddings → Qdrant    ││
│  │       ↓                                                       ││
│  │  Query Builder → Semantic Search + BM25 → RRF Fusion         ││
│  │       ↓                                                       ││
│  │  Reranker → Validator → Evidence Assembler → LegalEvidence   ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌───────────────────────────┐                                   │
│  │    AssemblyAI Voice API   │ ◄── Real-time STT + TTS + LLM    │
│  └───────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
worker-rights-navigator/
├── app/
│   ├── __init__.py              # Package init
│   ├── config.py                # Settings from .env
│   ├── main.py                  # FastAPI app, startup, routes
│   │
│   ├── agent/                   # 🧠 AI Agent Layer
│   │   ├── orchestrator.py      # Central backend orchestrator
│   │   ├── prompts.py           # System prompt templates
│   │   ├── tool_registry.py     # Tool schemas & permissions
│   │   ├── classifier.py        # Worker type / issue classifier
│   │   ├── conversation.py      # Conversation tracking
│   │   ├── test_orchestrator.py # Unit tests
│   │   └── test_scenarios.py    # End-to-end scenario tests
│   │
│   ├── api/                     # 🌐 FastAPI REST + WebSocket
│   │   ├── routes.py            # REST endpoints (12 routes)
│   │   ├── ws.py                # WebSocket voice proxy
│   │   ├── session.py           # Multi-session manager
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── knowledge.py         # Knowledge base API routes
│   │
│   ├── case/                    # 📋 Case State Machine
│   │   ├── models.py            # Enums, CaseState, CaseStatus
│   │   ├── state.py             # CaseManager (state transitions)
│   │   └── fields.py            # Field definitions & validation
│   │
│   ├── rag/                     # 📚 Retrieval-Augmented Generation
│   │   ├── loader.py            # Load knowledge from JSON
│   │   ├── chunker.py           # Document chunking
│   │   ├── embeddings.py        # HuggingFace embedding client
│   │   ├── qdrant_store.py      # Qdrant vector database
│   │   ├── query_builder.py     # Structured query construction
│   │   ├── retriever.py         # Hybrid retrieval engine
│   │   ├── reranker.py          # Authority-weighted reranking
│   │   ├── validator.py         # Legal evidence validation
│   │   ├── evidence.py          # Evidence assembler
│   │   ├── models.py            # RAG data models
│   │   ├── matrix.py            # Rights matrix utilities
│   │   ├── pipeline.py          # Full RAG pipeline
│   │   └── sources.py           # Source tracking & verification
│   │
│   ├── voice/                   # 🎤 Voice Agent
│   │   ├── assemblyai.py        # AssemblyAI WebSocket client
│   │   └── audio.py             # Microphone & Speaker (PyAudio)
│   │
│   ├── safety/                  # 🛡️ Safety Detection
│   │   └── __init__.py          # Safety check & escalation logic
│   │
│   ├── evidence/                # 📋 Evidence & Action Planning
│   │   └── action_planner.py    # Step-by-step action plans
│   │
│   ├── static/                  # 🖥️ Frontend
│   │   └── voice.html           # Browser-based voice client
│   │
│   └── db/                      # 💾 Database (future)
│
├── knowledge/                   # 📖 Legal Knowledge Base
│   ├── workersaathi/json/       # Curated Central Government data
│   ├── central/                 # Central legislation
│   ├── states/                  # State-specific laws
│   ├── rights_matrix.json       # Comprehensive rights mapping
│   └── sources.json             # Verified source registry
│
├── data/                        # 📦 Runtime Data
│   └── qdrant/                  # Qdrant vector DB (file-based)
│
├── tests/                       # 🧪 Test Suite
├── scripts/                     # 🔧 Utility Scripts
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **AssemblyAI API Key** — [Get one here](https://www.assemblyai.com/) (Universal-2 with Voice Agent access)
- **Microphone + Headphones** (for voice testing)

### 1. Clone & Setup

```bash
git clone https://github.com/your-username/worker-rights-navigator.git
cd worker-rights-navigator

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example .env
cp .env.example .env

# Edit .env and add your AssemblyAI API key
```

Your `.env` file should contain:

```env
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
APP_ENV=development
APP_PORT=8000
APP_HOST=0.0.0.0
```

### 3. Start the Server

```bash
uvicorn app.main:app --reload
```

The server starts at `http://127.0.0.1:8000`

### 4. Use WorkerSaathi

| Interface | URL | Description |
|-----------|-----|-------------|
| 🎤 **Voice Agent** | http://127.0.0.1:8000/voice | Browser-based voice interaction |
| 📖 **API Docs** | http://127.0.0.1:8000/docs | Interactive Swagger UI |
| ❤️ **Health Check** | http://127.0.0.1:8000/api/v1/health | System status |

---

## 🎤 Voice Agent Usage

1. Open **http://127.0.0.1:8000/voice** in your browser
2. Click the **microphone button** 🎙️
3. **Allow microphone access** when prompted
4. **Speak naturally** — the agent understands Hindi, Hinglish, and English

### Example Conversations

**Unpaid Wages (Hindi):**
> "Main Swiggy mein delivery karta hoon Mumbai mein. Mujhe teen hafte se 8000 rupaye ka payment nahi mila."

**Workplace Injury (English):**
> "I had an accident at the construction site and I am injured right now."

**Platform Deactivation (Hinglish):**
> "Mera Zomato account deactivate ho gaya hai, koi reason nahi bataya."

### What WorkerSaathi Does

```
🎤 Worker speaks their problem
    ↓
🔍 Classifies: worker type, issue category, state
    ↓
📝 Collects: employer, amount, dates, details
    ↓
🛡️ Safety check: escalates if immediate danger
    ↓
📚 RAG retrieval: searches verified legal knowledge base
    ↓
⚖️ Explains: relevant laws, rights, and protections
    ↓
📋 Generates: evidence package + action plan
    ↓
✉️ Drafts: formal message to employer/platform
```

---

## 🌐 API Reference

### Session Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/sessions` | Create a new session |
| `GET` | `/api/v1/sessions/{id}` | Get session details |
| `DELETE` | `/api/v1/sessions/{id}` | End a session |

### Case Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/sessions/{id}/case` | Get current case state |
| `POST` | `/api/v1/sessions/{id}/tool` | Execute a tool call |
| `POST` | `/api/v1/sessions/{id}/transcript` | Submit user transcript |

### Knowledge Base

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/knowledge/stats` | Knowledge base statistics |
| `GET` | `/api/v1/knowledge/sources` | List verified sources |
| `POST` | `/api/v1/knowledge/search` | Search the knowledge base |

### Voice

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WebSocket` | `/api/v1/voice/{session_id}` | Real-time voice connection |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/voice` | Voice agent web UI |

---

## 🧠 How It Works

### 1. Voice Processing

WorkerSaathi uses **AssemblyAI's Voice Agent API** for real-time speech-to-text, LLM reasoning, and text-to-speech. The conversation flows through a WebSocket proxy that intercepts tool calls for server-side execution.

### 2. Case State Machine

Every conversation tracks a `CaseState` with defined transitions:

```
new → listening → classified → collecting_information → retrieving_rights
    → rights_verified → action_plan_ready → evidence_generated → closed
```

At any point, if danger is detected: `→ safety_escalation`

### 3. Tool System

The LLM has access to 5 backend tools:

| Tool | Purpose | When Available |
|------|---------|----------------|
| `update_case_info` | Extract worker details from speech | Early stages |
| `retrieve_rights` | Search legal knowledge base via RAG | After classification |
| `generate_evidence` | Build structured evidence package | After rights verified |
| `draft_message` | Draft formal employer message | After rights verified |
| `escalate_safety` | Emergency safety response | **Always** |

### 4. RAG Pipeline

The Retrieval-Augmented Generation pipeline ensures WorkerSaathi **never fabricates legal information**:

```
Knowledge Base (33 curated items)
    ↓
Loader → Chunker (27 chunks)
    ↓
Embeddings (HuggingFace all-MiniLM-L6-v2)
    ↓
Dual Search:
  • Qdrant (semantic similarity)
  • BM25 (keyword matching)
    ↓
RRF Fusion (Reciprocal Rank Fusion)
    ↓
Reranker (authority + status + specificity weighting)
    ↓
Validator (legal status + applicability checks)
    ↓
Evidence Assembler → LegalEvidence
```

### 5. Safety-First Design

If a worker mentions injury, violence, trafficking, or child labour, WorkerSaathi **immediately** provides emergency helplines:

- **Emergency (Police/Fire/Ambulance):** 112
- **Police:** 100
- **Ambulance:** 108
- **Women Helpline:** 1091 / 181
- **Child Helpline:** 1098
- **Anti-Trafficking:** 1800-419-8588

Safety escalation **always** takes priority over normal conversation flow.

---

## 📚 Knowledge Base

WorkerSaathi's legal knowledge comes from verified Central Government sources:

| Source Type | Examples |
|-------------|----------|
| **Legislation** | Code on Wages 2019, Occupational Safety Health and Working Conditions Code 2020 |
| **Government Portals** | e-Shram, EPFO, ESIC |
| **Schemes** | PM-SVANidhi, e-Shram registration, BOCW welfare boards |
| **Helplines** | Verified emergency and grievance redressal numbers |
| **Procedures** | How to file complaints with Labour Commissioner, DLSA |

### Worker Types Supported

- 🛵 **Gig Workers** — Delivery riders, cab drivers (Swiggy, Zomato, Uber, Ola)
- 🏗️ **Construction Workers** — Daily wage labourers, site workers
- 🏠 **Domestic Workers** — Household helpers, cooks, caretakers

### Issue Categories

- 💰 **Unpaid Wages** — Salary delays, non-payment, underpayment
- 🤕 **Workplace Injury** — Accidents, unsafe conditions, compensation
- 📵 **Platform Deactivation** — Unfair account termination, no reason given

---

## 🧪 Testing

### Run End-to-End Scenario Tests

```bash
python -m app.agent.test_scenarios
```

Tests 3 golden scenarios:
- **Scenario A:** Gig worker unpaid wages → RAG retrieval → evidence
- **Scenario B:** Construction worker injury → safety escalation
- **Scenario C:** Platform deactivation → RAG retrieval → action plan

### Run Orchestrator Unit Tests

```bash
python -m app.agent.test_orchestrator
```

### Test via Swagger UI

1. Open http://127.0.0.1:8000/docs
2. Create a session: `POST /api/v1/sessions`
3. Execute tools: `POST /api/v1/sessions/{id}/tool`
4. Check case state: `GET /api/v1/sessions/{id}/case`

---

## 🔧 Technical Stack

| Component | Technology |
|-----------|-----------|
| **Backend Framework** | FastAPI + Uvicorn |
| **Voice Agent** | AssemblyAI Voice Agent API (WebSocket) |
| **Embeddings** | HuggingFace `all-MiniLM-L6-v2` |
| **Vector Database** | Qdrant (in-memory mode) |
| **Keyword Search** | BM25 (rank-bm25) |
| **Data Validation** | Pydantic v2 |
| **Configuration** | python-dotenv + pydantic-settings |
| **Audio I/O** | PyAudio (CLI), Web Audio API (browser) |
| **Frontend** | Vanilla HTML/CSS/JS |

---

## 🛣️ Roadmap

- [x] Voice-first conversational agent
- [x] Multi-tool orchestration (5 tools)
- [x] RAG pipeline with verified legal knowledge
- [x] Safety-first escalation system
- [x] Case state machine with transitions
- [x] Evidence package generation
- [x] Employer message drafting
- [x] FastAPI REST + WebSocket API
- [x] Browser-based voice client
- [ ] State-specific law retrieval (Karnataka, Tamil Nadu, etc.)
- [ ] Persistent database (PostgreSQL)
- [ ] User authentication
- [ ] Multi-language TTS voice selection
- [ ] Mobile-optimized PWA
- [ ] Integration with e-Shram portal
- [ ] SMS/WhatsApp fallback for low-bandwidth areas

---

## ⚠️ Important Disclaimers

> **WorkerSaathi is NOT a lawyer.** It provides general legal information from verified government sources but does NOT provide legal advice. Workers should consult a legal professional for specific legal matters.

> **Information may be incomplete.** The knowledge base covers Central Government laws. State-specific regulations may differ. WorkerSaathi clearly indicates when it doesn't have verified information.

> **Emergency situations:** If you or someone else is in immediate danger, call **112** (Emergency) or **100** (Police) directly.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is built for the purpose of empowering Indian workers. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built with ❤️ for India's 450M+ informal workers</strong>
</p>
