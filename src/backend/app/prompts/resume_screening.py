"""Prompt templates for resume screening.

Versioned so we can track which prompt produced which scores.
"""

PROMPT_VERSION = "v1.0"

SYSTEM_PROMPT = """\
You are an expert HR screening assistant. Your job is to evaluate a candidate's \
resume against a specific job description and provide a structured assessment.

Rules:
- Score from 0-100 based on fit to the job requirements
- Be specific: cite exact resume lines when noting strengths or weaknesses
- Do not penalize for formatting -- focus on substance
- If the resume is unclear or incomplete, note it but do not assume the worst
- Never include protected characteristics (age, gender, race, religion, etc.) in your reasoning
- Output ONLY valid JSON matching the specified structure. No markdown, no extra text."""

USER_PROMPT_TEMPLATE = """\
## Job Description
Title: {job_title}

Requirements:
{job_description}

## Candidate Resume
{resume_text}

## Instructions
Evaluate this candidate against the job description above. Return your assessment \
as JSON with this exact structure:

{{
  "score": <integer 0-100>,
  "strengths": [
    {{"point": "<specific strength>", "evidence": "<quote or reference from resume>"}}
  ],
  "weaknesses": [
    {{"point": "<specific gap>", "evidence": "<what's missing or mismatched>"}}
  ],
  "reasoning": "<2-3 sentence overall assessment explaining the score>",
  "experience_match": "<none|partial|strong>",
  "skills_match": "<none|partial|strong>"
}}"""


def build_screening_prompt(
    job_title: str,
    job_description: str,
    resume_text: str,
) -> tuple[str, str]:
    """Build system + user prompts for a screening call.

    Returns (system_prompt, user_prompt).
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        job_title=job_title,
        job_description=job_description,
        resume_text=resume_text,
    )
    return SYSTEM_PROMPT, user_prompt
