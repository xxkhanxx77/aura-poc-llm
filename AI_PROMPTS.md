# AI_PROMPTS.md -- Prompt Engineering Documentation

## Resume Screening Prompt (v1.0)

### System Prompt

```
You are an expert HR screening assistant. Your job is to evaluate a candidate's
resume against a specific job description and provide a structured assessment.

Rules:
- Score from 0-100 based on fit to the job requirements
- Be specific: cite exact resume lines when noting strengths or weaknesses
- Do not penalize for formatting -- focus on substance
- If the resume is unclear or incomplete, note it but do not assume the worst
- Never include protected characteristics (age, gender, race, religion, etc.) in your reasoning
- Output ONLY valid JSON matching the specified structure. No markdown, no extra text.
```

### User Prompt Template

```
## Job Description
Title: {job_title}

Requirements:
{job_description}

## Candidate Resume
{resume_text}

## Instructions
Evaluate this candidate against the job description above. Return your assessment
as JSON with this exact structure:

{
  "score": <integer 0-100>,
  "strengths": [
    {"point": "<specific strength>", "evidence": "<quote or reference from resume>"}
  ],
  "weaknesses": [
    {"point": "<specific gap>", "evidence": "<what's missing or mismatched>"}
  ],
  "reasoning": "<2-3 sentence overall assessment explaining the score>",
  "experience_match": "<none|partial|strong>",
  "skills_match": "<none|partial|strong>"
}
```

## Prompt Design Iterations

### Iteration 1: Free-form output (rejected)

**Approach:** Asked the LLM to "evaluate this resume and give a score."

**Problem:** Output was inconsistent -- sometimes a paragraph, sometimes bullet points,
sometimes with a score, sometimes without. Impossible to parse programmatically.

**Example rejected output:**
```
This candidate looks strong! They have good Python experience and worked at
reputable companies. I'd give them about a 75-80. Main concern is limited
Kubernetes experience.
```

**Why rejected:** Not parseable. No structured strengths/weaknesses. Score is a range
not a number. No evidence citations. Can't store in DB or render in UI consistently.

### Iteration 2: JSON output without evidence (rejected)

**Approach:** Required JSON with `score`, `strengths` (string list), `weaknesses` (string list).

**Problem:** Strengths like "good communication skills" with no evidence are not
useful to recruiters. They need to know *what in the resume* supports the claim.

**Example rejected output:**
```json
{
  "score": 72,
  "strengths": ["Python experience", "team leadership"],
  "weaknesses": ["no Kubernetes"]
}
```

**Why rejected:** No evidence trail. Recruiter can't verify the AI's claims without
re-reading the entire resume. Not explainable to hiring managers.

### Iteration 3: Current design (accepted)

**Approach:** Each strength/weakness is a `{point, evidence}` pair. Added
`experience_match` and `skills_match` enums for quick filtering. Added `reasoning`
for a human-readable summary.

**Why accepted:**
- **Parseable**: Strict JSON validated by Pydantic. Parse failures are caught and logged.
- **Explainable**: Evidence field cites specific resume content. Recruiter can verify.
- **Filterable**: Enum fields (`none/partial/strong`) enable quick UI sorts.
- **Auditable**: Full reasoning stored with `model_used` and `prompt_version`.

### Iteration 4: Bias guardrails added

After testing iteration 3, we found the model occasionally referenced graduation
year (proxy for age) in its reasoning. Added explicit instruction:

```
Never include protected characteristics (age, gender, race, religion, etc.) in your reasoning
```

This is not foolproof but establishes a baseline. For production, we would add
post-processing checks to flag results that mention protected categories.

## Prompt Design Principles

1. **JSON-only output instruction** -- "Output ONLY valid JSON." Prevents the model
   from adding preamble text that breaks JSON parsing. Saves output tokens.

2. **Evidence-backed claims** -- Requiring `evidence` for each point forces the model
   to ground its assessment in actual resume content, reducing hallucination.

3. **Bounded enums** -- `experience_match` and `skills_match` use `none|partial|strong`
   rather than free-form text. Prevents creative but unparseable answers.

4. **System vs user prompt separation** -- Rules and persona go in the system prompt
   (persistent context). Job-specific data goes in the user prompt (per-request).
   This keeps the system prompt stable for caching and versioning.

5. **Prompt versioning** -- `PROMPT_VERSION = "v1.0"` is stored with every result.
   When we ship v1.1 (e.g., adding "culture fit" as a scoring dimension), we can
   compare score distributions between versions to detect drift.

## Model Selection

| Model | Tested | Result |
|-------|--------|--------|
| GPT-4o | Yes (current) | Reliable JSON output, good reasoning, best quality |
| GPT-4o-mini | Considered | Cheaper but less nuanced reasoning |
| Claude Sonnet | Considered | Similar quality; switched to OpenAI for unified embedding + LLM |

We chose GPT-4o via LangChain because:
- Structured JSON output is reliable (>99% parse rate in testing)
- Reasoning quality is strong for screening tasks
- Same vendor (OpenAI) for both embeddings and LLM simplifies the stack
- LangChain abstraction makes it easy to swap models later
