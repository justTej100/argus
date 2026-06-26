.PHONY: help run app backend install venv stop test

APP_PORT := 8000
APP_URL := http://localhost:$(APP_PORT)

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Argus Study Buddy"
	@echo "make install  - create .venv (if needed) and install dependencies"
	@echo "make app      - run FastAPI + NiceGUI app ($(APP_URL))"
	@echo "make backend  - alias for make app"
	@echo "make run      - alias for make app"
	@echo "make test     - run pytest"
	@echo "make stop     - stop services on ports used by app"
	@echo ""
	@echo "No need to run 'source .venv/bin/activate' — make targets use $(VENV)/bin/* directly."

$(VENV)/bin/python:
	@echo "Creating virtualenv in $(VENV)..."
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip

venv: $(VENV)/bin/python

install: venv
	@echo "Installing dependencies into $(VENV)..."
	@$(PIP) install -r requirements.txt
	@echo "Done. Run: make app"

app: install
	@echo "Starting Argus on $(APP_URL) (python: $(PYTHON))..."
	@$(UVICORN) main:app --reload --port $(APP_PORT)

backend: app

run: app

test: venv
	@$(PYTEST) tests/ -v

stop:
	@-lsof -ti :$(APP_PORT) | xargs kill -9 2>/dev/null || true
