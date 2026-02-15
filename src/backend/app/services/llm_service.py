"""LLM integration via LangChain + OpenAI with cost tracking."""

import json
import logging
from uuid import UUID

import redis.asyncio as redis
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.models.schemas import ScreeningScore
from app.prompts.resume_screening import PROMPT_VERSION, build_screening_prompt

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_llm() -> ChatOpenAI:
    """Create a ChatOpenAI instance (stateless, no need to cache)."""
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
        max_tokens=1500,
    )


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def check_tenant_budget(tenant_id: UUID) -> bool:
    """Check if tenant has remaining LLM budget for the current month."""
    r = get_redis_client()
    key = f"tenant:{tenant_id}:llm_calls_month"
    current = await r.get(key)
    if current is None:
        return True
    return int(current) < settings.default_monthly_llm_budget


async def increment_tenant_usage(tenant_id: UUID, tokens: int) -> None:
    """Track LLM usage per tenant per month."""
    r = get_redis_client()
    key = f"tenant:{tenant_id}:llm_calls_month"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60 * 60 * 24 * 31)  # expire after ~1 month
    await pipe.execute()

    # Also track token usage for billing
    token_key = f"tenant:{tenant_id}:tokens_month"
    pipe = r.pipeline()
    pipe.incrby(token_key, tokens)
    pipe.expire(token_key, 60 * 60 * 24 * 31)
    await pipe.execute()


async def score_resume(
    tenant_id: UUID,
    job_title: str,
    job_description: str,
    resume_text: str,
) -> tuple[ScreeningScore, str, str, int]:
    """Score a single resume against a job description using LangChain + OpenAI.

    Returns (parsed_score, model_used, prompt_version, tokens_used).
    Raises ValueError if budget exceeded or LLM returns invalid output.
    """
    if not await check_tenant_budget(tenant_id):
        raise ValueError("Monthly LLM budget exceeded for this tenant")

    system_prompt, user_prompt = build_screening_prompt(
        job_title=job_title,
        job_description=job_description,
        resume_text=resume_text,
    )

    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)

    raw_text = response.content
    logger.info("LLM raw response: %s", raw_text[:500])

    # Extract token usage from response metadata
    usage = response.response_metadata.get("token_usage", {})
    tokens_used = usage.get("total_tokens", 0)

    # Track usage
    await increment_tenant_usage(tenant_id, tokens_used)

    # Strip markdown code fences if GPT wraps the JSON
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove opening ```json or ``` and closing ```
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing fence
        text = "\n".join(lines)

    # Parse and validate structured output
    try:
        parsed = json.loads(text)
        score = ScreeningScore.model_validate(parsed)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("LLM returned invalid JSON: %s", raw_text[:500])
        raise ValueError(f"LLM output failed validation: {exc}") from exc

    return score, settings.openai_model, PROMPT_VERSION, tokens_used
