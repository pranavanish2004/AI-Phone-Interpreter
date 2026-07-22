"""
Application settings, read once from environment variables at startup and
validated by Pydantic.

Why pydantic-settings instead of os.getenv() scattered through the code:
    1. Fail-fast: if a required setting is missing or malformed (e.g.
       DATABASE_URL isn't a valid URL), the app refuses to start with a
       clear error, instead of crashing 20 minutes later when the first
       request happens to touch that config value.
    2. Single source of truth: every other module imports `get_settings()`
       rather than reading `os.environ` directly, so there's exactly one
       place that knows the shape of our configuration.
    3. Type safety: `jwt_access_token_expire_minutes` is genuinely an int
       everywhere it's used, not a string that happens to look like a
       number.
"""

from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # other services' env vars may be present in the same .env
    )

    # ---------- General ----------
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ---------- Database ----------
    database_url: PostgresDsn = Field(
        ..., description="Async SQLAlchemy connection string, e.g. "
        "postgresql+asyncpg://user:pass@host:5432/dbname"
    )

    # ---------- Redis ----------
    redis_url: RedisDsn = Field(...)

    # ---------- Auth (used starting Phase 4; validated now so the .env
    # contract is fixed early and Phase 4 doesn't need a settings rewrite) ----------
    jwt_secret_key: str = Field(..., min_length=16)
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sqlalchemy_database_url(self) -> str:
        """
        SQLAlchemy's async engine needs the `+asyncpg` driver in the scheme.
        We accept a plain `postgresql://...` URL in .env (matches Phase 1's
        .env.example and what other services/tools like `psql` expect) and
        normalize it here, rather than forcing every deployment to remember
        the asyncpg-specific scheme.
        """
        url = str(self.database_url)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """
    Cached so Settings is parsed from the environment exactly once per
    process, not re-parsed (and re-validated) on every request that depends
    on it via FastAPI's dependency injection.
    """
    return Settings()
