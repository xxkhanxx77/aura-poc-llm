"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# --- Enums ---

class MatchLevel(str, Enum):
    none = "none"
    partial = "partial"
    strong = "strong"


class JobStatus(str, Enum):
    active = "active"
    closed = "closed"


# --- Job schemas ---

class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500, examples=["Senior Backend Engineer"])
    description: str = Field(min_length=10, examples=["Looking for a senior backend engineer with 5+ years experience in Python, PostgreSQL, and Docker."])
    requirements: list[str] = Field(default_factory=list, examples=[["Python", "PostgreSQL", "Docker"]])


class JobResponse(BaseModel):
    id: UUID
    title: str
    description: str
    requirements: list[str]
    status: JobStatus
    created_at: datetime


# --- Resume schemas ---

class ResumeCreate(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=300, examples=["Jane Smith"])
    email: str | None = Field(default=None, examples=["jane.smith@example.com"])
    raw_text: str = Field(min_length=10, examples=["Jane Smith\nSoftware Engineer | 5 years experience\n\nSkills: Python, FastAPI, PostgreSQL, Docker, Redis\n\nExperience:\n- Backend Engineer at Acme Corp (2020-2024)\n  Built microservices in Python/FastAPI, managed PostgreSQL databases\n- Junior Developer at StartupXYZ (2019-2020)\n  REST API development, Docker containerization"])


class ResumeResponse(BaseModel):
    id: UUID
    candidate_name: str
    email: str | None
    uploaded_at: datetime


# --- Screening schemas ---

class ScreenRequest(BaseModel):
    job_id: UUID = Field(description="Job ID to screen against. Get this from GET /jobs.", examples=["c2037c79-42c3-4311-be59-8a977d700f5f"])
    resume_ids: list[UUID] | None = Field(default=None, description="Specific resume IDs to screen. Leave empty to screen all resumes.", examples=[None])


class StrengthWeakness(BaseModel):
    point: str
    evidence: str


class ScreeningScore(BaseModel):
    """Structured output expected from the LLM."""
    score: int = Field(ge=0, le=100)
    strengths: list[StrengthWeakness]
    weaknesses: list[StrengthWeakness]
    reasoning: str
    experience_match: MatchLevel
    skills_match: MatchLevel


class ScreeningResultResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: UUID
    job_id: UUID
    resume_id: UUID
    candidate_name: str
    score: int
    strengths: list[StrengthWeakness]
    weaknesses: list[StrengthWeakness]
    reasoning: str
    experience_match: MatchLevel
    skills_match: MatchLevel
    model_used: str
    created_at: datetime


class ScreeningSummary(BaseModel):
    job_id: UUID
    job_title: str
    total_candidates: int
    results: list[ScreeningResultResponse]


# --- Feedback schemas ---

class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5, description="Your rating of the AI score (1=bad, 5=excellent)", examples=[4])
    notes: str | None = Field(default=None, description="Optional notes explaining your rating", examples=["AI score matches my assessment, good candidate"])


class FeedbackResponse(BaseModel):
    id: UUID
    result_id: UUID
    rating: int
    notes: str | None
    created_at: datetime
