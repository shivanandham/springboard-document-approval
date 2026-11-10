.PHONY: setup dev build test e2e migrate seed lint

setup:
	cd backend && uv sync
	cd frontend && npm ci

dev: migrate
	trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

build:
	cd frontend && npm run build

test:
	cd backend && uv run pytest

e2e:
	cd frontend && npx playwright test

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -c "import asyncio; from app.services import reseed_users; asyncio.run(reseed_users())"

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint
