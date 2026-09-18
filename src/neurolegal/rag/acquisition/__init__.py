from typing import Protocol

from neurolegal.core.domain import RawDocument


class Acquirer(Protocol):
    async def fetch(self, code_id: str) -> RawDocument: ...


__all__ = ["Acquirer"]
