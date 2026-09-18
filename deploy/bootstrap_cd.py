#!/usr/bin/env python3
"""One-shot laptop bootstrap: provision the VM and GitHub Actions deploy secrets.

Stdlib only — run with system python3, no uv. Requires ssh and gh in PATH
(`gh auth login` needs permission to write secrets and deploy keys).

  python3 deploy/bootstrap_cd.py --host 1.2.3.4 --user ubuntu --env-file .env.prod
"""

from __future__ import annotations

import argparse
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROVISION_REMOTE = SCRIPT_DIR / "provision_remote.sh"
DEFAULT_DEPLOY_DIR = "/srv/neurolegal"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
PUBKEY_RE = re.compile(
    r"===NEUROLEGAL_GITHUB_DEPLOY_PUBKEY===\n(?P<key>ssh-(?:ed25519|rsa) [^\n]+)\n===END===",
    re.MULTILINE,
)
_REMOTE_RE = re.compile(
    r"^(?:git@github\.com:|https://github\.com/)(?P<slug>[^/]+/[^/]+?)(?:\.git)?$"
)
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

REQUIRED_PROD_KEYS: tuple[str, ...] = (
    "DATABASE_URL",
    "OPENROUTER_API_KEY",
    "NEUROLEGAL_DOMAIN",
    "NEUROLEGAL_PUBLIC_BASE_URL",
    "NEUROLEGAL_INTERNAL_TOKEN",
    "NEUROLEGAL_ADMIN_USER",
    "NEUROLEGAL_ADMIN_PASSWORD_HASH",
    "NEUROLEGAL_S3_BUCKET",
    "NEUROLEGAL_S3_ACCESS_KEY",
    "NEUROLEGAL_S3_SECRET_KEY",
)

GITHUB_SECRET_NAMES: tuple[str, ...] = (
    "DEPLOY_HOST",
    "DEPLOY_USER",
    "DEPLOY_SSH_KEY",
    "DEPLOY_PORT",
)

Run = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SshTarget:
    host: str
    user: str
    port: int
    identity: Path | None
    deploy_dir: str


class BootstrapError(RuntimeError):
    """Ожидаемый отказ: нет инструмента, пустой env, gh отклонил ключ."""


def parse_repo_slug(value: str) -> str:
    """owner/name из URL origin или уже готовый slug."""
    stripped = value.strip()
    match = _REMOTE_RE.match(stripped)
    if match is not None:
        return match.group("slug")
    if _SLUG_RE.match(stripped):
        return stripped
    raise BootstrapError(f"непонятный репозиторий: {value!r} (нужен owner/name)")


