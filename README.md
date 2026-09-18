# Файлы автовыкатки для yasa-tech

Скопировать в корень клона `yasa-tech` с сохранением путей
(перезапишет `.github/workflows/ci.yml`).

```bash
cd yasa-tech
cp -a /путь/к/этой/папке/.github .
cp -a /путь/к/этой/папке/deploy/bootstrap_cd.py deploy/
cp -a /путь/к/этой/папке/deploy/github_remote.sh deploy/
cp -a /путь/к/этой/папке/deploy/provision_remote.sh deploy/
chmod +x deploy/bootstrap_cd.py deploy/github_remote.sh deploy/provision_remote.sh
git add .github/workflows/ci.yml deploy/bootstrap_cd.py deploy/github_remote.sh deploy/provision_remote.sh
git commit -m "Add GitHub Actions auto-deploy"
git push origin main
```

`.env.prod` здесь нет — его не кладут в git.

Дальше с ноутбука:

```bash
cp .env.prod.example .env.prod
python3 deploy/bootstrap_cd.py --host IP --user ubuntu --repo marcusaure1ius/yasa-tech --env-file .env.prod --release v0.1.0
```
