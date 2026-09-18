#!/usr/bin/env bash
# Идемпотентный провижининг VM. Запускает bootstrap_cd.py через ssh (stdin).
# Обязательные переменные: REPO (owner/name). Для MODE=setup ещё CD_PUBKEY.
set -euo pipefail

MODE="${MODE:?нужен MODE=setup|clone}"
DIR="${DEPLOY_DIR:-/srv/neurolegal}"
TESSDATA_URL="${TESSDATA_URL:-https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata}"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif sudo -n true 2>/dev/null; then
    sudo "$@"
  else
    echo "ОТКАЗ: нужен root или passwordless sudo для apt/docker и ${DIR}" >&2
    exit 3
  fi
}

ensure_packages() {
  if command -v docker >/dev/null 2>&1 && command -v git >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
    return 0
  fi
  export DEBIAN_FRONTEND=noninteractive
  as_root apt-get update -y
  as_root apt-get install -y git curl ca-certificates
  if ! command -v docker >/dev/null 2>&1; then
    as_root apt-get install -y docker.io docker-compose-v2 \
      || as_root apt-get install -y docker.io docker-compose
  fi
}

ensure_docker_group() {
  command -v docker >/dev/null 2>&1 || return 0
  if [ "$(id -u)" -ne 0 ]; then
    as_root usermod -aG docker "$(id -un)" || true
  fi
}

ensure_layout() {
  as_root mkdir -p "${DIR}" "${DIR}/tessdata"
  as_root chown -R "$(id -un):$(id -gn)" "${DIR}"
  as_root touch /var/log/neurolegal-deploys.log
  as_root chown "$(id -un):$(id -gn)" /var/log/neurolegal-deploys.log
}

ensure_github_deploy_key() {
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  if [ ! -f "${HOME}/.ssh/github_deploy" ]; then
    ssh-keygen -t ed25519 -f "${HOME}/.ssh/github_deploy" -N "" -C "neurolegal-vm-${REPO:-repo}"
  fi
  chmod 600 "${HOME}/.ssh/github_deploy"
  # ssh config: не затираем чужие Host-блоки, добавляем только если нет.
  if [ ! -f "${HOME}/.ssh/config" ] || ! grep -q 'IdentityFile ~/.ssh/github_deploy' "${HOME}/.ssh/config"; then
    cat >> "${HOME}/.ssh/config" <<'EOF'

Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
    chmod 600 "${HOME}/.ssh/config"
  fi
}

ensure_cd_authorized_key() {
  [ -n "${CD_PUBKEY:-}" ] || return 0
  mkdir -p "${HOME}/.ssh"
  touch "${HOME}/.ssh/authorized_keys"
  chmod 600 "${HOME}/.ssh/authorized_keys"
  if ! grep -Fqx "${CD_PUBKEY}" "${HOME}/.ssh/authorized_keys"; then
    printf '%s\n' "${CD_PUBKEY}" >> "${HOME}/.ssh/authorized_keys"
  fi
}

ensure_tessdata() {
  local target="${DIR}/tessdata/rus.traineddata"
  if [ ! -s "${target}" ]; then
    curl -fsSL -o "${target}" "${TESSDATA_URL}"
  fi
  chmod 644 "${target}"
}

print_github_deploy_pubkey() {
  echo "===NEUROLEGAL_GITHUB_DEPLOY_PUBKEY==="
  cat "${HOME}/.ssh/github_deploy.pub"
  echo "===END==="
}

clone_repo() {
  [ -n "${REPO:-}" ] || { echo "ОТКАЗ: REPO пуст" >&2; exit 3; }
  if [ ! -d "${DIR}/.git" ]; then
    GIT_SSH_COMMAND="ssh -i ${HOME}/.ssh/github_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
      git clone "git@github.com:${REPO}.git" "${DIR}"
  fi
  cd "${DIR}"
  if ! git config --get-all remote.origin.fetch 2>/dev/null | grep -q 'refs/ci-passed'; then
    git config --add remote.origin.fetch '+refs/ci-passed/*:refs/ci-passed/*'
  fi
}

case "${MODE}" in
  setup)
    [ -n "${REPO:-}" ] || { echo "ОТКАЗ: REPO пуст" >&2; exit 3; }
    [ -n "${CD_PUBKEY:-}" ] || { echo "ОТКАЗ: CD_PUBKEY пуст" >&2; exit 3; }
    ensure_packages
    ensure_docker_group
    ensure_layout
    ensure_github_deploy_key
    ensure_cd_authorized_key
    ensure_tessdata
    print_github_deploy_pubkey
    ;;
  clone)
    clone_repo
    ;;
  *)
    echo "ОТКАЗ: неизвестный MODE=${MODE}" >&2
    exit 3
    ;;
esac
