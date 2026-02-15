# Aura -- AI Resume Screening Tool

AI-powered resume screening service for HR teams.
Upload a PDF resume, pick a job, and get an AI-generated score with strengths,
weaknesses, and reasoning.

## Table of Contents

| # | Section | What You'll Find |
|---|---------|-----------------|
| 1 | [Approach](#approach) | What this project does and key decisions |
| 2 | [Tech Stack](#tech-stack) | All technologies used |
| 3 | [Frontend](#frontend) | React UI with screenshots |
| 4 | [Project Structure](#project-structure) | Files and folders explained |
| 5 | [Runbook](#runbook) | How to start the app (one command) |
| 6 | [End-to-End API Flow](#end-to-end-api-flow-curl-examples) | 7-step curl walkthrough |
| 7 | [API Endpoints Summary](#api-endpoints-summary) | All 10 endpoints in one table |
| 8 | [What the AI Returns](#what-the-ai-returns) | Score format explained |
| 9 | [Cost Controls](#cost-controls) | 4 layers of cost management |
| 10 | [Design Decisions](#design-decisions-detailed) | Architecture, RAG, prompts, data model |
| 11 | [What I Would Improve](#what-i-would-improve-with-more-time) | Future work |

## Approach

**Option A: AI Resume Screening Tool** -- Recruiters create job descriptions,
upload candidate resumes (PDF or text), and the system uses GPT-4o to score
each candidate with evidence-backed reasoning.

The system uses a RAG (Retrieval-Augmented Generation) pipeline:
- PDF text is extracted, split into chunks, and embedded using OpenAI embeddings
- Chunks are stored in Qdrant vector database for semantic search
- When screening, only the most relevant resume chunks are sent to GPT-4o
- This reduces costs and improves scoring accuracy

**Key decisions:**
- **LangChain + GPT-4o** for LLM scoring with structured JSON output
- **Real OpenAI embeddings** (text-embedding-3-small) for semantic search
- **Qdrant vector DB** with chunked resume storage for RAG retrieval
- **Redis caching** so the same job+resume pair doesn't call the LLM twice
- **No auth required** for demo -- all requests use a default tenant

## Assumptions

- Resumes are uploaded as PDF files (text fallback also supported)
- Single-region deployment for v1
- GPT-4o is sufficient for scoring (no fine-tuning needed)
- Synchronous screening is acceptable (< 50 resumes per call)

## Trade-offs

| Decision | Trade-off |
|----------|-----------|
| RAG chunking vs whole-doc | Better relevance but more embedding API calls |
| Sync screening vs async queue | Simpler but blocks on LLM calls; add Celery for v2 |
| `create_all` vs Alembic | Faster to ship; add Alembic before second schema change |
| GPT-4o vs cheaper model | Better accuracy but higher cost per call |

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | FastAPI | REST endpoints with auto-generated Swagger docs |
| LLM | GPT-4o via LangChain | Scores resumes against job descriptions |
| Embeddings | OpenAI text-embedding-3-small | Converts text to vectors for semantic search |
| Vector DB | Qdrant | Stores resume chunks, finds relevant content |
| Database | PostgreSQL | Jobs, resumes, screening results, feedback |
| Cache | Redis | Caches scores, tracks per-tenant LLM usage |
| PDF Parsing | PyMuPDF | Extracts text from uploaded PDF files |
| Package Manager | uv (astral-sh) | Fast Python dependency management |
| Container | Docker Compose | Runs all 4 services together |

## Frontend

A React frontend is available in a separate repo:
**https://github.com/xxkhanxx77/aura-poc-frontend**

Features a **Career Page** where candidates browse jobs and upload PDF resumes,
and an **Admin Dashboard** where HR reviews AI screening results with scores,
strengths, weaknesses, and can submit feedback.

![Admin Dashboard](https://raw.githubusercontent.com/xxkhanxx77/aura-poc-frontend/main/docs/images/admin-dashboard.png)

![Career Page](https://raw.githubusercontent.com/xxkhanxx77/aura-poc-frontend/main/docs/images/career-page.png)

## Project Structure

| File | What It Does |
|------|-------------|
| **Backend (`src/backend/app/`)** | |
| `api/routes.py` | API endpoints (10 routes) |
| `core/config.py` | Settings (env vars with `AURA_` prefix) |
| `core/auth.py` | JWT auth (optional, demo mode by default) |
| `core/database.py` | PostgreSQL async connection |
| `models/orm.py` | SQLAlchemy models (Tenant, Job, Resume, Result, Feedback) |
| `models/schemas.py` | Pydantic request/response schemas |
| `prompts/resume_screening.py` | LLM prompt templates (versioned) |
| `services/llm_service.py` | LangChain + GPT-4o integration |
| `services/embedding_service.py` | OpenAI embeddings + text chunking (RAG) |
| `services/vector_service.py` | Qdrant vector storage and search |
| `services/screening_service.py` | Orchestrator: vector search -> cache -> LLM -> DB |
| `services/cache_service.py` | Redis caching with JD-hash invalidation |
| `services/pdf_service.py` | PDF text extraction (PyMuPDF) |
| **Scripts (`src/backend/scripts/`)** | |
| `init_db.py` | Create database tables |
| `seed_data.py` | Insert sample data for testing |
| **Infra (`infra/`)** | |
| `Dockerfile` | Multi-stage build with uv |
| `docker-compose.yml` | PostgreSQL + Redis + Qdrant + App |
| `.env.example` | Environment variable template |
| **Docs (`docs/`)** | |
| `A1-A4, B1, C1, C2, E` | Design documents (also summarized below) |

---

## Runbook

### Prerequisites

- Docker + Docker Compose
- An OpenAI API key (for GPT-4o and embeddings)

### One-Command Startup

```bash
cd infra
cp .env.example .env
```

Edit `infra/.env` and add your OpenAI API key:

```
AURA_OPENAI_API_KEY=sk-proj-your-key-here
```

Then start everything:

```bash
docker compose up --build -d
```

This starts 4 services:
- **app** (FastAPI on port 8000)
- **postgres** (PostgreSQL on port 5432)
- **redis** (Redis on port 6379)
- **qdrant** (Qdrant on port 6333)

### Initialize Database

```bash
docker compose exec -T app python -m scripts.init_db
docker compose exec -T app python -m scripts.seed_data
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AURA_OPENAI_API_KEY` | Yes | `""` | OpenAI API key for GPT-4o and embeddings |
| `AURA_JWT_SECRET` | No | `change-me-in-production` | JWT signing secret (not needed for demo) |
| `AURA_DATABASE_URL` | No | Set by docker-compose | PostgreSQL connection string |
| `AURA_REDIS_URL` | No | Set by docker-compose | Redis connection string |
| `AURA_QDRANT_URL` | No | Set by docker-compose | Qdrant connection string |

### Health Checks

```bash
# Check the app is running
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Check all services are healthy
docker compose ps
# All 4 should show "healthy"
```

### Swagger UI

Open **http://localhost:8000/docs** in your browser.
All endpoints have pre-filled examples. No authentication needed.

---

## End-to-End API Flow (curl examples)

No authentication is required. All requests work without a token.

### Step 1: Create a Job

First, create a job description that candidates will be screened against.

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Junior Python Dev",
    "description": "Looking for a junior Python developer with 1-2 years experience. Must know Flask or FastAPI, SQL basics, and Git.",
    "requirements": ["Python", "SQL", "Git"]
  }' | python3 -m json.tool
```

Response:
```json
{
    "id": "c2037c79-42c3-4311-be59-8a977d700f5f",
    "title": "Junior Python Dev",
    "description": "Looking for a junior Python developer...",
    "requirements": ["Python", "SQL", "Git"],
    "status": "active",
    "created_at": "2026-02-15T10:21:57.230804"
}
```

Save the `id` -- you'll need it in the next steps.

### Step 2: List All Jobs

See all jobs in the system:

```bash
curl -s http://localhost:8000/api/v1/jobs | python3 -m json.tool
```

### Step 3: Upload a PDF Resume and Screen It

Upload a PDF resume and screen it against the job -- all in one call.
Replace `<job-id>` with the ID from Step 1.

```bash
curl -s -X POST http://localhost:8000/api/v1/resumes/upload-pdf \
  -F "file=@pdf/Aran_Sriaran_Software_Resume_2025.pdf" \
  -F "candidate_name=Aran Sriaran" \
  -F "job_id=<job-id>" \
  -F "email=aran@example.com" | python3 -m json.tool
```

A sample resume PDF is included in the repo at `pdf/` for easy testing.

What happens behind the scenes:
1. PDF text is extracted using PyMuPDF
2. Text is split into ~500 character chunks with overlap
3. Each chunk is embedded using OpenAI text-embedding-3-small
4. Chunks are stored in Qdrant vector database
5. The most relevant chunks for this job are retrieved from Qdrant
6. GPT-4o scores the candidate based on the relevant chunks
7. Score is saved to PostgreSQL and cached in Redis

Response:
```json
{
    "job_id": "c2037c79-42c3-4311-be59-8a977d700f5f",
    "job_title": "Junior Python Dev",
    "total_candidates": 1,
    "results": [
        {
            "candidate_name": "Aran Sriaran",
            "score": 60,
            "strengths": [
                {"point": "Experience with Python", "evidence": "Skills: Python, SQL..."},
                {"point": "Knowledge of SQL and Git", "evidence": "Skills: ...SQL...Git..."}
            ],
            "weaknesses": [
                {"point": "Lack of Flask or FastAPI experience", "evidence": "Resume does not mention Flask or FastAPI"},
                {"point": "Overqualified for junior role", "evidence": "Developer Manager & Product Owner roles"}
            ],
            "reasoning": "Has Python, SQL, and Git skills but missing Flask/FastAPI...",
            "experience_match": "partial",
            "skills_match": "partial",
            "model_used": "gpt-4o"
        }
    ]
}
```

### Step 4: List All Resumes

See all uploaded resumes:

```bash
curl -s http://localhost:8000/api/v1/resumes | python3 -m json.tool
```

### Step 5: Screen Multiple Resumes Against a Job

After uploading multiple resumes, screen them all at once:

```bash
curl -s -X POST http://localhost:8000/api/v1/screen \
  -H "Content-Type: application/json" \
  -d '{"job_id": "<job-id>"}' | python3 -m json.tool
```

This screens all uploaded resumes against the job and returns them ranked
by score (highest first).

### Step 6: View Screening Results

Get all previously computed results for a job:

```bash
curl -s http://localhost:8000/api/v1/results/<job-id> | python3 -m json.tool
```

Returns all candidates ranked by score with their strengths, weaknesses,
and reasoning.

### Step 7: Submit Feedback on an AI Score

Rate how accurate an AI score was (1-5). Use the result `id` from Step 6.

```bash
curl -s -X POST http://localhost:8000/api/v1/results/<result-id>/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 4,
    "notes": "Good assessment, matched my own evaluation"
  }' | python3 -m json.tool
```

---

## API Endpoints Summary

| Method | Endpoint | What It Does |
|--------|----------|-------------|
| POST | `/api/v1/jobs` | Create a new job |
| GET | `/api/v1/jobs` | List all jobs |
| GET | `/api/v1/jobs/{job_id}` | Get a specific job |
| POST | `/api/v1/resumes/upload-pdf` | Upload PDF + screen against a job (one call) |
| POST | `/api/v1/resumes` | Upload resume as text |
| GET | `/api/v1/resumes` | List all resumes |
| POST | `/api/v1/screen` | Screen all resumes against a job |
| GET | `/api/v1/results/{job_id}` | Get screening results for a job |
| POST | `/api/v1/results/{result_id}/feedback` | Rate an AI score (1-5) |
| GET | `/health` | Health check |

---

## What the AI Returns

Each screening result includes:

| Field | Description |
|-------|-------------|
| `score` | 0-100, how well the candidate fits the job |
| `strengths` | What matches, with evidence quoted from the resume |
| `weaknesses` | What's missing or mismatched |
| `reasoning` | 2-3 sentence summary explaining the score |
| `experience_match` | none, partial, or strong |
| `skills_match` | none, partial, or strong |
| `model_used` | Which LLM was used (gpt-4o) |

## Cost Controls

4 layers to minimize OpenAI API costs:

1. **Vector pre-filter**: Only send semantically similar resumes to GPT-4o
2. **RAG chunking**: Send only relevant chunks, not the entire resume
3. **Redis cache**: Same job+resume pair returns cached result for 24 hours
4. **Budget limits**: Per-tenant monthly cap on LLM calls (default: 1000/month)

---

## Design Decisions (Detailed)

Full design documents are in `/docs/`. Below is a summary of each section.

### A1: Problem Framing -- Why Use AI Instead of Rules?

**Target users:** Non-technical HR recruiters who review 50-200+ resumes per role.
They need ranked candidate lists with plain-English reasoning.

**Why rules don't work:**
- Job descriptions are unstructured natural language with inconsistent phrasing
- Resumes have wildly different formats and section names
- Skill inference matters: an LLM understands that "Kafka and Spark experience" implies
  distributed systems knowledge, even if those exact words aren't in the job description
- Context matters: "3 years experience" is strong for a junior role but weak for a staff role
- Recruiters need to understand *why* a candidate scored high or low -- rules can't explain

**Why LLMs work here:**
- Can read unstructured text (both JDs and resumes)
- Can infer skills and experience from context
- Can produce structured, evidence-backed explanations
- Scoring quality is good enough for initial screening (humans still make final decisions)

### A2: System Architecture

```
                    ┌─────────────┐
                    │   FastAPI    │
                    │   (Port 8000)│
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     ┌────▼────┐    ┌─────▼─────┐    ┌─────▼─────┐
     │PostgreSQL│    │   Redis    │    │  Qdrant   │
     │  (5432)  │    │  (6379)    │    │  (6333)   │
     └─────────┘    └───────────┘    └───────────┘
     Jobs, Resumes   Score cache      Resume chunk
     Results,        Budget tracking  vectors for
     Feedback        Rate limiting    semantic search
                           │
                    ┌──────▼──────┐
                    │  OpenAI API  │
                    │ GPT-4o +     │
                    │ Embeddings   │
                    └─────────────┘
```

**Screening flow:** Load job → embed it → find top-N similar resumes via Qdrant →
check Redis cache → call GPT-4o if cache miss → parse JSON → store in PostgreSQL

**Multi-tenant isolation:** Every database query, vector search, and cache key is
scoped by `tenant_id`. No tenant can see another tenant's data.

### A3: Data Model

5 PostgreSQL tables, all with `tenant_id` for isolation:

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| `tenants` | name, plan, llm_budget | Tenant config |
| `jobs` | title, description, requirements (JSONB), embedding_id | Job descriptions |
| `resumes` | candidate_name, email, raw_text, embedding_id | Uploaded resumes |
| `screening_results` | job_id, resume_id, score (0-100), strengths/weaknesses (JSONB), reasoning, model_used, prompt_version | AI scoring results |
| `screening_feedback` | result_id, rating (1-5), notes | Human feedback on AI scores |

**Constraints:** Score must be 0-100. Rating must be 1-5. Each job+resume pair can only
have one screening result (UNIQUE constraint).

### A4: Prompt Design

The LLM prompt has two parts:

**System prompt** (sets behavior): Be an expert HR screening assistant. Score 0-100.
Cite evidence. Ignore protected characteristics. Output only JSON.

**User prompt** (per request): Receives the job description and resume text.
Must return structured JSON with score, strengths, weaknesses, reasoning,
experience_match, and skills_match.

**Why this design:**
- Evidence-backed: each strength/weakness cites specific resume content
- Parseable: strict JSON validated by Pydantic (>99% parse rate)
- Auditable: prompt_version stored with every result for A/B testing
- Bias guardrails: explicit instruction to ignore age, gender, race, religion

See `AI_PROMPTS.md` for prompt iterations and design principles.

### B1: RAG Design -- How Vector Search Works

**The pipeline:**

```
PDF Upload:                          Screening:
text → chunks (500 chars) →          job description → embed →
embed each chunk (OpenAI) →          query Qdrant for similar chunks →
store in Qdrant with metadata        retrieve top-5 relevant chunks →
                                     send chunks + JD to GPT-4o
```

**Why chunking:** Resumes have different sections (skills, experience, education).
Chunking lets Qdrant find the most relevant *sections* for each job, not just
match the whole document. A Python job retrieves the skills/experience chunks,
not the education section.

**Tenant isolation in vectors:** Every Qdrant search includes a mandatory
`tenant_id` filter. There is no code path that queries vectors without tenant filtering.

**Cost impact:** Without pre-filter: 200 resumes x $0.003 = $0.60 per screening.
With vector pre-filter (top-50): $0.15. That's a **75% cost reduction**.

### C1: Cost Control Strategy

4 layers to minimize OpenAI costs:

| Layer | What It Does | Savings |
|-------|-------------|---------|
| **Vector pre-filter** | Only score semantically similar resumes | ~75% fewer LLM calls |
| **RAG chunking** | Send relevant chunks, not full text | ~30% fewer tokens per call |
| **Redis cache** | Cache scores by JD content hash (24h TTL) | 100% on repeat queries |
| **Tenant budgets** | Monthly cap on LLM calls per tenant (default: 1000) | Prevents runaway costs |

**When NOT to use AI:** Exact-match queries (has Python? yes/no), simple filters,
binary checks -- use SQL instead of burning LLM tokens.

### C2: Output Evaluation -- How We Know the AI Is Good

4 quality mechanisms:

1. **Automated validation:** Every LLM response is parsed through Pydantic.
   Score must be 0-100, match fields must be none/partial/strong. Parse failures are logged.

2. **Score distribution monitoring:** Scores stored with model_used and prompt_version.
   A healthy distribution shows differentiation (not all 70s). Compare across prompt versions.

3. **Human feedback loop:** `POST /results/{id}/feedback` lets recruiters rate scores 1-5.
   Target: >80% of scores rated 4 or 5. Disagreements reveal systematic blind spots.

4. **Outcome tracking (future):** Did the top-scored candidate get hired? This is the
   highest-value signal 

### E: Execution Reality Check

**What shipped:**
- Resume upload (PDF + text) with real embedding pipeline
- Job creation with vector embedding
- LLM screening with structured JSON output (GPT-4o via LangChain)
- RAG pipeline: chunking, real OpenAI embeddings, Qdrant storage and retrieval
- Vector pre-filter for cost control
- Redis caching with JD-hash invalidation
- Multi-tenant isolation
- Human feedback endpoint
- Docker Compose with 4 services
- Swagger UI with pre-filled examples

**Not in v1 (deferred):**
- Frontend (API-first, use Swagger UI for demo)
- Async job queue (sync is fine for <50 resumes)
- Alembic migrations (using create_all)
- Model fine-tuning (need 500+ feedback data points first)

**Top risks and mitigations:**

| Risk | Mitigation |
|------|-----------|
| LLM scoring inconsistency (same resume scores 70 vs 78) | temperature=0, caching, human feedback |
| Bias in AI screening | Bias guardrails in prompt, score distribution audits, humans make final call |
| Cost runaway (10K resumes) | Per-tenant budgets, vector pre-filter, 50-resume cap per call |
| Prompt injection via resume | Structured JSON format limits attack surface, explicit system prompt constraints |

---

## What I Would Improve With More Time

- **Async job queue**: Move screening to background workers (Celery/Redis Streams)
- **Alembic migrations**: Replace `create_all` with proper migration management
- **Prompt A/B testing**: Compare scoring quality across prompt versions
- **Rate limiting middleware**: Per-tenant request throttling
- **Observability**: Structured logging, OpenTelemetry traces, Prometheus metrics
- **Frontend**: React dashboard for recruiters to view/filter/give feedback on results
