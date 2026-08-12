"""Strongly typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = (".env", ".env.example")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str
    pool_size: int = 5
    echo: bool = False


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str


class ObjectStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OBJECT_STORAGE_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str = "research"
    secure: bool = False


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = None
    model: str = "gpt-4o"
    base_url: str | None = None

    @field_validator("api_key", "base_url", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str = "text-embedding-3-small"
    dimensions: int = 1536


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    user_agent: str = "InvestmentResearchBot/0.1"
    rate_limit_seconds: float = 1.0


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    service_name: str = Field(default="investment-research", validation_alias="SERVICE_NAME")


class Settings:
    """Composed application settings. Only this module reads environment variables."""

    def __init__(
        self,
        *,
        app: AppSettings | None = None,
        database: DatabaseSettings | None = None,
        redis: RedisSettings | None = None,
        object_storage: ObjectStorageSettings | None = None,
        llm: LLMSettings | None = None,
        embedding: EmbeddingSettings | None = None,
        crawler: CrawlerSettings | None = None,
    ) -> None:
        self.app = app or AppSettings()
        self.database = database or DatabaseSettings()
        self.redis = redis or RedisSettings()
        self.object_storage = object_storage or ObjectStorageSettings()
        self.llm = llm or LLMSettings()
        self.embedding = embedding or EmbeddingSettings()
        self.crawler = crawler or CrawlerSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
