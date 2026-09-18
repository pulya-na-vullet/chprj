"""Pytest configuration and shared fixtures.

Unit tests don't need a real database, but they transitively import
``neurolegal.core.config.settings`` (pydantic-settings), which raises
``ValidationError`` at collection without ``DATABASE_URL``. To let unit
tests run with zero env:

1. Manually surface ``.env.local`` into ``os.environ`` so pydantic and the
   integration conftest see the same values (pydantic-settings reads
   ``.env.local`` itself, but only into the ``Settings`` object — it does
   not back-populate ``os.environ``).
2. Set a sentinel ``DATABASE_URL`` as a last resort.
   ``tests/integration/conftest.py`` checks for the sentinel and skips.
"""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).parent.parent / ".env.local"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        os.environ.setdefault(_key.strip(), _value.strip())

os.environ.setdefault("DATABASE_URL", "postgresql://_TEST_NO_DB_@localhost/_dummy_")
