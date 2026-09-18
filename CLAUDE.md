# CLAUDE.md

Project-specific context for neurolegal. Generic engineering discipline (think
before coding, simplicity first, surgical changes, goal-driven execution)
still applies — see the prior version in git history if needed.

## Stack

- Python 3.12, package + dep manager: **uv** (`uv run`, `uv sync`, `uv.lock`)
- Linter / formatter: **ruff** (`uv run ruff check`, `uv run ruff format`)
- Type checker: **mypy strict** (`uv run mypy src`)
- Tests: **pytest** + pytest-asyncio (`auto` mode). Coverage via pytest-cov.
- DB: **Postgres + pgvector** (local default: `docker compose up -d postgres`;
  remote Postgres also supported — set `NEUROLEGAL_DB_STATEMENT_CACHE_SIZE=0` when
  behind pgbouncer in transaction mode), accessed via SQLAlchemy 2.0 async +
  asyncpg
- Migrations: **Alembic**
- HTTP layer: **FastAPI** — RAG app at `neurolegal.rag.api.app:app`,
  agent app at `neurolegal.agent.api.app:app`
- CLI: **Typer** (`src/neurolegal/cli/main.py` dispatcher; subgroups in
  `src/neurolegal/rag/cli.py` and `src/neurolegal/agent/cli.py`)
- LLM/embeddings: **OpenRouter** (default `qwen/qwen3-embedding-8b`, truncated to 1024-d)
- Frontend: React + Vite + TypeScript in `frontend/`. Two apps, two Vite entries:
  - **Chat app** — `npm run dev` (HMR, proxies API to the agent on :8000);
    `npm run build` emits `app.js`/`app.css` (stable names) into
    `src/neurolegal/agent/api/static/`, plus `app-*.js` chunks — vendor groups
    and the lazily-loaded sections (T-0143: `App.tsx` `React.lazy` for
    Files/Reviews/Sources/Templates/Onboarding, `manualChunks` in
    `vite.config.ts`). Chunk names are stable too; CSS stays a single file
    (`cssCodeSplit: false`) so `app.css` keeps its name. Every emitted file is
    committed — `git status` after a build must be clean of strays.
  - **Admin app** (RAG corpus management) — `frontend/admin/index.html` +
    `frontend/vite.config.admin.ts` (root=`admin/`). `npm run dev:admin` (proxies
    to the RAG service on :8001); `npm run build:admin` emits `admin.js`/`admin.css`
    into `src/neurolegal/rag/api/static/`. Source lives in `frontend/src/admin/`;
    shared design tokens in `frontend/src/styles/tokens.css` (imported by both apps).
  Both bundles are committed — run the matching build before committing UI changes.
  `frontend/node_modules` is gitignored.

## Design system

- UI language is fixed: Alfa Bank design system (`@alfalab/core-components`
  + Kurs tokens). `PRODUCT.md` and `DESIGN.md` at the repo root are the law
  for any UI work — read `DESIGN.md` before touching frontend styles or
  components. core-components are consumed only via `frontend/src/ui/`
  wrappers; colors only via tokens (`frontend/src/styles/tokens.css`).
- impeccable guards the law: `make impeccable` installs the Claude Code
  skill + advisory hook (per-machine; `.claude/` is gitignored). Detector:
  `npx impeccable detect frontend/src`; calibration in
  `.impeccable/config.json` — **per-machine too, `.impeccable/` is
  gitignored in full**, so re-add brand-token exemptions (Alfa fonts,
  `--red-01`) after a fresh clone if the detector starts flagging them.

## Module map (`src/neurolegal/`)

### `core/` — shared, no dependencies on `rag/` or `agent/`
- `config.py`, `domain.py`, `logging_setup.py`, `http.py` (shared httpx retry
  factory + OpenRouter constants), `db.py` (async engine factory, shared by
  `rag/` and `agent/`; `rag/store/db.py` re-exports it)

### `rag/` — ingest + retrieval service
- `acquisition/` — fetch raw bytes for an act. Корпусные `.docx` живут в S3:
  `S3DocxAcquirer` тянет их по `docx_s3_key` из манифеста, `LocalDocxAcquirer`
  остаётся для записей с `docx_path` (локальная разработка без кредов S3),
  `DocxAcquirer` выбирает ветку по записи. `PravoGovAcquirer` — с pravo.gov.ru.
  `corpus_store.py` — собственный S3-клиент rag-сервиса: импортировать
  `neurolegal.documents.*` из `rag/` запрещено, поэтому хабовский `S3BlobStore`
  переиспользовать нельзя. `cache.py` — кэш сырых байтов, `manifest.py` —
  манифест (`corpus/manifest.yaml`).
