# Файлы автовыкатки для yasa-tech

Скопировать в корень клона `yasa-tech` с сохранением путей
(перезапишет `.github/workflows/ci.yml`).

```bash
cd yasa-tech
git checkout main
git pull
git checkout -b add-github-auto-deploy

cp -a /путь/к/этой/папке/.github .
cp -a /путь/к/этой/папке/deploy/bootstrap_cd.py deploy/
cp -a /путь/к/этой/папке/deploy/github_remote.sh deploy/
cp -a /путь/к/этой/папке/deploy/provision_remote.sh deploy/
chmod +x deploy/bootstrap_cd.py deploy/github_remote.sh deploy/provision_remote.sh

git add .github/workflows/ci.yml deploy/bootstrap_cd.py deploy/github_remote.sh deploy/provision_remote.sh
git commit -m "Add GitHub Actions auto-deploy"
git push -u origin add-github-auto-deploy
```

Дальше на GitHub: PR `add-github-auto-deploy` → `main`. Не пушить сразу в `main`.

`bootstrap_cd.py --release` запускать **после merge** в `main`: гейт выкатки принимает только теги с `main`.

`.env.prod` здесь нет — его не кладут в git.

После merge PR, с ноутбука:

```bash
git checkout main && git pull
cp .env.prod.example .env.prod
python3 deploy/bootstrap_cd.py --host IP --user ubuntu --repo marcusaure1ius/yasa-tech --env-file .env.prod --release v0.1.0
```
