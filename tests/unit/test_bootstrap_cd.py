"""Тесты bootstrap_cd: чистые функции, без ssh/gh."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_BOOTSTRAP_PATH = Path(__file__).resolve().parents[2] / "deploy" / "bootstrap_cd.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_cd", _BOOTSTRAP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


boot = _load()


def test_parse_repo_slug_from_https_and_ssh() -> None:
    assert boot.parse_repo_slug("https://github.com/marcusaure1ius/yasa-tech.git") == (
        "marcusaure1ius/yasa-tech"
    )
    assert boot.parse_repo_slug("git@github.com:pulya-na-vullet/chprj.git") == (
        "pulya-na-vullet/chprj"
    )
    assert boot.parse_repo_slug("pulya-na-vullet/chprj") == "pulya-na-vullet/chprj"


def test_parse_repo_slug_rejects_garbage() -> None:
    with pytest.raises(boot.BootstrapError, match="непонятный репозиторий"):
        boot.parse_repo_slug("not a repo")


def test_parse_dotenv_skips_comments_and_export() -> None:
    text = """
# comment
DATABASE_URL=postgresql://x
export OPENROUTER_API_KEY="sk-or-v1-abc"
EMPTY=
"""
    parsed = boot.parse_dotenv(text)
    assert parsed["DATABASE_URL"] == "postgresql://x"
    assert parsed["OPENROUTER_API_KEY"] == "sk-or-v1-abc"
    assert parsed["EMPTY"] == ""


def test_apply_env_defaults_fills_public_url_and_token() -> None:
    filled = boot.apply_env_defaults({"NEUROLEGAL_DOMAIN": "yasa-tech.ru"})
    assert filled["NEUROLEGAL_PUBLIC_BASE_URL"] == "https://yasa-tech.ru"
    assert len(filled["NEUROLEGAL_INTERNAL_TOKEN"]) >= 32
    assert filled["NEUROLEGAL_COOKIE_SECURE"] == "true"


def test_missing_prod_keys() -> None:
    missing = boot.missing_prod_keys({"DATABASE_URL": "x", "OPENROUTER_API_KEY": ""})
    assert "DATABASE_URL" not in missing
    assert "OPENROUTER_API_KEY" in missing
    assert "NEUROLEGAL_DOMAIN" in missing


def test_escape_caddy_hash_doubles_dollars_once() -> None:
    raw = "$2a$14$abcdefghij"
    escaped = boot.escape_caddy_hash(raw)
    assert escaped == "$$2a$$14$$abcdefghij"
    assert boot.escape_caddy_hash(escaped) == escaped


def test_extract_deploy_pubkey() -> None:
    blob = """
docker ok
===NEUROLEGAL_GITHUB_DEPLOY_PUBKEY===
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake neurolegal-vm
===END===
done
"""
    assert boot.extract_deploy_pubkey(blob) == (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake neurolegal-vm"
    )


def test_github_action_secrets_omit_default_port() -> None:
    secrets_map = boot.github_action_secrets(
        host="10.0.0.1",
        user="ubuntu",
        port=22,
        private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nxyz",
    )
    assert secrets_map["DEPLOY_HOST"] == "10.0.0.1"
    assert secrets_map["DEPLOY_USER"] == "ubuntu"
    assert secrets_map["DEPLOY_SSH_KEY"].endswith("\n")
    assert "DEPLOY_PORT" not in secrets_map
    with_port = boot.github_action_secrets(
        host="10.0.0.1", user="ubuntu", port=2222, private_key="k\n"
    )
    assert with_port["DEPLOY_PORT"] == "2222"


def test_ssh_argv_skips_identities_only_without_identity() -> None:
    target = boot.SshTarget(
        host="10.0.0.1",
        user="ubuntu",
        port=22,
        identity=None,
        deploy_dir="/srv/neurolegal",
    )
    argv = boot.ssh_argv(target, "true")
    assert "IdentitiesOnly=yes" not in argv
    assert argv[-2:] == ["ubuntu@10.0.0.1", "true"]


def test_cd_key_stem() -> None:
    assert boot.cd_key_stem("pulya-na-vullet/chprj") == "neurolegal_cd_pulya-na-vullet_chprj"


def test_write_dotenv_updates_known_keys(tmp_path: Path) -> None:
    template = "# header\nDATABASE_URL=\nOPENROUTER_API_KEY=\nEXTRA=keep\n"
    path = tmp_path / ".env.prod"
    boot.write_dotenv(path, {"DATABASE_URL": "postgresql://db", "NEW": "1"}, template)
    text = path.read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql://db" in text
    assert "EXTRA=keep" in text
    assert "NEW=1" in text
    assert path.stat().st_mode & 0o777 == 0o600