- `parsing/` — turn `RawDocument` into `StructuredDoc`. `DocxParser` is the
  working implementation; `PravoGovHTMLParser` is a `NotImplementedError` stub.
- `chunking/` — split `Article` into `Chunk`s. Per-point strategy is default;
  sliding-window fallback exists.
- `embedding/` — `OpenRouterEmbedder` (with tenacity retry), `HttpEmbedder`
  (generic HTTP), `make_embedder()` factory keyed on `NEUROLEGAL_EMBEDDER` env.
- `retrieval/` — `RetrievalService` wraps the hybrid search.
- `store/` — SQLAlchemy models, hybrid search SQL (`search.py`), acts catalog
  query (`acts.py`), idempotent upserts (`upsert.py`), DB engine re-export
  (`db.py` → `neurolegal.core.db`), bulk-load index helpers (`indexes.py`).
- `pipelines/` — `IngestPipeline`; `factory.build_pipeline` dispatches on `--source`.
- `api/` — FastAPI routes (`/healthz`, `/embed`, `/search` + `/retrieve`,
  `/acts`, `/metrics`). ASGI app at `neurolegal.rag.api.app:app`.
- `cli.py` — RAG Typer commands (ingest, reindex, search).
- **Admin surface** (gated on `NEUROLEGAL_ADMIN_ENABLED`, default `True` —
  localhost-only operator console, **no auth**; set `False` before exposing
  the RAG service externally). When enabled, `app.py` mounts the admin routers
  and serves the built admin SPA on `/` via `StaticFiles(html=True)` from
  `api/static/`. Routes under `/admin/*` (`routes_admin_documents.py`,
  `routes_admin_jobs.py`): document list / manifest edit / upload (.docx) /
  delete, article+chunk inspection, ingest job submit + poll, index status.
  `routes_admin_users.py` (T-0022) is a thin proxy — via `rag/agent_client.py`
  (HTTP only, the first and deliberate rag→agent link) — to the agent's
  internal `/admin/users*` endpoints, backing the SPA's «Пользователи» tab.
  - `jobs.py` — in-memory `JobManager` (one job at a time, auto-bulk index
    drop/recreate above 30k vectors). `documents_view.py` — pure status-matrix
    assembly. `store/admin.py` — plain-SQL stats / inspection / cascade delete.
  - The manifest (`corpus/manifest.yaml`) is the source of truth; the UI
    reads/writes it (`acquisition/manifest.py` atomic save — YAML comments are
    lost on write). An entry points either at a local `docx_path` or at an S3
    `docx_s3_key`; the manifest-edit route carries both in the single string
    field `ManifestUpdateRequest.docx_path`, an `s3:` prefix selecting the
    bucket (the same marker `documents_view` emits in `file_path`, so the
    admin form round-trips). Both branches are guarded and both guards are a
    review gate: `_safe_docx_path` confines local paths to the documents dir,
    `_safe_docx_s3_key` confines bucket keys to `NEUROLEGAL_CORPUS_S3_PREFIX`
    (`.docx`, no `..`) — the bucket is shared with the documents hub, so an
    unvalidated key plus `DELETE ?drop_file=true` would erase a user's file.
    Uploads go to S3 under `corpus_key(code_id)` with a collision guard.
    Without S3 credentials the store dependency is `None`: the list degrades
    (`file_exists=False`), upload and delete-with-`drop_file` answer 503.

