.PHONY: setup install redis-up redis-down run ask analytics wipe test test-integration lint eval-lifecycle eval-grounding eval coverage ci demo

setup:
	uv sync --frozen
	test -f .env || cp .env.example .env

install:
	uv sync --frozen

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

eval-lifecycle:
	uv run python scripts/eval_lifecycle.py --mock

eval-grounding:
	uv run python scripts/eval_grounding.py --mock

eval: eval-lifecycle eval-grounding

coverage:
	uv run coverage report

# Mirror the full ci.yml gate set in step order (tested == shipped).
# The integration leg needs redis:8.2 -- run `make redis-up` first.
ci: install lint
	uv run pytest -m "not integration and not e2e" --cov=memagent --cov-report=term
	uv run pytest -m "integration or e2e" --cov=memagent --cov-append --cov-report=term
	$(MAKE) eval
	$(MAKE) coverage

demo:
	uv run memagent chat
