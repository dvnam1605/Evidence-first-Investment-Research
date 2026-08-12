.PHONY: up down migrate format lint typecheck test test-unit test-integration

WSL_PROJECT := $(shell wsl wslpath -a "$(CURDIR)")

up:
	wsl -e bash -lc "cd '$(WSL_PROJECT)' && docker compose up -d"

down:
	wsl -e bash -lc "cd '$(WSL_PROJECT)' && docker compose down"

migrate:
	alembic upgrade head

format:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy src apps

test:
	pytest

test-unit:
	pytest tests/unit -m "not integration"

test-integration:
	pytest tests/integration -m integration