def parse_dotenv(text: str) -> dict[str, str]:
    """Плоский KEY=VALUE без multiline. Пустые значения сохраняются."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        out[key] = value
    return out


def missing_prod_keys(env: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(key for key in REQUIRED_PROD_KEYS if not env.get(key, "").strip())


def apply_env_defaults(env: Mapping[str, str]) -> dict[str, str]:
    """Домен → публичный URL; пустой internal token → сгенерировать."""
    filled = dict(env)
    domain = filled.get("NEUROLEGAL_DOMAIN", "").strip()
    if domain and not filled.get("NEUROLEGAL_PUBLIC_BASE_URL", "").strip():
        filled["NEUROLEGAL_PUBLIC_BASE_URL"] = f"https://{domain}"
    if not filled.get("NEUROLEGAL_INTERNAL_TOKEN", "").strip():
        filled["NEUROLEGAL_INTERNAL_TOKEN"] = secrets.token_urlsafe(32)
    if not filled.get("NEUROLEGAL_COOKIE_SECURE", "").strip():
        filled["NEUROLEGAL_COOKIE_SECURE"] = "true"
    if not filled.get("NEUROLEGAL_REQUIRE_INTERNAL_TOKEN", "").strip():
        filled["NEUROLEGAL_REQUIRE_INTERNAL_TOKEN"] = "true"
    return filled


def escape_caddy_hash(raw: str) -> str:
    """docker compose ест `$` в env_file как интерполяцию — удваиваем."""
    stripped = raw.strip()
    if "$$" in stripped:
        return stripped
    return stripped.replace("$", "$$")


def github_action_secrets(
    *,
    host: str,
    user: str,
    port: int,
    private_key: str,
) -> dict[str, str]:
    secrets_map = {
        "DEPLOY_HOST": host,
        "DEPLOY_USER": user,
        "DEPLOY_SSH_KEY": private_key if private_key.endswith("\n") else private_key + "\n",
    }
    if port != 22:
        secrets_map["DEPLOY_PORT"] = str(port)
    return secrets_map


def extract_deploy_pubkey(output: str) -> str:
    match = PUBKEY_RE.search(output)
    if match is None:
        raise BootstrapError(
            "не удалось прочитать github_deploy.pub с сервера — нет маркера в выводе ssh"
        )
    return match.group("key").strip()


def cd_key_stem(repo_slug: str) -> str:
    return "neurolegal_cd_" + repo_slug.replace("/", "_")


def ssh_argv(target: SshTarget, *remote: str) -> list[str]:
    argv = [
        "ssh",
        "-p",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ServerAliveInterval=15",
    ]
    if target.identity is not None:
        # IdentitiesOnly only together with -i; otherwise ssh-agent is ignored.
        argv.extend(["-i", str(target.identity), "-o", "IdentitiesOnly=yes"])
    argv.append(f"{target.user}@{target.host}")
    argv.extend(remote)
    return argv


def scp_argv(target: SshTarget, local: Path, remote_path: str) -> list[str]:
    argv = [
        "scp",
        "-P",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if target.identity is not None:
        argv.extend(["-i", str(target.identity), "-o", "IdentitiesOnly=yes"])
    argv.extend([str(local), f"{target.user}@{target.host}:{remote_path}"])
    return argv


def _run(
    argv: Sequence[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(argv),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise BootstrapError(f"команда {argv[0]} упала ({completed.returncode}): {detail}")
    return completed


def require_tools(names: Sequence[str]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise BootstrapError("установите и добавьте в PATH: " + ", ".join(missing))


def ensure_cd_keypair(path: Path, *, run: Run = _run) -> tuple[Path, Path]:
    """Приватный + публичный ed25519 для Actions → VM. Существующий не трогаем."""
    private = path
    public = path.with_suffix(".pub")
    if private.is_file() and public.is_file():
        return private, public
    private.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(private),
            "-N",
            "",
            "-C",
            "github-actions-neurolegal-cd",
        ]
    )
    private.chmod(0o600)
    return private, public


def ssh_pipe(
    target: SshTarget,
    env: Mapping[str, str],
    script: str,
    *,
    run: Run = _run,
) -> subprocess.CompletedProcess[str]:
    assignment = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    remote = f"{assignment} bash -s"
    return run(ssh_argv(target, remote), input_text=script)


def gh_repo_ok(slug: str, *, run: Run = _run) -> None:
    run(["gh", "repo", "view", slug, "--json", "name"])


def gh_add_deploy_key(
    slug: str,
    pubkey: str,
    *,
    title: str,
    run: Run = _run,
) -> None:
    listed = run(["gh", "api", f"repos/{slug}/keys"])
    if pubkey.split()[1] in listed.stdout:
        return
    completed = run(
        [
            "gh",
            "api",
            f"repos/{slug}/keys",
            "-f",
            f"title={title}",
            "-f",
            f"key={pubkey}",
            "-F",
            "read_only=true",
        ],
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout).strip()
        if "key is already in use" in err.lower() or '"already_exists"' in err:
            return
        raise BootstrapError(f"не удалось добавить deploy key: {err}")


def gh_set_secrets(slug: str, values: Mapping[str, str], *, run: Run = _run) -> None:
    for name, value in values.items():
        run(["gh", "secret", "set", name, "--repo", slug, "--body", value])


def write_dotenv(path: Path, env: Mapping[str, str], template: str) -> None:
    """Обновляет значения известных ключей в шаблоне, остальное дописывает."""
    seen: set[str] = set()
    lines: list[str] = []
    for raw in template.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in env:
                lines.append(f"{key}={env[key]}")
                seen.add(key)
                continue
        lines.append(raw)
    for key, value in env.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise BootstrapError(f"нет файла {path}")
    return apply_env_defaults(parse_dotenv(path.read_text(encoding="utf-8")))


def bootstrap(args: argparse.Namespace, *, run: Run = _run) -> int:
    require_tools(("ssh", "scp", "ssh-keygen", "gh", "git"))
    if not PROVISION_REMOTE.is_file():
        raise BootstrapError(f"нет {PROVISION_REMOTE}")

    slug = parse_repo_slug(args.repo)
    target = SshTarget(
        host=args.host,
        user=args.user,
        port=args.port,
        identity=Path(args.identity).expanduser() if args.identity else None,
        deploy_dir=args.deploy_dir,
    )
    script = PROVISION_REMOTE.read_text(encoding="utf-8")

    print(f"==> репозиторий {slug}", file=sys.stderr)
    gh_repo_ok(slug, run=run)

    ssh_dir = Path.home() / ".ssh"
    private, public = ensure_cd_keypair(ssh_dir / cd_key_stem(slug), run=run)
    cd_pub = public.read_text(encoding="utf-8").strip()
    cd_priv = private.read_text(encoding="utf-8")

    print(f"==> ssh {target.user}@{target.host} (setup)", file=sys.stderr)
    setup = ssh_pipe(
        target,
        {
            "MODE": "setup",
            "REPO": slug,
            "CD_PUBKEY": cd_pub,
            "DEPLOY_DIR": target.deploy_dir,
            "TESSDATA_URL": TESSDATA_URL,
        },
        script,
        run=run,
    )
    sys.stderr.write(setup.stdout)
    if setup.stderr:
        sys.stderr.write(setup.stderr)
    vm_pubkey = extract_deploy_pubkey(setup.stdout + "\n" + setup.stderr)

    print("==> GitHub deploy key (read-only)", file=sys.stderr)
    gh_add_deploy_key(slug, vm_pubkey, title=f"neurolegal-vm-{target.host}", run=run)

    print("==> GitHub Actions secrets", file=sys.stderr)
    gh_set_secrets(
        slug,
        github_action_secrets(
            host=target.host,
            user=target.user,
            port=target.port,
            private_key=cd_priv,
        ),
        run=run,
    )

    print(f"==> ssh {target.user}@{target.host} (clone)", file=sys.stderr)
    cloned = ssh_pipe(
        target,
        {"MODE": "clone", "REPO": slug, "DEPLOY_DIR": target.deploy_dir},
        script,
        run=run,
    )
    sys.stderr.write(cloned.stdout)
    if cloned.stderr:
        sys.stderr.write(cloned.stderr)

    if args.env_file is not None:
        env_path = Path(args.env_file).expanduser()
        env = load_env_file(env_path)
        missing = missing_prod_keys(env)
        if missing:
            raise BootstrapError("в env-файле пусто: " + ", ".join(missing))
        if args.write_env:
            example = (SCRIPT_DIR.parent / ".env.prod.example").read_text(encoding="utf-8")
            write_dotenv(env_path, env, example)
        remote_env = f"{target.deploy_dir}/.env.prod"
        print(f"==> scp {env_path} → {remote_env}", file=sys.stderr)
        run(scp_argv(target, env_path, remote_env))
        run(ssh_argv(target, f"chmod 600 {shlex.quote(remote_env)}"))

    if args.release:
        tag: str = args.release
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
            raise BootstrapError(f"тег {tag!r} не похож на vX.Y.Z")
        if args.env_file is None:
            raise BootstrapError("--release нужен вместе с --env-file: иначе прод не поднимется")
        print(f"==> git tag {tag} && git push --tags", file=sys.stderr)
        existing = run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], check=False)
        if existing.returncode != 0:
            run(["git", "tag", tag, "-m", args.release_message or tag])
        run(["git", "push", "origin", "main", "--tags"])
        print(
            f"дальше — Actions: https://github.com/{slug}/actions",
            file=sys.stderr,
        )

    print("готово. следующий релиз: git tag vX.Y.Z && git push origin --tags", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="провижининг VM и секретов GitHub для автовыкатки neurolegal",
    )
    parser.add_argument("--host", required=True, help="IP или hostname VM")
    parser.add_argument("--user", required=True, help="ssh-пользователь на VM")
    parser.add_argument("--port", type=int, default=22, help="ssh-порт (по умолчанию 22)")
    parser.add_argument("--identity", help="приватный ключ, которым вы уже заходите на VM")
    parser.add_argument(
        "--repo",
        default="",
        help="owner/name; по умолчанию origin текущего клона",
    )
    parser.add_argument("--deploy-dir", default=DEFAULT_DEPLOY_DIR)
    parser.add_argument(
        "--env-file",
        help="готовый .env.prod (скопируется на VM как /srv/neurolegal/.env.prod)",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="дописать в --env-file сгенерированный INTERNAL_TOKEN и PUBLIC_BASE_URL",
    )
    parser.add_argument(
        "--release",
        metavar="vX.Y.Z",
        help="после провижининга поставить тег и запушить — Actions сам выкатит",
    )
    parser.add_argument("--release-message", default="", help="сообщение git tag")
    return parser


def resolve_repo(explicit: str, *, run: Run = _run) -> str:
    if explicit.strip():
        return parse_repo_slug(explicit)
    origin = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    if not origin:
        raise BootstrapError("задайте --repo owner/name: у клона нет origin")
    return parse_repo_slug(origin)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.repo = resolve_repo(args.repo)
        return bootstrap(args)
    except BootstrapError as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
