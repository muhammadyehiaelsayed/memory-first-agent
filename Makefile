.PHONY: setup redis-up redis-down run ask analytics wipe test test-integration lint demo

setup:
	uv sync
	test -f .env || cp .env.example .env

redis-up:
	docker compose up -d --wait

redis-down:
	docker compose down

run:
	uv run memagent chat

ask:
	uv run memagent ask "$(Q)"

analytics:
	uv run memagent analytics

wipe:
	uv run memagent wipe-memory

test:
	uv run pytest -m "not integration and not e2e"

test-integration:
	uv run pytest -m "integration or e2e"

lint:
	uv run ruff check . && uv run ruff format --check .

demo:
	uv run memagent chat
