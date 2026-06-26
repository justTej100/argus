.PHONY: help run app backend install venv stop test

APP_PORT := 8000
APP_URL := http://localhost:$(APP_PORT)

VENV := .venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Argus Study Buddy"
	@echo "make install  - install dependencies"
	@echo "make app      - run FastAPI + NiceGUI app"
	@echo "make backend  - alias for make app"
	@echo "make run      - alias for make app"
	@echo "make test     - run pytest"
	@echo "make stop     - stop services on ports used by app"

$(VENV)/bin/activate: requirements.txt
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

venv: $(VENV)/bin/activate

install: venv

app: venv
	@$(UVICORN) main:app --reload --port $(APP_PORT)

backend: app

run: app

test: venv
	@$(PYTEST) tests/ -v

stop:
	@-lsof -ti :$(APP_PORT) | xargs kill -9 2>/dev/null || true
