.PHONY: setup dev build test e2e migrate seed lint

FRONTENDS := frontend-submitter frontend-reviewer

setup:
	cd backend && uv sync
	for f in $(FRONTENDS); do (cd $$f && npm ci) || exit 1; done

dev: migrate
	trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend-submitter && npm run dev) & \
	(cd frontend-reviewer && npm run dev) & \
	wait

build:
	for f in $(FRONTENDS); do (cd $$f && npm run build) || exit 1; done

test:
	cd backend && uv run pytest

e2e:
	cd frontend-submitter && npx playwright test

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -c "import asyncio; from app.services import reseed_users; asyncio.run(reseed_users())"

lint:
	cd backend && uv run ruff check .
	for f in $(FRONTENDS); do (cd $$f && npm run lint) || exit 1; done
