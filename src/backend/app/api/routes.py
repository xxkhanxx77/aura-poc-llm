"""API routes with tenant isolation enforced at every endpoint."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import TenantContext, get_tenant
from app.core.database import get_db
from app.models.orm import Job, Resume, ScreeningFeedback, ScreeningResult
from app.models.schemas import (
    FeedbackCreate,
    FeedbackResponse,
    JobCreate,
    JobResponse,
    ResumeCreate,
    ResumeResponse,
    ScreeningResultResponse,
    ScreeningSummary,
    ScreenRequest,
)
from app.services.embedding_service import embed_and_store_job, embed_and_store_resume
from app.services.screening_service import screen_candidates

router = APIRouter()


# --- Job endpoints ---


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED, tags=["Jobs"])
async def create_job(
    body: JobCreate,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new job. The job description is embedded in Qdrant for semantic matching."""
    job = Job(
        tenant_id=tenant.tenant_id,
        title=body.title,
        description=body.description,
        requirements=body.requirements,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Generate and store embedding for the job description
    embedding_id = await embed_and_store_job(job.id, tenant.tenant_id, body.description)
    job.embedding_id = embedding_id
    await db.commit()

    return JobResponse(
        id=job.id,
        title=job.title,
        description=job.description,
        requirements=job.requirements,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("/jobs", response_model=list[JobResponse], tags=["Jobs"])
async def list_jobs(
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs for the current tenant."""
    result = await db.execute(
        select(Job).where(Job.tenant_id == tenant.tenant_id).order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    return [
        JobResponse(
            id=j.id, title=j.title, description=j.description,
            requirements=j.requirements, status=j.status, created_at=j.created_at,
        )
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific job -- tenant-scoped."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == tenant.tenant_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        id=job.id, title=job.title, description=job.description,
        requirements=job.requirements, status=job.status, created_at=job.created_at,
    )


# --- Resume endpoints ---


@router.post("/resumes", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED, tags=["Resumes"])
async def upload_resume(
    body: ResumeCreate,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume as plain text (JSON). Text is chunked and embedded in Qdrant."""
    resume = Resume(
        tenant_id=tenant.tenant_id,
        candidate_name=body.candidate_name,
        email=body.email,
        raw_text=body.raw_text,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    # Generate and store embedding for the resume
    embedding_id = await embed_and_store_resume(resume.id, tenant.tenant_id, body.raw_text)
    resume.embedding_id = embedding_id
    await db.commit()

    return ResumeResponse(
        id=resume.id,
        candidate_name=resume.candidate_name,
        email=resume.email,
        uploaded_at=resume.uploaded_at,
    )


@router.post("/resumes/upload-pdf", response_model=ScreeningSummary, status_code=status.HTTP_201_CREATED, tags=["Resumes"])
async def upload_resume_pdf(
    file: UploadFile = File(..., description="PDF resume file"),
    candidate_name: str = Form(..., description="Candidate full name", examples=["Aran Sriaran"]),
    job_id: uuid.UUID = Form(..., description="Job ID to screen against", examples=["c2037c79-42c3-4311-be59-8a977d700f5f"]),
    email: str | None = Form(default=None, description="Candidate email", examples=["aran@example.com"]),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF resume. Extracts text, chunks it, embeds in Qdrant, and scores against the selected job using GPT-4o."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Verify job exists
    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == tenant.tenant_id)
    )
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.pdf_service import extract_text_from_pdf

    pdf_bytes = await file.read()
    raw_text = extract_text_from_pdf(pdf_bytes)

    if len(raw_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    resume = Resume(
        tenant_id=tenant.tenant_id,
        candidate_name=candidate_name,
        email=email,
        raw_text=raw_text,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    embedding_id = await embed_and_store_resume(resume.id, tenant.tenant_id, raw_text)
    resume.embedding_id = embedding_id
    await db.commit()

    # Automatically screen against the specified job
    try:
        summary = await screen_candidates(
            db=db,
            tenant_id=tenant.tenant_id,
            job_id=job_id,
            resume_ids=[resume.id],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return summary


@router.get("/resumes", response_model=list[ResumeResponse], tags=["Resumes"])
async def list_resumes(
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all resumes for the current tenant."""
    result = await db.execute(
        select(Resume).where(Resume.tenant_id == tenant.tenant_id).order_by(Resume.uploaded_at.desc())
    )
    resumes = result.scalars().all()
    return [
        ResumeResponse(
            id=r.id, candidate_name=r.candidate_name,
            email=r.email, uploaded_at=r.uploaded_at,
        )
        for r in resumes
    ]


# --- Screening endpoints ---


@router.post("/screen", response_model=ScreeningSummary, tags=["Screening"])
async def screen(
    body: ScreenRequest,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Screen all resumes against a job using GPT-4o. Uses vector search to find the best matches first. Leave resume_ids empty to screen all candidates."""
    try:
        summary = await screen_candidates(
            db=db,
            tenant_id=tenant.tenant_id,
            job_id=body.job_id,
            resume_ids=body.resume_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return summary


@router.get("/results/{job_id}", response_model=ScreeningSummary, tags=["Screening"])
async def get_results(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get all screening results for a job, ranked by score (highest first). Use the job_id from GET /jobs."""
    # Load job (tenant-scoped)
    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == tenant.tenant_id)
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Load results with candidate names
    results_query = await db.execute(
        select(ScreeningResult, Resume.candidate_name)
        .join(Resume, ScreeningResult.resume_id == Resume.id)
        .where(
            ScreeningResult.job_id == job_id,
            ScreeningResult.tenant_id == tenant.tenant_id,
        )
        .order_by(ScreeningResult.score.desc())
    )
    rows = results_query.all()

    results = [
        ScreeningResultResponse(
            id=r.id,
            job_id=r.job_id,
            resume_id=r.resume_id,
            candidate_name=name,
            score=r.score,
            strengths=r.strengths,
            weaknesses=r.weaknesses,
            reasoning=r.reasoning,
            experience_match=r.experience_match,
            skills_match=r.skills_match,
            model_used=r.model_used,
            created_at=r.created_at,
        )
        for r, name in rows
    ]

    return ScreeningSummary(
        job_id=job_id,
        job_title=job.title,
        total_candidates=len(results),
        results=results,
    )


# --- Feedback endpoints ---


@router.post(
    "/results/{result_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Feedback"],
)
async def submit_feedback(
    result_id: uuid.UUID,
    body: FeedbackCreate,
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Rate an AI screening result (1-5). Use the result id from GET /results/{job_id}."""
    # Verify the result exists and belongs to this tenant
    result = await db.execute(
        select(ScreeningResult).where(
            ScreeningResult.id == result_id,
            ScreeningResult.tenant_id == tenant.tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Screening result not found")

    feedback = ScreeningFeedback(
        tenant_id=tenant.tenant_id,
        result_id=result_id,
        rating=body.rating,
        notes=body.notes,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return FeedbackResponse(
        id=feedback.id,
        result_id=feedback.result_id,
        rating=feedback.rating,
        notes=feedback.notes,
        created_at=feedback.created_at,
    )