### `agent/` — agent service
- `api/` — FastAPI ASGI app at `neurolegal.agent.api.app:app`; exposes `/healthz`
  and the SSE `POST /chat` endpoint. `deps.py`, `routes_chat.py` wire it.
  Agent API also exposes: `GET /acts` (proxies RAG acts catalog),
  `GET /conversations`, `GET /conversations/{id}/messages`,
  `DELETE /conversations/{id}`. `POST /chat` accepts `acts` (user-selected source
  short names) which the agent applies as a hard filter on every `rag_search`.
  Agent also proxies the owner document **library** under `/library/*`:
  `GET /library/documents` (owner = current session's user), `POST /library/documents`
  (upload into library, no conversation attach), `DELETE /library/documents/{id}`,
  `GET /documents/{id}/content` (extracted text/sections) — all via
  `documents_client` (boundary intact). The chat SPA's **Файлы** section is a
  two-pane library + reader (`FilesView.tsx` + `FilesReader.tsx`): PDF renders
  via a native iframe on the `/documents/{id}/download` proxy; DOCX shows
  extracted text/sections from `/content`.
  The built SPA is served on `/` via `StaticFiles(html=True)` from `api/static/`.
  `routes_admin_users.py` (T-0022) exposes internal `GET/PATCH /admin/users*`
  for the RAG operator proxy — gated by `verify_internal_token`
  (`api/deps.py`), never by `get_current_user`; not reachable from the browser.
  The PATCH is partial (T-0026): `is_active` and/or `new_password` (operator
  password reset, min 8 chars). Deactivation and any password change drop all
  the user's sessions (activation doesn't); the everywhere-logout invariant
  lives in `AuthService.admin_patch_user` (T-0033), the route is a thin
  HTTP↔exception mapper.
- `auth/` — self-signup auth (E05): store / service / routes / deps / rate
  limiter. **No email verification and no self-service password reset**
  (T-0026, client decision 2026-07-11): `POST /auth/register` activates the
  account immediately (`email_verified_at = now`) and answers like
  `POST /auth/login` — MeResponse + `neurolegal_session` httpOnly cookie (30-day
  sliding TTL); duplicate email → 409 `email_taken`. Password reset is
  operator-only via the admin «Пользователи» tab. `core/mail` + SMTP config
  and the `auth_tokens` table stay in the codebase dormant (for when mail
  returns; the removed verify/reset flows live in git history).
  `get_current_user` (cookie → `auth_sessions`, argon2id via
  `core/security.py`) gates `/chat`, `/conversations*`, `/library/*`,
  `/documents/*`, `/acts`, `/sources*`; `/auth/*` and `/healthz` stay open.
  Per-IP/per-email rate limiting on login/register; an Origin middleware in
  `app.py` checks mutating requests against `NEUROLEGAL_PUBLIC_BASE_URL`.
- `llm/` — `OpenRouterChatClient` (streaming chat + tool calling, tenacity
  retry on connection setup), `ChatLLM` protocol, provider-neutral types.
- `chat/` — `ChatAgent` tool-calling loop (capped at
  `behavior.max_tool_iterations` — default 8, range 1–10, set in
  `contracts/agent_settings.py` and editable from the RAG admin card; on cap
  it streams **and stores** the fixed `CAP_NOTE` refusal), `rag_search` tool,
  system prompt (answers only from search results; cites every claim as
  «ст. N АКТ»), and SSE event types in `events.py` (`session`, `reasoning`,
  `tool_call`, `tool_result`, `delta`, `citations`, `done`, `error`).
- `store/` — `conversations` / `messages` SQLAlchemy models (agent-owned,
  SQLite-portable) and the `ConversationStore` repository.
- `tools/` — `rag_client.py` (**the only** path from agent to RAG, HTTP) and
  `documents_client.py` (**the only** path from agent to the documents hub, HTTP).
  Document storage/extraction lives entirely in `neurolegal.documents`; the
  agent reaches it via HTTP only. `read_document` and `risk_review` tools fetch
  section content from the hub on demand.
- `eval/` — seed retrieval benchmark (`benchmark.py`: cases + scoring),
  driven by the `neurolegal agent eval-retrieval` CLI against a live RAG service.
- `cli.py` — Typer commands (`chat` stub, `eval-retrieval`).
- `chat/intent.py` classifies each user turn as `legal | text_task | smalltalk`.
  Only `legal` exposes `rag_search` to the model and emits citations; non-legal
  intents run the LLM with no tools and a text-task system prompt.
- Streaming contract: when the model streams visible text and then asks for a
  tool, the agent emits a `reset_delta` SSE event so the frontend drops what
  it already showed. The stored answer contains only post-reset text.
- `NEUROLEGAL_RAG_MIN_SCORE` env var (default 0.0 — off) sets a hard RRF floor on
  the article score. When non-zero, off-corpus queries return an empty list
  and the agent emits a "no basis" answer.

### `cli/main.py` — top-level dispatcher
- `neurolegal migrate | rag <…> | agent <…>` via Typer subgroups.

### `neurolegal.documents` — document hub service
- Own FastAPI app (`neurolegal.documents.api.app:app`, :8002): upload →
  store original in S3 → async-extract text → serve original + extracted text
  back; documents attach to chat conversations many-to-many.
