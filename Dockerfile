# syntax=docker/dockerfile:1

# ---------- фронт: два бандла (чат + админка) ----------
FROM node:22-slim AS frontend
WORKDIR /build
# impeccable (devDep) тянет puppeteer с install-скриптом: ~150 МБ Chrome с
# storage.googleapis.com. С российской VM это зависание на таймаутах.
ENV PUPPETEER_SKIP_DOWNLOAD=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Оба билда включают `tsc --noEmit` — ошибка типов валит сборку образа. Так и задумано.
RUN npm run build && npm run build:admin

# ---------- рантайм ----------
FROM python:3.12-slim AS runtime

# Никакого apt: с российских адресов deb.debian.org не отвечает, а зеркало
# провайдера проксирует только Docker Hub. ca-certificates уже есть в
# python:3.12-slim (иначе не работал бы pip), curl не нужен — healthcheck'и
# в compose сделаны на stdlib-питоне.

# uv ставим из PyPI, а не образом с ghcr.io: с российских адресов ghcr.io
# недоступен (i/o timeout), а Docker Hub закрыт зеркалом провайдера. Версия
# закреплена — та же, что у разработчика, чтобы uv.lock (revision 3) читался
# без сюрпризов.
RUN pip install --no-cache-dir uv==0.11.14

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    NEUROLEGAL_TESSDATA_PATH=/opt/tessdata

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# rus.traineddata НЕ качается в сборке: github.com с сервера доступен
# нестабильно, а лишний внешний источник в конвейере выкатки — лишний отказ.
# Файл провижинится один раз на хосте и монтируется в /opt/tessdata
# read-only (см. docker-compose.prod.yml и раздел «Деплой» в README).
# Каталог создаём здесь, чтобы preflight хаба падал с внятной ошибкой,
# если том забыли смонтировать.
RUN mkdir -p /opt/tessdata

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY playbooks/ ./playbooks/
# pyproject.toml объявляет readme = "README.md" — второй `uv sync` (без
# --no-install-project) собирает сам пакет neurolegal и падает на
# hatchling.metadata.core.readme без этого файла.
COPY README.md ./
COPY --from=frontend /src/neurolegal/agent/api/static/ ./src/neurolegal/agent/api/static/
COPY --from=frontend /src/neurolegal/rag/api/static/ ./src/neurolegal/rag/api/static/

RUN uv sync --frozen --no-dev

# Тома монтируются в /app/data — каталог должен существовать и принадлежать
# непривилегированному пользователю ДО объявления тома, иначе docker создаст
# его от root и загрузка файлов упадёт с EACCES.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app /opt/tessdata
USER app

EXPOSE 8000 8001 8002
