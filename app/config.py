from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env in dev)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    # LLM + embeddings
    google_api_key: SecretStr
    model_name: str = "gemini-3.5-flash-lite"
    embed_model: str = "models/gemini-embedding-001"
    embed_dims: int = 1536
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2

    # Infra
    database_url: str
    mcp_url: str = "http://localhost:8000/mcp"

    # Auth
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"

    # Limits
    request_timeout_s: float = 60.0
    recursion_limit: int = 12
    max_message_chars: int = 2000
    rate_limit_per_min: int = 30

    # Memory
    memory_min_score: float = 0.7
    memory_max_chars: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
