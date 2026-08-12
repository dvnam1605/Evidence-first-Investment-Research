"""Seed initial MVP companies."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import Settings
from src.db.repositories.company import CompanyRepository
from src.db.session import create_engine, create_session_factory
from src.domain.enums import Exchange

SEED_COMPANIES = [
    ("FPT", "FPT Corporation", Exchange.HOSE, "8300", "Information Technology", 12),
    ("MWG", "Mobile World Investment Corporation", Exchange.HOSE, "6500", "Retail", 12),
    ("HPG", "Hoa Phat Group JSC", Exchange.HOSE, "3100", "Materials", 12),
    ("VNM", "Vinamilk", Exchange.HOSE, "3000", "Consumer Staples", 12),
    ("PNJ", "Phu Nhuan Jewelry JSC", Exchange.HOSE, "6500", "Consumer Discretionary", 12),
]


async def seed_companies(session: AsyncSession) -> int:
    created = 0
    repo = CompanyRepository(session)
    for ticker, name, exchange, industry_code, industry_name, fiscal_month in SEED_COMPANIES:
        if await repo.get_by_ticker(ticker) is not None:
            continue

        # Repository method owns DB persistence; seed script only orchestrates.
        await repo.create(
            ticker=ticker,
            company_name=name,
            exchange=exchange.value,
            industry_code=industry_code,
            industry_name=industry_name,
            fiscal_year_end_month=fiscal_month,
            is_active=True,
        )
        created += 1
    await session.commit()
    return created


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        count = await seed_companies(session)
    await engine.dispose()
    print(f"Seeded {count} companies")


if __name__ == "__main__":
    asyncio.run(main())
