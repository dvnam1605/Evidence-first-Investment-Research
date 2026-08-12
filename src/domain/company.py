"""Company domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums import Exchange


@dataclass(frozen=True, slots=True)
class Company:
    id: UUID
    ticker: str
    company_name: str
    exchange: Exchange
    industry_code: str | None
    industry_name: str | None
    fiscal_year_end_month: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be empty")
        return normalized

    @staticmethod
    def validate_fiscal_year_end_month(month: int) -> int:
        if month < 1 or month > 12:
            raise ValueError("fiscal_year_end_month must be between 1 and 12")
        return month
