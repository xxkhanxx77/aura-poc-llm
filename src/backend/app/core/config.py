from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost:5432/aura"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # Cost controls
    default_monthly_llm_budget: int = 1000
    max_resumes_per_screen: int = 50  # vector pre-filter cap
    result_cache_ttl: int = 86400  # 24 hours

    model_config = {"env_prefix": "AURA_"}


settings = Settings()
