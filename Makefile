.PHONY: setup build-css run run-prod

setup:
	@echo "Running setup script..."
	bash scripts/setup.sh

build-css:
	@if [ -f package.json ]; then \
		if command -v npm >/dev/null 2>&1; then \
			npm install && npm run build:css; \
		else \
			echo "npm not found — install Node.js/npm to build CSS"; exit 1; \
		fi \
	else \
		echo "package.json not found — skipping CSS build"; \
	fi

run:
	@echo "Start dev server (activate .venv first if present)"
	@. .venv/bin/activate 2>/dev/null || true
	@export FLASK_APP=app && flask run --host=0.0.0.0 --port=5000

run-prod:
	@echo "Run production server with Gunicorn (requires .venv/gunicorn)"
	@. .venv/bin/activate 2>/dev/null || true
	@.venv/bin/gunicorn --bind 0.0.0.0:8000 api.index:app
