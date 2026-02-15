"""Redis caching for screening results.

Avoids re-scoring the same resume against the same JD.
Cache key includes a hash of the JD content so scores invalidate
when the job description is edited.
"""

import hashlib
import json
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.models.schemas import ScreeningScore

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _cache_key(tenant_id: UUID, job_id: UUID, resume_id: UUID, jd_hash: str) -> str:
    return f"tenant:{tenant_id}:screen:{job_id}:{resume_id}:{jd_hash}"


def hash_jd(description: str) -> str:
    """Hash the JD text so cache invalidates when JD content changes."""
    return hashlib.sha256(description.encode()).hexdigest()[:16]


async def get_cached_score(
    tenant_id: UUID,
    job_id: UUID,
    resume_id: UUID,
    jd_hash: str,
) -> ScreeningScore | None:
    """Return cached screening score if available."""
    r = get_redis()
    key = _cache_key(tenant_id, job_id, resume_id, jd_hash)
    data = await r.get(key)
    if data is None:
        return None
    return ScreeningScore.model_validate_json(data)


async def set_cached_score(
    tenant_id: UUID,
    job_id: UUID,
    resume_id: UUID,
    jd_hash: str,
    score: ScreeningScore,
) -> None:
    """Cache a screening score with TTL."""
    r = get_redis()
    key = _cache_key(tenant_id, job_id, resume_id, jd_hash)
    await r.set(key, score.model_dump_json(), ex=settings.result_cache_ttl)
