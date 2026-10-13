.PHONY: data run check test lint

data:
	uv run python scripts/generate_data.py

run: data
	uv run order-margin

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:
	uv run pytest -q

check: lint test
