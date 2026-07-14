.PHONY: install dev up down migrate test lint format typecheck check

install:
	uv sync --extra dev
	pnpm install

dev:
	uv run uvicorn apps.api.main:app --reload

up:
	docker compose up --build

down:
	docker compose down

migrate:
	uv run alembic upgrade head

test:
	uv run pytest
	pnpm test

lint:
	uv run ruff check .
	pnpm lint

format:
	uv run ruff format .
	pnpm format

typecheck:
	uv run mypy src apps
	pnpm typecheck

check: lint typecheck test
