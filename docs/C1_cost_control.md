# C1 -- Cost Control Strategy

## The Problem

LLM calls are expensive. In a multi-tenant B2B SaaS, uncontrolled usage by one tenant
can blow the entire infrastructure budget. Our cost controls operate at four layers.

## Layer 1: Avoid the LLM Call Entirely

**Vector pre-filter** -- Instead of scoring all 200 resumes with the LLM, embed the
job description, find the top-50 semantically similar resumes via Qdrant, and only
score those. This cuts LLM calls by ~75%.

**Redis result cache** -- If we've already scored resume R against job J (same JD text),
return the cached result. Cache key includes a SHA-256 hash of the JD content, so editing
the job description automatically invalidates stale scores.

```
Cache key: tenant:{tid}:screen:{job_id}:{resume_id}:{jd_hash}
TTL: 24 hours
```

**When AI should NOT be used:**
- Exact-match queries ("show me all candidates named John Smith") → SQL query
- Simple filters ("resumes uploaded this week") → SQL query
- Binary checks ("does this resume mention Python?") → keyword search
- The LLM is reserved for *judgment* tasks: scoring fit, summarizing strengths/weaknesses

## Layer 2: Choose the Right Model

| Task | Model | Cost/1K tokens | Why |
|------|-------|----------------|-----|
| Resume scoring | GPT-4o via LangChain | ~$0.0025 input / $0.01 output | Best price-to-performance ratio; structured JSON output is reliable |
| Embedding | text-embedding-3-small | ~$0.00002 | Cheapest OpenAI embedding; 1536 dims is sufficient for document-level similarity |

We could escalate to GPT-4 Turbo or o1 for edge cases (e.g., very senior roles where
scoring nuance matters more), and this would be a per-tenant configuration option.
LangChain abstracts the model choice, so swapping models requires changing only `config.py`.

## Layer 3: Tenant Budget Enforcement

Each tenant has a monthly LLM call budget tracked in Redis:

```python
key = f"tenant:{tenant_id}:llm_calls_month"
# Incremented on each LLM call, checked before each call
# Key expires after ~31 days (auto-reset)
```

Token usage is also tracked separately for billing:

```python
token_key = f"tenant:{tenant_id}:tokens_month"
```

If a tenant exceeds their budget, the screening endpoint returns a 400 error
with a clear message. The tenant can upgrade their plan for a higher limit.

**Default budget:** 1000 LLM calls/month (configurable per tenant via `tenants.llm_budget`)

## Layer 4: Reduce Tokens Per Call

- **Structured JSON output** -- Forces concise responses, no verbose prose
- **max_tokens: 1500** -- Hard cap on response length
- **System prompt says "Output ONLY valid JSON"** -- Prevents preamble/explanation text
  that wastes tokens
- **Resume text is sent as-is** -- No expensive pre-processing; the LLM handles messy input
