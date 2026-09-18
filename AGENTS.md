# AGENTS.md — правила работы агентов в репозитории neurolegal

Документ обязателен к прочтению перед любым изменением в этом репозитории.
Инженерные детали стека, границы модулей и операционные уроки — в `CLAUDE.md`
(он остаётся источником истины по коду). Здесь — процесс работы через доску.

## 1. Источник истины — доска, а не файлы

Задачи, эпики, зависимости и статусы ведутся **только** в MCP
`projects-control-work` (skill `agent-board`), проект **«neurolegal»**.
Внимание: отображаемое имя проекта — `neurolegal`, но стабильный **ключ**
остался историческим — все вызовы доски делай с `projectKey: "jurai"`
(он же в `.project-control.json`).

- Не создавай в репозитории файлов вида `TODO.md`, `TASKS.md`, `roadmap.md`
  и не заводи локальных досок-зеркал. Единственный источник истины по задачам —
  MCP. (Историческое зеркало `tracking/` удалено в T-0096: доска покрывала его
  целиком.)
- Не редактируй базу трекера напрямую (SQLite), не ходи во внутренние
  HTTP-эндпоинты, не пиши одноразовых import-скриптов. Только публичные
  инструменты agent-board.
- Статус меняется только через инструменты жизненного цикла
  (`task_claim`, `task_submit_review`, `task_review_decide`), никогда через
  `task_update` (он — для scope/описания/приоритета/acceptance criteria).

## 2. Порядок работы над задачей

1. `agent_run_start` — начать идентифицированный run (clientKind `claude-code`).
2. `task_context` — загрузить постановку, зависимости, документы, evidence.
   Если привязаны документы — `document_check`, разрулить `changed`/`missing`.
3. `task_claim` — взять lease. **До получения lease файлы не создаются и не
   изменяются.** Не клеймить задачу с незакрытой зависимостью `depends_on`.
4. Работа строго в границах `scope`. Всё из `outOfScope` — отдельной задачей.
5. `task_heartbeat` — продлевать lease при длительной работе.
6. Проверки (раздел 3) → один осмысленный коммит с ключом задачи → `evidence_add`
   → `task_submit_review`.
7. Одобряет задачу **другой** run (`task_review_decide`). Самоодобрение
   запрещено. Одобрение — единственный путь в `done`.

Остановка не доведённой работы — `task_release`. Внешнее препятствие —
`task_block` с конкретной причиной.

## 3. Обязательные проверки перед сдачей

```bash
make check      # ruff (lint) + mypy strict + pytest tests/unit  (то, что гоняют хуки)
```

Дополнительно по типу задачи:

```bash
make test-int                 # интеграционные тесты с моками (без DB/сети)
make build                    # production-сборка обоих фронтенд-бандлов (chat + admin)
npx impeccable detect frontend/src   # для UI-задач — находок быть не должно
npm --prefix frontend run openapi:generate  # при изменении контрактов (+ снапшоты)
```

Задача не отправляется на проверку, пока `make check` (и `make build` для UI) не
завершатся с кодом 0. Сборку запускать при остановленном dev-сервере.

Результаты прикладываются как evidence:

| Что | Как |
| --- | --- |
| Коммит | `evidence_add` c `kind: commit` и точным SHA |
| Прогон тестов | `kind: test` (команда + итог) |
| Затронутые файлы | `kind: file` |
| Документы (спека/план) | `kind: document` + `document_link` |

Коммит обязан содержать ключ задачи в теме: `feat(T-0001): …`,
`fix(T-0002): …`. Один завершённый таск = один осмысленный коммит.
**Не добавляй `Co-Authored-By: Claude`.** На дефолтной ветке `main` —
сначала завести ветку.

## 4. Архитектурные границы (гейт ревью)

Полностью — в `CLAUDE.md` (раздел «Boundary rules»); коротко:

- `agent/` не импортирует `neurolegal.rag.*` и `neurolegal.documents.*` — только
  по HTTP (`agent.tools.rag_client`, `agent.tools.documents_client`). Гард:
  `tests/unit/test_agent_boundary.py`.
- `rag/` не импортирует `neurolegal.agent.*` (единственное исключение — HTTP через
  `rag/agent_client.py`). Гард: `tests/unit/test_rag_boundary.py`.
- `neurolegal.documents` не импортирует `neurolegal.agent.*`/`neurolegal.rag.*` —
  только `neurolegal.core`/`neurolegal.contracts`. Гард:
  `tests/unit/documents/test_documents_boundary.py`.
- `core/` ничего не импортирует из `rag/`/`agent/`.
- Все HTTP-DTO — в `src/neurolegal/contracts/`. Дрейф OpenAPI ловит
  `tests/unit/test_contracts_openapi.py`: при изменении API регенерируй и
  коммить снапшоты + сгенерированные TS вместе с кодом.
- UI — только дизайн-система Альфа: core-components через `frontend/src/ui/`,
  цвета только токенами. Закон — `DESIGN.md` (читать перед правкой стилей).

## 5. Сервисы, порты, запуск

- RAG-сервис `neurolegal.rag.api.app` — **:8001** (ingest+retrieval, admin-консоль).
- Agent-сервис `neurolegal.agent.api.app` — **:8000** (чат SSE, auth, прокси) —
  основной пользовательский вход и health-порт (`/healthz`).
- Documents-хаб `neurolegal.documents.api.app` — **:8002**.
- Frontend (Vite dev) — **:5173** (Origin-allowlist агента знает только его).
- Postgres+pgvector — **:5432** (docker compose).

`.project-control.json`: `command` = `make dev` (поднимает postgres+миграции,
затем RAG+agent+documents+frontend через honcho; Ctrl+C гасит всё),
`stopCommand` = `make down` (гасит docker-Postgres; том сохраняется),
управляющий порт — `8710` (регистрационный порт проекта в контроль-системе;
сам agent слушает на `8000`, health-эндпоинт `/healthz`). `make dev` использует
фиксированные порты 8000/8001/8002/5173 и не может стартовать, пока они заняты.

Установка зависимостей: `make sync`. Миграции: `neurolegal migrate`.

## 6. Язык

Интерфейс, отчёты, документация и тексты задач — русский. Код и
идентификаторы — английский.

## 7. Ключевые документы

`README.md` (обзор, запуск), `PRODUCT.md` (продукт), `DESIGN.md` (закон дизайна,
обязателен перед UI), `CLAUDE.md` (стек, границы, операционные уроки),
`.env.example` (переменные окружения), `docs/superpowers/{specs,plans}/`
(спеки и планы, gitignored).
