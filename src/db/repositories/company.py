"""Company repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.company import CompanyModel
from src.domain.company import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_ticker(self, ticker: str) -> Company | None:
        normalized = Company.normalize_ticker(ticker)
        result = await self._session.execute(
            select(CompanyModel).where(CompanyModel.ticker == normalized)
        )
        row = result.scalar_one_or_none()
        return row.to_domain() if row else None

    async def get_by_id(self, company_id: uuid.UUID) -> Company | None:
        result = await self._session.execute(
            select(CompanyModel).where(CompanyModel.id == company_id)
        )
        row = result.scalar_one_or_none()
        return row.to_domain() if row else None

    async def create(
        self,
        *,
        ticker: str,
        company_name: str,
        exchange: str,
        industry_code: str | None = None,
        industry_name: str | None = None,
        fiscal_year_end_month: int,
        is_active: bool = True,
    ) -> Company:
        normalized = Company.normalize_ticker(ticker)
        Company.validate_fiscal_year_end_month(fiscal_year_end_month)
        now = datetime.now(tz=UTC)
        model = CompanyModel(
            id=uuid.uuid4(),
            ticker=normalized,
            company_name=company_name,
            exchange=exchange,
            industry_code=industry_code,
            industry_name=industry_name,
            fiscal_year_end_month=fiscal_year_end_month,
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return model.to_domain()

    async def list_all(self) -> list[Company]:
        result = await self._session.execute(select(CompanyModel).order_by(CompanyModel.ticker))
        return [row.to_domain() for row in result.scalars().all()]
