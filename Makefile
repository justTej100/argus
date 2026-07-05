.PHONY: help run app backend install venv stop test frontend frontend-dev

APP_PORT := 8000
APP_URL := http://localhost:$(APP_PORT)

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
NPM := npm

help:
	@echo "Argus Study Buddy"
	@echo "make install       - Python venv + pip dependencies"
	@echo "make frontend      - npm install + build React UI"
	@echo "make frontend-dev  - Vite dev server (proxies API to :8000)"
	@echo "make app           - build frontend + run FastAPI ($(APP_URL))"
	@echo "make test          - run pytest"
	@echo "make stop          - stop services on port $(APP_PORT)"

$(VENV)/bin/python:
	@echo "Creating virtualenv in $(VENV)..."
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip

venv: $(VENV)/bin/python

install: venv
	@echo "Installing Python dependencies..."
	@$(PIP) install -r requirements.txt

frontend:
	@echo "Building React frontend..."
	@cd frontend && $(NPM) install && $(NPM) run build

frontend-dev:
	@cd frontend && $(NPM) install && $(NPM) run dev

app: install frontend
	@echo "Starting Argus on $(APP_URL)..."
	@$(UVICORN) main:app --reload --port $(APP_PORT)

backend: app
run: app

test: venv
	@$(PYTEST) tests/ -v

stop:
	@-lsof -ti :$(APP_PORT) | xargs kill -9 2>/dev/null || true
