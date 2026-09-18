from neurolegal.agent.store.models import Base, ConversationRow, MessageRow


def test_table_names() -> None:
    assert ConversationRow.__tablename__ == "conversations"
    assert MessageRow.__tablename__ == "messages"


def test_message_columns() -> None:
    cols = {c.name for c in MessageRow.__table__.columns}
    assert cols == {
        "id",
        "conversation_id",
        "ordinal",
        "role",
        "content",
        "citations",
        "web_sources",
        "review",
        "stopped",
        "ask",
        "template_draft",
        "template_doc",
        "created_at",
    }


def test_message_ask_column_is_nullable() -> None:
    col = MessageRow.__table__.c.ask
    assert col.nullable is True


def test_models_share_one_metadata() -> None:
    assert ConversationRow.metadata is Base.metadata
    assert MessageRow.metadata is Base.metadata


def test_client_side_uuid_default() -> None:
    # IDs default via a Python-side callable, with no server_default, so the
    # same models run on SQLite in tests and Postgres in production.
    for col in (ConversationRow.__table__.c.id, MessageRow.__table__.c.id):
        assert col.default is not None
        assert col.default.is_callable
        assert col.server_default is None
