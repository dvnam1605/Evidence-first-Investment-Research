"""Company domain unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from src.domain.company import Company
from src.domain.enums import Exchange


def test_normalize_ticker_uppercase() -> None:
    assert Company.normalize_ticker(" fpt ") == "FPT"


def test_normalize_ticker_empty_raises() -> None:
    with pytest.raises(ValueError):
        Company.normalize_ticker("  ")


def test_invalid_fiscal_month() -> None:
    with pytest.raises(ValueError):
        Company.validate_fiscal_year_end_month(13)


def test_company_dataclass() -> None:
    now = datetime.now(tz=UTC)
    company = Company(
        id=uuid.uuid4(),
        ticker="FPT",
        company_name="FPT Corporation",
        exchange=Exchange.HOSE,
        industry_code=None,
        industry_name=None,
        fiscal_year_end_month=12,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert company.exchange == Exchange.HOSE
