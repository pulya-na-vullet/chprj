# Neurolegal («Нейроюрист»)

Russian-law RAG system with a tool-calling agent and a React frontend.

Four independently-deployable processes share a single repo:

- **RAG service** (`neurolegal.rag.api.app:app`, port 8001) — hybrid search over a
  pgvector corpus of 25 codices + 10 federal laws. Also hosts the
  localhost-only operator admin console (corpus management + a "Пользователи"
  tab); no auth by design, gated by `NEUROLEGAL_ADMIN_ENABLED` (default on).
- **Agent service** (`neurolegal.agent.api.app:app`, port 8000) — SSE chat with a
  tool-calling loop that grounds every legal claim in `rag_search` results.
  Per-turn intent router separates legal questions from text tasks. Serves
  the built React SPA at `/`. **Behind auth (E05):** all chat/library/acts
  routes require a session; users self-register on the sign-in screen (email +
  password, no email verification — see below).
- **Documents hub** (`neurolegal.documents.api.app:app`, port 8002) —
  upload → store originals in S3 → extract text (.docx / .pdf OCR) → serve
  back; documents attach to chat conversations. Reached by the agent over HTTP
  only.
- **Templates service** (`neurolegal.templates.api.app:app`, port 8003, E20) —
  operator-managed .docx templates the agent fills in chat (docxtpl,
  deterministic render). Reached only over HTTP: the agent proxies the public
  list/render API, the RAG admin console proxies the operator CRUD
  (`X-Internal-Token`); the browser never talks to :8003.
- **Frontend** (`frontend/`, Vite dev server) — chat SPA talks to the agent on
  :8000; a second admin SPA (`npm run dev:admin`) talks to the RAG service on
  :8001. In production both build outputs are mounted by their services at `/`.

## Automation (make)

A `Makefile` wraps the common workflows; `make` (no target) lists them.

```bash
make sync          # uv sync + frontend npm install
cp .env.example .env.local   # fill OPENROUTER_API_KEY (DATABASE_URL defaults to local docker)
make hooks         # install git hooks (ruff+mypy on commit, unit tests on push)
make dev           # postgres + migrate + RAG :8001 + agent :8000 + documents :8002 + templates :8003 + frontend, one terminal (Ctrl+C stops all)
```

Other targets: `make up` / `make down` (just Postgres), `make rag|agent|frontend`
(single process), `make lint|format|typecheck|test|check`, `make openapi`,
`make build`. Git hooks run via [pre-commit](https://pre-commit.com/): ruff +
ruff-format + mypy + file hygiene on **commit**; `pytest tests/unit` (+ frontend
`tsc --noEmit` when `frontend/**` changed) on **push**. Integration tests
(DB/network) are deliberately excluded from hooks.

The Quickstart below spells out what `make dev` does under the hood.

## Quickstart

```bash
# 1. Setup
uv sync
cp .env.example .env.local
# fill OPENROUTER_API_KEY in .env.local (DATABASE_URL defaults to the local docker one)

# 2. Start Postgres (pgvector image, loopback-only)
docker compose up -d postgres

# 3. Migrate
uv run neurolegal migrate

# 4. Ingest the corpus (one-off; --bulk drops/recreates search indexes)
uv run neurolegal rag ingest --code ГК-1 --code ФЗ-44
uv run neurolegal rag ingest --code НК-2 --bulk

# 5. Provision OCR data for the documents hub (once per environment; the hub
#    preflights this at startup and fails fast if missing — never downloads it
#    at runtime)
mkdir -p data/tessdata && curl -fsSL -o data/tessdata/rus.traineddata \
  https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata

# 6. Run the five processes (separate terminals; or just `make dev`)
uv run uvicorn neurolegal.rag.api.app:app --port 8001 --reload
uv run uvicorn neurolegal.agent.api.app:app --port 8000 --reload
uv run uvicorn neurolegal.documents.api.app:app --port 8002 --reload
uv run uvicorn neurolegal.templates.api.app:app --port 8003 --reload
npm --prefix frontend install && npm --prefix frontend run dev
```

Dev UI is on the Vite port that the previous command prints (usually 5173) and
proxies `/auth`, `/chat`, `/acts`, `/conversations`, `/library`, `/documents`,
`/sources`, `/templates`, `/healthz` to the agent on :8000.

**First run:** the agent is behind auth — open the dev UI and self-register
(email + password) on the sign-in screen; you're logged in immediately (no
email verification, T-0026). The operator admin console is a separate SPA on
the RAG service (`npm --prefix frontend run dev:admin`, proxies to :8001) with
no login; its "Пользователи" tab is where an operator resets a user's password
or blocks an account. That tab reaches the agent's internal endpoints — set a
shared `NEUROLEGAL_INTERNAL_TOKEN` on both services before exposing either
externally (see Environment).

