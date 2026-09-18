# neurolegal — точки входа для запуска, тестов и линта.
# Аналог npm-скриптов; поверх лежат git-хуки (.pre-commit-config.yaml).
# `make` без аргумента печатает список целей.

.DEFAULT_GOAL := help
.PHONY: help sync hooks impeccable up down dev rag agent documents templates frontend migrate \
        lint format typecheck test test-int check openapi build deploy deploy-history

# --- meta ------------------------------------------------------------------

help: ## показать список целей
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## uv sync + установка зависимостей фронтенда
	uv sync
	npm --prefix frontend install

hooks: ## установить git-хуки (pre-commit + pre-push)
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

impeccable: ## установить impeccable (скилл + advisory-hook Claude Code, per-machine)
	npx impeccable install --providers=claude --scope=project

# --- запуск ----------------------------------------------------------------

up: ## поднять postgres (docker) и накатить миграции
	docker compose up -d postgres
	@echo "ждём, пока postgres станет healthy..."
	@for i in $$(seq 1 30); do \
		s=$$(docker inspect --format '{{.State.Health.Status}}' neurolegal-postgres 2>/dev/null); \
		if [ "$$s" = "healthy" ]; then echo "postgres healthy"; break; fi; \
		sleep 1; \
		if [ "$$i" = "30" ]; then echo "postgres не стал healthy за 30s" >&2; exit 1; fi; \
	done
	uv run neurolegal migrate

down: ## остановить postgres (volume сохраняется)
	docker compose stop postgres

dev: up ## поднять весь стек (postgres+миграции, затем RAG+agent+documents+templates+frontend параллельно)
	@for p in 8000 8001 8002 8003 5173; do \
		if lsof -nP -iTCP:$$p -sTCP:LISTEN >/dev/null 2>&1; then \
			echo "порт :$$p уже занят — остановите старый стек перед make dev" >&2; exit 1; \
		fi; \
	done
	uv run honcho start

rag: ## запустить только RAG-сервис (:8001, reload)
	uv run uvicorn neurolegal.rag.api.app:app --port 8001 --reload

agent: ## запустить только agent-сервис (:8000, reload)
	uv run uvicorn neurolegal.agent.api.app:app --port 8000 --reload

documents: ## запустить только documents-хаб (:8002, reload)
	uv run uvicorn neurolegal.documents.api.app:app --port 8002 --reload

templates: ## запустить только templates-сервис (:8003, reload)
	uv run uvicorn neurolegal.templates.api.app:app --port 8003 --reload

frontend: ## запустить только Vite dev-сервер
	npm --prefix frontend run dev

migrate: ## alembic upgrade head
	uv run neurolegal migrate

# --- качество --------------------------------------------------------------

lint: ## ruff check + ruff format --check (без правок)
	uv run ruff check src tests deploy
	uv run ruff format --check src tests deploy

format: ## ruff check --fix + ruff format (правит файлы)
	uv run ruff check --fix src tests deploy
	uv run ruff format src tests deploy

typecheck: ## mypy strict по src и скриптам деплоя
	uv run mypy src deploy

test: ## юнит-тесты (оффлайн, без env)
	uv run pytest tests/unit -q

test-int: ## интеграционные тесты с моками (ASGI, без DB/сети)
	uv run pytest tests/integration -m api_with_mocks -q

check: lint typecheck test ## всё, что суммарно гоняют хуки

# --- прочее ----------------------------------------------------------------

openapi: ## пересобрать схемы OpenAPI и сгенерированные TS-типы
	uv run python -m scripts.generate_openapi
	npm --prefix frontend run openapi:generate

build: ## production-сборка обоих фронтенд-бандлов (chat + admin)
	npm --prefix frontend run build
	npm --prefix frontend run build:admin

# --- деплой ------------------------------------------------------------------

DEPLOY_HOST ?= $(NEUROLEGAL_DEPLOY_HOST)
DEPLOY_DIR  ?= /srv/neurolegal
DEPLOY_LOG  ?= /var/log/neurolegal-deploys.log

deploy: ## Запасной путь: выкатить тег с ноутбука. Обычный путь — job deploy в Actions (deploy/CD.md).
	@test -n "$(TAG)" || (echo "укажите TAG, например: make deploy TAG=v0.3.0" && exit 1)
	@test -n "$(DEPLOY_HOST)" || (echo "укажите DEPLOY_HOST=user@host" && exit 1)
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_DIR) && ALLOW_UNVERIFIED=$(ALLOW_UNVERIFIED) ./deploy/deploy.sh $(TAG)'

deploy-history: ## Показать журнал выкаток на сервере
	@test -n "$(DEPLOY_HOST)" || (echo "укажите DEPLOY_HOST=user@host" && exit 1)
	@ssh $(DEPLOY_HOST) 'tail -n 20 $(DEPLOY_LOG) 2>/dev/null || echo "журнала ещё нет"'