- Owns `hub_documents` / `hub_document_attachments` Postgres tables, reached
  via `neurolegal.core.db` (never `neurolegal.rag.store.*` / `neurolegal.agent.store.*`).
  Original bytes live in S3 (`store/blob.py`); Postgres holds only metadata
  plus extracted text/sections.
- `processing/` — format dispatch (`.docx` via python-docx, `.pdf` via
  liteparse local rus-OCR); `worker.py` runs extraction in-process after
  upload and flips row status `processing → ready|failed`.
- **«Суть» (T-0017):** one-line LLM summary in `hub_documents.summary`,
  computed by `worker.py` right after the row flips to `ready` (ready is
  never blocked by the LLM; a summary failure leaves NULL, not `failed`).
  `processing/summary.py` is the hub's own OpenRouter chat mini-client
  (built on `neurolegal.core.http`; `provider sort=latency`, 20 s timeout) —
  boundary stays intact. A startup sweep (`backfill_missing_summaries`,
  spawned in lifespan) re-fills `ready AND summary IS NULL` rows: restarts,
  LLM outages, and legacy-library backfill. No `OPENROUTER_API_KEY` → both
  are silently off. Model: `NEUROLEGAL_SUMMARY_MODEL`.
- Imports only `neurolegal.core` and `neurolegal.contracts` — never `neurolegal.agent.*` or
  `neurolegal.rag.*` (see Boundary rules).

### `neurolegal.templates` — templates service (E20)
- Own FastAPI app (`neurolegal.templates.api.app:app`, :8003): операторская
  библиотека .docx-шаблонов, которые агент заполняет в чате. docxtpl: скан
  `{{ плейсхолдеров }}` + детерминированный рендер (значения — данные,
  autoescape; LLM текст шаблона не трогает).
- Owns `tpl_templates` (Postgres, SQLite-portable) via `neurolegal.core.db`;
  шаблонные .docx — в общем S3-бакете под `NEUROLEGAL_TEMPLATES_S3_PREFIX`
  (default `templates/`), ключи только внутри префикса
  (`store/blob.safe_template_key` — бакет общий с хабом и корпусом).
- Публичные роуты `GET /templates`, `GET /templates/{slug}`,
  `POST /templates/{slug}/render` (422 — структурный `RenderValidationError`
  по полям, без detail-обёртки); draft неотличим от несуществующего (404).
  Операторский CRUD `/admin/templates*` — за `X-Internal-Token`
  (навешивается при монтировании в app.py); загрузка/замена .docx со сканом
  полей, дифф added/orphaned при замене. На старте fail-fast без токена при
  `NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true` (как у хаба).
- Валидация значений — `contracts.validate_template_values`: одна проверка
  на рендер сервиса и `stage_template` агента; кап загрузки —
  `contracts.TEMPLATE_MAX_UPLOAD_BYTES`, его обязаны применять обе стороны
  пути «RAG-прокси → сервис».
- Двухфазный инвариант доверия живёт у агента: `stage_template` валидирует и
  сохраняет черновик (`template_drafts`, один на беседу), `render_template`
  без аргументов рендерит ровно staged. Карточки чата переживают перезагрузку
  через `messages.template_draft` / `messages.template_doc` (паттерн review) —
  включая терминальную ветку `ask_user` в `chat/agent.py`, куда карточка
  текущего хода обязана уехать явно (T-0143).
- **Один черновик — один документ** (T-0143). `render_template` идемпотентен:
  `rendered_at` возвращает уже готовый документ без второй загрузки и без
  второй карточки, а `template_drafts.document_id` пишется между upload и
  attach, поэтому оборванная попытка довершается привязкой, не загрузкой.
  Новый `stage_template` обнуляет обе отметки — новые данные, новый цикл.
  По той же причине `DocumentsClient.upload` ходит с
  `make_http_retry(idempotent=False)`: read-timeout не доказывает, что хаб
  не создал запись. Не снимать ни одну из трёх защит поодиночке.
- Imports only `neurolegal.core` and `neurolegal.contracts`; никто не
  импортирует `neurolegal.templates` — связи только HTTP:
  агент → `agent/tools/templates_client.py` (публичное API + прокси
  `GET /templates` за auth), RAG → `rag/templates_client.py` +
  `rag/api/routes_admin_templates.py` (вкладка «Шаблоны» в админ-SPA).

