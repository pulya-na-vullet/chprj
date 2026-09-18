from pathlib import Path

ENV_PY = Path(__file__).resolve().parents[2] / "alembic" / "env.py"


def test_env_passes_connect_args_to_engine() -> None:
    """Иначе NEUROLEGAL_DB_STATEMENT_CACHE_SIZE=0 не действует на миграции
    и через pgbouncer в transaction-режиме они падают на prepared statements."""
    src = ENV_PY.read_text("utf-8")
    assert "asyncpg_connect_args" in src
    assert "connect_args" in src


def test_env_includes_documents_metadata() -> None:
    """Иначе autogenerate предложит удалить hub_documents/hub_document_attachments."""
    src = ENV_PY.read_text("utf-8")
    assert "neurolegal.documents.store.models" in src
    assert "DocumentsBase" in src


def test_env_includes_templates_metadata() -> None:
    """Иначе autogenerate предложит удалить tpl_templates."""
    src = ENV_PY.read_text("utf-8")
    assert "neurolegal.templates.store.models" in src
    assert "TemplatesBase" in src


def test_env_escapes_percent_for_configparser() -> None:
    """Пароль в DATABASE_URL бывает процентно-кодированным (%3B, %29).

    set_main_option кладёт URL в configparser, где "%" — начало интерполяции,
    поэтому без удвоения alembic падает на ValueError при боевом пароле.
    """
    src = ENV_PY.read_text("utf-8")
    assert '.replace("%", "%%")' in src
