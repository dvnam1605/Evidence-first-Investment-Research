"""Configuration unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.config.settings import (
    AppSettings,
    CrawlerSettings,
    DatabaseSettings,
    EmbeddingSettings,
    LLMSettings,
    ObjectStorageSettings,
    ProcessingSettings,
    RedisSettings,
    Settings,
)


def test_settings_load_with_required_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://research:research@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "localhost:9000")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "minioadmin")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "research")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")

    settings = Settings()

    assert settings.database.url.endswith("/db")
    assert settings.redis.url == "redis://localhost:6379/0"
    assert settings.object_storage.bucket == "research"
    assert settings.llm.model == "gpt-4o"
    assert settings.embedding.dimensions == 1536
    assert settings.crawler.rate_limit_seconds == 1.0


def test_database_settings_missing_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        DatabaseSettings(_env_file=None)


def test_redis_settings_missing_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ValidationError):
        RedisSettings(_env_file=None)


def test_object_storage_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBJECT_STORAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        ObjectStorageSettings(_env_file=None)


def test_app_settings_defaults() -> None:
    settings = AppSettings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"


def test_processing_settings_accepts_optional_raw_table_directory(tmp_path: Path) -> None:
    settings = ProcessingSettings(raw_table_dir=tmp_path, _env_file=None)

    assert settings.raw_table_dir == tmp_path
    assert settings.stale_job_after_seconds == 3600


def test_processing_settings_treats_blank_raw_table_directory_as_unset() -> None:
    settings = ProcessingSettings(raw_table_dir="", _env_file=None)

    assert settings.raw_table_dir is None


def test_llm_and_embedding_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("CRAWLER_USER_AGENT", raising=False)
    monkeypatch.delenv("CRAWLER_RATE_LIMIT_SECONDS", raising=False)
    llm = LLMSettings(_env_file=None)
    embedding = EmbeddingSettings(_env_file=None)
    crawler = CrawlerSettings(_env_file=None)

    assert llm.api_key is None
    assert embedding.model == "text-embedding-3-small"
    assert crawler.user_agent.startswith("InvestmentResearchBot")