## Boundary rules (enforce on review)

- `agent/` may import from `core/`, `agent.tools.rag_client`, and
  `agent.tools.documents_client`; it must **never** import `neurolegal.rag.*` or
  `neurolegal.documents.*` modules directly. `tests/unit/test_agent_boundary.py`
  scans the whole `agent/` subtree for both `neurolegal.rag` and `neurolegal.documents`
  imports.
- `agent/` owns its Postgres tables (`conversations`, `messages`) but reaches
  the DB via `neurolegal.core.db`, never `neurolegal.rag.store.*`.
- `rag/` does not import `agent/` (asymmetric) — the sole exception is HTTP,
  via `rag/agent_client.py` (T-0022, operator users proxy). `rag/` must never
  import `neurolegal.agent.*` modules directly; `tests/unit/test_rag_boundary.py`
  guards it.
- `core/` imports nothing from `rag/` or `agent/`.
- `neurolegal.documents` must never import `neurolegal.agent.*`/`neurolegal.rag.*`/
  `neurolegal.templates.*`; `tests/unit/documents/test_documents_boundary.py` guards it.
- `neurolegal.templates` imports only `core`/`contracts`
  (`tests/unit/templates/test_templates_boundary.py`); agent/rag reach it
  only over HTTP — их boundary-тесты запрещают импорт `neurolegal.templates`.

## Contracts

- `src/neurolegal/contracts/` is the single source of truth for every Pydantic DTO
  that touches an HTTP boundary (RAG `/search`, `/embed`, `/acts`,
  `/retrieve`; agent `/chat`, `/conversations`, `/acts`; SSE event payloads).
- `core.domain` keeps ingest-only types (`Article`, `Chunk`, `RawDocument`,
  `StructuredDoc`). Do **not** add HTTP shapes here.
- Frontend types are generated, not hand-written:
  - `uv run python -m scripts.generate_openapi` dumps live schemas to
    `frontend/openapi/`.
  - `npm --prefix frontend run openapi:generate` rebuilds
    `frontend/src/api/generated/{rag,agent}.ts`.
  - `frontend/src/api/types.ts` aliases the generated `components.schemas`.
- `tests/unit/test_contracts_openapi.py` fails when the live OpenAPI drifts
  from `tests/data/openapi/*.json`. Treat that as a deliberate review gate:
  regenerate + commit snapshots + regenerated TS together with the API change.

## CLI

- `neurolegal migrate` — `alembic upgrade head`.
- `neurolegal rag ingest --code X [--code Y ...] [--source docx|pravo] [--bulk]` —
  load one or more acts. **Always use `--bulk` when the HNSW index already
  holds 30k+ vectors** (see Operational Notes); it drops HNSW + GIN before
  ingest and recreates them after, in a `try/finally`.
- `neurolegal rag reindex --code X [--source docx|pravo]` — re-run ingest for
  one act (no bulk wrapper).
- `neurolegal rag search "<query>" [--act "ВК РФ" ...] [--limit N]` — hybrid
  search, prints JSON.
- `neurolegal rag indexes status|create|drop` — inspect / recreate / drop the HNSW
  + GIN search indexes (recovery for a half-finished bulk ingest; runbook
  `docs/runbooks/search-indexes.md`, local-only).
- `neurolegal agent chat` — stub.
- `neurolegal agent eval-retrieval [--rag-url URL] [--limit N] [--case ID]` — run
  the seed retrieval benchmark (`agent/eval/`) against a live RAG service.

## Automation (`Makefile` + hooks)

- **`Makefile`** is the task-runner entry point (npm-scripts analog); bare
  `make` lists targets. Key: `make sync` (uv + frontend deps), `make hooks`
  (install git hooks), `make dev` (postgres + migrate + RAG + agent +
  documents + templates + frontend via `Procfile`/honcho, Ctrl+C stops all), `make up|down`
  (just Postgres), `make lint|format|typecheck|test|test-int|check`,
  `make openapi`, `make build`.
- **Git hooks** via **pre-commit** (`.pre-commit-config.yaml`), installed by
  `make hooks`:
  - *pre-commit* (sub-second): `ruff check --fix`, `ruff format`, `mypy src`
    (strict), file hygiene.
  - *pre-push*: `pytest tests/unit` + frontend `tsc --noEmit` (only when
    `frontend/**` changed). Integration tests (DB/network) are **excluded** by
    design.
