# A4 -- Prompt Design

## Resume Screening Prompt

### System Prompt

```
You are an expert HR screening assistant. Your job is to evaluate a candidate's
resume against a specific job description and provide a structured assessment.

Rules:
- Score from 0-100 based on fit to the job requirements
- Be specific: cite exact resume lines when noting strengths or weaknesses
- Do not penalize for formatting -- focus on substance
- If the resume is unclear or incomplete, note it but do not assume the worst
- Never include protected characteristics (age, gender, race, etc.) in your reasoning
- Output ONLY the JSON structure specified below. No other text.
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

### Example Output

```json
{
  "score": 78,
  "strengths": [
    {
      "point": "Strong Python backend experience",
      "evidence": "Resume states '5 years building Python microservices with FastAPI and Django'"
    },
    {
      "point": "Team leadership experience",
      "evidence": "Led team of 6 engineers on payment processing rewrite"
    }
  ],
  "weaknesses": [
    {
      "point": "No Kubernetes experience listed",
      "evidence": "JD requires 'production Kubernetes experience' but resume only mentions Docker"
    },
    {
      "point": "Limited data pipeline experience",
      "evidence": "JD requires Kafka/streaming; resume shows only batch processing with Airflow"
    }
  ],
  "reasoning": "Strong backend engineer with relevant Python experience and leadership skills. The gaps in Kubernetes and streaming infrastructure are notable given the JD's emphasis on cloud-native architecture, but the candidate's strong fundamentals suggest they could ramp up. Score reflects solid core match with specific technical gaps.",
  "experience_match": "strong",
  "skills_match": "partial"
}
```

## Why This Structure

1. **Structured JSON output**: Parseable by code, storable in DB, renderable in UI.
   No regex extraction needed. We validate against a Pydantic model on response.

2. **Evidence-backed points**: Each strength/weakness cites specific resume content.
   This makes the output explainable to HR users ("the AI said this *because*...").

3. **Bias guardrails in system prompt**: Explicit instruction to ignore protected
   characteristics. Not foolproof, but establishes baseline behavior.

4. **Separate match dimensions**: `experience_match` and `skills_match` give the UI
   quick filter/sort options beyond the single score.

5. **Reasoning field**: Human-readable summary for the recruiter who doesn't want
   to read individual strength/weakness bullets.

6. **Prompt versioning**: We store `prompt_version` with each result so we can
   track scoring drift when prompts change. Enables A/B testing prompts.
