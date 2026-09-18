"""Startup checks: things that must hold before the hub accepts traffic.

liteparse otherwise downloads `<lang>.traineddata` from the network on first
OCR, which fails in air-gapped/container deploys. We provision the data and
fail fast if it is missing rather than silently reach out to the network.

`check_internal_token` guards the agent<->hub shared secret the same way:
if the operator has opted into requiring it (NEUROLEGAL_REQUIRE_INTERNAL_TOKEN)
but never configured it, that's a misconfiguration worth crashing on rather
than silently running the hub open.
"""

from pathlib import Path


class PreflightError(RuntimeError):
    pass


def check_tessdata(tessdata_path: Path, *, language: str = "rus") -> None:
    expected = tessdata_path / f"{language}.traineddata"
    if not expected.is_file():
        raise PreflightError(
            f"OCR-данные не найдены: ожидается {expected}. "
            f"Скачайте {language}.traineddata (tesseract-ocr tessdata) в "
            f"NEUROLEGAL_TESSDATA_PATH перед запуском сервиса."
        )


def check_internal_token(require_internal_token: bool, internal_token: str | None) -> None:
    if require_internal_token and not internal_token:
        raise PreflightError(
            "NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true, но NEUROLEGAL_INTERNAL_TOKEN не задан. "
            "Задайте общий секрет агента и хаба перед запуском сервиса."
        )
