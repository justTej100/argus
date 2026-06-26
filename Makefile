.PHONY: help run backend worker install venv stop

BACKEND_PORT := 8000
BACKEND_URL := http://localhost:$(BACKEND_PORT)

VENV := backend/.venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
RQ := $(VENV)/bin/rq

help:
	@echo "Argus Study Buddy"
	@echo "make install  - install backend dependencies"
	@echo "make backend  - run FastAPI + NiceGUI app"
	@echo "make worker   - run RQ ingestion worker"
	@echo "make run      - run backend and worker"
	@echo "make stop     - stop services on ports used by app"

$(VENV)/bin/activate: backend/requirements.txt
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r backend/requirements.txt

venv: $(VENV)/bin/activate

install: venv

backend: venv
	@cd backend && ../$(UVICORN) main:app --reload --port $(BACKEND_PORT)

worker: venv
	@cd backend && REDIS_URL=$${REDIS_URL:-redis://localhost:6379/0} ../$(RQ) worker argus-ingestion

run: venv
	@$(MAKE) -j2 backend worker

stop:
	@-lsof -ti :$(BACKEND_PORT) | xargs kill -9 2>/dev/null || true