Migrating from Neon? See `docs/runbooks/local-postgres.md` (local-only —
`docs/` is gitignored, ask a maintainer for a copy).

## Production build

```bash
npm --prefix frontend run build         # chat SPA → src/neurolegal/agent/api/static/ (committed)
npm --prefix frontend run build:admin   # admin SPA → src/neurolegal/rag/api/static/ (committed)
# (`make build` runs both)
uv run uvicorn neurolegal.agent.api.app:app --port 8000
# now the built chat SPA is served at http://localhost:8000/
```

Both bundles are committed — run the matching build before committing UI changes.

## CLI

```bash
uv run neurolegal migrate                                  # alembic upgrade head
uv run neurolegal rag ingest --code <id> [--bulk]          # ingest one or more acts
uv run neurolegal rag reindex --code <id>                  # re-run ingest for one act
uv run neurolegal rag search "<query>" [--act ...]         # hybrid search, JSON output
uv run neurolegal rag indexes status|drop|create           # HNSW/GIN index runbook
uv run neurolegal agent chat                               # stub for future CLI chat
uv run neurolegal agent eval-retrieval [--rag-url ...]     # seed retrieval benchmark vs a live RAG
```

The corpus and per-act metadata live in `corpus/manifest.yaml`
(35 entries: 25 codices + 10 federal laws).

## Layout

- `src/neurolegal/core/` — config, ingest-only domain models, logging, DB engine,
  HTTP retry utilities (shared, depends on nothing else under `neurolegal/`).
- `src/neurolegal/contracts/` — Pydantic DTOs for every HTTP boundary; the single
  source of truth that both `rag/` and `agent/` import, and that frontend TS
  types are generated from.
- `src/neurolegal/rag/` — RAG service: acquisition, parsing, chunking, embedding,
  retrieval, store, pipelines, FastAPI app, CLI.
- `src/neurolegal/agent/` — agent service: FastAPI app + tool-calling chat loop +
  intent router + RAG HTTP client + conversation store.
- `src/neurolegal/cli/main.py` — top-level Typer dispatcher (`neurolegal migrate | rag | agent`).
- `frontend/` — React 19 + Vite SPA; bundle is built into
  `src/neurolegal/agent/api/static/` and served by the agent FastAPI app.

See `CLAUDE.md` for module boundaries, the contracts workflow, operational
notes (Neon pgbouncer, HNSW maintenance, tombstones, intent router,
streaming contract, min_score floor), and conventions.

## Environment

`DATABASE_URL` and `OPENROUTER_API_KEY` are the only required variables; see
`.env.example` for optional knobs:

- `NEUROLEGAL_RAG_BASE_URL` — agent's RAG endpoint (default `http://127.0.0.1:8001`;
  override for staging / docker / split-service deploys).
- `NEUROLEGAL_RAG_MIN_SCORE` — minimum RRF article score for hybrid search
  (default `0.0` = off; non-zero filters off-corpus queries).
- `NEUROLEGAL_DB_STATEMENT_CACHE_SIZE` — asyncpg prepared-statement cache (default
  `100`). Set to `0` when connecting through pgbouncer in transaction-pool
  mode (e.g. Neon `-pooler.` host).
- `NEUROLEGAL_LLM_MODEL`, `NEUROLEGAL_EMBEDDER_MODEL`, `NEUROLEGAL_EMBEDDER_TARGET_DIM`,
  `NEUROLEGAL_LOG_LEVEL`, `NEUROLEGAL_RAW_CACHE_DIR`, `NEUROLEGAL_DB_POOL_SIZE`,
  `NEUROLEGAL_EMBED_BATCH_SIZE` — see `src/neurolegal/core/config.py`.

Auth / deploy (matter once you expose a service beyond loopback):

- `NEUROLEGAL_PUBLIC_BASE_URL` — browser-facing origin of the agent (default
  `http://127.0.0.1:8000`); the Origin/CSRF middleware validates mutating
  requests against it.
- `NEUROLEGAL_COOKIE_SECURE` — `Secure` flag on the session cookie (default `False`
  for local http; **set `True` when serving the agent over https**).
- `NEUROLEGAL_INTERNAL_TOKEN` — shared secret between the RAG admin proxy and
  the agent's internal `/admin/users*` endpoints (and the agent↔documents-hub
  link). **Set it before exposing the agent externally** — unset leaves those
  operator endpoints unauthenticated. `NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true`
  makes the services fail fast at startup if the token isn't configured.
