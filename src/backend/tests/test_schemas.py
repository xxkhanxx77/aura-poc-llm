"""Tests for Pydantic schema validation -- the parsing layer between LLM output and our DB."""

import json

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    JobCreate,
    MatchLevel,
    ResumeCreate,
    ScreeningScore,
    StrengthWeakness,
)


class TestScreeningScore:
    """Validate that LLM output parsing works correctly."""

    def test_valid_score_parses(self):
        raw = {
            "score": 78,
            "strengths": [
                {"point": "Strong Python", "evidence": "5 years FastAPI experience"}
            ],
            "weaknesses": [
                {"point": "No K8s", "evidence": "Only mentions Docker"}
            ],
            "reasoning": "Solid backend engineer with gaps in cloud-native.",
            "experience_match": "strong",
            "skills_match": "partial",
        }
        score = ScreeningScore.model_validate(raw)
        assert score.score == 78
        assert len(score.strengths) == 1
        assert score.experience_match == MatchLevel.strong

    def test_score_out_of_range_rejected(self):
        raw = {
            "score": 150,
            "strengths": [],
            "weaknesses": [],
            "reasoning": "test",
            "experience_match": "strong",
            "skills_match": "strong",
        }
        with pytest.raises(ValidationError):
            ScreeningScore.model_validate(raw)

    def test_negative_score_rejected(self):
        raw = {
            "score": -5,
            "strengths": [],
            "weaknesses": [],
            "reasoning": "test",
            "experience_match": "none",
            "skills_match": "none",
        }
        with pytest.raises(ValidationError):
            ScreeningScore.model_validate(raw)

    def test_invalid_match_level_rejected(self):
        raw = {
            "score": 50,
            "strengths": [],
            "weaknesses": [],
            "reasoning": "test",
            "experience_match": "excellent",  # invalid
            "skills_match": "none",
        }
        with pytest.raises(ValidationError):
            ScreeningScore.model_validate(raw)

    def test_parses_from_json_string(self):
        """Simulates parsing raw LLM text output."""
        llm_output = json.dumps({
            "score": 65,
            "strengths": [
                {"point": "Relevant degree", "evidence": "BS Computer Science from MIT"}
            ],
            "weaknesses": [],
            "reasoning": "Academic background is strong but limited industry experience.",
            "experience_match": "partial",
            "skills_match": "strong",
        })
        score = ScreeningScore.model_validate_json(llm_output)
        assert score.score == 65
        assert score.strengths[0].point == "Relevant degree"


class TestJobCreate:
    def test_valid_job(self):
        job = JobCreate(
            title="Senior Backend Engineer",
            description="We are looking for a senior backend engineer with Python experience.",
            requirements=["Python", "PostgreSQL", "5+ years"],
        )
        assert job.title == "Senior Backend Engineer"

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(title="", description="Valid description here")

    def test_short_description_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(title="Engineer", description="Short")


class TestResumeCreate:
    def test_valid_resume(self):
        resume = ResumeCreate(
            candidate_name="Jane Doe",
            email="jane@example.com",
            raw_text="Experienced software engineer with 10 years in backend development.",
        )
        assert resume.candidate_name == "Jane Doe"

    def test_email_optional(self):
        resume = ResumeCreate(
            candidate_name="Jane Doe",
            raw_text="Experienced software engineer with 10 years.",
        )
        assert resume.email is None
