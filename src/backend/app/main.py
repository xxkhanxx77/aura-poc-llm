"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="Aura - AI Resume Screening",
    description="""
AI-powered resume screening tool for HR teams. Upload a PDF resume, pick a job,
and get an AI score with strengths, weaknesses, and reasoning.

## How It Works
1. **Create a job** with title, description, and requirements
2. **Upload a PDF resume** -- system extracts text, chunks it, and embeds in Qdrant
3. **Get AI score** -- GPT-4o evaluates the candidate against the job (0-100)

## Features
- **PDF Upload**: Upload PDF resumes, auto-extract text
- **RAG Pipeline**: Text chunking + OpenAI embeddings + Qdrant vector search
- **AI Scoring**: GPT-4o scores each candidate with evidence-backed reasoning
- **Semantic Search**: Finds the most relevant resume sections for each job
- **Result Caching**: Redis caches scores for 24 hours
- **Human Feedback**: Rate AI scores 1-5 to track quality

## Authentication
No auth needed for demo. All requests use the demo tenant by default.
""",
    version="1.0.0",
    openapi_tags=[
        {"name": "Jobs", "description": "Create and manage job descriptions"},
        {"name": "Resumes", "description": "Upload and list candidate resumes"},
        {"name": "Screening", "description": "Trigger AI screening and view results"},
        {"name": "Feedback", "description": "Submit human feedback on AI scores"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint used by Docker."""
    return {"status": "ok"}
