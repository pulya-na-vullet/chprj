#!/usr/bin/env bash
# Выкатка тега на сервере. Запускать из каталога проекта.
#   ./deploy/deploy.sh v0.3.0
set -euo pipefail

TAG="${1:?использование: deploy.sh <тег>}"
export COMPOSE_FILE=docker-compose.prod.yml
export TAG

PREV_TAG="$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD)"

DEPLOY_LOG="${DEPLOY_LOG:-/var/log/neurolegal-deploys.log}"
STARTED_AT="$(date +%s)"
CI_VERDICT="unknown"

# Журнал пишется через trap, а не в конце скрипта: упавшая и прерванная
# выкатки — самые интересные записи в истории, и именно они не дошли бы до
# последней строки.
journal() {
  local rc="$1" result who
  case "${rc}" in
    0) result=ok ;;
    3) result=refused ;;
    *) result=fail ;;
  esac
  # SSH_CLIENT задана только при запуске по ssh; при set -u её отсутствие
  # уронило бы сам журнал — то есть ровно тогда, когда запись важнее всего.
  who="${SSH_CLIENT:-}"
  who="${who%% *}"
  [ -n "${who}" ] || who=local
  printf '%s\t%s\tprev=%s\twho=%s@%s\tci=%s\tresult=%s\t%ss\n' \
    "$(date +%Y-%m-%dT%H:%M:%S%z)" "${TAG}" "${PREV_TAG}" "$(id -un)" "${who}" \
    "${CI_VERDICT}" "${result}" "$(( $(date +%s) - STARTED_AT ))" \
    >>"${DEPLOY_LOG}" 2>/dev/null \
    || echo "предупреждение: не удалось записать журнал ${DEPLOY_LOG}" >&2
}
trap 'journal "$?"' EXIT

echo "==> текущая версия: ${PREV_TAG}; выкатываем ${TAG}"
echo "==> последние выкатки"
tail -n 3 "${DEPLOY_LOG}" 2>/dev/null || echo "(журнала ещё нет)"

git fetch --tags --prune origin
# Метки CI лежат в своём namespace и стандартным refspec не тянутся.
git fetch --force origin "+refs/ci-passed/*:refs/ci-passed/*" || true

# Админка правит corpus/manifest.yaml на живой системе, а ниже идёт checkout
# тега — на изменённом отслеживаемом файле он откажется переключаться уже после
# начала выкатки. Проверяем заранее и объясняем, что делать.
if ! git diff --quiet -- corpus/manifest.yaml; then
  echo "ОТКАЗ: corpus/manifest.yaml изменён на сервере (правки через админку)."
  echo "Закоммитьте их в репозиторий либо отбросьте:"
  echo "  git -C \"$(pwd)\" checkout -- corpus/manifest.yaml"
  exit 3
fi

# Гейт: тег принадлежит main и на его коммите зелёный CI. Отказ — до checkout,
# то есть до любых изменений на сервере.
echo "==> гейт CI"
CI_VERDICT="$(python3 deploy/ci_gate.py --tag "${TAG}" --current-sha "$(git rev-parse HEAD)")" \
  || exit 3

git checkout "${TAG}"

echo "==> сборка образа (старые контейнеры продолжают работать)"
docker compose build

# JobManager держит состояние в памяти, а bulk-ингест сбрасывает и пересоздаёт
# HNSW/GIN в try/finally. Контейнер, убитый посреди джоба, оставит прод без
# поисковых индексов — молча, без ошибок в логах.
echo "==> проверка активного ingest-джоба"
if docker compose ps --status running --services | grep -qx rag; then
  ACTIVE="$(docker compose exec -T rag python -c "
import json, urllib.request
data = json.load(urllib.request.urlopen('http://127.0.0.1:8001/admin/jobs'))
print(json.dumps(data.get('active')))
" 2>/dev/null || echo null)"
  if [ "${ACTIVE}" != "null" ]; then
    echo "ОТКАЗ: в rag выполняется ingest-джоб: ${ACTIVE}"
    echo "Дождитесь его завершения и повторите."
    exit 3
  fi
fi

# Файлы, которые монтируются с хоста, обязаны быть доступны пользователю
# контейнера (uid 10001). Оба уже ломали прод: rus.traineddata с правами 600 от
# root давал бесконечный перезапуск documents с PermissionError, а нечитаемый
# corpus/manifest.yaml — 500 на всех экранах админки. Симптомы обманчивые:
# файлы на месте и нужного размера.
echo "==> проверка данных на хосте"
require_readable() {
  path="$1"
  hint="$2"
  if [ ! -f "${path}" ]; then
    echo "ОТКАЗ: нет ${path}"
    echo "${hint}"
    exit 3
  fi
  # GNU stat на сервере, BSD stat на macOS; пустой режим означает отказ, не «ок»
  mode="$(stat -c '%a' "${path}" 2>/dev/null || stat -f '%Lp' "${path}" 2>/dev/null || true)"
  if [ -z "${mode}" ]; then
    echo "ОТКАЗ: не удалось определить права ${path} — проверьте вручную."
    exit 3
  fi
  if [ "${mode: -1}" -lt 4 ]; then
    echo "ОТКАЗ: ${path} (права ${mode}) недоступен пользователю контейнера (uid 10001)."
    echo "Исправьте: chmod 644 ${path}"
    exit 3
  fi
}

require_readable "tessdata/rus.traineddata" \
  "Положите файл: mkdir -p tessdata && curl -fsSL -o tessdata/rus.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
require_readable "corpus/manifest.yaml" \
  "Манифест приходит из чекаута репозитория — проверьте, что вы в каталоге проекта."

echo "==> миграции"
docker compose run --rm agent neurolegal migrate

echo "==> пересоздание сервисов"
docker compose up -d

echo "==> проверка"
sleep 10
FAILED=0
# curl в образе нет (apt выпилен: deb.debian.org недоступен из РФ), поэтому
# проверяем stdlib-питоном. /acts у агента не годится — он закрыт авторизацией
# и без сессии отдаёт 401; связь с БД доказывает rag, он ходит в неё в /healthz.
probe() {
  docker compose exec -T "$1" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$2/healthz', timeout=10)" \
    >/dev/null 2>&1
}
probe rag 8001       || { echo "ОШИБКА: rag /healthz (БД недоступна?)"; FAILED=1; }
probe agent 8000     || { echo "ОШИБКА: agent /healthz"; FAILED=1; }
probe documents 8002 || { echo "ОШИБКА: documents /healthz (tessdata? S3?)"; FAILED=1; }
probe templates 8003 || { echo "ОШИБКА: templates /healthz (internal token не задан при REQUIRE?)"; FAILED=1; }

if [ "${FAILED}" -ne 0 ]; then
  echo
  echo "Откат: ./deploy/deploy.sh ${PREV_TAG}"
  echo "Схему БД откат НЕ трогает — миграции аддитивны по правилу из CLAUDE.md."
  exit 1
fi

echo "==> ${TAG} выкачен"
