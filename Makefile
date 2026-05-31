.PHONY: help run start backend frontend install install-backend install-frontend stop

BACKEND_PORT  := 8000
FRONTEND_PORT := 3000
BACKEND_URL   := http://localhost:$(BACKEND_PORT)
FRONTEND_URL  := http://localhost:$(FRONTEND_PORT)

# Default target
help:
	@echo ""
	@echo "  Argus — ChatGPT for fresh ideas"
	@echo ""
	@echo "  Usage:"
	@echo "    make run        Start backend + frontend together"
	@echo "    make backend    Start backend only"
	@echo "    make frontend   Start frontend only"
	@echo "    make install    Install all dependencies (backend + frontend)"
	@echo "    make stop       Kill anything running on :8000 and :3000"
	@echo ""

# ── Install ────────────────────────────────────────────────────────────────────

install: install-backend install-frontend
	@echo ""
	@echo "  ✔  All dependencies installed. Run 'make dev' to start."
	@echo ""

install-backend:
	@echo "  → Installing Python dependencies..."
	@cd backend && pip install -r requirements.txt -q

install-frontend:
	@echo "  → Installing Node dependencies..."
	@cd frontend && npm install --silent

# ── Run ────────────────────────────────────────────────────────────────────────

# Start both services in parallel using a trap to kill both on Ctrl-C.
# Each process is backgrounded then waited on so Ctrl-C reaches both.
start: run
run:
	@if [ ! -f .env ]; then \
		echo ""; \
		echo "  ⚠  No .env file found. Copy the example and fill in your keys:"; \
		echo "       cp .env.example .env"; \
		echo ""; \
	fi
	@echo ""
	@echo "  Starting Argus..."
	@echo ""
	@$(MAKE) -j2 _backend _frontend



# Internal targets used by the parallel make above
_backend:
	@echo "  → Backend  →  $(BACKEND_URL)"
	@echo "  → Swagger  →  $(BACKEND_URL)/docs"
	@echo ""
	@cd backend && uvicorn main:app --reload --port $(BACKEND_PORT)

_frontend:
	@echo "  → Frontend →  $(FRONTEND_URL)"
	@echo ""
	@cd frontend && npm run dev -- --port $(FRONTEND_PORT)

backend:
	@if [ ! -f .env ]; then \
		echo ""; \
		echo "  ⚠  No .env file found. Copy the example and fill in your keys:"; \
		echo "       cp .env.example .env"; \
		echo ""; \
	fi
	@echo ""
	@echo "  Backend  →  $(BACKEND_URL)"
	@echo "  Swagger  →  $(BACKEND_URL)/docs"
	@echo ""
	@cd backend && uvicorn main:app --reload --port $(BACKEND_PORT)

frontend:
	@echo ""
	@echo "  Frontend →  $(FRONTEND_URL)"
	@echo ""
	@cd frontend && npm run dev -- --port $(FRONTEND_PORT)

# ── Stop ───────────────────────────────────────────────────────────────────────

stop:
	@echo "  Stopping services on :$(BACKEND_PORT) and :$(FRONTEND_PORT)..."
	@-lsof -ti :$(BACKEND_PORT) | xargs kill -9 2>/dev/null || true
	@-lsof -ti :$(FRONTEND_PORT) | xargs kill -9 2>/dev/null || true
	@echo "  Done."