- `honcho`, `pre-commit` are dev-deps (`uv`). `make dev` can't run while the
  five services already occupy :8001/:8000/:8002/:8003/:5173 (порт-чек в
  цели dev).
- pre-commit refuses to install if `core.hooksPath` is set; if you hit that,
  `git config --local --unset core.hooksPath` (the repo default is `.git/hooks`).

## Environment

Read via pydantic-settings from `.env.local` (callers don't import dotenv).

Required:
- `DATABASE_URL` — Postgres URL. Defaults to the local docker compose
  Postgres (`postgresql://neurolegal:neurolegal@127.0.0.1:5432/neurolegal`). Going through
  a pgbouncer-in-transaction-mode pooler (`-pooler.` hostname) requires
  `NEUROLEGAL_DB_STATEMENT_CACHE_SIZE=0` — see Operational notes.

Optional:
- `OPENROUTER_API_KEY` — required for OpenRouter embedder + search/retrieve
  and for the agent chat model.
- `HF_TOKEN` — reserved name for a future HF Inference embedder; **not read by
  the code today** (no Settings field).
- `NEUROLEGAL_EMBEDDER` (default `openrouter`; also accepts `http://...`)
- `NEUROLEGAL_EMBEDDER_MODEL`, `NEUROLEGAL_EMBEDDER_TARGET_DIM`
- `NEUROLEGAL_LLM_MODEL` (default `qwen/qwen3.6-flash`) — OpenRouter chat model for
  the agent; reuses `OPENROUTER_API_KEY`.
- `NEUROLEGAL_PLAYBOOKS_DIR` (default `playbooks`) — directory of contract-review
  playbooks (risk checklists per doc type) loaded by the agent.
- `NEUROLEGAL_REVIEW_MODEL` (default unset) — OpenRouter chat model override for the
  contract-review pipeline; unset → reuse `NEUROLEGAL_LLM_MODEL`.
- `NEUROLEGAL_RAG_BASE_URL` (default `http://127.0.0.1:8001`) — agent's RAG endpoint;
  override for staging / docker / split-service deploys.
- `NEUROLEGAL_TAVILY_API_KEY` (default unset) — enables the agent's `web_search` tool
  (Tavily). Absent → `web_search` degrades gracefully ("unavailable"); never
  persisted in `agent_settings.yaml`. `web_search`/`web_fetch` are also gated by
  `tools.web_search.enabled` / `tools.web_fetch.enabled` (off by default). Web
  results are context only, never a legal basis.
- `NEUROLEGAL_RAG_MIN_SCORE` (default `0.0` — off) — minimum RRF article score for
  hybrid_search to return a result. Non-zero values filter off-corpus queries;
  calibrate against your corpus before enabling.
- `NEUROLEGAL_HNSW_EF_SEARCH` (default `200`, max `1000`) — pgvector HNSW search
  width, applied per-transaction in hybrid search. The dense leg filters by
  act after the index scan, so pgvector's default of 40 starves searches
  filtered to a small act.
- `NEUROLEGAL_DB_STATEMENT_CACHE_SIZE` (default `100`) — asyncpg per-connection
  prepared-statement cache size. Set to `0` for pgbouncer-in-transaction-mode
  (Neon `-pooler.`).
- `NEUROLEGAL_ADMIN_ENABLED` (default `True`) — enables the RAG admin surface
  (`/admin/*` routes + admin SPA on `/`). Localhost-only, **no auth** by design;
  set `False` before exposing the RAG service externally.
- `NEUROLEGAL_AGENT_SETTINGS_PATH` (default `data/agent_settings.yaml`) — persisted
  agent settings written by the RAG admin UI (`/admin/agent/*`) and read by the
  agent at startup. Operator runtime state — gitignored, not committed.
- `NEUROLEGAL_SMTP_HOST`, `NEUROLEGAL_SMTP_PORT` (default `587`), `NEUROLEGAL_SMTP_USER`,
  `NEUROLEGAL_SMTP_PASSWORD`, `NEUROLEGAL_SMTP_FROM`, `NEUROLEGAL_SMTP_STARTTLS` (default
  `true`) — outbound mail (`core/mail.py`). **Currently dormant**: T-0026
  removed the auth mail flows (email verification / password-reset links),
  nothing sends mail at runtime. Kept for when mail returns. No
  `NEUROLEGAL_SMTP_HOST` → console mode (mail goes to the log); `NEUROLEGAL_SMTP_FROM`
  is required once HOST is set.
- `NEUROLEGAL_PUBLIC_BASE_URL` (default `http://127.0.0.1:8000`) — browser-facing
  origin of the agent service; the Origin middleware validates mutating
  requests against it (CSRF guard, see `agent/api/app.py`).
- `NEUROLEGAL_COOKIE_SECURE` (default `False`) — `Secure` flag on the `neurolegal_session`
  cookie set by `POST /auth/login` and `POST /auth/register`. `False` for
  local http dev; set `True` wherever the agent is served over https.
- `NEUROLEGAL_LOG_LEVEL`, `NEUROLEGAL_RAW_CACHE_DIR`, `NEUROLEGAL_DB_POOL_SIZE`, `NEUROLEGAL_EMBED_BATCH_SIZE`
- `NEUROLEGAL_S3_ENDPOINT`, `NEUROLEGAL_S3_BUCKET` (default
  `nfs-neurolegal-documents`), `NEUROLEGAL_S3_REGION` (default `us-east-1`),
  `NEUROLEGAL_S3_ACCESS_KEY`, `NEUROLEGAL_S3_SECRET_KEY` — S3 config, shared
  by the documents hub's original-bytes store and the RAG service's corpus
  `.docx` store (`rag/acquisition/corpus_store.py` — a separate client, the
  boundary rules forbid reusing the hub's). `NEUROLEGAL_CORPUS_S3_PREFIX`
  (default `corpus/`) — key prefix for corpus `.docx` in the bucket.
- `NEUROLEGAL_TESSDATA_PATH` (default `data/tessdata`) — local OCR language
  data dir for the documents hub's PDF/rus-OCR extraction. liteparse does not
  bundle `rus.traineddata` and would otherwise fetch it from the network on
  first OCR; the service preflights its presence at startup and fails fast
  instead. Provision it once per environment, e.g. `mkdir -p data/tessdata &&
  curl -fsSL -o data/tessdata/rus.traineddata
  https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata` — never
  download it at runtime.
- `NEUROLEGAL_SUMMARY_MODEL` (default `openai/gpt-4o-mini`) — OpenRouter chat
  model for the hub's one-line document summary («Суть», T-0017); reuses
  `OPENROUTER_API_KEY` (no key → summaries + startup sweep silently off).
- `NEUROLEGAL_DOCUMENTS_BASE_URL` (default `http://127.0.0.1:8002`) — the
  documents hub's own base URL; consumed by the agent via `settings.documents_base_url`.
- `NEUROLEGAL_TEMPLATES_BASE_URL` (default `http://127.0.0.1:8003`) — endpoint
  templates-сервиса для агента и RAG-прокси (core `settings.templates_base_url`);
  в docker-деплое `http://templates:8003` в `.env.prod`.
  `NEUROLEGAL_TEMPLATES_S3_PREFIX` (default `templates/`) — префикс шаблонных
  .docx в общем бакете (читается templates-сервисом, `templates/config.py`).
- `NEUROLEGAL_AGENT_BASE_URL` (default `http://127.0.0.1:8000`) — the RAG
  service's endpoint for the agent, used only by the operator "users" proxy
  (`rag/agent_client.py`, `rag/api/routes_admin_users.py`).
- `NEUROLEGAL_INTERNAL_TOKEN` (default unset) — shared secret between the
  agent and the documents hub, and (T-0022) between the RAG service and the
  agent's internal `/admin/users*` endpoints. When set, the caller sends it
  as `X-Internal-Token` and the callee rejects any request whose header
  doesn't match (constant-time compare); unset on both sides is the open
  local-dev default. `NEUROLEGAL_REQUIRE_INTERNAL_TOKEN` (default `False`)
  makes the hub fail fast at startup if the token isn't configured.

## Operational notes

These constraints come from real incidents — respect them on changes.

- **Statement-cache and pgbouncer:** `core/db.py` reads
  `NEUROLEGAL_DB_STATEMENT_CACHE_SIZE` (default `100`, asyncpg's default) and
  passes it to `connect_args`. When connecting through pgbouncer in
  transaction-pool mode (e.g. Neon's `-pooler.` hostname), set it to `0`
  — otherwise asyncpg's per-connection prepared-statement cache becomes
  invalid whenever a transaction lands on a different backend, surfacing
  as opaque `ConnectionDoesNotExistError` mid-write. The local-docker
  default Postgres is direct (no pgbouncer), so `100` is correct.
- **HNSW index maintenance dominates incremental INSERTs.** With 30k+ vectors
  in `chunks_embedding_hnsw`, even a 300-row INSERT can exceed the pooler's
  connection timeout. Bulk loads must drop the search indexes first; CLI
  `--bulk` does this via `store/indexes.drop_search_indexes` /
  `create_search_indexes`. Index DDL is mirrored in
  `alembic/versions/0002_search_vector_indexes.py` — keep the two in sync;
  `tests/unit/test_store_indexes.py` guards against drift. To check live
  state and recover from a half-finished bulk ingest, use
  `neurolegal rag indexes status|create|drop` (runbook:
  `docs/runbooks/search-indexes.md`, local-only — docs/ is gitignored).
- **Tombstones.** Russian codices often keep `Статья N. Утратила силу...`
  entries with empty bodies. The parser drops them (see
  `_dedupe_by_number` + the post-dedupe empty-body filter in
  `parsing/docx.py`). Embedding empty strings was producing 1024-d phantom
  hits in HNSW.
- **Article numbering quirks:** the regex accepts `N.M.K-1` suffixes
  (e.g. КоАП ст. 14.1.1-1) — articles inserted by later amendments share
  the dotted prefix of the original.
- **Acts identity is `source_doc_id` alone.** Migration `0015` replaced
  `uq_acts_source_doc (source, source_doc_id)` with `uq_acts_source_doc_id
  (source_doc_id)`: `source` is a descriptive field that changes with the
  acquirer (`local-docx` → `s3-docx`), and reindexing under a new acquirer
  was duplicating the act (and all its articles/chunks) instead of updating it.
- **OpenRouter is flaky on long sequential runs.** `OpenRouterEmbedder`
  wraps each call in tenacity (5 attempts, exponential-jitter backoff),
  same pattern as `PravoGovAcquirer`. Don't remove without a replacement.
- **OpenRouter provider lottery on embeddings (T-0013).** Without a provider
  preference, `qwen/qwen3-embedding-8b` is sometimes routed to a provider
  answering in 20-60 s (Nebius) vs 1-3 s (DeepInfra/SiliconFlow) — this was
  the "60 s search" symptom. `OpenRouterEmbedder` sends
  `provider: {"sort": "latency"}`, and the search path builds its embedder
  with a 15 s timeout (`rag/api/deps.QUERY_EMBED_TIMEOUT`) so one hung
  connection costs seconds (retry), not a minute; ingest keeps the 60 s
  default (128-text batches are legitimately slower). Don't remove either
  half without re-measuring the tail.
- `/embed` is bounded: at most 128 texts (existing), each ≤8000 chars, total
  ≤200 000 chars. Oversize requests return 422. Limits live in
  `contracts/search.py` (`EMBED_MAX_TEXT_CHARS`, `EMBED_MAX_BATCH_CHARS`).

## Tests

- `tests/unit/` runs without network / DB (uses `unittest.mock`, `tmp_path`).
- `tests/integration/` is split by pytest marker — only the matching marker
  skips when env is absent (see `tests/integration/conftest.py`):
  - `-m api_with_mocks` — ASGI + `dependency_overrides`; needs nothing.
  - `-m db_only` — needs `DATABASE_URL` (real connection).
  - `-m external_openrouter` — needs `OPENROUTER_API_KEY`.
  - `-m e2e` — needs both.
- `tests/integration/test_cli_ingest_docx.py` is additionally gated on
  `NEUROLEGAL_E2E=1` and on S3 credentials — the corpus `.docx` files live in
  the bucket (`docx_s3_key` in the manifest), not on disk.

## Convention reminders

- Commits follow `type(scope): subject` (see `git log`).
- `corpus/` (except its manifest), `logs/`, `docs/` and the whole of `data/` are gitignored
  (see `.gitignore` — it is grouped by section and root-anchors local paths).
- Don't add `Co-Authored-By: Claude` to commits.
- Don't put `import 'dotenv/config'`-style env loading into library code —
  config.py is the single entry point.
- Миграции только аддитивные: новые таблицы и nullable-столбцы. Никаких `DROP`
  и `NOT NULL` без default в том же релизе, что и использующий их код — все
  `downgrade()` деструктивны, поэтому откат кода на проде возможен только если
  предыдущая версия работает поверх новой схемы. Удаление столбца — в два
  релиза.
