# Vietnam Evidence-first Investment Research

Evidence-first financial research system for Vietnamese listed companies.

Every material claim traces back to structured financial facts and/or original source documents.

## Development

Requires Python 3.12+.

This repo uses a hybrid setup:

- **Python tooling** (`pytest`, `ruff`, `mypy`, `alembic`) runs in the Windows/conda environment.
- **Docker services** (`postgres`, `redis`, `minio`) run in WSL via `docker compose`.

Ports are forwarded to `localhost`, so Windows tools connect with the URLs in `.env.example`.

```bash
pip install -e ".[dev]"

# Start infrastructure in WSL
make up

# Run quality checks on Windows
make lint
make typecheck
make test-unit

# Apply migrations (Windows -> localhost:5432 in WSL Docker)
make migrate
make test-integration
```

See `IMPLEMENTATION_PLAN.md` for the full execution specification.
