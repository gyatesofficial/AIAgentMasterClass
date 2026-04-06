"""
config.py - Application Configuration
======================================
Loads settings from environment variables / .env file using pydantic-settings.

All configuration for the support platform lives here.
Import Settings and use settings.openai_api_key, etc.

Usage:
    from support_platform.config import settings

    client = OpenAI(api_key=settings.openai_api_key)
    db_engine = create_engine(settings.database_url)
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.

    Priority order:
    1. Environment variables (highest)
    2. .env file
    3. Default values (lowest)
    """

    # ── LLM API Keys ─────────────────────────────────────────
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (required for GPT-4o and embeddings)",
        alias="OPENAI_API_KEY",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key (required for Claude models)",
        alias="ANTHROPIC_API_KEY",
    )
    langchain_api_key: Optional[str] = Field(
        default=None,
        description="LangSmith API key (optional, enables tracing)",
        alias="LANGCHAIN_API_KEY",
    )
    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangSmith tracing",
        alias="LANGCHAIN_TRACING_V2",
    )
    langchain_project: str = Field(
        default="ai-agents-masterclass",
        description="LangSmith project name",
        alias="LANGCHAIN_PROJECT",
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql://agents_user:agents_password@localhost:5432/agents_db",
        description="PostgreSQL connection string",
        alias="DATABASE_URL",
    )
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="agents_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="agents_password", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="agents_db", alias="POSTGRES_DB")

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
        alias="REDIS_URL",
    )

    # ── ChromaDB ──────────────────────────────────────────────
    chroma_host: str = Field(default="localhost", alias="CHROMA_HOST")
    chroma_port: int = Field(default=8000, alias="CHROMA_PORT")

    # ── LLM Settings ──────────────────────────────────────────
    default_model: str = Field(
        default="gpt-4o",
        description="Default LLM model for agent calls",
        alias="DEFAULT_MODEL",
    )
    default_temperature: float = Field(
        default=0.3,
        description="Default sampling temperature (0 = deterministic)",
        alias="DEFAULT_TEMPERATURE",
    )
    max_iterations: int = Field(
        default=10,
        description="Maximum agent loop iterations (prevents infinite loops)",
        alias="MAX_ITERATIONS",
    )
    cost_limit_per_request: float = Field(
        default=0.50,
        description="Maximum USD cost per ticket processing run",
        alias="COST_LIMIT_PER_REQUEST",
    )

    # ── Application Settings ──────────────────────────────────
    app_env: str = Field(
        default="development",
        description="Environment: development, staging, production",
        alias="APP_ENV",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR",
        alias="LOG_LEVEL",
    )
    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Allow extra fields (don't error on unknown env vars)
        extra = "ignore"

    # ── Computed Properties ────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def chroma_url(self) -> str:
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key and "your-key" not in self.openai_api_key)

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key and "your-key" not in self.anthropic_api_key)

    def validate_for_production(self) -> list[str]:
        """
        Return a list of configuration problems that would prevent production use.
        Returns empty list if config is valid.
        """
        issues = []
        if not self.has_openai_key:
            issues.append("OPENAI_API_KEY not set or invalid")
        if not self.has_anthropic_key:
            issues.append("ANTHROPIC_API_KEY not set or invalid")
        if self.is_production and self.cors_origins == ["*"]:
            issues.append("CORS origins should be restricted in production")
        if self.log_level == "DEBUG" and self.is_production:
            issues.append("LOG_LEVEL=DEBUG in production may expose sensitive data")
        return issues

    def __repr__(self) -> str:
        """Show settings without exposing API keys."""
        return (
            f"Settings("
            f"env={self.app_env}, "
            f"model={self.default_model}, "
            f"openai={'set' if self.has_openai_key else 'MISSING'}, "
            f"anthropic={'set' if self.has_anthropic_key else 'MISSING'}"
            f")"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached Settings instance.

    Using @lru_cache means Settings is only initialized once per process.
    This avoids re-reading .env on every import.

    Usage:
        from support_platform.config import settings
    """
    return Settings()


# Convenience import — use this everywhere
settings = get_settings()


if __name__ == "__main__":
    print("Current settings:")
    print(f"  {settings}")
    print(f"\n  Database: {settings.database_url}")
    print(f"  Redis: {settings.redis_url}")
    print(f"  ChromaDB: {settings.chroma_url}")
    print(f"  Default model: {settings.default_model}")
    print(f"  Cost limit: ${settings.cost_limit_per_request}")

    issues = settings.validate_for_production()
    if issues:
        print(f"\n  Config issues:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"\n  Config OK")
