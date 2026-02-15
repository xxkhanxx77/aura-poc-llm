"""Orchestrator: ties together vector search, caching, LLM scoring, and persistence."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Job, Resume, ScreeningResult
from app.models.schemas import ScreeningResultResponse, ScreeningScore, ScreeningSummary
from app.services import cache_service, embedding_service, llm_service, vector_service

logger = logging.getLogger(__name__)


async def screen_candidates(
    db: AsyncSession,
    tenant_id: UUID,
    job_id: UUID,
    resume_ids: list[UUID] | None = None,
) -> ScreeningSummary:
    """Screen candidates for a job. Main orchestration flow:

    1. Load job description (tenant-scoped)
    2. If no resume_ids provided, use vector search to find top-N matches
    3. For each resume: check cache -> call LLM if miss -> persist result
    4. Return ranked results
    """
    # 1. Load job (tenant-scoped query)
    job = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
    )
    job = job.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found for this tenant")

    jd_hash = cache_service.hash_jd(job.description)

    # 2. Determine which resumes to score
    if resume_ids is None:
        # Use vector similarity to pre-filter (cost control)
        if job.embedding_id:
            job_embedding = await embedding_service.get_embedding_vector(job.embedding_id)
            similar_ids = await vector_service.find_similar_resumes(
                tenant_id=tenant_id,
                job_embedding=job_embedding,
            )
            resume_ids = [UUID(rid) for rid in similar_ids]
        else:
            # Fallback: score all tenant resumes (capped)
            result = await db.execute(
                select(Resume.id)
                .where(Resume.tenant_id == tenant_id)
                .limit(50)
            )
            resume_ids = list(result.scalars().all())

    # 3. Load resumes (tenant-scoped)
    resumes_result = await db.execute(
        select(Resume).where(
            Resume.id.in_(resume_ids),
            Resume.tenant_id == tenant_id,  # enforce isolation
        )
    )
    resumes = list(resumes_result.scalars().all())

    # 4. Score each resume
    results: list[ScreeningResultResponse] = []
    for resume in resumes:
        # Check cache first
        cached = await cache_service.get_cached_score(
            tenant_id, job_id, resume.id, jd_hash
        )
        if cached is not None:
            logger.info("Cache hit for resume %s", resume.id)
            score_data = cached
            model_used = "cached"
            prompt_version = "cached"
            tokens_used = 0
        else:
            # RAG: retrieve relevant chunks if available, else use full text
            resume_text = resume.raw_text
            if job.embedding_id:
                try:
                    job_emb = await embedding_service.get_embedding_vector(job.embedding_id)
                    rag_text = await embedding_service.retrieve_resume_chunks(
                        resume_id=resume.id,
                        job_embedding=job_emb,
                        top_k=5,
                    )
                    if rag_text:
                        resume_text = rag_text
                except Exception:
                    logger.warning("RAG retrieval failed for resume %s, using full text", resume.id)

            # Call LLM
            score_data, model_used, prompt_version, tokens_used = (
                await llm_service.score_resume(
                    tenant_id=tenant_id,
                    job_title=job.title,
                    job_description=job.description,
                    resume_text=resume_text,
                )
            )
            # Cache the result
            await cache_service.set_cached_score(
                tenant_id, job_id, resume.id, jd_hash, score_data
            )

        # Persist to DB (upsert)
        existing = await db.execute(
            select(ScreeningResult).where(
                ScreeningResult.job_id == job_id,
                ScreeningResult.resume_id == resume.id,
            )
        )
        existing_row = existing.scalar_one_or_none()

        if existing_row:
            existing_row.score = score_data.score
            existing_row.strengths = [s.model_dump() for s in score_data.strengths]
            existing_row.weaknesses = [w.model_dump() for w in score_data.weaknesses]
            existing_row.reasoning = score_data.reasoning
            existing_row.experience_match = score_data.experience_match.value
            existing_row.skills_match = score_data.skills_match.value
            existing_row.model_used = model_used
            existing_row.prompt_version = prompt_version
            existing_row.tokens_used = tokens_used
            db_row = existing_row
        else:
            db_row = ScreeningResult(
                tenant_id=tenant_id,
                job_id=job_id,
                resume_id=resume.id,
                score=score_data.score,
                strengths=[s.model_dump() for s in score_data.strengths],
                weaknesses=[w.model_dump() for w in score_data.weaknesses],
                reasoning=score_data.reasoning,
                experience_match=score_data.experience_match.value,
                skills_match=score_data.skills_match.value,
                model_used=model_used,
                prompt_version=prompt_version,
                tokens_used=tokens_used,
            )
            db.add(db_row)

        await db.flush()

        results.append(
            ScreeningResultResponse(
                id=db_row.id,
                job_id=job_id,
                resume_id=resume.id,
                candidate_name=resume.candidate_name,
                score=score_data.score,
                strengths=score_data.strengths,
                weaknesses=score_data.weaknesses,
                reasoning=score_data.reasoning,
                experience_match=score_data.experience_match,
                skills_match=score_data.skills_match,
                model_used=model_used,
                created_at=db_row.created_at,
            )
        )

    await db.commit()

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)

    return ScreeningSummary(
        job_id=job_id,
        job_title=job.title,
        total_candidates=len(results),
        results=results,
    )
