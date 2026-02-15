# C2 -- Output Evaluation Strategy

## How We Measure AI Output Quality

### 1. Structured Output Validation (Automated)

Every LLM response is parsed through a strict Pydantic model (`ScreeningScore`):

- `score` must be 0-100 (integer)
- `experience_match` and `skills_match` must be "none", "partial", or "strong"
- `strengths` and `weaknesses` must each contain `point` + `evidence` fields
- If parsing fails, the call is logged and retried or flagged

**Parse failure rate** is tracked as a quality signal. A spike in failures suggests
the prompt needs adjustment or the model is behaving unexpectedly.

### 2. Score Distribution Monitoring

We store every score in PostgreSQL with `model_used` and `prompt_version`. This enables:

- **Distribution analysis**: Are scores normally distributed? A flat distribution
  suggests the model isn't differentiating well. A bimodal distribution is healthy
  (clear strong/weak candidates).
- **Prompt version comparison**: When we ship prompt v1.1, we can compare score
  distributions against v1.0 to detect drift.
- **Per-tenant patterns**: If one tenant's scores are all 90+, their JD may be
  too generic.

### 3. Human Feedback Loop

We provide a `POST /api/v1/results/{result_id}/feedback` endpoint where HR users
can rate each AI assessment:

```json
{
  "rating": 4,
  "notes": "Score was fair but missed that the candidate has relevant startup experience"
}
```

This feedback is stored in a `screening_feedback` table and enables:

- **Agreement rate**: % of scores where human rating >= 4 (out of 5)
- **Disagreement analysis**: When humans rate low, what did the AI miss?
  Group by weakness type to find systematic blind spots.
- **Prompt iteration**: Concrete examples of "AI said X, human said Y" drive
  targeted prompt improvements.

### 4. Outcome Tracking (Future)

The highest-value quality signal: **did the candidate get hired?**

When the hiring decision is recorded (integration with the ATS), we can measure:
- Did the AI's top-10 include the eventual hire?
- What was the hired candidate's AI score?
- False negative rate: strong candidates scored low by AI

This requires ATS integration and is out of scope for v1, but the schema supports
it (add `hired_at` to screening_results or a separate `hiring_outcomes` table).

## How Humans Give Feedback

The feedback flow is intentionally lightweight to maximize adoption:

1. HR user views screening results in the UI
2. Each candidate card shows score + reasoning
3. A simple thumbs-up/thumbs-down (mapped to 1-5 scale) with optional text note
4. Feedback is stored immediately -- no batch submission required

**Key design choice:** Feedback is per-result, not per-screening-run. This gives us
granular signal on individual AI assessments rather than aggregate "this batch was good."

## Quality Dashboard (Future)

Metrics to surface:
- Parse failure rate (should be < 1%)
- Human agreement rate (target: > 80%)
- Score distribution per prompt version
- Average tokens per call (cost efficiency)
- Top disagreement patterns (drives prompt improvements)
