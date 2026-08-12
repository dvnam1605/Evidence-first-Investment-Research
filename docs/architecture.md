# System Architecture

Evidence-first financial research for Vietnamese listed companies.

## High-level architecture

```text
                         EXTERNAL DATA SOURCES

              ┌──────────┬──────────┬──────────┐
              │   HOSE   │   HNX    │   SSC    │
              └────┬─────┴────┬─────┴────┬─────┘
                   │          │          │
                   ▼          ▼          ▼

              ┌──────────────────────────────┐
              │       INGESTION LAYER        │
              │ SourceConnector / Downloader │
              │ SHA256 / Version Resolver    │
              └──────────────┬───────────────┘
                             │
                   ┌─────────┴─────────┐
                   ▼                   ▼
        ┌────────────────────┐   ┌────────────────────┐
        │ OBJECT STORAGE     │   │ DOCUMENT METADATA  │
        │ Raw PDF/XLS/XLSX   │   │ PostgreSQL         │
        └──────────┬─────────┘   └────────────────────┘
                   ▼
        ┌─────────────────────────────────────────────┐
        │           DOCUMENT PROCESSING               │
        │ MIME / PDF / OCR / Excel / Table extraction │
        └────────────────────┬────────────────────────┘
                             │
                 ┌───────────┴────────────┐
                 ▼                        ▼
       FINANCIAL PIPELINE             DOCUMENT PIPELINE
                 │                        │
                 ▼                        ▼
       FINANCIAL FACT STORE         DOCUMENT EVIDENCE STORE
                 │                        │
                 └───────────┬────────────┘
                             ▼
              ┌───────────────────────────────┐
              │        RESEARCH ENGINE        │
              │ Quant Agent / Filing Agent    │
              └──────────────┬────────────────┘
                             ▼
                  ┌─────────────────┐
                  │   CLAIM STORE   │
                  └────────┬────────┘
                           ▼
              ┌───────────────────────────────┐
              │      VERIFICATION LAYER       │
              └──────────────┬────────────────┘
                             ▼
                  ┌────────────────────┐
                  │ REPORT GENERATOR   │
                  └──────────┬─────────┘
                             ▼
                ┌────────────────────────┐
                │ FastAPI / Web UI       │
                └────────────────────────┘
```

## Core architectural principle

The application maintains two independent research data paths:

**Numeric path:** financial reports → table extraction → normalization → financial facts → calculations → numeric claims.

**Textual path:** notes/disclosures → document processing → chunking → retrieval → textual evidence → textual claims.

Both paths converge in the claim store and verification layer.

## Module boundaries

| Module | Responsibility | Must not contain |
|--------|----------------|------------------|
| `src/domain/` | Pure domain models and enums | SQL, HTTP, storage, LLM, FastAPI |
| `src/db/` | SQLAlchemy models, sessions, repositories | Business orchestration |
| `src/storage/` | Object storage abstraction | Financial interpretation |
| `src/ingestion/` | Source discovery, download, deduplication | Metric normalization |
| `src/processing/` | PDF/OCR/table extraction | Research analysis |
| `src/financial/` | Metric mapping, units, periods, validation | LLM reasoning |
| `src/calculation/` | Deterministic analytics | LLM calls |
| `src/retrieval/` | Chunking, indexing, hybrid search | Claim generation |
| `src/evidence/` | Source-grounded evidence objects | Unverified claims |
| `src/agents/` | Research orchestration | Raw SQL |
| `src/verification/` | Claim verification | Report rendering |
| `src/workflows/` | LangGraph workflow nodes | FastAPI routes |
| `src/reporting/` | Structured report generation | Unverified LLM facts |
| `apps/api/` | Thin FastAPI handlers | Business logic |

## Configuration rule

Only `src/config/` reads environment variables. Business modules receive typed settings objects.

## Transaction boundaries

Application services own transactions. Long network downloads happen outside database transactions:

```text
download externally → calculate hash → store raw object → short DB transaction
```

## Idempotency

These operations must be safe to rerun without uncontrolled duplicates:

- company ingestion
- document download
- document processing
- financial normalization
- embedding generation
- research evaluation

## Point-in-time requirement

Research accepts an `as_of` timestamp. No document published after `as_of` may influence retrieval, financial facts, corporate events, verification, or reporting.

Example:

```text
BCTC Q2 v1 published: 10:00
Correction v2 published: 14:00

research.as_of = 11:00  → must use v1
research.as_of = 15:00  → may use v2
```

This prevents look-ahead bias in backtests and historical research runs.

## Technology stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- LangGraph for research workflows
- PostgreSQL + pgvector, Redis, MinIO (S3-compatible)
- pytest, ruff, mypy

See `IMPLEMENTATION_PLAN.md` section 7 for the authoritative specification.
