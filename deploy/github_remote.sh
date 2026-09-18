#!/usr/bin/env bash
# Запускается на боевой VM из GitHub Actions (stdin через ssh).
# Переменные задаёт workflow: TAG, REPO (owner/name). Неинтерактивно.
set -euo pipefail

TAG="${TAG:?нужен TAG (например v0.1.0)}"
REPO="${REPO:?нужен REPO (owner/name)}"
DIR="${DEPLOY_DIR:-/srv/neurolegal}"

echo "==> GitHub CD: ${REPO} @ ${TAG} → ${DIR}"

if [ ! -d "${DIR}/.git" ]; then
  parent="$(dirname "${DIR}")"
  echo "==> первый клон в ${DIR}"
  if [ ! -d "${parent}" ]; then
    echo "ОТКАЗ: нет каталога ${parent}."
    echo "На сервере один раз: sudo mkdir -p ${parent} && sudo chown \$(id -un):\$(id -gn) ${parent}"
    exit 3
  fi
  if [ ! -w "${parent}" ]; then
    echo "ОТКАЗ: нет прав писать в ${parent}."
    echo "На сервере один раз: sudo mkdir -p ${DIR} && sudo chown \$(id -un):\$(id -gn) ${DIR}"
    exit 3
  fi
  git clone "git@github.com:${REPO}.git" "${DIR}"
fi

cd "${DIR}"

if ! git config --get-all remote.origin.fetch 2>/dev/null | grep -q 'refs/ci-passed'; then
  git config --add remote.origin.fetch '+refs/ci-passed/*:refs/ci-passed/*'
fi

chmod +x deploy/deploy.sh

# mark только что запушил refs/ci-passed/<sha>; короткая пауза, чтобы fetch
# с сервера не обогнал видимость ссылки на github.com.
sleep 5

./deploy/deploy.sh "${TAG}"
