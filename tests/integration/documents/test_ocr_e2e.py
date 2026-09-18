"""Реальный OCR: сканированный PDF → liteparse rus OCR → секции.

T-0103, пункт 5: тест стоял под маркером `e2e`, то есть требовал DATABASE_URL
и OPENROUTER_API_KEY — и потому не выполнялся никогда. Между тем `extract()`
не нуждается ни в БД, ни в ключе: это чистая функция над байтами. При этом
проверка единственная на весь путь PDF/rus-OCR.

Теперь маркер `api_with_mocks` (ничего не требует), и гейт остался только на
том, что действительно нужно: наличии `rus.traineddata`. Скачивать этот файл
в рантайме нельзя (см. операционные заметки), поэтому без данных — честный
skip, не поход в сеть.
"""

from pathlib import Path

import pytest

from neurolegal.documents.config import settings

pytestmark = pytest.mark.api_with_mocks

_FIXTURE = Path(__file__).parent / "fixtures" / "scanned_ru.pdf"
_TESSDATA = settings.tessdata_path / "rus.traineddata"


@pytest.mark.skipif(not _TESSDATA.is_file(), reason=f"нет OCR-данных: {_TESSDATA}")
def test_scanned_pdf_ocr_extracts_russian_text() -> None:
    from neurolegal.documents.processing.pipeline import extract

    result = extract(_FIXTURE.read_bytes(), "scanned_ru.pdf")
    assert result.parser == "pdf"
    assert result.page_count and result.page_count >= 1
    normalized = result.full_text.lower().replace("\n", " ")
    assert "договор" in normalized
