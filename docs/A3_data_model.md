# A3 -- Data Model

## Tenant Isolation Strategy

Every table includes a `tenant_id` column. All queries go through a repository layer
that injects `WHERE tenant_id = :tid` automatically. There is no path to query data
without a tenant context.

## PostgreSQL Schemas

```sql
-- Tenants
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'standard',  -- controls LLM budget
    llm_budget  INTEGER NOT NULL DEFAULT 1000,     -- monthly LLM call limit
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Job descriptions
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL,              -- raw JD text
    requirements JSONB NOT NULL DEFAULT '[]', -- extracted must-haves
    embedding_id TEXT,                       -- Qdrant point ID for JD vector
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_jobs_tenant ON jobs(tenant_id);

-- Resumes
CREATE TABLE resumes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    candidate_name TEXT NOT NULL,
    email       TEXT,
    raw_text    TEXT NOT NULL,               -- extracted resume text
    parsed_data JSONB,                       -- structured extraction
    embedding_id TEXT,                       -- Qdrant point ID
    uploaded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_resumes_tenant ON resumes(tenant_id);

-- Screening results (AI outputs)
CREATE TABLE screening_results (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    job_id      UUID NOT NULL REFERENCES jobs(id),
    resume_id   UUID NOT NULL REFERENCES resumes(id),
    score       INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    strengths   JSONB NOT NULL DEFAULT '[]',
    weaknesses  JSONB NOT NULL DEFAULT '[]',
    reasoning   TEXT NOT NULL,               -- full LLM reasoning
    model_used  TEXT NOT NULL,               -- e.g. 'gpt-4o'
    prompt_version TEXT NOT NULL,            -- track which prompt generated this
    tokens_used INTEGER,                     -- for cost tracking
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(job_id, resume_id)               -- one score per resume per job
);
CREATE INDEX idx_results_tenant_job ON screening_results(tenant_id, job_id);
```

## TenantId Enforcement

Enforced at three levels:

1. **API middleware**: Extracts `tenant_id` from JWT, attaches to request state
2. **Repository layer**: Every query method requires `tenant_id` parameter
3. **DB constraint**: Foreign key to `tenants(id)` on every row

```python
# Example: no way to call this without tenant context
class ResumeRepository:
    async def get_by_id(self, tenant_id: UUID, resume_id: UUID) -> Resume:
        return await self.db.fetch_one(
            "SELECT * FROM resumes WHERE id = :rid AND tenant_id = :tid",
            {"rid": resume_id, "tid": tenant_id}
        )
```
