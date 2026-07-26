.PHONY: dev test lint typecheck assets demo-fixtures

dev:
	docker compose up --build

test:
	uv run --all-packages pytest

lint:
	uv run --all-packages ruff check .
	pnpm lint

typecheck:
	uv run --all-packages mypy services/core/src apps/api/src apps/worker/src
	pnpm typecheck

assets:
	uv run python scripts/index_resource_pack.py minecraft.zip var/assets/vanilla

demo-fixtures:
	uv run python scripts/generate_fixtures.py
