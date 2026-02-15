# A2 -- System Architecture: AI Resume Screening Tool

## High-Level Architecture

```
                        +------------------+
                        |   Frontend (React) |
                        +--------+---------+
                                 |
                                 | REST/JSON
                                 v
                   +-------------+-------------+
                   |     API Gateway /  Autn    |
                   ( focus on features first)
                   |  (JWT + TenantId in token) |
                   +-------------+-------------+
                                 |
                                 v
              +------------------+------------------+
              |          FastAPI Application         |
              |                                      |
              |  /jobs      -- CRUD job descriptions |
              |  /resumes   -- upload + parse         |
              |  /screen    -- trigger screening      |
              |  /results   -- fetch scores/reasons   |
              +--+--------+--------+--------+--------+
                 |        |        |        |
                 v        v        v        v
           +------+  +------+  +------+  +------+
           |Postgres| |Redis | |Qdrant | |OpenAI|
           |        | |      | |(Vec)  | |GPT-4o |
           +--------+ +------+ +------+ +-------+
```

## Component Responsibilities

### API Layer (FastAPI)
- JWT auth middleware(if have authen for now i remove for easy demo) extracts `tenant_id` from token on every request
- All DB queries are scoped by `tenant_id` -- no exceptions
- Rate limiting per tenant via Redis
- Request validation with Pydantic models

### PostgreSQL
- Stores structured data: tenants, jobs, resumes (metadata), screening results
- Row-level tenant isolation via `tenant_id` FK on every table
- Stores LLM responses for audit trail and re-scoring

### Redis
- **Caching**: Parsed resume text (avoid re-parsing on each screen)
- **Rate limiting**: Per-tenant LLM call budget tracking
- **Job queue**: Screening tasks dispatched via Redis streams
- Keys namespaced by tenant: `tenant:{id}:resume:{hash}`

### Qdrant (Vector DB)
- Stores resume embeddings for semantic similarity search
- Collections partitioned by tenant (payload filter on `tenant_id`)
- Used to pre-filter candidates before expensive LLM scoring
- Flow: embed JD -> find top-N similar resumes -> only score those with LLM

### LLM Integration (LangChain + OpenAI GPT-4o)
- **Embedding model**: OpenAI `text-embedding-3-small` for resume/JD vectorization (cheap, fast, 1536 dims)
- **Scoring model**: GPT-4o via LangChain for structured candidate evaluation
- Prompt layer abstracts model choice (swap without code changes)
- Cost control: vector pre-filter reduces LLM calls by ~70%

## Request Flow: Screen Candidates

1. User hits `POST /screen` with `job_id`
2. API fetches JD from Postgres (tenant-scoped)
3. JD is embedded -> Qdrant similarity search returns top-N resume IDs
4. For each candidate resume:
   a. Check Redis cache for existing score (same JD version)
   b. If miss: build prompt (JD + resume text) -> call LLM
   c. Parse structured JSON response -> store in Postgres
   d. Cache result in Redis (TTL: 24h)
5. Return ranked results with scores + reasoning

## Cost Control Strategy

| Technique              | Savings     |
|------------------------|-------------|
| Vector pre-filter      | ~70% fewer LLM calls |
| Redis result caching   | Eliminates duplicate screens |
| Tenant rate limits     | Prevents runaway costs |
| GPT-4o (cost-effective) | Cheaper than GPT-4 Turbo with better performance |
| Structured output      | Fewer retries from bad format |
