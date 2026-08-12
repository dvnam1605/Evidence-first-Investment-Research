"""Database migration integration tests."""

from __future__ import annotations

import os
import subprocess

import pytest
from src.config.settings import Settings
from tests.integration.safety import require_safe_test_database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database_settings() -> Settings:
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not configured for integration tests")
    return Settings()


def test_alembic_upgrade_downgrade_cycle(database_settings: Settings) -> None:
    require_safe_test_database(
        database_settings.database.url,
        operation="migration upgrade/downgrade cycle",
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = database_settings.database.url

    upgrade = subprocess.run(
        ["alembic", "upgrade", "head"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    downgrade = subprocess.run(
        ["alembic", "downgrade", "-1"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert downgrade.returncode == 0, downgrade.stderr

    reupgrade = subprocess.run(
        ["alembic", "upgrade", "head"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert reupgrade.returncode == 0, reupgrade.stderr
