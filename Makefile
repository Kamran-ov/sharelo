# Targets run directly against DATABASE_URL, or through compose with USE_DOCKER=1.
# DATABASE_URL and SECRET_KEY below are test values for local/CI runs; never used in production.
PYTHON ?= python3
# invoked as `python -m` so the interpreter that holds the installed packages is the one used
export DATABASE_URL ?= postgres://sharelo:sharelo@localhost:5432/sharelo
export SECRET_KEY ?= test-only-not-a-secret

ifeq ($(USE_DOCKER),1)
BACKEND = docker compose run --rm backend
FRONTEND = docker compose run --rm frontend
else
BACKEND = cd backend &&
FRONTEND = cd frontend &&
endif

.PHONY: install test test-backend test-frontend lint schema e2e

install:
	$(PYTHON) -m pip install -q -r backend/requirements-dev.txt
	cd frontend && npm ci --silent

test: test-backend test-frontend

test-backend:
	$(BACKEND) $(PYTHON) -m pytest

test-frontend:
	$(FRONTEND) npm test

lint:
	$(BACKEND) $(PYTHON) -m ruff check .
	$(BACKEND) $(PYTHON) -m ruff format --check .
	$(FRONTEND) npm run lint

schema:
	$(BACKEND) $(PYTHON) manage.py spectacular --format openapi-json --file ../frontend/src/api/schema.json --validate --fail-on-warn

# Browser tests: Playwright starts and stops the servers itself (frontend/playwright.config.ts).
# Own database (*_e2e), so `e2e_reset` can never wipe the dev data; the settings refuse any other name.
e2e: export E2E = 1
e2e: export DATABASE_URL = postgres://sharelo:sharelo@localhost:5432/sharelo_e2e
e2e:
	cd frontend && npm run build && npx playwright test
