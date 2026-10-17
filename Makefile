# Targets run directly against DATABASE_URL, or through compose with USE_DOCKER=1.
# DATABASE_URL and SECRET_KEY below are test values for local/CI runs; never used in production.
PYTHON ?= python3
export DATABASE_URL ?= postgres://sharelo:sharelo@localhost:5432/sharelo
export SECRET_KEY ?= test-only-not-a-secret

ifeq ($(USE_DOCKER),1)
BACKEND = docker compose run --rm backend
FRONTEND = docker compose run --rm frontend
else
BACKEND = cd backend &&
FRONTEND = cd frontend &&
endif

.PHONY: install test test-backend test-frontend lint

install:
	$(PYTHON) -m pip install -q -r backend/requirements-dev.txt
	cd frontend && npm ci --silent

test: test-backend test-frontend

test-backend:
	$(BACKEND) pytest

test-frontend:
	$(FRONTEND) npm test

lint:
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(FRONTEND) npm run lint
