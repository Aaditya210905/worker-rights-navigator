# WorkerSaathi

**Voice-first Indian worker rights navigator.**

A retrieval-grounded legal/benefits navigator for Indian informal workers.
AssemblyAI handles real-time voice (STT → LLM → TTS).
FastAPI backend provides deterministic legal tools, RAG retrieval,
case management, safety escalation, and evidence generation.

> **Important architectural principle:**
> The LLM determines *what the user needs*.
> It does **not** determine the law from memory.
> Legal intelligence lives in verified, metadata-tagged knowledge chunks
> retrieved via RAG — never invented by the model.

---

## Architecture

```
                     WORKERSAATHI
                          │
                ┌─────────▼─────────┐
                │ AssemblyAI Voice  │
                │ Agent API         │
                │                   │
                │ Hindi + English   │
                │ Hinglish          │
                └─────────┬─────────┘
                          │
                    Tool Calls
                          │
                ┌─────────▼─────────┐
                │ FastAPI Backend    │
                └─────────┬─────────┘
                          │
       ┌──────────────────┼───────────────────┐
       │                  │                   │
       ▼                  ▼                   ▼
   Case Engine        Legal RAG          Safety Engine
       │                  │                   │
       ▼                  ▼                   ▼
   Database             Qdrant           112/181/1098
                                            /15100
                          │
                          ▼
                    Evidence Engine
                          │
                    ┌─────┴──────┐
                    ▼            ▼
                  PDF       Follow-up msg
```

---

## MVP Scope

### Supported Workers
- Platform / gig worker
- Construction worker
- Domestic / informal worker

### Supported Issues
| # | Issue                  | Example                                                           |
|---|------------------------|-------------------------------------------------------------------|
| 1 | **Unpaid wages**       | "Mujhe do mahine ki salary nahi mili."                            |
| 2 | **Construction injury**| "Site pe accident hua tha aur contractor treatment nahi de raha." |
| 3 | **Platform deactivation** | "Mera Swiggy/Zomato account deactivate kar diya bina reason ke." |

### Supported Jurisdictions
- **Central** — India Code, Code on Social Security 2020, Payment of Wages Act, BOCW Act, Employees' Compensation Act
- **Karnataka** — Karnataka Platform Based Gig Workers Act 2024, Karnataka BOCW Board
- **Tamil Nadu** — TN Manual Workers Act, TN Construction Workers Welfare Board

### Supported Languages
- Hindi
- English
- Hinglish (mid-sentence code-switching)

---

## Case Lifecycle

```
NEW
 ↓
LISTENING
 ↓
CLASSIFIED
 ↓
COLLECTING_INFORMATION
 ↓
SAFETY_CHECK
 ↓
RETRIEVING_RIGHTS
 ↓
RIGHTS_VERIFIED
 ↓
ACTION_PLAN_READY
 ↓
EVIDENCE_GENERATED
 ↓
CLOSED
```

**Safety exception — can interrupt ANY state:**

```
ANY STATE
    │
    ▼
SAFETY RISK DETECTED
    │
    ▼
SAFETY_ESCALATION
```

Safety escalation always takes priority over the rights-mapping flow.

---

## Project Structure

```
worker-rights-navigator/
│
├── app/
│   ├── __init__.py          # Package root
│   ├── config.py            # Pydantic Settings (from .env)
│   ├── main.py              # FastAPI entry point
│   │
│   ├── voice/               # AssemblyAI integration
│   ├── agent/               # Prompt, tools, dispatcher, policies
│   ├── rag/                 # Embeddings, vector search, retrieval
│   ├── case/                # Case object, slot filling, persistence
│   ├── safety/              # Danger detection, escalation, PII
│   └── evidence/            # PDF generation, follow-up messages
│
├── knowledge/
│   ├── central/             # Central Indian law chunks
│   ├── karnataka/           # Karnataka state law chunks
│   └── tamil_nadu/          # Tamil Nadu state law chunks
│
├── tests/                   # Retrieval, safety, case, tool tests
├── scripts/                 # Ingestion, agent publishing, etc.
│
├── .env                     # Local environment variables (not committed)
├── .env.example             # Template for .env
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Knowledge Base Data Rules

Every legal rule in the knowledge base must track:

| Field            | Purpose                                 |
|------------------|-----------------------------------------|
| `source`         | Official source (India Code, Gazette…)  |
| `jurisdiction`   | CENTRAL / KARNATAKA / TAMIL_NADU        |
| `law`            | Act or scheme name                      |
| `section`        | Specific section reference              |
| `law_status`     | IN_FORCE / NOT_YET_OPERATIONAL / …      |
| `effective_from` | Date the provision became operational   |
| `last_verified`  | When we last checked against the source |

**Source hierarchy (prefer higher levels):**

| Level | Source type                       |
|-------|-----------------------------------|
| 1     | Official Act / Gazette            |
| 2     | Government department / board     |
| 3     | PRS / authoritative tracker       |
| 4     | Legal aid / NGO                   |
| 5     | News / blog                       |

---

## Quick Start

```bash
# 1. Clone and enter the project
cd worker-rights-navigator

# 2. Activate virtual environment
# (Windows — conda)
conda activate ./venv

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env and add your ASSEMBLYAI_API_KEY

# 5. Run the server
python -m uvicorn app.main:app --reload --port 8000

# 6. Check health
curl http://localhost:8000/health
```

---

## Tools (Phase 5)

| Tool                        | Purpose                                   |
|-----------------------------|-------------------------------------------|
| `retrieve_rights`           | RAG retrieval of verified legal evidence   |
| `log_case_field`            | Validated case field update                |
| `generate_evidence_package` | PDF case summary generation                |
| `draft_followup_message`    | Employer notice / referral note drafting   |
| `escalate_safety`           | Deterministic emergency routing            |

---

## What is Deterministic vs Agentic?

| Function                   | Deterministic | Agentic |
|----------------------------|:---:|:---:|
| PII redaction              | ✅  |     |
| Safety routing             | ✅  |     |
| Jurisdiction normalization | ✅  |     |
| Database writes            | ✅  |     |
| Law retrieval              | ✅  |     |
| Law selection              |     | ✅  |
| Asking clarification       |     | ✅  |
| Summarization              |     | ✅  |
| Evidence generation        | ✅  | ✅  |
| Message drafting           |     | ✅  |
| Spoken explanation         |     | ✅  |

The LLM should explain and reason over verified evidence — **not invent the law.**

---

## License

This project is for the AssemblyAI hackathon. Not legal advice.
