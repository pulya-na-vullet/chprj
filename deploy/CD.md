# Автовыкатка из GitHub Actions

После зелёного CI на теге `v*` GitHub сам заходит по SSH на VM и запускает
`deploy/deploy.sh`. Образ собирается **на сервере**, не в Actions. Реестра
образов нет.

Раскатка с ветки `main` без тега не делается: прод — это checkout тега.

Полный ручной регламент релиза — `RELEASE.md`. Этот файл — что настроить
один раз, чтобы джоба `deploy` в `.github/workflows/ci.yml` заработала.

## Секреты GitHub

Repository → Settings → Secrets and variables → Actions → New repository secret.

| Secret | Что положить |
|---|---|
| `DEPLOY_HOST` | IP или hostname VM (как в `ssh user@…`) |
| `DEPLOY_USER` | linux-пользователь, который может `docker` и писать в `/srv/neurolegal` |
| `DEPLOY_SSH_KEY` | **приватная** половина ключа, которым Actions логинится на VM |
| `DEPLOY_PORT` | необязательно; по умолчанию `22` |

Это **не** deploy key репозитория. Два разных ключа:

1. **Actions → VM** (`DEPLOY_SSH_KEY`): GitHub запускает выкатку.
2. **VM → GitHub** (Deploy key, read-only): сервер делает `git fetch` и читает
   `refs/ci-passed/*`. Write access на ключ не включать.

## Один раз на сервере

Пакеты:

```bash
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# выйти из ssh и зайти снова
```

Если Docker Hub с российских IP отвечает 429 — registry mirror провайдера в
`/etc/docker/daemon.json`, затем `sudo systemctl restart docker`.

Каталог и журнал:

```bash
sudo mkdir -p /srv/neurolegal
sudo chown "$USER":"$USER" /srv/neurolegal
sudo touch /var/log/neurolegal-deploys.log
sudo chown "$USER":"$USER" /var/log/neurolegal-deploys.log
```

Ключ, которым сервер ходит в GitHub (read-only Deploy key):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Публичную часть — в GitHub: Settings → Deploy keys → Add deploy key
(Allow write access **выкл**).

`~/.ssh/config` на VM:

```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
```

Проверка: `ssh -T git@github.com`

Ключ, которым GitHub ходит на VM:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_cd -N ""
cat ~/.ssh/github_cd.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Содержимое **`~/.ssh/github_cd` (приватный файл)** целиком — в secret
`DEPLOY_SSH_KEY`. Файл на сервер можно не оставлять: нужен только публичный
хвост в `authorized_keys` и приватная часть в GitHub.

OCR (без этого `documents` не поднимется; контейнер — uid 10001, права 644):

```bash
mkdir -p /srv/neurolegal/tessdata
curl -fsSL -o /srv/neurolegal/tessdata/rus.traineddata \
  https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata
chmod 644 /srv/neurolegal/tessdata/rus.traineddata
```

Боевой env (в git не попадает):

```bash
# после первого клона репо окажется в /srv/neurolegal;
# до первой выкатки файл можно положить рядом заранее:
cp /srv/neurolegal/.env.prod.example /srv/neurolegal/.env.prod
chmod 600 /srv/neurolegal/.env.prod
```

Заполнить `DATABASE_URL`, `OPENROUTER_API_KEY`, `HTTPS_PROXY`, `NO_PROXY`,
`NEUROLEGAL_PUBLIC_BASE_URL`, `NEUROLEGAL_COOKIE_SECURE=true`,
`NEUROLEGAL_INTERNAL_TOKEN`, `NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true`,
`NEUROLEGAL_DOMAIN`, `NEUROLEGAL_ADMIN_USER`, `NEUROLEGAL_ADMIN_PASSWORD_HASH`,
`NEUROLEGAL_S3_*`. Комментарии — в `.env.prod.example`.

Хеш пароля админки для Caddy (каждый `$` удвоить):

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'ПАРОЛЬ' | sed 's/\$/$$/g'
```

DNS: A-записи apex, `www`, `admin` на IP VM. Порты 80 и 443 открыты.

Первый клон может сделать джоба `deploy` сама (если `/srv` писабелен). Либо:

```bash
git clone git@github.com:OWNER/REPO.git /srv/neurolegal
git -C /srv/neurolegal config --add remote.origin.fetch '+refs/ci-passed/*:refs/ci-passed/*'
```

`OWNER/REPO` — репозиторий, из которого идёт Actions (для этой копии —
`pulya-na-vullet/chprj`; для исходного проекта — `marcusaure1ius/yasa-tech`).

## Как выкатить

В `main` уже зелёный CI, секреты заданы, сервер провиженен:

```bash
git checkout main && git pull
git tag v0.1.0 -m "first production deploy"
git push origin main --tags
```

Дальше смотреть Actions: jobs `backend`, `frontend`, `mark`, `deploy`.
Ноутбук и `make deploy` не нужны. Ручной запасной путь тот же, что раньше:

```bash
make deploy TAG=v0.1.0 DEPLOY_HOST=user@host
```

Откат — тег предыдущей версии (гейт откат не блокирует, схему БД не трогает):

```bash
git tag v0.1.0   # уже существует — не переставлять
# выкатить старый тег вручную:
make deploy TAG=v0.1.0 DEPLOY_HOST=user@host
```

Автоматический откат из Actions нет: джоба `deploy` срабатывает только на
push **нового** тега `v*`. Откат — с машины, у которой есть SSH на VM.

## Если джоба deploy красная

| Сообщение | Что сделать |
|---|---|
| нет secret DEPLOY_* | задать три секрета, перезапустить job |
| Permission denied (publickey) | публичный ключ не в `authorized_keys` или не тот пользователь |
| нет каталога /srv | создать `/srv/neurolegal` и отдать пользователю `DEPLOY_USER` |
| `ssh: connect to host` | firewall / неверный IP / не 22 порт |
| нет отметки CI | job `mark` не прошёл или GitHub недоступен с VM |
| нет tessdata / права | команды из вывода `deploy.sh` |
| Docker Hub 429 | mirror в `daemon.json` |
| `.env.prod` / compose | файл на сервере, chmod 600, заполнены URL и токены |

Логи на VM: `docker compose -f /srv/neurolegal/docker-compose.prod.yml logs --tail=100`
и `/var/log/neurolegal-deploys.log`.