- `NEUROLEGAL_ADMIN_ENABLED` — RAG admin console + SPA (default `True`,
  localhost-only, no auth); set `False` before exposing the RAG service.
- `NEUROLEGAL_S3_*`, `NEUROLEGAL_TESSDATA_PATH`, `NEUROLEGAL_DOCUMENTS_BASE_URL`
  — documents hub (see `.env.example` and `CLAUDE.md`).
- `NEUROLEGAL_TEMPLATES_BASE_URL` — templates service endpoint for the agent
  and the RAG admin proxy (default `http://127.0.0.1:8003`; in the docker
  deploy set it to `http://templates:8003` in `.env.prod`).
  `NEUROLEGAL_TEMPLATES_S3_PREFIX` — key prefix for template .docx in the
  shared bucket (default `templates/`). The internal-token fail-fast
  (`NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true`) covers the templates service too.

## Deploy

Production is one VM behind Caddy: four services (`agent`, `rag`,
`documents`, `templates`) built from a single Docker image, sharing a managed
PostgreSQL over a private network and S3 for files. OpenRouter is unreachable
from Russian IPs, so LLM/embedding traffic routes through a
proxy node abroad (`HTTPS_PROXY`, see `docs/runbooks/llm-proxy.md`).

```bash
git tag vX.Y.Z && git push --tags
# GitHub Actions job `deploy` раскатывает тег на VM сама.
# Запасной путь с ноутбука:
make deploy TAG=vX.Y.Z DEPLOY_HOST=user@host
```

**A release is gated on CI, then rolled out automatically.**
`.github/workflows/ci.yml` runs lint, mypy strict, unit and mocked-integration
tests and both frontend builds on every push to `main`, every PR, and every
`v*` tag. A green run **on a tag** pushes a marker ref `refs/ci-passed/<sha>`
and SSHes to the VM (`deploy/github_remote.sh`) to run `deploy.sh`. The script
refuses to roll out a tag without the marker (`deploy/ci_gate.py`). No
registry is involved — the image is still built on the VM. The server reads
the marker with a read-only deploy key; Actions uses a separate SSH key
(`DEPLOY_SSH_KEY`). First-time server + secret setup: `deploy/CD.md`.
When GitHub itself is unreachable, `ALLOW_UNVERIFIED=1 make deploy TAG=…`
skips the gate and records the bypass in the journal.

Rollback is the same command with the previous tag — the server is a
read-only checkout of a tag, never edited in place. Migrations are additive
only (see `CLAUDE.md`): every `downgrade()` is destructive, so rollback never
touches the schema — only the code moves back. **The gate never blocks a
rollback:** returning to a commit that already ran in production is always
allowed, including tags cut before CI existed — otherwise the gate would trap
you exactly when production is broken.

Every rollout appends one line to `/var/log/neurolegal-deploys.log` (time,
tag, previous tag, origin of the SSH session, CI verdict, result, duration) —
written from a `trap`, so refused and failed rollouts are recorded too. Read
it with `make deploy-history`.

Before the first deploy on a new server, provision outside the repo:
`.env.prod` (from `.env.prod.example`, chmod 600), `tessdata/rus.traineddata`
next to the project (mounted into the `documents` container — never
downloaded during the image build, and it must be world-readable: the
container runs as uid 10001, so a root-owned 600 file makes `documents`
restart-loop with `PermissionError`), and a Docker Hub registry mirror in
`/etc/docker/daemon.json` (Docker Hub 429s anonymous pulls from Russian
cloud IPs). `deploy.sh` refuses to roll out if the OCR file is missing or
unreadable.

Set `NEUROLEGAL_DEPLOY_HOST` (an alias from `~/.ssh/config` works) and
`make deploy TAG=vX.Y.Z` needs no `DEPLOY_HOST=`. When users report the site
as unreachable, check it from several vantage points before suspecting the
config — a broken public IP looks exactly like a firewall or TLS problem.

Full rationale and the runbook (provisioning, corpus migration, incident
recovery, gotchas) live in `docs/superpowers/specs/2026-08-04-deploy-release-design.md`
and `docs/runbooks/deploy.md` — both local-only, `docs/` is gitignored.

## Tests

```bash
uv run pytest tests/unit                                    # offline; no env needed
uv run pytest tests/integration -m api_with_mocks           # ASGI + dependency overrides
DATABASE_URL=... uv run pytest tests/integration -m db_only  # against a real DB
DATABASE_URL=... OPENROUTER_API_KEY=... uv run pytest tests/integration -m e2e
```

Integration tests skip per-marker — see `tests/integration/conftest.py`.
