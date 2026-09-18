"""RAG admin surface is unauthenticated by design — startup must say so (T-0031).

/admin/* has no auth and proxies account management to the agent; the operator
needs a loud reminder to keep the RAG service on loopback.
"""

import logging

import pytest

from neurolegal.rag.api.app import _warn_admin_open


def test_warn_admin_open_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _warn_admin_open()
    assert any("NEUROLEGAL_ADMIN_ENABLED" in r.message for r in caplog.records)
