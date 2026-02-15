# Scoring Flow: How Candidates Get Scored

## Overview

When a recruiter triggers screening (`POST /api/v1/screen`), each candidate's resume is scored 0-100 against the job description using GPT-4o via LangChain. The score reflects how well the candidate fits the specific job requirements.

## End-to-End Flow

```
Recruiter clicks "Screen"
        │
        ▼
┌─────────────────────┐
│ 1. Load Job          │  Load job description + requirements (tenant-scoped)
│    Description       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 2. Find Candidates   │  Vector similarity search in Qdrant OR use provided resume_ids
│    (Pre-filter)      │  Reduces LLM calls by ~75% (cost control)
└────────┬────────────┘
         │
         ▼
   ┌─────┴─────┐
   │ For each   │
   │ resume:    │
   └─────┬─────┘
         │
         ▼
┌─────────────────────┐
│ 3. Check Cache       │  Redis lookup by tenant + job + resume + JD hash
│    (Redis)           │  If hit → skip LLM, return cached score
└────────┬────────────┘
         │ cache miss
         ▼
┌─────────────────────┐
│ 4. Budget Check      │  Verify tenant hasn't exceeded monthly LLM call limit
│    (Redis)           │  If exceeded → raise error
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 5. LLM Scoring       │  Send system prompt + job desc + resume to GPT-4o
│    (LangChain/GPT-4o)│  Receive structured JSON response
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 6. Parse & Validate  │  Parse JSON → validate with Pydantic ScreeningScore model
│    (Pydantic)        │  Ensures score 0-100, required fields present
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 7. Cache + Persist   │  Cache in Redis (24h TTL) + save to PostgreSQL
│    (Redis + Postgres)│
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 8. Return Ranked     │  Sort all results by score descending
│    Results           │  Return to recruiter
└─────────────────────┘
```

## What GPT-4o Evaluates

The LLM receives two prompts:

### System Prompt (sets behavior)
- Act as an expert HR screening assistant
- Score 0-100 based on fit to job requirements
- Cite specific resume lines as evidence
- Focus on substance, not formatting
- Never consider protected characteristics (age, gender, race, religion)
- Output only valid JSON

### User Prompt (the actual evaluation)
The LLM receives the full job description and the full resume text, then evaluates:

| Criteria | What It Measures | Output Field |
|----------|-----------------|--------------|
| **Overall Score** | How well the candidate fits the job (0-100) | `score` |
| **Strengths** | Specific qualifications that match the job | `strengths[]` with `point` + `evidence` |
| **Weaknesses** | Gaps or mismatches vs. job requirements | `weaknesses[]` with `point` + `evidence` |
| **Experience Match** | Years + relevance of work history | `experience_match`: none / partial / strong |
| **Skills Match** | Technical skills alignment | `skills_match`: none / partial / strong |
| **Reasoning** | 2-3 sentence human-readable summary | `reasoning` |

## Score Breakdown (What Drives the 0-100 Score)

The score is holistic -- GPT-4o weighs these factors against the specific job description:

| Factor | Impact | Example |
|--------|--------|---------|
| **Required skills match** | High | JD asks for Python + PostgreSQL, resume has both → higher score |
| **Years of experience** | High | JD asks for 5+ years, candidate has 7 → strong; has 2 → weak |
| **Relevant work history** | High | Built similar systems at similar companies → higher score |
| **Nice-to-have skills** | Medium | JD lists Kafka as nice-to-have, candidate has it → bonus |
| **Leadership/mentoring** | Medium | If JD asks for it, experience mentoring → higher score |
| **Missing requirements** | Negative | Each missing "must-have" skill reduces the score |
| **Career trajectory** | Low | Progression from junior to senior shows growth |

### Score Ranges

| Range | Meaning | Typical Profile |
|-------|---------|-----------------|
| **90-100** | Exceptional fit | Matches all requirements + nice-to-haves |
| **75-89** | Strong fit | Matches most requirements, minor gaps |
| **60-74** | Moderate fit | Has core skills but missing some requirements |
| **40-59** | Weak fit | Some relevant experience but significant gaps |
| **0-39** | Poor fit | Doesn't match the job requirements |

## Real Example

**Job**: Senior Backend Engineer (Python, PostgreSQL, Redis, Docker, K8s)

**Candidate: Alice Chen (Score: 95)**
```
Strengths:
  - "Extensive backend development experience"
    Evidence: "Senior Backend Engineer at Stripe (2020-2024), Backend Engineer at Dropbox (2017-2020)"
  - "Strong Python skills with relevant frameworks"
    Evidence: "Built payment processing microservices in Python (FastAPI)"
  - "Experience with PostgreSQL and Redis"
    Evidence: "Designed PostgreSQL schemas handling 10M+ transactions/day"

Weaknesses:
  - "No machine learning / AI integration experience"
    Evidence: "No mention of ML/AI in resume"

Experience Match: strong
Skills Match: strong
```

**Candidate: Bob Martinez (Score: 40)**
```
Strengths:
  - "Experience with Python Flask"
    Evidence: "Some backend work with Python Flask for internal tools"

Weaknesses:
  - "Lack of 5+ years backend experience"
    Evidence: "Total professional experience ~4 years, limited backend focus"
  - "Limited required technologies"
    Evidence: "No mention of PostgreSQL, Docker, Kubernetes, or RESTful APIs at scale"

Experience Match: partial
Skills Match: partial
```

## Key Design Decisions

1. **Evidence-based scoring**: Every strength/weakness must cite the resume. This makes scores explainable to recruiters -- they can see *why* the AI gave a score.

2. **Job-specific, not generic**: The score is always relative to a specific job description. The same candidate may score 95 for one role and 40 for another.

3. **Bias guardrails**: The system prompt explicitly forbids considering protected characteristics. Not foolproof, but establishes baseline behavior.

4. **Prompt versioning**: Every result stores `prompt_version` and `model_used`. When we update prompts, we can compare scoring patterns between versions (A/B testing).

5. **Human feedback loop**: Recruiters can rate AI scores 1-5 via `POST /results/{id}/feedback`. Over time, this data reveals if the AI over/under-scores certain profiles.

## Cost Controls

| Layer | What It Does |
|-------|-------------|
| **Vector pre-filter** | Only send top-N similar resumes to LLM (not all resumes) |
| **Redis cache** | Same job+resume combo → cached for 24 hours, no repeat LLM call |
| **Budget limits** | Per-tenant monthly cap on LLM calls (default: 1000/month) |
| **Token tracking** | Track total tokens per tenant for billing visibility |

## Files Involved

| File | Role |
|------|------|
| `app/services/screening_service.py` | Orchestrator -- ties everything together |
| `app/services/llm_service.py` | LangChain + GPT-4o integration, budget checks |
| `app/prompts/resume_screening.py` | Prompt templates (versioned) |
| `app/services/vector_service.py` | Qdrant similarity search (pre-filter) |
| `app/services/cache_service.py` | Redis caching layer |
| `app/models/schemas.py` | Pydantic models for score validation |
