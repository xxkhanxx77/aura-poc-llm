"""Tests for prompt construction -- ensures prompts are well-formed and versioned."""

from app.prompts.resume_screening import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_screening_prompt,
)


def test_prompt_version_format():
    assert PROMPT_VERSION.startswith("v")
    assert "." in PROMPT_VERSION


def test_system_prompt_has_bias_guardrails():
    assert "protected characteristics" in SYSTEM_PROMPT.lower()
    assert "JSON" in SYSTEM_PROMPT


def test_system_prompt_requires_json_only():
    assert "ONLY" in SYSTEM_PROMPT
    assert "No markdown" in SYSTEM_PROMPT or "No other text" in SYSTEM_PROMPT


def test_build_screening_prompt_substitutes_values():
    system, user = build_screening_prompt(
        job_title="Senior Engineer",
        job_description="5 years Python required",
        resume_text="Jane Doe, 7 years Python experience",
    )
    assert "Senior Engineer" in user
    assert "5 years Python required" in user
    assert "Jane Doe" in user
    assert system == SYSTEM_PROMPT


def test_build_screening_prompt_preserves_json_template():
    """The output format instructions must survive .format() without breaking."""
    _, user = build_screening_prompt(
        job_title="Test",
        job_description="Test desc",
        resume_text="Test resume",
    )
    # The JSON template uses {{ }} to escape braces in .format()
    assert '"score"' in user
    assert '"strengths"' in user
    assert '"weaknesses"' in user
    assert '"reasoning"' in user
