import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from neurolegal.core.config import settings

_HANDLER_TAG = "_neurolegal_json_handler"


def configure_logging() -> None:
    """Install our JSON handler on the root logger.

    Idempotent: re-installing replaces our prior handler, but does not touch
    foreign handlers (e.g. pytest's caplog handler), so test infra is preserved.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level"},
        )
    )
    setattr(handler, _HANDLER_TAG, True)

    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, _HANDLER_TAG, False)]
    root.addHandler(handler)
    root.setLevel(settings.log_level)
